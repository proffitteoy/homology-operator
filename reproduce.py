"""Verify, summarize, or rerun the immutable PR #110 cost archive (stdlib only)."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import platform
from statistics import median
import subprocess
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parent
CASES = ("T1", "T2", "T3", "T4", "T5", "fan8", "fan12", "fan16")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def source_files(repo, revision, directory):
    paths = git(repo, "ls-tree", "-r", "--name-only", revision, directory)
    return paths.decode().splitlines()


def verify(repo):
    manifest = json.loads((ROOT / "manifest.json").read_text("utf-8"))
    for name, expected in manifest["sha256"].items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Archive hash mismatch: {name}")
    expected_sources = {}
    for variant, revision in manifest["sources"].items():
        expected_sources[variant] = {
            Path(path).name: sha256(git(repo, "show", f"{revision}:{path}")).hexdigest()
            for path in source_files(repo, revision, "src/homology_operator")
            if path.endswith(".py")
        }
    fixture = git(
        repo,
        "show",
        f"{manifest['sources']['after']}:tests/fixtures/geometry_queries.json",
    )
    rows = [
        json.loads(line)
        for line in (ROOT / "geometry-cost.jsonl").read_text("utf-8").splitlines()
    ]
    matched = [
        row for row in rows if row["case"] in CASES and row["mode"] in ("cold", "warm")
    ]
    if len(rows) != 102 or len(matched) != 96:
        raise ValueError("Expected 96 matched samples and six domain controls")
    pairs = defaultdict(dict)
    for row in rows:
        if row["source_hashes"] != expected_sources[row["variant"]]:
            raise ValueError("Recorded module hashes differ from the pinned Git source")
        if row["fixture_sha256"] != sha256(fixture).hexdigest():
            raise ValueError("Recorded fixture hash differs from the pinned fixture")
        harness = (
            "geometry_cost.py" if row["case"] == "fan20" else "geometry_cost_matched.py"
        )
        if row["harness_sha256"] != manifest["sha256"][f"harness/{harness}"]:
            raise ValueError("Recorded harness hash differs from the original bytes")
        key = (row["case"], row["mode"], row["sample"])
        if row["variant"] in pairs[key]:
            raise ValueError(f"Duplicate sample: {key}")
        pairs[key][row["variant"]] = row
    expected_keys = {
        (case, mode, sample)
        for case in CASES
        for mode in ("cold", "warm")
        for sample in range(3)
    }
    expected_keys.update(
        {("T2", "exhausted", 0), ("T2", "unsupported", 0), ("fan20", "cold", 0)}
    )
    if set(pairs) != expected_keys or any(
        set(pair) != {"before", "after"} for pair in pairs.values()
    ):
        raise ValueError("Missing or unexpected sample pair")
    for key, pair in pairs.items():
        if (
            key[0] in CASES
            and key[1] in ("cold", "warm")
            and pair["before"]["output"] != pair["after"]["output"]
        ):
            raise ValueError(f"Five-query output mismatch: {key}")
    return manifest, matched


def summarize(rows):
    print(
        "| Input | Cold before / after ms | Cold ratio | Warm before / after ms | Warm ratio | Peak before / after MiB |"
    )
    print("| --- | --- | --- | --- | --- | --- |")
    for case in CASES:
        values = {}
        for mode in ("cold", "warm"):
            for variant in ("before", "after"):
                selected = [
                    row
                    for row in rows
                    if (row["case"], row["mode"], row["variant"])
                    == (case, mode, variant)
                ]
                values[mode, variant] = (
                    median(row["total_seconds"] for row in selected) * 1000
                )
        peaks = [
            max(
                row["process_peak_working_set_bytes"]
                for row in rows
                if row["case"] == case and row["variant"] == variant
            )
            / 2**20
            for variant in ("before", "after")
        ]
        cold_before, cold_after = values["cold", "before"], values["cold", "after"]
        warm_before, warm_after = values["warm", "before"], values["warm", "after"]
        print(
            f"| {case} | {cold_before:.2f} / {cold_after:.2f} | {cold_before / cold_after:.3f} | {warm_before:.2f} / {warm_after:.2f} | {warm_before / warm_after:.3f} | {peaks[0]:.2f} / {peaks[1]:.2f} |"
        )


def export_sources(repo, manifest):
    for variant, revision in manifest["sources"].items():
        for path in source_files(repo, revision, "src/homology_operator"):
            target = ROOT / variant / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(git(repo, "show", f"{revision}:{path}"))
    revision = manifest["sources"]["after"]
    for path in source_files(repo, revision, "tests"):
        target = ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git(repo, "show", f"{revision}:{path}"))


def run(repo, manifest, options):
    if platform.system() != "Windows":
        raise RuntimeError(
            "The unchanged historical harness requires Windows GetProcessMemoryInfo; verify/summarize also work on other platforms"
        )
    if options.output.resolve() == (ROOT / "geometry-cost.jsonl").resolve():
        raise ValueError("Refusing to replace the frozen measurements")
    export_sources(repo, manifest)
    # Exclusive creation also protects earlier replay output from accidental replacement.
    with options.output.open("x", encoding="utf-8", newline="\n") as stream:

        def sample(case, mode, repetition, variants, harness):
            pair = []
            for variant in variants:
                started = perf_counter()
                raw = subprocess.check_output(
                    [
                        sys.executable,
                        str(ROOT / "harness" / harness),
                        "--source",
                        str(ROOT / variant),
                        "--case",
                        case,
                        "--mode",
                        mode,
                    ],
                    cwd=repo,
                )
                row = json.loads(raw)
                row.update(
                    variant=variant,
                    sample=repetition,
                    process_wall_seconds=perf_counter() - started,
                )
                stream.write(json.dumps(row, separators=(",", ":")) + "\n")
                stream.flush()
                pair.append(row)
            if (
                harness == "geometry_cost_matched.py"
                and pair[0]["output"] != pair[1]["output"]
            ):
                raise ValueError(f"Five-query output mismatch: {case}/{mode}")

        for repetition in range(options.repeats):
            variants = (
                ("before", "after") if repetition % 2 == 0 else ("after", "before")
            )
            for case in options.cases:
                for mode in ("cold", "warm"):
                    sample(case, mode, repetition, variants, "geometry_cost_matched.py")
            print(f"Completed matched round {repetition + 1}", flush=True)
        if not options.skip_controls:
            for case, mode in (
                ("T2", "exhausted"),
                ("T2", "unsupported"),
                ("fan20", "cold"),
            ):
                harness = (
                    "geometry_cost.py"
                    if case == "fan20"
                    else "geometry_cost_matched.py"
                )
                sample(case, mode, 0, ("before", "after"), harness)
    print(f"Saved replay to {options.output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "summarize", "run"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=CASES)
    parser.add_argument("--skip-controls", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "replay.jsonl")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    frozen_manifest, matched_rows = verify(args.repo)
    print(
        "Verified original byte hashes, pinned sources/fixture, 102 samples and 48 matched output pairs."
    )
    if args.action == "summarize":
        summarize(matched_rows)
    elif args.action == "run":
        run(args.repo, frozen_manifest, args)
