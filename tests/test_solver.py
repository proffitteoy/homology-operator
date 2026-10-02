from itertools import product
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from homology_operator.algebra import Matrix
from homology_operator.chain import ChainWindow
from homology_operator.operator import HomologyOperator
from homology_operator.family import OperatorFamily, OperatorFamilyResult
from homology_operator.result import OperatorResult, QueryResult
from homology_operator.solver import (
    FeasibleSolver,
    ExhaustiveExactSolver,
    GreedyCertifiedSolver,
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

    def test_dispatch_failures_keep_actual_backend_method(self):
        problem = ProjectionProblem(self.window())
        for method in (
            "FeasibleSolver",
            "ExhaustiveExactSolver",
            "GreedyCertifiedSolver",
            "Rank2ExactSolver",
            "StructuredFamilySolver",
            "GeneralSearchSolver",
        ):
            failed = solve_projection(
                replace(problem, arithmetic_policy="MixedCertified"), method
            )
            self.assertEqual(failed.status, "Unavailable")
            self.assertEqual(failed.method, method)
            self.assertIsNone(failed.projection)
        self.assertEqual(solve_projection(problem, object()).method, "object")

        class BrokenBackend:
            def capabilities(self):
                return FeasibleSolver().capabilities()

            def solve(self, problem):
                raise RuntimeError("backend failure")

        failed = solve_projection(problem, BrokenBackend())
        self.assertEqual(
            (failed.status, failed.method), ("InternalError", "BrokenBackend")
        )

        class Wrapper(BrokenBackend):
            def solve(self, problem):
                return FeasibleSolver().solve(problem)

        self.assertEqual(solve_projection(problem, Wrapper()).method, "FeasibleSolver")

    def test_cross_solver_exact_arithmetic_and_float_scope(self):
        window = ChainWindow(
            0,
            Matrix.zero(0, 3),
            Matrix.from_columns(((1, 1, 1),), nrows=3),
            (),
            ("x", "y", "z"),
            ("b",),
            (1, 1, 1),
        )
        methods = (
            "FeasibleSolver",
            "ExhaustiveExactSolver",
            "GreedyCertifiedSolver",
            "Rank2ExactSolver",
            "StructuredFamilySolver",
        )
        for method in methods:
            structure = (
                "CyclicTrace"
                if method == "StructuredFamilySolver"
                else "GeneralChainWindow"
            )
            for arithmetic, weight in (
                ("ExactInteger", 2**60 + 1),
                ("ExactRational", Fraction(2**60 + 1, 7)),
            ):
                exact_window = replace(
                    window, weights=(weight,) * 3, arithmetic=arithmetic
                )
                solution = solve_projection(
                    ProjectionProblem(exact_window, input_structure=structure), method
                )
                op = HomologyOperator(exact_window, solution)
                objective = op.stretch()
                self.assertEqual(objective.value, 2)
                self.assertIs(type(objective.value), Fraction)
                self.assertIs(objective.exact, True)
                self.assertEqual(
                    op.selected_mass((1, 0, 0)),
                    sum(
                        w
                        for w, bit in zip(exact_window.weights, op.project((1, 0, 0)))
                        if bit
                    ),
                )
                self.assertEqual(
                    op.to_result(), OperatorResult.from_json(op.to_result().to_json())
                )
            float_window = replace(
                window, weights=(1.0,) * 3, arithmetic="FloatingPoint"
            )
            problem = ProjectionProblem(float_window, input_structure=structure)
            floating = solve_projection(problem, method)
            if method == "FeasibleSolver":
                op = HomologyOperator(float_window, floating)
                objective = op.stretch()
                self.assertIs(objective.exact, False)
                self.assertIsNone(objective.details["tolerance"])
                self.assertIn("nearest-even", objective.details["rounding_policy"])
                self.assertIsNone(floating.upper_bound)
                self.assertNotIn("upper_bound", objective.details)
            else:
                self.assertEqual(floating.status, "Unavailable")
            self.assertEqual(
                solve_projection(
                    replace(problem, arithmetic_policy="MixedCertified"), method
                ).status,
                "Unavailable",
            )
        with self.assertRaises(ValueError):
            replace(window, arithmetic="MixedCertified")

    def test_cross_solver_positive_wall_limits_at_checkpoints(self):
        window = ChainWindow(
            0,
            Matrix.zero(0, 3),
            Matrix.from_columns(((1, 1, 1),), nrows=3),
            (),
            ("x", "y", "z"),
            ("b",),
            (1, 1, 1),
        )
        for method in (
            "FeasibleSolver",
            "ExhaustiveExactSolver",
            "GreedyCertifiedSolver",
            "Rank2ExactSolver",
            "StructuredFamilySolver",
        ):
            problem = ProjectionProblem(
                window,
                input_structure="CyclicTrace"
                if method == "StructuredFamilySolver"
                else "GeneralChainWindow",
            )
            # Every clock read advances one second, without real sleeps or races.
            with patch(
                "homology_operator.solver.perf_counter", side_effect=range(10000)
            ) as clock:
                complete = solve_projection(
                    replace(
                        problem, resource_limits=ResourceLimits(wall_time_limit=10000)
                    ),
                    method,
                )
                calls = clock.call_count
            self.assertIn(complete.status, {"Solved", "FeasibleOnly"})
            saw_seed, saw_bound = False, False
            for seconds in range(1, calls + 1):
                with patch(
                    "homology_operator.solver.perf_counter", side_effect=range(10000)
                ):
                    solution = solve_projection(
                        replace(
                            problem,
                            resource_limits=ResourceLimits(wall_time_limit=seconds),
                        ),
                        method,
                    )
                if solution.status != "ResourceExhausted":
                    continue
                self.assertEqual(solution.diagnostics, ("wall_time_limit",))
                if solution.projection is None:
                    self.assertIsNone(solution.certificate_level)
                    with self.assertRaises(ValueError):
                        HomologyOperator(window, solution)
                    continue
                saw_seed = True
                record = HomologyOperator(window, solution).to_result()
                self.assertEqual(record.status, "Ready")
                self.assertEqual(record, OperatorResult.from_json(record.to_json()))
                if solution.upper_bound is not None:
                    saw_bound = True
                    self.assertEqual(solution.certificate_level, "CertifiedInterval")
                    self.assertLessEqual(solution.lower_bound, 2)
                    self.assertGreaterEqual(solution.upper_bound, 2)
                    self.assertEqual(
                        solution.optimality_gap["absolute"],
                        solution.upper_bound - solution.lower_bound,
                    )
            if method in {
                "ExhaustiveExactSolver",
                "GreedyCertifiedSolver",
                "Rank2ExactSolver",
            }:
                self.assertTrue(saw_seed and saw_bound, method)

    def test_resource_fields_reject_unimplemented_limits(self):
        for name in (
            "memory_limit",
            "node_limit",
            "iteration_limit",
            "output_size_limit",
        ):
            with self.subTest(name=name), self.assertRaises(TypeError):
                ResourceLimits(**{name: 1})

    def test_solver_policy_and_geometry_cache_boundaries(self):
        problem = ProjectionProblem(self.window())
        first, second = (
            solve_projection(problem, "ExhaustiveExactSolver") for _ in range(2)
        )
        records = [
            HomologyOperator(problem.window, s).to_result() for s in (first, second)
        ]
        key = records[0].cache_key(
            first.solver_config_id, first.tie_break_policy, "reference-v1"
        )
        self.assertEqual(
            key,
            records[1].cache_key(
                second.solver_config_id, second.tie_break_policy, "reference-v1"
            ),
        )
        for changes in (
            {"tie_break_policy": "LexicographicProjection"},
            {"resource_limits": ResourceLimits(state_limit=99999)},
        ):
            changed = solve_projection(
                replace(problem, **changes), "ExhaustiveExactSolver"
            )
            self.assertEqual(first.projection, changed.projection)
            record = HomologyOperator(problem.window, changed).to_result()
            self.assertNotEqual(
                key,
                record.cache_key(
                    changed.solver_config_id, changed.tie_break_policy, "reference-v1"
                ),
            )
        window, feasible = self.bound_solution()
        optimal = solve_projection(ProjectionProblem(window), "ExhaustiveExactSolver")
        ops = tuple(HomologyOperator(window, s) for s in (feasible, optimal))
        self.assertEqual([op.betti() for op in ops], [1, 1])
        self.assertEqual([op.support((1, 0)) for op in ops], [(0,), (1,)])
        self.assertEqual([op.selected_mass((1, 0)) for op in ops], [10, 1])
        queried = [op.readout("selected_mass", (1, 0)) for op in ops]
        self.assertNotEqual(
            ops[0].to_result().cache_key("solver-v1", "stable", "reference-v1"),
            ops[1].to_result().cache_key("solver-v1", "stable", "reference-v1"),
        )
        data = ops[0].to_result().to_dict()
        data["query_results"]["selected_mass"] = queried[1].to_dict()
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(data)

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

        window, certified = self.bound_solution(level="CertifiedUpperBound")
        for extra in ({"optimality_verified": True}, {"lower_bound_method": "Forged"}):
            proof = dict(certified.certificate["optimization"]) | extra
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                HomologyOperator(
                    window, replace(certified, certificate={"optimization": proof})
                )
            tampered = HomologyOperator(window, certified).to_result().to_dict()
            tampered["certificate"]["optimization"].update(extra)
            with self.assertRaises(ValidationError):
                OperatorResult.from_dict(tampered)

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

    def test_exhaustive_matches_all_small_ambient_projections(self):
        def apply(columns, x):
            value = 0
            for j, column in enumerate(columns):
                if x >> j & 1:
                    value ^= column
            return value

        for n in range(1, 4):
            for a, b in product(range(1 << n), repeat=2):
                if (a & b).bit_count() % 2:
                    continue
                weights = tuple(Fraction(j + 1, 2) for j in range(n))

                def mass(x):
                    return sum(w for j, w in enumerate(weights) if x >> j & 1)

                cycles = tuple(x for x in range(1 << n) if (a & x).bit_count() % 2 == 0)
                optimum = None
                for encoded in range(1 << (n * n)):
                    columns = tuple(
                        (encoded >> (n * j)) & ((1 << n) - 1) for j in range(n)
                    )
                    if (
                        any(apply(columns, z) != z for z in columns)
                        or any((a & z).bit_count() % 2 for z in columns)
                        or apply(columns, b)
                    ):
                        continue
                    if any(z ^ apply(columns, z) not in {0, b} for z in cycles):
                        continue
                    value = max(
                        (mass(apply(columns, z)) / mass(z) for z in cycles if z),
                        default=Fraction(0),
                    )
                    optimum = value if optimum is None else min(optimum, value)
                window = ChainWindow(
                    1,
                    Matrix.from_rows((tuple((a >> j) & 1 for j in range(n)),)),
                    Matrix.from_columns(
                        (tuple((b >> j) & 1 for j in range(n)),), nrows=n
                    ),
                    ("v",),
                    tuple(f"c{j}" for j in range(n)),
                    ("f",),
                    weights,
                )
                solution = solve_projection(
                    ProjectionProblem(
                        window, requested_certificate_level="ExactOptimal"
                    ),
                    "ExhaustiveExactSolver",
                )
                self.assertEqual(
                    solution.status, "Solved", (n, a, b, solution.diagnostics)
                )
                self.assertEqual(solution.objective.value, optimum)
                self.assertEqual(solution.lower_bound, optimum)
                op = HomologyOperator(window, solution)
                record = op.to_result()
                self.assertEqual(record, OperatorResult.from_json(record.to_json()))

    def test_exhaustive_weighted_and_higher_rank_ground_truth(self):
        # Hand-derived simplex boundary quotient: unit weights give optimum beta.
        for k, n, weights, expected in (
            (0, 2, (10, 1), 1),
            (1, 3, (1, 1, 1), 2),
            (2, 4, (1, 1, 1, 1), 3),
            (3, 4, (4, 1, 1, 1), 1),
        ):
            window = ChainWindow(
                k,
                Matrix.zero(0, n),
                Matrix.from_columns(((1,) * n,), nrows=n),
                (),
                tuple(f"c{i}" for i in range(n)),
                ("b",),
                weights,
            )
            problem = ProjectionProblem(
                window,
                requested_certificate_level="ExactOptimal",
                tie_break_policy="LexicographicProjection",
            )
            first, second = (ExhaustiveExactSolver().solve(problem) for _ in range(2))
            self.assertEqual(first.objective.value, expected)
            self.assertEqual(first.resource_usage["candidates_visited"], 1 << (n - 1))
            self.assertEqual(first.projection, second.projection)
            self.assertEqual(first.solver_config_id, second.solver_config_id)
            op = HomologyOperator(window, first)
            record = op.to_result()
            self.assertEqual(record, OperatorResult.from_json(record.to_json()))
            bad = record.to_dict()
            bad["certificate"]["optimization"]["candidate_count"] = 1
            with self.assertRaises(ValueError):
                OperatorResult.from_dict(bad)
            bad = record.to_dict()
            bad["solver"]["objective"]["details"]["witness"] = [0] * n
            with self.assertRaises(ValueError):
                OperatorResult.from_dict(bad)
            if n == 3:
                from homology_operator.result import make_identity

                alternate = Matrix.from_columns(
                    ((0, 1, 1), (0, 1, 0), (0, 0, 1)), nrows=3
                )
                identity = make_identity(
                    window, alternate, first.solver_run_id, first.tie_break_policy
                )
                noncanonical = replace(
                    first,
                    projection=alternate,
                    identity=identity,
                    objective=QueryResult(
                        "Computed", 2, identity, True, {"witness": (1, 0, 0)}
                    ),
                )
                with self.assertRaises(ValidationError):
                    HomologyOperator(window, noncanonical)

    def test_frozen_solver_corpus_and_exact_family_roundtrips(self):
        from test_joint import oracle, window as fixture_window

        regression = json.loads(
            (Path(__file__).parent / "fixtures" / "solver_reference.json").read_text(
                encoding="utf-8"
            )
        )
        fixtures = {item["id"]: item for item in oracle.load_fixtures()}
        self.assertEqual(
            {item["fixture_id"] for item in regression["fixtures"]}, set(fixtures)
        )
        for expected in regression["fixtures"]:
            fixture = fixtures[expected["fixture_id"]]
            self.assertEqual(fixture["input_hash"], expected["input_hash"])
            window = fixture_window(fixture)
            solution = solve_projection(
                ProjectionProblem(window, requested_certificate_level="ExactOptimal"),
                "ExhaustiveExactSolver",
            )
            self.assertEqual(
                solution.status,
                expected["expected_status"],
                (fixture["id"], solution.diagnostics),
            )
            if solution.status == "Unavailable":
                self.assertIsNone(solution.projection)
                continue
            value = expected["expected_optimum"]
            self.assertEqual(
                solution.objective.value,
                Fraction(value["numerator"], value["denominator"]),
            )
            self.assertEqual(
                solution.resource_usage["candidates_visited"],
                expected["expected_candidates"],
            )
            self.assertEqual(
                solution.resource_usage["nonzero_cycle_inputs"],
                expected["expected_nonzero_cycles"],
            )
            op = HomologyOperator(window, solution)
            snapshot = OperatorFamily((0,), (window,), (op,)).to_result()
            restored = OperatorFamilyResult.from_json(snapshot.to_json()).to_family()
            self.assertEqual(snapshot.to_json(), restored.to_result().to_json())

    def test_exhaustive_interruption_preserves_only_proven_bounds(self):
        window, _ = self.bound_solution()
        constructor = FeasibleSolver().solve(ProjectionProblem(window))
        limit = constructor.resource_usage["states"] + 4
        for state_limit in (0, limit - 1, limit):
            solution = solve_projection(
                ProjectionProblem(
                    window,
                    ResourceLimits(state_limit=state_limit),
                    requested_certificate_level="ExactOptimal",
                    tie_break_policy="LexicographicProjection",
                ),
                "ExhaustiveExactSolver",
            )
            self.assertEqual(solution.status, "ResourceExhausted", solution.diagnostics)
            self.assertNotEqual(solution.certificate_level, "ExactOptimal")
            if solution.projection is not None:
                op = HomologyOperator(window, solution)
                self.assertEqual(
                    op.to_result(), OperatorResult.from_json(op.to_result().to_json())
                )
            if state_limit == limit:
                self.assertEqual(solution.certificate_level, "CertifiedInterval")
                self.assertEqual((solution.lower_bound, solution.upper_bound), (0, 10))
        floating = replace(window, weights=(10.0, 1.0), arithmetic="FloatingPoint")
        self.assertEqual(
            ExhaustiveExactSolver().solve(ProjectionProblem(floating)).status,
            "Unavailable",
        )
        for limits in (
            ResourceLimits(wall_time_limit=0),
            ResourceLimits(matrix_entry_limit=0),
        ):
            failed = solve_projection(
                ProjectionProblem(
                    window,
                    limits,
                    requested_certificate_level="ExactOptimal",
                    tie_break_policy="LexicographicProjection",
                ),
                "ExhaustiveExactSolver",
            )
            self.assertEqual(failed.status, "ResourceExhausted")
            self.assertIsNone(failed.projection)
        for n, boundary_columns in (
            (9, ((1,) * 4 + (0,) * 5, (0,) * 4 + (1,) * 5)),
            (17, ()),
        ):
            large = ChainWindow(
                0,
                Matrix.zero(0, n),
                Matrix.from_columns(boundary_columns, nrows=n),
                (),
                tuple(f"c{i}" for i in range(n)),
                tuple(f"b{i}" for i in range(len(boundary_columns))),
                (1,) * n,
            )
            failed = solve_projection(
                ProjectionProblem(large, requested_certificate_level="ExactOptimal"),
                "ExhaustiveExactSolver",
            )
            self.assertEqual(failed.status, "ResourceExhausted", failed.diagnostics)
            self.assertEqual(failed.diagnostics, ("certificate_replay_state_limit",))
            self.assertNotEqual(failed.certificate_level, "ExactOptimal")
            HomologyOperator(large, failed).to_result()

    def test_greedy_sourced_corpus_optimum_bound_and_queried_roundtrip(self):
        from test_joint import oracle, window as fixture_window

        fixtures = {f["id"]: f for f in oracle.load_fixtures()}
        corpus = json.loads(
            (Path(__file__).parent / "fixtures/solver_reference.json").read_text(
                encoding="utf-8"
            )
        )
        for expected in corpus["fixtures"]:
            fixture = fixtures[expected["fixture_id"]]
            self.assertEqual(fixture["input_hash"], expected["input_hash"])
            window = fixture_window(fixture)
            solution = solve_projection(
                ProjectionProblem(
                    window, requested_certificate_level="CertifiedInterval"
                ),
                "GreedyCertifiedSolver",
            )
            self.assertEqual(
                solution.status, expected["expected_status"], solution.diagnostics
            )
            if solution.status == "Unavailable":
                self.assertIsNone(solution.projection)
                continue
            result = expected["greedy"]
            value = result["objective"]
            self.assertEqual(
                solution.objective.value,
                Fraction(value["numerator"], value["denominator"]),
            )
            optimum = expected["expected_optimum"]
            self.assertLessEqual(
                Fraction(optimum["numerator"], optimum["denominator"]),
                solution.objective.value,
            )
            self.assertLessEqual(
                solution.objective.value, result["theoretical_upper_bound"]
            )
            self.assertEqual(solution.certificate_level, result["certificate_level"])
            proof = solution.certificate["optimization"]
            self.assertEqual(
                [
                    sum(bit << j for j, bit in enumerate(z))
                    for z in proof["selected_generators"]
                ],
                result["selected_generators_packed"],
            )
            op = HomologyOperator(window, solution)
            columns = tuple(
                sum(bit << j for j, bit in enumerate(z)) for z in op.P.transpose().rows
            )
            self.assertTrue(oracle.verify_projection(fixture, columns))
            op.readout("kernel_basis")
            op.readout("selected_mass", (0,) * window.n)
            op.stretch()
            op.minimum_class_mass((0,) * window.n)
            record = op.to_result()
            self.assertEqual(record, OperatorResult.from_json(record.to_json()))
            family = OperatorFamily((0,), (window,), (op,))
            family.barcode()
            family.track_class((0,) * window.n, 0, 0)
            snapshot = family.to_result()
            for _ in range(2):
                snapshot = (
                    OperatorFamilyResult.from_json(snapshot.to_json())
                    .to_family()
                    .to_result()
                )
                self.assertEqual(snapshot.to_json(), family.to_result().to_json())
            if fixture["id"] == "h1_k4_stage_4":
                self.assertEqual(solution.objective.value, Fraction(4, 3))
                self.assertEqual(
                    (solution.lower_bound, solution.upper_bound), (1, Fraction(4, 3))
                )
                self.assertFalse(op.certificate()["optimality_verified"])

    def test_greedy_proof_tampering_is_rejected(self):
        window, _ = self.bound_solution()
        solution = solve_projection(ProjectionProblem(window), "GreedyCertifiedSolver")
        self.assertEqual(solution.status, "Solved", solution.diagnostics)
        proof = dict(solution.certificate["optimization"])
        for changes in (
            {"selected_generators": ((1, 0),)},  # legal class, not minimum mass
            {"selected_generators": ((1, 1),)},  # boundary, not independent
            {"selected_generators": ()},
            {"theoretical_upper_bound": 0},
            {"theoretical_upper_bound": True},
            {"hypotheses": dict(proof["hypotheses"]) | {"positive_weights": False}},
            {"hypotheses": dict(proof["hypotheses"]) | {"betti": True}},
            {
                "hypotheses": dict(proof["hypotheses"])
                | {"arithmetic_policy": "FloatingPoint"}
            },
            {"nonzero_cycles": 2},
            {"optimality_verified": True},
            {"cycle_retraction": {"nrows": 2, "ncols": 2, "rows": [[0, 0], [0, 0]]}},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                HomologyOperator(
                    window,
                    replace(solution, certificate={"optimization": proof | changes}),
                )
        for details in ({}, {"witness": (0, 0)}, {"witness": (1, 1)}):
            with self.subTest(details=details), self.assertRaises(ValueError):
                HomologyOperator(
                    window,
                    replace(
                        solution, objective=replace(solution.objective, details=details)
                    ),
                )
        same_run_problem = solve_projection(
            ProjectionProblem(window), "GreedyCertifiedSolver"
        )
        with self.assertRaises(ValueError):
            HomologyOperator(
                window, replace(solution, objective=same_run_problem.objective)
            )
        record = HomologyOperator(window, solution).to_result()
        data = record.to_dict()
        data["certificate"]["optimization"]["theoretical_upper_bound"] = 0
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(data)
        equal_weights = replace(window, weights=(1, 1))
        tied = solve_projection(
            ProjectionProblem(equal_weights), "GreedyCertifiedSolver"
        )
        self.assertEqual(
            tied.certificate["optimization"]["selected_generators"], ((1, 0),)
        )
        with self.assertRaisesRegex(ValueError, "greedy_minimum_or_tie_break"):
            HomologyOperator(
                equal_weights,
                replace(
                    tied,
                    certificate={
                        "optimization": dict(tied.certificate["optimization"])
                        | {"selected_generators": ((0, 1),)}
                    },
                ),
            )

    def test_greedy_noncycle_and_wrong_action_cannot_claim_greedy_proof(self):
        window = self.window()
        solution = solve_projection(ProjectionProblem(window), "GreedyCertifiedSolver")
        proof = dict(solution.certificate["optimization"])
        with self.assertRaisesRegex(ValueError, "greedy_independence"):
            HomologyOperator(
                window,
                replace(
                    solution,
                    certificate={
                        "optimization": proof | {"selected_generators": ((1, 0, 0),)}
                    },
                ),
            )
        window, _ = self.bound_solution(weights=(1, 1))
        solution = solve_projection(ProjectionProblem(window), "GreedyCertifiedSolver")
        other_action = Matrix.from_rows(((0, 0), (1, 1)))
        # Both actions have the same objective and are legal, but only one is greedy.
        self.assertNotEqual(solution.projection, other_action)
        from homology_operator.result import make_identity

        identity = make_identity(
            window,
            other_action,
            solution.solver_run_id,
            solution.tie_break_policy,
        )
        with self.assertRaisesRegex(ValueError, "greedy_section_action"):
            HomologyOperator(
                window,
                replace(
                    solution,
                    projection=other_action,
                    identity=identity,
                    objective=replace(solution.objective, identity=identity),
                ),
            )

    def test_greedy_empty_zero_and_unsupported_requests(self):
        for n in (0, 2):
            window = ChainWindow(
                0,
                Matrix.zero(0, n),
                Matrix.identity(n),
                (),
                tuple(f"x{i}" for i in range(n)),
                tuple(f"b{i}" for i in range(n)),
                (1,) * n,
            )
            solution = solve_projection(
                ProjectionProblem(window), "GreedyCertifiedSolver"
            )
            self.assertEqual(solution.status, "Solved", solution.diagnostics)
            self.assertEqual(solution.certificate_level, "ExactOptimal")
            self.assertEqual(
                solution.objective.state, "Computed" if n else "EmptyDomain"
            )
            self.assertEqual((solution.lower_bound, solution.upper_bound), (0, 0))
            self.assertEqual(
                solution.certificate["optimization"]["theoretical_upper_bound"], 0
            )
        window = self.window()
        integer = replace(window, weights=(1, 2, 3), arithmetic="ExactInteger")
        self.assertEqual(
            solve_projection(
                ProjectionProblem(integer), "GreedyCertifiedSolver"
            ).status,
            "Solved",
        )
        floating = replace(window, weights=(1.0, 2.0, 3.0), arithmetic="FloatingPoint")
        for problem in (
            ProjectionProblem(floating),
            ProjectionProblem(window, requested_certificate_level="ExactOptimal"),
            ProjectionProblem(window, tie_break_policy="LexicographicProjection"),
            ProjectionProblem(window, matrix_free_output=True),
        ):
            self.assertEqual(
                solve_projection(problem, "GreedyCertifiedSolver").status, "Unavailable"
            )
        self.assertEqual(GreedyCertifiedSolver().solve(None).status, "InvalidProblem")

    def test_greedy_interruption_retains_only_completed_seed_bounds(self):
        window, _ = self.bound_solution()
        complete = solve_projection(ProjectionProblem(window), "GreedyCertifiedSolver")
        saw_bound, saw_unbounded_action = False, False
        for limit in range(complete.resource_usage["states"]):
            solution = solve_projection(
                ProjectionProblem(
                    window,
                    ResourceLimits(state_limit=limit),
                    requested_certificate_level="CertifiedInterval",
                ),
                "GreedyCertifiedSolver",
            )
            self.assertEqual(solution.status, "ResourceExhausted", solution.diagnostics)
            self.assertNotEqual(solution.certificate_level, "ExactOptimal")
            if solution.projection is None:
                continue
            op = HomologyOperator(window, solution)
            self.assertEqual(
                op.to_result(), OperatorResult.from_json(op.to_result().to_json())
            )
            if solution.objective.state == "Computed":
                saw_bound = True
                self.assertEqual((solution.lower_bound, solution.upper_bound), (0, 10))
                self.assertEqual(
                    solution.certificate["optimization"]["kind"], "CycleBounds"
                )
            else:
                saw_unbounded_action = True
                self.assertEqual(solution.certificate_level, "Feasible")
                self.assertIsNone(solution.upper_bound)
        self.assertTrue(saw_bound and saw_unbounded_action)
        for limits, retained in (
            (ResourceLimits(wall_time_limit=0), False),
            (ResourceLimits(matrix_entry_limit=0), False),
            (ResourceLimits(matrix_entry_limit=32), True),
        ):
            solution = solve_projection(
                ProjectionProblem(window, limits), "GreedyCertifiedSolver"
            )
            self.assertEqual(solution.status, "ResourceExhausted", solution.diagnostics)
            self.assertEqual(solution.projection is not None, retained)
            self.assertIsNone(solution.upper_bound)
        n = 14
        large = ChainWindow(
            0,
            Matrix.zero(0, n),
            Matrix.zero(n, 0),
            (),
            tuple(f"x{i}" for i in range(n)),
            (),
            (1,) * n,
        )
        solution = solve_projection(ProjectionProblem(large), "GreedyCertifiedSolver")
        self.assertEqual(solution.status, "ResourceExhausted", solution.diagnostics)
        self.assertEqual(solution.diagnostics, ("certificate_replay_state_limit",))
        HomologyOperator(large, solution).to_result()

    def test_exhaustive_two_boundary_directions_three_homology_directions(self):
        # Direct sum of a three-coordinate circuit quotient and a two-coordinate one.
        for weights, optimum in (((1, 1, 1, 1, 1), 2), ((3, 2, 1, 5, 1), 1)):
            window = ChainWindow(
                2,
                Matrix.zero(0, 5),
                Matrix.from_columns(((1, 1, 1, 0, 0), (0, 0, 0, 1, 1)), nrows=5),
                (),
                ("a", "b", "c", "d", "e"),
                ("f", "g"),
                weights,
            )
            solution = solve_projection(
                ProjectionProblem(window, requested_certificate_level="ExactOptimal"),
                "ExhaustiveExactSolver",
            )
            self.assertEqual(solution.status, "Solved", solution.diagnostics)
            self.assertEqual(solution.objective.value, optimum)
            self.assertEqual(solution.resource_usage["candidates_visited"], 64)
            record = HomologyOperator(window, solution).to_result()
            self.assertEqual(record, OperatorResult.from_json(record.to_json()))


if __name__ == "__main__":
    unittest.main()
