"""S5-03 three-way finite corpus, same-P joint audit and mismatch preservation."""

import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from itertools import combinations
import json
from math import dist
from pathlib import Path
import random
import subprocess
import sys

from benchmark_acceptance import CANDIDATE, R0, run_pipeline

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))


def make_corpus(seed=20261003, random_cases=64):
    from oracle.simplicial import (
        digest,
        freeze_manifest,
        load_manifests,
        synthetic_manifest,
    )
    from oracle.gudhi_oracle import flag_cycle_manifest

    manifests = deepcopy(load_manifests()) + [flag_cycle_manifest()]
    disconnected = [((v,), 0) for v in range(6)]
    disconnected += [
        (s, 1) for vertices in ((0, 1, 2), (3, 4, 5)) for s in combinations(vertices, 2)
    ]
    disconnected += [((0, 1, 2), 2)]
    manifests.append(
        synthetic_manifest("two_classes_one_survivor", disconnected, [0, 1, 1], q=1)
    )
    base = next(m for m in manifests if m["id"] == "ring_repeated_scale")
    reordered = deepcopy(base)
    reordered.update(id="ring_reordered", coordinate_order="reverse_lexicographic")
    manifests.append(freeze_manifest(reordered))
    for arithmetic in ("ExactInteger", "ExactRational", "FloatingPoint"):
        weighted = deepcopy(base)
        weighted["id"] = "ring_weights_" + arithmetic
        weighted["weight_policy"]["arithmetic"] = arithmetic
        weighted["weight_policy"]["semantics_by_degree"] = {
            str(k): "abstract_positive_cost" for k in range(3)
        }
        weighted["source"]["payload"]["weight_transform"] = arithmetic
        weighted["source"]["sha256"] = digest(weighted["source"]["payload"])
        for i, record in enumerate(weighted["simplices"]):
            record["weight"] = (
                i + 2
                if arithmetic == "ExactInteger"
                else {
                    "numerator": i + 2,
                    "denominator": 2 * i + 3,
                }
                if arithmetic == "ExactRational"
                else 0.5 + i / 10
            )
        manifests.append(freeze_manifest(weighted))
    euclidean = deepcopy(base)
    euclidean["id"] = "ring_euclidean"
    coordinates = [[0, 0], [2, 0], [1, 1]]
    for v in euclidean["vertices"]:
        v["coordinates"] = coordinates[v["id"]]
    euclidean["source"]["payload"]["coordinates"] = coordinates
    euclidean["source"]["payload"]["weight_formula"] = (
        "vertices=1, edge=Euclidean length, triangle=area"
    )
    euclidean["source"]["sha256"] = digest(euclidean["source"]["payload"])
    euclidean["weight_policy"] = {
        "arithmetic": "FloatingPoint",
        "semantics_by_degree": {
            "0": "unit",
            "1": "euclidean_length",
            "2": "euclidean_area",
        },
        "units_by_degree": {"0": None, "1": "length", "2": "length^2"},
    }
    for r in euclidean["simplices"]:
        s = r["vertices"]
        r["weight"] = dist(coordinates[s[0]], coordinates[s[1]]) if len(s) == 2 else 1.0
    manifests.append(freeze_manifest(euclidean))
    rng = random.Random(seed)
    for index in range(random_cases):
        n = rng.randrange(3, 6)
        births = [((v,), 0) for v in range(n)]
        edges = {
            s: rng.randrange(3) for s in combinations(range(n), 2) if rng.random() < 0.7
        }
        births += list(edges.items())
        for triangle in combinations(range(n), 3):
            faces = tuple(combinations(triangle, 2))
            if all(edge in edges for edge in faces) and rng.random() < 0.5:
                births.append(
                    (triangle, rng.randrange(max(edges[e] for e in faces), 4))
                )
        manifest = synthetic_manifest(
            f"random/{seed}/{index}", births, [0, 1, 1, 2], q=1
        )
        manifest["source"]["payload"].update(
            seed=seed, case_index=index, generator="closed random 2-complex v1"
        )
        manifest["source"]["sha256"] = digest(manifest["source"]["payload"])
        manifests.append(freeze_manifest(manifest))
    return {
        "schema_version": 1,
        "seed": seed,
        "random_cases": random_cases,
        "manifests": manifests,
        "corpus_hash": digest(manifests),
    }


