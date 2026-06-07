"""Model-build instrumentation helpers for scheduler performance analysis."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This code is mostly AI generated.

import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .context import Context


@dataclass(frozen=True)
class ModelBuildStats:
    """Instrumented model-build statistics for one scheduler build step."""

    step: str
    elapsedSeconds: float
    variablesAdded: int
    constraintsAdded: int
    totalVariables: int
    totalConstraints: int
    preferenceIndex: int | None = None
    preferenceType: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible payload."""
        return {
            "step": self.step,
            "elapsedSeconds": self.elapsedSeconds,
            "variablesAdded": self.variablesAdded,
            "constraintsAdded": self.constraintsAdded,
            "totalVariables": self.totalVariables,
            "totalConstraints": self.totalConstraints,
            "preferenceIndex": self.preferenceIndex,
            "preferenceType": self.preferenceType,
        }


@dataclass
class _ModelBuildStatsSummaryRow:
    """Aggregated model-build statistics for one summary step."""

    count: int = 0
    elapsed_seconds: float = 0.0
    variables_added: int = 0
    constraints_added: int = 0
    total_variables: int = 0
    total_constraints: int = 0


class ModelBuildStatsSummary:
    """Buffer model-build events and print a compact summary."""

    def __init__(self):
        self.rows = OrderedDict()

    def __call__(self, payload: ModelBuildStats) -> None:
        step = payload.step
        if payload.preferenceType is not None:
            step = f"pref:{payload.preferenceType}"
        row = self.rows.setdefault(step, _ModelBuildStatsSummaryRow())
        row.count += 1
        row.elapsed_seconds += payload.elapsedSeconds
        row.variables_added += payload.variablesAdded
        row.constraints_added += payload.constraintsAdded
        row.total_variables = payload.totalVariables
        row.total_constraints = payload.totalConstraints

    def print_summary(self) -> None:
        """Print buffered stats as dense tab-separated rows."""
        if not self.rows:
            return
        print(
            "MODEL_BUILD_STATS\tstep\tcount\telapsed_seconds\tvariables_added\tconstraints_added"
            "\ttotal_variables\ttotal_constraints"
        )
        for step, row in self.rows.items():
            print(
                step,
                row.count,
                f"{row.elapsed_seconds:.6f}",
                row.variables_added,
                row.constraints_added,
                row.total_variables,
                row.total_constraints,
                sep="\t",
            )


def get_model_entity_counts(ctx: Context) -> tuple[int, int]:
    """Return the current solver model variable and constraint counts."""
    solver = ctx.solver
    if solver is None:
        return 0, 0

    if hasattr(solver, "model"):
        model = solver.model
        if hasattr(model, "Proto"):
            proto = model.Proto()
            return len(proto.variables), len(proto.constraints)
        if hasattr(solver, "variables") and hasattr(model, "constraints"):
            return len(solver.variables), len(model.constraints)

    return len(ctx.model_vars), 0


def emit_model_build_stats(
    callback: Callable[[ModelBuildStats], None] | None,
    ctx: Context,
    step: str,
    started_at: float,
    start_counts: tuple[int, int],
    *,
    preference_index: int | None = None,
    preference_type: str | None = None,
) -> None:
    """Emit model-build instrumentation without letting callback failures break scheduling."""
    if callback is None:
        return
    total_variables, total_constraints = get_model_entity_counts(ctx)
    try:
        callback(
            ModelBuildStats(
                step=step,
                elapsedSeconds=round(time.perf_counter() - started_at, 6),
                variablesAdded=total_variables - start_counts[0],
                constraintsAdded=total_constraints - start_counts[1],
                totalVariables=total_variables,
                totalConstraints=total_constraints,
                preferenceIndex=preference_index,
                preferenceType=preference_type,
            )
        )
    except Exception:
        logging.exception("Model build stats callback failed")


def start_model_build_step(
    callback: Callable[[ModelBuildStats], None] | None,
    ctx: Context,
) -> tuple[float, tuple[int, int]]:
    """Capture the start time and model size for a build step."""
    if callback is None:
        return 0.0, (0, 0)
    return time.perf_counter(), get_model_entity_counts(ctx)
