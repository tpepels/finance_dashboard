"""V03: MSCI regional factsheets from raw Internet Archive captures."""
import gzip
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import httpx

from finance_dashboard import msci_regional_factsheets as msci
from finance_dashboard.regional_valuation_acceptance import regional_composition_checks


def text_pdf(pages):
    """A minimal PDF: each page's lines in 6pt Courier, one string per line."""
    objects = []

    def add(body):
        objects.append(body)
        return len(objects)
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    pages_id = len(pages) * 2 + 2
    kids = []
    for lines in pages:
        ops = []
        for row, line in enumerate(lines):
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"BT /F1 6 Tf 10 {780 - row * 8} Td ({safe}) Tj ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 1300 800] /Contents %d 0 R "
                        b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (pages_id, content, font)))
    add(b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids) + b"] /Count %d >>" % len(kids))
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref)
    return bytes(out)


def factsheet(index="World", asof="SEP 30, 2026", rows=None, *, misaligned=False, countries=True, mkt_cap="77,499,426.33"):
    rows = rows or [("MSCI World", "1.52", "22.69", "17.92", "4.10"),
                    ("MSCI Emerging Markets", "2.02", "14.90", "9.72", "2.39"),
                    ("MSCI ACWI", "1.58", "21.35", "16.28", "3.77")]
    table = []
    for number, (label, *values) in enumerate(rows):
        perf = "  " + label.ljust(24) + "-1.19    1.88"
        fundamentals = "      " + "      ".join(value.rjust(7) for value in values)
        if misaligned and number == 0:
            table.append(perf)
            continue
        table.append(perf + fundamentals)
    if misaligned:
        table.append(" " * 39 + "      ".join(value.rjust(7) for value in rows[0][1:]))
    first = [f"MSCI {index} Index (USD)",
             "The index captures large and mid cap representation. With 1,604 constituents, the index covers",
             f"INDEX PERFORMANCE - NET RETURNS (%) ({asof})                FUNDAMENTALS  ({asof})",
             "                          1 Mo     3 Mo       Div Yld (%)      P/E        P/E Fwd        P/BV",
             *table,
             f"INDEX RISK AND RETURN CHARACTERISTICS ({asof})"]
    cut = 80
    legend = [("    Information Technology 30%  Financials 15%  Industrials 11%", "United States 70%  Japan 6%"),
              ("    Health Care 10%  Consumer Discretionary 10%  Communication Services 8%", "Other 24%"),
              ("    Consumer Staples 6%  Energy 4%  Materials 3%  Utilities 2%", ""),
              ("    Real Estate 1%", "")]
    second = ["INDEX CHARACTERISTICS                         TOP 10 CONSTITUENTS",
              "  Number of           1,604", "  Constituents",
              *(["               Mkt Cap ( USD Millions)          APPLE        US    3,807.42",
                 f"  Index           {mkt_cap}         NVIDIA       US    3,294.13",
                 "  Largest          3,807,419.99"] if mkt_cap else []),
              "SECTOR WEIGHTS".ljust(cut) + ("COUNTRY WEIGHTS" if countries else ""),
              *[left.ljust(cut) + (right if countries else "") for left, right in legend],
              f"                                         MSCI {index} Index (USD) | msci.com"]
    return text_pdf([first, second])


WORLD_URL = "https://www.msci.com/documents/10199/255599/msci-world-index.pdf"
ACWI_URL = "https://www.msci.com/documents/10199/255599/msci-acwi.pdf"


def row(timestamp, original, payload):
    return {"timestamp": timestamp, "original": original, "statuscode": "200", "mimetype": "application/pdf",
            "digest": msci.cdx_digest(payload), "length": str(len(payload))}


