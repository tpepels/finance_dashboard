"""Focus on original-source parsing and as-of safety for Claude's Phase 2 adapters.

All inputs are synthetic, scoped publisher-format fixtures. These tests prove
parser/contract behaviour, not historical source acquisition or certification.
"""
from datetime import date
from decimal import Decimal
import unittest

from finance_dashboard.bis import ProviderError
from finance_dashboard.boj_call_rates import audit_boj_consistency, parse_boj_csv
from finance_dashboard.fdic_banks import parse_fdic_aggregates
from finance_dashboard.fed_g17 import parse_g17_diffusion
from finance_dashboard.imf_external import parse_imf_bop_iip
from finance_dashboard.nber_chronology import information_available_as_of
from finance_dashboard.oecd_cli import parse_oecd_cli_csv
from finance_dashboard.ofr_fsi import parse_ofr_fsi, audit_ofr_fsi_partitions
from finance_dashboard.captured_sources import _fdic
from finance_dashboard.source_reconciliation import EvidenceError


class Phase2NewOriginalParserTests(unittest.TestCase):
    def test_fdic_report_date_must_be_actual_quarter_end_in_both_independent_parsers(self):
        def payload(ymd):
            return {"meta": {"parameters": {"aggsMetaData": {"by": "REPDTE",
                "sumFields": ["ASSET", "EQ"]}}},
                "data": [{"data": {"REPDTE": ymd, "sum_ASSET": 1000,
                                   "sum_EQ": 100, "count": 10}}]}
        definition = {"source_key": "financials?agg_by=REPDTE#sum_ASSET",
                      "frequency": "Q", "unit": "thousand_usd"}
        url = ("https://api.fdic.gov/banks/financials?"
               "agg_by=REPDTE&agg_sum_fields=ASSET%2CEQ&agg_limit=1000")
        for stamp in ("20260330", "20260631", "20260931", "20261230"):
            with self.subTest(stamp=stamp):
                with self.assertRaises(ProviderError):
                    parse_fdic_aggregates(payload(stamp), "bank.us.fdic_total_assets")
                with self.assertRaises(EvidenceError):
                    _fdic(payload(stamp), definition, url)
        # A future quarter-end must be rejected even if its stored quarter
        # start (2026-10-01) is already in the past.
        from unittest.mock import patch
        with patch("finance_dashboard.fdic_banks.date") as clock:
            clock.today.return_value = date(2026, 11, 4)
            clock.side_effect = date
            with self.assertRaises(ProviderError):
                parse_fdic_aggregates(payload("20261231"), "bank.us.fdic_total_assets")
        with patch("finance_dashboard.captured_sources.date") as clock:
            clock.today.return_value = date(2026, 11, 4)
            clock.side_effect = date
            with self.assertRaises(EvidenceError):
                _fdic(payload("20261231"), definition, url)
        good = payload("20260331")
        self.assertEqual(parse_fdic_aggregates(good, "bank.us.fdic_total_assets"),
                         {date(2026, 1, 1): Decimal("1000")})
        self.assertEqual(_fdic(good, definition, url)[0],
                         {date(2026, 1, 1): Decimal("1000")})

    def test_nber_information_set_does_not_reveal_retrospective_future_dates(self):
        evidence = {"announcements": [
            {"announcement_date": "2008-12-01", "classification": "determination",
             "turning_point": "peak", "event_month": "2007-12"},
            {"announcement_date": "2010-09-20", "classification": "determination",
             "turning_point": "trough", "event_month": "2009-06"}],
            "retrospective_cycles": [{"peak_month": "2007-12", "trough_month": "2009-06"}]}
        before = information_available_as_of(evidence, date(2008, 1, 1))
        self.assertEqual(before["announced_turning_points"], [])
        self.assertNotIn("dated_but_not_yet_announced", before)
        self.assertNotIn(("peak", "2007-12"), before["announced_turning_points"])
        middle = information_available_as_of(evidence, date(2009, 6, 1))
        self.assertEqual(middle["announced_turning_points"], [("peak", "2007-12")])
        self.assertNotIn(("trough", "2009-06"), middle["announced_turning_points"])
        after = information_available_as_of(evidence, date(2011, 1, 1))
        self.assertEqual(len(after["announced_turning_points"]), 2)

    def test_original_fed_g17_fixed_width_rows_preserve_missing_months(self):
        text = ('"DIFFUSION_1: Diffusion index of industrial production, one month earlier"\n'
                '"DIFFUSION_1"   1967      63.7363   36.4407   43.2203\n')
        actual = parse_g17_diffusion(text, block="DIFFUSION_1", span="one month earlier")
        self.assertEqual(actual[date(1967, 1, 1)], Decimal("63.7363"))
        self.assertEqual(actual[date(1967, 3, 1)], Decimal("43.2203"))
        self.assertNotIn(date(1967, 4, 1), actual)
        with self.assertRaises(ProviderError):
            parse_g17_diffusion(text.replace("DIFFUSION_1", "DIFFUSION_3"),
                                block="DIFFUSION_1", span="one month earlier")

    def test_oecd_cli_selector_preserves_identity_and_rejects_wrong_area(self):
        columns = ("DATAFLOW,REF_AREA,FREQ,MEASURE,UNIT_MEASURE,ACTIVITY,"
                   "ADJUSTMENT,TRANSFORMATION,TIME_HORIZ,METHODOLOGY,UNIT_MULT,"
                   "TIME_PERIOD,OBS_VALUE,OBS_STATUS\n")
        line = ("OECD.SDD.STES:DSD_STES@DF_CLI(4.1),USA,M,LI,IX,_Z,"
                "AA,IX,_Z,H,0,2026-01,100.25,A\n")
        self.assertEqual(parse_oecd_cli_csv(columns + line, "USA", "AA"),
                         {date(2026, 1, 1): Decimal("100.25")})
        with self.assertRaises(ProviderError):
            parse_oecd_cli_csv(columns + line, "JPN", "AA")

    def test_ofr_parts_are_separate_and_not_summed_across_partitions(self):
        header = ("Date,OFR FSI,Credit,Equity valuation,Safe assets,Funding,"
                  "Volatility,United States,Other advanced economies,Emerging markets\n")
        body = "2026-01-02,1.000,0.200,0.200,0.200,0.200,0.200,0.400,0.300,0.300\n"
        self.assertEqual(parse_ofr_fsi(header + body, "OFR FSI"),
                         {date(2026, 1, 2): Decimal("1.000")})
        self.assertEqual(audit_ofr_fsi_partitions(header + body)["partition_failures"],
                         {"categories": 0, "regions": 0})

    def test_imf_bop_and_iip_are_independent_signed_flow_and_stock(self):
        from finance_dashboard.imf_external import IMF_SERIES
        for sid, indicator, entry, value in (
            ("external.us.imf_bop_current_account_usd", "CAB", "NETCD_T", "-123.4"),
            ("external.us.imf_iip_net_position_usd", "NIIP", "NETAL_P", "-567.8"),
        ):
            self.assertIn(sid, IMF_SERIES)
            xml = ('<GenericData><DataSet><Series COUNTRY="USA" INDICATOR="' + indicator
                   + '" BOP_ACCOUNTING_ENTRY="' + entry
                   + '" UNIT="USD" FREQUENCY="A" METHODOLOGY="BPM6">'
                   '<Obs TIME_PERIOD="2025" OBS_VALUE="' + value
                   + '"/></Series></DataSet></GenericData>')
            self.assertEqual(parse_imf_bop_iip(xml.encode(), sid),
                             {date(2025, 1, 1): Decimal(value)})
            with self.assertRaises(ProviderError):
                parse_imf_bop_iip(xml.replace('METHODOLOGY="BPM6"',
                                             'METHODOLOGY="BPM5"').encode(), sid)

    def test_registered_probe_group_and_read_only_source_status(self):
        from scripts.phase2_source_probe import CLAUDE_SOURCE_IDS, DEFAULT_IDS, probe
        from finance_dashboard.catalog import load_documents
        sources = {row["id"]: row for row in load_documents()[0]["series"]}
        self.assertEqual(len(CLAUDE_SOURCE_IDS), 12)
        self.assertEqual(len(CLAUDE_SOURCE_IDS), len(set(CLAUDE_SOURCE_IDS)))
        self.assertTrue(set(CLAUDE_SOURCE_IDS) <= set(sources))
        self.assertGreaterEqual(len({sources[sid]["provider"] for sid in CLAUDE_SOURCE_IDS}), 7)

        class Sample:
            def __init__(self, points):
                self.observations = points
                self.prepared_at = None

        class Router:
            def __init__(self):
                self.seen = []
            def fetch(self, identifier, start):
                self.seen.append((identifier, start))
                if identifier == CLAUDE_SOURCE_IDS[0]:
                    return Sample({date(2024, 3, 1): Decimal("100.1")})
                raise ProviderError("Private publisher error that must never be shown")

        router = Router()
        results = probe(router, CLAUDE_SOURCE_IDS[:2], since=date(2024, 1, 1))
        self.assertTrue(results["no_database_writes"])
        self.assertEqual(results["sampled"], 1)
        self.assertEqual(results["failed"], 1)
        self.assertNotIn("Private publisher", str(results))
        self.assertEqual(len(router.seen), 2)
        self.assertTrue(DEFAULT_IDS)

    def test_boj_rejects_uncheckable_overlap(self):
        # Different published windows must produce an explicit diagnostic,
        # not a ValueError from max()/min() on an empty intersection.
        daily = "2025/01/02,0.01\n"
        monthly = "2024/12,0.01,0.01\n"
        with self.assertRaises(ProviderError):
            audit_boj_consistency(daily, monthly)


if __name__ == "__main__":
    unittest.main()
