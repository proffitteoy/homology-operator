"""Meaningful process-failure and statistics boundaries for S5 sampling."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark_s5 import sample_process, summarize, successful, output_key  # noqa: E402


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
                            "records": [
                                {
                                    "completed": True,
                                    "state": "Computed",
                                    "output_hash": "same",
                                    "topology_hash": "topology",
                                }
                            ],
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


if __name__ == "__main__":
    unittest.main()
