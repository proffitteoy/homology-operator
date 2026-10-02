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


def prepared_worker(backend, count, width, revision):
    started = perf_counter()
    from homology_operator import Matrix
    from homology_operator.native import PreparedMatrix
    from homology_operator.result import content_id

    imported = perf_counter()
    rng = random.Random(6300 + width)
    positions = [set(rng.sample(range(width), 4)) for _ in range(24)]
    matrix = Matrix.from_rows(
        (tuple(int(j in row) for j in range(width)) for row in positions)
    )
    vectors = tuple(
        tuple(int((j + i) % 5 == 0) for j in range(width)) for i in range(count)
    )
    rhs = tuple(matrix.apply(x) for x in vectors)
    ready = perf_counter()
    decompositions = 0

    def prepare():
        nonlocal decompositions
        decompositions += 1
        return PreparedMatrix(matrix)

    stats = None
    if backend == "reference":
        # Observe actual rref calls, including membership's solve.
        original_rref = Matrix.rref

        def counted_rref(self):
            nonlocal decompositions
            decompositions += 1
            return original_rref(self)

        Matrix.rref = counted_rref
        rank, kernel, image = matrix.rank(), matrix.kernel_basis(), matrix.image_basis()
        solutions = tuple(matrix.solve(x) for x in rhs)
        membership = tuple(matrix.solve(x) is not None for x in rhs)
        actions = tuple(matrix.apply(x) for x in vectors)
        Matrix.rref = original_rref
    elif backend == "prepared":
        handle = prepare()
        rank, kernel, image = handle.rank(), handle.kernel_basis(), handle.image_basis()
        solutions, membership, actions = (
            handle.solve_many(rhs),
            handle.membership_many(rhs),
            handle.apply_many(vectors),
        )
        stats = handle.statistics()
    else:
        handle = prepare()
        rank, kernel, image = (
            handle.rank(),
            prepare().kernel_basis(),
            prepare().image_basis(),
        )
        solutions = tuple(prepare().solve(x) for x in rhs)
        membership = tuple(prepare().membership_many((x,))[0] for x in rhs)
        actions = handle.apply_many(vectors)
        stats = handle.statistics()
    calculated = perf_counter()
    output = {
        "rank": rank,
        "kernel": kernel,
        "image": image,
        "solutions": solutions,
        "membership": membership,
        "actions": actions,
    }
    from homology_operator.result import canonical_json

    restored = json.loads(canonical_json(output))
    result_hash = content_id("packed-output", restored)
    encoded = perf_counter()
    return {
        "backend": backend,
        "queries": count,
        "width": width,
        "shape": [24, width],
        "source_revision": revision,
        "fixture_hash": content_id("packed-fixture", matrix.rows),
        "output_hash": result_hash,
        "decomposition_count": decompositions,
        "statistics": stats,
        "phases_seconds": {
            "imports": imported - started,
            "input_and_rhs": ready - imported,
            "algebra_including_conversion_decode": calculated - ready,
            "serialization_restore_hash": encoded - calculated,
        },
        "worker_seconds": encoded - started,
    }


def solver_cases():
    """Predeclared finite cases; reuse the pinned Phase-3 fixture constructors."""
    from compare_solvers import suite
    from homology_operator import ResourceLimits

    source = dict(suite())
    k4 = source["h1_k4_stage_4"]
    yield "k4_exact", k4, "ExhaustiveExactSolver"
    yield (
        "k4_greedy",
        replace(k4, requested_certificate_level="CertifiedInterval"),
        "GreedyCertifiedSolver",
    )
    yield "cut_rank2", source["cut_macro_specialized"], "Rank2ExactSolver"
    yield "cyclic_m4", source["cyclic_m4"], "StructuredFamilySolver"
    yield (
        "k4_bigint",
        replace(
            k4,
            window=replace(
                k4.window,
                weights=tuple(2**200 + 2 * j + 1 for j in range(k4.window.n)),
                arithmetic="ExactInteger",
            ),
            requested_certificate_level="CertifiedInterval",
        ),
        "GreedyCertifiedSolver",
    )
    yield (
        "k4_interrupted",
        replace(k4, resource_limits=ResourceLimits(state_limit=20)),
        "ExhaustiveExactSolver",
    )
    yield (
        "floating_unavailable",
        replace(
            k4,
            window=replace(
                k4.window, weights=(1.0,) * k4.window.n, arithmetic="FloatingPoint"
            ),
        ),
        "GreedyCertifiedSolver",
    )


