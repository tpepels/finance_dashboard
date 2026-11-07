"""EU KLEMS 2025 workbooks: exact pinned file, TOT row, and an independent reader."""
from datetime import date
from decimal import Decimal
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.sax.saxutils import escape
import zipfile

import httpx

from finance_dashboard.captured_sources import _euklems
from finance_dashboard.euklems import EUKLEMS_FILES, euklems_url, parse_euklems_workbook
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.source_capture import SourceAcquisition
from finance_dashboard.source_reconciliation import EvidenceError


def workbook(sheets: dict[str, list[list]]) -> bytes:
    """A minimal xlsx: inline strings and numbers, one sheet per entry."""
    def cell(ref, value):
        if isinstance(value, (int, float)):
            return f'<c r="{ref}"><v>{value}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
    def column(index):
        name = ""
        index += 1
        while index:
            index, rest = divmod(index - 1, 26)
            name = chr(65 + rest) + name
        return name
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                      for i in range(1, len(sheets) + 1)) + "</Types>")
        package.writestr("_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        package.writestr("xl/workbook.xml",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(sheets, 1))
            + "</sheets></workbook>")
        package.writestr("xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                      for i in range(1, len(sheets) + 1)) + "</Relationships>")
        for i, rows in enumerate(sheets.values(), 1):
            body = "".join(f'<row r="{r + 1}">' + "".join(cell(f"{column(c)}{r + 1}", v) for c, v in enumerate(row)) + "</row>"
                           for r, row in enumerate(rows))
            package.writestr(f"xl/worksheets/sheet{i}.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"<sheetData>{body}</sheetData></worksheet>")
    return buffer.getvalue()


NATIONAL = workbook({"Legend": [["DE"]], "VA_CP": [
    ["var", "nace_r2_code", "geo_code", "nace_r2_name", "geo_name", "1995", "1996"],
    ["VA_CP", "A", "DE", "Agriculture", "Germany", 1.5, 2.5],
    ["VA_CP", "TOT", "DE", "Total - all NACE activities", "Germany", 1800000.25, 1850000.5]]})
GROWTH = workbook({"LAB": [
    ["nace_r2_code", "geo_code", "nace_r2_name", "geo_name", "var", "1995", "1996"],
    ["TOT", "DE", "Total - all NACE activities", "Germany", "LAB", 1100000.125, ""]]})
DEFINITION = {"id": "test.de.euklems_va", "provider": "EUKLEMS", "source_key": "DE/TOT/VA_CP", "frequency": "A",
              "unit": "million_local_currency", "currency": "EUR", "status": "mapped", "geography": "DEU",
              "source_url": "https://euklems-intanprod-llee.luiss.it/download/", "name": "t", "theme": "labour_capital",
              "measurement": "t", "revision_policy": "revisable", "rights": "review_required", "notes": "t"}


class EuklemsTests(unittest.TestCase):
    def test_capture_fetches_the_pinned_workbook_and_independent_reader_agrees(self):
        with TemporaryDirectory() as temp:
            seen = []
            def handler(request):
                seen.append(str(request.url))
                return httpx.Response(200, content=NATIONAL)
            with httpx.Client(transport=httpx.MockTransport(handler)) as http:
                router = ProviderRouter(http)
                router.definitions[DEFINITION["id"]] = DEFINITION
                result = SourceAcquisition(router, Path(temp)).fetch(DEFINITION["id"])
            manifest = json.loads(next(Path(temp).glob("responses/*/*/manifest.json")).read_text())
        self.assertEqual(seen, ["https://dl.dropboxusercontent.com/" + EUKLEMS_FILES["DE"]["national"]])
        self.assertEqual(result.observations, {date(1995, 1, 1): Decimal("1800000.25"), date(1996, 1, 1): Decimal("1850000.5")})
        values, _ = _euklems(NATIONAL, DEFINITION, manifest["sources"][0]["url"])
        self.assertEqual(values, result.observations)

    def test_lab_comes_from_the_growth_workbook_and_blanks_stay_missing(self):
        key = "DE/TOT/LAB"
        self.assertTrue(euklems_url(key).endswith(EUKLEMS_FILES["DE"]["growth"]))
        self.assertEqual(parse_euklems_workbook(GROWTH, key), {date(1995, 1, 1): Decimal("1100000.125")})
        values, _ = _euklems(GROWTH, {**DEFINITION, "source_key": key}, euklems_url(key))
        self.assertEqual(values, {date(1995, 1, 1): Decimal("1100000.125")})

    def test_other_country_variable_industry_or_url_is_rejected(self):
        with self.assertRaises(ValueError):
            euklems_url("DE/MARKT/VA_CP")
        with self.assertRaises(ValueError):
            euklems_url("JP/TOT/VA_CP")
        url = euklems_url("DE/TOT/VA_CP")
        for raw, definition, address in (
                (workbook({"VA_CP": [["var", "nace_r2_code", "geo_code", "1995"], ["VA_CP", "TOT", "FR", 1.0]]}), DEFINITION, url),
                (b"not a workbook", DEFINITION, url),
                (NATIONAL, {**DEFINITION, "source_key": "FR/TOT/VA_CP"}, url),
                (NATIONAL, DEFINITION, url.replace("DE_national", "FR_national"))):
            with self.subTest(address=address[-30:]), self.assertRaises(EvidenceError):
                _euklems(raw, definition, address)


if __name__ == "__main__":
    unittest.main()