class FactsheetParsingTests(unittest.TestCase):
    def test_headline_and_comparison_rows_and_composition_are_read_as_printed(self):
        facts, _ = msci.parse_factsheet_payload(factsheet())
        self.assertEqual((facts["index"], facts["currency"], facts["as_of"]), ("WORLD", "USD", "2026-09-30"))
        self.assertEqual(facts["fundamentals"]["WORLD"]["pe"], "22.69")
        self.assertEqual(facts["fundamentals"]["EM"]["pe_fwd"], "9.72")
        self.assertEqual(facts["fundamentals"]["ACWI"]["pbv"], "3.77")
        composition = facts["composition"]
        self.assertEqual(composition["constituent_count"], 1604)
        self.assertEqual(composition["sector_weights_pct"]["Information Technology"], "30")
        self.assertEqual(composition["country_weights_pct"], {"Japan": "6", "Other": "24", "United States": "70"})
        self.assertEqual(facts["transfer_encoding"], "identity")

    def test_the_headline_index_market_cap_is_read_as_printed(self):
        facts, _ = msci.parse_factsheet_payload(factsheet(index="ACWI", rows=[("MSCI ACWI", "1.58", "21.35", "16.28", "3.77")]))
        self.assertEqual(facts["index_market_cap_usd_m"], "77499426.33")
        facts, _ = msci.parse_factsheet_payload(factsheet(mkt_cap=None))
        self.assertIsNone(facts["index_market_cap_usd_m"])

    def test_gzip_payload_is_the_archived_pdf(self):
        pdf = factsheet()
        facts, _ = msci.parse_factsheet_payload(gzip.compress(pdf))
        self.assertEqual(facts["transfer_encoding"], "gzip")
        self.assertEqual(facts["fundamentals"]["WORLD"]["pe"], "22.69")

    def test_a_value_line_without_its_index_label_is_never_assigned(self):
        with self.assertRaisesRegex(msci.MsciFactsheetError, "misaligned"):
            msci.parse_factsheet_payload(factsheet(misaligned=True))

    def test_document_date_must_be_a_month_end_and_weights_must_sum(self):
        with self.assertRaisesRegex(msci.MsciFactsheetError, "month_end"):
            msci.parse_factsheet_payload(factsheet(asof="SEP 15, 2026"))
        facts, _ = msci.parse_factsheet_payload(factsheet(countries=False))
        self.assertIsNone(facts["composition"])
        self.assertEqual(facts["composition_rejected"], "country_weights_do_not_sum")


