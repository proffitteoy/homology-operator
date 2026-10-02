"""Native/reference differentials with independent finite-chain validation."""

from dataclasses import replace
from fractions import Fraction
from itertools import product
import os
import unittest
from unittest.mock import patch

from homology_operator import (
    ChainWindow,
    FeasibleSolver,
    HomologyOperator,
    Matrix,
    CompactAction,
    OperatorResult,
    ProjectionProblem,
    ResourceLimits,
    solve_projection,
)
from homology_operator.chain import matrix_data
from homology_operator.native import (
    NativeFeasibleSolver,
    NativeFactorizedSolver,
    PreparedMatrix,
    apply_batch,
    geometry_batch,
    packed_add,
    packed_multiply,
)
from homology_operator.result import require_same_identity
from homology_operator.validation import ValidationError, validate_projection
from test_joint import oracle, window

try:
    import _homology_native as extension
except ImportError:
    extension = None
    if os.environ.get("HOMOLOGY_NATIVE_REQUIRED") == "1":
        raise RuntimeError("native validation required but extension is missing")


class NativeAvailabilityTests(unittest.TestCase):
    def test_missing_extension_and_unsupported_domain_are_explicit(self):
        w = window(oracle.load_fixtures()[0])
        with patch("homology_operator.native._extension", side_effect=ImportError):
            solution = solve_projection(ProjectionProblem(w), NativeFeasibleSolver())
            self.assertEqual(solution.status, "Unavailable")
            self.assertIsNone(solution.projection)
            op = HomologyOperator(w, FeasibleSolver().solve(ProjectionProblem(w)))
            self.assertEqual(apply_batch(op, []).state, "Unavailable")
            compact = solve_projection(
                ProjectionProblem(w, matrix_free_output=True), NativeFactorizedSolver()
            )
            self.assertEqual(compact.status, "Unavailable")
        w = ChainWindow(
            0,
            Matrix.zero(0, 65),
            Matrix.zero(65, 0),
            (),
            tuple(map(str, range(65))),
            (),
            (1,) * 65,
        )
        self.assertEqual(
            solve_projection(ProjectionProblem(w), NativeFeasibleSolver()).status,
            "Unavailable",
        )
        self.assertEqual(
            solve_projection(
                ProjectionProblem(w, requested_certificate_level="ExactOptimal"),
                NativeFeasibleSolver(),
            ).status,
            "Unavailable",
        )


