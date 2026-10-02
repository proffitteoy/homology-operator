"""S4-08 preparation: frozen S4-03 wire records, independent of native edits."""

from contextlib import ExitStack
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from homology_operator import (
    HomologyOperator,
    Matrix,
    OperatorFamilyResult,
    OperatorResult,
    ProjectionSolution,
    QueryResult,
)
from homology_operator.result import make_identity

FIXTURE = Path(__file__).parent / "fixtures" / "legacy_results.json"
FIXTURE_SHA256 = "ee79ac1b3525dc8e9f88c8404d9bb53c79ce346cc20e90df99b42ef5e9b44c4a"
BUNDLE = json.loads(FIXTURE.read_text(encoding="utf-8"))


def restore_operator(record):
    metadata = record.solver
    solution = ProjectionSolution(
        metadata["status"],
        record.identity["solver_run_id"],
        record.projection,
        record.identity,
        metadata["certificate_level"],
        QueryResult.from_dict(metadata["objective"]),
        record.certificate,
        metadata["resource_usage"],
        tie_break_policy=metadata["tie_break_policy"],
        method=metadata["method"],
        arithmetic_policy=metadata["arithmetic_policy"],
        lower_bound=metadata["lower_bound"],
        upper_bound=metadata["upper_bound"],
        solver_config=metadata["solver_config"],
    )
    return HomologyOperator(record.input_data, solution)


