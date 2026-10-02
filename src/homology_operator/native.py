"""Optional native adapters; Python remains the independent validator.

Importing this adapter never requires Rust. Missing/unsupported construction is
Unavailable, without silently calling a different solver. Geometry uses checked
native integers or a visible arbitrary-precision/fsum weight fallback.
"""

from dataclasses import asdict, dataclass, field
from fractions import Fraction
from math import fsum, isfinite
from time import perf_counter
from uuid import uuid4

from .algebra import Matrix, CompactAction, validate_vector
from .operator import HomologyOperator
from .result import QueryResult, make_identity, require_same_identity
from .solver import (
    FeasibleSolver,
    ProjectionSolution,
    check_solver_request,
    _Budget,
    _Exhausted,
    CancellationToken,
    ResourceLimits,
)


def _extension():
    import _homology_native

    if getattr(_homology_native, "__semantics_version__", None) != 1:
        raise ImportError("incompatible native extension; rebuild the S4-08 wheel")
    return _homology_native


def backend_info():
    """Report the actually loaded extension; importing reference never loads Rust."""
    import platform

    try:
        extension = _extension()
    except ImportError as error:
        return {
            "reference": "Available",
            "native": "Unavailable",
            "reason": str(error),
            "platform": platform.platform(),
        }
    return {
        "reference": "Available",
        "native": "Available",
        "semantics_version": extension.__semantics_version__,
        "extension_path": extension.__file__,
        "platform": platform.platform(),
        "threads": 1,
    }


def _pack(vector):
    return sum(bit << i for i, bit in enumerate(vector))


def _matrix(rows, ncols):
    return Matrix.from_rows(
        (tuple((row >> j) & 1 for j in range(ncols)) for row in rows), ncols=ncols
    )


def _words(vector):
    return tuple(_pack(vector[i : i + 64]) for i in range(0, len(vector), 64))


