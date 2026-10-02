from itertools import product
from dataclasses import replace
from fractions import Fraction
import unittest

from homology_operator.algebra import Matrix
from homology_operator.chain import ChainWindow
from homology_operator.operator import HomologyOperator
from homology_operator.family import OperatorFamily, OperatorFamilyResult
from homology_operator.result import OperatorResult, QueryResult
from homology_operator.solver import (
    FeasibleSolver,
    ProjectionProblem,
    ResourceLimits,
    generalized_inverse,
    check_solver_request,
    solve_projection,
)
from homology_operator.validation import ValidationError


class SolverTests(unittest.TestCase):
    def window(self):
        return ChainWindow(
            1,
            Matrix.from_rows(((1, 1, 0),)),
            Matrix.from_rows(((1,), (1,), (0,))),
            ("v",),
            ("a", "b", "c"),
            ("f",),
            (1, 2, 3),
        )

    def test_generalized_inverses_all_small_shapes(self):
        for m, n in product(range(4), repeat=2):
            for bits in product((0, 1), repeat=m * n):
                M = Matrix(
                    m, n, tuple(tuple(bits[r * n : (r + 1) * n]) for r in range(m))
                )
                G = generalized_inverse(M)
                self.assertEqual((G.nrows, G.ncols), (n, m))
                self.assertEqual(M @ G @ M, M)

    def test_construction_and_determinism(self):
        window = self.window()
        solver = FeasibleSolver()
        first, second = (solver.solve(ProjectionProblem(window)) for _ in range(2))
        self.assertEqual(first.status, "FeasibleOnly")
        self.assertEqual(first.certificate_level, "Feasible")
        self.assertEqual(first.objective.state, "NotComputed")
        self.assertEqual(first.solver_metadata()["arithmetic_policy"], "ExactRational")
        self.assertEqual(first.resource_usage["limits"]["state_limit"], 100_000)
        self.assertEqual(first.projection, second.projection)
        self.assertEqual(
            first.identity["projection_id"], second.identity["projection_id"]
        )
        self.assertNotEqual(first.solver_run_id, second.solver_run_id)
        identity_matrix = Matrix.identity(window.n)
        self.assertEqual(
            first.projection,
            (identity_matrix + window.D @ first.generalized_inverse_d)
            @ (identity_matrix + first.generalized_inverse_a @ window.A),
        )
        self.assertEqual(first.projection.rows, ((0, 0, 0), (0, 0, 0), (0, 0, 1)))
        for z in product((0, 1), repeat=window.n):
            if window.A.apply(z) == (0,):
                Pz = first.projection.apply(z)
                self.assertIsNotNone(
                    window.D.solve(tuple(a ^ b for a, b in zip(z, Pz)))
                )

    def test_empty_shapes(self):
        for A, D in (
            (Matrix.zero(0, 0), Matrix.zero(0, 0)),
            (Matrix.zero(0, 2), Matrix.zero(2, 0)),
            (Matrix.zero(2, 0), Matrix.zero(0, 3)),
        ):
            window = ChainWindow(
                0,
                A,
                D,
                tuple(f"a{i}" for i in range(A.nrows)),
                tuple(f"c{i}" for i in range(A.ncols)),
                tuple(f"d{i}" for i in range(D.ncols)),
                (1,) * A.ncols,
            )
            solution = FeasibleSolver().solve(ProjectionProblem(window))
            self.assertEqual(solution.status, "FeasibleOnly")
            self.assertEqual(solution.projection, Matrix.identity(window.n))

    def test_failures_and_resource_limits_are_structured(self):
        solver = FeasibleSolver()
        self.assertEqual(solver.solve(None).status, "InvalidProblem")
        self.assertEqual(solver.solve(ProjectionProblem(None)).status, "InvalidProblem")
        for options in (
            {"requested_certificate_level": "ExactOptimal"},
            {"objective": "Other"},
            {"tie_break_policy": "Other"},
        ):
            self.assertEqual(
                solver.solve(ProjectionProblem(self.window(), **options)).status,
                "Unavailable",
            )
        for options in (
            {"state_limit": 0},
            {"wall_time_limit": 0},
            {"matrix_entry_limit": 0},
        ):
            solution = solver.solve(
                ProjectionProblem(self.window(), ResourceLimits(**options))
            )
            self.assertEqual(solution.status, "ResourceExhausted")
            self.assertIsNone(solution.projection)
            self.assertEqual(solution.objective.state, "NotComputed")
        for options in (
            {"state_limit": -1},
            {"state_limit": True},
            {"wall_time_limit": float("nan")},
        ):
            with self.assertRaises(ValueError):
                ResourceLimits(**options)

    def test_preflight_capabilities_and_no_fallback(self):
        problem = ProjectionProblem(self.window())
        caps = dict(FeasibleSolver().capabilities())
        self.assertIsNone(check_solver_request(problem, caps))
        for changes in (
            {"arithmetic_policy": "MixedCertified"},
            {"arithmetic_policy": "ExactInteger"},
            {"input_structure": "PlanarSurface"},
            {"matrix_free_output": True},
            {"solver_options": {"hidden_fallback": True}},
        ):
            self.assertEqual(
                solve_projection(replace(problem, **changes)).status, "Unavailable"
            )
        for changes in (
            {"matrix_free_output": 1},
            {"deterministic": "yes"},
            {"solver_options": []},
        ):
            self.assertEqual(
                solve_projection(replace(problem, **changes)).status, "InvalidProblem"
            )
        self.assertEqual(solve_projection(problem, "unknown").status, "Unavailable")
        for key, value in (
            ("supported_dimensions", (0,)),
            ("supported_betti_range", (2, 2)),
            ("deterministic", False),
            ("resource_limits", ()),
        ):
            with self.subTest(key=key):
                self.assertEqual(
                    check_solver_request(problem, caps | {key: value})[0], "Unavailable"
                )

    def test_config_identity_is_immutable_and_run_independent(self):
        problem = ProjectionProblem(self.window())
        first, second = (solve_projection(problem) for _ in range(2))
        self.assertEqual(first.solver_config_id, second.solver_config_id)
        self.assertNotEqual(first.solver_run_id, second.solver_run_id)
        changed = solve_projection(
            replace(problem, resource_limits=ResourceLimits(state_limit=1000))
        )
        self.assertNotEqual(first.solver_config_id, changed.solver_config_id)
        with self.assertRaises(TypeError):
            first.solver_config["resource_limits"]["state_limit"] = 0
        record = HomologyOperator(problem.window, first).to_result()
        self.assertEqual(record.solver["solver_config_id"], first.solver_config_id)
        data = record.to_dict()
        data["solver"]["solver_config_id"] = "wrong"
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(data)
        failure = solve_projection(
            replace(problem, resource_limits=ResourceLimits(state_limit=0))
        )
        record = OperatorResult(
            None,
            problem.window,
            None,
            failure.solver_metadata(),
            {},
            {},
            "ResourceExhausted",
        )
        self.assertEqual(record, OperatorResult.from_json(record.to_json()))
        data = record.to_dict()
        data["solver"]["solver_config_id"] = "wrong"
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(data)

    def test_backend_claims_cannot_become_verified_certificate_flags(self):
        window, base = self.bound_solution()
        base = FeasibleSolver().solve(ProjectionProblem(window))
        forged = {
            "optimality_verified": True,
            "bounds_verified": True,
            "objective_replayed": True,
            "p_idempotent": False,
            "optimization": {"kind": "ForgedExactSearch"},
            "unrecognized_verified": True,
        }
        for level in ("Feasible", "Heuristic"):
            op = HomologyOperator(
                window, replace(base, certificate_level=level, certificate=forged)
            )
            certificate = op.certificate()
            self.assertTrue(certificate["p_idempotent"])
            for key in ("optimality_verified", "bounds_verified", "objective_replayed"):
                self.assertIs(certificate[key], False)
            self.assertNotIn("optimization", certificate)
            self.assertNotIn("unrecognized_verified", certificate)
            self.assertEqual(certificate["solver_evidence"], forged)
            self.assertEqual(op.stretch().value, 10)
            record = op.to_result()
            for _ in range(3):
                record = OperatorResult.from_json(record.to_json())
                self.assertEqual(record.certificate, certificate)
            tampered = record.to_dict()
            tampered["certificate"].update(forged)
            restored = OperatorResult.from_dict(tampered)
            self.assertEqual(restored.certificate, certificate)
            family = OperatorFamily((0,), (window,), (op,))
            snapshot = family.to_result()
            restored_family = OperatorFamilyResult.from_json(
                snapshot.to_json()
            ).to_family()
            self.assertEqual(restored_family.operators[0].certificate(), certificate)
            self.assertEqual(restored_family.to_result().to_json(), snapshot.to_json())

    def test_dispatch_binds_returned_configuration_to_request(self):
        problem = ProjectionProblem(self.window())
        original = FeasibleSolver().solve(problem)

        class CachedBackend:
            result = original

            def capabilities(self):
                return dict(FeasibleSolver().capabilities()) | {
                    "tie_break_policies": (
                        "StableBasisOrder",
                        "LexicographicProjection",
                    )
                }

            def solve(self, problem):
                return self.result

        backend = CachedBackend()
        self.assertEqual(solve_projection(problem, backend).status, "FeasibleOnly")
        for request in (
            replace(problem, tie_break_policy="LexicographicProjection"),
            replace(problem, resource_limits=ResourceLimits(state_limit=0)),
            replace(problem, deterministic=False),
        ):
            with self.subTest(request=request):
                failed = solve_projection(request, backend)
                self.assertEqual(failed.status, "InternalError")
                self.assertIsNone(failed.projection)
        backend.result = replace(original, solver_config=None)
        self.assertEqual(solve_projection(problem, backend).status, "InternalError")
        # A matching configuration cannot disguise mismatching actual policy metadata.
        backend.result = replace(original, tie_break_policy="LexicographicProjection")
        self.assertEqual(solve_projection(problem, backend).status, "InternalError")
        backend.result = replace(
            original, resource_usage={"limits": {"state_limit": 0}}
        )
        self.assertEqual(solve_projection(problem, backend).status, "InternalError")

    def bound_solution(
        self, weights=(10, 1), level="CertifiedInterval", status="ResourceExhausted"
    ):
        window = ChainWindow(
            0,
            Matrix.zero(0, 2),
            Matrix.from_columns(((1, 1),), nrows=2),
            (),
            ("a", "b"),
            ("f",),
            weights,
        )
        base = FeasibleSolver().solve(ProjectionProblem(window))
        value = Fraction(weights[0]) / min(map(Fraction, weights))
        return window, replace(
            base,
            status=status,
            certificate_level=level,
            objective=QueryResult("Computed", value, base.identity, True),
            lower_bound=Fraction(1) if level != "CertifiedUpperBound" else None,
            upper_bound=value,
            certificate={
                "optimization": {
                    "kind": "CycleBounds",
                    "nonzero_cycles": 3,
                    "lower_bound_method": "UniversalHomology",
                }
            },
            diagnostics=("state_limit",) if status == "ResourceExhausted" else (),
        )

    def test_interrupted_best_feasible_interval_roundtrip_and_family(self):
        window, solution = self.bound_solution()
        op = HomologyOperator(window, solution)
        self.assertEqual(solution.optimality_gap, {"absolute": 9, "relative": 9})
        self.assertEqual(op.selected_mass((0, 1)), 10)
        record = op.to_result()
        self.assertEqual(record.status, "Ready")
        self.assertEqual(record.solver["status"], "ResourceExhausted")
        self.assertEqual(record, OperatorResult.from_json(record.to_json()))
        family = OperatorFamily((0,), (window,), (op,))
        restored = OperatorFamilyResult.from_json(
            family.to_result().to_json()
        ).to_family()
        self.assertEqual(restored.operators[0].solution.lower_bound, 1)
        self.assertEqual(
            restored.operators[0].solution.solver_config_id, solution.solver_config_id
        )
        self.assertEqual(restored.to_result().to_json(), family.to_result().to_json())

    def test_supported_grades_require_independent_evidence(self):
        window, solution = self.bound_solution(
            level="CertifiedUpperBound", status="Solved"
        )
        self.assertTrue(
            HomologyOperator(window, solution).certificate()["bounds_verified"]
        )
        optimal_window, optimal = self.bound_solution(
            weights=(1, 1), level="ExactOptimal", status="Solved"
        )
        self.assertTrue(
            HomologyOperator(optimal_window, optimal).certificate()[
                "optimality_verified"
            ]
        )
        heuristic = replace(
            solution,
            certificate_level="Heuristic",
            lower_bound=None,
            upper_bound=None,
            objective=QueryResult("NotComputed", identity=solution.identity),
            certificate={},
        )
        self.assertEqual(HomologyOperator(window, heuristic).betti(), 1)
        with self.assertRaises(ValidationError):
            HomologyOperator(window, replace(heuristic, projection=Matrix.zero(2, 2)))
        for changes in (
            {"certificate": {"optimization": {"kind": "dummy"}}},
            {"upper_bound": 2},
            {"lower_bound": 11},
            {"certificate_level": "ExactOptimal", "lower_bound": 10},
            {"objective": QueryResult("Computed", 0, solution.identity, True)},
            {"upper_bound": 10.0},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                HomologyOperator(window, replace(solution, **changes))
        with self.assertRaises(ValueError):
            HomologyOperator(
                optimal_window, replace(optimal, certificate_level="CertifiedInterval")
            )
        data = HomologyOperator(optimal_window, optimal).to_result().to_dict()
        data["solver"]["optimality_gap"]["absolute"] = 1
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(data)
        data = HomologyOperator(optimal_window, optimal).to_result().to_dict()
        data["solver"]["optimality_gap"]["absolute"] = False
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(data)

    def test_exact_zero_and_empty_objective_remain_distinct(self):
        for n in (0, 2):
            window = ChainWindow(
                0,
                Matrix.zero(0, n),
                Matrix.identity(n),
                (),
                tuple(f"c{i}" for i in range(n)),
                tuple(f"b{i}" for i in range(n)),
                (1,) * n,
            )
            base = FeasibleSolver().solve(ProjectionProblem(window))
            state = "EmptyDomain" if n == 0 else "Computed"
            solution = replace(
                base,
                status="Solved",
                certificate_level="ExactOptimal",
                lower_bound=0,
                upper_bound=0,
                objective=QueryResult(state, 0, base.identity, True),
                certificate={
                    "optimization": {
                        "kind": "CycleBounds",
                        "nonzero_cycles": (1 << n) - 1,
                        "lower_bound_method": "UniversalHomology",
                    }
                },
            )
            op = HomologyOperator(window, solution)
            record = OperatorResult.from_json(op.to_result().to_json())
            self.assertEqual(record.solver["objective"]["state"], state)
            self.assertEqual(solution.optimality_gap, {"absolute": 0, "relative": None})

    def test_validated_heuristic_changes_geometry_with_same_topology(self):
        from homology_operator.result import make_identity

        window, solution = self.bound_solution()
        first = HomologyOperator(window, solution)
        projection = Matrix.from_rows(((0, 0), (1, 1)))
        identity = make_identity(window, projection, "heuristic-run")
        alternative = replace(
            solution,
            status="Solved",
            certificate_level="Heuristic",
            projection=projection,
            solver_run_id="heuristic-run",
            identity=identity,
            lower_bound=None,
            upper_bound=None,
            certificate={},
            objective=QueryResult("NotComputed", identity=identity),
            solver_config=None,
            method="ValidatedCandidate",
        )
        second = HomologyOperator(window, alternative)
        self.assertEqual(first.betti(), second.betti())
        self.assertEqual(
            first.same_class((1, 0), (0, 1)), second.same_class((1, 0), (0, 1))
        )
        self.assertEqual(
            (first.selected_mass((1, 0)), second.selected_mass((1, 0))), (10, 1)
        )
        self.assertNotEqual(
            first.identity["projection_id"], second.identity["projection_id"]
        )
        for op in (first, second):
            self.assertEqual(
                op.to_result(), OperatorResult.from_json(op.to_result().to_json())
            )

    def test_float_equality_cannot_certify_exact_optimality(self):
        window, solution = self.bound_solution(
            weights=(1, 1), level="ExactOptimal", status="Solved"
        )
        window = replace(window, weights=(1.0, 1.0), arithmetic="FloatingPoint")
        from homology_operator.result import make_identity

        identity = make_identity(window, solution.projection, solution.solver_run_id)
        solution = replace(
            solution,
            identity=identity,
            arithmetic_policy="FloatingPoint",
            solver_config=None,
            objective=QueryResult("Computed", 1.0, identity, False),
        )
        for exact in (False, True):
            with self.assertRaises(ValueError):
                HomologyOperator(
                    window,
                    replace(
                        solution,
                        objective=QueryResult("Computed", 1.0, identity, exact),
                    ),
                )

    def test_dispatch_rejects_invalid_backend_candidates(self):
        problem = ProjectionProblem(self.window())
        base = FeasibleSolver().solve(problem)

        class CandidateBackend:
            def capabilities(self):
                return FeasibleSolver().capabilities()

            def solve(self, problem):
                return replace(
                    base,
                    projection=Matrix.zero(3, 3),
                    certificate={"cycle_homology_preservation": True},
                )

        failed = solve_projection(problem, CandidateBackend())
        self.assertEqual(failed.status, "InternalError")
        self.assertIsNone(failed.projection)


if __name__ == "__main__":
    unittest.main()
