"""Owner inputs: validated, stored locally, an explicit example until the owner saves their own."""
import json
from pathlib import Path
import tempfile
import unittest

from finance_dashboard.owner_inputs import EXAMPLE, OwnerInputError, load_owner_inputs, save_owner_inputs


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


if __name__ == "__main__":
    unittest.main()
