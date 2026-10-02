from itertools import product
import unittest

from homology_operator.algebra import Matrix
from homology_operator.chain import ChainWindow
from homology_operator.solver import (
    FeasibleSolver,
    ProjectionProblem,
    ResourceLimits,
    generalized_inverse,
)


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


if __name__ == "__main__":
    unittest.main()
