"""Typed contracts shared by every allocation layer (design section 10.3).

All values are immutable. Vectors and matrices are tuples so that the
objects can be hashed, compared and serialised without numerical libraries;
later phases convert to numpy at the point of computation.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date
import math
from typing import Any, Literal, Protocol, Sequence, runtime_checkable

Tier = Literal["E", "R"]
Family = Literal["econometric", "ml", "llm"]
AllocationStatus = Literal["validated", "research_view", "reference"]

REQUIRED_QUANTILES = (0.1, 0.5, 0.9)
_TOLERANCE = 1e-9


def _probability(name: str, value: float) -> None:
    if not (isinstance(value, (int, float)) and 0.0 <= value <= 1.0):
        raise ValueError(f"{name} must be a probability in [0, 1], got {value!r}")


def _pairs_sum_to_one(name: str, pairs: Sequence[tuple[str, float]]) -> None:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{name} has duplicate keys")
    if any(not math.isfinite(value) or value < -_TOLERANCE for _, value in pairs):
        raise ValueError(f"{name} must be finite and non-negative")
    if abs(sum(value for _, value in pairs) - 1.0) > 1e-6:
        raise ValueError(f"{name} must sum to 1")


@dataclass(frozen=True)
class Provenance:
    """Everything needed to trace an output back to its code and inputs."""
    code_commit: str
    spec_hash: str
    snapshot_hashes: tuple[str, ...] = ()
    artifact_hashes: tuple[str, ...] = ()
    llm_record_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeatureSnapshot:
    """Point-in-time feature matrix for one decision date (layer L2 output)."""
    as_of: date
    tier: Tier
    entities: tuple[str, ...]
    feature_ids: tuple[str, ...]
    values: tuple[tuple[float | None, ...], ...]   # rows follow entities, columns follow feature_ids
    snapshot_hash: str
    target_ids: tuple[str, ...] = ()
    targets: tuple[tuple[float | None, ...], ...] = ()  # realised targets whose window ended by as_of

    def __post_init__(self) -> None:
        if self.tier not in ("E", "R"):
            raise ValueError("tier must be 'E' or 'R'")
        if len(set(self.entities)) != len(self.entities) or len(set(self.feature_ids)) != len(self.feature_ids):
            raise ValueError("entities and feature_ids must be unique")
        if len(self.values) != len(self.entities) or any(len(row) != len(self.feature_ids) for row in self.values):
            raise ValueError("values must be an entities x feature_ids matrix")
        if self.targets and (len(self.targets) != len(self.entities)
                             or any(len(row) != len(self.target_ids) for row in self.targets)):
            raise ValueError("targets must be an entities x target_ids matrix")
        if not self.snapshot_hash:
            raise ValueError("snapshot_hash is required")


@dataclass(frozen=True)
class ForecastDistribution:
    """One model's 12-month predictive distribution for one bucket (layer L3 output)."""
    bucket: str
    as_of: date
    model_id: str
    artifact_hash: str
    mean: float
    var: float
    quantiles: tuple[tuple[float, float], ...]          # (level, value), ascending levels
    events: tuple[tuple[str, float], ...] = ()          # uncalibrated event probabilities
    regimes: tuple[tuple[str, float], ...] | None = None

    def __post_init__(self) -> None:
        if not (math.isfinite(self.mean) and math.isfinite(self.var) and self.var >= 0.0):
            raise ValueError("mean must be finite and var non-negative")
        levels = [level for level, _ in self.quantiles]
        if levels != sorted(levels) or len(set(levels)) != len(levels):
            raise ValueError("quantile levels must be strictly ascending")
        if any(not 0.0 < level < 1.0 for level in levels):
            raise ValueError("quantile levels must lie in (0, 1)")
        missing = [q for q in REQUIRED_QUANTILES if not any(abs(q - level) < _TOLERANCE for level in levels)]
        if missing:
            raise ValueError(f"quantiles must include {REQUIRED_QUANTILES}; missing {missing}")
        values = [value for _, value in self.quantiles]
        if any(later < earlier for earlier, later in zip(values, values[1:])):
            raise ValueError("quantile values must be non-decreasing")
        for name, probability in self.events:
            _probability(f"event {name}", probability)
        if self.regimes is not None:
            _pairs_sum_to_one("regimes", self.regimes)

    def quantile(self, level: float) -> float:
        for candidate, value in self.quantiles:
            if abs(candidate - level) < _TOLERANCE:
                return value
        raise KeyError(level)


