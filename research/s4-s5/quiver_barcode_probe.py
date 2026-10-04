"""Independent finite F2 probe: adjacent-map barcode versus all-interval ranks.

This does not import homology-operator or GUDHI, implement a native backend,
or measure performance. Matrices are lists of packed column vectors.
Run: python quiver_barcode_probe.py --cases 5000 --seed 20261002 --output result.json
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
from typing import Optional

Interval = tuple[int, Optional[int]]


def apply(columns: list[int], vector: int) -> int:
    result = 0
    while vector:
        bit = vector & -vector
        result ^= columns[bit.bit_length() - 1]
        vector ^= bit
    return result


def add_independent(pivots: dict[int, int], vector: int) -> bool:
    while vector:
        pivot = vector.bit_length() - 1
        if pivot not in pivots:
            pivots[pivot] = vector
            return True
        vector ^= pivots[pivot]
    return False


def adjacent_barcode(dimensions: list[int], maps: list[list[int]]) -> Counter[Interval]:
    """Keep a current basis ordered by birth; discard dependent forward images.

    This computes interval endpoints only. It does not return historical
    barcode bases or replace HomologyOperator's geometric class tracking.
    """
    alive = [(0, 1 << index) for index in range(dimensions[0])]
    result: Counter[Interval] = Counter()
    for stage, columns in enumerate(maps, start=1):
        pivots: dict[int, int] = {}
        following: list[tuple[int, int]] = []
        for birth, vector in alive:
            image = apply(columns, vector)
            if add_independent(pivots, image):
                following.append((birth, image))
            else:
                result[(birth, stage)] += 1
        for index in range(dimensions[stage]):
            vector = 1 << index
            if add_independent(pivots, vector):
                following.append((stage, vector))
        assert len(following) == dimensions[stage]
        assert all(a[0] <= b[0] for a, b in zip(following, following[1:]))
        alive = following
    for birth, _ in alive:
        result[(birth, None)] += 1
    return result


def rank_barcode(dimensions: list[int], maps: list[list[int]]) -> Counter[Interval]:
    """Independent rank oracle via complete image-set enumeration, not elimination."""
    stages = len(dimensions)
    ranks: dict[tuple[int, int], int] = {}
    for start in range(stages):
        image = set(range(1 << dimensions[start]))
        ranks[(start, start)] = dimensions[start]
        for target in range(start + 1, stages):
            # Explicit coordinate sums, independent of apply()/add_independent().
            columns = maps[target - 1]
            next_image: set[int] = set()
            for vector in image:
                value = 0
                for column, output in enumerate(columns):
                    if (vector >> column) & 1:
                        value ^= output
                next_image.add(value)
            image = next_image
            count = len(image)
            assert count > 0 and count & (count - 1) == 0
            ranks[(start, target)] = count.bit_length() - 1

    def rank(i: int, j: int) -> int:
        return 0 if i < 0 or j >= stages else ranks[(i, j)]

    result: Counter[Interval] = Counter()
    for birth in range(stages):
        for death in range(birth + 1, stages + 1):
            multiplicity = (rank(birth, death - 1) - rank(birth - 1, death - 1)
                            - rank(birth, death) + rank(birth - 1, death))
            assert multiplicity >= 0
            if multiplicity:
                result[(birth, None if death == stages else death)] = multiplicity
    return result


def run(cases: int, seed: int) -> dict:
    if cases < 1:
        raise ValueError("cases must be positive")
    rng = random.Random(seed)
    corpus_hash = hashlib.sha256()
    intervals = 0
    empty_cases = 0
    # Exhaustive tiny maps plus random longer modules.
    deterministic = []
    for source_dim in range(4):
        for target_dim in range(4):
            for encoding in range(1 << (source_dim * target_dim)):
                mask = (1 << target_dim) - 1
                columns = [(encoding >> (j * target_dim)) & mask for j in range(source_dim)]
                deterministic.append(([source_dim, target_dim], [columns]))

    def check(dimensions: list[int], maps: list[list[int]]) -> None:
        nonlocal intervals, empty_cases
        record = {"dimensions": dimensions, "maps": maps}
        corpus_hash.update(json.dumps(record, sort_keys=True, separators=(",", ":")).encode())
        corpus_hash.update(b"\n")
        actual = adjacent_barcode(dimensions, maps)
        expected = rank_barcode(dimensions, maps)
        if actual != expected:
            raise AssertionError({**record, "actual": str(actual), "expected": str(expected)})
        intervals += sum(expected.values())
        empty_cases += int(any(d == 0 for d in dimensions))

    for dimensions, maps in deterministic:
        check(dimensions, maps)
    for _ in range(cases):
        stages = rng.randint(1, 9)
        dimensions = [rng.randint(0, 6) for _ in range(stages)]
        maps = [[rng.randrange(1 << target) for _ in range(source)]
                for source, target in zip(dimensions, dimensions[1:])]
        check(dimensions, maps)

    return {
        "experiment": "Adjacent-map endpoint barcode vs exhaustive-image rank oracle",
        "date": "2026-10-02",
        "seed": seed,
        "exhaustive_two_stage_cases": len(deterministic),
        "random_cases": cases,
        "total_cases": cases + len(deterministic),
        "mismatches": 0,
        "random_stage_range": [1, 9],
        "random_dimension_range": [0, 6],
        "cases_with_zero_dimensional_stage": empty_cases,
        "interval_multiplicity_total": intervals,
        "corpus_sha256": corpus_hash.hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "limitations": [
            "Finite endpoint-only correctness probe; not a proof of all inputs.",
            "No homology-operator, GUDHI, solver, geometric output or serialization integration.",
            "No performance measurement and no high-performance implementation.",
            "Does not produce historical barcode bases; geometric tracking is not tested.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--output", type=Path, default=Path("quiver_barcode_probe_result.json"))
    args = parser.parse_args()
    result = run(args.cases, args.seed)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
