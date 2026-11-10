"""Owner-supplied Phase 2 roles: accepted only when the supplying store actually holds valid values."""
import unittest

from finance_dashboard.owner_inputs import EXAMPLE
from finance_dashboard.owner_supply import supplied_roles


EVENTS = [{"id": "covid", "date": "2020-03-11", "geography": "GLOBAL", "category": "pandemic_shock",
           "label": "WHO pandemic", "source_url": "https://www.who.int/x"}]


class OwnerSupplyTests(unittest.TestCase):
    def test_saved_owner_inputs_supply_their_roles_and_the_example_supplies_none(self):
        saved = supplied_roles({**EXAMPLE, "is_example": False}, EVENTS)
        self.assertIn(("P05", "target_weights"), saved)
        self.assertIn(("P05", "tax_policy"), saved)
        self.assertIn(("P04", "modified_duration"), saved)
        self.assertNotIn(("P05", "benchmark_weights"), saved)      # nothing supplies it
        self.assertNotIn(("P04", "convexity"), saved)
        self.assertEqual(saved[("P05", "target_weights")]["limitation"]["code"], "owner_supplied_values_not_verified")
        example = supplied_roles({**EXAMPLE, "is_example": True}, EVENTS)
        self.assertFalse(any(key[0] in ("P04", "P05") for key in example))

    def test_the_shock_register_supplies_the_event_roles_only_when_every_event_is_sourced(self):
        roles = supplied_roles({**EXAMPLE, "is_example": True}, EVENTS)
        self.assertEqual(set(roles), {("C05", "independent_shock_events"), ("P03", "market_shock_dates")})
        self.assertEqual(roles[("C05", "independent_shock_events")]["limitation"]["code"], "curated_shock_register")
        unsourced = [{**EVENTS[0], "source_url": ""}]
        self.assertEqual(supplied_roles({**EXAMPLE, "is_example": True}, unsourced), {})


if __name__ == "__main__":
    unittest.main()


class AcceptanceTests(unittest.TestCase):
    def test_a_supplied_owner_role_is_accepted_with_its_limitation_and_others_stay_open(self):
        from finance_dashboard.research_acceptance import analysis_acceptance
        from finance_dashboard.research_corpus import load_research_corpus
        p05 = next(a for a in load_research_corpus()["analyses"] if a["id"] == "P05")
        supply = supplied_roles({**EXAMPLE, "is_example": False}, [])
        result = analysis_acceptance(p05, {}, {}, [], observations_checked=False, owner_supply=supply)
        roles = {r["role"]: r for r in result["requirements"]}
        self.assertTrue(roles["target_weights"]["accepted"])
        self.assertEqual(roles["target_weights"]["checks"][0]["code"], "owner_inputs_supplied")
        self.assertEqual(roles["target_weights"]["limitations"][0]["code"], "owner_supplied_values_not_verified")
        self.assertFalse(roles["benchmark_weights"]["accepted"])
        self.assertIn("benchmark_weights", result["blocking_roles"])
        self.assertNotIn("target_weights", result["blocking_roles"])
