"""National-accounts surplus and profit-rate research with explicit assumptions.

The OECD 2025 harmonised input-output table has compensation, consumption of
fixed capital and net operating surplus components (1995–2022). These are
observable accounts, not automatically Marxian 'surplus value'. A source-
provenanced, normalized OECD component extract is required: never fabricate a
country, industry, self-employment imputation, or stock of productive capital.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
import csv
import json
import os

SOURCE = "OECD_IOT_2025_VALUE_ADDED_COMPONENTS"
REFERENCE = "https://www.oecd.org/en/data/datasets/input-output-tables.html"
ROOT = Path(os.environ.get("FINANCE_SURPLUS_DIR","/data/surplus"))
# Assumptions are deliberately exposed. 'Market industry' is a classification
# convention, not a settled Marxian productive/unproductive-labour distinction.
SCENARIOS = {
    "all_industries": set("ABCDEFGHIJKLMNOPQRSTU"),
    "market_broad": set("ABCDEFGHIJKLMNRS"),
    "market_narrow": set("ABCDEFGHIJ"),
}
NUMBERS = ("employee_compensation","consumption_fixed_capital",
           "net_operating_surplus")
OPTIONAL = ("imputed_selfemployed_compensation","net_fixed_capital_stock")
ACCOUNT_IDENTITY = ("gross_value_added","net_taxes_on_production")
ALLOWED = set(NUMBERS) | set(OPTIONAL) | set(ACCOUNT_IDENTITY) | {
    "country","year","isic_section","unit","currency","source_release",
    "original_table","source_url","imputation_method","capital_stock_source"}
MAX_ROWS = 100_000
MAX_SIZE = 50_000_000


class AccountingError(ValueError):
    pass


def number(value: str | None, name: str, *, required: bool=True) -> Decimal | None:
    if value is None or str(value).strip() == "":
        if required:
            raise AccountingError("Missing required "+name)
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AccountingError("Invalid numeric "+name) from exc
    if not d.is_finite():
        raise AccountingError("Nonfinite "+name)
    return d


def parse_oecd_normalized_csv(source: bytes, *, expected_sha256: str | None=None) -> dict:
    """Validated, provenance-tagged source extract; no guessed OECD CSV schema."""
    if len(source) > MAX_SIZE:
        raise AccountingError("Input accounting extract exceeds configured size")
    checksum = sha256(source).hexdigest()
    if expected_sha256 and checksum != expected_sha256:
        raise AccountingError("Source extract SHA256 mismatch")
    from io import StringIO
    try:
        raw = source.decode("utf-8-sig")
    except UnicodeError as exc:
        raise AccountingError("OECD extract must be UTF-8 CSV") from exc
    reader = csv.DictReader(StringIO(raw))
    if (not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames))
        or not set(NUMBERS).issubset(reader.fieldnames)
        or not {"country","year","isic_section","unit","currency",
                "source_release","original_table","source_url"}.issubset(reader.fieldnames)):
        raise AccountingError("Missing OECD accounting columns or duplicate headers")
    if set(reader.fieldnames) - ALLOWED:
        raise AccountingError("Unrecognized economics input columns")
    rows = []
    identities = set()
    for row in reader:
        if len(rows) >= MAX_ROWS:
            raise AccountingError("OECD extract exceeds row limit")
        country = row["country"].strip().upper()
        section = row["isic_section"].strip().upper()
        year = int(row["year"])
        if (len(country) != 2 or not country.isalpha()
            or section not in SCENARIOS["all_industries"]
            or not 1995 <= year <= 2022):
            raise AccountingError("Unexpected ISO country, ISIC section or OECD vintage year")
        identity = (country,year,section)
        if identity in identities:
            raise AccountingError("Duplicate country/year/industry record")
        identities.add(identity)
        if row["source_release"] != SOURCE or row["source_url"] != REFERENCE:
            raise AccountingError("Unverified OECD source release/URL contract")
        unit = row["unit"].strip()
        currency = row["currency"].strip().upper()
        if unit not in ("millions_current_currency","millions_usd"):
            raise AccountingError("Unsupported value-added accounting unit")
        if len(currency) != 3 or not currency.isalpha():
            raise AccountingError("Missing reported currency")
        numeric = {key:number(row.get(key),key) for key in NUMBERS}
        optional = {key:number(row.get(key),key,required=False) for key in OPTIONAL}
        identity = {key:number(row.get(key),key,required=False)
                    for key in ACCOUNT_IDENTITY}
        if (identity["gross_value_added"] is None) != (identity["net_taxes_on_production"] is None):
            raise AccountingError("Gross value added and net taxes must be supplied together")
        if identity["gross_value_added"] is not None:
            # OECD IOT identities are in identical current-price reporting units.
            # Optional original-account balancing detects extraction/mapping mistakes;
            # it does not authenticate the publisher ZIP or provenance.
            gva = identity["gross_value_added"]
            calculated = (numeric["employee_compensation"] +
                          numeric["consumption_fixed_capital"] +
                          numeric["net_operating_surplus"] +
                          identity["net_taxes_on_production"])
            tolerance = max(Decimal("0.01"),abs(gva)*Decimal("0.000001"))
            if gva < 0 or abs(calculated-gva) > tolerance:
                raise AccountingError("OECD value-added component identity does not reconcile")
        if numeric["employee_compensation"] < 0 or numeric["consumption_fixed_capital"] < 0:
            raise AccountingError("Employee pay and depreciation cannot be negative")
        if (optional["imputed_selfemployed_compensation"] is not None
            and (optional["imputed_selfemployed_compensation"] < 0
            or not row.get("imputation_method"))):
            raise AccountingError("Self-employment compensation needs a documented methodology")
        if (optional["net_fixed_capital_stock"] is not None
            and (optional["net_fixed_capital_stock"] <= 0
            or not row.get("capital_stock_source"))):
            raise AccountingError("Capital stock needs independently documented provenance")
        rows.append({
            "country":country,"year":year,"isic_section":section,
            "currency":currency,"unit":unit,
            "original_table":row["original_table"].strip(),
            "source_release":SOURCE,"source_url":REFERENCE,
            "imputation_method":row.get("imputation_method",""),
            "capital_stock_source":row.get("capital_stock_source",""),
            **{key: str(v) for key,v in {**numeric,**optional,**identity}.items()
               if v is not None},
        })
    if not rows:
        raise AccountingError("No verified accounting rows")
    return {
        "schema_version":1,"release":SOURCE,"source_url":REFERENCE,
        "normalized_extract_sha256":checksum,
        "rows":rows,"record_count":len(rows),
        "classification":"OECD IOT 2025 national-industry ISIC Rev4 components",
        "source_authentication":"operator_supplied_csv_hash_only_not_independently_authenticated",
        "accounting_identity_rows":sum("gross_value_added" in x for x in rows),
        "caveat":("Net operating surplus is a national-accounts aggregate. "
                  "The Marxian distinction productive/unproductive labour "
                  "and self-employed value/capital cannot be read directly "
                  "from standard national accounts."),
    }


def compute_country_year(dataset: dict, *, country: str, year: int,
                         scenario: str="all_industries",
                         adjust_selfemployment: bool=False) -> dict:
    """Compute explicit national-accounts ratios, plus sensitivity envelopes."""
    if scenario not in SCENARIOS:
        raise AccountingError("Unknown labour theory classification assumption")
    rows = [x for x in dataset["rows"]
            if x["country"] == country and x["year"] == year
            and x["isic_section"] in SCENARIOS[scenario]]
    if not rows:
        return {"status":"no_data","country":country,"year":year,
                "scenario":scenario,"reason":"No source-reported industries"}
    units = {(x["currency"],x["unit"]) for x in rows}
    if len(units) != 1:
        raise AccountingError("Do not mix currencies or denominators in surplus accounts")
    sum_comp = sum((Decimal(x["employee_compensation"]) for x in rows),Decimal(0))
    sum_cfc = sum((Decimal(x["consumption_fixed_capital"]) for x in rows),Decimal(0))
    sum_surplus = sum((Decimal(x["net_operating_surplus"]) for x in rows),Decimal(0))
    if sum_comp <= 0:
        raise AccountingError("Nonpositive employee compensation denominator")
    missing_imputation = [x["isic_section"] for x in rows
                          if "imputed_selfemployed_compensation" not in x]
    missing_stock = [x["isic_section"] for x in rows
                     if "net_fixed_capital_stock" not in x]
    identity_rows = [x["isic_section"] for x in rows
                     if "gross_value_added" in x]
    imputed = sum((Decimal(x.get("imputed_selfemployed_compensation","0"))
                   for x in rows), Decimal(0))
    if adjust_selfemployment and missing_imputation:
        raise AccountingError("Self-employment-adjusted calculation requires documented values for all included industries")
    if adjust_selfemployment and imputed > sum_surplus:
        raise AccountingError("Cannot impute self-employment from net surplus above available surplus")
    v = sum_comp + imputed if adjust_selfemployment else sum_comp
    s = sum_surplus - imputed if adjust_selfemployment else sum_surplus
    ratio = s / v * Decimal(100) if v > 0 else None
    stock = (sum((Decimal(x["net_fixed_capital_stock"]) for x in rows),Decimal(0))
             if not missing_stock else None)
    profit_rate = (s / stock * Decimal(100)) if stock is not None and stock>0 else None
    return {
        "status":"accounting_sensitivity_not_marxian_exploitation_rate",
        "country":country,"year":year,"scenario":scenario,
        "included_isic_sections":sorted({x["isic_section"] for x in rows}),
        "excluded_isic_sections":sorted(SCENARIOS["all_industries"]-SCENARIOS[scenario]),
        "currency":rows[0]["currency"],"unit":rows[0]["unit"],
        "source_release":SOURCE, "source_url":REFERENCE,
        "sectors_observed":len(rows),
        "reported_isic_sections":sorted({x["isic_section"] for x in rows}),
        "unreported_in_scope_sections":sorted(
            SCENARIOS[scenario] - {x["isic_section"] for x in rows}),
        "complete_assumed_industry_scope":(
            {x["isic_section"] for x in rows} == SCENARIOS[scenario]),
        "employee_compensation":str(sum_comp),
        "net_operating_surplus":str(sum_surplus),
        "consumption_fixed_capital":str(sum_cfc),
        "selfemployment_adjusted":adjust_selfemployment,
        "selfemployment_imputed":str(imputed) if adjust_selfemployment else None,
        "net_surplus_to_employee_pay_pct":str(sum_surplus/sum_comp*Decimal(100)),
        "assumed_surplus_to_variable_capital_pct":str(ratio) if ratio is not None else None,
        "observed_net_capital_stock":str(stock) if stock is not None else None,
        "net_surplus_over_net_capital_stock_pct":str(profit_rate) if profit_rate is not None else None,
        "capital_stock_coverage_complete":not missing_stock,
        "missing_capital_stock_sectors":missing_stock,
        "missing_selfemployment_imputation_sectors":missing_imputation,
        "source_extract_sha256":dataset["normalized_extract_sha256"],
        "source_authentication":dataset.get(
            "source_authentication",
            "operator_supplied_csv_hash_only_not_independently_authenticated"),
        "accounting_identity_reconciled_sections":sorted(identity_rows),
        "accounting_identity_coverage_complete":len(identity_rows)==len(rows),
        "limitation":("Sector inclusion is a user-visible theoretical assumption; reported "
                      "industry totals cover only the actually supplied ISIC rows, "
                      "and omitted industries cannot be treated as zero. "
                      "OECD net operating surplus is not observed Marxian surplus "
                      "value; nominal net fixed capital stock is not the complete "
                      "Marxian capital advanced. Unpaid domestic labour, productive "
                      "versus unproductive activities, taxes, self-employment, "
                      "fixed/variable capital timing and cross-border value "
                      "transfers remain methodological choices. No rates are "
                      "claimed when source capital stock is absent."),
    }


def store(dataset: dict, *, root: Path=ROOT) -> Path:
    root.mkdir(parents=True,exist_ok=True)
    path = root / "oecd_iot_2025_normalized.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != dataset:
        raise AccountingError("Different OECD extract requires explicit reviewed version migration")
    with NamedTemporaryFile("w",encoding="utf-8",dir=root,prefix=".oecd-",delete=False) as temp:
        json.dump(dataset,temp,indent=2)
        temporary = Path(temp.name)
    try:
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def read(root: Path=ROOT) -> dict | None:
    path = root / "oecd_iot_2025_normalized.json"
    if not path.is_file():
        return None
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("release") != SOURCE or result.get("schema_version") != 1:
        raise AccountingError("Invalid OECD surplus data provenance")
    return result


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Import source-verified OECD IOT value-added components")
    parser.add_argument("--csv",type=Path,required=True)
    parser.add_argument("--sha256",required=True,help="SHA256 of audited local normalized OECD CSV")
    parser.add_argument("--root",type=Path,default=ROOT)
    args = parser.parse_args()
    parsed = parse_oecd_normalized_csv(args.csv.read_bytes(),expected_sha256=args.sha256)
    path=store(parsed,root=args.root)
    print(json.dumps({"stored":str(path),"source":SOURCE,
                      "records":parsed["record_count"],
                      "countries":sorted(set(row["country"] for row in parsed["rows"]))},indent=2))


if __name__ == "__main__":
    main()
