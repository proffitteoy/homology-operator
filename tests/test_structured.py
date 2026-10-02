"""Pinned T-B1 cyclic formulas; generator, query, identity and handle boundaries.

Source: homology-operator-lab@6143729669902ee875b211b58085e954c76cdf88,
structured/verify_exact.py blob 21adb77a258a7342312333c3b77d8a8406ce5037.
The fixture below uses the independent column formula, not CyclicAction.apply.
"""

from dataclasses import replace
from fractions import Fraction
from itertools import product
import unittest
from unittest.mock import patch

from homology_operator import (
    Matrix,
    CyclicAction,
    ChainWindow,
    ProjectionProblem,
    ResourceLimits,
    HomologyOperator,
    OperatorResult,
    OperatorFamily,
    OperatorFamilyResult,
    solve_projection,
    validate_projection,
)


def cyclic_window(m):
    n = (1 << m) - 1
    columns = tuple(
        tuple(int((i - j) % n in {1 << s for s in range(m)}) for i in range(n))
        for j in range(n)
    )
    P = Matrix.from_columns(columns, nrows=n)
    D = Matrix.from_columns((Matrix.identity(n) + P).image_basis(), nrows=n)
    window = ChainWindow(
        1,
        Matrix.zero(0, n),
        D,
        (),
        tuple(f"e{i}" for i in range(n)),
        tuple(f"b{i}" for i in range(D.ncols)),
        (1,) * n,
    )
    return window, P


