"""Reproduce S5-02 F2 topology and record actual optional secondary entrances."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))


def main():
    from oracle.simplicial import digest, load_manifests
    from oracle.gudhi_oracle import (
        build_families,
        environment,
        flag_cycle_manifest,
        gudhi_topology,
        operator_topology,
        secondary_topology,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-secondary", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be new; do not overwrite frozen evidence")
    manifests, rows = load_manifests(), []
    for manifest in manifests:
        oracle = gudhi_topology(manifest)
        actual = operator_topology(build_families(manifest))
        if actual != oracle["topology"]:
            raise ValueError(f"topology mismatch: {manifest['id']}")
        rows.append(
            {
                "id": manifest["id"],
                "gudhi": oracle,
                "operator_topology": actual,
                "mismatch": False,
            }
        )
    flag = flag_cycle_manifest()
    secondary = [
        secondary_topology(flag, route)
        for route in ("edge_collapse", "rips_persistence")
    ]
    if args.require_secondary and any(r["state"] != "Computed" for r in secondary):
        raise ValueError(
            "install locked oracle-secondary group to execute both secondary methods"
        )
    primary = gudhi_topology(flag)["topology"]
    if any(r["state"] == "Computed" and r["topology"] != primary for r in secondary):
        raise ValueError("secondary flag topology mismatch")
    result = {
        "schema_version": 1,
        "environment": environment(),
        "corpus_hash": digest(manifests),
        "rows": rows,
        "secondary_flag_manifest": flag,
        "secondary_results": secondary,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Checked {len(rows)} exact complexes: zero topology mismatches")


if __name__ == "__main__":
    main()
