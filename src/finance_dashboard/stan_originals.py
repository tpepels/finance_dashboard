"""OECD STAN 2025 original industry accounts: one verified structured-source path.

The source has country/industry/measure/year dimensions. It cannot be collapsed
into one scalar macro series or automatically satisfy L01/L02/L03 original roles.
Validated publisher CSVs are retained byte-for-byte in immutable bundles with
the project's existing acquisition receipts. No observation database writes.
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .bis import ProviderError
from .oecd_corporate import OECD_MEMBER_ISO3
from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt
from .source_reconciliation import EvidenceError, _original_file, _selected_manifest


STAN_FLOW = "OECD.STI.PIE,DSD_STAN@DF_STAN_2025,1.0"
STAN_DATAFLOW_ID = "OECD.STI.PIE:DSD_STAN@DF_STAN_2025(1.0)"
STAN_ROOT = "https://sdmx.oecd.org/public/rest/data"
STAN_MEASURES = ("B1G", "D1", "B2N", "P51C", "D29X39")
# Four candidate measures were confirmed in the 2026-11-05 Portugal probe.
# B2N returned no selection for PRT/_T/2020. Never assume it is absent
# historically or insert zeros; archive four-measure evidence as partial.
STAN_VERIFIED_PORTUGAL_MEASURES = ("B1G", "D1", "P51C", "D29X39")
# Additional publisher candidates from OECD STAN income-account terminology.
# A recognized code is NOT proof of availability in the current STAN dataflow;
# --resolve-surplus must verify an actual native CSV response.
STAN_SURPLUS_CANDIDATES = ("B2N_B3N", "B2G_B3G")
STAN_ALLOWED_MEASURES = frozenset((*STAN_MEASURES, *STAN_SURPLUS_CANDIDATES))
STAN_FIELDS = frozenset({
    "FREQ", "REF_AREA", "ACTIVITY", "MEASURE", "PRICE_BASE",
    "UNIT_MEASURE", "TIME_PERIOD", "OBS_VALUE",
})
MAX_STAN_SOURCE_BYTES = 100_000_000
MAX_STAN_SOURCE_ROWS = 1_000_000
IDENTITY = "OECD_STAN_2025_INDUSTRY_ORIGINAL"


def stan_source_request(country: str, start_year: int = 1970, *,
                        measures: tuple[str, ...] | None = None,
                        activity: str | None = None,
                        end_year: int | None = None) -> tuple[str, dict]:
    """Exact native six-dimension key from the OECD 2025 Data Explorer.

    Omitted activity means all published industries. Small, explicitly bounded
    queries are used for live identity diagnostics, never treated as history.
    """
    if country not in OECD_MEMBER_ISO3 or not 1970 <= start_year <= date.today().year:
        raise ValueError("invalid_stan_country_or_period")
    selected = STAN_MEASURES if measures is None else tuple(measures)
    if (not selected or len(selected) != len(set(selected))
            or any(value not in STAN_ALLOWED_MEASURES for value in selected)):
        raise ValueError("invalid_stan_native_measure")
    if (activity is not None and not re.fullmatch(r"[A-Z0-9_]{1,32}", activity)):
        raise ValueError("invalid_stan_activity")
    if end_year is not None and not start_year <= end_year <= date.today().year:
        raise ValueError("invalid_stan_period_window")
    key = "A." + country + "." + (activity or "") + "." + "+".join(selected) + ".V.XDC"
    params = {"startPeriod": str(start_year),
              "dimensionAtObservation": "AllDimensions"}
    if end_year is not None:
        params["endPeriod"] = str(end_year)
    return (f"{STAN_ROOT}/{STAN_FLOW}/{key}", params)


def stan_source_identity(country: str, start_year: int, *,
                         measures: tuple[str, ...] | None = None) -> dict:
    selection = STAN_MEASURES if measures is None else tuple(measures)
    url, _ = stan_source_request(country, start_year, measures=selection)
    return {"provider": "OECD_STAN", "country": country,
            "source_key": STAN_FLOW + "/" + url.split(STAN_FLOW + "/", 1)[-1],
            "requested_since": start_year,
            "native_measures": list(selection)}



def parse_stan_original_csv(raw: bytes, *, country: str, start_year: int,
                            expected_measures: tuple[str, ...] | None = None,
                            expected_activity: str | None = None,
                            end_year: int | None = None) -> dict:
    """Validate all requested native dimensions; summarize exact country-industry-years.

    Financial identities are diagnostics only: B2N includes mixed income and
    these source codes do not prove a pure Marxian surplus-value numerator.
    Report every source status flag without assuming it denotes official data.
    """
    stan_source_request(country, start_year, measures=expected_measures,
                        activity=expected_activity, end_year=end_year)
    allowed_measures = STAN_ALLOWED_MEASURES if expected_measures is None else expected_measures
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_STAN_SOURCE_BYTES:
        raise ProviderError("STAN original response outside permitted byte bounds")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ProviderError("STAN original source is not UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text))
    if (not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames))
            or not STAN_FIELDS <= set(reader.fieldnames)):
        raise ProviderError("STAN original dimensions are missing")
    fields = set(reader.fieldnames)
    counts, flags, currencies, multipliers = Counter(), Counter(), set(), set()
    missing = Counter()
    values = {}
    metadata = {}
    seen = set()
    years, industries = set(), set()
    row_count = 0
    for row in reader:
        row_count += 1
        if row_count > MAX_STAN_SOURCE_ROWS:
            raise ProviderError("STAN source exceeds bounded native row count")
        if None in row or any(value is None for value in row.values()):
            raise ProviderError("STAN row width changed")
        activity, transaction, period = (
            row["ACTIVITY"], row["MEASURE"], row["TIME_PERIOD"])
        if (row["FREQ"] != "A" or row["REF_AREA"] != country
                or row["PRICE_BASE"] != "V" or row["UNIT_MEASURE"] != "XDC"
                or transaction not in allowed_measures
                or (expected_activity is not None and activity != expected_activity)
                or not re.fullmatch(r"[A-Z0-9_]{1,32}", activity)
                or not re.fullmatch(r"[0-9]{4}", period)
                or (end_year is not None and int(period) > end_year)
                or not start_year <= int(period) <= date.today().year):
            raise ProviderError("STAN source dimension identity is inconsistent")
        if "DATAFLOW" in fields and row["DATAFLOW"] != STAN_DATAFLOW_ID:
            raise ProviderError("STAN publisher dataflow identity changed")
        key = (activity, transaction, int(period))
        if key in seen:
            raise ProviderError("Duplicate STAN original observation")
        seen.add(key)
        unit_mult = row.get("UNIT_MULT", "")
        currency = row.get("CURRENCY", "")
        status = row.get("OBS_STATUS", "")
        if unit_mult and not re.fullmatch(r"-?[0-9]{1,2}", unit_mult):
            raise ProviderError("STAN original unit multiplier invalid")
        if currency and not re.fullmatch(r"[A-Z]{3}", currency):
            raise ProviderError("STAN original currency label invalid")
        multipliers.add(unit_mult or "unreported")
        currencies.add(currency or "unreported")
        flags[status or "unreported"] += 1
        original = row["OBS_VALUE"]
        if original in ("", ".", ":", "NA", "N/A"):
            missing[transaction] += 1
            continue
        try:
            number = Decimal(original)
            if not number.is_finite():
                raise InvalidOperation
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ProviderError("STAN original number is invalid") from exc
        counts[transaction] += 1
        industries.add(activity)
        years.add(int(period))
        group_key = (activity, int(period))
        values.setdefault(group_key, {})[transaction] = number
        metadata.setdefault(group_key, {})[transaction] = (unit_mult, currency)
    if not counts:
        raise ProviderError("STAN publisher response contains no numeric observations")
    residuals = []
    incompatible_units = 0
    for (activity, year), sample in values.items():
        if not set(STAN_MEASURES) <= set(sample):
            continue
        unit_identity = set(metadata[(activity, year)].values())
        if len(unit_identity) != 1:
            incompatible_units += 1
            continue
        residual = sample["B1G"] - (sample["D1"] + sample["B2N"]
                                   + sample["P51C"] + sample["D29X39"])
        residuals.append({"activity": activity, "year": year, "residual": residual})
    residuals.sort(key=lambda item: (-abs(item["residual"]), item["activity"], item["year"]))
    return {
        "schema_version": 1,
        "dataset": "OECD_STAN_2025", "country": country,
        "source_dataflow_field_verified": "DATAFLOW" in fields,
        "native_frequency": "A", "native_price_basis": "V",
        "native_unit_code": "XDC",
        "requested_from_year": start_year,
        "source_rows": row_count,
        "numeric_observations": sum(counts.values()),
        "missing_original_values": dict(sorted(missing.items())),
        "native_measure_observation_counts": dict(sorted(counts.items())),
        "missing_candidate_measures": sorted(set(STAN_MEASURES) - set(counts)),
        "reported_industries": len(industries),
        "reported_years": sorted(years),
        "native_status_flag_counts": dict(sorted(flags.items())),
        "source_estimate_flags_interpreted": False,
        "reported_currency_codes": sorted(currencies),
        "reported_unit_multipliers": sorted(multipliers),
        "matched_five_measure_industry_years": len(residuals),
        "unit_incompatible_five_measure_industry_years": incompatible_units,
        "nonzero_nominal_income_identity_residuals": sum(
            item["residual"] != 0 for item in residuals),
        "largest_absolute_identity_residual_native": (
            str(abs(residuals[0]["residual"])) if residuals else None),
        "largest_identity_residual_examples": [
            {"activity": item["activity"], "year": item["year"],
             "residual_native": str(item["residual"])}
            for item in residuals[:5]],
        "income_identity_interpretation":
            "Original same-industry B1G - (D1 + B2N including mixed income "
            "+ P51C + D29X39); not an accepted statistical identity or pure net profit.",
        "no_database_writes": True,
        "original_role_bindings_created": 0,
        "all_l01_l03_original_roles_verified": False,
        "first_publication_vintage_verified": False,
    }


def _source_parent(root: Path, country: str, start_year: int,
                   measures: tuple[str, ...] | None = None) -> Path:
    """Isolate each native selection; one receipt directory per source identity."""
    selection = STAN_MEASURES if measures is None else tuple(measures)
    stan_source_request(country, start_year, measures=selection)
    return Path(root) / "stan-2025" / country / str(start_year) / (
        "measure-" + "+".join(selection))



def store_stan_original(raw: bytes, *, country: str, start_year: int, root: Path,
                        measures: tuple[str, ...] | None = None) -> dict:
    """Atomically retain a checked original + hashed provenance; append receipt."""
    selection = STAN_MEASURES if measures is None else tuple(measures)
    facts = parse_stan_original_csv(
        raw, country=country, start_year=start_year, expected_measures=selection)
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ProviderError("Existing original evidence root required")
    identity = stan_source_identity(country, start_year, measures=selection)
    url, query = stan_source_request(country, start_year, measures=selection)
    # The acquisition requests SDMX flat CSV explicitly. Record the exact
    # non-sensitive query format alongside the native source key.
    query = {**query, "format": "csvfile"}
    digest = sha256(raw).hexdigest()
    content = {"source_identity": identity, "original_sha256": digest,
               "original_bytes": len(raw), "facts_sha256": sha256(canonical_bytes(facts)).hexdigest()}
    bundle_digest = sha256(canonical_bytes(content)).hexdigest()
    parent = _source_parent(root, country, start_year, selection)
    if (parent.is_symlink() or parent.parent.is_symlink()
            or parent.parent.parent.is_symlink()
            or parent.parent.parent.parent.is_symlink()):
        raise ProviderError("Original STAN archive folder is a symbolic link")
    parent.mkdir(parents=True, exist_ok=True)
    bundle = parent / bundle_digest
    staged = None
    try:
        if bundle.exists():
            if bundle.is_symlink() or not bundle.is_dir():
                raise ProviderError("STAN original bundle identity collision")
            saved = json.loads((bundle / "manifest.json").read_bytes())
            if saved.get("content_identity") != content:
                raise ProviderError("STAN original manifest identity collision")
            original = bundle / "original.csv"
            if original.is_symlink() or original.read_bytes() != raw:
                raise ProviderError("STAN original bytes changed")
        else:
            staged = Path(tempfile.mkdtemp(prefix=".stan-", dir=parent))
            (staged / "original.csv").write_bytes(raw)
            manifest = {
                "schema_version": 1,
                "source_identity": identity,
                "content_identity": content,
                "source_url": url,
                "source_request_parameters": query,
                "scope": "selected_native_measures_all_industries_from_requested_start",
                "requested_native_measures": list(selection),
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "original": {"file": "original.csv", "sha256": digest, "bytes": len(raw)},
                "facts": facts,
                "first_publication_verified": False,
                "same_release_across_countries_verified": False,
                "notes": "STAN can include Secretariat estimates; source status "
                         "codes are retained but not reinterpreted as official national submissions.",
            }
            (staged / "manifest.json").write_bytes(canonical_bytes(manifest))
            os.rename(staged, bundle)
            staged = None
        receipt = record_acquisition_receipt(bundle, identity)
        return {"country": country, "status": "original_retained",
                "original_response_sha256": digest,
                "bundle_digest": bundle_digest,
                "receipt_sha256": sha256(receipt.read_bytes()).hexdigest(),
                "facts": facts}
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise ProviderError("STAN source could not be archived") from exc
    finally:
        if staged is not None:
            shutil.rmtree(staged)


def _read_stan_scope(root: Path, country: str, start_year: int,
                     selection: tuple[str, ...]) -> dict:
    """Independently hash and parse one exact publisher selection and its receipts."""
    folder = _source_parent(root, country, start_year, selection)
    receipts = folder / "retrievals"
    if not receipts.is_dir() or receipts.is_symlink() or folder.is_symlink():
        raise EvidenceError("source_receipt_invalid")
    files = sorted(p for p in receipts.glob("*.json") if not p.name.startswith("."))
    if not files:
        raise EvidenceError("missing_evidence")
    identity = stan_source_identity(country, start_year, measures=selection)
    # _selected_manifest rejects even a single mismatched or tampered receipt.
    observed, manifest_hash, path, manifest, method = _selected_manifest(folder, identity)
    if method != "acquisition_receipt" or manifest.get("source_identity") != identity:
        raise EvidenceError("source_identity_mismatch")
    if (manifest.get("requested_native_measures") != list(selection)
            or manifest.get("source_url") != stan_source_request(
                country, start_year, measures=selection)[0]
            or manifest.get("source_request_parameters") != {
                **stan_source_request(country, start_year, measures=selection)[1],
                "format": "csvfile",
            }):
        raise EvidenceError("source_identity_mismatch")
    raw, digest = _original_file(
        path.parent, manifest["original"], "original.csv", binary=True)
    facts = parse_stan_original_csv(
        raw, country=country, start_year=start_year,
        expected_measures=selection)
    content = manifest.get("content_identity", {})
    if (facts != manifest.get("facts")
            or content.get("source_identity") != identity
            or content.get("original_sha256") != digest
            or content.get("facts_sha256") != sha256(canonical_bytes(facts)).hexdigest()):
        raise EvidenceError("source_values_mismatch")
    return {
        "scope": "measure-" + "+".join(selection),
        "requested_since": start_year,
        "source_manifest_sha256": manifest_hash,
        "original_response_sha256": digest,
        "selection_method": method,
        "retrieval_time": observed.isoformat(),
        "numeric_observations": facts["numeric_observations"],
        "native_measure_counts": facts["native_measure_observation_counts"],
        "industry_count": facts["reported_industries"],
        "years": facts["reported_years"],
        "native_status_flag_counts": facts["native_status_flag_counts"],
        "missing_candidate_measures": facts["missing_candidate_measures"],
        "matched_five_measure_industry_years": facts["matched_five_measure_industry_years"],
        "income_identity_residuals_nonzero": facts["nonzero_nominal_income_identity_residuals"],
        "first_publication_verified": False,
    }


def read_stan_evidence(root: Path, *, countries: tuple[str, ...] | None = None) -> dict:
    """Rehash each native scope independently; never merge partial series as truth.

    Original publisher responses can differ by measure selection and historical
    start date. The reader verifies every discovered scope and rejects an entire
    country's certification on any invalid archive rather than ignoring it.
    """
    root = Path(root)
    archive = root / "stan-2025"
    if archive.is_symlink():
        raise ValueError("STAN archive symbolic link")
    if countries is None:
        countries = tuple(sorted(
            p.name for p in archive.iterdir() if p.is_dir() and
            p.name in OECD_MEMBER_ISO3
        )) if archive.is_dir() else ()
    results = []
    for country in countries:
        if country not in OECD_MEMBER_ISO3:
            raise ValueError("Invalid OECD STAN country scope")
        country_dir = archive / country
        if not country_dir.is_dir():
            results.append({"country": country, "status": "missing_original_stan"})
            continue
        starts, evidence, errors = set(), [], []
        try:
            if country_dir.is_symlink():
                raise EvidenceError("source_directory_invalid")
            years = sorted(
                p for p in country_dir.iterdir()
                if p.is_dir() and re.fullmatch(r"[0-9]{4}", p.name))
            if not years:
                raise EvidenceError("missing_evidence")
            for year_dir in years:
                if year_dir.is_symlink():
                    raise EvidenceError("source_directory_invalid")
                start_year = int(year_dir.name)
                starts.add(start_year)
                scopes = sorted(year_dir.iterdir())
                if not scopes:
                    raise EvidenceError("missing_evidence")
                for scoped_dir in scopes:
                    if scoped_dir.is_symlink() or not scoped_dir.is_dir():
                        raise EvidenceError("source_directory_invalid")
                    if not scoped_dir.name.startswith("measure-"):
                        raise EvidenceError("source_directory_invalid")
                    selection = tuple(scoped_dir.name.removeprefix("measure-").split("+"))
                    try:
                        stan_source_request(country, start_year, measures=selection)
                        evidence.append(_read_stan_scope(root, country, start_year, selection))
                    except (EvidenceError, ProviderError, OSError, KeyError, TypeError,
                            ValueError, json.JSONDecodeError):
                        errors.append({"start_year": start_year,
                                       "scope": scoped_dir.name, "status": "invalid_original_stan"})
        except (EvidenceError, ProviderError, OSError, KeyError, TypeError,
                ValueError, json.JSONDecodeError):
            errors.append({"status": "invalid_original_stan_scope"})
        if errors:
            results.append({"country": country, "status": "invalid_original_stan",
                            "scope_errors": errors,
                            "verified_scopes_not_certified": len(evidence)})
            continue
        if not evidence:
            results.append({"country": country, "status": "missing_original_stan"})
            continue
        # Observations/years are reported by scope, not naively added across
        # overlapping publication requests. No implicit cross-source joins.
        covered = {measure for scope in evidence
                   for measure in scope["native_measure_counts"]}
        results.append({
            "country": country, "status": "verified_original_stan_partial",
            "requested_since": min(starts),
            "available_requested_starts": sorted(starts),
            "source_scopes": evidence,
            "observations": sum(scope["numeric_observations"] for scope in evidence),
            "scope_observations_may_overlap": len(evidence) > 1,
            "covered_native_measures": sorted(covered),
            "missing_candidate_measures": sorted(set(STAN_MEASURES) - covered),
            "original_role_bindings_created": 0,
            "first_publication_verified": False,
        })
    verified = [item for item in results if item["status"] == "verified_original_stan_partial"]
    return {
        "status": "verified_original_stan_partial" if verified else
                  "missing_original_stan" if not results else "invalid_or_missing_original_stan",
        "original_source_hash_verified": bool(verified),
        "country_count": len(verified),
        "countries_checked": list(countries),
        "country_results": results,
        "native_values_aggregated": False,
        "original_role_bindings_created": 0,
        "complete_same_industry_compensation_capital_matrix_verified": False,
        "full_history_verified": False,
        "first_publication_verified": False,
    }


def read_verified_stan_scope_csv(root: Path, *, country: str, start_year: int,
                                 measures: tuple[str, ...]) -> bytes:
    """Return exactly one independently verified original response, unmodified.

    Selection and receipt verification reuse the canonical archive reader.
    The second hash check protects the bytes passed to the research audit.
    """
    scope = _read_stan_scope(Path(root), country, start_year, tuple(measures))
    folder = _source_parent(Path(root), country, start_year, tuple(measures))
    identity = stan_source_identity(country, start_year, measures=tuple(measures))
    _, _, path, manifest, _ = _selected_manifest(folder, identity)
    raw, digest = _original_file(
        path.parent, manifest["original"], "original.csv", binary=True)
    if digest != scope["original_response_sha256"]:
        raise EvidenceError("source_values_mismatch")
    return raw
