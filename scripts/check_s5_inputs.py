"""Reproduce S5-01 actual input exports without computing persistence."""

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from oracle.simplicial import (  # noqa: E402 - test-only adapter, outside runtime package
    audit_inputs,
    build_simplex_tree,
    build_windows,
    digest,
    export_simplex_tree,
    export_windows,
    load_manifests,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "tests/fixtures/s5_simplicial.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be a new path; frozen evidence is never overwritten")
    rows = []
    for manifest in load_manifests(args.manifest):
        windows, tree = build_windows(manifest), build_simplex_tree(manifest)
        rows.append(
            {
                "id": manifest["id"],
                "audit": audit_inputs(manifest, windows, tree),
                "chain_export": export_windows(manifest, windows),
                "simplex_tree_export": export_simplex_tree(manifest, tree),
            }
        )
    result = {
        "schema_version": 1,
        "python": platform.python_version(),
        "gudhi": version("gudhi"),
        "numpy": version("numpy"),
        "corpus_hash": digest(load_manifests(args.manifest)),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Audited {len(rows)} explicit complexes; all actual input exports match")


if __name__ == "__main__":
    main()
