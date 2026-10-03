"""S5 serial fresh-process cold/warm, separate OS RSS and failure-preserving sampling."""

import argparse
from collections import Counter
from copy import deepcopy
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

from benchmark_acceptance import (
    CANDIDATE,
    R0,
    checkpoint_json,
    paired_interval,
    run_pipeline,
)
from benchmark_reference import peak_rss
from check_s5_correctness import joint_case, source_hashes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
THREAD_ENV = {
    key: "1"
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    )
}


def digest(value):
    from oracle.simplicial import digest as canonical_digest

    return canonical_digest(value)


def read_topology(families):
    from oracle.gudhi_oracle import interval_statistics

    bars = {}
    for degree, family in families.items():
        query = family.barcode()
        if query.state != "Computed":
            raise ValueError(f"barcode: {query.state}")
        bars[str(degree)] = sorted(
            [
                [b["birth_stage"], b["death_stage"], b["multiplicity"]]
                for b in query.value
            ],
            key=lambda b: (b[0], len(family.windows) if b[1] is None else b[1]),
        )
    return interval_statistics(bars, len(next(iter(families.values())).windows))


def construct_families(manifest, case, route):
    from homology_operator import (
        HomologyOperator,
        OperatorFamily,
        ProjectionProblem,
        ResourceLimits,
        solve_projection,
    )
    from oracle.simplicial import build_windows, number

    windows = build_windows(manifest)
    families, statuses, details = {}, [], []
    compact = (
        route in {"integrated", "factorized_scalar", "hc_workspace"}
        and case["solver"] == "FeasibleSolver"
    )
    method = (
        "NativeFactorizedSolver"
        if compact
        else "NativeFeasibleSolver"
        if route == "native_explicit"
        else "Native" + case["solver"]
        if route == "integrated"
        else case["solver"]
    )
    for degree, slices in windows.items():
        operators = []
        for stage, window in enumerate(slices):
            solution = solve_projection(
                ProjectionProblem(
                    window,
                    resource_limits=ResourceLimits(**case["resource_limits"]),
                    requested_certificate_level=case["requested_certificate_level"],
                    matrix_free_output=compact,
                    solver_options={
                        "representation": "HC"
                        if route == "hc_workspace"
                        else "Factorized"
                    }
                    if compact
                    else {},
                ),
                method,
            )
            statuses.append(
                {
                    "degree": degree,
                    "stage": stage,
                    "status": solution.status,
                    "certificate_level": solution.certificate_level,
                }
            )
            details.append(
                {
                    "method": solution.method,
                    "solver_config": solution.solver_config,
                    "diagnostics": solution.diagnostics,
                    "resource_usage": solution.resource_usage,
                }
            )
            if solution.projection is None or solution.status not in {
                "Solved",
                "FeasibleOnly",
            }:
                return None, statuses, details
            operators.append(HomologyOperator(window, solution))
        families[degree] = OperatorFamily(
            tuple(number(x) for x in manifest["scales"]), slices, tuple(operators)
        )
    return families, statuses, details


def geometry_value(families, case, route, workspaces):
    from homology_operator.result import canonical_json

    values, metadata = {}, []
    count = case["query_count"]
    for degree, family in families.items():
        for stage, op in enumerate(family.operators):
            basis = op.window.A.kernel_basis()
            cycles = [(0,) * op.window.n] + list(basis)
            requested = tuple(cycles[i % len(cycles)] for i in range(2 * count))
            pairs = tuple((2 * i, 2 * i + 1) for i in range(count))
            if route in {"integrated", "native_explicit", "hc_workspace"}:
                from homology_operator.native import GeometryWorkspace, geometry_batch

                key = degree, stage
                if key not in workspaces:
                    workspaces[key] = GeometryWorkspace(op)
                query = geometry_batch(op, requested, pairs, workspace=workspaces[key])
                if query.state != "Computed":
                    raise ValueError(f"geometry batch: {query.state}")
                value = query.value
                metadata.append(
                    {
                        k: v
                        for k, v in query.details.items()
                        if k not in {"arguments", "pairs"}
                    }
                )
            else:
                value = {
                    name: tuple(getattr(op, name)(z) for z in requested)
                    for name in ("class_representative", "selected_mass", "support")
                }
                value.update(
                    {
                        name: tuple(
                            getattr(op, name)(requested[a], requested[b])
                            for a, b in pairs
                        )
                        for name in (
                            "class_distance",
                            "shared_support",
                            "union_support",
                        )
                    }
                )
                metadata.append({"route": "scalar"})
            tracking = [
                tuple(
                    getattr(family, name)(
                        requested[2 * i], stage, len(family.windows) - 1
                    ).value
                    for name in ("track_class", "track_mass", "track_support")
                )
                for i in range(count)
            ]
            values[f"{degree}/{stage}"] = {"geometry": value, "tracking": tracking}
    return json.loads(canonical_json(values)), json.loads(canonical_json(metadata))


