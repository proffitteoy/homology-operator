"""S4-09 frozen same-output acceptance, serial process blocks and separate RSS."""

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import importlib.util
import json
import math
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
from time import perf_counter
import traceback

from benchmark_reference import digest, peak_rss, source_snapshot, write_json

ROOT = Path(__file__).resolve().parents[1]
R0 = "54ce78bccdcba619ffa2a4d76aeb450bfd24270e"
CANDIDATE = "7fa812d5e76ca80ac16316cb212d133c0639bfd7"
DEFAULT_ROUTES = ("r0", "reference", "integrated")


def measured_snapshot(source, revision, native=False):
    snapshot = source_snapshot(source, revision)
    if native:
        hashes = {}
        paths = sorted((source / "native/src").rglob("*.rs")) + [
            source / "native/Cargo.toml",
            source / "native/Cargo.lock",
            source / "native/pyproject.toml",
        ]
        for path in paths:
            relative = path.relative_to(source).as_posix()
            data = path.read_bytes().replace(b"\r\n", b"\n")
            committed = subprocess.check_output(
                ["git", "show", f"{revision}:{relative}"], cwd=ROOT
            ).replace(b"\r\n", b"\n")
            if data != committed:
                raise ValueError(f"native source differs: {relative}")
            hashes[relative] = sha256(data).hexdigest()
        snapshot["native_lf_sha256"] = hashes
    return snapshot


