# Input semantics

[中文](../../guide/input-semantics.md)

## Input and arithmetic

A `ChainWindow` represents one fixed degree:

```math
C_{k+1}\xrightarrow{D}C_k\xrightarrow{A}C_{k-1},\qquad AD=0.
```

`A` has shape m×n and `D` has shape n×p, using column vectors. Supply ordered,
unique nonempty basis identifiers for each space and n finite positive weights.
Empty spaces are supported. Invalid dimensions, bases, coordinates, weights, or
`AD≠0` raise `InvalidInput`, a `ValueError` subclass.

```python
from homology_operator import Matrix

matrix = Matrix.from_rows(((1, 1, 0), (0, 1, 1)))
assert matrix.kernel_basis() == ((1, 1, 1),)
assert matrix.solve((1, 0)) == (1, 0, 0)
assert Matrix.from_rows((), ncols=3) == Matrix.zero(0, 3)
```

Coordinates must be integer 0/1 values; booleans, floats, truncation, and implicit
reduction modulo 2 are rejected. `solve(b)` returns a deterministic solution with
free variables set to zero, or `None` when no solution exists. A valid empty
solution is `()`.

| `arithmetic` | Accepted weights | Geometry |
| --- | --- | --- |
| `ExactInteger` | Arbitrary-precision integers | Exact; objective ratios use `Fraction` |
| `ExactRational` (default) | Integers and `fractions.Fraction` | Exact rational arithmetic |
| `FloatingPoint` | Integers, floats, fractions converted to finite positive binary64 | Numerical `fsum`; no exact geometric optimality certificate |

The caller declares `weight_semantics` and `unit`. Positive costs do not imply
that weights are areas or volumes. Original coordinates determine geometry.

## Source mapping and location

`source_metadata["source_mapping"]` optionally declares the version 1 protocol
below. Other metadata remains descriptive. The protocol binds a simplicial
window to original point records, coordinate units, a metric, periodic lifts,
and an ordered filtration. It requires no external topology package or renderer.

| Field | Required value |
| --- | --- |
| `version` | Integer `1` |
| `source_hash` | Lowercase SHA-256 hex digest of the caller's original dataset bytes |
| `stage_order` | Nonempty ordered list of distinct stage ID strings, including stages with repeated scales |
| `stage`, `scale` | Zero-based stage index and finite JSON number for its scale |
| `vertices` | Map from nonempty vertex ID to `{"original_id": ..., "coordinates": ...}` |
| `simplices` | Map from basis label to `{"vertices": [...], "offsets": ...}` |
| `embedding` | `null`, or `{"dimension": d, "unit": "m", "metric": "euclidean", "periods": [...]}` |

Original IDs are distinct nonempty strings or integers, preserving the caller's
indices without renumbering. Coordinates are finite numbers of dimension `d`.
The vertex table is the same complete source table at every mapped family stage.
The simplex table covers exactly the three window bases with distinct labels
across degrees. A degree-q simplex has q+1 distinct vertices; repeated vertex
sets within a degree are rejected. Its faces must agree with the actual A/D
columns, including all faces represented in the window. H0 is unaugmented.
This protocol covers simplicial windows; arbitrary cellular windows can omit it.

An absent embedding requires `coordinates=null` and `offsets=null`; connectivity
and original IDs are still available. Without any source mapping, location
returns basis labels and support indices, with null vertices, coordinates and
components. Ordinary descriptive metadata is never treated as a verified map.

The embedding unit is the coordinate unit. Weight units remain separate:
Euclidean length/area/volume semantics require degree 1/2/3 respectively and
units `m`, `m^2`, `m^3` when the coordinate unit is `m`. These checks validate
declared dimensions and units, not the numerical correctness of supplied weights,
nondegeneracy, a manifold condition, or measurement accuracy.

Each axis period is null or a positive finite number in the coordinate unit.
Periodic base coordinates lie in `[0, period)`. An embedded simplex supplies one
integer offset vector per vertex, zero on nonperiodic axes; its first vertex has
offset zero. Its drawing coordinates are `coordinate + offset * period` axis by
axis. Shared faces must have the same relative lifts, up to a common lattice
translation. A renderer uses these lifted vertices, optionally clipping or
translating copies into the base cell. It must not independently choose shortest
wrapped edges. Only Cartesian Euclidean embeddings with axis periods are
supported; self-identified vertices and multiple simplices with the same vertex
set require a different protocol.

For example, this edge crosses a periodic seam from 9 m to 11 m, although its
second endpoint is stored at 1 m:

```python
from hashlib import sha256
import json
from homology_operator import (
    ChainWindow, HomologyOperator, Matrix, ProjectionProblem, solve_projection,
)

points = [{"original_id": 42, "coordinates": [9]},
          {"original_id": 7, "coordinates": [1]}]
source_bytes = json.dumps(points, separators=(",", ":")).encode("utf-8")
mapping = {
    "version": 1,
    "source_hash": sha256(source_bytes).hexdigest(),
    "stage_order": ["merged"], "stage": 0, "scale": 2,
    "vertices": dict(zip(("a", "b"), points)),
    "simplices": {
        "a": {"vertices": ["a"], "offsets": [[0]]},
        "b": {"vertices": ["b"], "offsets": [[0]]},
        "edge": {"vertices": ["a", "b"], "offsets": [[0], [1]]},
    },
    "embedding": {"dimension": 1, "unit": "m", "metric": "euclidean",
                  "periods": [10]},
}
window = ChainWindow(
    0, Matrix.zero(0, 2), Matrix.from_rows(((1,), (1,))),
    (), ("a", "b"), ("edge",), (1, 1),
    source_metadata={"source_mapping": mapping},
)
op = HomologyOperator(window, solve_projection(ProjectionProblem(window)))
edge = window.locate_chain((1,), degree=1)
assert edge["simplices"][0]["original_ids"] == (42, 7)
assert edge["simplices"][0]["coordinates"] == ((9,), (11,))
point = op.readout("locate_support", (0, 1))
assert point.value["degree"] == 0  # The selected H0 representative is points.
assert point.value["support"] == op.support((0, 1))
```

`window.locate_chain(x, degree=0, source_mapping_id=None)` locates any raw chain;
`degree` is the offset -1/0/1 from k. It can locate a supplied H0 merge edge or
a supplied three-dimensional filling in a k=2 window. It does not compute an
event witness or filling. `op.locate_support(z, source_mapping_id=None)` accepts
cycles and locates the same-P representative. Use `op.readout("locate_support", z)`
to persist the query with all six operator identities. H1 support may contain
several components; H2 support contains triangles. No readout reinterprets H0
as a loop. Components are sets of support indices joined by shared vertex IDs
in the quotient complex; they do not certify simple loops or manifolds.

Location records contain `source_hash`, `source_mapping_id`, `input_id`,
`basis_id`, `stage`, `stage_order`, `scale`, units, support, simplices, components,
and a content `location_id`. An optional expected `source_mapping_id` rejects
cross-input location requests. `exact=None` on recorded locations makes no
metric-accuracy claim. Integer lifts are explicit; floating overflow is rejected.
`weight_degree` identifies the window degree k: its weight unit/semantics do not
describe a measure of a raw chain at degree k-1 or k+1.

`family.track_location(x, i, j)` locates the transported representative at stage
j and carries the same filtration identity as transport/rank/barcode readouts.
Mapped families require every stage to match its index/scale and complete stage
order, with unchanged source hash, vertices, embedding and existing simplices.
See [identity and recovery](../RESULT_MODEL.md#source-mapping-identity) for hashing
and tamper checks.
