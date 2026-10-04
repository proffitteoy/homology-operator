"""Check the research catalog and reproduce archived results without resampling."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CATALOG = "benchmarks/registry.json"
PROTECTED = (
    "benchmarks",
    "docs",
    "native",
    "research",
    "scripts",
    "src",
    "tests",
    ".git",
)


def repository_path(root, name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"invalid repository path: {name}")
    target = (root / name).resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError(f"path leaves repository: {name}")
    return target


def audit_registry(root, catalog):
    """Verify complete artifact coverage and canonical or original byte hashes."""
    root = root.resolve()
    if catalog["schema_version"] != 1:
        raise ValueError("unsupported research catalog schema")
    groups = {}
    for group in catalog["groups"]:
        if group["id"] in groups:
            raise ValueError(f"duplicate experiment: {group['id']}")
        groups[group["id"]] = group
        for name in [group["report"], *group["entrypoints"]]:
            if not repository_path(root, name).is_file():
                raise ValueError(f"missing research entrypoint: {name}")
    registered = set()
    counts = Counter()
    for item in catalog["artifacts"]:
        name = item["path"]
        if name in registered or item["group"] not in groups:
            raise ValueError(f"duplicate artifact or unknown experiment: {name}")
        registered.add(name)
        counts[item["group"]] += 1
        data = repository_path(root, name).read_bytes()
        if item["hash_mode"] == "lf":
            data = data.replace(b"\r\n", b"\n")
        elif item["hash_mode"] != "bytes":
            raise ValueError(f"unknown hash mode: {name}")
        if len(data) != item["size"] or sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"research artifact changed: {name}")
        if "decompressed_sha256" in item:
            plain = gzip.decompress(data)
            if (
                len(plain) != item["decompressed_size"]
                or sha256(plain).hexdigest() != item["decompressed_sha256"]
            ):
                raise ValueError(f"decompressed artifact changed: {name}")
    discovered = {
        path.relative_to(root).as_posix()
        for folder in ("benchmarks", "tests/fixtures", "research/s4-s5")
        for path in (root / folder).rglob("*")
        if path.is_file()
        and path.suffix in (".json", ".csv", ".log", ".gz", ".md", ".py")
        and path.name not in ("registry.json", "README.md")
        and "__pycache__" not in path.parts
    }
    if discovered != registered:
        raise ValueError(
            f"artifact coverage differs: uncatalogued={sorted(discovered - registered)}, "
            f"outside artifact roots={sorted(registered - discovered)}"
        )
    return {
        "artifacts": len(registered),
        "experiments": len(groups),
        "groups": dict(counts),
    }


def prepare_output(root, output):
    """Reserve a new output directory outside source and frozen evidence."""
    root = root.resolve()
    output = output.resolve()
    if output == root or any(output.is_relative_to(root / name) for name in PROTECTED):
        raise ValueError(
            "output must be outside source and frozen evidence directories"
        )
    output.mkdir(parents=True, exist_ok=False)
    return output


def reproduce(root, output, selection):
    result = {}
    if selection in ("probe", "all"):
        generated = output / "quiver_barcode_probe_result.json"
        subprocess.run(
            [
                sys.executable,
                str(root / "research/s4-s5/quiver_barcode_probe.py"),
                "--cases",
                "5000",
                "--seed",
                "20261002",
                "--output",
                str(generated),
            ],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        actual = json.loads(generated.read_text("utf-8"))
        expected = json.loads(
            (root / "research/s4-s5/quiver_barcode_probe_result.json").read_text(
                "utf-8"
            )
        )
        if actual != expected:
            raise ValueError("probe result differs from the archived result")
        result["probe"] = {"cases": actual["total_cases"], "matches_archive": True}
    if selection in ("s5-report", "all"):
        target = output / "s5-report"
        subprocess.run(
            [
                sys.executable,
                str(root / "scripts/report_s5.py"),
                "--output-dir",
                str(target),
            ],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        expected = json.loads(
            (root / "benchmarks/s5_report_audit.json").read_text("utf-8")
        )["table_sha256"]
        actual = {
            name: sha256((target / name).read_bytes()).hexdigest() for name in expected
        }
        if actual != expected:
            raise ValueError("S5 statistical tables differ from frozen table hashes")
        result["s5-report"] = {"matches_archive": True, "table_sha256": actual}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reproduce", choices=("probe", "s5-report", "all"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if bool(args.reproduce) != bool(args.output_dir):
        parser.error("--reproduce and --output-dir must be supplied together")
    catalog = json.loads((ROOT / CATALOG).read_text("utf-8"))
    result = audit_registry(ROOT, catalog)
    if args.reproduce:
        output = prepare_output(ROOT, args.output_dir)
        result["reproduced"] = reproduce(ROOT, output, args.reproduce)
        result["output_dir"] = str(output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
