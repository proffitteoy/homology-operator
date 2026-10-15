"""Stable-volume invariants and shared T1--T5 geometry acceptance controls."""

from dataclasses import replace
from fractions import Fraction
from hashlib import sha256
from importlib.util import find_spec
from itertools import combinations, product
from pathlib import Path
import json
import os
import runpy
import unittest
from unittest.mock import patch

from homology_operator import (
    ChainWindow,
    Matrix,
    OperatorFamily,
    QueryResult,
    ResourceLimits,
    CancellationToken,
    ValidationError,
    validate_stable_volume,
)
from oracle.geometry import boundary, histories, subsets, volumes
from test_family import simplex_family, op
from test_geometry import mapped_window


CORPUS = Path(__file__).parent / "fixtures/geometry_queries.json"


def digest(data):
    return sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_case(case, empty=False, reverse=False):
    cells = tuple(map(tuple, case["simplices"]))
    levels = tuple(Fraction(x) for x in case["levels"])
    if "points" in case:
        order = tuple(f"event-{i}" for i in range(len(cells)))
        windows = []
        for i in range(len(cells)):
            window = mapped_window(
                case["points"],
                cells[: i + 1],
                case["degree"],
                i,
                order,
                weight_semantics="unit",
            )
            mapping = dict(
                window.source_metadata["source_mapping"], scale=case["levels"][i]
            )
            windows.append(replace(window, source_metadata={"source_mapping": mapping}))
        family = OperatorFamily(
            levels,
            tuple(windows),
            tuple(op(w) for w in windows),
            simplex_source={
                "stage_convention": "AfterInsertion",
                "simplices": [
                    {"vertices": s, "label": "s" + ",".join(map(str, s))} for s in cells
                ],
            },
        )
    else:
        family = simplex_family(
            cells, case["degree"], empty_initial=empty, reverse=reverse
        )
        windows = tuple(replace(w, weight_semantics="unit") for w in family.windows)
        family = replace(
            family,
            windows=windows,
            operators=tuple(op(w) for w in windows),
            scales=((levels[0],) if empty else ()) + levels,
        )
    return family


def upper_costs(family, ref, weights=None):
    window = family.windows[ref["death_stage"]]
    mapping = window.source_metadata.get("source_mapping")
    metadata = {"source": "frozen geometry corpus: explicitly supplied simplex counts"}
    if mapping is not None:
        metadata["source_mapping"] = {
            **mapping,
            "simplices": {
                label: mapping["simplices"][label]
                for label in window.basis_current + window.basis_next
            },
        }
    return ChainWindow(
        window.k + 1,
        window.D,
        Matrix.zero(window.p, 0),
        window.basis_current,
        window.basis_next,
        (),
        (1,) * window.p if weights is None else weights,
        weight_semantics="unit" if weights is None else "custom",
        unit="simplex_count" if weights is None else "cost",
        source_metadata=metadata,
    )


class StableVolumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads(CORPUS.read_text("utf-8"))
        if digest(cls.corpus["cases"]) != cls.corpus["corpus_sha256"]:
            raise ValueError("geometry corpus hash mismatch")
        cls.cases = cls.corpus["cases"]

    def square(self, mapped=False):
        case = next(c for c in self.cases if c["id"] == ("T5" if mapped else "T2"))
        family = build_case(case)
        ref = next(r for r in family.features().value if r["birth_stage"] == 7)
        return family, ref, upper_costs(family, ref)

    def test_all_volume_constraints_epsilon_boundaries_orders_and_histories(self):
        checked = 0
        for case in self.cases:
            for empty, reverse in (
                ((False, False),)
                if "points" in case
                else product((False, True), repeat=2)
            ):
                family = build_case(case, empty, reverse)
                offset = int(empty)
                cells = tuple(map(tuple, case["simplices"]))
                levels = tuple(Fraction(x) for x in case["levels"])
                raw = histories(cells, case["degree"])
                refs = family.features().value
                self.assertEqual(
                    {
                        (
                            r["birth_stage"] - offset,
                            None
                            if r["death_stage"] is None
                            else r["death_stage"] - offset,
                        )
                        for r in refs
                    },
                    set(raw),
                )
                for ref in refs:
                    b = ref["birth_stage"] - offset
                    d = (
                        None
                        if ref["death_stage"] is None
                        else ref["death_stage"] - offset
                    )
                    window = family.windows[ref["birth_stage"]]
                    by_label = {
                        e["label"]: e["vertices"]
                        for e in family.simplex_source["simplices"]
                    }
                    seed = family.resolve_feature(ref, ref["birth_stage"]).value[
                        "representative"
                    ]
                    history = {
                        by_label[label]
                        for label, bit in zip(window.basis_current, seed)
                        if bit
                    }
                    old_faces = [
                        s for s in cells[: b + 1] if len(s) == case["degree"] + 2
                    ]
                    self.assertFalse(boundary(history))
                    self.assertNotIn(history, [boundary(s) for s in subsets(old_faces)])
                    # Interval bases may differ. Check the product history in
                    # independently enumerated raw boundary spaces at every stage.
                    for stage in range(b, len(cells) if d is None else d + 1):
                        images = [
                            boundary(s)
                            for s in subsets(
                                [
                                    s
                                    for s in cells[: stage + 1]
                                    if len(s) == case["degree"] + 2
                                ]
                            )
                        ]
                        self.assertEqual(history in images, stage == d)
                    # Independent class minimum and birth-pair optimum share a fiber.
                    boundaries = [boundary(s) for s in subsets(old_faces)]
                    optimum = min(len(history ^ image) for image in boundaries)
                    self.assertEqual(
                        family.stage(ref["birth_stage"]).minimum_class_mass(seed).value,
                        optimum,
                    )
                    if case["degree"] == 1:
                        self.assertEqual(
                            family.optimal_1_cycle(ref).value["mass"], optimum
                        )
                    if d is None:
                        continue
                    upper = upper_costs(family, ref)
                    for epsilon in (None, Fraction(1, 2), 1, Fraction(101, 100), 2, 20):
                        result = (
                            family.optimal_volume(ref, upper)
                            if epsilon is None
                            else family.stable_volume(
                                ref, epsilon, upper, epsilon_unit="level"
                            )
                        )
                        candidates = volumes(
                            cells,
                            levels,
                            case["degree"],
                            b,
                            d,
                            {s: 1 for s in cells},
                            epsilon,
                        )
                        best = min(c[0] for c in candidates)
                        self.assertEqual(result.state, "Computed")
                        self.assertEqual(result.value["mass"], best)
                        self.assertIn(
                            (
                                best,
                                frozenset(result.value["filling_simplices"]),
                                frozenset(result.value["boundary_simplices"]),
                            ),
                            candidates,
                        )
                        self.assertEqual(
                            boundary(result.value["filling_simplices"]),
                            set(result.value["boundary_simplices"]),
                        )
                        if epsilon is not None:
                            restored = QueryResult.from_dict(
                                json.loads(json.dumps(result.to_dict()))
                            )
                            self.assertTrue(
                                validate_stable_volume(
                                    family,
                                    ref,
                                    epsilon,
                                    upper,
                                    restored,
                                    epsilon_unit="level",
                                )["optimality_verified"]
                            )
                        checked += 1
        self.assertEqual(checked, 180)

    def test_nonunique_minima_are_compared_by_objective_and_feasible_set(self):
        family = build_case(next(c for c in self.cases if c["id"] == "T4"))
        cells = tuple(map(tuple, self.cases[3]["simplices"]))
        edges = [s for s in cells[:12] if len(s) == 2]
        faces = [s for s in cells[:12] if len(s) == 3]
        boundaries = [boundary(s) for s in subsets(faces)]
        ties = 0
        for chain in subsets(edges):
            if boundary(chain):
                continue
            candidates = {frozenset(chain ^ image) for image in boundaries}
            best = min(map(len, candidates))
            optima = {c for c in candidates if len(c) == best}
            ties += len(optima) > 1
            vector = tuple(int(s in chain) for s in edges)
            result = family.stage(11).minimum_class_mass(vector)
            output = {
                s for s, bit in zip(edges, result.details["representative"]) if bit
            }
            self.assertEqual(result.value, best)
            self.assertIn(frozenset(output), optima)
        self.assertGreater(ties, 0)

    def test_convex_domain_rejections_and_fixed_order_perturbation_sandwich(self):
        case = next(c for c in self.cases if c["id"] == "T5")
        for points in (
            [[0, 0], [1, 0], [0, 1], [0, 2]],
            list(reversed(case["points"])),
        ):
            family = build_case({**case, "points": points})
            ref = next(r for r in family.features().value if r["birth_stage"] == 7)
            result = family.stable_volume(
                ref, 1, upper_costs(family, ref), epsilon_unit="level"
            )
            self.assertEqual(result.details["guarantee_level"], "OptimizationOnly")
        # Integer rescaling permits exact mapped perturbations in both directions.
        base = {**case, "levels": [100 * x for x in case["levels"]]}
        family = build_case(base)
        ref = next(r for r in family.features().value if r["birth_stage"] == 7)

        def support(f, r, e):
            return set(
                f.stable_volume(r, e, upper_costs(f, r), epsilon_unit="level").value[
                    "filling_simplices"
                ]
            )

        for sign in (-1, 1):
            moved = list(base["levels"])
            for j in range(4, 8):
                moved[j] += sign
            moved[8] -= sign
            changed = build_case({**case, "levels": moved})
            other = next(r for r in changed.features().value if r["birth_stage"] == 7)
            for epsilon in (99, 100, 101):
                self.assertLessEqual(
                    support(family, ref, epsilon + 2), support(changed, other, epsilon)
                )
                self.assertLessEqual(
                    support(changed, other, epsilon), support(family, ref, epsilon - 2)
                )

    def test_threshold_equality_birth_constraint_and_unit_separation(self):
        family, ref, upper = self.square()
        for epsilon, mass in (
            (Fraction(99, 100), 2),
            (1, 2),
            (Fraction(101, 100), 1),
            (10, 1),
        ):
            result = family.stable_volume(ref, epsilon, upper, epsilon_unit="seconds")
            self.assertEqual(result.value["mass"], mass)
            self.assertEqual(result.details["epsilon_unit"], "seconds")
            self.assertEqual(result.details["unit"], "simplex_count")
            self.assertEqual(result.details["guarantee_level"], "OptimizationOnly")
            if epsilon > 1:
                self.assertFalse(result.value["same_history_class"])
        # Perturbation theorem is attached only after exact embedding certification.
        mapped, mref, mupper = self.square(True)
        result = mapped.stable_volume(mref, 1, mupper, epsilon_unit="seconds")
        self.assertEqual(
            result.details["guarantee_level"], "ConditionalCommonRobustPart"
        )
        self.assertIsNotNone(result.value["filling_location"]["source_hash"])
        for epsilon in (None, 0, -1, True, 0.5, float("nan")):
            with self.assertRaises(ValueError):
                family.stable_volume(ref, epsilon, upper, epsilon_unit="s")
        with self.assertRaises(ValueError):
            family.stable_volume(ref, 1, upper, epsilon_unit="")

    def test_budget_domain_and_no_solution_states(self):
        family, ref, upper = self.square()
        for limits in (
            ResourceLimits(state_limit=0),
            ResourceLimits(wall_time_limit=0),
            ResourceLimits(matrix_entry_limit=0),
        ):
            result = family.stable_volume(
                ref, 1, upper, epsilon_unit="level", limits=limits
            )
            self.assertEqual(
                (result.state, result.value, result.details["guarantee_level"]),
                ("ResourceExhausted", None, None),
            )
        token = CancellationToken()
        token.cancel()
        self.assertEqual(
            family.stable_volume(
                ref, 1, upper, epsilon_unit="level", cancellation=token
            ).details["reason"],
            "cancelled",
        )
        self.assertEqual(
            family.stable_volume(
                ref,
                1,
                replace(upper, arithmetic="FloatingPoint", weights=(1.0,) * upper.n),
                epsilon_unit="level",
            ).state,
            "Unavailable",
        )
        self.assertEqual(
            family.stable_volume(
                ref,
                1,
                upper,
                epsilon_unit="level",
                limits=ResourceLimits(packed_word_limit=10),
            ).state,
            "Unavailable",
        )
        infinite = build_case(
            {
                **self.cases[1],
                "simplices": self.cases[1]["simplices"][:8],
                "levels": self.cases[1]["levels"][:8],
            }
        )
        self.assertEqual(
            infinite.stable_volume(
                infinite.features().value[0], 1, epsilon_unit="level"
            ).state,
            "EmptyDomain",
        )
        # Existing fixed-filling API retains a genuine infeasible domain.
        window = family.windows[ref["birth_stage"]]
        empty_upper = ChainWindow(
            2,
            window.D,
            Matrix.zero(window.p, 0),
            window.basis_current,
            window.basis_next,
            (),
            (),
            unit="count",
            source_metadata={"source": "no triangles"},
        )
        from homology_operator import minimum_filling

        seed = family.resolve_feature(ref, ref["birth_stage"]).value["representative"]
        self.assertEqual(minimum_filling(window, seed, empty_upper).state, "Infeasible")

    def test_independent_replay_and_request_tampering(self):
        family, ref, upper = self.square(True)
        result = family.stable_volume(ref, 1, upper, epsilon_unit="level")
        with (
            patch.object(Matrix, "solve", side_effect=AssertionError("solver")),
            patch.object(Matrix, "kernel_basis", side_effect=AssertionError("kernel")),
        ):
            self.assertTrue(
                validate_stable_volume(
                    family, ref, 1, upper, result, epsilon_unit="level"
                )["optimality_verified"]
            )
        for changes in (
            {"epsilon": 2},
            {"epsilon_unit": "other"},
            {"robust_domain": False},
            {"guarantee_level": "ResamplingStable"},
            {"certificate": {"kind": "LPRelaxation"}},
            {"zero_indices": ()},
            {"problem_id": "forged"},
        ):
            with self.assertRaises(ValidationError):
                validate_stable_volume(
                    family,
                    ref,
                    1,
                    upper,
                    replace(result, details={**result.details, **changes}),
                    epsilon_unit="level",
                )
        for changes in (
            {"mass": 1},
            {"boundary": (0,) * family.windows[ref["death_stage"]].n},
            {"same_history_class": False},
        ):
            with self.assertRaises(ValidationError):
                validate_stable_volume(
                    family,
                    ref,
                    1,
                    upper,
                    replace(result, value={**result.value, **changes}),
                    epsilon_unit="level",
                )
        for changed in (
            replace(upper, weights=(2, 1), weight_semantics="custom"),
            replace(upper, unit="area"),
        ):
            with self.assertRaises(ValidationError):
                validate_stable_volume(
                    family, ref, 1, changed, result, epsilon_unit="level"
                )
        mapping = upper.source_metadata["source_mapping"]
        for key, value in (("original_id", 999), ("coordinates", (99, 0))):
            changed_vertices = {
                **mapping["vertices"],
                "0": {**mapping["vertices"]["0"], key: value},
            }
            changed = replace(
                upper,
                source_metadata={
                    **upper.source_metadata,
                    "source_mapping": {**mapping, "vertices": changed_vertices},
                },
            )
            with self.assertRaises(ValueError):
                family.stable_volume(ref, 1, changed, epsilon_unit="level")
        recovered = family.to_result().to_family()
        validate_stable_volume(recovered, ref, 1, upper, result, epsilon_unit="level")
        with self.assertRaises(ValueError):
            recovered.stable_volume(
                {**ref, "death_stage": 9}, 1, upper, epsilon_unit="level"
            )

    @unittest.skipUnless(find_spec("gudhi"), "optional locked GUDHI oracle unavailable")
    def test_frozen_topology_against_real_gudhi_f2(self):
        import gudhi

        self.assertEqual(gudhi.__version__, "3.11.0")
        for case in self.cases:
            family = build_case(case)
            tree = gudhi.SimplexTree()
            for j, cell in enumerate(case["simplices"]):
                tree.insert(cell, filtration=j)
            pairs = tree.persistence(
                homology_coeff_field=2, min_persistence=0, persistence_dim_max=True
            )
            expected = {
                (int(b), None if d == float("inf") else int(d))
                for k, (b, d) in pairs
                if k == case["degree"]
            }
            self.assertEqual(
                expected,
                {(r["birth_stage"], r["death_stage"]) for r in family.features().value},
            )

    @unittest.skipUnless(
        os.environ.get("HOMOLOGY_HOMCLOUD_VOLUME_SOURCE"),
        "optional hash-verified HomCloud LP replay unavailable",
    )
    def test_homcloud_actual_lp_in_matched_domain_and_threshold_difference(self):
        path = Path(os.environ["HOMOLOGY_HOMCLOUD_VOLUME_SOURCE"])
        self.assertEqual(
            sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
            self.corpus["homcloud"]["sha256"],
        )
        upstream = runpy.run_path(str(path))
        family, ref, upper = self.square()
        cells = tuple(map(tuple, self.cases[1]["simplices"]))
        levels = self.cases[1]["levels"]
        bmap = {
            "type": "simplicial",
            "map": [
                (
                    len(s) - 1,
                    [cells.index(face) for face in combinations(s, len(s) - 1)]
                    if len(s) > 1
                    else [],
                )
                for s in cells
            ],
        }
        for epsilon in (Fraction(1, 2), 1, Fraction(3, 2)):
            proxy = upstream["bisect_tightened"](7, 10, levels, float(epsilon))
            optimizer = upstream["Optimizer"](
                proxy, 10, bmap, upstream["default_lp_solver"]()
            )
            actual = optimizer.find()
            self.assertTrue(actual.success)
            actual_support = {cells[j] for j in actual.cell_indices}
            result = family.stable_volume(ref, epsilon, upper, epsilon_unit="level")
            # On this disk signed LP has an integral optimum. Equality at the
            # cutoff changes HomCloud's feasible set and is a retained negative row.
            if epsilon == 1:
                self.assertNotEqual(
                    actual_support, set(result.value["filling_simplices"])
                )
            else:
                self.assertEqual(actual_support, set(result.value["filling_simplices"]))

    def test_frozen_homcloud_rows_keep_the_threshold_negative_control(self):
        family, ref, upper = self.square()
        for row in self.corpus["homcloud"]["frozen_rows"]:
            result = family.stable_volume(
                ref, Fraction(row["epsilon"]), upper, epsilon_unit="level"
            )
            same = set(result.value["filling_simplices"]) == set(
                map(tuple, row["support"])
            )
            self.assertEqual(same, row["comparison"] == "same_feasible_set")

    def test_positive_cost_anchor_certificate_skips_search_but_rechecks_feasibility(
        self,
    ):
        family, ref, upper = self.square()
        family.feature_pairing(ref)
        with (
            patch.object(Matrix, "solve", side_effect=AssertionError("unneeded solve")),
            patch.object(
                Matrix,
                "kernel_basis",
                side_effect=AssertionError("unneeded enumeration"),
            ),
        ):
            result = family.stable_volume(ref, 2, upper, epsilon_unit="level")
        self.assertEqual(
            result.details["certificate"]["kind"], "PositiveCostDeathAnchor"
        )
        self.assertEqual(result.details["resource_usage"]["states"], 1)
        self.assertEqual(result.details["verification"]["replayed_candidates"], 1)
        # Eighteen triangles leave seventeen unconstrained optional variables:
        # the affine reference cap is exceeded, but the anchor proof is finite.
        triangles = [(0, i, i + 1) for i in range(1, 19)]
        cells = sorted(
            {
                s
                for t in triangles
                for size in range(1, 4)
                for s in combinations(t, size)
            },
            key=lambda s: (len(s), s),
        )
        large = build_case(
            {
                "degree": 1,
                "simplices": cells,
                "levels": [
                    0 if len(s) == 1 else 1 if len(s) == 2 else 3 for s in cells
                ],
            }
        )
        large_ref = max(large.features().value, key=lambda r: r["death_stage"])
        large_upper = upper_costs(large, large_ref)
        self.assertEqual(
            large.optimal_volume(large_ref, large_upper).state, "Unavailable"
        )
        large_result = large.stable_volume(
            large_ref, 2, large_upper, epsilon_unit="level"
        )
        self.assertEqual(large_result.value["mass"], 1)
        self.assertEqual(
            large_result.details["certificate"]["kind"], "PositiveCostDeathAnchor"
        )
        constrained = family.stable_volume(ref, 1, upper, epsilon_unit="level")
        with self.assertRaises(ValidationError):
            validate_stable_volume(
                family,
                ref,
                1,
                upper,
                replace(
                    constrained,
                    details={
                        **constrained.details,
                        "certificate": {
                            "kind": "PositiveCostDeathAnchor",
                            "candidate_count": 1,
                        },
                    },
                ),
                epsilon_unit="level",
            )
        for count in (True, 0, 2):
            with self.assertRaises(ValidationError):
                validate_stable_volume(
                    family,
                    ref,
                    2,
                    upper,
                    replace(
                        result,
                        details={
                            **result.details,
                            "certificate": {
                                "kind": "PositiveCostDeathAnchor",
                                "candidate_count": count,
                            },
                        },
                    ),
                    epsilon_unit="level",
                )


if __name__ == "__main__":
    unittest.main()