@unittest.skipUnless(extension is not None, "optional native wheel not installed")
class NativeTests(unittest.TestCase):
    def operator(self, w):
        solution = solve_projection(ProjectionProblem(w), NativeFeasibleSolver())
        self.assertEqual(solution.status, "FeasibleOnly", solution.diagnostics)
        return HomologyOperator(w, solution)

    def test_entire_corpus_actions_identities_and_independent_homology(self):
        for fixture in oracle.load_fixtures():
            with self.subTest(fixture=fixture["id"]):
                w = window(fixture)
                op = self.operator(w)
                ref = HomologyOperator(w, FeasibleSolver().solve(ProjectionProblem(w)))
                self.assertEqual(op.P, ref.P)
                self.assertEqual(op.L, ref.L)
                self.assertEqual(op.kernel_basis(), ref.kernel_basis())
                self.assertEqual(op.betti(), oracle.betti(fixture))
                self.assertTrue(
                    oracle.verify_projection(fixture, oracle.columns(matrix_data(op.P)))
                )
                for key in op.identity:
                    if key != "solver_run_id":
                        self.assertEqual(op.identity[key], ref.identity[key])
                self.assertNotEqual(
                    op.identity["solver_run_id"], ref.identity["solver_run_id"]
                )
                vectors = (
                    tuple(product((0, 1), repeat=w.n))
                    if w.n <= 8
                    else tuple(
                        tuple(int(i == j) for i in range(w.n)) for j in range(w.n)
                    )
                )
                batch = apply_batch(op, vectors)
                self.assertEqual(batch.identity, op.identity)
                self.assertEqual(
                    batch.value["project"], tuple(ref.project(z) for z in vectors)
                )
                self.assertEqual(
                    batch.value["apply_operator"],
                    tuple(ref.apply_operator(z) for z in vectors),
                )

    def test_geometry_empty_repeated_and_round_trip_queries(self):
        for fixture in oracle.load_fixtures():
            w = window(fixture)
            op = self.operator(w)
            cycles = tuple(
                tuple((z >> i) & 1 for i in range(w.n)) for z in oracle.cycles(fixture)
            )
            cycles = cycles[:8] + cycles[:1]
            pairs = tuple((i, (i + 1) % len(cycles)) for i in range(len(cycles)))
            query = geometry_batch(op, cycles, pairs)
            for name in ("class_representative", "selected_mass", "support"):
                self.assertEqual(
                    query.value[name], tuple(getattr(op, name)(z) for z in cycles)
                )
            for name in ("class_distance", "shared_support", "union_support"):
                self.assertEqual(
                    query.value[name],
                    tuple(getattr(op, name)(cycles[i], cycles[j]) for i, j in pairs),
                )
            self.assertEqual(query.exact, w.arithmetic != "FloatingPoint")
            self.assertEqual(geometry_batch(op, []).value["selected_mass"], ())
            before = op.to_result()
            record = replace(
                before, query_results={**before.query_results, "native_geometry": query}
            )
            restored = OperatorResult.from_json(record.to_json())
            self.assertEqual(restored, record)
            recovered = HomologyOperator(
                w, replace(op.solution, projection=restored.projection)
            )
            self.assertEqual(
                geometry_batch(recovered, cycles, pairs).value, query.value
            )
            self.assertEqual(before, op.to_result())

    def test_all_small_augmented_inverses_match_noncycle_extension(self):
        from homology_operator.solver import generalized_inverse

        for m, n in product(range(4), repeat=2):
            for entries in product((0, 1), repeat=m * n):
                a = Matrix(m, n, tuple(entries[i * n : (i + 1) * n] for i in range(m)))
                g, _, _, _, _, reason = extension.construct(
                    tuple(sum(bit << i for i, bit in enumerate(row)) for row in a.rows),
                    m,
                    n,
                    [0] * n,
                    0,
                    1000,
                    10.0,
                    1000000,
                )
                self.assertIsNone(reason)
                actual = Matrix.from_rows(
                    (tuple((row >> j) & 1 for j in range(m)) for row in g), ncols=m
                )
                self.assertEqual(actual, generalized_inverse(a))

    def test_failure_inputs_cycles_padding_and_wrong_identity(self):
        fixture = next(f for f in oracle.load_fixtures() if f["id"] == "h1_k4_stage_4")
        op = self.operator(window(fixture))
        with self.assertRaises(ValidationError):
            validate_projection(op.window, Matrix.zero(op.window.n, op.window.n))
        noncycle = next(
            tuple((x >> i) & 1 for i in range(op.window.n))
            for x in range(1 << op.window.n)
            if not op.is_cycle(tuple((x >> i) & 1 for i in range(op.window.n)))
        )
        self.assertEqual(apply_batch(op, [noncycle]).state, "Computed")
        with self.assertRaisesRegex(ValueError, "cycle"):
            geometry_batch(op, [noncycle])
        for vector in (
            (True,) * op.window.n,
            (0.0,) * op.window.n,
            (0,),
            (2,) * op.window.n,
        ):
            with self.assertRaises(ValueError):
                apply_batch(op, [vector])
        with self.assertRaises(ValueError):
            geometry_batch(op, [tuple([0] * op.window.n)], [(0, 1)])
        with self.assertRaises(ValueError):
            require_same_identity(
                apply_batch(op, []), apply_batch(self.operator(op.window), [])
            )
        for args in (([2], 1, 1, [0], 0), ([1], 1, 1, [1], 1), ([], 1, 0, [], 0)):
            with self.assertRaises(ValueError):
                extension.construct(*args, 1000, 10.0, 1000000)
        with self.assertRaises(ValueError):
            extension.actions([1], 1, [2])

    def test_resource_units_and_empty_and_word_edge(self):
        for m, n, p in ((0, 0, 0), (0, 1, 0), (0, 64, 0), (64, 1, 0), (0, 1, 64)):
            w = ChainWindow(
                0,
                Matrix.zero(m, n),
                Matrix.zero(n, p),
                tuple(f"a{i}" for i in range(m)),
                tuple(f"b{i}" for i in range(n)),
                tuple(f"d{i}" for i in range(p)),
                (1,) * n,
            )
            op = self.operator(w)
            x = (1,) * n
            self.assertEqual(apply_batch(op, [x]).value["project"], (x,))
            self.assertEqual(op.solution.resource_usage["states"], 5 + m + n)
            for limits in (
                ResourceLimits(state_limit=0),
                ResourceLimits(state_limit=4 + m + n),
                ResourceLimits(wall_time_limit=0),
                ResourceLimits(matrix_entry_limit=0),
            ):
                if m == n == p == 0 and limits.matrix_entry_limit == 0:
                    continue
                result = solve_projection(
                    ProjectionProblem(w, resource_limits=limits), NativeFeasibleSolver()
                )
                self.assertEqual(result.status, "ResourceExhausted", result.diagnostics)
                self.assertIsNone(result.projection)

    def test_unbounded_exact_weights_and_floating_policy(self):
        for weights, arithmetic in (
            ((10**100, Fraction(1, 10**80)), "ExactRational"),
            ((1.5, 2.25), "FloatingPoint"),
        ):
            w = ChainWindow(
                0,
                Matrix.zero(0, 2),
                Matrix.zero(2, 0),
                (),
                ("x", "y"),
                (),
                weights,
                arithmetic=arithmetic,
            )
            op = self.operator(w)
            result = geometry_batch(op, [(1, 1), (1, 0)], [(0, 1)])
            self.assertEqual(
                result.value["selected_mass"],
                (op.selected_mass((1, 1)), op.selected_mass((1, 0))),
            )
            self.assertEqual(
                result.value["class_distance"], (op.class_distance((1, 1), (1, 0)),)
            )


