"""Phase D0 of the allocation module: contracts, feature flag and reference definitions."""
import copy
from dataclasses import FrozenInstanceError
from datetime import date
import json
import os
import unittest
from unittest import mock

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from finance_dashboard.__main__ import main as cli_main
from finance_dashboard.allocation.contracts import (
    Allocation, FeatureSnapshot, ForecastDistribution, Forecaster, Posterior, Provenance,
    ReferencePortfolio, to_jsonable,
)
from finance_dashboard.allocation.flags import FLAG, allocation_enabled, require_allocation
from finance_dashboard.allocation.references import (
    load_allocation_documents, reference_portfolio, rung_weights, validate_preregistration,
    validate_references,
)

PROV = Provenance(code_commit="abc1234", spec_hash="0" * 64, snapshot_hashes=("s1",))
QUANTILES = ((0.1, -0.2), (0.5, 0.03), (0.9, 0.18))
GROWTH_MIX = {"EQ_US": 0.62, "EQ_EUROPE": 0.15, "EQ_JAPAN": 0.06, "EQ_APAC_XJ": 0.03,
              "EQ_EM": 0.11, "REIT_GLOBAL": 0.03}


def forecast(**overrides):
    values = dict(bucket="EQ_US", as_of=date(2026, 10, 31), model_id="M1", artifact_hash="h",
                  mean=0.03, var=0.025, quantiles=QUANTILES)
    values.update(overrides)
    return ForecastDistribution(**values)


class FlagTests(unittest.TestCase):
    def test_flag_is_off_unless_explicitly_enabled(self):
        self.assertFalse(allocation_enabled({}))
        self.assertFalse(allocation_enabled({FLAG: "0"}))
        self.assertFalse(allocation_enabled({FLAG: "maybe"}))
        for value in ("1", "true", "YES", " on "):
            self.assertTrue(allocation_enabled({FLAG: value}))

    def test_routes_are_hidden_while_flag_is_off(self):
        app = FastAPI()

        @app.get("/api/allocation/probe", dependencies=[Depends(require_allocation)])
        def probe():
            return {"ok": True}

        client = TestClient(app)
        with mock.patch.dict(os.environ, {FLAG: "0"}):
            self.assertEqual(client.get("/api/allocation/probe").status_code, 404)
        with mock.patch.dict(os.environ, {FLAG: "1"}):
            self.assertEqual(client.get("/api/allocation/probe").json(), {"ok": True})


class ContractTests(unittest.TestCase):
    def test_contracts_are_immutable_and_serialisable(self):
        item = forecast(events=(("dd_eq_15", 0.2),), regimes=(("expansion", 0.7), ("slowdown", 0.3)))
        with self.assertRaises(FrozenInstanceError):
            item.mean = 1.0
        encoded = json.loads(json.dumps(to_jsonable(item)))
        self.assertEqual(encoded["as_of"], "2026-10-31")
        self.assertEqual(item.quantile(0.5), 0.03)

    def test_forecast_rejects_invalid_distributions(self):
        with self.assertRaises(ValueError):
            forecast(var=-0.1)
        with self.assertRaises(ValueError):
            forecast(quantiles=((0.1, 0.0), (0.9, 0.1)))                 # median missing
        with self.assertRaises(ValueError):
            forecast(quantiles=((0.1, 0.2), (0.5, 0.1), (0.9, 0.3)))     # crossing quantiles
        with self.assertRaises(ValueError):
            forecast(events=(("dd_eq_15", 1.2),))
        with self.assertRaises(ValueError):
            forecast(regimes=(("expansion", 0.5), ("slowdown", 0.2)))

    def test_feature_snapshot_shape_is_checked(self):
        FeatureSnapshot(as_of=date(2026, 10, 31), tier="E", entities=("US", "DE"), feature_ids=("ecy",),
                        values=((0.02,), (None,)), snapshot_hash="h")
        with self.assertRaises(ValueError):
            FeatureSnapshot(as_of=date(2026, 10, 31), tier="X", entities=("US",), feature_ids=("ecy",),
                            values=((0.02,),), snapshot_hash="h")
        with self.assertRaises(ValueError):
            FeatureSnapshot(as_of=date(2026, 10, 31), tier="E", entities=("US",), feature_ids=("ecy", "cape"),
                            values=((0.02,),), snapshot_hash="h")

    def test_posterior_requires_symmetric_aligned_inputs(self):
        args = dict(as_of=date(2026, 10, 31), buckets=("A", "B"), mu=(0.01, 0.02),
                    sigma=((0.04, 0.01), (0.01, 0.02)), model_weights=(("A", (("M1", 0.6), ("M2", 0.4))),),
                    view_omega=(0.01, None), provenance=PROV)
        Posterior(**args)
        with self.assertRaises(ValueError):
            Posterior(**{**args, "sigma": ((0.04, 0.02), (0.01, 0.02))})
        with self.assertRaises(ValueError):
            Posterior(**{**args, "model_weights": (("A", (("M1", 0.6),)),)})

    def test_allocation_must_state_a_reason_and_valid_ranges(self):
        args = dict(reference_id="R3", as_of=date(2026, 10, 31), weights=(("A", 0.6), ("B", 0.4)),
                    ranges=(("A", 0.55, 0.65),), status="reference", reason="no validated edge", provenance=PROV)
        Allocation(**args)
        with self.assertRaises(ValueError):
            Allocation(**{**args, "reason": ""})
        with self.assertRaises(ValueError):
            Allocation(**{**args, "ranges": (("A", 0.7, 0.6),)})
        with self.assertRaises(ValueError):
            Allocation(**{**args, "weights": (("A", 0.6), ("B", 0.3))})

    def test_forecaster_protocol_is_structural(self):
        class Dummy:
            model_id, family, depends_on = "M0", "econometric", ()

            def fit(self, history, spec):
                return None

            def predict(self, fitted, snapshot):
                return []

        self.assertIsInstance(Dummy(), Forecaster)


