"""Rank-two algebra, pinned T5/T-A3/T-A4 reductions, and rejection boundaries.

Formula-generated fixtures use homology-operator-lab commit
6143729669902ee875b211b58085e954c76cdf88, PROOF.md Git blob
62bd2b85163fe0f28f4b513fd4798e01565941bc; no research runtime is imported.
"""

from dataclasses import replace
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
import unittest

from homology_operator import (
    Matrix,
    ChainWindow,
    ProjectionProblem,
    ResourceLimits,
    Rank2ExactSolver,
    HomologyOperator,
    OperatorResult,
    OperatorFamily,
    OperatorFamilyResult,
    solve_projection,
)
from homology_operator.solver import _Budget, _pareto_rank2
from test_joint import oracle, window as fixture_window


def cut_problem(delta=Fraction(1, 4)):
    # Fixed PROOF T-A4 macro dual U0,U1,UV,V0,V2 (no planar mesh inference).
    edges = ((3, 0), (3, 1), (3, 4), (4, 0), (4, 2))
    coboundary = Matrix.from_rows(
        (tuple(int(u == t) ^ int(v == t) for t in (1, 2, 3, 4)) for u, v in edges)
    )
    A = Matrix.from_rows(coboundary.transpose().kernel_basis(), ncols=5)
    D = Matrix.from_columns(coboundary.transpose().rows[2:], nrows=5)
    window = ChainWindow(
        1,
        A,
        D,
        ("cycle_relation",),
        ("U0", "U1", "UV", "V0", "V2"),
        ("U", "V"),
        (1, 2 - 2 * delta, 1 - delta, 1, 2 - delta),
    )
    return ProjectionProblem(
        window,
        requested_certificate_level="ExactOptimal",
        input_structure="ThreeTerminalCut",
        solver_options={
            "dual_vertex_count": 5,
            "dual_edges": edges,
            "terminals": (0, 1, 2),
        },
    )


