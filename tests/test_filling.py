"""Independent fixed-boundary enumeration and geometric upper-weight checks."""

from dataclasses import replace
from fractions import Fraction
from itertools import combinations, product
import json
import random
import unittest
from unittest.mock import patch

from homology_operator import (
    CancellationToken,
    ChainWindow,
    InvalidInput,
    Matrix,
    QueryResult,
    ResourceLimits,
    ValidationError,
    minimum_filling,
    validate_minimum_filling,
    validate_optimal_volume,
    OperatorFamily,
)
from test_family import simplex_family, op
from test_geometry import mapped_window


def windows(D=None, weights=(1, 1), **changes):
    D = D if D is not None else Matrix.from_rows(((1, 1),))
    window = ChainWindow(
        1,
        Matrix.zero(0, D.nrows),
        D,
        (),
        tuple(f"e{i}" for i in range(D.nrows)),
        tuple(f"f{i}" for i in range(D.ncols)),
        (999,) * D.nrows,
    )
    upper = ChainWindow(
        2,
        D,
        Matrix.zero(D.ncols, 0),
        window.basis_current,
        window.basis_next,
        (),
        weights,
        unit="cost",
        source_metadata={"source": "hand-derived test costs"},
    )
    return window, replace(upper, **changes)


def geometric_windows(points, k):
    """Generate actual simplex incidences and independently measured costs."""
    vertices = tuple(range(len(points)))
    previous = tuple(combinations(vertices, k))
    current = tuple(combinations(vertices, k + 1))
    upper = tuple(combinations(vertices, k + 2))

    def incidence(rows, columns):
        return Matrix.from_rows(
            tuple(tuple(int(set(r) < set(c)) for c in columns) for r in rows)
        )

    weights = []
    for simplex in upper:
        origin = points[simplex[0]]
        vectors = [tuple(b - a for a, b in zip(origin, points[i])) for i in simplex[1:]]
        if k == 1:
            a, b = vectors
            determinant = a[0] * b[1] - a[1] * b[0]
            weights.append(Fraction(abs(determinant), 2))
        else:
            a, b, c = vectors
            determinant = (
                a[0] * (b[1] * c[2] - b[2] * c[1])
                - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])
            )
            weights.append(Fraction(abs(determinant), 6))
    window = ChainWindow(
        k,
        incidence(previous, current),
        incidence(current, upper),
        tuple(map(str, previous)),
        tuple(map(str, current)),
        tuple(map(str, upper)),
        (999,) * len(current),
    )
    filling = ChainWindow(
        k + 1,
        window.D,
        Matrix.zero(len(upper), 0),
        window.basis_current,
        window.basis_next,
        (),
        tuple(weights),
        weight_semantics="euclidean_area" if k == 1 else "euclidean_volume",
        unit="m^2" if k == 1 else "m^3",
        source_metadata={
            "source": "hand-derived Euclidean simplices",
            "points": points,
        },
    )
    return window, filling


def oracle(window, upper, z):
    """All original-coordinate chains; no production solve/kernel/mass helpers."""
    candidates = []
    for chain in product((0, 1), repeat=window.p):
        boundary = tuple(
            sum(a * b for a, b in zip(row, chain)) % 2 for row in window.D.rows
        )
        if boundary == z:
            mass = sum(w for w, bit in zip(upper.weights, chain) if bit)
            candidates.append(
                (mass, sum(bit << i for i, bit in enumerate(chain)), chain)
            )
    return min(candidates) if candidates else None