class ReferenceDefinitionTests(unittest.TestCase):
    def setUp(self):
        self.refs, self.prereg = load_allocation_documents()

    def test_committed_definitions_are_valid(self):
        self.assertEqual(validate_references(self.refs), [])
        self.assertEqual(validate_preregistration(self.prereg), [])
        self.assertEqual(len(self.refs["buckets"]), 21)
        self.assertEqual([r["growth_share"] for r in self.refs["rungs"]], [0.2, 0.4, 0.6, 0.8, 1.0])

    def test_owner_decisions_are_recorded(self):
        self.assertEqual(self.refs["backtest_defaults"]["costs"], False)
        self.assertEqual(self.refs["backtest_defaults"]["tax"], False)
        self.assertEqual(self.refs["compute"]["location"], "server")

    def test_rungs_combine_growth_and_defensive_mixes(self):
        for rung in self.refs["rungs"]:
            weights = rung_weights(self.refs, rung["id"], GROWTH_MIX)
            self.assertAlmostEqual(sum(weights.values()), 1.0, places=12)
            growth = sum(w for b, w in weights.items() if b in GROWTH_MIX)
            self.assertAlmostEqual(growth, rung["growth_share"], places=12)
            satellites = [b["id"] for b in self.refs["buckets"] if b["group"] == "satellite"]
            self.assertTrue(all(weights[b] == 0.0 for b in satellites))
        r5 = rung_weights(self.refs, "R5", GROWTH_MIX)
        self.assertEqual(r5["GOV_EUR_INT"], 0.0)

    def test_reference_portfolio_contract(self):
        portfolio = reference_portfolio(self.refs, "R3", GROWTH_MIX, risk_aversion=3.0)
        self.assertIsInstance(portfolio, ReferencePortfolio)
        self.assertAlmostEqual(portfolio.weight("EQ_US"), 0.6 * 0.62)
        self.assertEqual(portfolio.te_max, 0.03)

    def test_mixes_outside_their_group_are_rejected(self):
        with self.assertRaises(ValueError):
            rung_weights(self.refs, "R3", {**GROWTH_MIX, "EQ_US": 0.32, "GOLD": 0.30})
        with self.assertRaises(ValueError):
            rung_weights(self.refs, "R3", {"EQ_US": 0.5})
        with self.assertRaises(KeyError):
            rung_weights(self.refs, "R9", GROWTH_MIX)

    def test_invalid_reference_documents_are_reported(self):
        broken = copy.deepcopy(self.refs)
        broken["rungs"][1]["growth_share"] = 0.1
        broken["anchor"]["defensive_mix"]["shares"]["EQ_US"] = 0.1
        broken["constraints"]["long_only"] = False
        broken["buckets"][6]["cap"] = 0.5
        errors = "\n".join(validate_references(broken))
        for fragment in ("strictly increasing", "non-defensive bucket EQ_US", "long_only", "exceeds satellite_cap"):
            self.assertIn(fragment, errors)

    def test_preregistration_draft_and_frozen_rules(self):
        frozen = {**self.prereg, "status": "frozen", "frozen": True, "spec_hash": None}
        self.assertTrue(any("SHA-256" in e for e in validate_preregistration(frozen)))
        draft_with_hash = {**self.prereg, "spec_hash": "a" * 64}
        self.assertTrue(any("draft spec" in e for e in validate_preregistration(draft_with_hash)))
        reused = {**self.prereg, "holdout": {**self.prereg["holdout"], "evaluations_allowed_per_spec": 3}}
        self.assertTrue(validate_preregistration(reused))

    def test_cli_validate_includes_allocation_definitions(self):
        broken = copy.deepcopy(self.refs)
        broken["compute"]["max_concurrent_heavy_jobs"] = 2
        with mock.patch("finance_dashboard.__main__.load_allocation_documents", return_value=(broken, self.prereg)), \
                mock.patch("sys.stderr"):
            self.assertEqual(cli_main(["validate"]), 1)


if __name__ == "__main__":
    unittest.main()