def _unwords(words, size):
    return tuple((words[i // 64] >> (i % 64)) & 1 for i in range(size))


@dataclass(frozen=True)
class PreparedMatrix:
    """One immutable native RREF reused for canonical algebra, without weights."""

    matrix: Matrix
    cancellation: CancellationToken | None = field(
        default=None, repr=False, compare=False
    )
    _handle: object = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.matrix, Matrix):
            raise ValueError("prepare requires a validated Matrix")
        if self.cancellation is not None and not isinstance(
            self.cancellation, CancellationToken
        ):
            raise ValueError("cancellation must be a CancellationToken")
        try:
            handle = _extension().PreparedMatrix(
                tuple(map(_words, self.matrix.rows)),
                self.matrix.ncols,
                None
                if self.cancellation is None
                else self.cancellation._native_handle(),
            )
        except ValueError as error:
            if str(error).startswith("resource_exhausted:cancelled:"):
                raise _Exhausted("cancelled") from error
            raise
        object.__setattr__(
            self,
            "_handle",
            handle,
        )

    def rank(self):
        return self._handle.rank()

    def rref(self):
        return Matrix.from_rows(
            (_unwords(row, self.matrix.ncols) for row in self._handle.rref()),
            ncols=self.matrix.ncols,
        ), tuple(self._handle.pivots)

    def kernel_basis(self):
        return tuple(
            _unwords(row, self.matrix.ncols) for row in self._handle.kernel_basis()
        )

    def image_basis(self):
        return tuple(
            _unwords(row, self.matrix.nrows) for row in self._handle.image_basis()
        )

    def apply_many(self, vectors):
        vectors = tuple(_words(validate_vector(x, self.matrix.ncols)) for x in vectors)
        return tuple(
            _unwords(row, self.matrix.nrows) for row in self._handle.apply_many(vectors)
        )

    def solve_many(self, vectors):
        vectors = tuple(_words(validate_vector(x, self.matrix.nrows)) for x in vectors)
        return tuple(
            None if row is None else _unwords(row, self.matrix.ncols)
            for row in self._handle.solve_many(vectors)
        )

    def solve(self, vector):
        return self.solve_many((vector,))[0]

    def membership_many(self, vectors):
        vectors = tuple(_words(validate_vector(x, self.matrix.nrows)) for x in vectors)
        return tuple(self._handle.membership_many(vectors))

    def statistics(self):
        return {
            name: getattr(self._handle, name)
            for name in (
                "decomposition_count",
                "source_nonzero_bits",
                "reduced_nonzero_bits",
                "peak_nonzero_bits",
                "stored_words",
            )
        }


def packed_add(left, right):
    if not isinstance(left, Matrix) or not isinstance(right, Matrix):
        raise ValueError("packed addition requires validated matrices")
    rows = _extension().packed_add(
        tuple(map(_words, left.rows)),
        left.ncols,
        tuple(map(_words, right.rows)),
        right.ncols,
    )
    return Matrix.from_rows(
        (_unwords(row, left.ncols) for row in rows), ncols=left.ncols
    )


def packed_multiply(left, right):
    if not isinstance(left, Matrix) or not isinstance(right, Matrix):
        raise ValueError("packed product requires validated matrices")
    rows = _extension().packed_product(
        tuple(map(_words, left.rows)),
        left.ncols,
        tuple(map(_words, right.rows)),
        right.ncols,
    )
    return Matrix.from_rows(
        (_unwords(row, right.ncols) for row in rows), ncols=right.ncols
    )


class NativeFeasibleSolver:
    """One-word stable feasible construction; not a native optimizer."""

    def capabilities(self):
        return FeasibleSolver().capabilities()

    def solve(self, problem):
        run_id = str(uuid4())
        method = type(self).__name__
        rejection = check_solver_request(problem, self.capabilities())
        if rejection is not None:
            return ProjectionSolution(rejection[0], run_id, diagnostics=(rejection[1],))
        window, limits = problem.window, problem.resource_limits
        common = dict(
            method=method,
            arithmetic_policy=window.arithmetic,
            tie_break_policy=problem.tie_break_policy,
            solver_config=problem.solver_config(method),
        )
        if max(window.m, window.n, window.p) > 64:
            return ProjectionSolution(
                "Unavailable",
                run_id,
                diagnostics=("prototype dimensions exceed 64",),
                **common,
            )
        try:
            extension = _extension()
        except ImportError:
            return ProjectionSolution(
                "Unavailable",
                run_id,
                diagnostics=("optional native extension is not installed",),
                **common,
            )
        started = perf_counter()
        a, d = tuple(map(_pack, window.A.rows)), tuple(map(_pack, window.D.rows))
        converted = perf_counter()
        g, u, p, states, native_wall, reason = extension.construct(
            a,
            window.m,
            window.n,
            d,
            window.p,
            limits.state_limit,
            max(0.0, limits.wall_time_limit - (converted - started)),
            limits.matrix_entry_limit,
            None
            if problem.cancellation is None
            else problem.cancellation._native_handle(),
        )
        returned = perf_counter()
        usage = {
            "states": states,
            "limits": asdict(limits),
            "conversion_seconds": converted - started,
            "native_seconds": native_wall,
            "binding_seconds": max(0.0, returned - converted - native_wall),
            "threads": 1,
        }
        if reason is not None:
            usage["wall_time"] = returned - started
            return ProjectionSolution(
                "ResourceExhausted",
                run_id,
                resource_usage=usage,
                diagnostics=(reason,),
                **common,
            )
        G, U, P = _matrix(g, window.m), _matrix(u, window.n), _matrix(p, window.n)
        decoded = perf_counter()
        # These checks and the independent projection validator are not bypassed.
        if window.A @ G @ window.A != window.A or window.D @ U @ window.D != window.D:
            raise ValueError("native generalized inverse failed independent validation")
        identity = make_identity(window, P, run_id, problem.tie_break_policy)
        usage.update(
            decode_seconds=decoded - returned,
            python_verification_and_identity_seconds=perf_counter() - decoded,
            wall_time=perf_counter() - started,
        )
        if usage["wall_time"] >= limits.wall_time_limit:
            return ProjectionSolution(
                "ResourceExhausted",
                run_id,
                resource_usage=usage,
                diagnostics=("wall_time_limit",),
                **common,
            )
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
            usage,
            generalized_inverse_a=G,
            generalized_inverse_d=U,
            **common,
        )


class NativeFactorizedSolver:
    """Stable feasible P in factor/HC form; no dense P or expanded inverses."""

    def capabilities(self):
        return {
            **FeasibleSolver().capabilities(),
            "matrix_free_output": True,
            "solver_options": ("representation",),
        }

    def solve(self, problem):
        run_id = str(uuid4())
        method = type(self).__name__
        rejection = check_solver_request(problem, self.capabilities())
        if rejection is not None:
            return ProjectionSolution(rejection[0], run_id, diagnostics=(rejection[1],))
        w = problem.window
        common = {
            "method": method,
            "arithmetic_policy": w.arithmetic,
            "tie_break_policy": problem.tie_break_policy,
            "solver_config": problem.solver_config(method),
        }
        representation = problem.solver_options.get("representation", "Factorized")
        if (
            not problem.matrix_free_output
            or type(representation) is not str
            or representation not in {"Factorized", "HC"}
        ):
            return ProjectionSolution(
                "Unavailable",
                run_id,
                diagnostics=(
                    "requires matrix_free_output and Factorized/HC representation",
                ),
                **common,
            )
        try:
            _extension()
        except ImportError:
            return ProjectionSolution(
                "Unavailable",
                run_id,
                diagnostics=("optional native extension is not installed",),
                **common,
            )
        budget = _Budget(problem.resource_limits, cancellation=problem.cancellation)
        try:
            budget.step()
            # Keep reference's logical entry guard; not a claim about packed RSS.
            budget.entries(w.m * w.n + w.n * w.p + w.n * w.m + w.p * w.n + 4 * w.n**2)
            parts, indices = [], []
            for matrix in (w.A, w.D):
                budget.step()
                budget.entries(matrix.nrows * (matrix.ncols + matrix.nrows))
                prepared = PreparedMatrix(matrix, cancellation=problem.cancellation)
                rows = prepared._handle.inverse_rows()
                parts.append(
                    Matrix.from_rows(
                        (_unwords(row, matrix.nrows) for row in rows),
                        ncols=matrix.nrows,
                    )
                )
                indices.append(tuple(prepared._handle.pivots))
                budget.step(matrix.nrows)
            budget.step()
            action = CompactAction(
                "GeneralizedInverse", (w.A, w.D, *parts), tuple(indices)
            )
            if any(
                w.A.apply(action._inverse(0, z)) != z for z in w.A.transpose().rows
            ) or any(
                w.D.apply(action._inverse(1, z)) != z for z in w.D.transpose().rows
            ):
                raise ValueError(
                    "compact generalized inverse failed independent validation"
                )
            if representation == "HC":
                # Stream columns of P to construct its image. Never store all P.
                H = Matrix.from_columns(action.image_basis(), nrows=w.n)
                budget.step(w.n)
                prepared_h = PreparedMatrix(H, cancellation=problem.cancellation)
                coordinates = []
                for j in range(w.n):
                    budget.step()
                    z = action.apply(tuple(int(i == j) for i in range(w.n)))
                    coordinates.append(prepared_h.solve(z))
                C = Matrix.from_columns(coordinates, nrows=H.ncols)
                action = CompactAction("HC", (H, C))
            budget.step()
            identity = make_identity(w, action, run_id, problem.tie_break_policy)
            budget.step(0)
            usage = budget.usage()
            usage.update(
                threads=1,
                representation=representation,
                expanded_projection=False,
                factor_entries=sum(x.nrows * x.ncols for x in action.factors),
            )
            return ProjectionSolution(
                "FeasibleOnly",
                run_id,
                action,
                identity,
                "Feasible",
                QueryResult("NotComputed", identity=identity),
                {
                    "exact_arithmetic": True,
                    "verification_method": "CompactGeneralizedInverseConstruction",
                },
                usage,
                **common,
            )
        except _Exhausted as error:
            return ProjectionSolution(
                "ResourceExhausted",
                run_id,
                resource_usage=budget.usage(),
                diagnostics=(str(error),),
                **common,
            )


def apply_batch(operator, vectors):
    """P/L on all chains in one call; preserve the operator's six identities."""
    if not isinstance(operator, HomologyOperator) or not isinstance(
        operator.P, (Matrix, CompactAction)
    ):
        raise ValueError("native batch requires an explicit/compact validated operator")
    n = operator.window.n
    if n > 64 and isinstance(operator.P, Matrix):
        return QueryResult(
            "Unavailable",
            identity=operator.identity,
            details={"reason": "prototype dimensions exceed 64"},
        )
    try:
        extension = _extension()
    except ImportError:
        return QueryResult(
            "Unavailable",
            identity=operator.identity,
            details={"reason": "optional native extension is not installed"},
        )
    started = perf_counter()
    vectors = tuple(validate_vector(x, n) for x in vectors)
    if isinstance(operator.P, CompactAction):
        action = operator.P
        packed = tuple(map(_words, vectors))
        rows = tuple(tuple(map(_words, matrix.rows)) for matrix in action.factors)
    else:
        packed = tuple(map(_pack, vectors))
        rows = tuple(map(_pack, operator.P.rows))
    converted = perf_counter()
    if isinstance(operator.P, CompactAction):
        projected, applied, supports, native_wall = extension.compact_actions(
            action.form,
            rows,
            tuple(x.ncols for x in action.factors),
            action.pivots,
            action.complement,
            packed,
        )
    else:
        projected, applied, supports, native_wall = extension.actions(rows, n, packed)
    returned = perf_counter()
    result = {
        "project": tuple(_unwords(z, n) for z in projected)
        if isinstance(operator.P, CompactAction)
        else tuple(tuple((z >> j) & 1 for j in range(n)) for z in projected),
        "apply_operator": tuple(_unwords(z, n) for z in applied)
        if isinstance(operator.P, CompactAction)
        else tuple(tuple((z >> j) & 1 for j in range(n)) for z in applied),
        "support": tuple(tuple(indices) for indices in supports),
    }
    return QueryResult(
        "Computed",
        result,
        operator.identity,
        True,
        {
            "arguments": vectors,
            "conversion_seconds": converted - started,
            "native_seconds": native_wall,
            "binding_seconds": max(0.0, returned - converted - native_wall),
            "decode_seconds": perf_counter() - returned,
            "threads": 1,
        },
    )


@dataclass(frozen=True)
class GeometryWorkspace:
    """Prepared action/weights plus private scratch; bound to all six identities.

    Preparing or using this workspace never adds readouts to its operator.
    Pass it to geometry_batch to reuse native storage across batches. It is
    process-local and is deliberately absent from serialized operator results.
    """

    operator: HomologyOperator
    _handle: object = field(init=False, repr=False, compare=False)
    _weight_fallback: str | None = field(init=False, repr=False, compare=False)
    _preparation: dict = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        started = perf_counter()
        op = self.operator
        if not isinstance(op, HomologyOperator) or not isinstance(
            op.P, (Matrix, CompactAction)
        ):
            raise ValueError("geometry workspace requires an explicit/compact operator")
        action = op.P
        if isinstance(action, Matrix):
            form, factors, pivots, complement = "Matrix", (action,), (), False
        else:
            form, factors, pivots, complement = (
                action.form,
                action.factors,
                action.pivots,
                action.complement,
            )
        rows = tuple(tuple(map(_words, matrix.rows)) for matrix in factors)
        boundary = tuple(map(_words, op.window.A.rows))
        fallback, weights = None, None
        if op.window.arithmetic == "FloatingPoint":
            fallback = "binary64 fsum"
        elif any(Fraction(w).denominator != 1 for w in op.window.weights):
            fallback = "arbitrary Fraction"
        elif any(w > (1 << 64) - 1 for w in op.window.weights):
            fallback = "integer weight exceeds u64"
        else:
            weights = tuple(int(w) for w in op.window.weights)
        converted = perf_counter()
        handle = _extension().GeometryWorkspace(
            boundary,
            form,
            rows,
            tuple(x.ncols for x in factors),
            pivots,
            complement,
            weights,
        )
        prepared = perf_counter()
        object.__setattr__(self, "_handle", handle)
        object.__setattr__(self, "_weight_fallback", fallback)
        object.__setattr__(
            self,
            "_preparation",
            {
                "conversion_seconds": converted - started,
                "native_and_binding_seconds": prepared - converted,
                "total_seconds": prepared - started,
            },
        )

    @property
    def identity(self):
        return self.operator.identity

    def statistics(self):
        batches, growths, capacity = self._handle.statistics()
        return {
            "completed_batches": batches,
            "projection_buffer_growths": growths,
            "projection_capacity_words": capacity,
        }


def geometry_batch(
    operator, cycles, pairs=(), *, workspace=None, limits=None, cancellation=None
):
    """Project each cycle once; derive all geometry from that same packed Pz.

    Native integers use checked u64 sums. Nonintegral rationals, large weights,
    individual sum overflows and floats retain Python's exact/fsum policy, with
    fallback reasons/counts/timing included. No operator history is mutated.
    """
    if not isinstance(operator, HomologyOperator):
        raise ValueError("geometry batch requires a validated operator")
    if limits is not None and not isinstance(limits, ResourceLimits):
        raise ValueError("limits must be ResourceLimits")
    if cancellation is not None and not isinstance(cancellation, CancellationToken):
        raise ValueError("cancellation must be a CancellationToken")
    if workspace is not None:
        if not isinstance(workspace, GeometryWorkspace):
            raise ValueError("workspace must be a GeometryWorkspace")
        require_same_identity(workspace, operator)
    started = perf_counter()
    cycles = tuple(validate_vector(z, operator.window.n) for z in cycles)
    pairs = tuple(tuple(pair) for pair in pairs)
    if any(
        len(pair) != 2
        or any(type(i) is not int or not 0 <= i < len(cycles) for i in pair)
        for pair in pairs
    ):
        raise ValueError("pairs must index two cycles in this batch")
    if not isinstance(operator.P, (Matrix, CompactAction)):
        for z in cycles:
            operator._cycle(z)
        return QueryResult(
            "Unavailable",
            identity=operator.identity,
            details={"reason": "unsupported native geometry action"},
        )
    reused = workspace is not None
    try:
        workspace = workspace or GeometryWorkspace(operator)
    except ImportError:
        for z in cycles:
            operator._cycle(z)
        return QueryResult(
            "Unavailable",
            identity=operator.identity,
            details={"reason": "optional native extension is not installed"},
        )
    packed = tuple(map(_words, cycles))
    converted = perf_counter()
    if (
        limits is not None
        and operator.window.n * (2 * len(cycles) + len(pairs))
        > limits.matrix_entry_limit
    ):
        return QueryResult(
            "ResourceExhausted",
            identity=operator.identity,
            details={
                "reason": "matrix_entry_limit",
                "resource_usage": {"states": 0, "limits": asdict(limits)},
            },
        )
    try:
        raw = workspace._handle.query(
            packed,
            pairs,
            None if cancellation is None else cancellation._native_handle(),
            None if limits is None else limits.state_limit,
            None
            if limits is None
            else max(0.0, limits.wall_time_limit - (converted - started)),
        )
    except ValueError as error:
        parts = str(error).split(":")
        if len(parts) != 3 or parts[0] != "resource_exhausted":
            raise
        return QueryResult(
            "ResourceExhausted",
            identity=operator.identity,
            details={
                "reason": parts[1],
                "resource_usage": {
                    "states": int(parts[2]),
                    "limits": None if limits is None else asdict(limits),
                    "wall_time": perf_counter() - started,
                },
                "arguments": cycles,
                "pairs": pairs,
            },
        )
    (
        representatives,
        supports,
        masses,
        distances,
        differences,
        shared,
        union,
        native_wall,
    ) = raw
    returned = perf_counter()
    fallback_seconds, fallback_count, overflow_count = 0.0, 0, 0

    def mass(indices, native_value):
        nonlocal fallback_seconds, fallback_count, overflow_count
        if native_value is not None:
            return (
                Fraction(native_value)
                if (operator.window.arithmetic == "ExactRational" and indices)
                else native_value
            )
        fallback_started = perf_counter()
        fallback_count += 1
        overflow_count += workspace._weight_fallback is None
        costs = [operator.window.weights[i] for i in indices]
        if operator.window.arithmetic == "FloatingPoint":
            try:
                value = fsum(costs)
            except OverflowError as error:
                raise ValueError("NumericalFailure: floating mass overflow") from error
            if not isfinite(value):
                raise ValueError("NumericalFailure: nonfinite floating mass")
        else:
            value = sum(costs)
        fallback_seconds += perf_counter() - fallback_started
        return value

    value = {
        "class_representative": tuple(
            _unwords(z, operator.window.n) for z in representatives
        ),
        "selected_mass": tuple(
            mass(indices, number) for indices, number in zip(supports, masses)
        ),
        "support": tuple(tuple(indices) for indices in supports),
        "class_distance": tuple(
            mass(indices, number) for indices, number in zip(differences, distances)
        ),
        "shared_support": tuple(tuple(indices) for indices in shared),
        "union_support": tuple(tuple(indices) for indices in union),
    }
    decoded = perf_counter()
    reason = (
        "cancelled"
        if cancellation is not None and cancellation.is_cancelled()
        else "wall_time_limit"
        if limits is not None and decoded - started >= limits.wall_time_limit
        else None
    )
    if reason is not None:
        return QueryResult(
            "ResourceExhausted",
            identity=operator.identity,
            details={
                "reason": reason,
                "resource_usage": {
                    "states": len(cycles) + len(pairs),
                    "wall_time": decoded - started,
                    "limits": None if limits is None else asdict(limits),
                },
            },
        )
    exact = operator.window.arithmetic != "FloatingPoint"
    return QueryResult(
        "Computed",
        value,
        operator.identity,
        exact,
        {
            "arguments": cycles,
            "pairs": pairs,
            "workspace_reused": reused,
            "preparation_seconds": 0.0
            if reused
            else workspace._preparation["total_seconds"],
            "preparation_costs": None if reused else workspace._preparation,
            "conversion_seconds": converted
            - started
            - (0.0 if reused else workspace._preparation["total_seconds"]),
            "native_seconds": native_wall,
            "binding_seconds": max(0.0, returned - converted - native_wall),
            "decode_seconds": max(0.0, decoded - returned - fallback_seconds),
            "geometry_fallback": (
                workspace._weight_fallback
                or "integer sum overflow; arbitrary precision"
            )
            if fallback_count
            else None,
            "geometry_fallback_seconds": fallback_seconds,
            "weight_fallback_count": fallback_count,
            "integer_overflow_count": overflow_count,
            "projection_applications": len(cycles),
            "workspace_statistics": workspace.statistics(),
            "threads": 1,
            "arithmetic_policy": operator.window.arithmetic,
            "rounding_policy": None if exact else "binary64 fsum; nearest-even",
            **(
                {
                    "resource_usage": {
                        "states": len(cycles) + len(pairs),
                        "limits": None if limits is None else asdict(limits),
                        "wall_time": decoded - started,
                    }
                }
                if limits is not None or cancellation is not None
                else {}
            ),
        },
    )


def _integer_weights(weights):
    """Normalize exact rationals; return None instead of narrowing large integers."""
    from fractions import Fraction
    from math import gcd, lcm

    weights = tuple(map(Fraction, weights))
    denominator = lcm(*(w.denominator for w in weights))
    values = tuple(w.numerator * (denominator // w.denominator) for w in weights)
    divisor = gcd(*values) if values else 1
    values = tuple(value // divisor for value in values)
    return (values, Fraction(divisor, denominator)) if sum(values) < 1 << 128 else None


def _apply_many(projection, vectors):
    from .algebra import CyclicAction

    packed = tuple(map(_words, vectors))
    if isinstance(projection, CyclicAction):
        output = _extension().cyclic_batch(projection.m, packed)
        if projection.complement:
            output = tuple(
                tuple(a ^ b for a, b in zip(x, y)) for x, y in zip(packed, output)
            )
    else:
        output = _extension().packed_apply(
            tuple(map(_words, projection.rows)), projection.ncols, packed
        )
    return tuple(_unwords(row, projection.nrows) for row in output)


def _span_objective(window, projection, basis, budget=None, detail=None):
    """Algebra-only native kernel; verifier supplies its independently rebuilt basis."""
    from fractions import Fraction

    detail = detail if detail is not None else budget.native_detail
    normalized = _integer_weights(window.weights)
    if normalized is None:
        detail["exact_mass_fallback_calls"] = (
            detail.get("exact_mass_fallback_calls", 0) + 1
        )
        return None
    started = perf_counter()
    weights, _ = normalized
    images = _apply_many(projection, basis)
    remaining = (
        None
        if budget is None
        else max(0.0, budget.limits.wall_time_limit - (perf_counter() - budget.started))
    )
    quota = (
        100_000
        if budget is None
        else min(100_000, budget.limits.state_limit - budget.states)
    )
    a, b, witness, used, reason = _extension().span_objective(
        tuple(map(_words, basis)),
        tuple(map(_words, images)),
        weights,
        quota,
        remaining,
        None
        if budget is None or budget.cancellation is None
        else budget.cancellation._native_handle(),
    )
    detail["span_objective_calls"] = detail.get("span_objective_calls", 0) + 1
    detail["native_kernel_seconds"] = (
        detail.get("native_kernel_seconds", 0.0) + perf_counter() - started
    )
    if budget is not None:
        budget.states += used
        if reason:
            from .solver import _Exhausted

            raise _Exhausted(reason)
    return Fraction(a, b), None if witness is None else _unwords(witness, window.n)


def _span_table(window, basis, budget=None, detail=None):
    detail = detail if detail is not None else budget.native_detail
    normalized = _integer_weights(window.weights)
    if normalized is None:
        detail["exact_mass_fallback_calls"] = (
            detail.get("exact_mass_fallback_calls", 0) + 1
        )
        return None
    started = perf_counter()
    weights, unit = normalized
    remaining = (
        None
        if budget is None
        else max(0.0, budget.limits.wall_time_limit - (perf_counter() - budget.started))
    )
    quota = (
        100_000
        if budget is None
        else min(100_000, budget.limits.state_limit - budget.states)
    )
    vectors, masses, used, reason = _extension().span_table(
        tuple(map(_words, basis)),
        weights,
        quota,
        remaining,
        None
        if budget is None or budget.cancellation is None
        else budget.cancellation._native_handle(),
    )
    detail["span_table_calls"] = detail.get("span_table_calls", 0) + 1
    detail["native_kernel_seconds"] = (
        detail.get("native_kernel_seconds", 0.0) + perf_counter() - started
    )
    if budget is not None:
        budget.states += used
        if reason:
            from .solver import _Exhausted

            raise _Exhausted(reason)
    return tuple(
        (
            _unwords(z, window.n),
            int(mass * unit) if window.arithmetic == "ExactInteger" else mass * unit,
        )
        for z, mass in zip(vectors, masses)
    )