class MinimumFillingTests(unittest.TestCase):
    def test_h1_actual_areas_and_every_cycle_against_all_chains(self):
        window, upper = geometric_windows(((0, 0), (2, 0), (2, 2), (0, 2)), 1)
        self.assertEqual(upper.weights, (2,) * 4)
        for z in product((0, 1), repeat=window.n):
            if any(sum(a * b for a, b in zip(row, z)) % 2 for row in window.A.rows):
                continue
            result = minimum_filling(window, z, upper)
            expected = oracle(window, upper, z)
            self.assertEqual(result.state, "Computed")
            self.assertEqual(
                (result.value["mass"], result.value["chain"]),
                (expected[0], expected[2]),
            )
            self.assertTrue(result.details["verification"]["optimality_verified"])
            restored = QueryResult.from_dict(result.to_dict())
            self.assertEqual(restored, result)
            self.assertTrue(
                validate_minimum_filling(window, z, upper, restored)[
                    "optimality_verified"
                ]
            )
        # The square has two equal-area triangulations; retain packed-coordinate tie order.
        z = (1, 0, 1, 1, 0, 1)
        result = minimum_filling(window, z, upper)
        self.assertEqual(result.value["mass"], 4)
        self.assertEqual(result.value["chain"], oracle(window, upper, z)[2])

    def test_h2_actual_volumes_and_all_fillable_boundaries(self):
        window, upper = geometric_windows(
            ((0, 0, 0), (6, 0, 0), (0, 6, 0), (0, 0, 6), (1, 1, 1)), 2
        )
        self.assertEqual(upper.weights, (36, 6, 6, 6, 18))
        targets = {
            tuple(sum(a * b for a, b in zip(row, c)) % 2 for row in window.D.rows)
            for c in product((0, 1), repeat=window.p)
        }
        for z in targets:
            result = minimum_filling(window, z, upper)
            expected = oracle(window, upper, z)
            self.assertEqual(
                (result.value["mass"], result.value["chain"]),
                (expected[0], expected[2]),
            )
            self.assertEqual(result.details["unit"], "m^3")

    def test_rational_unbounded_integer_costs_and_unit_counting(self):
        for costs in ((10**100, 1), (Fraction(1, 7), Fraction(1, 9))):
            window, upper = windows(weights=costs)
            result = minimum_filling(window, (1,), upper)
            self.assertEqual(result.value["chain"], (0, 1))
            self.assertEqual(result.value["mass"], costs[1])
        window, upper = windows(weight_semantics="unit", unit="faces")
        result = minimum_filling(window, (1,), upper)
        self.assertEqual(result.value["chain"], (1, 0))
        self.assertEqual(result.value["mass"], 1)
        self.assertEqual(
            minimum_filling(replace(window, weights=(1,)), (1,), upper).value,
            result.value,
        )

    def test_zero_empty_and_infeasible_are_distinct(self):
        for D in (Matrix.zero(0, 0), Matrix.zero(1, 0), Matrix.zero(1, 2)):
            window, upper = windows(D, (1,) * D.ncols)
            zero = (0,) * D.nrows
            result = minimum_filling(
                window, zero, upper, limits=ResourceLimits(state_limit=0)
            )
            self.assertEqual(result.state, "Computed")
            self.assertEqual(result.value["mass"], 0)
            self.assertEqual(result.value["support"], ())
            if D.nrows:
                result = minimum_filling(window, (1,), upper)
                self.assertEqual(result.state, "Infeasible")
                self.assertIsNone(result.value)
                self.assertTrue(
                    validate_minimum_filling(
                        window, (1,), upper, QueryResult.from_dict(result.to_dict())
                    )["infeasibility_verified"]
                )
        with self.assertRaises(ValueError):
            QueryResult("Infeasible", 0)

    def test_all_small_matrices_against_brute_force_including_nonboundaries(self):
        for entries in product((0, 1), repeat=6):
            D = Matrix.from_rows((entries[:3], entries[3:]))
            window, upper = windows(D, (3, 2, 1))
            for z in product((0, 1), repeat=2):
                result = minimum_filling(window, z, upper)
                expected = oracle(window, upper, z)
                if expected is None:
                    self.assertEqual(result.state, "Infeasible")
                else:
                    self.assertEqual(
                        (result.value["mass"], result.value["chain"]),
                        (expected[0], expected[2]),
                    )

    def test_bad_weights_sources_dimensions_and_boundaries_rejected(self):
        window, upper = windows()
        for changes in (
            {"weights": (1,)},
            {"weights": (0, 1)},
            {"weights": (-1, 1)},
            {"weights": (True, 1)},
            {"weights": (float("nan"), 1)},
            {"weights": (float("inf"), 1)},
            {"source_metadata": {"source": object()}},
        ):
            with self.subTest(changes=changes), self.assertRaises(InvalidInput):
                replace(upper, **changes)
        for changes in (
            {"k": 3},
            {"A": Matrix.zero(1, 2)},
            {"basis_previous": ("wrong",)},
            {"basis_current": ("f1", "f0")},
            {"source_metadata": {}},
            {"source_metadata": {"source": " "}},
            {"source_metadata": {"source": 1}},
            {"unit": None},
            {"weight_semantics": "euclidean_volume"},
            {"weight_semantics": "unit", "weights": (1, 2)},
        ):
            with self.subTest(changes=changes), self.assertRaises(InvalidInput):
                minimum_filling(window, (1,), replace(upper, **changes))
        for z in ((1, 0), (True,), (1.0,), (2,)):
            with self.assertRaises(ValueError):
                minimum_filling(window, z, upper)
        noncycle, top = windows(Matrix.zero(1, 0), ())
        noncycle = replace(noncycle, A=Matrix.identity(1), basis_previous=("v",))
        with self.assertRaises(InvalidInput):
            minimum_filling(noncycle, (1,), top)

    def test_budget_cancellation_and_unsupported_remain_missing(self):
        window, upper = windows(weights=(10, 1))
        for limits, reason in (
            (ResourceLimits(state_limit=0), "state_limit"),
            (ResourceLimits(state_limit=1), "state_limit"),
            (ResourceLimits(wall_time_limit=0), "wall_time_limit"),
            (ResourceLimits(matrix_entry_limit=0), "matrix_entry_limit"),
        ):
            result = minimum_filling(window, (1,), upper, limits=limits)
            self.assertEqual(result.state, "ResourceExhausted")
            self.assertIsNone(result.value)
            self.assertEqual(result.details["reason"], reason)
            self.assertFalse(result.details["verification"]["optimality_verified"])
            if limits.state_limit == 1:
                self.assertEqual(result.details["candidate"], (1, 0))
                self.assertEqual(result.details["certificate_level"], "Feasible")
        self.assertEqual(
            minimum_filling(
                window, (1,), upper, limits=ResourceLimits(state_limit=2)
            ).state,
            "Computed",
        )
        token = CancellationToken()
        token.cancel()
        self.assertEqual(
            minimum_filling(window, (1,), upper, cancellation=token).details["reason"],
            "cancelled",
        )
        self.assertEqual(
            minimum_filling(
                window, (1,), replace(upper, arithmetic="FloatingPoint")
            ).state,
            "Unavailable",
        )
        self.assertEqual(
            minimum_filling(
                window, (1,), upper, limits=ResourceLimits(packed_word_limit=1)
            ).state,
            "Unavailable",
        )
        large, costs = windows(Matrix.from_rows(((1,) * 18,)), (1,) * 18)
        self.assertEqual(minimum_filling(large, (1,), costs).state, "Unavailable")
        for kwargs in ({"limits": {}}, {"cancellation": object()}):
            with self.assertRaises(ValueError):
                minimum_filling(window, (1,), upper, **kwargs)

    def test_independent_replay_and_tampered_evidence(self):
        window, upper = windows(weights=(1, 2))
        result = minimum_filling(window, (1,), upper)
        with (
            patch.object(Matrix, "solve", side_effect=AssertionError("solver used")),
            patch.object(
                Matrix, "kernel_basis", side_effect=AssertionError("solver kernel used")
            ),
        ):
            self.assertTrue(
                validate_minimum_filling(window, (1,), upper, result)[
                    "optimality_verified"
                ]
            )
        wrong = {**result.value, "chain": (0, 1), "support": (1,), "mass": Fraction(2)}
        mutations = (
            (wrong, {**result.details, "lower_bound": 2, "upper_bound": 2}),
            ({**result.value, "boundary": (0,)}, result.details),
            ({**result.value, "mass": 1.0}, result.details),
            (
                result.value,
                {
                    **result.details,
                    "certificate": {
                        "kind": "CompleteAffineEnumeration",
                        "candidate_count": 1,
                    },
                },
            ),
            (result.value, {**result.details, "certificate": {"kind": "LPRelaxation"}}),
        )
        for value, details in mutations:
            with self.assertRaises(ValidationError):
                validate_minimum_filling(
                    window, (1,), upper, replace(result, value=value, details=details)
                )
        for changed in (
            replace(upper, weights=(2, 1)),
            replace(upper, unit="other"),
            replace(upper, source_metadata={"source": "another source"}),
        ):
            with self.assertRaises(ValidationError):
                validate_minimum_filling(window, (1,), changed, result)
        tie_window, tie_upper = windows()
        tie = minimum_filling(tie_window, (1,), tie_upper)
        with self.assertRaises(ValidationError):
            validate_minimum_filling(
                tie_window,
                (1,),
                tie_upper,
                replace(tie, value={**tie.value, "chain": (0, 1), "support": (1,)}),
            )
        impossible, costs = windows(Matrix.zero(1, 1), (1,))
        no = minimum_filling(impossible, (1,), costs)
        with self.assertRaises(ValidationError):
            validate_minimum_filling(
                impossible,
                (1,),
                costs,
                replace(
                    no,
                    details={
                        **no.details,
                        "certificate": {"kind": "DualObstruction", "witness": (0,)},
                    },
                ),
            )
        with (
            patch.object(Matrix, "solve", return_value=(0, 0)),
            self.assertRaises(ValidationError),
        ):
            minimum_filling(window, (1,), upper)
        with (
            patch.object(Matrix, "kernel_basis", return_value=()),
            self.assertRaises(ValidationError),
        ):
            minimum_filling(window, (1,), upper)


