"""The comparison protocol must preserve certification and failure boundaries."""

from dataclasses import replace
import importlib.util
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from homology_operator import ChainWindow, Matrix, ProjectionProblem, ResourceLimits
from homology_operator import OperatorResult, HomologyOperator, solve_projection
from homology_operator.result import _decode, content_id

spec = importlib.util.spec_from_file_location(
    "compare_solvers",
    Path(__file__).resolve().parents[1] / "scripts/compare_solvers.py",
)
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)

r0_spec = importlib.util.spec_from_file_location(
    "benchmark_reference",
    Path(__file__).resolve().parents[1] / "scripts/benchmark_reference.py",
)
r0 = importlib.util.module_from_spec(r0_spec)
r0_spec.loader.exec_module(r0)


class ComparisonTests(unittest.TestCase):
    def test_r0_json_output_is_lf_before_git_normalization(self):
        value = {"unicode": "原始证据", "values": [1, 2]}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            r0.write_json(path, value)
            raw = path.read_bytes()
            self.assertNotIn(b"\r", raw)
            self.assertTrue(raw.endswith(b"\n"))
            self.assertEqual(json.loads(raw), value)
            # An exact file digest survives text-mode read/write on Windows.
            other = Path(directory) / "copy.json"
            r0.write_json(other, json.loads(path.read_text("utf-8")))
            self.assertEqual(sha256(raw).digest(), sha256(other.read_bytes()).digest())

    def test_r0_frozen_lf_and_historical_crlf_checksums(self):
        folder = Path(__file__).resolve().parents[1] / "benchmarks"
        mapping = json.loads((folder / "s4_r0_checksums.json").read_text("utf-8"))
        for name, checksums in mapping["artifacts"].items():
            with self.subTest(file=name):
                raw = (folder / name).read_bytes().replace(b"\r\n", b"\n")
                self.assertEqual(sha256(raw).hexdigest(), checksums["git_lf_sha256"])
                self.assertEqual(
                    sha256(raw.replace(b"\n", b"\r\n")).hexdigest(),
                    checksums["original_crlf_sha256"],
                )
        manifest = mapping["artifacts"]["s4_r0_manifest.json"]
        for name in mapping["reports_with_historical_manifest_binding"]:
            report = json.loads((folder / name).read_text("utf-8"))
            self.assertEqual(
                report["manifest_sha256"], manifest["original_crlf_sha256"]
            )
            self.assertNotEqual(report["manifest_sha256"], manifest["git_lf_sha256"])

    def test_r0_disjoint_costs_and_repeatable_joint_output(self):
        manifest = json.loads(
            (
                Path(__file__).resolve().parents[1] / "benchmarks/s4_r0_manifest.json"
            ).read_text("utf-8")
        )
        case = next(
            c
            for c in manifest["cases"]
            if c["id"] == "family/h1_k4_all_deaths/feasible/q8"
        )
        first = r0.run_case(manifest, case, manifest["source"]["revision"])
        second = r0.run_case(manifest, case, manifest["source"]["revision"])
        self.assertEqual(
            first["semantic_output_sha256"], second["semantic_output_sha256"]
        )
        self.assertTrue(first["completed_requested_workload"])
        costs = first["segments_seconds"]
        self.assertTrue(all(value >= 0 for value in costs.values()))
        self.assertAlmostEqual(sum(costs.values()), first["pipeline_seconds"])
        for phase in (
            "dispatch_validation",
            "operator_validation",
            "serialization",
            "restore",
            "transport_barcode",
            "geometry",
        ):
            self.assertGreater(costs[phase], 0)

    def test_r0_library_failures_are_not_successful_or_zero_queries(self):
        manifest = json.loads(
            (
                Path(__file__).resolve().parents[1] / "benchmarks/s4_r0_manifest.json"
            ).read_text("utf-8")
        )
        for name, expected in (
            ("failure/floating-exact", "Unavailable"),
            ("failure/k4-exact-states-0", "ResourceExhausted"),
        ):
            case = next(c for c in manifest["cases"] if c["id"] == name)
            result = r0.run_case(manifest, case, manifest["source"]["revision"])
            self.assertFalse(result["completed_requested_workload"])
            self.assertEqual(result["solver_results"][0]["status"], expected)
            self.assertNotIn("geometry", result["segments_seconds"])
            self.assertNotIn("operator_validation", result["segments_seconds"])

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

    def test_frozen_report_revalidates_every_retained_action(self):
        path = Path(__file__).resolve().parents[1] / "benchmarks/phase3_reference.json"
        report = _decode(json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(
            report["source_snapshot_id"],
            content_id("source-snapshot", report["source_manifest_sha256_lf"]),
        )
        self.assertFalse(report["working_tree_dirty"])
        self.assertEqual(len(report["rows"]), 324)
        verified = 0
        for row in report["rows"]:
            if row["projection"] is None:
                self.assertIsNone(row["independent_validation"])
                continue
            verified += 1
            window = ChainWindow.from_dict(report["problem_windows"][row["problem_id"]])
            record = OperatorResult(
                row["identity"],
                window,
                row["projection"],
                row["solver"],
                row["certificate"],
                {},
            )
            self.assertEqual(
                record.solver["solver_config_id"],
                content_id("solver-config", row["request"]),
            )
            self.assertEqual(record, OperatorResult.from_json(record.to_json()))
        self.assertEqual(verified, 114)

    def test_local_search_frozen_report_preserves_proof_and_cost_boundaries(self):
        report = _decode(
            json.loads(
                (comparison.ROOT / "benchmarks/phase3_local_search.json").read_text(
                    encoding="utf-8"
                )
            )
        )
        self.assertFalse(report["working_tree_dirty"])
        self.assertEqual(len(report["rows"]), 144)
        self.assertEqual(report["protocol"]["experiment"], "boundary-flips")
        verified = 0
        for row in report["rows"]:
            if row["projection"] is None:
                self.assertIn(
                    row["solver"]["status"], {"Unavailable", "ResourceExhausted"}
                )
                continue
            verified += 1
            window = ChainWindow.from_dict(report["problem_windows"][row["problem_id"]])
            record = OperatorResult(
                row["identity"],
                window,
                row["projection"],
                row["solver"],
                row["certificate"],
                {},
            )
            self.assertEqual(
                record.solver["solver_config_id"],
                content_id("solver-config", row["request"]),
            )
            self.assertEqual(record, OperatorResult.from_json(record.to_json()))
            if (
                row["backend"] == "BoundaryFlipExperiment"
                and row["fixture_id"] == "h1_k4_stage_4"
                and row["solver"]["resource_usage"]["local_complete"]
            ):
                self.assertEqual(
                    record.solver["upper_bound"], comparison.Fraction(9, 8)
                )
                self.assertEqual(
                    record.solver["certificate_level"], "CertifiedInterval"
                )
                self.assertIs(record.certificate["optimality_verified"], False)
        self.assertEqual(verified, 120)

    def test_local_search_keeps_completed_improvements_on_interruption(self):
        fixtures = json.loads(
            (comparison.ROOT / "tests/fixtures/reference.json").read_text(
                encoding="utf-8"
            )
        )["fixtures"]
        problem = comparison.fixture_problem(
            next(f for f in fixtures if f["id"] == "h1_k4_stage_4")
        )
        complete = solve_projection(problem, comparison.BoundaryFlipExperiment())
        self.assertEqual(complete.upper_bound, comparison.Fraction(9, 8))
        improved_interruption = False
        for limit in range(complete.resource_usage["states"]):
            solution = solve_projection(
                replace(problem, resource_limits=ResourceLimits(state_limit=limit)),
                comparison.BoundaryFlipExperiment(),
            )
            self.assertEqual(solution.status, "ResourceExhausted", solution.diagnostics)
            if solution.projection is None:
                continue
            op = HomologyOperator(problem.window, solution)
            self.assertEqual(
                op.to_result(), OperatorResult.from_json(op.to_result().to_json())
            )
            if solution.upper_bound is not None:
                self.assertEqual(op.stretch().value, solution.upper_bound)
                self.assertGreaterEqual(solution.upper_bound, complete.upper_bound)
                improved_interruption |= solution.upper_bound < comparison.Fraction(
                    4, 3
                )
        self.assertTrue(improved_interruption)
        self.assertEqual(
            solve_projection(problem, "GeneralSearchSolver").status, "Unavailable"
        )


class AcceptanceTests(unittest.TestCase):
    @staticmethod
    def harness():
        import sys

        directory = str(Path(__file__).resolve().parents[1] / "scripts")
        sys.path.insert(0, directory)
        try:
            import benchmark_acceptance

            return benchmark_acceptance
        finally:
            sys.path.remove(directory)

    def test_checkpoint_preserves_previous_data_when_atomic_replace_fails(self):
        from unittest.mock import patch

        harness = self.harness()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text('{"previous":true}', encoding="utf-8")
            with patch.object(Path, "replace", side_effect=OSError(22, "locked")):
                with patch("time.sleep"):
                    with self.assertRaises(OSError):
                        harness.checkpoint_json(path, {"new": True})
            self.assertEqual(json.loads(path.read_text("utf-8")), {"previous": True})
            saved = list(Path(directory).glob("*.json.tmp"))
            self.assertEqual(len(saved), 1)
            self.assertEqual(json.loads(saved[0].read_text("utf-8")), {"new": True})
            harness.checkpoint_json(path, {"new": True})
            self.assertEqual(json.loads(path.read_text("utf-8")), {"new": True})

    def test_admission_requires_all_successful_same_output_process_blocks(self):
        harness = self.harness()
        manifest = {"cases": [{"id": "case", "routes": ["r0", "candidate"]}]}

        def sample(route, block, output="same", completed=True):
            return {
                "case": "case",
                "route": route,
                "block": block,
                "mode": "timing",
                "process_state": "completed",
                "cold_block_seconds": 1 if route == "r0" else 0.5,
                "result": {
                    "records": [{"completed": completed, "output_hash": output}]
                },
            }

        rows = [
            sample(route, block) for block in range(10) for route in ("r0", "candidate")
        ]
        result = harness.summarize(manifest, rows)[2]
        self.assertTrue(result["admission_improvement"])
        self.assertEqual(result["paired_blocks"], 10)
        self.assertFalse(
            harness.summarize(manifest, rows[:-2])[2]["admission_improvement"]
        )
        rows[-1] = sample("candidate", 9, completed=False)
        result = harness.summarize(manifest, rows)[2]
        self.assertFalse(result["admission_improvement"])
        self.assertEqual(result["complete_blocks"], 9)
        rows[-1] = sample("candidate", 9, output="different")
        result = harness.summarize(manifest, rows)[2]
        self.assertFalse(result["same_output"])
        self.assertFalse(result["admission_improvement"])
        # Ten matching blocks plus a mismatch must still fail admission.
        rows.extend((sample("r0", 10), sample("candidate", 10)))
        self.assertFalse(harness.summarize(manifest, rows)[2]["admission_improvement"])
        empty = harness.summarize(
            manifest, [sample("r0", 0), sample("candidate", 0, completed=False)]
        )[2]
        self.assertIsNone(empty["same_output"])
        self.assertIsNone(empty["median"])

    def test_separate_rss_and_non_deterministic_repeats_cannot_be_admitted(self):
        harness = self.harness()
        manifest = {"cases": [{"id": "case", "routes": ["r0", "candidate"]}]}
        rows = []
        for block in range(10):
            for route in ("r0", "candidate"):
                rows.append(
                    {
                        "case": "case",
                        "route": route,
                        "block": block,
                        "mode": "rss",
                        "process_state": "completed",
                        "result": {
                            "peak_rss_bytes": 100 if route == "r0" else 150,
                            "records": [{"completed": True, "output_hash": "same"}],
                        },
                    }
                )
        result = harness.summarize(manifest, rows)[3]
        self.assertTrue(result["median_regression_over_20_percent"])
        self.assertFalse(result["admission_improvement"])
        rows[-1]["result"]["records"].append(
            {"completed": True, "output_hash": "changed"}
        )
        self.assertFalse(harness.summarize(manifest, rows)[3]["same_output"])
        for row in rows:
            row["result"]["peak_rss_bytes"] = None
        missing = harness.summarize(manifest, rows)[3]
        self.assertIsNone(missing["median"])
        self.assertEqual(missing["paired_blocks"], 0)

    def test_joint_acceptance_replays_recovery_and_audits_noncycle_extension(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        harness = self.harness()
        w = ChainWindow(
            1,
            Matrix.from_rows(((1, 0),)),
            Matrix.zero(2, 0),
            ("v",),
            ("a", "b"),
            (),
            (2, 3),
        )
        manifest = {"windows": {"w": w.to_dict()}, "candidate": {"revision": "test"}}
        case = {
            "fixture_ids": ["w"],
            "solver": "FeasibleSolver",
            "resource_limits": {},
            "requested_certificate_level": "Feasible",
            "input_structure": "GeneralChainWindow",
            "matrix_free_output": False,
            "scales": None,
            "queries": [{"stage": 0, "z": [0, 1], "y": [0, 0]}],
        }
        first = harness.run_pipeline(manifest, case, "reference", Path())
        second = harness.run_pipeline(manifest, case, "reference", Path())
        self.assertTrue(first["completed"])
        self.assertEqual(first["output_hash"], second["output_hash"])
        identity = first["details"]["operator_identities"][0]
        self.assertEqual(
            set(identity),
            {
                "input_id",
                "basis_id",
                "weight_id",
                "projection_id",
                "operator_id",
                "solver_run_id",
            },
        )
        restore = harness.restore_operator

        def corrupted(record, revision):
            op = restore(record, revision)
            names = (
                "window",
                "P",
                "project",
                "class_representative",
                "selected_mass",
                "support",
                "class_distance",
                "shared_support",
                "union_support",
            )
            proxy = SimpleNamespace(**{name: getattr(op, name) for name in names})
            # Geometry on cycles stays correct; corruption only affects e0 outside ker(A).
            proxy.apply_operator = (
                lambda z: (0, 0) if tuple(z) == (1, 0) else op.apply_operator(z)
            )
            return proxy

        with patch.object(harness, "restore_operator", side_effect=corrupted):
            with self.assertRaisesRegex(ValueError, "restored full-chain P/L differs"):
                harness.run_pipeline(manifest, case, "reference", Path())


if __name__ == "__main__":
    unittest.main()
