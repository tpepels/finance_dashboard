"""Acceptance gates Piketty supplemental source roles without blocking core L07."""
from datetime import date, datetime, timezone
import unittest
from finance_dashboard.engine.acceptance import AcceptanceSnapshot
from finance_dashboard.engine.analyses import DEFINITIONS
from finance_dashboard.engine.bundle import build_bundle

class PikettyAcceptanceTests(unittest.TestCase):
    def test_l07_core_remains_when_piketty_original_unaccepted(self):
        definition=DEFINITIONS["L07"]
        optional=set(definition.optional_inputs)
        self.assertGreaterEqual(len(optional),90)
        requirements=[
            {"role":role,"series_ids":[sid],"state":"accepted" if role not in optional
             else "incomplete","limitations":[]}
            for role,sid in definition.inputs.items()]
        points={role:[] for role in definition.inputs}
        points["top1:US"]=[(date(2024,1,1),.2)]
        points["bottom50:US"]=[(date(2024,1,1),.12)]
        points["piketty:US:income:top10"]=[(date(2024,1,1),.49)]
        points["piketty:US:wealth:top1"]=[(date(2024,1,1),.32)]
        points["piketty:US:wealth:top10"]=[(date(2024,1,1),.70)]
        points["piketty:US:wealth:bottom50"]=[(date(2024,1,1),-.01)]
        def run(accepted):
            roles=[{**row,"state":"accepted" if row["role"] in accepted
                    or row["role"] not in optional else "incomplete"}
                   for row in requirements]
            snap=AcceptanceSnapshot(datetime(2026,11,14,tzinfo=timezone.utc),{
              "L07":{"state":"accepted","blocking_roles":[],"limitations":[],
                     "requirements":roles}})
            return build_bundle(definition,points=points,snapshot=snap,
              corpus_analysis={"title":"L07","method_sources":[]},catalog_series={},
              view={},computed_at=datetime(2026,11,14,tzinfo=timezone.utc))
        base=run(set())
        self.assertEqual(base["phase2"]["state"],"accepted")
        self.assertTrue(base["values"]["economies"])
        income=base["values"]["piketty"]["areas"][0]["concentration"]["concepts"]["income"]
        self.assertFalse(income["percentage_shares"]["top10"])
        record=next(x for x in base["inputs"] if x["role"]=="piketty:US:income:top10")
        self.assertEqual(record["observations"],0)
        self.assertIsNone(record["accepted_under"])
        partially=run({"piketty:US:income:top10"})
        inc=partially["values"]["piketty"]["areas"][0]["concentration"]["concepts"]["income"]
        self.assertEqual(inc["percentage_shares"]["top10"],[["2024",49.0]])
        self.assertEqual(partially["values"]["piketty"]["areas"][0]
                         ["concentration"]["concepts"]["wealth"]["observed_matched_years"],0)
        both=run({"piketty:US:income:top10","piketty:US:wealth:top1",
                  "piketty:US:wealth:top10","piketty:US:wealth:bottom50"})
        wealth=both["values"]["piketty"]["areas"][0]["concentration"]["concepts"]["wealth"]
        self.assertEqual(wealth["percentage_shares"]["top10"],[["2024",70.0]])
        self.assertEqual(wealth["percentage_shares"]["bottom50"],[["2024",-1.0]])
        self.assertEqual(both["values"]["piketty"]["areas"][0]["inheritance"]["status"],
                         "awaiting_comparable_originals")

if __name__=="__main__":
    unittest.main()
