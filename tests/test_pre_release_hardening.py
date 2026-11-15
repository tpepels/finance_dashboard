"""Release-gate tests for cached diagnostic integrity and collector failure isolation."""
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock
from zipfile import ZipFile
import unittest

import httpx

from finance_dashboard.bis import ProviderError
from finance_dashboard.diagnostic_exports import DiagnosticExportManager
from finance_dashboard.source_capture import SourceAcquisition, MAX_RESPONSE_COUNT
from finance_dashboard.extra_publisher_sources import _tsv as read_publisher_table
from finance_dashboard.extra_publisher_evidence import _tsv as read_evidence_table


def sample_zip(title="ready"):
    stream=BytesIO()
    with ZipFile(stream,"w") as z:
        z.writestr("diagnostics/release.json",'{"release_id":"test-release"}')
        z.writestr("diagnostics/status.json",json.dumps({"status":title}))
    return stream.getvalue()


class DiagnosticArtifactTests(unittest.TestCase):
    def manager(self,root,build):
        return DiagnosticExportManager(
            build,zip_path=root/"export.zip",state_path=root/"state.json",lifetime=900)

    def test_valid_zip_is_hashed_and_download_rejects_same_size_tampering(self):
        with TemporaryDirectory() as temp, patch(
                "finance_dashboard.diagnostic_exports.release_info",
                return_value={"release_id":"test-release"}):
            root=Path(temp)
            manager=self.manager(root,lambda:sample_zip("good"))
            manager.prepare()
            manager.worker.join(timeout=10)
            self.assertEqual(manager.status()["state"],"ready")
            self.assertEqual(manager.ready_file(),root/"export.zip")
            self.assertEqual(manager.record["sha256"].__len__(),64)
            original=(root/"export.zip").read_bytes()
            self.assertIn(b"good",original)
            (root/"export.zip").write_bytes(original.replace(b"good",b"evil"))
            self.assertIsNone(manager.ready_file())
            self.assertEqual(manager.status()["state"],"failed")
            self.assertEqual(manager.status()["error"],"cached_zip_missing_or_corrupt")

    def test_restart_invalidates_old_archive_and_legacy_unhashed_marker(self):
        with TemporaryDirectory() as temp, patch(
                "finance_dashboard.diagnostic_exports.release_info",
                return_value={"release_id":"test-release"}):
            root=Path(temp)
            manager=self.manager(root,lambda:sample_zip())
            manager.prepare()
            manager.worker.join(timeout=10)
            self.assertEqual(manager.status()["state"],"ready")
            (root/"export.zip").write_bytes(sample_zip("tampered"))
            restarted=self.manager(root,lambda:sample_zip())
            self.assertEqual(restarted.status()["state"],"failed")
            self.assertFalse(restarted.status()["ready"])
            # Even a ready JSON state with a real ZIP must not bypass
            # the digest check during process restart.
            data=json.loads((root/"state.json").read_text())
            data.update(state="ready",sha256=None)
            (root/"state.json").write_text(json.dumps(data))
            self.assertEqual(self.manager(root,lambda:sample_zip()).status()["state"],"failed")

    def test_invalid_zip_and_missing_required_sections_never_become_ready(self):
        for payload in (b"PK\x03\x04broken",b"not a zip",b""):
            with self.subTest(payload=payload),TemporaryDirectory() as temp,patch(
                    "finance_dashboard.diagnostic_exports.release_info",
                    return_value={"release_id":"test-release"}):
                manager=self.manager(Path(temp),lambda:payload)
                manager.prepare()
                manager.worker.join(timeout=10)
                self.assertEqual(manager.status()["state"],"failed")
                self.assertFalse(manager.status()["ready"])
        bad=BytesIO()
        with ZipFile(bad,"w") as z:z.writestr("diagnostics/other.json","{}")
        self.assertFalse(DiagnosticExportManager._verify_zip_content(bad.getvalue()))

    def test_ready_zip_verification_streams_file_instead_of_reading_entire_archive(self):
        with TemporaryDirectory() as temp, patch(
                "finance_dashboard.diagnostic_exports.release_info",
                return_value={"release_id":"test-release"}):
            manager=self.manager(Path(temp),lambda:sample_zip())
            manager.prepare()
            manager.worker.join(timeout=10)
            with patch.object(Path,"read_bytes",
                              side_effect=AssertionError("whole-file read forbidden")):
                self.assertEqual(manager.ready_file(),Path(temp)/"export.zip")

    def test_missing_cached_zip_is_reported_failed_and_can_be_regenerated(self):
        with TemporaryDirectory() as temp, patch(
                "finance_dashboard.diagnostic_exports.release_info",
                return_value={"release_id":"test-release"}):
            manager=self.manager(Path(temp),lambda:sample_zip())
            manager.prepare()
            manager.worker.join(timeout=10)
            self.assertTrue(manager.status()["ready"])
            manager.zip_path.unlink()
            self.assertEqual(manager.status()["state"],"failed")
            self.assertFalse(manager.status()["ready"])
            self.assertEqual(manager.status()["error"],"cached_zip_missing_or_corrupt")
            self.assertIsNone(manager.ready_file())
            self.assertEqual(manager.prepare()["state"],"preparing")
            manager.worker.join(timeout=10)
            self.assertTrue(manager.status()["ready"])

    def test_status_poll_does_not_rehash_zip(self):
        with TemporaryDirectory() as temp, patch(
                "finance_dashboard.diagnostic_exports.release_info",
                return_value={"release_id":"test-release"}):
            manager=self.manager(Path(temp),lambda:sample_zip())
            manager.prepare()
            manager.worker.join(timeout=10)
            with patch.object(manager,"_verify_ready_archive",
                              side_effect=AssertionError("hash work on status path")):
                self.assertTrue(manager.status()["ready"])