def load_corpus(path):
    from oracle.simplicial import digest, validate_manifest

    data = json.loads(Path(path).read_text("utf-8"))
    for manifest in data["manifests"]:
        validate_manifest(manifest)
    if digest(data["manifests"]) != data["corpus_hash"] or len(
        {m["id"] for m in data["manifests"]}
    ) != len(data["manifests"]):
        raise ValueError("correctness corpus hash or unique identifiers mismatch")
    return data


def joint_case(slices, scales, method="FeasibleSolver", query_count=8):
    """Use the already accepted S4 full joint pipeline, preserving all costs."""
    from homology_operator import ResourceLimits

    windows, queries = {}, []
    for stage, window in enumerate(slices):
        windows[str(stage)] = window.to_dict()
        basis = window.A.kernel_basis()
        cycles = [(0,) * window.n] + list(basis)
        for i in range(query_count):
            queries.append(
                {
                    "stage": stage,
                    "z": cycles[i % len(cycles)],
                    "y": cycles[(i + 1) % len(cycles)],
                }
            )
    manifest = {
        "windows": windows,
        "candidate": {"revision": CANDIDATE},
        "baseline": {"revision": R0},
    }
    case = {
        "fixture_ids": list(windows),
        "scales": scales,
        "solver": method,
        "resource_limits": vars(
            ResourceLimits(state_limit=100000, wall_time_limit=20.0)
        ),
        "requested_certificate_level": "Feasible"
        if method == "FeasibleSolver"
        else "ExactOptimal"
        if method == "ExhaustiveExactSolver"
        else "CertifiedInterval",
        "input_structure": "GeneralChainWindow",
        "matrix_free_output": False,
        "queries": queries,
    }
    return manifest, case


