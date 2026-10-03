"""Frozen finite triad and truthful reproducible mismatch minimization."""

from copy import deepcopy
from importlib.util import find_spec
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_s5_correctness import (
    archive_mismatch,
    check_manifest,
    load_corpus,
    make_corpus,
    minimize_manifest,
)  # noqa: E402
from test_s5_manifest import GUDHI_AVAILABLE  # noqa: E402
from oracle.simplicial import build_windows, digest, freeze_manifest, synthetic_manifest  # noqa: E402

NATIVE_AVAILABLE = find_spec("_homology_native") is not None


class CorrectnessCorpusTests(unittest.TestCase):
    def test_corpus_is_reproducible_and_rejects_tampering(self):
        corpus = load_corpus(Path(__file__).parent / "fixtures/s5_correctness.json")
        self.assertEqual(corpus, make_corpus())
        self.assertEqual(len(corpus["manifests"]), 77)
        self.assertEqual(corpus["random_cases"], 64)
        self.assertEqual(corpus["corpus_hash"], digest(corpus["manifests"]))
        for manifest in corpus["manifests"]:
            build_windows(manifest)

    def test_archive_preserves_both_results_and_declares_limited_minimality(self):
        manifest = synthetic_manifest(
            "injected_difference",
            [((0,), 0), ((1,), 0), ((2,), 0), ((0, 1), 1)],
            [0, 1],
            q=0,
        )

        def evaluate(m):
            edge = any(len(r["vertices"]) == 2 for r in m["simplices"])
            return {
                "state": "Mismatch" if edge else "Passed",
                "reference": {"betti": 1},
                "injected_oracle": {"betti": 2},
            }

        minimized = minimize_manifest(
            manifest, lambda m: evaluate(m)["state"] == "Mismatch"
        )
        self.assertEqual(len(minimized["simplices"]), 3)
        with tempfile.TemporaryDirectory() as directory:
            path = archive_mismatch(directory, manifest, evaluate)
            record = json.loads(path.read_text("utf-8"))
            self.assertEqual(record["original_manifest"], manifest)
            self.assertEqual(record["results"]["injected_oracle"], {"betti": 2})
            self.assertIn("not global", record["minimality"])

    def test_original_failure_is_saved_first_and_minimization_keeps_its_category(self):
        manifest = synthetic_manifest(
            "failure_class", [((0,), 0), ((1,), 0), ((2,), 0), ((0, 1), 1)], [0, 1], q=0
        )
        original = {
            "state": "Mismatch",
            "failure_category": "geometry",
            "run_id": "original-run",
        }
        with tempfile.TemporaryDirectory() as directory:

            def evaluate(candidate):
                self.assertEqual(len(list(Path(directory).glob("*.original.json"))), 1)
                return {
                    "state": "Mismatch",
                    "failure_category": "geometry"
                    if any(len(s["vertices"]) == 2 for s in candidate["simplices"])
                    else "different-topology-failure",
                    "run_id": "reproduction-run",
                }

            path = archive_mismatch(directory, manifest, evaluate, original)
            record = json.loads(path.read_text("utf-8"))
            self.assertEqual(record["original_result"], original)
            self.assertEqual(len(record["minimal_manifest"]["simplices"]), 3)
            self.assertEqual(record["results"]["failure_category"], "geometry")