@unittest.skipUnless(extension is not None, "optional native wheel not installed")
class PackedAlgebraTests(unittest.TestCase):
    def test_exhaustive_small_canonical_results_and_independent_enumeration(self):
        from test_algebra import multiply_rows, span, vectors

        for m, n in product(range(4), repeat=2):
            for entries in product((0, 1), repeat=m * n):
                matrix = Matrix(
                    m, n, tuple(entries[i * n : (i + 1) * n] for i in range(m))
                )
                prepared = PreparedMatrix(matrix)
                self.assertEqual(prepared.rref(), matrix.rref())
                self.assertEqual(prepared.rank(), matrix.rank())
                self.assertEqual(prepared.kernel_basis(), matrix.kernel_basis())
                self.assertEqual(prepared.image_basis(), matrix.image_basis())
                inputs, rhs = vectors(n), vectors(m)
                image = {multiply_rows(matrix.rows, x) for x in inputs}
                kernel = {
                    x for x in inputs if multiply_rows(matrix.rows, x) == (0,) * m
                }
                self.assertEqual(span(prepared.image_basis(), m), image)
                self.assertEqual(span(prepared.kernel_basis(), n), kernel)
                self.assertEqual(
                    prepared.apply_many(inputs),
                    tuple(multiply_rows(matrix.rows, x) for x in inputs),
                )
                expected = tuple(matrix.solve(x) for x in rhs)
                self.assertEqual(prepared.solve_many(rhs), expected)
                self.assertEqual(
                    prepared.membership_many(rhs), tuple(x in image for x in rhs)
                )
                self.assertEqual(prepared.solve_many(rhs * 2), expected * 2)
                self.assertEqual(prepared.statistics()["decomposition_count"], 1)

    def test_multiword_boundaries_products_padding_and_original_coordinates(self):
        for n in (63, 64, 65, 127, 128, 129):
            for matrix in (
                Matrix.from_rows(
                    (
                        tuple(int((j + 3 * i) % 7 == 0) for j in range(n))
                        for i in range(7)
                    )
                ),
                Matrix.from_rows(
                    (tuple(int((i + j) % 5 == 0) for j in range(7)) for i in range(n))
                ),
                Matrix.identity(n),
                Matrix.zero(0, n),
                Matrix.zero(n, 0),
            ):
                prepared = PreparedMatrix(matrix)
                self.assertEqual(prepared.rref(), matrix.rref())
                self.assertEqual(prepared.kernel_basis(), matrix.kernel_basis())
                self.assertEqual(prepared.image_basis(), matrix.image_basis())
                vectors = tuple(
                    tuple(int((j + i) % 3 == 0) for j in range(matrix.ncols))
                    for i in range(3)
                )
                self.assertEqual(
                    prepared.apply_many(vectors),
                    tuple(matrix.apply(x) for x in vectors),
                )
                rhs = tuple(matrix.apply(x) for x in vectors) + (
                    tuple(int(j == matrix.nrows - 1) for j in range(matrix.nrows)),
                )
                self.assertEqual(
                    prepared.solve_many(rhs), tuple(matrix.solve(x) for x in rhs)
                )
                self.assertEqual(
                    prepared.membership_many(rhs),
                    tuple(matrix.solve(x) is not None for x in rhs),
                )
                self.assertEqual(
                    packed_add(matrix, matrix), Matrix.zero(matrix.nrows, matrix.ncols)
                )
                for row in prepared._handle.rref():
                    if matrix.ncols % 64:
                        self.assertEqual(row[-1] >> (matrix.ncols % 64), 0)
            left = Matrix.from_rows(
                (tuple(int((j + i) % 4 == 0) for j in range(n)) for i in range(3))
            )
            right = Matrix.from_rows(
                (tuple(int((j + i) % 7 == 0) for j in range(n + 1)) for i in range(n))
            )
            self.assertEqual(packed_multiply(left, right), left @ right)
            self.assertEqual(
                packed_multiply(Matrix.zero(3, 0), Matrix.zero(0, n)), Matrix.zero(3, n)
            )

    def test_immutable_reuse_no_weight_or_projection_selection(self):
        from dataclasses import FrozenInstanceError

        matrix = Matrix.from_rows(((0, 1, 1), (0, 1, 0), (0, 0, 0)))
        prepared = PreparedMatrix(matrix)
        initial = prepared.statistics()
        for count in (0, 1, 8, 64, 1024):
            rhs = ((1, 0, 0),) * count
            self.assertEqual(
                prepared.solve_many(rhs), (matrix.solve((1, 0, 0)),) * count
            )
            self.assertEqual(prepared.statistics(), initial)
        with self.assertRaises(FrozenInstanceError):
            prepared.matrix = Matrix.zero(3, 3)
        with self.assertRaises(AttributeError):
            prepared._handle.ncols = 9
        self.assertGreaterEqual(
            initial["peak_nonzero_bits"], initial["source_nonzero_bits"]
        )
        self.assertGreaterEqual(
            initial["peak_nonzero_bits"], initial["reduced_nonzero_bits"]
        )
        # 2 copies of coefficient words plus the independent row transform.
        self.assertEqual(initial["stored_words"], 9)

    def test_invalid_shapes_rhs_padding_and_unavailable_extension(self):
        with patch("homology_operator.native._extension", side_effect=ImportError):
            with self.assertRaises(ImportError):
                PreparedMatrix(Matrix.zero(0, 0))
        with self.assertRaises(ValueError):
            PreparedMatrix(((1, 0),))
        for operation in (
            lambda: packed_add(Matrix.zero(2, 3), Matrix.zero(3, 2)),
            lambda: packed_multiply(Matrix.zero(2, 3), Matrix.zero(2, 3)),
            lambda: PreparedMatrix(Matrix.identity(2)).solve((True, 0)),
            lambda: PreparedMatrix(Matrix.identity(2)).apply_many([(0,)]),
            lambda: PreparedMatrix(Matrix.identity(2)).membership_many([(2, 0)]),
            lambda: extension.PreparedMatrix([[2]], 1),
            lambda: extension.PreparedMatrix([[]], 1),
            lambda: extension.PreparedMatrix([[0]], 0),
            lambda: extension.PreparedMatrix([[0, 2]], 65),
            lambda: extension.PreparedMatrix([[0, 0]], 65).apply_many([[0, 2]]),
            lambda: extension.PreparedMatrix([[1]], 1).solve_many([[2]]),
        ):
            with self.assertRaises(ValueError):
                operation()