def check_manifest(manifest, require_native=False, certified=False):
    from collections.abc import Mapping
    from homology_operator.native import backend_info
    from homology_operator.chain import action_data
    from homology_operator.result import canonical_json
    from oracle import reference
    from oracle.gudhi_oracle import build_families, gudhi_topology, operator_topology
    from oracle.simplicial import audit_inputs, build_windows, number

    def mismatch(message, **results):
        error = ValueError(message)
        error.results = json.loads(
            json.dumps(
                results,
                default=lambda value: dict(value)
                if isinstance(value, Mapping)
                else json.loads(canonical_json(value)),
                allow_nan=False,
            )
        )
        error.failure_category = message
        raise error

    audit = audit_inputs(manifest)
    expected = gudhi_topology(manifest)["topology"]
    reference_families = build_families(manifest)
    reference_topology = operator_topology(reference_families)
    if expected != reference_topology:
        mismatch(
            "GUDHI/reference topology mismatch",
            gudhi=expected,
            reference=reference_topology,
            reference_snapshots={
                str(degree): family.to_result().to_json()
                for degree, family in reference_families.items()
            },
        )
    native_available = backend_info()["native"] == "Available"
    if require_native and not native_available:
        raise RuntimeError("native unavailable for required three-way correctness")
    native_families = (
        build_families(manifest, "NativeFactorizedSolver", matrix_free_output=True)
        if native_available
        else None
    )
    if native_families is not None:
        native_topology = operator_topology(native_families)
        if native_topology != expected:
            mismatch(
                "GUDHI/native topology mismatch",
                gudhi=expected,
                native=native_topology,
                native_snapshots={
                    str(degree): family.to_result().to_json()
                    for degree, family in native_families.items()
                },
            )

    for families in (reference_families, native_families):
        if families is None:
            continue
        for family in families.values():
            for i, op in enumerate(family.operators):
                # Independent chain/coset enumeration imports no production algebra.
                if op.window.n <= 10:
                    columns = tuple(
                        sum(
                            bit << row
                            for row, bit in enumerate(
                                op.project(
                                    tuple(int(j == col) for j in range(op.window.n))
                                )
                            )
                        )
                        for col in range(op.window.n)
                    )
                    if not reference.verify_projection(op.window.to_dict(), columns):
                        mismatch(
                            "independent full-chain/cycle projection mismatch",
                            degree=op.window.k,
                            stage=i,
                            window=op.window.to_dict(),
                            projection=action_data(op.P),
                            identity=op.identity,
                            columns=columns,
                            source_revision=CANDIDATE,
                        )
                for j in range(i, len(family.windows)):
                    for k in range(j, len(family.windows)):
                        for cycle in op.window.A.kernel_basis():
                            intermediate = family.track_class(cycle, i, j).value
                            direct = family.track_class(cycle, i, k)
                            composed = family.track_class(intermediate, j, k)
                            if direct.value != composed.value:
                                mismatch(
                                    "transport composition mismatch",
                                    stages=[i, j, k],
                                    cycle=cycle,
                                    intermediate=intermediate,
                                    direct=direct.to_dict(),
                                    composed=composed.to_dict(),
                                    family_snapshot=family.to_result().to_json(),
                                    source_revision=CANDIDATE,
                                )
    comparisons = []
    for k, slices in build_windows(manifest).items():
        for method in (
            ("FeasibleSolver", "ExhaustiveExactSolver", "GreedyCertifiedSolver")
            if certified and manifest["weight_policy"]["arithmetic"] != "FloatingPoint"
            else ("FeasibleSolver",)
        ):
            joint_manifest, case = joint_case(
                slices, [number(x) for x in manifest["scales"]], method
            )
            reference_capture, native_capture = {}, {}
            try:
                ref = run_pipeline(
                    joint_manifest, case, "reference", ROOT, capture=reference_capture
                )
                native = (
                    run_pipeline(
                        joint_manifest, case, "integrated", ROOT, capture=native_capture
                    )
                    if native_available
                    else None
                )
            except (ValueError, AssertionError) as error:
                mismatch(
                    f"joint pipeline failure: H{k}/{method}",
                    error=str(error),
                    reference_capture=reference_capture,
                    native_capture=native_capture,
                )
            comparable = ref["completed"] and native is not None and native["completed"]
            if comparable and ref["output_hash"] != native["output_hash"]:
                mismatch(
                    f"native/reference full action/geometry/certification/recovery mismatch: H{k}/{method}",
                    reference=ref,
                    native=native,
                    reference_capture=reference_capture,
                    native_capture=native_capture,
                )
            comparisons.append(
                {"degree": k, "solver": method, "reference": ref, "native": native}
            )
    incomplete = [
        result
        for comparison in comparisons
        for result in (comparison["reference"], comparison["native"])
        if result is None or not result["completed"]
    ]
    states = {
        status["status"]
        for result in incomplete
        if result is not None
        for status in result["statuses"]
    }
    interrupted = any(
        "cancelled" in str(result.get("details", {})).lower()
        for result in incomplete
        if result is not None
    )
    state = (
        "Passed"
        if not incomplete
        else "Interrupted"
        if interrupted or states & {"Interrupted", "Cancelled"}
        else "ResourceExhausted"
        if "ResourceExhausted" in states
        else "Unavailable"
        if not native_available or "Unavailable" in states
        else "Failed"
    )
    return {
        "id": manifest["id"],
        "input_hash": manifest["input_hash"],
        "state": state,
        "native_state": "Compared" if state == "Passed" else state,
        "input_audit": audit,
        "topology": expected,
        "joint_comparisons": comparisons,
    }


def minimize_manifest(manifest, mismatch):
    """Deletion-minimize a reproducible mismatch; never claim global minimality."""
    from oracle.simplicial import freeze_manifest

    current = deepcopy(manifest)
    changed = True
    while changed:
        changed = False
        for record in sorted(current["simplices"], key=lambda r: -len(r["vertices"])):
            simplex = set(record["vertices"])
            if any(simplex < set(r["vertices"]) for r in current["simplices"]):
                continue
            trial = deepcopy(current)
            trial["simplices"].remove(record)
            if len(simplex) == 1:
                trial["vertices"] = [
                    v for v in trial["vertices"] if v["id"] not in simplex
                ]
            trial = freeze_manifest(trial)
            if mismatch(trial):
                current, changed = trial, True
                break
    return current


