from fractions import Fraction
from itertools import product, combinations
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from math import sqrt
import unittest
from unittest.mock import patch

from homology_operator.algebra import Matrix
from homology_operator.chain import ChainWindow
from homology_operator.operator import HomologyOperator
from homology_operator.result import OperatorResult, QueryResult, require_same_identity
from homology_operator.solver import (
    FeasibleSolver,
    ProjectionProblem,
    ResourceLimits,
    solve_projection,
)
from test_joint import oracle, window as fixture_window, pack, unpack
from homology_operator import OperatorFamily, OperatorFamilyResult
from homology_operator.result import content_id


def operator(weights=(10, 1), arithmetic="ExactRational"):
    window = ChainWindow(
        0,
        Matrix.zero(0, 2),
        Matrix.from_rows(((1,), (1,))),
        (),
        ("a", "b"),
        ("e",),
        weights,
        arithmetic=arithmetic,
    )
    return HomologyOperator(window, FeasibleSolver().solve(ProjectionProblem(window)))


def mapped_window(points, cells, k, stage=0, order=("only",), **changes):
    """Small explicit point/mesh input; incidence is built independently by subsets."""
    bases = [
        tuple(s for s in cells if len(s) == degree + 1) for degree in (k - 1, k, k + 1)
    ]

    def labels(ss):
        return tuple("s" + ",".join(map(str, s)) for s in ss)

    def incidence(lower, upper):
        return Matrix.from_columns(
            (tuple(int(set(face) < set(cell)) for face in lower) for cell in upper),
            nrows=len(lower),
        )

    vertices = {
        str(i): {"original_id": 100 + 7 * i, "coordinates": list(p)}
        for i, p in enumerate(points)
    }
    mapping = {
        "version": 1,
        "source_hash": sha256(
            json.dumps(vertices, sort_keys=True).encode()
        ).hexdigest(),
        "stage_order": list(order),
        "stage": stage,
        "scale": stage,
        "vertices": vertices,
        "simplices": {
            label: {
                "vertices": list(map(str, cell)),
                "offsets": [[0] * len(points[0]) for _ in cell],
            }
            for basis in bases
            for cell, label in zip(basis, labels(basis))
        },
        "embedding": {
            "dimension": len(points[0]),
            "unit": "m",
            "metric": "euclidean",
            "periods": [None] * len(points[0]),
        },
    }
    values = dict(
        k=k,
        A=incidence(bases[0], bases[1]),
        D=incidence(bases[1], bases[2]),
        basis_previous=labels(bases[0]),
        basis_current=labels(bases[1]),
        basis_next=labels(bases[2]),
        weights=(1,) * len(bases[1]),
        source_metadata={"source_mapping": mapping},
    )
    values.update(changes)
    return ChainWindow(**values)


def mapped_operator(window):
    return HomologyOperator(window, FeasibleSolver().solve(ProjectionProblem(window)))


