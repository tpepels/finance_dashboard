"""Registered WID research codes must be the publisher's actual codes.

Literal rows are copied from the hash-verified WID bulk originals
WID_data_US.csv (SHA-256 5daf54acd9fe5e949c453e2f85ce089c8754b436ba9dff7dd6a7397022cb4cce)
and WID_data_WO.csv (SHA-256 2b3e5d23cd54e9c20a40fff91a06226e896da094416a214ed2ce47b09608e51b)
with their metadata pairs. Neither file contains any "wweal?999i" code: the
wealth-to-income ratios are published as w + nweal/pweal/gweal, and the world
file writes the age/population suffix as i999.
"""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

from finance_dashboard.bis import ProviderError
from finance_dashboard.wid import WID_ALL_SERIES, parse_piketty_original

META_HEADER = ("country;variable;age;pop;countryname;shortname;simpledes;technicaldes;"
               "shorttype;longtype;shortpop;longpop;shortage;longage;unit;source;method;"
               "avg_quality\n")


def _meta(area, variable, shortname, shorttype, unit, source):
    return (f"{area};{variable};999;i;;{shortname};;;{shorttype};;individuals;;"
            f"All Ages;;{unit};{source};;\n")


US_DATA = (
    "country;variable;percentile;year;value;age;pop;data_quality\n"
    "US;mnninc999i;p0p100;2023;24520904508729;999;i;5\n"
    "US;wgweal999i;p0p100;2023;-0.2811;999;i;3\n"
    "US;wnweal999i;p0p100;2022;5.966600000000001;999;i;3\n"
    "US;wnweal999i;p0p100;2023;5.7042;999;i;3\n"
    "US;wpweal999i;p0p100;2023;5.985300000000001;999;i;3\n")
US_METADATA = META_HEADER + "".join((
    _meta("US", "mnninc999i", "National income", "Total", "USD",
          "1800-2025: In-house calculation (see method)"),
    _meta("US", "wgweal999i", "Net public wealth", "% of NNI",
          "% of national income", "1800-1879: [URL][URL_LINK]https://wid.world/document/"),
    _meta("US", "wnweal999i", "Market-value national wealth ", "% of NNI",
          "% of national income", "1800-1879: In-house calculation (see method)"),
    _meta("US", "wpweal999i", "Net private wealth", "% of NNI",
          "% of national income", "1800-1879: [URL][URL_LINK]https://wid.world/document/"),
))
WO_DATA = (
    "country;variable;percentile;year;value;age;pop\n"
    "WO;mnninci999;p0p100;2023;158280668151808;999;i\n"
    "WO;mnweali999;p0p100;2023;977002853040128;999;i\n"
    "WO;wnweali999;p0p100;2023;6.172599792480469;999;i\n")
WO_METADATA = META_HEADER + "".join((
    _meta("WO", "mnninci999", "National income", "Total", "USD", ""),
    _meta("WO", "mnweali999", "Market-value national wealth ", "Total", "USD", ""),
    _meta("WO", "wnweali999", "Market-value national wealth ", "% of NNI",
          "% of national income", ""),
))


class WidPublisherCodeTests(unittest.TestCase):
    def test_wealth_income_ratios_use_published_codes(self):
        for role, stem in (("national", "wnweal"), ("private", "wpweal"),
                           ("public", "wgweal")):
            for label, area in (("us", "US"), ("fr", "FR"), ("pt", "PT"),
                                ("cn", "CN"), ("in", "IN")):
                self.assertEqual(
                    WID_ALL_SERIES[f"piketty.{label}.wealth_to_income.{role}"],
                    (area, stem + "999i", "p0p100"))
            self.assertEqual(
                WID_ALL_SERIES[f"piketty.world.wealth_to_income.{role}"],
                ("WO", stem + "i999", "p0p100"))

    def test_world_totals_use_the_world_file_suffix(self):
        for role, stem in (("net_national_income", "mnninc"),
                           ("net_national_wealth", "mnweal"),
                           ("net_capital_income", "mfkpin"),
                           ("national_housing_assets", "mnwhou"),
                           ("national_business_assets", "mnwbus")):
            self.assertEqual(WID_ALL_SERIES[f"piketty.world.{role}"],
                             ("WO", stem + "i999", "p0p100"))
            self.assertEqual(WID_ALL_SERIES[f"piketty.us.{role}"],
                             ("US", stem + "999i", "p0p100"))

    def test_catalogue_source_keys_match_the_collector_identity(self):
        root = Path(__file__).resolve().parents[1]
        series = json.loads((root / "definitions" / "series.json").read_text("utf-8"))
        registered = {item["id"]: item["source_key"] for item in series["series"]
                      if item["id"] in WID_ALL_SERIES}
        self.assertEqual(set(registered), set(WID_ALL_SERIES))
        for sid, identity in WID_ALL_SERIES.items():
            self.assertEqual(registered[sid], "/".join(identity), sid)

    def test_published_national_ratio_rows_are_read_as_filed(self):
        parsed, invalid = parse_piketty_original(
            US_DATA, US_METADATA, area="US", strict=False, return_invalid=True)
        self.assertEqual(invalid, frozenset())
        self.assertEqual(parsed[("wnweal999i", "p0p100")],
                         {date(2022, 1, 1): Decimal("5.966600000000001"),
                          date(2023, 1, 1): Decimal("5.7042")})
        self.assertEqual(parsed[("wpweal999i", "p0p100")][date(2023, 1, 1)],
                         Decimal("5.985300000000001"))
        self.assertEqual(parsed[("wgweal999i", "p0p100")][date(2023, 1, 1)],
                         Decimal("-0.2811"))
        self.assertEqual(parsed[("mnninc999i", "p0p100")][date(2023, 1, 1)],
                         Decimal("24520904508729"))

    def test_ratio_with_a_monetary_unit_is_still_rejected(self):
        wrong = US_METADATA.replace(
            "Market-value national wealth ;;;% of NNI;;individuals;;All Ages;;"
            "% of national income",
            "Market-value national wealth ;;;% of NNI;;individuals;;All Ages;;USD")
        self.assertNotEqual(wrong, US_METADATA)
        with self.assertRaisesRegex(ProviderError, "unit mismatch"):
            parse_piketty_original(US_DATA, wrong, area="US")

    def test_world_rows_without_a_source_citation_are_invalid_not_absent(self):
        # The world metadata leaves the source citation blank for these
        # aggregates. They are published but fail the citation rule; they
        # must be quarantined as invalid, never reported as unpublished.
        parsed, invalid = parse_piketty_original(
            WO_DATA, WO_METADATA, area="WO", strict=False, return_invalid=True)
        self.assertEqual(invalid, {"mnninci999", "mnweali999", "wnweali999"})
        self.assertEqual(parsed[("wnweali999", "p0p100")], {})
        with self.assertRaisesRegex(ProviderError, "original method mismatch"):
            parse_piketty_original(WO_DATA, WO_METADATA, area="WO")


if __name__ == "__main__":
    unittest.main()
