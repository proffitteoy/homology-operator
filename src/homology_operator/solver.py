"""Deterministic feasible construction, with explicit reference resource limits."""

from dataclasses import dataclass, field
from math import isfinite
from time import perf_counter
from types import MappingProxyType
from uuid import uuid4

from .algebra import Matrix
from .chain import ChainWindow
from .result import QueryResult, make_identity


@dataclass(frozen=True)
class ResourceLimits:
    state_limit: int = 100_000
    wall_time_limit: float = 10.0
    matrix_entry_limit: int = 1_000_000

    def __post_init__(self):
        for value in (self.state_limit, self.matrix_entry_limit):
            if type(value) is not int or value < 0:
                raise ValueError("resource counts must be nonnegative integers")
        if (
            isinstance(self.wall_time_limit, bool)
            or not isinstance(self.wall_time_limit, (int, float))
            or not isfinite(self.wall_time_limit)
            or self.wall_time_limit < 0
        ):
            raise ValueError("wall_time_limit must be finite and nonnegative")


class _Exhausted(Exception):
    pass


class _Budget:
    def __init__(self, limits):
        self.limits = limits
        self.started = perf_counter()
        self.states = 0

    def step(self, count=1):
        if self.states + count > self.limits.state_limit:
            raise _Exhausted("state_limit")
        if perf_counter() - self.started >= self.limits.wall_time_limit:
            raise _Exhausted("wall_time_limit")
        self.states += count

    def entries(self, count):
        if count > self.limits.matrix_entry_limit:
            raise _Exhausted("matrix_entry_limit")

    def usage(self):
        return {"states": self.states, "wall_time": perf_counter() - self.started}


def generalized_inverse(matrix, budget=None):
    """Return G with M G M=M using row operations on [M | identity_matrix]."""
    if not isinstance(matrix, Matrix):
        raise ValueError("generalized_inverse requires a Matrix")
    if budget is not None:
        budget.step()
        budget.entries(matrix.nrows * (matrix.ncols + matrix.nrows))
    augmented = Matrix.from_rows(
        (
            row + unit
            for row, unit in zip(matrix.rows, Matrix.identity(matrix.nrows).rows)
        ),
        ncols=matrix.ncols + matrix.nrows,
    )
    reduced, pivots = augmented.rref()
    rows = [(0,) * matrix.nrows for _ in range(matrix.ncols)]
    for row, pivot in enumerate(pivots):
        if pivot < matrix.ncols:
            rows[pivot] = reduced.rows[row][matrix.ncols :]
        if budget is not None:
            budget.step()
    return Matrix(matrix.ncols, matrix.nrows, tuple(rows))


@dataclass(frozen=True)
class ProjectionProblem:
    window: ChainWindow
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    objective: str = "MinimumStretch"
    requested_certificate_level: str = "Feasible"
    tie_break_policy: str = "StableBasisOrder"


@dataclass(frozen=True)
class ProjectionSolution:
    status: str
    solver_run_id: str
    projection: Matrix | None = None
    identity: object = None
    certificate_level: str | None = None
    objective: QueryResult = field(default_factory=lambda: QueryResult("NotComputed"))
    certificate: object = field(default_factory=dict)
    resource_usage: object = field(default_factory=dict)
    diagnostics: tuple = ()
    tie_break_policy: str = "StableBasisOrder"
    generalized_inverse_a: Matrix | None = None
    generalized_inverse_d: Matrix | None = None
    method: str = "FeasibleSolver"

    def __post_init__(self):
        for name in ("identity", "certificate", "resource_usage"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, MappingProxyType(dict(value)))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def solver_metadata(self):
        return {
            "status": self.status,
            "certificate_level": self.certificate_level,
            "solver_run_id": self.solver_run_id,
            "tie_break_policy": self.tie_break_policy,
            "method": self.method,
            "objective": self.objective.to_dict(),
            "lower_bound": None,
            "upper_bound": None,
            "optimality_gap": None,
            "resource_usage": dict(self.resource_usage),
        }


class FeasibleSolver:
    def solve(self, problem):
        run_id = str(uuid4())
        if (
            not isinstance(problem, ProjectionProblem)
            or not isinstance(problem.window, ChainWindow)
            or not isinstance(problem.resource_limits, ResourceLimits)
        ):
            return ProjectionSolution(
                "InvalidProblem", run_id, diagnostics=("invalid input",)
            )
        if (
            problem.objective != "MinimumStretch"
            or problem.requested_certificate_level != "Feasible"
            or problem.tie_break_policy != "StableBasisOrder"
        ):
            return ProjectionSolution(
                "Unavailable", run_id, diagnostics=("unsupported policy",)
            )
        window = problem.window
        budget = _Budget(problem.resource_limits)
        try:
            budget.step()
            # A conservative entry cap, not an assertion about peak process memory.
            budget.entries(
                window.m * window.n
                + window.n * window.p
                + window.n * window.m
                + window.p * window.n
                + 4 * window.n**2
            )
            G = generalized_inverse(window.A, budget)
            U = generalized_inverse(window.D, budget)
            budget.step()
            if (
                window.A @ G @ window.A != window.A
                or window.D @ U @ window.D != window.D
            ):
                return ProjectionSolution(
                    "InternalError", run_id, diagnostics=("generalized inverse",)
                )
            identity_matrix = Matrix.identity(window.n)
            P = (identity_matrix + window.D @ U) @ (identity_matrix + G @ window.A)
            budget.step()
            identity = make_identity(window, P, run_id, problem.tie_break_policy)
            return ProjectionSolution(
                "FeasibleOnly",
                run_id,
                P,
                identity,
                "Feasible",
                QueryResult("NotComputed", identity=identity),
                {
                    "a_g_a": True,
                    "d_u_d": True,
                    "exact_arithmetic": True,
                    "verification_method": "GeneralizedInverseConstruction",
                },
                budget.usage(),
                (),
                problem.tie_break_policy,
                G,
                U,
            )
        except _Exhausted as error:
            return ProjectionSolution(
                "ResourceExhausted",
                run_id,
                resource_usage=budget.usage(),
                diagnostics=(str(error),),
            )
