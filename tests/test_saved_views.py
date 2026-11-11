"""Saved figures retain independent state and reject stale or unsafe writes."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from finance_dashboard.saved_views import (SavedViewConflict, SavedViewError, SavedViewNotFound,
                                           SavedViewStore, SavedViewUnavailable)


SPEC = {"version": 1, "figure_id": "input:prices.*.hicp:EUROSTAT", "roles": ["DE"],
        "geographies": ["DE"], "events": [], "scale": "linear"}


def create_in_process(path, barrier, number, results):
    try:
        store = SavedViewStore(Path(path))
        barrier.wait(timeout=10)
        for index in range(8):
            store.create(f"Process {number}, figure {index}", "C01", SPEC)
        results.put(None)
    except Exception as exc:
        results.put(repr(exc))


class SavedViewTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "saved-views.json"
        self.store = SavedViewStore(self.path)

    def test_missing_store_is_empty_and_environment_selects_its_path(self):
        self.assertEqual(self.store.list(), [])
        self.assertFalse(self.path.exists())
        with patch.dict(os.environ, {"FINANCE_SAVED_VIEWS": str(self.path)}):
            record = SavedViewStore().create("Environment", "C01", SPEC)
        self.assertEqual(self.store.list(), [record])

    def test_independent_figures_reload_and_do_not_share_mutable_objects(self):
        spec = copy.deepcopy(SPEC)
        first = self.store.create("  Germany inflation  ", "C01", spec)
        second = self.store.create("Rates", "M01", {**SPEC, "figure_id": "input:policy_rate.*:ECB"})
        self.assertEqual(first["name"], "Germany inflation")
        self.assertEqual(str(UUID(first["id"])), first["id"])
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["revision"], 1)
        self.assertEqual(first["method_version"], "1")
        self.assertEqual(first["figure_id"], SPEC["figure_id"])
        spec["roles"].append("US")
        first["spec"]["geographies"].append("US")
        reloaded = SavedViewStore(self.path).list()
        self.assertEqual(reloaded[0]["spec"], SPEC)
        reloaded[0]["spec"]["roles"].clear()
        self.assertEqual(self.store.list()[0]["spec"], SPEC)
        self.assertEqual(self.store.list()[1], second)
        envelope = json.loads(self.path.read_text())
        self.assertEqual(envelope["version"], 1)
        self.assertEqual(len(envelope["items"]), 2)

    def test_update_checks_revision_preserves_other_views_and_records_method_version(self):
        first = self.store.create("First", "C01", SPEC, method_version="0")
        second = self.store.create("Other", "M01", SPEC)
        changed = self.store.update(first["id"], " Renamed ", {**SPEC, "figure_id": "result:table"},
                                    first["revision"], method_version="2")
        self.assertEqual(changed["id"], first["id"])
        self.assertEqual(changed["analysis_id"], "C01")
        self.assertEqual(changed["figure_id"], "result:table")
        self.assertEqual(changed["name"], "Renamed")
        self.assertEqual(changed["revision"], 2)
        self.assertEqual(changed["method_version"], "2")
        before = self.path.read_bytes()
        with self.assertRaises(SavedViewConflict):
            SavedViewStore(self.path).update(first["id"], "Stale", SPEC, 1)
        with self.assertRaises(SavedViewConflict):
            self.store.delete(first["id"], 1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store.list(), [changed, second])
        self.store.delete(first["id"], 2)
        self.assertEqual(self.store.list(), [second])

    def test_missing_records_are_distinct_from_conflicts(self):
        missing = str(uuid4())
        with self.assertRaises(SavedViewNotFound):
            self.store.update(missing, "Missing", SPEC, 1)
        with self.assertRaises(SavedViewNotFound):
            self.store.delete(missing, 1)
        self.assertFalse(self.path.exists())

    def test_invalid_creation_is_refused_before_writing(self):
        for name, analysis, spec, version in (
            ("", "C01", SPEC, "1"), ("   ", "C01", SPEC, "1"), ("x" * 121, "C01", SPEC, "1"),
            (False, "C01", SPEC, "1"), ("Figure", "invalid", SPEC, "1"),
            ("Figure", None, SPEC, "1"), ("Figure", "C01", [], "1"),
            ("Figure", "C01", {}, "1"), ("Figure", "C01", {"figure_id": False}, "1"),
            ("Figure", "C01", {"figure_id": ""}, "1"),
            ("Figure", "C01", {**SPEC, "unsafe": float("nan")}, "1"),
            ("Figure", "C01", {**SPEC, "unsafe": object()}, "1"),
            ("Figure", "C01", {**SPEC, 1: "not a JSON field"}, "1"),
            ("Figure", "C01", SPEC, ""), ("Figure", "C01", SPEC, True),
        ):
            with self.subTest(name=name, analysis=analysis, spec=spec, version=version):
                with self.assertRaises(SavedViewError):
                    self.store.create(name, analysis, spec, version)
                self.assertFalse(self.path.exists())

    def test_revision_and_id_validation_do_not_modify_saved_data(self):
        first = self.store.create("First", "C01", SPEC)
        before = self.path.read_bytes()
        for bad in (True, 0, -1, 1.5, "1", None):
            with self.subTest(revision=bad):
                with self.assertRaises(SavedViewError):
                    self.store.update(first["id"], "Renamed", SPEC, bad)
                with self.assertRaises(SavedViewError):
                    self.store.delete(first["id"], bad)
        with self.assertRaises(SavedViewError):
            self.store.delete("not-a-uuid", 1)
        self.assertEqual(self.path.read_bytes(), before)

    def test_excessively_nested_spec_is_a_validation_error_and_preserves_saved_state(self):
        self.store.create("Saved", "C01", SPEC)
        before = self.path.read_bytes()
        nested = []
        for _ in range(1200):
            nested = [nested]
        with self.assertRaises(SavedViewError):
            self.store.create("Invalid", "C01", {**SPEC, "nested": nested})
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_store_is_never_replaced_by_any_operation(self):
        record = self.store.create("Saved", "C01", SPEC)
        invalid_record = {**record, "figure_id": "different"}
        for document in (
            "{broken", "[]", '{"version":2,"items":[]}', '{"version":true,"items":[]}',
            '{"version":1,"items":{}}', '{"version":1,"version":1,"items":[]}',
            json.dumps({"version": 1, "items": [record, record]}),
            json.dumps({"version": 1, "items": [invalid_record]}),
            json.dumps({"version": 1, "items": [{**record, "revision": True}]}),
            json.dumps({"version": 1, "items": [{**record, "method_version": None}]}),
            json.dumps({"version": 1, "items": [{**record, "spec": {**SPEC, "bad": float("inf")}}]}),
        ):
            with self.subTest(document=document):
                self.path.write_text(document)
                before = self.path.read_bytes()
                for operation in (self.store.list,
                                  lambda: self.store.create("New", "C01", SPEC),
                                  lambda: self.store.update(record["id"], "New", SPEC, 1),
                                  lambda: self.store.delete(record["id"], 1)):
                    with self.assertRaises(SavedViewUnavailable):
                        operation()
                    self.assertEqual(self.path.read_bytes(), before)

    def test_atomic_replace_failure_keeps_old_file_and_removes_temporary_file(self):
        record = self.store.create("Saved", "C01", SPEC)
        before = self.path.read_bytes()
        with patch("finance_dashboard.saved_views.os.replace", side_effect=PermissionError("denied")):
            with self.assertRaises(SavedViewUnavailable):
                self.store.update(record["id"], "Unsaved", SPEC, 1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])
        self.assertEqual(self.store.list(), [record])

    def test_unusable_path_has_an_actionable_storage_error(self):
        parent = Path(self.folder.name) / "plain-file"
        parent.write_text("preserve")
        with self.assertRaisesRegex(SavedViewUnavailable, "saved|Saved"):
            SavedViewStore(parent / "views.json").create("Figure", "C01", SPEC)
        self.assertEqual(parent.read_text(), "preserve")

    def test_two_threads_updating_the_same_revision_have_one_winner(self):
        first = self.store.create("Saved", "C01", SPEC)
        other = self.store.create("Other", "M01", SPEC)
        barrier = threading.Barrier(2)

        def update(name):
            barrier.wait(timeout=5)
            try:
                return SavedViewStore(self.path).update(first["id"], name, SPEC, 1)
            except SavedViewConflict:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, ("Tab A", "Tab B")))
        self.assertEqual(sum(item is not None for item in results), 1)
        self.assertEqual(self.store.list()[0]["revision"], 2)
        self.assertEqual(self.store.list()[1], other)

    def test_independent_processes_keep_every_created_view(self):
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(3)
        results = context.Queue()
        processes = [context.Process(target=create_in_process, args=(str(self.path), barrier, index, results))
                     for index in range(3)]
        try:
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=15)
                self.assertFalse(process.is_alive(), "saved-view process did not finish")
                self.assertEqual(process.exitcode, 0)
            self.assertEqual([results.get(timeout=2) for _ in processes], [None, None, None])
            records = self.store.list()
            self.assertEqual(len(records), 24)
            self.assertEqual(len({item["id"] for item in records}), 24)
            self.assertEqual(len({item["name"] for item in records}), 24)
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
            results.close()
            results.join_thread()


if __name__ == "__main__":
    unittest.main()
