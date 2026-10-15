from dataclasses import replace
from fractions import Fraction
import unittest
from collections import Counter
from hashlib import sha256
import json
import random
from unittest.mock import patch
from itertools import product
from pathlib import Path

from homology_operator import (
    ChainWindow,
    FeasibleSolver,
    HomologyOperator,
    Matrix,
    OperatorFamily,
    OperatorFamilyResult,
    OperatorResult,
    QueryResult,
    ResourceLimits,
    ProjectionProblem,
)
from homology_operator.chain import matrix_from_data


def op(window):
    return HomologyOperator(window, FeasibleSolver().solve(ProjectionProblem(window)))


def merge_family():
    first = ChainWindow(
        0, Matrix.zero(0, 2), Matrix.zero(2, 0), (), ("a", "b"), (), (10, 1)
    )
    second = replace(first, D=Matrix.from_rows(((1,), (1,))), basis_next=("e",))
    return OperatorFamily(
        (0, 1, 1), (first, second, second), (op(first), op(second), op(second))
    )


class FamilyInputTests(unittest.TestCase):
    def test_ordered_stages_duplicates_and_empty_chain(self):
        family = merge_family()
        self.assertEqual(family.status, "Ready")
        self.assertEqual(family.stage(0).betti(), 2)
        self.assertEqual(family.stage(1).betti(), 1)
        self.assertEqual(family.inclusion(0, 2), Matrix.identity(2))
        empty = ChainWindow(1, Matrix.zero(0, 0), Matrix.zero(0, 0), (), (), (), ())
        self.assertEqual(
            OperatorFamily((Fraction(0),), (empty,), (op(empty),)).stage(0).betti(), 0
        )
        with self.assertRaises(ValueError):
            replace(family, scales=(1, 0, 2))
        for scales in ((0, float("nan"), 1), (0, True, 1), {0, 1, 2}, ()):
            with self.subTest(scales=scales), self.assertRaises(ValueError):
                replace(family, scales=scales)
        with self.assertRaises(ValueError):
            family.stage(True)

    def test_invalid_chain_inclusion_and_stage_identity(self):
        family = merge_family()
        first, second = family.windows[:2]
        for target in (
            replace(second, basis_current=("x", "b")),
            replace(second, A=Matrix.from_rows(((1, 1),)), basis_previous=("v",)),
            replace(second, k=1),
        ):
            with self.subTest(target=target), self.assertRaises(ValueError):
                OperatorFamily((0, 1), (first, target), (op(first), op(target)))
        with self.assertRaises(ValueError):
            replace(
                family, operators=(family.stage(1), family.stage(1), family.stage(2))
            )
        for i, j in ((1, 0), (-1, 0), (0, 3)):
            with self.assertRaises(ValueError):
                family.inclusion(i, j)

    def test_weight_policy_is_explicit(self):
        family = merge_family()
        first, second = family.windows[:2]
        changed = replace(second, weights=(1, 20))
        with self.assertRaises(ValueError):
            OperatorFamily((0, 1), (first, changed), (op(first), op(changed)))
        variable = OperatorFamily(
            (0, 1), (first, changed), (op(first), op(changed)), "Variable"
        )
        self.assertNotEqual(variable.identity, family.identity)
        with self.assertRaises(ValueError):
            replace(variable, terminal_extension="Unknown")

    def test_failed_stage_remains_partial(self):
        family = merge_family()
        failure = OperatorResult(
            None,
            family.windows[1],
            None,
            {"status": "ResourceExhausted", "certificate_level": None},
            {},
            {"diagnostic": "budget"},
            "ResourceExhausted",
        )
        partial = replace(family, operators=(family.stage(0), failure, family.stage(2)))
        self.assertEqual(partial.status, "Partial")
        self.assertEqual(partial.stage(1).status, "ResourceExhausted")
        self.assertIsNone(partial.stage(1).projection)
        self.assertEqual(partial.inclusion(0, 1), Matrix.identity(2))


