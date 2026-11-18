"""Plan phase D1a: AQR quality, low-beta and century-of-factor-premia returns.

Fixtures are factual cell excerpts of the workbooks downloaded on 2026-11-18;
tests pack them into a minimal workbook (see xlsx_from_factual_cells).
"""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

import os
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finance_dashboard.database import Base, ObservationVersion, make_engine
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.service import IngestionService, current_observations
from finance_dashboard.aqr import AQR_SERIES, AQR_WORKBOOKS, aqr_source_key, aqr_url, parse_aqr_rows
from finance_dashboard.bis import ProviderError
from finance_dashboard.captured_sources import _aqr, _workbook_rows
from finance_dashboard.catalog import load_documents
from finance_dashboard.provider_registry import PROVIDER_REGISTRY
from finance_dashboard.source_reconciliation import EvidenceError
from test_captured_source_families import xlsx_from_factual_cells

FIXTURES = Path(__file__).parent / "fixtures" / "aqr"
PROVENANCE = {item["workbook"]: item for item in json.loads((FIXTURES / "provenance.json").read_text())["workbooks"]}


def excerpt(workbook):
    return json.loads((FIXTURES / workbook.replace(".xlsx", ".json")).read_text())


def workbook_bytes(workbook, edit=None):
    data = excerpt(workbook)
    rows = [row["cells"] for row in data["rows"]]
    if edit:
        edit(rows)
    return xlsx_from_factual_cells(rows, data["sheet"])


def definition(series_id):
    return {"source_key": aqr_source_key(series_id), "unit": "ratio", "frequency": "M"}


class AqrFactorTests(unittest.TestCase):
    def test_registration_policy_and_catalogue(self):
        catalog = {item["id"]: item for item in load_documents()[0]["series"]}
        self.assertEqual(PROVIDER_REGISTRY["AQR_FACTORS"].handler, "fetch_aqr_factors")
        policies = json.loads((Path(__file__).parents[1] / "definitions" / "source_policies.json").read_text())["policies"]
        self.assertTrue(any("www.aqr.com" in policy["hosts"] for policy in policies))
        for sid, (workbook, _column) in AQR_SERIES.items():
            item = catalog[sid]
            self.assertEqual((item["provider"], item["source_key"], item["source_url"], item["unit"]),
                             ("AQR_FACTORS", aqr_source_key(sid), aqr_url(workbook), "ratio"))
            self.assertEqual(item["revision_policy"], "revisable")

    def test_parser_and_independent_reader_agree_on_real_cells(self):
        for sid, (workbook, column) in AQR_SERIES.items():
            raw = workbook_bytes(workbook)
            rows = _workbook_rows(raw, AQR_WORKBOOKS[workbook][0])
            parsed = parse_aqr_rows(rows, sid)
            values, metadata = _aqr(raw, definition(sid), aqr_url(workbook))
            self.assertEqual(values, parsed, sid)
            self.assertEqual(metadata["source_variable"], column)
            self.assertGreaterEqual(len(parsed), 2, sid)

    def test_values_are_decimal_ratios_on_month_start_periods(self):
        raw = workbook_bytes("Quality-Minus-Junk-Factors-Monthly.xlsx")
        rows = _workbook_rows(raw, "QMJ Factors")
        us = parse_aqr_rows(rows, "returns.aqr.us.quality_qmj")
        self.assertEqual(us[date(1957, 7, 1)], Decimal("0.0111539791294"))     # cell on 07/31/1957
        self.assertEqual(us[date(2026, 8, 1)], Decimal("-0.0343739863620799"))  # cell on 08/31/2026
        commodities = parse_aqr_rows(_workbook_rows(workbook_bytes("Century-of-Factor-Premia-Monthly.xlsx"),
                                                    "Century of Factor Premia"), "returns.aqr.commodities.market")
        self.assertEqual(min(commodities), date(1926, 7, 1))                   # cell dated 07/30/1926
        self.assertEqual(max(commodities), date(2026, 2, 1))

    def test_identity_order_and_magnitude_are_checked(self):
        workbook = "Betting-Against-Beta-Equity-Factors-Monthly.xlsx"
        sid = "returns.aqr.us.low_beta_bab"

        def rename(rows):
            rows[18][24] = "US"
        with self.assertRaises(ProviderError):
            parse_aqr_rows(_workbook_rows(workbook_bytes(workbook, rename), "BAB Factors"), sid)
        with self.assertRaises(EvidenceError):
            _aqr(workbook_bytes(workbook, rename), definition(sid), aqr_url(workbook))

        def reverse(rows):
            rows[19:] = rows[19:][::-1]
        with self.assertRaises(ProviderError):
            parse_aqr_rows(_workbook_rows(workbook_bytes(workbook, reverse), "BAB Factors"), sid)

        def percent(rows):
            rows[-1][24] = 12.5
        with self.assertRaises(ProviderError):
            parse_aqr_rows(_workbook_rows(workbook_bytes(workbook, percent), "BAB Factors"), sid)
        with self.assertRaises(EvidenceError):    # a different workbook URL is not this source
            _aqr(workbook_bytes(workbook), definition(sid), aqr_url("Quality-Minus-Junk-Factors-Monthly.xlsx"))

    def test_ingestion_reads_each_workbook_once_per_batch(self):
        requests = []

        def publisher(request):
            requests.append(request.url.path)
            workbook = request.url.path.rsplit("/", 1)[-1]
            if workbook not in AQR_WORKBOOKS:
                raise AssertionError("Unexpected request")
            return httpx.Response(200, content=workbook_bytes(workbook), request=request)

        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(publisher)) as http:
            with patch.dict(os.environ, {"FINANCE_SOURCE_EVIDENCE_DIR": str(Path(tmp) / "evidence")}):
                engine = make_engine("sqlite+pysqlite:///" + str(Path(tmp) / "aqr.sqlite3"))
                Base.metadata.create_all(engine)
                service = IngestionService(engine, ProviderRouter(client=http))
                for sid in ("returns.aqr.us.quality_qmj", "returns.aqr.global.quality_qmj"):
                    self.assertEqual(service.refresh(sid)["status"], "success")
                with Session(engine) as session:
                    us = current_observations(session, "returns.aqr.us.quality_qmj")
                    self.assertEqual((us[0].period, us[0].value.normalize()), (date(1957, 7, 1), Decimal("0.0111539791")))
                    self.assertGreater(session.scalar(select(func.count()).select_from(ObservationVersion)), 0)
                engine.dispose()
        self.assertEqual(len(requests), len(set(requests)))

    def test_recorded_workbooks(self):
        self.assertEqual(PROVENANCE["Quality-Minus-Junk-Factors-Monthly.xlsx"]["last_date"], "08/31/2026")
        self.assertEqual(PROVENANCE["Betting-Against-Beta-Equity-Factors-Monthly.xlsx"]["first_date"], "12/31/1930")
        self.assertEqual(PROVENANCE["Century-of-Factor-Premia-Monthly.xlsx"]["last_date"], "02/27/2026")


if __name__ == "__main__":
    unittest.main()
