"""The comparison protocol must preserve certification and failure boundaries."""

from dataclasses import replace
import importlib.util
from pathlib import Path
import unittest

from homology_operator import ChainWindow, Matrix, ProjectionProblem, ResourceLimits

spec = importlib.util.spec_from_file_location(
    "compare_solvers",
    Path(__file__).resolve().parents[1] / "scripts/compare_solvers.py",
)
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class ComparisonTests(unittest.TestCase):
    def problem(self):
        return ProjectionProblem(
            ChainWindow(
                0,
                Matrix.zero(0, 2),
                Matrix.from_columns(((1, 1),), nrows=2),
                (),
                ("x", "y"),
                ("b",),
                (10, 1),
            )
        )

    def test_problem_and_actual_certificate_groups_are_not_interchangeable(self):
        problem = self.problem()
        feasible = comparison.compare(problem, "FeasibleSolver")
        exact = comparison.compare(problem, "ExhaustiveExactSolver")
        self.assertEqual(feasible["problem_id"], exact["problem_id"])
        self.assertNotEqual(feasible["comparison_group"], exact["comparison_group"])
        self.assertEqual(feasible["solver"]["certificate_level"], "Feasible")
        self.assertEqual(exact["solver"]["certificate_level"], "ExactOptimal")
        self.assertEqual(feasible["solver"]["objective"]["state"], "NotComputed")
        self.assertEqual(feasible["audit_current_objective"]["state"], "Computed")
        self.assertIsNone(feasible["solver"]["upper_bound"])
        self.assertTrue(exact["independent_validation"]["optimality_verified"])
        changed = comparison.compare(
            replace(problem, resource_limits=ResourceLimits(state_limit=1000)),
            "ExhaustiveExactSolver",
        )
        self.assertNotEqual(exact["problem_id"], changed["problem_id"])
        self.assertIsNone(exact["costs"]["rss_peak_bytes"])
        self.assertGreaterEqual(
            exact["costs"]["total_measured_seconds"], exact["costs"]["dispatch_seconds"]
        )

    def test_unsupported_and_budget_failure_are_preserved(self):
        problem = replace(self.problem(), requested_certificate_level="ExactOptimal")
        for backend in ("FeasibleSolver", "GeneralSearchSolver"):
            record = comparison.compare(problem, backend)
            self.assertEqual(record["solver"]["status"], "Unavailable")
            self.assertIsNone(record["costs"]["construction_seconds"])
            self.assertIsNone(record["costs"]["construction_python_peak_bytes"])
            self.assertIsNone(record["independent_validation"])
        failed = comparison.compare(
            replace(problem, resource_limits=ResourceLimits(state_limit=0)),
            "ExhaustiveExactSolver",
        )
        self.assertEqual(failed["solver"]["status"], "ResourceExhausted")
        self.assertIsNotNone(failed["costs"]["construction_seconds"])
        self.assertIsNone(failed["audit_current_objective"])


if __name__ == "__main__":
    unittest.main()
