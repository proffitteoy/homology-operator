"""S5 strict input and actual double-builder audit, independent of PH results."""

from copy import deepcopy
from dataclasses import replace
import importlib.util
from itertools import combinations
import os
import unittest

from oracle.simplicial import (
    applicability,
    audit_inputs,
    build_simplex_tree,
    build_windows,
    digest,
    expected_export,
    export_windows,
    freeze_manifest,
    load_manifests,
    synthetic_manifest,
    validate_manifest,
)


GUDHI_AVAILABLE = importlib.util.find_spec("gudhi") is not None
if os.environ.get("HOMOLOGY_GUDHI_REQUIRED") == "1" and not GUDHI_AVAILABLE:
    raise RuntimeError("GUDHI oracle tests require the locked oracle dependency group")


class ManifestTests(unittest.TestCase):
    def test_frozen_corpus_shapes_boundaries_weights_and_repeat_scales(self):
        manifests = load_manifests()
        self.assertEqual(len(manifests), 6)
        for manifest in manifests:
            with self.subTest(manifest=manifest["id"]):
                windows = build_windows(manifest)
                self.assertEqual(
                    export_windows(manifest, windows), expected_export(manifest)
                )
                for slices in windows.values():
                    for w in slices:
                        self.assertEqual(w.A.ncols, w.D.nrows)
                        self.assertFalse(
                            any(x for row in (w.A @ w.D).rows for x in row)
                        )
        empty = build_windows(manifests[0])
        self.assertEqual(
            [(empty[k][0].m, empty[k][0].n, empty[k][0].p) for k in empty],
            [(0, 0, 0)] * 4,
        )
        repeated = next(m for m in manifests if m["id"] == "ring_repeated_scale")
        self.assertEqual(repeated["scales"], [0, 1, 1])
        self.assertEqual([w.n for w in build_windows(repeated)[1]], [0, 3, 3])

    def test_invalid_faces_stage_vertex_truncation_and_source_are_rejected(self):
        base = synthetic_manifest(
            "edge", [((0,), 0), ((1,), 0), ((0, 1), 1)], [0, 1], q=0
        )
        changes = []

        def add(mutator):
            value = deepcopy(base)
            value.pop("input_hash")
            mutator(value)
            changes.append(value)

        add(lambda m: m["simplices"].pop(0))
        add(lambda m: m["simplices"][0].update(birth_stage=1))
        changes[-1]["simplices"][-1]["birth_stage"] = 0
        for stage in (True, 0.5, -1, 2, 2**53 + 1):
            add(lambda m, stage=stage: m["simplices"][-1].update(birth_stage=stage))
        add(lambda m: m["simplices"][-1].update(vertices=[1, 0]))
        add(lambda m: m["simplices"][-1].update(vertices=[0, 0]))
        add(lambda m: m["vertices"][0].update(id=2**31))
        add(lambda m: m["truncation"].update(max_dimension=0))
        add(lambda m: m["truncation"].update(max_scale=2))
        add(lambda m: m["source"].update(sha256="bad"))
        add(lambda m: m["scales"].reverse())
        add(lambda m: m.update(terminal_extension="unknown"))
        for value in changes:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    freeze_manifest(value)

    def test_positive_exact_weights_float_policy_and_hash_tampering(self):
        base = load_manifests()[1]
        for weight in (
            0,
            -1,
            True,
            float("nan"),
            float("inf"),
            {"numerator": 1, "denominator": 0},
        ):
            changed = deepcopy(base)
            changed["simplices"][0]["weight"] = weight
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                freeze_manifest(changed)
        rational = deepcopy(base)
        rational["weight_policy"]["arithmetic"] = "ExactRational"
        rational["simplices"][0]["weight"] = {"numerator": 3, "denominator": 7}
        rational = freeze_manifest(rational)
        self.assertEqual(str(build_windows(rational)[0][0].weights[0]), "3/7")
        floating = deepcopy(base)
        floating["weight_policy"]["arithmetic"] = "FloatingPoint"
        for r in floating["simplices"]:
            r["weight"] = 1.0
        build_windows(freeze_manifest(floating))
        changed = deepcopy(base)
        changed["simplices"][0]["weight"] = 2
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_manifest(changed)
        self.assertEqual(applicability()["state"], "NotApplicable")

    def test_reordered_coordinates_keep_explicit_complex_and_detect_weight_changes(
        self,
    ):
        base = load_manifests()[2]
        reordered = deepcopy(base)
        reordered["coordinate_order"] = "reverse_lexicographic"
        reordered = freeze_manifest(reordered)
        first, second = build_windows(base), build_windows(reordered)
        self.assertNotEqual(first[0][0].basis_current, second[0][0].basis_current)
        self.assertEqual(export_windows(base, first), export_windows(reordered, second))
        self.assertNotEqual(base["input_hash"], reordered["input_hash"])
        tampered = dict(first)
        tampered[0] = (replace(first[0][0], weights=(2,) * first[0][0].n),) + first[0][
            1:
        ]
        with self.assertRaisesRegex(ValueError, "weights"):
            export_windows(base, tampered)


@unittest.skipUnless(GUDHI_AVAILABLE, "optional GUDHI dependency is unavailable")
class DoubleBuilderTests(unittest.TestCase):
    def test_all_actual_simplex_filtration_boundary_and_counts_match(self):
        for manifest in load_manifests():
            with self.subTest(manifest=manifest["id"]):
                audit = audit_inputs(manifest)
                self.assertEqual(audit["chain_hash"], audit["simplex_tree_hash"])
                self.assertEqual(audit["chain_hash"], digest(expected_export(manifest)))

    def test_gudhi_auto_faces_and_filtration_edits_cannot_pass_audit(self):
        manifest = load_manifests()[2]
        tree = build_simplex_tree(manifest)
        tree.insert([0, 1, 2], filtration=0)
        with self.assertRaisesRegex(ValueError, "differs"):
            audit_inputs(manifest, tree=tree)
        tree = build_simplex_tree(manifest)
        tree.insert([9], filtration=0)
        with self.assertRaises(ValueError):
            audit_inputs(manifest, tree=tree)

    def test_insertion_order_and_h0_through_h3_truncation_are_explicit(self):
        import gudhi

        for q in range(4):
            vertices = tuple(range(q + 2))
            births = [
                (s, 0)
                for size in range(1, len(vertices))
                for s in combinations(vertices, size)
            ]
            births.append((vertices, 1))
            manifest = synthetic_manifest(f"h{q}_death", births, [0, 1], q=q)
            tree = gudhi.SimplexTree()
            for r in reversed(manifest["simplices"]):
                tree.insert(r["vertices"], filtration=r["birth_stage"])
            audit_inputs(manifest, tree=tree)
            self.assertEqual(tree.dimension(), q + 1)


if __name__ == "__main__":
    unittest.main()
