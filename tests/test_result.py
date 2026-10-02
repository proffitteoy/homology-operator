import unittest
from fractions import Fraction

from homology_operator.algebra import Matrix
from homology_operator.chain import ChainWindow
from homology_operator.result import (
    OperatorResult,
    QueryResult,
    canonical_json,
    content_id,
    make_identity,
)


class ResultTests(unittest.TestCase):
    def window(self, **changes):
        values = dict(
            k=1,
            A=Matrix.zero(0, 2),
            D=Matrix.from_rows(((1,), (1,))),
            basis_previous=(),
            basis_current=("a", "b"),
            basis_next=("f",),
            weights=(1, Fraction(3, 2)),
            source_metadata={"source": "hand-derived"},
        )
        values.update(changes)
        return ChainWindow(**values)

    def record(self, window=None, projection=None, **changes):
        window = window or self.window()
        projection = projection or Matrix.from_rows(((1, 1), (0, 0)))
        identity = make_identity(window, projection, "test-run")
        values = dict(
            identity=identity,
            input_data=window,
            projection=projection,
            solver={
                "status": "FeasibleOnly",
                "certificate_level": "Feasible",
                "tie_break_policy": "StableBasisOrder",
                "solver_run_id": "test-run",
                "lower_bound": None,
                "upper_bound": Fraction(3, 2),
            },
            certificate={"p_idempotent": True},
            status="Unavailable",
            provenance={
                "theory_revision": "fixed-revision",
                "backend": "reference",
                "arithmetic_mode": window.arithmetic,
            },
            query_results={
                "selected_mass": QueryResult("Computed", Fraction(0), identity, True),
                "minimum_class_mass": QueryResult("NotComputed", identity=identity),
                "stretch": QueryResult("EmptyDomain", 0, identity, True),
            },
        )
        values.update(changes)
        return OperatorResult(**values)

    def test_canonical_hash_and_reproducible_identity(self):
        self.assertEqual(
            canonical_json({"a": 1, "b": [2]}), canonical_json({"b": (2,), "a": 1})
        )
        self.assertEqual(
            content_id("fixture", {"b": 2, "a": 1}),
            content_id("fixture", {"a": 1, "b": 2}),
        )
        first = self.record()
        self.assertEqual(first.identity, self.record().identity)
        self.assertEqual(first.to_json(), self.record().to_json())

    def test_weight_basis_and_projection_identity_changes(self):
        first = self.record()
        weighted = self.record(self.window(weights=(2, 3)))
        reordered = self.record(self.window(basis_current=("b", "a")))
        changed = self.record(projection=Matrix.from_rows(((0, 0), (1, 1))))
        self.assertEqual(first.identity["input_id"], weighted.identity["input_id"])
        self.assertEqual(
            first.identity["projection_id"], weighted.identity["projection_id"]
        )
        self.assertNotEqual(first.identity["weight_id"], weighted.identity["weight_id"])
        self.assertNotEqual(
            first.identity["operator_id"], weighted.identity["operator_id"]
        )
        self.assertNotEqual(first.identity["basis_id"], reordered.identity["basis_id"])
        self.assertNotEqual(first.identity["input_id"], reordered.identity["input_id"])
        self.assertNotEqual(
            first.identity["projection_id"], changed.identity["projection_id"]
        )
        with self.assertRaises(ValueError):
            first.require_same_identity(changed)
        with self.assertRaises(ValueError):
            first.query_results["selected_mass"].require_same_identity(
                changed.query_results["selected_mass"]
            )

    def test_lossless_round_trip(self):
        record = self.record()
        restored = OperatorResult.from_json(record.to_json())
        self.assertEqual(record, restored)
        self.assertEqual(restored.solver["upper_bound"], Fraction(3, 2))
        self.assertEqual(restored.input_data.weights[1], Fraction(3, 2))
        self.assertEqual(restored.provenance["theory_revision"], "fixed-revision")
        self.assertEqual(restored.query_results["selected_mass"].value, 0)
        self.assertEqual(
            restored.query_results["minimum_class_mass"].state, "NotComputed"
        )

    def test_missing_states_are_not_zero(self):
        identity = self.record().identity
        results = [
            QueryResult("Computed", 0, identity),
            QueryResult("EmptyDomain", 0, identity),
        ]
        results += [
            QueryResult(state, identity=identity)
            for state in ("NotComputed", "Unavailable", "ResourceExhausted", "NoClass")
        ]
        self.assertEqual(len({result.state for result in results}), 6)
        for result in results:
            self.assertEqual(result, QueryResult.from_dict(result.to_dict()))
        with self.assertRaises(ValueError):
            QueryResult("Computed")
        with self.assertRaises(ValueError):
            QueryResult("ResourceExhausted", 0)

    def test_deserialization_rejects_tampering_and_mixed_results(self):
        data = self.record().to_dict()
        data["projection"]["rows"][0][0] = 0
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(data)
        data = self.record().to_dict()
        data["input_data"]["weights"][0]["numerator"] = 5
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(data)
        data = self.record().to_dict()
        data["query_results"]["selected_mass"]["identity"]["projection_id"] = "other"
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(data)
        data = self.record().to_dict()
        data["schema_version"] = 2
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(data)
        with self.assertRaises(ValueError):
            OperatorResult.from_json('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            OperatorResult.from_json('{"value":NaN}')

    def test_cache_binds_every_semantic_policy(self):
        first = self.record()
        original = first.cache_key("solver-v1", "stable", "reference-v1")
        self.assertEqual(
            original, self.record().cache_key("solver-v1", "stable", "reference-v1")
        )
        variants = (
            self.record(self.window(weights=(2, 3))).cache_key(
                "solver-v1", "stable", "reference-v1"
            ),
            first.cache_key("solver-v2", "stable", "reference-v1"),
            first.cache_key("solver-v1", "lexical", "reference-v1"),
            first.cache_key("solver-v1", "stable", "reference-v2"),
        )
        self.assertTrue(all(key != original for key in variants))
        window = first.input_data
        repeated_identity = make_identity(window, first.projection, "another-run")
        solver = dict(first.solver)
        solver["solver_run_id"] = "another-run"
        repeated = OperatorResult(
            repeated_identity,
            window,
            first.projection,
            solver,
            first.certificate,
            first.provenance,
            "Unavailable",
        )
        self.assertEqual(
            first.identity["operator_id"], repeated.identity["operator_id"]
        )
        self.assertEqual(
            original, repeated.cache_key("solver-v1", "stable", "reference-v1")
        )
        with self.assertRaises(ValueError):
            first.require_same_identity(repeated)

    def test_exact_optimal_requires_more_than_a_feasible_flag(self):
        solver = dict(self.record().solver)
        solver["certificate_level"] = "ExactOptimal"
        with self.assertRaises(ValueError):
            self.record(solver=solver)
        solver["objective_exact"] = True
        with self.assertRaises(ValueError):
            self.record(
                solver=solver,
                certificate={"optimality_certificate": "unverified dummy"},
            )

    def test_metadata_is_immutable(self):
        record = self.record()
        with self.assertRaises(TypeError):
            record.identity["weight_id"] = "other"
        with self.assertRaises(TypeError):
            record.solver["upper_bound"] = 0
        with self.assertRaises(TypeError):
            record.query_results["extra"] = QueryResult("Unavailable")

    def test_unsupported_certificate_and_failed_ready_are_rejected(self):
        for level in ("CertifiedInterval", "CertifiedUpperBound", "Heuristic"):
            solver = dict(self.record().solver)
            solver["certificate_level"] = level
            with self.assertRaises(ValueError):
                self.record(solver=solver)
        solver = dict(self.record().solver)
        solver["status"] = "InvalidProblem"
        with self.assertRaises(ValueError):
            self.record(solver=solver, status="Ready")

    def test_reserved_mapping_keys_and_fractions_round_trip(self):
        for value in (
            {"$fraction": [1, 2]},
            {"$fraction": [1, 0]},
            {"$mapping": {"$fraction": Fraction(1, 2)}},
            {"nested": [{"$mapping": [1]}, Fraction(3, 2)]},
            Fraction(1, 2),
        ):
            with self.subTest(value=value):
                query = QueryResult("Computed", value, details={"payload": value})
                self.assertEqual(query, QueryResult.from_dict(query.to_dict()))
                record = self.record(provenance={"payload": value})
                self.assertEqual(record, OperatorResult.from_json(record.to_json()))
        self.assertNotEqual(
            content_id("value", {"$fraction": [1, 2]}),
            content_id("value", Fraction(1, 2)),
        )

    def test_missing_projection_failure_round_trip(self):
        window = self.window()
        partial = {
            key: window.identity()[key] for key in ("input_id", "basis_id", "weight_id")
        }
        partial["solver_run_id"] = "failed-run"
        for status, solver_status in (
            ("Unavailable", "Unavailable"),
            ("SolverFailed", "NumericalFailure"),
            ("ResourceExhausted", "ResourceExhausted"),
            ("InternalValidationFailed", "InternalError"),
            ("InvalidInput", "InvalidProblem"),
        ):
            with self.subTest(status=status):
                record = OperatorResult(
                    partial,
                    window,
                    None,
                    {
                        "status": solver_status,
                        "certificate_level": None,
                        "solver_run_id": "failed-run",
                    },
                    {},
                    {"diagnostic": "no feasible action"},
                    status,
                )
                self.assertEqual(record, OperatorResult.from_json(record.to_json()))
                self.assertNotIn("projection_id", record.identity)
                with self.assertRaises(ValueError):
                    record.cache_key("solver", "stable", "reference")
        invalid = OperatorResult(
            None,
            None,
            None,
            {"status": "InvalidProblem"},
            {},
            {"error": "AD != 0"},
            "InvalidInput",
        )
        self.assertEqual(invalid, OperatorResult.from_json(invalid.to_json()))

    def test_missing_projection_rejects_fabricated_action(self):
        values = dict(
            identity=None,
            input_data=self.window(),
            projection=None,
            solver={"status": "Unavailable", "certificate_level": None},
            certificate={},
            provenance={},
            status="Unavailable",
        )
        for changes in (
            {"status": "Ready"},
            {"identity": self.record().identity},
            {"certificate": {"p_idempotent": True}},
            {"query_results": {"mass": QueryResult("Computed", 0)}},
            {"solver": {"status": "Unavailable", "certificate_level": "Feasible"}},
            {"solver": {"status": "FeasibleOnly", "certificate_level": None}},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                OperatorResult(**(values | changes))

    def test_bounds_reject_invalid_values_and_uncertified_grades(self):
        for bounds in (
            {"lower_bound": 100, "upper_bound": -100},
            {"lower_bound": 2, "upper_bound": 1},
            {"lower_bound": True},
            {"upper_bound": "1"},
            {"upper_bound": float("inf")},
            {"upper_bound": float("nan")},
        ):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                self.record(solver=dict(self.record().solver) | bounds)
        for grade in ("CertifiedUpperBound", "CertifiedInterval", "Heuristic"):
            with self.subTest(grade=grade), self.assertRaises(ValueError):
                self.record(
                    solver=dict(self.record().solver) | {"certificate_level": grade}
                )

    def test_nested_objective_requires_same_identity(self):
        identity = self.record().identity
        objective = QueryResult("Computed", Fraction(3, 2), identity, True)
        record = self.record(
            solver=dict(self.record().solver) | {"objective": objective.to_dict()}
        )
        self.assertEqual(record, OperatorResult.from_json(record.to_json()))
        other = self.record(self.window(weights=(2, 3))).identity
        with self.assertRaises(ValueError):
            self.record(
                solver=dict(record.solver)
                | {"objective": QueryResult("Computed", 99, other).to_dict()}
            )
        data = record.to_dict()
        data["solver"]["objective"]["identity"]["weight_id"] = "other"
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(data)


if __name__ == "__main__":
    unittest.main()
