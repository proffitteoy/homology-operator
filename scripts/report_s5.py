"""Audit frozen S5 evidence and deterministically rebuild every statistical table."""

import argparse
from collections import Counter, defaultdict
import csv
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import statistics
import subprocess

from benchmark_s5 import (
    CANDIDATE,
    ROOT,
    digest,
    environment_identity,
    metric,
    output_key,
    sampling_fingerprint,
    successful,
    summarize,
)


def read_raw(path):
    data = Path(path).read_bytes()
    if str(path).endswith(".gz"):
        data = gzip.decompress(data)
    return json.loads(data), sha256(data).hexdigest()


def audit(plan, report):
    if digest(plan) != report["plan_hash"]:
        raise ValueError("raw evidence belongs to another manifest")
    if environment_identity(plan["freeze_environment"]) != environment_identity(
        report["environment"]
    ):
        raise ValueError("raw source/build/environment differs from the freeze")
    revision = report["execution_checkout_sha"]
    for name, expected in report["environment"]["helper_lf_sha256"].items():
        source = subprocess.check_output(
            ["git", "show", f"{revision}:{name}"], cwd=ROOT
        )
        if sha256(source.replace(b"\r\n", b"\n")).hexdigest() != expected:
            raise ValueError(f"historical measured helper differs: {name}")
    generator = subprocess.check_output(
        ["git", "show", f"{revision}:scripts/prepare_s5_performance.py"], cwd=ROOT
    )
    if (
        sha256(generator.replace(b"\r\n", b"\n")).hexdigest()
        != report["environment"]["generator_lf_sha256"]
    ):
        raise ValueError("frozen input generator differs")
    measured_source = subprocess.check_output(
        ["git", "show", f"{revision}:scripts/benchmark_s5.py"], cwd=ROOT, text=True
    )
    if (
        sampling_fingerprint(measured_source)
        != plan["freeze_notes"]["measured_worker_ast_sha256"]
    ):
        raise ValueError("measured worker differs from predeclared pilot")
    production = report["environment"]["production"]
    if production["production_sha"] != CANDIDATE:
        raise ValueError("production source is not frozen S4")
    for name, expected in production["lf_sha256"].items():
        source = subprocess.check_output(
            ["git", "show", f"{CANDIDATE}:{name}"], cwd=ROOT
        )
        if sha256(source.replace(b"\r\n", b"\n")).hexdigest() != expected:
            raise ValueError(f"frozen production hash differs: {name}")
    cases = {case["id"]: case for case in plan["cases"]}
    expected_keys = {
        (case["id"], route, block, scope, mode)
        for case in plan["cases"]
        for route in case["routes"]
        for block in range(plan["blocks"])
        for scope in ("cold", "warm")
        for mode in ("timing", "rss")
    }
    seen = set()
    for row in report["rows"]:
        key = (row["case"], row["route"], row["block"], row["scope"], row["mode"])
        if key in seen or key not in expected_keys:
            raise ValueError("duplicate or undeclared observation")
        seen.add(key)
        case = cases[row["case"]]
        expected_input = plan["inputs"].get(case["input_id"], {}).get(
            "input_hash"
        ) or case.get("input_hash")
        if row["input_hash"] != expected_input:
            raise ValueError("sample input identity differs")
        if row["process_state"] != "completed":
            continue
        records = row["result"]["records"]
        if len(records) != (case["repeats"] if row["scope"] == "cold" else 1):
            raise ValueError("sample repetition count differs")
        for record in records:
            if (
                record["completed"]
                and record["topology_hash"] != case["expected_topology_hash"]
            ):
                raise ValueError("completed sample has a topology mismatch")
        if successful(row) and output_key(row) is None:
            raise ValueError(
                "completed sample lacks stable output/actual solver evidence"
            )
    if seen != expected_keys:
        raise ValueError("formal schedule is incomplete")
    groups = summarize(plan, report["rows"])
    return {
        "process_states": dict(Counter(row["process_state"] for row in report["rows"])),
        "library_states": dict(
            Counter(
                record["state"]
                for row in report["rows"]
                if row["process_state"] == "completed"
                for record in row["result"]["records"]
            )
        ),
        "successful_process_samples": sum(successful(row) for row in report["rows"]),
        "rss_missing": sum(
            row["mode"] == "rss" and successful(row) and metric(row) is None
            for row in report["rows"]
        ),
        "rss_budget_exceeded": sum(
            row.get("rss_budget_exceeded") is True for row in report["rows"]
        ),
        "summary": groups,
        "original_summary_changed": report["summary"] != groups,
        "statistics_source": "review-corrected aggregator; raw worker and original summary are unchanged",
    }


