from dataclasses import replace
from fractions import Fraction
import unittest
from itertools import product

from homology_operator import (
    ChainWindow,
    FeasibleSolver,
    HomologyOperator,
    Matrix,
    OperatorFamily,
    OperatorResult,
    ProjectionProblem,
)
from homology_operator.chain import matrix_from_data


def op(window):
    return HomologyOperator(window, FeasibleSolver().solve(ProjectionProblem(window)))


def merge_family():
    first = ChainWindow(
        0, Matrix.zero(0, 2), Matrix.zero(2, 0), (), ("a", "b"), (), (10, 1)
    )
    second = replace(first, D=Matrix.from_rows(((1,), (1,))), basis_next=("e",))
    return OperatorFamily(
        (0, 1, 1), (first, second, second), (op(first), op(second), op(second))
    )


class FamilyInputTests(unittest.TestCase):
    def test_ordered_stages_duplicates_and_empty_chain(self):
        family = merge_family()
        self.assertEqual(family.status, "Ready")
        self.assertEqual(family.stage(0).betti(), 2)
        self.assertEqual(family.stage(1).betti(), 1)
        self.assertEqual(family.inclusion(0, 2), Matrix.identity(2))
        empty = ChainWindow(1, Matrix.zero(0, 0), Matrix.zero(0, 0), (), (), (), ())
        self.assertEqual(
            OperatorFamily((Fraction(0),), (empty,), (op(empty),)).stage(0).betti(), 0
        )
        with self.assertRaises(ValueError):
            replace(family, scales=(1, 0, 2))
        for scales in ((0, float("nan"), 1), (0, True, 1), {0, 1, 2}, ()):
            with self.subTest(scales=scales), self.assertRaises(ValueError):
                replace(family, scales=scales)
        with self.assertRaises(ValueError):
            family.stage(True)

    def test_invalid_chain_inclusion_and_stage_identity(self):
        family = merge_family()
        first, second = family.windows[:2]
        for target in (
            replace(second, basis_current=("x", "b")),
            replace(second, A=Matrix.from_rows(((1, 1),)), basis_previous=("v",)),
            replace(second, k=1),
        ):
            with self.subTest(target=target), self.assertRaises(ValueError):
                OperatorFamily((0, 1), (first, target), (op(first), op(target)))
        with self.assertRaises(ValueError):
            replace(
                family, operators=(family.stage(1), family.stage(1), family.stage(2))
            )
        for i, j in ((1, 0), (-1, 0), (0, 3)):
            with self.assertRaises(ValueError):
                family.inclusion(i, j)

    def test_weight_policy_is_explicit(self):
        family = merge_family()
        first, second = family.windows[:2]
        changed = replace(second, weights=(1, 20))
        with self.assertRaises(ValueError):
            OperatorFamily((0, 1), (first, changed), (op(first), op(changed)))
        variable = OperatorFamily(
            (0, 1), (first, changed), (op(first), op(changed)), "Variable"
        )
        self.assertNotEqual(variable.identity, family.identity)
        with self.assertRaises(ValueError):
            replace(variable, terminal_extension="Unknown")

    def test_failed_stage_remains_partial(self):
        family = merge_family()
        failure = OperatorResult(
            None,
            family.windows[1],
            None,
            {"status": "ResourceExhausted", "certificate_level": None},
            {},
            {"diagnostic": "budget"},
            "ResourceExhausted",
        )
        partial = replace(family, operators=(family.stage(0), failure, family.stage(2)))
        self.assertEqual(partial.status, "Partial")
        self.assertEqual(partial.stage(1).status, "ResourceExhausted")
        self.assertIsNone(partial.stage(1).projection)
        self.assertEqual(partial.inclusion(0, 1), Matrix.identity(2))


class TransportTests(unittest.TestCase):
    def test_identity_composition_rank_and_original_chain_action(self):
        family = merge_family()
        for i in range(3):
            self.assertEqual(
                matrix_from_data(family.transport(i, i).value["action"]),
                Matrix.identity(family.stage(i).betti()),
            )
            for j in range(i, 3):
                result = family.transport(i, j)
                self.assertEqual(result.identity, family.stage(j).identity)
                self.assertEqual(
                    result.details["source_identity"], family.stage(i).identity
                )
                self.assertEqual(family.transport_certificate(i, j).state, "Computed")
                for middle in range(i, j + 1):
                    direct = matrix_from_data(result.value["action"])
                    composed = matrix_from_data(
                        family.transport(middle, j).value["action"]
                    ) @ matrix_from_data(family.transport(i, middle).value["action"])
                    self.assertEqual(direct, composed)
        self.assertEqual(family.transport_rank(0, 2).value, 1)
        chain = matrix_from_data(family.transport(0, 1).value["chain_action"])
        self.assertEqual(chain, family.stage(1).P)

    def test_same_betti_different_maps_and_quotient_rank(self):
        first = ChainWindow(
            1, Matrix.zero(0, 1), Matrix.zero(1, 0), (), ("a",), (), (1,)
        )
        for boundary, expected in ((((1,), (0,)), 0), (((0,), (1,)), 1)):
            second = ChainWindow(
                1,
                Matrix.zero(0, 2),
                Matrix.from_rows(boundary),
                (),
                ("a", "b"),
                ("f",),
                (1, 1),
            )
            family = OperatorFamily((0, 1), (first, second), (op(first), op(second)))
            self.assertEqual([stage.betti() for stage in family.operators], [1, 1])
            self.assertEqual(family.transport_rank(0, 1).value, expected)
            # Enumerate image cosets under the coordinate inclusion independently.
            boundaries = {
                tuple(
                    sum(row[c] * bits[c] for c in range(second.p)) % 2
                    for row in second.D.rows
                )
                for bits in product((0, 1), repeat=second.p)
            }
            cosets = {
                min(
                    tuple(a ^ b for a, b in zip((bit, 0), boundary))
                    for boundary in boundaries
                )
                for bit in (0, 1)
            }
            self.assertEqual(len(cosets).bit_length() - 1, expected)

    def test_partial_transport_is_missing_not_zero(self):
        family = merge_family()
        failure = OperatorResult(
            None,
            family.windows[1],
            None,
            {"status": "ResourceExhausted"},
            {},
            {},
            "ResourceExhausted",
        )
        partial = replace(family, operators=(family.stage(0), failure, family.stage(2)))
        self.assertEqual(partial.transport_rank(0, 1).state, "ResourceExhausted")
        self.assertIsNone(partial.transport_rank(0, 1).value)
        self.assertEqual(partial.transport(0, 2).state, "Computed")
        self.assertEqual(partial.transport_certificate(0, 2).state, "Unavailable")


if __name__ == "__main__":
    unittest.main()
