"""Joint S4-04/05/06/07 regression, including portable family recovery."""

from dataclasses import replace
from fractions import Fraction
from importlib.util import find_spec
from itertools import product
import unittest
from unittest.mock import patch

from homology_operator import (
    ChainWindow,
    CompactAction,
    CyclicAction,
    HomologyOperator,
    Matrix,
    OperatorFamily,
    OperatorFamilyResult,
    ProjectionProblem,
    QueryResult,
    solve_projection,
)
from homology_operator.native import (
    GeometryWorkspace,
    NativeFactorizedSolver,
    geometry_batch,
)
from homology_operator.result import make_identity


def small_window():
    return ChainWindow(
        1,
        Matrix.zero(0, 3),
        Matrix.from_columns(((1, 1, 1),), nrows=3),
        (),
        ("x", "y", "z"),
        ("boundary",),
        (1, 1, 1),
    )


def checked_operator(window, method, **options):
    solution = solve_projection(ProjectionProblem(window, **options), method)
    if solution.projection is None:
        raise AssertionError((solution.status, solution.diagnostics))
    return HomologyOperator(window, solution)


class FamilyIntegrationChecks:
    def check_family(self, window, operators):
        family = OperatorFamily(
            (0, 0, 1, 2, 3, 4), (window,) * len(operators), tuple(operators)
        )
        barcode = family.barcode()
        self.assertEqual(barcode.state, "Computed")
        self.assertEqual(
            tuple(
                (bar["birth_stage"], bar["death_stage"], bar["multiplicity"])
                for bar in barcode.value
            ),
            ((0, None, 2),),
        )
        history = family.barcode_basis()
        for i in range(len(operators)):
            for j in range(i, len(operators)):
                self.assertEqual(family.transport_rank(i, j).value, 2)
                self.assertEqual(family.transport_certificate(i, j).state, "Computed")
                for cycle in product((0, 1), repeat=window.n):
                    self.assertEqual(
                        family.track_mass(cycle, i, j).value,
                        operators[j].selected_mass(cycle),
                    )
        for version in (1, 2):
            record = family.to_result(schema_version=version)
            # Rebuild every native-labelled certificate through the Python path.
            with patch("homology_operator.native._extension", side_effect=ImportError):
                restored = OperatorFamilyResult.from_json(record.to_json())
                recovered = restored.to_family()
                self.assertEqual(recovered.identity, family.identity)
                self.assertEqual(recovered.barcode(), barcode)
                self.assertEqual(recovered.barcode_basis(), history)
                self.assertEqual(recovered.transport_rank(0, 5).value, 2)
                self.assertEqual(
                    geometry_batch(recovered.stage(0), ((0, 0, 0),)).state,
                    "Unavailable",
                )


class PortableIntegrationTests(FamilyIntegrationChecks, unittest.TestCase):
    def test_reference_solvers_compact_actions_and_family_restore_without_native(self):
        window = small_window()
        operators = [
            checked_operator(window, method)
            for method in (
                "ExhaustiveExactSolver",
                "GreedyCertifiedSolver",
                "Rank2ExactSolver",
            )
        ]
        operators.append(
            checked_operator(
                window,
                "StructuredFamilySolver",
                input_structure="CyclicTrace",
                matrix_free_output=True,
            )
        )
        seed = solve_projection(ProjectionProblem(window))
        pivots = (window.A.rref()[1], window.D.rref()[1])
        factors = tuple(
            Matrix.from_rows((inverse.rows[i] for i in indices), ncols=matrix.nrows)
            for matrix, inverse, indices in zip(
                (window.A, window.D),
                (seed.generalized_inverse_a, seed.generalized_inverse_d),
                pivots,
            )
        )
        factorized = CompactAction(
            "GeneralizedInverse", (window.A, window.D, *factors), pivots
        )
        h = Matrix.from_columns(seed.projection.image_basis(), nrows=window.n)
        c = Matrix.from_columns(
            (h.solve(z) for z in seed.projection.transpose().rows), nrows=h.ncols
        )
        for action in (factorized, CompactAction("HC", (h, c))):
            identity = make_identity(window, action, seed.solver_run_id)
            operators.append(
                HomologyOperator(
                    window,
                    replace(
                        seed,
                        projection=action,
                        identity=identity,
                        objective=QueryResult("NotComputed", identity=identity),
                    ),
                )
            )
        self.check_family(window, operators)


