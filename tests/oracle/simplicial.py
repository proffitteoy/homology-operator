"""S5 explicit simplicial manifests and independently audited input builders.

This adapter lives outside the runtime package. GUDHI supplies no operator,
geometry, or solver result. Integer stages, not original scales, are filtrations.
"""

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from itertools import combinations
import json
from math import isfinite
from pathlib import Path


def digest(value):
    return sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def number(value):
    if type(value) in (int, float):
        if type(value) is float and not isfinite(value):
            raise ValueError("numbers must be finite")
        return value
    if isinstance(value, dict) and set(value) == {"numerator", "denominator"}:
        if any(type(x) is not int for x in value.values()) or value["denominator"] <= 0:
            raise ValueError("invalid rational encoding")
        return Fraction(value["numerator"], value["denominator"])
    raise ValueError("expected an integer, finite float, or exact rational")


def facets(simplex):
    return tuple(combinations(simplex, len(simplex) - 1)) if len(simplex) > 1 else ()


def label(simplex):
    return "s:" + ",".join(map(str, simplex))


def manifest_hash(manifest):
    return digest(
        {key: value for key, value in manifest.items() if key != "input_hash"}
    )


def validate_manifest(manifest):
    fields = {
        "schema_version",
        "id",
        "scales",
        "vertices",
        "simplices",
        "requested_degrees",
        "truncation",
        "terminal_extension",
        "coordinate_order",
        "weight_policy",
        "source",
        "input_hash",
    }
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise ValueError("manifest has missing or unknown fields")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("unsupported simplicial manifest schema")
    if not isinstance(manifest["id"], str) or not manifest["id"]:
        raise ValueError("manifest id is required")
    scales = manifest["scales"]
    if not isinstance(scales, list) or not scales or len(scales) > 2**53:
        raise ValueError("at least one exactly representable integer stage is required")
    values = [number(x) for x in scales]
    if any(a > b for a, b in zip(values, values[1:])):
        raise ValueError("original scales must be nondecreasing")
    degrees = manifest["requested_degrees"]
    if (
        not isinstance(degrees, list)
        or not degrees
        or any(type(k) is not int for k in degrees)
        or degrees != list(range(degrees[-1] + 1))
        or not 0 <= degrees[-1] <= 3
    ):
        raise ValueError("requested degrees must be the prefix H0 through Hq, q <= 3")
    truncation = manifest["truncation"]
    if not isinstance(truncation, dict) or set(truncation) != {
        "max_dimension",
        "max_scale",
    }:
        raise ValueError("explicit dimension and scale truncation are required")
    maximum = truncation["max_dimension"]
    if type(maximum) is not int or not degrees[-1] <= maximum <= degrees[-1] + 1:
        raise ValueError(
            "truncation must include requested chains, optionally their deaths"
        )
    if number(truncation["max_scale"]) != values[-1]:
        raise ValueError("scale truncation must match the final declared stage")
    if manifest["terminal_extension"] != "constant":
        raise ValueError("only declared constant terminal extension is supported")
    if manifest["coordinate_order"] not in {"lexicographic", "reverse_lexicographic"}:
        raise ValueError("unsupported coordinate order")
    vertices = manifest["vertices"]
    if not isinstance(vertices, list):
        raise ValueError("vertices must be ordered records")
    ids, coordinate_sizes = set(), set()
    for vertex in vertices:
        if not isinstance(vertex, dict) or set(vertex) != {"id", "coordinates"}:
            raise ValueError("vertex coordinates and identifier are required")
        v = vertex["id"]
        if type(v) is not int or not 0 <= v < 2**31 or v in ids:
            raise ValueError("vertex ids must be distinct nonnegative int32 values")
        ids.add(v)
        if not isinstance(vertex["coordinates"], list):
            raise ValueError("coordinates must be an ordered list")
        coordinate_sizes.add(len(vertex["coordinates"]))
        for coordinate in vertex["coordinates"]:
            number(coordinate)
    if len(coordinate_sizes) > 1:
        raise ValueError("coordinate dimensions must agree")
    policy = manifest["weight_policy"]
    if not isinstance(policy, dict) or set(policy) != {
        "arithmetic",
        "semantics_by_degree",
        "units_by_degree",
    }:
        raise ValueError("weight arithmetic, semantics, and units are required")
    arithmetic = policy["arithmetic"]
    if arithmetic not in {"ExactInteger", "ExactRational", "FloatingPoint"}:
        raise ValueError("unsupported weight arithmetic")
    for field in ("semantics_by_degree", "units_by_degree"):
        if not isinstance(policy[field], dict) or set(policy[field]) != {
            str(k) for k in range(maximum + 1)
        }:
            raise ValueError(
                "weight metadata must cover each declared simplex dimension"
            )
    if any(
        x
        not in {
            "unit",
            "abstract_positive_cost",
            "euclidean_length",
            "euclidean_area",
            "euclidean_volume",
            "custom",
        }
        for x in policy["semantics_by_degree"].values()
    ):
        raise ValueError("unknown weight semantics")
    if any(
        x is not None and (not isinstance(x, str) or not x)
        for x in policy["units_by_degree"].values()
    ):
        raise ValueError("units must be nonempty strings or null")
    births = {}
    if not isinstance(manifest["simplices"], list):
        raise ValueError("simplices must be an ordered list")
    for record in manifest["simplices"]:
        if not isinstance(record, dict) or set(record) != {
            "vertices",
            "birth_stage",
            "weight",
        }:
            raise ValueError("invalid simplex record")
        simplex = record["vertices"]
        if (
            not isinstance(simplex, list)
            or not simplex
            or any(type(v) is not int or v not in ids for v in simplex)
            or simplex != sorted(set(simplex))
            or len(simplex) - 1 > maximum
        ):
            raise ValueError(
                "simplices must be canonical, declared, and within truncation"
            )
        simplex = tuple(simplex)
        if simplex in births:
            raise ValueError("duplicate simplex")
        stage = record["birth_stage"]
        if (
            type(stage) is not int
            or not 0 <= stage < len(scales)
            or int(float(stage)) != stage
        ):
            raise ValueError("simplex stage must be exactly representable and declared")
        births[simplex] = stage
        weight = number(record["weight"])
        if weight <= 0:
            raise ValueError(
                "zero or negative geometric weight is not repaired with epsilon"
            )
        if arithmetic == "ExactInteger" and type(weight) is not int:
            raise ValueError("integer policy requires integer weights")
        if arithmetic == "ExactRational" and isinstance(weight, float):
            raise ValueError("rational policy rejects floating weights")
        if arithmetic == "FloatingPoint" and type(weight) is not float:
            raise ValueError("floating policy requires explicit float weights")
    if {s[0] for s in births if len(s) == 1} != ids:
        raise ValueError("vertices and explicit zero simplices must agree")
    for simplex, stage in births.items():
        if any(face not in births or births[face] > stage for face in facets(simplex)):
            raise ValueError("missing face or nonmonotone simplex birth")
    source = manifest["source"]
    if not isinstance(source, dict) or set(source) != {
        "description",
        "payload",
        "sha256",
    }:
        raise ValueError("source payload and hash are required")
    if not isinstance(source["description"], str) or not source["description"]:
        raise ValueError("source description is required")
    if digest(source["payload"]) != source["sha256"]:
        raise ValueError("source hash mismatch")
    if manifest_hash(manifest) != manifest["input_hash"]:
        raise ValueError("manifest input hash mismatch")
    return manifest


