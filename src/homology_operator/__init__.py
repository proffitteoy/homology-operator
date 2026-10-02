"""Exact F2 single-scale reference backend (unreleased)."""

__version__ = "0.0.2.dev0"

from .algebra import Matrix
from .chain import ChainWindow, InvalidInput
from .result import OperatorResult, QueryResult
from .solver import (
    FeasibleSolver,
    ProjectionProblem,
    ProjectionSolution,
    ResourceLimits,
)
from .validation import ValidationError, validate_projection
from .operator import HomologyOperator
from .family import OperatorFamily

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
    "ValidationError",
    "validate_projection",
    "HomologyOperator",
    "OperatorFamily",
    "__version__",
]
