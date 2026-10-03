"""Backend, cancellation and compact restoration boundaries for S4-08."""

from dataclasses import replace
from fractions import Fraction
import os
import sys
from types import SimpleNamespace
import threading
import time
import unittest
from unittest.mock import patch

from homology_operator import (
    CancellationToken,
    ExhaustiveExactSolver,
    GreedyCertifiedSolver,
    ChainWindow,
    HomologyOperator,
    Matrix,
    OperatorFamily,
    OperatorFamilyResult,
    OperatorResult,
    ProjectionProblem,
    ResourceLimits,
    solve_projection,
)
from homology_operator.native import backend_info, geometry_batch, _extension

try:
    extension = _extension()
except ImportError:
    extension = None
    if os.environ.get("HOMOLOGY_NATIVE_REQUIRED") == "1":
        raise RuntimeError("compatible S4-08 native wheel required")


def window(n=3):
    return ChainWindow(
        1,
        Matrix.zero(0, n),
        Matrix.from_columns(((1,) * n,), nrows=n),
        (),
        tuple(f"e{i}" for i in range(n)),
        ("b",),
        (Fraction(1, 3),) * n,
    )


class IntegrationTests(unittest.TestCase):
    def test_explicit_backend_selection_and_visible_same_solver_fallback(self):
        problem = ProjectionProblem(window())
        for backend, name in (
            ("NativeFeasibleSolver", "NativeFeasibleSolver"),
            ("NativeExhaustiveExactSolver", "NativeExhaustiveExactSolver"),
            ("NativeGreedyCertifiedSolver", "NativeGreedyCertifiedSolver"),
            (ExhaustiveExactSolver(native=True), "NativeExhaustiveExactSolver"),
            (GreedyCertifiedSolver(native=True), "NativeGreedyCertifiedSolver"),
        ):
            with patch("homology_operator.native._extension", side_effect=ImportError):
                unavailable = solve_projection(problem, backend)
                self.assertEqual(unavailable.status, "Unavailable")
                recovered = solve_projection(problem, backend, fallback=True)
                self.assertIsNotNone(recovered.projection)
                selection = recovered.resource_usage["backend_selection"]
                self.assertEqual(selection["requested"], name)
                self.assertEqual(selection["selected"], name.removeprefix("Native"))
                expected = solve_projection(problem, name.removeprefix("Native"))
                self.assertEqual(recovered.projection, expected.projection)
                self.assertEqual(
                    recovered.certificate_level, expected.certificate_level
                )
                self.assertEqual(recovered.solver_config_id, expected.solver_config_id)
        self.assertEqual(
            solve_projection(problem, "unknown", fallback=True).status, "Unavailable"
        )
        self.assertEqual(
            solve_projection(problem, fallback="yes").status, "InvalidProblem"
        )
        with patch("homology_operator.native._extension", side_effect=ImportError):
            unsupported = solve_projection(
                replace(problem, matrix_free_output=True),
                "NativeFactorizedSolver",
                fallback=True,
            )
            self.assertEqual(unsupported.status, "Unavailable")

    def test_reference_cancel_is_runtime_state_and_not_a_zero_result(self):
        token = CancellationToken()
        original = ProjectionProblem(window())
        cancelled = replace(original, cancellation=token)
        self.assertEqual(
            original.solver_config("FeasibleSolver"),
            cancelled.solver_config("FeasibleSolver"),
        )
        token.cancel()
        for backend in (
            "FeasibleSolver",
            "ExhaustiveExactSolver",
            "GreedyCertifiedSolver",
        ):
            result = solve_projection(cancelled, backend)
            self.assertEqual(result.status, "ResourceExhausted")
            self.assertIn("cancelled", result.diagnostics)
            self.assertIsNone(result.projection)
            self.assertEqual(result.objective.state, "NotComputed")
        self.assertEqual(
            solve_projection(replace(original, cancellation=object())).status,
            "InvalidProblem",
        )
        budget = solve_projection(
            replace(original, resource_limits=ResourceLimits(state_limit=0))
        )
        self.assertIn("state_limit", budget.diagnostics)
        self.assertNotIn("cancelled", budget.diagnostics)

    def test_backend_info_does_not_claim_missing_or_old_wheel_available(self):
        with patch(
            "homology_operator.native._extension", side_effect=ImportError("old wheel")
        ):
            info = backend_info()
            self.assertEqual(info["reference"], "Available")
            self.assertEqual(info["native"], "Unavailable")
            self.assertIn("old wheel", info["reason"])

        for old in (SimpleNamespace(), SimpleNamespace(__semantics_version__=0)):
            with patch.dict(sys.modules, {"_homology_native": old}):
                with self.assertRaisesRegex(ImportError, "rebuild"):
                    _extension()
                self.assertEqual(backend_info()["native"], "Unavailable")

    def test_public_restore_preserves_p_run_provenance_and_history_without_resolve(
        self,
    ):
        w = window()
        op = HomologyOperator(w, solve_projection(ProjectionProblem(w)))
        op.readout("selected_mass", (1, 0, 0))
        op.readout("support", (1, 0, 0))
        record = op.to_result()
        with patch(
            "homology_operator.solver.FeasibleSolver.solve",
            side_effect=AssertionError("re-solve"),
        ):
            restored = OperatorResult.from_json(record.to_json()).to_operator()
        self.assertEqual(restored.to_result(), record)
        self.assertEqual(restored.project((0, 1, 1)), op.project((0, 1, 1)))
        self.assertEqual(record.query_results["kernel_basis"].state, "NotComputed")

    def test_external_restore_replays_argument_bound_geometry(self):
        w = window()
        op = HomologyOperator(w, solve_projection(ProjectionProblem(w)))
        op.readout("selected_mass", (1, 0, 0))
        wire = op.to_result().to_dict()
        query = next(
            q
            for q in wire["query_results"].values()
            if q["details"].get("query") == "selected_mass"
        )
        query["value"] = 999
        with self.assertRaisesRegex(ValueError, "persisted query"):
            OperatorResult.from_dict(wire)


