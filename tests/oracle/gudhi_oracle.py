"""Locked F2 topology oracle; never supplies an operator or a geometric readout."""

from collections import Counter
from hashlib import sha256
from importlib.metadata import distribution, version
from itertools import combinations
from math import isfinite, isinf
from pathlib import Path

from .simplicial import (
    build_simplex_tree,
    build_windows,
    digest,
    expected_export,
    export_simplex_tree,
    number,
    validate_manifest,
    synthetic_manifest,
)

GUDHI_VERSION = "3.11.0"
PERSISTENCE_OPTIONS = {
    "homology_coeff_field": 2,
    "min_persistence": 0,
    "persistence_dim_max": True,
}


def require_gudhi():
    actual = version("gudhi")
    if actual != GUDHI_VERSION:
        raise ValueError(f"oracle requires GUDHI {GUDHI_VERSION}, found {actual}")


def environment():
    require_gudhi()
    dist = distribution("gudhi")
    binaries = {
        str(p): sha256(Path(dist.locate_file(p)).read_bytes()).hexdigest()
        for p in dist.files
        if p.suffix in {".pyd", ".so", ".dll"}
    }
    return {
        "gudhi_version": version("gudhi"),
        "numpy_version": version("numpy"),
        "origin": "PyPI binary wheel locked by uv.lock; no local GUDHI build",
        "installed_compiled_sha256": binaries,
        "persistence_options": PERSISTENCE_OPTIONS,
    }


def normalize_pairs(pairs, degrees, stages):
    counts = {k: Counter() for k in degrees}
    for degree, (birth, death) in pairs:
        if degree not in counts:
            continue
        if not isfinite(birth) or birth != int(birth) or not 0 <= birth < stages:
            raise ValueError("invalid or lossy oracle birth stage")
        birth = int(birth)
        if isinf(death) and death > 0:
            death = None
        elif not isfinite(death) or death != int(death) or not birth <= death < stages:
            raise ValueError("invalid or lossy oracle death stage")
        else:
            death = int(death)
        if death == birth:
            continue  # Instantaneous within-stage pairs are absent from stage modules.
        counts[degree][birth, death] += 1
    return {
        str(k): [
            [b, d, multiplicity]
            for (b, d), multiplicity in sorted(
                counter.items(),
                key=lambda item: (
                    item[0][0],
                    stages if item[0][1] is None else item[0][1],
                ),
            )
        ]
        for k, counter in counts.items()
    }


def interval_statistics(barcodes, stages):
    result = {}
    for degree, bars in barcodes.items():

        def rank(i, j):
            return sum(m for b, d, m in bars if b <= i and (d is None or j < d))

        result[degree] = {
            "barcode": bars,
            "betti": [rank(i, i) for i in range(stages)],
            "ranks": [
                [i, j, rank(i, j)] for i in range(stages) for j in range(i, stages)
            ],
        }
    return result


def gudhi_topology(manifest, tree=None):
    """Primary oracle on the exact declared explicit complex, including max dim."""
    require_gudhi()
    validate_manifest(manifest)
    tree = build_simplex_tree(manifest) if tree is None else tree
    exported = export_simplex_tree(manifest, tree)
    if exported != expected_export(manifest):
        raise ValueError("oracle SimplexTree input differs from declared manifest")
    pairs = tree.persistence(**PERSISTENCE_OPTIONS)
    bars = normalize_pairs(
        pairs, manifest["requested_degrees"], len(manifest["scales"])
    )
    return {
        "state": "Computed",
        "input_hash": manifest["input_hash"],
        "actual_complex_hash": digest(exported),
        "topology": interval_statistics(bars, len(manifest["scales"])),
        "options": PERSISTENCE_OPTIONS,
        "oracle_scope": "F2 topology only",
    }


def build_families(manifest, method="FeasibleSolver", **problem_options):
    from homology_operator import (
        HomologyOperator,
        OperatorFamily,
        ProjectionProblem,
        solve_projection,
    )

    windows = build_windows(manifest)
    families = {}
    for k, slices in windows.items():
        operators = []
        for window in slices:
            solution = solve_projection(
                ProjectionProblem(window, **problem_options), method
            )
            if solution.projection is None:
                raise ValueError(f"{method}: {solution.status}: {solution.diagnostics}")
            operators.append(HomologyOperator(window, solution))
        families[k] = OperatorFamily(
            tuple(number(x) for x in manifest["scales"]), slices, tuple(operators)
        )
    return families


