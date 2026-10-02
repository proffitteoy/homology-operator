"""S4 R0: isolated reference workers, disjoint costs and separate RSS/profile runs."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
from time import perf_counter
import traceback

ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def source_snapshot(source, revision):
    paths = sorted((source / "src").rglob("*.py")) + [
        source / name
        for name in (
            "tests/fixtures/reference.json",
            "tests/fixtures/solver_reference.json",
            "scripts/compare_solvers.py",
            "pyproject.toml",
            "uv.lock",
        )
    ]
    hashes = {}
    for path in paths:
        relative = path.relative_to(source).as_posix()
        data = path.read_bytes().replace(b"\r\n", b"\n")
        frozen = subprocess.check_output(
            ["git", "show", f"{revision}:{relative}"], cwd=ROOT
        )
        if data != frozen.replace(b"\r\n", b"\n"):
            raise ValueError(f"source differs from {revision}: {relative}")
        hashes[relative] = sha256(data).hexdigest()
    return {
        "revision": revision,
        "lf_sha256": hashes,
        "snapshot_sha256": digest(hashes),
    }


def make_manifest(source, revision):
    # Reuse the frozen input constructor, never its tracemalloc comparison path.
    sys.path[:0] = [str(source / "src"), str(source / "scripts")]
    from compare_solvers import fixture_problem, suite
    from homology_operator import ResourceLimits

    fixtures = json.loads(
        (source / "tests/fixtures/reference.json").read_text("utf-8")
    )["fixtures"]
    windows = {f["id"]: fixture_problem(f).window.to_dict() for f in fixtures}
    provenance = {
        f["id"]: {"input_hash": f["input_hash"], "source": f["source"]}
        for f in fixtures
    }
    groups, families = defaultdict(list), []
    for fixture in fixtures:
        info = fixture["expected"].get("filtration_slice")
        if info and not fixture["id"].endswith("permuted"):
            groups[info["family"]].append(fixture)
        elif not info:
            families.append((fixture["id"], [fixture]))
    for name, stages in groups.items():
        families.append(
            (
                name,
                sorted(
                    stages, key=lambda f: f["expected"]["filtration_slice"]["stage"]
                ),
            )
        )
    k4 = sorted(
        groups["h1_k4_all_deaths"],
        key=lambda f: f["expected"]["filtration_slice"]["stage"],
    )
    families.append(("h1_survivor_prefix", k4[:6]))
    permuted = list(k4)
    permuted[4] = next(f for f in fixtures if f["id"].endswith("permuted"))
    families.append(("h1_permuted_coordinates", permuted))
    limits = {
        "state_limit": 100000,
        "wall_time_limit": 10.0,
        "matrix_entry_limit": 1000000,
    }
    cases = []

    def add(
        name,
        ids,
        scales=None,
        solver="FeasibleSolver",
        target="Feasible",
        q=8,
        **options,
    ):
        cases.append(
            {
                "id": name,
                "fixture_ids": ids,
                "scales": scales,
                "solver": solver,
                "requested_certificate_level": target,
                "query_count": q,
                "workload": "Joint-certified"
                if solver != "FeasibleSolver"
                else "Topology"
                if q == 0
                else "Joint-basic",
                "resource_limits": limits,
                **options,
            }
        )

    for fixture in fixtures:
        add(f"window/{fixture['id']}/feasible/q8", [fixture["id"]])
    for name, stages in families:
        scales = [
            f["expected"].get("filtration_slice", {}).get("scale", i)
            for i, f in enumerate(stages)
        ]
        add(
            f"family/{name}/feasible/q8",
            [f["id"] for f in stages],
            [i if s is None else s for i, s in enumerate(scales)],
        )
    for solver, target in (
        ("ExhaustiveExactSolver", "ExactOptimal"),
        ("GreedyCertifiedSolver", "CertifiedInterval"),
        ("Rank2ExactSolver", "ExactOptimal"),
    ):
        add(
            f"window/h1_k4_stage_4/{solver}/q8",
            ["h1_k4_stage_4"],
            solver=solver,
            target=target,
        )
    for name, problem in suite():
        if name.startswith("cyclic_m"):
            windows[name] = problem.window.to_dict()
            provenance[name] = dict(problem.window.source_metadata)
            add(
                f"window/{name}/structured/q8",
                [name],
                solver="StructuredFamilySolver",
                target="ExactOptimal",
                input_structure="CyclicTrace",
                matrix_free_output=True,
            )
    for q in (0, 1, 64):
        add(f"window/h1_k4_stage_4/feasible/q{q}", ["h1_k4_stage_4"], q=q)
    floating = next(f["id"] for f in fixtures if f["arithmetic"] == "FloatingPoint")
    add(
        "failure/floating-exact",
        [floating],
        solver="ExhaustiveExactSolver",
        target="ExactOptimal",
    )
    for states in (0, 20):
        budget = ResourceLimits(state_limit=states)
        add(
            f"failure/k4-exact-states-{states}",
            ["h1_k4_stage_4"],
            solver="ExhaustiveExactSolver",
            resource_limits={
                "state_limit": budget.state_limit,
                "wall_time_limit": budget.wall_time_limit,
                "matrix_entry_limit": budget.matrix_entry_limit,
            },
        )
    # Query requests are frozen, including legal zero cycles and repeated requests.
    from homology_operator import ChainWindow

    for case in cases:
        case["queries"] = []
        for index in range(case["query_count"]):
            stage = index % len(case["fixture_ids"])
            window = ChainWindow.from_dict(windows[case["fixture_ids"][stage]])
            basis = window.A.kernel_basis() or ((0,) * window.n,)
            case["queries"].append(
                {
                    "stage": stage,
                    "z": basis[index % len(basis)],
                    "y": basis[(index + 1) % len(basis)],
                }
            )
    metadata = {}
    for key, data in windows.items():
        window = ChainWindow.from_dict(data)
        rank_a, rank_d = window.A.rank(), window.D.rank()
        metadata[key] = {
            "shape": [window.m, window.n, window.p],
            "nnz": [sum(map(sum, window.A.rows)), sum(map(sum, window.D.rows))],
            "rank_A": rank_a,
            "rank_D": rank_d,
            "beta": window.n - rank_a - rank_d,
            "arithmetic": window.arithmetic,
        }
    return {
        "schema_version": 1,
        "purpose": "S4 development R0; not S5 formal performance ranking",
        "source": source_snapshot(source, revision),
        "fixture_file_sha256": sha256(
            (source / "tests/fixtures/reference.json")
            .read_bytes()
            .replace(b"\r\n", b"\n")
        ).hexdigest(),
        "windows": windows,
        "window_metadata": metadata,
        "provenance": provenance,
        "cases": cases,
        "pilot": {"blocks": 1, "repeats": 1},
        "r0": {"blocks": 3, "repeats": 1},
        "worker_timeout_seconds": 60,
        "seed": 20261002,
        "rss": "separate fresh worker: Windows PeakWorkingSetSize; Linux ru_maxrss*1024; macOS ru_maxrss; otherwise null",
        "grouping": [
            "case input",
            "workload",
            "solver",
            "requested and actual certificate",
            "stop status",
            "arithmetic",
            "resource limits",
        ],
        "admission": {
            "scope": "freeze after pilot, before native sampling; R0 is not a native result",
            "benefit": "paired process-block 95% CI wholly below 1 for cold total or absolute RSS on at least one predeclared same-output workload",
            "statistics": "10000 seeded bootstrap resamples of paired process-block median log ratios; at least 10 independent blocks for an admission claim",
            "regression": "report every group; >1.20 median cold-time or RSS ratio blocks default replacement; optional backend may retain explicit restricted scope",
            "correctness": "all joint outputs, statuses, certificates and independent validators pass; no PH bypass",
        },
    }


def run_case(manifest, case, revision):
    from homology_operator import (
        ChainWindow,
        HomologyOperator,
        OperatorFamily,
        OperatorFamilyResult,
        OperatorResult,
        ProjectionProblem,
        ResourceLimits,
        solve_projection,
    )
    from homology_operator import solver as solvers, validation
    from homology_operator import operator as operator_module
    from homology_operator.chain import action_data
    from homology_operator.result import _encode

    if sys.getprofile() is not None and not case.get("diagnostic"):
        raise ValueError("timing worker must have no profiler")
    costs = defaultdict(float)

    def timed(name, call):
        started = perf_counter()
        try:
            return call()
        finally:
            costs[name] += perf_counter() - started

    class MeasuredSolver:
        def __init__(self):
            self.backend = getattr(solvers, case["solver"])()

        def capabilities(self):
            return self.backend.capabilities()

        def solve(self, problem):
            return timed("solver", lambda: self.backend.solve(problem))

    original_dispatch, original_operator = (
        validation.validate_solution,
        operator_module.validate_solution,
    )
    validation.validate_solution = lambda *a: timed(
        "dispatch_validation", lambda: original_dispatch(*a)
    )
    operator_module.validate_solution = lambda *a: timed(
        "operator_validation", lambda: original_operator(*a)
    )
    started = perf_counter()
    outputs, operators, windows = [], [], []
    try:
        windows = timed(
            "input_conversion",
            lambda: [
                ChainWindow.from_dict(manifest["windows"][key])
                for key in case["fixture_ids"]
            ],
        )
        solutions = []
        for window in windows:
            problem = timed(
                "input_conversion",
                lambda: ProjectionProblem(
                    window,
                    resource_limits=ResourceLimits(**case["resource_limits"]),
                    requested_certificate_level=case["requested_certificate_level"],
                    input_structure=case.get("input_structure", "GeneralChainWindow"),
                    matrix_free_output=case.get("matrix_free_output", False),
                ),
            )
            solutions.append(
                timed(
                    "dispatch_inclusive",
                    lambda: solve_projection(problem, MeasuredSolver()),
                )
            )
        costs["dispatch_other"] = (
            costs.pop("dispatch_inclusive")
            - costs.get("solver", 0)
            - costs.get("dispatch_validation", 0)
        )
        validation.validate_solution = original_dispatch
        for window, solution in zip(windows, solutions):
            if solution.projection is not None:
                operators.append(
                    timed(
                        "operator_inclusive",
                        lambda: HomologyOperator(window, solution, revision),
                    )
                )
        if "operator_inclusive" in costs:
            costs["operator_other"] = costs.pop("operator_inclusive") - costs.get(
                "operator_validation", 0
            )
        # Later snapshot/recovery validators belong to their enclosing phases.
        operator_module.validate_solution = original_operator
        if len(operators) == len(windows):
            for op in operators:
                outputs.append(
                    timed(
                        "topology",
                        lambda: {
                            "identity": {
                                k: v
                                for k, v in op.identity.items()
                                if k != "solver_run_id"
                            },
                            "action": action_data(op.P),
                            "betti": op.betti(),
                            "kernel": op.kernel_basis(),
                        },
                    )
                )
            family = None
            if case["scales"] is not None:
                family = timed(
                    "family_input_audit",
                    lambda: OperatorFamily(
                        tuple(case["scales"]), tuple(windows), tuple(operators)
                    ),
                )

                def transport():
                    result = family.barcode()
                    for i in range(len(windows)):
                        for j in range(i, len(windows)):
                            family.transport_certificate(i, j)
                    return result.to_dict()

                # Run IDs in the barcode metadata are omitted only from the semantic digest.
                barcode = timed("transport_barcode", transport)
                outputs.append(
                    {"barcode": {k: barcode[k] for k in ("state", "value", "exact")}}
                )

            def geometry():
                result = []
                for query in case["queries"]:
                    i, z, y = query["stage"], query["z"], query["y"]
                    op = operators[i]
                    row = {
                        "representative": op.class_representative(z),
                        "mass": op.selected_mass(z),
                        "distance": op.class_distance(z, y),
                        "support": op.support(z),
                        "shared": op.shared_support(z, y),
                        "union": op.union_support(z, y),
                    }
                    if family is not None:
                        j = len(windows) - 1
                        row["tracking"] = [
                            family.track_class(z, i, j).value,
                            family.track_mass(z, i, j).value,
                            family.track_support(z, i, j).value,
                        ]
                    result.append(row)
                return result

            outputs.append(timed("geometry", geometry))
            objects = [family] if family else operators
            for obj in objects:
                text = timed("serialization", lambda: obj.to_result().to_json())
                restored = timed(
                    "restore",
                    lambda: (
                        OperatorFamilyResult if family else OperatorResult
                    ).from_json(text),
                )
                if timed("restore_audit", restored.to_json) != text:
                    raise ValueError("round-trip changed the snapshot")
        statuses = [
            {
                "status": s.status,
                "certificate_level": s.certificate_level,
                "objective": {
                    "state": s.objective.state,
                    "value": s.objective.value,
                    "exact": s.objective.exact,
                    "details": dict(s.objective.details),
                }
                if s.objective
                else None,
                "lower_bound": s.lower_bound,
                "upper_bound": s.upper_bound,
                "diagnostics": s.diagnostics,
            }
            for s in solutions
        ]
        semantic = _encode({"statuses": statuses, "outputs": outputs})
        semantic_sha = timed("output_digest", lambda: digest(semantic))
        total = perf_counter() - started
        costs["pipeline_other"] = total - sum(costs.values())
        if any(value < 0 for value in costs.values()):
            raise ValueError("overlapping timing segments")
        return {
            "state": "Completed",
            "completed_requested_workload": all(
                s.status in ("Solved", "FeasibleOnly") for s in solutions
            ),
            "solver_results": semantic["statuses"],
            "comparison_group_sha256": digest(
                {
                    "case": case["id"],
                    "actual": [(s.status, s.certificate_level) for s in solutions],
                    "arithmetic": [w.arithmetic for w in windows],
                }
            ),
            "semantic_output_sha256": semantic_sha,
            "pipeline_seconds": total,
            "segments_seconds": dict(costs),
            "shapes": [[w.m, w.n, w.p] for w in windows],
        }
    finally:
        validation.validate_solution, operator_module.validate_solution = (
            original_dispatch,
            original_operator,
        )


def peak_rss():
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                ] + [
                    (name, ctypes.c_size_t)
                    for name in (
                        "PeakWorkingSetSize",
                        "WorkingSetSize",
                        "QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage",
                        "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage",
                        "PagefileUsage",
                        "PeakPagefileUsage",
                    )
                ]

            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            get_info = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
            get_info.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(Counters),
                wintypes.DWORD,
            ]
            get_info.restype = wintypes.BOOL
            if not get_info(
                kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            return (
                counters.PeakWorkingSetSize,
                "Windows GetProcessMemoryInfo.PeakWorkingSetSize",
                None,
            )
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform not in ("linux", "darwin"):
            return None, None, "unsupported ru_maxrss units"
        return (
            int(value * (1024 if sys.platform == "linux" else 1)),
            "getrusage(RUSAGE_SELF).ru_maxrss",
            None,
        )
    except (ImportError, OSError) as error:
        return None, None, str(error)


def worker(args):
    source = args.source_root.resolve()
    sys.path[:0] = [str(source / "src")]
    manifest = json.loads(args.manifest.read_text("utf-8"))
    case = next(c for c in manifest["cases"] if c["id"] == args.case)
    import homology_operator

    if (
        Path(homology_operator.__file__).resolve().parent
        != source / "src/homology_operator"
    ):
        raise ValueError("worker imported a different reference source")
    import tracemalloc

    if tracemalloc.is_tracing():
        raise ValueError("tracemalloc must be disabled")
    if args.mode == "diagnostic":
        import cProfile

        profiler = cProfile.Profile()
        args.profile_output.parent.mkdir(parents=True, exist_ok=True)
        result = profiler.runcall(
            run_case,
            manifest,
            case | {"diagnostic": True},
            manifest["source"]["revision"],
        )
        profiler.dump_stats(str(args.profile_output))
        result = {
            "state": result["state"],
            "semantic_output_sha256": result["semantic_output_sha256"],
            "profile": str(args.profile_output),
            "timing_excluded": True,
        }
    else:
        result = run_case(manifest, case, manifest["source"]["revision"])
        if args.mode == "memory":
            value, method, failure = peak_rss()
            result = {
                "state": result["state"],
                "semantic_output_sha256": result["semantic_output_sha256"],
                "peak_rss_bytes": value,
                "rss_method": method,
                "rss_failure": failure,
                "timing_excluded": True,
            }
    return result | {"pid": os.getpid(), "mode": args.mode}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--source-revision")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--create-manifest", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--phase", choices=("pilot", "r0"), default="pilot")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--case")
    parser.add_argument(
        "--mode", choices=("timing", "memory", "diagnostic"), default="timing"
    )
    parser.add_argument("--profile-output", type=Path)
    args = parser.parse_args()
    if args.worker:
        try:
            print(json.dumps(worker(args)))
        except Exception:
            print(
                json.dumps(
                    {
                        "state": "WorkerFailed",
                        "error": traceback.format_exc(),
                        "pid": os.getpid(),
                        "mode": args.mode,
                    }
                )
            )
            return 1
        return 0
    if args.create_manifest:
        if not args.source_revision:
            parser.error("--create-manifest requires --source-revision")
        write_json(
            args.manifest,
            make_manifest(args.source_root.resolve(), args.source_revision),
        )
        print(f"Manifest frozen: {args.manifest}")
        return 0
    if not args.output:
        parser.error("measurement requires --output")
    manifest = json.loads(args.manifest.read_text("utf-8"))
    source_snapshot(args.source_root.resolve(), manifest["source"]["revision"])
    plan = manifest[args.phase]
    samples = []
    rng = random.Random(manifest["seed"])
    modes = {
        "timing": ("timing", "memory"),
        "memory": ("memory",),
        "diagnostic": ("diagnostic",),
    }[args.mode]
    for mode in modes:
        for block in range(plan["blocks"] if mode == "timing" else 1):
            cases = list(manifest["cases"])
            if mode == "diagnostic":
                cases = [
                    c
                    for c in cases
                    if c["id"]
                    in (
                        "window/h1_k4_stage_4/ExhaustiveExactSolver/q8",
                        "family/h1_k4_all_deaths/feasible/q8",
                    )
                ]
            rng.shuffle(cases)
            for case in cases:
                for repeat in range(plan["repeats"] if mode == "timing" else 1):
                    command = [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--worker",
                        "--source-root",
                        str(args.source_root.resolve()),
                        "--manifest",
                        str(args.manifest.resolve()),
                        "--case",
                        case["id"],
                        "--mode",
                        mode,
                    ]
                    if mode == "diagnostic":
                        command += [
                            "--profile-output",
                            str(
                                args.output.parent
                                / (case["id"].replace("/", "_") + ".prof")
                            ),
                        ]
                    started = perf_counter()
                    try:
                        child = subprocess.run(
                            command,
                            capture_output=True,
                            text=True,
                            timeout=manifest["worker_timeout_seconds"],
                        )
                        elapsed = perf_counter() - started
                        try:
                            row = (
                                json.loads(child.stdout)
                                if child.stdout
                                else {"state": "ProcessFailed"}
                            )
                        except json.JSONDecodeError:
                            row = {"state": "ProcessFailed", "stdout": child.stdout}
                        if child.returncode and row["state"] == "Completed":
                            row["state"] = "ProcessFailed"
                        row |= {"exit_code": child.returncode, "stderr": child.stderr}
                    except subprocess.TimeoutExpired:
                        elapsed = perf_counter() - started
                        row = {
                            "state": "ExternalTimeout",
                            "exit_code": None,
                            "timeout_seconds": manifest["worker_timeout_seconds"],
                        }
                    row |= {
                        "case": case["id"],
                        "block": block,
                        "repeat": repeat,
                        "order": len(samples),
                        "mode": mode,
                        "cold_process_seconds": elapsed
                        if mode == "timing" and row["state"] == "Completed"
                        else None,
                        "failure_elapsed_seconds": elapsed
                        if row["state"] != "Completed"
                        else None,
                    }
                    samples.append(row)
            print(f"{mode}: block {block + 1} complete", flush=True)
    hashes = defaultdict(set)
    for row in samples:
        if row.get("semantic_output_sha256"):
            hashes[row["case"]].add(row["semantic_output_sha256"])
    unstable = [key for key, values in hashes.items() if len(values) != 1]
    summary = {}
    for case in manifest["cases"]:
        rows = [
            r
            for r in samples
            if r["case"] == case["id"]
            and r["mode"] == "timing"
            and r["state"] == "Completed"
            and r.get("completed_requested_workload")
        ]
        if rows:
            summary[case["id"]] = {
                "n": len(rows),
                "median_cold_seconds": statistics.median(
                    r["cold_process_seconds"] for r in rows
                ),
                "median_pipeline_seconds": statistics.median(
                    r["pipeline_seconds"] for r in rows
                ),
            }
    write_json(
        args.output,
        {
            "schema_version": 1,
            "phase": args.phase,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "manifest_sha256": sha256(args.manifest.read_bytes()).hexdigest(),
            "harness_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "harness_tracked_dirty": bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain", "--untracked-files=no"],
                    cwd=ROOT,
                    text=True,
                ).strip()
            ),
            "harness_sha256": sha256(
                Path(__file__).read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest(),
            "environment": {
                "python": sys.version,
                "executable": sys.executable,
                "platform": platform.platform(),
                "machine": platform.machine(),
                "processor": os.environ.get(
                    "PROCESSOR_IDENTIFIER", platform.processor()
                ),
                "threads": 1,
                "timer": "perf_counter; no profiler or tracemalloc in timing/RSS workers",
                "cold_scope": "process launch, interpreter/imports, manifest parsing, validated pipeline, JSON output and exit; parent aggregation excluded",
            },
            "source": manifest["source"],
            "samples": samples,
            "summary": summary,
            "unstable_output_cases": unstable,
        },
    )
    if unstable or any(r["state"] != "Completed" for r in samples):
        print(
            "Retained worker failures or unstable semantic outputs; inspect raw samples."
        )
        return 1
    print(f"Saved {len(samples)} raw samples: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
