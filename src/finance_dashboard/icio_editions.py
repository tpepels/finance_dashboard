"""Additional OECD ICIO edition archive intake through the canonical ICIO evidence store.

Older and extended layouts have different industry/account definitions from the
2025 regular tables. Retain their ORIGINAL bytes and member inventories with
immutable receipts; do not promote them to validated matrices or derive TiVA
values without an edition-specific dimensional/accounting contract.
"""
from __future__ import annotations

from hashlib import sha256
from functools import lru_cache
import json
from pathlib import Path, PurePosixPath
import re
import stat
from zipfile import ZipFile, BadZipFile

MAX_ARCHIVE_BYTES = 2 * 1024 ** 3
MAX_MEMBERS = 20000
MAX_UNCOMPRESSED = 25 * 1024 ** 3


def archive_identity(filename: str) -> dict:
    if re.fullmatch(r"(?:1995-2000|2001-2005|2006-2010|2011-2015|2016-2022)_EXT(?: \([0-9]+\))?\.zip", filename):
        return {"edition": "2025", "table": "extended"}
    # The 2016-2020 files are from OECD's 2023 release, not the 2025
    # January-2026 edition. Keep the two populations and sectors distinct.
    if re.fullmatch(r"2016-2020_EXT(?: \([0-9]+\))?\.zip", filename):
        return {"edition": "2023", "table": "extended"}
    if re.fullmatch(r"2016-2020_SML\.zip", filename):
        return {"edition": "2023", "table": "regular"}
    if re.fullmatch(r"ICIO2018_[A-Za-z0-9_-]+\.zip", filename):
        return {"edition": "2018", "table": "edition_specific_unresolved"}
    if re.fullmatch(r"ICIO2021[A-Za-z0-9_-]+\.zip", filename):
        return {"edition": "2021", "table": "edition_specific_unresolved"}
    raise ValueError("icio_archive_edition_not_registered")


def _effective_archive_identity(filename: str, recorded: dict, probe: dict) -> dict:
    """Choose a processing identity without altering the sealed original.

    The 1995-2015 EXT archive names occur in BOTH 2023 and 2025.
    All other recognised basename patterns specify their own edition.
    Header classification must be unique, internally consistent, and have
    the published dimensions and industry vocabulary.
    """
    expected = archive_identity(filename)
    ambiguous = bool(re.fullmatch(
        r"(?:1995-2000|2001-2005|2006-2010|2011-2015)_EXT(?: \([0-9]+\))?\.zip",
        filename))
    candidate = probe.get("candidate") if probe.get("status") == "recognized" else None
    if candidate and (ambiguous or candidate == expected or
                      (candidate["edition"] == expected["edition"] and
                       expected["table"] == "edition_specific_unresolved")):
        effective = candidate
        status = "source_structure_confirmed"
    else:
        effective = expected
        status = ("source_schema_conflicts_filename" if candidate else
                  "source_schema_unresolved" if probe.get("headers") else
                  "no_matrix_schema_available")
    return {"edition": effective["edition"], "table": effective["table"],
            "sealed_edition": recorded.get("edition"),
            "sealed_table": recorded.get("table"),
            "status": status,
            "candidate": candidate,
            "source_structure_reclassified": bool(candidate and
                (effective["edition"] != recorded.get("edition") or
                 effective["table"] != recorded.get("table")))}


