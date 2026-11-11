"""Owner holdings, independently persisted with revisions and explicit unknowns.

Supplied EUR values are authoritative. Identity references and owner-entered
classifications never grant source acceptance or establish scientific exposure.
The adjacent lock covers the entire read/check/replace across processes.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from urllib.parse import urlsplit


class PortfolioHoldingsError(ValueError):
    """An owner holdings request does not meet the storage contract."""


class PortfolioHoldingsConflict(PortfolioHoldingsError):
    """Another editor has already saved the expected revision."""


class PortfolioHoldingsUnavailable(PortfolioHoldingsError):
    """The store cannot safely be used; preserve it for recovery."""


_CENT = Decimal("0.01")
_MAX_NUMBER = Decimal("1000000000000000")
_ASSET_CLASSES = {"equity", "bonds", "gold", "precious_metals", "cash", "other", "unclassified"}
_IDENTITY_SOURCES = {"owner", "issuer_reference", "unresolved"}
_BASE_FIELDS = {"version", "revision", "as_of", "combine_accounts", "scope", "monthly_contribution_eur",
                "annual_withdrawal_eur", "positions"}
_ROW_FIELDS = {"id", "account", "name", "isin", "ticker", "quantity", "price_eur", "value_eur",
               "asset_class", "identity_source", "source_url"}
_PATH_LOCKS: dict[Path, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _text(value, field: str, maximum: int) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise PortfolioHoldingsError(f"{field} must be nonempty text of at most {maximum} characters")
    return value.strip()


def _revision(value) -> int:
    if type(value) is not int or value < 0:
        raise PortfolioHoldingsError("revision must be a nonnegative integer")
    return value


def _number(value, field: str, *, nullable=False, positive=False, money=False):
    if value is None and nullable:
        return None
    if type(value) not in (int, float):
        raise PortfolioHoldingsError(f"{field} must be a finite nonnegative number")
    try:
        numeric = Decimal(str(value))
        if (not numeric.is_finite() or numeric < 0 or numeric > _MAX_NUMBER
                or (positive and numeric == 0)):
            raise ValueError
        if money:
            numeric = numeric.quantize(_CENT, rounding=ROUND_HALF_UP)
        return float(numeric)
    except (ValueError, InvalidOperation, OverflowError):
        raise PortfolioHoldingsError(f"{field} must be finite, nonnegative, and at most 1000000000000000") from None


def _isin(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value):
        raise PortfolioHoldingsError("isin must be a 12-character uppercase ISIN or null")
    digits = "".join(character if character.isdigit() else str(ord(character) - 55) for character in value)
    checksum = 0
    for index, character in enumerate(reversed(digits)):
        number = int(character) * (2 if index % 2 else 1)
        checksum += number // 10 + number % 10
    if checksum % 10:
        raise PortfolioHoldingsError("isin has an invalid check digit")
    return value


def _source_url(value):
    if value is None:
        return None
    value = _text(value, "source_url", 2000)
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or any(character.isspace() for character in value)
                or "\\" in value):
            raise ValueError
        parsed.port  # Refuse invalid or out-of-range ports without fetching the reference.
    except ValueError:
        raise PortfolioHoldingsError("source_url must be an HTTPS reference without credentials") from None
    return value


def _choice(value, allowed: set[str], field: str):
    if not isinstance(value, str) or value not in allowed:
        raise PortfolioHoldingsError(f"{field} is not a supported value")
    return value


def _position(raw) -> dict:
    if not isinstance(raw, dict) or set(raw) - _ROW_FIELDS:
        raise PortfolioHoldingsError("Each position must contain only supported position fields")
    ticker = raw.get("ticker")
    return {"id": _text(raw.get("id"), "id", 100),
            "account": _text(raw.get("account"), "account", 120),
            "name": _text(raw.get("name"), "name", 300),
            "isin": _isin(raw.get("isin")),
            "ticker": None if ticker is None else _text(ticker, "ticker", 40),
            "quantity": _number(raw.get("quantity"), "quantity", positive=True),
            "price_eur": _number(raw.get("price_eur"), "price_eur", nullable=True),
            "value_eur": _number(raw.get("value_eur"), "value_eur", money=True),
            "asset_class": _choice(raw.get("asset_class", "unclassified"), _ASSET_CLASSES, "asset_class"),
            "identity_source": _choice(raw.get("identity_source", "unresolved"), _IDENTITY_SOURCES, "identity_source"),
            "source_url": _source_url(raw.get("source_url"))}


def _normalize(raw) -> dict:
    if not isinstance(raw, dict) or set(raw) - (_BASE_FIELDS | {"summary"}):
        raise PortfolioHoldingsError("Holdings must be an object containing only supported fields")
    if type(raw.get("version", 1)) is not int or raw.get("version", 1) != 1:
        raise PortfolioHoldingsError("Holdings version is unsupported")
    revision = _revision(raw.get("revision"))
    combine = raw.get("combine_accounts", False)
    if type(combine) is not bool:
        raise PortfolioHoldingsError("combine_accounts must be a boolean")
    as_of = raw.get("as_of")
    if as_of is not None:
        try:
            if not isinstance(as_of, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", as_of):
                raise ValueError
            if date.fromisoformat(as_of) > date.today():
                raise ValueError
        except ValueError:
            raise PortfolioHoldingsError("as_of must be a valid nonfuture YYYY-MM-DD date or null") from None
    rows = raw.get("positions")
    if not isinstance(rows, list) or len(rows) > 500:
        raise PortfolioHoldingsError("positions must be a list of at most 500 positions")
    positions = [_position(row) for row in rows]
    if len({row["id"] for row in positions}) != len(positions):
        raise PortfolioHoldingsError("Position ids must be unique")
    if positions and sum(Decimal(str(row["value_eur"])) for row in positions) <= 0:
        raise PortfolioHoldingsError("Listed positions must have a positive total supplied value")
    return {"version": 1, "revision": revision, "as_of": as_of, "combine_accounts": combine,
            "scope": _choice(raw.get("scope", "listed_positions"),
                             {"listed_positions", "full_invested_portfolio"}, "scope"),
            "monthly_contribution_eur": _number(raw.get("monthly_contribution_eur"), "monthly_contribution_eur", nullable=True, money=True),
            "annual_withdrawal_eur": _number(raw.get("annual_withdrawal_eur"), "annual_withdrawal_eur", nullable=True, money=True),
            "positions": positions}


def _empty() -> dict:
    return {"version": 1, "revision": 0, "as_of": None, "combine_accounts": False,
            "scope": "listed_positions", "monthly_contribution_eur": None,
            "annual_withdrawal_eur": None, "positions": []}


def _weight(value: Decimal, total: Decimal | None):
    return float(value / total) if total else None


def _with_summary(document: dict) -> dict:
    warnings = []
    for field, warning in (("as_of", "Valuation date is unknown."),
                           ("monthly_contribution_eur", "Monthly contribution is unknown."),
                           ("annual_withdrawal_eur", "Annual withdrawal is unknown.")):
        if document[field] is None:
            warnings.append(warning)
    rows = document["positions"]
    accounts = {}
    grouped = {}
    total = Decimal(0)
    for index, row in enumerate(rows, 1):
        label = f"Position {index} ({row['account']} · {row['name']})"
        value = Decimal(str(row["value_eur"]))
        total += value
        account = accounts.setdefault(row["account"], {"value": Decimal(0), "positions": 0})
        account["value"] += value
        account["positions"] += 1
        key = f"isin:{row['isin']}" if row["isin"] else f"position:{row['id']}"
        fund = grouped.setdefault(key, {"isin": row["isin"], "name": row["name"], "value": Decimal(0),
                                        "quantity": Decimal(0), "accounts": [], "classes": set()})
        fund["value"] += value
        fund["quantity"] += Decimal(str(row["quantity"]))
        if row["account"] not in fund["accounts"]:
            fund["accounts"].append(row["account"])
        fund["classes"].add(row["asset_class"])
        if row["isin"] is None:
            warnings.append(f"{label} has unresolved ISIN identity and is kept separate.")
        if row["asset_class"] == "unclassified":
            warnings.append(f"{label} has no supplied asset classification.")
        if row["price_eur"] is not None:
            with localcontext() as context:
                context.prec = 64
                expected = (Decimal(str(row["quantity"])) * Decimal(str(row["price_eur"]))).quantize(_CENT, rounding=ROUND_HALF_UP)
            if abs(expected - value) > _CENT:
                warnings.append(f"{label} quantity × price differs from its supplied value; supplied value is used.")
    combined = bool(rows) and (document["combine_accounts"] or len(accounts) == 1)
    combined_total = total if combined else None
    if len(accounts) > 1 and not document["combine_accounts"]:
        warnings.append("Multiple accounts are separate; enable account combination to calculate portfolio totals and weights.")
    if document["scope"] == "listed_positions":
        warnings.append("Totals describe listed positions; completeness of the invested portfolio is unconfirmed.")
    funds = []
    classes = {}
    for key, fund in grouped.items():
        classification = next(iter(fund["classes"])) if len(fund["classes"]) == 1 else "unclassified"
        if len(fund["classes"]) > 1:
            warnings.append(f"Classification conflict for {key}; grouped value is unclassified.")
        classes[classification] = classes.get(classification, Decimal(0)) + fund["value"]
        funds.append({"key": key, "isin": fund["isin"], "name": fund["name"],
                      "value_eur": float(fund["value"]), "weight": _weight(fund["value"], combined_total),
                      "quantity": float(fund["quantity"]), "accounts": fund["accounts"], "asset_class": classification})
    return {**document, "summary": {
        "accounts": [{"account": name, "value_eur": float(account["value"]), "positions": account["positions"]}
                     for name, account in accounts.items()],
        "total_value_eur": float(combined_total) if combined_total is not None else None,
        "positions": [{**row, "account_weight": _weight(Decimal(str(row["value_eur"])), accounts[row["account"]]["value"]),
                       "portfolio_weight": _weight(Decimal(str(row["value_eur"])), combined_total)} for row in rows],
        "funds": funds,
        "asset_classes": [{"asset_class": key, "value_eur": float(value), "weight": _weight(value, combined_total)}
                          for key, value in classes.items()],
        "warnings": warnings, "position_count": len(rows)}}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate object field")
        result[key] = value
    return result


def _nonfinite_constant(value):
    raise ValueError("Nonfinite number")


def _read(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object,
                         parse_constant=_nonfinite_constant)
        if not isinstance(raw, dict) or set(raw) != _BASE_FIELDS:
            raise ValueError
        clean = _normalize(raw)
        if clean != raw or clean["revision"] < 1:
            raise ValueError
        return clean
    except FileNotFoundError:
        return _empty()
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise PortfolioHoldingsUnavailable(
            "Owner holdings are invalid or unreadable; preserve the file and repair or restore it before saving.") from None


def _write(path: Path, document: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(document, handle, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _path(path: Path | None) -> Path:
    try:
        return Path(path if path is not None else os.environ.get("FINANCE_PORTFOLIO_HOLDINGS", "/data/portfolio-holdings.json")).expanduser().resolve()
    except (OSError, ValueError, TypeError, RuntimeError):
        raise PortfolioHoldingsUnavailable("Owner holdings storage could not be accessed.") from None


@contextmanager
def _locked(path: Path, *, create=False):
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.setdefault(path, threading.RLock())
    with lock:
        try:
            if not create and not path.parent.exists():
                yield
                return
            if create:
                path.parent.mkdir(parents=True, exist_ok=True)
            with path.with_name(path.name + ".lock").open("a+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            raise PortfolioHoldingsUnavailable("Owner holdings storage could not be accessed or safely written.") from None


def load_portfolio_holdings(path: Path | None = None) -> dict:
    """Return the current document and recomputed summary, without replacing corruption."""
    selected = _path(path)
    with _locked(selected):
        return _with_summary(_read(selected))


def save_portfolio_holdings(raw: dict, path: Path | None = None) -> dict:
    """Atomically save owner inputs only if raw.revision is still current."""
    clean = _normalize(raw)
    selected = _path(path)
    with _locked(selected, create=True):
        current = _read(selected)
        if clean["revision"] != current["revision"]:
            raise PortfolioHoldingsConflict("Owner holdings changed in another editor; reload them before saving.")
        clean["revision"] += 1
        _write(selected, clean)
        return _with_summary(clean)
