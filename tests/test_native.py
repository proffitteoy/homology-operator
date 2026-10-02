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
    OperatorResult,
    ProjectionProblem,
    ResourceLimits,
    solve_projection,
)
from homology_operator.chain import matrix_data
from homology_operator.native import NativeFeasibleSolver, apply_batch, geometry_batch
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


if __name__ == "__main__":
    unittest.main()