def run_worker_case(plan, case, route, scope, baseline_root):
    if route in {"gudhi", "edge_collapse", "rips_persistence"}:

        def canonical_json(value):
            return json.dumps(
                value, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
    else:
        from homology_operator.result import canonical_json
    from oracle.simplicial import validate_manifest, build_windows
    from oracle.gudhi_oracle import (
        gudhi_topology,
        interval_statistics,
        normalize_pairs,
        secondary_topology,
    )

    began, phases = perf_counter(), {}
    stamp = began

    def done(name):
        nonlocal stamp
        now = perf_counter()
        phases[name], stamp = now - stamp, now

    manifest = plan["inputs"].get(case["input_id"])
    if manifest is None:
        return {
            "completed": False,
            "state": "NotApplicable",
            "reason": "no explicit simplicial adapter; input not replaced",
        }
    validate_manifest(manifest)
    done("frontend_manifest_validation")
    if route in {"gudhi", "edge_collapse", "rips_persistence"}:
        if route != "gudhi" and scope == "warm":
            return {
                "completed": False,
                "state": "NotApplicable",
                "reason": "secondary API does not expose the same stored warm PH object",
            }
        if route == "gudhi":
            from oracle.simplicial import build_simplex_tree

            tree = build_simplex_tree(manifest)
            topology = gudhi_topology(manifest, tree)
        else:
            topology = secondary_topology(manifest, route)
        done("explicit_frontend_ph_and_input_audit")
        if topology["state"] != "Computed":
            return {
                "completed": False,
                "state": topology["state"],
                "details": topology,
                "phases_seconds": phases,
            }

        # Warm is an existing PH object's requested interval readout; no reconstruction.
        def read():
            if scope == "cold" or route != "gudhi":
                return topology["topology"]
            pairs = [
                (k, interval)
                for k in manifest["requested_degrees"]
                for interval in tree.persistence_intervals_in_dimension(k)
            ]
            return interval_statistics(
                normalize_pairs(
                    pairs, manifest["requested_degrees"], len(manifest["scales"])
                ),
                len(manifest["scales"]),
            )

        statuses, details, families = (
            [{"status": "Computed", "certificate_level": "F2Topology"}],
            [topology.get("options", {})],
            None,
        )
    elif scope == "cold" and case["workload"] != "Topology":
        records = []
        for degree, slices in build_windows(manifest).items():
            joint_manifest, joint_request = joint_case(
                slices, manifest["scales"], case["solver"], case["query_count"]
            )
            joint_request["resource_limits"] = case["resource_limits"]
            joint_request["requested_certificate_level"] = case[
                "requested_certificate_level"
            ]
            records.append(
                {
                    "degree": degree,
                    **run_pipeline(joint_manifest, joint_request, route, baseline_root),
                }
            )
        done("joint_complete_pipeline_with_disjoint_nested_phase_records")
        completed = all(r["completed"] for r in records)
        if not completed:
            states = {s["status"] for r in records for s in r["statuses"]}
            return {
                "completed": False,
                "state": "ResourceExhausted"
                if "ResourceExhausted" in states
                else "Unavailable"
                if "Unavailable" in states
                else "Failed",
                "records": records,
                "phases_seconds": phases,
            }
        # Separate full requested topology readout: this extra validated construction is charged.
        families, statuses, details = construct_families(manifest, case, route)
        done("full_topology_additional_validated_construction")
        if families is None:
            states = {s["status"] for s in statuses}
            return {
                "completed": False,
                "state": "ResourceExhausted"
                if "ResourceExhausted" in states
                else "Unavailable"
                if "Unavailable" in states
                else "Failed",
                "statuses": statuses,
                "details": json.loads(canonical_json(details)),
                "records": records,
                "phases_seconds": phases,
            }
        topology_value = read_topology(families)
        done("all_requested_topology_readout")
        encoded = canonical_json(
            {
                "joint_hashes": [r["output_hash"] for r in records],
                "topology": topology_value,
            }
        )
        done("output_normalization_hash")
        return {
            "completed": True,
            "state": "Computed",
            "output_hash": sha256(encoded.encode()).hexdigest(),
            "topology_hash": digest(topology_value),
            "records": records,
            "phases_seconds": phases,
            "worker_pipeline_seconds": perf_counter() - began,
        }
    else:
        families, statuses, details = construct_families(manifest, case, route)
        done("conversion_solve_independent_validation_operator_family")
        if families is None:
            states = {s["status"] for s in statuses}
            return {
                "completed": False,
                "state": "ResourceExhausted"
                if "ResourceExhausted" in states
                else "Unavailable"
                if "Unavailable" in states
                else "Failed",
                "statuses": statuses,
                "details": details,
                "phases_seconds": phases,
            }

        def read():
            return read_topology(families)

    topology_value = read()
    done("topology_readout")
    warm_records, workspaces = [], {}
    if scope == "warm":
        for repeat in range(case["warm_repeats"]):
            started = perf_counter()
            topology_value = read()
            semantic = {"topology": topology_value}
            if families is not None:
                semantic["solver_evidence"] = solver_evidence(
                    {"statuses": statuses, "details": details}
                )
            metadata = []
            if families is not None and case["workload"] != "Topology":
                semantic["geometry"], metadata = geometry_value(
                    families, case, route, workspaces
                )
            output_hash = sha256(canonical_json(semantic).encode()).hexdigest()
            warm_records.append(
                {
                    "repeat": repeat,
                    "seconds": perf_counter() - started,
                    "output_hash": output_hash,
                    "topology_hash": digest(topology_value),
                    "details": metadata,
                }
            )
        done("warm_existing_objects_batches_including_first_workspace_preparation")
    encoded = canonical_json({"topology": topology_value, "statuses": statuses})
    done("output_normalization_hash")
    return {
        "completed": True,
        "state": "Computed",
        "output_hash": sha256(encoded.encode()).hexdigest(),
        "topology_hash": digest(topology_value),
        "statuses": statuses,
        "details": json.loads(canonical_json(details)),
        "warm_records": warm_records,
        "phases_seconds": phases,
        "worker_pipeline_seconds": perf_counter() - began,
    }


def worker(args):
    began = perf_counter()
    import tracemalloc

    if (
        sys.getprofile() is not None
        or sys.gettrace() is not None
        or tracemalloc.is_tracing()
    ):
        raise ValueError(
            "profilers, tracing and tracemalloc forbidden in measurement workers"
        )
    plan = json.loads(args.manifest.read_text("utf-8"))
    case = next(c for c in plan["cases"] if c["id"] == args.case)
    source = args.baseline_root if args.route == "r0" else ROOT
    sys.path.insert(0, str(source / "src"))
    loaded_source = None
    if args.route not in {"gudhi", "edge_collapse", "rips_persistence"}:
        import homology_operator

        if (
            Path(homology_operator.__file__).resolve().parent
            != (source / "src/homology_operator").resolve()
        ):
            raise ValueError("worker loaded the wrong production source")
        loaded_source = str(Path(homology_operator.__file__).resolve())
    initialized = perf_counter()
    records = [
        run_worker_case(plan, case, args.route, args.scope, args.baseline_root)
        for _ in range(case["repeats"] if args.scope == "cold" else 1)
    ]
    result = {
        "records": records,
        "loaded_source": loaded_source,
        "source_revision": R0 if args.route == "r0" else CANDIDATE,
        "initialization_seconds": initialized - began,
        "worker_seconds": perf_counter() - began,
    }
    if args.route not in {"gudhi", "edge_collapse", "rips_persistence"}:
        from homology_operator.result import canonical_json

        result = json.loads(canonical_json(result))
    if args.mode == "rss":
        # Record construction and its first JSON allocation are inside the observed historical peak.
        json.dumps(result, allow_nan=False)
        value, method, failure = peak_rss()
        result.update(
            peak_rss_bytes=value,
            rss_method=method,
            rss_failure=failure,
            rss_scope="absolute process peak through report allocation; final output/exit not separately observed",
        )
        result.pop("initialization_seconds")
        result.pop("worker_seconds")
        for record in records:
            record.pop("phases_seconds", None)
            record.pop("worker_pipeline_seconds", None)
            for warm in record.get("warm_records", []):
                warm.pop("seconds", None)
            for nested in record.get("records", []):
                nested.pop("phases_seconds", None)
    return result


def sample_process(command, timeout, env=None):
    began = perf_counter()
    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except subprocess.TimeoutExpired as error:
        return {
            "process_state": "process_timeout",
            "timeout_seconds": timeout,
            "stdout": str(error.stdout or ""),
            "stderr": str(error.stderr or ""),
            "end_to_end_seconds": None,
        }
    except KeyboardInterrupt:
        return {"process_state": "cancelled", "end_to_end_seconds": None}
    elapsed = perf_counter() - began
    try:
        payload = json.loads(process.stdout)
    except (ValueError, TypeError):
        payload = None
    if process.returncode or payload is None:
        state = (
            "process_oom"
            if (payload or {}).get("error_kind") == "MemoryError"
            else "process_killed"
            if process.returncode in {-9, 137}
            else "process_error"
        )
        return {
            "process_state": state,
            "exit_code": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "error": payload,
            "end_to_end_seconds": elapsed,
        }
    return {
        "process_state": "completed",
        "exit_code": 0,
        "result": payload,
        "stderr": process.stderr,
        "end_to_end_seconds": elapsed,
    }


def successful(row):
    if row["process_state"] != "completed":
        return False
    records = row["result"]["records"]
    return bool(records) and all(r["completed"] for r in records)


def output_key(row):
    records = row["result"]["records"]
    hashes = [r["output_hash"] for r in records]
    if row["scope"] == "warm":
        hashes = [w["output_hash"] for r in records for w in r["warm_records"]]
    if not hashes or len(set(hashes)) != 1:
        return None
    evidence = [solver_evidence(r) for r in records]
    if any(e is None for e in evidence):
        return None
    evidence_hashes = [digest(e) for e in evidence]
    if len(set(evidence_hashes)) != 1:
        return None
    return digest({"output_hash": hashes[0], "solver_evidence": evidence[0]})


def solver_evidence(record):
    """Compare actual methods/configuration and certification, not requested labels."""
    from homology_operator.result import canonical_json

    if record.get("records"):
        nested = [solver_evidence(r) for r in record["records"]]
        return nested if all(r is not None for r in nested) else None
    statuses = record.get("statuses")
    details = record.get("details")
    if not statuses or details is None:
        return None
    if all(s["status"] == "Computed" for s in statuses):
        return {"statuses": statuses, "oracle_options": details}
    solutions = details.get("solutions") if isinstance(details, dict) else details
    configs = []
    for solution in solutions or []:
        original = solution.get("solver_config", solution.get("config"))
        config = json.loads(canonical_json(original))
        method = solution.get("method")
        if not config or method is None:
            return None

        # These are representations of the same verified feasible construction.
        def normalize_method(value):
            name = value.removeprefix("Native")
            return "FeasibleSolver" if name == "FactorizedSolver" else name

        config["method"] = normalize_method(config["method"])
        config.pop("matrix_free_output", None)
        config["solver_options"].pop("representation", None)
        configs.append({"method": normalize_method(method), "config": config})
    if len(configs) != len(statuses):
        return None
    return {"statuses": statuses, "actual_solvers": configs}


def metric(row):
    if not successful(row):
        return None
    if row["mode"] == "rss":
        return row["result"].get("peak_rss_bytes")
    if row["scope"] == "cold":
        return row["end_to_end_seconds"]
    return statistics.median(
        w["seconds"] for r in row["result"]["records"] for w in r["warm_records"]
    )


def summarize(plan, rows):
    output = []
    for case in plan["cases"]:
        for scope in ("cold", "warm"):
            for mode in ("timing", "rss"):
                selected = [
                    r
                    for r in rows
                    if r["case"] == case["id"]
                    and r["scope"] == scope
                    and r["mode"] == mode
                ]
                reference = {
                    r["block"]: r for r in selected if r["route"] == "reference"
                }
                gudhi = {r["block"]: r for r in selected if r["route"] == "gudhi"}
                for route in case["routes"]:
                    samples = [r for r in selected if r["route"] == route]
                    values = [metric(r) for r in samples if metric(r) is not None]
                    group = {
                        "case": case["id"],
                        "route": route,
                        "scope": scope,
                        "mode": mode,
                        "samples": len(samples),
                        "successful_samples": len(values),
                        "median": statistics.median(values) if values else None,
                        "iqr": list(
                            statistics.quantiles(values, n=4, method="inclusive")[::2]
                        )
                        if len(values) >= 4
                        else None,
                        "process_states": dict(
                            Counter(r["process_state"] for r in samples)
                        ),
                        "library_states": dict(
                            Counter(
                                record["state"]
                                for r in samples
                                if r["process_state"] == "completed"
                                for record in r["result"]["records"]
                            )
                        ),
                    }
                    for baseline, peers in (("reference", reference), ("gudhi", gudhi)):
                        ratios, mismatches = [], 0
                        for row in samples:
                            peer = peers.get(row["block"])
                            if baseline == "reference" and route in {
                                "gudhi",
                                "edge_collapse",
                                "rips_persistence",
                            }:
                                continue
                            # run_plan marks a semantic discrepancy incomplete. It
                            # still vetoes a ratio, even though it has no metric.
                            if any(
                                record.get("state") == "Mismatch"
                                for sample in (row, peer)
                                if sample is not None
                                for record in sample.get("result", {}).get(
                                    "records", []
                                )
                            ):
                                mismatches += 1
                                continue
                            if peer is None:
                                continue
                            if metric(row) is None or metric(peer) is None:
                                continue
                            if baseline == "reference":
                                compatible = output_key(row) is not None and output_key(
                                    row
                                ) == output_key(peer)
                            else:
                                compatible = {
                                    r["topology_hash"] for r in row["result"]["records"]
                                } == {
                                    r["topology_hash"]
                                    for r in peer["result"]["records"]
                                }
                            if not compatible:
                                mismatches += 1
                            elif metric(peer) > 0 and metric(row) > 0:
                                ratios.append(metric(row) / metric(peer))
                        comparison = {
                            "paired_blocks": len(ratios),
                            "mismatched_blocks": mismatches,
                            "interpretation": "same output/solver/certification ratio"
                            if baseline == "reference"
                            else "same topology ratio"
                            if case["workload"] == "Topology"
                            else "joint outputs / GUDHI PH additional information cost ratio",
                        }
                        if (
                            ratios
                            and mismatches == 0
                            and len(ratios)
                            >= plan["statistics"]["minimum_paired_blocks"]
                        ):
                            comparison.update(paired_interval(ratios, plan["seed"]))
                        else:
                            comparison.update(
                                paired_median_ratio=None, bootstrap_95_interval=None
                            )
                        group[baseline + "_comparison"] = comparison
                    output.append(group)
    return output


def smoke_plan():
    from oracle.simplicial import load_manifests
    from oracle.gudhi_oracle import gudhi_topology

    inputs = {m["id"]: m for m in load_manifests()}
    cases = []
    for identifier, workload, q in (
        ("isolated", "Topology", 0),
        ("ring_repeated_scale", "Joint-basic", 8),
    ):
        cases.append(
            {
                "id": identifier + "/" + workload,
                "input_id": identifier,
                "workload": workload,
                "solver": "FeasibleSolver",
                "requested_certificate_level": "Feasible",
                "query_count": q,
                "resource_limits": {
                    "state_limit": 100000,
                    "wall_time_limit": 20.0,
                    "matrix_entry_limit": 1000000,
                },
                "routes": ["reference", "integrated", "gudhi"],
                "repeats": 2,
                "warm_repeats": 2,
                "expected_topology_hash": digest(
                    gudhi_topology(inputs[identifier])["topology"]
                ),
            }
        )
    failure = deepcopy(cases[0])
    failure.update(id="resource_entries0", routes=["reference", "integrated"])
    failure["resource_limits"]["matrix_entry_limit"] = 0
    cases.append(failure)
    return {
        "schema_version": 1,
        "phase": "smoke",
        "seed": 7304,
        "inputs": inputs,
        "cases": cases,
        "blocks": 1,
        "process_wall_seconds": 180.0,
        "rss_budget_bytes": 2 * 1024**3,
        "rss_budget_policy": "post-run absolute peak assessment, not an OS hard memory limit",
        "statistics": {"minimum_paired_blocks": 10},
        "threads": THREAD_ENV,
    }


def frozen_environment():
    from homology_operator.native import backend_info
    from oracle.gudhi_oracle import environment

    native = backend_info()
    native["binary_sha256"] = (
        sha256(Path(native["extension_path"]).read_bytes()).hexdigest()
        if native["native"] == "Available"
        else None
    )
    helpers = [
        "scripts/benchmark_s5.py",
        "scripts/benchmark_acceptance.py",
        "scripts/benchmark_reference.py",
        "scripts/check_s5_correctness.py",
        "tests/oracle/simplicial.py",
        "tests/oracle/gudhi_oracle.py",
        "pyproject.toml",
        "uv.lock",
    ]
    production = source_hashes()
    production.pop("checkout_head")
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "executable": sys.executable,
        "production": production,
        "gudhi": environment(),
        "native": native,
        "helper_lf_sha256": {
            name: sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in helpers
        },
        "build": {
            "rust": "1.98.1",
            "pyo3": "0.29.3",
            "maturin": "1.15.0",
            "profile": "release",
            "threads": 1,
        },
        "thread_env": THREAD_ENV,
    }