def freeze_manifest(payload):
    manifest = deepcopy(payload)
    manifest["input_hash"] = manifest_hash(manifest)
    return validate_manifest(manifest)


def load_manifests(path=None):
    path = path or Path(__file__).resolve().parents[1] / "fixtures/s5_simplicial.json"
    data = json.loads(Path(path).read_text("utf-8"))
    if (
        set(data) != {"schema_version", "manifests", "corpus_hash"}
        or data["schema_version"] != 1
    ):
        raise ValueError("unsupported corpus schema")
    manifests = [validate_manifest(m) for m in data["manifests"]]
    if len({m["id"] for m in manifests}) != len(manifests):
        raise ValueError("duplicate manifest id")
    if digest(manifests) != data["corpus_hash"]:
        raise ValueError("corpus hash mismatch")
    return manifests


def build_windows(manifest):
    """Construct actual based windows from explicit simplices; no GUDHI import."""
    from homology_operator import ChainWindow, Matrix

    validate_manifest(manifest)
    records = {tuple(r["vertices"]): r for r in manifest["simplices"]}
    policy = manifest["weight_policy"]
    result = {}
    for k in manifest["requested_degrees"]:
        windows = []
        for stage in range(len(manifest["scales"])):
            bases = [
                tuple(
                    sorted(
                        (
                            s
                            for s, r in records.items()
                            if len(s) == degree + 1 and r["birth_stage"] <= stage
                        ),
                        reverse=manifest["coordinate_order"] == "reverse_lexicographic",
                    )
                )
                for degree in (k - 1, k, k + 1)
            ]

            def boundary(rows, columns):
                positions = {s: i for i, s in enumerate(rows)}
                return Matrix.from_columns(
                    (
                        tuple(int(face in facets(s)) for face in positions)
                        for s in columns
                    ),
                    len(rows),
                )

            previous, current, following = bases
            windows.append(
                ChainWindow(
                    k,
                    boundary(previous, current),
                    boundary(current, following),
                    tuple(map(label, previous)),
                    tuple(map(label, current)),
                    tuple(map(label, following)),
                    tuple(number(records[s]["weight"]) for s in current),
                    policy["semantics_by_degree"][str(k)],
                    policy["units_by_degree"][str(k)],
                    policy["arithmetic"],
                    {
                        "manifest_id": manifest["id"],
                        "input_hash": manifest["input_hash"],
                        "source": manifest["source"],
                        "stage": stage,
                    },
                )
            )
        result[k] = tuple(windows)
    return result


