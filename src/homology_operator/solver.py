"""Deterministic feasible construction, with explicit reference resource limits."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from fractions import Fraction
from itertools import product
from math import isfinite
from time import perf_counter
from threading import Event
from uuid import uuid4

from .algebra import Matrix, CyclicAction, CompactAction
from .chain import ChainWindow, matrix_data
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


class CancellationToken:
    """One-shot cooperative cancellation; runtime state is never serialized."""

    def __init__(self):
        self._event = Event()
        self._native = None

    def cancel(self):
        self._event.set()
        if self._native is not None:
            self._native.cancel()

    def is_cancelled(self):
        return self._event.is_set()

    def _native_handle(self):
        if self._native is None:
            from .native import _extension

            self._native = _extension().CancellationFlag()
            if self.is_cancelled():
                self._native.cancel()
        return self._native


class _Exhausted(Exception):
    pass


class _Budget:
    def __init__(self, limits, native=False, cancellation=None):
        self.cancellation = cancellation
        self.native = native
        self.native_detail = {}
        self.limits = limits
        self.started = perf_counter()
        self.states = 0

    def step(self, count=1):
        if self.cancellation is not None and self.cancellation.is_cancelled():
            raise _Exhausted("cancelled")
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
            **(
                {
                    "execution_backend": "packed-rust-v1",
                    "native_detail": self.native_detail,
                }
                if self.native
                else {}
            ),
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
    cancellation: CancellationToken | None = field(
        default=None, repr=False, compare=False
    )

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
    projection: Matrix | CyclicAction | CompactAction | None = None
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
        or (
            problem.cancellation is not None
            and not isinstance(problem.cancellation, CancellationToken)
        )
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
    if problem.cancellation is not None and not capabilities.get("cancellation", False):
        return "Unavailable", "cooperative cancellation is unsupported"
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
    if capabilities.get("execution_backend") == "packed-rust-v1":
        from .native import _extension

        try:
            extension = _extension()
            if not hasattr(extension, "span_objective"):
                return (
                    "Unavailable",
                    "native extension lacks S4-05 kernels; rebuild the release wheel",
                )
        except ImportError:
            return "Unavailable", "optional native extension is not installed"
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
                "cancellation": True,
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
        budget = _Budget(problem.resource_limits, cancellation=problem.cancellation)
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


def solve_projection(problem, backend="FeasibleSolver", *, fallback=False):
    """Dispatch a declared solver and independently check any returned action."""
    from .validation import validate_solution

    method = backend if isinstance(backend, str) else type(backend).__name__
    if type(fallback) is not bool:
        return ProjectionSolution(
            "InvalidProblem",
            str(uuid4()),
            diagnostics=("fallback must be boolean",),
            method=method,
        )
    requested_method = method
    if isinstance(backend, str):
        from .native import NativeFeasibleSolver, NativeFactorizedSolver

        constructors = {
            "FeasibleSolver": FeasibleSolver,
            "ExhaustiveExactSolver": ExhaustiveExactSolver,
            "Rank2ExactSolver": Rank2ExactSolver,
            "StructuredFamilySolver": StructuredFamilySolver,
            "GreedyCertifiedSolver": GreedyCertifiedSolver,
            "NativeExhaustiveExactSolver": lambda: ExhaustiveExactSolver(native=True),
            "NativeGreedyCertifiedSolver": lambda: GreedyCertifiedSolver(native=True),
            "NativeRank2ExactSolver": lambda: Rank2ExactSolver(native=True),
            "NativeStructuredFamilySolver": lambda: StructuredFamilySolver(native=True),
            "NativeFeasibleSolver": NativeFeasibleSolver,
            "NativeFactorizedSolver": NativeFactorizedSolver,
        }
        if backend not in constructors:
            return ProjectionSolution(
                "Unavailable",
                str(uuid4()),
                diagnostics=(f"unknown backend: {backend}",),
                method=method,
            )
        backend = constructors[backend]()
    if not callable(getattr(backend, "capabilities", None)) or not callable(
        getattr(backend, "solve", None)
    ):
        return ProjectionSolution(
            "Unavailable",
            str(uuid4()),
            diagnostics=("backend has no solver interface",),
            method=method,
        )
    try:
        rejection = check_solver_request(problem, backend.capabilities())
        if rejection is not None:
            solution = ProjectionSolution(
                rejection[0], str(uuid4()), diagnostics=(rejection[1],), method=method
            )
        else:
            solution = backend.solve(problem)
        if not isinstance(solution, ProjectionSolution):
            raise ValueError("backend did not return ProjectionSolution")
        fallback_methods = {
            "NativeFeasibleSolver": "FeasibleSolver",
            "NativeExhaustiveExactSolver": "ExhaustiveExactSolver",
            "NativeGreedyCertifiedSolver": "GreedyCertifiedSolver",
            "NativeRank2ExactSolver": "Rank2ExactSolver",
            "NativeStructuredFamilySolver": "StructuredFamilySolver",
        }
        if (
            fallback
            and solution.status == "Unavailable"
            and requested_method in fallback_methods
        ):
            original_reason = solution.diagnostics
            selected = fallback_methods[requested_method]
            solution = solve_projection(problem, selected)
            return replace(
                solution,
                resource_usage={
                    **solution.resource_usage,
                    "backend_selection": {
                        "requested": requested_method,
                        "selected": selected,
                        "fallback_reason": original_reason,
                    },
                },
            )
        if rejection is not None:
            return solution
        # A wrapper may return its inner solver's method and configuration.
        method = solution.method
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
            validation_started = perf_counter()
            checks = validate_solution(problem.window, solution)
            if getattr(backend, "native", False):
                solution = replace(
                    solution,
                    resource_usage={
                        **solution.resource_usage,
                        "independent_validation_seconds": perf_counter()
                        - validation_started,
                        "certificate_replay_backend": checks.get(
                            "certificate_replay_backend", "python-reference"
                        ),
                    },
                )
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
            "InternalError", str(uuid4()), diagnostics=(str(error),), method=method
        )
    return solution


def _cycle_objective(window, projection, cycles, budget):
    if budget.native:
        from .native import _span_objective

        result = _span_objective(window, projection, cycles.transpose().rows, budget)
        if result is not None:
            return result
    value, witness = Fraction(0), None
    for coefficients in product((0, 1), repeat=cycles.ncols):
        if not any(coefficients):
            continue
        budget.step()
        z = cycles.apply(coefficients)
        numerator = sum(w for w, bit in zip(window.weights, projection.apply(z)) if bit)
        denominator = sum(w for w, bit in zip(window.weights, z) if bit)
        ratio = Fraction(numerator) / Fraction(denominator)
        if witness is None or ratio > value:
            value, witness = ratio, z
    return value, witness


def _prepare(matrix, budget):
    if not budget.native:
        return matrix
    from .native import PreparedMatrix

    budget.native_detail["prepared_decompositions"] = (
        budget.native_detail.get("prepared_decompositions", 0) + 1
    )
    return PreparedMatrix(matrix, cancellation=budget.cancellation)


def _multiply(left, right, budget):
    if not budget.native:
        return left @ right
    from .native import packed_multiply

    budget.native_detail["packed_products"] = (
        budget.native_detail.get("packed_products", 0) + 1
    )
    return packed_multiply(left, right)


def _cycle_table(window, cycles, budget):
    if budget.native:
        from .native import _span_table

        result = _span_table(window, cycles.transpose().rows, budget)
        if result is not None:
            return result
    result = []
    for bits in product((0, 1), repeat=cycles.ncols):
        if not any(bits):
            continue
        budget.step()
        z = cycles.apply(bits)
        result.append((z, sum(w for w, bit in zip(window.weights, z) if bit)))
    return result


class ExhaustiveExactSolver:
    """Search 2^(boundary_rank * beta) cycle retractions, for tiny rational inputs.

    Implements pinned compressed_native_operator's complete parameterization.
    Non-cycle extensions are fixed by the feasible constructor's cycle retraction.
    It never uses PH results or shortest-class tables as inputs or intermediates.
    """

    def __init__(self, *, native=False):
        if type(native) is not bool:
            raise ValueError("native must be a boolean")
        self.native = native

    def capabilities(self):
        return _freeze(
            {
                **FeasibleSolver().capabilities(),
                "execution_backend": "packed-rust-v1"
                if self.native
                else "python-reference",
                "arithmetic_policies": ("ExactInteger", "ExactRational"),
                "certificate_levels": (
                    "Feasible",
                    "CertifiedUpperBound",
                    "CertifiedInterval",
                    "ExactOptimal",
                ),
                "tie_break_policies": ("StableBasisOrder", "LexicographicProjection"),
            }
        )

    def solve(self, problem):
        method = (
            "NativeExhaustiveExactSolver" if self.native else "ExhaustiveExactSolver"
        )
        run_id = str(uuid4())
        rejection = check_solver_request(problem, self.capabilities())
        if rejection is not None:
            return ProjectionSolution(
                rejection[0],
                run_id,
                method=method,
                diagnostics=(rejection[1],),
            )
        window = problem.window
        config = problem.solver_config(method)
        budget = _Budget(problem.resource_limits, self.native, problem.cancellation)
        seed = FeasibleSolver().solve(
            replace(
                problem,
                requested_certificate_level="Feasible",
                tie_break_policy="StableBasisOrder",
            )
        )
        if seed.projection is None:
            return replace(
                seed,
                solver_run_id=run_id,
                method=method,
                solver_config=config,
                tie_break_policy=problem.tie_break_policy,
                arithmetic_policy=window.arithmetic,
            )
        budget.states = seed.resource_usage["states"]
        best = seed.projection
        best_value, best_witness = None, None
        count, visited, cycle_count, R = None, 0, None, None
        exhausted = None
        try:
            budget.step()
            R = Matrix.identity(window.n) + seed.generalized_inverse_a @ window.A
            N = Matrix.from_columns(
                _prepare(window.A, budget).kernel_basis(), nrows=window.n
            )
            F = Matrix.from_columns(
                _prepare(window.D, budget).image_basis(), nrows=window.n
            )
            d, r = N.ncols, F.ncols
            beta = d - r
            count, cycle_count = 1 << (r * beta), (1 << d) - 1
            # Independent certificate replay has the same finite reference support.
            # Larger requests retain the seed; they cannot claim an unreplayable optimum.
            budget.entries(4 * window.n**2 + window.n * d + d * r + window.n * r)
            if cycle_count > 100_000:
                raise _Exhausted("certificate_replay_state_limit")
            best_value, best_witness = _cycle_objective(window, best, N, budget)
            if count * max(1, cycle_count) > 100_000:
                raise _Exhausted("certificate_replay_state_limit")
            if count == 1:
                visited = 1
            else:
                M = Matrix.from_columns(
                    (
                        _prepare(N, budget).solve_many(F.transpose().rows)
                        if budget.native
                        else (N.solve(f) for f in F.transpose().rows)
                    ),
                    nrows=d,
                )
                constraints = M.transpose()
                prepared = _prepare(constraints, budget)
                offsets = prepared.kernel_basis()
                particulars = tuple(
                    prepared.solve(unit) for unit in Matrix.identity(r).rows
                )
                T = Matrix.from_columns(
                    (
                        _prepare(N, budget).solve_many(R.transpose().rows)
                        if budget.native
                        else (N.solve(z) for z in R.transpose().rows)
                    ),
                    nrows=d,
                )
                for parameters in product((0, 1), repeat=r * beta):
                    budget.step()
                    Y = Matrix.from_rows(
                        (
                            tuple(
                                particular[j]
                                ^ (
                                    sum(
                                        parameters[i * beta + h] * offsets[h][j]
                                        for h in range(beta)
                                    )
                                    % 2
                                )
                                for j in range(d)
                            )
                            for i, particular in enumerate(particulars)
                        ),
                        ncols=d,
                    )
                    candidate = R + _multiply(_multiply(F, Y, budget), T, budget)
                    value, witness = _cycle_objective(window, candidate, N, budget)
                    visited += 1
                    key = tuple(
                        sum(bit << j for j, bit in enumerate(column))
                        for column in candidate.transpose().rows
                    )
                    best_key = tuple(
                        sum(bit << j for j, bit in enumerate(column))
                        for column in best.transpose().rows
                    )
                    if (value, key) < (best_value, best_key):
                        best, best_value, best_witness = candidate, value, witness
        except _Exhausted as error:
            exhausted = str(error)
        identity = make_identity(window, best, run_id, problem.tie_break_policy)
        usage = {
            **budget.usage(),
            "candidates_visited": visited,
            "candidate_count": count,
            "nonzero_cycle_inputs": cycle_count,
            "tie_break_complete": exhausted is None,
        }
        if best_value is None:
            return ProjectionSolution(
                "ResourceExhausted",
                run_id,
                best,
                identity,
                "Feasible",
                QueryResult("ResourceExhausted", identity=identity),
                resource_usage=usage,
                diagnostics=(exhausted,),
                tie_break_policy=problem.tie_break_policy,
                method=method,
                arithmetic_policy=window.arithmetic,
                solver_config=config,
            )
        objective = QueryResult(
            "EmptyDomain" if cycle_count == 0 else "Computed",
            best_value,
            identity,
            True,
            {"witness": best_witness, "nonzero_cycles": cycle_count},
        )
        if exhausted is not None:
            # No incomplete search claims ExactOptimal, including a point optimum.
            # This search tracks the trivial nonnegative lower bound until completion.
            proof = {
                "kind": "CycleBounds",
                "nonzero_cycles": cycle_count,
                "lower_bound_method": "UniversalHomology",
            }
            return ProjectionSolution(
                "ResourceExhausted",
                run_id,
                best,
                identity,
                "CertifiedInterval",
                objective,
                {"optimization": proof},
                usage,
                (exhausted,),
                problem.tie_break_policy,
                method=method,
                arithmetic_policy=window.arithmetic,
                lower_bound=Fraction(0),
                upper_bound=best_value,
                solver_config=config,
            )
        proof = {
            "kind": "ExhaustiveSearch",
            "candidate_count": count,
            "nonzero_cycles": cycle_count,
            "cycle_retraction": matrix_data(R),
            "tie_break_complete": True,
        }
        return ProjectionSolution(
            "Solved",
            run_id,
            best,
            identity,
            "ExactOptimal",
            objective,
            {"optimization": proof},
            usage,
            tie_break_policy=problem.tie_break_policy,
            method=method,
            arithmetic_policy=window.arithmetic,
            lower_bound=best_value,
            upper_bound=best_value,
            solver_config=config,
        )


def _pareto_rank2(window, pair, boundaries, budget):
    """Pinned T5: remove a supported boundary using the heaviest of three colors."""
    x, y = pair
    trace = []
    F = Matrix.from_columns(boundaries, nrows=window.n)
    while True:
        budget.step()
        outside_matrix = Matrix.from_rows(
            (row for j, row in enumerate(F.rows) if not (x[j] or y[j])),
            ncols=F.ncols,
        )
        outside = _prepare(outside_matrix, budget).kernel_basis()
        if not outside:
            return (x, y), tuple(trace)
        b = F.apply(outside[0])
        costs = tuple(
            sum(
                w
                for w, bit, a, c in zip(window.weights, b, x, y)
                if bit and a + 2 * c == label
            )
            for label in (1, 2, 3)
        )
        label = max((1, 2, 3), key=lambda a: (costs[a - 1], -a))
        trace.append({"boundary": b, "color": label})
        x = tuple(a ^ (bit if label & 1 else 0) for a, bit in zip(x, b))
        y = tuple(a ^ (bit if label & 2 else 0) for a, bit in zip(y, b))


class Rank2ExactSolver:
    """Finite rank-two search: Pareto-reduced sections or verified three-label cuts.

    General rank two does not imply planarity or Euclidean flat-torus geometry.
    The cut route requires an explicit chain/cut-space equivalence witness.
    """

    def __init__(self, *, native=False):
        if type(native) is not bool:
            raise ValueError("native must be a boolean")
        self.native = native

    def capabilities(self):
        return _freeze(
            {
                **ExhaustiveExactSolver().capabilities(),
                "supported_betti_range": (2, 2),
                "execution_backend": "packed-rust-v1"
                if self.native
                else "python-reference",
                "input_structures": (
                    "GeneralChainWindow",
                    "GraphCycle",
                    "ThreeTerminalCut",
                ),
                "tie_break_policies": ("StableBasisOrder",),
                "solver_options": ("dual_vertex_count", "dual_edges", "terminals"),
            }
        )

    def solve(self, problem):
        from .validation import validate_rank2_structure

        method = "NativeRank2ExactSolver" if self.native else "Rank2ExactSolver"
        run_id = str(uuid4())
        rejection = check_solver_request(problem, self.capabilities())
        if rejection is not None:
            return ProjectionSolution(
                rejection[0],
                run_id,
                method=method,
                diagnostics=(rejection[1],),
            )
        window = problem.window
        config = problem.solver_config(method)
        budget = _Budget(problem.resource_limits, self.native, problem.cancellation)
        try:
            cut = validate_rank2_structure(
                window, problem.input_structure, problem.solver_options
            )
        except ValueError as error:
            return ProjectionSolution(
                "Unavailable",
                run_id,
                method=method,
                diagnostics=(str(error),),
                solver_config=config,
                arithmetic_policy=window.arithmetic,
            )
        seed = FeasibleSolver().solve(
            replace(
                problem,
                requested_certificate_level="Feasible",
                input_structure="GeneralChainWindow",
                solver_options={},
            )
        )
        if seed.projection is None:
            return replace(
                seed,
                solver_run_id=run_id,
                method=method,
                solver_config=config,
            )
        budget.states = seed.resource_usage["states"]
        best, value, witness = seed.projection, None, None
        cycle_count, count, visited = None, None, 0
        exhausted, proof = None, {}
        try:
            budget.step()
            R = Matrix.identity(window.n) + seed.generalized_inverse_a @ window.A
            boundaries = _prepare(window.D, budget).image_basis()
            r = len(boundaries)
            cycle_count, count = (1 << (r + 2)) - 1, 1 << (2 * r)
            if count * cycle_count > 100_000:
                raise _Exhausted("certificate_replay_state_limit")
            budget.entries(10 * window.n**2 + cycle_count * window.n)
            full = list(boundaries)
            H = []
            if cut is None:
                for z in _prepare(window.A, budget).kernel_basis():
                    if _prepare(
                        Matrix.from_columns((*full, z), nrows=window.n), budget
                    ).rank() > len(full):
                        H.append(z)
                        full.append(z)
            else:
                delta, vertices, terminals, internal = cut
                H = [
                    tuple(
                        int(u == t) ^ int(v == t)
                        for u, v in problem.solver_options["dual_edges"]
                    )
                    for t in terminals[1:]
                ]
                full.extend(H)
            basis = Matrix.from_columns(full, nrows=window.n)
            coordinates = Matrix.from_columns(
                (
                    tuple(
                        c[r:]
                        for c in _prepare(basis, budget).solve_many(R.transpose().rows)
                    )
                    if budget.native
                    else (basis.solve(z)[r:] for z in R.transpose().rows)
                ),
                nrows=2,
            )
            minima, minimum_witnesses = [None] * 3, [None] * 3
            for encoded, (z, mass) in enumerate(_cycle_table(window, basis, budget), 1):
                h = ((encoded >> 1) & 1) + 2 * (encoded & 1)
                if h and (minima[h - 1] is None or mass < minima[h - 1]):
                    minima[h - 1], minimum_witnesses[h - 1] = mass, z

            def objective(pair):
                x, y = pair
                outputs = (x, y, tuple(a ^ b for a, b in zip(x, y)))
                ratios = tuple(
                    Fraction(sum(w for w, bit in zip(window.weights, z) if bit))
                    / minima[i]
                    for i, z in enumerate(outputs)
                )
                j = max(range(3), key=lambda i: ratios[i])
                return ratios[j], minimum_witnesses[j]

            value, witness = objective(tuple(best.apply(z) for z in H))
            best_reduced = None
            params = (
                product((0, 1), repeat=2 * r)
                if cut is None
                else product((0, 1, 2), repeat=len(internal))
            )
            F = Matrix.from_columns(boundaries, nrows=window.n)
            for parameters in params:
                budget.step()
                if cut is None:
                    initial = tuple(
                        tuple(
                            a ^ b
                            for a, b in zip(z, F.apply(parameters[i * r : (i + 1) * r]))
                        )
                        for i, z in enumerate(H)
                    )
                    pair, trace = _pareto_rank2(window, initial, boundaries, budget)
                    labels = None
                else:
                    labels = [0] * vertices
                    labels[terminals[1]], labels[terminals[2]] = 1, 2
                    for v, label in zip(internal, parameters):
                        labels[v] = label
                    pair = tuple(
                        tuple(
                            ((labels[u] ^ labels[v]) >> i) & 1
                            for u, v in problem.solver_options["dual_edges"]
                        )
                        for i in range(2)
                    )
                    initial, trace = pair, ()
                candidate = _multiply(
                    Matrix.from_columns(pair, nrows=window.n), coordinates, budget
                )
                current, current_witness = objective(pair)
                key = tuple(
                    sum(bit << j for j, bit in enumerate(z))
                    for z in candidate.transpose().rows
                )
                visited += 1
                if best_reduced is None or (current, key) < best_reduced:
                    best_reduced = current, key
                    final_action, final_witness = candidate, current_witness
                    proof = {
                        "kind": "Rank2Search",
                        "candidate_count": count,
                        "nonzero_cycles": cycle_count,
                        "cycle_retraction": matrix_data(R),
                        "tie_break_complete": True,
                        "structure": problem.input_structure,
                        "searched_candidates": count
                        if cut is None
                        else 3 ** len(internal),
                        "quotient_generators": tuple(H),
                        "class_minima": tuple(minima),
                        "initial_generators": initial,
                        "pareto_steps": trace,
                        "terminal_labels": labels,
                    }
                if current < value:
                    best, value, witness = candidate, current, current_witness
            best, value, witness = final_action, best_reduced[0], final_witness
        except _Exhausted as error:
            exhausted = str(error)
        identity = make_identity(window, best, run_id, problem.tie_break_policy)
        lower = None if value is None else (value if exhausted is None else Fraction(0))
        level = (
            "Feasible"
            if value is None
            else ("ExactOptimal" if exhausted is None else "CertifiedInterval")
        )
        if exhausted is not None:
            proof = (
                {}
                if value is None
                else {
                    "kind": "CycleBounds",
                    "nonzero_cycles": cycle_count,
                    "lower_bound_method": "UniversalHomology",
                }
            )
        return ProjectionSolution(
            "Solved" if exhausted is None else "ResourceExhausted",
            run_id,
            best,
            identity,
            level,
            QueryResult("ResourceExhausted", identity=identity)
            if value is None
            else QueryResult(
                "Computed",
                value,
                identity,
                True,
                {"witness": witness, "nonzero_cycles": cycle_count},
            ),
            {"optimization": proof} if proof else {},
            {
                **budget.usage(),
                "candidates_visited": visited,
                "nonzero_cycle_inputs": cycle_count,
            },
            (exhausted,) if exhausted else (),
            problem.tie_break_policy,
            method=method,
            arithmetic_policy=window.arithmetic,
            lower_bound=lower,
            upper_bound=value,
            solver_config=config,
        )


def _structured_images(action, vectors, budget):
    if not budget.native:
        return tuple(action.apply(z) for z in vectors)
    from .native import _apply_many

    budget.native_detail["cyclic_batch_calls"] = (
        budget.native_detail.get("cyclic_batch_calls", 0) + 1
    )
    return _apply_many(action, vectors)


class StructuredFamilySolver:
    """Pinned T-B1 cyclic trace family, with explicit recognition and a small cap."""

    def __init__(self, *, native=False):
        if type(native) is not bool:
            raise ValueError("native must be a boolean")
        self.native = native

    def capabilities(self):
        return _freeze(
            {
                **FeasibleSolver().capabilities(),
                "execution_backend": "packed-rust-v1"
                if self.native
                else "python-reference",
                "arithmetic_policies": ("ExactInteger", "ExactRational"),
                "input_structures": ("CyclicTrace",),
                "certificate_levels": (
                    "Feasible",
                    "CertifiedUpperBound",
                    "CertifiedInterval",
                    "ExactOptimal",
                ),
                "tie_break_policies": ("StableBasisOrder", "StructuredCanonical"),
                "matrix_free_output": True,
            }
        )

    def solve(self, problem):
        method = (
            "NativeStructuredFamilySolver" if self.native else "StructuredFamilySolver"
        )
        run_id = str(uuid4())
        rejection = check_solver_request(problem, self.capabilities())
        if rejection is not None:
            return ProjectionSolution(
                rejection[0],
                run_id,
                method=method,
                diagnostics=(rejection[1],),
            )
        window = problem.window
        config = problem.solver_config(method)
        budget = _Budget(problem.resource_limits, self.native, problem.cancellation)
        failure = None
        try:
            budget.step()
            m = (window.n + 1).bit_length() - 1
            if not 2 <= m <= 4 or window.n != (1 << m) - 1:
                failure = "CyclicTrace supports n=2^m-1 for m=2,3,4"
            else:
                action = CyclicAction(m)
                budget.entries(
                    window.m * window.n
                    + window.n * window.p
                    + window.n * m
                    + (0 if problem.matrix_free_output else window.n**2)
                )
                if (
                    _prepare(window.A, budget).rank() != 0
                    or len(set(window.weights)) != 1
                    or _prepare(window.D, budget).rank() != window.n - (1 << (m - 1))
                    or any(
                        any(z)
                        for z in _structured_images(
                            action, window.D.transpose().rows, budget
                        )
                    )
                ):
                    failure = "CyclicTrace requires A=0, uniform exact weights, and im(D)=ker(P_m)"
                budget.step()
            if failure is not None:
                return ProjectionSolution(
                    "Unavailable",
                    run_id,
                    method=method,
                    arithmetic_policy=window.arithmetic,
                    tie_break_policy=problem.tie_break_policy,
                    solver_config=config,
                    resource_usage=budget.usage(),
                    diagnostics=(failure,),
                )
            projection = (
                action
                if problem.matrix_free_output
                else Matrix.from_columns(
                    _structured_images(
                        action,
                        tuple(
                            tuple(int(i == j) for i in range(window.n))
                            for j in range(window.n)
                        ),
                        budget,
                    ),
                    nrows=window.n,
                )
            )
            budget.step()
        except _Exhausted as error:
            return ProjectionSolution(
                "ResourceExhausted",
                run_id,
                method=method,
                arithmetic_policy=window.arithmetic,
                tie_break_policy=problem.tie_break_policy,
                solver_config=config,
                resource_usage=budget.usage(),
                diagnostics=(str(error),),
            )
        identity = make_identity(window, projection, run_id, problem.tie_break_policy)
        return ProjectionSolution(
            "Solved",
            run_id,
            projection,
            identity,
            "ExactOptimal",
            QueryResult(
                "Computed",
                Fraction(m),
                identity,
                True,
                {"witness": (1,) + (0,) * (window.n - 1)},
            ),
            {"optimization": {"kind": "CyclicTrace", "m": m, "kernel_distance": m + 1}},
            budget.usage(),
            (),
            problem.tie_break_policy,
            method=method,
            arithmetic_policy=window.arithmetic,
            lower_bound=Fraction(m),
            upper_bound=Fraction(m),
            solver_config=config,
        )


class GreedyCertifiedSolver:
    """Exact minimum-mass greedy section with the pinned T4/Rossman beta bound.

    This finite reference enumerates cycles. It is not a polynomial-time solver.
    Each chosen cycle is independent modulo boundaries and earlier choices.
    """

    def __init__(self, *, native=False):
        if type(native) is not bool:
            raise ValueError("native must be a boolean")
        self.native = native

    def capabilities(self):
        return _freeze(
            {
                **FeasibleSolver().capabilities(),
                "execution_backend": "packed-rust-v1"
                if self.native
                else "python-reference",
                "arithmetic_policies": ("ExactInteger", "ExactRational"),
                "certificate_levels": (
                    "Feasible",
                    "CertifiedUpperBound",
                    "CertifiedInterval",
                ),
            }
        )

    def solve(self, problem):
        method = (
            "NativeGreedyCertifiedSolver" if self.native else "GreedyCertifiedSolver"
        )
        run_id = str(uuid4())
        rejection = check_solver_request(problem, self.capabilities())
        if rejection is not None:
            return ProjectionSolution(
                rejection[0],
                run_id,
                method=method,
                diagnostics=(rejection[1],),
            )
        window = problem.window
        config = problem.solver_config(method)
        budget = _Budget(problem.resource_limits, self.native, problem.cancellation)
        seed = FeasibleSolver().solve(
            replace(problem, requested_certificate_level="Feasible")
        )
        if seed.projection is None:
            return replace(
                seed,
                solver_run_id=run_id,
                method=method,
                solver_config=config,
                arithmetic_policy=window.arithmetic,
            )
        budget.states = seed.resource_usage["states"]
        projection, value, witness = seed.projection, None, None
        selected, cycle_count, beta, R = [], None, None, None
        exhausted = None
        try:
            budget.step()
            R = Matrix.identity(window.n) + seed.generalized_inverse_a @ window.A
            N = Matrix.from_columns(
                _prepare(window.A, budget).kernel_basis(), nrows=window.n
            )
            boundaries = _prepare(window.D, budget).image_basis()
            beta = N.ncols - len(boundaries)
            cycle_count = (1 << N.ncols) - 1
            if cycle_count * max(1, beta) > 100_000:
                raise _Exhausted("certificate_replay_state_limit")
            budget.entries(8 * window.n**2 + (cycle_count * window.n if beta else 0))
            value, witness = _cycle_objective(window, projection, N, budget)
            if beta:
                candidates = [
                    (mass, sum(bit << j for j, bit in enumerate(z)), z)
                    for z, mass in _cycle_table(window, N, budget)
                ]
                candidates.sort()
                span_basis = list(boundaries)
                for _, _, z in candidates:
                    budget.step()
                    trial = Matrix.from_columns((*span_basis, z), nrows=window.n)
                    if _prepare(trial, budget).rank() > len(span_basis):
                        selected.append(z)
                        span_basis.append(z)
                    if len(selected) == beta:
                        break
                if len(selected) != beta:
                    raise ValueError("greedy choices did not span homology")
                basis = Matrix.from_columns(span_basis, nrows=window.n)
                coordinates = Matrix.from_columns(
                    (
                        _prepare(basis, budget).solve_many(R.transpose().rows)
                        if budget.native
                        else (basis.solve(z) for z in R.transpose().rows)
                    ),
                    nrows=N.ncols,
                )
                section = Matrix.from_columns(
                    ((0,) * window.n,) * len(boundaries) + tuple(selected),
                    nrows=window.n,
                )
                candidate = _multiply(section, coordinates, budget)
                candidate_value, candidate_witness = _cycle_objective(
                    window, candidate, N, budget
                )
                projection, value, witness = (
                    candidate,
                    candidate_value,
                    candidate_witness,
                )
        except _Exhausted as error:
            exhausted = str(error)
        identity = make_identity(window, projection, run_id, problem.tie_break_policy)
        usage = {
            **budget.usage(),
            "nonzero_cycle_inputs": cycle_count,
            "greedy_generators_selected": len(selected),
            "greedy_complete": exhausted is None,
        }
        lower, upper, proof = None, None, {}
        if value is None:
            status, level = "ResourceExhausted", "Feasible"
            objective = QueryResult("ResourceExhausted", identity=identity)
        else:
            objective = QueryResult(
                "EmptyDomain" if cycle_count == 0 else "Computed",
                value,
                identity,
                True,
                {"witness": witness, "nonzero_cycles": cycle_count},
            )
            upper = value
            if exhausted is not None:
                status, level, lower = (
                    "ResourceExhausted",
                    "CertifiedInterval",
                    Fraction(0),
                )
                proof = {
                    "kind": "CycleBounds",
                    "nonzero_cycles": cycle_count,
                    "lower_bound_method": "UniversalHomology",
                }
            else:
                status, lower = "Solved", Fraction(int(beta > 0))
                level = "ExactOptimal" if lower == upper else "CertifiedInterval"
                proof = {
                    "kind": "GreedyBasis",
                    "nonzero_cycles": cycle_count,
                    "selected_generators": tuple(selected),
                    "cycle_retraction": matrix_data(R),
                    "theoretical_upper_bound": beta,
                    "hypotheses": {
                        "coefficient_field": "F2",
                        "positive_weights": True,
                        "arithmetic_policy": window.arithmetic,
                        "betti": beta,
                    },
                }
        return ProjectionSolution(
            status,
            run_id,
            projection,
            identity,
            level,
            objective,
            {"optimization": proof} if proof else {},
            usage,
            (exhausted,) if exhausted is not None else (),
            problem.tie_break_policy,
            method=method,
            arithmetic_policy=window.arithmetic,
            lower_bound=lower,
            upper_bound=upper,
            solver_config=config,
        )
