"""Product correctness across the independent simplicial regression corpus."""

from importlib.util import find_spec
import json
from math import fsum
from pathlib import Path
import unittest

from homology_operator import OperatorResult
from oracle.simplicial import digest, validate_manifest
from oracle.gudhi_oracle import build_families, gudhi_topology, operator_topology
from test_simplicial_inputs import GUDHI_AVAILABLE


class OracleCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        corpus = json.loads(
            (Path(__file__).parent / "fixtures/oracle_corpus.json").read_text("utf-8")
        )
        if digest(corpus["manifests"]) != corpus["corpus_hash"]:
            raise ValueError("correctness corpus identity differs")
        cls.manifests = corpus["manifests"]

    def test_reference_geometry_and_restoration_for_all_inputs(self):
        for manifest in self.manifests:
            with self.subTest(manifest=manifest["id"]):
                validate_manifest(manifest)
                for family in build_families(manifest).values():
                    for op in family.operators:
                        window = op.window
                        cycles = (
                            tuple(0 for _ in window.weights),
                            *window.A.kernel_basis(),
                        )
                        for cycle in cycles:
                            representative = op.project(cycle)
                            parts = [
                                w
                                for w, bit in zip(window.weights, representative)
                                if bit
                            ]
                            expected = (
                                fsum(parts)
                                if window.arithmetic == "FloatingPoint"
                                else sum(parts)
                            )
                            self.assertEqual(
                                op.class_representative(cycle), representative
                            )
                            self.assertEqual(op.selected_mass(cycle), expected)
                            self.assertEqual(op.class_distance(cycle, cycle), 0)
                        restored = OperatorResult.from_json(
                            op.to_result().to_json()
                        ).to_operator()
                        self.assertEqual(restored.betti(), op.betti())
                        for cycle in cycles:
                            self.assertEqual(restored.project(cycle), op.project(cycle))

    @unittest.skipUnless(GUDHI_AVAILABLE, "optional GUDHI dependency is unavailable")
    def test_all_betti_barcodes_and_interval_ranks_against_gudhi(self):
        for manifest in self.manifests:
            with self.subTest(manifest=manifest["id"]):
                self.assertEqual(
                    operator_topology(build_families(manifest)),
                    gudhi_topology(manifest)["topology"],
                )

    @unittest.skipUnless(
        find_spec("_homology_native"), "optional native extension is unavailable"
    )
    def test_native_same_projection_and_topology_for_all_inputs(self):
        for manifest in self.manifests:
            with self.subTest(manifest=manifest["id"]):
                reference = build_families(manifest)
                native = build_families(
                    manifest, "NativeFactorizedSolver", matrix_free_output=True
                )
                self.assertEqual(
                    operator_topology(native), operator_topology(reference)
                )
                for degree, family in reference.items():
                    for op, optimized in zip(
                        family.operators, native[degree].operators
                    ):
                        for cycle in op.window.A.kernel_basis():
                            self.assertEqual(
                                optimized.project(cycle), op.project(cycle)
                            )
                            self.assertEqual(
                                optimized.selected_mass(cycle), op.selected_mass(cycle)
                            )


if __name__ == "__main__":
    unittest.main()