def make_manifest(baseline_root):
    from homology_operator import ChainWindow, Matrix, ResourceLimits
    from homology_operator.chain import _thaw_metadata
    from benchmark_compact import case_window
    from benchmark_native import solver_cases
    from compare_solvers import fixture_problem

    fixtures = json.loads((ROOT / "tests/fixtures/reference.json").read_text("utf-8"))
    sourced = {f["id"]: f for f in fixtures["fixtures"]}
    windows, provenance, cases = {}, {}, []

    def add(
        name,
        stages,
        count=8,
        method="FeasibleSolver",
        target="Feasible",
        routes=DEFAULT_ROUTES,
        scales=None,
        limits=None,
        structure="GeneralChainWindow",
        matrix_free=False,
        repeats=5,
    ):
        ids = []
        for i, window in enumerate(stages):
            key = f"{name}/{i}"
            windows[key] = window.to_dict()
            provenance[key] = _thaw_metadata(window.source_metadata)
            ids.append(key)
        queries = []
        for q in range(count):
            i = q % len(stages)
            basis = stages[i].A.kernel_basis() or ((0,) * stages[i].n,)
            queries.append(
                {
                    "stage": i,
                    "z": basis[q % len(basis)],
                    "y": basis[(q + 1) % len(basis)],
                }
            )
        cases.append(
            {
                "id": name,
                "fixture_ids": ids,
                "scales": scales,
                "solver": method,
                "requested_certificate_level": target,
                "resource_limits": vars(limits or ResourceLimits()),
                "input_structure": structure,
                "matrix_free_output": matrix_free,
                "query_count": count,
                "queries": queries,
                "routes": list(routes),
                "formal_repeats": repeats,
                "repeat_exception": "large explicit input or legacy quadratic family snapshot"
                if repeats == 1
                else None,
                "workload": "Joint-certified"
                if method != "FeasibleSolver"
                else "Topology"
                if count == 0
                else "Joint-basic",
            }
        )

    k4 = fixture_problem(sourced["h1_k4_stage_4"]).window
    for count in (0, 1, 8, 64, 1024):
        routes = list(DEFAULT_ROUTES)
        if count in (0, 64, 1024):
            routes.append("native_explicit")
        if count == 64:
            routes += ["factorized_scalar", "factorized_batch"]
        add(f"k4/q{count}", (k4,), count=count, routes=routes)
    for name, weights, arithmetic in (
        (
            "rational",
            tuple(Fraction(i + 1, 2 * i + 3) for i in range(k4.n)),
            "ExactRational",
        ),
        ("bigint", (10**100,) * k4.n, "ExactInteger"),
    ):
        window = replace(
            k4,
            weights=weights,
            arithmetic=arithmetic,
            source_metadata={**k4.source_metadata, "weight_transform": name},
        )
        add(f"geometry/{name}", (window,), count=64)
    floating = fixture_problem(sourced["h1_euclidean_length_triangle"]).window
    add("geometry/euclidean_float", (floating,), count=64)
    for name in (
        "h0_interval_stage_1",
        "h2_euclidean_one_hole",
        "h3_euclidean_one_hole",
    ):
        add(f"dimension/{name}", (fixture_problem(sourced[name]).window,), count=8)
    for beta, count in ((2, 8), (2, 64), (64, 8), (64, 64)):
        window, _ = case_window(f"artificial_beta{beta}_n65")
        routes = list(DEFAULT_ROUTES)
        if count == 64:
            routes += ["hc_workspace"]
        if beta == 2 and count == 64:
            routes += ["factorized_scalar", "factorized_batch"]
        if beta == 64 and count == 8:
            routes += ["native_explicit"]  # Predeclared unsupported-width probe.
        add(
            f"wide/n65/beta{beta}/q{count}",
            (window,),
            count=count,
            routes=routes,
            repeats=1,
        )
    n, beta = 129, 2
    wide = ChainWindow(
        0,
        Matrix.zero(0, n),
        Matrix.from_columns(
            (tuple(int(i == j) for i in range(n)) for j in range(beta, n)), nrows=n
        ),
        (),
        tuple(f"c{i}" for i in range(n)),
        tuple(f"b{i}" for i in range(beta, n)),
        (1,) * n,
        source_metadata={"source": "local coordinate boundary span", "beta": beta},
    )
    add("wide/n129/beta2/q64", (wide,), count=64, repeats=1)
    for kind, count in (("constant", 48), ("growing", 48), ("growing", 96)):
        phases = []
        for phase in range(6 if kind == "growing" else 1):
            size = 4 + 2 * phase if kind == "growing" else 12
            p = min(phase, 4) if kind == "growing" else 6
            phases.append(
                ChainWindow(
                    0,
                    Matrix.zero(0, size),
                    Matrix.from_columns(
                        (tuple(int(i == j) for i in range(size)) for j in range(p)),
                        nrows=size,
                    ),
                    (),
                    tuple(f"v{i}" for i in range(size)),
                    tuple(f"e{i}" for i in range(p)),
                    tuple(range(1, size + 1)),
                    arithmetic="ExactInteger",
                    source_metadata={
                        "source": "local finite filtration",
                        "family": kind,
                    },
                )
            )
        stages = tuple(
            phases[min(i * len(phases) // count, len(phases) - 1)] for i in range(count)
        )
        add(
            f"family/{kind}/s{count}",
            stages,
            count=8,
            routes=(*DEFAULT_ROUTES, "legacy_family"),
            scales=tuple(i // 2 for i in range(count)),
            repeats=1,
        )
    for name, problem, method in solver_cases():
        add(
            f"certified/{name}",
            (problem.window,),
            method=method,
            target=problem.requested_certificate_level,
            limits=problem.resource_limits,
            structure=problem.input_structure,
            matrix_free=problem.matrix_free_output,
        )
    add("failure/feasible_entries0", (k4,), limits=ResourceLimits(matrix_entry_limit=0))
    metadata = {}
    for key, data in windows.items():
        w = ChainWindow.from_dict(data)
        rank_a, rank_d = w.A.rank(), w.D.rank()
        metadata[key] = {
            "shape": [w.m, w.n, w.p],
            "nnz": [sum(map(sum, w.A.rows)), sum(map(sum, w.D.rows))],
            "rank_A": rank_a,
            "rank_D": rank_d,
            "beta": w.n - rank_a - rank_d,
            "arithmetic": w.arithmetic,
        }
    return {
        "schema_version": 1,
        "purpose": "S4-09 acceptance; no GUDHI/S5 claim",
        "baseline": measured_snapshot(baseline_root, R0),
        "candidate": measured_snapshot(ROOT, CANDIDATE, native=True),
        "windows": windows,
        "window_metadata": metadata,
        "provenance": provenance,
        "cases": cases,
        "seed": 6909,
        "blocks": 10,
        "worker_timeout_seconds": 180,
        "statistics": {
            "bootstrap_resamples": 10000,
            "confidence": 0.95,
            "unit": "paired independent process block; median log ratio",
            "time": "cold whole process block including all rebuild repeats",
            "rss": "separate same-repetition fresh process absolute peak",
        },
        "admission": {
            "benefit": "at least one predeclared successful same-output group: CI entirely below 1 for cold block or absolute RSS",
            "default_replacement_regression_limit": 1.20,
            "policy": "all groups retained; any >20% median regression blocks a global default replacement",
        },
        "route_policy": {
            "r0": "pinned Phase3 source; reference scalar geometry; legacy family/schema1",
            "reference": "candidate source; reference solver/scalar; adjacent family/schema2",
            "integrated": "explicit native certified solver, or Factorized Feasible; reusable geometry workspace for supported action; adjacent family/schema2",
            "native_explicit": "candidate NativeFeasibleSolver, workspace geometry; width>64 is a declared Unavailable probe",
            "factorized_scalar": "candidate Factorized plus scalar geometry",
            "factorized_batch": "candidate Factorized plus transient native geometry workspace",
            "hc_workspace": "candidate HC plus reusable native geometry workspace",
            "legacy_family": "candidate reference scalar pipeline, only family.py loaded from R0",
        },
        "cost_scope": "import/manifest/input/solver/mandatory validators/topology/joint queries/two batches/snapshot/recovery/requery/streamed P,L generator audit/JSON output/exit; no profiler",
        "history": "one common identity-bound joint record per stage; official scalar readout APIs used without per-query history; restore explicitly rechecks all requested geometry",
    }


def restore_operator(record, revision):
    from homology_operator import HomologyOperator
    from homology_operator.solver import ProjectionSolution
    from homology_operator.result import QueryResult

    if hasattr(record, "to_operator"):
        return record.to_operator()
    metadata = record.solver
    solution = ProjectionSolution(
        status=metadata["status"],
        solver_run_id=record.identity["solver_run_id"],
        projection=record.projection,
        identity=record.identity,
        certificate_level=metadata["certificate_level"],
        objective=QueryResult.from_dict(metadata["objective"]),
        certificate=record.certificate,
        resource_usage=metadata.get("resource_usage", {}),
        diagnostics=metadata.get("diagnostics", ()),
        tie_break_policy=metadata.get("tie_break_policy", "StableBasisOrder"),
        method=metadata.get("method", "FeasibleSolver"),
        arithmetic_policy=metadata.get("arithmetic_policy"),
        lower_bound=metadata.get("lower_bound"),
        upper_bound=metadata.get("upper_bound"),
        solver_config=metadata.get("solver_config"),
    )
    op = HomologyOperator(record.input_data, solution, revision)
    op._queries.update(record.query_results)
    return op


def run_pipeline(manifest, case, route, baseline_root):
    from homology_operator import (
        ChainWindow,
        HomologyOperator,
        Matrix,
        OperatorFamily,
        OperatorFamilyResult,
        OperatorResult,
        ProjectionProblem,
        QueryResult,
        ResourceLimits,
        solve_projection,
    )
    from homology_operator.result import canonical_json

    phases = {}
    stamp = perf_counter()

    def done(name):
        nonlocal stamp
        now = perf_counter()
        phases[name] = now - stamp
        stamp = now

    windows = [
        ChainWindow.from_dict(manifest["windows"][key]) for key in case["fixture_ids"]
    ]
    done("input_conversion")
    compact = (
        route in ("integrated", "factorized_scalar", "factorized_batch", "hc_workspace")
        and case["solver"] == "FeasibleSolver"
    )
    method = case["solver"]
    if route == "native_explicit":
        method = "NativeFeasibleSolver"
    elif compact:
        method = "NativeFactorizedSolver"
    elif route == "integrated":
        method = "Native" + method
    solutions = []
    revision = manifest["baseline" if route == "r0" else "candidate"]["revision"]
    for window in windows:
        problem = ProjectionProblem(
            window,
            resource_limits=ResourceLimits(**case["resource_limits"]),
            requested_certificate_level=case["requested_certificate_level"],
            input_structure=case["input_structure"],
            matrix_free_output=compact or case["matrix_free_output"],
            solver_options={
                "representation": "HC" if route == "hc_workspace" else "Factorized"
            }
            if compact
            else {},
        )
        solutions.append(solve_projection(problem, method))
    done("solve_dispatch_mandatory_validation")
    statuses = [
        {
            "status": s.status,
            "certificate_level": s.certificate_level,
            "objective": {
                "state": s.objective.state,
                "value": s.objective.value,
                "exact": s.objective.exact,
            },
            "bounds": (s.lower_bound, s.upper_bound),
            "gap": s.optimality_gap,
        }
        for s in solutions
    ]
    completed = all(s.status in ("Solved", "FeasibleOnly") for s in solutions)
    operators = [
        HomologyOperator(w, s, revision)
        for w, s in zip(windows, solutions)
        if s.projection is not None
    ]
    done("operator_mandatory_validation")
    details = {
        "solutions": [
            {
                "method": s.method,
                "config": s.solver_config,
                "solver_run_id": s.solver_run_id,
                "diagnostics": s.diagnostics,
                "resource_usage": s.resource_usage,
            }
            for s in solutions
        ]
    }
    semantic = {"statuses": statuses}
    if len(operators) != len(windows):
        semantic["missing_action"] = True
        done("semantic_digest")
        return {
            "completed": completed,
            "output_hash": sha256(canonical_json(semantic).encode()).hexdigest(),
            "statuses": json.loads(canonical_json(statuses)),
            "phases_seconds": phases,
            "details": json.loads(canonical_json(details)),
        }
    semantic["topology"] = [
        {"betti": op.betti(), "kernel": op.kernel_basis()} for op in operators
    ]
    done("topology")
    family_type = OperatorFamily
    if route == "legacy_family":
        spec = importlib.util.spec_from_file_location(
            "homology_operator._acceptance_family_r0",
            baseline_root / "src/homology_operator/family.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        family_type = module.OperatorFamily
    family = (
        None
        if case["scales"] is None
        else family_type(tuple(case["scales"]), tuple(windows), tuple(operators))
    )
    done("family_validation")
    if family is not None:
        bars = family.barcode()
        semantic["barcode"] = (bars.state, bars.value, bars.exact)
        endpoints = tuple(
            sorted({(q["stage"], len(windows) - 1) for q in case["queries"]})
        )
        semantic["transport"] = []
        for i, j in endpoints:
            rank, certificate = (
                family.transport_rank(i, j),
                family.transport_certificate(i, j),
            )
            semantic["transport"].append(
                (i, j, rank.state, rank.value, certificate.state, certificate.value)
            )
    done("barcode_transport_certificates")
    requested = defaultdict(list)
    for q in case["queries"]:
        requested[q["stage"]].append((tuple(q["z"]), tuple(q["y"])))
    geometry_details = []

    def geometry(ops, reusable):
        output = {}
        for i, queries in requested.items():
            op = ops[i]
            cycles = tuple(z for pair in queries for z in pair)
            pairs = tuple((2 * j, 2 * j + 1) for j in range(len(queries)))
            use_native = route not in (
                "r0",
                "reference",
                "legacy_family",
                "factorized_scalar",
            ) and not hasattr(op.P, "m")
            if use_native:
                from homology_operator.native import GeometryWorkspace, geometry_batch

                workspace = reusable.get(i)
                if route != "factorized_batch" and workspace is None:
                    workspace = reusable[i] = GeometryWorkspace(op)
                result = geometry_batch(op, cycles, pairs, workspace=workspace)
                if result.state != "Computed":
                    raise ValueError(f"geometry: {result.state}: {result.details}")
                value = result.value
                geometry_details.append(
                    {
                        k: v
                        for k, v in result.details.items()
                        if k not in ("arguments", "pairs")
                    }
                )
            else:
                value = {
                    name: tuple(getattr(op, name)(z) for z in cycles)
                    for name in ("class_representative", "selected_mass", "support")
                }
                value.update(
                    {
                        name: tuple(
                            getattr(op, name)(cycles[a], cycles[b]) for a, b in pairs
                        )
                        for name in (
                            "class_distance",
                            "shared_support",
                            "union_support",
                        )
                    }
                )
                geometry_details.append(
                    {"route": "scalar", "unsupported_native_action": hasattr(op.P, "m")}
                )
            output[str(i)] = value
        return output

    workspaces = {}
    first = geometry(operators, workspaces)
    done("geometry_first_including_preparation")
    second = geometry(operators, workspaces)
    if canonical_json(first) != canonical_json(second):
        raise ValueError("warm geometry changed the same P output")
    semantic["geometry"] = first
    done("geometry_second")
    if family is not None:
        semantic["tracking"] = []
        for q in case["queries"]:
            i, z, j = q["stage"], tuple(q["z"]), len(windows) - 1
            semantic["tracking"].append(
                tuple(
                    getattr(family, name)(z, i, j).value
                    for name in ("track_class", "track_mass", "track_support")
                )
            )
    done("class_tracking")
    # Same history and value freezing contract in every route; no dense action encoding.
    for i, op in enumerate(operators):
        if str(i) in first:
            queries = requested[i]
            op._queries["joint_batch"] = QueryResult(
                "Computed",
                first[str(i)],
                op.identity,
                windows[i].arithmetic != "FloatingPoint",
                {
                    "arguments": tuple(z for pair in queries for z in pair),
                    "pairs": tuple((2 * j, 2 * j + 1) for j in range(len(queries))),
                },
            )
    records = (
        [family.to_result()]
        if family is not None
        else [op.to_result() for op in operators]
    )
    wires = [record.to_json() for record in records]
    done("snapshot_serialization_mandatory_validation")
    if family is not None:
        record = OperatorFamilyResult.from_json(wires[0])
        recovered = record.to_family()
        if canonical_json(recovered.barcode().value) != canonical_json(
            family.barcode().value
        ):
            raise ValueError("restored barcode differs")
        restored = [recovered.stage(i) for i in range(len(windows))]
    else:
        decoded = [OperatorResult.from_json(wire) for wire in wires]
        restored = [restore_operator(record, revision) for record in decoded]
    done("restore_mandatory_validation")
    if canonical_json(first) != canonical_json(geometry(restored, {})):
        raise ValueError("restored joint geometry differs")
    done("restore_geometry_audit")
    action_hash = sha256()
    for op, recovered in zip(operators, restored):
        for j in range(op.window.n):
            e = tuple(int(i == j) for i in range(op.window.n))
            projection, complement = op.project(e), op.apply_operator(e)
            if projection != recovered.project(
                e
            ) or complement != recovered.apply_operator(e):
                raise ValueError("restored full-chain P/L differs")
            action_hash.update(bytes(projection))
            action_hash.update(bytes(complement))
    semantic["full_chain_stream_hash"] = action_hash.hexdigest()
    done("streamed_full_chain_restore_audit")
    encoded = canonical_json(semantic)
    done("semantic_digest")
    details["geometry"] = geometry_details
    details["serialized_utf8_bytes"] = sum(len(w.encode()) for w in wires)
    details["action_entries"] = [
        op.window.n**2
        if isinstance(op.P, Matrix)
        else sum(f.nrows * f.ncols for f in op.P.factors)
        if hasattr(op.P, "factors")
        else None
        for op in operators
    ]
    return {
        "completed": completed,
        "output_hash": sha256(encoded.encode()).hexdigest(),
        "statuses": json.loads(canonical_json(statuses)),
        "phases_seconds": phases,
        "details": json.loads(canonical_json(details)),
    }


def worker(args):
    began = perf_counter()
    manifest = json.loads(args.manifest.read_text("utf-8"))
    case = next(c for c in manifest["cases"] if c["id"] == args.case)
    source = args.baseline_root if args.route == "r0" else ROOT
    sys.path.insert(0, str(source / "src"))
    import homology_operator

    loaded = Path(homology_operator.__file__).resolve()
    if loaded.parent != (source / "src/homology_operator").resolve():
        raise ValueError(f"wrong imported source: {loaded}")
    if sys.getprofile() is not None:
        raise ValueError("profiler forbidden in sampling workers")
    imported = perf_counter()
    records = [
        run_pipeline(manifest, case, args.route, args.baseline_root)
        for _ in range(args.repeats)
    ]
    result = {
        "case": case["id"],
        "route": args.route,
        "repeats": args.repeats,
        "loaded_source": str(loaded),
        "source_revision": manifest["baseline" if args.route == "r0" else "candidate"][
            "revision"
        ],
        "import_manifest_seconds": imported - began,
        "records": records,
    }
    if args.mode == "rss":
        value, method, error = peak_rss()
        result.update(peak_rss_bytes=value, rss_method=method, rss_failure=error)
        result.pop("import_manifest_seconds")
        for record in records:
            record.pop("phases_seconds")
    return result


def paired_interval(values, seed=6909):
    rng = random.Random(seed)
    logs = [math.log(v) for v in values]
    draws = sorted(
        math.exp(statistics.median(rng.choices(logs, k=len(logs))))
        for _ in range(10000)
    )
    return {
        "paired_median_ratio": math.exp(statistics.median(logs)),
        "bootstrap_95_interval": [draws[249], draws[9749]],
    }


def summarize(manifest, samples):
    groups = defaultdict(list)
    for sample in samples:
        groups[(sample["case"], sample["route"], sample["mode"])].append(sample)
    summaries = []
    for case in manifest["cases"]:
        for route in case["routes"]:
            for mode in ("timing", "rss"):
                rows = groups[case["id"], route, mode]
                ok = [r for r in rows if r["process_state"] == "completed"]
                completed = [
                    r for r in ok if all(x["completed"] for x in r["result"]["records"])
                ]
                key = "cold_block_seconds" if mode == "timing" else "peak_rss_bytes"
                values = [
                    (r[key] if mode == "timing" else r["result"][key])
                    for r in completed
                ]
                values = [v for v in values if v is not None]
                item = {
                    "case": case["id"],
                    "route": route,
                    "mode": mode,
                    "process_counts": dict(Counter(r["process_state"] for r in rows)),
                    "complete_blocks": len(completed),
                    "metric": key,
                    "median": statistics.median(values) if values else None,
                    "iqr": statistics.quantiles(values, n=4, method="inclusive")[2]
                    - statistics.quantiles(values, n=4, method="inclusive")[0]
                    if len(values) > 1
                    else None,
                }
                baseline = groups[case["id"], "r0", mode]
                base_by_block = {
                    r["block"]: r for r in baseline if r["process_state"] == "completed"
                }
                ratios, equal = [], True
                for row in completed:
                    base = base_by_block.get(row["block"])
                    if not base or not all(
                        x["completed"] for x in base["result"]["records"]
                    ):
                        continue
                    hashes = {r["output_hash"] for r in row["result"]["records"]}
                    base_hashes = {r["output_hash"] for r in base["result"]["records"]}
                    if len(hashes) != 1 or hashes != base_hashes:
                        equal = False
                        continue
                    a = (
                        row["cold_block_seconds"]
                        if mode == "timing"
                        else row["result"]["peak_rss_bytes"]
                    )
                    b = (
                        base["cold_block_seconds"]
                        if mode == "timing"
                        else base["result"]["peak_rss_bytes"]
                    )
                    if a is not None and b is not None and b > 0:
                        ratios.append(a / b)
                item.update(
                    same_output=equal if ratios else None, paired_blocks=len(ratios)
                )
                if ratios:
                    item.update(paired_interval(ratios))
                    item["median_regression_over_20_percent"] = (
                        statistics.median(ratios) > 1.20
                    )
                    item["admission_improvement"] = (
                        len(ratios) >= 10 and item["bootstrap_95_interval"][1] < 1
                    )
                else:
                    item.update(admission_improvement=False)
                summaries.append(item)
    return summaries


def sample_process(command, timeout):
    began = perf_counter()
    try:
        process = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, timeout=timeout
        )
        elapsed = perf_counter() - began
        if process.returncode:
            state = (
                "process_oom"
                if "MemoryError" in process.stderr
                else "process_killed"
                if process.returncode in (-9, 137)
                else "process_error"
            )
            return {
                "process_state": state,
                "exit_code": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "cold_block_seconds": elapsed,
            }
        return {
            "process_state": "completed",
            "exit_code": 0,
            "cold_block_seconds": elapsed,
            "result": json.loads(process.stdout),
            "stderr": process.stderr,
        }
    except subprocess.TimeoutExpired as error:
        return {
            "process_state": "process_timeout",
            "timeout_seconds": timeout,
            "stdout": str(error.stdout or ""),
            "stderr": str(error.stderr or ""),
            "cold_block_seconds": None,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--phase", choices=("pilot", "formal"), default="pilot")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--case")
    parser.add_argument("--route")
    parser.add_argument("--mode", choices=("timing", "rss"), default="timing")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    args.baseline_root = args.baseline_root.resolve()
    if args.worker:
        print(json.dumps(worker(args), sort_keys=True, separators=(",", ":")))
        return
    if args.prepare:
        if args.manifest.exists():
            raise ValueError("will not overwrite an existing manifest")
        write_json(args.manifest, make_manifest(args.baseline_root))
        return
    if args.output is None or args.output.exists():
        parser.error("a new --output path is required")
    manifest = json.loads(args.manifest.read_text("utf-8"))
    for source, key in ((args.baseline_root, "baseline"), (ROOT, "candidate")):
        if (
            measured_snapshot(source, manifest[key]["revision"], key == "candidate")
            != manifest[key]
        ):
            raise ValueError(f"changed {key} source")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    harness_hashes = {}
    for name in (
        "scripts/benchmark_acceptance.py",
        "scripts/benchmark_reference.py",
        "scripts/benchmark_native.py",
        "scripts/benchmark_compact.py",
    ):
        data = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
        committed = subprocess.check_output(
            ["git", "show", f"{head}:{name}"], cwd=ROOT
        ).replace(b"\r\n", b"\n")
        if data != committed:
            raise ValueError(f"dirty sampling harness: {name}")
        harness_hashes[name] = sha256(data).hexdigest()
    # Do not import native in the R0 worker. Parent checks the release binary once.
    from homology_operator.native import backend_info

    info = backend_info()
    if info["native"] != "Available":
        raise ValueError(info)
    binary_hashes = {
        info["extension_path"]: sha256(
            Path(info["extension_path"]).read_bytes()
        ).hexdigest()
    }
    for path in (ROOT / ".task-artifacts/native-wheels").glob("*.whl"):
        binary_hashes[path.name] = sha256(path.read_bytes()).hexdigest()
    blocks = 1 if args.phase == "pilot" else manifest["blocks"]
    report = {
        "schema_version": 1,
        "phase": args.phase,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256_lf": sha256(
            args.manifest.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        "harness_revision": head,
        "harness_lf_sha256": harness_hashes,
        "baseline": manifest["baseline"],
        "candidate": manifest["candidate"],
        "native_binary_sha256": binary_hashes,
        "environment": {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "native": info,
            "threads": 1,
        },
        "protocol": {
            k: manifest[k]
            for k in ("statistics", "admission", "cost_scope", "route_policy")
        },
        "samples": [],
    }
    for mode in ("timing", "rss"):
        for block in range(blocks):
            cases = list(manifest["cases"])
            random.Random(manifest["seed"] + block).shuffle(cases)
            for case in cases:
                routes = list(case["routes"])
                random.Random(digest([manifest["seed"], block, case["id"]])).shuffle(
                    routes
                )
                repeats = 1 if args.phase == "pilot" else case["formal_repeats"]
                for route in routes:
                    command = [
                        sys.executable,
                        "-I",
                        str(Path(__file__).resolve()),
                        "--manifest",
                        str(args.manifest.resolve()),
                        "--baseline-root",
                        str(args.baseline_root),
                        "--worker",
                        "--case",
                        case["id"],
                        "--route",
                        route,
                        "--mode",
                        mode,
                        "--repeats",
                        str(repeats),
                    ]
                    # -I intentionally excludes script dir; the bootstrap adds only our
                    # committed helper directory before executing the same worker.
                    bootstrap = (
                        "import runpy,sys;sys.path.insert(0,"
                        + repr(str(ROOT / "scripts"))
                        + ");sys.argv="
                        + repr(command[2:])
                        + ";runpy.run_path("
                        + repr(str(Path(__file__).resolve()))
                        + ",run_name='__main__')"
                    )
                    command = [sys.executable, "-I", "-c", bootstrap]
                    sample = sample_process(command, manifest["worker_timeout_seconds"])
                    sample.update(
                        case=case["id"],
                        route=route,
                        mode=mode,
                        block=block,
                        repeats=repeats,
                        command=command,
                    )
                    if mode == "rss":
                        sample.pop("cold_block_seconds", None)
                    report["samples"].append(sample)
                write_json(args.output, report)
                print(
                    f"{args.phase} {mode} block={block} {case['id']} done", flush=True
                )
            print(
                f"{args.phase} {mode} block {block + 1}/{blocks} complete", flush=True
            )
    report["summary"] = summarize(manifest, report["samples"])
    write_json(args.output, report)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