class ArchiveTests(unittest.TestCase):
    def store(self, root, timestamp, original, pdf):
        return msci.store_capture(root, row(timestamp, original, pdf), pdf)

    def methodology(self, root):
        pdf = text_pdf([["MSCI Fundamental Data Methodology"], ["P/E"]])
        payload = gzip.compress(pdf)
        pins = {"archived_sha256": msci.sha256(payload).hexdigest(), "cdx_digest": msci.cdx_digest(payload),
                "pdf_sha256": msci.sha256(pdf).hexdigest()}
        return payload, pins

    def test_cross_listed_rows_join_and_a_printed_conflict_blocks_the_index(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            payload, pins = self.methodology(root)
            with mock.patch.dict(msci.METHODOLOGY, pins):
                msci.store_methodology(root, payload)
                self.store(root, "20261015000000", WORLD_URL, factsheet())
                self.store(root, "20261016000000", ACWI_URL, factsheet(index="ACWI", rows=[
                    ("MSCI ACWI", "1.58", "21.35", "16.28", "3.77"),
                    ("MSCI World", "1.52", "22.69", "17.92", "4.10"),
                    ("MSCI Emerging Markets", "2.02", "14.90", "9.72", "2.39")]))
                evidence = msci.read_msci_regional_evidence(root)
                self.assertEqual(evidence["documents_parsed"], 2)
                self.assertEqual(evidence["conflicts"], [])
                self.assertEqual(msci.series_values(evidence, "EM/PE"), {date(2026, 9, 1): Decimal("14.90")})
                self.assertEqual(evidence["panels"]["EM"]["coverage"]["months_from_comparison_rows_only"], 1)
                # A later capture printing another ACWI P/E for the same month blocks
                # that month: neither value is used, and the conflict is recorded.
                self.store(root, "20261017000000", ACWI_URL, factsheet(index="ACWI", rows=[
                    ("MSCI ACWI", "1.58", "21.40", "16.28", "3.77")]))
                evidence = msci.read_msci_regional_evidence(root)
                self.assertEqual(msci.series_values(evidence, "ACWI/PE"), {})
                self.assertEqual(set(msci.series_conflicts(evidence, "ACWI/PE")[0]["values"]), {"21.35", "21.40"})
                self.assertEqual(msci.series_values(evidence, "ACWI/PE_FWD"), {date(2026, 9, 1): Decimal("16.28")})
                # Market cap comes only from the index's own factsheet, never a comparison row.
                self.assertEqual(msci.series_values(evidence, "ACWI/MKT_CAP"), {date(2026, 9, 1): Decimal("77499426.33")})
                self.assertEqual(msci.series_values(evidence, "WORLD/MKT_CAP"), {date(2026, 9, 1): Decimal("77499426.33")})
                self.assertEqual(msci.series_values(evidence, "EM/MKT_CAP"), {})

    def test_rejected_documents_are_retained_and_tampering_is_detected(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            payload, pins = self.methodology(root)
            with mock.patch.dict(msci.METHODOLOGY, pins):
                msci.store_methodology(root, payload)
                self.store(root, "20200101000000", WORLD_URL, factsheet())   # as-of after capture
                folder = self.store(root, "20261015000000", WORLD_URL, factsheet())
                with self.assertRaisesRegex(msci.MsciFactsheetError, "cdx_digest"):
                    msci.store_capture(root, {**row("20261016000000", WORLD_URL, b"x"), "digest": "A" * 32}, factsheet())
                evidence = msci.read_msci_regional_evidence(root)
                self.assertEqual(evidence["rejections"], {"document_as_of_after_capture": 1})
                (folder / "archived.bin").write_bytes(factsheet(asof="AUG 31, 2026"))
                with self.assertRaises(msci.MsciFactsheetError):
                    msci.read_msci_regional_evidence(root)

    def test_collection_reads_cdx_fetches_each_unseen_capture_once_and_skips_url_variants(self):
        pdf = factsheet()
        payload, pins = self.methodology(None)
        seen = []
        listing = [["timestamp", "original", "statuscode", "mimetype", "digest", "length"],
                   ["20261015000000", "http://www.msci.com:80/documents/10199/255599/msci-world-index.pdf", "200",
                    "application/pdf", msci.cdx_digest(pdf), str(len(pdf))],
                   ["20261016000000", "https://www.msci.com/documents/10199/255599/MSCI-World-Index.pdf", "200",
                    "application/pdf", "B" * 32, "1"],
                   ["20261017000000", "https://www.msci.com/documents/10199/255599/msci-world-index.pdf", "302",
                    "warc/revisit", "C" * 32, "1"]]

        def handler(request):
            url = str(request.url)
            seen.append(url)
            if url == msci.METHODOLOGY["capture_url"]:
                return httpx.Response(200, content=payload)
            if url.startswith(msci.CDX_URL):
                body = json.dumps(listing if "msci-world-index.pdf" in url and "255599" in url else []).encode()
                return httpx.Response(200, content=body)
            if url == "https://web.archive.org/web/20261015000000id_/http://www.msci.com:80/documents/10199/255599/msci-world-index.pdf":
                return httpx.Response(200, content=pdf)
            return httpx.Response(404)
        with TemporaryDirectory() as temp, mock.patch.dict(msci.METHODOLOGY, pins):
            root = Path(temp)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                report = msci.collect(root, client=client, indexes={"WORLD"}, log=lambda _: None)
                again = msci.collect(root, client=client, indexes={"WORLD"}, log=lambda _: None)
            self.assertEqual(report["stored_parsed"], 1)
            self.assertEqual(report["cdx_rows_other_url"], 1)
            self.assertEqual(again["already_stored"], 1)
            captures = [url for url in seen if "/web/2026" in url]
            self.assertEqual(len(captures), 1)
            summary = msci.read_msci_regional_summary(root)
            self.assertEqual(summary["panels"]["WORLD"]["latest_composition"]["constituent_count"], 1604)


    def test_source_health_prioritizes_new_captures_and_reuses_verified_cdx(self):
        old_pdf = factsheet(asof="AUG 31, 2024")
        new_pdf = factsheet(asof="SEP 30, 2026")
        payload, pins = self.methodology(None)
        urls = [original for original, index in msci.ORIGINAL_URLS.items()
                if index == "WORLD"]
        header = ["timestamp", "original", "statuscode", "mimetype", "digest", "length"]
        visits = []
        with TemporaryDirectory() as temp, mock.patch.dict(msci.METHODOLOGY, pins):
            root = Path(temp)
            msci.store_methodology(root, payload)
            for original in urls:
                body = [header]
                if original == WORLD_URL:
                    body.extend([
                        ["20240918000000", original, "200", "application/pdf",
                         msci.cdx_digest(old_pdf), str(len(old_pdf))],
                        ["20261016000000", original, "200", "application/pdf",
                         msci.cdx_digest(new_pdf), str(len(new_pdf))],
                    ])
                msci.store_cdx_listing(root, original, json.dumps(body).encode())

            def handler(request):
                url = str(request.url)
                visits.append(url)
                if url == msci.capture_url("20261016000000", WORLD_URL):
                    return httpx.Response(200, content=new_pdf)
                if url == msci.capture_url("20240918000000", WORLD_URL):
                    return httpx.Response(500)
                return httpx.Response(503)

            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                report = msci.collect(root, client=client, indexes={"WORLD"},
                                      prefer_recent=True,
                                      capture_not_before=date(2026, 9, 1),
                                      log=lambda _: None)
            self.assertEqual(report["stored_parsed"], 1)
            self.assertEqual(report["cdx_cache_reused"], len(urls))
            self.assertEqual(report["excluded_older_captures"], 1)
            self.assertEqual(report["unique_captures"], 1)
            self.assertEqual(report["already_stored"], 0)
            self.assertEqual(visits, [msci.capture_url("20261016000000", WORLD_URL)])

            # Any tampered or swapped archived listing must not be silently
            # trusted as the basis for acquisition.
            parent = root / msci.ARCHIVE_DIR / "cdx" / msci.sha256(WORLD_URL.encode()).hexdigest()[:16]
            folder = next(parent.iterdir())
            (folder / "listing.json").write_bytes(b"[]")
            with self.assertRaisesRegex(msci.MsciFactsheetError, "bundle_file_hash_mismatch"):
                msci._latest_cdx_listing(root, WORLD_URL)

    def test_cdx_request_policy_stop_preserves_cached_progress_for_next_run(self):
        from finance_dashboard.source_policy_types import PolicyDeferred
        payload, pins = self.methodology(None)
        originals = {WORLD_URL: "WORLD", ACWI_URL: "ACWI"}
        calls = []
        first_name = min(originals).rsplit("/", 1)[-1]
        def handler(request):
            import time
            url = str(request.url)
            calls.append(url)
            if first_name in url:
                return httpx.Response(200, content=json.dumps([
                    ["timestamp","original","statuscode","mimetype","digest","length"]
                ]).encode())
            raise PolicyDeferred("internet-archive", "request-budget", time.time() + 60)
        with TemporaryDirectory() as temp, mock.patch.dict(msci.METHODOLOGY, pins), \
             mock.patch.dict(msci.ORIGINAL_URLS, originals, clear=True):
            root = Path(temp)
            msci.store_methodology(root, payload)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                first = msci.collect(root, client=client, log=lambda _: None)
                second = msci.collect(root, client=client, log=lambda _: None)
            self.assertEqual(first["source_policy_deferred"], 1)
            self.assertEqual(first["cdx_listings"], 1)
            self.assertEqual(first["cdx_missing"], 1)
            self.assertEqual(second["cdx_cache_reused"], 1)
            self.assertEqual(second["cdx_missing"], 1)
            self.assertEqual(len([u for u in calls if first_name in u]), 1)


class OwnerUploadedMsciTests(unittest.TestCase):
    def _original(self):
        return factsheet(index="EAFE", rows=[
            ("MSCI EAFE", "1.23", "16.50", "13.20", "2.25"),
            ("MSCI World", "1.52", "22.69", "17.92", "4.10"),
        ])

    def test_direct_pdf_enters_existing_original_evidence_without_forged_wayback_identity(self):
        payload = self._original()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = ArchiveTests()
            methodology, pins = fixture.methodology(root)
            with mock.patch.dict(msci.METHODOLOGY, pins):
                msci.store_methodology(root, methodology)
                canonical = next(url for url, index in msci.ORIGINAL_URLS.items()
                                 if index == "EAFE")
                digest, receipt = msci.store_manual_factsheet(
                    root, "EAFE", canonical, payload)
                self.assertEqual(len(digest), 64)
                self.assertTrue(receipt.endswith(".json"))
                evidence = msci.read_msci_regional_evidence(root)
                self.assertEqual(msci.series_values(evidence, "EAFE/PE"),
                                 {date(2026, 9, 1): Decimal("16.50")})
                self.assertEqual(msci.series_values(evidence, "EAFE/PE_FWD"),
                                 {date(2026, 9, 1): Decimal("13.20")})
                proof = next(row for row in evidence["document_proofs"]
                             if row["index"] == "EAFE")
                self.assertIsNone(proof["capture_timestamp"])
                self.assertIsNone(proof["cdx_digest"])
                self.assertTrue(proof["capture_url"].startswith("owner-upload:sha256:"))
                self.assertFalse(evidence["first_publication_verified"])
                manual = next((root / msci.ARCHIVE_DIR / "manual-documents" / "EAFE")
                              .glob("*/manifest.json"))
                self.assertFalse(json.loads(manual.read_text())["publisher_origin_verified"])
                # Same original re-upload creates another receipt, not a
                # duplicate printed observation, fabricated index month or
                # overwritten archive.
                msci.store_manual_factsheet(root, "EAFE", canonical, payload)
                self.assertEqual(len(msci.read_msci_regional_evidence(root)
                                     ["document_proofs"]), 1)
                (manual.parent / "publisher.pdf").write_bytes(b"tampered")
                with self.assertRaises(msci.MsciFactsheetError):
                    msci.read_msci_regional_evidence(root)

    def test_wrong_printed_index_is_rejected_without_receipt_or_evidence(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            canonical = next(url for url, index in msci.ORIGINAL_URLS.items()
                             if index == "EAFE")
            with self.assertRaises(msci.MsciFactsheetError):
                msci.store_manual_factsheet(root, "EAFE", canonical, factsheet())
            self.assertFalse(list((root / msci.ARCHIVE_DIR).glob(
                "manual-documents/EAFE/retrievals/*.json")))

    def test_direct_pdf_and_archive_conflicting_prints_block_same_index_month(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = ArchiveTests()
            methodology, pins = fixture.methodology(root)
            canonical = next(url for url, index in msci.ORIGINAL_URLS.items()
                             if index == "EAFE")
            with mock.patch.dict(msci.METHODOLOGY, pins):
                msci.store_methodology(root, methodology)
                msci.store_manual_factsheet(root, "EAFE", canonical, self._original())
                # The archive's own document prints a different EAFE value
                # for the same month, so neither is automatically selected.
                historical = factsheet(index="EAFE", rows=[
                    ("MSCI EAFE", "1.23", "16.70", "13.20", "2.25")])
                msci.store_capture(root, row("20261016000000", canonical, historical),
                                   historical)
                evidence = msci.read_msci_regional_evidence(root)
                self.assertEqual(msci.series_values(evidence, "EAFE/PE"), {})
                self.assertEqual(msci.series_values(evidence, "EAFE/PE_FWD"),
                                 {date(2026, 9, 1): Decimal("13.20")})
                self.assertTrue(any(item["index"] == "EAFE" and item["measure"] == "pe"
                                    for item in evidence["conflicts"]))


class CompositionGateTests(unittest.TestCase):
    def evidence(self, months=("2026-09-01",)):
        panels = {index: {"bound": True, "composition_months": list(months),
                          "coverage": {"months_with_values": 3, "missing_months_in_span": ["2026-07-01"]}}
                  for index in msci.BOUND_INDEXES}
        return {"original_source_hash_verified": True, "methodology": {"edition": "March 2021"},
                "documents_parsed": 7, "documents_rejected": 0, "rejections": {}, "conflicts": [], "panels": panels}

    def test_all_seven_gates_pass_and_the_role_is_conditional_on_stated_limits(self):
        result = regional_composition_checks(self.evidence())
        self.assertEqual([check["state"] for check in result["checks"]], ["passed"] * 7)
        self.assertTrue(result["resolved"] and result["conditional"])
        codes = {item["code"] for item in result["checks"][-1]["limitations"]}
        self.assertTrue({"archived_factsheet_months_missing", "history_starts_with_archive_captures",
                         "country_weights_top_n_only"} <= codes)

    def test_missing_evidence_blocks_a_gap_never_passes_and_conflicts_are_listed(self):
        self.assertFalse(regional_composition_checks({})["resolved"])
        evidence = self.evidence()
        evidence["panels"]["JAPAN"]["composition_months"] = []
        self.assertEqual(regional_composition_checks(evidence)["checks"][2]["state"], "incomplete")
        evidence = self.evidence()
        evidence["conflicts"] = [{"index": "USA", "month": "2026-09-01", "measure": "composition", "values": []}]
        result = regional_composition_checks(evidence)
        self.assertEqual(result["checks"][3]["blocked_conflict_months"], evidence["conflicts"])
        self.assertIn("printed_value_conflicts_blocked",
                      {item["code"] for item in result["checks"][-1]["limitations"]})


class OriginalCollectionCancellationTests(unittest.TestCase):
    def test_cancelled_original_collection_does_not_issue_any_request(self):
        from threading import Event
        stopped = Event()
        stopped.set()
        requested = []
        transport = httpx.MockTransport(lambda request: (
            requested.append(str(request.url)) or httpx.Response(500)))
        with httpx.Client(transport=transport) as client, TemporaryDirectory() as directory:
            output = msci.collect(Path(directory), client=client,
                                  indexes={"EUROPE", "EAFE", "JAPAN"},
                                  stopped=stopped, log=lambda _: None)
        self.assertEqual(output, {"cancelled": 1})
        self.assertEqual(requested, [])


if __name__ == "__main__":
    unittest.main()