class StructuredTests(unittest.TestCase):
    def test_formula_and_all_small_actions_match_explicit_reference(self):
        for m in (2, 3, 4):
            window, dense = cyclic_window(m)
            for matrix_free in (True, False):
                problem = ProjectionProblem(
                    window,
                    input_structure="CyclicTrace",
                    matrix_free_output=matrix_free,
                    requested_certificate_level="ExactOptimal",
                )
                result = solve_projection(problem, "StructuredFamilySolver")
                self.assertEqual(result.status, "Solved", result.diagnostics)
                self.assertEqual(result.objective.value, m)
                self.assertEqual(result.certificate_level, "ExactOptimal")
                self.assertEqual(
                    isinstance(result.projection, CyclicAction), matrix_free
                )
                op = HomologyOperator(window, result)
                self.assertEqual(op.betti(), 1 << (m - 1))
                vectors = (
                    product((0, 1), repeat=window.n)
                    if m < 4
                    else (
                        tuple(int(i == j) for i in range(window.n))
                        for j in range(window.n)
                    )
                )
                for z in vectors:
                    projected = dense.apply(z)
                    self.assertEqual(op.project(z), projected)
                    self.assertEqual(
                        op.apply_operator(z), tuple(a ^ b for a, b in zip(z, projected))
                    )
                    self.assertEqual(op.selected_mass(z), sum(projected))
                    self.assertEqual(
                        op.support(z),
                        tuple(i for i, bit in enumerate(projected) if bit),
                    )
                    self.assertEqual(
                        op.class_distance(z, (0,) * window.n), sum(projected)
                    )
                K = Matrix.from_columns(op.kernel_basis(), nrows=window.n)
                self.assertEqual(K.rank(), 1 << (m - 1))
                self.assertTrue(all(dense.apply(z) == z for z in K.transpose().rows))
            if m == 2:
                exact = solve_projection(
                    ProjectionProblem(
                        window, requested_certificate_level="ExactOptimal"
                    ),
                    "ExhaustiveExactSolver",
                )
                self.assertEqual(exact.status, "Solved", exact.diagnostics)
                self.assertEqual(exact.objective.value, m)

    def test_seven_coordinate_optimum_by_independent_integer_section_search(self):
        window, dense = cyclic_window(3)
        boundaries, homology = window.D.image_basis(), dense.image_basis()
        basis = Matrix.from_columns(boundaries + homology, nrows=7)
        coordinates = [
            basis.solve(tuple(int(i == j) for i in range(7)))[len(boundaries) :]
            for j in range(7)
        ]
        packed_b = [sum(bit << i for i, bit in enumerate(z)) for z in boundaries]
        packed_h = [sum(bit << i for i, bit in enumerate(z)) for z in homology]
        offsets = []
        for bits in product((0, 1), repeat=len(boundaries)):
            value = 0
            for bit, b in zip(bits, packed_b):
                if bit:
                    value ^= b
            offsets.append(value)
        optimum, count = 7, 0
        for changes in product(offsets, repeat=len(homology)):
            lifts = [h ^ b for h, b in zip(packed_h, changes)]
            largest = 0
            for bits in coordinates:
                value = 0
                for bit, z in zip(bits, lifts):
                    if bit:
                        value ^= z
                largest = max(largest, value.bit_count())
            optimum = min(optimum, largest)
            count += 1
        self.assertEqual((count, optimum), (4096, 3))

    def test_no_dense_projection_required_for_constructor_project_or_restore(self):
        window, dense = cyclic_window(4)
        problem = ProjectionProblem(
            window, input_structure="CyclicTrace", matrix_free_output=True
        )
        with patch.object(
            Matrix, "identity", side_effect=AssertionError("dense identity allocation")
        ):
            result = solve_projection(problem, "StructuredFamilySolver")
            self.assertEqual(result.status, "Solved", result.diagnostics)
            op = HomologyOperator(window, result)
            self.assertIsInstance(op.P, CyclicAction)
            self.assertIsInstance(op.L, CyclicAction)
            self.assertFalse(hasattr(op.P, "rows"))
            z = (1,) + (0,) * 14
            self.assertEqual(op.project(z), dense.apply(z))
            record = op.to_result()
            self.assertEqual(
                record.to_dict()["projection"],
                {"kind": "CyclicTrace", "version": 1, "m": 4, "complement": False},
            )
            self.assertEqual(record, OperatorResult.from_json(record.to_json()))
        self.assertEqual(record.provenance["backend"], "python-structured-reference")

    def test_structured_family_transport_queries_and_identity_roundtrip(self):
        window, _ = cyclic_window(2)
        problem = ProjectionProblem(
            window, input_structure="CyclicTrace", matrix_free_output=True
        )
        first, second = (
            solve_projection(problem, "StructuredFamilySolver") for _ in range(2)
        )
        self.assertEqual(
            first.identity["projection_id"], second.identity["projection_id"]
        )
        self.assertNotEqual(first.solver_run_id, second.solver_run_id)
        ops = tuple(HomologyOperator(window, solution) for solution in (first, second))
        for op in ops:
            op.readout("selected_mass", (1, 0, 0))
            op.stretch()
            op.minimum_class_mass((1, 0, 0))
        family = OperatorFamily((0, 1), (window, window), ops)
        self.assertEqual(family.transport_rank(0, 1).value, 2)
        self.assertEqual(family.transport_certificate(0, 1).state, "Computed")
        snapshot = family.to_result()
        for _ in range(2):
            restored = OperatorFamilyResult.from_json(snapshot.to_json()).to_family()
            self.assertIsInstance(restored.operators[0].P, CyclicAction)
            self.assertEqual(restored.to_result().to_json(), snapshot.to_json())
        with self.assertRaises(ValueError):
            HomologyOperator(window, replace(first, objective=second.objective))
        dense = solve_projection(
            replace(problem, matrix_free_output=False), "StructuredFamilySolver"
        )
        # Versioned handles and dense matrices have distinct representation IDs.
        self.assertNotEqual(
            dense.identity["projection_id"], first.identity["projection_id"]
        )
        with self.assertRaises(ValueError):
            HomologyOperator(window, replace(first, projection=dense.projection))

    def test_wrong_family_float_weights_and_unsupported_parameters_rejected(self):
        window, _ = cyclic_window(3)
        problem = ProjectionProblem(
            window, input_structure="CyclicTrace", matrix_free_output=True
        )
        for changes in (
            {"input_structure": "GeneralChainWindow"},
            {"window": replace(window, weights=(2,) + (1,) * 6)},
            {"window": replace(window, weights=(1.0,) * 7, arithmetic="FloatingPoint")},
            {"window": replace(window, D=Matrix.zero(7, 0), basis_next=())},
            {"solver_options": {"pretend_cyclic": True}},
        ):
            failed = solve_projection(
                replace(problem, **changes), "StructuredFamilySolver"
            )
            self.assertEqual(
                failed.status, "Unavailable", (changes, failed.diagnostics)
            )
            self.assertIsNone(failed.projection)
        scaled = replace(window, weights=(Fraction(2, 3),) * 7)
        result = solve_projection(
            replace(problem, window=scaled), "StructuredFamilySolver"
        )
        self.assertEqual(result.status, "Solved", result.diagnostics)
        self.assertEqual(result.objective.value, 3)
        n = 31
        unsupported = ChainWindow(
            0,
            Matrix.zero(0, n),
            Matrix.zero(n, 0),
            (),
            tuple(f"e{i}" for i in range(n)),
            (),
            (1,) * n,
        )
        self.assertEqual(
            solve_projection(
                replace(problem, window=unsupported), "StructuredFamilySolver"
            ).status,
            "Unavailable",
        )
        for m in (True, 1, 5, 3.0):
            with self.assertRaises(ValueError):
                CyclicAction(m)

    def test_handle_certificate_and_action_tampering_rejected(self):
        window, _ = cyclic_window(3)
        solution = solve_projection(
            ProjectionProblem(
                window, input_structure="CyclicTrace", matrix_free_output=True
            ),
            "StructuredFamilySolver",
        )
        record = HomologyOperator(window, solution).to_result()
        for changes in (
            {"version": True},
            {"version": 2},
            {"m": 4},
            {"m": True},
            {"complement": True},
            {"rows": []},
        ):
            data = record.to_dict()
            data["projection"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                OperatorResult.from_dict(data)
        proof = dict(solution.certificate["optimization"])
        for changes in (
            {"m": True},
            {"kernel_distance": 3},
            {"kernel_distance": 4.0},
            {"optimality_verified": True},
            {"kind": "CycleBounds"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                HomologyOperator(
                    window,
                    replace(solution, certificate={"optimization": proof | changes}),
                )
        for changes in (
            {"lower_bound": 2},
            {"upper_bound": 4},
            {"lower_bound": 3.0},
            {"certificate_level": "CertifiedInterval"},
        ):
            with self.assertRaises(ValueError):
                HomologyOperator(window, replace(solution, **changes))
        for details in ({}, {"witness": (0,) * 7}, {"witness": (1,) * 7}):
            with self.assertRaises(ValueError):
                HomologyOperator(
                    window,
                    replace(
                        solution, objective=replace(solution.objective, details=details)
                    ),
                )
        with self.assertRaises(ValueError):
            validate_projection(window, CyclicAction(3, True))
        with self.assertRaises(ValueError):
            solution.projection.apply((True,) + (0,) * 6)

    def test_resource_failures_do_not_claim_certification(self):
        window, _ = cyclic_window(3)
        for matrix_free in (False, True):
            for limits in (
                ResourceLimits(state_limit=0),
                ResourceLimits(state_limit=2),
                ResourceLimits(wall_time_limit=0),
                ResourceLimits(matrix_entry_limit=0),
            ):
                result = solve_projection(
                    ProjectionProblem(
                        window,
                        limits,
                        input_structure="CyclicTrace",
                        matrix_free_output=matrix_free,
                        tie_break_policy="StructuredCanonical",
                    ),
                    "StructuredFamilySolver",
                )
                self.assertEqual(result.status, "ResourceExhausted", result.diagnostics)
                self.assertIsNone(result.projection)
                self.assertIsNone(result.certificate_level)
                failed = OperatorResult(
                    None,
                    window,
                    None,
                    result.solver_metadata(),
                    {},
                    {},
                    "ResourceExhausted",
                )
                self.assertEqual(failed, OperatorResult.from_json(failed.to_json()))


if __name__ == "__main__":
    unittest.main()
