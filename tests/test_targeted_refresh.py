"""Targeted source repair must never silently refresh the wrong source."""
from unittest.mock import patch
import unittest

from sqlalchemy import create_engine

from finance_dashboard.worker import refresh_all, main
from finance_dashboard.catalog import load_documents
from finance_dashboard.database import Base


class TargetedRefreshTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.series = {row["id"]: row for row in load_documents()[0]["series"]}

    def tearDown(self):
        self.engine.dispose()

    def test_can_refresh_exact_pwt_country_series_without_running_50_other_sources(self):
        ids = {"labour.de.pwt_labour_share",
               "labour.fr.pwt_labour_share",
               "labour.it.pwt_labour_share"}
        attempted = []
        with patch("finance_dashboard.worker.IngestionService") as service:
            service.return_value.refresh.side_effect = lambda sid, **kw: (
                attempted.append((sid,kw["full"])) or {
                    "series_id":sid, "status":"success","received":8})
            count = refresh_all(self.engine,full=True,series_ids=ids)
        self.assertEqual(count,0)
        self.assertEqual(set(sid for sid,_ in attempted),ids)
        self.assertEqual(len(attempted),3)
        self.assertTrue(all(full for _,full in attempted))

    def test_scheduled_refresh_reuses_complete_pinned_editions_without_network(self):
        from datetime import date
        from decimal import Decimal
        from finance_dashboard.database import SeriesRow, IngestionRun, ObservationVersion, now_utc
        from sqlalchemy.orm import Session
        sources = {
            "supply_chain.pt.foreign_final_demand_share": date(2022, 1, 1),
            "returns.swinkels.au.sovereign_10y_modelled_local": date(2022, 12, 1),
        }
        with Session(self.engine) as session, session.begin():
            for sid, observed in sources.items():
                definition = self.series[sid]
                session.add(SeriesRow(id=sid, provider=definition["provider"],
                    source_key=definition["source_key"], updated_at=now_utc()))
                session.add(IngestionRun(id="original-" + sid, series_id=sid,
                    status="success", started_at=now_utc(), ended_at=now_utc(),
                    observations_received=1, versions_added=1))
                session.add(ObservationVersion(
                    series_id=sid, period=observed, value=Decimal("22.5"),
                    first_seen_at=now_utc(), ingestion_run_id="original-" + sid))
        ids = set(sources) | {"bond.us.nominal_10y"}
        attempted = []
        with patch("finance_dashboard.worker.IngestionService") as service, \
             patch("finance_dashboard.worker.record_event"):
            service.return_value.refresh.side_effect = lambda sid, **kw: (
                attempted.append(sid) or {"series_id": sid, "status": "success"})
            self.assertEqual(refresh_all(self.engine, series_ids=ids,
                                         skip_complete_pinned=True), 0)
            self.assertEqual(attempted, ["bond.us.nominal_10y"])
            attempted.clear()
            self.assertEqual(refresh_all(self.engine, series_ids=ids), 0)
            self.assertEqual(set(attempted), ids)

    def test_scheduled_pinned_reuse_never_exempts_incomplete_source(self):
        from datetime import date
        from decimal import Decimal
        from finance_dashboard.database import SeriesRow, IngestionRun, ObservationVersion, now_utc
        from sqlalchemy.orm import Session
        sid = "supply_chain.pt.foreign_final_demand_share"
        with Session(self.engine) as session, session.begin():
            session.add(SeriesRow(id=sid, provider=self.series[sid]["provider"],
                source_key=self.series[sid]["source_key"], updated_at=now_utc()))
            session.add(IngestionRun(id="old-tiva",series_id=sid,
                started_at=now_utc(), status="success", observations_received=1,
                versions_added=1))
            session.add(ObservationVersion(series_id=sid,period=date(2021,1,1),
                value=Decimal("25"),first_seen_at=now_utc(),ingestion_run_id="old-tiva"))
        with patch("finance_dashboard.worker.IngestionService") as service:
            service.return_value.refresh.return_value = {"status": "success"}
            refresh_all(self.engine, series_ids={sid}, skip_complete_pinned=True)
            service.return_value.refresh.assert_called_once()

    def test_health_repair_avoids_in_cadence_deferred_histories(self):
        from datetime import date
        from decimal import Decimal
        from sqlalchemy.orm import Session
        from finance_dashboard.database import (
            SeriesRow, IngestionRun, ObservationVersion, now_utc,
        )
        sid = "activity.us.oecd_cli"
        stale = "activity.jp.oecd_cli"
        for chosen, day, status in (
                (sid, date(2026, 10, 1), "deferred"),
                (stale, date(2025, 1, 1), "deferred")):
            with Session(self.engine) as session, session.begin():
                definition = self.series[chosen]
                session.add(SeriesRow(id=chosen,
                    provider=definition["provider"],
                    source_key=definition["source_key"], updated_at=now_utc()))
                session.add(IngestionRun(
                    id="run-" + chosen, series_id=chosen,
                    status=status, started_at=now_utc(),
                    ended_at=now_utc(), observations_received=1,
                    versions_added=1, error="source_policy_deferred"))
                session.add(ObservationVersion(
                    series_id=chosen, period=day,
                    value=Decimal("100"), first_seen_at=now_utc(),
                    ingestion_run_id="run-" + chosen))
        attempted = []
        with patch("finance_dashboard.worker.IngestionService") as service:
            service.return_value.refresh.side_effect = lambda selected, **kwargs: (
                attempted.append(selected) or {"status": "success"})
            failed = refresh_all(self.engine, series_ids={sid, stale},
                                 attention_only=True)
        self.assertEqual(failed, 0)
        self.assertEqual(attempted, [stale])

    def test_cli_health_repair_is_macro_only_and_preserves_publisher_policy(self):
        with patch("finance_dashboard.worker.make_engine", return_value=self.engine), \
             patch("finance_dashboard.worker.refresh_all", return_value=0) as refresh, \
             patch("finance_dashboard.worker.refresh_market_all") as markets:
            code = main(["--once", "--health-repair", "--macro-only"])
        self.assertEqual(code, 0)
        self.assertTrue(refresh.call_args.kwargs["attention_only"])
        markets.assert_not_called()

    def test_invalid_id_refuses_network_and_fails_loudly(self):
        with patch("finance_dashboard.worker.IngestionService") as service:
            with self.assertRaisesRegex(ValueError,"Unknown series"):
                refresh_all(self.engine,series_ids={"labour.fake.pwt_labour_share"})
            service.assert_not_called()

    def test_cli_accepts_multiple_series_while_staying_macro_only(self):
        ids = ["labour.de.pwt_labour_share","labour.fr.pwt_labour_share"]
        with patch("finance_dashboard.worker.make_engine",return_value=self.engine), \
             patch("finance_dashboard.worker.refresh_all",return_value=0) as refresh:
            code=main(["--once","--macro-only","--full",
                "--series",ids[0],"--series",ids[1]])
        self.assertEqual(code,0)
        self.assertEqual(refresh.call_args.kwargs["series_ids"],set(ids))
        self.assertTrue(refresh.call_args.kwargs["full"])

    def test_cli_rejects_market_only_with_series_selection(self):
        with self.assertRaises(SystemExit) as raised:
            main(["--once","--market-only","--series","labour.de.pwt_labour_share"])
        self.assertEqual(raised.exception.code,2)


if __name__=="__main__":
    unittest.main()