class TransportTests(unittest.TestCase):
    def test_rank_table_composes_adjacent_maps_with_the_same_interval_ranks(self):
        family = merge_family()
        expected = {
            f"{i}:{j}": family.transport_rank(i, j).value
            for i in range(3)
            for j in range(i, 3)
        }
        original = OperatorFamily._coordinate_action
        intervals = []

        def adjacent(owner, i, j):
            intervals.append((i, j))
            return original(owner, i, j)

        with patch.object(OperatorFamily, "_coordinate_action", adjacent):
            actual = family.rank_table()
        self.assertEqual(actual.value, expected)
        self.assertEqual(intervals, [(0, 1), (1, 2)])

    def test_identity_composition_rank_and_original_chain_action(self):
        family = merge_family()
        for i in range(3):
            self.assertEqual(
                matrix_from_data(family.transport(i, i).value["action"]),
                Matrix.identity(family.stage(i).betti()),
            )
            for j in range(i, 3):
                result = family.transport(i, j)
                self.assertEqual(result.identity, family.stage(j).identity)
                self.assertEqual(
                    result.details["source_identity"], family.stage(i).identity
                )
                self.assertEqual(family.transport_certificate(i, j).state, "Computed")
                for middle in range(i, j + 1):
                    direct = matrix_from_data(result.value["action"])
                    composed = matrix_from_data(
                        family.transport(middle, j).value["action"]
                    ) @ matrix_from_data(family.transport(i, middle).value["action"])
                    self.assertEqual(direct, composed)
        self.assertEqual(family.transport_rank(0, 2).value, 1)
        chain = matrix_from_data(family.transport(0, 1).value["chain_action"])
        self.assertEqual(chain, family.stage(1).P)

    def test_same_betti_different_maps_and_quotient_rank(self):
        first = ChainWindow(
            1, Matrix.zero(0, 1), Matrix.zero(1, 0), (), ("a",), (), (1,)
        )
        for boundary, expected in ((((1,), (0,)), 0), (((0,), (1,)), 1)):
            second = ChainWindow(
                1,
                Matrix.zero(0, 2),
                Matrix.from_rows(boundary),
                (),
                ("a", "b"),
                ("f",),
                (1, 1),
            )
            family = OperatorFamily((0, 1), (first, second), (op(first), op(second)))
            self.assertEqual([stage.betti() for stage in family.operators], [1, 1])
            self.assertEqual(family.transport_rank(0, 1).value, expected)
            # Enumerate image cosets under the coordinate inclusion independently.
            boundaries = {
                tuple(
                    sum(row[c] * bits[c] for c in range(second.p)) % 2
                    for row in second.D.rows
                )
                for bits in product((0, 1), repeat=second.p)
            }
            cosets = {
                min(
                    tuple(a ^ b for a, b in zip((bit, 0), boundary))
                    for boundary in boundaries
                )
                for bit in (0, 1)
            }
            self.assertEqual(len(cosets).bit_length() - 1, expected)

    def test_partial_transport_is_missing_not_zero(self):
        family = merge_family()
        failure = OperatorResult(
            None,
            family.windows[1],
            None,
            {"status": "ResourceExhausted"},
            {},
            {},
            "ResourceExhausted",
        )
        partial = replace(family, operators=(family.stage(0), failure, family.stage(2)))
        self.assertEqual(partial.transport_rank(0, 1).state, "ResourceExhausted")
        self.assertIsNone(partial.transport_rank(0, 1).value)
        self.assertEqual(partial.transport(0, 2).state, "Computed")
        self.assertEqual(partial.transport_certificate(0, 2).state, "Unavailable")


class TrackingTests(unittest.TestCase):
    def test_float_ratio_product_overflow_and_zero_queries(self):
        first = ChainWindow(
            1,
            Matrix.zero(0, 1),
            Matrix.zero(1, 0),
            (),
            ("a",),
            (),
            (1e-300,),
            arithmetic="FloatingPoint",
        )
        second = replace(first, weights=(1e300,))
        family = OperatorFamily(
            (0, 1), (first, second), (op(first), op(second)), "Variable"
        )
        for x in ((0,), (1,)):
            result = family.endpoint_mass_bound(x, 0, 1)
            self.assertEqual(result.state, "Unavailable")
            self.assertIsNone(result.value)
            self.assertEqual(result.details["reason"], "NumericalFailure")
        source = ChainWindow(
            0,
            Matrix.zero(0, 2),
            Matrix.zero(2, 0),
            (),
            ("a", "b"),
            (),
            (1e-100, 1e250),
            arithmetic="FloatingPoint",
        )
        target = replace(
            source,
            D=Matrix.from_rows(((1,), (1,))),
            basis_next=("e",),
            weights=(1.0, 1e250),
        )
        family = OperatorFamily(
            (0, 1), (source, target), (op(source), op(target)), "Variable"
        )
        self.assertEqual(family.stage(1).stretch().state, "Computed")
        overflow = family.endpoint_mass_bound((0, 1), 0, 1)
        self.assertEqual(overflow.state, "Unavailable")
        self.assertEqual(overflow.details["reason"], "NumericalFailure")
        zero = family.endpoint_mass_bound((0, 0), 0, 1)
        self.assertEqual(zero.state, "Computed")
        self.assertEqual(zero.value["mass_bound"], 0)

    def test_direct_multistep_death_merger_and_support(self):
        family = merge_family()
        for x in product((0, 1), repeat=2):
            first = family.track_class(x, 0, 1).value
            self.assertEqual(
                family.track_class(first, 1, 2).value, family.track_class(x, 0, 2).value
            )
            self.assertEqual(
                family.track_class(x, 0, 2).identity, family.stage(2).identity
            )
            self.assertEqual(
                family.track_support(x, 0, 2).value, family.stage(2).support(first)
            )
            bound = family.endpoint_mass_bound(x, 0, 2)
            self.assertTrue(bound.exact)
            self.assertTrue(bound.value["bound_verified"])
            self.assertEqual(bound.value["weight_change_factor"], 1)
            self.assertLessEqual(
                family.track_mass(x, 0, 2).value, bound.value["mass_bound"]
            )
        self.assertEqual(
            family.track_class((1, 0), 0, 1).value,
            family.track_class((0, 1), 0, 1).value,
        )
        self.assertEqual(family.track_class((1, 1), 0, 1).value, (0, 0))
        self.assertEqual(family.track_mass((1, 1), 0, 1).value, 0)
        self.assertEqual(family.track_support((1, 1), 0, 1).value, ())
        self.assertEqual(family.track_shared_support((1, 0), (0, 1), 0, 1).value, (0,))
        self.assertEqual(family.track_union_support((1, 0), (0, 1), 0, 1).value, (0,))

    def test_variable_weights_numerical_bounds_and_resource_failure(self):
        family = merge_family()
        first, second = family.windows[:2]
        changed = replace(second, weights=(20, 2))
        variable = OperatorFamily(
            (0, 1), (first, changed), (op(first), op(changed)), "Variable"
        )
        result = variable.endpoint_mass_bound((0, 1), 0, 1)
        self.assertEqual(result.value["weight_change_factor"], 2)
        self.assertEqual(result.value["mass_bound"], 20)
        self.assertEqual(variable.track_mass((0, 1), 0, 1).value, 20)
        missing = variable.endpoint_mass_bound(
            (0, 1), 0, 1, ResourceLimits(state_limit=0)
        )
        self.assertEqual(missing.state, "ResourceExhausted")
        self.assertIsNone(missing.value)
        floating = replace(changed, weights=(20.0, 2.0), arithmetic="FloatingPoint")
        numeric = OperatorFamily(
            (0, 1), (first, floating), (op(first), op(floating)), "Variable"
        )
        observed = numeric.endpoint_mass_bound((0, 1), 0, 1)
        self.assertFalse(observed.exact)
        self.assertIsNone(observed.value["bound_verified"])

    def test_tracking_rejects_noncycles_and_wrong_coordinates(self):
        window = ChainWindow(
            1, Matrix.identity(1), Matrix.zero(1, 0), ("v",), ("e",), (), (1,)
        )
        family = OperatorFamily((0,), (window,), (op(window),))
        for x in ((1,), (), (2,)):
            with self.subTest(x=x), self.assertRaises(ValueError):
                family.track_class(x, 0, 0)


