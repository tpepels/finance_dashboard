"""Owner inputs: validated, stored locally, an explicit example until the owner saves their own."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from finance_dashboard.owner_inputs import EXAMPLE, OwnerInputError, load_owner_inputs, save_owner_inputs, validate


class OwnerInputTests(unittest.TestCase):
    def test_example_until_saved_then_the_owners_own(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "owner-inputs.json"
            loaded = load_owner_inputs(path)
            self.assertTrue(loaded["is_example"])
            self.assertEqual(loaded["allocation"], EXAMPLE["allocation"])
            mine = {**EXAMPLE, "allocation": {"equity": 0.8, "bonds": 0.2, "gold": 0.0}}
            save_owner_inputs(path, mine)
            again = load_owner_inputs(path)
            self.assertFalse(again["is_example"])
            self.assertEqual(again["allocation"]["equity"], 0.8)
            self.assertNotIn("is_example", json.loads(path.read_text()))

    def test_invalid_inputs_are_refused_with_a_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "owner-inputs.json"
            with self.assertRaisesRegex(OwnerInputError, "add up to 100%"):
                save_owner_inputs(path, {**EXAMPLE, "allocation": {"equity": 0.8, "bonds": 0.3, "gold": 0.0}})
            with self.assertRaisesRegex(OwnerInputError, "rebalancing rule"):
                save_owner_inputs(path, {**EXAMPLE, "rebalancing": {"rule": "sometimes", "months": 12, "band_pp": 5}})
            with self.assertRaisesRegex(OwnerInputError, "between 0 and 1"):
                save_owner_inputs(path, {**EXAMPLE, "equity_hedged_share": 1.5})
            with self.assertRaisesRegex(OwnerInputError, "tax"):
                save_owner_inputs(path, {**EXAMPLE, "tax": {"mode": "sometimes", "rate_pct": 10}})
            with self.assertRaisesRegex(OwnerInputError, "tax"):
                save_owner_inputs(path, {**EXAMPLE, "tax": {"mode": "realised_gains", "rate_pct": 120}})
            self.assertFalse(path.exists())

    def test_tax_defaults_to_none(self):
        self.assertEqual(EXAMPLE["tax"], {"mode": "none", "rate_pct": 0.0})

    def test_nonfinite_numbers_are_refused_in_every_numeric_field(self):
        fields = [
            ("allocation", "equity"), ("equity_hedged_share",), ("equity_euro_share",),
            ("bond_duration_years",), ("trading_cost_bps",), ("start_value_eur",),
            ("monthly_contribution_eur",), ("annual_withdrawal_pct",),
            ("rebalancing", "months"), ("rebalancing", "band_pp"), ("tax", "rate_pct"),
        ]
        for field in fields:
            for bad in (float("nan"), float("inf"), float("-inf"), "NaN", "Infinity"):
                with self.subTest(field=field, value=bad):
                    raw = copy.deepcopy(EXAMPLE)
                    target = raw[field[0]] if len(field) == 2 else raw
                    target[field[-1]] = bad
                    with self.assertRaises(OwnerInputError):
                        validate(raw)

    def test_malformed_objects_and_numeric_fields_have_owner_input_errors(self):
        for raw in (None, [], "portfolio", 5, True):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(OwnerInputError, "object"):
                    validate(raw)
        for field in ("allocation", "rebalancing", "tax"):
            for bad in (None, [], "default", 1, True):
                with self.subTest(field=field, value=bad):
                    with self.assertRaisesRegex(OwnerInputError, field):
                        validate({**EXAMPLE, field: bad})
        for field in ("bond_duration_years", "trading_cost_bps", "start_value_eur", "monthly_contribution_eur"):
            for bad in (None, {}, [], "", "many", True, 10 ** 1000):
                with self.subTest(field=field, value=bad):
                    with self.assertRaises(OwnerInputError):
                        validate({**EXAMPLE, field: bad})

    def test_boolean_and_integer_fields_do_not_silently_coerce(self):
        for bad in ("false", "true", "", 0, 1, None, [], {}):
            with self.subTest(bonds_hedged=bad):
                with self.assertRaisesRegex(OwnerInputError, "bonds_hedged"):
                    validate({**EXAMPLE, "bonds_hedged": bad})
        for bad in (1.5, "12.5", True):
            with self.subTest(months=bad):
                with self.assertRaisesRegex(OwnerInputError, "months"):
                    validate({**EXAMPLE, "rebalancing": {"rule": "calendar", "months": bad, "band_pp": 5}})
        for field in ("equity_hedged_share", "equity_euro_share", "annual_withdrawal_pct"):
            with self.subTest(field=field):
                with self.assertRaises(OwnerInputError):
                    validate({**EXAMPLE, field: False})

    def test_invalid_save_preserves_the_previous_owner_file_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "owner-inputs.json"
            save_owner_inputs(path, {**EXAMPLE, "start_value_eur": 12345.0})
            before = path.read_bytes()
            for bad in ({**EXAMPLE, "start_value_eur": float("nan")},
                        {**EXAMPLE, "tax": []}, {**EXAMPLE, "bonds_hedged": "false"}):
                with self.subTest(raw=bad):
                    with self.assertRaises(OwnerInputError):
                        save_owner_inputs(path, bad)
                    self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_malformed_saved_input_falls_back_to_an_explicit_example(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "owner-inputs.json"
            for bad in ([], {"allocation": []}, {**EXAMPLE, "start_value_eur": float("inf")}):
                with self.subTest(raw=bad):
                    path.write_text(json.dumps(bad))
                    before = path.read_bytes()
                    self.assertTrue(load_owner_inputs(path)["is_example"])
                    self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
