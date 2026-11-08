"""Run analyses against the stored corpus."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..service import current_observations
from .bundle import AnalysisDefinition


def load_points(session: Session, definition: AnalysisDefinition) -> dict[str, list[tuple[date, float]]]:
    """Current observed values of each declared input, by role."""
    return {role: [(row.period, float(row.value)) for row in current_observations(session, series_id)]
            for role, series_id in definition.inputs.items()}
