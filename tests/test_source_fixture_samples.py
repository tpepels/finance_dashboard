"""Publisher-derived row samples must reproduce ingestion parser results and
never manufacture data when the exact archived original is unavailable."""
import csv
from datetime import date
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from finance_dashboard.bis import ProviderError
from finance_dashboard.provider_parsers import PINK_SHEET_URL, parse_pink_sheet_price
from finance_dashboard.source_fixture_samples import collect_failure_samples
from finance_dashboard.wid import WID_ROOT, parse_wid_bundle, parse_piketty_original

HERE = Path(__file__).parent / "fixtures" / "wid_top1"


def _csv(header, rows):
    output=io.StringIO(newline="")
    writer=csv.DictWriter(output,fieldnames=header,delimiter=";",lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _make_wid_archive(root, area, data_raw, meta_raw):
    archive=root/"wid"/area/("a"*64)
    archive.mkdir(parents=True)
    sources={}
    for kind,raw in (("data",data_raw),("metadata",meta_raw)):
        name=f"WID_{kind}_{area}.csv"
        (archive/name).write_bytes(raw)
        sources[kind]={"file":name,"url":f"{WID_ROOT}/{name}",
                       "sha256":sha256(raw).hexdigest(),"bytes":len(raw)}
    (archive/"manifest.json").write_text(json.dumps({
        "schema_version":1,"publisher":"WID.world","area":area,
        "retrieved_at_utc":"2026-11-15T13:00:00+00:00",
        "sources":sources}),encoding="utf-8")
    return archive


class ArchivedOriginalSamplingTests(unittest.TestCase):
    def test_real_wid_publisher_rows_reproduce_original_share_ingestion(self):
        # The checked-in US excerpt comes directly from the publisher,
        # with the original full-file SHA256 in wid_top1/provenance.json.
        data=(HERE/"US_data.csv").read_bytes()
        metadata=(HERE/"US_metadata.csv").read_bytes()
        with TemporaryDirectory() as temp:
            root=Path(temp)
            _make_wid_archive(root,"US",data,metadata)
            result=collect_failure_samples(root,[
                {"id":"inequality.us.pretax_income.top1","state":"stale"}])
            self.assertEqual(result["unavailable"],[])
            self.assertEqual(len(result["samples"]),1)
            fixture=result["samples"][0]
            self.assertEqual(fixture["source_sha256"]["data"],sha256(data).hexdigest())
            self.assertEqual(fixture["source_sha256"]["metadata"],sha256(metadata).hexdigest())
            self.assertEqual(fixture["source_urls"]["data"],f"{WID_ROOT}/WID_data_US.csv")
            parsed=parse_wid_bundle(
                _csv(fixture["data_header"],fixture["data_rows"]),
                _csv(fixture["metadata_header"],fixture["metadata_rows"]),area="US")
            self.assertEqual(parsed.observations[("sptinc992j","p99p100")][date(2024,1,1)],
                             Decimal("0.2073"))
            self.assertEqual(parsed.observations[("shweal992j","p90p100")][date(2024,1,1)],
                             Decimal("0.6954"))
            # Changing the selected source unit remains an ingestion error.
            meta=[dict(row) for row in fixture["metadata_rows"]]
            next(r for r in meta if r["variable"]=="sptinc992j")["unit"]="ratio"
            with self.assertRaisesRegex(ProviderError,"concept, population, unit"):
                parse_wid_bundle(_csv(fixture["data_header"],fixture["data_rows"]),
                                 _csv(fixture["metadata_header"],meta),area="US")

    def test_invalid_or_missing_originals_never_generate_accepted_samples(self):
        data=(HERE/"US_data.csv").read_bytes()
        metadata=(HERE/"US_metadata.csv").read_bytes()
        with TemporaryDirectory() as temp:
            root=Path(temp)
            archive=_make_wid_archive(root,"US",data,metadata)
            (archive/"WID_data_US.csv").write_bytes(data+b"unverified")
            result=collect_failure_samples(root,[
                {"id":"inequality.us.pretax_income.top1","state":"collection_failed"}])
            self.assertEqual(result["samples"],[])
            self.assertEqual(result["unavailable"][0]["reason"],
                             "verified_wid_original_pair_unavailable")
            self.assertNotIn("unverified",json.dumps(result))
            (archive/"WID_data_US.csv").unlink()
            (archive/"WID_data_US.csv").symlink_to(HERE/"US_data.csv")
            result=collect_failure_samples(root,[
                {"id":"inequality.us.pretax_income.top1","state":"collection_failed"}])
            self.assertFalse(result["samples"])

    def test_pink_sheet_rejected_workbook_rows_are_hash_checked_and_parseable(self):
        rows=[
            ["World Bank monthly prices, nominal USD"],
            ["Publisher series"],
            ["", "Gold", "Copper"],
            ["", "($/troy oz)", "($/mt)"],
            ["2026M08", 4411, 14326],
            ["2026M09", 4319, 14474],
            ["2026M10", 4105, 14508],
        ]
        raw=bytes([80,75,3,4])+b"archived-copper-xlsx"
        sid="prices.commodity.copper_usd"
        with TemporaryDirectory() as temp:
            root=Path(temp)
            archive=root/"rejected-responses"/sid/("b"*64)
            archive.mkdir(parents=True)
            (archive/"response-0.bin").write_bytes(raw)
            (archive/"manifest.json").write_text(json.dumps({
                "schema_version":1,"series_id":sid,
                "provider":"WORLD_BANK_PINK_SHEET",
                "retrieved_at_utc":"2026-11-15T13:45:00+00:00",
                "sources":[{
                    "file":"response-0.bin","url":PINK_SHEET_URL,
                    "bytes":len(raw),"sha256":sha256(raw).hexdigest()}],
            }))
            workbook=MagicMock()
            workbook.sheet_names=["Monthly Prices"]
            workbook.get_sheet_by_name.return_value.to_python.return_value=rows
            with patch("python_calamine.CalamineWorkbook.from_filelike",
                       return_value=workbook):
                sample=collect_failure_samples(root,[{"id":sid,"state":"collection_failed"}])
            self.assertEqual(sample["unavailable"],[])
            self.assertEqual(sample["samples"][0]["source_sha256"],sha256(raw).hexdigest())
            values=parse_pink_sheet_price(sample["samples"][0]["rows"],"Copper")
            self.assertEqual(values[date(2026,10,1)],Decimal("14508"))
            with patch("python_calamine.CalamineWorkbook.from_filelike",
                       return_value=workbook):
                available=collect_failure_samples(root,[{"id":sid,"state":"available"}])
            self.assertEqual(len(available["samples"]),1)
            self.assertEqual(available["samples"][0]["kind"],"world_bank_pink_sheet")
            # A rejected HTTP response body must never be exported as a
            # source fixture or interpreted as economic data.
            (archive/"response-0.bin").write_bytes(b"<html>HTTP 403 SECRET</html>")
            unavailable=collect_failure_samples(root,[{"id":sid,"state":"collection_failed"}])
            self.assertFalse(unavailable["samples"])
            self.assertNotIn("SECRET",json.dumps(unavailable))

    def test_bls_archived_publisher_zip_preserves_native_mean_median_total(self):
        from zipfile import ZipFile
        from finance_dashboard.bls_oews import parse_national_rows
        source_id="labour.us.oews_all_mean_hourly"
        rows=[
            ["May 2025 OEWS"],
            ["OCC_CODE","OCC_TITLE","TOT_EMP","H_MEAN","H_MEDIAN"],
            ["00-0000","All Occupations",155495730,33.54,24.51],
            ["11-0000","Management occupations",11132700,69.84,60.83],
        ]
        # A tiny ZIP-shaped original is test-only; the exported row values
        # correspond to the BLS May 2025 All Occupations source excerpt.
        zipped=io.BytesIO()
        with ZipFile(zipped,"w") as archive:
            archive.writestr("oesm25nat/national_M2025_dl.xlsx",
                             bytes([80,75,3,4])+b"publisher-workbook-test")
        raw=zipped.getvalue()
        with TemporaryDirectory() as temp:
            root=Path(temp)
            archive=root/"responses"/source_id/("c"*64)
            archive.mkdir(parents=True)
            (archive/"response-0.bin").write_bytes(raw)
            url="https://www.bls.gov/oes/special-requests/oesm25nat.zip"
            (archive/"manifest.json").write_text(json.dumps({
                "schema_version":1,"provider":"BLS_OEWS",
                "series_id":source_id,
                "retrieved_at_utc":"2026-11-15T13:00:00+00:00",
                "sources":[{"file":"response-0.bin","url":url,
                            "bytes":len(raw),"sha256":sha256(raw).hexdigest()}],
            }))
            fake=MagicMock()
            fake.sheet_names=["national_M2025_dl","Field Descriptions"]
            data_sheet=MagicMock()
            data_sheet.to_python.return_value=rows
            notes=MagicMock()
            notes.to_python.return_value=[["Field","Description"]]
            fake.get_sheet_by_index.side_effect=[data_sheet,notes]
            with patch("python_calamine.CalamineWorkbook.from_filelike",
                       return_value=fake):
                result=collect_failure_samples(root,[
                    {"id":source_id,"provider":"BLS_OEWS","state":"collection_failed"}])
            self.assertEqual(result["unavailable"],[])
            self.assertEqual(len(result["samples"]),1)
            sample=result["samples"][0]["samples"][0]
            self.assertEqual(sample["original_sha256"],sha256(raw).hexdigest())
            self.assertEqual(sample["expected_values"]["H_MEAN"],"33.54")
            self.assertEqual(sample["expected_values"]["H_MEDIAN"],"24.51")
            self.assertEqual(parse_national_rows(
                [sample["header"],sample["national_total_row"]],2025),
                {"H_MEAN":Decimal("33.54"),"H_MEDIAN":Decimal("24.51")})
            (archive/"response-0.bin").write_bytes(b"<html>blocked by source</html>")
            blocked=collect_failure_samples(root,[
                {"id":source_id,"provider":"BLS_OEWS","state":"collection_failed"}])
            self.assertFalse(blocked["samples"])
            self.assertEqual(blocked["unavailable"][0]["reason"],
                             "verified_bls_national_archive_unavailable")

    def test_one_broken_sampler_does_not_prevent_other_source_fixture_exports(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            with patch("finance_dashboard.source_fixture_samples._sample_wid",
                       side_effect=RuntimeError("test malformed WID archive")), \
                 patch("finance_dashboard.source_fixture_samples._sample_pink_sheet",
                       return_value={"kind":"world_bank_pink_sheet","rows":[["Copper"]]}):
                result=collect_failure_samples(root,[
                    {"id":"inequality.us.pretax_income.top1","state":"collection_failed"},
                    {"id":"prices.commodity.copper_usd","state":"collection_failed"},
                ])
            self.assertEqual(len(result["samples"]),1)
            self.assertEqual(result["samples"][0]["kind"],"world_bank_pink_sheet")
            self.assertEqual(result["unavailable"][0]["reason"],"source_sampling_failed")
            self.assertNotIn("malformed WID",json.dumps(result))


    def test_sec_archived_zip_schema_and_parser_outcome_are_deduplicated(self):
        from test_extra_publisher_sources import zipped_sec
        from finance_dashboard.extra_publisher_sources import SEC_NMFP_INDEX, SEC_NMFP_ROOT
        from finance_dashboard.source_fixture_samples import collect_sec_archive_inspection
        raw = zipped_sec()
        zip_url = SEC_NMFP_ROOT + "20261101-20261130_nmfp.zip"
        html = (f'<a href="{zip_url}">2026 October NMFP</a>').encode()
        ids = ("funding.us.sec_nmfp_net_assets_musd",
               "funding.us.sec_nmfp_wam_days")
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for sid in ids:
                folder = root / "rejected-responses" / sid / ("a"*64)
                folder.mkdir(parents=True)
                sources = []
                for index, (body, url) in enumerate((
                        (html, SEC_NMFP_INDEX), (raw, zip_url))):
                    name = f"response-{index}.bin"
                    (folder / name).write_bytes(body)
                    sources.append({"file": name, "bytes": len(body),
                                    "sha256": sha256(body).hexdigest(), "url": url,
                                    "http_status": 200})
                (folder / "manifest.json").write_text(json.dumps({
                    "schema_version": 1, "series_id": sid, "provider": "SEC_NMFP",
                    "retrieved_at_utc": "2026-11-15T20:00:00+00:00",
                    "sources": sources,
                }))
            report = collect_sec_archive_inspection(root, [
                {"id": sid, "provider": "SEC_NMFP",
                 "state": "collection_failed", "last_failure_code": "source_invalid"}
                for sid in ids])
            self.assertEqual(report["archives_found"], 1)
            self.assertEqual(len(report["archives_inspected"]), 1)
            entry = report["archives_inspected"][0]
            self.assertEqual(entry["publisher_month"], "2026-10-01")
            self.assertEqual(entry["source_sha256"], sha256(raw).hexdigest())
            self.assertEqual(entry["referenced_by"], list(ids))
            self.assertEqual(entry["tables"]["SUBMISSION"]["missing_columns"], [])
            self.assertEqual(entry["parser_outcome"], "accepted_shape_not_certified")
            self.assertEqual(entry["parsed_metric_keys"],
                             ["NET_ASSETS_MUSD", "WAL_DAYS",
                              "WAM_DAYS", "WEEKLY_LIQUIDITY_PCT"])
            self.assertNotIn("200000000", json.dumps(report))
            self.assertNotIn("S000000001", json.dumps(report))

    def test_sec_inspection_reports_missing_original_without_substituting_bytes(self):
        from finance_dashboard.source_fixture_samples import collect_sec_archive_inspection
        with TemporaryDirectory() as temporary:
            report = collect_sec_archive_inspection(Path(temporary), [
                {"id": "funding.us.sec_nmfp_wal_days",
                 "provider": "SEC_NMFP", "state": "collection_failed",
                 "last_failure_code": "sec_nmfp_schema_invalid"}])
        self.assertEqual(report["archives_found"], 0)
        self.assertEqual(report["archives_inspected"], [])
        self.assertEqual(report["unavailable"][0]["reason"],
                         "no_hash_identified_archived_sec_zip")

    def test_wid_sampling_reports_full_row_count_not_just_four_excerpts(self):
        data = (HERE / "US_data.csv").read_bytes()
        meta = (HERE / "US_metadata.csv").read_bytes()
        lines = data.decode("utf-8-sig").splitlines()
        copied = lines[1].split(";")
        header = lines[0].split(";")
        self.assertIn("year", header)
        self.assertIn("variable", header)
        self.assertIn("percentile", header)
        self.assertIn("country", header)
        year_column = header.index("year")
        augmented = data.decode("utf-8-sig")
        if not augmented.endswith("\n"):
            augmented += "\n"
        for year in range(1930, 1939):
            row = list(copied)
            row[year_column] = str(year)
            augmented += ";".join(row) + "\n"
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _make_wid_archive(root, "US", augmented.encode("utf-8"), meta)
            samples = collect_failure_samples(root, [
                {"id": "inequality.us.pretax_income.top1", "state": "stale"}])
        self.assertEqual(samples["unavailable"], [])
        selected = samples["samples"][0]["selected_keys"]
        exact = next(item for item in selected
                     if item["variable"] == copied[header.index("variable")]
                     and item["percentile"] == copied[header.index("percentile")])
        self.assertGreater(exact["rows"], exact["sampled_rows"])
        self.assertLessEqual(exact["sampled_rows"], 4)

    def test_optional_wid_monetary_measure_with_source_but_no_method_can_be_sampled(self):
        # Synthetic extension is explicit; it exercises the *same* parser
        # against the schema copied from the real WID captured excerpt.
        from test_wid_piketty import extended_pair
        data,metadata=extended_pair()
        metadata=metadata.replace("WID national accounts methodology","")
        with TemporaryDirectory() as temp:
            root=Path(temp)
            _make_wid_archive(root,"US",data.encode(),metadata.encode())
            sample=collect_failure_samples(root,[
                {"id":"piketty.us.wealth_to_income.national","state":"collection_failed"}])
            self.assertEqual(sample["unavailable"],[])
            row=sample["samples"][0]
            parsed=parse_piketty_original(
                _csv(row["data_header"],row["data_rows"]),
                _csv(row["metadata_header"],row["metadata_rows"]),area="US")
            self.assertEqual(parsed[("wnweal999i","p0p100")][date(2024,1,1)],
                             Decimal("6"))


if __name__=="__main__":
    unittest.main()
