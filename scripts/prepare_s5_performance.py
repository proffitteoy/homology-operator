"""Predeclare S5 scale/workload grid, then freeze without selecting by pilot speed."""

import argparse
from copy import deepcopy
from hashlib import sha256
from itertools import combinations
import json
from math import cos, sin, pi, dist
from pathlib import Path
import sys

from benchmark_s5 import digest, frozen_environment

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))


def grid_manifest(columns, rows=2):
    from oracle.simplicial import synthetic_manifest

    vertices = list(range(columns * rows))
    triangles = []
    for y in range(rows - 1):
        for x in range(columns - 1):
            a, b = y * columns + x, y * columns + x + 1
            c, d = (y + 1) * columns + x, (y + 1) * columns + x + 1
            triangles.extend(((a, b, d), (a, c, d)))
    edges = sorted(
        {edge for triangle in triangles for edge in combinations(triangle, 2)}
    )
    births = [((v,), 0) for v in vertices] + [(s, 1) for s in edges]
    births += [(s, 2) for s in triangles[:-1]]  # one unfilled triangle leaves beta_1=1
    return synthetic_manifest(
        f"small_beta/grid_{columns}x{rows}", births, [0, 1, 2], q=1
    )


def high_beta_manifest(n):
    from oracle.simplicial import synthetic_manifest

    births = [((v,), 0) for v in range(2 * n)]
    births += [((u, v), 1) for u in range(n) for v in range(n, 2 * n)]
    return synthetic_manifest(f"high_beta/K{n}_{n}", births, [0, 1], q=1)


