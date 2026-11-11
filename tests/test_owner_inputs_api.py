"""Owner-input API: read the current inputs, save valid ones, refuse invalid ones with a reason."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from engine_fixtures import memory_engine
from finance_dashboard.api import create_app
from finance_dashboard.owner_inputs import EXAMPLE


class OwnerInputApiTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"FINANCE_AUTO_REFRESH": "0", "FINANCE_INCLUDE_MARKETS": "0", "FINANCE_AUTO_BACKUP": "0",
                                           "FINANCE_OWNER_INPUTS": os.path.join(self.folder.name, "owner-inputs.json")})
        self.env.start()
        self.client = TestClient(create_app(memory_engine()))

    def tearDown(self):
        self.env.stop()
        self.folder.cleanup()

    def test_example_then_saved_then_refused(self):
        first = self.client.get("/api/owner-inputs").json()
        self.assertTrue(first["is_example"])
        saved = self.client.put("/api/owner-inputs", json={**EXAMPLE, "allocation": {"equity": 0.8, "bonds": 0.2, "gold": 0.0}})
        self.assertEqual(saved.status_code, 200)
        self.assertFalse(self.client.get("/api/owner-inputs").json()["is_example"])
        refused = self.client.put("/api/owner-inputs", json={**EXAMPLE, "allocation": {"equity": 0.9, "bonds": 0.2, "gold": 0.0}})
        self.assertEqual(refused.status_code, 422)
        self.assertIn("add up to 100%", refused.json()["detail"])

    def test_an_unwritable_store_says_where_it_failed(self):
        with patch("finance_dashboard.api.save_owner_inputs", side_effect=PermissionError("denied")):
            response = self.client.put("/api/owner-inputs", json=EXAMPLE)
        self.assertEqual(response.status_code, 500)
        self.assertIn("could not be stored", response.json()["detail"])

    def test_malformed_input_returns_422_and_preserves_saved_owner_data(self):
        self.assertEqual(self.client.put("/api/owner-inputs", json=EXAMPLE).status_code, 200)
        path = Path(self.folder.name) / "owner-inputs.json"
        before = path.read_bytes()
        for bad in ({**EXAMPLE, "allocation": []}, {**EXAMPLE, "tax": None},
                    {**EXAMPLE, "start_value_eur": "Infinity"}, {**EXAMPLE, "bonds_hedged": "false"}):
            with self.subTest(raw=bad):
                response = self.client.put("/api/owner-inputs", json=bad)
                self.assertEqual(response.status_code, 422)
                self.assertTrue(response.json()["detail"])
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
