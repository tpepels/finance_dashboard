"""Native TWSE/TPEx issuer-income samples; no annual/world profit aggregate.

The retained public CSVs predate the canonical source capture path. Their
original acquisition manifest and both original bodies are pinned here so they
can be independently read without rewriting that historical evidence. The flat
tables do not verify currency, scale, filing context or cumulative-flow scope.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import re


EDITION = "2026-11-04-59569897b7cc"
MANIFEST_SHA256 = "59569897b7ccf60d6a94c00ce821a5fb0ce33c3ca0b45de3dc3633d825d3a969"
SOURCE_SPECS = {
    "L": {"file": "t187ap06_L_ci.csv", "market": "TWSE listed general business",
          "sha256": "29b03ff3ceb84a7ffb079dbf0e63860e98013c909631bdceec25a616fa38c5a0"},
    "O": {"file": "t187ap06_O_ci.csv", "market": "TPEx OTC general business",
          "sha256": "35afc88edb821c88c2bf68e6d521018ab3bcdd3388dfe63463ce9839c234030e"},
}
BASE = "https://mopsfin.twse.com.tw/opendata/"
COLUMNS = (
    "出表日期", "年度", "季別", "公司代號", "公司名稱", "營業收入", "營業成本",
    "原始認列生物資產及農產品之利益（損失）", "生物資產當期公允價值減出售成本之變動利益（損失）",
    "營業毛利（毛損）", "未實現銷貨（損）益", "已實現銷貨（損）益", "營業毛利（毛損）淨額",
    "營業費用", "其他收益及費損淨額", "營業利益（損失）", "營業外收入及支出", "稅前淨利（淨損）",
    "所得稅費用（利益）", "繼續營業單位本期淨利（淨損）", "停業單位損益", "合併前非屬共同控制股權損益",
    "本期淨利（淨損）", "其他綜合損益（淨額）", "合併前非屬共同控制股權綜合損益淨額", "本期綜合損益總額",
    "淨利（淨損）歸屬於母公司業主", "淨利（淨損）歸屬於共同控制下前手權益", "淨利（淨損）歸屬於非控制權益",
    "綜合損益總額歸屬於母公司業主", "綜合損益總額歸屬於共同控制下前手權益", "綜合損益總額歸屬於非控制權益",
    "基本每股盈餘（元）",
)
PARENT_INCOME_COLUMN = "淨利（淨損）歸屬於母公司業主"


def _amount(raw: str) -> str | None:
    if raw == "":
        return None
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("Invalid original Taiwan income value") from exc
    if not amount.is_finite():
        raise ValueError("Nonfinite original Taiwan income value")
    return str(amount)


def parse_taiwan_income(original: bytes, *, board: str) -> dict:
    """Keep explicit parent facts, native reference labels and missing inputs."""
    if board not in SOURCE_SPECS or len(original) > 5_000_000:
        raise ValueError("Unreviewed Taiwan income table identity or size")
    reader = csv.DictReader(StringIO(original.decode("utf-8-sig")))
    if tuple(reader.fieldnames or ()) != COLUMNS:
        raise ValueError("Original Taiwan income table columns mismatch")
    records, seen = [], set()
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Original Taiwan income row width invalid")
        native_year, quarter, code = (row[key] for key in ("年度", "季別", "公司代號"))
        if (not re.fullmatch(r"[0-9]{2,3}", native_year) or quarter not in {"1", "2", "3", "4"}
                or not re.fullmatch(r"[0-9]{4,6}", code) or not row["公司名稱"]):
            raise ValueError("Original Taiwan issuer/reference identity invalid")
        key = (code, native_year, quarter)
        if key in seen:
            raise ValueError("Repeated original Taiwan issuer/reference row")
        seen.add(key)
        output_date = row["出表日期"]
        if not re.fullmatch(r"[0-9]{7}", output_date):
            raise ValueError("Original Taiwan table date invalid")
        output_date = date(int(output_date[:3]) + 1911, int(output_date[3:5]), int(output_date[5:]))
        records.append({"company_code": code, "issuer_name": row["公司名稱"],
            "native_fiscal_year": native_year, "reported_reference_year": int(native_year) + 1911,
            "native_quarter": quarter, "reported_table_date": output_date.isoformat(),
            "reported_total_period_income_native": _amount(row["本期淨利（淨損）"]),
            "parent_attributable_income_native": _amount(row[PARENT_INCOME_COLUMN]),
            "noncontrolling_income_native": _amount(row["淨利（淨損）歸屬於非控制權益"]),
            "predecessor_common_control_income_native": _amount(row["淨利（淨損）歸屬於共同控制下前手權益"]),
            "native_currency": None, "native_scale": None, "annual_period_verified": False,
            "consolidation_scope_verified": False, "cumulative_or_discrete_flow_verified": False,
            "first_publication_verified": False})
    if not records:
        raise ValueError("Original Taiwan income table empty")
    return {"source": "TWSE_MOPS_GENERAL_BUSINESS_INCOME_CSV", "board": board,
            "market": SOURCE_SPECS[board]["market"], "records": records,
            "parent_income_column": PARENT_INCOME_COLUMN,
            "source_url": BASE + SOURCE_SPECS[board]["file"],
            "original_sha256": sha256(original).hexdigest()}


def _bounded_original(folder: Path, name: str, digest: str) -> bytes:
    path = folder / name
    if path.is_symlink() or path.stat().st_size > 5_000_000:
        raise ValueError("Taiwan original source size or symlink invalid")
    body = path.read_bytes()
    if sha256(body).hexdigest() != digest:
        raise ValueError("Taiwan original source digest mismatch")
    return body


def read_taiwan_sources(root: Path) -> dict:
    """Verify the retained original edition; never create or mutate evidence."""
    folder = Path(root) / "profit-samples" / EDITION
    if not folder.exists():
        return {"status": "missing_original_taiwan_profit_evidence", "records": []}
    if folder.is_symlink():
        raise ValueError("Taiwan source folder symlink invalid")
    manifest_bytes = _bounded_original(folder, "acquisition_manifest.json", MANIFEST_SHA256)
    expected = {"acquisition_manifest.json": MANIFEST_SHA256,
                **{spec["file"]: spec["sha256"] for spec in SOURCE_SPECS.values()}}
    ledger = folder / "SHA256SUMS"
    if ledger.is_symlink() or ledger.stat().st_size > 1000:
        raise ValueError("Taiwan original source ledger invalid")
    lines = [line.split("  ") for line in ledger.read_text().splitlines()]
    if len(lines) != len(expected) or any(len(line) != 2 for line in lines):
        raise ValueError("Taiwan original source ledger invalid")
    if {name: digest for digest, name in lines} != expected:
        raise ValueError("Taiwan original source ledger mismatch")
    manifest = json.loads(manifest_bytes)
    if manifest["schema_version"] != 1 or len(manifest["original_files"]) != len(SOURCE_SPECS):
        raise ValueError("Taiwan original source manifest identity invalid")
    records = []
    for board, spec in SOURCE_SPECS.items():
        original = _bounded_original(folder, spec["file"], spec["sha256"])
        entries = [item for item in manifest["original_files"] if item["file"] == spec["file"]]
        if len(entries) != 1:
            raise ValueError("Taiwan original source receipt missing or repeated")
        entry = entries[0]
        observed = datetime.fromisoformat(entry["observed_at_utc"])
        if (entry["url"] != BASE + spec["file"] or entry["sha256"] != spec["sha256"]
                or entry["http_status"] != 200 or entry["bytes"] != len(original)
                or observed.utcoffset() is None):
            raise ValueError("Taiwan original source acquisition identity invalid")
        records.append({**parse_taiwan_income(original, board=board),
            "source_manifest_sha256": MANIFEST_SHA256, "edition": EDITION,
            "evidence_retrieved_at_utc": observed.isoformat(),
            "http_last_modified": entry["http_last_modified"],
            "selection_method": "pinned_retained_original_acquisition"})
    return {"status": "regional_native_income_sample_partial", "records": records}