def long_manifest(stages):
    from oracle.simplicial import synthetic_manifest

    births = [((v,), v) for v in range(stages)]
    births += [((v - 1, v), v) for v in range(1, stages)]
    return synthetic_manifest(
        f"long_filtration/path_{stages}", births, [i // 2 for i in range(stages)], q=0
    )


def vr_manifest(n):
    from oracle.simplicial import synthetic_manifest, freeze_manifest

    coordinates = [[cos(2 * pi * v / n), sin(2 * pi * v / n)] for v in range(n)]
    scales = [0, 0.65, 1.2]
    births = [((v,), 0) for v in range(n)]
    edges = {}
    for edge in combinations(range(n), 2):
        length = dist(*(coordinates[v] for v in edge))
        stage = next(
            (i for i, threshold in enumerate(scales) if length <= threshold), None
        )
        if stage is not None:
            edges[edge] = stage
    births += list(edges.items())
    for triangle in combinations(range(n), 3):
        faces = tuple(combinations(triangle, 2))
        if all(face in edges for face in faces):
            births.append((triangle, max(edges[face] for face in faces)))
    manifest = synthetic_manifest(f"vr/circle_{n}", births, scales, q=1)
    for vertex in manifest["vertices"]:
        vertex["coordinates"] = coordinates[vertex["id"]]
    manifest["weight_policy"] = {
        "arithmetic": "FloatingPoint",
        "semantics_by_degree": {
            "0": "unit",
            "1": "euclidean_length",
            "2": "euclidean_area",
        },
        "units_by_degree": {"0": None, "1": "length", "2": "length^2"},
    }
    for record in manifest["simplices"]:
        simplex = record["vertices"]
        if len(simplex) == 1:
            weight = 1.0
        elif len(simplex) == 2:
            weight = dist(*(coordinates[v] for v in simplex))
        else:
            a, b, c = (coordinates[v] for v in simplex)
            weight = (
                abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2
            )
        record["weight"] = weight
    manifest["source"]["payload"].update(
        generator="explicit circle Euclidean VR q+1 truncation v1",
        coordinates=coordinates,
        thresholds=scales,
        weight_formula="unit vertices, Euclidean edges, determinant triangle area",
    )
    manifest["source"]["sha256"] = digest(manifest["source"]["payload"])
    return freeze_manifest(manifest)


def scale_metadata(manifest):
    from oracle.simplicial import build_windows

    rows = []
    for degree, slices in build_windows(manifest).items():
        for stage, window in enumerate(slices):
            a, d = window.A.rref()[0], window.D.rref()[0]
            nnz_a, nnz_d = sum(map(sum, window.A.rows)), sum(map(sum, window.D.rows))
            rows.append(
                {
                    "degree": degree,
                    "stage": stage,
                    "dimensions": [window.m, window.n, window.p],
                    "nnz_A_D": [nnz_a, nnz_d],
                    "rref_nnz_A_D": [sum(map(sum, a.rows)), sum(map(sum, d.rows))],
                    "rank_A_D": [window.A.rank(), window.D.rank()],
                    "betti": window.n - window.A.rank() - window.D.rank(),
                }
            )
    return rows


def make_plan():
    from oracle.simplicial import audit_inputs, freeze_manifest, load_manifests
    from oracle.gudhi_oracle import gudhi_topology
    from check_s5_correctness import make_corpus

    inputs, cases = {}, []

    def add(
        manifest,
        identifier=None,
        workload="Topology",
        query_count=0,
        routes=("r0", "reference", "integrated", "gudhi"),
        solver="FeasibleSolver",
        repeats=5,
        limits=None,
    ):
        inputs[manifest["id"]] = manifest
        certificate = (
            "Feasible"
            if solver == "FeasibleSolver"
            else "ExactOptimal"
            if solver == "ExhaustiveExactSolver"
            else "CertifiedInterval"
        )
        cases.append(
            {
                "id": identifier or manifest["id"] + "/" + workload,
                "input_id": manifest["id"],
                "workload": workload,
                "solver": solver,
                "requested_certificate_level": certificate,
                "query_count": query_count,
                "routes": list(routes),
                "repeats": 1,
                "formal_repeats": repeats,
                "warm_repeats": 2,
                "formal_warm_repeats": 5,
                "resource_limits": limits
                or {
                    "state_limit": 100000,
                    "wall_time_limit": 20.0,
                    "matrix_entry_limit": 1000000,
                },
                "expected_topology_hash": digest(gudhi_topology(manifest)["topology"]),
                "scale_metadata": scale_metadata(manifest),
                "actual_input_audit": audit_inputs(manifest),
            }
        )

    for columns in (10, 18):
        add(grid_manifest(columns), repeats=1)
    for n in (4, 5):
        add(high_beta_manifest(n))
    for stages in (16, 32):
        add(long_manifest(stages), repeats=1)
    for n in (10, 18):
        add(
            vr_manifest(n),
            routes=(
                "r0",
                "reference",
                "integrated",
                "gudhi",
                "edge_collapse",
                "rips_persistence",
            ),
            repeats=1,
        )
    ring = next(m for m in load_manifests() if m["id"] == "ring_repeated_scale")
    for count in (0, 1, 8, 64, 1024):
        routes = (
            (
                "r0",
                "reference",
                "integrated",
                "gudhi",
                "native_explicit",
                "factorized_scalar",
                "hc_workspace",
            )
            if count == 8
            else ("reference", "integrated", "gudhi")
        )
        add(
            ring,
            f"query/q{count}",
            "Topology" if count == 0 else "Joint-basic",
            count,
            routes=routes,
            repeats=1 if count == 1024 else 5,
        )
    for arithmetic in ("ExactRational", "FloatingPoint"):
        weighted = next(
            m
            for m in make_corpus(random_cases=0)["manifests"]
            if m["id"] == "ring_weights_" + arithmetic
        )
        add(
            weighted,
            "weight/" + arithmetic,
            "Joint-basic",
            8,
            routes=("reference", "integrated", "gudhi"),
        )
    bigint = deepcopy(ring)
    bigint["id"] = "ring_bigint"
    bigint["weight_policy"]["semantics_by_degree"] = {
        str(k): "abstract_positive_cost" for k in range(3)
    }
    for i, record in enumerate(bigint["simplices"]):
        record["weight"] = 2**130 + i
    bigint["source"]["payload"]["weight_transform"] = "2^130 + simplex index"
    bigint["source"]["sha256"] = digest(bigint["source"]["payload"])
    add(
        freeze_manifest(bigint),
        "weight/bigint",
        "Joint-basic",
        8,
        routes=("reference", "integrated", "gudhi"),
    )
    add(
        ring,
        "certificate/exhaustive",
        "Joint-certified",
        8,
        routes=("reference", "integrated"),
        solver="ExhaustiveExactSolver",
    )
    floating = next(
        m for m in inputs.values() if m["id"] == "ring_weights_FloatingPoint"
    )
    add(
        floating,
        "failure/float_exact_unavailable",
        "Joint-certified",
        8,
        routes=("reference", "integrated"),
        solver="ExhaustiveExactSolver",
    )
    add(
        ring,
        "failure/entries0",
        routes=("reference", "integrated"),
        limits={
            "state_limit": 100000,
            "wall_time_limit": 20.0,
            "matrix_entry_limit": 0,
        },
    )
    general = {
        "k": 1,
        "A": [[0, 0, 0]],
        "D": [[1], [1], [0]],
        "basis": ["x", "y", "z"],
        "weights": [1, 2, 3],
        "source": "explicit AD=0 algebra window, no simplicial adapter",
    }
    cases.append(
        {
            "id": "general_chain/gudhi_na",
            "input_id": "general_chain",
            "input_hash": digest(general),
            "chain_window": general,
            "workload": "Topology",
            "query_count": 0,
            "solver": "FeasibleSolver",
            "requested_certificate_level": "Feasible",
            "routes": ["gudhi"],
            "repeats": 1,
            "formal_repeats": 5,
            "warm_repeats": 2,
            "formal_warm_repeats": 5,
            "expected_topology_hash": None,
            "resource_limits": {
                "state_limit": 100000,
                "wall_time_limit": 20.0,
                "matrix_entry_limit": 1000000,
            },
        }
    )
    return {
        "schema_version": 1,
        "phase": "pilot",
        "seed": 7405,
        "inputs": inputs,
        "cases": cases,
        "blocks": 1,
        "process_wall_seconds": 180.0,
        "rss_budget_bytes": 2 * 1024**3,
        "rss_budget_policy": "post-run absolute peak assessment, not an OS hard memory limit",
        "statistics": {
            "minimum_paired_blocks": 10,
            "bootstrap_draws": 10000,
            "interval": "95% percentile paired block median log ratios",
            "tail_quantiles": "not reported",
        },
        "threads": {
            key: "1"
            for key in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
                "BLIS_NUM_THREADS",
            )
        },
        "predeclaration": {
            "formal_blocks": 10,
            "cold_repeats": "5 except predeclared grid/long/VR/q1024=1",
            "warm_repeats": 5,
            "selection": "no route/case/threshold selection by pilot or formal performance",
            "scale_scope": "finite dense boundary grid; VR10/18 vertices, grid20/36 vertices, max chain69/VR90; no universal scale claim",
            "cost_scope": "same explicit frontend, mandatory validation, full requested outputs; topology and joint workloads separated",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-pilot", type=Path)
    parser.add_argument(
        "--pilot-manifest",
        type=Path,
        default=ROOT / "benchmarks/s5_performance_pilot_manifest.json",
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be new")
    if args.freeze_pilot:
        plan = json.loads(args.pilot_manifest.read_text("utf-8"))
        report = json.loads(args.freeze_pilot.read_text("utf-8"))
        if report["plan_hash"] != digest(plan):
            raise ValueError("pilot report does not match predeclared grid")
        if any(
            r["process_state"] != "completed"
            or any(
                s["state"] == "Mismatch" for s in r.get("result", {}).get("records", [])
            )
            for r in report["rows"]
        ):
            raise ValueError(
                "fix execution/correctness errors and preserve old pilot before freeze; no performance-based deletion"
            )
        for group in report["summary"]:
            if group["reference_comparison"]["mismatched_blocks"]:
                raise ValueError("same-output mismatch in pilot")
        plan["phase"], plan["blocks"] = (
            "formal",
            plan["predeclaration"]["formal_blocks"],
        )
        for case in plan["cases"]:
            case["repeats"] = case["formal_repeats"]
            case["warm_repeats"] = case["formal_warm_repeats"]
        plan["pilot_sha256"] = sha256(
            args.freeze_pilot.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        plan["pilot_manifest_hash"] = report["plan_hash"]
        plan["freeze_environment"] = frozen_environment()
    else:
        plan = make_plan()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        f"Predeclared {len(plan['cases'])} cases and {sum(len(c['routes']) for c in plan['cases'])} case/route pairs ({plan['phase']})"
    )


if __name__ == "__main__":
    main()
