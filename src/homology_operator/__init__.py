"""Exact F2 homology operator and finite filtration reference (unreleased)."""

__version__ = "0.0.2.dev0"

from .algebra import Matrix
from .chain import ChainWindow, InvalidInput
from .result import OperatorResult, QueryResult
from .solver import (
    FeasibleSolver,
    ProjectionProblem,
    ProjectionSolution,
    ResourceLimits,
    solve_projection,
)
from .validation import ValidationError, validate_projection, validate_solution
from .operator import HomologyOperator
from .family import OperatorFamily, OperatorFamilyResult

__all__ = [
    "Matrix",
    "ChainWindow",
    "InvalidInput",
    "OperatorResult",
    "QueryResult",
    "FeasibleSolver",
    "ProjectionProblem",
    "ProjectionSolution",
    "ResourceLimits",
    "solve_projection",
    "ValidationError",
    "validate_projection",
    "validate_solution",
    "HomologyOperator",
    "OperatorFamily",
    "OperatorFamilyResult",
    "__version__",
]
