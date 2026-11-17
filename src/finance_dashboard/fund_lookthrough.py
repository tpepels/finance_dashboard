"""Look through the owner's equity ETFs using each issuer's own holdings file.

Every fund is fetched from its issuer, identified by the fund ISIN the issuer
publishes (in the file, its API answer or its fund page), archived with
SHA-256 hashes and a receipt, and reduced to one figure: the share of the
fund held in euro-area securities. Nothing is estimated: a fund whose file
cannot be read or identified stops the calculation.

How "euro" is recognised depends on what the issuer reports per holding:
  iShares, SPDR  trading currency of the holding (EUR)
  VanEck         Bloomberg exchange code of the listing (euro-area exchanges)
  Vanguard       issuer country of the holding (euro-area member states),
                 because Vanguard reports no currency or exchange per holding.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET

from .source_evidence import record_acquisition_receipt


class LookthroughError(ValueError):
    """A fund's holdings could not be identified, read or reconciled."""


@dataclass(frozen=True)
class FundSource:
    isin: str
    issuer: str
    reference: str  # iShares portfolio id, SPDR file ticker, VanEck page slug, Vanguard port id


FUNDS = {source.isin: source for source in (
    FundSource("IE00B5BMR087", "ishares", "253743"),
    FundSource("IE00BYZK4552", "ishares", "284219"),
    FundSource("IE00BF4RFH31", "ishares", "296576"),
    FundSource("IE000I8KRLL9", "ishares", "319084"),
    FundSource("IE00B466KX20", "spdr", "spya-gy"),
    FundSource("IE00BMC38736", "vaneck", "semiconductor-etf"),
    FundSource("IE000YU9K6K2", "vaneck", "space-etf"),
    FundSource("IE0007Y8Y157", "vaneck", "quantum-computing-etf"),
    FundSource("IE00BK5BQT80", "vanguard", "9679"),
    FundSource("IE00BK5BR626", "vanguard", "9677"),
    FundSource("IE00BFMXXD54", "vanguard", "9694"),
)}

ISHARES_URL = ("https://www.blackrock.com/varnish-api/uk-retail01-product-data/product-data/api/v1/"
               "get-fund-document?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=ishares-uk"
               "&locale=en_GB&portfolioId={}&component=fundDownloadV2&userType=individual")
SPDR_URL = "https://www.ssga.com/library-content/products/fund-data/etfs/emea/holdings-daily-emea-en-{}.xlsx"
VANECK_PAGE = "https://www.vaneck.com/ie/en/investments/{}/overview/"
VANECK_FILE = "https://www.vaneck.com/ie/en/investments/{}/downloads/holdings/"
VANGUARD_URL = "https://www.de.vanguard/gpx/graphql"
VANGUARD_HEADERS = {"Content-Type": "application/json", "X-Consumer-ID": "de7"}
VANGUARD_FUNDS_QUERY = (
    "query FundsQuery($portIds: [String!]!) { funds(portIds: $portIds) { portId profile "
    '{ portId fundFullName identifiers(altIds: ["ISIN"]) { altIdValue } } } }')
VANGUARD_HOLDINGS_QUERY = (
    "query FundsHoldingsQuery($portIds: [String!], $lastItemKey: String) { "
    "borHoldings(portIds: $portIds) { holdings(limit: 1500, lastItemKey: $lastItemKey) { "
    "items { issuerName marketValuePercentage securityType effectiveDate bloombergIsoCountry } "
    "totalHoldings lastItemKey } } }")
MAX_BYTES = 20_000_000

# Euro area member states in 2026 (Bulgaria adopted the euro on 1 January 2026).
EURO_AREA = frozenset("AT BE BG HR CY EE FI FR DE GR IE IT LV LT LU MT NL PT SK SI ES".split())
# Bloomberg exchange codes. Unknown codes stop the calculation instead of
# silently counting as non-euro.
EURO_EXCHANGES = frozenset("GR GY GF GD GM GS GH FP NA IM SM BB ID FH AV PL GA LX".split())
OTHER_EXCHANGES = frozenset(
    "US UN UW UQ UA UR UP JP JT KS KQ LN TT PW CN CT HK SW SE SS DC NO AU SP IN IB IT TB MK "
    "IJ PM MM BZ SJ CH CG CS C1 C2 NZ".split())


def _decimal(text) -> Decimal:
    raw = str(text).strip().replace(",", "").replace("%", "").replace("$", "").strip()
    if raw.upper().startswith(("USD ", "EUR ")):
        raw = raw[4:]
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise LookthroughError("holding weight is not a number") from None
    if not value.is_finite():
        raise LookthroughError("holding weight is not finite")
    return value


