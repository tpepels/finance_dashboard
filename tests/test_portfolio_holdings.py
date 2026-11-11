"""Owner holdings persist independently and calculate only supplied valuations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from finance_dashboard import portfolio_holdings as holdings


def position(identifier="one", account="Example account", **changes):
    return {"id": identifier, "account": account, "name": "Example broad fund",
            "isin": "AA0000000006", "ticker": None, "quantity": 2,
            "price_eur": 50, "value_eur": 100, "asset_class": "equity",
            "identity_source": "owner", "source_url": None, **changes}


def document(**changes):
    return {"version": 1, "revision": 0, "as_of": "2020-01-01", "combine_accounts": True,
            "scope": "listed_positions", "monthly_contribution_eur": 20,
            "annual_withdrawal_eur": 0, "positions": [position()], **changes}


def save_in_process(path, barrier, results, number):
    try:
        barrier.wait(timeout=10)
        holdings.save_portfolio_holdings(document(positions=[position(name=f"Example {number}")]), Path(path))
        results.put("saved")
    except holdings.PortfolioHoldingsConflict:
        results.put("conflict")
    except Exception as exc:
        results.put(type(exc).__name__)


class PortfolioHoldingsTests(unittest.TestCase):
    def test_warnings_locate_same_named_instruments_in_the_affected_account(self):
        rows = [position('opaque-a', 'Account A', name='Same fund'),
                position('opaque-b', 'Account B', name='Same fund', isin=None,
                         asset_class='unclassified', value_eur=300)]
        saved = holdings.save_portfolio_holdings(document(positions=rows), self.path)
        warnings = saved['summary']['warnings']
        for detail in ('ISIN', 'classification', 'quantity'):
            affected = [warning for warning in warnings if detail in warning]
            self.assertTrue(affected)
            self.assertTrue(all('Account B' in warning and 'Same fund' in warning for warning in affected))

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "holdings.json"

    def test_missing_store_has_explicit_unknown_inputs_without_writing_a_file(self):
        from finance_dashboard.portfolio_holdings import load_portfolio_holdings
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "holdings.json"
            document = load_portfolio_holdings(path)
            self.assertEqual(document["version"], 1)
            self.assertEqual(document["revision"], 0)
            self.assertEqual(document["positions"], [])
            self.assertIsNone(document["as_of"])
            self.assertIsNone(document["monthly_contribution_eur"])
            self.assertIsNone(document["annual_withdrawal_eur"])
            self.assertFalse(document["combine_accounts"])
            self.assertEqual(document["scope"], "listed_positions")
            self.assertIsNone(document["summary"]["total_value_eur"])
            self.assertEqual(document["summary"]["position_count"], 0)
            self.assertTrue(any("date" in warning.lower() for warning in document["summary"]["warnings"]))
            self.assertFalse(path.exists())

    def test_supplied_cent_values_group_only_matching_isins_and_keep_metals_distinct(self):
        rows = [position("first", "Account A", value_eur=100.10),
                position("second", "Account B", quantity=4, value_eur=199.90),
                position("metals", "Account A", isin="BB0000000004", name="Example metals",
                         asset_class="precious_metals", quantity=3, price_eur=25, value_eur=75),
                position("unknown-a", "Account A", isin=None, name="Same example name", quantity=1,
                         price_eur=None, value_eur=25, asset_class="unclassified", identity_source="unresolved"),
                position("unknown-b", "Account B", isin=None, name="Same example name", quantity=1,
                         price_eur=None, value_eur=100, asset_class="unclassified", identity_source="unresolved")]
        saved = holdings.save_portfolio_holdings(document(positions=rows), self.path)
        summary = saved["summary"]
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(summary["total_value_eur"], 500)
        self.assertEqual(summary["position_count"], 5)
        self.assertEqual(summary["accounts"], [{"account": "Account A", "value_eur": 200.10, "positions": 3},
                                               {"account": "Account B", "value_eur": 299.90, "positions": 2}])
        self.assertEqual(len(summary["funds"]), 4)
        fund = next(row for row in summary["funds"] if row["isin"] == "AA0000000006")
        self.assertEqual(fund["key"], "isin:AA0000000006")
        self.assertEqual(fund["value_eur"], 300)
        self.assertEqual(fund["quantity"], 6)
        self.assertEqual(fund["weight"], .6)
        self.assertEqual(fund["accounts"], ["Account A", "Account B"])
        self.assertEqual({row["asset_class"]: row["value_eur"] for row in summary["asset_classes"]},
                         {"equity": 300, "precious_metals": 75, "unclassified": 125})
        self.assertAlmostEqual(summary["positions"][0]["portfolio_weight"], .2002)
        self.assertAlmostEqual(summary["positions"][0]["account_weight"], 100.10 / 200.10)
        self.assertTrue(any("quantity" in warning.lower() for warning in summary["warnings"]))
        self.assertEqual(holdings.load_portfolio_holdings(self.path), saved)
        saved["positions"][0]["name"] = "Changed returned object"
        self.assertEqual(holdings.load_portfolio_holdings(self.path)["positions"][0]["name"], "Example broad fund")

    def test_multiple_accounts_require_explicit_combination_and_single_account_can_be_filtered(self):
        rows = [position("first", "Account A", value_eur=100),
                position("second", "Account B", value_eur=300, quantity=6)]
        saved = holdings.save_portfolio_holdings(document(combine_accounts=False, positions=rows), self.path)
        self.assertIsNone(saved["summary"]["total_value_eur"])
        self.assertTrue(all(row["portfolio_weight"] is None for row in saved["summary"]["positions"]))
        self.assertTrue(all(row["weight"] is None for row in saved["summary"]["funds"]))
        self.assertTrue(all(row["weight"] is None for row in saved["summary"]["asset_classes"]))
        self.assertEqual([row["account_weight"] for row in saved["summary"]["positions"]], [1, 1])
        selected = document(revision=1, combine_accounts=False, positions=[rows[1]])
        filtered = holdings.save_portfolio_holdings(selected, self.path)
        self.assertEqual(filtered["summary"]["total_value_eur"], 300)
        self.assertEqual(filtered["summary"]["funds"][0]["weight"], 1)

    def test_duplicate_identity_with_conflicting_classification_is_flagged_and_unclassified(self):
        saved = holdings.save_portfolio_holdings(document(positions=[position("first"),
            position("second", asset_class="bonds")]), self.path)
        self.assertEqual(saved["summary"]["funds"][0]["asset_class"], "unclassified")
        self.assertEqual(saved["summary"]["asset_classes"], [{"asset_class": "unclassified", "value_eur": 200, "weight": 1}])
        self.assertTrue(any("conflict" in warning.lower() for warning in saved["summary"]["warnings"]))

    def test_unknown_date_flows_and_identity_remain_unknown_and_never_inferred_from_ticker(self):
        saved = holdings.save_portfolio_holdings(document(as_of=None, monthly_contribution_eur=None,
            annual_withdrawal_eur=None, positions=[position(isin=None, ticker="GOLD-EUR",
            asset_class="unclassified", identity_source="unresolved", price_eur=None)]), self.path)
        self.assertIsNone(saved["as_of"])
        self.assertIsNone(saved["monthly_contribution_eur"])
        self.assertIsNone(saved["annual_withdrawal_eur"])
        self.assertEqual(saved["summary"]["funds"][0]["asset_class"], "unclassified")
        self.assertIsNone(saved["positions"][0]["isin"])
        self.assertGreaterEqual(len(saved["summary"]["warnings"]), 4)

    def test_decimal_cent_rounding_is_applied_before_aggregation_and_price_is_only_a_check(self):
        saved = holdings.save_portfolio_holdings(document(positions=[position("first", value_eur=.105,
            quantity=1, price_eur=.11), position("second", isin=None, value_eur=.205, quantity=1,
            price_eur=.21)]), self.path)
        self.assertEqual(saved["summary"]["total_value_eur"], .32)
        self.assertEqual([row["value_eur"] for row in saved["positions"]], [.11, .21])
        self.assertFalse(any("quantity" in warning.lower() for warning in saved["summary"]["warnings"]))

    def test_environment_store_is_separate_and_get_roundtrip_ignores_derived_summary(self):
        owner = self.path.parent / "owner-inputs.json"
        owner.write_text('{"example": "preserve"}')
        with patch.dict(os.environ, {"FINANCE_PORTFOLIO_HOLDINGS": str(self.path)}):
            saved = holdings.save_portfolio_holdings(document())
            saved["summary"]["total_value_eur"] = 999999
            saved = holdings.save_portfolio_holdings(saved)
            self.assertEqual(saved["revision"], 2)
            self.assertEqual(holdings.load_portfolio_holdings()["summary"]["total_value_eur"], 100)
        self.assertEqual(owner.read_text(), '{"example": "preserve"}')
        self.assertNotIn("summary", json.loads(self.path.read_text()))

    def test_stale_and_invalid_revision_never_replace_a_saved_document(self):
        holdings.save_portfolio_holdings(document(), self.path)
        before = self.path.read_bytes()
        with self.assertRaises(holdings.PortfolioHoldingsConflict):
            holdings.save_portfolio_holdings(document(), self.path)
        for revision in (None, True, -1, 1.0, "1"):
            with self.subTest(revision=revision), self.assertRaises(holdings.PortfolioHoldingsError):
                holdings.save_portfolio_holdings(document(revision=revision), self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_numbers_dates_enums_identity_and_urls_preserve_valid_state(self):
        holdings.save_portfolio_holdings(document(), self.path)
        before = self.path.read_bytes()
        bad_documents = [document(revision=1, combine_accounts=value) for value in (1, "true", None)]
        bad_documents += [document(revision=1, as_of=value) for value in
                          ("2020-02-30", "2020-1-1", True, (date.today() + timedelta(days=2)).isoformat())]
        bad_documents += [document(revision=1, scope="everything"), document(revision=1, version=True),
                          document(revision=1, version=2), document(revision=1, unexpected="secret")]
        bad_documents += [document(revision=1, monthly_contribution_eur=value) for value in
                          (-1, True, "5", float("nan"), float("inf"))]
        bad_rows = [{"quantity": value} for value in (0, -1, True, "5", float("nan"), float("inf"))]
        bad_rows += [{"value_eur": value} for value in (-1, True, "5", float("nan"), float("inf"))]
        bad_rows += [{"price_eur": value} for value in (-1, True, "5", float("nan"), float("inf"))]
        bad_rows += [{"isin": value} for value in ("AA0000000007", "not-an-isin", True, "aa0000000006")]
        bad_rows += [{"source_url": value} for value in ("http://example.test/reference", "https://user:secret@example.test/",
                      "https://example.test:invalid/", "https:///no-host", "javascript:secret", "https://example.test/\nsecret")]
        bad_rows += [{"asset_class": "inferred_gold"}, {"identity_source": "verified"}, {"account": ""},
                     {"name": "x" * 301}, {"id": ""}, {"unexpected": "secret"}]
        bad_documents += [document(revision=1, positions=[position(**changes)]) for changes in bad_rows]
        bad_documents += [document(revision=1, positions=[position("duplicate"), position("duplicate")]),
                          document(revision=1, positions=[position(value_eur=0)]),
                          document(revision=1, positions=[position(str(index)) for index in range(501)])]
        for invalid in bad_documents:
            with self.subTest(invalid=invalid), self.assertRaises(holdings.PortfolioHoldingsError):
                holdings.save_portfolio_holdings(invalid, self.path)
            self.assertEqual(self.path.read_bytes(), before)

    def test_zero_value_row_is_allowed_when_the_document_total_is_positive(self):
        saved = holdings.save_portfolio_holdings(document(positions=[position("zero", value_eur=0),
            position("positive", isin=None)]), self.path)
        self.assertEqual(saved["summary"]["positions"][0]["portfolio_weight"], 0)
        self.assertEqual(saved["summary"]["total_value_eur"], 100)

    def test_optional_metadata_defaults_to_unknown_and_https_is_only_a_reference(self):
        minimal = {"id": "row", "account": " Sample account ", "name": " Sample position ",
                   "quantity": .25, "value_eur": 12.25, "source_url": "https://example.test/reference.pdf"}
        saved = holdings.save_portfolio_holdings({"revision": 0, "positions": [minimal]}, self.path)
        row = saved["positions"][0]
        self.assertEqual(row["account"], "Sample account")
        self.assertEqual(row["name"], "Sample position")
        self.assertEqual(row["identity_source"], "unresolved")
        self.assertEqual(row["asset_class"], "unclassified")
        self.assertIsNone(row["isin"])
        self.assertIsNone(row["ticker"])
        self.assertIsNone(row["price_eur"])
        self.assertEqual(row["source_url"], "https://example.test/reference.pdf")
        self.assertEqual(saved["summary"]["funds"][0]["key"], "position:row")

    def test_exact_position_limit_and_empty_replacement_are_allowed(self):
        rows = [position(str(index), isin=None, quantity=.01, price_eur=None, value_eur=.01)
                for index in range(500)]
        saved = holdings.save_portfolio_holdings(document(positions=rows), self.path)
        self.assertEqual(saved["summary"]["total_value_eur"], 5)
        self.assertEqual(saved["summary"]["position_count"], 500)
        cleared = holdings.save_portfolio_holdings(document(revision=1, positions=[]), self.path)
        self.assertEqual(cleared["positions"], [])
        self.assertIsNone(cleared["summary"]["total_value_eur"])

    def test_unusable_storage_path_returns_sanitized_error(self):
        parent = self.path.parent / "not-a-directory"
        parent.write_text("private data")
        with self.assertRaises(holdings.PortfolioHoldingsUnavailable) as caught:
            holdings.save_portfolio_holdings(document(), parent / "holdings.json")
        self.assertNotIn(str(parent), str(caught.exception))
        self.assertNotIn("private data", str(caught.exception))
        self.assertEqual(parent.read_text(), "private data")

    def test_corrupt_unsupported_or_noncanonical_stored_documents_are_never_overwritten(self):
        saved = holdings.save_portfolio_holdings(document(), self.path)
        valid = json.loads(self.path.read_text())
        invalid_documents = ["{private source body", "[]", '{"version":1,"version":1}',
                            json.dumps({**valid, "version":2}), json.dumps({**valid, "revision":True}),
                            json.dumps({**valid, "positions":[position(value_eur=float("nan"))]}),
                            json.dumps({**valid, "positions":[position(name="  Name  ")]}),
                            json.dumps({**valid, "summary":{}})]
        for invalid in invalid_documents:
            with self.subTest(invalid=invalid):
                self.path.write_text(invalid)
                before = self.path.read_bytes()
                for action in (lambda: holdings.load_portfolio_holdings(self.path),
                               lambda: holdings.save_portfolio_holdings(document(revision=saved["revision"]), self.path)):
                    with self.assertRaises(holdings.PortfolioHoldingsUnavailable) as caught:
                        action()
                    self.assertNotIn("private source body", str(caught.exception))
                    self.assertNotIn(str(self.path), str(caught.exception))
                    self.assertEqual(self.path.read_bytes(), before)

    def test_replace_failure_preserves_old_file_and_cleans_up_temporary_file(self):
        holdings.save_portfolio_holdings(document(), self.path)
        before = self.path.read_bytes()
        with patch("finance_dashboard.portfolio_holdings.os.replace", side_effect=PermissionError("private details")):
            with self.assertRaises(holdings.PortfolioHoldingsUnavailable) as caught:
                holdings.save_portfolio_holdings(document(revision=1), self.path)
        self.assertNotIn("private details", str(caught.exception))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_concurrent_threads_have_exactly_one_revision_winner(self):
        barrier = threading.Barrier(2)
        def save(number):
            barrier.wait(timeout=5)
            try:
                return holdings.save_portfolio_holdings(document(positions=[position(name=f"Example {number}")]), self.path)
            except holdings.PortfolioHoldingsConflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(save, (1, 2)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(holdings.load_portfolio_holdings(self.path)["revision"], 1)

    def test_concurrent_processes_have_exactly_one_revision_winner(self):
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        results = context.Queue()
        processes = [context.Process(target=save_in_process, args=(str(self.path), barrier, results, number))
                     for number in (1, 2)]
        try:
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=15)
                self.assertFalse(process.is_alive())
                self.assertEqual(process.exitcode, 0)
            self.assertCountEqual([results.get(timeout=2) for _ in processes], ["saved", "conflict"])
            self.assertEqual(holdings.load_portfolio_holdings(self.path)["revision"], 1)
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
            results.close()
            results.join_thread()


if __name__ == "__main__":
    unittest.main()