class DiagnosticSectionRecoveryTests(unittest.TestCase):
    def test_live_diagnostics_degrades_explicitly_when_status_observers_fail(self):
        import os
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from finance_dashboard.diagnostics_api import install_diagnostics
        with TemporaryDirectory() as temp,patch.dict(os.environ,{
                "FINANCE_MAINTENANCE_STATE":str(Path(temp)/"jobs.json"),
                "FINANCE_DIAGNOSTIC_EXPORT_CACHE":str(Path(temp)/"export.zip"),
                "FINANCE_DIAGNOSTIC_EXPORT_STATE":str(Path(temp)/"export.json")}):
            app=FastAPI()
            app.state.source_health_cache=MagicMock()
            app.state.collection_workflow=MagicMock()
            app.state.data_change_coordinator=MagicMock()
            app.state.manual_sources=MagicMock()
            app.state.acceptance=MagicMock(loading=False)
            app.state.acceptance.peek.return_value=None
            importer=MagicMock()
            importer.evidence=Path(temp)
            importer.running.return_value=False
            maintenance=MagicMock()
            maintenance.list.return_value={"active_job_id":None,"jobs":[]}
            install_diagnostics(app,db=None,catalog={"series":[]},
                market_registry=[],research_document={"analyses":[]},
                maintenance=maintenance,importer=importer)
            app.state.source_health_cache.status.side_effect=OSError("health unavailable")
            app.state.collection_workflow.status.side_effect=RuntimeError("collection unavailable")
            app.state.data_change_coordinator.status.side_effect=RuntimeError("reconcile unavailable")
            with TestClient(app) as client:
                response=client.get("/api/diagnostics")
                app.state.source_health_cache.status.side_effect=None
                app.state.source_health_cache.status.return_value={
                    "state":"ready",
                    "snapshot":{"groups":{"invalid":"shape"},
                                "attention_items":{"invalid":"shape"}},
                    "error":None}
                app.state.collection_workflow.status.side_effect=None
                app.state.collection_workflow.status.return_value={"running":False}
                app.state.data_change_coordinator.status.side_effect=None
                app.state.data_change_coordinator.status.return_value={
                    "state":"complete","events_reconciled":0}
                malformed=client.get("/api/diagnostics")
            self.assertEqual(malformed.status_code,200)
            self.assertIn("source_health_snapshot",
                malformed.json()["status"]["unavailable_diagnostic_components"])
            self.assertNotEqual(malformed.json()["status"]["colour"],"green")
            self.assertEqual(response.status_code,200)
            result=response.json()
            self.assertEqual(result["status"]["colour"],"red")
            self.assertIn("source_health",result["status"]["unavailable_diagnostic_components"])
            self.assertIn("collection_status",result["status"]["unavailable_diagnostic_components"])
            self.assertIn("data_changes",result["status"]["unavailable_diagnostic_components"])
            self.assertIsNone(result["update_progress"]["collection"]["running"])
            self.assertEqual(result["data_changes"]["state"],"unavailable")

    def test_export_survives_broken_database_snapshot_and_reports_missing_section(self):
        import os
        from fastapi import FastAPI
        from finance_dashboard.diagnostics_api import install_diagnostics
        with TemporaryDirectory() as temp,patch.dict(os.environ,{
                "FINANCE_MAINTENANCE_STATE":str(Path(temp)/"jobs.json"),
                "FINANCE_DIAGNOSTIC_EXPORT_CACHE":str(Path(temp)/"export.zip"),
                "FINANCE_DIAGNOSTIC_EXPORT_STATE":str(Path(temp)/"export.json")}):
            app=FastAPI()
            app.state.source_health_cache=MagicMock()
            app.state.collection_workflow=MagicMock()
            app.state.data_change_coordinator=MagicMock()
            app.state.manual_sources=MagicMock()
            app.state.acceptance=MagicMock(loading=False)
            app.state.acceptance.peek.return_value=None
            app.state.source_health_cache.status.return_value={
                "state":"unavailable","snapshot":{},"error":None}
            app.state.collection_workflow.status.return_value={
                "running":True,"repair":{"completed":4,"total":10}}
            app.state.data_change_coordinator.status.return_value={
                "state":"pending","events_reconciled":0,"events_seen":4}
            app.state.manual_sources.status.return_value={
                "datasets":[],"jobs":[],"queued":0,"deferred":0,"active":False}
            importer=MagicMock()
            importer.evidence=Path(temp)
            importer.public_status.return_value={"state":"idle"}
            importer.running.return_value=False
            maintenance=MagicMock()
            maintenance.list.return_value={"active_job_id":None,"jobs":[]}
            with patch("finance_dashboard.source_coverage.build_coverage",
                       side_effect=RuntimeError("simulated database offline")):
                install_diagnostics(app,db=None,catalog={"series":[]},
                    market_registry=[],research_document={"analyses":[]},
                    maintenance=maintenance,importer=importer)
                output=app.state.diagnostic_exports.build()
                from fastapi.testclient import TestClient
                with TestClient(app) as client:
                    response=client.get("/api/data/debug-console")
                self.assertEqual(response.status_code,200)
                diagnostic=response.json()
                self.assertEqual(diagnostic["diagnostic_sections"]["status"],"partial")
                self.assertIn("source_snapshot",
                              diagnostic["diagnostic_sections"]["unavailable"])
            with ZipFile(BytesIO(output)) as archive:
                self.assertIn("diagnostics/status.json",archive.namelist())
                self.assertIn("diagnostics/failure-journal.json",archive.namelist())
                self.assertIn("diagnostics/source-coverage.json",archive.namelist())
                health=json.loads(archive.read("diagnostics/section-health.json"))
                self.assertEqual(health["status"],"partial")
                self.assertIn("source_snapshot",[
                    e["section"] for e in health["unavailable_sections"]])
                self.assertTrue(health["collection_in_progress"])


