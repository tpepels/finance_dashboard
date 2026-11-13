"""MSCI regional index factsheets recovered from raw Internet Archive captures.

MSCI overwrites each factsheet URL every month and serves only the current
edition. Past editions survive as the Wayback Machine's raw (``id_``) captures
of MSCI's own URLs. Each capture is fetched once, checked against the archive's
CDX SHA-1 digest, hash-pinned and parsed with the pinned pypdf layout reader.

The document controls its own as-of date (the FUNDAMENTALS block), never the
capture timestamp; the capture time is only an upper bound on dissemination.
Every factsheet also prints comparison rows (World, ACWI, EM ...): those are
MSCI's own published values for those indexes and count as such. Two documents
that print different values for the same index and as-of month are a recorded
conflict: that index-month is blocked (neither value is chosen) and stays
absent; nothing is filled or interpolated.

P/E and P/E Fwd follow MSCI's Fundamental Data Methodology (pinned March 2021
edition): aggregate cap-weighted ratios, trailing 12-month EPS and the rolling
12-month I/B/E/S consensus EPS12F, losses included, currency-invariant.
"""
from __future__ import annotations

import base64
import calendar
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
from hashlib import sha1, sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import quote

from .source_evidence import record_acquisition_receipt

SOURCE = "MSCI_REGIONAL_FACTSHEET_WAYBACK_PDF"
ARCHIVE_DIR = "msci-regional-factsheets"
WAYBACK = "https://web.archive.org"
CDX_URL = WAYBACK + "/cdx/search/cdx"
MAXIMUM_PDF_BYTES = 5_000_000
MAXIMUM_CDX_BYTES = 2_000_000
PYPDF_VERSION = "6.21.4"
_MSCI = "https://www.msci.com/"
_GEN1 = "resources/factsheets/index_fact_sheet/"
_GEN3 = "documents/10199/255599/"
_UUID = "documents/10199/"

# The bound regional indexes; EMU and Pacific ex Japan are collected where the
# archive holds captures but have too few to bind a monthly series.
INDEXES = {
    "ACWI": {"title": "ACWI", "single_country": False, "bound": True},
    "WORLD": {"title": "WORLD", "single_country": False, "bound": True},
    "EM": {"title": "EMERGING MARKETS", "single_country": False, "bound": True},
    "USA": {"title": "USA", "single_country": True, "bound": True},
    "EUROPE": {"title": "EUROPE", "single_country": False, "bound": True},
    "JAPAN": {"title": "JAPAN", "single_country": True, "bound": True},
    "EAFE": {"title": "EAFE", "single_country": False, "bound": True},
    "EMU": {"title": "EMU", "single_country": False, "bound": False},
    "PXJ": {"title": "PACIFIC EX JAPAN", "single_country": False, "bound": False},
}
BOUND_INDEXES = tuple(key for key, item in INDEXES.items() if item["bound"])
# Row labels MSCI prints in the fundamentals table (with or without "MSCI ").
ROW_NAMES = {"ACWI": "ACWI", "WORLD": "WORLD", "EMERGING MARKETS": "EM", "USA": "USA",
             "EUROPE": "EUROPE", "JAPAN": "JAPAN", "EAFE": "EAFE", "EMU": "EMU",
             "PACIFIC EX JAPAN": "PXJ", "ACWI IMI": "ACWI_IMI"}

# Every original MSCI factsheet URL whose captures are queried, by index.
# Three URL generations (2012-2016 named, 2015-2026 document UUIDs, 2024-2026
# 255599 named); UUIDs were identified from MSCI's own archived index pages and
# confirmed by each document's title line, which the parser checks again.
FACTSHEET_URLS = {
    "ACWI": (_GEN1 + "msci-acwi.pdf", _GEN1 + "msci-acwi-net.pdf", _GEN1 + "msci-acwi-price.pdf",
             _UUID + "a71b65b5-d0ea-4b5c-a709-24b1213bc3c5", _GEN3 + "msci-acwi.pdf", _GEN3 + "msci-acwi-net.pdf"),
    "WORLD": (_GEN1 + "msci-world-index.pdf", _GEN1 + "msci-world-index-net.pdf", _GEN1 + "msci-world-index-eur-net.pdf",
              _UUID + "149ed7bc-316e-4b4c-8ea4-43fcb5bd6523", _UUID + "178e6643-6ae6-47b9-82be-e1fc565ededb",
              _UUID + "178e6643-6ae6-47b9-82be-e1fc565ededb/",
              _GEN3 + "msci-world-index.pdf", _GEN3 + "msci-world-index-usd-net.pdf", _GEN3 + "msci-world-index-usd-price.pdf"),
    "EM": (_GEN1 + "msci-emerging-markets.pdf", _GEN1 + "msci-emerging-markets-index.pdf",
           _GEN1 + "msci-emerging-markets-index-net.pdf", _GEN1 + "msci-emerging-markets-index-usd-net.pdf",
           _GEN1 + "msci-emerging-markets-index-gross.pdf", _GEN1 + "msci-emerging-markets-index-usd-price.pdf",
           _UUID + "c0db0a48-01f2-4ba9-ad01-226fd5678111",
           _GEN3 + "msci-emerging-markets-index-net.pdf", _GEN3 + "msci-emerging-markets-index-usd-net.pdf",
           _GEN3 + "msci-emerging-markets-index-gross.pdf", _GEN3 + "msci-emerging-markets-index-usd-price.pdf"),
    "USA": (_GEN1 + "msci-usa.pdf", _GEN1 + "msci-usa-index-net.pdf", _GEN1 + "msci-usa-index-gross.pdf",
            _UUID + "543ede35-09f9-4fa7-84ad-74e6750b2a42", _UUID + "67a768a1-71d0-4bd0-8d7e-f7b53e8d0d9f",
            _GEN3 + "msci-usa-index-net.pdf", _GEN3 + "msci-usa-index-gross.pdf", _GEN3 + "msci-usa-index-usd-price.pdf"),
    "EUROPE": (_GEN1 + "msci-europe-index.pdf", _GEN1 + "msci-europe-index-net.pdf",
               _GEN1 + "msci-europe-index-eur-net.pdf", _GEN1 + "msci-europe-index-eur-price.pdf",
               _UUID + "f6179af3-b1d1-4df0-8ac9-215451f3ac0a",
               _GEN3 + "msci-europe-index.pdf", _GEN3 + "msci-europe-index-net.pdf", _GEN3 + "msci-europe-index-price.pdf",
               _GEN3 + "msci-europe-index-eur-net.pdf", _GEN3 + "msci-europe-index-eur-price.pdf"),
    "JAPAN": (_GEN1 + "msci-japan-index.pdf", _GEN1 + "msci-japan-index-net.pdf", _GEN1 + "msci-japan-jpy.pdf",
              _UUID + "7c88aa58-4d51-492b-8802-e43962611fb1", _UUID + "b3ee6464-f705-4d65-81a0-d8756607cf9f",
              _GEN3 + "msci-japan-index.pdf", _GEN3 + "msci-japan-index-net.pdf"),
    "EAFE": (_GEN1 + "msci-eafe.pdf", _GEN1 + "msci-eafe-index-usd-net.pdf", _GEN1 + "msci-eafe-index-usd-price.pdf",
             _UUID + "822e3d18-16fb-4d23-9295-11bc9e07b8ba",
             _GEN3 + "msci-eafe.pdf", _GEN3 + "msci-eafe-index-usd-net.pdf", _GEN3 + "msci-eafe-index-usd-price.pdf"),
    "EMU": (_GEN1 + "msci-emu-index.pdf", _GEN1 + "msci-emu-index-eur-net.pdf", _GEN1 + "msci-emu-index-eur-gross.pdf",
            _GEN3 + "msci-emu-index.pdf"),
    "PXJ": (_GEN1 + "msci-pacific-ex-japan-index.pdf", _GEN1 + "msci-pacific-ex-japan-index-net.pdf"),
}
ORIGINAL_URLS = {_MSCI + path: index for index, paths in FACTSHEET_URLS.items() for path in paths}