def solver_worker(backend, revision, block, memory=False):
    from homology_operator import HomologyOperator, OperatorResult, solve_projection
    from homology_operator.result import content_id
    from homology_operator.solver import (
        ExhaustiveExactSolver,
        GreedyCertifiedSolver,
        Rank2ExactSolver,
        StructuredFamilySolver,
    )

    classes = {
        cls.__name__: cls
        for cls in (
            ExhaustiveExactSolver,
            GreedyCertifiedSolver,
            Rank2ExactSolver,
            StructuredFamilySolver,
        )
    }
    records = []
    cases = tuple(solver_cases())
    schedule = [
        (case, repeat) for repeat in range(1 if memory else 5) for case in cases
    ]
    random.Random(6500 + block).shuffle(schedule)
    for (case, problem, method), repeat in schedule:
        solver = classes[method](native=backend == "native")
        construction = None

        class Measured:
            def capabilities(self):
                return solver.capabilities()

            def solve(self, request):
                nonlocal construction
                started = perf_counter()
                solution = solver.solve(request)
                construction = perf_counter() - started
                return solution

        started = perf_counter()
        solution = solve_projection(problem, Measured())
        dispatched = perf_counter()
        readout, serialized, restored = None, None, None
        if solution.projection is not None:
            op = HomologyOperator(
                problem.window, solution, repository_revision=revision
            )
            z = problem.window.A.kernel_basis()[:2]
            readout = {
                "betti": op.betti(),
                "representatives": tuple(op.class_representative(x) for x in z),
                "mass": tuple(op.selected_mass(x) for x in z),
                "support": tuple(op.support(x) for x in z),
            }
            serialized = op.to_result().to_json()
            restored = OperatorResult.from_json(serialized)
        exported = perf_counter()
        semantic = {
            "projection": None
            if solution.projection is None
            else tuple(
                solution.projection.apply(
                    tuple(int(i == j) for i in range(problem.window.n))
                )
                for j in range(problem.window.n)
            ),
            "objective_state": solution.objective.state,
            "objective": solution.objective.value,
            "certificate_level": solution.certificate_level,
            "status": solution.status,
            "bounds": (solution.lower_bound, solution.upper_bound),
            "proof": solution.certificate,
            "readout": readout,
            "restored_projection": None
            if restored is None
            else tuple(
                restored.projection.apply(
                    tuple(int(i == j) for i in range(problem.window.n))
                )
                for j in range(problem.window.n)
            ),
        }
        record = {
            "case": case,
            "method": method,
            "backend": backend,
            "block": block,
            "repeat": repeat,
            "input_hash": content_id(
                "solver-benchmark-input", problem.window.to_dict()
            ),
            "request": problem.solver_config(method),
            "status": solution.status,
            "certificate_level": solution.certificate_level,
            "objective_state": solution.objective.state,
            "output_hash": content_id("solver-benchmark-output", semantic),
            "resource_usage": solution.resource_usage,
            "actual_method": solution.method,
            "actual_solver_config": solution.solver_config,
            "solver_config_id": solution.solver_config_id,
            "diagnostics": solution.diagnostics,
            "phases_seconds": {
                "construction": construction,
                "dispatch_and_independent_validation": dispatched - started,
                "dispatch_overhead_including_validation": dispatched
                - started
                - (construction or 0),
                "operator_readout_serialization_restore": exported - dispatched,
                "complete": exported - started,
            },
            "serialized_bytes": None
            if serialized is None
            else len(serialized.encode("utf-8")),
        }
        records.append(record)
    if memory:
        from benchmark_reference import peak_rss

        value, method, failure = peak_rss()
        return {
            "backend": backend,
            "block": block,
            "worker_peak_rss_bytes": value,
            "rss_method": method,
            "rss_failure": failure,
            "timing_excluded": True,
            "scope": "absolute peak of the whole seven-case worker; not per-case RSS",
            "records": [
                {
                    key: r[key]
                    for key in ("case", "output_hash", "status", "certificate_level")
                }
                for r in records
            ],
        }
    return records