class OriginalResponseFailureTests(unittest.TestCase):
    @staticmethod
    def router(callback):
        client=httpx.Client()
        router=MagicMock()
        router.client=client
        router.original_reuse_hooks=[]
        router.definitions={"test.source":{"id":"test.source",
            "provider":"FRED","source_key":"TEST","frequency":"M"}}
        router.fetch.side_effect=callback(client)
        return router,client

    def test_quarantine_disk_error_cannot_hide_original_parser_error(self):
        with TemporaryDirectory() as temp:
            def parser(client):
                def run(*_):
                    response=httpx.Response(
                        200,content=b"bad publisher file",
                        request=httpx.Request("GET","https://fred.stlouisfed.org/bad.csv"))
                    for hook in tuple(client.event_hooks["response"]):
                        hook(response)
                    raise ProviderError("original_parser_failure")
                return run
            router,client=self.router(parser)
            try:
                acquire=SourceAcquisition(router,Path(temp))
                with patch.object(acquire,"_quarantine_failed_response",
                                  side_effect=OSError("archive unavailable")):
                    with self.assertRaisesRegex(ProviderError,"original_parser_failure"):
                        acquire.fetch("test.source")
            finally:
                client.close()

    def test_empty_http_rejection_keeps_transport_error_and_quarantine(self):
        with TemporaryDirectory() as temp:
            def parser(client):
                def run(*_):
                    rejected=httpx.Response(
                        503,content=b"",request=httpx.Request(
                            "GET","https://fred.stlouisfed.org/empty.csv"))
                    for hook in tuple(client.event_hooks["response"]):
                        hook(rejected)
                    raise ProviderError("upstream_http_503")
                return run
            router,client=self.router(parser)
            try:
                acquire=SourceAcquisition(router,Path(temp))
                with self.assertRaisesRegex(ProviderError,"upstream_http_503"):
                    acquire.fetch("test.source")
                self.assertTrue(list(Path(temp).glob(
                    "rejected-responses/test.source/*/manifest.json")))
                self.assertIsNone(acquire.last_evidence["receipt_name"])
            finally:
                client.close()

    def test_response_capture_cannot_accumulate_unbounded_documents(self):
        with TemporaryDirectory() as temp:
            def parser(client):
                def run(*_):
                    for n in range(MAX_RESPONSE_COUNT+1):
                        response=httpx.Response(
                            200,content=f"source row {n}".encode(),
                            request=httpx.Request("GET",
                                f"https://fred.stlouisfed.org/rows/{n}"))
                        for hook in tuple(client.event_hooks["response"]):
                            hook(response)
                    raise AssertionError("The collector must reject excess originals")
                return run
            router,client=self.router(parser)
            try:
                acquire=SourceAcquisition(router,Path(temp))
                with patch.object(acquire,"_quarantine_failed_response"):
                    with self.assertRaisesRegex(ProviderError,"response count exceeds"):
                        acquire.fetch("test.source")
            finally:
                client.close()


    def test_cached_reuse_must_obey_the_same_count_limit_as_real_network_responses(self):
        from finance_dashboard.source_documents import BatchOriginal
        with TemporaryDirectory() as temp:
            router,client=self.router(lambda _: lambda *_: None)
            response=httpx.Response(
                200, content=b"verified source",request=httpx.Request(
                    "GET","https://fred.stlouisfed.org/reused.csv"))
            original=BatchOriginal.from_response(response,"digest","anonymous")
            def overfilled(*_):
                for _ in range(MAX_RESPONSE_COUNT+1):
                    for hook in tuple(router.original_reuse_hooks):
                        hook(original)
                raise AssertionError("Reuse bypassed canonical evidence limits")
            router.fetch.side_effect=overfilled
            try:
                acquire=SourceAcquisition(router,Path(temp))
                with patch.object(acquire,"_quarantine_failed_response"):
                    with self.assertRaisesRegex(ProviderError,"response count exceeds"):
                        acquire.fetch("test.source")
                self.assertIsNone(acquire.last_evidence["receipt_name"])
                self.assertEqual(router.original_reuse_hooks,[])
            finally:
                client.close()

    def test_cached_reuse_obeys_same_byte_budget_as_real_response(self):
        from finance_dashboard.source_documents import BatchOriginal
        with TemporaryDirectory() as temp:
            router,client=self.router(lambda _: lambda *_: None)
            original=BatchOriginal.from_response(httpx.Response(
                200,content=b"123456",request=httpx.Request(
                    "GET","https://fred.stlouisfed.org/reused.csv")),
                "digest","anonymous")
            def oversized(*_):
                for _ in range(2):
                    for hook in tuple(router.original_reuse_hooks):
                        hook(original)
                raise AssertionError("Reuse bypassed source byte budget")
            router.fetch.side_effect=oversized
            try:
                acquire=SourceAcquisition(router,Path(temp))
                with patch("finance_dashboard.source_capture.MAX_BATCH_CAPTURE_BYTES",9):
                    with patch.object(acquire,"_quarantine_failed_response"):
                        with self.assertRaisesRegex(ProviderError,"bytes exceed"):
                            acquire.fetch("test.source")
                self.assertIsNone(acquire.last_evidence["receipt_name"])
            finally:
                client.close()