# MSCI Fundamental Data Methodology, March 2021, as archived raw (gzip payload).
METHODOLOGY = {
    "capture_url": WAYBACK + "/web/20230220162443id_/https://www.msci.com/eqb/methodology/meth_docs/MSCI_Fundamental_Data_Methodology_Mar2021.pdf",
    "original_url": "https://www.msci.com/eqb/methodology/meth_docs/MSCI_Fundamental_Data_Methodology_Mar2021.pdf",
    "archived_sha256": "02ffe3493732cfcc7aecfcadafcabfc4d7cb5557d191de27f76037d68eda4208",
    "archived_bytes": 734706, "cdx_digest": "GCSW7F22HUXQHJB2HLU7CJEQXR5LRPVJ",
    "pdf_sha256": "7eea07131456a9be40146fda57cf8f1246ae80d77ee796cdfcaefee01b98c3a3", "pdf_bytes": 883427,
    "definitions": {
        "pe": "Price/Earnings using trailing 12-month earnings per share; index ratio = sum of security market caps / sum of security earnings (inclusion-factor and FX weighted), negative earnings included.",
        "pe_fwd": "Price to 12-month forward earnings using EPS12F = (M x EPS1 + (12 - M) x EPS2) / 12, rolled from I/B/E/S consensus fiscal-year estimates.",
    },
}

GICS_SECTORS = frozenset({
    "Energy", "Materials", "Industrials", "Consumer Discretionary", "Consumer Staples", "Health Care",
    "Financials", "Information Technology", "Communication Services", "Telecommunication Services",
    "Utilities", "Real Estate"})
MONTHS = {name.upper(): number for number, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.upper(): number for number, name in enumerate(calendar.month_abbr) if name})
MONTHS["SEPT"] = 9
_DATE = r"([A-Za-z]{3,9})\.?\s+([0-9]{1,2}),\s+([0-9]{4})"
_DECIMAL = re.compile(r"-?[0-9]+\.[0-9]+")
_LEGEND = re.compile(r"(?<![A-Za-z])([A-Z][A-Za-z.&'()-]*(?: [A-Za-z.&'()-]+)*) ([0-9]{1,3}(?:\.[0-9]{1,2})?)%")


class MsciFactsheetError(ValueError):
    pass


def _date(month: str, day: str, year: str) -> date:
    number = MONTHS.get(month.upper())
    if number is None:
        raise MsciFactsheetError("factsheet_date_unreadable")
    return date(int(year), number, int(day))


def _month_end(day: date) -> bool:
    return calendar.monthrange(day.year, day.month)[1] - day.day <= 4


def _title(lines: list[str]) -> tuple[str, str]:
    for line in lines[:4]:
        # "MSCI World Index (USD)", "MSCI ACWI INDEX (USD)" or, for ACWI in
        # 2013-2016, "MSCI ACWI (USD)" without the word Index.
        match = (re.match(r"^\s*MSCI (.+?) INDEX\b\s*(?:\(\s*([A-Z]{3})\s*\))?\s*$", line, re.IGNORECASE)
                 or re.match(r"^\s*MSCI (.+?)\s+\(\s*([A-Z]{3})\s*\)\s*$", line, re.IGNORECASE))
        if match:
            name = " ".join(match.group(1).upper().split())
            index = next((key for key, item in INDEXES.items() if item["title"] == name), None)
            if index is None:
                raise MsciFactsheetError("factsheet_index_not_registered")
            return index, (match.group(2) or "").upper()
    raise MsciFactsheetError("factsheet_title_absent")


def _row_index(label: str) -> str | None:
    name = " ".join(label.upper().split())
    if name.startswith("MSCI "):
        name = name[5:]
    return ROW_NAMES.get(name)


def _fundamentals(lines: list[str]) -> tuple[date, dict]:
    heads = [i for i, line in enumerate(lines) if re.search(r"FUNDAMENTALS\s*\(", line, re.IGNORECASE)]
    if len(heads) != 1:
        raise MsciFactsheetError("fundamentals_block_absent_or_ambiguous")
    match = re.search(r"FUNDAMENTALS\s*\(\s*" + _DATE, lines[heads[0]], re.IGNORECASE)
    if not match:
        raise MsciFactsheetError("fundamentals_as_of_unreadable")
    asof = _date(*match.groups())
    header = next((i for i in range(heads[0], min(heads[0] + 8, len(lines)))
                   if all(label in lines[i] for label in ("Div Yld", "P/E Fwd", "P/BV"))), None)
    if header is None:
        raise MsciFactsheetError("fundamentals_header_absent")
    start = lines[header].index("Div Yld")
    rows, stray = {}, False
    for line in lines[header + 1:]:
        if re.match(r"^\s*INDEX RISK", line, re.IGNORECASE):
            break
        tokens = [m for m in _DECIMAL.finditer(line) if m.end() > start]
        numbers = list(_DECIMAL.finditer(line))
        label = line[:numbers[0].start()].strip() if numbers else line.strip()
        if not label:
            stray = stray or bool(tokens)
            continue
        index = _row_index(label)
        if not numbers:
            continue
        if len(tokens) != 4:
            stray = True
            continue
        if index is None:
            continue
        if index in rows:
            raise MsciFactsheetError("fundamentals_row_repeated")
        values = [Decimal(m.group()) for m in tokens]
        dy, pe, fwd, pbv = values
        if not (Decimal(0) <= dy < 20 and Decimal(0) < pe < 200 and Decimal(0) < fwd < 200 and Decimal(0) < pbv < 50):
            raise MsciFactsheetError("fundamentals_value_implausible")
        rows[index] = {"dividend_yield_pct": str(dy), "pe": str(pe), "pe_fwd": str(fwd), "pbv": str(pbv),
                       "printed_label": label}
    if stray:
        # Gross-return editions can shift the fundamentals one row under the
        # layout reader; a value line without its index label is never assigned.
        raise MsciFactsheetError("fundamentals_rows_misaligned")
    if not rows:
        raise MsciFactsheetError("fundamentals_rows_absent")
    return asof, rows


