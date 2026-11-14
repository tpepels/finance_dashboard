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

# Static, pinned originals should only be acquired once. Frequently revised
# public source files need fresh bytes even after a successful earlier import.
_REFRESH_SECONDS = {
    "gold-spot": 3600,
    "wid-world": 7 * 86400,
    "euklems-us": 30 * 86400,
    "msci-eafe": 7 * 86400,
    "msci-europe": 7 * 86400,
    "msci-japan": 7 * 86400,
}

def _recent_import(job: dict, dataset: str) -> bool:
    """Whether a successful import is still fresh for global collection."""
    if job.get("status") != "complete":
        return False
    interval = _REFRESH_SECONDS.get(dataset)
    if interval is None:
        return True
    stamp = job.get("finished_at") or job.get("created_at")
    try:
        imported = datetime.fromisoformat(stamp).timestamp()
    except (ValueError, TypeError):
        return False
    return time.time() - imported < interval

_AGENT_DOWNLOAD_ERRORS = {
    "publisher_url_invalid", "publisher_file_too_large",
    "publisher_http_404", "publisher_http_410",
    "oecd_readme_identity_mismatch", "oecd_archive_identity_mismatch",
}

def _retry_transient_publisher_http(job: dict, role: str, code: str) -> int | None:
    """Retry temporary publisher failures twice before manual intervention.

    The managed transport enforces publisher-specific cooldowns, including
    longer Retry-After values; this bounded retry adds network resilience.
    """
    if code not in {"publisher_http_408", "publisher_http_425",
                    "publisher_http_429", "publisher_http_500",
                    "publisher_http_502", "publisher_http_503",
                    "publisher_http_504", "publisher_timeout",
                    "publisher_network_error"}:
        return None
    previous = sum(attempt.get("role") == role and attempt.get("outcome") == code
                   for attempt in job.get("attempts", []))
    return 60 * (2 ** previous) if previous < 2 else None

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
        "manual_files": [
            {"id": filename, "label": filename, "download_url": url,
             "accept": Path(filename).suffix,
             "max_bytes": 10_000_000 if filename.endswith(".xlsx") else
                          2_000_000_000}
            for filename, url in PUBLISHER_URLS.items()
            if filename.endswith((".xlsx", ".zip"))
        ],
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
    download_keys = set(downloads or ())
    source_roles = {role["id"] for role in roles}
    if not download_keys <= source_roles:
        raise ProviderError("Unknown publisher acquisition role")
    fully_publisher = bool(download_keys) and download_keys == source_roles
    mixed = bool(download_keys) and not fully_publisher
    origin = ("mixed_upload_and_publisher_https" if mixed else
              "publisher_https" if fully_publisher else "user_upload")
    fingerprint = sha256(json.dumps(
        {"hashes": hashes, "mode": origin} if download_keys else hashes,
        sort_keys=True).encode()).hexdigest()
    parent = root / "manual-sources" / dataset
    folder = parent / fingerprint
    manifest = {"schema_version": 1,
                "kind": ("mixed_original" if mixed else
                         "publisher_fetched_original" if fully_publisher else
                         "owner_uploaded_original"),
                "source_identity": {"dataset": dataset, "acquisition": origin},
                "files": hashes,
                "source_urls": {role["id"]: role["download_url"] for role in roles},
                "publisher_origin_verified": fully_publisher,
                "first_publication_verified": False}
    if mixed:
        manifest["role_acquisitions"] = {
            role: ("publisher_https" if role in download_keys else "user_upload")
            for role in sorted(source_roles)}
    if downloads:
        if any(downloads[key]["sha256"] != hashes[key] for key in download_keys):
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
            acquisition={"mode": ("mixed_verified_and_uploaded" if mixed else
                                   "publisher_https_verified_endpoint" if fully_publisher else
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
        self.browser_profiles: dict[str, dict] = {}
        try:
            saved = json.loads(self.journal.read_text())
            for job in saved.get("jobs", []):
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
            # Migrate complete role pairs staged by earlier releases. No click
            # is needed after a container upgrade or unexpected restart.
            for dataset, spec in source_specs().items():
                if spec["roles"] and len(self._staged(dataset, spec["roles"])) == len(spec["roles"]):
                    self._enqueue(dataset, "upload")
            if any(job["status"] in ("queued", "deferred") for job in self.jobs):
                self._ensure_worker()

    @staticmethod
    def _retained_jobs(jobs: list[dict]) -> list[dict]:
        """Bound completed history while never evicting an unfinished recovery.

        Keeping only the last N raw jobs used to make older manual-required
        uploads disappear from the API and permanently lose their job identity
        on restart after enough later completions.
        """
        retained = []
        completed = 0
        # Retain one successful acquisition per source beyond the history
        # window. Otherwise a restart forgets an old pinned OECD import and
        # may download the entire edition again.
        last_success = {}
        for job in jobs:
            if job.get("status") == "complete":
                last_success[job["dataset"]] = job["id"]
        for job in reversed(jobs):
            if job.get("status") == "complete":
                if completed >= 80 and last_success.get(job["dataset"]) != job["id"]:
                    continue
                completed += 1
            # Errors and incomplete imports remain visible until resolved.
            retained.append(job)
        return list(reversed(retained))

    def _save(self):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8",
                                    prefix=".manual-jobs-", dir=self.journal.parent,
                                    delete=False) as out:
                temporary = Path(out.name)
                json.dump({"version": 2, "jobs": self._retained_jobs(self.jobs)}, out)
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

    @staticmethod
    def _public_job(job: dict) -> dict:
        """Never expose redirect query tokens, cookies or client fingerprints."""
        from urllib.parse import urlsplit
        row = dict(job)
        row["downloaded"] = {}
        for role, record in job.get("downloaded", {}).items():
            parsed = urlsplit(record.get("final_url", ""))
            row["downloaded"][role] = {
                key: record.get(key) for key in (
                    "sha256", "bytes", "content_type", "retrieved_at_utc")}
            row["downloaded"][role]["final_host"] = parsed.hostname
        return row

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
                "jobs": [self._public_job(job)
                         for job in reversed(self._retained_jobs(self.jobs))],
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
        jobs_root = spool.parent
        jobs_root.mkdir(parents=True, exist_ok=True)
        if jobs_root.is_symlink():
            raise ValueError("Original job spool must not be a symlink")
        spool.mkdir(mode=0o700, exist_ok=False)
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
                   "downloaded": {}, "failed_roles": {}, "manual_supplied": [],
                   "attempts": [], "phase": "waiting"}
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

    def fetch(self, dataset: str | None = None, browser: dict | None = None):
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
                latest = next((job for job in reversed(self.jobs)
                               if job["dataset"] == name), None)
                # Keep the existing partial spool and stable manual links. A
                # second click must not hide an outstanding human upload.
                if dataset is None and latest and latest["status"] == "manual_required":
                    skipped[name] = "manual_upload_pending"
                    continue
                if dataset is None and latest and _recent_import(latest, name):
                    skipped[name] = "already_current_or_pinned"
                    continue
                token = self._enqueue(name, "publisher")
                if token is not None:
                    if browser and token not in self.browser_profiles:
                        from .publisher_downloads import safe_browser_profile
                        self.browser_profiles[token] = safe_browser_profile(browser)
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
                    job.setdefault("attempts", []).append({
                        "role": job.get("current_role"), "outcome": "policy_deferred",
                        "reason": exc.reason, "retry_at_unix": job["retry_at_unix"],
                        "at_utc": datetime.now(timezone.utc).isoformat(),
                    })
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
        if (folder.parent.is_symlink() or folder.is_symlink() or
                not folder.is_dir()):
            raise ProviderError("Original import spool identity invalid")
        if dataset == "oecd-icio":
            self._run_icio(job, folder)
            return
        from .publisher_downloads import PublisherDownloadError
        from .source_policy_types import PolicyDeferred
        downloads = dict(job.get("downloaded") or {}) if method in ("publisher", "hybrid") else {}
        if method == "publisher":
            from .source_policy import managed_client
            from .publisher_downloads import browser_headers
            import httpx
            failed = {}
            profile = self.browser_profiles.get(job["id"])
            with managed_client(
                    headers=browser_headers(profile, spec["roles"][0]["download_url"]),
                    timeout=httpx.Timeout(connect=15, read=90, write=20, pool=15),
                    follow_redirects=False) as network:
                for role in spec["roles"]:
                    role_id = role["id"]
                    path = folder / (role_id + ".bin")
                    recorded = downloads.get(role_id)
                    if (recorded and path.is_file() and not path.is_symlink()
                            and 0 < path.stat().st_size <= role["max_bytes"]
                            and sha256(path.read_bytes()).hexdigest() == recorded.get("sha256")):
                        continue
                    downloads.pop(role_id, None)
                    with self.lock:
                        job["current_role"] = role_id
                        self._save()
                    retry_delay = None
                    try:
                        detail = fetch_publisher_file(
                            role, path, client=network, browser=profile)
                        downloads[role_id] = detail
                        result_code = "downloaded"
                    except PublisherDownloadError as exc:
                        retry_delay = _retry_transient_publisher_http(
                            job, role_id, exc.code)
                        if retry_delay is None:
                            failed[role_id] = exc.code
                        result_code = exc.code
                    with self.lock:
                        job["downloaded"] = dict(downloads)
                        job["failed_roles"] = dict(failed)
                        job.setdefault("attempts", []).append({
                            "role": role_id, "outcome": result_code,
                            "at_utc": datetime.now(timezone.utc).isoformat(),
                            "browser_hints_used": bool(profile),
                        })
                        job["current_role"] = None
                        self._save()
                    if retry_delay is not None:
                        raise PolicyDeferred("publisher-http", result_code,
                                             time.time() + retry_delay)
            if failed:
                agent_codes = sorted(set(failed.values()) & _AGENT_DOWNLOAD_ERRORS)
                with self.lock:
                    job["status"] = "failed" if agent_codes else "manual_required"
                    job["phase"] = ("source_contract_failed" if agent_codes
                                    else "waiting_for_manual_files")
                    job["error_code"] = (agent_codes[0] if agent_codes
                                         else "publisher_files_unavailable")
                    job["finished_at"] = datetime.now(timezone.utc).isoformat()
                    self._save()
                return
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
        try:
            values = _parse_source(dataset, files)
        except Exception:
            # An automatically received file that fails economic parsing is an
            # agent/source-contract problem. Downloading the same bytes by
            # hand cannot fix it. An invalid user replacement can be retried.
            if job.get("manual_supplied"):
                with self.lock:
                    job["failed_roles"] = {
                        role: "manual_original_validation_failed"
                        for role in job["manual_supplied"]}
                    job["status"] = "manual_required"
                    job["phase"] = "waiting_for_valid_originals"
                    job["error_code"] = "manual_original_invalid"
                    job["finished_at"] = datetime.now(timezone.utc).isoformat()
                    self._save()
                return
            raise
        verified_download = bool(downloads) and len(downloads) == len(spec["roles"])
        provenance_scope = ("publisher_https_source" if verified_download else
                            "mixed_user_upload_and_publisher_https" if downloads else
                            "user_uploaded_publisher_origin_unverified")
        if dataset == "msci-methodology":
            from .msci_regional_factsheets import store_manual_methodology
            digest, receipt = store_manual_methodology(
                self.evidence, files["methodology"], publisher_download=verified_download)
            evidence = {"kind": "local",
                        "scope": provenance_scope,
                        "bundle_digest": digest, "receipt_name": receipt}
        elif dataset.startswith("msci-"):
            from .msci_regional_factsheets import (
                store_manual_factsheet, read_msci_regional_evidence, series_values)
            index = dataset[5:].upper()
            original = spec["roles"][0]["download_url"]
            digest, receipt = store_manual_factsheet(
                self.evidence, index, original, files["factsheet"],
                publisher_download=verified_download)
            evidence = {"kind": "local",
                        "scope": provenance_scope,
                        "bundle_digest": digest, "receipt_name": receipt}
            full = read_msci_regional_evidence(self.evidence)
            values = {sid: series_values(full, _definitions()[sid]["source_key"])
                      for sid in spec["series_ids"]}
        else:
            digest, receipt = _archive(self.evidence, dataset, files, spec["roles"],
                                       downloads=downloads or None)
            evidence = {"kind": "local",
                        "scope": provenance_scope,
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
                       origin_verified=verified_download,
                       finished_at=datetime.now(timezone.utc).isoformat(),
                       phase="finished")
            self._save()
        if any(item["status"] == "success" for item in results):
            self.accepted()
        if state == "complete":
            shutil.rmtree(folder, ignore_errors=True)

    def _run_icio(self, job: dict, folder: Path):
        """Try every registered OECD original; report only files needing a human."""
        from .publisher_downloads import fetch_publisher_file, PublisherDownloadError
        from .source_policy_types import PolicyDeferred
        from .icio import PUBLISHER_ARCHIVES, README_SHA256, import_original_archive
        from .oecd_icio_access import PUBLISHER_URLS
        from .original_uploads import OriginalImportManager, README
        from .source_policy import managed_client
        from .publisher_downloads import browser_headers
        import httpx
        profile = self.browser_profiles.get(job["id"])
        with managed_client(
                headers=browser_headers(profile, PUBLISHER_URLS[README]),
                timeout=httpx.Timeout(connect=15, read=90, write=20, pool=15),
                follow_redirects=False) as network:
            manager = OriginalImportManager(evidence=self.evidence)
            readme = manager.pinned_readme()
            failures = dict(job.get("failed_roles") or {})
            if readme is None:
                readme = folder / README
                cached = job["downloaded"].get(README)
                supplied = README in job.get("manual_supplied", [])
                if not ((cached or supplied) and readme.is_file()
                        and not readme.is_symlink()
                        and sha256(readme.read_bytes()).hexdigest() == README_SHA256):
                    try:
                        detail = fetch_publisher_file(
                            {"download_url": PUBLISHER_URLS[README], "max_bytes": 10_000_000},
                            readme, client=network, browser=profile)
                        if sha256(readme.read_bytes()).hexdigest() != README_SHA256:
                            raise PublisherDownloadError("oecd_readme_identity_mismatch")
                        with self.lock:
                            job["downloaded"][README] = detail
                            failures.pop(README, None)
                            job["failed_roles"] = dict(failures)
                            job.setdefault("attempts", []).append({
                                "role": README, "outcome": "downloaded",
                                "at_utc": datetime.now(timezone.utc).isoformat()})
                            self._save()
                    except PublisherDownloadError as exc:
                        retry_delay = _retry_transient_publisher_http(
                            job, README, exc.code)
                        if retry_delay is None:
                            failures[README] = exc.code
                        readme = None
                        with self.lock:
                            job["failed_roles"] = dict(failures)
                            job.setdefault("attempts", []).append({
                                "role": README, "outcome": exc.code,
                                "at_utc": datetime.now(timezone.utc).isoformat()})
                            self._save()
                        if retry_delay is not None:
                            raise PolicyDeferred("publisher-http", exc.code,
                                                 time.time() + retry_delay)
            completed = {entry["id"] for entry in job["sources"] if entry["status"] == "success"}
            failures = {k: v for k, v in failures.items()
                        if k not in completed and k not in job.get("manual_supplied", [])}
            for filename, pin in PUBLISHER_ARCHIVES.items():
                if filename in completed:
                    continue
                try:
                    target = folder / filename
                    prior = job["downloaded"].get(filename)
                    supplied = filename in job.get("manual_supplied", [])
                    if not ((prior or supplied) and target.is_file()
                            and not target.is_symlink()
                            and target.stat().st_size == pin["bytes"]
                            and sha256(target.read_bytes()).hexdigest() == pin["sha256"]):
                        detail = fetch_publisher_file(
                            {"download_url": PUBLISHER_URLS[filename],
                             "max_bytes": min(1_500_000_000, max(pin["bytes"] * 2, 200_000_000))},
                            target, client=network, browser=profile)
                        if detail["sha256"] != pin["sha256"] or detail["bytes"] != pin["bytes"]:
                            raise PublisherDownloadError("oecd_archive_identity_mismatch")
                        with self.lock:
                            job["downloaded"][filename] = detail
                            failures.pop(filename, None)
                            job["failed_roles"] = dict(failures)
                            job.setdefault("attempts", []).append({
                                "role": filename, "outcome": "downloaded",
                                "at_utc": datetime.now(timezone.utc).isoformat()})
                            self._save()
                    if readme is None:
                        # ZIP is already available. Only the missing ReadMe must
                        # be uploaded; do not fetch this archive a second time.
                        continue
                    with self.lock:
                        job["status"] = "running"
                        job["phase"] = "validating"
                        self._save()
                    result = import_original_archive(
                        target, self.evidence, readme,
                        publisher_download=filename not in job.get("manual_supplied", []))
                    row = {"id": filename, "status": "success",
                           "edition": result.get("edition"), "table": result.get("table")}
                    target.unlink(missing_ok=True)
                    with self.lock:
                        job["sources"] = [s for s in job["sources"] if s["id"] != filename] + [row]
                        failures.pop(filename, None)
                        self._save()
                except PolicyDeferred:
                    raise
                except PublisherDownloadError as exc:
                    retry_delay = _retry_transient_publisher_http(
                        job, filename, exc.code)
                    if retry_delay is None:
                        failures[filename] = exc.code
                    with self.lock:
                        job["failed_roles"] = dict(failures)
                        job.setdefault("attempts", []).append({
                            "role": filename, "outcome": exc.code,
                            "at_utc": datetime.now(timezone.utc).isoformat()})
                        self._save()
                    if retry_delay is not None:
                        raise PolicyDeferred("publisher-http", exc.code,
                                             time.time() + retry_delay)
                except Exception as exc:
                    from .service import safe_source_failure_code
                    row = {"id": filename, "status": "failed",
                           "error_code": safe_source_failure_code(exc)}
                    with self.lock:
                        job["sources"] = [s for s in job["sources"] if s["id"] != filename] + [row]
                        self._save()
                finally:
                    with self.lock:
                        job["status"] = "downloading"
                        job["phase"] = "downloading"
                        self._save()
            succeeded = sum(s["status"] == "success" for s in job["sources"])
            total = len(PUBLISHER_ARCHIVES)
            agent_codes = sorted(set(failures.values()) & _AGENT_DOWNLOAD_ERRORS)
            with self.lock:
                job["failed_roles"] = dict(failures)
                job.update(
                    status=("partial" if succeeded else "failed") if agent_codes else
                           ("manual_required" if failures else
                            "complete" if succeeded == total else
                            "partial" if succeeded else "failed"),
                    phase=("source_contract_failed" if agent_codes else
                           "waiting_for_manual_files" if failures else "finished"),
                    error_code=(agent_codes[0] if agent_codes else
                                "publisher_files_unavailable" if failures else None),
                    origin_verified=(succeeded == total and not job.get("manual_supplied")
                                     and README in job["downloaded"]),
                    finished_at=datetime.now(timezone.utc).isoformat())
                self._save()
            if succeeded:
                self.accepted()
            if succeeded == total:
                shutil.rmtree(folder, ignore_errors=True)

    def commit_fallback_file(self, job_id: str, role_id: str, original: str,
                             uploaded: Path, size: int, digest: str):
        """Supply one failed publisher role; enqueue automatically when complete."""
        with self.lock:
            job = next((item for item in self.jobs if item["id"] == job_id), None)
            if job is None or job["status"] != "manual_required":
                raise ValueError("No manual file is needed for this job")
            spec = source_specs()[job["dataset"]]
            role = next((item for item in spec["roles"] if item["id"] == role_id), None)
            if job["dataset"] == "oecd-icio":
                from .icio import PUBLISHER_ARCHIVES, README_SHA256
                from .original_uploads import README
                if role_id == README:
                    expected_hash, expected_size = README_SHA256, 10_000_000
                else:
                    pin = PUBLISHER_ARCHIVES.get(role_id)
                    expected_hash = pin["sha256"] if pin else ""
                    expected_size = pin["bytes"] if pin else 0
                role = {"id": role_id, "accept": Path(role_id).suffix,
                        "max_bytes": expected_size}
                if original != role_id or digest != expected_hash or (
                        role_id != README and size != expected_size):
                    raise ValueError("OECD original does not match pinned archive identity")
            if (role is None or role_id not in job["failed_roles"]
                    or not NAME.fullmatch(original)
                    or not original.lower().endswith(role["accept"])
                    or not 0 < size <= role["max_bytes"]
                    or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                raise ValueError("Manual fallback file identity invalid")
            folder = self._job_dir(job_id)
            if (folder.parent.is_symlink() or folder.is_symlink() or
                    uploaded.parent != folder or uploaded.is_symlink()
                    or not uploaded.is_file() or uploaded.stat().st_size != size):
                raise ValueError("Manual fallback staging invalid")
            # OECD's canonical importer reads original filenames directly;
            # other source parsers read role-named binary staging files.
            destination = folder / (role_id if job["dataset"] == "oecd-icio"
                                    else role_id + ".bin")
            if destination.is_symlink():
                raise ValueError("Manual fallback destination invalid")
            os.replace(uploaded, destination)
            job["downloaded"].pop(role_id, None)
            job["failed_roles"].pop(role_id, None)
            if role_id not in job["manual_supplied"]:
                job["manual_supplied"].append(role_id)
            queued = not job["failed_roles"]
            if queued:
                job["method"] = "hybrid" if job["downloaded"] else "upload"
                job.update(status="queued", phase="waiting", finished_at=None, error_code=None)
            self._save()
            if queued:
                self._ensure_worker()
            return {"job_id": job_id, "role": role_id, "import_started": queued,
                    "remaining": sorted(job["failed_roles"])}

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

    @app.post("/api/manual-sources/fallback-upload", status_code=201)
    async def upload_failed_original(request: Request, job_id: str, role: str,
                                     filename: str,
                                     x_gcm_action: str | None = Header(default=None)):
        _guard(request, x_gcm_action)
        with manager.lock:
            job = next((item for item in manager.jobs if item["id"] == job_id), None)
            spec = source_specs().get(job["dataset"]) if job else None
            selected = next((r for r in (spec or {}).get("roles", [])
                             if r["id"] == role), None)
            if job and job["dataset"] == "oecd-icio":
                from .icio import PUBLISHER_ARCHIVES
                from .original_uploads import README
                if role == README:
                    selected = {"accept": ".xlsx", "max_bytes": 10_000_000}
                elif role in PUBLISHER_ARCHIVES:
                    selected = {"accept": ".zip", "max_bytes": PUBLISHER_ARCHIVES[role]["bytes"]}
        if (selected is None or job is None or job["status"] != "manual_required"
                or role not in job["failed_roles"] or
                not NAME.fullmatch(filename) or not filename.lower().endswith(selected["accept"])):
            raise HTTPException(422, "No matching failed publisher file")
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > selected["max_bytes"]:
                    raise HTTPException(413, "Original file too large")
            except ValueError:
                raise HTTPException(422, "Invalid content length") from None
        folder = manager._job_dir(job_id)
        if folder.is_symlink() or not folder.is_dir():
            raise HTTPException(422, "Manual fallback storage missing")
        staged = None
        total, digest = 0, sha256()
        try:
            with NamedTemporaryFile(dir=folder, prefix=".fallback-", suffix=".part",
                                    delete=False) as out:
                staged = Path(out.name)
                os.chmod(staged, 0o600)
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > selected["max_bytes"]:
                        raise HTTPException(413, "Original file too large")
                    digest.update(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            if total == 0:
                raise HTTPException(422, "Original file is empty")
            return manager.commit_fallback_file(job_id, role, filename, staged, total,
                                                digest.hexdigest())
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
