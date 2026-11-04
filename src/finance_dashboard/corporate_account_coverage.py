"""Read-only field coverage from validated retained corporate-account originals.

These inventories measure the files actually queried and retained. A variable
absent from those queries is not proved unavailable from the publisher. Sector
accounts, whole-economy accounts and industry accounts remain distinct scopes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re

from .bis import ProviderError
from .catalog import load_documents
from .constructed_source_reconciliation import constructed_source
from .oecd_corporate import OECD_MEMBER_ISO3
from .source_reconciliation import EvidenceError, _selected_manifest, _original_file


SOURCE_IDS = (
    "profit.oecd38.corporate_gross_surplus_gdp",
    "profit.eu27.corporate_operating_surplus_gdp",
    "profit.eu27.nonfinancial_gross_surplus_value_added",
)


def _coverage(pairs, *, universe):
    """Unique reported geography/year pairs; no interpolation or row summation."""
    years, countries = defaultdict(set), defaultdict(set)
    for country, year in set(pairs):
        years[year].add(country); countries[country].add(year)
    return {"country_year_pairs": sum(len(value) for value in years.values()),
            "geographies_ever_reported": len(countries),
            "first_year": min(years) if years else None, "last_year": max(years) if years else None,
            "countries_by_year": {str(year): sorted(value) for year, value in sorted(years.items())},
            "missing_countries_by_year": {str(year): sorted(set(universe) - value)
                                          for year, value in sorted(years.items())},
            "country_periods": {country: sorted(value) for country, value in sorted(countries.items())}}


def _finite(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProviderError("Invalid native corporate-account inventory value") from exc
    if not number.is_finite():
        raise ProviderError("Nonfinite native corporate-account inventory value")
    return number


def inventory_oecd_account_rows(original: bytes) -> list[dict]:
    """Inventory native dimensions after the existing original-source boundary.

    This helper is not an ingestion endpoint. Its caller first verifies every
    raw dependency, request identity and accounting dimensions using the
    canonical constructed-source reconciliation boundary.
    """
    reader = csv.DictReader(io.StringIO(original.decode("utf-8-sig")))
    required = {"SECTOR", "ACCOUNTING_ENTRY", "TRANSACTION", "REF_AREA", "TIME_PERIOD",
                "OBS_VALUE", "UNIT_MEASURE", "UNIT_MULT", "CURRENCY"}
    if (not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames))
            or not required <= set(reader.fieldnames)):
        raise ProviderError("Native corporate-account inventory fields changed")
    groups, rows, missing, currencies = defaultdict(set), Counter(), Counter(), defaultdict(set)
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ProviderError("Native corporate-account inventory row width invalid")
        if (not re.fullmatch(r"[0-9]{4}", row["TIME_PERIOD"])
                or row["REF_AREA"] not in OECD_MEMBER_ISO3):
            raise ProviderError("Native corporate-account inventory country/year invalid")
        identity = tuple(row[key] for key in ("SECTOR", "ACCOUNTING_ENTRY", "TRANSACTION",
                                               "UNIT_MEASURE", "UNIT_MULT"))
        if row["OBS_VALUE"] == "":
            missing[identity] += 1
            continue
        _finite(row["OBS_VALUE"])
        groups[identity].add((row["REF_AREA"], int(row["TIME_PERIOD"])))
        rows[identity] += 1; currencies[identity].add(row["CURRENCY"])
    return [{"sector": key[0], "accounting_entry": key[1], "transaction": key[2],
             "unit_measure": key[3], "unit_multiplier": int(key[4]),
             "currencies": sorted(currencies[key]), "numeric_source_rows": rows[key],
             "missing_source_rows": missing[key],
             "coverage": _coverage(groups[key], universe=OECD_MEMBER_ISO3),
             "account_scope": "institutional_sector" if key[0] in {"S11", "S12"} else "whole_economy",
             "industry_dimension_reported": False}
            for key in sorted(set(groups) | set(missing))]


def inventory_eurostat_account_rows(original: bytes, *, dataset: str) -> list[dict]:
    """Inventory a fully filtered native cube already checked by the boundary."""
    payload = json.loads(original, parse_float=Decimal)
    dimensions = payload["dimension"]
    def singleton(key):
        index = dimensions[key]["category"]["index"]
        if len(index) != 1 or next(iter(index.values())) != 0:
            raise ProviderError("Ambiguous native Eurostat inventory dimension")
        return next(iter(index))
    sector, transaction, geo, unit = (singleton(key) for key in ("sector", "na_item", "geo", "unit"))
    values = payload["value"]
    pairs = set()
    for year, index in dimensions["time"]["category"]["index"].items():
        if str(index) in values and values[str(index)] is not None:
            _finite(values[str(index)]); pairs.add((geo, int(year)))
    return [{"dataset": dataset, "sector": sector, "transaction": transaction,
             "accounting_entry": singleton("direct") if "direct" in dimensions else None,
             "unit_measure": unit, "unit_multiplier": 6 if unit == "CP_MEUR" else 0,
             "currencies": ["EUR"] if unit == "CP_MEUR" else [],
             "numeric_source_rows": len(pairs),
             "coverage": _coverage(pairs, universe={geo}),
             "account_scope": "published_sector_ratio" if dataset == "nasa_10_ki" else
                 "institutional_sector" if sector in {"S11", "S12"} else "whole_economy",
             "industry_dimension_reported": False}]


def _required_coverage(inventory):
    # These are interpretations of observed native fields, not a source registry
    # or a claim about fields outside the retained queries.
    fields = {"gross_operating_surplus": {"B2G", "B2A3G"}, "gross_value_added": {"B1G"},
              "compensation_of_employees": {"D1"}, "net_operating_surplus": {"B2N"},
              "consumption_of_fixed_capital": {"P51C"}, "other_taxes_less_subsidies_on_production": {"D29X39"},
              # No asset-balance-sheet dimension is present in these retained
              # current-account queries. Do not invent a publisher asset code.
              "net_fixed_capital_stock": set()}
    result = {}
    for name, transactions in fields.items():
        result[name] = {}
        for sector in ("S11", "S12"):
            selected = [item for item in inventory if item["sector"] == sector
                        and item["transaction"] in transactions
                        and item["accounting_entry"] in {"D", "RECV"}]
            pairs = {(country, year) for item in selected
                     for country, years in item["coverage"]["country_periods"].items() for year in years}
            detail = _coverage(pairs, universe=set().union(*(set(i["coverage"]["country_periods"]) for i in selected)))
            # Exact country/year memberships already appear once in each
            # native-field inventory. Requirement summaries refer to those
            # fields instead of duplicating every membership several times.
            coverage = {key: detail[key] for key in
                        ("country_year_pairs", "geographies_ever_reported", "first_year", "last_year")}
            coverage["country_counts_by_year"] = {year: len(countries)
                                                   for year, countries in detail["countries_by_year"].items()}
            result[name][sector] = {**coverage,
                "native_fields": [{key: item[key] for key in ("sector", "transaction", "accounting_entry", "unit_measure")}
                                  for item in selected],
                "status": "reported_in_retained_queried_originals" if pairs else "not_present_in_retained_queried_originals",
                "global_source_availability_assessed": False}
    result["matched_industry_gross_value_added"] = {
        "country_year_pairs": 0, "industry_dimension_reported": False,
        "status": "not_present_in_retained_queried_originals",
        "reason": "Retained inputs are institutional-sector/whole-economy accounts and an EU27 sector ratio. Neither S1 nor S11/S12 aggregate GVA is matched-industry GVA.",
        "global_source_availability_assessed": False}
    return result


def _scoped_required_coverage(sources):
    """Keep country counts source-specific; never count EU27 as another country."""
    by_source = {source["series_id"]: source["required_variable_coverage"] for source in sources
                 if source["original_source_hash_verified"]}
    result = {}
    for variable in _required_coverage([]):
        scoped = {sid: fields[variable] for sid, fields in by_source.items()}
        if variable == "matched_industry_gross_value_added":
            empty = all(item["country_year_pairs"] == 0 for item in scoped.values())
        else:
            empty = all(item[sector]["country_year_pairs"] == 0 for item in scoped.values()
                        for sector in ("S11", "S12"))
        result[variable] = {"source_coverage": scoped,
            "country_year_pairs": 0 if by_source and empty else None,
            "validated_retained_sources_checked": len(by_source),
            "status": "not_present_in_retained_queried_originals" if by_source and empty else
                "reported_in_named_retained_sources" if by_source else "no_validated_retained_originals",
            "global_source_availability_assessed": False,
            "counts_are_source_specific": True}
    return result


def _retained_inputs(root, definition):
    # Reuse the complete canonical boundary, including all WDI dependencies of
    # the OECD construction. A second receipt/hash check prevents mixing a new
    # acquisition selected between validation and field inventory.
    values, proof = constructed_source(root, definition, _selected_manifest, _original_file)
    identity = {"provider": definition["provider"], "source_key": definition["source_key"],
                "series_id": definition["id"]}
    retrieved, digest, path, manifest, method = _selected_manifest(root / "responses" / definition["id"], identity)
    if digest != proof["source_manifest_sha256"] or method != "acquisition_receipt":
        raise ProviderError("Corporate-account original selection changed or receipt missing")
    raw = [_original_file(path.parent, source, f"response-{index}.bin", binary=True)[0]
           for index, source in enumerate(manifest["sources"])]
    return raw, {"series_id": definition["id"], "status": "verified_original_variable_coverage",
                 "original_source_hash_verified": True, "selection_method": method,
                 "source_manifest_sha256": digest, "evidence_retrieved_at_utc": retrieved.isoformat(),
                 "sources": [{key: source[key] for key in ("file", "url", "sha256", "bytes")}
                             for source in manifest["sources"]],
                 "constructed_series_years": sorted(day.year for day in values)}


class _UnItemLabels(HTMLParser):
    def __init__(self):
        super().__init__(); self.labels = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and str(attrs.get("id", "")).lower().startswith("item_code%3a"):
            self.labels[attrs["id"].lower().split("%3a", 1)[1]] = attrs.get("name")


UN_INVESTIGATION_FILES = {
    "un-s11-original.html": "5def420a551a97f0bf3002ab89da5edf09ff11d814cfa1d4e7d104b80bc45b97",
    "un-sector/download-errors.json": "159ba39c479b079cc9fb498dee0cfdce76bdb7fed63ba769388d574d2d8c5701",
    "un-sector/http-s11-b2g-error.html": "8ef3da215ff1000f05581814f1e5ef349a5f18b070b18bec5eb0507e967b1d8a",
    "un-sector/https-s11-b2g-error.html": "8ef3da215ff1000f05581814f1e5ef349a5f18b070b18bec5eb0507e967b1d8a",
}


def read_un_corporate_source_investigation(root):
    """Read a pinned native-page/error acquisition, never a free-editable audit."""
    parent = Path(root) / "multinationals" / "2026-11-04"
    if not parent.exists():
        return {"status": "missing_original_un_source_investigation", "original_source_hash_verified": False}
    try:
        bodies = {}
        for name, digest in UN_INVESTIGATION_FILES.items():
            path = parent / name
            if path.is_symlink() or path.stat().st_size > 150_000:
                raise ValueError("file identity")
            bodies[name] = path.read_bytes()
            if sha256(bodies[name]).hexdigest() != digest:
                raise ValueError("file digest")
        labels = _UnItemLabels(); labels.feed(bodies["un-s11-original.html"].decode())
        if (labels.labels.get("32") != "Acquisitions less disposals of non-produced non-financial assets"
                or labels.labels.get("10") != "OPERATING SURPLUS, GROSS"):
            raise ValueError("native item identity")
        errors = json.loads(bodies["un-sector/download-errors.json"])
        if len(errors) != 2:
            raise ValueError("error identity")
        for scheme, error in zip(("http", "https"), errors, strict=True):
            name = f"{scheme}-s11-b2g-error.html"
            if (error["url"] != f"{scheme}://data.un.org/Handlers/DownloadHandler.ashx?DataFilter=group_code:403;item_code:10&DataMartId=SNA&Format=csv"
                    or error["http_status"] != 404 or error["error_body_file"] != name
                    or error["bytes"] != len(bodies["un-sector/" + name])
                    or error["error_body_sha256"] != UN_INVESTIGATION_FILES["un-sector/" + name]
                    or datetime.fromisoformat(error["observed_at_utc"]).utcoffset() is None):
                raise ValueError("error acquisition identity")
        return {"status": "verified_original_un_source_investigation", "original_source_hash_verified": True,
                "files_sha256": UN_INVESTIGATION_FILES, "prior_reference_item": "32",
                "prior_reference_actual_label": labels.labels["32"],
                "correct_s11_operating_surplus_item": "10", "correct_item_label": labels.labels["10"],
                "correct_view_url": "https://data.un.org/Data.aspx?d=SNA&f=group_code%3A403%3Bitem_code%3A10",
                "export_acquisitions": errors, "country_period_coverage_measured": False,
                "table_wide_country_filter_is_variable_coverage": False,
                "first_publication_verified": False,
                "scope": "The pinned native page identifies item32 as a capital-account asset transaction and item10 as gross operating surplus. Corrected export requests returned404 over HTTP and HTTPS. No country/period coverage is inferred from a table-wide country filter; this is an investigation record, not a UN macro series."}
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        return {"status": "invalid_original_un_source_investigation", "original_source_hash_verified": False}


def read_corporate_account_coverage(root: Path) -> dict:
    """Measure retained native variable×sector coverage, without database writes."""
    root = Path(root)
    registry = {item["id"]: item for item in load_documents()[0]["series"]}
    sources, inventory = [], []
    for sid in SOURCE_IDS:
        try:
            raw, source = _retained_inputs(root, registry[sid])
            if sid == SOURCE_IDS[0]:
                items = inventory_oecd_account_rows(raw[0])
                source["dependency_roles"] = ["native_sector_accounts", "WDI_USD_GDP_weights", "restricted_WDI_local_GDP_denominators"]
            elif sid == SOURCE_IDS[1]:
                items = [item for body in raw for item in inventory_eurostat_account_rows(body, dataset="nasa_10_nf_tr")]
            else:
                items = inventory_eurostat_account_rows(raw[0], dataset="nasa_10_ki")
            source["native_field_inventory"] = items
            source["required_variable_coverage"] = _required_coverage(items)
            sources.append(source); inventory.extend(items)
        except (EvidenceError, ProviderError, KeyError, TypeError, ValueError, OSError) as exc:
            sources.append({"series_id": sid, "status": "missing_or_invalid_original_corporate_account_evidence",
                            "original_source_hash_verified": False,
                            "failure_code": exc.code if isinstance(exc, EvidenceError) else "native_account_inventory_invalid"})
    verified = [source for source in sources if source["original_source_hash_verified"]]
    return {"schema_version": 1, "status": "verified_original_corporate_account_coverage" if len(verified) == len(SOURCE_IDS)
                else "partial_original_corporate_account_coverage" if verified else "missing_original_corporate_account_coverage",
            "original_source_hash_verified": len(verified) == len(SOURCE_IDS),
            "source_count": sum(len(source["sources"]) for source in verified), "sources": sources,
            "native_field_combinations": len(inventory),
            "required_variable_coverage": _scoped_required_coverage(sources),
            "un_source_investigation": read_un_corporate_source_investigation(root),
            "database_writes": 0, "aggregate_produced": False,
            "worldwide_population_verified": False, "first_publication_verified": False,
            "full_history_verified": False,
            "coverage_semantics": "Unique geography/year pairs within each native variable×sector×accounting-entry and source. OECD countries and the EU27 geographic aggregate are not added into a world count. Missing-variable zeros refer only to retained queried files, not all publisher data. S1 whole-economy GVA, S11/S12 sector GVA, national GDP and matched-industry GVA are distinct."}