def environment_identity(environment):
    identity = deepcopy(environment)
    identity.pop("executable", None)
    identity.get("native", {}).pop("extension_path", None)
    return identity


def run_plan(plan, path, output, baseline_root, phase, resume=None, cancel_file=None):
    from oracle.simplicial import validate_manifest

    for manifest in plan["inputs"].values():
        validate_manifest(manifest)
    if output.exists():
        raise ValueError("output must be new; existing evidence is never overwritten")
    environment = frozen_environment()
    if phase == "formal":
        if plan.get("phase") != "formal" or environment_identity(
            plan.get("freeze_environment", {})
        ) != environment_identity(environment):
            raise ValueError(
                "formal input/source/build/environment must match its precommitted freeze"
            )
        subprocess.run(
            [
                "git",
                "diff",
                "--exit-code",
                "HEAD",
                "--",
                *environment["helper_lf_sha256"],
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        plan_relative = path.resolve().relative_to(ROOT).as_posix()
        committed_plan = subprocess.check_output(
            ["git", "show", f"HEAD:{plan_relative}"], cwd=ROOT
        )
        if committed_plan.replace(b"\r\n", b"\n") != path.read_bytes().replace(
            b"\r\n", b"\n"
        ):
            raise ValueError(
                "formal manifest must match its already committed frozen bytes"
            )
        if plan["blocks"] < 10:
            raise ValueError("formal requires at least ten independent process blocks")
    # Bind R0 only when requested, and verify its actual Python files against its SHA.
    if any("r0" in case["routes"] for case in plan["cases"]):
        for file in (baseline_root / "src").rglob("*.py"):
            name = file.relative_to(baseline_root).as_posix()
            if file.read_bytes().replace(b"\r\n", b"\n") != subprocess.check_output(
                ["git", "show", f"{R0}:{name}"], cwd=ROOT
            ).replace(b"\r\n", b"\n"):
                raise ValueError("R0 source differs from frozen SHA")
    report = {
        "schema_version": 1,
        "phase": phase,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_hash": digest(plan),
        "environment": environment,
        "command": sys.argv,
        "rows": [],
        "execution_checkout_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "scope": "cold fresh-process entire repetition block; warm existing-object batches; timing and absolute RSS in separate processes",
    }
    if resume:
        previous = json.loads(resume.read_text("utf-8"))
        if (
            previous["plan_hash"] != report["plan_hash"]
            or environment_identity(previous["environment"])
            != environment_identity(environment)
            or previous["phase"] != phase
        ):
            raise ValueError("resume identity differs; do not mix observations")
        report["rows"] = previous["rows"]
        report["resumed_from_sha256"] = sha256(resume.read_bytes()).hexdigest()
    completed = {
        (r["case"], r["route"], r["block"], r["scope"], r["mode"])
        for r in report["rows"]
    }
    schedule = [
        (case, route, block, scope, mode)
        for block in range(plan["blocks"])
        for case in plan["cases"]
        for route in case["routes"]
        for scope in ("cold", "warm")
        for mode in ("timing", "rss")
    ]
    # Fixed seed order is frozen independent of observed timings.
    random.Random(plan["seed"]).shuffle(schedule)
    child_env = {**os.environ, **plan["threads"]}
    for case, route, block, scope, mode in schedule:
        key = (case["id"], route, block, scope, mode)
        if key in completed:
            continue
        if cancel_file is not None and cancel_file.exists():
            report["stop_reason"] = "cancelled between workers"
            checkpoint_json(output, report)
            return report
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            "--manifest",
            str(path.resolve()),
            "--case",
            case["id"],
            "--route",
            route,
            "--scope",
            scope,
            "--mode",
            mode,
            "--baseline-root",
            str(baseline_root.resolve()),
        ]
        sampled = sample_process(command, plan["process_wall_seconds"], child_env)
        row = {
            "case": case["id"],
            "input_id": case["input_id"],
            "input_hash": plan["inputs"].get(case["input_id"], {}).get("input_hash"),
            "route": route,
            "block": block,
            "scope": scope,
            "mode": mode,
            "workload": case["workload"],
            "query_count": case["query_count"],
            "scale_metadata": case.get("scale_metadata"),
            "solver": case["solver"],
            "requested_certificate_level": case["requested_certificate_level"],
            "resource_limits": case["resource_limits"],
            **sampled,
        }
        if sampled["process_state"] == "completed":
            for record in sampled["result"]["records"]:
                if (
                    record["completed"]
                    and record["topology_hash"] != case["expected_topology_hash"]
                ):
                    record["completed"], record["state"] = False, "Mismatch"
            if successful(row) and output_key(row) is None:
                for record in sampled["result"]["records"]:
                    record["completed"], record["state"] = False, "Mismatch"
            if mode == "rss":
                peak = sampled["result"].get("peak_rss_bytes")
                row["rss_budget_exceeded"] = (
                    None if peak is None else peak > plan["rss_budget_bytes"]
                )
            elif scope == "cold":
                pipeline = sum(
                    r.get("worker_pipeline_seconds", 0)
                    for r in sampled["result"]["records"]
                )
                row["unallocated_seconds"] = (
                    sampled["end_to_end_seconds"]
                    - sampled["result"]["initialization_seconds"]
                    - pipeline
                )
        report["rows"].append(row)
        checkpoint_json(output, report)
        print(
            f"{len(report['rows'])}/{len(schedule)} {case['id']} {route} {scope}/{mode}: {sampled['process_state']}",
            flush=True,
        )
        if sampled["process_state"] == "cancelled":
            report["stop_reason"] = "cancelled active worker"
            break
    report["summary"] = summarize(plan, report["rows"])
    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    checkpoint_json(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--prepare-smoke", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--phase", choices=("smoke", "pilot", "formal"), default="smoke"
    )
    parser.add_argument(
        "--baseline-root", type=Path, default=ROOT / ".task-artifacts/s5-r0/source"
    )
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--cancel-file", type=Path)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--case")
    parser.add_argument("--route")
    parser.add_argument("--scope", choices=("cold", "warm"), default="cold")
    parser.add_argument("--mode", choices=("timing", "rss"), default="timing")
    args = parser.parse_args()
    if args.prepare_smoke:
        with args.prepare_smoke.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(smoke_plan(), stream, indent=2)
            stream.write("\n")
    elif args.worker:
        try:
            result = worker(args)
        except Exception as error:
            print(
                json.dumps(
                    {
                        "error_kind": type(error).__name__,
                        "error": str(error),
                        "traceback": traceback.format_exc(),
                    }
                )
            )
            raise SystemExit(1)
        print(json.dumps(result, allow_nan=False))
    else:
        if args.output is None or args.manifest is None:
            parser.error("provide manifest and a new output path")
        run_plan(
            json.loads(args.manifest.read_text("utf-8")),
            args.manifest,
            args.output,
            args.baseline_root,
            args.phase,
            args.resume_from,
            args.cancel_file,
        )


if __name__ == "__main__":
    main()
