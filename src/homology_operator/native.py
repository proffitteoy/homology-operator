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

    if (
        getattr(_homology_native, "__semantics_version__", None) != 1
        or getattr(_homology_native, "__api_version__", None) != 3
    ):
        raise ImportError("incompatible native extension; rebuild from matching source")
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
        "api_version": extension.__api_version__,
        "extension_path": getattr(extension, "_homology_native", extension).__file__,
        "platform": platform.platform(),
        "threads": 1,
    }


def _pack(vector):
    return sum(bit << i for i, bit in enumerate(vector))


def _matrix(rows, ncols):
    return Matrix._from_packed(rows, ncols)


def _words(vector):
    return tuple(_pack(vector[i : i + 64]) for i in range(0, len(vector), 64))


def _unwords(words, size):
    return tuple((words[i // 64] >> (i % 64)) & 1 for i in range(size))


def _matrix_words(matrix):
    """Convert packed rows directly; never expand binary coordinate tuples."""
    mask = (1 << 64) - 1
    return tuple(
        tuple((row >> i) & mask for i in range(0, matrix.ncols, 64))
        for row in matrix._bits
    )


def _from_matrix_words(rows, ncols):
    return Matrix._from_packed(
        (sum(word << (64 * i) for i, word in enumerate(row)) for row in rows), ncols
    )


def _matrix_handle(matrix):
    """Convert an immutable input once; never enable native dispatch on it."""
    if hasattr(matrix, "_native_matrix"):
        return matrix._native_matrix
    if not hasattr(matrix, "_cached_native_matrix"):
        extension = _extension()
        words = (matrix.ncols + 63) // 64
        if (
            words >= 8
            and sum(row.bit_count() for row in matrix._bits)
            <= matrix.nrows * words // 2
        ):
            rows = []
            for bits in matrix._bits:
                indices = []
                while bits:
                    low = bits & -bits
                    indices.append(low.bit_length() - 1)
                    bits ^= low
                rows.append(indices)
            handle = extension.NativeMatrix.from_sparse_rows(rows, matrix.ncols)
        else:
            handle = extension.NativeMatrix(_matrix_words(matrix), matrix.ncols)
        object.__setattr__(
            matrix,
            "_cached_native_matrix",
            handle,
        )
    return matrix._cached_native_matrix


@dataclass(frozen=True)
class PreparedMatrix:
    """One immutable native RREF reused for canonical algebra, without weights."""

    matrix: Matrix
    cancellation: CancellationToken | None = field(
        default=None, repr=False, compare=False
    )
    full: bool = True
    diagnostics: bool = True
    _handle: object = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.matrix, Matrix):
            raise ValueError("prepare requires a validated Matrix")
        if type(self.full) is not bool or type(self.diagnostics) is not bool:
            raise ValueError("full and diagnostics must be booleans")
        if self.cancellation is not None and not isinstance(
            self.cancellation, CancellationToken
        ):
            raise ValueError("cancellation must be a CancellationToken")
        try:
            handle = _extension().PreparedMatrix.from_matrix(
                _matrix_handle(self.matrix),
                None
                if self.cancellation is None
                else self.cancellation._native_handle(),
                self.full,
                self.diagnostics,
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
        return Matrix._from_native(self._handle.reduced_matrix()), tuple(
            self._handle.pivots
        )

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
        result = {
            name: getattr(self._handle, name)
            for name in (
                "decomposition_count",
                "source_nonzero_bits",
                "reduced_nonzero_bits",
                "peak_nonzero_bits",
                "stored_words",
            )
        }
        sparse_input, sparse_reduced, switches = self._handle.storage()
        result.update(
            sparse_input=sparse_input,
            sparse_reduced=sparse_reduced,
            sparse_to_dense_switches=switches,
        )
        return result


def packed_add(left, right):
    if not isinstance(left, Matrix) or not isinstance(right, Matrix):
        raise ValueError("packed addition requires validated matrices")
    return Matrix._from_native(_matrix_handle(left).add(_matrix_handle(right)))


def packed_multiply(left, right):
    if not isinstance(left, Matrix) or not isinstance(right, Matrix):
        raise ValueError("packed product requires validated matrices")
    return Matrix._from_native(_matrix_handle(left).product(_matrix_handle(right)))


class NativeFeasibleSolver:
    """Stable packed feasible construction; not a native optimizer."""

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
        a, d = _matrix_handle(window.A), _matrix_handle(window.D)
        converted = perf_counter()
        g, u, p, states, native_wall, reason = extension.construct_multi(
            a,
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
        G, U, P = (Matrix._from_native(handle) for handle in (g, u, p))
        decoded = perf_counter()
        # These checks and the independent projection validator are not bypassed.
        if (
            window.A._reference() @ G._reference() @ window.A._reference() != window.A
            or window.D._reference() @ U._reference() @ window.D._reference()
            != window.D
        ):
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
            "resource_limits": (
                *FeasibleSolver().capabilities()["resource_limits"],
                "packed_word_limit",
            ),
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

            # Packed payload, sparse indices and possible elimination fill are
            # charged separately from logical entries of explicit matrices.
            def buffer_words(rows, columns):
                dense = rows * ((columns + 63) // 64)
                # Sparse/dense transition can coexist with one replaced row.
                return 2 * dense + columns if dense else 0

            detail = {
                "input_nonzero_entries": sum(
                    row.bit_count() for matrix in (w.A, w.D) for row in matrix._bits
                ),
                "boundary_words_upper": sum(
                    buffer_words(matrix.nrows, matrix.ncols) for matrix in (w.A, w.D)
                ),
                "elimination_words_upper": sum(
                    buffer_words(matrix.nrows, matrix.ncols)
                    + 2 * buffer_words(matrix.nrows, matrix.nrows)
                    for matrix in (w.A, w.D)
                ),
                "factor_words_upper": sum(
                    3 * buffer_words(min(matrix.nrows, matrix.ncols), matrix.nrows)
                    for matrix in (w.A, w.D)
                ),
                "output_words_upper": 0,
                "scratch_words_upper": 16 * (w.m + w.n + w.p),
            }

            def check_storage():
                count = sum(
                    value for key, value in detail.items() if key.endswith("_upper")
                )
                budget.search_detail.update(
                    storage_accounting="CompactPackedPayloadV1",
                    storage_breakdown=detail.copy(),
                    packed_words_upper=count,
                    materialized_projection_entries=0,
                )
                limit = problem.resource_limits.packed_word_limit
                limit = 8_000_000 if limit is None else limit
                budget.search_detail["effective_packed_word_limit"] = limit
                if count > limit:
                    raise _Exhausted("packed_word_limit")

            check_storage()
            prepared = []
            for matrix in (w.A, w.D):
                budget.step()
                prepared.append(
                    PreparedMatrix(
                        matrix, cancellation=problem.cancellation, diagnostics=False
                    )
                )
                budget.step(matrix.nrows)
            budget.step()
            if representation == "HC":
                beta = w.n - sum(part.rank() for part in prepared)
                # H/C output plus the reduced span used while constructing H.
                detail["output_words_upper"] = 3 * buffer_words(
                    w.n, beta
                ) + 3 * buffer_words(beta, w.n)
                check_storage()
                budget.step(w.n)
                try:
                    h, c = _extension().hc_factors(
                        prepared[0]._handle,
                        prepared[1]._handle,
                        None
                        if problem.cancellation is None
                        else problem.cancellation._native_handle(),
                        max(
                            0.0,
                            problem.resource_limits.wall_time_limit
                            - (perf_counter() - budget.started),
                        ),
                    )
                except ValueError as error:
                    if str(error).startswith("resource_exhausted:"):
                        raise _Exhausted(str(error).split(":")[1]) from error
                    raise
                budget.step(w.n)
                H, C = Matrix._from_native(h), Matrix._from_native(c)
                action = CompactAction("HC", (H, C))
            else:
                parts = tuple(
                    Matrix._from_native(part._handle.inverse_matrix())
                    for part, matrix in zip(prepared, (w.A, w.D))
                )
                indices = tuple(tuple(part._handle.pivots) for part in prepared)
                action = CompactAction(
                    "GeneralizedInverse", (w.A, w.D, *parts), indices
                )
                if any(
                    w.A.apply(action._inverse(0, z)) != z for z in w.A.transpose().rows
                ) or any(
                    w.D.apply(action._inverse(1, z)) != z for z in w.D.transpose().rows
                ):
                    raise ValueError(
                        "compact generalized inverse failed independent validation"
                    )
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
    started = perf_counter()
    vectors = tuple(validate_vector(x, n) for x in vectors)
    try:
        _extension()
        reused = operator._native_workspace is not None
        workspace = _prepared_workspace(operator)
    except ImportError:
        return QueryResult(
            "Unavailable",
            identity=operator.identity,
            details={"reason": "optional native extension is not installed"},
        )
    packed = tuple(map(_words, vectors))
    converted = perf_counter()
    projected, applied, supports, native_wall = workspace._handle.apply_many(packed)
    returned = perf_counter()
    result = {
        "project": tuple(_unwords(z, n) for z in projected),
        "apply_operator": tuple(_unwords(z, n) for z in applied),
        "support": tuple(tuple(indices) for indices in supports),
    }
    return QueryResult(
        "Computed",
        result,
        operator.identity,
        True,
        {
            "arguments": vectors,
            "workspace_reused": reused,
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
        rows = tuple(_matrix_handle(matrix) for matrix in factors)
        boundary = _matrix_handle(op.window.A)
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


def _prepared_workspace(operator):
    if operator._native_workspace is None:
        object.__setattr__(operator, "_native_workspace", GeometryWorkspace(operator))
    return operator._native_workspace


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
    reused = workspace is not None or operator._native_workspace is not None
    try:
        _extension()
        workspace = workspace or _prepared_workspace(operator)
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
        for z in cycles:
            operator._cycle(z)
        return QueryResult(
            "ResourceExhausted",
            identity=operator.identity,
            details={
                "reason": "matrix_entry_limit",
                "resource_usage": {
                    "states": 0,
                    "limits": asdict(limits),
                    "wall_time": perf_counter() - started,
                },
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
        output = _matrix_handle(projection).apply_many(packed)
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
