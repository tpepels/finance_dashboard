"""Policy inspection is read-only, redacted and requires no publisher access."""
import json
from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from finance_dashboard.source_policy_cli import main


class PolicyStatusTests(unittest.TestCase):
    def test_brief_local_registry_inventory(self):
        with patch("finance_dashboard.source_policy_cli.policy_summary", return_value={
            "registry_sha256": "a" * 64,
            "publisher_count": 2, "host_count": 3,
            "unclassified_hosts_denied": True, "requests_recorded": 7,
            "catalog_source_reference_coverage": {
                "source_references_classified": 262,
                "unclassified_or_invalid_source_references": [],
            },
            "publishers": [
                {"id": "fred-v1", "classification": "publisher_verified", "collection_enabled": True},
                {"id": "ishares", "classification": "restricted_use", "collection_enabled": True},
            ],
            "state": [
                {"publisher": "fred-v1", "cooldown_seconds_remaining": 30,
                 "last_http_status": 429},
                {"publisher": "ishares", "cooldown_seconds_remaining": 0,
                 "last_http_status": None},
            ],
        }):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["--brief"]), 0)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["registered_publishers"], 2)
        self.assertEqual(report["catalog_references_classified"], 262)
        self.assertEqual(report["catalog_reference_issues"], [])
        self.assertEqual(report["publisher_cooldowns"][0]["http_status"], 429)
        self.assertEqual(report["licence_restricted_sources"], ["ishares"])
        self.assertEqual(report["collection_mode"], "personal_private_best_effort")
        self.assertEqual(report["operator_acknowledgement_required"], [])
        self.assertNotIn("source_url", output.getvalue())

    def test_classify_url_without_network(self):
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                "--check-url",
                "https://api.stlouisfed.org/fred/series/observations"
            ]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["publisher_id"], "fred-v1")
        self.assertTrue(report["no_network_request"])

    def test_unknown_url_classification_rejected(self):
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                "--check-url", "https://unknown.example.net/?api_key=secret"
            ]), 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["classification"], "denied")
        self.assertNotIn("secret", output.getvalue())


if __name__ == "__main__":
    unittest.main()