@unittest.skipIf(extension is None, "optional native wheel not installed")
class NativeSolverTests(unittest.TestCase):
    def compare(self, problem, method):
        reference = solve_projection(problem, method)
        actual = solve_projection(problem, "Native" + method)
        self.assertEqual(actual.status, reference.status, actual.diagnostics)
        self.assertEqual(actual.projection, reference.projection)
        self.assertEqual(actual.certificate_level, reference.certificate_level)
        self.assertEqual(actual.objective.state, reference.objective.state)
        self.assertEqual(actual.objective.value, reference.objective.value)
        self.assertEqual(actual.lower_bound, reference.lower_bound)
        self.assertEqual(actual.upper_bound, reference.upper_bound)
        self.assertEqual(actual.certificate, reference.certificate)
        self.assertEqual(
            actual.resource_usage.get("states"), reference.resource_usage.get("states")
        )
        if actual.projection is not None:
            self.assertEqual(
                actual.identity["projection_id"], reference.identity["projection_id"]
            )
            # Force the original Python replay independently of the native choice.
            from homology_operator.validation import validate_solution

            with patch(
                "homology_operator.validation._replay_native", return_value=False
            ):
                validate_solution(problem.window, actual)
            op = HomologyOperator(problem.window, actual)
            record = op.to_result()
            restored = OperatorResult.from_json(record.to_json())
            self.assertEqual(restored.projection, actual.projection)
            self.assertEqual(
                restored.to_json(),
                OperatorResult.from_json(restored.to_json()).to_json(),
            )
        return actual

    def test_sourced_corpus_same_actions_certificates_and_states(self):
        for fixture in oracle.load_fixtures():
            w = window(fixture)
            for method in (
                "ExhaustiveExactSolver",
                "GreedyCertifiedSolver",
                "Rank2ExactSolver",
            ):
                with self.subTest(fixture=fixture["id"], method=method):
                    self.compare(ProjectionProblem(w), method)

    def test_cut_and_structured_supports_remain_exact(self):
        from test_rank2 import cut_problem
        from test_structured import cyclic_window

        self.compare(cut_problem(), "Rank2ExactSolver")
        for m in (2, 3, 4):
            w, _ = cyclic_window(m)
            for matrix_free in (False, True):
                self.compare(
                    ProjectionProblem(
                        w,
                        input_structure="CyclicTrace",
                        matrix_free_output=matrix_free,
                        requested_certificate_level="ExactOptimal",
                    ),
                    "StructuredFamilySolver",
                )

    def test_all_state_interruptions_keep_completed_bounds_and_seeds(self):
        from test_structured import cyclic_window

        w, _ = cyclic_window(2)
        for method in (
            "ExhaustiveExactSolver",
            "GreedyCertifiedSolver",
            "Rank2ExactSolver",
            "StructuredFamilySolver",
        ):
            problem = ProjectionProblem(
                w,
                input_structure="CyclicTrace"
                if method == "StructuredFamilySolver"
                else "GeneralChainWindow",
            )
            complete = solve_projection(problem, method)
            for limit in range(complete.resource_usage["states"] + 1):
                with self.subTest(method=method, state_limit=limit):
                    self.compare(
                        replace(
                            problem, resource_limits=ResourceLimits(state_limit=limit)
                        ),
                        method,
                    )
            for limits in (
                ResourceLimits(wall_time_limit=0),
                ResourceLimits(matrix_entry_limit=0),
            ):
                self.compare(replace(problem, resource_limits=limits), method)

    def test_unbounded_weights_visible_fallback_and_cross_product_overflow(self):
        from test_structured import cyclic_window

        w, _ = cyclic_window(2)
        for arithmetic, weights in (
            ("ExactInteger", (2**200 + 1, 2**200 + 3, 2**200 + 7)),
            (
                "ExactRational",
                (Fraction(1, 2**131 - 1), Fraction(1, 2**127 - 1), Fraction(7, 11)),
            ),
            ("ExactInteger", (2**126 - 1, 2**125 + 1, 2**124 + 3)),
        ):
            problem = ProjectionProblem(
                replace(w, weights=weights, arithmetic=arithmetic)
            )
            for method in (
                "ExhaustiveExactSolver",
                "GreedyCertifiedSolver",
                "Rank2ExactSolver",
            ):
                actual = self.compare(problem, method)
                if sum(weights) > 2**128 or arithmetic == "ExactRational":
                    self.assertGreater(
                        actual.resource_usage["native_detail"][
                            "exact_mass_fallback_calls"
                        ],
                        0,
                    )

    def test_multiword_cycle_objective_matches_independent_finite_vectors(self):
        from homology_operator.native import _span_objective, _words, _integer_weights
        from homology_operator.solver import _Budget, _cycle_objective

        for n in (0, 1, 63, 64, 65, 127, 128, 129):
            basis = Matrix.from_columns(
                (tuple(int(j == i) for j in range(n)) for i in range(min(3, n))),
                nrows=n,
            )
            w = ChainWindow(
                1,
                Matrix.zero(0, n),
                Matrix.zero(n, 0),
                (),
                tuple(f"e{j}" for j in range(n)),
                (),
                tuple(Fraction(j + 1, 3) for j in range(n)),
            )
            P = Matrix.from_rows(
                (
                    tuple(int((i - j) % max(1, n) in (0, 1)) for j in range(n))
                    for i in range(n)
                ),
                ncols=n,
            )
            expected = _cycle_objective(w, P, basis, _Budget(ResourceLimits()))
            self.assertEqual(
                _span_objective(w, P, basis.transpose().rows, detail={}), expected
            )
            weights, _ = _integer_weights(w.weights)
            vectors, masses, used, reason = extension.span_table(
                tuple(map(_words, basis.transpose().rows)), weights, 100000, None
            )
            self.assertEqual(used, 2**basis.ncols - 1)
            self.assertIsNone(reason)
            self.assertEqual(len(vectors), len(masses))

    def test_tampered_proofs_actions_and_witnesses_rejected_by_both_replays(self):
        from test_rank2 import cut_problem
        from homology_operator.validation import validate_solution

        problem = cut_problem()
        solution = solve_projection(problem, "NativeRank2ExactSolver")
        for key, value in (
            ("candidate_count", 1),
            ("class_minima", (1, 1, 1)),
            ("searched_candidates", 0),
            ("tie_break_complete", False),
        ):
            bad = replace(
                solution,
                certificate={
                    "optimization": {**solution.certificate["optimization"], key: value}
                },
            )
            for native in (True, False):
                with patch(
                    "homology_operator.validation._replay_native", return_value=native
                ):
                    with self.assertRaises(ValidationError):
                        validate_solution(problem.window, bad)
        bad = replace(
            solution, projection=Matrix.zero(problem.window.n, problem.window.n)
        )
        with self.assertRaises(ValidationError):
            validate_solution(problem.window, bad)
        bad = replace(
            solution,
            objective=replace(
                solution.objective, details={"witness": (0,) * problem.window.n}
            ),
        )
        with self.assertRaises(ValidationError):
            validate_solution(problem.window, bad)

    def test_missing_extension_recovery_and_unsupported_requests(self):
        from test_structured import cyclic_window

        w, _ = cyclic_window(2)
        for method in (
            "ExhaustiveExactSolver",
            "GreedyCertifiedSolver",
            "Rank2ExactSolver",
            "StructuredFamilySolver",
        ):
            problem = ProjectionProblem(
                w,
                input_structure="CyclicTrace"
                if method == "StructuredFamilySolver"
                else "GeneralChainWindow",
            )
            with patch("homology_operator.native._extension", side_effect=ImportError):
                result = solve_projection(problem, "Native" + method)
                self.assertEqual(result.status, "Unavailable")
                self.assertIsNone(result.projection)
            floating = replace(
                problem,
                window=replace(w, weights=(1.0,) * w.n, arithmetic="FloatingPoint"),
            )
            self.assertEqual(
                solve_projection(floating, "Native" + method).status, "Unavailable"
            )
        result = solve_projection(ProjectionProblem(w), "NativeExhaustiveExactSolver")
        record = HomologyOperator(w, result).to_result()
        with patch("homology_operator.native._extension", side_effect=ImportError):
            recovered = OperatorResult.from_json(record.to_json())
            self.assertEqual(recovered.projection, result.projection)
            self.assertEqual(
                recovered.certificate["certificate_replay_backend"], "python-reference"
            )
        for operation in (
            lambda: extension.span_table([[2]], [1], 10, None),
            lambda: extension.span_table([[1]], [0], 10, None),
            lambda: extension.span_table([[1]], [2**128 - 1, 1], 10, None),
            lambda: extension.span_objective([[1]], [], [1], 10, None),
            lambda: extension.span_table([[1]] * 17, [1], 10, None),
            lambda: extension.span_table([[1]], [1], 10, -1.0),
            lambda: extension.span_table([[1], [1]], [1], 10, None),
            lambda: extension.cyclic_batch(5, [[0]]),
        ):
            with self.assertRaises(ValueError):
                operation()


