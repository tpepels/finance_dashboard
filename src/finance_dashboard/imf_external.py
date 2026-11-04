"""IMF original BOP current-account flows and IIP net-position stocks (BPM6, annual USD).

BOP_ACCOUNTING_ENTRY separates flow semantics (NETCD_T, net credit less debit
transactions) from stock semantics (NETAL_P, net assets less liabilities
position). Values are IMF-converted USD levels; a WEO percent-of-GDP ratio is a
different source and concept and is never mixed with these.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import xml.etree.ElementTree as ET

from .bis import ProviderError

IMF_SDMX_ROOT = "https://api.imf.org/external/sdmx/2.1/data"
IMF_AGENCY = "IMF.STA"
COUNTRIES = {"us": "USA", "jp": "JPN", "de": "DEU", "cn": "CHN", "pt": "PRT"}
FLOWS = {
    "bop_current_account_usd": ("BOP", "21.0.0", "CAB", "NETCD_T"),
    "iip_net_position_usd": ("IIP", "13.0.0", "NIIP", "NETAL_P"),
}
IMF_SERIES = {
    f"external.{label}.imf_{concept}": (flow, version, iso, indicator, entry)
    for label, iso in COUNTRIES.items()
    for concept, (flow, version, indicator, entry) in FLOWS.items()
}
METHODOLOGY = "BPM6"


def imf_key(flow: str, version: str, country: str, indicator: str) -> str:
    return f"{IMF_AGENCY},{flow},{version}/{country}..{indicator}.USD.A"


def parse_imf_bop_iip(xml_bytes: bytes, series_id: str, start: date | None = None) -> dict[date, Decimal]:
    spec = IMF_SERIES.get(series_id)
    if spec is None:
        raise ProviderError("Unregistered IMF BOP/IIP series")
    flow, version, country, indicator, entry = spec
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ProviderError("IMF SDMX response is not valid XML") from exc
    series = [node for node in root.iter() if node.tag.endswith("}Series") or node.tag == "Series"]
    if len(series) != 1:
        raise ProviderError("IMF response must contain exactly one series")
    attributes = series[0].attrib
    expected = {"COUNTRY": country, "BOP_ACCOUNTING_ENTRY": entry, "INDICATOR": indicator,
                "UNIT": "USD", "FREQUENCY": "A", "METHODOLOGY": METHODOLOGY}
    if any(attributes.get(name) != value for name, value in expected.items()):
        raise ProviderError("IMF country, entry, indicator, unit, frequency or BPM methodology changed")
    values: dict[date, Decimal] = {}
    for node in series[0]:
        if not (node.tag.endswith("}Obs") or node.tag == "Obs"):
            continue
        label, raw = node.attrib.get("TIME_PERIOD", ""), node.attrib.get("OBS_VALUE")
        if len(label) != 4 or not label.isdigit():
            raise ProviderError("IMF annual reference period is invalid")
        day = date(int(label), 1, 1)
        if raw in (None, ""):
            continue
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ProviderError("IMF observation value is invalid") from exc
        if not value.is_finite() or day.year > date.today().year or day in values:
            raise ProviderError("IMF observation is nonfinite, future-dated or duplicated")
        if start is None or day >= start:
            values[day] = value
    if not values:
        raise ProviderError("IMF series has no observations in the requested period")
    return dict(sorted(values.items()))
