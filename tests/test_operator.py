from dataclasses import FrozenInstanceError, replace
from itertools import product
import unittest

from homology_operator.algebra import Matrix
from homology_operator.chain import ChainWindow
from homology_operator.operator import HomologyOperator
from homology_operator.result import OperatorResult, make_identity
from homology_operator.solver import FeasibleSolver, ProjectionProblem
from homology_operator.validation import ValidationError


class OperatorTests(unittest.TestCase):
    def operator(self):
        window = ChainWindow(
            1,
            Matrix.from_rows(((1, 1, 0),)),
            Matrix.from_rows(((1,), (1,), (0,))),
            ("v",),
            ("a", "b", "c"),
            ("f",),
            (1, 2, 3),
        )
        return HomologyOperator(
            window, FeasibleSolver().solve(ProjectionProblem(window))
        )

    def test_actions_and_quotient_correspondence(self):
        op = self.operator()
        cycles = ((0, 0, 0), (1, 1, 0), (0, 0, 1), (1, 1, 1))
        boundaries = {(0, 0, 0), (1, 1, 0)}
        self.assertEqual(op.betti(), 1)
        self.assertEqual(op.kernel_basis(), ((0, 0, 1),))
        for x in product((0, 1), repeat=3):
            self.assertEqual(op.project(x), op.P.apply(x))
            self.assertEqual(
                op.apply_operator(x), tuple(a ^ b for a, b in zip(x, op.project(x)))
            )
            self.assertEqual(op.is_cycle(x), x in cycles)
            self.assertEqual(op.is_boundary(x), x in boundaries)
        for z, y in product(cycles, repeat=2):
            difference = tuple(a ^ b for a, b in zip(z, y))
            self.assertEqual(op.same_class(z, y), difference in boundaries)

    def test_cycle_domain_and_immutability(self):
        op = self.operator()
        self.assertEqual(op.project((1, 0, 0)), (0, 0, 0))
        self.assertFalse(op.is_boundary((1, 0, 0)))
        for operation in (
            lambda: op.class_representative((1, 0, 0)),
            lambda: op.same_class((0, 0, 0), (1, 0, 0)),
            lambda: op.project((2, 0, 0)),
            lambda: op.project((1,)),
        ):
            with self.assertRaises(ValueError):
                operation()
        with self.assertRaises(FrozenInstanceError):
            op.P = Matrix.zero(3, 3)

    def test_snapshot_state_and_roundtrip_revalidation(self):
        op = self.operator()
        self.assertEqual(
            op.to_result().query_results["kernel_basis"].state, "NotComputed"
        )
        op.kernel_basis()
        self.assertEqual(op.to_result().query_results["kernel_basis"].state, "Computed")
        query = op.readout("class_representative", (0, 0, 1))
        self.assertEqual(query.identity, op.identity)
        self.assertEqual(query.value, (0, 0, 1))
        result = op.to_result()
        self.assertEqual(result, OperatorResult.from_json(result.to_json()))
        bad = result.to_dict()
        bad["projection"] = {"nrows": 3, "ncols": 3, "rows": [[0] * 3] * 3}
        bad["identity"] = make_identity(
            op.window, Matrix.zero(3, 3), op.solution.solver_run_id
        )
        bad["query_results"] = {}
        with self.assertRaises(ValidationError):
            OperatorResult.from_dict(bad)

    def test_solution_mismatch_and_zero_homology(self):
        op = self.operator()
        with self.assertRaises(ValidationError):
            HomologyOperator(
                op.window,
                replace(op.solution, identity={**op.identity, "weight_id": "wrong"}),
            )
        with self.assertRaises(ValidationError):
            HomologyOperator(
                op.window, replace(op.solution, projection=Matrix.zero(3, 3))
            )
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
            zero = HomologyOperator(
                window, FeasibleSolver().solve(ProjectionProblem(window))
            )
            self.assertEqual(zero.betti(), 0)
            self.assertEqual(zero.kernel_basis(), ())
            self.assertEqual(zero.to_result().query_results["kernel_basis"].value, ())


if __name__ == "__main__":
    unittest.main()