class CompactValidationTests(unittest.TestCase):
    def test_reference_only_compact_identity_recovery_and_geometry(self):
        from homology_operator.result import make_identity, QueryResult

        w = ChainWindow(
            0,
            Matrix.zero(0, 2),
            Matrix.from_rows(((1,), (1,))),
            (),
            ("a", "b"),
            ("e",),
            (10, 1),
        )
        hc = CompactAction(
            "HC", (Matrix.from_columns(((1, 0),), 2), Matrix.from_rows(((1, 1),)))
        )
        seed = FeasibleSolver().solve(ProjectionProblem(w))
        identity = make_identity(w, hc, seed.solver_run_id)
        solution = replace(
            seed,
            projection=hc,
            identity=identity,
            objective=QueryResult("NotComputed", identity=identity),
        )
        with patch("homology_operator.native._extension", side_effect=ImportError):
            op = HomologyOperator(w, solution)
            self.assertEqual(op.kernel_basis(), ((1, 0),))
            self.assertEqual(op.selected_mass((0, 1)), 10)
            self.assertEqual(op.class_distance((1, 0), (0, 1)), 0)
            restored = OperatorResult.from_json(op.to_result().to_json())
            self.assertEqual(restored.projection, hc)
            self.assertEqual(restored.identity, identity)
            self.assertEqual(restored.projection.apply((1, 1)), (0, 0))

    def test_independent_homology_validation_rejects_zero_and_bad_hc(self):
        w = ChainWindow(
            0, Matrix.zero(0, 2), Matrix.zero(2, 0), (), ("a", "b"), (), (1, 1)
        )
        zero = CompactAction("HC", (Matrix.zero(2, 0), Matrix.zero(0, 2)))
        with self.assertRaises(ValidationError) as error:
            validate_projection(w, zero)
        self.assertEqual(error.exception.failures, ("cycle_homology_preservation",))
        bad = CompactAction("HC", (Matrix.identity(2), Matrix.zero(2, 2)))
        with self.assertRaises(ValidationError) as error:
            validate_projection(w, bad)
        self.assertIn("c_h_identity", error.exception.failures)