class Rank2Tests(unittest.TestCase):
    def test_all_sourced_rank2_windows_match_exhaustive(self):
        expectations = json.loads(
            (Path(__file__).parent / "fixtures/solver_reference.json").read_text(
                encoding="utf-8"
            )
        )
        by_id = {f["fixture_id"]: f for f in expectations["fixtures"]}
        checked = 0
        for fixture in oracle.load_fixtures():
            window = fixture_window(fixture)
            if window.n - window.A.rank() - window.D.rank() != 2:
                continue
            checked += 1
            expected = by_id[fixture["id"]]
            self.assertEqual(expected["input_hash"], fixture["input_hash"])
            result = solve_projection(
                ProjectionProblem(window, requested_certificate_level="ExactOptimal"),
                "Rank2ExactSolver",
            )
            self.assertEqual(result.status, "Solved", result.diagnostics)
            optimum = expected["expected_optimum"]
            self.assertEqual(
                result.objective.value,
                Fraction(optimum["numerator"], optimum["denominator"]),
            )
            self.assertEqual(result.certificate_level, "ExactOptimal")
            op = HomologyOperator(window, result)
            columns = tuple(
                sum(bit << j for j, bit in enumerate(z)) for z in op.P.transpose().rows
            )
            self.assertTrue(oracle.verify_projection(fixture, columns))
            op.readout("selected_mass", (0,) * window.n)
            op.stretch()
            record = op.to_result()
            self.assertEqual(record, OperatorResult.from_json(record.to_json()))
            family = OperatorFamily((0,), (window,), (op,))
            snapshot = family.to_result()
            restored = (
                OperatorFamilyResult.from_json(snapshot.to_json())
                .to_family()
                .to_result()
            )
            self.assertEqual(restored.to_json(), snapshot.to_json())
            if window.k == 1:
                graph = solve_projection(
                    ProjectionProblem(window, input_structure="GraphCycle"),
                    "Rank2ExactSolver",
                )
                self.assertEqual(graph.status, "Solved", graph.diagnostics)
                self.assertEqual(graph.objective.value, result.objective.value)
        self.assertEqual(checked, 6)

    def test_three_terminal_exact_macro_family_and_all_small_weights(self):
        for delta in (Fraction(1, 4), Fraction(1, 10), Fraction(1, 1000)):
            problem = cut_problem(delta)
            result = solve_projection(problem, "Rank2ExactSolver")
            self.assertEqual(result.status, "Solved", result.diagnostics)
            self.assertEqual(result.objective.value, (2 - delta) / (2 - 2 * delta))
            self.assertEqual(result.resource_usage["candidates_visited"], 9)
            proof = result.certificate["optimization"]
            self.assertEqual(proof["terminal_labels"], (0, 1, 2, 1, 2))
            self.assertEqual(proof["class_minima"], (2 - 2 * delta, 2 - delta, 2))
            exact = solve_projection(
                ProjectionProblem(
                    problem.window, requested_certificate_level="ExactOptimal"
                ),
                "ExhaustiveExactSolver",
            )
            self.assertEqual(result.objective.value, exact.objective.value)
        for weights in product((1, 2), repeat=5):
            problem = cut_problem()
            problem = replace(
                problem,
                window=replace(
                    problem.window, weights=weights, arithmetic="ExactInteger"
                ),
            )
            result = solve_projection(problem, "Rank2ExactSolver")
            exact = solve_projection(
                ProjectionProblem(
                    problem.window, requested_certificate_level="ExactOptimal"
                ),
                "ExhaustiveExactSolver",
            )
            self.assertEqual(result.status, "Solved", result.diagnostics)
            self.assertEqual(result.objective.value, exact.objective.value)

    def test_pareto_elimination_reduces_support_without_increasing_any_class(self):
        for weights in ((1, 2, 3), (3, 1, 2), (2, 3, 1), (1, 1, 1)):
            window = ChainWindow(
                2,
                Matrix.zero(0, 3),
                Matrix.from_columns(((1, 1, 1),), nrows=3),
                (),
                ("x", "y", "z"),
                ("b",),
                weights,
            )
            pair = ((1, 1, 0), (0, 1, 1))
            final, trace = _pareto_rank2(
                window, pair, window.D.image_basis(), _Budget(ResourceLimits())
            )
            self.assertEqual(len(trace), 1)
            self.assertEqual(sum(any(bits) for bits in zip(*final)), 2)

            def masses(p):
                x, y = p
                return tuple(
                    sum(w for w, bit in zip(weights, z) if bit)
                    for z in (x, y, tuple(a ^ b for a, b in zip(x, y)))
                )

            self.assertTrue(
                all(
                    after <= before
                    for before, after in zip(masses(pair), masses(final))
                )
            )
            for before, after in zip(pair, final):
                self.assertIsNotNone(
                    window.D.solve(tuple(a ^ b for a, b in zip(before, after)))
                )
            # All sections of this abstract positive-weight rank-2 quotient.
            result = solve_projection(ProjectionProblem(window), "Rank2ExactSolver")
            exact = solve_projection(
                ProjectionProblem(window, requested_certificate_level="ExactOptimal"),
                "ExhaustiveExactSolver",
            )
            self.assertEqual(result.objective.value, exact.objective.value)

    def test_structural_rejections_do_not_infer_geometry_from_rank(self):
        problem = cut_problem()
        for changes in (
            {"input_structure": "PlanarSurface", "solver_options": {}},
            {"input_structure": "EuclideanFlatTorus", "solver_options": {}},
            {"input_structure": "GraphCycle", "solver_options": {}},
            {"input_structure": "GeneralChainWindow"},
            {"matrix_free_output": True},
            {"tie_break_policy": "LexicographicProjection"},
            {"solver_options": {}},
            {
                "window": replace(
                    problem.window, weights=(1.0,) * 5, arithmetic="FloatingPoint"
                )
            },
        ):
            result = solve_projection(replace(problem, **changes), "Rank2ExactSolver")
            self.assertEqual(
                result.status, "Unavailable", (changes, result.diagnostics)
            )
            self.assertIsNone(result.projection)
        for changes in (
            {"dual_vertex_count": True},
            {"dual_vertex_count": 7},
            {"terminals": (0, 0, 1)},
            {"terminals": (True, 1, 2)},
            {"dual_edges": ((3, 0),) * 5},
            {"dual_edges": ((0, 0),) * 5},
            {"dual_edges": ((0, 1),)},
            {"terminals": (0, 1, 3)},  # Valid graph, wrong boundary subspace.
        ):
            result = solve_projection(
                replace(problem, solver_options=dict(problem.solver_options) | changes),
                "Rank2ExactSolver",
            )
            self.assertEqual(
                result.status, "Unavailable", (changes, result.diagnostics)
            )
        for n in (0, 1, 3):
            window = ChainWindow(
                0,
                Matrix.zero(0, n),
                Matrix.zero(n, 0),
                (),
                tuple(f"e{i}" for i in range(n)),
                (),
                (1,) * n,
            )
            self.assertEqual(
                solve_projection(ProjectionProblem(window), "Rank2ExactSolver").status,
                "Unavailable",
            )
        self.assertEqual(Rank2ExactSolver().solve(None).status, "InvalidProblem")

    def test_rank_three_pareto_counterexample_is_preserved_and_rejected(self):
        # Fixed PROOF T10: every nonzero linear boundary correction worsens a basis class.
        edges = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3), (0, 4), (3, 4))
        A = Matrix.from_columns(
            (tuple(int(v == a) ^ int(v == b) for v in range(5)) for a, b in edges),
            nrows=5,
        )
        boundary = (1, 1, 1, 0, 0, 0, 0, 0)
        window = ChainWindow(
            1,
            A,
            Matrix.from_columns((boundary,), nrows=8),
            tuple(f"v{i}" for i in range(5)),
            tuple(f"e{i}" for i in range(8)),
            ("ABC",),
            (1,) * 8,
        )
        labels = (1, 2, 4, 2, 3, 6, 7, 7)
        section = tuple(tuple((label >> i) & 1 for label in labels) for i in range(3))
        for functional in range(1, 8):
            changed = tuple(
                tuple(
                    a ^ (b if (functional >> i) & 1 else 0) for a, b in zip(z, boundary)
                )
                for i, z in enumerate(section)
            )
            self.assertTrue(
                any(sum(after) > sum(before) for before, after in zip(section, changed))
            )
        self.assertEqual(
            solve_projection(ProjectionProblem(window), "Rank2ExactSolver").status,
            "Unavailable",
        )

    def test_certificate_replays_reduction_minima_identity_and_witness(self):
        problem = cut_problem()
        result = solve_projection(problem, "Rank2ExactSolver")
        proof = dict(result.certificate["optimization"])
        for changes in (
            {"class_minima": (1, 1, 1)},
            {"candidate_count": 9},
            {"searched_candidates": 16},
            {"terminal_labels": (0, 1, 2, 3, 2)},
            {"structure": "GeneralChainWindow"},
            {"pareto_steps": ({"boundary": (0,) * 5, "color": 1},)},
            {"quotient_generators": ((0,) * 5,) * 2},
            {"initial_generators": ((0,) * 5,) * 2},
            {"optimality_verified": True},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                HomologyOperator(
                    problem.window,
                    replace(result, certificate={"optimization": proof | changes}),
                )
        other = solve_projection(problem, "Rank2ExactSolver")
        self.assertEqual(result.projection, other.projection)
        with self.assertRaises(ValueError):
            HomologyOperator(problem.window, replace(result, objective=other.objective))
        for details in ({}, {"witness": (0,) * 5}):
            with self.assertRaises(ValueError):
                HomologyOperator(
                    problem.window,
                    replace(
                        result, objective=replace(result.objective, details=details)
                    ),
                )
        record = HomologyOperator(problem.window, result).to_result()
        self.assertEqual(record, OperatorResult.from_json(record.to_json()))
        data = record.to_dict()
        data["certificate"]["optimization"]["searched_candidates"] = 10
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(data)

    def test_resources_preserve_proven_seed_and_completed_objective(self):
        problem = cut_problem()
        complete = solve_projection(problem, "Rank2ExactSolver")
        states = complete.resource_usage["states"]
        saw_no_bound, saw_bound = False, False
        for count in range(states):
            result = solve_projection(
                replace(problem, resource_limits=ResourceLimits(state_limit=count)),
                "Rank2ExactSolver",
            )
            self.assertEqual(result.status, "ResourceExhausted", result.diagnostics)
            self.assertNotEqual(result.certificate_level, "ExactOptimal")
            if result.projection is None:
                continue
            record = HomologyOperator(problem.window, result).to_result()
            self.assertEqual(record, OperatorResult.from_json(record.to_json()))
            if result.upper_bound is None:
                saw_no_bound = True
                self.assertEqual(result.certificate_level, "Feasible")
            else:
                saw_bound = True
                self.assertEqual(result.lower_bound, 0)
                self.assertGreaterEqual(result.upper_bound, complete.objective.value)
                self.assertEqual(
                    result.certificate["optimization"]["kind"], "CycleBounds"
                )
        self.assertTrue(saw_no_bound and saw_bound)
        for limits in (
            ResourceLimits(wall_time_limit=0),
            ResourceLimits(matrix_entry_limit=0),
        ):
            result = solve_projection(
                replace(problem, resource_limits=limits), "Rank2ExactSolver"
            )
            self.assertEqual(result.status, "ResourceExhausted")
            self.assertIsNone(result.projection)

    def test_nonempty_pareto_transcript_is_independently_verified(self):
        window = ChainWindow(
            2,
            Matrix.zero(0, 3),
            Matrix.from_columns(((1, 1, 1),), nrows=3),
            (),
            ("x", "y", "z"),
            ("b",),
            (1, 1, 3),
        )
        result = solve_projection(ProjectionProblem(window), "Rank2ExactSolver")
        proof = dict(result.certificate["optimization"]) | {
            "initial_generators": ((0, 1, 1), (1, 0, 1)),
            "pareto_steps": ({"boundary": (1, 1, 1), "color": 3},),
        }
        HomologyOperator(window, replace(result, certificate={"optimization": proof}))
        for step in (
            {"boundary": (1, 1, 1), "color": 1},
            {"boundary": (0, 0, 0), "color": 3},
            {"boundary": (1, 0, 0), "color": 3},
            {"boundary": (1, 1, 1), "color": True},
            {"boundary": (1, 1, 1), "color": 3, "verified": True},
        ):
            with self.subTest(step=step), self.assertRaises(ValueError):
                HomologyOperator(
                    window,
                    replace(
                        result,
                        certificate={"optimization": proof | {"pareto_steps": (step,)}},
                    ),
                )


if __name__ == "__main__":
    unittest.main()