class SecArchiveShapeTests(unittest.TestCase):
    @staticmethod
    def archive(header):
        raw=BytesIO()
        with ZipFile(raw,"w") as z:
            z.writestr("NMFP_SUBMISSION.tsv",header)
        return raw.getvalue()

    def test_duplicate_original_header_refused_by_both_independent_readers(self):
        bad=self.archive(
            "ACCESSION_NUMBER\tACCESSION_NUMBER\tREPORTDATE\n1\t2\t2026-10-31\n")
        with ZipFile(BytesIO(bad)) as z:
            with self.assertRaises(ProviderError):
                read_publisher_table(z,"SUBMISSION")
            with self.assertRaises(Exception):
                read_evidence_table(z,"SUBMISSION")

    def test_traversal_member_refused_by_both_readers(self):
        bad=BytesIO()
        with ZipFile(bad,"w") as z:
            z.writestr("../NMFP_SUBMISSION.tsv",
                       "ACCESSION_NUMBER\tREPORTDATE\n1\t2026-10-31\n")
        with ZipFile(BytesIO(bad.getvalue())) as z:
            with self.assertRaises(ProviderError):
                read_publisher_table(z,"SUBMISSION")
            with self.assertRaises(Exception):
                read_evidence_table(z,"SUBMISSION")


if __name__=="__main__":
    unittest.main()
