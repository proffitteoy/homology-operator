"""Frozen filtration corpus against independent PH reduction and coset ranks."""

import ast
from dataclasses import replace
from itertools import product
from pathlib import Path
import unittest

from homology_operator import (
    ChainWindow,
    HomologyOperator,
    Matrix,
    OperatorFamily,
    OperatorFamilyResult,
    QueryResult,
    ProjectionProblem,
    solve_projection,
)
from homology_operator.chain import matrix_data
from homology_operator.result import make_identity
from test_joint import oracle, window, pack, unpack
from test_family import op, merge_family


def corpus_families():
    fixtures = oracle.load_fixtures()
    grouped, singles = {}, []
    for fixture in fixtures:
        info = fixture["expected"].get("filtration_slice")
        if info and not fixture["id"].endswith("permuted"):
            grouped.setdefault(info["family"], []).append(fixture)
        elif not info:
            singles.append((fixture["id"], [fixture]))
    result = [
        (name, sorted(stages, key=lambda f: f["expected"]["filtration_slice"]["stage"]))
        for name, stages in grouped.items()
    ] + singles
    k4 = grouped["h1_k4_all_deaths"]
    result.append(("h1_survivor_prefix", k4[:6]))
    permuted = list(k4)
    permuted[4] = next(f for f in fixtures if f["id"].endswith("permuted"))
    result.append(("h1_permuted_coordinates", permuted))
    return result


def family_from(stages):
    windows = tuple(window(f) for f in stages)
    scales = tuple(
        f["expected"].get("filtration_slice", {}).get("scale", i)
        for i, f in enumerate(stages)
    )
    scales = tuple(i if scale is None else scale for i, scale in enumerate(scales))
    return OperatorFamily(scales, windows, tuple(op(w) for w in windows))


