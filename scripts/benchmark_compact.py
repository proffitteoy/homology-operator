"""S4-04: same-P explicit/factor/HC costs; independent fresh RSS workers."""

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
CASES = (
    "h1_k4_stage_4",
    "h0_interval_stage_0",
    "artificial_beta2_n65",
    "artificial_beta64_n65",
)


def case_window(name):
    from homology_operator import ChainWindow, Matrix
    from compare_solvers import fixture_problem

    if name.startswith("artificial"):
        n = 65
        beta = 2 if name == "artificial_beta2_n65" else 64
        D = Matrix.from_columns(
            (tuple(int(i == j) for i in range(n)) for j in range(beta, n)), nrows=n
        )
        return ChainWindow(
            0,
            Matrix.zero(0, n),
            D,
            (),
            tuple(f"c{i}" for i in range(n)),
            tuple(f"b{i}" for i in range(D.ncols)),
            (1,) * n,
            arithmetic="ExactRational",
            source_metadata={
                "source": "hand-derived coordinate boundary span",
                "beta": beta,
            },
        ), None
    fixture = next(
        f
        for f in json.loads(
            (ROOT / "tests/fixtures/reference.json").read_text("utf-8")
        )["fixtures"]
        if f["id"] == name
    )
    return fixture_problem(fixture).window, fixture["input_hash"]


