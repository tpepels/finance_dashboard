"""Bounded manual original-source intake in the existing dashboard and ingestion store.

Source/role allowlists are server-owned. User-uploaded bytes are *not* remote
publisher acquisitions: every retained bundle labels provenance as owner-
supplied, with immutable byte hashes and an independent receipt. The canonical
provider parsers and IngestionService perform all economic validation and
append-only observations; no CSV mapping or unknown source URL is accepted.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock, Thread
from tempfile import NamedTemporaryFile, mkdtemp
from uuid import uuid4
import json
import os
import re
import shutil
import time

from fastapi import FastAPI, HTTPException, Header, Request

from .original_uploads import _guard
from .source_evidence import record_acquisition_receipt
from .bis import FetchedSeries, ProviderError
from .catalog import load_documents
from .service import IngestionService
from .standalone import maintenance_network_lock

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.() -]{0,119}$")

def _definitions() -> dict:
    return {row["id"]: row for row in load_documents()[0]["series"]}

def source_specs() -> dict[str, dict]:
    """Publisher links from canonical, fixed request identities only."""
    from .wid import WID_ROOT, WID_SERIES
    from .research_returns import (SWINKELS_DATA_URL, SWINKELS_README_URL,
        SWINKELS_METADATA_URL, SWINKELS_ORIGINAL_METADATA_URL)
    from .euklems import euklems_url
    from .msci_regional_factsheets import FACTSHEET_URLS, METHODOLOGY, _MSCI
    from .provider_parsers import GOLD_API_SPOT_LATEST
    from .oecd_icio_access import PUBLISHER_URLS
    from .msci_regional_factsheets import _GEN3
    defs = _definitions()
    def role(key, label, url, ext, limit):
        return {"id": key, "label": label, "download_url": url,
                "accept": ext, "max_bytes": limit}
    specs = {
        "wid-world": {
            "title": "WID.world — world income and wealth",
            "description": "Both original world CSV files are required. Import updates five registered series.",
            "series_ids": sorted(sid for sid, (area, _, _) in WID_SERIES.items() if area == "WO"),
            "roles": [
                role("data", "WID world observations", WID_ROOT + "/WID_data_WO.csv", ".csv", 200_000_000),
                role("metadata", "WID variable metadata", WID_ROOT + "/WID_metadata_WO.csv", ".csv", 30_000_000),
            ],
        },
        "euklems-us": {
            "title": "EU KLEMS — US labour compensation",
            "description": "Original 2025 US growth accounts workbook; the LAB/TOT/US row is validated.",
            "series_ids": ["labour.us.euklems_labour_compensation"],
            "roles": [role("workbook", "US growth accounts", euklems_url("US/TOT/LAB"), ".xlsx", 35_000_000)],
        },
        "swinkels-au": {
            "title": "Swinkels — original sovereign returns",
            "description": "Only the exact SHA-256-pinned v6 ODS workbook is accepted. Methodology and publisher metadata remain separate.",
            "series_ids": ["returns.swinkels.au.sovereign_10y_modelled_local"],
            "roles": [role("workbook", "Original v6 returns workbook", SWINKELS_DATA_URL, ".ods", 5_000_000)],
            "reference_links": [
                {"label": "Publisher ReadMe", "url": SWINKELS_README_URL},
                {"label": "Dataverse release metadata", "url": SWINKELS_METADATA_URL},
                {"label": "Original v6 publication metadata", "url": SWINKELS_ORIGINAL_METADATA_URL},
            ],
        },
        "gold-spot": {
            "title": "Gold — indicative USD spot",
            "description": "Current XAU/USD JSON with source timestamp. Older quotes are rejected.",
            "series_ids": ["gold.usd.spot"],
            "roles": [role("json", "Current XAU spot response", GOLD_API_SPOT_LATEST, ".json", 1_000_000)],
        },
    }
    specs["msci-methodology"] = {
        "title": "MSCI — fundamental data methodology (March 2021)",
        "description": ("Needed once when the pinned archived methodology is not already present. "
                        "Only the exact pinned PDF SHA-256 is accepted."),
        "series_ids": [],
        "roles": [role("methodology", "March 2021 methodology PDF",
                       METHODOLOGY["original_url"], ".pdf", 5_000_000)],
    }
    for index in ("EAFE", "EUROPE", "JAPAN"):
        sid = index.lower()
        matched = [x for x in defs.values()
                   if x["provider"] == "MSCI_REGIONAL_FACTSHEETS"
                   and x["source_key"] in (index + "/PE", index + "/PE_FWD")]
        if len(matched) != 2:
            raise RuntimeError("Manual MSCI source contract mismatched")
        original = matched[0]["source_url"]
        if original not in {_MSCI + suffix for suffix in FACTSHEET_URLS[index]}:
            raise RuntimeError("Unregistered MSCI original URL")
        specs["msci-" + sid] = {
            "title": "MSCI " + index.title() + " — valuation factsheet",
            "description": "Original MSCI PDF. Trailing and forward P/E are parsed from the printed index table.",
            "series_ids": sorted(item["id"] for item in matched),
            "roles": [role("factsheet", "Index factsheet PDF", original, ".pdf", 5_000_000)],
        }
    for spec in specs.values():
        for sid in spec["series_ids"]:
            if sid not in defs or defs[sid]["status"] != "mapped":
                raise RuntimeError("Manual source ID no longer registered: " + sid)
    specs["oecd-icio"] = {
        "title": "OECD — ICIO original archives",
        "description": "Use the existing checked ZIP/ReadMe importer below. Earlier and extended editions are supported there.",
        "series_ids": [],
        "roles": [],
        "existing_importer": True,
        "reference_links": [
            {"label": "All OECD ICIO editions: 2025 regular/extended, 2023, 2021, 2018",
             "url": "https://www.oecd.org/en/data/datasets/inter-country-input-output-tables.html"},
            *[{"label": "2025 regular / " + filename, "url": url}
              for filename, url in PUBLISHER_URLS.items()],
        ],
    }
    return specs


def _parse_source(dataset: str, files: dict[str, bytes]) -> dict[str, dict]:
    """Return canonical original-date Decimal observations, never user-supplied mappings."""
    from .wid import WID_SERIES, parse_wid_bundle
    from .euklems import parse_euklems_workbook
    from .research_returns import SWINKELS_SHA256, parse_swinkels_ods
    from .provider_parsers import parse_gold_api_spot
    if dataset == "wid-world":
        try:
            data = files["data"].decode("utf-8-sig")
            metadata = files["metadata"].decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ProviderError("WID original text encoding invalid") from exc
        bundle = parse_wid_bundle(data, metadata, area="WO")
        return {sid: bundle.observations[(key, percentile)]
                for sid, (area, key, percentile) in WID_SERIES.items()
                if area == "WO"}
    if dataset == "euklems-us":
        return {"labour.us.euklems_labour_compensation":
                parse_euklems_workbook(files["workbook"], "US/TOT/LAB")}
    if dataset == "swinkels-au":
        if sha256(files["workbook"]).hexdigest() != SWINKELS_SHA256:
            raise ProviderError("Swinkels source does not match exact pinned v6 original SHA-256")
        original = parse_swinkels_ods(files["workbook"])
        sid = "returns.swinkels.au.sovereign_10y_modelled_local"
        return {sid: original.observations[sid]}
    if dataset == "gold-spot":
        try:
            payload = json.loads(files["json"])
        except (ValueError, UnicodeError) as exc:
            raise ProviderError("Gold spot original JSON invalid") from exc
        return {"gold.usd.spot": parse_gold_api_spot(payload)}
    if dataset == "msci-methodology":
        from .msci_regional_factsheets import archived_pdf, METHODOLOGY, MsciFactsheetError
        pdf, _ = archived_pdf(files["methodology"])
        if sha256(pdf).hexdigest() != METHODOLOGY["pdf_sha256"]:
            raise MsciFactsheetError("manual_methodology_differs_from_pinned_edition")
        return {}
    if dataset.startswith("msci-"):
        from .msci_regional_factsheets import parse_factsheet_payload, MsciFactsheetError
        index = dataset[5:].upper()
        facts, _ = parse_factsheet_payload(files["factsheet"])
        if facts["index"] != index:
            raise ProviderError("MSCI uploaded original prints a different index")
        if date.fromisoformat(facts["as_of"]) > date.today():
            raise ProviderError("MSCI original factsheet is future dated")
        return {}
    raise ProviderError("Unregistered manual original source")


def _archive(root: Path, dataset: str, files: dict[str, bytes], roles: list[dict],
             *, downloads: dict | None = None) -> tuple[str, str]:
    """Retain original bytes, distinguishing uploaded and publisher-fetched origins."""
    hashes = {role["id"]: sha256(files[role["id"]]).hexdigest() for role in roles}
    fingerprint = sha256(json.dumps(
        {"hashes": hashes, "mode": "publisher_https"} if downloads else hashes,
        sort_keys=True).encode()).hexdigest()
    parent = root / "manual-sources" / dataset
    folder = parent / fingerprint
    origin = "publisher_https" if downloads else "user_upload"
    manifest = {"schema_version": 1,
                "kind": "publisher_fetched_original" if downloads else "owner_uploaded_original",
                "source_identity": {"dataset": dataset, "acquisition": origin},
                "files": hashes,
                "source_urls": {role["id"]: role["download_url"] for role in roles},
                "publisher_origin_verified": bool(downloads),
                "first_publication_verified": False}
    if downloads:
        if set(downloads) != set(hashes) or any(
                downloads[key]["sha256"] != hashes[key] for key in hashes):
            raise ProviderError("Publisher download receipt hash mismatch")
        manifest["download_evidence"] = {
            key: {field: downloads[key][field] for field in (
                "requested_url", "sha256", "bytes")} for key in sorted(downloads)}
    temporary = None
    try:
        parent.mkdir(parents=True, exist_ok=True)
        if not folder.exists():
            temporary = Path(mkdtemp(prefix=".manual-", dir=parent))
            for key, content in files.items():
                (temporary / (key + ".bin")).write_bytes(content)
            (temporary / "manifest.json").write_text(
                json.dumps(manifest, sort_keys=True), encoding="utf-8")
            try:
                os.rename(temporary, folder)
                temporary = None
            except FileExistsError:
                pass
        if folder.is_symlink() or not folder.is_dir():
            raise ProviderError("Manual source archive identity invalid")
        existing = json.loads((folder / "manifest.json").read_text())
        if existing != manifest:
            raise ProviderError("Manual source archive manifest mismatch")
        for key, content in files.items():
            path = folder / (key + ".bin")
            if path.is_symlink() or sha256(path.read_bytes()).hexdigest() != hashes[key]:
                raise ProviderError("Manual source archive hash mismatch")
        receipt = record_acquisition_receipt(
            folder, manifest["source_identity"],
            acquisition={"mode": ("publisher_https_verified_endpoint" if downloads else
                                   "owner_supplied_unverified_publisher_origin"),
                         **({"downloads": downloads} if downloads else {})})
        return folder.name, receipt.name
    finally:
        if temporary and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


class _PreparedManualProvider:
    """Same canonical ingestion service, with validated local original provenance."""
    def __init__(self, series: dict[str, dict], evidence: dict, definitions: dict):
        self.series, self.last_evidence, self.definitions = series, evidence, definitions

    def fetch(self, series_id, start=None):
        if series_id not in self.series:
            raise ProviderError("Manual source not mapped to requested canonical series")
        values = {period: value for period, value in self.series[series_id].items()
                  if start is None or period >= start}
        if not values:
            raise ProviderError("Manual source has no observations in requested period")
        return FetchedSeries(series_id, self.definitions[series_id]["source_url"],
                             None, values)


class ManualSourceManager:
    """Durable FIFO import queue; uploads never wait for ongoing research work."""

    def __init__(self, engine, *, stage: Path | None = None, evidence: Path | None = None,
                 journal: Path | None = None, accepted=None):
        self.engine = engine
        self.accepted = accepted or (lambda: None)
        self.stage = Path(stage or os.environ.get(
            "FINANCE_MANUAL_SOURCE_DIR", "/data/incoming/manual-sources"))
        self.evidence = Path(evidence or os.environ.get(
            "FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence"))
        self.journal = Path(journal or os.environ.get(
            "FINANCE_MANUAL_IMPORT_JOURNAL", "/data/maintenance/manual-imports.json"))
        self.lock = Lock()
        self._wake = Event()
        self.active = False
        self._worker: Thread | None = None
        self.jobs: list[dict] = []
        try:
            saved = json.loads(self.journal.read_text())
            for job in saved.get("jobs", [])[-80:]:
                # Replay an immutable snapshot after a process restart.
                # Ingestion is content-addressed/idempotent; the interrupted
                # job keeps its original identity and no new source URL.
                job.setdefault("method", "upload")
                if job["status"] in ("running", "downloading"):
                    job["status"] = ("queued" if re.fullmatch(r"[0-9a-f]{32}", job["id"])
                                     and not self._job_dir(job["id"]).is_symlink()
                                     and self._job_dir(job["id"]).is_dir()
                                     else "interrupted")
                self.jobs.append(job)
        except (OSError, ValueError, TypeError, KeyError):
            pass
        with self.lock:
            if any(job["status"] in ("queued", "deferred") for job in self.jobs):
                self._ensure_worker()

    def _save(self):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8",
                                    prefix=".manual-jobs-", dir=self.journal.parent,
                                    delete=False) as out:
                temporary = Path(out.name)
                json.dump({"version": 2, "jobs": self.jobs[-80:]}, out)
                out.flush()
                os.fsync(out.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.journal)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _job_dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise ValueError("Invalid import job identifier")
        return self.stage / "_jobs" / job_id

    def _staged(self, dataset, roles):
        folder = self.stage / dataset
        out = {}
        for role in roles:
            path = folder / (role["id"] + ".bin")
            if path.is_symlink():
                raise ProviderError("Manual upload symlink forbidden")
            if path.is_file():
                size = path.stat().st_size
                if not 0 < size <= role["max_bytes"]:
                    raise ProviderError("Manual upload size invalid")
                out[role["id"]] = {"bytes": size}
        return out

    def status(self):
        specs = source_specs()
        with self.lock:
            return {
                "datasets": [{**spec, "id": name,
                              "staged": self._staged(name, spec["roles"])}
                             for name, spec in specs.items()],
                "active": self.active,
                "queued": sum(job["status"] == "queued" for job in self.jobs),
                "deferred": sum(job["status"] == "deferred" for job in self.jobs),
                "jobs": [dict(job) for job in reversed(self.jobs[-80:])],
            }

    def _ensure_worker(self):
        # Caller owns self.lock. The worker resets the slot before exiting to
        # avoid losing a job queued during its shutdown boundary.
        if self._worker is None or not self._worker.is_alive():
            self._worker = Thread(target=self._drain, daemon=True,
                                  name="gcm-original-import-queue")
            self._worker.start()
        else:
            self._wake.set()

    def _enqueue(self, dataset: str, method: str) -> str | None:
        """Caller owns self.lock. Uploads are snapshot-linked before queuing."""
        spec = source_specs()[dataset]
        if not spec["roles"] and (dataset != "oecd-icio" or method != "publisher"):
            raise ValueError("This source uses its dedicated importer")
        if method == "upload" and len(self._staged(dataset, spec["roles"])) != len(spec["roles"]):
            return None
        if method == "publisher":
            pending = next((job for job in reversed(self.jobs)
                            if job["dataset"] == dataset and job["method"] == "publisher"
                            and job["status"] in ("queued", "downloading", "running", "deferred")), None)
            if pending:
                return pending["id"]
        job_id = uuid4().hex
        spool = self._job_dir(job_id)
        spool.mkdir(parents=True, exist_ok=False)
        try:
            if method == "upload":
                for role in spec["roles"]:
                    path = self.stage / dataset / (role["id"] + ".bin")
                    if path.is_symlink() or not path.is_file():
                        raise ProviderError("Original upload staging changed")
                    os.link(path, spool / (role["id"] + ".bin"))
            job = {"id": job_id, "dataset": dataset, "method": method,
                   "status": "queued", "created_at": datetime.now(timezone.utc).isoformat(),
                   "finished_at": None, "sources": [], "error_code": None,
                   "downloaded": {}, "phase": "waiting"}
            self.jobs.append(job)
            try:
                self._save()
            except Exception:
                self.jobs.pop()
                raise
            if method == "upload":
                # The queued job owns immutable file links. New uploads can be
                # accepted immediately, even for the same dataset.
                for role in spec["roles"]:
                    (self.stage / dataset / (role["id"] + ".bin")).unlink(missing_ok=True)
            self._ensure_worker()
            return job_id
        except Exception:
            shutil.rmtree(spool, ignore_errors=True)
            raise

    def start(self, dataset: str) -> str:
        if dataset not in source_specs() or not source_specs()[dataset]["roles"]:
            raise ValueError("Unknown manual source")
        with self.lock:
            token = self._enqueue(dataset, "upload")
            if token is not None:
                return token
            # Retry a retained failed/interrupted immutable upload snapshot.
            old = next((job for job in reversed(self.jobs)
                        if job["dataset"] == dataset and job["method"] == "upload"
                        and job["status"] in ("failed", "partial", "interrupted")
                        and self._job_dir(job["id"]).is_dir()), None)
            if old is None:
                raise ValueError("Required original files not yet uploaded")
            old.update(status="queued", phase="waiting", error_code=None,
                       finished_at=None, sources=[])
            self._save()
            self._ensure_worker()
            return old["id"]

    def fetch(self, dataset: str | None = None):
        specs = source_specs()
        if dataset is not None and dataset not in specs:
            raise ValueError("Unknown publisher download source")
        queued, skipped = [], {}
        with self.lock:
            for name, spec in specs.items():
                if dataset is not None and name != dataset:
                    continue
                if not spec["roles"] and name != "oecd-icio":
                    skipped[name] = "dedicated_original_importer"
                    continue
                if dataset is None and any(
                        job["dataset"] == name and job["status"] == "complete"
                        for job in self.jobs):
                    skipped[name] = "already_imported"
                    continue
                token = self._enqueue(name, "publisher")
                if token is not None:
                    queued.append({"dataset": name, "job_id": token})
        return {"jobs": queued, "skipped": skipped}

    def _drain(self):
        """Process ready jobs and revisit publisher deferrals at their due time.

        Publisher rate budgets remain owned by the shared managed transport.
        Deferred jobs do not block new uploads or other queued datasets.
        """
        from .source_policy_types import PolicyDeferred
        from .publisher_downloads import PublisherDownloadError
        from .service import safe_source_failure_code
        while True:
            waiting = False
            with self.lock:
                now = time.time()
                job = next((item for item in self.jobs
                            if item["status"] == "queued" or
                            (item["status"] == "deferred" and
                             float(item.get("retry_at_unix") or 0) <= now)), None)
                if job is None:
                    due = [float(item["retry_at_unix"]) for item in self.jobs
                           if item["status"] == "deferred" and item.get("retry_at_unix")]
                    if not due:
                        self.active = False
                        self._worker = None
                        return
                    self.active = False
                    waiting = True
                    timeout = max(.1, min(3600, min(due) - now))
                    self._wake.clear()
                else:
                    self.active = True
                    job["status"] = "downloading" if job["method"] == "publisher" else "running"
                    job["phase"] = "downloading" if job["method"] == "publisher" else "validating"
                    job["retry_at_unix"] = None
                    self._save()
            if waiting:
                self._wake.wait(timeout)
                continue
            try:
                with maintenance_network_lock:
                    self._run(job)
            except PolicyDeferred as exc:
                with self.lock:
                    job["status"] = "deferred"
                    job["phase"] = "waiting_for_publisher_budget"
                    job["error_code"] = exc.reason
                    job["retry_at_unix"] = max(float(exc.retry_at), time.time() + 1)
                    self._save()
            except Exception as exc:
                with self.lock:
                    job["status"] = "failed"
                    job["error_code"] = (exc.code if isinstance(exc, PublisherDownloadError)
                                         else safe_source_failure_code(exc))
                    job["finished_at"] = datetime.now(timezone.utc).isoformat()
                    job["phase"] = "failed"
                    self._save()

    def _run(self, job: dict):
        from .publisher_downloads import fetch_publisher_file
        dataset, method = job["dataset"], job["method"]
        spec = source_specs()[dataset]
        folder = self._job_dir(job["id"])
        if dataset == "oecd-icio":
            self._run_icio(job, folder)
            return
        downloads = dict(job.get("downloaded") or {}) if method == "publisher" else {}
        if method == "publisher":
            for role in spec["roles"]:
                role_id = role["id"]
                path = folder / (role_id + ".bin")
                recorded = downloads.get(role_id)
                if (recorded and path.is_file() and not path.is_symlink()
                        and 0 < path.stat().st_size <= role["max_bytes"]
                        and sha256(path.read_bytes()).hexdigest() == recorded.get("sha256")):
                    continue  # verified prior role: do not burn another publisher permit
                downloads.pop(role_id, None)
                detail = fetch_publisher_file(role, path)
                downloads[role_id] = detail
                with self.lock:
                    job["downloaded"] = dict(downloads)
                    self._save()
        with self.lock:
            job["status"] = "running"
            job["phase"] = "validating"
            self._save()
        files = {}
        for role in spec["roles"]:
            path = folder / (role["id"] + ".bin")
            if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= role["max_bytes"]:
                raise ProviderError("Queued original source file invalid")
            files[role["id"]] = path.read_bytes()
        values = _parse_source(dataset, files)
        if dataset == "msci-methodology":
            from .msci_regional_factsheets import store_manual_methodology
            digest, receipt = store_manual_methodology(
                self.evidence, files["methodology"], publisher_download=bool(downloads))
            evidence = {"kind": "local",
                        "scope": ("publisher_https_source" if downloads else
                                  "user_uploaded_publisher_origin_unverified"),
                        "bundle_digest": digest, "receipt_name": receipt}
        elif dataset.startswith("msci-"):
            from .msci_regional_factsheets import (
                store_manual_factsheet, read_msci_regional_evidence, series_values)
            index = dataset[5:].upper()
            original = spec["roles"][0]["download_url"]
            digest, receipt = store_manual_factsheet(
                self.evidence, index, original, files["factsheet"],
                publisher_download=bool(downloads))
            evidence = {"kind": "local",
                        "scope": ("publisher_https_source" if downloads else
                                  "user_uploaded_publisher_origin_unverified"),
                        "bundle_digest": digest, "receipt_name": receipt}
            full = read_msci_regional_evidence(self.evidence)
            values = {sid: series_values(full, _definitions()[sid]["source_key"])
                      for sid in spec["series_ids"]}
        else:
            digest, receipt = _archive(self.evidence, dataset, files, spec["roles"],
                                       downloads=downloads or None)
            evidence = {"kind": "local",
                        "scope": ("publisher_https_source" if downloads else
                                  "user_uploaded_publisher_origin_unverified"),
                        "bundle_digest": digest, "receipt_name": receipt}
        provider = _PreparedManualProvider(values, evidence, _definitions())
        ingest = IngestionService(self.engine, provider)
        results = []
        for sid in sorted(spec["series_ids"]):
            try:
                result = ingest.refresh(sid, full=True)
                results.append({"id": sid, "status": "success",
                                "received": result["received"],
                                "versions_added": result["versions_added"],
                                "last_period": (max(values[sid]).isoformat()
                                                if values.get(sid) else None)})
            except Exception:
                results.append({"id": sid, "status": "failed",
                                "error_code": "manual_source_ingestion_failed"})
        state = "complete" if all(x["status"] == "success" for x in results) else "partial"
        with self.lock:
            job.update(sources=results, status=state, archive_sha256=digest,
                       origin_verified=bool(downloads),
                       finished_at=datetime.now(timezone.utc).isoformat(),
                       phase="finished")
            self._save()
        if any(item["status"] == "success" for item in results):
            self.accepted()
        if state == "complete":
            shutil.rmtree(folder, ignore_errors=True)

    def _run_icio(self, job: dict, folder: Path):
        """Download and import pinned 2025 OECD regular archives independently."""
        from .publisher_downloads import fetch_publisher_file, PublisherDownloadError
        from .source_policy_types import PolicyDeferred
        from .icio import PUBLISHER_ARCHIVES, README_SHA256, import_original_archive
        from .oecd_icio_access import PUBLISHER_URLS
        from .original_uploads import OriginalImportManager, README
        manager = OriginalImportManager(evidence=self.evidence)
        readme = manager.pinned_readme()
        if readme is None:
            readme = folder / README
            cached = job["downloaded"].get(README)
            if (not cached or not readme.is_file() or readme.is_symlink()
                    or sha256(readme.read_bytes()).hexdigest() != README_SHA256):
                detail = fetch_publisher_file(
                    {"download_url": PUBLISHER_URLS[README], "max_bytes": 10_000_000},
                    readme)
                if sha256(readme.read_bytes()).hexdigest() != README_SHA256:
                    raise ProviderError("OECD publisher ReadMe does not match pinned original")
                with self.lock:
                    job["downloaded"][README] = detail
                    self._save()
        completed = {entry["id"] for entry in job["sources"]}
        successes = sum(entry["status"] == "success" for entry in job["sources"])
        for filename, pin in PUBLISHER_ARCHIVES.items():
            if filename in completed:
                continue
            try:
                target = folder / filename
                prior = job["downloaded"].get(filename)
                if (not prior or not target.is_file() or target.is_symlink()
                        or sha256(target.read_bytes()).hexdigest() != pin["sha256"]):
                    detail = fetch_publisher_file(
                        {"download_url": PUBLISHER_URLS[filename],
                         "max_bytes": min(1_500_000_000, max(pin["bytes"] * 2, 200_000_000))},
                        target)
                    if detail["sha256"] != pin["sha256"] or detail["bytes"] != pin["bytes"]:
                        raise ProviderError("OECD archive differs from pinned 2025 edition")
                    with self.lock:
                        job["downloaded"][filename] = detail
                        self._save()
                with self.lock:
                    job["status"] = "running"
                    job["phase"] = "validating"
                    self._save()
                result = import_original_archive(target, self.evidence, readme)
                successes += 1
                row = {"id": filename, "status": "success",
                       "edition": result.get("edition"), "table": result.get("table")}
                target.unlink(missing_ok=True)
            except PolicyDeferred:
                raise  # Preserve the job; the worker retries at the ledger deadline.
            except Exception as exc:
                from .service import safe_source_failure_code
                row = {"id": filename, "status": "failed",
                       "error_code": (exc.code if isinstance(exc, PublisherDownloadError)
                                      else safe_source_failure_code(exc))}
            with self.lock:
                job["sources"].append(row)
                job["status"] = "downloading"
                job["phase"] = "downloading"
                self._save()
        with self.lock:
            job.update(status=("complete" if successes == len(PUBLISHER_ARCHIVES)
                               else "partial" if successes else "failed"),
                       phase="finished", origin_verified=bool(successes),
                       finished_at=datetime.now(timezone.utc).isoformat())
            self._save()
        if successes:
            self.accepted()
        if successes == len(PUBLISHER_ARCHIVES):
            shutil.rmtree(folder, ignore_errors=True)

    def commit_uploaded_file(self, dataset: str, role: str, original: str,
                             uploaded: Path, size: int, digest: str):
        """Commit a bounded streamed upload without blocking other queue work."""
        spec = source_specs().get(dataset)
        selected = next((r for r in (spec or {}).get("roles", []) if r["id"] == role), None)
        if not selected or not NAME.fullmatch(original) or not original.lower().endswith(
                selected["accept"]):
            raise ValueError("Uploaded filename or extension does not match the selected original")
        if not 0 < size <= selected["max_bytes"] or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Original file exceeds the permitted bound")
        folder = self.stage / dataset
        with self.lock:
            if (folder.is_symlink() or not folder.is_dir()
                    or uploaded.parent != folder or uploaded.is_symlink()
                    or not uploaded.is_file() or uploaded.stat().st_size != size):
                raise ValueError("Manual original staging identity invalid")
            destination = folder / (role + ".bin")
            if destination.is_symlink():
                raise ValueError("Manual upload destination is a symlink")
            os.replace(uploaded, destination)
            started = self._enqueue(dataset, "upload")
        return {"dataset": dataset, "role": role,
                "sha256": digest, "import_started": started is not None,
                "job_id": started}


def install_manual_sources(app: FastAPI, engine, *, stage=None, evidence=None, journal=None,
                           persistent: bool = True):
    accepted = app.state.acceptance.invalidate if persistent else (lambda: None)
    manager = ManualSourceManager(engine, stage=stage, evidence=evidence,
                                  journal=journal, accepted=accepted)

    @app.get("/api/manual-sources")
    def get_manual_sources():
        return manager.status()

    @app.post("/api/manual-sources/upload", status_code=201)
    async def upload_manual_source(request: Request, dataset: str, role: str,
                                   filename: str,
                                   x_gcm_action: str | None = Header(default=None)):
        _guard(request, x_gcm_action)
        spec = source_specs().get(dataset)
        selected = next((r for r in (spec or {}).get("roles", [])
                         if r["id"] == role), None)
        if selected is None:
            raise HTTPException(422, "Unknown manual source role")
        length = request.headers.get("content-length")
        if length is not None:
            try:
                size = int(length)
            except ValueError:
                raise HTTPException(422, "Invalid content length") from None
            if size > selected["max_bytes"]:
                raise HTTPException(413, "Original file too large")
        # Before reading an upload, reject incorrect file metadata. This does
        # not trust the filename as evidence of any publisher origin.
        if not NAME.fullmatch(filename) or not filename.lower().endswith(
                selected["accept"]):
            raise HTTPException(422, "Filename does not match the selected source format")
        folder = manager.stage / dataset
        folder.mkdir(parents=True, exist_ok=True)
        if folder.is_symlink():
            raise HTTPException(422, "Manual upload directory invalid")
        total = 0
        digest = sha256()
        staged = None
        try:
            with NamedTemporaryFile(dir=folder, prefix=".incoming-stream-",
                                    suffix=".part", delete=False) as out:
                staged = Path(out.name)
                os.chmod(staged, 0o600)
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > selected["max_bytes"]:
                        raise HTTPException(413, "Original file too large")
                    out.write(chunk)
                    digest.update(chunk)
                out.flush()
                os.fsync(out.fileno())
            if not total:
                raise HTTPException(422, "Empty original file")
            return manager.commit_uploaded_file(
                dataset, role, filename, staged, total, digest.hexdigest())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)

    @app.post("/api/manual-sources/import", status_code=202)
    def import_manual_source(request: Request, dataset: str,
                             x_gcm_action: str | None = Header(default=None)):
        _guard(request, x_gcm_action)
        try:
            return {"job_id": manager.start(dataset)}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/manual-sources/fetch", status_code=202)
    def fetch_manual_sources(request: Request, dataset: str | None = None,
                             x_gcm_action: str | None = Header(default=None)):
        """Fetch only fixed publisher URLs. No arbitrary URL can be supplied."""
        _guard(request, x_gcm_action)
        try:
            return manager.fetch(dataset)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    return manager