class FamilySerializationTests(unittest.TestCase):
    def test_queried_failures_survive_with_and_without_partial_identity(self):
        family = merge_family()
        for status, solver_status in (
            ("InvalidInput", "InvalidProblem"),
            ("SolverFailed", "NumericalFailure"),
            ("ResourceExhausted", "ResourceExhausted"),
            ("Unavailable", "Unavailable"),
            ("InternalValidationFailed", "InternalError"),
        ):
            for with_identity in (False, True):
                with self.subTest(status=status, with_identity=with_identity):
                    identity = {
                        key: family.windows[1].identity()[key]
                        for key in ("input_id", "basis_id", "weight_id")
                    }
                    identity["solver_run_id"] = "failed-run"
                    failure = OperatorResult(
                        identity if with_identity else None,
                        family.windows[1],
                        None,
                        {
                            "status": solver_status,
                            "certificate_level": None,
                            "solver_run_id": "failed-run",
                        },
                        {},
                        {"diagnostic": status},
                        status,
                    )
                    partial = replace(
                        family, operators=(family.stage(0), failure, family.stage(2))
                    )
                    transport, rank = (
                        partial.transport(0, 1),
                        partial.transport_rank(0, 1),
                    )
                    expected = (
                        "ResourceExhausted"
                        if status == "ResourceExhausted"
                        else "Unavailable"
                    )
                    self.assertEqual(transport.state, expected)
                    self.assertIsNone(rank.value)
                    result = partial.to_result()
                    restored = OperatorFamilyResult.from_json(result.to_json())
                    data = restored.to_dict()
                    self.assertEqual(
                        QueryResult.from_dict(data["transports"]["0:1"]), transport
                    )
                    self.assertEqual(
                        QueryResult.from_dict(data["rank_readout"]["0:1"]), rank
                    )
                    self.assertEqual(restored, result)
                    self.assertEqual(
                        data["transports"]["0:1"]["details"]["target_identity"],
                        dict(identity) if with_identity else None,
                    )
                    self.assertNotIn("0:2", data["transports"])
                    self.assertEqual(result.to_json(), partial.to_result().to_json())

    def test_lossless_snapshot_and_restored_actions(self):
        family = merge_family()
        family = replace(family, scales=(Fraction(0), Fraction(1, 2), Fraction(1, 2)))
        family.transport(0, 2)
        family.track_class((1, 1), 0, 2)
        family.track_mass((1, 0), 0, 1)
        family.track_support((0, 1), 0, 2)
        result = family.to_result()
        frozen = result.to_json()
        restored = OperatorFamilyResult.from_json(frozen)
        self.assertEqual(result, restored)
        self.assertEqual(result.stage_results, restored.stage_results)
        self.assertEqual(restored.to_family().identity, family.identity)
        self.assertEqual(restored.to_family().barcode(), family.barcode())
        family.track_mass((0, 0), 1, 2)
        self.assertEqual(result.to_json(), frozen)
        with self.assertRaises(TypeError):
            result.data["status"] = "Partial"

    def test_readout_identity_action_rank_and_barcode_tampering(self):
        family = merge_family()
        family.transport(0, 1)
        family.track_mass((0, 1), 0, 1)
        record = family.to_result()
        for field in (
            "identity",
            "projection",
            "rank",
            "barcode",
            "tracking",
            "provenance",
            "scale",
        ):
            data = record.to_dict()
            if field == "identity":
                data["transports"]["0:1"]["details"]["source_identity"][
                    "operator_id"
                ] = "wrong"
            elif field == "projection":
                data["transports"]["0:1"]["value"]["chain_action"]["rows"][0][0] ^= 1
            elif field == "rank":
                data["rank_readout"]["0:1"]["value"] = 0
            elif field == "barcode":
                data["barcode_readout"]["value"][0]["multiplicity"] = 99
            elif field == "tracking":
                next(
                    value
                    for value in data["tracking_readout"].values()
                    if value["details"]["query"] == "track_mass"
                )["value"] = 99
            elif field == "provenance":
                data["provenance"]["oracle_used_for_result"] = True
            else:
                data["scales"][1] = 100
            with self.subTest(field=field), self.assertRaises(ValueError):
                OperatorFamilyResult.from_dict(data)

    def test_partial_roundtrip_and_zero_remain_distinct(self):
        family = merge_family()
        failure = OperatorResult(
            None,
            family.windows[1],
            None,
            {"status": "ResourceExhausted"},
            {},
            {"$fraction": [1, 0]},
            "ResourceExhausted",
        )
        partial = replace(family, operators=(family.stage(0), failure, family.stage(2)))
        partial.track_mass((1, 1), 0, 1)
        result = partial.to_result()
        restored = OperatorFamilyResult.from_json(result.to_json())
        self.assertEqual(result, restored)
        self.assertEqual(restored.status, "Partial")
        self.assertEqual(restored.stage_results[1].status, "ResourceExhausted")
        self.assertEqual(
            restored.to_family().track_mass((1, 1), 0, 1).state, "ResourceExhausted"
        )
        self.assertEqual(family.track_mass((1, 1), 0, 1).value, 0)
        self.assertIsNone(restored.to_family().track_mass((1, 1), 0, 1).value)

    def test_schema_json_and_weight_mixing_rejected(self):
        record = merge_family().to_result()
        data = record.to_dict()
        data["schema_version"] = 3
        with self.assertRaises(ValueError):
            OperatorFamilyResult.from_dict(data)
        data = record.to_dict()
        data["windows"]["stages"][1]["weights"][0]["numerator"] = 5
        with self.assertRaises(ValueError):
            OperatorFamilyResult.from_dict(data)
        for text in ('{"schema_version":1,"schema_version":1}', '{"value":NaN}'):
            with self.assertRaises(ValueError):
                OperatorFamilyResult.from_json(text)