class PairVolumeTests(unittest.TestCase):
    def upper(self, family, reference, weights=None):
        window = family.windows[reference["death_stage"]]
        return ChainWindow(
            window.k + 1,
            window.D,
            Matrix.zero(window.p, 0),
            window.basis_current,
            window.basis_next,
            (),
            (1,) * window.p if weights is None else weights,
            weight_semantics="custom",
            unit="cost",
            source_metadata={"source": "independent pair fixture costs"},
        )

    def oracle(self, family, ref, upper):
        # Enumerate sets of original simplex events, without production matrices.
        events = family.simplex_source["simplices"]
        offset = int(family.simplex_source["stage_convention"] == "EmptyInitial")
        order = {e["vertices"]: i + offset for i, e in enumerate(events)}
        by_label = {e["label"]: e["vertices"] for e in events}
        window = family.windows[ref["death_stage"]]
        cells = tuple(by_label[label] for label in window.basis_next)
        birth, death = ref["birth_stage"], ref["death_stage"]
        candidates = []
        for bits in product((0, 1), repeat=len(cells)):
            selected = {s for s, bit in zip(cells, bits) if bit}
            if events[death - offset]["vertices"] not in selected:
                continue
            if any(
                order[s] != death and not birth < order[s] < death for s in selected
            ):
                continue
            boundary = set()
            for cell in selected:
                for face in combinations(cell, len(cell) - 1):
                    boundary.symmetric_difference_update({face})
            if events[birth - offset]["vertices"] not in boundary:
                continue
            if any(order[s] > birth for s in boundary):
                continue
            mass = sum(w for w, bit in zip(upper.weights, bits) if bit)
            key = (mass, sum(bit << i for i, bit in enumerate(bits)))
            candidates.append((key, bits, boundary))
        return sorted(candidates)

    def test_independent_all_pair_enumeration_total_orders_ties_and_upper_objective(
        self,
    ):
        rng = random.Random(100)
        nontrivial = False
        different_boundary_objective = False
        replay_attacked = False
        changed_history_class = False
        for trial in range(4):
            edges = list(combinations(range(5), 2))
            faces = list(combinations(range(5), 3))
            rng.shuffle(edges)
            rng.shuffle(faces)
            cells = [(v,) for v in range(5)] + edges + faces
            family = simplex_family(
                cells, 1, empty_initial=bool(trial % 2), reverse=bool(trial % 2)
            )
            before = family.barcode()
            for ref in family.features().value:
                if ref["death_stage"] is None:
                    continue
                weights = tuple(
                    Fraction(rng.randrange(1, 8), 3)
                    for _ in family.windows[ref["death_stage"]].basis_next
                )
                for upper in (
                    self.upper(family, ref),
                    self.upper(family, ref, weights),
                ):
                    expected = self.oracle(family, ref, upper)
                    result = family.optimal_volume(ref, upper)
                    self.assertEqual(result.state, "Computed")
                    self.assertEqual(
                        (result.value["mass"], result.value["chain"]),
                        (expected[0][0][0], expected[0][1]),
                    )
                    self.assertEqual(
                        set(result.value["boundary_simplices"]), expected[0][2]
                    )
                    self.assertEqual(
                        result.details["verification"]["replayed_candidates"],
                        len(expected),
                    )
                    nontrivial |= len(expected) > 1
                    different_boundary_objective |= len(expected[0][2]) > min(
                        len(x[2]) for x in expected
                    )
                    self.assertTrue(
                        validate_optimal_volume(family, ref, upper, result)[
                            "optimality_verified"
                        ]
                    )
                    changed_history_class |= not result.value["same_history_class"]
                    if len(expected) > 1 and not replay_attacked:
                        replay_attacked = True
                        chain = expected[-1][1]
                        window = family.windows[ref["death_stage"]]
                        boundary = window.D.apply(chain)
                        by_label = {
                            e["label"]: e["vertices"]
                            for e in family.simplex_source["simplices"]
                        }
                        at_birth = tuple(
                            boundary[window.basis_current.index(label)]
                            for label in family.windows[
                                ref["birth_stage"]
                            ].basis_current
                        )
                        historical = family.resolve_feature(
                            ref, ref["birth_stage"]
                        ).value["representative"]
                        value = {
                            "chain": chain,
                            "boundary": boundary,
                            "support": tuple(i for i, bit in enumerate(chain) if bit),
                            "mass": expected[-1][0][0],
                            "filling_location": upper.locate_chain(chain),
                            "boundary_location": window.locate_chain(boundary),
                            "filling_simplices": tuple(
                                by_label[label]
                                for label, bit in zip(window.basis_next, chain)
                                if bit
                            ),
                            "boundary_simplices": tuple(
                                by_label[label]
                                for label, bit in zip(window.basis_current, boundary)
                                if bit
                            ),
                            "same_history_class": family.stage(
                                ref["birth_stage"]
                            ).P.apply(at_birth)
                            == historical,
                        }
                        details = {
                            k: v
                            for k, v in result.details.items()
                            if k != "verification"
                        }
                        details.update(
                            lower_bound=value["mass"], upper_bound=value["mass"]
                        )
                        with self.assertRaisesRegex(
                            ValidationError, "volume_optimum_or_tie"
                        ):
                            validate_optimal_volume(
                                family,
                                ref,
                                upper,
                                replace(result, value=value, details=details),
                            )
                        with (
                            patch.object(Matrix, "kernel_basis", return_value=()),
                            self.assertRaisesRegex(ValidationError, "volume_coverage"),
                        ):
                            family.optimal_volume(ref, upper)
            self.assertEqual(family.barcode(), before)
        self.assertTrue(nontrivial)
        self.assertTrue(different_boundary_objective)
        self.assertTrue(replay_attacked)
        self.assertTrue(changed_history_class)

    def test_fixed_boundary_and_pair_volume_have_different_domains(self):
        cells = [(i,) for i in range(4)] + [
            (0, 1),
            (1, 2),
            (0, 2),
            (0, 1, 2),
            (2, 3),
            (0, 3),
            (0, 2, 3),
        ]
        family = simplex_family(cells, 1)
        ref = next(r for r in family.features().value if r["birth_stage"] == 9)
        upper = self.upper(family, ref)
        result = family.optimal_volume(ref, upper)
        self.assertEqual(result.value["filling_simplices"], ((0, 2, 3),))
        window = family.windows[ref["death_stage"]]
        outer = {(0, 1), (1, 2), (2, 3), (0, 3)}
        simplices = {
            e["label"]: e["vertices"] for e in family.simplex_source["simplices"]
        }
        z = tuple(int(simplices[label] in outer) for label in window.basis_current)
        fixed = minimum_filling(window, z, upper)
        self.assertEqual((result.value["mass"], fixed.value["mass"]), (1, 2))
        self.assertNotEqual(result.value["boundary"], z)
        self.assertTrue(result.value["same_history_class"])

    def test_h1_h2_actual_geometry_source_and_wire_recovery(self):
        for k, points, mass in (
            (1, ((0, 0), (3, 0), (0, 4)), Fraction(6)),
            (2, ((0, 0, 0), (2, 0, 0), (0, 3, 0), (0, 0, 4)), Fraction(4)),
        ):
            n = len(points)
            cells = tuple(
                s for degree in range(1, n + 1) for s in combinations(range(n), degree)
            )
            order = tuple(f"event{i}" for i in range(len(cells)))
            windows = tuple(
                mapped_window(points, cells[: i + 1], k, stage=i, order=order)
                for i in range(len(cells))
            )
            family = OperatorFamily(
                tuple(range(len(cells))),
                windows,
                tuple(op(w) for w in windows),
                simplex_source={
                    "stage_convention": "AfterInsertion",
                    "simplices": [
                        {"vertices": s, "label": "s" + ",".join(map(str, s))}
                        for s in cells
                    ],
                },
            )
            ref = next(
                r for r in family.features().value if r["death_stage"] is not None
            )
            upper = mapped_window(
                points,
                cells,
                k + 1,
                stage=ref["death_stage"],
                order=order,
                weights=(mass,),
                weight_semantics="euclidean_area" if k == 1 else "euclidean_volume",
                unit=f"m^{k + 1}",
            )
            upper = replace(
                upper,
                source_metadata={
                    **upper.source_metadata,
                    "source": "determinants: 3*4/2 or 2*3*4/6",
                },
            )
            result = family.optimal_volume(ref, upper)
            self.assertEqual(result.value["mass"], mass)
            self.assertEqual(result.identity, family.stage(ref["death_stage"]).identity)
            location = result.value["filling_location"]
            self.assertEqual(
                location["simplices"][0]["original_ids"],
                tuple(100 + 7 * i for i in range(n)),
            )
            self.assertEqual(location["simplices"][0]["coordinates"], points)
            self.assertEqual(location["weight_unit"], f"m^{k + 1}")
            restored = QueryResult.from_dict(json.loads(json.dumps(result.to_dict())))
            recovered = family.to_result().to_family()
            self.assertTrue(
                validate_optimal_volume(recovered, ref, upper, restored)[
                    "optimality_verified"
                ]
            )
            for key, value in (
                (
                    "vertices",
                    {
                        **upper.source_metadata["source_mapping"]["vertices"],
                        "0": {"original_id": 999, "coordinates": points[0]},
                    },
                ),
                ("source_hash", "a" * 64),
            ):
                changed = replace(
                    upper,
                    source_metadata={
                        **upper.source_metadata,
                        "source_mapping": {
                            **upper.source_metadata["source_mapping"],
                            key: value,
                        },
                    },
                )
                with self.assertRaises(ValueError):
                    family.optimal_volume(ref, changed)
            changed_location = {**location, "source_hash": "b" * 64}
            with self.assertRaises(ValidationError):
                validate_optimal_volume(
                    family,
                    ref,
                    upper,
                    replace(
                        result,
                        value={**result.value, "filling_location": changed_location},
                    ),
                )

    def square(self):
        cells = [(v,) for v in range(4)] + [
            (0, 1),
            (1, 2),
            (2, 3),
            (0, 3),
            (0, 2),
            (0, 1, 2),
            (0, 2, 3),
        ]
        family = simplex_family(cells, 1)
        ref = next(r for r in family.features().value if r["birth_stage"] == 7)
        return family, ref, self.upper(family, ref)

    def test_infinite_unavailable_invalid_upper_and_foreign_references(self):
        infinite = simplex_family([(0,), (1,), (2,), (0, 1), (1, 2), (0, 2)], 1)
        ref = infinite.features().value[0]
        result = infinite.optimal_volume(ref)
        self.assertEqual(
            (result.state, result.value, result.exact), ("EmptyDomain", None, None)
        )
        self.assertEqual(result.details["applicability"], "NotApplicable")
        family, ref, upper = self.square()
        for changed in (
            None,
            "costs",
            replace(upper, unit=None),
            replace(upper, source_metadata={}),
            replace(upper, A=Matrix.zero(upper.m, upper.n)),
            replace(upper, basis_current=tuple(reversed(upper.basis_current))),
        ):
            with self.assertRaises(ValueError):
                family.optimal_volume(ref, changed)
        plain = replace(family, simplex_source=None)
        plain_ref = next(
            r for r in plain.features().value if r["death_stage"] is not None
        )
        self.assertEqual(plain.optimal_volume(plain_ref).state, "Unavailable")
        h0 = simplex_family([(0,), (1,), (0, 1)])
        self.assertEqual(h0.optimal_volume(h0.features().value[1]).state, "Unavailable")
        for wrong in ({**ref, "birth_stage": True}, {**ref, "history_id": "forged"}):
            with self.assertRaises(ValueError):
                family.optimal_volume(wrong, upper)
        other, other_ref, _ = self.square()
        with self.assertRaises(ValueError):
            other.optimal_volume(ref, upper)
        result = family.optimal_volume(ref, upper)
        with self.assertRaises(ValidationError):
            validate_optimal_volume(other, other_ref, upper, result)
        floating = replace(upper, weights=(1.0,) * upper.n, arithmetic="FloatingPoint")
        self.assertEqual(family.optimal_volume(ref, floating).state, "Unavailable")
        for kwargs in ({"limits": {}}, {"cancellation": True}):
            with self.assertRaises(ValueError):
                family.optimal_volume(ref, upper, **kwargs)

    def test_resource_checkpoints_candidates_and_replay_domain(self):
        family, ref, upper = self.square()
        for limits, reason in (
            (ResourceLimits(state_limit=0), "state_limit"),
            (ResourceLimits(wall_time_limit=0), "wall_time_limit"),
            (ResourceLimits(matrix_entry_limit=0), "matrix_entry_limit"),
        ):
            result = family.optimal_volume(ref, upper, limits=limits)
            self.assertEqual(
                (result.state, result.details["reason"]), ("ResourceExhausted", reason)
            )
            self.assertIsNone(result.value)
        token = CancellationToken()
        token.cancel()
        self.assertEqual(
            family.optimal_volume(ref, upper, cancellation=token).details["reason"],
            "cancelled",
        )
        self.assertEqual(
            family.optimal_volume(
                ref, upper, limits=ResourceLimits(packed_word_limit=100)
            ).state,
            "Unavailable",
        )
        # Interrupt after one evaluated candidate, preserving feasibility only.
        from homology_operator.solver import _Budget, _Exhausted

        step = _Budget.step

        def stop_after_candidate(budget, count=1):
            if budget.states:
                raise _Exhausted("cancelled")
            return step(budget, count)

        with patch.object(_Budget, "step", stop_after_candidate):
            result = family.optimal_volume(ref, upper)
        self.assertEqual(result.details["certificate_level"], "Feasible")
        self.assertTrue(result.details["verification"]["feasibility_verified"])
        self.assertFalse(result.details["verification"]["optimality_verified"])
        with patch.object(Matrix, "kernel_basis", return_value=((0,),) * 17):
            self.assertEqual(family.optimal_volume(ref, upper).state, "Unavailable")

    def test_independent_replay_rejects_anchor_coefficients_proof_and_source_tampering(
        self,
    ):
        family, ref, upper = self.square()
        result = family.optimal_volume(ref, upper)
        with (
            patch.object(Matrix, "solve", side_effect=AssertionError("solver used")),
            patch.object(
                Matrix, "kernel_basis", side_effect=AssertionError("search kernel used")
            ),
        ):
            self.assertTrue(
                validate_optimal_volume(family, ref, upper, result)[
                    "optimality_verified"
                ]
            )
        for value in (
            {**result.value, "chain": (1, 0)},
            {**result.value, "chain": (0, 1)},
            {**result.value, "boundary": (0,) * len(result.value["boundary"])},
            {**result.value, "mass": float(result.value["mass"])},
            {**result.value, "same_history_class": False},
            {**result.value, "filling_simplices": ((9, 10, 11),)},
        ):
            with self.assertRaises(ValidationError):
                validate_optimal_volume(
                    family, ref, upper, replace(result, value=value)
                )
        for changes in (
            {"problem_id": "forged"},
            {"allowed_indices": ()},
            {"birth_index": 0},
            {"certificate": {"kind": "LPRelaxation"}},
            {
                "certificate": {
                    "kind": "CompletePairAffineEnumeration",
                    "candidate_count": 2,
                }
            },
            {"verification": {"optimality_verified": True}},
        ):
            with self.assertRaises(ValidationError):
                validate_optimal_volume(
                    family,
                    ref,
                    upper,
                    replace(result, details={**result.details, **changes}),
                )
        for changed in (
            replace(upper, weights=(2, 1)),
            replace(upper, unit="area"),
            replace(upper, source_metadata={"source": "other"}),
        ):
            with self.assertRaises(ValidationError):
                validate_optimal_volume(family, ref, changed, result)
        with (
            patch.object(Matrix, "solve", return_value=(0,)),
            self.assertRaises(ValidationError),
        ):
            family.optimal_volume(ref, upper)


if __name__ == "__main__":
    unittest.main()