def _export(records, stages, maximum):
    records = sorted(records, key=lambda r: (len(r["vertices"]), r["vertices"]))
    return {
        "simplices": records,
        "counts_by_stage_degree": [
            [
                sum(
                    len(r["vertices"]) == k + 1 and r["birth_stage"] <= i
                    for r in records
                )
                for k in range(maximum + 1)
            ]
            for i in range(stages)
        ],
    }


def export_windows(manifest, windows):
    """Read bases and actual A/D columns back, rather than hashing input records."""
    reverse_labels = {
        label(r["vertices"]): r["vertices"] for r in manifest["simplices"]
    }
    observed = {}
    if set(windows) != set(manifest["requested_degrees"]):
        raise ValueError("export is missing a requested degree")
    for k, slices in windows.items():
        if len(slices) != len(manifest["scales"]):
            raise ValueError("export is missing a declared stage")
        for stage, window in enumerate(slices):
            if window.k != k:
                raise ValueError("window degree mismatch")
            for degree, basis in (
                (k - 1, window.basis_previous),
                (k, window.basis_current),
                (k + 1, window.basis_next),
            ):
                expected_basis = tuple(
                    map(
                        label,
                        sorted(
                            (
                                tuple(r["vertices"])
                                for r in manifest["simplices"]
                                if len(r["vertices"]) == degree + 1
                                and r["birth_stage"] <= stage
                            ),
                            reverse=manifest["coordinate_order"]
                            == "reverse_lexicographic",
                        ),
                    )
                )
                if basis != expected_basis:
                    raise ValueError(
                        "actual stage basis differs from declared coordinates"
                    )
            weights = {
                label(r["vertices"]): number(r["weight"]) for r in manifest["simplices"]
            }
            policy = manifest["weight_policy"]
            if (
                window.weights != tuple(weights[name] for name in window.basis_current)
                or window.arithmetic != policy["arithmetic"]
                or window.weight_semantics != policy["semantics_by_degree"][str(k)]
                or window.unit != policy["units_by_degree"][str(k)]
            ):
                raise ValueError(
                    "actual chain weights or arithmetic differ from manifest"
                )
            for degree, basis, rows, matrix in (
                (k, window.basis_current, window.basis_previous, window.A),
                (k + 1, window.basis_next, window.basis_current, window.D),
            ):
                for j, name in enumerate(basis):
                    vertices = reverse_labels[name]
                    boundary = sorted(
                        reverse_labels[rows[i]]
                        for i in range(matrix.nrows)
                        if matrix.rows[i][j]
                    )
                    record = {
                        "vertices": vertices,
                        "birth_stage": stage,
                        "boundary": boundary,
                    }
                    if name in observed:
                        if observed[name]["boundary"] != boundary:
                            raise ValueError("boundary changed between windows")
                    else:
                        observed[name] = record
    return _export(
        list(observed.values()),
        len(manifest["scales"]),
        manifest["truncation"]["max_dimension"],
    )