class LegacyCompatibilityTests(unittest.TestCase):
    def wire(self, name):
        return deepcopy(BUNDLE["records"][name]["wire"])

    def test_frozen_source_and_record_hashes(self):
        self.assertEqual(sha256(FIXTURE.read_bytes()).hexdigest(), FIXTURE_SHA256)
        self.assertEqual(
            BUNDLE["source_revision"], "88f69661859fe7475705fb76589cf30674b63746"
        )
        self.assertEqual(len(BUNDLE["records"]), 7)
        for name, entry in BUNDLE["records"].items():
            wire_bytes = json.dumps(
                entry["wire"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            with self.subTest(record=name):
                self.assertEqual(sha256(wire_bytes).hexdigest(), entry["record_sha256"])

    def test_old_wire_and_history_restore_without_native_or_resolving(self):
        with ExitStack() as stack:
            stack.enter_context(
                patch("homology_operator.native._extension", side_effect=ImportError)
            )
            for method in (
                "FeasibleSolver",
                "ExhaustiveExactSolver",
                "GreedyCertifiedSolver",
                "Rank2ExactSolver",
                "StructuredFamilySolver",
            ):
                stack.enter_context(
                    patch(
                        f"homology_operator.solver.{method}.solve",
                        side_effect=AssertionError("restoration must not re-solve"),
                    )
                )
            for name, entry in BUNDLE["records"].items():
                with self.subTest(record=name):
                    result_type = (
                        OperatorFamilyResult
                        if entry["kind"] == "family"
                        else OperatorResult
                    )
                    record = result_type.from_dict(self.wire(name))
                    self.assertEqual(record.to_dict(), entry["wire"])
                    repeated = result_type.from_json(record.to_json())
                    self.assertEqual(repeated.to_dict(), entry["wire"])
                    if entry["kind"] == "family":
                        restored = repeated.to_family()
                        for index, stage in enumerate(repeated.stage_results):
                            if stage.status == "Ready":
                                self.assertEqual(
                                    restored.stage(index).to_result().query_results,
                                    stage.query_results,
                                )

    def test_all_chain_actions_and_noncycle_domain_keep_old_meaning(self):
        for name in ("matrix_unqueried", "matrix_certified_queried", "cyclic_trace"):
            record = OperatorResult.from_dict(self.wire(name))
            operator = restore_operator(record)
            for x in product((0, 1), repeat=3):
                projected = (
                    (x[1] ^ x[2], x[0] ^ x[2], x[0] ^ x[1])
                    if name == "cyclic_trace"
                    else (0, 0, x[2])
                )
                with self.subTest(record=name, chain=x):
                    self.assertEqual(operator.project(x), projected)
                    self.assertEqual(
                        operator.apply_operator(x),
                        tuple(a ^ b for a, b in zip(x, projected)),
                    )
        operator = restore_operator(
            OperatorResult.from_dict(self.wire("matrix_unqueried"))
        )
        self.assertEqual(operator.project((1, 0, 0)), (0, 0, 0))
        with self.assertRaises(ValueError):
            operator.class_representative((1, 0, 0))

    def test_exact_weight_certificate_and_query_states_survive(self):
        record = OperatorResult.from_dict(self.wire("matrix_certified_queried"))
        self.assertEqual(
            record.input_data.weights, (Fraction(1, 3), Fraction(2, 7), Fraction(7, 5))
        )
        self.assertEqual(record.solver["certificate_level"], "ExactOptimal")
        self.assertEqual(QueryResult.from_dict(record.solver["objective"]).value, 1)
        masses = [
            q
            for name, q in record.query_results.items()
            if name.startswith("selected_mass:")
        ]
        distances = [
            q
            for name, q in record.query_results.items()
            if name.startswith("class_distance:")
        ]
        self.assertEqual(masses[0].value, Fraction(7, 5))
        self.assertEqual(distances[0].value, 0)
        self.assertTrue(masses[0].exact)
        unqueried = OperatorResult.from_dict(self.wire("matrix_unqueried"))
        self.assertEqual(unqueried.query_results["kernel_basis"].state, "NotComputed")
        self.assertEqual(unqueried.query_results["stretch"].state, "NotComputed")
        empty = OperatorResult.from_dict(self.wire("empty_domain"))
        self.assertEqual(empty.query_results["stretch"].state, "EmptyDomain")
        self.assertEqual(empty.query_results["stretch"].value, 0)
        self.assertEqual(empty.query_results["betti"].value, 0)
        failed = OperatorResult.from_dict(self.wire("resource_failure"))
        self.assertEqual(failed.status, "ResourceExhausted")
        self.assertIsNone(failed.projection)
        self.assertEqual(dict(failed.query_results), {})

    def test_restore_revalidates_zero_projection_even_with_matching_identity(self):
        wire = self.wire("matrix_unqueried")
        original = OperatorResult.from_dict(wire)
        zero = Matrix.zero(3, 3)
        wire["projection"]["rows"] = [[0, 0, 0]] * 3
        wire["identity"] = make_identity(
            original.input_data, zero, original.identity["solver_run_id"]
        )
        wire["query_results"] = {}
        wire["solver"]["objective"]["identity"] = wire["identity"]
        with self.assertRaisesRegex(ValueError, "cycle_homology_preservation"):
            OperatorResult.from_dict(wire)

    def test_restore_rejects_schema_handle_certificate_and_query_tampering(self):
        variants = []
        wire = self.wire("matrix_unqueried")
        wire["schema_version"] = 999
        variants.append(wire)
        wire = self.wire("cyclic_trace")
        wire["projection"]["version"] = 999
        variants.append(wire)
        wire = self.wire("matrix_certified_queried")
        wire["solver"]["upper_bound"] = 0
        variants.append(wire)
        wire = self.wire("matrix_certified_queried")
        query = next(
            value
            for key, value in wire["query_results"].items()
            if key.startswith("selected_mass:")
        )
        query["identity"]["weight_id"] = "foreign-weight"
        variants.append(wire)
        for index, wire in enumerate(variants):
            with self.subTest(tampering=index), self.assertRaises(ValueError):
                OperatorResult.from_dict(wire)

    def test_family_ranks_duplicate_stages_tracking_and_partial_failure(self):
        record = OperatorFamilyResult.from_dict(self.wire("family_repeated_scale"))
        family = record.to_family()
        self.assertEqual(family.scales, (0, 1, 1))
        self.assertEqual(family.transport_rank(0, 0).value, 2)
        for i, j in ((0, 1), (0, 2), (1, 1), (1, 2), (2, 2)):
            self.assertEqual(family.transport_rank(i, j).value, 1)
        bars = family.barcode().value
        self.assertEqual(
            tuple((b["birth_stage"], b["death_stage"]) for b in bars),
            ((0, 1), (0, None)),
        )
        self.assertEqual(family.track_class((0, 1), 0, 2).value, (1, 0))
        self.assertEqual(family.track_mass((0, 1), 0, 2).value, 10)
        self.assertEqual(family.track_support((0, 1), 0, 2).value, (0,))
        partial = OperatorFamilyResult.from_dict(
            self.wire("family_partial")
        ).to_family()
        self.assertEqual(partial.status, "Partial")
        self.assertEqual(partial.transport_rank(0, 1).state, "ResourceExhausted")
        self.assertIsNone(partial.transport_rank(0, 1).value)

    def test_family_restore_rejects_rank_barcode_and_tracking_tampering(self):
        variants = []
        wire = self.wire("family_repeated_scale")
        wire["rank_readout"]["0:2"]["value"] = 2
        variants.append(wire)
        wire = self.wire("family_repeated_scale")
        wire["barcode_readout"]["value"][0]["death_stage"] = 2
        variants.append(wire)
        wire = self.wire("family_repeated_scale")
        query = next(
            q
            for q in wire["tracking_readout"].values()
            if q["details"]["query"] == "track_mass"
        )
        query["value"] = 1
        variants.append(wire)
        for index, wire in enumerate(variants):
            with self.subTest(tampering=index), self.assertRaises(ValueError):
                OperatorFamilyResult.from_dict(wire)


if __name__ == "__main__":
    unittest.main()