def _composition(text: str, lines: list[str], index: str) -> dict:
    heads = [i for i, line in enumerate(lines) if re.search(r"SECTOR WEIGHTS", line, re.IGNORECASE)]
    if len(heads) != 1:
        raise MsciFactsheetError("sector_weights_absent_or_ambiguous")
    cut = re.search(r"COUNTRY WEIGHTS", lines[heads[0]], re.IGNORECASE)
    sectors, countries = {}, {}
    for line in lines[heads[0] + 1:]:
        if ("| msci.com" in line or re.match(r"^\s*(Index Methodology|About MSCI|MSCI FACTOR BOX)", line, re.IGNORECASE)):
            break
        for match in _LEGEND.finditer(line):
            label, value = match.group(1).strip(), Decimal(match.group(2))
            target = sectors if label in GICS_SECTORS else countries
            if target is countries and (cut is None or match.start() < cut.start() - 4):
                raise MsciFactsheetError("weights_legend_unrecognised")
            if label in target:
                raise MsciFactsheetError("weights_legend_repeated")
            target[label] = value
    if len(sectors) < 10 or abs(sum(sectors.values()) - 100) > Decimal("0.1"):
        raise MsciFactsheetError("sector_weights_do_not_sum")
    if INDEXES[index]["single_country"]:
        if countries:
            raise MsciFactsheetError("single_country_index_prints_country_weights")
    elif len(countries) < 2 or abs(sum(countries.values()) - 100) > Decimal("0.1"):
        # Small regions print every country; larger ones the top few plus "Other".
        raise MsciFactsheetError("country_weights_do_not_sum")
    table = re.findall(r"\bNumber of(?:\s+Constituents)?\s+([0-9,]+)\s", text)
    described = re.findall(r"\bWith\s+([0-9,]+)\s+constituents", text)
    if len(set(table)) != 1:
        raise MsciFactsheetError("constituent_count_absent_or_ambiguous")
    count = int(table[0].replace(",", ""))
    if described and {int(item.replace(",", "")) for item in described} != {count}:
        raise MsciFactsheetError("constituent_count_contradicts_description")
    return {"sector_weights_pct": {k: str(v) for k, v in sorted(sectors.items())},
            "country_weights_pct": {k: str(v) for k, v in sorted(countries.items())},
            "countries_reported": sorted(k for k in countries if k != "Other"),
            "country_weights_complete": bool(countries) and "Other" not in countries,
            "constituent_count": count,
            "gics_vintage": "pre_2018_telecommunication" if "Telecommunication Services" in sectors else "communication_services"}


def _market_cap(lines: list[str]) -> str | None:
    """The headline index's float-adjusted market cap in USD millions (INDEX CHARACTERISTICS), or None if not printed."""
    heads = [i for i, line in enumerate(lines) if re.search(r"Mkt Cap\s*\(\s*USD Millions\s*\)", line)]
    if len(heads) != 1:
        return None
    for line in lines[heads[0] + 1:heads[0] + 4]:
        match = re.match(r"^\s*Index\s+([0-9][0-9,]*\.[0-9]+)\b", line)
        if match:
            value = Decimal(match.group(1).replace(",", ""))
            if not Decimal(1000) < value < Decimal(1_000_000_000):
                raise MsciFactsheetError("market_cap_implausible")
            return str(value)
    return None


def parse_factsheet_text(text: str) -> dict:
    lines = text.replace("\f", "\n").splitlines()
    index, currency = _title([line for line in lines if line.strip()])
    asof, rows = _fundamentals(lines)
    if not _month_end(asof) or asof > date.today():
        raise MsciFactsheetError("fundamentals_as_of_not_a_month_end")
    if index not in rows:
        raise MsciFactsheetError("headline_index_row_absent")
    try:
        composition, reason = _composition(text, lines, index), None
    except MsciFactsheetError as exc:
        composition, reason = None, str(exc)
    return {"schema_version": 1, "source": SOURCE, "index": index, "currency": currency,
            "as_of": asof.isoformat(), "fundamentals": rows, "index_market_cap_usd_m": _market_cap(lines),
            "composition": composition, "composition_rejected": reason}


def _pdf_text(pdf: bytes) -> str:
    from pypdf import PdfReader, __version__
    if __version__ != PYPDF_VERSION:
        raise MsciFactsheetError("factsheet_extraction_requires_pinned_pypdf")
    try:
        reader = PdfReader(BytesIO(pdf))
        if not 2 <= len(reader.pages) <= 6:
            raise MsciFactsheetError("factsheet_page_count_unexpected")
        return "\f".join(page.extract_text(extraction_mode="layout", layout_mode_space_vertically=False)
                         for page in reader.pages)
    except MsciFactsheetError:
        raise
    except Exception as exc:  # pypdf raises many types for damaged documents
        raise MsciFactsheetError("factsheet_pdf_unreadable") from exc


def archived_pdf(payload: bytes) -> tuple[bytes, str]:
    """The archived payload is the PDF itself or MSCI's gzip transfer encoding of it."""
    encoding = "identity"
    if payload.startswith(b"\x1f\x8b"):
        try:
            payload, encoding = gzip.decompress(payload), "gzip"
        except (OSError, EOFError) as exc:
            raise MsciFactsheetError("archived_gzip_payload_invalid") from exc
    if not payload.startswith(b"%PDF-") or len(payload) > MAXIMUM_PDF_BYTES:
        raise MsciFactsheetError("archived_payload_is_not_a_bounded_pdf")
    return payload, encoding


def cdx_digest(payload: bytes) -> str:
    return base64.b32encode(sha1(payload).digest()).decode()


def parse_factsheet_payload(payload: bytes) -> tuple[dict, str]:
    pdf, encoding = archived_pdf(payload)
    text = _pdf_text(pdf)
    facts = parse_factsheet_text(text)
    return {**facts, "transfer_encoding": encoding, "pdf_sha256": sha256(pdf).hexdigest(),
            "extraction": {"tool": "pypdf", "version": PYPDF_VERSION, "mode": "layout",
                           "text_sha256": sha256(text.encode()).hexdigest()}}, text