class BarcodeTests(unittest.TestCase):
    def test_merge_essential_duplicate_and_rank_reconstruction(self):
        family = merge_family()
        result = family.barcode()
        self.assertEqual(result.state, "Computed")
        self.assertEqual(
            [
                (x["birth_stage"], x["death_stage"], x["multiplicity"])
                for x in result.value
            ],
            [(0, 1, 1), (0, None, 1)],
        )
        self.assertFalse(result.details["oracle_used_for_result"])
        for i in range(3):
            for j in range(i, 3):
                rank = sum(
                    x["multiplicity"]
                    for x in result.value
                    if x["birth_stage"] <= i
                    and (x["death_stage"] is None or j < x["death_stage"])
                )
                self.assertEqual(rank, family.transport_rank(i, j).value)

    def test_same_betti_different_barcode_and_zero_scale_length(self):
        first = ChainWindow(
            1, Matrix.zero(0, 1), Matrix.zero(1, 0), (), ("a",), (), (1,)
        )
        dead = ChainWindow(
            1,
            Matrix.zero(0, 2),
            Matrix.from_rows(((1,), (0,))),
            (),
            ("a", "b"),
            ("f",),
            (1, 1),
        )
        alive = replace(dead, D=Matrix.from_rows(((0,), (1,))))
        killed = OperatorFamily((1, 1), (first, dead), (op(first), op(dead))).barcode()
        kept = OperatorFamily((1, 1), (first, alive), (op(first), op(alive))).barcode()
        self.assertEqual(
            [(x["birth_stage"], x["death_stage"]) for x in killed.value],
            [(0, 1), (1, None)],
        )
        self.assertEqual(
            [(x["birth_stage"], x["death_stage"]) for x in kept.value], [(0, None)]
        )
        self.assertTrue(killed.value[0]["zero_scale_length"])
        self.assertFalse(kept.value[0]["zero_scale_length"])

    def test_empty_barcode_and_failure_are_distinct(self):
        empty = ChainWindow(1, Matrix.zero(0, 0), Matrix.zero(0, 0), (), (), (), ())
        family = OperatorFamily((0,), (empty,), (op(empty),))
        self.assertEqual(family.barcode().value, ())
        failure = OperatorResult(
            None, empty, None, {"status": "Unavailable"}, {}, {}, "Unavailable"
        )
        missing = replace(family, operators=(failure,)).barcode()
        self.assertEqual(missing.state, "Unavailable")
        self.assertIsNone(missing.value)


