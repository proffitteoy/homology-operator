from dataclasses import replace
from fractions import Fraction
import unittest
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import random
from unittest.mock import patch
from itertools import product

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
        for bad in (True, -1, 1.5):
            with self.assertRaises(ValueError):
                replace(small, cache_limit=bad)

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

    def test_5689_original_modules_plus_historical_bases_against_enumeration(self):
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
        old = json.loads(
            (
                Path(__file__).parents[1]
                / "research/s4-s5/quiver_barcode_probe_result.json"
            ).read_text("utf-8")
        )
        self.assertEqual(len(cases), 5689)
        self.assertEqual(digest.hexdigest(), old["corpus_sha256"])


if __name__ == "__main__":
    unittest.main()
