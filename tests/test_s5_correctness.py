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


@unittest.skipUnless(
    GUDHI_AVAILABLE and NATIVE_AVAILABLE, "three-way check requires GUDHI and native"
)
class TriadTests(unittest.TestCase):
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