def solver_benchmark(args):
    import _homology_native
    from homology_operator.result import canonical_json, content_id

    if args.worker:
        print(
            canonical_json(
                solver_worker(args.worker, args.revision, args.block, args.memory)
            )
        )
        return
    if args.output is None:
        raise ValueError("--output is required")
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
            "scripts/benchmark_reference.py",
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
    manifest = [
        {
            "case": case,
            "method": method,
            "input_hash": content_id("solver-benchmark-input", p.window.to_dict()),
            "request": p.solver_config(method),
        }
        for case, p, method in solver_cases()
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    schedule = [
        (backend, block) for block in range(10) for backend in ("reference", "native")
    ]
    random.Random(65).shuffle(schedule)
    records, failures, memory = [], [], []
    for mode in ("timing", "memory"):
        jobs = schedule if mode == "timing" else [("reference", 0), ("native", 0)]
        for backend, block in jobs:
            started = perf_counter()
            command = [
                sys.executable,
                __file__,
                "--solvers",
                "--worker",
                backend,
                "--block",
                str(block),
                "--revision",
                head,
            ]
            if mode == "memory":
                command.append("--memory")
            try:
                done = subprocess.run(
                    command, cwd=ROOT, text=True, capture_output=True, timeout=120
                )
                if done.returncode:
                    failures.append(
                        {
                            "mode": mode,
                            "backend": backend,
                            "block": block,
                            "returncode": done.returncode,
                            "stderr": done.stderr,
                        }
                    )
                    continue
                result = json.loads(done.stdout)
                if mode == "memory":
                    memory.append(result)
                else:
                    for r in result:
                        r["worker_process_seconds"] = perf_counter() - started
                    records.extend(result)
            except subprocess.TimeoutExpired:
                failures.append(
                    {
                        "mode": mode,
                        "backend": backend,
                        "block": block,
                        "status": "process_timeout",
                    }
                )
    for case in manifest:
        samples = [r for r in records if r["case"] == case["case"]]
        if len(samples) != 100 or len({r["output_hash"] for r in samples}) != 1:
            failures.append(
                {
                    "case": case["case"],
                    "status": "missing_samples_or_semantic_mismatch",
                    "samples": len(samples),
                }
            )
    from statistics import median, quantiles

    summaries = []
    for case in manifest:
        samples = [r for r in records if r["case"] == case["case"]]
        phases = ("construction", "dispatch_overhead_including_validation", "complete")
        for phase in phases:
            values = {
                backend: [
                    r["phases_seconds"][phase]
                    for r in samples
                    if r["backend"] == backend
                    and r["phases_seconds"][phase] is not None
                ]
                for backend in ("reference", "native")
            }
            if any(len(v) != 50 for v in values.values()):
                continue
            paired = []
            for block in range(10):
                times = {
                    backend: median(
                        r["phases_seconds"][phase]
                        for r in samples
                        if r["backend"] == backend and r["block"] == block
                    )
                    for backend in values
                }
                paired.append(times["reference"] / times["native"])
            rng = random.Random(65000)
            bootstraps = sorted(median(rng.choices(paired, k=10)) for _ in range(10000))
            summaries.append(
                {
                    "case": case["case"],
                    "phase": phase,
                    "reference_median_seconds": median(values["reference"]),
                    "native_median_seconds": median(values["native"]),
                    "reference_iqr_seconds": quantiles(
                        values["reference"], n=4, method="inclusive"
                    )[2]
                    - quantiles(values["reference"], n=4, method="inclusive")[0],
                    "native_iqr_seconds": quantiles(
                        values["native"], n=4, method="inclusive"
                    )[2]
                    - quantiles(values["native"], n=4, method="inclusive")[0],
                    "paired_block_median_ratio": median(paired),
                    "paired_bootstrap_95_percent_interval": [
                        bootstraps[249],
                        bootstraps[9749],
                    ],
                }
            )
    for worker in memory:
        for record in worker["records"]:
            if {r["output_hash"] for r in records if r["case"] == record["case"]} != {
                record["output_hash"]
            }:
                failures.append(
                    {
                        "mode": "memory",
                        "case": record["case"],
                        "status": "semantic_mismatch",
                    }
                )
    report = {
        "schema_version": 1,
        "scope": "S4-05 finite same-solver pilot; not S4/S5 acceptance",
        "source_revision": head,
        "source_lf_sha256": hashes,
        "manifest": manifest,
        "python": sys.version,
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "rustc": subprocess.check_output(
            ["rustc", "+1.98.1", "--version"], text=True
        ).strip(),
        "build": "maturin 1.15.0 --release --locked; PyO3 0.29.3; safe Rust; one thread",
        "extension_sha256": sha256(
            Path(_homology_native.__file__).read_bytes()
        ).hexdigest(),
        "wheel_sha256": {
            p.name: sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / ".task-artifacts/native-s4-65-wheels").glob("*.whl")
        },
        "protocol": {
            "seed": 65,
            "blocks": 10,
            "repeats_per_worker": 5,
            "worker_order": "randomized, seed 65",
            "case_order": "paired random order, seed 6500+block",
            "warm_repeats_after_process_import": True,
            "profiling": False,
            "memory": "separate new processes, whole-worker absolute RSS; timings excluded",
            "timeout_seconds": 120,
            "general_search": "existing no-go unchanged",
        },
        "records": records,
        "failures": failures,
        "memory_workers": memory,
        "summaries": summaries,
    }
    args.output.write_text(
        json.dumps(json.loads(canonical_json(report)), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"{len(records)} records; {len(failures)} failures; {args.output}", flush=True
    )
    if failures:
        raise ValueError("retained benchmark failures; inspect the report")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--worker", choices=("native", "reference", "prepared", "repeated")
    )
    parser.add_argument("--prepared", action="store_true")
    parser.add_argument("--solvers", action="store_true")
    parser.add_argument("--block", type=int, default=0)
    parser.add_argument("--memory", action="store_true")
    parser.add_argument("--width", type=int, default=65)
    parser.add_argument("--queries", type=int, default=8)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.solvers:
        solver_benchmark(args)
        return
    if args.worker:
        result = (
            prepared_worker(args.worker, args.queries, args.width, args.revision)
            if args.prepared
            else worker(args.worker, args.queries, args.revision)
        )
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
    if args.prepared:
        schedule = [
            (backend, count, repeat, width)
            for repeat in range(3)
            for count in (8, 64)
            for width in (65, 129)
            for backend in ("reference", "prepared", "repeated")
        ]
        random.Random(63).shuffle(schedule)
    records = []
    for job in schedule:
        backend, count, repeat = job[:3]
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
            ]
            + (["--prepared", "--width", str(job[3])] if args.prepared else []),
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        record = json.loads(completed.stdout)
        record.update(repeat=repeat, process_seconds=perf_counter() - started)
        records.append(record)
    for count in (8, 64) if args.prepared else (0, 8, 64):
        if args.prepared:
            for width in (65, 129):
                if (
                    len(
                        {
                            r["output_hash"]
                            for r in records
                            if r["queries"] == count and r["width"] == width
                        }
                    )
                    != 1
                ):
                    raise ValueError("prepared/repeated/reference outputs differ")
            continue
        if len({r["output_hash"] for r in records if r["queries"] == count}) != 1:
            raise ValueError("reference/native semantic outputs differ")
    import _homology_native

    binaries = list(
        (
            ROOT
            / (
                ".task-artifacts/native-s4-63-wheels"
                if args.prepared
                else ".task-artifacts/native-wheels"
            )
        ).glob("*.whl")
    )
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
    if args.prepared:
        report.update(
            scope="S4-03 sparse prepared algebra ablation; not operator/S4 performance acceptance",
            protocol={
                "query_counts": [8, 64],
                "widths": [65, 129],
                "rows": 24,
                "repeats": 3,
                "seed": 63,
                "fixture_seed": "6300+width; 4 random distinct bits per row",
                "cold_workers": True,
                "rss": "not measured; stored words/fill-in recorded",
                "reference_counter": "actual Matrix.rref calls; counter overhead included",
                "native_counter": "actual PreparedMatrix constructions; immutable handle count=1",
            },
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        f"{len(records)} cold workers; matching semantic output hashes; {args.output}"
    )


if __name__ == "__main__":
    main()