def inspect_archive(path: Path) -> dict:
    identity = archive_identity(path.name)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_ARCHIVE_BYTES:
        raise ValueError("icio_archive_size_or_type_invalid")
    members = []
    total = 0
    try:
        with ZipFile(path) as z:
            infos = z.infolist()
            if not infos or len(infos) > MAX_MEMBERS:
                raise ValueError("icio_archive_member_count_invalid")
            seen = set()
            for member in infos:
                name = member.filename
                parts = PurePosixPath(name)
                if (not name or len(name) > 512 or name.startswith("/")
                        or "\\" in name or ".." in parts.parts or "." in parts.parts
                        or name in seen or parts.is_absolute()
                        or stat.S_ISLNK(member.external_attr >> 16)
                        or member.flag_bits & 1):
                    raise ValueError("icio_archive_member_path_invalid")
                seen.add(name)
                if member.is_dir():
                    continue
                total += member.file_size
                if total > MAX_UNCOMPRESSED:
                    raise ValueError("icio_archive_uncompressed_limit_exceeded")
                members.append({"name": name, "bytes": member.file_size,
                                "crc32": format(member.CRC, "08x")})
            if not members:
                raise ValueError("icio_archive_without_members")
            if z.testzip() is not None:
                raise ValueError("icio_archive_crc_mismatch")
    except (BadZipFile, EOFError, OSError) as exc:
        raise ValueError("icio_archive_unreadable") from exc
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    from .icio_native import audit_archive_native
    # Validate every available annual member within this edition. Supplemental
    # econA/Rdata packages remain distinct source evidence, not matrix claims.
    from .icio_schema import probe_archive_layout
    with ZipFile(path) as z:
        probe = probe_archive_layout(z)
        reconciliation = _effective_archive_identity(path.name, identity, probe)
        identity = {"edition": reconciliation["edition"], "table": reconciliation["table"]}
        native = audit_archive_native(z, identity["edition"], table=identity["table"],
                                      original_filename=path.name)
        native["source_identity_reconciliation"] = reconciliation
        if native["annual_matrix_count"] or native["rejected_matrices"]:
            auxiliary = {"status": "no_auxiliary_parse_needed", "numeric_reports": []}
        else:
            from .icio_auxiliary import inspect_auxiliary_zip
            auxiliary = inspect_auxiliary_zip(z, staging_parent=path.parent)
    return {**identity, **native, "auxiliary_numeric": auxiliary,
            "filename": path.name, "archive_sha256": digest.hexdigest(),
            "archive_bytes": path.stat().st_size, "members": members,
            "member_count": len(members), "uncompressed_bytes": total,
            "status": (native["native_validation_status"]
                       if native["annual_matrix_count"] or native["rejected_matrices"] else
                       auxiliary["status"] if auxiliary["status"] != "no_rdata_members" else
                       "original_archived_dimensions_unverified"),
            "source_authenticity_verified": False,
            "industry_accounts_validated": native["native_validation_status"] == "native_accounts_verified",
            "tiva_comparability_certified": False,
            "scientific_analysis_certified": False,
            "first_publication_verified": False}


def register_edition_archive(path: Path, root: Path) -> dict:
    from .icio import _store_original_bundle, _verified_manifest
    from .source_capture import canonical_bytes
    path = Path(path)
    record = inspect_archive(path)
    # Duplicate downloads (for example "(1)" copies) must not occupy another
    # immutable archive slot. Reuse verified evidence with identical bytes.
    for existing in read_edition_archives(root, archive_sha=record["archive_sha256"]):
        if (existing["archive_sha256"] == record["archive_sha256"] and
                existing["edition"] == record["edition"] and
                existing["table"] == record["table"]):
            return {**existing, "filename": path.name, "status": "already_registered",
                    "duplicate_of": existing["filename"]}
    identity = {"publisher": "OECD", "edition": record["edition"],
                "table": record["table"], "filename": path.name,
                "acquisition": "owner_supplied_unverified_original"}
    source = {"owner_supplied_archive": path.name}
    parent = (Path(root) / "icio" / "other-editions" /
              (re.sub(r"[^A-Za-z0-9_.-]", "_", path.name) + "-" + record["archive_sha256"][:16]))
    def verify(bundle):
        manifest = _verified_manifest(bundle, identity,
                    {"archive.zip", "audit.json"}, source, record["archive_sha256"])
        stored = json.loads((bundle / "audit.json").read_text())
        if stored != record or manifest["files"]["archive.zip"] != record["archive_sha256"]:
            raise ValueError("icio_edition_archive_changed")
        return stored
    bundle = _store_original_bundle(parent, {"archive.zip": path}, record,
                                     identity, source, verify)
    return {"status": record["status"], "edition": record["edition"],
            "table": record["table"], "filename": path.name,
            "member_count": record["member_count"],
            "archive_sha256": record["archive_sha256"], "bundle_digest": bundle.name}