class SourceLocationTests(unittest.TestCase):
    def triangle(self, **changes):
        return mapped_window(
            ((0, 0), (3, 0), (0, 4)),
            ((0,), (1,), (2,), (0, 1), (0, 2), (1, 2)),
            1,
            weights=(3, 4, 5),
            weight_semantics="euclidean_length",
            unit="m",
            **changes,
        )

    def test_point_indices_units_same_p_and_source_hash(self):
        window = self.triangle()
        op = mapped_operator(window)
        query = op.readout("locate_support", (1, 1, 1))
        location = query.value
        self.assertEqual(query.identity, op.identity)
        self.assertIsNone(query.exact)
        self.assertNotIn("rounding_policy", query.details)
        self.assertEqual(location["support"], op.support((1, 1, 1)))
        self.assertEqual(location["components"], ((0, 1, 2),))
        self.assertEqual(location["simplices"][2]["original_ids"], (107, 114))
        self.assertEqual(location["simplices"][2]["coordinates"], ((3, 0), (0, 4)))
        self.assertEqual(op.selected_mass((1, 1, 1)), 12)
        self.assertEqual(location["weight_unit"], "m")
        self.assertEqual(location["embedding"]["unit"], "m")
        self.assertEqual(
            location["source_mapping_id"], window.identity()["source_mapping_id"]
        )
        self.assertEqual(
            location["source_hash"],
            window.source_metadata["source_mapping"]["source_hash"],
        )
        expected = dict(location)
        del expected["location_id"]
        self.assertEqual(location["location_id"], content_id("location", expected))
        restored = OperatorResult.from_json(op.to_result().to_json()).to_operator()
        self.assertEqual(restored.locate_support((1, 1, 1)), location)
        with self.assertRaises(ValueError):
            op.locate_support((1, 0, 0))

    def test_h1_can_have_multiple_connected_support_components(self):
        points = ((0, 0), (3, 0), (0, 4), (10, 0), (13, 0), (10, 4))
        edges = ((0, 1), (0, 2), (1, 2), (3, 4), (3, 5), (4, 5))
        w = mapped_window(points, tuple((i,) for i in range(6)) + edges, 1)
        op = mapped_operator(w)
        self.assertEqual(op.betti(), 2)
        location = op.locate_support((1,) * 6)
        self.assertEqual(location["components"], ((0, 1, 2), (3, 4, 5)))

    def test_h0_merge_edge_and_points_and_ph_share_sources(self):
        points = ((0, 0), (3, 4))
        first = mapped_window(points, ((0,), (1,)), 0, order=("points", "edge"))
        last = mapped_window(points, ((0,), (1,), (0, 1)), 0, 1, ("points", "edge"))
        family = OperatorFamily(
            (0, 1), (first, last), (mapped_operator(first), mapped_operator(last))
        )
        edge = last.locate_chain((1,), degree=1)
        self.assertEqual(edge["degree"], 1)
        self.assertEqual(edge["simplices"][0]["original_ids"], (100, 107))
        point = family.stage(1).locate_support((0, 1))
        self.assertEqual(point["degree"], 0)
        self.assertEqual(len(point["simplices"][0]["vertices"]), 1)
        dead = family.track_location((1, 1), 0, 1)
        self.assertEqual(dead.state, "Computed")
        self.assertEqual(dead.value["support"], ())
        alive = family.track_location((1, 0), 0, 1)
        self.assertEqual(alive.value["source_hash"], edge["source_hash"])
        self.assertEqual(
            alive.details["filtration_id"], family.identity["filtration_id"]
        )
        self.assertEqual(family.transport_rank(0, 1).value, 1)
        self.assertEqual(
            {
                (bar["birth_stage"], bar["death_stage"], bar["multiplicity"])
                for bar in family.barcode().value
            },
            {(0, 1, 1), (0, None, 1)},
        )
        for schema in (1, 2):
            wire = family.to_result(schema_version=schema).to_json()
            restored = OperatorFamilyResult.from_json(wire).to_family()
            self.assertEqual(restored.track_location((1, 0), 0, 1), alive)

    def test_h2_tetrahedron_surface_and_raw_three_dimensional_filling(self):
        points = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
        cells = tuple(s for size in range(1, 5) for s in combinations(range(4), size))
        surface = mapped_window(
            points,
            cells[:-1],
            2,
            arithmetic="FloatingPoint",
            weights=(0.5, 0.5, 0.5, sqrt(3) / 2),
            weight_semantics="euclidean_area",
            unit="m^2",
        )
        op = mapped_operator(surface)
        self.assertEqual(surface.A.apply((1,) * 4), (0,) * 6)
        self.assertEqual(op.betti(), 1)
        self.assertEqual(op.locate_support((1,) * 4)["support"], (0, 1, 2, 3))
        solid = mapped_window(points, cells, 2)
        self.assertEqual(solid.D.apply((1,)), (1,) * 4)
        filling = solid.locate_chain((1,), degree=1)
        self.assertEqual(filling["degree"], 3)
        self.assertEqual(filling["simplices"][0]["coordinates"], points)
        self.assertEqual(mapped_operator(solid).locate_support((1,) * 4)["support"], ())

    def test_explicit_periodic_lifts_and_boundary_compatibility(self):
        base = mapped_window(((9,), (1,)), ((0,), (1,), (0, 1)), 0)
        data = base.to_dict()
        mapping = data["source_metadata"]["source_mapping"]
        mapping["embedding"]["periods"] = [10]
        mapping["simplices"]["s0,1"]["offsets"] = [[0], [1]]
        window = ChainWindow.from_dict(data)
        edge = window.locate_chain((1,), degree=1)
        self.assertEqual(edge["simplices"][0]["coordinates"], ((9,), (11,)))
        self.assertEqual(edge["simplices"][0]["offsets"], ((0,), (1,)))
        overflow = window.to_dict()
        overflow["source_metadata"]["source_mapping"]["embedding"]["periods"] = [10.0]
        overflow["source_metadata"]["source_mapping"]["simplices"]["s0,1"]["offsets"][
            1
        ][0] = 10**400
        with self.assertRaisesRegex(ValueError, "overflow"):
            ChainWindow.from_dict(overflow).locate_chain((1,), degree=1)
        # A filled triangle's face lifts must be restrictions up to one translation.
        filled = mapped_window(
            ((0, 0), (3, 0), (0, 4)),
            ((0,), (1,), (2,), (0, 1), (0, 2), (1, 2), (0, 1, 2)),
            1,
        )
        data = filled.to_dict()
        mapping = data["source_metadata"]["source_mapping"]
        mapping["embedding"]["periods"] = [10, None]
        mapping["simplices"]["s0,1"]["offsets"][1][0] = 1
        with self.assertRaisesRegex(ValueError, "face lifts"):
            ChainWindow.from_dict(data)

    def test_abstract_support_never_invents_coordinates(self):
        abstract = operator().locate_support((1, 0))
        self.assertIsNone(abstract["source_mapping_id"])
        self.assertIsNone(abstract["components"])
        self.assertIsNone(abstract["simplices"][0]["coordinates"])
        data = self.triangle().to_dict()
        mapping = data["source_metadata"]["source_mapping"]
        mapping["embedding"] = None
        for v in mapping["vertices"].values():
            v["coordinates"] = None
        for s in mapping["simplices"].values():
            s["offsets"] = None
        location = mapped_operator(ChainWindow.from_dict(data)).locate_support(
            (1, 1, 1)
        )
        self.assertEqual(location["simplices"][0]["original_ids"], (100, 107))
        self.assertIsNone(location["simplices"][0]["coordinates"])

    def test_source_replacement_cross_input_and_snapshot_tampering_rejected(self):
        op = mapped_operator(self.triangle())
        op.readout("locate_support", (1, 1, 1))
        mutations = (
            lambda m: m["vertices"]["0"]["coordinates"].__setitem__(0, 2),
            lambda m: m["vertices"]["0"].__setitem__("original_id", "replacement"),
            lambda m: m["embedding"].__setitem__("periods", [10, None]),
            lambda m: m["embedding"].__setitem__("unit", "cm"),
            lambda m: m.__setitem__("stage_order", ["replacement"]),
            lambda m: m.__setitem__("scale", 9),
            lambda m: m.__setitem__("source_hash", "a" * 64),
        )
        for mutate in mutations:
            data = op.to_result().to_dict()
            mutate(data["input_data"]["source_metadata"]["source_mapping"])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                OperatorResult.from_dict(data)
        data = op.window.to_dict()
        data["source_metadata"]["source_mapping"]["vertices"]["0"]["coordinates"][0] = 2
        changed = ChainWindow.from_dict(data)
        self.assertNotEqual(changed.identity()["input_id"], op.identity["input_id"])
        self.assertEqual(
            changed.identity()["chain_window_hash"],
            op.window.identity()["chain_window_hash"],
        )
        with self.assertRaises(ValueError):
            HomologyOperator(changed, op.solution)
        with self.assertRaises(ValueError):
            changed.locate_chain(
                (1, 1, 1), source_mapping_id=op.window.identity()["source_mapping_id"]
            )
        data = op.to_result().to_dict()
        key = content_id("locate_support", ((1, 1, 1),))
        data["query_results"][key]["value"]["simplices"][0]["original_ids"][0] = 999
        with self.assertRaises(ValueError):
            OperatorResult.from_dict(data)

    def test_invalid_source_protocol_and_non_simplicial_incidence_rejected(self):
        mutations = (
            lambda m: m.__setitem__("version", True),
            lambda m: m.__setitem__("extra", 0),
            lambda m: m.__setitem__("stage", 1),
            lambda m: m.__setitem__("stage_order", ["x", "x"]),
            lambda m: m.__setitem__("source_hash", "not-a-digest"),
            lambda m: m["vertices"]["1"].__setitem__("original_id", 100),
            lambda m: m["vertices"]["0"].__setitem__("coordinates", [float("nan"), 0]),
            lambda m: m["vertices"]["0"].__setitem__("coordinates", [0]),
            lambda m: m["embedding"].__setitem__("metric", "unknown"),
            lambda m: m["embedding"].__setitem__("periods", [0, None]),
            lambda m: m["simplices"]["s0,1"].__setitem__("vertices", ["0", "2"]),
            lambda m: m["simplices"]["s0,1"]["offsets"][0].__setitem__(0, 1),
        )
        original = self.triangle().to_dict()
        for mutate in mutations:
            data = deepcopy(original)
            mutate(data["source_metadata"]["source_mapping"])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                ChainWindow.from_dict(data)
        with self.assertRaises(ValueError):
            replace(self.triangle(), A=Matrix.zero(3, 3))
        with self.assertRaises(ValueError):
            replace(self.triangle(), unit="cm")

    def test_family_rejects_source_stage_and_saved_location_mixing(self):
        points = ((0, 0), (3, 4))
        first = mapped_window(points, ((0,), (1,)), 0, order=("points", "edge"))
        last = mapped_window(points, ((0,), (1,), (0, 1)), 0, 1, ("points", "edge"))
        for field, value in (
            ("stage", 0),
            ("scale", 0),
            ("stage_order", ["other", "edge"]),
            ("source_hash", "b" * 64),
        ):
            data = last.to_dict()
            data["source_metadata"]["source_mapping"][field] = value
            changed = ChainWindow.from_dict(data)
            with self.subTest(field=field), self.assertRaises(ValueError):
                OperatorFamily(
                    (0, 1),
                    (first, changed),
                    (mapped_operator(first), mapped_operator(changed)),
                )
        abstract = replace(last, source_metadata={})
        with self.assertRaises(ValueError):
            OperatorFamily(
                (0, 1),
                (first, abstract),
                (mapped_operator(first), mapped_operator(abstract)),
            )
        family = OperatorFamily(
            (0, 1), (first, last), (mapped_operator(first), mapped_operator(last))
        )
        family.track_location((1, 0), 0, 1)
        for mutate in (
            lambda m: m["vertices"]["0"]["coordinates"].__setitem__(0, 1),
            lambda m: m["embedding"].__setitem__("unit", "cm"),
        ):
            wire = last.to_dict()
            mutate(wire["source_metadata"]["source_mapping"])
            changed = ChainWindow.from_dict(wire)
            with self.assertRaises(ValueError):
                OperatorFamily(
                    (0, 1),
                    (first, changed),
                    (mapped_operator(first), mapped_operator(changed)),
                )
        for schema in (1, 2):
            wire = family.to_result(schema_version=schema).to_dict()
            entry = wire["windows"][1] if schema == 1 else wire["windows"]["stages"][1]
            entry["source_metadata"]["source_mapping"]["vertices"]["0"][
                "original_id"
            ] = "other"
            with self.assertRaises(ValueError):
                OperatorFamilyResult.from_dict(wire)
        data = family.to_result().to_dict()
        location = next(
            q
            for q in data["tracking_readout"].values()
            if q["details"]["query"] == "track_location"
        )
        location["value"]["source_mapping_id"] = "forged"
        with self.assertRaises(ValueError):
            OperatorFamilyResult.from_dict(data)