@unittest.skipUnless(
    find_spec("_homology_native"), "optional native wheel not installed"
)
class NativeIntegrationTests(FamilyIntegrationChecks, unittest.TestCase):
    def test_native_solvers_geometry_workspaces_and_compact_family_together(self):
        window = small_window()
        operators = [
            checked_operator(window, method)
            for method in (
                "NativeExhaustiveExactSolver",
                "NativeGreedyCertifiedSolver",
                "NativeRank2ExactSolver",
            )
        ]
        operators.append(
            checked_operator(
                window,
                "NativeStructuredFamilySolver",
                input_structure="CyclicTrace",
                matrix_free_output=True,
            )
        )
        operators.extend(
            checked_operator(
                window,
                NativeFactorizedSolver(),
                matrix_free_output=True,
                solver_options={"representation": form},
            )
            for form in ("HC", "Factorized")
        )
        cycles = tuple(product((0, 1), repeat=window.n))
        pairs = tuple(product(range(len(cycles)), repeat=2))
        for operator in operators:
            before = operator.to_result()
            if isinstance(operator.P, CyclicAction):
                self.assertEqual(
                    geometry_batch(operator, cycles, pairs).state, "Unavailable"
                )
                continue
            workspace = GeometryWorkspace(operator)
            first = geometry_batch(operator, cycles, pairs, workspace=workspace)
            stats = workspace.statistics()
            second = geometry_batch(operator, cycles, pairs, workspace=workspace)
            self.assertEqual(first.value, second.value)
            self.assertEqual(
                stats["projection_buffer_growths"],
                workspace.statistics()["projection_buffer_growths"],
            )
            for name in ("class_representative", "selected_mass", "support"):
                self.assertEqual(
                    first.value[name], tuple(getattr(operator, name)(z) for z in cycles)
                )
            for name in ("class_distance", "shared_support", "union_support"):
                self.assertEqual(
                    first.value[name],
                    tuple(
                        getattr(operator, name)(cycles[i], cycles[j]) for i, j in pairs
                    ),
                )
            self.assertEqual(operator.to_result(), before)
            with self.assertRaisesRegex(ValueError, "identities"):
                geometry_batch(
                    operators[(operators.index(operator) + 1) % len(operators)],
                    cycles,
                    workspace=workspace,
                )
        self.check_family(window, operators)

    def test_multiword_geometry_and_family_snapshot_share_same_compact_action(self):
        n = 65
        window = ChainWindow(
            0,
            Matrix.zero(0, n),
            Matrix.from_columns(
                (tuple(int(i == j) for i in range(n)) for j in range(2, n)), nrows=n
            ),
            (),
            tuple(f"c{i}" for i in range(n)),
            tuple(f"b{i}" for i in range(2, n)),
            tuple(Fraction(i + 1, 131) for i in range(n)),
        )
        operators = tuple(
            checked_operator(
                window,
                NativeFactorizedSolver(),
                matrix_free_output=True,
                solver_options={"representation": form},
            )
            for form in ("HC", "Factorized")
        )
        family = OperatorFamily((0, 0), (window, window), operators)
        cycles = ((1,) * n, tuple(int(i % 2 == 0) for i in range(n)))
        for stage, operator in enumerate(operators):
            workspace = GeometryWorkspace(operator)
            query = geometry_batch(operator, cycles, ((0, 1),), workspace=workspace)
            for i, cycle in enumerate(cycles):
                self.assertEqual(
                    query.value["selected_mass"][i],
                    family.track_mass(cycle, 0, stage).value,
                )
            self.assertIn("Fraction", query.details["geometry_fallback"])
        history = family.barcode_basis()
        record = family.to_result()
        with patch("homology_operator.native._extension", side_effect=ImportError):
            restored = OperatorFamilyResult.from_json(record.to_json()).to_family()
            self.assertEqual(restored.barcode_basis(), history)
            self.assertEqual(restored.transport_rank(0, 1).value, 2)


if __name__ == "__main__":
    unittest.main()