DERIVED_METHOD = "native_leontief_rdata_v4"


def _derived_folder(root: Path, original_sha: str, method: str = DERIVED_METHOD) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", original_sha):
        raise ValueError("icio_derived_source_hash_invalid")
    if method not in {"native_leontief_rdata_v3", DERIVED_METHOD}:
        raise ValueError("icio_derived_method_invalid")
    return Path(root) / "icio" / "native-method-reports" / original_sha / method


def _read_native_derived(root: Path, original_sha: str, *,
                         allow_legacy: bool = True) -> dict | None:
    from .source_capture import canonical_bytes
    method = DERIVED_METHOD
    folder = _derived_folder(root, original_sha)
    if not folder.is_dir() and allow_legacy:
        # Existing reports remain usable until each sealed archive is reassessed.
        method = "native_leontief_rdata_v3"
        folder = _derived_folder(root, original_sha, method)
    if not folder.is_dir():
        return None
    results = []
    for file in sorted(folder.iterdir()):
        if (file.is_symlink() or not file.is_file() or
                not re.fullmatch(r"[0-9a-f]{64}\.json", file.name)):
            raise ValueError("icio_derived_evidence_structure_invalid")
        body = file.read_bytes()
        if sha256(body).hexdigest() != file.stem:
            raise ValueError("icio_derived_evidence_hash_changed")
        result = json.loads(body)
        if (result.get("schema_version") != 1 or
                result.get("source_archive_sha256") != original_sha or
                result.get("method") != method or
                not isinstance(result.get("native"), dict) or
                canonical_bytes(result) != body):
            raise ValueError("icio_derived_evidence_identity_mismatch")
        results.append(result)
    if len(results) > 1:
        # Two different values from the same original + same method could
        # indicate a nondeterministic parser or altered code. Do not choose
        # the more flattering result.
        raise ValueError("icio_derived_conflicting_method_versions")
    return results[0] if results else None


def _store_native_derived(root: Path, original_sha: str, native: dict,
                          auxiliary: dict) -> dict:
    from .source_capture import canonical_bytes
    record = {"schema_version": 1, "source_archive_sha256": original_sha,
              "method": DERIVED_METHOD, "native": native, "auxiliary": auxiliary}
    body = canonical_bytes(record)
    digest = sha256(body).hexdigest()
    folder = _derived_folder(root, original_sha)
    folder.mkdir(parents=True, exist_ok=True)
    previous = _read_native_derived(root, original_sha, allow_legacy=False)
    if previous is not None:
        if previous != record:
            raise ValueError("icio_derived_method_result_conflict")
        return previous
    import os
    import tempfile
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".derived-",
                                         delete=False) as out:
            temporary = Path(out.name)
            out.write(body)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temporary, 0o600)
        os.link(temporary, folder / (digest + ".json"))
    except FileExistsError:
        if _read_native_derived(root, original_sha, allow_legacy=False) != record:
            raise ValueError("icio_derived_method_result_conflict") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return record


