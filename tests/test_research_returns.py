"""Original academic return semantics, historical values and durable evidence.

The breaks each test guards are stated beside its assertions. French fixtures
are factual source-row excerpts; full-history verification uses acquired originals
separately, never a generated expansion of those excerpts.
"""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import importlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

import httpx
from finance_dashboard.bis import ProviderError

FIXTURES = Path(__file__).parent / "fixtures" / "research_returns"
ODS = "swinkels_international_monthly_government_bond_returns.ods"
NS = {"t": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
      "o": "urn:oasis:names:tc:opendocument:xmlns:office:1.0"}


def french_zip(region="developed", body=None):
    member = "Developed_3_Factors.csv" if region == "developed" else "Emerging_5_Factors.csv"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo(member, (1980, 1, 1, 0, 0, 0)), body if body is not None else (FIXTURES / (region + "_excerpts.csv")).read_bytes())
    return buf.getvalue()


def replace_ods(replace):
    buf = io.BytesIO()
    with zipfile.ZipFile(FIXTURES / ODS) as original, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as modified:
        for item in original.infolist():
            raw = original.read(item.filename)
            if item.filename == "content.xml":
                raw = replace(raw)
            modified.writestr(item, raw)
    return buf.getvalue()


def source_cells(sheet, month):
    # Independent literal XML selection: no production parser/helper is used.
    with zipfile.ZipFile(FIXTURES / ODS) as z:
        tree = ET.fromstring(z.read("content.xml"))
    tab = next(x for x in tree.findall(".//t:table", NS) if x.get("{" + NS["t"] + "}name") == sheet)
    for row in tab.findall("t:table-row", NS):
        cells = []
        for cell in row:
            if cell.tag not in ("{" + NS["t"] + "}table-cell", "{" + NS["t"] + "}covered-table-cell"):
                continue
            n = min(int(cell.get("{" + NS["t"] + "}number-columns-repeated", "1")), 12)
            cells.extend([cell] * n)
            if len(cells) >= 12:
                break
        if cells and (cells[0].get("{" + NS["o"] + "}date-value") or "").startswith(month):
            return [c.get("{" + NS["o"] + "}value") for c in cells]
    raise AssertionError("Original publisher row absent")


class ResearchReturnsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("finance_dashboard.research_returns"),
                             "Original research return adapter is missing")
        self.rr = importlib.import_module("finance_dashboard.research_returns")

    def test_french_excess_rf_and_explicit_total_keep_native_percent(self):
        # Misreading excess as total or dividing native percentages by 100 fails.
        bundle = self.rr.parse_french_zip(french_zip(), dataset="Developed_3_Factors")
        prefix = "returns.french.developed."
        self.assertEqual(bundle.observations[prefix + "market_excess_usd"][date(1990, 7, 1)], Decimal("0.77"))
        self.assertEqual(bundle.observations[prefix + "risk_free_usd"][date(1990, 7, 1)], Decimal("0.68"))
        self.assertEqual(bundle.observations[prefix + "market_total_usd"][date(1990, 7, 1)], Decimal("1.45"))
        self.assertEqual(bundle.observations[prefix + "market_total_usd"][date(2026, 9, 1)], Decimal("-1.63"))
        self.assertEqual(len(bundle.observations[prefix + "market_total_usd"]), 18)
        self.assertEqual(bundle.metadata["source_database_vintage"], "202609")
        self.assertEqual(bundle.metadata["original_first_publication_at"], None)
        self.assertEqual(bundle.metadata["series"][prefix + "market_total_usd"]["transformation"], "Mkt-RF + RF")
        self.assertNotIn(date(2025, 1, 1), bundle.observations[prefix + "market_total_usd"])

    def test_emerging_early_missing_factor_sentinels_are_not_market_returns(self):
        # Ignoring RF's actual column or rejecting unrelated missing factors fails.
        bundle = self.rr.parse_french_zip(french_zip("emerging"), dataset="Emerging_5_Factors")
        prefix = "returns.french.emerging."
        self.assertEqual(bundle.observations[prefix + "market_total_usd"][date(1989, 7, 1)], Decimal("1.30"))
        self.assertEqual(bundle.observations[prefix + "market_total_usd"][date(2026, 9, 1)], Decimal("-1.17"))
        self.assertEqual(bundle.metadata["missing_values_by_variable"]["RMW"], 5)
        self.assertEqual(bundle.metadata["missing_values_by_variable"]["CMA"], 5)

    def test_missing_native_return_excludes_only_affected_values_and_total(self):
        # Turning -99.99 into a real return or inventing the matched input fails.
        body = (FIXTURES / "developed_excerpts.csv").read_text().replace("0.77    ,0.53", "-99.99    ,0.53", 1)
        bundle = self.rr.parse_french_zip(french_zip(body=body), dataset="Developed_3_Factors")
        self.assertNotIn(date(1990, 7, 1), bundle.observations["returns.french.developed.market_excess_usd"])
        self.assertNotIn(date(1990, 7, 1), bundle.observations["returns.french.developed.market_total_usd"])
        self.assertEqual(bundle.observations["returns.french.developed.risk_free_usd"][date(1990, 7, 1)], Decimal("0.68"))

    def test_french_identity_duplicates_invalid_periods_and_nonfinite_rejected(self):
        original = (FIXTURES / "developed_excerpts.csv").read_text()
        changes = [original.replace("Mkt-RF,SMB", "Mkt,SMB"),
                   original.replace("199007", "199013"),
                   original.replace("0.77    ,0.53", "Infinity    ,0.53", 1),
                   original.replace("199008", "199007")]
        for body in changes:
            with self.subTest(body=body[:100]):
                with self.assertRaises(ProviderError):
                    self.rr.parse_french_zip(french_zip(body=body), dataset="Developed_3_Factors")
        with self.assertRaises(ProviderError):
            self.rr.parse_french_zip(french_zip("emerging"), dataset="Developed_3_Factors")
        with self.assertRaises(ProviderError):
            self.rr.parse_french_zip(b"not a ZIP", dataset="Developed_3_Factors")

    def test_all_real_sovereign_histories_preserve_early_late_and_negative_values(self):
        # Dropped/repeated rows, percent scaling, wrong return columns and gap fills fail.
        bundle = self.rr.parse_swinkels_ods((FIXTURES / ODS).read_bytes())
        expected = [("us", 912, date(1947, 1, 1), "0.0017705673642301508", "-0.013267257796374382"),
                    ("de", 603, date(1972, 10, 1), "-0.018087803085468472", "-0.049843441180574086"),
                    ("jp", 579, date(1974, 10, 1), "0.00041819503822051757", "-0.017011085392979859"),
                    ("fr", 431, date(1987, 2, 1), "0.012754916840863221", "-0.05783404077371683"),
                    ("gb", 635, date(1970, 2, 1), "0.022450712752992368", "-0.032612546987391328"),
                    ("au", 641, date(1969, 8, 1), "0.0055798268563925554", "-0.039181894481790165"),
                    ("ca", 443, date(1986, 2, 1), "0.043081238084515236", "-0.02786208700577773"),
                    ("no", 1223, date(1921, 2, 1), "-0.013403202207418446", "-0.0050079658035804032"),
                    ("se", 1236, date(1920, 1, 1), "0.0068271088694513166", "-0.050875388688315926")]
        for country, count, first, first_value, last_value in expected:
            sid = "returns.swinkels." + country + ".sovereign_10y_modelled_local"
            values = bundle.observations[sid]
            with self.subTest(country=country):
                self.assertEqual((len(values), min(values), max(values)), (count, first, date(2022, 12, 1)))
                self.assertEqual(values[first], Decimal(first_value))
                self.assertEqual(values[date(2022, 12, 1)], Decimal(last_value))
                self.assertEqual(len(values), (2022-first.year)*12 + 12-first.month + 1)
        original = bundle.observations["returns.swinkels.us.sovereign_10y_original_1962_usd"]
        self.assertEqual(len(original), 732)
        self.assertEqual(original[date(1962, 1, 1)], Decimal("0.000073667611639348894"))
        self.assertEqual(sum(map(len, bundle.observations.values())), 7435)
        self.assertNotEqual(original[date(2022, 12, 1)], bundle.observations["returns.swinkels.us.sovereign_10y_modelled_local"][date(2022, 12, 1)])
        series = bundle.metadata["series"]["returns.swinkels.jp.sovereign_10y_modelled_local"]
        self.assertIn("9-year", series["method_note"])
        self.assertEqual(series["currency"], "JPY")
        self.assertEqual(series["source_periods"]["1974-10-01"], "1974-10-31")
        self.assertEqual(bundle.metadata["dataset_release_at"], "2023-01-10T08:58:37Z")
        self.assertIsNone(bundle.metadata["original_first_publication_at"])

    def test_selected_cached_bond_returns_match_independent_cashflow_calculation(self):
        # Reading a neighbouring value or accepting stale formula-cache results fails.
        bundle = self.rr.parse_swinkels_ods((FIXTURES / ODS).read_bytes())
        for country, sheet, earlier, later in [("us", "Improved_US_1947", "1946-12", "1947-01"),
                                                ("de", "Germany_DE_1972", "2022-11", "2022-12"),
                                                ("jp", "Japan_JP_1974", "1974-09", "1974-10")]:
            previous = float(source_cells(sheet, earlier)[1]) / 100
            current = float(source_cells(sheet, later)[1]) / 100
            # Semiannual coupon bond price with remaining maturity 10 - 1/12,
            # plus one month's accrued previous coupon, per source method.
            discount = (1 + current / 2) ** (-2 * (10 - 1 / 12))
            calculated = previous / 12 + previous / current * (1-discount) + discount - 1
            observed = bundle.observations[f"returns.swinkels.{country}.sovereign_10y_modelled_local"][date.fromisoformat(later + "-01")]
            self.assertAlmostEqual(float(observed), calculated, places=12)

    def test_swinkels_rejects_misidentified_sheets_dates_cache_and_duplicate_months(self):
        body = (FIXTURES / ODS).read_bytes()
        for modify in [lambda x: x.replace(b'table:name="Improved_US_1947"', b'table:name="Unknown_US_1947"', 1),
                       lambda x: x.replace(b'office:date-value="1947-01-31T00:00:00"', b'office:date-value="1947-01-30T00:00:00"', 1),
                       lambda x: x.replace(b'office:value="1.7705673642301508E-3"', b'office:value="NaN"', 1)]:
            with self.subTest(modify=modify):
                changed = replace_ods(modify)
                self.assertNotEqual(changed, body)
                with self.assertRaises(ProviderError):
                    self.rr.parse_swinkels_ods(changed)

    def test_french_fetch_archives_once_caches_both_inputs_and_bounds_months(self):
        # Missing durable evidence, repeated per-series downloads or window leaks fail.
        requests = []
        def serve(request):
            requests.append(str(request.url))
            return httpx.Response(200, content=french_zip(), headers={"last-modified": "Mon, 26 Oct 2026 20:49:43 GMT"}, request=request)
        with tempfile.TemporaryDirectory() as folder, httpx.Client(transport=httpx.MockTransport(serve)) as http:
            client = self.rr.ResearchReturnsClient(http, archive_dir=Path(folder))
            for suffix in ("market_excess_usd", "risk_free_usd", "market_total_usd"):
                result = client.fetch("returns.french.developed." + suffix, date(2026, 1, 1))
                self.assertEqual(set(result.observations), {date(2026, 9, 1)})
                self.assertIsNone(result.prepared_at)
            self.assertEqual(len(requests), 1)
            manifests = list(Path(folder).glob("research-returns/french/developed/*/manifest.json"))
            self.assertEqual(len(manifests), 1)
            record = json.loads(manifests[0].read_text())
            self.assertEqual(record["sources"]["data"]["sha256"], sha256(french_zip()).hexdigest())
            self.assertEqual(record["data_metadata"]["source_database_vintage"], "202609")
            self.assertEqual(record["data_metadata"]["series"]["returns.french.developed.market_total_usd"]["transformation"], "Mkt-RF + RF")
            self.assertEqual(len(list(manifests[0].parent.parent.glob("retrievals/*.json"))), 1)

    def test_reacquisition_and_a_b_a_revisions_keep_original_bundles_and_receipts(self):
        # Reusing a byte-identical bundle must still record the newest acquisition.
        first = (FIXTURES / "developed_excerpts.csv").read_text()
        second = first.replace("0.77    ,0.53", "0.78    ,0.53", 1)
        with tempfile.TemporaryDirectory() as folder:
            for body in (first, second, first):
                with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=french_zip(body=body), request=request))) as http:
                    result = self.rr.ResearchReturnsClient(http, archive_dir=Path(folder)).fetch("returns.french.developed.market_total_usd")
            self.assertEqual(result.observations[date(1990, 7, 1)], Decimal("1.45"))
            parent = Path(folder) / "research-returns/french/developed"
            self.assertEqual(len(list(parent.glob("*/manifest.json"))), 2)
            receipts = sorted(parent.glob("retrievals/*.json"))
            self.assertEqual(len(receipts), 3)
            digests = [json.loads(x.read_text())["bundle_digest"] for x in receipts]
            self.assertEqual(digests[0], digests[2])
            self.assertNotEqual(digests[0], digests[1])

    def test_evidence_tampering_is_rejected_before_observations_return(self):
        with tempfile.TemporaryDirectory() as folder:
            for index in range(2):
                with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=french_zip(), request=request))) as http:
                    client = self.rr.ResearchReturnsClient(http, archive_dir=Path(folder))
                    if index == 0:
                        client.fetch("returns.french.developed.market_total_usd")
                        original = next(Path(folder).glob("research-returns/french/developed/*/source.zip"))
                        original.write_bytes(b"changed")
                    else:
                        with self.assertRaises(ProviderError):
                            client.fetch("returns.french.developed.market_total_usd")

    def test_swinkels_fetch_pins_original_and_omits_signed_redirect_query(self):
        requests = []
        def serve(request):
            requests.append(str(request.url))
            if request.url.host == "dataverse.nl" and request.url.path.endswith("512630"):
                return httpx.Response(303, headers={"location": "https://objectstore.surf.nl/store/10.34894/YWT2IX/data?signature=private-value"}, request=request)
            if request.url.host == "objectstore.surf.nl":
                return httpx.Response(200, content=(FIXTURES / ODS).read_bytes(), request=request)
            if "persistentId" in str(request.url):
                return httpx.Response(200, content=(FIXTURES / "swinkels_publisher_metadata.json").read_bytes(), request=request)
            if "figshare" in request.url.host:
                return httpx.Response(200, content=(FIXTURES / "swinkels_original_figshare_v6_metadata.json").read_bytes(), request=request)
            if request.url.path.endswith("512631"):
                return httpx.Response(200, content=(FIXTURES / "swinkels_readme.pdf").read_bytes(), request=request)
            return httpx.Response(404, request=request)
        with tempfile.TemporaryDirectory() as folder, httpx.Client(transport=httpx.MockTransport(serve)) as http:
            client = self.rr.ResearchReturnsClient(http, archive_dir=Path(folder))
            for sid in self.rr.SWINKELS_SERIES:
                result = client.fetch(sid, date(2022, 12, 1))
                self.assertEqual(set(result.observations), {date(2022, 12, 1)})
                self.assertNotIn("signature", result.request_url)
            manifests = list(Path(folder).glob("research-returns/swinkels/*/manifest.json"))
            self.assertEqual(len(manifests), 1)
            for path in Path(folder).rglob("*.json"):
                self.assertNotIn("private-value", path.read_text())
            record = json.loads(manifests[0].read_text())
            self.assertEqual(record["data_metadata"]["dataset_release_at"], "2023-01-10T08:58:37Z")
            self.assertEqual(record["repository_release_at"], "2025-08-22T06:21:18Z")
            self.assertEqual(sum("512630" in x for x in requests), 1)

    def test_http_status_survives_and_unapproved_redirect_or_changed_v6_fails(self):
        # Wrapping HTTP errors as generic parsing errors loses actionable failures.
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(429, request=request))) as http:
            with self.assertRaises(httpx.HTTPStatusError) as raised:
                self.rr.ResearchReturnsClient(http).fetch("returns.french.developed.market_total_usd")
            self.assertEqual(raised.exception.response.status_code, 429)
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "https://unapproved.example/data"}, request=request))) as http:
            with self.assertRaises(ProviderError):
                self.rr.ResearchReturnsClient(http).fetch("returns.swinkels.us.sovereign_10y_modelled_local")

    def test_swinkels_changed_pinned_workbook_and_metadata_are_rejected(self):
        # A new method/workbook cannot silently inherit the pinned v6 identity.
        def changed_bytes(request):
            return httpx.Response(200, content=(FIXTURES / ODS).read_bytes() + b"changed", request=request)
        with httpx.Client(transport=httpx.MockTransport(changed_bytes)) as http:
            with self.assertRaises(ProviderError):
                self.rr.ResearchReturnsClient(http).fetch("returns.swinkels.us.sovereign_10y_modelled_local")
        def changed_metadata(request):
            if request.url.path.endswith("512630"):
                body = (FIXTURES / ODS).read_bytes()
            elif request.url.path.endswith("512631"):
                body = (FIXTURES / "swinkels_readme.pdf").read_bytes()
            elif request.url.host == "api.figshare.com":
                body = (FIXTURES / "swinkels_original_figshare_v6_metadata.json").read_bytes().replace(b'8152748.v6', b'8152748.v7')
            else:
                body = (FIXTURES / "swinkels_publisher_metadata.json").read_bytes()
            return httpx.Response(200, content=body, request=request)
        with httpx.Client(transport=httpx.MockTransport(changed_metadata)) as http:
            with self.assertRaises(ProviderError):
                self.rr.ResearchReturnsClient(http).fetch("returns.swinkels.us.sovereign_10y_modelled_local")

    def test_unregistered_ids_empty_windows_and_nonoriginal_archive_members_fail(self):
        # Arbitrary IDs, renamed members and empty result windows must not succeed.
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=french_zip(), request=request))) as http:
            client = self.rr.ResearchReturnsClient(http)
            with self.assertRaises(ProviderError):
                client.fetch("returns.global.bloomberg")
            with self.assertRaises(ProviderError):
                client.fetch("returns.french.developed.market_total_usd", date(2026, 10, 1))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("../Developed_3_Factors.csv", (FIXTURES / "developed_excerpts.csv").read_bytes())
        with self.assertRaises(ProviderError):
            self.rr.parse_french_zip(buf.getvalue(), dataset="Developed_3_Factors")

    def test_original_ods_cached_results_equal_independent_raw_selection_for_all_months(self):
        # Numeric corruption at any historical month must fail, not just endpoints.
        bundle = self.rr.parse_swinkels_ods((FIXTURES / ODS).read_bytes())
        with zipfile.ZipFile(FIXTURES / ODS) as archive:
            tree = ET.fromstring(archive.read("content.xml"))
        # Literal publisher sheet/column identities are independent of mappings.
        selected = [("Original_US_1962", "returns.swinkels.us.sovereign_10y_original_1962_usd", 4),
                    ("Improved_US_1947", "returns.swinkels.us.sovereign_10y_modelled_local", 4),
                    ("Germany_DE_1972", "returns.swinkels.de.sovereign_10y_modelled_local", 2),
                    ("Japan_JP_1974", "returns.swinkels.jp.sovereign_10y_modelled_local", 4),
                    ("France_FR_1987", "returns.swinkels.fr.sovereign_10y_modelled_local", 2),
                    ("UK_1970", "returns.swinkels.gb.sovereign_10y_modelled_local", 4),
                    ("Australia_AU_1969", "returns.swinkels.au.sovereign_10y_modelled_local", 4),
                    ("Canada_CA_1986", "returns.swinkels.ca.sovereign_10y_modelled_local", 2),
                    ("Norway_NO_1921", "returns.swinkels.no.sovereign_10y_modelled_local", 5),
                    ("Sweden_SE_1920", "returns.swinkels.se.sovereign_10y_modelled_local", 4)]
        checked = 0
        for sheet_name, sid, column in selected:
            sheet = next(x for x in tree.findall(".//t:table", NS) if x.get("{"+NS["t"]+"}name") == sheet_name)
            expected = {}
            for row in sheet.findall("t:table-row", NS):
                cells = []
                for cell in row.findall("t:table-cell", NS):
                    cells.extend([cell] * min(12, int(cell.get("{"+NS["t"]+"}number-columns-repeated", "1"))))
                    if len(cells) > column:
                        break
                if len(cells) <= column:
                    continue
                period = cells[0].get("{"+NS["o"]+"}date-value")
                raw = cells[column].get("{"+NS["o"]+"}value")
                if period and raw:
                    expected[date.fromisoformat(period[:7]+"-01")] = Decimal(raw)
            self.assertEqual(bundle.observations[sid], expected)
            checked += len(expected)
        self.assertEqual(checked, 7435)
