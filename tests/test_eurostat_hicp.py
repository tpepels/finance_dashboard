"""Eurostat ECOICOP ver.2 HICP: managed capture and an independent strict reader."""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx

from finance_dashboard.constructed_source_reconciliation import _eurostat_hicp
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.source_capture import SourceAcquisition
from finance_dashboard.source_reconciliation import EvidenceError

URL = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_minr"
       "?freq=M&unit=I25&coicop18=TOTAL&geo=EA")


def payload(unit="I25"):
    return {"version": "2.0", "class": "dataset", "source": "ESTAT", "label": "HICP",
            "id": ["freq", "unit", "coicop18", "geo", "time"], "size": [1, 1, 1, 1, 3],
            "dimension": {"freq": {"category": {"index": {"M": 0}}}, "unit": {"category": {"index": {unit: 0}}},
                          "coicop18": {"category": {"index": {"TOTAL": 0}}}, "geo": {"category": {"index": {"EA": 0}}},
                          "time": {"category": {"index": {"2026-08": 0, "2026-09": 1, "2026-10": 2}}}},
            "value": {"0": 101.2, "1": 101.5, "2": 101.9}}


class EurostatHicpTests(unittest.TestCase):
    def test_capture_and_independent_reader(self):
        with TemporaryDirectory() as temp:
            with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload()))) as http:
                result = SourceAcquisition(ProviderRouter(http), Path(temp)).fetch("prices.ea.hicp_index_2025")
            self.assertEqual(result.observations[date(2026, 10, 1)], Decimal("101.9"))
            manifest = json.loads(next(Path(temp).glob("responses/*/*/manifest.json")).read_text())
            self.assertEqual(manifest["scope"], "full_source_snapshot")
            # The recorded URL must identify the exact series for the independent reader.
            self.assertEqual(_eurostat_hicp(json.dumps(payload()).encode(), manifest["sources"][0]["url"])[date(2026, 10, 1)],
                             Decimal("101.9"))
        raw = json.dumps(payload()).encode()
        values = _eurostat_hicp(raw, URL)
        self.assertEqual(values[date(2026, 9, 1)], Decimal("101.5"))
        with self.assertRaises(EvidenceError):
            _eurostat_hicp(json.dumps(payload("I15")).encode(), URL)
        with self.assertRaises(EvidenceError):
            _eurostat_hicp(raw, URL.replace("unit=I25", "unit=I15"))


if __name__ == "__main__":
    unittest.main()
