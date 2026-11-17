"""Only fields the owner actually saved count as owner-supplied.

validate() completes missing fields from the example so the engine can run;
before this fix a partial save silently turned example values (for instance a
10% euro-area equity share) into accepted owner inputs.
"""
import json
from pathlib import Path
import tempfile
import unittest

from finance_dashboard.owner_inputs import EXAMPLE, load_owner_inputs, save_owner_inputs
from finance_dashboard.owner_supply import supplied_roles

PARTIAL = {"allocation": {"equity": 0.983, "bonds": 0.0, "gold": 0.017},
           "start_value_eur": 1000.0, "rebalancing": {"rule": "calendar", "months": 12, "band_pp": 5},
           "trading_cost_bps": 0, "tax": {"mode": "none", "rate_pct": 0},
           "monthly_contribution_eur": 0, "annual_withdrawal_pct": 0,
           "bond_duration_years": 0, "equity_hedged_share": 0}


class PartialOwnerInputTests(unittest.TestCase):
    def _saved(self, raw):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "owner-inputs.json"
        save_owner_inputs(path, raw)
        return path, load_owner_inputs(path)

    def test_saved_and_example_fields_are_recorded(self):
        path, loaded = self._saved(PARTIAL)
        self.assertEqual(set(loaded["example_fields"]), {"equity_euro_share", "bonds_hedged"})
        self.assertNotIn("equity_euro_share", loaded["supplied_fields"])
        self.assertEqual(json.loads(path.read_text())["supplied_fields"], sorted(PARTIAL))

    def test_roles_need_every_field_to_be_saved_by_the_owner(self):
        _, loaded = self._saved(PARTIAL)
        roles = supplied_roles(loaded, [])
        for key in (("P05", "target_weights"), ("P05", "actual_weights"), ("P05", "rebalance_policy"),
                    ("P05", "trading_costs"), ("P05", "tax_policy"), ("P05", "withdrawal_plan"),
                    ("P04", "modified_duration")):
            self.assertIn(key, roles)
        self.assertNotIn(("P04", "currency_portfolio_weights"), roles)

    def test_a_complete_save_supplies_every_owner_role(self):
        _, loaded = self._saved(EXAMPLE)
        self.assertEqual(loaded["example_fields"], [])
        self.assertIn(("P04", "currency_portfolio_weights"), supplied_roles(loaded, []))

    def test_a_file_saved_before_this_change_counts_every_field(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "owner-inputs.json"
        path.write_text(json.dumps(EXAMPLE))
        loaded = load_owner_inputs(path)
        self.assertFalse(loaded["is_example"])
        self.assertEqual(loaded["example_fields"], [])

    def test_p04_is_labelled_example_while_a_p04_field_is_an_example(self):
        from finance_dashboard.engine.analyses import _p04, _p05
        _, loaded = self._saved(PARTIAL)
        self.assertTrue(_p04({}, {}, {"owner_inputs": loaded}).values["is_example"])
        self.assertFalse(_p05_values(loaded)["is_example"])


def _p05_values(owner):
    from finance_dashboard.engine.analyses import p05_example_flag
    return {"is_example": p05_example_flag(owner)}


if __name__ == "__main__":
    unittest.main()