@dataclass(frozen=True)
class FittedModel:
    """Handle to a fitted model; the artifact itself lives in the artifact store."""
    model_id: str
    spec_hash: str
    refit_as_of: date
    tier: Tier
    artifact_hash: str


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    spec_hash: str
    hyperparameters: tuple[tuple[str, Any], ...] = ()


@runtime_checkable
class Forecaster(Protocol):
    """Contract for every forecaster M1-M11 (econometric, ML and LLM alike)."""
    model_id: str
    family: Family
    depends_on: tuple[str, ...]

    def fit(self, history: Sequence[FeatureSnapshot], spec: ModelSpec) -> FittedModel: ...

    def predict(self, fitted: FittedModel, snapshot: FeatureSnapshot) -> list[ForecastDistribution]: ...


@dataclass(frozen=True)
class Posterior:
    """Investor-independent market posterior for one decision date (layer L4 output)."""
    as_of: date
    buckets: tuple[str, ...]
    mu: tuple[float, ...]
    sigma: tuple[tuple[float, ...], ...]
    model_weights: tuple[tuple[str, tuple[tuple[str, float], ...]], ...]  # bucket -> ((model_id, weight), ...)
    view_omega: tuple[float | None, ...]   # None = view dropped (no out-of-sample skill)
    provenance: Provenance

    def __post_init__(self) -> None:
        n = len(self.buckets)
        if len(set(self.buckets)) != n or len(self.mu) != n or len(self.view_omega) != n:
            raise ValueError("buckets, mu and view_omega must align")
        if len(self.sigma) != n or any(len(row) != n for row in self.sigma):
            raise ValueError("sigma must be square and match buckets")
        for i in range(n):
            if self.sigma[i][i] < 0:
                raise ValueError("sigma diagonal must be non-negative")
            for j in range(i):
                if abs(self.sigma[i][j] - self.sigma[j][i]) > 1e-12:
                    raise ValueError("sigma must be symmetric")
        for bucket, weights in self.model_weights:
            _pairs_sum_to_one(f"model weights for {bucket}", weights)


@dataclass(frozen=True)
class ReferencePortfolio:
    """A declared benchmark: the market anchor, a ladder rung or the owner policy."""
    id: str
    weights: tuple[tuple[str, float], ...]
    risk_aversion: float
    te_max: float
    growth_band: float
    caps: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        _pairs_sum_to_one(f"reference {self.id} weights", self.weights)
        if not (self.risk_aversion > 0 and self.te_max > 0 and 0 < self.growth_band < 1):
            raise ValueError("risk_aversion and te_max must be positive; growth_band in (0, 1)")
        caps = dict(self.caps)
        for bucket, weight in self.weights:
            if bucket in caps and weight > caps[bucket] + _TOLERANCE:
                raise ValueError(f"reference {self.id} weight for {bucket} exceeds its cap")

    def weight(self, bucket: str) -> float:
        return dict(self.weights).get(bucket, 0.0)


@dataclass(frozen=True)
class Allocation:
    """Recommended weights for one reference portfolio at one decision date (layer L5 output)."""
    reference_id: str
    as_of: date
    weights: tuple[tuple[str, float], ...]
    ranges: tuple[tuple[str, float, float], ...]   # (bucket, 10% weight, 90% weight)
    status: AllocationStatus
    reason: str
    provenance: Provenance

    def __post_init__(self) -> None:
        _pairs_sum_to_one(f"allocation {self.reference_id}", self.weights)
        if self.status not in ("validated", "research_view", "reference"):
            raise ValueError("unknown allocation status")
        if not self.reason:
            raise ValueError("every allocation states its reason")
        for bucket, low, high in self.ranges:
            if not 0.0 <= low <= high <= 1.0:
                raise ValueError(f"range for {bucket} must satisfy 0 <= low <= high <= 1")


def to_jsonable(value: Any) -> Any:
    """Serialise a contract object to JSON-compatible primitives."""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value

