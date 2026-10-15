"""Independent birth-fiber enumeration, history counterexamples and location."""

from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from itertools import combinations, product
from hashlib import sha256
from pathlib import Path
import ast
import collections
import json
import os
import unittest
from unittest.mock import patch

from homology_operator import (
    CancellationToken,
    Matrix,
    OperatorFamily,
    QueryResult,
    ResourceLimits,
    ValidationError,
    validate_optimal_1_cycle,
)
from test_family import simplex_family, op
from test_geometry import mapped_window


TRIANGLE = ((0,), (1,), (2,), (0, 1), (1, 2), (0, 2), (0, 1, 2))
FILLED = (
    (0,),
    (1,),
    (2,),
    (3,),
    (0, 1),
    (1, 2),
    (0, 2),
    (0, 1, 2),
    (2, 3),
    (0, 3),
    (0, 2, 3),
)
THETA = (
    (0,),
    (1,),
    (2,),
    (3,),
    (0, 2),
    (1, 2),
    (0, 3),
    (1, 3),
    (0, 1),
    (0, 1, 2),
    (0, 1, 3),
)


def unit_family(stream=FILLED, **options):
    family = simplex_family(stream, degree=1, **options)
    windows = tuple(replace(w, weight_semantics="unit") for w in family.windows)
    return replace(family, windows=windows, operators=tuple(op(w) for w in windows))


def geometric_family(stream, points, weights, **changes):
    order = tuple(f"insert-{i}" for i in range(len(stream)))
    windows = tuple(
        mapped_window(
            points,
            stream[: i + 1],
            1,
            i,
            order,
            weights=tuple(weights[s] for s in stream[: i + 1] if len(s) == 2),
            **{"weight_semantics": "euclidean_length", "unit": "m", **changes},
        )
        for i in range(len(stream))
    )
    return OperatorFamily(
        tuple(range(len(stream))),
        windows,
        tuple(op(w) for w in windows),
        simplex_source={
            "stage_convention": "AfterInsertion",
            "simplices": [
                {"vertices": s, "label": "s" + ",".join(map(str, s))} for s in stream
            ],
        },
    )


