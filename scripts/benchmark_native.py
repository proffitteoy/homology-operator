"""S4-02 cold-worker vertical slice; complete costs and unfavorable results kept."""

import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]


def worker(backend, count, revision):
    started = perf_counter()
    from homology_operator import (
        FeasibleSolver,
        HomologyOperator,
        OperatorResult,
        QueryResult,
        solve_projection,
    )
    from homology_operator.native import NativeFeasibleSolver, geometry_batch
    from homology_operator.result import content_id
    from compare_solvers import fixture_problem

    imported = perf_counter()
    fixture = next(
        f
        for f in json.loads(
            (ROOT / "tests/fixtures/reference.json").read_text("utf-8")
        )["fixtures"]
        if f["id"] == "h1_k4_stage_4"
    )
    problem = fixture_problem(fixture)
    window = problem.window
    ready = perf_counter()
    solution = solve_projection(
        problem, NativeFeasibleSolver() if backend == "native" else FeasibleSolver()
    )
    if solution.status != "FeasibleOnly":
        raise ValueError(str(solution.diagnostics))
    solved = perf_counter()
    op = HomologyOperator(window, solution, repository_revision=revision)
    constructed = perf_counter()
    topology = {"betti": op.betti(), "kernel_basis": op.kernel_basis()}
    basis = window.A.kernel_basis()
    cycles = tuple(basis[i % len(basis)] for i in range(count))
    pairs = tuple((i, (i + 1) % count) for i in range(count))
    prepared = perf_counter()
    detail = {}
    if backend == "native":
        query = geometry_batch(op, cycles, pairs)
        if query.state != "Computed":
            raise ValueError(str(query.details))
        geometry, detail = query.value, dict(query.details)
    else:
        geometry = {
            name: tuple(getattr(op, name)(z) for z in cycles)
            for name in ("class_representative", "selected_mass", "support")
        }
        geometry.update(
            {
                name: tuple(getattr(op, name)(cycles[i], cycles[j]) for i, j in pairs)
                for name in ("class_distance", "shared_support", "union_support")
            }
        )
    queried = perf_counter()
    # Equal query semantics, with no backend timing metadata in the output hash.
    query = QueryResult(
        "Computed", geometry, op.identity, True, {"arguments": cycles, "pairs": pairs}
    )
    record = op.to_result()
    record = replace(
        record, query_results={**record.query_results, "joint_batch": query}
    )
    serialized = record.to_json()
    exported = perf_counter()
    restored = OperatorResult.from_json(serialized)
    recovered = perf_counter()
    generators = tuple(
        tuple(int(i == j) for i in range(window.n)) for j in range(window.n)
    )
    output_hash = content_id(
        "vertical-output",
        {
            "P": op.P.rows,
            "L": op.L.rows,
            **topology,
            "geometry": geometry,
            "all_chain_generators": tuple(op.project(z) for z in generators),
            "restored_projection": restored.projection.rows,
            "restored_queries": {
                key: value.value for key, value in restored.query_results.items()
            },
            "identity": {
                key: value
                for key, value in op.identity.items()
                if key != "solver_run_id"
            },
            "status": solution.status,
            "certificate_level": solution.certificate_level,
        },
    )
    hashed = perf_counter()
    points = (
        started,
        imported,
        ready,
        solved,
        constructed,
        prepared,
        queried,
        exported,
        recovered,
        hashed,
    )
    names = (
        "imports",
        "input",
        "solve_and_independent_validation",
        "operator_validation",
        "topology_and_query_preparation",
        "geometry",
        "snapshot_and_serialization",
        "restore_validation",
        "semantic_hash",
    )
    return {
        "backend": backend,
        "queries": count,
        "source_revision": revision,
        "fixture_id": fixture["id"],
        "fixture_input_hash": fixture["input_hash"],
        "output_hash": output_hash,
        "certificate_level": solution.certificate_level,
        "objective_state": solution.objective.state,
        "resource_limits": dict(solution.solver_config["resource_limits"]),
        "phases_seconds": dict(zip(names, (b - a for a, b in zip(points, points[1:])))),
        "worker_seconds": hashed - started,
        "native_solver_detail": dict(solution.resource_usage)
        if backend == "native"
        else None,
        "native_query_detail": detail if backend == "native" else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=("native", "reference"))
    parser.add_argument("--queries", type=int, default=8)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        result = worker(args.worker, args.queries, args.revision)
        from homology_operator.result import canonical_json

        print(canonical_json(result))
        return
    if not args.output:
        parser.error("--output is required")
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
            "scripts/benchmark_native.py",
            "scripts/compare_solvers.py",
            "tests/fixtures/reference.json",
            "uv.lock",
        ],
        cwd=ROOT,
        text=True,
    ).splitlines()
    hashes = {}
    for path in paths:
        data = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
        committed = subprocess.check_output(
            ["git", "show", f"{head}:{path}"], cwd=ROOT
        ).replace(b"\r\n", b"\n")
        if data != committed:
            raise ValueError(f"dirty measured source: {path}")
        hashes[path] = sha256(data).hexdigest()
    schedule = [
        (backend, count, repeat)
        for repeat in range(5)
        for count in (0, 8, 64)
        for backend in ("reference", "native")
    ]
    random.Random(62).shuffle(schedule)
    records = []
    for backend, count, repeat in schedule:
        started = perf_counter()
        completed = subprocess.run(
            [
                sys.executable,
                __file__,
                "--worker",
                backend,
                "--queries",
                str(count),
                "--revision",
                head,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        record = json.loads(completed.stdout)
        record.update(repeat=repeat, process_seconds=perf_counter() - started)
        records.append(record)
    for count in (0, 8, 64):
        if len({r["output_hash"] for r in records if r["queries"] == count}) != 1:
            raise ValueError("reference/native semantic outputs differ")
    import _homology_native

    binaries = list((ROOT / ".task-artifacts/native-wheels").glob("*.whl"))
    report = {
        "schema_version": 1,
        "scope": "S4-02 finite vertical prototype; not S4/S5 performance acceptance",
        "source_revision": head,
        "source_lf_sha256": hashes,
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "rustc": subprocess.check_output(["rustc", "--version"], text=True).strip(),
        "build": "maturin 1.15.0 --release --locked; PyO3 0.29.3; single-threaded",
        "extension_sha256": sha256(
            Path(_homology_native.__file__).read_bytes()
        ).hexdigest(),
        "wheel_sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in binaries},
        "protocol": {
            "query_counts": [0, 8, 64],
            "repeats": 5,
            "seed": 62,
            "cold_workers": True,
            "rss": "not measured in this minimal timing experiment",
            "float_policy": "not applicable: exact rational fixture",
        },
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"{len(records)} cold workers; 3 matching output hashes; {args.output}")


if __name__ == "__main__":
    main()
