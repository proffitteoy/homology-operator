"""Deterministic feasible construction, with explicit reference resource limits."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from math import isfinite
from time import perf_counter
from uuid import uuid4

from .algebra import Matrix
from .chain import ChainWindow
from .result import QueryResult, _freeze, content_id, make_identity


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
        return {
            "states": self.states,
            "wall_time": perf_counter() - self.started,
            "limits": asdict(self.limits),
        }


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
    arithmetic_policy: str | None = None
    input_structure: str = "GeneralChainWindow"
    matrix_free_output: bool = False
    deterministic: bool = True
    solver_options: object = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.solver_options, Mapping):
            object.__setattr__(self, "solver_options", _freeze(self.solver_options))

    def solver_config(self, method):
        return {
            "method": method,
            "objective": self.objective,
            "arithmetic_policy": self.arithmetic_policy or self.window.arithmetic,
            "requested_certificate_level": self.requested_certificate_level,
            "tie_break_policy": self.tie_break_policy,
            "input_structure": self.input_structure,
            "matrix_free_output": self.matrix_free_output,
            "deterministic": self.deterministic,
            "resource_limits": asdict(self.resource_limits),
            "solver_options": self.solver_options,
        }


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
    arithmetic_policy: str | None = None
    lower_bound: object = None
    upper_bound: object = None
    solver_config: object = None

    def __post_init__(self):
        for name in ("identity", "certificate", "resource_usage", "solver_config"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _freeze(dict(value)))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def solver_metadata(self):
        return {
            "status": self.status,
            "certificate_level": self.certificate_level,
            "solver_run_id": self.solver_run_id,
            "tie_break_policy": self.tie_break_policy,
            "method": self.method,
            "arithmetic_policy": self.arithmetic_policy,
            "objective": self.objective.to_dict(),
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "optimality_gap": self.optimality_gap,
            "solver_config": self.solver_config,
            "solver_config_id": self.solver_config_id,
            "diagnostics": self.diagnostics,
            "resource_usage": dict(self.resource_usage),
        }

    @property
    def solver_config_id(self):
        return (
            None
            if self.solver_config is None
            else content_id("solver-config", self.solver_config)
        )

    @property
    def optimality_gap(self):
        if self.lower_bound is None or self.upper_bound is None:
            return None
        from fractions import Fraction

        difference = self.upper_bound - self.lower_bound
        return {
            "absolute": difference,
            "relative": None
            if self.lower_bound == 0
            else Fraction(difference) / Fraction(self.lower_bound),
        }


def check_solver_request(problem, capabilities):
    """Return a structured preflight rejection; never select an implicit fallback."""
    if (
        not isinstance(problem, ProjectionProblem)
        or not isinstance(problem.window, ChainWindow)
        or not isinstance(problem.resource_limits, ResourceLimits)
        or not isinstance(problem.solver_options, Mapping)
        or type(problem.matrix_free_output) is not bool
        or type(problem.deterministic) is not bool
        or any(
            not isinstance(value, str)
            for value in (
                problem.objective,
                problem.requested_certificate_level,
                problem.tie_break_policy,
                problem.input_structure,
            )
        )
        or (
            problem.arithmetic_policy is not None
            and not isinstance(problem.arithmetic_policy, str)
        )
    ):
        return "InvalidProblem", "invalid input or request fields"
    if not isinstance(capabilities, Mapping):
        return "Unavailable", "backend capabilities must be a mapping"
    checks = (
        (problem.objective, "objectives"),
        (problem.arithmetic_policy or problem.window.arithmetic, "arithmetic_policies"),
        (problem.input_structure, "input_structures"),
        (problem.requested_certificate_level, "certificate_levels"),
        (problem.tie_break_policy, "tie_break_policies"),
    )
    for value, key in checks:
        if value not in capabilities.get(key, ()):
            return "Unavailable", f"unsupported {key}: {value}"
    if problem.arithmetic_policy not in {None, problem.window.arithmetic}:
        return "Unavailable", "arithmetic policy differs from the input weights"
    if problem.matrix_free_output and not capabilities.get("matrix_free_output"):
        return "Unavailable", "matrix-free output is unsupported"
    if problem.deterministic and not capabilities.get("deterministic"):
        return "Unavailable", "deterministic output is unsupported"
    if set(problem.solver_options) - set(capabilities.get("solver_options", ())):
        return "Unavailable", "unsupported solver options"
    dimensions = capabilities.get("supported_dimensions")
    if dimensions is not None and problem.window.k not in dimensions:
        return "Unavailable", "unsupported homological degree"
    betti_range = capabilities.get("supported_betti_range")
    if betti_range is not None:
        beta = problem.window.n - problem.window.A.rank() - problem.window.D.rank()
        if not betti_range[0] <= beta <= betti_range[1]:
            return "Unavailable", "unsupported Betti number"
    requested_limits = {
        key
        for key, value in asdict(problem.resource_limits).items()
        if value is not None
    }
    if requested_limits - set(capabilities.get("resource_limits", ())):
        return "Unavailable", "unsupported resource limits"
    return None


class FeasibleSolver:
    def capabilities(self):
        return _freeze(
            {
                "objectives": ("MinimumStretch",),
                "arithmetic_policies": (
                    "ExactInteger",
                    "ExactRational",
                    "FloatingPoint",
                ),
                "input_structures": ("GeneralChainWindow",),
                "certificate_levels": ("Feasible",),
                "tie_break_policies": ("StableBasisOrder",),
                "supported_dimensions": None,
                "supported_betti_range": None,
                "matrix_free_output": False,
                "deterministic": True,
                "resource_limits": (
                    "state_limit",
                    "wall_time_limit",
                    "matrix_entry_limit",
                ),
                "solver_options": (),
            }
        )

    def solve(self, problem):
        run_id = str(uuid4())
        rejection = check_solver_request(problem, self.capabilities())
        if rejection is not None:
            return ProjectionSolution(rejection[0], run_id, diagnostics=(rejection[1],))
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
                arithmetic_policy=window.arithmetic,
                solver_config=problem.solver_config("FeasibleSolver"),
            )
        except _Exhausted as error:
            return ProjectionSolution(
                "ResourceExhausted",
                run_id,
                resource_usage=budget.usage(),
                diagnostics=(str(error),),
                arithmetic_policy=window.arithmetic,
                solver_config=problem.solver_config("FeasibleSolver"),
            )


def solve_projection(problem, backend="FeasibleSolver"):
    """Dispatch a declared solver and independently check any returned action."""
    from .validation import validate_solution

    if isinstance(backend, str):
        if backend != "FeasibleSolver":
            return ProjectionSolution(
                "Unavailable",
                str(uuid4()),
                diagnostics=(f"unknown backend: {backend}",),
            )
        backend = FeasibleSolver()
    if not callable(getattr(backend, "capabilities", None)) or not callable(
        getattr(backend, "solve", None)
    ):
        return ProjectionSolution(
            "Unavailable",
            str(uuid4()),
            diagnostics=("backend has no solver interface",),
        )
    try:
        rejection = check_solver_request(problem, backend.capabilities())
        if rejection is not None:
            return ProjectionSolution(
                rejection[0], str(uuid4()), diagnostics=(rejection[1],)
            )
        solution = backend.solve(problem)
        if not isinstance(solution, ProjectionSolution):
            raise ValueError("backend did not return ProjectionSolution")
        expected_config = problem.solver_config(solution.method)
        if solution.solver_config_id != content_id("solver-config", expected_config):
            raise ValueError(
                "returned solver configuration does not match this request"
            )
        if (
            solution.tie_break_policy != problem.tie_break_policy
            or solution.arithmetic_policy != expected_config["arithmetic_policy"]
        ):
            raise ValueError("returned solver policies do not match this request")
        if "limits" in solution.resource_usage and content_id(
            "limits", solution.resource_usage["limits"]
        ) != content_id("limits", expected_config["resource_limits"]):
            raise ValueError("reported resource limits do not match this request")
        if solution.projection is not None:
            validate_solution(problem.window, solution)
            acceptable = {
                "Feasible": {
                    "Feasible",
                    "Heuristic",
                    "CertifiedUpperBound",
                    "CertifiedInterval",
                    "ExactOptimal",
                },
                "Heuristic": {
                    "Feasible",
                    "Heuristic",
                    "CertifiedUpperBound",
                    "CertifiedInterval",
                    "ExactOptimal",
                },
                "CertifiedUpperBound": {
                    "CertifiedUpperBound",
                    "CertifiedInterval",
                    "ExactOptimal",
                },
                "CertifiedInterval": {"CertifiedInterval", "ExactOptimal"},
                "ExactOptimal": {"ExactOptimal"},
            }
            if (
                solution.status != "ResourceExhausted"
                and solution.certificate_level
                not in acceptable[problem.requested_certificate_level]
            ):
                raise ValueError("backend did not meet the requested certificate level")
        elif (
            solution.status
            not in {
                "ResourceExhausted",
                "Unavailable",
                "InvalidProblem",
                "NumericalFailure",
                "InternalError",
            }
            or solution.certificate_level is not None
            or solution.certificate
            or solution.lower_bound is not None
            or solution.upper_bound is not None
            or solution.objective.state != "NotComputed"
            or solution.objective.identity is not None
        ):
            raise ValueError("missing action cannot claim feasibility or certification")
    except Exception as error:
        return ProjectionSolution(
            "InternalError", str(uuid4()), diagnostics=(str(error),)
        )
    return solution
