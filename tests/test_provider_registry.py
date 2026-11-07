"""Provider registration is the only source dispatch and refresh-scope contract."""
from datetime import date
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.catalog import load_documents
from finance_dashboard.bis import FetchedSeries
from finance_dashboard.provider_registry import PROVIDER_CODES, PROVIDER_REGISTRY
from finance_dashboard.providers import ProviderRouter
from finance_dashboard import provider_adapters


class ProviderRegistryTests(unittest.TestCase):
    def test_all_catalog_mapped_providers_have_exactly_one_callable(self):
        mapped = {row["provider"] for row in load_documents()[0]["series"]
                  if row["status"] == "mapped"}
        self.assertFalse(mapped - PROVIDER_CODES)
        self.assertEqual(len(PROVIDER_CODES), 41)
        for code, registration in PROVIDER_REGISTRY.items():
            self.assertTrue(callable(getattr(provider_adapters, registration.handler, None)))
            self.assertIn(registration.acquisition,
                          {"response", "native", "local", "derived", "unsupported"})
            self.assertIn(registration.refresh_scope, {"full", "windowed"})

    def test_declared_request_origin_matches_adapter_and_paces_its_policy(self):
        """Preflight paces the API host, not the descriptive catalogue page."""
        from finance_dashboard.oecd_cli import OECD_CLI_ROOT
        from finance_dashboard.source_policy_registry import PolicyRegistry
        from finance_dashboard.remaining_sources import MSCI_LEVELS_URL
        from finance_dashboard import euklems
        roots = {"OECD_CLI": (OECD_CLI_ROOT, "oecd-sdmx"),
                 "OECD_NFC_ACCOUNTS": (provider_adapters.OECD_TABLE14_ROOT, "oecd-sdmx"),
                 "MSCI_NETR": (MSCI_LEVELS_URL, "msci-restricted-api"),
                 "EUKLEMS": (euklems.EUKLEMS_ROOT, "euklems-dropbox")}
        policies = PolicyRegistry()
        declared = {code for code, entry in PROVIDER_REGISTRY.items() if entry.request_origin}
        self.assertEqual(declared, set(roots))
        series = load_documents()[0]["series"]
        for code, (root, policy_id) in roots.items():
            origin = PROVIDER_REGISTRY[code].request_origin
            self.assertTrue(root.startswith(origin), code)
            self.assertEqual(policies.for_url(origin).id, policy_id)
            # The descriptive pages are on another policy; this is why the
            # origin must be declared.
            self.assertTrue(any(policies.for_url(row["source_url"]).id != policy_id
                                for row in series if row["provider"] == code), code)

    def test_two_step_shiller_fetch_fits_its_publisher_policy(self):
        """Homepage link discovery plus workbook download pass one real gate.

        The ledger only sleeps short pacing waits inside one fetch, so a
        policy spacing longer than that wait can never admit the second step.
        """
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from finance_dashboard.source_policy import managed_client
        from finance_dashboard.source_policy_registry import PolicyRegistry
        from finance_dashboard.source_policy_ledger import SourcePolicyGate

        def respond(request):
            if request.url.host == "shillerdata.com":
                return httpx.Response(200, text=(
                    '<a href="https://img1.wsimg.com/official/ie_data.xls">Download</a>'))
            return httpx.Response(200, content=bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 40)
        now = [1_000_000.0]
        slept = []
        def sleep(seconds):
            slept.append(seconds)
            now[0] += seconds
        rows = [["Date", "CAPE"]] + [[float(f"{year}.{month:02d}"), 20.0]
                                     for year in range(1881, 2026) for month in range(1, 13)]
        with TemporaryDirectory() as tmp:
            gate = SourcePolicyGate(registry=PolicyRegistry(), state_path=Path(tmp) / "rates.sqlite",
                                    clock=lambda: now[0], sleep=sleep)
            with managed_client(policy_gate=gate, transport=httpx.MockTransport(respond)) as client:
                with patch("python_calamine.CalamineWorkbook.from_filelike") as load:
                    load.return_value.get_sheet_by_name.return_value.to_python.return_value = rows
                    fetched = ProviderRouter(client).fetch("valuation.us.cape")
            self.assertTrue(fetched.observations)
            self.assertEqual(gate.report()["requests_recorded"], 2)
        self.assertLessEqual(sum(slept), gate.max_wait_seconds)

    def test_reenabled_sources_use_one_managed_publisher_budget(self):
        """Bounded HTTP requests reach real registered parsers, not stubs."""
        from datetime import datetime, timezone
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from finance_dashboard.source_policy import managed_client
        from finance_dashboard.source_policy_registry import PolicyRegistry
        from finance_dashboard.source_policy_ledger import SourcePolicyGate

        observed_hosts = []
        def respond(request):
            observed_hosts.append(request.url.host)
            if request.url.host == "goldprice.corgano.com":
                return httpx.Response(200, json={
                    "data": {
                        "metal": "gold", "symbol": "XAU",
                        "price_usd": {"per_oz": 3900.25, "per_gram": 125.4,
                                      "per_kg": 125400},
                        "as_of": datetime.now(timezone.utc).isoformat(),
                    },
                    "meta": {"unit": "USD / troy oz",
                              "source": "Swissquote bid/ask midpoint"},
                })
            if request.url.host == "siblisresearch.supabase.co":
                return httpx.Response(200, json={
                    "ticker": "ACWI", "ratio": "cape",
                    "data": [{"trading_day (EOD)": "2025-09-30",
                              "value": 30.75}],
                })
            if request.url.host == "unstats.un.org":
                name = "SL_EMP_GTOTL" if "SL_EMP_GTOTL" in str(request.url) else "SL_EMP_PCAP"
                return httpx.Response(200, json={
                    "series": name, "geoAreaCode": 1,
                    "dimensions": [{"value": "53.9",
                                    "timePeriodStart": "2004",
                                    "Age": "ALLAGE",
                                    "Reporting Type": "G"}],
                })
            self.fail("Unclassified network request")
        with TemporaryDirectory() as tmp:
            gate = SourcePolicyGate(
                registry=PolicyRegistry(), state_path=Path(tmp) / "rates.sqlite",
                max_wait_seconds=0)
            with managed_client(
                    policy_gate=gate,
                    transport=httpx.MockTransport(respond)) as client:
                router = ProviderRouter(client)
                self.assertTrue(router.fetch("gold.usd.spot").observations)
                self.assertTrue(router.fetch("valuation.global.cape").observations)
                self.assertTrue(router.fetch("labour.world.income_share").observations)
                self.assertEqual(client._transport.requests_reserved, 3)
            self.assertEqual(gate.report()["requests_recorded"], 3)
        self.assertEqual(set(observed_hosts), {
            "goldprice.corgano.com", "siblisresearch.supabase.co",
            "unstats.un.org",
        })

    def test_registered_dispatch_executes_only_selected_handler(self):
        series = "bond.us.nominal_10y"
        expected = FetchedSeries(series, "https://fred.stlouisfed.org/series/DGS10",
                                 None, {date(2024, 1, 2): __import__("decimal").Decimal("4.01")})
        with httpx.Client(transport=httpx.MockTransport(
                lambda req: self.fail("Unexpected publisher request"))) as client:
            router = ProviderRouter(client)
            with patch.object(provider_adapters, "fetch_fred", lambda *args: expected):
                self.assertIs(router.fetch(series), expected)

    def test_full_snapshot_and_overlap_are_registered_not_duplicated(self):
        self.assertTrue(PROVIDER_REGISTRY["WID"].requires_full_refresh("x"))
        self.assertTrue(PROVIDER_REGISTRY["FRED"].requires_full_refresh("NFCI"))
        self.assertFalse(PROVIDER_REGISTRY["FRED"].requires_full_refresh("DGS10"))
        self.assertFalse(PROVIDER_REGISTRY["WORLD_BANK"].requires_full_refresh("anything"))
        self.assertEqual(PROVIDER_REGISTRY["OECD_TIVA"].acquisition, "native")
        self.assertEqual(PROVIDER_REGISTRY["FRED"].acquisition, "response")

    def test_unknown_and_unmapped_catalog_entries_cannot_be_dispatched(self):
        with httpx.Client(transport=httpx.MockTransport(
                lambda req: self.fail("Unexpected publisher request"))) as client:
            router = ProviderRouter(client)
            with self.assertRaises(ValueError):
                router.fetch("not_in_catalog")


if __name__ == "__main__":
    unittest.main()
