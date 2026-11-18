"""European Commission Economic Sentiment Indicator via Eurostat (dataset ei_bssi_m_r2).

One JSON-stat series per request: ``freq`` M, ``indic`` BS-ESI-I, ``s_adj`` SA
and one ``geo``. The indicator is a survey composite (long-run average 100),
seasonally adjusted; survey results are essentially unrevised, while seasonal
factors may be re-estimated. Missing periods stay absent. The euro area
aggregate is taken in its current composition (EA21 since 2026); when the
euro area enlarges again Eurostat changes the code and this series fails
closed until it is re-registered.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re

from .bis import ProviderError

EUROSTAT_SENTIMENT_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/ei_bssi_m_r2"
EUROSTAT_SENTIMENT_SERIES = {
    "sentiment.ea.esi": "ei_bssi_m_r2/M.BS-ESI-I.SA.EA21",
    "sentiment.de.esi": "ei_bssi_m_r2/M.BS-ESI-I.SA.DE",
    "sentiment.pt.esi": "ei_bssi_m_r2/M.BS-ESI-I.SA.PT",
}
_DIMENSIONS = ["freq", "indic", "s_adj", "geo", "time"]


def sentiment_params(key: str) -> dict[str, str]:
    match = re.fullmatch(r"ei_bssi_m_r2/M\.BS-ESI-I\.SA\.([A-Z0-9_]+)", key)
    if not match or key not in EUROSTAT_SENTIMENT_SERIES.values():
        raise ProviderError("Unapproved Eurostat sentiment series")
    return {"indic": "BS-ESI-I", "s_adj": "SA", "geo": match.group(1), "format": "JSON", "lang": "en"}


def parse_eurostat_sentiment(payload: dict, key: str, start: date | None = None) -> dict[date, Decimal]:
    params = sentiment_params(key)
    if payload.get("id") != _DIMENSIONS or list(payload.get("size", []))[:-1] != [1, 1, 1, 1]:
        raise ProviderError("Eurostat sentiment response has unexpected dimensions")
    expected = {"freq": "M", "indic": params["indic"], "s_adj": params["s_adj"], "geo": params["geo"]}
    for name, code in expected.items():
        if payload["dimension"][name]["category"]["index"] != {code: 0}:
            raise ProviderError("Eurostat returned a different sentiment series")
    values: dict[date, Decimal] = {}
    for label, index in payload["dimension"]["time"]["category"]["index"].items():
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", label):
            raise ProviderError("Eurostat sentiment period is not monthly")
        day = date(int(label[:4]), int(label[5:]), 1)
        if day > date.today():
            raise ProviderError("Eurostat sentiment period is in the future")
        raw = payload.get("value", {}).get(str(index))
        if raw is None:
            continue
        try:
            value = Decimal(str(raw))
        except InvalidOperation as exc:
            raise ProviderError("Eurostat sentiment value is invalid") from exc
        if not value.is_finite() or not 0 < value < 250:
            raise ProviderError("Eurostat sentiment value is implausible")
        if start is None or day >= start:
            values[day] = value
    if not values and start is None:
        raise ProviderError("Eurostat sentiment series contains no observations")
    return values