@unittest.skipUnless(
    GUDHI_AVAILABLE and NATIVE_AVAILABLE, "three-way check requires GUDHI and native"
)
class TriadTests(unittest.TestCase):
    def test_matching_exhausted_or_interrupted_runs_cannot_pass(self):
        from unittest.mock import patch

        manifest = synthetic_manifest(
            "seventeen_isolated", [((v,), 0) for v in range(17)], [0], q=0
        )
        row = check_manifest(manifest, certified=True)
        self.assertEqual(row["state"], "ResourceExhausted")
        self.assertTrue(
            any(not c["reference"]["completed"] for c in row["joint_comparisons"])
        )
        interrupted = {
            "completed": False,
            "output_hash": "same-interruption",
            "statuses": [{"status": "Interrupted"}],
            "details": {},
        }
        with patch("check_s5_correctness.run_pipeline", return_value=interrupted):
            row = check_manifest(manifest)
        self.assertEqual(row["state"], "Interrupted")

    def test_mismatch_retains_original_exact_request_wires_and_run_identity(self):
        from unittest.mock import patch
        import check_s5_correctness as checker

        manifest = make_corpus(random_cases=0)["manifests"][1]
        pipeline = checker.run_pipeline
        captured = []

        def run(*args, **kwargs):
            result = pipeline(*args, **kwargs)
            if args[1]["solver"] == "ExhaustiveExactSolver":
                captured.append(kwargs["capture"])
                if args[2] == "reference":
                    result["output_hash"] = "injected-exact-mismatch"
            return result

        with (
            patch.object(checker, "run_pipeline", side_effect=run),
            self.assertRaises(ValueError) as raised,
        ):
            check_manifest(manifest, require_native=True, certified=True)
        results = raised.exception.results
        self.assertIn("ExhaustiveExactSolver", raised.exception.failure_category)
        for route in ("reference", "native"):
            capture = results[route + "_capture"]
            self.assertEqual(
                capture["request"]["requested_certificate_level"], "ExactOptimal"
            )
            self.assertEqual(
                capture["request"]["resource_limits"]["wall_time_limit"], 20.0
            )
            wire = capture["snapshot_wires"][0]
            self.assertIn(capture["solutions"][0]["solver"]["solver_run_id"], wire)
            self.assertIn("joint_batch", wire)
            self.assertIn(checker.CANDIDATE, wire)
        self.assertEqual(
            results["reference_capture"]["solutions"], captured[0]["solutions"]
        )

    def test_independent_projection_failure_retains_actual_context(self):
        from unittest.mock import patch

        manifest = make_corpus(random_cases=0)["manifests"][1]
        with (
            patch("oracle.reference.verify_projection", return_value=False),
            self.assertRaises(ValueError) as raised,
        ):
            check_manifest(manifest, require_native=True)
        self.assertIn("window", raised.exception.results)
        self.assertIn("projection", raised.exception.results)
        self.assertIn("solver_run_id", raised.exception.results["identity"])

    def test_structural_and_random_corpus_same_topology_full_action_joint_and_restore(
        self,
    ):
        corpus = load_corpus(Path(__file__).parent / "fixtures/s5_correctness.json")
        # The CLI audits all 77; this regression includes every structural and 8 seeded random inputs.
        for manifest in corpus["manifests"][:21]:
            with self.subTest(manifest=manifest["id"]):
                row = check_manifest(
                    manifest,
                    require_native=True,
                    certified=not manifest["id"].startswith("random/"),
                )
                self.assertEqual(row["state"], "Passed")
                for comparison in row["joint_comparisons"]:
                    self.assertEqual(
                        comparison["reference"]["output_hash"],
                        comparison["native"]["output_hash"],
                    )

    def test_weight_changes_preserve_topology_and_reordering_preserves_input_complex(
        self,
    ):
        corpus = load_corpus(Path(__file__).parent / "fixtures/s5_correctness.json")
        selected = [m for m in corpus["manifests"] if m["id"].startswith("ring_")]
        baseline = check_manifest(
            next(m for m in selected if m["id"] == "ring_repeated_scale"), True
        )
        for manifest in selected:
            if manifest["id"] == "ring_truncated_survivor":
                continue
            with self.subTest(manifest=manifest["id"]):
                self.assertEqual(
                    check_manifest(manifest, True)["topology"], baseline["topology"]
                )
        bad = deepcopy(selected[0])
        bad["simplices"][0]["weight"] = 0
        with self.assertRaises(ValueError):
            freeze_manifest(bad)


if __name__ == "__main__":
    unittest.main()
