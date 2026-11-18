"""Plan phase D1b: European Commission economic sentiment indicator via Eurostat (trimmed responses of 2026-11-18)."""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

import httpx

from finance_dashboard.bis import ProviderError
from finance_dashboard.captured_sources import _eurostat_sentiment
from finance_dashboard.catalog import load_documents
from finance_dashboard.eurostat_sentiment import (
    EUROSTAT_SENTIMENT_SERIES, EUROSTAT_SENTIMENT_URL, parse_eurostat_sentiment, sentiment_params,
)
from finance_dashboard.provider_registry import PROVIDER_REGISTRY
from finance_dashboard.source_reconciliation import EvidenceError

FIXTURES = Path(__file__).parent / "fixtures" / "eurostat_sentiment"


def response(geo):
    return (FIXTURES / f"esi_{geo}.json").read_text()


def url(key):
    return str(httpx.Request("GET", EUROSTAT_SENTIMENT_URL, params=sentiment_params(key)).url)


class EurostatSentimentTests(unittest.TestCase):
    def test_registration_and_agreement(self):
        catalog = {item["id"]: item for item in load_documents()[0]["series"]}
        self.assertEqual(PROVIDER_REGISTRY["EUROSTAT_SENTIMENT"].handler, "fetch_eurostat_sentiment")
        for sid, key in EUROSTAT_SENTIMENT_SERIES.items():
            geo = key.rsplit(".", 1)[1]
            self.assertEqual((catalog[sid]["provider"], catalog[sid]["source_key"]), ("EUROSTAT_SENTIMENT", key))
            parsed = parse_eurostat_sentiment(json.loads(response(geo)), key)
            values, _ = _eurostat_sentiment(json.loads(response(geo), parse_float=Decimal), catalog[sid], url(key))
            self.assertEqual(values, parsed, sid)
        euro = parse_eurostat_sentiment(json.loads(response("EA21")), EUROSTAT_SENTIMENT_SERIES["sentiment.ea.esi"])
        self.assertEqual(min(euro), date(1980, 1, 1))
        self.assertEqual(max(euro), date(2026, 10, 1))

    def test_other_area_or_indicator_is_refused(self):
        key = EUROSTAT_SENTIMENT_SERIES["sentiment.ea.esi"]
        with self.assertRaises(ProviderError):
            parse_eurostat_sentiment(json.loads(response("DE")), key)
        with self.assertRaises(ProviderError):
            sentiment_params("ei_bssi_m_r2/M.BS-ESI-I.SA.EA20")
        catalog = {item["id"]: item for item in load_documents()[0]["series"]}
        with self.assertRaises(EvidenceError):
            _eurostat_sentiment(json.loads(response("DE"), parse_float=Decimal), catalog["sentiment.ea.esi"], url(key))


if __name__ == "__main__":
    unittest.main()
