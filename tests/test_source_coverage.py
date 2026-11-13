"""Acceptance tests for all macro, market and FX histories, without live network."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from finance_dashboard.api import create_app
from finance_dashboard.catalog import load_documents
from finance_dashboard.database import (
    Base, SeriesRow, IngestionRun, ObservationVersion, MarketInstrumentRow,
    MarketIngestionRun, MarketPriceVersion, FxIngestionRun, FxRateVersion,
)
from finance_dashboard.market import instruments
from finance_dashboard.source_coverage import build_coverage


NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)


class SourceCoverageTests(unittest.TestCase):
    def test_observation_freshness_is_independent_of_deferred_or_successful_refresh(self):
        self.add_macro('activity.us.oecd_cli', status='deferred', when=date(2026, 10, 1),
                       error='source_policy_deferred')
        self.add_macro('activity.jp.oecd_cli', status='success', when=date(2020, 1, 1))
        report = build_coverage(self.engine, self.catalog, self.registry, asof=date(2026, 11, 11))
        rows = {r['id']: r for r in report['items']}
        self.assertEqual(rows['activity.us.oecd_cli']['observation_state'], 'current')
        self.assertEqual(rows['activity.us.oecd_cli']['refresh_state'], 'deferred')
        self.assertEqual(rows['activity.us.oecd_cli']['state'], 'available')
        self.assertEqual(rows['activity.us.oecd_cli']['last_failure_code'],
                         'source_policy_deferred')
        self.assertEqual(report['summary']['macro']['deferred_attempts_with_data'], 1)
        self.assertEqual(report['summary']['macro']['deferred_attempts_current_data'], 1)
        self.assertEqual(report['summary']['macro']['deferred_attempts_stale_data'], 0)
        self.assertEqual(report['summary']['macro']['needs_attention'], len(self.catalog) - 1)
        self.assertIn('C01', rows['activity.us.oecd_cli']['research_questions'])
        self.assertIn('deferred', rows['activity.us.oecd_cli']['next_action'].lower())
        self.assertEqual(rows['activity.jp.oecd_cli']['observation_state'], 'stale')
        self.assertEqual(rows['activity.jp.oecd_cli']['refresh_state'], 'success')
        self.assertEqual(rows['gold.usd.spot']['observation_state'], 'missing')

    def test_stale_deferred_history_still_requires_attention(self):
        self.add_macro('activity.us.oecd_cli', status='deferred',
                       when=date(2022, 1, 1), error='source_policy_deferred')
        report = build_coverage(self.engine, self.catalog, self.registry,
                                asof=date(2026, 11, 13))
        item = next(row for row in report['items']
                    if row['id'] == 'activity.us.oecd_cli')
        self.assertEqual(item['state'], 'refresh_deferred_with_data')
        self.assertEqual(item['observation_state'], 'stale')
        self.assertEqual(item['refresh_state'], 'deferred')
        self.assertEqual(item['last_failure_code'], 'source_policy_deferred')
        self.assertIn('stale', item['next_action'].lower())
        self.assertEqual(report['summary']['macro']['deferred_attempts_with_data'], 1)
        self.assertEqual(report['summary']['macro']['deferred_attempts_current_data'], 0)
        self.assertEqual(report['summary']['macro']['deferred_attempts_stale_data'], 1)
        self.assertEqual(report['summary']['macro']['needs_attention'], len(self.catalog))

    def test_irregular_world_bank_gini_current_publisher_years_have_expiring_confirmation(self):
        latest = {"cn": 2022, "fr": 2023, "in": 2023, "pt": 2023}
        for country, year in latest.items():
            self.add_macro(f"inequality.{country}.gini_survey_wdi",
                           when=date(year, 1, 1))
        verified = {x["id"]: x for x in build_coverage(
            self.engine, self.catalog, self.registry,
            asof=date(2026, 11, 13))["items"]}
        for country, year in latest.items():
            sid = f"inequality.{country}.gini_survey_wdi"
            with self.subTest(series=sid):
                row = verified[sid]
                self.assertEqual(row["state"], "available")
                self.assertTrue(row["complete_for_pinned_release"])
                self.assertEqual(row["published_through"], f"{year}-01-01")
                self.assertEqual(row["publisher_release_verified_as_of"], "2026-11-13")
                self.assertFalse(row["regular_cadence_assumed"])
                self.assertIsNone(row["unobserved_internal_periods"])
        # Publisher check has a real expiry. An old verification must never
        # suppress a missing 2027 publication or claim fresh 2026 metadata.
        expired = {x["id"]: x for x in build_coverage(
            self.engine, self.catalog, self.registry,
            asof=date(2026, 12, 13))["items"]}
        for country in latest:
            row = expired[f"inequality.{country}.gini_survey_wdi"]
            self.assertEqual(row["state"], "stale")
            self.assertFalse(row["complete_for_pinned_release"])
            self.assertIsNone(row["published_through"])
        # The country-specific exception must not leak to the US survey.
        self.add_macro("inequality.us.gini_survey_wdi",
                       when=date(2021, 1, 1))
        others = {x["id"]: x for x in build_coverage(
            self.engine, self.catalog, self.registry,
            asof=date(2026, 11, 13))["items"]}
        self.assertFalse(others["inequality.us.gini_survey_wdi"]
                         ["complete_for_pinned_release"])
        self.assertEqual(others["inequality.us.gini_survey_wdi"]["state"], "stale")

    def test_deferred_current_not_same_as_failed_current(self):
        self.add_macro('activity.us.oecd_cli', status='deferred',
                       when=date(2026, 9, 1), error='source_policy_deferred')
        self.add_macro('activity.jp.oecd_cli', status='failed',
                       when=date(2026, 9, 1), error='source_transport_failed')
        report = build_coverage(self.engine, self.catalog, self.registry,
                                asof=date(2026, 11, 13))
        rows = {row['id']: row for row in report['items']}
        self.assertEqual(rows['activity.us.oecd_cli']['state'], 'available')
        self.assertEqual(rows['activity.jp.oecd_cli']['state'], 'refresh_failed_with_data')
        self.assertEqual(report['summary']['macro']['needs_attention'], len(self.catalog) - 1)

    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.catalog = load_documents()[0]["series"]
        self.registry = instruments()

    def tearDown(self):
        self.engine.dispose()

    def add_macro(self, sid, status="success", recorded=True, when=date(2025, 1, 1), error=None):
        definition = next(row for row in self.catalog if row["id"] == sid)
        with Session(self.engine) as session, session.begin():
            session.add(SeriesRow(id=sid, provider=definition["provider"],
                source_key=definition["source_key"], updated_at=NOW))
            session.add(IngestionRun(id="run-"+sid, series_id=sid,
                status=status, started_at=NOW, ended_at=NOW, requested_from=None,
                observations_received=1 if recorded else 0, versions_added=1 if recorded else 0,
                error=error))
            if recorded:
                session.add(ObservationVersion(series_id=sid, period=when,
                    value=Decimal("0.58"), first_seen_at=NOW, ingestion_run_id="run-"+sid))

    def test_returns_exactly_all_registered_macro_market_and_currency_sources(self):
        with patch.dict(os.environ, {"FINANCE_AUTO_REFRESH":"1", "FINANCE_INCLUDE_MARKETS":"0"}):
            report = build_coverage(self.engine, self.catalog, self.registry, asof=date(2026, 11, 3))
        self.assertEqual(report["summary"]["macro"]["total"], len(self.catalog))
        self.assertEqual(report["summary"]["markets"]["total"], 25)
        self.assertEqual(report["summary"]["fx"]["total"], 3)
        self.assertEqual(len(report["items"]),len(self.catalog)+len(self.registry)+3)
        self.assertEqual(len({(x["family"],x["id"]) for x in report["items"]}), len(self.catalog)+len(self.registry)+3)
        self.assertTrue(all(x["stored_periods"] == 0 for x in report["items"]))
        self.assertTrue(all(x["latest_source_date"] is None for x in report["items"]))
        self.assertEqual(report["summary"]["macro"]["not_ingested"], len(self.catalog))
        self.assertEqual(report["summary"]["markets"]["collection_disabled"], 25)
        self.assertEqual(report["summary"]["fx"]["collection_disabled"], 3)

    def test_failed_macro_refresh_does_not_hide_retained_observations(self):
        self.add_macro("labour.de.pwt_labour_share", status="success", recorded=True)
        with Session(self.engine) as session, session.begin():
            session.add(IngestionRun(id="failed-pwt",series_id="labour.de.pwt_labour_share",
                started_at=NOW + timedelta(seconds=1),
                ended_at=NOW + timedelta(seconds=2), status="failed",
                requested_from=None,observations_received=0,versions_added=0,
                error="HTTPStatusError: api_key=SHOULD_NOT_APPEAR"))
        self.add_macro("labour.fr.pwt_labour_share", status="failed", recorded=False,
                       error="HTTPStatusError")
        result = build_coverage(self.engine, self.catalog, self.registry, asof=date(2026,11,3))
        rows = {row["id"]:row for row in result["items"]}
        germany = rows["labour.de.pwt_labour_share"]
        france = rows["labour.fr.pwt_labour_share"]
        self.assertEqual(germany["stored_periods"], 1)
        self.assertEqual(germany["latest_source_date"], "2025-01-01")
        self.assertEqual(germany["state"], "refresh_failed_with_data")
        self.assertIsNotNone(germany["last_success_utc"])
        self.assertEqual(france["state"], "collection_failed")
        self.assertEqual(france["stored_periods"], 0)
        self.assertNotIn("SHOULD_NOT_APPEAR", str(result))
        self.assertNotIn("api_key=", str(result))

    def test_last_observed_date_and_period_count_deduplicate_revisions(self):
        sid = "labour.us.pwt_labour_share"
        self.add_macro(sid, when=date(2023,1,1))
        with Session(self.engine) as session, session.begin():
            session.add(ObservationVersion(series_id=sid, period=date(2023,1,1),
                value=Decimal("0.59"), first_seen_at=NOW, ingestion_run_id="run-"+sid))
        report = build_coverage(self.engine,self.catalog,self.registry,asof=date(2026,11,3))
        row=next(item for item in report["items"] if item["id"]==sid)
        self.assertEqual(row["stored_periods"],1)
        self.assertEqual(row["stored_versions"],2)
        self.assertEqual(row["additional_revisions"],1)
        self.assertEqual(row["unobserved_internal_periods"],0)
        self.assertEqual(row["oldest_source_date"],"2023-01-01")
        self.assertEqual(row["latest_source_date"],"2023-01-01")
        self.assertEqual(row["state"],"available")
        self.assertTrue(row["complete_for_pinned_release"])
        self.assertEqual(row["published_through"],"2023-01-01")
        self.assertEqual(row["published_release"],"Penn World Table 11.0")

    def test_2022_pwt_history_is_still_stale_but_complete_2023_release_is_not(self):
        self.add_macro("labour.de.pwt_labour_share", when=date(2022, 1, 1))
        self.add_macro("labour.fr.pwt_labour_share", when=date(2023, 1, 1))
        rows = {item["id"]: item for item in build_coverage(
            self.engine, self.catalog, self.registry,
            asof=date(2026, 11, 3))["items"]}
        self.assertEqual(rows["labour.de.pwt_labour_share"]["state"],"stale")
        self.assertFalse(rows["labour.de.pwt_labour_share"]["complete_for_pinned_release"])
        self.assertEqual(rows["labour.fr.pwt_labour_share"]["state"],"available")
        self.assertTrue(rows["labour.fr.pwt_labour_share"]["complete_for_pinned_release"])

    def test_publication_exception_is_not_applied_to_absent_source(self):
        with patch.dict(os.environ, {"FINANCE_AUTO_REFRESH": "1"}):
            rows={row["id"]: row for row in build_coverage(
                self.engine,self.catalog,self.registry,
                asof=date(2026,11,3))["items"]}
        de=rows["labour.de.pwt_labour_share"]
        self.assertEqual(de["state"],"not_ingested")
        self.assertFalse(de["complete_for_pinned_release"])
        self.assertEqual(de["published_through"],"2023-01-01")

    def test_official_bis_credit_release_is_not_mislabeled_stale(self):
        bis_ids = [
            "credit.world.private_gdp_gap",
            "credit.world.private_gdp_gap_coverage",
            "credit_gap.ea.bis",
            "credit_gap.jp.bis",
            "credit_gap.us.bis",
        ]
        for sid in bis_ids:
            self.add_macro(sid, when=date(2026,1,1))
        rows={x["id"]:x for x in build_coverage(
            self.engine,self.catalog,self.registry,asof=date(2026,11,3))["items"]}
        for sid in bis_ids:
            with self.subTest(sid=sid):
                self.assertEqual(rows[sid]["state"],"available")
                self.assertEqual(rows[sid]["published_through"],"2026-01-01")
                self.assertTrue(rows[sid]["complete_for_pinned_release"])

    def test_bis_release_window_expires_and_older_quarter_is_still_stale(self):
        current = "credit_gap.us.bis"
        old = "credit_gap.jp.bis"
        self.add_macro(current,when=date(2026,1,1))
        self.add_macro(old,when=date(2025,10,1))
        november={x["id"]:x for x in build_coverage(
            self.engine,self.catalog,self.registry,asof=date(2026,11,3))["items"]}
        self.assertEqual(november[current]["state"],"available")
        self.assertEqual(november[old]["state"],"stale")
        december={x["id"]:x for x in build_coverage(
            self.engine,self.catalog,self.registry,asof=date(2026,12,7))["items"]}
        self.assertEqual(december[current]["state"],"stale")
        self.assertIsNone(december[current]["published_through"])

    def test_bis_dsr_q1_is_current_only_within_verified_publication_window(self):
        dsr_ids = (
            "debt_service.us.private.bis", "debt_service.us.households.bis",
            "debt_service.us.corporations.bis", "debt_service.jp.private.bis",
            "debt_service.de.private.bis", "debt_service.cn.private.bis",
            "debt_service.pt.private.bis", "debt_service.pt.households.bis",
        )
        for sid in dsr_ids:
            self.add_macro(sid, when=date(2026, 1, 1))
        for asof, state, through in (
            (date(2026, 9, 13), "stale", None),
            (date(2026, 9, 14), "available", "2026-01-01"),
            (date(2026, 12, 6), "available", "2026-01-01"),
            (date(2026, 12, 7), "stale", None),
        ):
            rows = {x["id"]: x for x in build_coverage(
                self.engine, self.catalog, self.registry, asof=asof)["items"]}
            for sid in dsr_ids:
                with self.subTest(series=sid, asof=asof):
                    self.assertEqual(rows[sid]["state"], state)
                    self.assertEqual(rows[sid]["published_through"], through)
                    self.assertEqual(rows[sid]["complete_for_pinned_release"],
                                     through is not None)
                    self.assertEqual(rows[sid]["published_release_date"],
                                     "2026-09-14" if through else None)

    def test_bis_dsr_release_does_not_exempt_older_or_absent_observations(self):
        old = "debt_service.jp.private.bis"
        absent = "debt_service.de.private.bis"
        self.add_macro(old, when=date(2025, 10, 1))
        with patch.dict(os.environ, {"FINANCE_AUTO_REFRESH": "1"}):
            rows = {x["id"]: x for x in build_coverage(
                self.engine, self.catalog, self.registry,
                asof=date(2026, 11, 4))["items"]}
        self.assertEqual(rows[old]["state"], "stale")
        self.assertEqual(rows[absent]["state"], "not_ingested")
        for sid in (old, absent):
            self.assertEqual(rows[sid]["published_through"], "2026-01-01")
            self.assertFalse(rows[sid]["complete_for_pinned_release"])

    def test_bis_dsr_release_preserves_active_refresh_failure(self):
        sid = "debt_service.us.private.bis"
        self.add_macro(sid, status="failed", when=date(2026, 1, 1),
                       error="provider_http_503")
        rows = {x["id"]: x for x in build_coverage(
            self.engine, self.catalog, self.registry, asof=date(2026, 11, 4))["items"]}
        self.assertEqual(rows[sid]["state"], "refresh_failed_with_data")
        self.assertEqual(rows[sid]["last_failure_code"], "provider_http_503")
        self.assertTrue(rows[sid]["complete_for_pinned_release"])

    def test_bis_dsr_release_does_not_exempt_property_sources(self):
        self.add_macro("property.jp.real_residential.bis", when=date(2025, 10, 1))
        self.add_macro("property.world.real_residential.bis", when=date(2026, 1, 1))
        rows = {x["id"]: x for x in build_coverage(
            self.engine, self.catalog, self.registry, asof=date(2026, 11, 4))["items"]}
        for sid in ("property.jp.real_residential.bis", "property.world.real_residential.bis"):
            with self.subTest(series=sid):
                self.assertEqual(rows[sid]["state"], "stale")
                self.assertIsNone(rows[sid]["published_through"])
                self.assertFalse(rows[sid]["complete_for_pinned_release"])

    def test_complete_pinned_release_remains_available_after_budget_deferral(self):
        tiva = "supply_chain.pt.foreign_final_demand_share"
        sovereign = "returns.swinkels.us.sovereign_10y_modelled_local"
        self.add_macro(tiva, status="deferred", when=date(2022, 1, 1),
                       error="source_policy_deferred")
        self.add_macro(sovereign, status="deferred", when=date(2022, 12, 1),
                       error="source_policy_deferred")
        rows={x["id"]:x for x in build_coverage(
            self.engine, self.catalog, self.registry, asof=date(2026, 11, 12))["items"]}
        for sid in (tiva, sovereign):
            self.assertEqual(rows[sid]["state"], "available")
            self.assertTrue(rows[sid]["scheduled_download_unnecessary_for_pinned_release"])
            self.assertEqual(rows[sid]["refresh_state"], "deferred")
            self.assertEqual(rows[sid]["last_failure_code"], "source_policy_deferred")
            self.assertIn("pinned release", rows[sid]["next_action"].lower())

    def test_tiva_2022_is_current_for_pinned_edition_after_revision_date(self):
        tiva_ids = [x["id"] for x in self.catalog if x["provider"] == "OECD_TIVA"]
        for sid in tiva_ids:
            self.add_macro(sid, when=date(2022, 1, 1))
        for asof, state, through in (
            (date(2026, 1, 21), "stale", None),
            (date(2026, 1, 22), "available", "2022-01-01"),
            (date(2026, 11, 4), "available", "2022-01-01"),
        ):
            rows = {x["id"]: x for x in build_coverage(
                self.engine, self.catalog, self.registry, asof=asof)["items"]}
            for sid in tiva_ids:
                with self.subTest(series=sid, asof=asof):
                    self.assertEqual(rows[sid]["state"], state)
                    self.assertEqual(rows[sid]["published_through"], through)
                    self.assertEqual(rows[sid]["complete_for_pinned_release"],
                                     through is not None)
                    self.assertEqual(rows[sid]["published_release_date"],
                                     "2026-01-22" if through else None)
                    self.assertEqual(rows[sid]["published_release"],
                                     "TiVA 2025 edition, January 2026 revision" if through else None)

    def test_tiva_edition_bound_preserves_older_empty_and_failed_states(self):
        old = "supply_chain.pt.foreign_final_demand_va"
        absent = "supply_chain.pt.value_added"
        failed = "supply_chain.pt.foreign_final_demand_share"
        self.add_macro(old, when=date(2021, 1, 1))
        self.add_macro(failed, status="failed", when=date(2022, 1, 1),
                       error="provider_http_503")
        with patch.dict(os.environ, {"FINANCE_AUTO_REFRESH": "1"}):
            rows = {x["id"]: x for x in build_coverage(
                self.engine, self.catalog, self.registry,
                asof=date(2026, 11, 4))["items"]}
        self.assertEqual(rows[old]["state"], "stale")
        self.assertFalse(rows[old]["complete_for_pinned_release"])
        self.assertEqual(rows[absent]["state"], "not_ingested")
        self.assertFalse(rows[absent]["complete_for_pinned_release"])
        self.assertEqual(rows[failed]["state"], "refresh_failed_with_data")
        self.assertEqual(rows[failed]["last_failure_code"], "provider_http_503")
        self.assertTrue(rows[failed]["complete_for_pinned_release"])
        self.assertEqual(rows[old]["published_through"], "2022-01-01")
        self.assertEqual(rows[absent]["published_through"], "2022-01-01")

    def test_tiva_edition_bound_does_not_exempt_older_wid_world_file(self):
        sid = "inequality.world.pretax_income.top10"
        self.add_macro(sid, when=date(2023, 1, 1))
        rows = {x["id"]: x for x in build_coverage(
            self.engine, self.catalog, self.registry, asof=date(2026, 11, 4))["items"]}
        self.assertEqual(rows[sid]["state"], "stale")
        self.assertIsNone(rows[sid]["published_through"])
        self.assertFalse(rows[sid]["complete_for_pinned_release"])

    def test_swinkels_fixed_v6_bounds_apply_to_each_native_country_method_only(self):
        # A stale warning must recognise the frozen publisher edition without
        # pretending that a 2022 return is a contemporary 2026 observation.
        sovereign = [x["id"] for x in self.catalog if x["provider"] == "SWINKELS_RETURNS"]
        self.assertEqual(len(sovereign), 10)
        for sid in sovereign:
            self.add_macro(sid, when=date(2022, 12, 1))
        rows = {x["id"]: x for x in build_coverage(
            self.engine, self.catalog, self.registry, asof=date(2026, 11, 4))["items"]}
        for sid in sovereign:
            self.assertEqual(rows[sid]["state"], "available")
            self.assertEqual(rows[sid]["latest_source_date"], "2022-12-01")
            self.assertEqual(rows[sid]["published_through"], "2022-12-01")
            self.assertEqual(rows[sid]["published_release_date"], "2023-01-10")
            self.assertEqual(rows[sid]["published_release"], "Swinkels original dataset v6")
            self.assertTrue(rows[sid]["complete_for_pinned_release"])

    def test_sovereign_bounds_preserve_old_empty_failed_and_unpinned_equity_states(self):
        old = "returns.swinkels.de.sovereign_10y_modelled_local"
        failed = "returns.swinkels.jp.sovereign_10y_modelled_local"
        absent = "returns.swinkels.fr.sovereign_10y_modelled_local"
        equity = "returns.french.developed.market_total_usd"
        self.add_macro(old, when=date(2022, 11, 1))
        self.add_macro(failed, status="failed", when=date(2022, 12, 1), error="provider_http_503")
        self.add_macro(equity, when=date(2022, 12, 1))
        with patch.dict(os.environ, {"FINANCE_AUTO_REFRESH": "1"}):
            rows = {x["id"]: x for x in build_coverage(
                self.engine, self.catalog, self.registry, asof=date(2026, 11, 4))["items"]}
        self.assertEqual(rows[old]["state"], "stale")
        self.assertFalse(rows[old]["complete_for_pinned_release"])
        self.assertEqual(rows[absent]["state"], "not_ingested")
        self.assertFalse(rows[absent]["complete_for_pinned_release"])
        self.assertEqual(rows[failed]["state"], "refresh_failed_with_data")
        self.assertEqual(rows[failed]["last_failure_code"], "provider_http_503")
        self.assertTrue(rows[failed]["complete_for_pinned_release"])
        self.assertEqual(rows[equity]["state"], "stale")
        self.assertIsNone(rows[equity]["published_through"])

    def test_annual_gap_diagnostic_does_not_label_revisions_as_missing_dates(self):
        sid = "labour.us.pwt_labour_share"
        self.add_macro(sid, when=date(2020,1,1))
        with Session(self.engine) as session, session.begin():
            session.add(ObservationVersion(series_id=sid,period=date(2022,1,1),
                value=Decimal("0.52"),first_seen_at=NOW,ingestion_run_id="run-"+sid))
        report = build_coverage(self.engine,self.catalog,self.registry,
                                asof=date(2026,11,3))
        row = next(x for x in report["items"] if x["id"] == sid)
        self.assertEqual(row["stored_periods"],2)
        self.assertEqual(row["unobserved_internal_periods"],1)
        self.assertEqual(row["additional_revisions"],0)

    def test_verified_euklems_2025_coverage_is_current_only_through_2021(self):
        from finance_dashboard.source_coverage import PUBLICATION_BOUNDS
        self.assertEqual(len([sid for sid in PUBLICATION_BOUNDS
                              if sid.startswith("labour.") and ".euklems_" in sid]), 32)
        current = "labour.pt.euklems_value_added"
        gap = "labour.us.euklems_labour_compensation"
        self.add_macro(current, when=date(2021, 1, 1))
        self.add_macro(gap, when=date(2020, 1, 1))
        rows={row["id"]: row for row in build_coverage(
            self.engine, self.catalog, self.registry, asof=date(2026,11,12))["items"]}
        self.assertEqual(rows[current]["state"], "available")
        self.assertTrue(rows[current]["complete_for_pinned_release"])
        self.assertEqual(rows[current]["published_through"], "2021-01-01")
        self.assertIsNone(rows[current]["published_release_date"])
        self.assertEqual(rows[current]["publisher_release_verified_as_of"], "2026-11-12")
        self.assertEqual(rows[gap]["state"], "stale")
        self.assertFalse(rows[gap]["complete_for_pinned_release"])
        expired = {row["id"]: row for row in build_coverage(
            self.engine, self.catalog, self.registry,
            asof=date(2026, 12, 12))["items"]}
        self.assertEqual(expired[current]["state"], "stale")
        self.assertIsNone(expired[current]["published_through"])

    def test_bis_total_credit_release_guard_expires_on_next_scheduled_release(self):
        from finance_dashboard.source_coverage import PUBLICATION_BOUNDS
        self.assertEqual(len([sid for sid in PUBLICATION_BOUNDS
                              if sid.startswith("credit.") and
                              sid.endswith(("_gdp_bis", "_stock_bis"))]), 20)
        sid = "credit.pt.private_nonfinancial_stock_bis"
        self.add_macro(sid, when=date(2026,1,1))
        november = {row["id"]: row for row in build_coverage(
            self.engine,self.catalog,self.registry,asof=date(2026,11,12))["items"]}
        self.assertEqual(november[sid]["state"], "available")
        self.assertEqual(november[sid]["published_release_date"], "2026-09-14")
        december = {row["id"]: row for row in build_coverage(
            self.engine,self.catalog,self.registry,asof=date(2026,12,7))["items"]}
        self.assertEqual(december[sid]["state"], "stale")
        self.assertIsNone(december[sid]["published_through"])

    def test_fed_financial_accounts_and_fdic_actual_release_windows(self):
        from finance_dashboard.source_coverage import (
            _FED_Z1_SERIES, _FED_DISTRIBUTIONAL_SERIES, PUBLICATION_BOUNDS
        )
        self.assertEqual(len(_FED_Z1_SERIES) + len(_FED_DISTRIBUTIONAL_SERIES), 27)
        ids = ("funding.us.broker_assets", "wealth.us.top1_share",
               "bank.us.fdic_total_assets")
        for sid in ids:
            self.add_macro(sid, when=date(2026,4,1))
        november={row["id"]: row for row in build_coverage(
            self.engine,self.catalog,self.registry,asof=date(2026,11,12))["items"]}
        for sid in ids:
            self.assertEqual(november[sid]["state"], "available")
            self.assertTrue(november[sid]["scheduled_download_unnecessary_for_pinned_release"])
            self.assertEqual(november[sid]["published_through"], "2026-04-01")
        self.assertEqual(november[ids[0]]["published_release_date"], "2026-09-11")
        self.assertEqual(november[ids[1]]["published_release_date"], "2026-09-18")
        self.assertEqual(november[ids[2]]["published_release_date"], "2026-08-25")
        november_end={row["id"]: row for row in build_coverage(
            self.engine,self.catalog,self.registry,asof=date(2026,11,21))["items"]}
        self.assertEqual(november_end[ids[2]]["state"], "stale")
        december={row["id"]: row for row in build_coverage(
            self.engine,self.catalog,self.registry,asof=date(2026,12,10))["items"]}
        self.assertEqual(december[ids[0]]["state"], "stale")
        self.assertEqual(december[ids[1]]["state"], "stale")

    def test_irregular_published_snapshots_do_not_claim_calendar_gaps(self):
        sid = "concentration.global.msci_acwi_published_top10"
        self.add_macro(sid, when=date(2019, 1, 1))
        with Session(self.engine) as session, session.begin():
            session.add(ObservationVersion(series_id=sid, period=date(2026, 10, 1),
                value=Decimal("25.5"), first_seen_at=NOW, ingestion_run_id="run-"+sid))
        report = build_coverage(self.engine, self.catalog, self.registry,
                                asof=date(2026, 11, 3))
        row = next(x for x in report["items"] if x["id"] == sid)
        self.assertFalse(row["regular_cadence_assumed"])
        self.assertIsNone(row["unobserved_internal_periods"])
        self.assertEqual(row["stored_periods"], 2)
        self.assertEqual(row["latest_source_date"], "2026-10-01")

    def test_market_and_fx_are_reported_with_actual_observation_dates(self):
        with Session(self.engine) as session, session.begin():
            session.add(MarketInstrumentRow(id="vt",symbol=self.registry["vt"]["source_symbol"],
                exchange_mic=self.registry["vt"]["exchange_mic"],currency="USD",updated_at=NOW))
            session.add(MarketIngestionRun(id="market-1", instrument_id="vt",
                started_at=NOW,ended_at=NOW,status="success",requested_from=None,
                observations_received=2,versions_added=2))
            session.add(MarketPriceVersion(instrument_id="vt",day=date(2026,10,30),
                close=Decimal("110"),adjusted_close=Decimal("110"),
                volume=0,first_seen_at=NOW,ingestion_run_id="market-1"))
            session.add(FxIngestionRun(id="fx-1",currency="USD",started_at=NOW,
                ended_at=NOW,status="success",observations_received=1,versions_added=1))
            session.add(FxRateVersion(currency="USD",day=date(2026,11,2),
                foreign_per_eur=Decimal("1.12"),first_seen_at=NOW,ingestion_run_id="fx-1"))
        with patch.dict(os.environ,{"FINANCE_INCLUDE_MARKETS":"1"}):
            report=build_coverage(self.engine,self.catalog,self.registry,asof=date(2026,11,3))
        market=next(x for x in report["items"] if x["id"]=="vt")
        fx=next(x for x in report["items"] if x["family"]=="fx" and x["id"]=="USD")
        self.assertEqual((market["stored_periods"],market["latest_source_date"],market["state"]),
                         (1,"2026-10-30","available"))
        self.assertEqual((fx["stored_periods"],fx["latest_source_date"],fx["state"]),
                         (1,"2026-11-02","available"))
        self.assertIsNone(fx["unobserved_internal_periods"])
        self.assertIsNone(market["unobserved_internal_periods"])

    def test_readonly_api_contains_complete_coverage_without_credentials(self):
        with patch.dict(os.environ,{"FINANCE_AUTO_REFRESH":"0","FRED_API_KEY":"a"*32,
                                     "WISESHEETS_API_KEY":"SENSITIVE_KEY"}):
            with TestClient(create_app(self.engine)) as client:
                response=client.get("/api/source-coverage")
        self.assertEqual(response.status_code,200)
        payload=response.json()
        self.assertEqual(len(payload["items"]),len(self.catalog)+len(self.registry)+3)
        self.assertEqual(payload["summary"]["macro"]["total"],len(self.catalog))
        self.assertNotIn("SENSITIVE_KEY", response.text)
        self.assertNotIn("a"*32, response.text)


if __name__=="__main__":
    unittest.main()