class GeometryTests(unittest.TestCase):
    def test_selected_mass_is_not_minimum_class_mass(self):
        op = operator()
        self.assertEqual(op.class_representative((1, 0)), (1, 0))
        self.assertEqual(op.selected_mass((1, 0)), Fraction(10))
        # Enumerate z + im(D) directly, without production geometry helpers.
        representatives = ((1, 0), (0, 1))
        minimum = min(
            sum(w * bit for w, bit in zip(op.window.weights, z))
            for z in representatives
        )
        self.assertEqual(minimum, 1)
        self.assertGreater(op.selected_mass((1, 0)), minimum)
        self.assertEqual(
            op.to_result().query_results["minimum_class_mass"].state, "NotComputed"
        )
        self.assertNotIn("shortest_length", op.to_result().to_dict())

    def test_coordinate_geometry_and_metric(self):
        window = ChainWindow(
            1,
            Matrix.zero(0, 3),
            Matrix.zero(3, 0),
            (),
            ("a", "b", "c"),
            (),
            (Fraction(1, 2), 2, 3),
        )
        op = HomologyOperator(window, FeasibleSolver().solve(ProjectionProblem(window)))
        chains = tuple(product((0, 1), repeat=3))
        for z, y in product(chains, repeat=2):
            support_z = tuple(i for i, bit in enumerate(z) if bit)
            shared = tuple(i for i in range(3) if z[i] and y[i])
            union = tuple(i for i in range(3) if z[i] or y[i])
            mass_z = sum(window.weights[i] for i in support_z)
            distance = sum(window.weights[i] for i in range(3) if z[i] != y[i])
            self.assertEqual(op.support(z), support_z)
            self.assertEqual(op.shared_support(z, y), shared)
            self.assertEqual(op.union_support(z, y), union)
            self.assertEqual(op.selected_mass(z), mass_z)
            self.assertEqual(op.class_distance(z, y), distance)
            self.assertGreaterEqual(distance, 0)
            self.assertEqual(op.class_distance(z, y), op.class_distance(y, z))
            self.assertEqual(distance == 0, op.same_class(z, y))
            self.assertEqual(
                op.selected_mass(z) + op.selected_mass(y),
                distance + 2 * sum(window.weights[i] for i in shared),
            )
            for x in chains:
                self.assertLessEqual(
                    distance, op.class_distance(z, x) + op.class_distance(x, y)
                )

    def test_weight_and_arithmetic_identity(self):
        first, changed = operator(), operator((20, 1))
        self.assertEqual(
            first.identity["projection_id"], changed.identity["projection_id"]
        )
        self.assertNotEqual(first.identity["weight_id"], changed.identity["weight_id"])
        self.assertEqual(changed.selected_mass((1, 0)), 20)
        result = first.readout("selected_mass", (1, 0))
        self.assertEqual(result.identity, first.identity)
        self.assertTrue(result.exact)
        floating = operator((10.0, 1.0), "FloatingPoint")
        result = floating.readout("selected_mass", (1, 0))
        self.assertFalse(result.exact)
        self.assertTrue(floating.readout("support", (1, 0)).exact)

    def test_geometry_rejects_noncycles(self):
        window = ChainWindow(
            1, Matrix.identity(1), Matrix.zero(1, 0), ("v",), ("a",), (), (1,)
        )
        op = HomologyOperator(window, FeasibleSolver().solve(ProjectionProblem(window)))
        for query in (
            lambda: op.selected_mass((1,)),
            lambda: op.class_distance((0,), (1,)),
            lambda: op.support((1,)),
            lambda: op.shared_support((1,), (0,)),
            lambda: op.union_support((0,), (1,)),
            lambda: op.minimum_class_mass((1,)),
        ):
            with self.assertRaises(ValueError):
                query()

    def test_minimum_classes_against_independent_cosets_and_witnesses(self):
        degrees = set()
        for fixture in oracle.load_fixtures():
            w = fixture_window(fixture)
            if w.arithmetic == "FloatingPoint":
                continue
            degrees.add(w.k)
            op = HomologyOperator(w, FeasibleSolver().solve(ProjectionProblem(w)))
            a, d = oracle.columns(fixture["A"]), oracle.columns(fixture["D"])
            for coset in oracle.quotient_classes(fixture):
                expected = min(
                    (oracle.mass(chain, w.weights), unpack(chain, w.n))
                    for chain in coset
                )
                for chain in coset:
                    z = unpack(chain, w.n)
                    result = op.minimum_class_mass(z)
                    self.assertEqual(result.state, "Computed")
                    self.assertTrue(result.exact)
                    self.assertEqual(result.identity, op.identity)
                    y = result.details["representative"]
                    b = result.details["boundary_witness"]
                    self.assertEqual((result.value, y), expected)
                    self.assertEqual(oracle.apply(a, pack(y)), 0)
                    self.assertEqual(op.P.apply(y), op.P.apply(z))
                    self.assertEqual(oracle.apply(d, pack(b)), pack(y) ^ chain)
                    self.assertIn(pack(y) ^ chain, oracle.boundaries(fixture))
            record = op.to_result()
            self.assertEqual(record, OperatorResult.from_json(record.to_json()))
        self.assertTrue({0, 1, 2} <= degrees)

    def test_six_edge_minima_are_separate_from_minimax_section(self):
        fixture = next(f for f in oracle.load_fixtures() if f["id"] == "h1_k4_stage_4")
        w = fixture_window(fixture)
        op = HomologyOperator(
            w,
            solve_projection(
                ProjectionProblem(w, requested_certificate_level="ExactOptimal"),
                "ExhaustiveExactSolver",
            ),
        )
        nonzero = [
            coset for coset in oracle.quotient_classes(fixture) if 0 not in coset
        ]
        before = op.P
        minima = [op.minimum_class_mass(unpack(c[0], w.n)).value for c in nonzero]
        selected = [op.selected_mass(unpack(c[0], w.n)) for c in nonzero]
        self.assertEqual(sorted(minima), [8, 8, 9])
        self.assertEqual(sorted(selected), [8, 9, 9])
        self.assertEqual(op.P, before)
        self.assertEqual(op.solution.objective.value, Fraction(9, 8))

    def test_dependent_boundaries_count_distinct_elements_and_stable_ties(self):
        w = replace(
            operator((1, 1)).window,
            D=Matrix.from_columns(((1, 1), (1, 1), (0, 0)), nrows=2),
            basis_next=("a", "duplicate", "zero"),
            weights=(1, 1),
            arithmetic="ExactInteger",
        )
        op = HomologyOperator(w, FeasibleSolver().solve(ProjectionProblem(w)))
        result = op.minimum_class_mass((1, 0), ResourceLimits(state_limit=2))
        self.assertEqual(result.value, 1)
        self.assertEqual(result.details["representative"], (0, 1))
        self.assertEqual(result.details["boundary_witness"], (1, 0, 0))
        self.assertEqual(result.details["enumerated_boundaries"], 2)
        self.assertEqual(result.details["total_boundaries"], 2)
        self.assertEqual(
            op.minimum_class_mass((0, 1)).details["representative"], (0, 1)
        )

    def test_budget_candidates_bounds_and_final_deadline(self):
        op = operator()
        for limits in (
            ResourceLimits(state_limit=0),
            ResourceLimits(state_limit=1),
            ResourceLimits(wall_time_limit=0),
            ResourceLimits(matrix_entry_limit=0),
        ):
            result = op.minimum_class_mass((1, 0), limits)
            self.assertEqual(result.state, "ResourceExhausted")
            self.assertIsNone(result.value)
            self.assertIsNone(result.exact)
            self.assertEqual(result.details["representative"], (1, 0))
            self.assertEqual(result.details["lower_bound"], 0)
            self.assertEqual(result.details["upper_bound"], 10)
            self.assertEqual(result.details["certificate_level"], "CertifiedInterval")
            self.assertEqual(QueryResult.from_dict(result.to_dict()), result)
        with patch(
            "homology_operator.solver.perf_counter", side_effect=[0] * 6 + [20] * 10
        ):
            late = op.minimum_class_mass((1, 0))
        self.assertEqual(late.state, "ResourceExhausted")
        self.assertEqual(late.details["candidate_mass"], 1)
        self.assertEqual(late.details["upper_bound"], 1)
        self.assertIsNone(late.details["optimality_proof"])
        record = op.to_result()
        self.assertEqual(record, OperatorResult.from_json(record.to_json()))

    def test_minimum_legacy_unavailable_records_remain_readable(self):
        op = operator()
        record = op.to_result().to_dict()
        record["query_results"]["minimum_class_mass"] = QueryResult(
            "Unavailable", identity=op.identity, details={"method": "not implemented"}
        ).to_dict()
        restored = OperatorResult.from_dict(record).to_operator()
        self.assertEqual(restored.minimum_class_mass((1, 0)).value, 1)

    def test_zero_class_empty_homology_and_unsupported_requests(self):
        op = operator()
        zero = op.minimum_class_mass((1, 1))
        self.assertEqual((zero.state, zero.value), ("Computed", 0))
        self.assertEqual(zero.details["representative"], (0, 0))
        self.assertEqual(zero.details["optimality_proof"], "NonnegativeMass")
        for n in (0, 2):
            w = ChainWindow(
                0,
                Matrix.zero(0, n),
                Matrix.identity(n),
                (),
                tuple(f"v{i}" for i in range(n)),
                tuple(f"b{i}" for i in range(n)),
                (1,) * n,
            )
            empty = HomologyOperator(w, FeasibleSolver().solve(ProjectionProblem(w)))
            self.assertEqual(empty.minimum_class_mass((1,) * n).value, 0)
        for changed, limits in (
            (operator((10.0, 1.0), "FloatingPoint"), None),
            (op, ResourceLimits(packed_word_limit=1)),
        ):
            unavailable = changed.minimum_class_mass((1, 0), limits)
            self.assertEqual(unavailable.state, "Unavailable")
            self.assertNotIn("certificate_level", unavailable.details)
            record = changed.to_result()
            self.assertEqual(record, OperatorResult.from_json(record.to_json()))
        for z in ((True, 0), (1,), (2, 0)):
            with self.assertRaises(ValueError):
                op.minimum_class_mass(z)
        with self.assertRaises(ValueError):
            op.minimum_class_mass((1, 0), {})

    def test_minimum_snapshot_rejects_forged_witness_optimum_and_identity(self):
        op = operator((Fraction(10, 7), Fraction(1, 7)))
        result = op.minimum_class_mass((1, 0))
        record = op.to_result()
        self.assertEqual(
            record, OperatorResult.from_json(record.to_json()).to_operator().to_result()
        )
        other = operator((20, 1)).minimum_class_mass((1, 0))
        with self.assertRaises(ValueError):
            require_same_identity(result, other)
        for field, value in (
            ("representative", [1, 0]),
            ("boundary_witness", [0]),
            ("input_cycle", [0, 0]),
            ("total_boundaries", 1),
            ("enumerated_boundaries", 1),
            ("certificate_level", "Feasible"),
            ("optimality_proof", "NonnegativeMass"),
            ("upper_bound", 10),
            ("method", "not implemented"),
            ("resource_usage", None),
        ):
            bad = deepcopy(record.to_dict())
            bad["query_results"]["minimum_class_mass"]["details"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                OperatorResult.from_dict(bad)
        bad = deepcopy(record.to_dict())
        q = bad["query_results"]["minimum_class_mass"]
        q["value"] = {"$fraction": [10, 7]}
        q["details"].update(representative=[1, 0], boundary_witness=[0])
        for name in ("candidate_mass", "upper_bound", "lower_bound"):
            q["details"][name] = {"$fraction": [10, 7]}
        with self.assertRaisesRegex(ValueError, "replay"):
            OperatorResult.from_dict(bad)


if __name__ == "__main__":
    unittest.main()