def csv_bytes(groups, plan):
    stream = io.StringIO(newline="")
    fields = [
        "case",
        "route",
        "scope",
        "mode",
        "samples",
        "successful_samples",
        "median",
        "q1",
        "q3",
        "unit",
        "workload",
        "query_count",
        "cold_repeats",
        "warm_repeats",
        "process_states",
        "library_states",
    ]
    for baseline in ("reference", "gudhi"):
        fields += [
            baseline + "_" + key
            for key in (
                "paired_blocks",
                "mismatched_blocks",
                "paired_median_ratio",
                "ci_low",
                "ci_high",
                "interpretation",
            )
        ]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    cases = {case["id"]: case for case in plan["cases"]}
    for group in groups:
        row = {key: group[key] for key in fields[:7]}
        row.update(
            q1=(group["iqr"] or [None, None])[0], q3=(group["iqr"] or [None, None])[1]
        )
        case = cases[group["case"]]
        row.update(
            unit="bytes" if group["mode"] == "rss" else "seconds",
            workload=case["workload"],
            query_count=case["query_count"],
            cold_repeats=case["repeats"],
            warm_repeats=case["warm_repeats"],
        )
        for key in ("process_states", "library_states"):
            row[key] = json.dumps(group[key], sort_keys=True, separators=(",", ":"))
        for baseline in ("reference", "gudhi"):
            comparison = group[baseline + "_comparison"]
            for key in (
                "paired_blocks",
                "mismatched_blocks",
                "paired_median_ratio",
                "interpretation",
            ):
                row[baseline + "_" + key] = comparison[key]
            row[baseline + "_ci_low"], row[baseline + "_ci_high"] = comparison.get(
                "bootstrap_95_interval"
            ) or [None, None]
        writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def phase_rows(rows):
    values = defaultdict(list)
    for row in rows:
        if row["mode"] != "timing" or not successful(row):
            continue
        records = row["result"]["records"]
        for name in {name for r in records for name in r.get("phases_seconds", {})}:
            values[row["case"], row["route"], row["scope"], "outer", name].append(
                sum(r.get("phases_seconds", {}).get(name, 0) for r in records)
            )
        for degree in {
            r["degree"] for record in records for r in record.get("records", [])
        }:
            nested = [
                r
                for record in records
                for r in record.get("records", [])
                if r["degree"] == degree
            ]
            for name in {name for r in nested for name in r.get("phases_seconds", {})}:
                values[
                    row["case"], row["route"], row["scope"], f"nested/H{degree}", name
                ].append(sum(r.get("phases_seconds", {}).get(name, 0) for r in nested))
        for name in (
            "initialization_seconds",
            "unallocated_seconds",
            "end_to_end_seconds",
        ):
            value = row.get(name, row["result"].get(name))
            if value is not None:
                values[row["case"], row["route"], row["scope"], "process", name].append(
                    value
                )
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "case",
            "route",
            "scope",
            "level",
            "phase",
            "blocks",
            "median_seconds",
            "q1_seconds",
            "q3_seconds",
        ]
    )
    for key, measured in sorted(values.items()):
        q1, q3 = (
            statistics.quantiles(measured, n=4, method="inclusive")[::2]
            if len(measured) >= 4
            else [None, None]
        )
        writer.writerow([*key, len(measured), statistics.median(measured), q1, q3])
    return stream.getvalue().encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw", type=Path, default=ROOT / "benchmarks/s5_performance_formal.json.gz"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "benchmarks/s5_performance_frozen_manifest.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    raw, raw_hash = read_raw(args.raw)
    plan = json.loads(args.manifest.read_text("utf-8"))
    result = audit(plan, raw)
    result.update(
        raw_decompressed_sha256=raw_hash,
        raw_file_sha256=sha256(args.raw.read_bytes()).hexdigest(),
        manifest_lf_sha256=sha256(
            args.manifest.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        measured_checkout_sha=raw["execution_checkout_sha"],
        environment=raw["environment"],
    )
    tables = {
        "s5_statistics.csv": csv_bytes(result.pop("summary"), plan),
        "s5_phases.csv": phase_rows(raw["rows"]),
    }
    result["table_sha256"] = {
        name: sha256(data).hexdigest() for name, data in tables.items()
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        **tables,
        "s5_report_audit.json": (
            json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        ).encode("utf-8"),
    }
    if any((args.output_dir / name).exists() for name in outputs):
        raise ValueError("output artifacts must be new; evidence is never overwritten")
    for name, data in outputs.items():
        with (args.output_dir / name).open("xb") as stream:
            stream.write(data)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "process_states",
                    "library_states",
                    "successful_process_samples",
                    "rss_missing",
                    "rss_budget_exceeded",
                    "original_summary_changed",
                    "table_sha256",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