class FamilyJointTests(unittest.TestCase):
    def test_cross_solver_replacements_preserve_ph_and_action_bound_geometry(self):
        configurations = 0
        for name, stages in corpus_families():
            base = family_from(stages)
            for policy in (
                "FeasibleSolver",
                "ExhaustiveExactSolver",
                "GreedyCertifiedSolver",
                "Mixed",
            ):
                operators = []
                for i, fixture in enumerate(stages):
                    method = policy
                    if policy == "Mixed":
                        method = (
                            "Rank2ExactSolver"
                            if oracle.betti(fixture) == 2
                            else (
                                "FeasibleSolver",
                                "ExhaustiveExactSolver",
                                "GreedyCertifiedSolver",
                            )[i % 3]
                        )
                    if fixture["arithmetic"] == "FloatingPoint":
                        method = "FeasibleSolver"
                    solution = solve_projection(
                        ProjectionProblem(base.windows[i]), method
                    )
                    operators.append(HomologyOperator(base.windows[i], solution))
                family = replace(base, operators=tuple(operators))
                configurations += 1
                with self.subTest(family=name, policy=policy):
                    bars = family.barcode()
                    self.assertEqual(
                        tuple(
                            (bar["birth_stage"], bar["death_stage"])
                            for bar in bars.value
                            for _ in range(bar["multiplicity"])
                        ),
                        oracle.persistence_barcode(stages),
                    )
                    history = family.barcode_basis().value
                    for stage, operator in enumerate(family.operators):
                        active = [
                            v
                            for bar in history
                            for v in bar["vectors"]
                            if v["stage"] == stage
                        ]
                        self.assertEqual(
                            Matrix.from_columns(
                                (v["representative"] for v in active), operator.window.n
                            ).rank(),
                            operator.betti(),
                        )
                    for bar in history:
                        for left, right in zip(bar["vectors"], bar["vectors"][1:]):
                            self.assertEqual(
                                family.track_class(
                                    left["representative"],
                                    left["stage"],
                                    right["stage"],
                                ).value,
                                right["representative"],
                            )
                        if bar["death_stage"] is not None:
                            last = bar["vectors"][-1]
                            self.assertEqual(
                                family.track_class(
                                    last["representative"],
                                    last["stage"],
                                    bar["death_stage"],
                                ).value,
                                (0,) * family.windows[bar["death_stage"]].n,
                            )
                    for (i, j), expected_rank in oracle.persistence_ranks(
                        stages
                    ).items():
                        self.assertEqual(
                            family.transport_rank(i, j).value, expected_rank
                        )
                        self.assertEqual(
                            family.transport_certificate(i, j).state, "Computed"
                        )
                        inclusion = oracle.columns(matrix_data(family.inclusion(i, j)))
                        P = oracle.columns(matrix_data(family.stage(j).P))
                        for z in oracle.cycles(stages[i]):
                            vector = unpack(z, family.windows[i].n)
                            expected = oracle.apply(P, oracle.apply(inclusion, z))
                            self.assertEqual(
                                pack(family.track_class(vector, i, j).value), expected
                            )
                            self.assertAlmostEqual(
                                family.track_mass(vector, i, j).value,
                                oracle.mass(expected, oracle.weights(stages[j])),
                            )
                            self.assertEqual(
                                family.track_support(vector, i, j).value,
                                oracle.support(expected),
                            )
                            for middle in range(i, j + 1):
                                via = family.track_class(vector, i, middle).value
                                self.assertEqual(
                                    family.track_class(via, middle, j).value,
                                    family.track_class(vector, i, j).value,
                                )
                    snapshot = family.to_result()
                    for _ in range(2):
                        restored = OperatorFamilyResult.from_json(
                            snapshot.to_json()
                        ).to_family()
                        self.assertEqual(
                            restored.to_result().to_json(), snapshot.to_json()
                        )
        self.assertEqual(configurations, 44)

    def test_all_five_solvers_dense_and_structured_in_one_family(self):
        from test_structured import cyclic_window

        window, _ = cyclic_window(2)
        methods = (
            "FeasibleSolver",
            "ExhaustiveExactSolver",
            "GreedyCertifiedSolver",
            "Rank2ExactSolver",
            "StructuredFamilySolver",
            "StructuredFamilySolver",
        )
        operators = []
        for i, method in enumerate(methods):
            problem = ProjectionProblem(
                window,
                input_structure="CyclicTrace"
                if method == "StructuredFamilySolver"
                else "GeneralChainWindow",
                matrix_free_output=i == 5,
            )
            operators.append(
                HomologyOperator(window, solve_projection(problem, method))
            )
        family = OperatorFamily(tuple(range(6)), (window,) * 6, tuple(operators))
        for i in range(6):
            for j in range(i, 6):
                self.assertEqual(family.transport_rank(i, j).value, 2)
                self.assertEqual(family.transport_certificate(i, j).state, "Computed")
                for z in range(8):
                    vector = unpack(z, 3)
                    target = operators[j].project(vector)
                    self.assertEqual(family.track_class(vector, i, j).value, target)
                    self.assertEqual(family.track_mass(vector, i, j).value, sum(target))
                    for middle in range(i, j + 1):
                        via = family.track_class(vector, i, middle).value
                        self.assertEqual(
                            family.track_class(via, middle, j).value, target
                        )
        bars = family.barcode().value
        self.assertEqual(
            tuple(
                (bar["birth_stage"], bar["death_stage"])
                for bar in bars
                for _ in range(bar["multiplicity"])
            ),
            ((0, None), (0, None)),
        )
        snapshot = family.to_result()
        for _ in range(3):
            restored = OperatorFamilyResult.from_json(snapshot.to_json()).to_family()
            self.assertEqual(restored.to_result().to_json(), snapshot.to_json())
        wire = snapshot.to_dict()
        # Query the structured stage so that its distinct representation/run is present.
        operators[5].readout("support", (1, 0, 0))
        wire["stage_results"][0]["query_results"] = (
            operators[5].to_result().to_dict()["query_results"]
        )
        with self.assertRaises(ValueError):
            OperatorFamilyResult.from_dict(wire)

    def test_numerical_failures_and_bool_rank_tampering_are_explicit(self):
        source = ChainWindow(
            1,
            Matrix.zero(0, 1),
            Matrix.zero(1, 0),
            (),
            ("a",),
            (),
            (1e-308,),
            arithmetic="FloatingPoint",
        )
        target = replace(source, weights=(1e308,))
        family = OperatorFamily(
            (0, 1), (source, target), (op(source), op(target)), "Variable"
        )
        result = family.endpoint_mass_bound((1,), 0, 1)
        self.assertEqual(result.state, "Unavailable")
        self.assertEqual(result.details["reason"], "NumericalFailure")
        large = ChainWindow(
            1,
            Matrix.zero(0, 2),
            Matrix.zero(2, 0),
            (),
            ("a", "b"),
            (),
            (1e308, 1e308),
            arithmetic="FloatingPoint",
        )
        overflow = OperatorFamily((0,), (large,), (op(large),))
        self.assertEqual(overflow.track_mass((1, 1), 0, 0).state, "Unavailable")
        self.assertEqual(
            overflow.to_result(),
            OperatorFamilyResult.from_json(overflow.to_result().to_json()),
        )
        normal = merge_family()
        normal.transport(0, 1)
        wire = normal.to_result().to_dict()
        wire["rank_readout"]["0:1"]["value"] = True
        with self.assertRaises(ValueError):
            OperatorFamilyResult.from_dict(wire)

    def test_all_frozen_families_rank_barcode_and_expected_endpoints(self):
        covered = set()
        for name, stages in corpus_families():
            with self.subTest(family=name):
                covered.update(f["id"] for f in stages)
                family = family_from(stages)
                ranks = oracle.persistence_ranks(stages)
                for (i, j), expected in ranks.items():
                    self.assertEqual(family.transport_rank(i, j).value, expected)
                    self.assertEqual(
                        family.transport_certificate(i, j).state, "Computed"
                    )
                bars = family.barcode()
                expanded = tuple(
                    (bar["birth_stage"], bar["death_stage"])
                    for bar in bars.value
                    for _ in range(bar["multiplicity"])
                )
                self.assertEqual(expanded, oracle.persistence_barcode(stages))
                if name == "h1_k4_all_deaths":
                    self.assertEqual(expanded, ((1, 4), (2, 5), (3, 6)))
                elif name == "h1_survivor_prefix":
                    self.assertEqual(expanded, ((1, 4), (2, 5), (3, None)))
                elif name == "h0_interval_merge":
                    self.assertEqual(expanded, ((0, 1), (0, None)))
                for (i, j), expected in ranks.items():
                    self.assertEqual(
                        sum(b <= i and (d is None or j < d) for b, d in expanded),
                        expected,
                    )
                snapshot = family.to_result()
                self.assertEqual(
                    snapshot, OperatorFamilyResult.from_json(snapshot.to_json())
                )
        self.assertEqual(covered, {f["id"] for f in oracle.load_fixtures()})

    def test_all_cycles_tracking_geometry_and_endpoint_control(self):
        for name, stages in corpus_families():
            family = family_from(stages)
            for i, source in enumerate(stages):
                for j in range(i, len(stages)):
                    target = stages[j]
                    inclusion = oracle.columns(matrix_data(family.inclusion(i, j)))
                    projection = oracle.columns(matrix_data(family.stage(j).P))
                    weights = oracle.weights(target)
                    chains = oracle.cycles(source)
                    for x in chains:
                        with self.subTest(family=name, interval=(i, j), chain=x):
                            vector = unpack(x, source["A"]["ncols"])
                            expected = oracle.apply(
                                projection, oracle.apply(inclusion, x)
                            )
                            tracked = family.track_class(vector, i, j)
                            self.assertEqual(pack(tracked.value), expected)
                            self.assertAlmostEqual(
                                family.track_mass(vector, i, j).value,
                                oracle.mass(expected, weights),
                            )
                            self.assertEqual(
                                family.track_support(vector, i, j).value,
                                oracle.support(expected),
                            )
                            bound = family.endpoint_mass_bound(vector, i, j)
                            self.assertIn(bound.state, ("Computed",))
                            if bound.exact:
                                self.assertLessEqual(
                                    oracle.mass(expected, weights),
                                    bound.value["mass_bound"],
                                )
                            else:
                                self.assertIsNone(bound.value["bound_verified"])
                            for middle in range(i, j + 1):
                                previous = family.track_class(vector, i, middle).value
                                self.assertEqual(
                                    family.track_class(previous, middle, j).value,
                                    tracked.value,
                                )
                    for x, y in product(chains, repeat=2):
                        vx, vy = (
                            unpack(x, source["A"]["ncols"]),
                            unpack(y, source["A"]["ncols"]),
                        )
                        px, py = (
                            oracle.apply(projection, oracle.apply(inclusion, chain))
                            for chain in (x, y)
                        )
                        self.assertEqual(
                            family.track_shared_support(vx, vy, i, j).value,
                            oracle.shared_support(px, py),
                        )
                        self.assertEqual(
                            family.track_union_support(vx, vy, i, j).value,
                            oracle.union_support(px, py),
                        )

    def test_projection_change_preserves_topology_and_changes_geometry_identity(self):
        family = merge_family()
        target = family.stage(1)
        projection = Matrix.from_rows(((0, 0), (1, 1)))
        identity = make_identity(
            target.window, projection, target.solution.solver_run_id
        )
        solution = replace(
            target.solution,
            projection=projection,
            identity=identity,
            objective=QueryResult("NotComputed", identity=identity),
        )
        alternative = HomologyOperator(target.window, solution)
        changed = replace(
            family, operators=(family.stage(0), alternative, family.stage(2))
        )
        self.assertEqual(family.barcode().value, changed.barcode().value)
        self.assertNotEqual(family.identity, changed.identity)
        self.assertEqual(family.track_mass((1, 0), 0, 1).value, 10)
        self.assertEqual(changed.track_mass((1, 0), 0, 1).value, 1)
        snapshot = family.to_result().to_dict()
        snapshot["tracking_readout"] = changed.to_result().to_dict()["tracking_readout"]
        with self.assertRaises(ValueError):
            OperatorFamilyResult.from_dict(snapshot)

    def test_production_does_not_import_oracle_or_ph_packages(self):
        root = Path(__file__).resolve().parents[1] / "src/homology_operator"
        for path in root.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else []
                )
                self.assertFalse(
                    any(
                        name.split(".")[0]
                        in {"tests", "oracle", "reference", "ripser", "gudhi"}
                        for name in names
                    ),
                    path,
                )