@unittest.skipUnless(extension is not None, "optional native wheel not installed")
class CompactActionTests(unittest.TestCase):
    def solution(self, w, form="Factorized", limits=None):
        request = ProjectionProblem(
            w,
            matrix_free_output=True,
            solver_options={"representation": form},
            resource_limits=limits or ResourceLimits(),
        )
        result = solve_projection(request, NativeFactorizedSolver())
        self.assertEqual(result.status, "FeasibleOnly", result.diagnostics)
        return result

    def test_corpus_all_generator_and_cycle_actions_same_p_and_geometry(self):
        for fixture in oracle.load_fixtures():
            w = window(fixture)
            ref = HomologyOperator(w, FeasibleSolver().solve(ProjectionProblem(w)))
            for form in ("Factorized", "HC"):
                with self.subTest(fixture=fixture["id"], form=form):
                    solution = self.solution(w, form)
                    op = HomologyOperator(w, solution)
                    self.assertIsNone(solution.generalized_inverse_a)
                    self.assertIsNone(solution.generalized_inverse_d)
                    self.assertFalse(hasattr(op.P, "rows"))
                    self.assertEqual(op.kernel_basis(), ref.kernel_basis())
                    self.assertEqual(op.betti(), ref.betti())
                    generators = tuple(
                        tuple(int(i == j) for i in range(w.n)) for j in range(w.n)
                    )
                    vectors = (
                        tuple(product((0, 1), repeat=w.n)) if w.n <= 8 else generators
                    )
                    self.assertEqual(
                        tuple(op.project(x) for x in vectors),
                        tuple(ref.project(x) for x in vectors),
                    )
                    batch = apply_batch(op, vectors)
                    self.assertEqual(
                        batch.value["project"], tuple(ref.project(x) for x in vectors)
                    )
                    self.assertEqual(
                        batch.value["apply_operator"],
                        tuple(ref.apply_operator(x) for x in vectors),
                    )
                    columns = tuple(
                        sum(bit << i for i, bit in enumerate(op.project(e)))
                        for e in generators
                    )
                    self.assertTrue(oracle.verify_projection(fixture, columns))
                    cycles = tuple(
                        tuple((z >> i) & 1 for i in range(w.n))
                        for z in oracle.cycles(fixture)
                    )[:8]
                    pairs = tuple(
                        (i, (i + 1) % len(cycles)) for i in range(len(cycles))
                    )
                    query = geometry_batch(op, cycles, pairs)
                    for name in ("class_representative", "selected_mass", "support"):
                        self.assertEqual(
                            query.value[name],
                            tuple(getattr(ref, name)(z) for z in cycles),
                        )
                    for name in ("class_distance", "shared_support", "union_support"):
                        self.assertEqual(
                            query.value[name],
                            tuple(
                                getattr(ref, name)(cycles[i], cycles[j])
                                for i, j in pairs
                            ),
                        )
                    restored = OperatorResult.from_json(op.to_result().to_json())
                    self.assertEqual(restored.projection, op.P)
                    self.assertEqual(restored.identity, op.identity)
                    with self.assertRaises(ValueError):
                        require_same_identity(op.identity, ref.identity)

    def test_full_augmented_inverse_rows_and_small_chain_windows(self):
        from homology_operator.solver import generalized_inverse

        for m, n in product(range(4), repeat=2):
            for entries in product((0, 1), repeat=m * n):
                a = Matrix(m, n, tuple(entries[i * n : (i + 1) * n] for i in range(m)))
                handle = PreparedMatrix(a)._handle
                rows = handle.inverse_rows()
                expanded = [[0] * m for _ in range(n)]
                for pivot, row in zip(handle.pivots, rows):
                    expanded[pivot] = [(row[i // 64] >> (i % 64)) & 1 for i in range(m)]
                self.assertEqual(
                    Matrix.from_rows(expanded, ncols=m), generalized_inverse(a)
                )
        for m, n in product(range(3), range(4)):
            for entries in product((0, 1), repeat=m * n):
                a = Matrix(m, n, tuple(entries[i * n : (i + 1) * n] for i in range(m)))
                for z in product((0, 1), repeat=n):
                    if any(a.apply(z)):
                        continue
                    d = Matrix.from_columns((z,), nrows=n)
                    w = ChainWindow(
                        1,
                        a,
                        d,
                        tuple(f"a{i}" for i in range(m)),
                        tuple(f"c{i}" for i in range(n)),
                        ("b",),
                        (1,) * n,
                    )
                    ref = HomologyOperator(
                        w, FeasibleSolver().solve(ProjectionProblem(w))
                    )
                    op = HomologyOperator(w, self.solution(w))
                    self.assertEqual(op.kernel_basis(), ref.kernel_basis())
                    self.assertEqual(op.betti(), ref.betti())

    def test_no_dense_projection_inverse_identity_or_rust_required_for_restore(self):
        fixture = next(f for f in oracle.load_fixtures() if f["id"] == "h1_k4_stage_4")
        w = window(fixture)
        with (
            patch(
                "homology_operator.solver.generalized_inverse",
                side_effect=AssertionError("expanded G/U"),
            ),
            patch.object(
                Matrix, "identity", side_effect=AssertionError("dense identity")
            ),
        ):
            # Factorized verifier uses generators, never an n by n identity/P.
            solution = self.solution(w)
            op = HomologyOperator(w, solution)
            op.project((1, 0, 0, 0, 0, 0))
            record = op.to_result()
            OperatorResult.from_json(record.to_json())
        # HC verifier may allocate a beta by beta identity, never n by n P.
        original_identity = Matrix.identity

        def guarded_identity(size):
            if size == w.n:
                raise AssertionError("dense projection identity")
            return original_identity(size)

        with patch.object(Matrix, "identity", side_effect=guarded_identity):
            hc = HomologyOperator(w, self.solution(w, "HC"))
            serialized = hc.to_result().to_json()
        with patch("homology_operator.native._extension", side_effect=ImportError):
            restored = OperatorResult.from_json(serialized)
            restored_op = HomologyOperator(
                w, replace(hc.solution, projection=restored.projection)
            )
            self.assertEqual(
                restored_op.project((1, 0, 0, 0, 0, 0)), hc.project((1, 0, 0, 0, 0, 0))
            )

    def test_illegal_factors_hc_zero_projection_and_tampered_version_identity(self):
        from homology_operator.chain import action_data, action_from_data
        from homology_operator.result import make_identity

        fixture = next(f for f in oracle.load_fixtures() if f["id"] == "h1_k4_stage_4")
        w = window(fixture)
        op = HomologyOperator(w, self.solution(w))
        a, d, g, u = op.P.factors
        invalid = CompactAction(
            op.P.form, (a, d, Matrix.zero(g.nrows, g.ncols), u), op.P.pivots
        )
        with self.assertRaises(ValidationError):
            validate_projection(w, invalid)
        zero = CompactAction("HC", (Matrix.zero(w.n, 0), Matrix.zero(0, w.n)))
        with self.assertRaises(ValidationError) as error:
            validate_projection(w, zero)
        self.assertIn("cycle_homology_preservation", error.exception.failures)
        hc = HomologyOperator(w, self.solution(w, "HC"))
        h, c = hc.P.factors
        invalid = CompactAction("HC", (h, Matrix.zero(c.nrows, c.ncols)))
        with self.assertRaises(ValidationError):
            validate_projection(w, invalid)
        data = action_data(op.P)
        for changes in (
            {"version": 2},
            {"version": True},
            {"extra": 0},
            {"complement": 1},
            {"form": "Unknown"},
        ):
            with self.assertRaises(ValueError):
                action_from_data({**data, **changes})
        record = op.to_result().to_dict()
        record["projection"]["factors"][2]["rows"] = [
            [0] * g.ncols for _ in range(g.nrows)
        ]
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(record)
        with self.assertRaises(ValueError):
            HomologyOperator(
                w,
                replace(
                    op.solution,
                    projection=hc.P,
                    identity=make_identity(w, op.P, op.solution.solver_run_id),
                ),
            )
        with self.assertRaises(ValueError):
            CompactAction("GeneralizedInverse", op.P.factors, ((True,), op.P.pivots[1]))
        with self.assertRaises(ValueError):
            extension.compact_actions("HC", [[[0]], [[0]]], [1, 2], [], False, [[1]])

    def test_multiword_factor_hc_resource_and_query_domains(self):
        for n in (0, 1, 63, 64, 65, 127, 128, 129):
            # Two surviving coordinates, all remaining coordinates boundaries.
            d = Matrix.from_columns(
                (tuple(int(i == j) for i in range(n)) for j in range(2, n)), nrows=n
            )
            w = ChainWindow(
                0,
                Matrix.zero(0, n),
                d,
                (),
                tuple(map(str, range(n))),
                tuple(f"b{i}" for i in range(d.ncols)),
                (1,) * n,
            )
            for form in ("Factorized", "HC"):
                op = HomologyOperator(w, self.solution(w, form))
                x = (1,) * n
                expected = tuple(int(i < 2) for i in range(n))
                self.assertEqual(op.project(x), expected)
                self.assertEqual(apply_batch(op, [x]).value["project"], (expected,))
                self.assertEqual(op.betti(), min(n, 2))
                expected_states = 5 + n + (2 * n if form == "HC" else 0)
                self.assertEqual(op.solution.resource_usage["states"], expected_states)
        w = window(
            next(f for f in oracle.load_fixtures() if f["id"] == "h1_k4_stage_4")
        )
        for limits in (
            ResourceLimits(state_limit=0),
            ResourceLimits(wall_time_limit=0),
            ResourceLimits(matrix_entry_limit=0),
        ):
            result = solve_projection(
                ProjectionProblem(w, matrix_free_output=True, resource_limits=limits),
                NativeFactorizedSolver(),
            )
            self.assertEqual(result.status, "ResourceExhausted", result.diagnostics)
            self.assertIsNone(result.projection)
        op = HomologyOperator(w, self.solution(w))
        with self.assertRaisesRegex(ValueError, "cycle"):
            geometry_batch(op, [(1, 0, 0, 0, 0, 0)])
        self.assertEqual(
            solve_projection(ProjectionProblem(w), NativeFactorizedSolver()).status,
            "Unavailable",
        )
        self.assertEqual(
            solve_projection(
                ProjectionProblem(
                    w,
                    matrix_free_output=True,
                    requested_certificate_level="ExactOptimal",
                ),
                NativeFactorizedSolver(),
            ).status,
            "Unavailable",
        )

    def test_compact_family_transport_ranks_barcode_and_restore(self):
        from homology_operator import OperatorFamily, OperatorFamilyResult
        from test_family_joint import corpus_families, family_from

        for _, fixtures in corpus_families():
            ref = family_from(fixtures)
            for form in ("Factorized", "HC"):
                operators = tuple(
                    HomologyOperator(w, self.solution(w, form)) for w in ref.windows
                )
                family = OperatorFamily(ref.scales, ref.windows, operators)
                self.assertEqual(family.barcode().value, ref.barcode().value)
                for i in range(len(operators)):
                    for j in range(i, len(operators)):
                        self.assertEqual(
                            family.transport_rank(i, j).value,
                            ref.transport_rank(i, j).value,
                        )
                        self.assertEqual(
                            family.transport(i, j).value, ref.transport(i, j).value
                        )
                restored = OperatorFamilyResult.from_json(
                    family.to_result().to_json()
                ).to_family()
                self.assertEqual(restored.barcode().value, family.barcode().value)


if __name__ == "__main__":
    unittest.main()
