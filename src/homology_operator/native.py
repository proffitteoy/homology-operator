"""Optional native adapters; Python remains the independent validator.

Importing this adapter never requires Rust. Missing/unsupported construction is
Unavailable, without silently calling a different solver. Geometry uses exact
Python weights on native Pz; its cost is reported as a visible fallback.
"""

from dataclasses import asdict, dataclass, field
from time import perf_counter
from uuid import uuid4

from .algebra import Matrix, CompactAction, validate_vector
from .operator import HomologyOperator
from .result import QueryResult, make_identity
from .solver import (
    FeasibleSolver,
    ProjectionSolution,
    check_solver_request,
    _Budget,
    _Exhausted,
)


def _extension():
    import _homology_native

    return _homology_native


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
    _handle: object = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.matrix, Matrix):
            raise ValueError("prepare requires a validated Matrix")
        object.__setattr__(
            self,
            "_handle",
            _extension().PreparedMatrix(
                tuple(map(_words, self.matrix.rows)), self.matrix.ncols
            ),
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
        budget = _Budget(problem.resource_limits)
        try:
            budget.step()
            # Keep reference's logical entry guard; not a claim about packed RSS.
            budget.entries(w.m * w.n + w.n * w.p + w.n * w.m + w.p * w.n + 4 * w.n**2)
            parts, indices = [], []
            for matrix in (w.A, w.D):
                budget.step()
                budget.entries(matrix.nrows * (matrix.ncols + matrix.nrows))
                prepared = PreparedMatrix(matrix)
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
                prepared_h = PreparedMatrix(H)
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


def geometry_batch(operator, cycles, pairs=()):
    """Reuse native Pz for exact Python mass/distance/support, on cycles only."""
    cycles = tuple(operator._cycle(z) for z in cycles)
    pairs = tuple(tuple(pair) for pair in pairs)
    if any(
        len(pair) != 2
        or any(type(i) is not int or not 0 <= i < len(cycles) for i in pair)
        for pair in pairs
    ):
        raise ValueError("pairs must index two cycles in this batch")
    actions = apply_batch(operator, cycles)
    if actions.state != "Computed":
        return actions
    started = perf_counter()
    representatives = actions.value["project"]
    supports = actions.value["support"]
    distances, shared, union = [], [], []
    for i, j in pairs:
        distances.append(
            operator._mass(
                tuple(a ^ b for a, b in zip(representatives[i], representatives[j]))
            )
        )
        shared.append(tuple(sorted(set(supports[i]) & set(supports[j]))))
        union.append(tuple(sorted(set(supports[i]) | set(supports[j]))))
    value = {
        "class_representative": representatives,
        "selected_mass": tuple(operator._mass(z) for z in representatives),
        "support": supports,
        "class_distance": tuple(distances),
        "shared_support": tuple(shared),
        "union_support": tuple(union),
    }
    exact = operator.window.arithmetic != "FloatingPoint"
    return QueryResult(
        "Computed",
        value,
        operator.identity,
        exact,
        {
            **actions.details,
            "pairs": pairs,
            "geometry_fallback": "python Fraction/int or binary64 fsum",
            "geometry_fallback_seconds": perf_counter() - started,
            "arithmetic_policy": operator.window.arithmetic,
            "rounding_policy": None if exact else "binary64 fsum; nearest-even",
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
        tuple(map(_words, basis)), tuple(map(_words, images)), weights, quota, remaining
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
        tuple(map(_words, basis)), weights, quota, remaining
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
