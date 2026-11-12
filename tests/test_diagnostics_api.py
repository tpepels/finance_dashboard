"""Stable severity semantics: loading 503s are not failed collectors."""
from datetime import datetime, timezone
import unittest

from finance_dashboard.diagnostics_api import _status, _console


class DiagnosticsSeverityTests(unittest.TestCase):
    def test_expected_research_503_does_not_mark_system_red(self):
        events = [{"at": datetime.now(timezone.utc).isoformat(), "scope": "system",
                   "level": "error", "event": "collector_failed",
                   "stage": "api", "http_status": 503, "reason": "http_5xx"}]
        current = {"summary": {"macro": {"needs_attention": 0},
                               "fx": {"needs_attention": 0}}}
        result = _status(events, current, accepting=False, importing=False)
        self.assertNotEqual(result["colour"], "red")
        self.assertEqual(result["recent_errors"], 0)

    def test_source_failure_is_red_and_deferred_sources_or_imports_are_orange(self):
        events = [{"at": datetime.now(timezone.utc).isoformat(), "scope": "macro",
                   "level": "error", "event": "source_failed", "reason": "provider_failed"}]
        current = {"summary": {"macro": {"needs_attention": 8}}}
        self.assertEqual(_status(events, current, False, False)["colour"], "red")
        self.assertEqual(_status([], current, False, False)["colour"], "orange")
        self.assertEqual(_status([], {"summary": {}}, False, True)["colour"], "orange")
        self.assertEqual(_status([], {"summary": {}}, False, False)["colour"], "green")

    def test_console_only_formats_whitelisted_event_fields(self):
        message = _console([{"at": "2026-11-12T14:00:00+00:00", "scope": "macro",
                             "event": "source_deferred", "level": "warning",
                             "reason": "source_policy_deferred"}])[0]["message"]
        self.assertIn("source_policy_deferred", message)
        self.assertNotIn("secret", message)


if __name__ == "__main__":
    unittest.main()
