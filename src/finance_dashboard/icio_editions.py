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
    if re.fullmatch(r"(?:1995-2000|2001-2005|2006-2010|2011-2015|2016-2020|2016-2022)_EXT(?: \([0-9]+\))?\.zip", filename):
        return {"edition": "2025", "table": "extended"}
    if re.fullmatch(r"2016-2020_SML\.zip", filename):
        return {"edition": "2025", "table": "regular", "status": "overlapping_release_unverified"}
    if re.fullmatch(r"ICIO2018_[A-Za-z0-9_-]+\.zip", filename):
        return {"edition": "2018", "table": "edition_specific_unresolved"}
    if re.fullmatch(r"ICIO2021[A-Za-z0-9_-]+\.zip", filename):
        return {"edition": "2021", "table": "edition_specific_unresolved"}
    raise ValueError("icio_archive_edition_not_registered")


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
    return {**identity, "filename": path.name, "archive_sha256": digest.hexdigest(),
            "archive_bytes": path.stat().st_size, "members": members,
            "member_count": len(members), "uncompressed_bytes": total,
            "status": "original_archived_dimensions_unverified",
            "source_authenticity_verified": False,
            "industry_accounts_validated": False,
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
            output.append({key: record[key] for key in ("filename", "edition", "table",
                "status", "archive_sha256", "member_count", "source_authenticity_verified",
                "industry_accounts_validated", "tiva_comparability_certified")})
    return output