def archive_mismatch(directory, manifest, evaluate, original_result=None):
    from oracle.simplicial import digest

    original = evaluate(manifest) if original_result is None else original_result
    if original["state"] != "Mismatch":
        raise ValueError("only an actual mismatch may be archived")
    category = original.get("failure_category", original.get("error", "Mismatch"))
    original_record = {
        "classification": "Mismatch",
        "failure_category": category,
        "original_manifest": manifest,
        "original_result": original,
    }
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    original_path = directory / (digest(original_record) + ".original.json")
    with original_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(original_record, stream, indent=2, allow_nan=False)
        stream.write("\n")

    def mismatches(candidate):
        result = evaluate(candidate)
        return (
            result["state"] == "Mismatch"
            and result.get("failure_category", result.get("error", "Mismatch"))
            == category
        )

    minimized = minimize_manifest(manifest, mismatches)
    record = {
        "classification": "Mismatch",
        "failure_category": category,
        "original_archive": original_path.name,
        "original_result": original,
        "original_manifest": manifest,
        "minimal_manifest": minimized,
        "results": evaluate(minimized),
        "minimality": "deletion-minimal among maximal-simplex removals, not global",
    }
    path = directory / (digest(record) + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    return path


def source_hashes():
    hashes = {}
    for directory, suffix in (("src", "*.py"), ("native/src", "*.rs")):
        for path in sorted((ROOT / directory).rglob(suffix)):
            relative = path.relative_to(ROOT).as_posix()
            data = path.read_bytes().replace(b"\r\n", b"\n")
            frozen = subprocess.check_output(
                ["git", "show", f"{CANDIDATE}:{relative}"], cwd=ROOT
            ).replace(b"\r\n", b"\n")
            if data != frozen:
                raise ValueError(
                    f"production source differs from S4 frozen SHA: {relative}"
                )
            hashes[relative] = sha256(data).hexdigest()
    helper_paths = [
        ROOT / name
        for name in (
            "scripts/check_s5_correctness.py",
            "scripts/benchmark_acceptance.py",
            "tests/oracle/simplicial.py",
            "tests/oracle/gudhi_oracle.py",
            "uv.lock",
            "pyproject.toml",
        )
    ]
    helper_hashes = {
        p.relative_to(ROOT).as_posix(): sha256(
            p.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for p in helper_paths
    }
    return {
        "helper_lf_sha256": helper_hashes,
        "production_sha": CANDIDATE,
        "lf_sha256": hashes,
        "checkout_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
    }


def main():
    from oracle.simplicial import digest
    from oracle.gudhi_oracle import environment
    from homology_operator.native import backend_info

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path)
    parser.add_argument(
        "--corpus", type=Path, default=ROOT / "tests/fixtures/s5_correctness.json"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        with args.freeze.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(make_corpus(), stream, indent=2)
            stream.write("\n")
        return
    if args.output is None or args.output.exists():
        parser.error("provide a new output path")
    corpus, rows = load_corpus(args.corpus), []

    def evaluate(manifest):
        try:
            return check_manifest(
                manifest,
                args.require_native,
                certified=not manifest["id"].startswith("random/"),
            )
        except (ValueError, AssertionError) as error:
            return {
                "state": "Mismatch",
                "error": str(error),
                "failure_category": getattr(error, "failure_category", str(error)),
                "results": getattr(error, "results", None),
            }

    for manifest in corpus["manifests"]:
        row = evaluate(manifest)
        if row["state"] == "Mismatch":
            row["archive"] = str(
                archive_mismatch(
                    args.output.parent / "s5-counterexamples", manifest, evaluate, row
                )
            )
        rows.append(row)
        print(f"{manifest['id']}: {row['state']}", file=sys.stderr, flush=True)
    result = {
        "schema_version": 1,
        "source": source_hashes(),
        "environment": environment(),
        "native": {
            **backend_info(),
            "binary_sha256": sha256(
                Path(backend_info()["extension_path"]).read_bytes()
            ).hexdigest()
            if backend_info()["native"] == "Available"
            else None,
        },
        "corpus_hash": corpus["corpus_hash"],
        "seed": corpus["seed"],
        "summary": dict(Counter(r["state"] for r in rows)),
        "native_summary": dict(Counter(r.get("native_state", "NotRun") for r in rows)),
        "general_chain_gudhi": {
            "state": "NotApplicable",
            "reason": "legacy AD=0 windows are verified in existing independent algebra regression; no input replacement",
        },
        "rows": rows,
    }
    result["report_hash"] = digest(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    if any(row["state"] != "Passed" for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
