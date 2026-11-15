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
            # A rejected HTTP response body must never be exported as a
            # source fixture or interpreted as economic data.
            (archive/"response-0.bin").write_bytes(b"<html>HTTP 403 SECRET</html>")
            unavailable=collect_failure_samples(root,[{"id":sid,"state":"collection_failed"}])
            self.assertFalse(unavailable["samples"])
            self.assertNotIn("SECRET",json.dumps(unavailable))

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
            self.assertEqual(parsed[("wwealn999i","p0p100")][date(2024,1,1)],
                             Decimal("6"))


if __name__=="__main__":
    unittest.main()