# --- capture identity ---------------------------------------------------------------

def capture_url(timestamp: str, original: str) -> str:
    if not re.fullmatch(r"[0-9]{14}", timestamp):
        raise MsciFactsheetError("capture_timestamp_invalid")
    return f"{WAYBACK}/web/{timestamp}id_/{original}"


def _canonical(original: str) -> str:
    """CDX originals vary in scheme, host and port; map them to MSCI's https URL."""
    match = re.fullmatch(r"https?://(?:www\.)?msci\.com(?::80|:443)?/(.+)", original)
    if not match or "?" in original or "#" in original:
        raise MsciFactsheetError("capture_original_not_an_msci_factsheet")
    canonical = _MSCI + match.group(1)
    if canonical not in ORIGINAL_URLS:
        raise MsciFactsheetError("capture_original_not_registered")
    return canonical


def _registered(original: str) -> str | None:
    try:
        return _canonical(original)
    except MsciFactsheetError:
        return None


def cdx_query_url(original: str) -> str:
    if original not in ORIGINAL_URLS:
        raise MsciFactsheetError("factsheet_url_not_registered")
    return (CDX_URL + "?url=" + quote(original, safe="") +
            "&output=json&fl=timestamp,original,statuscode,mimetype,digest,length")


def parse_cdx(raw: bytes) -> list[dict]:
    try:
        rows = json.loads(raw) if raw.strip() else []
    except ValueError as exc:
        raise MsciFactsheetError("cdx_listing_invalid") from exc
    if rows and rows[0] != ["timestamp", "original", "statuscode", "mimetype", "digest", "length"]:
        raise MsciFactsheetError("cdx_listing_header_unexpected")
    out = []
    for row in rows[1:]:
        if len(row) != 6 or not re.fullmatch(r"[0-9]{14}", row[0]) or not re.fullmatch(r"[A-Z2-7]{32}", row[4]):
            raise MsciFactsheetError("cdx_listing_row_invalid")
        out.append(dict(zip(("timestamp", "original", "statuscode", "mimetype", "digest", "length"), row)))
    return out


def _write_bundle(parent: Path, payloads: dict[str, bytes], manifest: dict) -> Path:
    hashes = {name: sha256(body).hexdigest() for name, body in payloads.items()}
    folder = parent / sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    temporary = None
    try:
        parent.mkdir(parents=True, exist_ok=True)
        if not folder.exists():
            temporary = Path(tempfile.mkdtemp(prefix=".msci-", dir=parent))
            for name, body in payloads.items():
                (temporary / name).write_bytes(body)
            (temporary / "manifest.json").write_text(json.dumps({**manifest, "files": hashes}, indent=2, sort_keys=True))
            try:
                os.rename(temporary, folder)
                temporary = None
            except FileExistsError:
                pass
        return folder
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


def _read_bundle(folder: Path) -> tuple[dict, dict[str, bytes]]:
    manifest = json.loads((folder / "manifest.json").read_text())
    files = manifest["files"]
    if (folder.is_symlink() or sha256(json.dumps(files, sort_keys=True).encode()).hexdigest() != folder.name):
        raise MsciFactsheetError("bundle_identity_invalid")
    bodies = {}
    for name, digest in files.items():
        path = folder / name
        if path.is_symlink() or sha256(body := path.read_bytes()).hexdigest() != digest:
            raise MsciFactsheetError("bundle_file_hash_mismatch")
        bodies[name] = body
    return manifest, bodies


def store_cdx_listing(root: Path, original: str, raw: bytes) -> Path:
    rows = parse_cdx(raw)
    key = sha256(original.encode()).hexdigest()[:16]
    identity = {"publisher": "MSCI", "archive": "Internet Archive CDX", "original_url": original}
    folder = _write_bundle(root / ARCHIVE_DIR / "cdx" / key, {"listing.json": raw},
                           {"schema_version": 1, "source": SOURCE, "kind": "cdx_listing", **identity,
                            "query_url": cdx_query_url(original), "rows": len(rows),
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()})
    record_acquisition_receipt(folder, identity)
    return folder


def capture_facts(payload: bytes, original: str, timestamp: str) -> tuple[str, str | None, dict | None, str]:
    """Parse one archived capture and check it against its own capture identity."""
    try:
        facts, text = parse_factsheet_payload(payload)
    except MsciFactsheetError as exc:
        return "rejected", str(exc), None, ""
    captured = datetime.strptime(timestamp, "%Y%m%d%H%M%S").date()
    if facts["index"] != ORIGINAL_URLS[original]:
        return "rejected", "document_index_differs_from_url", None, text
    if date.fromisoformat(facts["as_of"]) > captured:
        return "rejected", "document_as_of_after_capture", None, text
    return "parsed", None, facts, text


def store_capture(root: Path, row: dict, payload: bytes) -> Path:
    """Retain every fetched capture; a document that does not parse stays as evidence.

    facts.json records the parse at collection time; the reader always parses
    the archived bytes again, so a corrected parser needs no new download."""
    original = _canonical(row["original"])
    if cdx_digest(payload) != row["digest"]:
        raise MsciFactsheetError("capture_payload_differs_from_cdx_digest")
    status, reason, facts, text = capture_facts(payload, original, row["timestamp"])
    identity = {"publisher": "MSCI", "original_url": original, "capture_timestamp": row["timestamp"],
                "cdx_digest": row["digest"]}
    payloads = {"archived.bin": payload, "facts.json": json.dumps(
        {"status": status, "rejection": reason, "facts": facts}, sort_keys=True).encode(),
        "extracted.txt": text.encode()}
    key = row["timestamp"] + "-" + row["digest"][:12].lower()
    folder = _write_bundle(root / ARCHIVE_DIR / "documents" / key, payloads,
                           {"schema_version": 1, "source": SOURCE, "kind": "factsheet_capture", **identity,
                            "index": ORIGINAL_URLS[original], "capture_url": capture_url(row["timestamp"], row["original"]),
                            "cdx_original": row["original"], "original_first_publication_at": None,
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()})
    record_acquisition_receipt(folder, identity)
    return folder


