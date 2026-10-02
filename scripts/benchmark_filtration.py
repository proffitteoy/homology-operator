"""S4-07 serial cold workers: frozen legacy, adjacent, and full-rank ablation."""

import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
from time import perf_counter

from benchmark_reference import peak_rss

ROOT = Path(__file__).resolve().parents[1]


def worker(args):
    started = perf_counter()
    from homology_operator import (
        ChainWindow,
        FeasibleSolver,
        HomologyOperator,
        Matrix,
        OperatorFamily,
        ProjectionProblem,
    )
    from homology_operator.result import content_id

    if args.worker == "legacy":
        spec = importlib.util.spec_from_file_location(
            "homology_operator._family_r0", args.legacy_file
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        family_type = module.OperatorFamily
    else:
        family_type = OperatorFamily
    imported = perf_counter()
    # Local synthetic chain inputs, not migrated research fixtures. Growing
    # stages add coordinates and subsequently kill four old directions.
    windows, operators = [], []
    for phase in range(6 if args.fixture == "growing" else 1):
        n = 4 + 2 * phase if args.fixture == "growing" else 12
        p = min(phase, 4) if args.fixture == "growing" else 6
        window = ChainWindow(
            0,
            Matrix.zero(0, n),
            Matrix.from_columns(
                (tuple(int(i == j) for i in range(n)) for j in range(p)), n
            ),
            (),
            tuple(f"v{i}" for i in range(n)),
            tuple(f"e{i}" for i in range(p)),
            tuple(range(1, n + 1)),
            arithmetic="ExactInteger",
        )
        solution = FeasibleSolver().solve(ProjectionProblem(window))
        windows.append(window)
        operators.append(HomologyOperator(window, solution))
    active = [
        min(i * len(windows) // args.stages, len(windows) - 1)
        for i in range(args.stages)
    ]
    scales = tuple(i // 2 for i in range(args.stages))
    fixture_hash = content_id(
        "filtration-fixture",
        {
            "windows": [w.to_dict() for w in windows],
            "active": active,
            "scales": scales,
        },
    )
    prepared = perf_counter()
    family = family_type(
        scales, tuple(windows[i] for i in active), tuple(operators[i] for i in active)
    )
    constructed = perf_counter()
    table = family.rank_table() if args.worker == "all-ranks" else None
    barcode = family.barcode()
    read = perf_counter()
    z = tuple(int(i == 0 or i == windows[0].n - 1) for i in range(windows[0].n))
    tracking = [
        family.track_class(z, 0, args.stages - 1).value,
        family.track_mass(z, 0, args.stages - 1).value,
        family.track_support(z, 0, args.stages - 1).value,
    ]
    tracked = perf_counter()
    output_hash = content_id(
        "filtration-output", {"bars": barcode.value, "tracking": tracking}
    )
    peak, method, failure = peak_rss()
    result = {
        "route": args.worker,
        "fixture": args.fixture,
        "stages": args.stages,
        "fixture_hash": fixture_hash,
        "output_hash": output_hash,
        "rank_entries": None if table is None else len(table.value),
        "retained_chain_actions": len(family._transports),
        "certificate_level": "Feasible",
        "topology_exact": True,
        "objective_state": solution.objective.state,
        "resource_limits": dict(solution.solver_config["resource_limits"]),
        "phases_seconds": {
            "imports": imported - started,
            "input_solver_validation": prepared - imported,
            "family_input_validation": constructed - prepared,
            "barcode_and_requested_ranks": read - constructed,
            "arbitrary_class_geometry": tracked - read,
        },
        "worker_seconds": tracked - started,
        "peak_rss_bytes": peak,
        "rss_method": method,
        "rss_failure": failure,
    }
    if args.worker == "adjacent" and args.stages == 64:
        # Snapshot storage ablation is kept outside the timed/RSS readout above.
        for schema in (1, 2):
            stamp = perf_counter()
            snapshot = family.to_result(schema_version=schema)
            wire = snapshot.to_json()
            result[f"schema_{schema}_seconds"] = perf_counter() - stamp
            result[f"schema_{schema}_bytes"] = len(wire.encode("utf-8"))
            result[f"schema_{schema}_hash"] = sha256(wire.encode("utf-8")).hexdigest()
            restored = snapshot.to_family()
            if restored.identity != family.identity or restored.barcode() != barcode:
                raise ValueError("snapshot ablation changed family identity or barcode")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("legacy", "adjacent", "all-ranks"))
    parser.add_argument("--legacy-file", type=Path)
    parser.add_argument(
        "--baseline", default="d9bdf3bfe7a3fb365929d99d90cb85ca7c367f23"
    )
    parser.add_argument(
        "--fixture", choices=("constant", "growing"), default="constant"
    )
    parser.add_argument("--stages", type=int, default=64)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args), sort_keys=True))
        return
    if args.repeats < 1 or not args.output:
        parser.error("positive --repeats and --output required")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    source_hashes = {}
    paths = subprocess.check_output(
        [
            "git",
            "ls-files",
            "src",
            "scripts/benchmark_filtration.py",
            "scripts/benchmark_reference.py",
            "uv.lock",
        ],
        cwd=ROOT,
        text=True,
    ).splitlines()
    for path in paths:
        actual = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
        frozen = subprocess.check_output(
            ["git", "show", f"{head}:{path}"], cwd=ROOT
        ).replace(b"\r\n", b"\n")
        if actual != frozen:
            raise ValueError(f"dirty measured source: {path}")
        source_hashes[path] = sha256(actual).hexdigest()
    legacy = subprocess.check_output(
        ["git", "show", f"{args.baseline}:src/homology_operator/family.py"], cwd=ROOT
    )
    legacy_file = ROOT / ".task-artifacts/filtration-legacy.py"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_bytes(legacy)
    jobs = [
        (route, fixture, stages, repeat)
        for repeat in range(args.repeats)
        for fixture in ("constant", "growing")
        for stages in (64, 192)
        for route in ("legacy", "adjacent", "all-ranks")
    ]
    random.Random(67).shuffle(jobs)
    samples = []
    for route, fixture, stages, repeat in jobs:
        stamp = perf_counter()
        completed = subprocess.run(
            [
                sys.executable,
                __file__,
                "--worker",
                route,
                "--fixture",
                fixture,
                "--stages",
                str(stages),
                "--legacy-file",
                str(legacy_file),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
            timeout=300,
        )
        sample = json.loads(completed.stdout)
        sample.update(repeat=repeat, process_seconds=perf_counter() - stamp)
        samples.append(sample)
        print(f"{len(samples)}/{len(jobs)} {route} {fixture} {stages}", flush=True)
    summary = []
    for fixture in ("constant", "growing"):
        for stages in (64, 192):
            group = [
                s for s in samples if s["fixture"] == fixture and s["stages"] == stages
            ]
            if (
                len({s["output_hash"] for s in group}) != 1
                or len({s["fixture_hash"] for s in group}) != 1
            ):
                raise ValueError("routes have different inputs or semantic outputs")
            for route in ("legacy", "adjacent", "all-ranks"):
                selected = [s for s in group if s["route"] == route]
                summary.append(
                    {
                        "route": route,
                        "fixture": fixture,
                        "stages": stages,
                        "median_worker_seconds": statistics.median(
                            s["worker_seconds"] for s in selected
                        ),
                        "median_peak_rss_bytes": statistics.median(
                            s["peak_rss_bytes"] for s in selected
                        ),
                        "median_retained_chain_actions": statistics.median(
                            s["retained_chain_actions"] for s in selected
                        ),
                    }
                )
    report = {
        "source_revision": head,
        "source_lf_sha256": source_hashes,
        "baseline_revision": args.baseline,
        "legacy_family_sha256": sha256(legacy.replace(b"\r\n", b"\n")).hexdigest(),
        "environment": {"python": sys.version, "platform": platform.platform()},
        "rss_scope": "absolute process peak through topology/geometry; before optional schema ablation",
        "schedule_seed": 67,
        "samples": samples,
        "summary": summary,
        "limitations": [
            "Synthetic finite filters; no GUDHI or application performance conclusion.",
            "Serial cold workers; absolute RSS includes runtime/imports.",
            "Full rank table has real quadratic output; not an equal-output speed comparison.",
            "Schema timing includes snapshot validation; per-run solver UUIDs change wire hashes.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Saved {len(samples)} matching semantic samples to {args.output}")


if __name__ == "__main__":
    main()
