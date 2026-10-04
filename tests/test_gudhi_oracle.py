"""Primary F2 PH and real secondary entrances, with stage semantics."""

import unittest
from unittest.mock import patch

from test_simplicial_inputs import GUDHI_AVAILABLE
from oracle.simplicial import load_manifests, synthetic_manifest
from oracle.gudhi_oracle import (
    PERSISTENCE_OPTIONS,
    build_families,
    flag_applicability,
    flag_cycle_manifest,
    gudhi_topology,
    normalize_pairs,
    operator_topology,
    secondary_topology,
)


class NormalizationTests(unittest.TestCase):
    def test_diagonals_multiplicity_and_infinity_are_distinct(self):
        pairs = [
            (0, (0, 0)),
            (0, (0, 1)),
            (1, (1, 2)),
            (1, (1, 2)),
            (1, (2, float("inf"))),
        ]
        self.assertEqual(
            normalize_pairs(pairs, [0, 1], 3),
            {"0": [[0, 1, 1]], "1": [[1, 2, 2], [2, None, 1]]},
        )
        for interval in (
            (0.5, 1),
            (0, 1.5),
            (-1, 2),
            (2, 1),
            (0, 3),
            (0, float("nan")),
            (0, -float("inf")),
        ):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                normalize_pairs([(0, interval)], [0], 3)


@unittest.skipUnless(GUDHI_AVAILABLE, "optional GUDHI dependency is unavailable")
class GudhiOracleTests(unittest.TestCase):
    def test_full_stage_betti_barcode_and_interval_rank_match_families(self):
        for manifest in load_manifests():
            with self.subTest(manifest=manifest["id"]):
                oracle = gudhi_topology(manifest)
                actual = operator_topology(build_families(manifest))
                self.assertEqual(actual, oracle["topology"])
                self.assertEqual(oracle["options"], PERSISTENCE_OPTIONS)

    def test_repeated_scale_keeps_cross_stage_bar_and_h2_requires_tetrahedron(self):
        repeated = next(m for m in load_manifests() if m["id"] == "ring_repeated_scale")
        self.assertEqual(
            gudhi_topology(repeated)["topology"]["1"]["barcode"], [[1, 2, 1]]
        )
        filled = next(m for m in load_manifests() if m["id"] == "h2_filled_boundary")
        self.assertEqual(
            gudhi_topology(filled)["topology"]["2"]["barcode"], [[0, 1, 1]]
        )
        boundary = [
            (tuple(r["vertices"]), r["birth_stage"])
            for r in filled["simplices"]
            if len(r["vertices"]) <= 3
        ]
        truncated = synthetic_manifest(
            "h2_without_death", boundary, [0, 1], q=2, maximum=2
        )
        self.assertEqual(
            gudhi_topology(truncated)["topology"]["2"]["barcode"], [[0, None, 1]]
        )
        self.assertEqual(
            gudhi_topology(load_manifests()[1])["topology"]["0"]["betti"], [2, 3]
        )

    def test_wrong_installed_version_is_rejected(self):
        with (
            patch("oracle.gudhi_oracle.version", return_value="0.0"),
            self.assertRaisesRegex(ValueError, "requires GUDHI"),
        ):
            gudhi_topology(load_manifests()[0])

    def test_secondary_flag_routes_run_or_report_unavailable_without_replacing_primary(
        self,
    ):
        manifest = flag_cycle_manifest()
        self.assertEqual(flag_applicability(manifest)["state"], "Comparable")
        primary = gudhi_topology(manifest)["topology"]
        self.assertEqual(primary["1"]["barcode"], [[1, 2, 1]])
        collapsed = secondary_topology(manifest, "edge_collapse")
        self.assertEqual(collapsed["topology"], primary)
        self.assertTrue(collapsed["input_representation_changed"])
        rips = secondary_topology(manifest, "rips_persistence")
        if rips["state"] == "Computed":
            self.assertEqual(rips["topology"], primary)
            self.assertEqual(rips["options"]["n_jobs"], 1)
        else:
            self.assertEqual(rips["state"], "Unavailable")
        for route in ("edge_collapse", "rips_persistence"):
            self.assertEqual(
                secondary_topology(load_manifests()[2], route)["state"], "NotApplicable"
            )


if __name__ == "__main__":
    unittest.main()
