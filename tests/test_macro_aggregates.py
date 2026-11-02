"""Short network-free tests for all new macro aggregates and provider routes."""
from datetime import date
from decimal import Decimal
import unittest

import httpx

from finance_dashboard.macro_aggregates import (
    AggregateSourceError, aggregate_earnings_yield,
    parse_siblis_world_pe, world_listed_market_cap_gdp,
)
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.catalog import load_documents, validate


def published_html() -> str:
    years = "".join(
        f"<tr><td>{year} Dec</td><td>20.00</td><td>21.0</td></tr>"
        for year in range(2025, 2015, -1)
    )
    return (
        "<html><h1>Global stock market valuations</h1>"
        "<h2>Historical trailing P/E</h2>"
        "<table><tr><th>Index</th><th>Trailing P/E</th></tr>"
        "<tr><td>Global</td><td>21.60</td></tr></table>"
        "<table><tr><th>Month</th><th>Global</th>"
        "<th>Developed markets</th></tr>"
        "<tr><td>Sept 2026</td><td>21.60</td><td>22.96</td></tr>"
        + years + "</table></html>"
    )


class MacroAggregateParserTests(unittest.TestCase):
    def test_source_identification_and_all_published_year_ends(self):
        obs = parse_siblis_world_pe(published_html())
        self.assertEqual(len(obs), 11)
        self.assertEqual(obs[date(2026, 9, 1)], Decimal("21.60"))
        for year in range(2016, 2026):
            self.assertEqual(obs[date(year, 12, 1)], Decimal("20.00"))
        self.assertNotIn(date(2026, 8, 1), obs)

    def test_start_filter_preserves_annual_validation(self):
        obs = parse_siblis_world_pe(published_html(), start=date(2024, 1, 1))
        self.assertEqual(len(obs), 3)

    def test_rejects_wrong_page_invalid_value_and_missing_history(self):
        for html in (
            "<html></html>",
            published_html().replace("Historical trailing P/E", "Random"),
            published_html().replace("21.60</td><td>22.96", "Infinity</td><td>22.96"),
            published_html().replace("2025 Dec", "2026 Dec"),
            published_html().replace("2016 Dec", "April 2016").replace("2017 Dec", "April 2017"),
        ):
            with self.assertRaises(AggregateSourceError):
                parse_siblis_world_pe(html)

    def test_index_earnings_yield_not_gdp_profit_share(self):
        obs = aggregate_earnings_yield({date(2026, 9, 1): Decimal("20")})
        self.assertEqual(obs, {date(2026, 9, 1): Decimal("5")})
        with self.assertRaises(AggregateSourceError):
            aggregate_earnings_yield({date(2020, 12, 1): Decimal("0")})

    def test_world_gdp_ratio_intersection_and_no_fabricated_years(self):
        cap = {date(2024, 1, 1): Decimal("150"), date(2025, 1, 1): Decimal("175")}
        gdp = {date(2024, 1, 1): Decimal("100"), date(2026, 1, 1): Decimal("150")}
        self.assertEqual(world_listed_market_cap_gdp(cap, gdp),
                         {date(2024, 1, 1): Decimal("150")})
        with self.assertRaises(AggregateSourceError):
            world_listed_market_cap_gdp(cap, {date(2025,1,1): Decimal("-1")})
        with self.assertRaises(AggregateSourceError):
            world_listed_market_cap_gdp(cap, {})


class MacroAggregateProviderTests(unittest.TestCase):
    def test_complete_registry_and_derived_world_cap(self):
        catalog, charts = load_documents()
        self.assertEqual([], validate(catalog, charts))
        identifiers = {s["id"] for s in catalog["series"]}
        self.assertTrue({"valuation.world.listed_market_cap_usd",
                         "valuation.world.listed_market_cap_world_gdp",
                         "valuation.world.global_trailing_pe",
                         "valuation.world.global_earnings_yield"}.issubset(identifiers))
        seen = []
        def handler(request):
            seen.append(str(request.url))
            if "CM.MKT.LCAP.CD" in str(request.url):
                series, val = "CM.MKT.LCAP.CD", "150000000000000"
            else:
                series, val = "NY.GDP.MKTP.CD", "120000000000000"
            return httpx.Response(200, json=[
                {"page": 1, "pages": 1},
                [{"date":"2025","value":val,"countryiso3code":"WLD",
                  "indicator":{"id":series}}],
            ])
        router = ProviderRouter(httpx.Client(transport=httpx.MockTransport(handler)))
        try:
            answer = router.fetch("valuation.world.listed_market_cap_world_gdp")
            self.assertEqual(answer.observations, {date(2025,1,1):Decimal("125")})
            self.assertEqual(len(seen), 2)
            cap = router.fetch("valuation.world.listed_market_cap_usd")
            self.assertEqual(cap.observations[date(2025,1,1)],Decimal("150000000000000"))
        finally:
            router.close()

    def test_siblis_world_pe_and_yield_router(self):
        seen = []
        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(200, text=published_html())
        router = ProviderRouter(httpx.Client(transport=httpx.MockTransport(handler)))
        try:
            pe = router.fetch("valuation.world.global_trailing_pe")
            y = router.fetch("valuation.world.global_earnings_yield")
            self.assertEqual(len(pe.observations), 11)
            self.assertEqual(y.observations[date(2025, 12, 1)], Decimal("5"))
            self.assertEqual(len(seen), 2)
            self.assertTrue(all("global-markets-pe" in link for link in seen))
        finally:
            router.close()

    def test_invalid_worldbank_indicator_identity_does_not_return_value(self):
        def handler(request):
            return httpx.Response(200, json=[{"pages": 1}, [{
                "date": "2025", "countryiso3code": "WLD",
                "indicator": {"id": "NY.GDP.MKTP.CD"}, "value": "1"
            }]])
        router = ProviderRouter(httpx.Client(transport=httpx.MockTransport(handler)))
        try:
            with self.assertRaisesRegex(ValueError, "indicator mismatch"):
                router.fetch("valuation.world.listed_market_cap_world_gdp")
        finally:
            router.close()


if __name__ == "__main__":
    unittest.main()
