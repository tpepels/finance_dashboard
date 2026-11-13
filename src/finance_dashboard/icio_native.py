"""Streaming native ICIO matrix inspection and conservative cross-edition rollups.

The OECD 2025 extended matrix is 85 * 50 industry nodes with 81 * 6 final
demand columns. ICIO 2021 uses 71 * 45 and 67 * 6; ICIO 2018 uses
69 * 36 and 65 * 6. Country variants CN1/CN2 and MX1/MX2 are mapped only
under explicit zero-parent conditions. No flow here is labelled TiVA FFD_DVA.

Industry mapping is many-to-one to the 2018 intersection. No proportionate
allocations of combined source industries are made: ambiguous coverage is
explicitly excluded. Source: OECD ICIO guides and exvatools extract_icio.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import re
from zipfile import ZipFile

# Full published 2018 target sectors: each newer sector must fit in exactly
# one target. D86T89 in 2025 spans D89, outside 2018's D86T88.
SECTORS_2018 = """D01T03 D05T06 D07T08 D09 D10T12 D13T15 D16 D17T18 D19
D20T21 D22 D23 D24 D25 D26 D27 D28 D29 D30 D31T33 D35T39 D41T43
D45T47 D49T53 D55T56 D58T60 D61 D62T63 D64T66 D68 D69T82 D84 D85
D86T88 D90T96 D97T98""".split()
SECTORS_2021 = """D01T02 D03 D05T06 D07T08 D09 D10T12 D13T15 D16 D17T18
D19 D20 D21 D22 D23 D24 D25 D26 D27 D28 D29 D30 D31T33 D35 D36T39
D41T43 D45T47 D49 D50 D51 D52 D53 D55T56 D58T60 D61 D62T63
D64T66 D68 D69T75 D77T82 D84 D85 D86T88 D90T93 D94T96 D97T98""".split()
SECTORS_2025 = """D01 D02 D03 D05 D06 D07 D08 D09 D10T12 D13T15 D16 D17T18
D19 D20 D21 D22 D23 D241 D242 D25 D26 D27 D28 D29 D301 D302 D31T33
D35 D36T39 D41T43 D45T47 D49 D50 D51 D52 D53 D55T56 D58T60
D61 D62T63 D64T66 D68 D69T75 D77T82 D84 D85 D86T89 D90T93
D94T96 D97T98""".split()
# Historical OECD CSV releases use alternative SNA final-demand labels.
# Each country must still have exactly six distinct, uniform categories.
FINAL_USE = {"HFCE", "NPISH", "NPS", "GGFC", "GFCF", "INVNT",
             "INV", "DIRPA", "DPABR", "P33", "DISC", "FD"}
SPLITS = {"CN1": "CHN", "CN2": "CHN", "MX1": "MEX", "MX2": "MEX"}
DIMENSIONS = {
    "2018": (69, 65, SECTORS_2018, 1995, 2015),
    "2021": (71, 67, SECTORS_2021, 1995, 2018),
    "2023": (81, 77, SECTORS_2021, 1995, 2020),
    "2025": (85, 81, SECTORS_2025, 1995, 2022),
}
# A safeguard against hundreds of thousands of invented "years" or unsuitable
# auxiliary archives passed as matrices.
YEAR_MEMBER = {
    "2018": re.compile(r"ICIO2018_(19[9][5-9]|20(?:0[0-9]|1[0-5]))\.csv", re.I),
    "2021": re.compile(r"ICIO2021_(19[9][5-9]|20(?:0[0-9]|1[0-8]))\.csv", re.I),
    "2023": re.compile(r"(19[9][5-9]|20(?:0[0-9]|1[0-9]|20))(?:_SML)?\.csv", re.I),
    "2025": re.compile(r"(19[9][5-9]|20(?:0[0-9]|1[0-9]|2[0-2]))\.csv", re.I),
}


def industry_members(code: str) -> frozenset[int]:
    """Coarse ISIC Rev.4 divisions represented by one declared source label."""
    value = code.removeprefix("D")
    if "T" in value:
        left, right = value.split("T", 1)
        if left.isdigit() and right.isdigit() and len(left) == 2 and len(right) == 2:
            a, b = int(left), int(right)
            if a <= b <= 98:
                return frozenset(range(a, b + 1))
    if value.isdigit() and len(value) in (2, 3):
        # 2025 D241/D242 subdivide division 24; D301/D302 subdivide 30.
        if len(value) == 3 and value not in {"241", "242", "301", "302"}:
            raise ValueError("icio_unknown_split_industry")
        return frozenset({int(value[:2])})
    raise ValueError("icio_unrecognized_industry_code")


def common_2018_concordance(source_codes: list[str]) -> dict:
    mapping, excluded = {}, []
    targets = {name: industry_members(name) for name in SECTORS_2018}
    for code in source_codes:
        src = industry_members(code)
        matches = [target for target, members in targets.items() if src <= members]
        if len(matches) == 1:
            mapping[code] = matches[0]
        else:
            excluded.append(code)
    # A many-to-one mapping is lossless only when ALL component divisions
    # of the target exist. Avoid treating a lone D01 as a complete D01T03,
    # or only D241 as all of the source's D24.
    source_set = set(source_codes)
    complete, incomplete = [], []
    valid_divisions = set().union(*(industry_members(item) for item in SECTORS_2018)) - {76}
    for target in SECTORS_2018:
        target_parts = industry_members(target) & valid_divisions
        members = [source for source, mapped in mapping.items() if mapped == target]
        covered = set().union(*(industry_members(source) for source in members))
        special = (target != "D24" or {"D241", "D242"} <= source_set or "D24" in source_set) and (
                   target != "D30" or {"D301", "D302"} <= source_set or "D30" in source_set)
        if covered & valid_divisions == target_parts and special:
            complete.append(target)
        else:
            incomplete.append(target)
    return {"target_edition": "2018", "mapping": mapping, "excluded": excluded,
            "complete_targets": complete, "incomplete_targets": incomplete,
            "mapping_is_aggregative_only": True,
            "allocated_combined_source_industries": False}


def canonical_country(source: str) -> str:
    return SPLITS.get(source, source)


def _split(label: str) -> tuple[str, str]:
    if "_" not in label:
        raise ValueError("icio_native_industry_header_invalid")
    area, code = label.split("_", 1)
    if not re.fullmatch(r"[A-Z0-9]{3}", area) or not code:
        raise ValueError("icio_native_industry_header_invalid")
    return area, code


def native_account_kind(label: str) -> str | None:
    """Explicit OECD factor-input and output-account row grammar."""
    if label in {"VA", "VALU", "VALUE_ADDED"}:
        return "value_added"
    if label in {"OUT", "OUTPUT"}:
        return "output"
    if label == "TLS":
        return "net_product_taxes"
    if re.fullmatch(r"[A-Z0-9]{3}_TAXSUB", label):
        return "country_product_taxes"
    return None


def _number(text: str) -> Decimal:
    try:
        value = Decimal(text)
        if not value.is_finite():
            raise InvalidOperation
        return value
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("icio_native_nonfinite_or_invalid_numeric_cell") from None


def _simple_text(value: Decimal) -> str:
    return format(value, "f")


def audit_native_csv(stream, *, edition: str, year: int,
                     dimensions: tuple | None = None, table: str = "extended") -> dict:
    """Audit one native matrix with O(columns) memory; never rebalance cells.

    A full accounting pass is impossible if the original contains no explicit
    OUT/TLS/VA components. Those cases stay structurally verified only.
    """
    n_areas, n_fd_areas, sectors, start_year, end_year = dimensions or DIMENSIONS[edition]
    if edition in ("2023", "2025") and table == "regular" and dimensions is None:
        n_areas = n_fd_areas  # Regular matrices have unsplit countries.
    if not start_year <= year <= end_year:
        raise ValueError("icio_native_year_outside_edition")
    rows = csv.reader(stream)
    header = next(rows, None)
    if not header or len(set(header)) != len(header):
        raise ValueError("icio_native_header_invalid")
    expected_nodes = n_areas * len(sectors)
    if len(header) < expected_nodes + 1:
        raise ValueError("icio_native_columns_incomplete")
    nodes = header[1:1 + expected_nodes]
    node_parts = [_split(label) for label in nodes]
    areas = list(dict.fromkeys(country for country, _ in node_parts))
    industry_codes = list(dict.fromkeys(code for _, code in node_parts))
    if (len(areas) != n_areas or len(industry_codes) != len(sectors)
            or set(node_parts) != {(country, sector) for country in areas for sector in industry_codes}):
        raise ValueError("icio_native_industry_dimensions_mismatch")
    if dimensions is None:
        from .icio_sector_codes import normalize_native_sector_labels
        sector_to_internal = normalize_native_sector_labels(industry_codes, edition)
    else:
        if set(industry_codes) != set(sectors):
            raise ValueError("icio_native_industry_dimensions_mismatch")
        sector_to_internal = {sector: sector for sector in industry_codes}
    remainder = header[1 + expected_nodes:]
    expected_fd_columns = n_fd_areas * 6
    if len(remainder) not in (expected_fd_columns, expected_fd_columns + 1):
        raise ValueError("icio_native_final_demand_dimensions_mismatch")
    output_column = len(remainder) == expected_fd_columns + 1
    if output_column and "_" in remainder[-1]:
        raise ValueError("icio_native_output_header_invalid")
    fds = remainder[:-1] if output_column else remainder
    if len(fds) != n_fd_areas * 6:
        raise ValueError("icio_native_final_demand_dimensions_mismatch")
    fd_parts = [_split(label) for label in fds]
    fd_areas = list(dict.fromkeys(area for area, _ in fd_parts))
    fd_code_sets = [{cat for a, cat in fd_parts if a == area} for area in fd_areas]
    if (len(fd_areas) != n_fd_areas or any(cat not in FINAL_USE for _, cat in fd_parts)
            or any(sum(x == area for x, _ in fd_parts) != 6 for area in fd_areas)
            or any(len(codes) != 6 or codes != fd_code_sets[0] for codes in fd_code_sets)):
        raise ValueError("icio_native_final_demand_labels_invalid")
    expected_splits = set(SPLITS) if n_areas != n_fd_areas else set()
    if set(fd_areas) - set(areas) or set(areas) - set(fd_areas) != expected_splits:
        raise ValueError("icio_native_country_split_dimensions_invalid")
    mapping = common_2018_concordance(list(sector_to_internal.values()))
    column_sums = [Decimal(0)] * expected_nodes
    countries: dict[str, dict[str, Decimal]] = {}
    sector_countries: dict[str, dict[str, dict[str, Decimal]]] = {}
    def totals(country: str):
        return countries.setdefault(country, {"gross_output": Decimal(0),
            "direct_foreign_final_demand": Decimal(0), "direct_domestic_final_demand": Decimal(0),
            "value_added": Decimal(0)})
    observed = set()
    row_failure, col_failure, output_mismatch = 0, 0, 0
    max_row = max_col = Decimal(0)
    numeric_scale = 0
    specials: dict[str, list[Decimal]] = {}
    node_output: dict[str, Decimal] = {}
    for row in rows:
        if len(row) != len(header):
            raise ValueError("icio_native_row_width_invalid")
        label = row[0]
        if label in observed:
            raise ValueError("icio_native_duplicate_row")
        observed.add(label)
        if label not in nodes and native_account_kind(label) is None:
            raise ValueError("icio_native_unrecognized_account_row")
        values = [_number(cell) for cell in row[1:]]
        numeric_scale = max(numeric_scale, max(-v.as_tuple().exponent for v in values))
        if label not in nodes:
            specials[label] = values
            continue
        area, sector = _split(label)
        t = totals(area)
        intermediate = sum(values[:expected_nodes], Decimal(0))
        final = sum(values[expected_nodes:expected_nodes + len(fds)], Decimal(0))
        foreign = sum((v for v, (c, _) in zip(values[expected_nodes:expected_nodes + len(fds)], fd_parts)
                       if c != canonical_country(area)), Decimal(0))
        output = values[-1] if output_column else intermediate + final
        if output < 0:
            raise ValueError("icio_native_negative_gross_output")
        node_output[label] = output
        t["gross_output"] += output
        t["direct_foreign_final_demand"] += foreign
        t["direct_domestic_final_demand"] += final - foreign
        sector_group = mapping["mapping"].get(sector_to_internal[sector])
        # Never publish a partial common-sector total as a full industry.
        if sector_group in mapping["complete_targets"]:
            group = sector_countries.setdefault(area, {}).setdefault(
                sector_group, {"gross_output": Decimal(0),
                               "direct_foreign_final_demand": Decimal(0)})
            group["gross_output"] += output
            group["direct_foreign_final_demand"] += foreign
        if output_column:
            residual = intermediate + final - output
            bound = Decimal(5).scaleb(-numeric_scale - 1) * (len(fds) + expected_nodes + 1)
            max_row = max(max_row, abs(residual))
            row_failure += abs(residual) > bound
        for j, val in enumerate(values[:expected_nodes]):
            column_sums[j] += val
    if not set(nodes) <= observed:
        raise ValueError("icio_native_missing_industry_rows")
    # Two independently observed publisher accounting layouts:
    # (1) VA + TLS = OUT - column_sum(Z)
    # (2) VALU + sum(country_TAXSUB) = OUTPUT - column_sum(Z).
    # No source accounts are inferred from the balancing residual.
    value_labels = [label for label in specials
                    if native_account_kind(label) == "value_added"]
    output_labels = [label for label in specials
                     if native_account_kind(label) == "output"]
    global_tax_labels = [label for label in specials
                         if native_account_kind(label) == "net_product_taxes"]
    country_tax_labels = [label for label in specials
                          if native_account_kind(label) == "country_product_taxes"]
    accounts_complete = (len(value_labels) == 1 and len(output_labels) == 1
                         and not (global_tax_labels and country_tax_labels)
                         and (len(global_tax_labels) == 1 or
                              set(country_tax_labels) ==
                              {area + "_TAXSUB" for area in fd_areas}
                              or not country_tax_labels)
                         and (not country_tax_labels or
                              len(country_tax_labels) == n_fd_areas))
    # A missing tax account is allowed only if the source has no tax rows;
    # it cannot be called independently tax-inclusive without a tax identity.
    has_accounts = accounts_complete and (
        bool(global_tax_labels) or bool(country_tax_labels)
        or value_labels[0] in {"VALU", "VALUE_ADDED"})
    account_schema = ("publisher_VA_TLS_OUT" if has_accounts and global_tax_labels else
                      "publisher_VALU_country_TAXSUB_OUTPUT"
                      if has_accounts and country_tax_labels else
                      "publisher_value_added_output_without_explicit_tax"
                      if has_accounts else "incomplete_or_absent")
    if has_accounts:
        vrow = specials[value_labels[0]]
        orow = specials[output_labels[0]]
        trow = ([sum((specials[name][j] for name in
                      [*global_tax_labels, *country_tax_labels]), Decimal(0))
                 for j in range(len(vrow))])
        col_bound = Decimal(5).scaleb(-numeric_scale - 1) * (
            expected_nodes + 2 + len(global_tax_labels) + len(country_tax_labels))
        for j, label in enumerate(nodes):
            residual = column_sums[j] + trow[j] + vrow[j] - orow[j]
            max_col = max(max_col, abs(residual))
            col_failure += abs(residual) > col_bound
            output_mismatch += abs(node_output[label] - orow[j]) > col_bound
            totals(_split(label)[0])["value_added"] += vrow[j] + trow[j]
    # Unknown extra row labels are rejected while known but incomplete source
    # accounts remain explicitly unverified rather than silently imputed.
    # If split and unsplit country rows both contain production, the parent
    # must not be summed twice or silently ignored.
    conflicts = sorted(area for area, splits in (("CHN", ("CN1", "CN2")),
                                                    ("MEX", ("MX1", "MX2")))
                       if (area in countries and any(s in countries for s in splits)
                           and countries[area]["gross_output"] != 0))
    merged = {}
    for area, amounts in countries.items():
        if area in ("CHN", "MEX") and n_areas != n_fd_areas and area in fd_areas:
            continue
        target = canonical_country(area)
        if target in conflicts:
            continue
        bucket = merged.setdefault(target, {k: Decimal(0) for k in amounts})
        for key, value in amounts.items():
            bucket[key] += value
    # Industry aggregates are exact many-to-one sums only. The schema
    # reports excluded 2025 sectors; it never allocates D86T89 into 2018
    # D86T88. CN/MX split-country nodes may only be combined unambiguously.
    common_industries: dict[str, dict[str, dict[str, Decimal]]] = {}
    for area, groups in sector_countries.items():
        if area in ("CHN", "MEX") and n_areas != n_fd_areas and area in fd_areas:
            continue
        target = canonical_country(area)
        if target in conflicts:
            continue
        merged_sectors = common_industries.setdefault(target, {})
        for sector, amounts in groups.items():
            group = merged_sectors.setdefault(sector, {key: Decimal(0) for key in amounts})
            for key, val in amounts.items():
                group[key] += val
    common_industries_public = {
        area: {sector: {key + "_usd_million": _simple_text(val)
                        for key, val in values.items()}
               for sector, values in sorted(groups.items())}
        for area, groups in sorted(common_industries.items())}
    series = {}
    for area in sorted(merged):
        t = merged[area]
        # Direct foreign demand for the country's goods/services is NOT
        # domestic value added embodied abroad (OECD TiVA FFD_DVA).
        share = 100 * t["direct_foreign_final_demand"] / t["value_added"] if (
            has_accounts and t["value_added"] > 0) else None
        series[area] = {
            "gross_output_usd_million": _simple_text(t["gross_output"]),
            "direct_foreign_final_demand_usd_million": _simple_text(t["direct_foreign_final_demand"]),
            "domestic_final_demand_usd_million": _simple_text(t["direct_domestic_final_demand"]),
            "source_value_added_usd_million": _simple_text(t["value_added"]) if has_accounts else None,
            "direct_foreign_final_demand_to_va_pct": _simple_text(share) if share is not None else None}
    return {"year": year, "edition": edition, "industry_nodes": expected_nodes,
            "structure_verified": True,
            "source_country_count": n_areas, "final_demand_country_count": n_fd_areas,
            "native_industries": industry_codes,
            "normalized_industries": list(sector_to_internal.values()),
            "output_column_label": remainder[-1] if output_column else None,
            "industry_concordance": mapping,
            "country_concordance": {"split_to_parent": SPLITS, "ambiguous_unsplit_parents": conflicts,
                "valid": not conflicts},
            "publisher_account_rows_present": has_accounts,
            "publisher_account_schema": account_schema,
            "observed_source_account_row_labels": sorted(specials),
            "final_demand_categories": sorted(fd_code_sets[0]),
            "accounting_passed": (row_failure == col_failure == output_mismatch == 0)
                                if has_accounts else None,
            "row_failures": row_failure if output_column else None,
            "column_failures": col_failure if has_accounts else None,
            "output_vector_mismatches": output_mismatch if has_accounts else None,
            "max_row_residual": _simple_text(max_row) if output_column else None,
            "max_column_residual": _simple_text(max_col) if has_accounts else None,
            "source_precision_decimals": numeric_scale,
            "country_direct_flows": series,
            "common_2018_sector_direct_flows": common_industries_public,
            "units": "current_USD_million",
            "tiva_equivalent": False, "first_publication_verified": False}


class _HashingRawStream(io.RawIOBase):
    """Hash exact uncompressed publisher bytes during the existing CSV read."""
    def __init__(self, original):
        super().__init__()
        self.original = original
        self.sha = sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        raw = self.original.read(len(buffer))
        size = len(raw)
        if size:
            buffer[:size] = raw
            self.sha.update(raw)
        return size


def native_year_members(zip_file: ZipFile, edition: str) -> list[tuple[int, str]]:
    result = []
    matcher = YEAR_MEMBER[edition]
    for entry in zip_file.infolist():
        if entry.is_dir():
            continue
        base = entry.filename.split("/")[-1]
        match = matcher.fullmatch(base)
        if match:
            result.append((int(match.group(1)), entry.filename))
    if len({year for year, _ in result}) != len(result):
        raise ValueError("icio_duplicate_annual_matrix_member")
    return sorted(result)


def expected_archive_years(filename: str, edition: str) -> list[int] | None:
    """Edition-specific mandatory annual members; None for auxiliary packages."""
    base = filename.rsplit("/", 1)[-1]
    if edition == "2025":
        match = re.fullmatch(r"(19[9][5-9]|20[0-2][0-9])-(19[9][5-9]|20[0-2][0-9])_EXT(?: \([0-9]+\))?\.zip", base)
        if match:
            low, high = map(int, match.groups())
            if 1995 <= low <= high <= 2022 and high - low <= 7:
                return list(range(low, high + 1))
    if edition == "2023":
        match = re.fullmatch(r"(\d{4})-(\d{4})_(?:EXT|SML)(?: \([0-9]+\))?\.zip", base)
        if match:
            low, high = map(int, match.groups())
            if 1995 <= low <= high <= 2020 and high - low <= 6:
                return list(range(low, high + 1))
    if edition == "2021":
        match = re.fullmatch(r"ICIO2021_(\d{4})-(\d{4})\.zip", base)
        if match:
            low, high = map(int, match.groups())
            if 1995 <= low <= high <= 2018 and high - low <= 5:
                return list(range(low, high + 1))
    if edition == "2018":
        match = re.fullmatch(r"ICIO2018_(\d{4})\.zip", base)
        if match:
            year = int(match.group(1))
            if 1995 <= year <= 2015:
                return [year]
    return None


def audit_archive_native(zip_file: ZipFile, edition: str,
                         *, dimensions: tuple | None = None, table: str = "extended",
                         original_filename: str | None = None) -> dict:
    # Rdata and supplemental econA/B/VB/Z archives are valid source evidence,
    # but cannot be called audited matrices without a CSV member.
    from .icio_schema import probe_archive_layout
    header_probe = probe_archive_layout(zip_file)
    members = native_year_members(zip_file, edition)
    mandatory = expected_archive_years(original_filename or getattr(zip_file, "filename", "") or "", edition)
    found = [year for year, _ in members]
    # Exact year coverage is required for edition comparison; absent years
    # never count as verified native original matrices.
    complete = mandatory is None or found == mandatory
    results = []
    rejected = []
    for year, path in members:
        try:
            with zip_file.open(path) as original:
                hashed = _HashingRawStream(original)
                with io.TextIOWrapper(io.BufferedReader(hashed),
                                      encoding="utf-8-sig", newline="") as stream:
                    audit = audit_native_csv(stream, edition=edition, year=year,
                                             dimensions=dimensions, table=table)
                    # The parser must read through the complete record stream.
                    # An early parser rejection skips source-value comparison.
                    audit["original_member_sha256"] = hashed.sha.hexdigest()
            # This is a distinct, correctly labelled Leontief reconstruction,
            # never a substitution for published OECD TiVA data. The original
            # matrix and source-level accounting result remain immutable.
            try:
                from .icio_leontief import reconstruct_native_tiva, NativeValueAddedError
                with zip_file.open(path) as original:
                    with io.TextIOWrapper(original, encoding="utf-8-sig", newline="") as stream:
                        audit["tiva_reconstruction"] = reconstruct_native_tiva(stream, audit)
            except (NativeValueAddedError, UnicodeError, MemoryError) as exc:
                code = str(exc)
                if not re.fullmatch(r"icio_[a-z_]{1,96}", code):
                    code = "icio_leontief_resource_or_encoding_failure"
                audit["tiva_reconstruction"] = {"status": "not_computable",
                                                "error_code": code}
            results.append(audit)
        except (ValueError, UnicodeError, csv.Error) as exc:
            # ZIP integrity has already been checked. Preserve the exact
            # original for later parser adaptation, but publish no derived
            # figures for the rejected member. No source data is corrected.
            code = str(exc)
            if not re.fullmatch(r"icio_[a-z_]{1,96}", code):
                code = "icio_native_matrix_schema_rejected"
            rejected.append({"year": year, "member": path, "error_code": code})
    return {"edition": edition, "table": table,
            "annual_matrices": results, "annual_matrix_count": len(results),
            "expected_years": mandatory, "observed_years": found,
            "rejected_matrices": rejected,
            "header_schema": header_probe,
            "native_validation_status": ("native_parser_rejected" if rejected
                else "native_matrix_years_incomplete" if not complete
                else "native_accounts_verified" if results
                and all(a["accounting_passed"] is True and a["country_concordance"]["valid"]
                        for a in results)
                else "native_structure_verified_accounting_unavailable" if results
                and all(a["accounting_passed"] is None and a["structure_verified"]
                        and a["country_concordance"]["valid"]
                        and a["row_failures"] in (None, 0) for a in results)
                else "native_accounts_unresolved" if results else "no_native_csv_matrices"),
            "tiva_equivalent": False,
            "method": "edition_native_streaming_audit_v1"}