def store_methodology(root: Path, payload: bytes) -> Path:
    pdf, _ = archived_pdf(payload)
    if (sha256(payload).hexdigest() != METHODOLOGY["archived_sha256"] or cdx_digest(payload) != METHODOLOGY["cdx_digest"]
            or sha256(pdf).hexdigest() != METHODOLOGY["pdf_sha256"]):
        raise MsciFactsheetError("methodology_differs_from_pinned_edition")
    identity = {"publisher": "MSCI", "original_url": METHODOLOGY["original_url"]}
    folder = _write_bundle(root / ARCHIVE_DIR / "methodology", {"archived.bin": payload},
                           {"schema_version": 1, "source": SOURCE, "kind": "methodology", **identity,
                            "capture_url": METHODOLOGY["capture_url"],
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()})
    record_acquisition_receipt(folder, identity)
    return folder


# --- collection -------------------------------------------------------------------

def _get(client, url: str, limit: int, *, raw: bool = True) -> tuple[int, bytes]:
    """Archived payloads are read raw (the CDX digest covers the stored bytes);
    CDX listings are ordinary responses whose transfer encoding is decoded."""
    payload = bytearray()
    with client.stream("GET", url, follow_redirects=False) as response:
        if response.status_code != 200:
            return response.status_code, b""
        if response.is_stream_consumed:
            # An in-memory (test) response already holds its body.
            payload.extend(response.content)
        else:
            for chunk in (response.iter_raw() if raw else response.iter_bytes()):
                payload.extend(chunk)
                if len(payload) > limit:
                    raise MsciFactsheetError("archived_response_exceeds_byte_limit")
    if len(payload) > limit:
        raise MsciFactsheetError("archived_response_exceeds_byte_limit")
    return 200, bytes(payload)


def _latest_cdx_listing(root: Path, original: str) -> tuple[bytes, datetime] | None:
    """Verify retained CDX evidence and use its newest observation as a cache.

    A recent complete listing can avoid consuming a publisher request on each
    partial repair run. The original URL and query identity must match exactly;
    corrupted archives fail closed rather than being silently disregarded.
    """
    parent = root / ARCHIVE_DIR / "cdx" / sha256(original.encode()).hexdigest()[:16]
    latest = None
    for folder in sorted(parent.iterdir()) if parent.is_dir() else []:
        if not re.fullmatch(r"[0-9a-f]{64}", folder.name):
            continue
        manifest, bodies = _read_bundle(folder)
        if (manifest.get("source") != SOURCE
                or manifest.get("kind") != "cdx_listing"
                or manifest.get("original_url") != original
                or manifest.get("query_url") != cdx_query_url(original)
                or set(bodies) != {"listing.json"}):
            raise MsciFactsheetError("cdx_original_identity_invalid")
        try:
            observed = datetime.fromisoformat(manifest["retrieved_at_utc"])
        except (KeyError, ValueError, TypeError) as exc:
            raise MsciFactsheetError("cdx_retrieval_timestamp_invalid") from exc
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise MsciFactsheetError("cdx_retrieval_timestamp_invalid")
        parse_cdx(bodies["listing.json"])
        if latest is None or observed > latest[1]:
            latest = (bodies["listing.json"], observed)
    return latest


def _stored_captures(root: Path) -> set[str]:
    base = root / ARCHIVE_DIR / "documents"
    return {path.name for path in base.iterdir()} if base.is_dir() else set()


def collect(root: Path, *, client=None, indexes=None, log=print,
            stopped=None, prefer_recent: bool = False,
            capture_not_before: date | None = None) -> dict:
    """Bounded, resumable original collection.

    The source-health mode first obtains recent captured issues instead of
    spending its constrained request budget backfilling already irrelevant
    older PDF vintages. Old captures are still available through the normal
    full collector; every accepted document retains its CDX digest.
    """
    import httpx
    from .source_policy import managed_client, require_managed_client
    owned = client is None
    client = require_managed_client(client) if client is not None else managed_client(
        timeout=90, follow_redirects=False, headers={"User-Agent": "finance-dashboard-research/0.2 (private research)"})
    summary = Counter()
    try:
        if stopped is not None and stopped.is_set():
            return {"cancelled": 1}
        if not (root / ARCHIVE_DIR / "methodology").is_dir():
            status, payload = _get(client, METHODOLOGY["capture_url"], MAXIMUM_PDF_BYTES)
            if status != 200:
                raise MsciFactsheetError("methodology_capture_unavailable")
            store_methodology(root, payload)
            summary["methodology"] += 1
        captures = {}
        from .source_policy_types import PolicyDeferred, PolicyViolation
        from datetime import timedelta
        # Prefer never-fetched URLs and then the oldest listing; the first
        # ten source URLs must not starve the others on every scheduled run.
        known = {
            original: _latest_cdx_listing(root, original)
            for original, index in ORIGINAL_URLS.items()
            if indexes is None or index in indexes
        }
        now = datetime.now(timezone.utc)
        candidates = sorted(known, key=lambda original: (
            known[original] is not None,
            known[original][1] if known[original] else datetime.min.replace(tzinfo=timezone.utc),
            original,
        ))
        policy_stopped = False
        for original in candidates:
            if stopped is not None and stopped.is_set():
                summary["cancelled"] += 1
                return dict(summary)
            cached = known[original]
            raw = cached[0] if cached is not None else None
            recently_checked = (cached is not None and
                timedelta(0) <= now - cached[1] < timedelta(days=7))
            if recently_checked:
                summary["cdx_cache_reused"] += 1
            elif not policy_stopped:
                try:
                    status, fresh = _get(client, cdx_query_url(original),
                                         MAXIMUM_CDX_BYTES, raw=False)
                except PolicyDeferred:
                    summary["source_policy_deferred"] += 1
                    policy_stopped = True
                except PolicyViolation:
                    summary["source_policy_blocked"] += 1
                    policy_stopped = True
                except httpx.HTTPError:
                    summary["cdx_failed"] += 1
                else:
                    if status == 200:
                        store_cdx_listing(root, original, fresh)
                        raw = fresh
                        summary["cdx_listings"] += 1
                    else:
                        summary["cdx_failed"] += 1
            if raw is None:
                summary["cdx_missing"] += 1
                continue
            for row in parse_cdx(raw):
                # The CDX lookup can also return near-variants of the URL
                # (another case or trailing slash); only exact registered
                # MSCI URLs are fetched.
                if (row["statuscode"] == "200" and "pdf" in row["mimetype"]
                        and _registered(row["original"]) == original):
                    captures.setdefault(row["digest"], row)
                elif row["statuscode"] == "200" and "pdf" in row["mimetype"]:
                    summary["cdx_rows_other_url"] += 1
        seen = _stored_captures(root)
        eligible = [row for row in sorted(captures.values(),
                    key=lambda r: r["timestamp"], reverse=prefer_recent)
                    if capture_not_before is None
                    or row["timestamp"][:8] >= capture_not_before.strftime("%Y%m%d")]
        pending = [row for row in eligible
                   if row["timestamp"] + "-" + row["digest"][:12].lower() not in seen]
        summary["unique_captures"] = len(eligible)
        summary["excluded_older_captures"] = len(captures) - len(eligible)
        summary["already_stored"] = len(eligible) - len(pending)
        for number, row in enumerate(pending, 1):
            if stopped is not None and stopped.is_set():
                summary["cancelled"] += 1
                return dict(summary)
            try:
                status, payload = _get(client, capture_url(row["timestamp"], row["original"]), MAXIMUM_PDF_BYTES)
            except PolicyDeferred:
                summary["source_policy_deferred"] += 1
                break
            except PolicyViolation:
                summary["source_policy_blocked"] += 1
                break
            except (httpx.HTTPError, MsciFactsheetError):
                summary["capture_failed"] += 1
                continue
            if status != 200:
                summary[f"capture_http_{status}"] += 1
                continue
            try:
                folder = store_capture(root, row, payload)
            except MsciFactsheetError as exc:
                summary[str(exc)] += 1
                continue
            outcome = json.loads((folder / "facts.json").read_text())
            summary["stored_" + outcome["status"]] += 1
            if number % 25 == 0:
                log(json.dumps({"progress": number, "pending": len(pending), **summary}))
        return dict(summary)
    finally:
        if owned:
            client.close()