def reassess_registered_archive(root: Path, archive_sha: str) -> dict:
    """Upgrade an existing sealed original without altering its manifest.

    The derived scientific report is an immutable, content-addressed adjunct
    within the same canonical ICIO source-evidence tree. Source bytes,
    acquisition receipt, original audit and any reported failures remain
    unchanged; every reader verifies the source original before this adjunct.
    """
    from .icio_native import audit_archive_native
    from .icio_auxiliary import inspect_auxiliary_zip
    base = Path(root) / "icio" / "other-editions"
    if not base.is_dir():
        raise ValueError("icio_no_existing_archives")
    for parent in sorted(base.iterdir()):
        if not parent.is_dir() or parent.is_symlink() or not parent.name.endswith("-" + archive_sha[:16]):
            continue
        for bundle in sorted(parent.iterdir()):
            if not bundle.is_dir() or bundle.is_symlink() or not re.fullmatch(r"[0-9a-f]{64}", bundle.name):
                continue
            record = json.loads((bundle / "audit.json").read_bytes())
            if record["archive_sha256"] != archive_sha:
                continue
            _verify_edition_bundle(bundle, record)
            from .icio_schema import probe_archive_layout
            with ZipFile(bundle / "archive.zip") as z:
                if z.testzip() is not None:
                    raise ValueError("icio_derived_original_crc_invalid")
                probe = probe_archive_layout(z)
                reconciliation = _effective_archive_identity(record["filename"], record, probe)
                native = audit_archive_native(z, reconciliation["edition"],
                    table=reconciliation["table"], original_filename=record["filename"])
                native["source_identity_reconciliation"] = reconciliation
                auxiliary = (inspect_auxiliary_zip(z, staging_parent=base)
                             if not native["annual_matrix_count"] and
                             not native["rejected_matrices"] else
                             {"status": "no_auxiliary_parse_needed", "numeric_reports": []})
            _store_native_derived(root, archive_sha, native, auxiliary)
            return {"status": "reassessed_verified_original", "archive_sha256": archive_sha,
                    "filename": record["filename"], "edition": native["edition"],
                    "source_identity_reconciliation": reconciliation,
                    "annual_matrix_count": native["annual_matrix_count"],
                    "rejected_year_count": len(native["rejected_matrices"]),
                    "native_validation_status": native["native_validation_status"],
                    "header_schema_status": native["header_schema"]["status"],
                    "auxiliary_status": auxiliary["status"]}
    raise ValueError("icio_existing_archive_sha_not_found")