def build_simplex_tree(manifest):
    import gudhi

    validate_manifest(manifest)
    tree = gudhi.SimplexTree()
    for record in manifest["simplices"]:
        tree.insert(record["vertices"], filtration=float(record["birth_stage"]))
    # Deliberately do not repair filtration: insertion side effects must be audited.
    return tree


def export_simplex_tree(manifest, tree):
    records = []
    for simplex, filtration in tree.get_filtration():
        if (
            not isfinite(filtration)
            or filtration != int(filtration)
            or not 0 <= filtration < len(manifest["scales"])
        ):
            raise ValueError("SimplexTree has an undeclared or lossy stage")
        records.append(
            {
                "vertices": sorted(simplex),
                "birth_stage": int(filtration),
                "boundary": sorted(
                    sorted(face) for face, _ in tree.get_boundaries(simplex)
                ),
            }
        )
    return _export(
        records, len(manifest["scales"]), manifest["truncation"]["max_dimension"]
    )


def expected_export(manifest):
    return _export(
        [
            {
                "vertices": r["vertices"],
                "birth_stage": r["birth_stage"],
                "boundary": [list(s) for s in facets(r["vertices"])],
            }
            for r in manifest["simplices"]
        ],
        len(manifest["scales"]),
        manifest["truncation"]["max_dimension"],
    )


def audit_inputs(manifest, windows=None, tree=None):
    validate_manifest(manifest)
    windows = build_windows(manifest) if windows is None else windows
    tree = build_simplex_tree(manifest) if tree is None else tree
    expected = expected_export(manifest)
    chain_export = export_windows(manifest, windows)
    tree_export = export_simplex_tree(manifest, tree)
    if chain_export != expected or tree_export != expected:
        raise ValueError(
            "actual constructed simplex/filtration/boundary input differs from manifest"
        )
    return {
        "state": "Comparable",
        "manifest_hash": manifest["input_hash"],
        "chain_hash": digest(chain_export),
        "simplex_tree_hash": digest(tree_export),
        "counts_by_stage_degree": expected["counts_by_stage_degree"],
    }


def applicability(manifest=None):
    if manifest is None:
        return {
            "state": "NotApplicable",
            "reason": "no explicit simplicial manifest for this AD=0 window",
        }
    validate_manifest(manifest)
    return {"state": "Comparable", "manifest_hash": manifest["input_hash"]}


def synthetic_manifest(
    identifier, births, scales, q=1, maximum=None, order="lexicographic"
):
    """Explicit synthetic fixture constructor; never fills missing faces."""
    maximum = q + 1 if maximum is None else maximum
    births = [(tuple(s), stage) for s, stage in births]
    source_payload = {
        "generator": "explicit synthetic simplex births v1",
        "births": births,
    }
    return freeze_manifest(
        {
            "schema_version": 1,
            "id": identifier,
            "scales": scales,
            "vertices": [
                {"id": v, "coordinates": []}
                for v in sorted({v for s, _ in births for v in s})
            ],
            "simplices": [
                {"vertices": list(s), "birth_stage": stage, "weight": 1}
                for s, stage in births
            ],
            "requested_degrees": list(range(q + 1)),
            "truncation": {"max_dimension": maximum, "max_scale": scales[-1]},
            "terminal_extension": "constant",
            "coordinate_order": order,
            "weight_policy": {
                "arithmetic": "ExactInteger",
                "semantics_by_degree": {str(k): "unit" for k in range(maximum + 1)},
                "units_by_degree": {str(k): None for k in range(maximum + 1)},
            },
            "source": {
                "description": "Synthetic explicit complex; no research fixture migration",
                "payload": source_payload,
                "sha256": digest(source_payload),
            },
        }
    )