# --- verified reading -------------------------------------------------------------

def store_manual_factsheet(root: Path, index: str, original: str,
                           payload: bytes, *, publisher_download: bool = False) -> tuple[str, str]:
    """Record one owner-supplied original without forging a Wayback capture.

    Only canonical MSCI original URLs and printed PDF identities are accepted.
    Acquisition provenance explicitly marks the byte source as user supplied.
    """
    from .source_evidence import record_acquisition_receipt
    if (index not in BOUND_INDEXES or ORIGINAL_URLS.get(original) != index
            or len(payload) > MAXIMUM_PDF_BYTES):
        raise MsciFactsheetError("manual_factsheet_source_identity_invalid")
    facts, text = parse_factsheet_payload(payload)
    if facts["index"] != index or date.fromisoformat(facts["as_of"]) > date.today():
        raise MsciFactsheetError("manual_factsheet_printed_index_or_date_invalid")
    identity = {"publisher": "MSCI", "index": index,
                "source_kind": ("publisher_fetched_pdf" if publisher_download else
                                "owner_supplied_pdf")}
    parent = root / ARCHIVE_DIR / (
        "publisher-documents" if publisher_download else "manual-documents") / index
    files = {"publisher.pdf": payload}
    manifest = {"schema_version": 1, "source": SOURCE,
                "kind": ("publisher_fetched_factsheet" if publisher_download else
                         "owner_supplied_factsheet"),
                "source_identity": identity, "original_url": original,
                "as_of": facts["as_of"], "pdf_sha256": facts["pdf_sha256"],
                "publisher_origin_verified": publisher_download,
                "first_publication_verified": False}
    folder = _write_bundle(parent, files, manifest)
    restored, bodies = _read_bundle(folder)
    if (restored != {**manifest, "files": {"publisher.pdf": sha256(payload).hexdigest()}}
            or bodies != files):
        raise MsciFactsheetError("manual_factsheet_original_hash_invalid")
    receipt = record_acquisition_receipt(
        folder, identity, acquisition={"mode": ("publisher_https_pdf" if publisher_download else
                                                "owner_supplied_pdf"),
                                      "publisher_network_request": publisher_download})
    return folder.name, receipt.name


def store_manual_methodology(root: Path, payload: bytes, *,
                             publisher_download: bool = False) -> tuple[str, str]:
    """Allow the exact pinned original PDF when archived Wayback gzip is absent."""
    pdf, _encoding = archived_pdf(payload)
    if sha256(pdf).hexdigest() != METHODOLOGY["pdf_sha256"]:
        raise MsciFactsheetError("manual_methodology_differs_from_pinned_edition")
    identity = {"publisher": "MSCI", "source_kind": (
                "publisher_fetched_methodology" if publisher_download else
                "owner_supplied_methodology"), "edition": "March 2021"}
    manifest = {"schema_version": 1, "source": SOURCE,
                "kind": ("publisher_fetched_methodology" if publisher_download else
                         "owner_supplied_methodology"),
                "source_identity": identity,
                "original_url": METHODOLOGY["original_url"],
                "publisher_origin_verified": publisher_download,
                "pdf_sha256": METHODOLOGY["pdf_sha256"]}
    folder = _write_bundle(
        root / ARCHIVE_DIR / (
            "publisher-methodology" if publisher_download else "manual-methodology"),
        {"methodology.pdf": pdf}, manifest)
    stored, files = _read_bundle(folder)
    if (stored != {**manifest, "files": {"methodology.pdf": sha256(pdf).hexdigest()}}
            or files != {"methodology.pdf": pdf}):
        raise MsciFactsheetError("manual_methodology_archive_identity_invalid")
    receipt = record_acquisition_receipt(
        folder, identity, acquisition={"mode": ("publisher_https_methodology_pdf" if publisher_download else
                                                "owner_supplied_methodology_pdf"),
                                      "publisher_network_request": publisher_download})
    return folder.name, receipt.name


def _manual_methodology(root: Path) -> dict:
    """Accept the exact pinned edition from either user or publisher HTTPS."""
    from .source_evidence import verified_receipted_bundles
    matched = []
    for downloaded in (False, True):
        identity = {"publisher": "MSCI", "source_kind": (
                    "publisher_fetched_methodology" if downloaded else
                    "owner_supplied_methodology"), "edition": "March 2021"}
        parent = root / ARCHIVE_DIR / (
            "publisher-methodology" if downloaded else "manual-methodology")
        records = verified_receipted_bundles(parent, identity)
        seen = set()
        for record in records:
            if record["bundle_digest"] in seen:
                continue
            seen.add(record["bundle_digest"])
            manifest, files = _read_bundle(record["bundle_path"])
            if (manifest.get("source_identity") != identity
                    or manifest.get("kind") != ("publisher_fetched_methodology" if downloaded else
                                               "owner_supplied_methodology")
                    or manifest.get("original_url") != METHODOLOGY["original_url"]
                    or manifest.get("publisher_origin_verified") is not downloaded
                    or manifest.get("pdf_sha256") != METHODOLOGY["pdf_sha256"]
                    or set(files) != {"methodology.pdf"}
                    or sha256(files["methodology.pdf"]).hexdigest() != METHODOLOGY["pdf_sha256"]):
                raise MsciFactsheetError("manual_methodology_original_invalid")
        if len(seen) > 1:
            raise MsciFactsheetError("manual_methodology_edition_ambiguous")
        if seen:
            matched.append(downloaded)
    if not matched:
        raise MsciFactsheetError("manual_methodology_edition_ambiguous")
    downloaded = True in matched
    return {"original_url": METHODOLOGY["original_url"],
            "capture_url": None, "pdf_sha256": METHODOLOGY["pdf_sha256"],
            "edition": "March 2021", "definitions": METHODOLOGY["definitions"],
            "publisher_origin_verified": downloaded,
            "provenance": ("publisher_https_exact_sha256_pinned_methodology" if downloaded
                           else "owner_supplied_exact_sha256_pinned_methodology")}