@lru_cache(maxsize=256)
def _cached_file_hash(filename: str, size: int, modified_ns: int) -> str:
    """Hash each unchanged immutable archive once per process, not once per visitor."""
    digest = sha256()
    with open(filename, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_edition_bundle(bundle: Path, record: dict) -> None:
    from .source_capture import canonical_bytes
    identity = {"publisher": "OECD", "edition": record["edition"],
                "table": record["table"], "filename": record["filename"],
                "acquisition": "owner_supplied_unverified_original"}
    manifest = json.loads((bundle / "manifest.json").read_text())
    files = manifest.get("files")
    if (manifest.get("schema_version") != 1 or
            manifest.get("source_identity") != identity or
            manifest.get("sources") != {"owner_supplied_archive": record["filename"]} or
            manifest.get("matrix_sha256") != record["archive_sha256"] or
            not isinstance(files, dict) or set(files) != {"archive.zip", "audit.json"} or
            sha256(canonical_bytes(files)).hexdigest() != bundle.name):
        raise ValueError("icio_edition_archive_identity_invalid")
    for name, digest in files.items():
        target = bundle / name
        if target.is_symlink() or not target.is_file():
            raise ValueError("icio_edition_archive_missing_member")
        if name == "audit.json":
            actual = sha256(target.read_bytes()).hexdigest()
        else:
            stat_info = target.stat()
            actual = _cached_file_hash(str(target), stat_info.st_size, stat_info.st_mtime_ns)
        if actual != digest:
            raise ValueError("icio_edition_archive_hash_mismatch")


def _annotate_source_year_collisions(output: list[dict]) -> list[dict]:
    """Reconcile logically equal source years without conflating ZIP metadata.

    Different ZIP hashes with identical validated annual CSV member hashes
    represent identical annual data in two archive wrappers. Different member
    hashes, parser failures, or missing member identities are unresolved source
    version collisions and cannot enter research calculations.
    """
    from collections import defaultdict
    from .icio_native import expected_archive_years
    by_period = defaultdict(list)
    for idx, item in enumerate(output):
        expected = item.get("expected_years")
        if expected is None:
            expected = expected_archive_years(item["filename"], item["edition"])
        for year in expected or []:
            by_period[(item["edition"], item["table"], year)].append(idx)
        item["conflicting_years"] = []
        item["equivalent_annual_years"] = []
        item["suppressed_equivalent_years"] = []
        item["conflicting_sources"] = []
    for (_, _, year), indices in by_period.items():
        if len({output[i]["archive_sha256"] for i in indices}) <= 1:
            continue
        annual_hashes = []
        for idx in indices:
            year_record = next((r for r in output[idx].get("annual_matrices", [])
                                if r.get("year") == year), None)
            annual_hashes.append(year_record.get("original_member_sha256")
                                 if year_record else None)
        if annual_hashes[0] and all(h == annual_hashes[0] for h in annual_hashes):
            primary = min(indices, key=lambda i: (
                output[i]["archive_sha256"], output[i]["filename"]))
            for i in indices:
                output[i]["equivalent_annual_years"].append(year)
                if i != primary:
                    output[i]["suppressed_equivalent_years"].append(year)
            continue
        for i in indices:
            output[i]["conflicting_years"].append(year)
            for j in indices:
                if i != j:
                    output[i]["conflicting_sources"].append({
                        "filename": output[j]["filename"],
                        "archive_sha256": output[j]["archive_sha256"],
                        "year": year})
    for item in output:
        item["conflicting_years"] = sorted(set(item["conflicting_years"]))
        item["equivalent_annual_years"] = sorted(set(item["equivalent_annual_years"]))
        item["suppressed_equivalent_years"] = sorted(set(item["suppressed_equivalent_years"]))
        item["source_year_conflict"] = bool(item["conflicting_years"])
    return output


def read_edition_archives(root: Path, *, archive_sha: str | None = None) -> list[dict]:
    base = Path(root) / "icio" / "other-editions"
    if not base.is_dir():
        return []
    output = []
    for parent in sorted(base.iterdir()):
        if parent.is_symlink() or not parent.is_dir():
            raise ValueError("icio_edition_archive_directory_invalid")
        if archive_sha is not None and not parent.name.endswith("-" + archive_sha[:16]):
            continue
        for bundle in sorted(p for p in parent.iterdir() if p.is_dir() and
                             re.fullmatch(r"[0-9a-f]{64}", p.name)):
            if bundle.is_symlink():
                raise ValueError("icio_edition_archive_directory_invalid")
            record = json.loads((bundle / "audit.json").read_text())
            _verify_edition_bundle(bundle, record)
            derived = _read_native_derived(root, record["archive_sha256"])
            if derived is not None:
                native = derived["native"]
                auxiliary = derived["auxiliary"]
                record = {**record, **native, "auxiliary_numeric": auxiliary,
                          "industry_accounts_validated":
                              native["native_validation_status"] == "native_accounts_verified",
                          "original_archive_status": record["status"],
                          "status": (native["native_validation_status"]
                                     if native["annual_matrix_count"] or native["rejected_matrices"]
                                     else auxiliary["status"] if auxiliary["status"] != "no_rdata_members"
                                     else "original_archived_dimensions_unverified")}
            output.append({**{key: record[key] for key in ("filename", "edition", "table",
                "status", "archive_sha256", "member_count", "source_authenticity_verified",
                "industry_accounts_validated", "tiva_comparability_certified")},
                "bundle_digest": bundle.name,
                "auxiliary_numeric": record.get("auxiliary_numeric", {
                    "status": "not_evaluated", "numeric_reports": []}),
                "native_validation_status": record.get("native_validation_status", "not_evaluated"),
                "annual_matrix_count": record.get("annual_matrix_count", 0),
                "annual_matrices": record.get("annual_matrices", []),
                "rejected_matrices": record.get("rejected_matrices", []),
                "expected_years": record.get("expected_years"),
                "observed_years": record.get("observed_years", []),
                "source_identity_reconciliation": record.get(
                    "source_identity_reconciliation"),
                "header_schema": record.get("header_schema"),
                "original_registered_edition": (
                    record.get("source_identity_reconciliation") or {}).get(
                        "sealed_edition", record.get("edition"))})
    if archive_sha is None:
        _annotate_source_year_collisions(output)
    return output
