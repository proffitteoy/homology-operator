"""Independent fixed-boundary enumeration and geometric upper-weight checks."""

from dataclasses import replace
from fractions import Fraction
from itertools import combinations, product
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
)


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


if __name__ == "__main__":
    unittest.main()