class OptimalCycleTests(unittest.TestCase):
    def independent_optimum(self, family, ref, result):
        birth = ref["birth_stage"]
        window = family.windows[birth]
        seed = family.resolve_feature(ref, birth).value["representative"]
        boundaries = {
            tuple(sum(a * b for a, b in zip(row, c)) % 2 for row in window.D.rows)
            for c in product((0, 1), repeat=window.p)
        }
        candidates = []
        for chain in product((0, 1), repeat=window.n):
            if tuple(a ^ b for a, b in zip(chain, seed)) in boundaries:
                self.assertFalse(any(window.A.apply(chain)))
                candidates.append(
                    (
                        sum(w * b for w, b in zip(window.weights, chain)),
                        sum(b << i for i, b in enumerate(chain)),
                        chain,
                    )
                )
        best = min(candidates)
        self.assertEqual(result.state, "Computed")
        self.assertEqual(
            (result.value["mass"], result.value["chain"]), (best[0], best[2])
        )
        self.assertTrue(
            validate_optimal_1_cycle(family, ref, result)["full_history_verified"]
        )

    def test_all_small_fibers_orders_conventions_infinite_and_zero_scale(self):
        streams = (
            TRIANGLE,
            TRIANGLE[:-1],
            FILLED,
            THETA,
            tuple((i,) for i in range(4))
            + tuple(combinations(range(4), 2))
            + tuple(combinations(range(4), 3)),
        )
        for stream, empty, reverse in product(streams, (False, True), (False, True)):
            family = unit_family(stream, empty_initial=empty, reverse=reverse)
            before = family.barcode()
            for ref in family.features().value:
                with self.subTest(
                    stream=stream,
                    birth=ref["birth_stage"],
                    empty=empty,
                    reverse=reverse,
                ):
                    result = family.optimal_1_cycle(ref)
                    self.independent_optimum(family, ref, result)
                    self.assertEqual(
                        result.identity, family.stage(ref["birth_stage"]).identity
                    )
                    self.assertEqual(result.details["reference"], ref)
                    self.assertEqual(
                        result.value["location"]["support"], result.value["support"]
                    )
                    wire = json.loads(json.dumps(result.to_dict()))
                    validate_optimal_1_cycle(family, ref, QueryResult.from_dict(wire))
                    restored = family.to_result().to_family()
                    self.assertEqual(restored.optimal_1_cycle(ref).value, result.value)
            self.assertEqual(family.barcode(), before)

    def test_birth_edge_and_future_boundaries_do_not_identify_history(self):
        family = unit_family(THETA)
        ref = next(r for r in family.features().value if r["birth_stage"] == 8)
        result = family.optimal_1_cycle(ref)
        window = family.windows[8]
        other = tuple(int(s in ((0, 1), (0, 3), (1, 3))) for s in THETA if len(s) == 2)
        seed = family.resolve_feature(ref, 8).value["representative"]
        residual = tuple(a ^ b for a, b in zip(other, seed))
        self.assertEqual(window.A.apply(other), (0,) * window.m)
        self.assertEqual(other[window.basis_current.index(str((0, 1)))], 1)
        self.assertIsNone(window.D.solve(residual))
        self.assertIsNotNone(family.windows[-1].D.solve(residual))
        bad = result.to_dict()
        bad["value"]["chain"] = other
        with self.assertRaisesRegex(ValidationError, "historical_class"):
            validate_optimal_1_cycle(family, ref, QueryResult.from_dict(bad))

    def test_filled_triangles_exact_lengths_and_original_ids(self):
        points = ((0, 0), (3, 0), (0, 4))
        costs = {(0, 1): 3, (1, 2): 5, (0, 2): 4}
        family = geometric_family(TRIANGLE, points, costs)
        ref = family.features().value[0]
        result = family.optimal_1_cycle(ref)
        self.assertEqual(result.value["mass"], 12)
        self.assertEqual(result.value["location"]["weight_unit"], "m")
        self.assertEqual(
            result.value["location"]["simplices"][0]["original_ids"], (100, 107)
        )
        self.independent_optimum(family, ref, result)
        invalid = geometric_family(TRIANGLE, points, {**costs, (0, 1): 2})
        with self.assertRaisesRegex(ValueError, "source length"):
            invalid.optimal_1_cycle(invalid.features().value[0])
        # Source coordinates bind original IDs and dataset identities to this query.
        replaced = geometric_family(TRIANGLE, ((1, 0), (4, 0), (1, 4)), costs)
        with self.assertRaises(ValueError):
            replaced.optimal_1_cycle(ref)
        rational = geometric_family(
            TRIANGLE,
            ((0, 0), (1.5, 0), (0, 2)),
            {s: Fraction(w, 2) for s, w in costs.items()},
        )
        answer = rational.optimal_1_cycle(rational.features().value[0])
        self.assertEqual(answer.value["mass"], 6)
        # A pre-existing filled face permits changing representatives at birth.
        family = unit_family(FILLED)
        ref = next(r for r in family.features().value if r["birth_stage"] == 9)
        self.independent_optimum(family, ref, family.optimal_1_cycle(ref))

    def test_multicomponent_birth_history_is_a_support_chain(self):
        faces = ((0, 1, 4), (0, 3, 4), (1, 2, 5), (1, 4, 5), (0, 2, 3), (2, 3, 5))
        loops = ((0, 1), (1, 2), (0, 2), (3, 4), (4, 5), (3, 5))
        edges = set(s for f in faces for s in combinations(f, 2))
        stream = (
            tuple((i,) for i in range(6))
            + loops
            + tuple(sorted(edges - set(loops)))
            + faces
        )
        family = unit_family(stream)
        ref = next(r for r in family.features().value if r["birth_stage"] == 11)
        result = family.optimal_1_cycle(ref)
        self.assertEqual(set(result.value["edges"]), set(loops))
        self.assertEqual(result.value["mass"], 6)
        self.assertNotIn("polygon", result.value)
        self.assertIsNone(result.value["location"]["source_mapping_id"])
        mapped = geometric_family(
            stream,
            tuple((i, 0) for i in range(6)),
            {e: 1 for e in edges},
            weight_semantics="unit",
            unit="edge",
        )
        ref = next(r for r in mapped.features().value if r["birth_stage"] == 11)
        location = mapped.optimal_1_cycle(ref).value["location"]
        self.assertEqual(len(location["components"]), 2)
        self.assertTrue(all(e["original_ids"] for e in location["simplices"]))

    def test_budgets_cancellation_and_unsupported_domains(self):
        family = unit_family()
        ref = next(r for r in family.features().value if r["birth_stage"] == 9)
        for limits, reason in (
            (ResourceLimits(state_limit=0), "state_limit"),
            (ResourceLimits(state_limit=1), "state_limit"),
            (ResourceLimits(wall_time_limit=0), "wall_time_limit"),
            (ResourceLimits(matrix_entry_limit=0), "matrix_entry_limit"),
        ):
            result = family.optimal_1_cycle(ref, limits=limits)
            self.assertEqual(result.state, "ResourceExhausted")
            self.assertEqual(result.details["reason"], reason)
            self.assertIsNone(result.value)
            self.assertIsNone(result.exact)
            self.assertNotIn("lower_bound", result.details)
        token = CancellationToken()
        token.cancel()
        self.assertEqual(
            family.optimal_1_cycle(ref, cancellation=token).details["reason"],
            "cancelled",
        )
        self.assertEqual(
            family.optimal_1_cycle(
                ref, limits=ResourceLimits(packed_word_limit=10)
            ).state,
            "Unavailable",
        )
        for replacement in (
            replace(family, simplex_source=None),
            simplex_family(TRIANGLE, degree=0),
            simplex_family(TRIANGLE, degree=1),
        ):
            self.assertEqual(
                replacement.optimal_1_cycle(replacement.features().value[0]).state,
                "Unavailable",
            )
        points = ((0, 0), (3, 0), (0, 4))
        floating = geometric_family(
            TRIANGLE,
            points,
            {(0, 1): 3, (1, 2): 5, (0, 2): 4},
            arithmetic="FloatingPoint",
        )
        self.assertEqual(
            floating.optimal_1_cycle(floating.features().value[0]).state, "Unavailable"
        )
        for kwargs in ({"limits": {}}, {"cancellation": True}):
            with self.assertRaises(ValueError):
                family.optimal_1_cycle(ref, **kwargs)

    def test_untrusted_proofs_ties_and_independent_search_replay(self):
        # Two equal-length paths around a filled square have the same birth class.
        stream = (
            (0,),
            (1,),
            (2,),
            (3,),
            (0, 1),
            (1, 2),
            (2, 3),
            (0, 3),
            (0, 2),
            (0, 1, 2),
            (0, 2, 3),
            (1, 3),
            (0, 1, 3),
        )
        family = unit_family(stream)
        ref = next(r for r in family.features().value if r["birth_stage"] == 11)
        result = family.optimal_1_cycle(ref)
        self.independent_optimum(family, ref, result)
        self.assertEqual(result.value["chain"], (0, 1, 1, 0, 0, 1))
        window = family.windows[11]
        alternative = (1, 0, 0, 1, 0, 1)
        wrong_tie = replace(
            result,
            value={
                "chain": alternative,
                "mass": 3,
                "support": (0, 3, 5),
                "edges": ((0, 1), (0, 3), (1, 3)),
                "location": window.locate_chain(alternative),
            },
        )
        with self.assertRaisesRegex(ValidationError, "optimum_or_tie"):
            validate_optimal_1_cycle(family, ref, wrong_tie)
        for field in (
            "feature",
            "pairing",
            "chain",
            "mass",
            "bounds",
            "coverage",
            "location",
            "identity",
        ):
            bad = deepcopy(result.to_dict())
            if field == "feature":
                bad["details"]["reference"]["feature_id"] = "forged"
            elif field == "pairing":
                bad["details"]["pairing"]["birth_label"] = "forged"
            elif field == "chain":
                bad["value"]["chain"][0] ^= 1
            elif field == "mass":
                bad["value"]["mass"] = -1
            elif field == "bounds":
                bad["details"]["lower_bound"] = 0
            elif field == "coverage":
                bad["details"]["certificate"]["candidate_count"] = True
            elif field == "location":
                bad["value"]["location"]["location_id"] = "forged"
            else:
                bad["identity"]["operator_id"] = "forged"
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_optimal_1_cycle(family, ref, QueryResult.from_dict(bad))
        with patch.object(Matrix, "image_basis", return_value=()):
            with self.assertRaisesRegex(ValidationError, "coverage"):
                family.optimal_1_cycle(ref)

    def test_rank_replay_limit(self):
        stream = []
        for i in range(18):
            cells = tuple(range(3 * i, 3 * i + 3))
            stream.extend(s for size in (1, 2) for s in combinations(cells, size))
            if i < 17:
                stream.append(cells)
        family = unit_family(tuple(stream))
        ref = next(r for r in family.features().value if r["death_stage"] is None)
        result = family.optimal_1_cycle(ref)
        self.assertEqual(result.state, "Unavailable")
        self.assertIn("boundary rank", result.details["reason"])

    def test_frozen_homcloud_comparison_respects_different_objectives(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/optimal_cycles.json").read_text("utf-8")
        )
        for case in fixture["cases"]:
            stream = tuple(map(tuple, case["simplices"]))
            family = unit_family(stream)
            ref = next(
                r for r in family.features().value if r["birth_stage"] == case["birth"]
            )
            result = family.optimal_1_cycle(ref)
            window = family.windows[ref["birth_stage"]]
            edges = tuple(stream[i] for i in case["homcloud_edge_events"])
            other = tuple(
                int(s in edges) for s in stream[: case["birth"] + 1] if len(s) == 2
            )
            self.assertFalse(any(window.A.apply(other)))
            self.assertEqual(sum(other), case["homcloud_mass"])
            seed = family.resolve_feature(ref, ref["birth_stage"]).value[
                "representative"
            ]
            residual = tuple(a ^ b for a, b in zip(seed, other))
            if case["relation"] == "EqualFeasibleSet":
                self.assertEqual(family.stage(ref["birth_stage"]).betti(), 1)
                self.assertIsNotNone(window.D.solve(residual))
                self.assertEqual(result.value["mass"], case["homcloud_mass"])
            else:
                self.assertIsNone(window.D.solve(residual))
                self.assertEqual((result.value["mass"], case["homcloud_mass"]), (4, 3))

    @unittest.skipUnless(
        os.environ.get("HOMOLOGY_HOMCLOUD_SOURCE"),
        "optional pinned HomCloud source replay",
    )
    def test_live_homcloud_python_source(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/optimal_cycles.json").read_text("utf-8")
        )
        path = Path(os.environ["HOMOLOGY_HOMCLOUD_SOURCE"])
        raw = path.read_bytes()
        self.assertEqual(sha256(raw).hexdigest(), fixture["source"]["sha256"])
        # Execute upstream pure functions unchanged; exclude the unused C++ import.
        module = ast.parse(raw)
        names = {"vertices", "edges", "adjacent_vertices", "path", "search"}
        module.body = [
            n for n in module.body if isinstance(n, ast.FunctionDef) and n.name in names
        ]
        namespace = {"collections": collections}
        exec(compile(module, str(path), "exec"), namespace)
        for case in fixture["cases"]:
            stream = tuple(map(tuple, case["simplices"]))
            boundary_map = {
                "map": [
                    (
                        len(s) - 1,
                        [stream.index(face) for face in combinations(s, len(s) - 1)]
                        if len(s) > 1
                        else [],
                    )
                    for s in stream
                ]
            }
            self.assertEqual(
                namespace["search"](boundary_map, case["birth"]),
                case["homcloud_edge_events"],
            )


if __name__ == "__main__":
    unittest.main()