def operator_topology(families):
    """Read every Betti and interval rank from the actual P-derived families."""
    result = {}
    for k, family in families.items():
        bars = family.barcode()
        if bars.state != "Computed":
            raise ValueError(f"family barcode is {bars.state}")
        result[str(k)] = {
            "barcode": sorted(
                [
                    [b["birth_stage"], b["death_stage"], b["multiplicity"]]
                    for b in bars.value
                ],
                key=lambda x: (x[0], len(family.windows) if x[1] is None else x[1]),
            ),
            "betti": [op.betti() for op in family.operators],
            "ranks": [
                [i, j, family.transport_rank(i, j).value]
                for i in range(len(family.windows))
                for j in range(i, len(family.windows))
            ],
        }
    return result


def flag_applicability(manifest):
    """Secondary graph methods require the same full flag q+1 truncation."""
    validate_manifest(manifest)
    births = {tuple(r["vertices"]): r["birth_stage"] for r in manifest["simplices"]}
    vertices = sorted(v["id"] for v in manifest["vertices"])
    q = manifest["requested_degrees"][-1]
    if not vertices or manifest["truncation"]["max_dimension"] != q + 1:
        return {
            "state": "NotApplicable",
            "reason": "secondary requires nonempty flag q+1 truncation",
        }
    if any(births[(v,)] != 0 for v in vertices):
        return {
            "state": "NotApplicable",
            "reason": "secondary requires vertices present at stage zero",
        }
    expected = {(v,): 0 for v in vertices}
    edges = {s: stage for s, stage in births.items() if len(s) == 2}
    expected.update(edges)
    for size in range(3, q + 3):
        for simplex in combinations(vertices, size):
            faces = tuple(combinations(simplex, 2))
            if all(edge in edges for edge in faces):
                expected[simplex] = max(edges[edge] for edge in faces)
    if expected != births:
        return {
            "state": "NotApplicable",
            "reason": "explicit input is not the stage flag expansion of its graph",
        }
    return {"state": "Comparable", "vertices": vertices, "edges": edges}


def secondary_topology(manifest, route):
    require_gudhi()
    applicable = flag_applicability(manifest)
    if applicable["state"] != "Comparable":
        return applicable
    import gudhi

    q, stages = manifest["requested_degrees"][-1], len(manifest["scales"])
    if route == "edge_collapse":
        tree = gudhi.SimplexTree()
        for vertex in applicable["vertices"]:
            tree.insert([vertex], filtration=0)
        for edge, stage in applicable["edges"].items():
            tree.insert(edge, filtration=stage)
        tree.collapse_edges(nb_iterations=1)
        tree.expansion(q + 1)
        pairs = tree.persistence(**PERSISTENCE_OPTIONS)
        options = {
            "nb_iterations": 1,
            "expansion_dimension": q + 1,
            **PERSISTENCE_OPTIONS,
        }
    elif route == "rips_persistence":
        try:
            import numpy as np
            from gudhi.sklearn.rips_persistence import RipsPersistence
        except ImportError as error:
            return {"state": "Unavailable", "reason": str(error)}
        vertices = applicable["vertices"]
        positions = {v: i for i, v in enumerate(vertices)}
        matrix = np.full((len(vertices), len(vertices)), np.inf)
        np.fill_diagonal(matrix, 0)
        for (u, v), stage in applicable["edges"].items():
            matrix[positions[u], positions[v]] = matrix[positions[v], positions[u]] = (
                stage
            )
        options = {
            "homology_dimensions": manifest["requested_degrees"],
            "threshold": stages - 1,
            "input_type": "full distance matrix",
            "num_collapses": 0,
            "homology_coeff_field": 2,
            "n_jobs": 1,
        }
        diagrams = RipsPersistence(**options).fit_transform([matrix])[0]
        pairs = [
            (k, interval)
            for k, diagram in zip(manifest["requested_degrees"], diagrams)
            for interval in diagram
        ]
    else:
        raise ValueError("unknown secondary route")
    bars = normalize_pairs(pairs, manifest["requested_degrees"], stages)
    return {
        "state": "Computed",
        "topology": interval_statistics(bars, stages),
        "input_hash": manifest["input_hash"],
        "route": route,
        "options": options,
        "oracle_scope": "flag topology only; no original chain geometry assertion",
        "input_representation_changed": route == "edge_collapse",
    }


def flag_cycle_manifest():
    edges = {
        s: 1 if s in {(0, 1), (1, 2), (2, 3), (0, 3)} else 2
        for s in combinations(range(4), 2)
    }
    births = [((v,), 0) for v in range(4)] + list(edges.items())
    births += [
        (s, max(edges[e] for e in combinations(s, 2)))
        for s in combinations(range(4), 3)
    ]
    return synthetic_manifest("flag_cycle", births, [0, 1, 1], q=1)