class AdjacentFiltrationTests(unittest.TestCase):
    def test_historical_merge_generator_dies_and_stage_bases_commute(self):
        family = merge_family()
        before = [stage.to_result().to_json() for stage in family.operators]
        bars = family.barcode_basis().value
        # Both original basis vectors have the same image. The dead interval
        # must use their sum, not retain the dependent nonzero image's source.
        dead = next(bar for bar in bars if bar["death_stage"] == 1)
        self.assertEqual(dead["vectors"][0]["representative"], (1, 1))
        for i in range(len(family.windows)):
            active = [
                vector
                for bar in bars
                for vector in bar["vectors"]
                if vector["stage"] == i
            ]
            basis = Matrix.from_columns(
                (v["representative"] for v in active), family.windows[i].n
            )
            self.assertEqual(basis.rank(), family.stage(i).betti())
            for vector in active:
                self.assertEqual(vector["identity"], family.stage(i).identity)
        for bar in bars:
            for left, right in zip(bar["vectors"], bar["vectors"][1:]):
                self.assertEqual(
                    family.track_class(
                        left["representative"], left["stage"], right["stage"]
                    ).value,
                    right["representative"],
                )
            if bar["death_stage"] is not None:
                last = bar["vectors"][-1]
                self.assertEqual(
                    family.track_class(
                        last["representative"], last["stage"], bar["death_stage"]
                    ).value,
                    (0, 0),
                )
        self.assertEqual(
            before, [stage.to_result().to_json() for stage in family.operators]
        )
        snapshot = family.to_result()
        self.assertEqual(snapshot.to_json(), snapshot.to_family().to_result().to_json())
        wire = snapshot.to_dict()
        wire["barcode_basis_readout"]["value"][0]["vectors"][0]["coordinates"][0] ^= 1
        with self.assertRaises(ValueError):
            OperatorFamilyResult.from_dict(wire)

    def test_long_barcode_only_adjacent_actions_and_bounded_cache(self):
        small = merge_family()
        window, operator = small.windows[0], small.stage(0)
        family = OperatorFamily(
            tuple(range(90)), (window,) * 90, (operator,) * 90, cache_limit=3
        )
        before = operator.to_result().to_json()
        with (
            patch.object(
                OperatorFamily,
                "inclusion",
                side_effect=AssertionError("dense inclusion"),
            ),
            patch.object(
                OperatorFamily, "transport", side_effect=AssertionError("chain action")
            ),
            patch.object(
                Matrix, "solve", side_effect=AssertionError("repeated decomposition")
            ),
        ):
            self.assertEqual(family.barcode().value[0]["multiplicity"], 2)
            self.assertTrue(all(j == i + 1 for i, j in family._actions))
            self.assertEqual(family._transports, {})
            table = family.rank_table()
            self.assertEqual(len(table.value), 90 * 91 // 2)
        self.assertLessEqual(len(family._actions), 3)
        self.assertLessEqual(len(family._ranks), 3)
        self.assertEqual(len(family._kernels), 1)
        self.assertEqual(before, operator.to_result().to_json())
        uncached = replace(small, cache_limit=0)
        for i in range(3):
            for j in range(i, 3):
                self.assertEqual(uncached.transport(i, j), small.transport(i, j))
        self.assertEqual(uncached._actions, {})
        self.assertEqual(uncached._transports, {})
        self.assertEqual(uncached._kernels, {})
        self.assertEqual(uncached._native_kernels, {})
        self.assertEqual(uncached._kernel_sizes, {})
        for bad in (True, -1, 1.5):
            with self.assertRaises(ValueError):
                replace(small, cache_limit=bad)
            with self.assertRaises(ValueError):
                replace(small, kernel_cache_byte_limit=bad)

    def test_kernel_byte_budget_eviction_and_oversized_uncached_stage(self):
        small = merge_family()
        small._kernel(0)
        limit = sum(small._kernel_sizes.values())
        bounded = replace(small, kernel_cache_byte_limit=limit)
        for i in range(3):
            for j in range(i, 3):
                self.assertEqual(bounded.transport(i, j), small.transport(i, j))
                self.assertLessEqual(sum(bounded._kernel_sizes.values()), limit)
        uncached = replace(small, kernel_cache_byte_limit=0)
        self.assertEqual(uncached.barcode().value, small.barcode().value)
        self.assertEqual(uncached.transport_certificate(0, 2).state, "Computed")
        self.assertEqual(uncached._kernels, {})
        self.assertEqual(uncached._kernel_sizes, {})
        # Recompute from evicted kernels; runtime policy does not alter identity
        # or appear in either snapshot schema.
        self.assertEqual(uncached.identity, small.identity)
        for version in (1, 2):
            restored = OperatorFamilyResult.from_json(
                uncached.to_result(schema_version=version).to_json()
            ).to_family()
            self.assertEqual(restored.barcode().value, small.barcode().value)

    def test_compact_shared_storage_and_legacy_roundtrip(self):
        family = merge_family()
        family.track_mass((0, 1), 0, 2)
        for i in range(3):
            for j in range(i, 3):
                family.transport(i, j)
        legacy = family.to_result(schema_version=1)
        self.assertEqual(
            legacy.to_json(),
            OperatorFamilyResult.from_json(legacy.to_json())
            .to_family()
            .to_result()
            .to_json(),
        )
        compact = family.to_result()
        restored = compact.to_family()
        self.assertEqual(compact.to_json(), restored.to_result().to_json())
        self.assertEqual(legacy.identity, compact.identity)
        self.assertIs(restored.windows[1].D, restored.windows[2].D)
        self.assertIs(
            restored.windows[0].basis_current, restored.windows[2].basis_current
        )
        self.assertIs(restored.windows[1], restored.stage(1).window)
        for mutation in (
            "bool",
            "duplicate",
            "outside",
            "final",
            "reference",
            "boundary",
        ):
            wire = compact.to_dict()
            if mutation == "bool":
                wire["windows"]["stages"][0]["active"][1][0] = True
            elif mutation == "duplicate":
                wire["windows"]["stages"][0]["active"][1] = [0, 0]
            elif mutation == "outside":
                wire["windows"]["stages"][0]["active"][1][0] = 99
            elif mutation == "final":
                wire["windows"]["stages"][-1]["active"][1].reverse()
            elif mutation == "reference":
                wire["stage_results"][0]["input_ref"] = True
            else:
                wire["windows"]["D"]["rows"][0][0] ^= 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                OperatorFamilyResult.from_dict(wire)

    def test_adjacent_barcode_and_historical_bases_against_enumeration(self):
        from homology_operator.family import _adjacent_intervals
        from oracle.reference import rank_barcode, apply

        cases = []
        for source in range(4):
            for target in range(4):
                for encoding in range(1 << (source * target)):
                    cases.append(
                        (
                            [source, target],
                            [
                                [
                                    (encoding >> (j * target)) & ((1 << target) - 1)
                                    for j in range(source)
                                ]
                            ],
                        )
                    )
        rng = random.Random(20261002)
        for _ in range(5000):
            dimensions = [rng.randint(0, 6) for _ in range(rng.randint(1, 9))]
            maps = [
                [rng.randrange(1 << target) for _ in range(source)]
                for source, target in zip(dimensions, dimensions[1:])
            ]
            cases.append((dimensions, maps))
        digest = sha256()
        for dimensions, maps in cases:
            digest.update(
                json.dumps(
                    {"dimensions": dimensions, "maps": maps},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            )
            digest.update(b"\n")
            expected, ranks = rank_barcode(dimensions, maps)
            bars = _adjacent_intervals(dimensions, maps, histories=True)
            self.assertEqual(Counter((b, d) for b, d, _ in bars), expected)
            self.assertEqual(
                Counter((b, d) for b, d, _ in _adjacent_intervals(dimensions, maps)),
                expected,
            )
            for stage, dimension in enumerate(dimensions):
                vectors = [
                    history[stage - birth]
                    for birth, death, history in bars
                    if birth <= stage and (death is None or stage < death)
                ]
                # Enumerate every sum, independent of production elimination.
                span = {0}
                for vector in vectors:
                    span |= {x ^ vector for x in span}
                self.assertEqual(len(vectors), dimension)
                self.assertEqual(span, set(range(1 << dimension)))
            for birth, death, history in bars:
                for stage, (left, right) in enumerate(zip(history, history[1:]), birth):
                    self.assertEqual(apply(maps[stage], left), right)
                if death is not None:
                    self.assertEqual(apply(maps[death - 1], history[-1]), 0)
            for (i, j), rank in ranks.items():
                self.assertEqual(
                    sum(b <= i and (d is None or j < d) for b, d, _ in bars), rank
                )
        self.assertEqual(len(cases), 5689)
        self.assertEqual(
            digest.hexdigest(),
            "c04561269bd169624947172489c3927bb0617db8b20ba84bc1257970a86ebc50",
        )


def simplex_family(simplices, degree=0, empty_initial=False, reverse=False):
    """Independent set-incidence windows, including arbitrary coordinate order."""
    simplices = tuple(map(tuple, simplices))
    windows = []
    for count in range(0 if empty_initial else 1, len(simplices) + 1):
        cells = tuple(
            tuple(s for s in simplices[:count] if len(s) == d + 1)[
                :: -1 if reverse else 1
            ]
            for d in (degree - 1, degree, degree + 1)
        )
        boundaries = tuple(
            Matrix.from_rows(
                (
                    tuple(int(set(face) < set(cell)) for cell in columns)
                    for face in rows
                ),
                ncols=len(columns),
            )
            for rows, columns in zip(cells, cells[1:])
        )
        bases = tuple(tuple(str(s) for s in group) for group in cells)
        windows.append(ChainWindow(degree, *boundaries, *bases, (1,) * len(cells[1])))
    return OperatorFamily(
        (0,) * len(windows),
        tuple(windows),
        tuple(op(w) for w in windows),
        simplex_source={
            "stage_convention": "EmptyInitial" if empty_initial else "AfterInsertion",
            "simplices": [{"vertices": s, "label": str(s)} for s in simplices],
        },
    )


class FeatureReferenceTests(unittest.TestCase):
    def test_duplicate_endpoints_resolution_and_stable_roundtrip(self):
        # Two simultaneous deaths, two survivors; all intervals have scale length zero.
        first = ChainWindow(
            0,
            Matrix.zero(0, 4),
            Matrix.zero(4, 0),
            (),
            ("a", "b", "c", "d"),
            (),
            (1,) * 4,
        )
        last = replace(
            first,
            D=Matrix.from_columns(((1, 1, 0, 0), (0, 0, 1, 1)), 4),
            basis_next=("ab", "cd"),
        )
        family = OperatorFamily((0, 0), (first, last), (op(first), op(last)))
        before = family.barcode()
        features = family.features()
        self.assertEqual(len(features.value), 4)
        self.assertEqual(len({f["feature_id"] for f in features.value}), 4)
        self.assertEqual(Counter(f["occurrence"] for f in features.value), {0: 2, 1: 2})
        for ref in features.value:
            resolved = family.resolve_feature(ref, 0)
            self.assertEqual(resolved.identity, family.stage(0).identity)
            self.assertEqual(resolved.value["basis_current"], first.basis_current)
            self.assertEqual(family.feature_pairing(ref).state, "Unavailable")
            if ref["death_stage"] is not None:
                inactive = family.resolve_feature(ref, 1)
                self.assertEqual(inactive.state, "NoClass")
                self.assertEqual(inactive.details["inactive_reason"], "Dead")
        self.assertEqual(family.barcode(), before)
        record = family.to_result()
        with patch(
            "homology_operator.solver.FeasibleSolver.solve", side_effect=AssertionError
        ):
            restored = OperatorFamilyResult.from_json(record.to_json()).to_family()
            self.assertEqual(restored.features(), features)
            for ref in features.value:
                self.assertEqual(
                    restored.resolve_feature(ref, 0), family.resolve_feature(ref, 0)
                )
        self.assertEqual(record.to_json(), restored.to_result().to_json())
        with self.assertRaises(ValueError):
            family.to_result(schema_version=2)

    def test_empty_unborn_and_infinite_features(self):
        family = simplex_family(((0,),), empty_initial=True)
        ref = family.features().value[0]
        unborn = family.resolve_feature(ref, 0)
        self.assertEqual(
            (unborn.state, unborn.details["inactive_reason"]), ("NoClass", "NotBorn")
        )
        self.assertIsNone(family.feature_pairing(ref).value["death_simplex"])
        self.assertEqual(family.resolve_feature(ref, 1).state, "Computed")
        for degree in (0, 1, 3):
            empty = ChainWindow(
                degree, Matrix.zero(0, 0), Matrix.zero(0, 0), (), (), (), ()
            )
            base = OperatorFamily((0,), (empty,), (op(empty),))
            self.assertEqual(base.features().value, ())
            self.assertEqual(base.to_result().to_family().features().value, ())
        for stage in (-1, 2, True):
            with self.assertRaises(ValueError):
                family.resolve_feature(ref, stage)

    def test_reference_replacement_duplicate_cross_filtration_and_run_rejected(self):
        family = merge_family()
        features = family.features()
        ref = features.value[0]
        for replacement in (
            {**ref, "occurrence": 1},
            {**ref, "birth_stage": True},
            {**ref, "history_id": "forged"},
            {**ref, "birth_basis": ()},
            {**ref, "extra": 1},
        ):
            with self.assertRaises(ValueError):
                family.resolve_feature(replacement, 0)
        for other in (merge_family(), replace(family, scales=(0, 1, 2))):
            with self.assertRaises(ValueError):
                other.resolve_feature(ref, 0)
        family.resolve_feature(ref, 0)
        wire = family.to_result().to_dict()
        for change in (
            "duplicate",
            "history",
            "query",
            "certificate",
            "missing_basis",
            "missing_features",
        ):
            candidate = json.loads(json.dumps(wire))
            if change == "duplicate":
                candidate["features_readout"]["value"][1] = candidate[
                    "features_readout"
                ]["value"][0]
            elif change == "history":
                candidate["barcode_basis_readout"]["value"][0]["vectors"][0][
                    "representative"
                ][0] ^= 1
            elif change == "certificate":
                candidate["features_readout"]["details"]["certificate"][
                    "stages_checked"
                ] = 0
            elif change in {"missing_basis", "missing_features"}:
                field = (
                    "barcode_basis_readout"
                    if change == "missing_basis"
                    else "features_readout"
                )
                candidate[field] = family._query("NotComputed", None, 0, 2).to_dict()
            else:
                next(iter(candidate["tracking_readout"].values()))["value"][
                    "reference"
                ]["feature_id"] = "forged"
            with self.subTest(change=change), self.assertRaises(ValueError):
                OperatorFamilyResult.from_dict(candidate)

    def test_failed_stages_do_not_become_empty_features(self):
        family = merge_family()
        record = OperatorResult(
            None,
            family.windows[0],
            None,
            {"status": "ResourceExhausted"},
            {},
            {},
            "ResourceExhausted",
        )
        partial = replace(family, operators=(record, *family.operators[1:]))
        self.assertEqual(partial.features().state, "ResourceExhausted")
        self.assertEqual(partial.to_result().to_family().features(), partial.features())


class SimplexFeatureTests(unittest.TestCase):
    STREAM = ((0,), (1,), (2,), (0, 1), (0, 2), (1, 2), (0, 1, 2), (3,))

    def test_full_histories_pairs_and_all_ranks_against_independent_oracle(self):
        from oracle import reference as oracle

        # Same scale, different valid total orders and chain basis permutations.
        streams = (
            self.STREAM,
            (*self.STREAM[:3], (1, 2), (0, 2), (0, 1), *self.STREAM[6:]),
        )
        for stream, degree, empty, reverse in product(
            streams, range(3), (False, True), (False, True)
        ):
            family = simplex_family(stream, degree, empty, reverse)
            features = family.features()
            stages = [w.to_dict() for w in family.windows]
            expected = oracle.persistence_barcode(stages)
            self.assertEqual(
                tuple((f["birth_stage"], f["death_stage"]) for f in features.value),
                expected,
            )
            offset = int(empty)
            for ref in features.value:
                pairing = family.feature_pairing(ref)
                self.assertEqual(
                    pairing.value["birth_simplex"], stream[ref["birth_stage"] - offset]
                )
                death = ref["death_stage"]
                self.assertEqual(
                    pairing.value["death_simplex"],
                    None if death is None else stream[death - offset],
                )
            ranks = oracle.persistence_ranks(stages)
            for (i, j), rank in ranks.items():
                self.assertEqual(family.transport_rank(i, j).value, rank)
                self.assertEqual(
                    sum(
                        f["birth_stage"] <= i
                        and (f["death_stage"] is None or j < f["death_stage"])
                        for f in features.value
                    ),
                    rank,
                )
            # Enumerate raw boundary cosets: every stage history is a quotient basis.
            for stage, window in enumerate(family.windows):
                active = [
                    family.resolve_feature(ref, stage).value["representative"]
                    for ref in features.value
                    if ref["birth_stage"] <= stage
                    and (ref["death_stage"] is None or stage < ref["death_stage"])
                ]
                boundaries = oracle.boundaries(stages[stage])
                span = oracle.span(
                    tuple(sum(b << i for i, b in enumerate(z)) for z in active)
                )
                cosets = {min(z ^ b for b in boundaries) for z in span}
                all_cosets = {
                    min(z ^ b for b in boundaries) for z in oracle.cycles(stages[stage])
                }
                self.assertEqual(len(cosets), 1 << len(active))
                self.assertEqual(cosets, all_cosets)
            record = family.to_result()
            restored = OperatorFamilyResult.from_json(record.to_json()).to_family()
            self.assertEqual(restored.features(), features)
            self.assertEqual(record.to_json(), restored.to_result().to_json())

    def test_source_input_and_snapshot_forgery_rejected(self):
        family = simplex_family(self.STREAM)
        for change in (
            "face",
            "duplicate",
            "label",
            "convention",
            "boundary",
            "vertex",
        ):
            source = {
                "stage_convention": family.simplex_source["stage_convention"],
                "simplices": [
                    {"vertices": list(e["vertices"]), "label": e["label"]}
                    for e in family.simplex_source["simplices"]
                ],
            }
            if change == "face":
                source["simplices"][0], source["simplices"][3] = (
                    source["simplices"][3],
                    source["simplices"][0],
                )
            elif change == "duplicate":
                source["simplices"][1] = source["simplices"][0]
            elif change == "label":
                source["simplices"][0]["label"] = "forged"
            elif change == "convention":
                source["stage_convention"] = "EmptyInitial"
            elif change == "boundary":
                source["simplices"][3]["vertices"] = [0, 2]
                source["simplices"][4]["vertices"] = [0, 1]
            else:
                source["simplices"][0]["vertices"] = [True]
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(family, simplex_source=source)
        ref = family.features().value[0]
        family.feature_pairing(ref)
        wire = family.to_result().to_dict()
        next(iter(wire["tracking_readout"].values()))["value"]["birth_simplex"] = [99]
        with self.assertRaises(ValueError):
            OperatorFamilyResult.from_dict(wire)
        # Restoring provenance before reading features must also remain lossless.
        fresh = simplex_family(self.STREAM)
        self.assertEqual(
            fresh.to_result().to_json(),
            fresh.to_result().to_family().to_result().to_json(),
        )
        empty = simplex_family((), empty_initial=True)
        self.assertEqual(empty.features().value, ())

    def test_full_certificate_rejects_duplicate_basis_and_broken_middle_history(self):
        family = simplex_family(self.STREAM, degree=1)
        history = family.barcode_basis().to_dict()["value"]
        for change in ("duplicate", "middle", "missing"):
            candidate = json.loads(json.dumps(history))
            if change == "duplicate":
                candidate.append(candidate[0])
            elif change == "middle":
                candidate[0]["vectors"][0]["representative"][0] ^= 1
            else:
                candidate[0]["vectors"] = []
            with self.subTest(change=change), self.assertRaises(ValueError):
                family._certify_feature_history(
                    QueryResult("Computed", candidate).value
                )

    def test_endpoint_checks_cannot_replace_middle_transport_certificate(self):
        stream = (
            (0,),
            (1,),
            (2,),
            (3,),
            (0, 1),
            (0, 2),
            (1, 2),
            (0, 3),
            (1, 3),
            (2, 3),
            (0, 1, 2),
            (0, 1, 3),
            (0, 2, 3),
            (1, 2, 3),
        )
        family = simplex_family(stream, degree=1)
        history = family.barcode_basis().to_dict()["value"]
        middle = [v for bar in history for v in bar["vectors"] if v["stage"] == 9]
        self.assertEqual(len(middle), 3)
        for field in ("coordinates", "representative"):
            middle[0][field], middle[1][field] = middle[1][field], middle[0][field]
        # Endpoints and every stage's full basis survive this middle-stage swap.
        with self.assertRaisesRegex(ValueError, "commute with transport"):
            family._certify_feature_history(QueryResult("Computed", history).value)

    def test_random_orders_h0_through_h3_and_all_higher_deaths(self):
        from itertools import combinations
        from oracle import reference as oracle

        rng = random.Random(9495)
        for trial in range(5):
            stream = []
            for size in range(1, 5):
                cells = list(combinations(range(4), size))
                rng.shuffle(cells)
                stream.extend(cells)
            for degree in range(4):
                family = simplex_family(
                    stream,
                    degree,
                    empty_initial=bool(trial % 2),
                    reverse=bool(trial % 3),
                )
                expected = oracle.persistence_barcode(
                    [w.to_dict() for w in family.windows]
                )
                features = family.features()
                self.assertEqual(
                    tuple((f["birth_stage"], f["death_stage"]) for f in features.value),
                    expected,
                )
                for ref in features.value:
                    self.assertEqual(family.feature_pairing(ref).state, "Computed")

    def test_fixed_research_pairs_and_numbering_migration(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/feature_pairing.json").read_text("utf-8")
        )
        payload = fixture["payload"]
        self.assertEqual(
            sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            fixture["payload_sha256"],
        )
        self.assertEqual(
            fixture["source"]["revision"], "f4d0de6a8f1cd0285e4dda0a48d951b60dad3282"
        )
        for degree, empty in product(range(3), (False, True)):
            family = simplex_family(payload["simplices"], degree, empty)
            offset = 0 if empty else -1  # incremental includes empty stage zero.
            expected = {
                (
                    p["birth"] + offset,
                    None if p["death"] is None else p["death"] + offset,
                    tuple(p["birth_simplex"]),
                    None if p["death_simplex"] is None else tuple(p["death_simplex"]),
                )
                for p in payload["incremental_pairs"]
                if p["degree"] == degree
            }
            actual = set()
            for ref in family.features().value:
                pair = family.feature_pairing(ref).value
                actual.add(
                    (
                        ref["birth_stage"],
                        ref["death_stage"],
                        pair["birth_simplex"],
                        pair["death_simplex"],
                    )
                )
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