def _verified_manual_documents(root: Path) -> list[dict]:
    """Include independently receipted uploads and direct publisher fetches."""
    from .source_evidence import verified_receipted_bundles
    docs = []
    for index in BOUND_INDEXES:
        for downloaded in (False, True):
            parent = root / ARCHIVE_DIR / (
                "publisher-documents" if downloaded else "manual-documents") / index
            if not parent.is_dir():
                continue
            identity = {"publisher": "MSCI", "index": index, "source_kind": (
                        "publisher_fetched_pdf" if downloaded else "owner_supplied_pdf")}
            seen = set()
            for record in verified_receipted_bundles(parent, identity):
                digest = record["bundle_digest"]
                if digest in seen:
                    continue
                seen.add(digest)
                manifest, files = _read_bundle(record["bundle_path"])
                original = manifest.get("original_url")
                if (manifest.get("source_identity") != identity
                        or manifest.get("source") != SOURCE
                        or manifest.get("kind") != ("publisher_fetched_factsheet" if downloaded else
                                                   "owner_supplied_factsheet")
                        or manifest.get("publisher_origin_verified") is not downloaded
                        or ORIGINAL_URLS.get(original) != index
                        or set(files) != {"publisher.pdf"}
                        or not manifest.get("as_of")):
                    raise MsciFactsheetError("manual_factsheet_original_identity_invalid")
                facts, _ = parse_factsheet_payload(files["publisher.pdf"])
                if (facts["index"] != index or facts["as_of"] != manifest["as_of"]
                        or facts["pdf_sha256"] != manifest["pdf_sha256"]
                        or date.fromisoformat(facts["as_of"]) > date.today()):
                    raise MsciFactsheetError("manual_factsheet_printed_identity_mismatch")
                docs.append({**facts,
                    "capture_url": ("publisher-fetch:" if downloaded else "owner-upload:")
                                   + "sha256:" + facts["pdf_sha256"],
                    "original_url": original, "capture_timestamp": None,
                    "cdx_digest": None,
                    "archived_sha256": sha256(files["publisher.pdf"]).hexdigest(),
                    "manifest_sha256": record["manifest_sha256"],
                    "acquired_at_utc": record["observed_at"].isoformat(),
                    "source_kind": ("publisher_https_endpoint" if downloaded else
                                    "owner_supplied_publisher_origin_unverified")})
    return docs


def _verified_documents(root: Path) -> tuple[list[dict], list[dict]]:
    from .source_reconciliation import _selected_manifest
    documents, rejected = [], []
    base = root / ARCHIVE_DIR / "documents"
    for parent in sorted(base.iterdir()) if base.is_dir() else []:
        if not re.fullmatch(r"[0-9]{14}-[a-z2-7]{12}", parent.name):
            continue
        bundles = [p for p in parent.iterdir() if re.fullmatch(r"[0-9a-f]{64}", p.name)]
        if len(bundles) != 1:
            raise MsciFactsheetError("capture_bundle_ambiguous")
        manifest, bodies = _read_bundle(bundles[0])
        identity = {key: manifest[key] for key in ("publisher", "original_url", "capture_timestamp", "cdx_digest")}
        observed, manifest_hash, path, _, selection = _selected_manifest(parent, identity)
        if selection != "acquisition_receipt" or path.parent != bundles[0]:
            raise MsciFactsheetError("capture_receipt_missing")
        if (cdx_digest(bodies["archived.bin"]) != manifest["cdx_digest"]
                or ORIGINAL_URLS.get(manifest["original_url"]) != manifest["index"]
                or parent.name != manifest["capture_timestamp"] + "-" + manifest["cdx_digest"][:12].lower()):
            raise MsciFactsheetError("capture_identity_invalid")
        proof = {"capture_url": manifest["capture_url"], "original_url": manifest["original_url"],
                 "capture_timestamp": manifest["capture_timestamp"], "cdx_digest": manifest["cdx_digest"],
                 "archived_sha256": sha256(bodies["archived.bin"]).hexdigest(), "manifest_sha256": manifest_hash,
                 "acquired_at_utc": observed.isoformat()}
        status, reason, facts, _ = capture_facts(bodies["archived.bin"], manifest["original_url"],
                                                 manifest["capture_timestamp"])
        if status == "rejected":
            rejected.append({**proof, "index": manifest["index"], "reason": reason})
            continue
        documents.append({**facts, **proof})
    return documents, rejected


def _methodology(root: Path) -> dict:
    parent = root / ARCHIVE_DIR / "methodology"
    bundles = [p for p in parent.iterdir() if re.fullmatch(r"[0-9a-f]{64}", p.name)] if parent.is_dir() else []
    if not bundles:
        return _manual_methodology(root)
    if len(bundles) != 1:
        raise MsciFactsheetError("methodology_ambiguous")
    _, bodies = _read_bundle(bundles[0])
    pdf, _ = archived_pdf(bodies["archived.bin"])
    if sha256(pdf).hexdigest() != METHODOLOGY["pdf_sha256"]:
        raise MsciFactsheetError("methodology_differs_from_pinned_edition")
    return {"original_url": METHODOLOGY["original_url"], "capture_url": METHODOLOGY["capture_url"],
            "pdf_sha256": METHODOLOGY["pdf_sha256"], "edition": "March 2021", "definitions": METHODOLOGY["definitions"]}


def _months(first: date, last: date) -> list[date]:
    out, day = [], first
    while day <= last:
        out.append(day)
        day = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    return out


_CACHE: dict = {}


def _fingerprint(root: Path) -> tuple:
    """Every retained file's path, size and modification time: an unchanged
    archive need not be re-parsed within one process; any change is re-read."""
    base = root / ARCHIVE_DIR
    if not base.is_dir():
        return ()
    return tuple(sorted((str(path.relative_to(base)), stat.st_size, stat.st_mtime_ns)
                        for path in base.rglob("*") if path.is_file() for stat in (path.stat(),)))


def read_msci_regional_evidence(root: Path) -> dict:
    """All verified captures as per-index monthly panels with measured coverage."""
    key = (str(Path(root).resolve()), _fingerprint(Path(root)))
    if key not in _CACHE:
        _CACHE.clear()
        _CACHE[key] = json.dumps(_read_evidence(Path(root)))
    return json.loads(_CACHE[key])