@unittest.skipIf(extension is None, "compatible native wheel not installed")
class NativeIntegrationTests(unittest.TestCase):
    def test_named_factorized_dispatch_and_cancelled_construction(self):
        info = backend_info()
        self.assertEqual(
            info["extension_path"],
            getattr(extension, "_homology_native", extension).__file__,
        )
        self.assertTrue(info["extension_path"].endswith((".pyd", ".so")))
        w = window()
        token = CancellationToken()
        token.cancel()
        for backend, matrix_free in (
            ("NativeFeasibleSolver", False),
            ("NativeFactorizedSolver", True),
            ("NativeExhaustiveExactSolver", False),
        ):
            result = solve_projection(
                ProjectionProblem(
                    w, cancellation=token, matrix_free_output=matrix_free
                ),
                backend,
            )
            self.assertEqual(result.status, "ResourceExhausted", result.diagnostics)
            self.assertIn("cancelled", result.diagnostics)
        result = solve_projection(
            ProjectionProblem(w, matrix_free_output=True), "NativeFactorizedSolver"
        )
        self.assertIsNotNone(result.projection, result.diagnostics)
        self.assertEqual(result.method, "NativeFactorizedSolver")

    def test_native_span_cancel_releases_gil_and_reports_completed_states(self):
        token = CancellationToken()
        flag = token._native_handle()
        n, dimension = 8192, 16
        basis = []
        for i in range(dimension):
            row = [(1 << 64) - 1] * (n // 64)
            row[0] ^= 1 << i
            basis.append(row)
        ready, output, errors = threading.Event(), [], []

        def run():
            try:
                ready.set()
                output.append(
                    extension.span_objective(basis, basis, [1] * n, 100000, None, flag)
                )
            except BaseException as error:
                errors.append(error)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        self.assertTrue(ready.wait(2))
        time.sleep(0.005)
        started = time.perf_counter()
        token.cancel()
        worker.join(2)
        self.assertFalse(worker.is_alive(), "native cancellation did not return")
        self.assertFalse(errors, errors)
        self.assertEqual(output[0][-1], "cancelled")
        self.assertGreater(output[0][-2], 0)
        self.assertLess(output[0][-2], (1 << dimension) - 1)
        self.assertLess(time.perf_counter() - started, 2)
        stopped = extension.span_table([[1]], [1], 100, None, flag)
        self.assertEqual(stopped[2:], (0, "cancelled"))

    def test_geometry_resource_cancel_failure_and_history(self):
        w = window()
        op = HomologyOperator(w, solve_projection(ProjectionProblem(w)))
        before = op.to_result()
        cycles, pairs = ((1, 0, 0), (0, 1, 0)), ((0, 1),)
        for limits, reason in (
            (ResourceLimits(state_limit=0), "state_limit"),
            (ResourceLimits(state_limit=2), "state_limit"),
            (ResourceLimits(wall_time_limit=0), "wall_time_limit"),
            (ResourceLimits(matrix_entry_limit=0), "matrix_entry_limit"),
        ):
            result = geometry_batch(op, cycles, pairs, limits=limits)
            self.assertEqual(result.state, "ResourceExhausted")
            self.assertIsNone(result.value)
            self.assertEqual(result.details["reason"], reason)
        token = CancellationToken()
        token.cancel()
        self.assertEqual(
            geometry_batch(op, cycles, cancellation=token).details["reason"],
            "cancelled",
        )
        result = geometry_batch(op, cycles, pairs, limits=ResourceLimits(state_limit=3))
        self.assertEqual(result.state, "Computed")
        self.assertEqual(result.details["resource_usage"]["states"], 3)
        self.assertEqual(before, op.to_result())
        self.assertEqual(
            geometry_batch(op, (), limits=ResourceLimits(state_limit=0)).state,
            "Computed",
        )
        with self.assertRaises(ValueError):
            geometry_batch(op, cycles, cancellation=object())
        noncycle = replace(
            w,
            A=Matrix.from_rows(((1, 0, 0),)),
            basis_previous=("v",),
            D=Matrix.zero(3, 0),
            basis_next=(),
        )
        invalid_op = HomologyOperator(
            noncycle, solve_projection(ProjectionProblem(noncycle))
        )
        with self.assertRaisesRegex(ValueError, "cycle"):
            geometry_batch(
                invalid_op, ((1, 0, 0),), limits=ResourceLimits(matrix_entry_limit=0)
            )

    def test_compact_single_and_both_family_schemas_restore_without_dense_or_native(
        self,
    ):
        w = window(65)
        for representation in ("Factorized", "HC"):
            problem = ProjectionProblem(
                w,
                matrix_free_output=True,
                solver_options={"representation": representation},
            )
            op = HomologyOperator(
                w, solve_projection(problem, "NativeFactorizedSolver")
            )
            op.readout("selected_mass", (1,) + (0,) * 64)
            wire = op.to_result().to_json()
            identity = Matrix.identity

            def guarded(size):
                if size == w.n:
                    raise AssertionError("dense P/L/identity materialization")
                return identity(size)

            with (
                patch("homology_operator.native._extension", side_effect=ImportError),
                patch.object(Matrix, "identity", side_effect=guarded),
            ):
                restored = OperatorResult.from_json(wire).to_operator()
                self.assertEqual(restored.identity, op.identity)
                self.assertEqual(restored.to_result().to_json(), wire)
            family = OperatorFamily((0, 0), (w, w), (op, op))
            family.track_mass((1,) + (0,) * 64, 0, 1)
            for version in (1, 2):
                snapshot = family.to_result(schema_version=version)
                with patch(
                    "homology_operator.native._extension", side_effect=ImportError
                ):
                    restored_family = OperatorFamilyResult.from_json(
                        snapshot.to_json()
                    ).to_family()
                    self.assertEqual(
                        restored_family.to_result().to_dict(), snapshot.to_dict()
                    )


if __name__ == "__main__":
    unittest.main()