def worker(backend, name, revision, rss):
    started = perf_counter()
    from homology_operator import (
        FeasibleSolver,
        HomologyOperator,
        OperatorResult,
        ProjectionProblem,
        QueryResult,
        Matrix,
    )
    from homology_operator.native import NativeFactorizedSolver, geometry_batch
    from homology_operator.result import content_id
    from homology_operator import validation, operator as operator_module

    # Independently time mandatory validators without adding those diagnostics to total.
    costs = {"dispatch_validation": 0.0, "operator_validation": 0.0}

    def measured(key, call):
        def run(*args):
            start = perf_counter()
            try:
                return call(*args)
            finally:
                costs[key] += perf_counter() - start

        return run

    validation.validate_solution = measured(
        "dispatch_validation", validation.validate_solution
    )
    operator_module.validate_solution = measured(
        "operator_validation", operator_module.validate_solution
    )
    imported = perf_counter()
    w, original_hash = case_window(name)
    problem = ProjectionProblem(
        w,
        matrix_free_output=backend != "explicit",
        solver_options={} if backend == "explicit" else {"representation": backend},
    )
    ready = perf_counter()
    from homology_operator import solve_projection

    solution = solve_projection(
        problem, FeasibleSolver() if backend == "explicit" else NativeFactorizedSolver()
    )
    if solution.status != "FeasibleOnly":
        raise ValueError(str(solution.diagnostics))
    solved = perf_counter()
    op = HomologyOperator(w, solution, repository_revision=revision)
    constructed = perf_counter()
    betti, kernel = op.betti(), op.kernel_basis()
    basis = w.A.kernel_basis()
    cycles = tuple(basis[i % len(basis)] for i in range(8))
    pairs = tuple((i, (i + 1) % 8) for i in range(8))
    topology = perf_counter()
    if backend == "explicit":
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
    else:
        geometry = geometry_batch(op, cycles, pairs).value
    queried = perf_counter()
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
    # Stream generator actions into the digest. The primary paths never store dense P.
    semantic = sha256()
    for j in range(w.n):
        e = tuple(int(i == j) for i in range(w.n))
        semantic.update(bytes(op.project(e)))
        semantic.update(bytes(op.apply_operator(e)))
        semantic.update(bytes(restored.projection.apply(e)))
    semantic.update(
        content_id(
            "compact-outputs",
            {
                "betti": betti,
                "kernel": kernel,
                "geometry": geometry,
                "restored_queries": {
                    k: v.value for k, v in restored.query_results.items()
                },
                "status": solution.status,
                "certificate_level": solution.certificate_level,
            },
        ).encode()
    )
    hashed = perf_counter()
    points = (
        started,
        imported,
        ready,
        solved,
        constructed,
        topology,
        queried,
        exported,
        recovered,
        hashed,
    )
    names = (
        "imports",
        "input",
        "solve_and_dispatch_validation",
        "operator_validation",
        "topology_query_preparation",
        "geometry",
        "snapshot_serialization",
        "restore_validation",
        "generator_semantic_hash",
    )
    result = {
        "backend": backend,
        "case": name,
        "source_revision": revision,
        "shape": [w.m, w.n, w.p],
        "betti": betti,
        "beta_over_n": betti / w.n,
        "fixture_hash": content_id("input", w.to_dict()),
        "original_fixture_hash": original_hash,
        "output_hash": semantic.hexdigest(),
        "certificate_level": solution.certificate_level,
        "objective_state": solution.objective.state,
        "resource_limits": dict(solution.solver_config["resource_limits"]),
        "phases_seconds": dict(zip(names, (b - a for a, b in zip(points, points[1:])))),
        "validator_diagnostics_seconds": costs,
        "worker_seconds": hashed - started,
        "serialized_utf8_bytes": len(serialized.encode()),
        "stored_action_entries": w.n * w.n
        if isinstance(op.P, Matrix)
        else sum(x.nrows * x.ncols for x in op.P.factors),
        "states": solution.resource_usage["states"],
        "mode": "rss" if rss else "timing",
    }
    if rss:
        from benchmark_reference import peak_rss

        value, method, failure = peak_rss()
        result.update(peak_rss_bytes=value, rss_method=method, rss_failure=failure)
        result.pop("phases_seconds")
        result.pop("validator_diagnostics_seconds")
        result.pop("worker_seconds")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=("explicit", "Factorized", "HC"))
    parser.add_argument("--case", choices=CASES, default=CASES[0])
    parser.add_argument("--rss", action="store_true")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        result = worker(args.worker, args.case, args.revision, args.rss)
        from homology_operator.result import canonical_json

        print(canonical_json(result))
        return
    if not args.output:
        parser.error("--output required")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if head != args.revision:
        raise ValueError("requires exact current source HEAD")
    paths = subprocess.check_output(
        [
            "git",
            "ls-files",
            "src",
            "native",
            "scripts/benchmark_compact.py",
            "scripts/benchmark_reference.py",
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
        if data != subprocess.check_output(
            ["git", "show", f"{head}:{path}"], cwd=ROOT
        ).replace(b"\r\n", b"\n"):
            raise ValueError(f"dirty measured source: {path}")
        hashes[path] = sha256(data).hexdigest()
    schedule = [
        (backend, name, repeat, False)
        for repeat in range(3)
        for name in CASES
        for backend in ("explicit", "Factorized", "HC")
    ]
    random.Random(64).shuffle(schedule)
    schedule += [
        (backend, name, 0, True)
        for name in CASES
        for backend in ("explicit", "Factorized", "HC")
    ]
    records = []
    for backend, name, repeat, rss in schedule:
        started = perf_counter()
        completed = subprocess.run(
            [
                sys.executable,
                __file__,
                "--worker",
                backend,
                "--case",
                name,
                "--revision",
                head,
            ]
            + (["--rss"] if rss else []),
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            records.append(
                {
                    "backend": backend,
                    "case": name,
                    "repeat": repeat,
                    "mode": "rss" if rss else "timing",
                    "status": "WorkerFailed",
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "failed_process_seconds": perf_counter() - started,
                }
            )
            continue
        record = json.loads(completed.stdout)
        record["status"] = "Completed"
        record["repeat"] = repeat
        if not rss:
            record["process_seconds"] = perf_counter() - started
        records.append(record)
    mismatched = [
        name
        for name in CASES
        if len(
            {
                r["output_hash"]
                for r in records
                if r["case"] == name and r["status"] == "Completed"
            }
        )
        != 1
    ]
    import _homology_native

    wheels = list((ROOT / ".task-artifacts/native-s4-64-wheels").glob("*.whl"))
    report = {
        "schema_version": 1,
        "scope": "S4-04 finite compact representation study; not S4/S5 admission",
        "source_revision": head,
        "source_lf_sha256": hashes,
        "python": sys.version,
        "platform": platform.platform(),
        "rustc": subprocess.check_output(
            ["rustc", "+1.98.1", "--version"], text=True
        ).strip(),
        "build": "Rust1.98.1/PyO3 0.29.3/maturin1.15.0 --release --locked; single-threaded",
        "extension_sha256": sha256(
            Path(_homology_native.__file__).read_bytes()
        ).hexdigest(),
        "wheel_sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in wheels},
        "protocol": {
            "cases": CASES,
            "queries": 8,
            "timing_repeats": 3,
            "seed": 64,
            "rss_repeats": 1,
            "rss_separate_workers": True,
            "budget_note": "same limits; Factorized preserves reference checkpoints; HC adds 2n construction checkpoints",
            "certification": "all Feasible; objective NotComputed; no PH bypass",
            "limits": "finite size and sampling; RSS is absolute process peak including imports/conversions/validators/restore",
        },
        "mismatched_cases": mismatched,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    failures = sum(r["status"] != "Completed" for r in records)
    print(
        f"{len(records)} fresh workers; failures={failures}; mismatches={mismatched}; {args.output}"
    )
    if failures or mismatched:
        raise SystemExit("failed/mismatched evidence preserved; study incomplete")


if __name__ == "__main__":
    main()