def _summary(isin, issuer, as_of, rows, method):
    """rows: (weight_percent, is_euro). Weights must add up to about 100%."""
    total = sum((weight for weight, _ in rows), Decimal(0))
    if not rows or not Decimal(98) <= total <= Decimal(102):
        raise LookthroughError(f"{isin}: holding weights add up to {total}%, not about 100%")
    euro = sum((weight for weight, is_euro in rows if is_euro), Decimal(0))
    return {"isin": isin, "issuer": issuer, "holdings_date": as_of.isoformat(),
            "holdings": len(rows), "weight_total_pct": str(total),
            "euro_weight_pct": str(euro), "euro_share": str((euro / total).quantize(Decimal("0.0001"))),
            "euro_method": method}


# --- iShares (BlackRock SpreadsheetML workbook) --------------------------------

def _spreadsheetml(original: bytes) -> dict[str, list[list]]:
    text = original.decode("utf-8-sig")
    # The publisher writes bare '&' in fund names; escape only those.
    text = re.sub(r"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", text)
    ns = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise LookthroughError("iShares workbook is not readable SpreadsheetML") from None
    sheets = {}
    for sheet in root.findall("ss:Worksheet", ns):
        rows = []
        for row in sheet.findall(".//ss:Row", ns):
            rows.append([(cell.find("ss:Data", ns).text if cell.find("ss:Data", ns) is not None else None)
                         for cell in row.findall("ss:Cell", ns)])
        sheets[sheet.get("{urn:schemas-microsoft-com:office:spreadsheet}Name")] = rows
    return sheets


def parse_ishares(original: bytes, isin: str) -> dict:
    sheets = _spreadsheetml(original)
    facts = {row[0]: row[1] for row in sheets.get("Key Facts", []) if len(row) >= 2 and row[0]}
    if facts.get("ISIN") != isin:
        raise LookthroughError(f"{isin}: iShares workbook is for another fund")
    holdings = sheets.get("Holdings") or []
    if len(holdings) < 4 or holdings[1][:1] != ["as of"]:
        raise LookthroughError(f"{isin}: iShares holdings sheet has no date")
    as_of = datetime.strptime(holdings[1][1], "%d/%b/%Y").date()
    header = holdings[2]
    try:
        weight, currency = header.index("Weight (%)"), header.index("Market Currency")
    except ValueError:
        raise LookthroughError(f"{isin}: iShares holdings columns changed") from None
    rows = [(_decimal(row[weight]), row[currency] == "EUR") for row in holdings[3:]
            if len(row) > max(weight, currency) and row[weight] not in (None, "", "-")]
    return _summary(isin, "iShares", as_of, rows, "trading currency EUR")


# --- SPDR (SSGA xlsx) ------------------------------------------------------------

def _xlsx_rows(original: bytes) -> list[list]:
    from python_calamine import CalamineWorkbook
    try:
        book = CalamineWorkbook.from_filelike(BytesIO(original))
        return book.get_sheet_by_index(0).to_python()
    except Exception:
        raise LookthroughError("issuer workbook is not readable") from None


def parse_spdr(original: bytes, isin: str) -> dict:
    rows = _xlsx_rows(original)
    meta = {str(row[0]).strip(): row[1] for row in rows[:6] if row and row[0]}
    if meta.get("ISIN:") != isin:
        raise LookthroughError(f"{isin}: SPDR workbook is for another fund")
    as_of = datetime.strptime(str(meta.get("Holdings As Of:")), "%d-%b-%Y").date()
    header = next((i for i, row in enumerate(rows) if row[:1] == ["ISIN"]), None)
    if header is None:
        raise LookthroughError(f"{isin}: SPDR holdings header missing")
    names = rows[header]
    weight, currency = names.index("Percent of Fund"), names.index("Currency")
    values = []
    for row in rows[header + 1:]:
        if not any(str(cell).strip() for cell in row[:weight + 1]):
            break  # the holdings table ends before the publisher's disclaimer
        if len(row) > weight and row[weight] not in (None, "", "-"):  # '-' marks cash/currency lines
            values.append((_decimal(row[weight]), row[currency] == "EUR"))
    return _summary(isin, "SPDR", as_of, values, "trading currency EUR")


# --- VanEck (xlsx, identified by the fund page) ------------------------------------

