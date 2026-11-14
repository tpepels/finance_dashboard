"""Stable severity semantics: loading 503s are not failed collectors."""
from datetime import datetime, timezone
import unittest

from finance_dashboard.diagnostics_api import _status, _console, _attention_publishers


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
        self.assertEqual(_status([], {"summary": {"macro": {"needs_attention": 8,
            "collection_failed": 1}}}, False, False)["colour"], "red")
        self.assertEqual(_status([], {"summary": {}}, False, True)["colour"], "orange")
        self.assertEqual(_status([], {"summary": {}}, False, False)["colour"], "green")

    def test_status_explains_stale_histories_without_inventing_import_failures(self):
        coverage={"summary":{
            "macro":{"total":398,"with_data":398,"needs_attention":6,
                     "collection_failed":0,"refresh_failed_with_data":0},
            "markets":{"total":25,"with_data":25,"needs_attention":0},
            "fx":{"total":3,"with_data":3,"needs_attention":0},
        }}
        result=_status([],coverage,False,False)
        self.assertEqual(result["colour"],"orange")
        self.assertEqual(result["label"],"6 source histories need review")
        self.assertEqual(result["sources_total"],426)
        self.assertEqual(result["sources_with_data"],426)
        self.assertEqual(result["sources_needing_attention"],6)
        self.assertEqual(result["recent_errors"],0)
        self.assertEqual(result["unresolved_source_failures"],0)
        self.assertEqual(result["warnings_last_24h"],0)

    def test_recent_warnings_are_visible_separately_from_errors(self):
        when=datetime.now(timezone.utc).isoformat()
        events=[{"at":when,"scope":"macro","level":"warning",
                 "event":"source_deferred","reason":"publisher_cooldown"}]
        result=_status(events,{"summary":{}},False,False)
        self.assertEqual(result["colour"],"orange")
        self.assertEqual(result["label"],"Recent source warnings")
        self.assertEqual(result["warnings_last_24h"],1)
        self.assertEqual(result["recent_errors"],0)

    def test_compact_publisher_list_uses_actual_cached_observation_dates(self):
        rows=[
            {"provider":"WID","state":"stale","latest_source_date":"2023-01-01",
             "last_attempt_state":"success"} for _ in range(5)
        ]+[{"provider":"EUKLEMS","state":"stale",
             "latest_source_date":"2020-01-01","last_attempt_state":"success"}]
        grouped=_attention_publishers(rows)
        self.assertEqual([(r["provider"],r["count"]) for r in grouped],
                         [("WID",5),("EUKLEMS",1)])
        self.assertEqual(grouped[0]["oldest_observation"],"2023-01-01")
        self.assertEqual(grouped[1]["oldest_observation"],"2020-01-01")
        self.assertEqual(sum(r["failed"] for r in grouped),0)

    def test_console_only_formats_whitelisted_event_fields(self):
        message = _console([{"at": "2026-11-12T14:00:00+00:00", "scope": "macro",
                             "event": "source_deferred", "level": "warning",
                             "reason": "source_policy_deferred"}])[0]["message"]
        self.assertIn("source_policy_deferred", message)
        self.assertNotIn("secret", message)


if __name__ == "__main__":
    unittest.main()