def _read_evidence(root: Path) -> dict:
    documents, rejected = _verified_documents(root)
    documents.extend(_verified_manual_documents(root))
    methodology = _methodology(root)
    values = defaultdict(lambda: defaultdict(dict))      # index -> month -> measure -> {value: [captures]}
    composition = defaultdict(lambda: defaultdict(list))
    for doc in documents:
        month = date.fromisoformat(doc["as_of"]).replace(day=1)
        for index, row in doc["fundamentals"].items():
            if index not in INDEXES:
                continue
            for measure in ("pe", "pe_fwd"):
                values[index][month].setdefault(measure, defaultdict(list))[row[measure]].append(doc["capture_url"])
        if doc.get("index_market_cap_usd_m") and doc["index"] in INDEXES and doc.get("currency") == "USD":
            values[doc["index"]][month].setdefault("mkt_cap", defaultdict(list))[doc["index_market_cap_usd_m"]].append(
                doc["capture_url"])
        if doc["composition"] is not None:
            composition[doc["index"]][month].append((doc["composition"], doc["capture_url"]))
    panels, conflicts = {}, []
    for index in INDEXES:
        series = {"pe": {}, "pe_fwd": {}, "mkt_cap": {}}
        for month, measures in sorted(values[index].items()):
            for measure, printed in measures.items():
                if len(printed) > 1:
                    conflicts.append({"index": index, "month": month.isoformat(), "measure": measure,
                                      "values": {value: urls for value, urls in sorted(printed.items())}})
                else:
                    series[measure][month] = next(iter(printed))
        months = sorted(series["pe"])
        own = sorted({date.fromisoformat(d["as_of"]).replace(day=1) for d in documents if d["index"] == index})
        grid = _months(months[0], months[-1]) if months else []
        composed = {}
        for month, items in sorted(composition[index].items()):
            distinct = {json.dumps(item, sort_keys=True) for item, _ in items}
            if len(distinct) > 1:
                conflicts.append({"index": index, "month": month.isoformat(), "measure": "composition",
                                  "values": sorted(distinct)})
            else:
                composed[month.isoformat()] = items[0][0]
        panels[index] = {
            "bound": INDEXES[index]["bound"],
            "pe": {m.isoformat(): v for m, v in series["pe"].items()},
            "pe_fwd": {m.isoformat(): v for m, v in series["pe_fwd"].items()},
            "mkt_cap": {m.isoformat(): v for m, v in series["mkt_cap"].items()},
            "composition": composed,
            "coverage": {
                "months_with_values": len(months),
                "first_month": months[0].isoformat() if months else None,
                "last_month": months[-1].isoformat() if months else None,
                "months_in_span": len(grid),
                "missing_months_in_span": [m.isoformat() for m in grid if m not in series["pe"]],
                "months_from_own_factsheet": len(own),
                "months_from_comparison_rows_only": len(set(months) - set(own)),
                "months_with_composition": len(composed),
                "months_per_year": dict(sorted(Counter(str(m.year) for m in months).items())),
            },
        }
    proofs = sorted(({key: d[key] for key in ("capture_url", "original_url", "capture_timestamp", "cdx_digest",
                                              "archived_sha256", "pdf_sha256", "manifest_sha256", "acquired_at_utc")}
                     | {"index": d["index"], "as_of": d["as_of"]} for d in documents),
                    key=lambda item: item["capture_url"])
    verified = bool(documents)
    return {"source": SOURCE, "original_source_hash_verified": verified, "methodology": methodology,
            "documents_parsed": len(documents), "documents_rejected": len(rejected),
            "rejections": dict(sorted(Counter(item["reason"] for item in rejected).items())),
            "rejected_documents": rejected, "conflicts": conflicts, "panels": panels,
            "document_proofs": proofs, "source_sha256": sha256(json.dumps(proofs, sort_keys=True).encode()).hexdigest(),
            "first_publication_verified": False,
            "scope": ("MSCI printed factsheets, archived originals, direct HTTPS publisher "
                      "downloads and owner uploads. Upload origin is unverified; "
                      "conflicting values are blocked."),}


def read_msci_regional_summary(root: Path) -> dict:
    """The artifact view: coverage, composition and conflicts, no raw values."""
    evidence = read_msci_regional_evidence(root)
    panels = {}
    for index, panel in evidence["panels"].items():
        months = sorted(panel["composition"])
        latest = panel["composition"][months[-1]] if months else None
        panels[index] = {"bound": panel["bound"], "coverage": panel["coverage"],
                         "composition_months": months,
                         "latest_composition": None if latest is None else {"month": months[-1], **latest}}
    return {"status": "verified_archived_original_factsheets" if evidence["original_source_hash_verified"]
            else "missing_original_factsheets",
            **{key: evidence[key] for key in ("source", "original_source_hash_verified", "methodology",
                                              "documents_parsed", "documents_rejected", "rejections",
                                              "conflicts", "source_sha256", "first_publication_verified", "scope")},
            "panels": panels}


SERIES_KEYS = {f"{index}/{measure}": (index, measure) for index in BOUND_INDEXES for measure in ("PE", "PE_FWD", "MKT_CAP")}


def series_conflicts(evidence: dict, key: str) -> list[dict]:
    index, measure = SERIES_KEYS[key]
    return [item for item in evidence["conflicts"] if item["index"] == index and item["measure"] == measure.lower()]


def series_values(evidence: dict, key: str) -> dict[date, Decimal]:
    """One bound index measure. A month two documents print differently is
    blocked: it has no value here and is listed by series_conflicts."""
    if key not in SERIES_KEYS:
        raise MsciFactsheetError("msci_regional_series_key_not_registered")
    index, measure = SERIES_KEYS[key]
    try:
        return {date.fromisoformat(m): Decimal(v) for m, v in evidence["panels"][index][measure.lower()].items()}
    except InvalidOperation as exc:
        raise MsciFactsheetError("msci_regional_value_invalid") from exc


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Collect MSCI regional factsheets from raw Internet Archive captures")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--index", action="append", choices=sorted(INDEXES))
    args = parser.parse_args(argv)
    if args.collect:
        print(json.dumps({"collection": collect(args.evidence_dir, indexes=set(args.index) if args.index else None)}))
    evidence = read_msci_regional_evidence(args.evidence_dir)
    print(json.dumps({key: evidence[key] for key in ("documents_parsed", "documents_rejected", "rejections")}
                     | {"conflicts": len(evidence["conflicts"]),
                        "coverage": {k: v["coverage"] for k, v in evidence["panels"].items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
