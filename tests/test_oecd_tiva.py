"""Original OECD TiVA 2025 source identity, missingness and evidence tests."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from finance_dashboard.bis import ProviderError
from finance_dashboard import oecd_tiva


LEVEL_FLOW = "DSD_TIVA_MAINLV@DF_MAINLV"
SHARE_FLOW = "DSD_TIVA_MAINSH@DF_MAINSH"


def fixture(flow=LEVEL_FLOW, *, statuses=True):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    columns = ["DATAFLOW", "MEASURE", "REF_AREA", "ACTIVITY", "COUNTERPART_AREA",
               "UNIT_MEASURE", "FREQ", "TIME_PERIOD", "OBS_VALUE", "UNIT_MULT"]
    if statuses:
        columns += ["OBS_STATUS", "CONF_STATUS"]
    writer.writerow(columns)
    for area in ["USA", "FRA", "PRT", "CHN", "JPN", "DEU", "IND"]:
        for measure, value in ([("FFD_DVA", "75545.559"), ("VALU", "231508.0")]
                               if flow == LEVEL_FLOW else [("FFD_DVA", "32.632")]):
            writer.writerow([f"OECD.STI.PIE:{flow}(1.1)", measure, area, "_T", "W",
                             "USD" if flow == LEVEL_FLOW else "PT_VA", "A", "2022", value,
                             "6" if flow == LEVEL_FLOW else "0"] + (["E", "F"] if statuses else []))
    return out.getvalue()


class TivaTests(unittest.TestCase):
    def setUp(self):
        self.tiva = oecd_tiva

    def test_published_levels_and_share_remain_source_native(self):
        # Recomputing the published ratio or scaling USD million to USD is a bug.
        levels = self.tiva.parse_tiva_csv(fixture(), flow=LEVEL_FLOW)
        shares = self.tiva.parse_tiva_csv(fixture(SHARE_FLOW), flow=SHARE_FLOW)
        self.assertEqual(levels.observations["supply_chain.pt.foreign_final_demand_va"],
                         {date(2022, 1, 1): Decimal("75545.559")})
        self.assertEqual(shares.observations["supply_chain.pt.foreign_final_demand_share"],
                         {date(2022, 1, 1): Decimal("32.632")})
        self.assertEqual(levels.attributes["supply_chain.pt.foreign_final_demand_va"][date(2022, 1, 1)],
                         {"OBS_STATUS": "E", "CONF_STATUS": "F"})

    def test_all_source_dimensions_and_version_must_match(self):
        # Accepting a regional, industry, counterparty or variant silently changes the analysis.
        original = fixture()
        for changed in (original.replace("(1.1)", "(1.0)"),
                        original.replace("OECD.STI.PIE:", "ANOTHER.PUBLISHER:"),
                        original.replace(",FFD_DVA,", ",EXGR,"),
                        original.replace(",PRT,", ",EU27_2020,"),
                        original.replace(",_T,", ",C,"),
                        original.replace(",W,", ",USA,"),
                        original.replace(",USD,", ",EUR,"),
                        original.replace(",A,", ",Q,"),
                        original.replace(",6,", ",0,")):
            with self.subTest(source=changed.splitlines()[1]):
                with self.assertRaises(ProviderError):
                    self.tiva.parse_tiva_csv(changed, flow=LEVEL_FLOW)
        with self.assertRaises(ProviderError):
            self.tiva.parse_tiva_csv(fixture(SHARE_FLOW).replace(",PT_VA,", ",PT_EXGR,"), flow=SHARE_FLOW)

    def test_original_missing_value_keeps_status_and_never_becomes_zero(self):
        # Losing a missing original row or inventing a zero would bias country exposure.
        data = fixture() + ("OECD.STI.PIE:DSD_TIVA_MAINLV@DF_MAINLV(1.1),FFD_DVA,PRT,_T,W,USD,A,2020,,6,M,F\n")
        batch = self.tiva.parse_tiva_csv(data, flow=LEVEL_FLOW)
        sid = "supply_chain.pt.foreign_final_demand_va"
        self.assertNotIn(date(2020, 1, 1), batch.observations[sid])
        self.assertEqual(batch.attributes[sid][date(2020, 1, 1)]["OBS_STATUS"], "M")
        # The actual public response omits status columns; absent is not inferred final.
        actual = self.tiva.parse_tiva_csv(fixture(statuses=False), flow=LEVEL_FLOW)
        self.assertEqual(actual.attributes[sid][date(2022, 1, 1)],
                         {"OBS_STATUS": None, "CONF_STATUS": None})

    def test_duplicate_nonfinite_and_nonannual_rows_are_rejected(self):
        # Duplicate dates and malformed numeric/period fields must not enter persistent data.
        original = fixture()
        for changed in (original + original.splitlines()[1] + "\n",
                        original.replace(",2022,", ",2022-Q1,"),
                        original.replace(",2022,", ",2099,"),
                        original.replace(",75545.559,", ",Infinity,")):
            with self.assertRaises(ProviderError):
                self.tiva.parse_tiva_csv(changed, flow=LEVEL_FLOW)

    def test_twenty_one_series_reuse_two_exact_original_batch_downloads(self):
        # Per-series requests are costly and risk inconsistent within-run source snapshots.
        requested = []
        def respond(request):
            requested.append(request)
            self.assertEqual(request.headers["Accept"], "text/csv")
            self.assertEqual(request.url.params["startPeriod"], "1995")
            self.assertEqual(request.url.params["dimensionAtObservation"], "AllDimensions")
            self.assertIn("USA+FRA+PRT+CHN+JPN+DEU+IND", str(request.url))
            if "DSD_TIVA_MAINSH" in request.url.path:
                self.assertTrue(request.url.path.endswith("/FFD_DVA.USA+FRA+PRT+CHN+JPN+DEU+IND._T.W.PT_VA.A"))
                body = fixture(SHARE_FLOW)
            else:
                self.assertTrue(request.url.path.endswith("/FFD_DVA+VALU.USA+FRA+PRT+CHN+JPN+DEU+IND._T.W.USD.A"))
                body = fixture()
            return httpx.Response(200, text=body, headers={"Content-Type": "text/csv"})
        with httpx.Client(transport=httpx.MockTransport(respond)) as http:
            client = self.tiva.TivaClient(http)
            selected = client.fetch("supply_chain.pt.foreign_final_demand_share", start=date(2020, 1, 1))
            for sid in self.tiva.TIVA_SERIES:
                result = client.fetch(sid)
                self.assertEqual(len(result.observations), 1)
        self.assertEqual(selected.observations, {date(2022, 1, 1): Decimal("32.632")})
        self.assertEqual(len(requested), 2)
        self.assertIsNone(selected.prepared_at)
        self.assertIn("DSD_TIVA_MAINSH", selected.request_url)

    def test_original_source_archive_keeps_both_snapshots_and_release_unknown(self):
        # An HTTP transport timestamp must not masquerade as a source publication vintage.
        def respond(request):
            return httpx.Response(200, text=fixture(SHARE_FLOW if "MAINSH" in request.url.path else LEVEL_FLOW),
                headers={"Last-Modified": "2024-05-07", "Content-Type": "text/csv", "ETag": '"original"'})
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            self.tiva.TivaClient(http, archive_dir=Path(tmp)).fetch("supply_chain.pt.value_added")
            paths = list(Path(tmp).glob("oecd-tiva/*/manifest.json"))
            self.assertEqual(len(paths), 1)
            before = paths[0].read_bytes()
            record = json.loads(before)
            self.assertEqual(record["edition"], "2025")
            self.assertIsNone(record["original_first_publication_at"])
            self.assertIn("+00:00", record["retrieved_at_utc"])
            self.assertEqual(record["sources"]["levels"]["last_modified"], "2024-05-07")
            for source in record["sources"].values():
                body = (paths[0].parent / source["file"]).read_bytes()
                self.assertEqual(source["sha256"], sha256(body).hexdigest())
            self.tiva.TivaClient(http, archive_dir=Path(tmp)).fetch("supply_chain.pt.foreign_final_demand_share")
            self.assertEqual(paths[0].read_bytes(), before)
            source_path = paths[0].parent / record["sources"]["levels"]["file"]
            source_path.write_text("corrupt original source")
            with self.assertRaises(ProviderError):
                self.tiva.TivaClient(http, archive_dir=Path(tmp)).fetch("supply_chain.pt.value_added")

    def test_repeated_original_tiva_pair_retains_each_acquisition_receipt(self):
        # Reverting to an earlier source pair must remain newer than an intervening revision.
        current = ["75545.559"]
        requests = []
        def respond(request):
            requests.append(str(request.url))
            body = fixture(SHARE_FLOW if "MAINSH" in request.url.path else LEVEL_FLOW)
            return httpx.Response(200, text=body.replace("75545.559", current[0]))
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            for value in ("75545.559", "75545.560", "75545.559"):
                current[0] = value
                client = self.tiva.TivaClient(http, archive_dir=Path(tmp))
                for sid in self.tiva.TIVA_SERIES:
                    client.fetch(sid)
            receipts = [json.loads(p.read_text()) for p in Path(tmp).glob("oecd-tiva/retrievals/*.json")]
            self.assertEqual(len(receipts), 3)
            receipts.sort(key=lambda row: row["observed_at_utc"])
            self.assertEqual(receipts[0]["bundle_digest"], receipts[2]["bundle_digest"])
            self.assertNotEqual(receipts[1]["bundle_digest"], receipts[2]["bundle_digest"])
            self.assertEqual(len(list(Path(tmp).glob("oecd-tiva/*/manifest.json"))), 2)
            for receipt in receipts:
                manifest = Path(tmp) / "oecd-tiva" / receipt["bundle_digest"] / "manifest.json"
                self.assertEqual(receipt["manifest_sha256"], sha256(manifest.read_bytes()).hexdigest())
                self.assertEqual(receipt["source_identity"]["publisher"], "OECD")
                self.assertEqual(receipt["source_identity"]["dataflow_version"], "1.1")
        self.assertEqual(len(requests), 6)

    def test_archive_failure_and_unknown_source_never_report_success(self):
        # An unwritten source archive cannot substantiate successful source acquisition.
        def respond(request):
            return httpx.Response(200, text=fixture(SHARE_FLOW if "MAINSH" in request.url.path else LEVEL_FLOW))
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            client = self.tiva.TivaClient(http, archive_dir=Path(tmp))
            with self.assertRaises(ProviderError):
                client.fetch("supply_chain.global.invalid")
            with patch("os.rename", side_effect=OSError("disk unavailable")):
                with self.assertRaises(ProviderError):
                    client.fetch("supply_chain.us.value_added")
            self.assertEqual(list(Path(tmp).glob("oecd-tiva/*/manifest.json")), [])

    def test_canonical_evidence_recomputes_real_original_discrepancies_and_rejects_tampering(self):
        originals = Path(__file__).parent / "fixtures" / "oecd_tiva"
        def respond(request):
            name = "tiva_2025_shares.csv" if "MAINSH" in request.url.path else "tiva_2025_levels.csv"
            return httpx.Response(200, content=(originals / name).read_bytes())
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            root = Path(tmp)
            self.tiva.TivaClient(http, archive_dir=root).fetch("supply_chain.pt.value_added")
            manifest = next(root.glob("oecd-tiva/*/manifest.json"))
            before = manifest.read_bytes()
            evidence = self.tiva.read_tiva_evidence(root)
            self.assertTrue(evidence["original_source_hash_verified"])
            self.assertTrue(evidence["selected_country_history_verified"])
            self.assertEqual(evidence["selection_method"], "acquisition_receipt")
            self.assertEqual(evidence["serialization_diagnostic"]["outside_serialization_rounding_intervals"], 46)
            self.assertEqual(evidence["serialization_diagnostic"]["beyond_existing_0_001pp_check"], 9)
            # Residuals stay reported but are serialization-level (max ~0.0016 pp < 0.01 pp bound).
            self.assertEqual(evidence["serialization_diagnostic"]["beyond_materiality_bound"], 0)
            self.assertLess(float(evidence["serialization_diagnostic"]["maximum_absolute_residual_pp"]), 0.01)
            self.assertTrue(evidence["accounting_passed"])
            self.assertFalse(evidence["common_release_verified"])
            self.assertEqual(manifest.read_bytes(), before)
            (manifest.parent / "tiva_2025_shares.csv").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                self.tiva.read_tiva_evidence(root)

    def test_material_share_discrepancy_still_fails(self):
        from finance_dashboard.tiva_diagnostics import audit_tiva_serialization
        originals = Path(__file__).parent / "fixtures" / "oecd_tiva"
        levels = (originals / "tiva_2025_levels.csv").read_bytes()
        shares = (originals / "tiva_2025_shares.csv").read_bytes().replace(b"21.209", b"21.309", 1)
        diagnostic = audit_tiva_serialization(levels, shares)
        self.assertEqual(diagnostic["beyond_materiality_bound"], 1)

    def test_partial_original_pair_is_available_without_full_history_or_fabricated_rounding_diagnostic(self):
        def respond(request):
            return httpx.Response(200, text=fixture(SHARE_FLOW if "MAINSH" in request.url.path else LEVEL_FLOW))
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            root = Path(tmp)
            self.tiva.TivaClient(http, archive_dir=root).fetch("supply_chain.pt.value_added")
            evidence = self.tiva.read_tiva_evidence(root)
            self.assertTrue(evidence["original_source_hash_verified"])
            self.assertFalse(evidence["selected_country_history_verified"])
            self.assertEqual(evidence["status"], "partial_original_tiva_pair")
            self.assertIsNone(evidence["serialization_diagnostic"])
            self.assertIsNone(evidence["accounting_passed"])
            self.assertEqual(evidence["missing_years_by_series"]["supply_chain.pt.value_added"], list(range(1995, 2022)))


if __name__ == "__main__":
    unittest.main()