def parse_vaneck(original: bytes, isin: str, page: bytes) -> dict:
    if isin.encode() not in page:
        raise LookthroughError(f"{isin}: VanEck fund page is for another fund")
    rows = _xlsx_rows(original)
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(rows[0][0]) if rows and rows[0] else "")
    if not match:
        raise LookthroughError(f"{isin}: VanEck holdings file has no date")
    as_of = date(int(match.group(3)), int(match.group(1)), int(match.group(2)))
    header = next((i for i, row in enumerate(rows) if row[:2] == ["Number", "Holding Name"]), None)
    if header is None:
        raise LookthroughError(f"{isin}: VanEck holdings header missing")
    values = []
    for row in rows[header + 1:]:
        if not isinstance(row[0], float):
            continue
        code = str(row[2]).split()[-1] if str(row[2]).strip() else "--"
        if code != "--" and code not in EURO_EXCHANGES | OTHER_EXCHANGES:
            raise LookthroughError(f"{isin}: unknown exchange code {code}")
        values.append((_decimal(row[6]), code in EURO_EXCHANGES))
    return _summary(isin, "VanEck", as_of, values, "listing on a euro-area exchange")


# --- Vanguard (GraphQL JSON, identified by its fund query) --------------------------

def parse_vanguard(funds_answer: bytes, pages: list[bytes], isin: str, port_id: str) -> dict:
    try:
        funds = json.loads(funds_answer)["data"]["funds"]
        ids = {item["altIdValue"] for fund in funds if fund["portId"] == port_id
               for item in fund["profile"]["identifiers"] or []}
    except (KeyError, TypeError, ValueError):
        raise LookthroughError(f"{isin}: Vanguard fund answer unreadable") from None
    if isin not in ids:
        raise LookthroughError(f"{isin}: Vanguard portfolio {port_id} is another fund")
    items, total = [], None
    for page in pages:
        try:
            block = json.loads(page)["data"]["borHoldings"][0]["holdings"]
        except (KeyError, TypeError, ValueError, IndexError):
            raise LookthroughError(f"{isin}: Vanguard holdings answer unreadable") from None
        items += block["items"]
        total = block["totalHoldings"]
    if total is None or len(items) != total:
        raise LookthroughError(f"{isin}: Vanguard returned {len(items)} of {total} holdings")
    dates = {item["effectiveDate"] for item in items}
    if len(dates) != 1:
        raise LookthroughError(f"{isin}: Vanguard holdings carry several dates")
    rows = [(_decimal(item["marketValuePercentage"]), item.get("bloombergIsoCountry") in EURO_AREA)
            for item in items if item.get("marketValuePercentage") is not None]
    return _summary(isin, "Vanguard", date.fromisoformat(dates.pop()), rows,
                    "issuer country in the euro area (no currency reported)")


# --- acquisition and archive ----------------------------------------------------------

def _get(client, url, **kwargs) -> bytes:
    response = client.get(url, **kwargs)
    response.raise_for_status()
    if len(response.content) > MAX_BYTES:
        raise LookthroughError("issuer response exceeds the size bound")
    return response.content


def _post(client, query, variables) -> bytes:
    body = json.dumps({"query": query, "variables": variables}).encode()
    response = client.post(VANGUARD_URL, content=body, headers=VANGUARD_HEADERS)
    response.raise_for_status()
    return response.content


def fetch_fund(client, source: FundSource) -> tuple[dict, dict[str, bytes], list[str]]:
    """Return the fund summary, the original responses and their URLs."""
    if source.issuer == "ishares":
        url = ISHARES_URL.format(source.reference)
        original = _get(client, url)
        return parse_ishares(original, source.isin), {"response-0.bin": original}, [url]
    if source.issuer == "spdr":
        url = SPDR_URL.format(source.reference)
        original = _get(client, url)
        return parse_spdr(original, source.isin), {"response-0.bin": original}, [url]
    if source.issuer == "vaneck":
        page_url, file_url = VANECK_PAGE.format(source.reference), VANECK_FILE.format(source.reference)
        page = _get(client, page_url)
        original = _get(client, file_url)
        return (parse_vaneck(original, source.isin, page),
                {"response-0.bin": page, "response-1.bin": original}, [page_url, file_url])
    if source.issuer == "vanguard":
        answer = _post(client, VANGUARD_FUNDS_QUERY, {"portIds": [source.reference]})
        pages, key = [], None
        for _ in range(5):
            page = _post(client, VANGUARD_HOLDINGS_QUERY, {"portIds": [source.reference], "lastItemKey": key})
            pages.append(page)
            key = json.loads(page)["data"]["borHoldings"][0]["holdings"].get("lastItemKey")
            if not key:
                break
        files = {"response-0.bin": answer, **{f"response-{i + 1}.bin": p for i, p in enumerate(pages)}}
        return (parse_vanguard(answer, pages, source.isin, source.reference), files,
                [VANGUARD_URL] * len(files))
    raise LookthroughError(f"{source.isin}: unsupported issuer")


