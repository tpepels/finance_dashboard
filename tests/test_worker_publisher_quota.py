"""A publisher rate refusal must not crash the remaining-source audit."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from finance_dashboard.source_policy_types import PolicyDeferred, PolicyViolation
from finance_dashboard.worker import RefreshTask, execute_refresh_tasks


class PublisherQuotaTests(unittest.TestCase):
    def test_full_catalogue_scheduled_planner_reaches_dispatch_without_network(self):
        """The real mapped 524 macro source plan must not abort before first attempt."""
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from finance_dashboard.database import Base, make_engine
        from finance_dashboard.worker import refresh_all
        from finance_dashboard.providers import ProviderRouter
        with TemporaryDirectory() as directory:
            engine=make_engine("sqlite:///" + str(Path(directory)/"refresh.db"))
            Base.metadata.create_all(engine)
            chosen=[]
            def dispatch(tasks, **kwargs):
                chosen.extend(task.source_id for task in tasks)
                return 0
            with patch("finance_dashboard.worker.execute_refresh_tasks",
                       side_effect=dispatch):
                failures=refresh_all(engine, skip_complete_pinned=True)
            self.assertEqual(failures,0)
            self.assertGreaterEqual(len(chosen),500)
            self.assertIn("piketty.us.real_pretax_average.all", chosen)
            self.assertIn("labour.us.cps_weekly_p50_nominal", chosen)
            self.assertEqual(len(chosen),len(set(chosen)))
            engine.dispose()

    def test_completed_pinned_history_does_not_crash_scheduled_plan(self):
        """Regression for 2.11: skipped= keyword caused TypeError only on populated DB."""
        from datetime import date, datetime, timezone
        from decimal import Decimal
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from sqlalchemy.orm import Session
        from finance_dashboard.catalog import load_documents
        from finance_dashboard.database import (
            Base, make_engine, SeriesRow, IngestionRun, ObservationVersion)
        from finance_dashboard.worker import refresh_all
        from finance_dashboard.developer_logs import record_event
        sid="labour.us.pwt_labour_share"
        definition=next(x for x in load_documents()[0]["series"] if x["id"]==sid)
        with TemporaryDirectory() as directory:
            engine=make_engine("sqlite:///"+str(Path(directory)/"repro.db"))
            Base.metadata.create_all(engine)
            now=datetime.now(timezone.utc)
            with Session(engine) as session, session.begin():
                session.add(SeriesRow(id=sid,provider=definition["provider"],
                                      source_key=definition["source_key"],updated_at=now))
                session.add(IngestionRun(id="pinned-run",series_id=sid,status="success",
                                         started_at=now,ended_at=now,
                                         observations_received=1,versions_added=1))
                session.add(ObservationVersion(series_id=sid,period=date(2023,1,1),
                                               value=Decimal("0.44"),first_seen_at=now,
                                               ingestion_run_id="pinned-run"))
            planned=[]
            def dispatch(tasks,**kwargs):
                planned.extend(task.source_id for task in tasks)
                return 0
            try:
                with (patch("finance_dashboard.worker.execute_refresh_tasks",
                            side_effect=dispatch),
                      patch("finance_dashboard.worker.record_event",
                            wraps=record_event) as events):
                    result=refresh_all(engine,skip_complete_pinned=True)
                self.assertEqual(result,0)
                self.assertNotIn(sid,planned)
                self.assertIn("piketty.us.real_pretax_average.all",planned)
                self.assertIn("labour.us.cps_weekly_p50_nominal",planned)
                self.assertTrue(any(call.kwargs.get("action")=="pinned_release_reuse"
                                    and call.kwargs.get("completed",0)>=1
                                    and "skipped" not in call.kwargs
                                    for call in events.call_args_list))
            finally:
                engine.dispose()

    def test_bad_bound_on_one_source_does_not_skip_its_or_siblings_attempts(self):
        from datetime import date
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from finance_dashboard.database import Base, make_engine
        from finance_dashboard.source_coverage import PUBLICATION_BOUNDS
        from finance_dashboard.worker import refresh_all
        sid="labour.us.pwt_labour_share"
        with TemporaryDirectory() as directory:
            engine=make_engine("sqlite:///"+str(Path(directory)/"badbound.db"))
            Base.metadata.create_all(engine)
            dispatched=[]
            try:
                with (patch.dict(PUBLICATION_BOUNDS,{
                          sid:{"released":"2025-10-07","through":date(2023,1,1)}}),
                      patch("finance_dashboard.worker.execute_refresh_tasks",
                            side_effect=lambda tasks,**kwargs: dispatched.extend(
                                task.source_id for task in tasks) or 0),
                      patch("finance_dashboard.worker.record_event") as recorder):
                    failures=refresh_all(engine,skip_complete_pinned=True)
                self.assertEqual(failures,1)
                self.assertIn(sid,dispatched)
                self.assertIn("piketty.us.real_pretax_average.all",dispatched)
                self.assertTrue(any(call.kwargs.get("stage")=="publication_bound_item"
                                    and call.kwargs.get("source_id")==sid
                                    for call in recorder.call_args_list))
            finally:
                engine.dispose()

    def test_rotation_query_failure_still_dispatches_every_other_source(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from finance_dashboard.database import Base, make_engine
        from finance_dashboard.worker import refresh_all
        with TemporaryDirectory() as directory:
            engine=make_engine("sqlite:///"+str(Path(directory)/"rotation.db"))
            Base.metadata.create_all(engine)
            chosen=[]
            def fail_query(_engine):
                raise RuntimeError("DATABASE_URL=should_not_reach_logs")
            try:
                with (patch("finance_dashboard.worker.Session",side_effect=fail_query),
                      patch("finance_dashboard.worker.execute_refresh_tasks",
                            side_effect=lambda tasks,**kwargs: chosen.extend(
                                task.source_id for task in tasks) or 0),
                      patch("finance_dashboard.worker.record_event") as recorder):
                    failures=refresh_all(engine,skip_complete_pinned=False)
                self.assertEqual(failures,1)
                self.assertGreaterEqual(len(chosen),500)
                self.assertIn("piketty.us.real_pretax_average.all",chosen)
                self.assertTrue(any(call.kwargs.get("stage")=="rotation_query"
                                    for call in recorder.call_args_list))
            finally:
                engine.dispose()

    def test_failed_source_and_progress_callback_cannot_abort_siblings(self):
        calls=[]
        progress=[]
        def fail():
            calls.append("wid-bad")
            raise ValueError("source invalid")
        def success(label):
            def run():
                calls.append(label)
                return {"received":1}
            return run
        tasks=[
            RefreshTask("macro","wid-a",fail,"wid-a",provider_group="WID"),
            RefreshTask("macro","wid-b",success("wid-good"),"wid-b",provider_group="WID"),
            RefreshTask("macro","fred-a",success("fred-good"),"fred-a",provider_group="FRED"),
            RefreshTask("macro","oecd-a",success("oecd-good"),"oecd-a",
                        provider_group="OECD_EARNINGS"),
        ]
        def progress_callback(index,total,source):
            progress.append(source)
            if index==2:
                raise ValueError("UI status callback failed")
        with patch("finance_dashboard.worker.record_event") as events:
            failures=execute_refresh_tasks(tasks,progress=progress_callback)
        self.assertEqual(failures,2)
        self.assertEqual(calls,["wid-bad","wid-good","fred-good","oecd-good"])
        self.assertEqual(progress,["wid-a","wid-b","fred-a","oecd-a"])
        self.assertTrue(any(call.kwargs.get("action")=="source_refresh_batch"
                            and call.kwargs.get("completed")==4
                            and call.kwargs.get("failed")==2
                            for call in events.call_args_list))

    def test_read_only_preflight_plans_full_catalogue_without_ingesting_or_contacting_publishers(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from sqlalchemy import func, select
        from sqlalchemy.orm import Session
        from finance_dashboard.database import Base, IngestionRun, make_engine
        from finance_dashboard.worker import refresh_all
        with TemporaryDirectory() as directory:
            engine=make_engine("sqlite:///" + str(Path(directory) / "preflight.db"))
            Base.metadata.create_all(engine)
            try:
                with patch("finance_dashboard.worker.execute_refresh_tasks",
                           side_effect=AssertionError("preflight must never ingest")) as dispatch:
                    result=refresh_all(engine,skip_complete_pinned=True,
                                       preflight_only=True)
                    self.assertEqual(result,0)
                    dispatch.assert_not_called()
                with Session(engine) as session:
                    self.assertEqual(session.scalar(
                        select(func.count()).select_from(IngestionRun)),0)
            finally:
                engine.dispose()

    def test_planner_failure_journals_stage_and_safe_class_without_leaking_error(self):
        from finance_dashboard.worker import refresh_all
        with (patch("finance_dashboard.worker.ProviderRouter",
                    side_effect=ValueError("secret provider API key in exception")),
              patch("finance_dashboard.worker.record_event") as recorder):
            with self.assertRaisesRegex(ValueError,"secret provider"):
                refresh_all(None)
            call=next(x for x in recorder.call_args_list
                      if x.args[:2]==("macro","collector_failed"))
            self.assertEqual(call.kwargs["action"],"scheduled_refresh_plan")
            self.assertEqual(call.kwargs["stage"],"instantiate_router")
            self.assertEqual(call.kwargs["reason"],"ValueError")
            self.assertNotIn("secret",str(call))

    def test_suppressed_sources_report_complete_bounded_diagnostics_without_crash(self):
        calls = []
        progress = []

        def deferred():
            calls.append("wid-first")
            raise PolicyDeferred("wid", "rolling_window_limit", time.time() + 90)

        def must_not_run():
            calls.append("wid-unattempted")
            raise AssertionError("Exhausted publisher must be skipped")

        def unrelated():
            calls.append("fred")
            return {"status": "success", "received": 1}

        tasks = [
            RefreshTask("macro", "inequality.world.pretax_income.top1",
                        deferred, "world-1", provider_group="WID"),
            RefreshTask("macro", "inequality.world.pretax_income.top10",
                        must_not_run, "world-2", provider_group="WID"),
            RefreshTask("macro", "inequality.world.net_personal_wealth.top10",
                        must_not_run, "world-3", provider_group="WID"),
            RefreshTask("macro", "bond.us.nominal_10y",
                        unrelated, "unrelated", provider_group="FRED"),
        ]
        with patch("finance_dashboard.worker.record_event", autospec=True) as log:
            failed = execute_refresh_tasks(tasks, progress=lambda *p: progress.append(p))
        self.assertEqual(failed, 3)
        self.assertEqual(calls, ["wid-first", "fred"])
        self.assertEqual(len(progress), 4)
        self.assertEqual(progress[-1], (4, 4, "unrelated"))
        self.assertTrue(any(
            call.args[:2] == ("macro", "stage_finished")
            and call.kwargs.get("action") == "publisher_quota_exhausted"
            and call.kwargs.get("stage") == "WID"
            and call.kwargs.get("failed") == 2
            for call in log.call_args_list))
        self.assertFalse(any(
            "provider" in call.kwargs or "sources_not_attempted" in call.kwargs
            for call in log.call_args_list))


    def test_publisher_policy_access_failure_records_controlled_reason_without_secrets(self):
        def blocked():
            raise PolicyViolation("unclassified", "publisher_rule_missing")
        task = RefreshTask(
            "macro", "returns.swinkels.au.sovereign_10y_modelled_local",
            blocked, "swinkels", provider_group="SWINKELS_RETURNS")
        with patch("finance_dashboard.worker.record_event", autospec=True) as logs:
            failed = execute_refresh_tasks([task])
        self.assertEqual(failed, 1)
        event = next(call for call in logs.call_args_list
                     if call.args[1] == "source_failed")
        self.assertEqual(event.kwargs["reason"], "source_policy_denied")
        self.assertEqual(event.kwargs["stage"],
                         "unclassified:publisher_rule_missing")
        self.assertNotIn("url", str(event))
        self.assertNotIn("secret", str(event).lower())


if __name__ == "__main__":
    unittest.main()
