"""Independently reconstruct TiVA foreign-final-demand value added from ICIO Z and Y.

OECD ICIO's Z is producer-by-user intermediate inputs (USD millions) and Y
is producer-by-country final demand. For column j, A[:, j] = Z[:, j] / X[j]
with X = row_sum(Z) + row_sum(Y). For final demand outside source country c:

    FFD_DVA(c) = sum_{i in c} (VA[i] / X[i]) *
                 [(I - A)^(-1) * Y_foreign(c)][i]

where VA includes product taxes through the input-output column residual
X - column_sum(Z). The split producer groups CN1/CN2 and MX1/MX2 are
included in their respective parent country; the unsplit parent groups must
be structurally empty, never double counted. No inverse matrix is materialised.

The exact OECD data can differ across releases, independently rounded SDMX
series, and statistical balancing. This calculation is a reconstructed
measurement; numerical convergence is NOT publisher-source certification.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from typing import TextIO

import numpy as np

from .icio_native import canonical_country

COUNTRIES = ("USA", "FRA", "PRT", "CHN", "JPN", "DEU", "IND")
MATH_METHOD = "ICIO_Leontief_FFD_DVA_v1"
MAX_NODES = 4500
DEFAULT_RTOL = 1.0e-10
DEFAULT_ITERATIONS = 600


class NativeValueAddedError(ValueError):
    pass


@dataclass(frozen=True)
class AnnualNative:
    countries: list[str]
    nodes: list[str]
    z: np.ndarray
    final_by_country: np.ndarray
    output: np.ndarray
    value_added: np.ndarray
    value_added_basis: str
    max_source_account_residual: float | None
    source_accounts_passed: bool | None


def read_native_year(stream: TextIO, audit: dict, *, max_nodes: int = MAX_NODES) -> AnnualNative:
    """Read a *previously structurally audited* native CSV into bounded arrays.

    The detailed dimensional, row identity and non-finite checks are repeated
    here rather than trusting a user-editable audit dictionary.
    """
    rows = csv.reader(stream)
    header = next(rows, None)
    n = audit["industry_nodes"]
    if not isinstance(n, int) or n < 2 or n > max_nodes:
        raise NativeValueAddedError("icio_leontief_invalid_node_count")
    if not header or not header[0] or len(header[0]) > 128:
        raise NativeValueAddedError("icio_leontief_header_invalid")
    node_names = header[1:n + 1]
    if len(set(node_names)) != n:
        raise NativeValueAddedError("icio_leontief_duplicate_node_label")
    observed_areas = [name.split("_", 1)[0] for name in node_names]
    if any(len(name.split("_", 1)) != 2 for name in node_names):
        raise NativeValueAddedError("icio_leontief_node_label_invalid")
    if len(set(observed_areas)) != audit["source_country_count"]:
        raise NativeValueAddedError("icio_leontief_country_count_mismatch")
    labels = header[n + 1:]
    has_output = bool(labels and labels[-1] == "OUT")
    if has_output:
        labels = labels[:-1]
    if len(labels) != audit["final_demand_country_count"] * 6:
        raise NativeValueAddedError("icio_leontief_final_demand_count_invalid")
    if len(set(header)) != len(header):
        raise NativeValueAddedError("icio_leontief_duplicate_column")
    final_destinations = [label.split("_", 1)[0] for label in labels]
    if any("_" not in label for label in labels):
        raise NativeValueAddedError("icio_leontief_final_demand_label_invalid")
    expected = (n + len(labels) + 1 + int(has_output))
    z = np.empty((n, n), dtype=np.float64)
    final = np.zeros((n, len(COUNTRIES) + 1), dtype=np.float64)
    country_positions = {
        c: np.asarray([j for j, area in enumerate(final_destinations)
                        if area == c], dtype=np.intp)
        for c in COUNTRIES
    }
    out = np.empty(n, dtype=np.float64)
    known = {label: j for j, label in enumerate(node_names)}
    seen: set[str] = set()
    extras: dict[str, np.ndarray] = {}
    for row in rows:
        if len(row) != expected or row[0] in seen:
            raise NativeValueAddedError("icio_leontief_row_shape_invalid")
        label = row[0]
        seen.add(label)
        if label not in known and label not in ("TLS", "VA", "OUT"):
            raise NativeValueAddedError("icio_leontief_unknown_account_row")
        try:
            arr = np.asarray(row[1:], dtype=np.float64)
        except (ValueError, TypeError, OverflowError) as exc:
            raise NativeValueAddedError("icio_leontief_numeric_value_invalid") from exc
        if not np.isfinite(arr).all():
            raise NativeValueAddedError("icio_leontief_nonfinite_numeric_value")
        if label not in known:
            extras[label] = arr
            continue
        i = known[label]
        z[i, :] = arr[:n]
        fd = arr[n:n + len(labels)]
        final[i, :-1] = [float(fd[positions].sum(dtype=np.float64))
                        for positions in country_positions.values()]
        final[i, -1] = float(fd.sum(dtype=np.float64))
        out[i] = arr[-1] if has_output else (z[i, :].sum(dtype=np.float64) +
                                             fd.sum(dtype=np.float64))
    if not set(known) <= seen:
        raise NativeValueAddedError("icio_leontief_missing_producer_row")
    if np.any(out < 0):
        raise NativeValueAddedError("icio_leontief_negative_gross_output")
    col_inputs = z.sum(axis=0, dtype=np.float64)
    value_added = out - col_inputs
    source_pass = audit.get("accounting_passed")
    if source_pass is False:
        raise NativeValueAddedError("icio_leontief_original_accounts_failed")
    residual = None
    basis = "derived_output_less_intermediate_inputs_including_taxes"
    if has_output and set(extras) == {"TLS", "VA", "OUT"}:
        publisher_value_added = extras["TLS"][:n] + extras["VA"][:n]
        residual = float(np.max(np.abs(publisher_value_added - value_added)))
        # The original source audit is the authority on its four-decimal
        # residual threshold. Never replace its flags with a float comparison.
        if source_pass is not True:
            raise NativeValueAddedError("icio_leontief_unverified_publisher_accounts")
        value_added = publisher_value_added
        basis = "publisher_VA_plus_TLS"
    elif extras and set(extras) != {"TLS", "VA", "OUT"}:
        raise NativeValueAddedError("icio_leontief_partial_account_rows")
    return AnnualNative(
        countries=observed_areas, nodes=node_names, z=z,
        final_by_country=final, output=out, value_added=value_added,
        value_added_basis=basis,
        max_source_account_residual=residual,
        source_accounts_passed=source_pass,
    )


def solve_foreign_final_demand(
    annual: AnnualNative, *, tolerance: float = DEFAULT_RTOL,
    max_iterations: int = DEFAULT_ITERATIONS,
) -> dict:
    """Iterate the Leontief system for seven foreign-demand vectors in one pass.

    Neumann iteration converges for productive matrices with spectral radius
    below one. If it does not, the result is rejected, never silently
    approximated or truncated. Strict input/output and residual tests avoid
    falsely passing numerical solutions.
    """
    if not 0 < tolerance <= 1.0e-6 or max_iterations <= 0:
        raise NativeValueAddedError("icio_leontief_solver_options_invalid")
    z = annual.z.copy()
    x = annual.output
    positive = x > 0
    zero = ~positive
    if np.any(np.abs(z[:, zero]) > 1.0e-9):
        raise NativeValueAddedError("icio_leontief_positive_inputs_zero_output")
    z[:, positive] /= x[np.newaxis, positive]
    z[:, zero] = 0
    country_row = np.asarray([canonical_country(label.split("_", 1)[0])
                              for label in annual.nodes], dtype=str)
    # The selected seven countries do not exhaust all final destinations.
    # Column -1 is the independently retained all-country final demand.
    if annual.final_by_country.shape[1] != len(COUNTRIES) + 1:
        raise NativeValueAddedError("icio_leontief_world_demand_missing")
    world = annual.final_by_country[:, -1]
    rhs = np.column_stack([world - annual.final_by_country[:, k]
                           for k in range(len(COUNTRIES))])
    if not np.isfinite(rhs).all():
        raise NativeValueAddedError("icio_leontief_rhs_invalid")
    state = rhs.copy()
    scale = max(1.0, float(np.max(np.abs(rhs))))
    count = 0
    converged = False
    for count in range(1, max_iterations + 1):
        next_state = rhs + z @ state
        if not np.isfinite(next_state).all():
            raise NativeValueAddedError("icio_leontief_numeric_diverged")
        change = float(np.max(np.abs(next_state - state)))
        state = next_state
        if change <= tolerance * max(scale, float(np.max(np.abs(state)))):
            converged = True
            break
    if not converged:
        raise NativeValueAddedError("icio_leontief_no_convergence")
    residual = float(np.max(np.abs(state - rhs - z @ state)))
    relative_residual = residual / max(scale, float(np.max(np.abs(state))))
    if relative_residual > tolerance * 5:
        raise NativeValueAddedError("icio_leontief_residual_too_large")
    coefficient = np.zeros_like(x)
    coefficient[positive] = annual.value_added[positive] / x[positive]
    if np.any((~positive) & (np.abs(annual.value_added) > 1.0e-8)):
        raise NativeValueAddedError("icio_leontief_zero_output_nonzero_value_added")
    result = {}
    for k, country in enumerate(COUNTRIES):
        mask = country_row == country
        if not mask.any():
            continue
        # Full model output weights the foreign final demand's direct and
        # indirect upstream domestic production by source value-added rate.
        va = float(annual.value_added[mask].sum())
        foreign = float(np.dot(coefficient[mask], state[mask, k]))
        if not math.isfinite(va) or va <= 0 or not math.isfinite(foreign):
            result[country] = {"status": "invalid_value_added_denominator"}
            continue
        share = 100.0 * foreign / va
        if share < -1.0e-6 or share > 100.000001:
            result[country] = {"status": "outside_physical_share_bounds",
                               "value_added_usd_million": va, "ffd_dva_usd_million": foreign,
                               "share_pct": share}
            continue
        result[country] = {
            "status": "reconstructed_unreconciled", "ffd_dva_usd_million": foreign,
            "value_added_usd_million": va, "share_pct": share,
        }
    return {
        "method": MATH_METHOD, "reference": "OECD TiVA 2025 Guide 6.3",
        "source_accounting": annual.source_accounts_passed,
        "value_added_basis": annual.value_added_basis,
        "iterations": count,
        "max_relative_residual": relative_residual,
        "selected_country_values": result,
        "scientific_certification": False,
        "publisher_reconciled": False,
        "model": "v * (I - Z diag(X)^-1)^-1 * Y_foreign",
    }


def reconstruct_native_tiva(stream: TextIO, audit: dict, *,
                            tolerance: float = DEFAULT_RTOL,
                            max_iterations: int = DEFAULT_ITERATIONS) -> dict:
    annual = read_native_year(stream, audit)
    return solve_foreign_final_demand(annual, tolerance=tolerance,
                                      max_iterations=max_iterations)
