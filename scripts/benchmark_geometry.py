"""S4-06 finite geometry workload: full costs, warm reuse, visible fallbacks."""

import argparse
from dataclasses import replace
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    "k4_integer",
    "k4_rational",
    "k4_bigint",
    "k4_overflow",
    "k4_float",
    "wide_integer",
)
COUNTS = (0, 1, 8, 64, 1024)
BACKENDS = ("scalar", "batch", "workspace")


def worker(backend, case, count, revision, rss):
    started = perf_counter()
    from homology_operator import (
        FeasibleSolver,
        HomologyOperator,
        OperatorResult,
        ProjectionProblem,
        QueryResult,
        solve_projection,
    )
    from homology_operator.native import (
        GeometryWorkspace,
        NativeFactorizedSolver,
        geometry_batch,
    )
    from homology_operator.result import content_id
    from benchmark_compact import case_window

    imported = perf_counter()
    w, source_hash = case_window(
        "artificial_beta2_n65" if case == "wide_integer" else "h1_k4_stage_4"
    )
    arithmetic = "ExactInteger"
    weights = tuple(range(1, w.n + 1))
    if case == "k4_rational":
        arithmetic, weights = (
            "ExactRational",
            tuple(Fraction(i + 1, 2 * i + 3) for i in range(w.n)),
        )
    elif case == "k4_bigint":
        weights = (10**100,) * w.n
    elif case == "k4_overflow":
        weights = ((1 << 64) - 1,) * w.n
    elif case == "k4_float":
        arithmetic, weights = (
            "FloatingPoint",
            tuple((1e16, 1.0, 0.1)[i % 3] for i in range(w.n)),
        )
    w = replace(w, weights=weights, arithmetic=arithmetic)
    ready = perf_counter()
    # Every compared route constructs exactly the same operator/solver/level.
    compact = case == "wide_integer"
    problem = ProjectionProblem(w, matrix_free_output=compact)
    solution = solve_projection(
        problem, NativeFactorizedSolver() if compact else FeasibleSolver()
    )
    if solution.projection is None:
        return {"state": solution.status, "diagnostics": solution.diagnostics}
    solved = perf_counter()
    op = HomologyOperator(w, solution, repository_revision=revision)
    constructed = perf_counter()
    basis = w.A.kernel_basis()
    cycles = tuple(basis[i % len(basis)] for i in range(count))
    pairs = tuple((i, (i + 1) % count) for i in range(count))
    topology = {"betti": op.betti(), "kernel": op.kernel_basis()}
    prepared = perf_counter()
    workspace = GeometryWorkspace(op) if backend == "workspace" else None
    workspace_ready = perf_counter()

    def query():
        if backend != "scalar":
            result = geometry_batch(op, cycles, pairs, workspace=workspace)
            if result.state != "Computed":
                raise ValueError(str(result.details))
            return result.value, dict(result.details)
        value = {
            name: tuple(getattr(op, name)(z) for z in cycles)
            for name in ("class_representative", "selected_mass", "support")
        }
        value.update(
            {
                name: tuple(getattr(op, name)(cycles[i], cycles[j]) for i, j in pairs)
                for name in ("class_distance", "shared_support", "union_support")
            }
        )
        # Equal identity/argument freezing costs, including q=0, in all routes.
        result = QueryResult(
            "Computed",
            value,
            op.identity,
            arithmetic != "FloatingPoint",
            {"arguments": cycles, "pairs": pairs},
        )
        return result.value, {}

    first, first_detail = query()
    first_done = perf_counter()
    second, second_detail = query()
    second_done = perf_counter()
    if first != second:
        raise ValueError("repeated geometry outputs differ")
    before = op.to_result()
    normalized = QueryResult(
        "Computed",
        second,
        op.identity,
        arithmetic != "FloatingPoint",
        {"arguments": cycles, "pairs": pairs},
    )
    record = replace(
        before, query_results={**before.query_results, "geometry": normalized}
    )
    restored = OperatorResult.from_json(record.to_json())
    if restored != record or before != op.to_result():
        raise ValueError("snapshot history or round-trip changed")
    output_hash = content_id(
        "geometry-output",
        {
            "geometry": second,
            "topology": topology,
            "identity": {k: v for k, v in op.identity.items() if k != "solver_run_id"},
            "solver_status": solution.status,
            "certificate_level": solution.certificate_level,
            "objective_state": solution.objective.state,
            "restored_geometry": restored.query_results["geometry"].value,
        },
    )
    finished = perf_counter()
    points = (
        started,
        imported,
        ready,
        solved,
        constructed,
        prepared,
        workspace_ready,
        first_done,
        second_done,
        finished,
    )
    names = (
        "imports",
        "input",
        "solve_and_validation",
        "operator_validation",
        "topology_and_arguments",
        "workspace_preparation",
        "first_batch",
        "second_batch",
        "snapshot_restore_hash",
    )
    result = {
        "state": "Computed",
        "backend": backend,
        "case": case,
        "queries": count,
        "source_revision": revision,
        "fixture_source_hash": source_hash,
        "input_id": w.identity()["input_id"],
        "output_hash": output_hash,
        "shape": [w.m, w.n, w.p],
        "arithmetic": arithmetic,
        "representation": "Factorized" if compact else "Matrix",
        "solver": solution.method,
        "certificate_level": solution.certificate_level,
        "objective_state": solution.objective.state,
        "resource_limits": dict(solution.solver_config["resource_limits"]),
        "phases_seconds": dict(zip(names, (b - a for a, b in zip(points, points[1:])))),
        "worker_seconds": finished - started,
        "first_query_detail": first_detail,
        "second_query_detail": second_detail,
        "workspace_statistics": workspace.statistics() if workspace else None,
    }
    if rss:
        from benchmark_reference import peak_rss

        value, method, failure = peak_rss()
        result.update(peak_rss_bytes=value, rss_method=method, rss_failure=failure)
        for key in (
            "phases_seconds",
            "worker_seconds",
            "first_query_detail",
            "second_query_detail",
        ):
            result.pop(key)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=BACKENDS)
    parser.add_argument("--case", choices=CASES, default=CASES[0])
    parser.add_argument("--queries", type=int, choices=COUNTS, default=8)
    parser.add_argument("--rss", action="store_true")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        from homology_operator.result import canonical_json

        print(
            canonical_json(
                worker(args.worker, args.case, args.queries, args.revision, args.rss)
            )
        )
        return
    if args.output is None:
        parser.error("--output required")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if head != args.revision:
        raise ValueError("measurement requires current exact source HEAD")
    paths = subprocess.check_output(
        [
            "git",
            "ls-files",
            "src",
            "native",
            "scripts",
            "tests/fixtures/reference.json",
            "uv.lock",
        ],
        cwd=ROOT,
        text=True,
    ).splitlines()
    hashes = {}
    for name in paths:
        data = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
        committed = subprocess.check_output(
            ["git", "show", f"{args.revision}:{name}"], cwd=ROOT
        ).replace(b"\r\n", b"\n")
        if data != committed:
            raise ValueError(f"dirty measured source: {name}")
        hashes[name] = sha256(data).hexdigest()
    schedule = [
        (b, c, q, r, False)
        for r in range(3)
        for c in CASES
        for q in COUNTS
        for b in BACKENDS
    ]
    random.Random(66).shuffle(schedule)
    schedule += [(b, c, 1024, 0, True) for c in CASES for b in BACKENDS]
    records = []
    for backend, case, count, repeat, rss in schedule:
        started = perf_counter()
        command = [
            sys.executable,
            __file__,
            "--worker",
            backend,
            "--case",
            case,
            "--queries",
            str(count),
            "--revision",
            args.revision,
        ] + (["--rss"] if rss else [])
        try:
            completed = subprocess.run(
                command, cwd=ROOT, text=True, capture_output=True, timeout=60
            )
            if completed.returncode:
                record = {
                    "state": "WorkerFailed",
                    "exit_code": completed.returncode,
                    "stderr": completed.stderr,
                    "stdout": completed.stdout,
                }
            else:
                record = json.loads(completed.stdout)
        except subprocess.TimeoutExpired:
            record = {"state": "Timeout", "timeout_seconds": 60}
        record.update(backend=backend, case=case, queries=count, repeat=repeat, rss=rss)
        if not rss:
            record["process_seconds"] = perf_counter() - started
        records.append(record)
        # Keep partial results if interrupted; never delete failed samples.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps({"incomplete": True, "records": records}, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    mismatches = []
    for case in CASES:
        for count in COUNTS:
            values = {
                r["output_hash"]
                for r in records
                if r["case"] == case
                and r["queries"] == count
                and r["state"] == "Computed"
            }
            if len(values) != 1:
                mismatches.append([case, count])
    from _homology_native import _homology_native as native_binary

    report = {
        "schema_version": 1,
        "scope": "S4-06 finite geometry study; not S4/S5 performance admission",
        "source_revision": args.revision,
        "source_lf_sha256": hashes,
        "python": sys.version,
        "platform": platform.platform(),
        "rustc": subprocess.check_output(
            ["rustc", "+1.98.1", "--version"], text=True
        ).strip(),
        "build": "maturin1.15.0/PyO3 0.29.3 --release --locked; single-threaded safe Rust",
        "extension_sha256": sha256(
            Path(native_binary.__file__).read_bytes()
        ).hexdigest(),
        "protocol": {
            "cases": CASES,
            "counts": COUNTS,
            "backends": BACKENDS,
            "repeats": 3,
            "shuffle_seed": 66,
            "queries_per_batch": "q cycles + q cyclic pairs",
            "warm": "second identical batch; all preparation charged to cold total",
            "rss": "separate fresh q1024 workers; OS absolute peak; unavailable=null",
            "timeout_seconds": 60,
            "profiling": False,
        },
        "mismatches": mismatches,
        "records": records,
    }
    args.output.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    failures = sum(r["state"] != "Computed" for r in records)
    print(
        f"{len(records)} workers; {failures} failures; {len(mismatches)} mismatches; {args.output}"
    )
    if failures or mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