def archive_fund(root: Path, summary: dict, files: dict[str, bytes], urls: list[str]) -> Path:
    payloads = {**files, "facts.json": json.dumps(summary, sort_keys=True).encode()}
    hashes = {name: sha256(body).hexdigest() for name, body in payloads.items()}
    digest = sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    parent = root / "fund-lookthrough" / summary["isin"] / summary["holdings_date"]
    folder = parent / digest
    temporary = None
    try:
        parent.mkdir(parents=True, exist_ok=True)
        if not folder.exists():
            temporary = Path(tempfile.mkdtemp(prefix=".fund-", dir=parent))
            for name, body in payloads.items():
                (temporary / name).write_bytes(body)
            manifest = {"schema_version": 1, "issuer": summary["issuer"], "isin": summary["isin"],
                        "holdings_date": summary["holdings_date"], "source_urls": urls,
                        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "files": hashes}
            (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2))
            try:
                os.rename(temporary, folder)
                temporary = None
            except FileExistsError:
                pass
        record_acquisition_receipt(folder, {"publisher": summary["issuer"], "isin": summary["isin"],
                                            "holdings_date": summary["holdings_date"]})
        return folder
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


def portfolio_euro_share(holdings: dict, funds: dict[str, dict]) -> dict:
    """Value-weighted euro share of the owner's equity funds."""
    equity = [fund for fund in holdings["summary"]["funds"] if fund["asset_class"] == "equity"]
    missing = sorted(fund["isin"] for fund in equity if fund["isin"] not in funds)
    if not equity or missing:
        raise LookthroughError("no look-through for " + ", ".join(missing or ["any equity fund"]))
    total = sum(Decimal(str(fund["value_eur"])) for fund in equity)
    euro = sum(Decimal(str(fund["value_eur"])) * Decimal(funds[fund["isin"]]["euro_share"]) for fund in equity)
    return {"equity_euro_share": float((euro / total).quantize(Decimal("0.0001"))),
            "portfolio_as_of": holdings["as_of"],
            "funds": [{"isin": fund["isin"], "name": fund["name"],
                       "equity_weight": float((Decimal(str(fund["value_eur"])) / total).quantize(Decimal("0.0001"))),
                       **{key: funds[fund["isin"]][key] for key in (
                           "issuer", "holdings_date", "holdings", "euro_share", "euro_method")}}
                      for fund in equity]}


def run(*, root: Path, apply: bool, client=None) -> dict:
    """Fetch every listed fund, archive it, and compute the owner's euro share."""
    from .portfolio_holdings import load_portfolio_holdings
    from .source_policy import managed_client, require_managed_client
    holdings = load_portfolio_holdings()
    wanted = {fund["isin"] for fund in holdings["summary"]["funds"] if fund["asset_class"] == "equity"}
    unknown = sorted(wanted - set(FUNDS))
    if unknown:
        raise LookthroughError("no registered issuer source for " + ", ".join(unknown))
    owns = client is None
    client = (require_managed_client(client) if client is not None else
              managed_client(timeout=90, follow_redirects=True,
                             headers={"User-Agent": "GlobalCapitalMonitor/0.2"}))
    funds, failures = {}, {}
    try:
        for isin in sorted(wanted):
            try:
                summary, files, urls = fetch_fund(client, FUNDS[isin])
                summary["bundle"] = archive_fund(root, summary, files, urls).name
                funds[isin] = summary
            except Exception as exc:  # keep going; the result says which fund failed
                failures[isin] = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        if owns:
            client.close()
    report = {"computed_at_utc": datetime.now(timezone.utc).isoformat(),
              "funds_read": len(funds), "failures": failures}
    if not failures:
        report.update(portfolio_euro_share(holdings, funds))
        if apply:
            from .owner_inputs import load_owner_inputs, save_owner_inputs
            current = load_owner_inputs()
            if current.get("is_example"):
                raise LookthroughError("save the other owner inputs first")
            keep = {field: current[field] for field in current.get("supplied_fields", [])}
            save_owner_inputs(None, {**keep, "equity_euro_share": report["equity_euro_share"]})
            report["applied_to_owner_inputs"] = True
    path = Path(os.environ.get("FINANCE_FUND_LOOKTHROUGH", "/data/maintenance/fund-lookthrough.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))
    return report


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true",
                        help="store the computed euro share as the owner's equity_euro_share")
    args = parser.parse_args()
    root = Path(os.environ.get("FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence"))
    report = run(root=root, apply=args.apply)
    print(json.dumps({key: report[key] for key in report if key != "funds"}, indent=2))
    return 0 if not report["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
