"""Meaningful process-failure and statistics boundaries for S5 sampling."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark_s5 import sample_process, summarize, successful, output_key  # noqa: E402


def computed_record():
    return {
        "completed": True,
        "state": "Computed",
        "output_hash": "same",
        "topology_hash": "topology",
        "worker_pipeline_seconds": 0.5,
        "warm_records": [{"output_hash": "same", "seconds": 0.1}],
        "statuses": [{"status": "FeasibleOnly", "certificate_level": "Feasible"}],
        "details": [
            {
                "method": "FeasibleSolver",
                "solver_config": {
                    "method": "FeasibleSolver",
                    "solver_options": {},
                    "requested_certificate_level": "Feasible",
                },
            }
        ],
    }


class S5SamplingTests(unittest.TestCase):
    def test_real_fresh_process_success_timeout_oom_and_killed_are_distinct(self):
        success = sample_process(
            [sys.executable, "-c", "import json; print(json.dumps({'records': []}))"], 5
        )
        self.assertEqual(success["process_state"], "completed")
        timeout = sample_process(
            [sys.executable, "-c", "import time; time.sleep(5)"], 0.1
        )
        self.assertEqual(timeout["process_state"], "process_timeout")
        self.assertIsNone(timeout["end_to_end_seconds"])
        oom = sample_process(
            [
                sys.executable,
                "-c",
                "import json,sys; print(json.dumps({'error_kind':'MemoryError'})); sys.exit(1)",
            ],
            5,
        )
        self.assertEqual(oom["process_state"], "process_oom")
        killed = sample_process([sys.executable, "-c", "import sys; sys.exit(137)"], 5)
        self.assertEqual(killed["process_state"], "process_killed")
        error = sample_process([sys.executable, "-c", "print('broken json')"], 5)
        self.assertEqual(error["process_state"], "process_error")

    def test_missing_rss_failure_and_mismatch_never_become_success_cost_ratios(self):
        plan = {
            "cases": [
                {
                    "id": "x",
                    "workload": "Joint-basic",
                    "routes": ["reference", "integrated", "gudhi"],
                }
            ],
            "statistics": {"minimum_paired_blocks": 10},
            "seed": 73,
        }
        rows = []
        for block in range(10):
            for route in ("reference", "integrated", "gudhi"):
                rows.append(
                    {
                        "case": "x",
                        "route": route,
                        "block": block,
                        "scope": "cold",
                        "mode": "rss",
                        "process_state": "completed",
                        "end_to_end_seconds": 0.1,
                        "result": {
                            "peak_rss_bytes": 200 if route == "reference" else 100,
                            "records": [computed_record()],
                        },
                    }
                )
        group = next(
            x
            for x in summarize(plan, rows)
            if x["route"] == "integrated"
            and x["mode"] == "rss"
            and x["scope"] == "cold"
        )
        self.assertEqual(group["reference_comparison"]["paired_median_ratio"], 0.5)
        self.assertIn(
            "additional information", group["gudhi_comparison"]["interpretation"]
        )
        bad = deepcopy(rows)
        bad[-2]["result"]["records"][0]["output_hash"] = "changed"
        group = next(
            x
            for x in summarize(plan, bad)
            if x["route"] == "integrated"
            and x["mode"] == "rss"
            and x["scope"] == "cold"
        )
        self.assertIsNone(group["reference_comparison"]["paired_median_ratio"])
        for row in rows:
            row["result"]["peak_rss_bytes"] = None
        self.assertTrue(all(x["median"] is None for x in summarize(plan, rows)))
        rows[0]["result"]["records"][0].update(
            completed=False, state="ResourceExhausted"
        )
        self.assertFalse(successful(rows[0]))

    def test_library_resource_failure_is_json_serializable_in_timing_and_rss(self):
        from types import SimpleNamespace
        from benchmark_s5 import worker
        from oracle.simplicial import load_manifests

        m = load_manifests()[1]
        case = {
            "id": "budget",
            "input_id": m["id"],
            "solver": "FeasibleSolver",
            "workload": "Topology",
            "query_count": 0,
            "requested_certificate_level": "Feasible",
            "repeats": 1,
            "warm_repeats": 1,
            "resource_limits": {
                "state_limit": 0,
                "wall_time_limit": 1.0,
                "matrix_entry_limit": 0,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(
                json.dumps({"cases": [case], "inputs": {m["id"]: m}}), "utf-8"
            )
            for mode in ("timing", "rss"):
                args = SimpleNamespace(
                    manifest=path,
                    case="budget",
                    route="reference",
                    scope="cold",
                    mode=mode,
                    baseline_root=Path(directory),
                )
                result = worker(args)
                json.dumps(result, allow_nan=False)
                self.assertEqual(result["records"][0]["state"], "ResourceExhausted")
                self.assertFalse(result["records"][0]["completed"])

    def test_warm_repetition_disagreement_does_not_pass_identity(self):
        row = {
            "scope": "warm",
            "result": {
                "records": [
                    {
                        "output_hash": "cold",
                        "warm_records": [{"output_hash": "a"}, {"output_hash": "b"}],
                    }
                ]
            },
        }
        self.assertIsNone(output_key(row))

    def test_checkpoint_failure_preserves_previous_and_complete_temporary_data(self):
        from unittest.mock import patch
        from benchmark_acceptance import checkpoint_json

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps({"previous": True}), "utf-8")
            with (
                patch("pathlib.Path.replace", side_effect=OSError("locked")),
                self.assertRaises(OSError),
            ):
                checkpoint_json(path, {"sample": "complete"})
            self.assertEqual(json.loads(path.read_text("utf-8")), {"previous": True})
            temporary = list(Path(directory).glob("*.json.tmp"))
            self.assertEqual(len(temporary), 1)
            self.assertEqual(
                json.loads(temporary[0].read_text("utf-8")), {"sample": "complete"}
            )

    def test_run_plan_marked_mismatch_vetoes_ten_remaining_valid_pairs(self):
        from unittest.mock import patch
        import benchmark_s5 as sampler

        case = {
            "id": "x",
            "input_id": "x",
            "workload": "Joint-basic",
            "query_count": 0,
            "solver": "FeasibleSolver",
            "requested_certificate_level": "Feasible",
            "resource_limits": {},
            "routes": ["reference", "integrated"],
            "expected_topology_hash": "topology",
        }
        plan = {
            "inputs": {},
            "cases": [case],
            "blocks": 11,
            "seed": 73,
            "threads": {},
            "process_wall_seconds": 5,
            "rss_budget_bytes": 1000,
            "statistics": {"minimum_paired_blocks": 10},
        }
        injected = False

        def sample(command, *args):
            nonlocal injected
            record = computed_record()
            if (
                not injected
                and command[command.index("--route") + 1] == "integrated"
                and command[command.index("--scope") + 1] == "cold"
                and command[command.index("--mode") + 1] == "timing"
            ):
                injected = True
                record["topology_hash"] = "incorrect-topology"
            return {
                "process_state": "completed",
                "end_to_end_seconds": 1,
                "result": {
                    "initialization_seconds": 0,
                    "peak_rss_bytes": 100,
                    "records": [record],
                },
            }

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(sampler, "frozen_environment", return_value={}),
            patch.object(sampler, "sample_process", side_effect=sample),
        ):
            root = Path(directory)
            report = sampler.run_plan(
                plan, root / "plan.json", root / "report.json", root, "smoke"
            )
        group = next(
            g
            for g in report["summary"]
            if (g["route"], g["scope"], g["mode"]) == ("integrated", "cold", "timing")
        )
        self.assertEqual(group["library_states"]["Mismatch"], 1)
        self.assertEqual(group["reference_comparison"]["paired_blocks"], 10)
        self.assertEqual(group["reference_comparison"]["mismatched_blocks"], 1)
        self.assertIsNone(group["reference_comparison"]["paired_median_ratio"])

    def test_identical_warm_values_with_different_actual_certification_are_not_comparable(
        self,
    ):
        record = computed_record()
        row = {
            "case": "x",
            "route": "reference",
            "block": 0,
            "scope": "warm",
            "mode": "timing",
            "process_state": "completed",
            "result": {"records": [record]},
        }
        peer = deepcopy(row)
        peer["route"] = "native_explicit"
        peer["result"]["records"][0]["statuses"] = [
            {"status": "Solved", "certificate_level": "ExactOptimal"}
        ]
        peer["result"]["records"][0]["details"][0]["method"] = (
            "NativeGreedyCertifiedSolver"
        )
        peer["result"]["records"][0]["details"][0]["solver_config"]["method"] = (
            "NativeGreedyCertifiedSolver"
        )
        self.assertNotEqual(output_key(row), output_key(peer))
        plan = {
            "cases": [
                {
                    "id": "x",
                    "workload": "Topology",
                    "routes": ["reference", "native_explicit"],
                }
            ],
            "seed": 73,
            "statistics": {"minimum_paired_blocks": 1},
        }
        group = next(
            g
            for g in summarize(plan, [row, peer])
            if g["route"] == "native_explicit"
            and g["scope"] == "warm"
            and g["mode"] == "timing"
        )
        self.assertEqual(group["reference_comparison"]["mismatched_blocks"], 1)
        self.assertIsNone(group["reference_comparison"]["paired_median_ratio"])

    def test_real_isolated_greedy_and_native_feasible_warm_are_distinct(self):
        from importlib.util import find_spec
        from benchmark_s5 import run_worker_case, ROOT
        from oracle.simplicial import load_manifests

        if find_spec("_homology_native") is None:
            self.skipTest("real native solver requires the optional extension")
        manifest = next(m for m in load_manifests() if m["id"] == "isolated")
        case = {
            "input_id": "isolated",
            "workload": "Topology",
            "query_count": 0,
            "solver": "GreedyCertifiedSolver",
            "requested_certificate_level": "Feasible",
            "resource_limits": {
                "state_limit": 100000,
                "wall_time_limit": 20.0,
                "matrix_entry_limit": 1000000,
            },
            "warm_repeats": 2,
        }
        plan = {"inputs": {"isolated": manifest}}
        ref = run_worker_case(plan, case, "reference", "warm", ROOT)
        native = run_worker_case(plan, case, "native_explicit", "warm", ROOT)
        self.assertEqual(ref["topology_hash"], native["topology_hash"])
        self.assertEqual(ref["statuses"][0]["certificate_level"], "ExactOptimal")
        self.assertEqual(native["statuses"][0]["certificate_level"], "Feasible")
        self.assertNotEqual(
            ref["warm_records"][0]["output_hash"],
            native["warm_records"][0]["output_hash"],
        )
        self.assertNotEqual(
            output_key({"scope": "warm", "result": {"records": [ref]}}),
            output_key({"scope": "warm", "result": {"records": [native]}}),
        )

    def test_cold_joint_additional_construction_failure_retains_original_records(self):
        from unittest.mock import patch
        import benchmark_s5 as sampler
        from oracle.simplicial import load_manifests

        manifest = load_manifests()[1]
        case = {
            "id": "failure",
            "input_id": manifest["id"],
            "solver": "FeasibleSolver",
            "workload": "Joint-basic",
            "query_count": 1,
            "requested_certificate_level": "Feasible",
            "resource_limits": {},
        }
        statuses = [
            {
                "degree": 0,
                "stage": 0,
                "status": "ResourceExhausted",
                "certificate_level": None,
            }
        ]
        details = [
            {
                "method": "FeasibleSolver",
                "solver_config": {"requested_certificate_level": "Feasible"},
                "resource_usage": {"states": 100000},
                "diagnostics": ["wall_time_limit"],
            }
        ]
        with (
            patch.object(
                sampler,
                "run_pipeline",
                return_value={
                    "completed": True,
                    "output_hash": "joint-success",
                    "statuses": [],
                },
            ),
            patch.object(
                sampler, "construct_families", return_value=(None, statuses, details)
            ),
        ):
            failed = sampler.run_worker_case(
                {"inputs": {manifest["id"]: manifest}},
                case,
                "reference",
                "cold",
                Path("."),
            )
        self.assertEqual(failed["state"], "ResourceExhausted")
        self.assertEqual(failed["statuses"], statuses)
        self.assertEqual(failed["details"], details)
        self.assertTrue(all(r["completed"] for r in failed["records"]))
        case.update(routes=["reference"], expected_topology_hash="unused")
        plan = {
            "inputs": {},
            "cases": [case],
            "blocks": 1,
            "seed": 73,
            "threads": {},
            "process_wall_seconds": 5,
            "rss_budget_bytes": 1000,
            "statistics": {"minimum_paired_blocks": 10},
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(sampler, "frozen_environment", return_value={}),
            patch.object(
                sampler,
                "sample_process",
                return_value={
                    "process_state": "completed",
                    "end_to_end_seconds": 1,
                    "result": {"initialization_seconds": 0, "records": [failed]},
                },
            ),
        ):
            root = Path(directory)
            report = sampler.run_plan(
                plan, root / "plan.json", root / "report.json", root, "smoke"
            )
        self.assertTrue(all(g["median"] is None for g in report["summary"]))
        self.assertTrue(
            all(
                g["library_states"] == {"ResourceExhausted": 1}
                for g in report["summary"]
            )
        )


if __name__ == "__main__":
    unittest.main()
