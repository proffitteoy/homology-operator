<h1 align="center">homology-operator</h1>

<p align="center">F2 homology, persistence, and weighted geometry from boundary matrices.</p>

<p align="center">
  <a href="https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml"><img src="https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml/badge.svg" alt="Reference checks"></a>
  <a href="https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml"><img src="https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml/badge.svg" alt="Native checks"></a>
  <a href="https://github.com/proffitteoy/homology-operator/actions/workflows/oracle.yml"><img src="https://github.com/proffitteoy/homology-operator/actions/workflows/oracle.yml/badge.svg" alt="GUDHI oracle"></a>
</p>

<p align="center">
  <a href="README.md">中文</a> ·
  <a href="https://proffitteoy.github.io/homology-operator/en/">Documentation</a> ·
  <a href="docs/en/INTERFACE.md">API</a> ·
  <a href="docs/en/VALIDATION.md">Development</a> ·
  <a href="LICENSE">MIT License</a>
</p>

`homology-operator` constructs homology operators from a based chain window
`C_{k+1} --D--> C_k --A--> C_{k-1}` over F2 and positive coordinate weights.
One projection `P` supplies Betti numbers, class representatives, selected mass,
class distances, support, and stretch. `OperatorFamily` reads finite-filtration
barcodes and class tracking from transport between stages.

The Python correctness reference uses only the standard library. An optional Rust
extension provides packed algebra, compact actions, supported solvers, and batch
queries. This is a source development snapshot, `0.0.2.dev0`; no PyPI release is
available. The project uses the [MIT License](LICENSE).

## When to use it

Use the library when you already have F2 boundary matrices and need homology and
weighted geometry in the original ordered coordinates, or a finite sequence of
chain windows for joint persistence and geometric tracking. Inputs, projections,
solver records, and results can be saved and independently checked.

The public input is a chain window. General point-cloud, Rips, and complex builders
must be supplied by the caller. True minimum class mass is currently unavailable;
`selected_mass` measures the representative selected by the current projection.

## Installation

Python 3.10+ is required. Install the reference from source:

```console
git clone https://github.com/proffitteoy/homology-operator.git
cd homology-operator
python -m pip install .
python examples/single_scale.py
```

Virtual environments, uv, and optional Rust builds are covered in
[installation](docs/en/getting-started/installation.md) and [platform support](docs/en/platforms.md).

## A minimal example

Two vertices joined by one edge represent the same H0 class:

```python
from homology_operator import (
    ChainWindow, HomologyOperator, Matrix, ProjectionProblem, solve_projection,
)

window = ChainWindow(
    k=0,
    A=Matrix.zero(0, 2),
    D=Matrix.from_rows(((1,), (1,))),
    basis_previous=(),
    basis_current=("v0", "v1"),
    basis_next=("edge",),
    weights=(10, 1),
)
solution = solve_projection(ProjectionProblem(window))
if solution.projection is None:
    raise RuntimeError((solution.status, solution.diagnostics))
op = HomologyOperator(window, solution)

assert op.betti() == 1
assert op.same_class((1, 0), (0, 1))
assert op.class_distance((1, 0), (0, 1)) == 0
assert op.class_representative((0, 1)) == (1, 0)
assert op.selected_mass((0, 1)) == 10

query = op.readout("selected_mass", (0, 1))
assert query.state == "Computed" and query.exact
record = op.to_result()
```

Here the selected representative has mass 10, although another representative of
the same class has mass 1. The default `FeasibleSolver` validates a projection and
does not certify minimum stretch. Projection feasibility, exact evaluation of the
current objective, and global optimality are reported separately.

`project` and `apply_operator` accept arbitrary chains. Class queries require
cycles. Matrix and vector coordinates must be integer 0/1 values; invalid inputs
are explicitly rejected.

## Finite filtrations

Provide a window and operator at each stage. Ordered basis identifiers determine
the coordinate inclusions in all three degrees:

```python
from dataclasses import replace
from homology_operator import OperatorFamily

before = replace(window, D=Matrix.zero(2, 0), basis_next=())
windows = (before, window)
operators = tuple(
    HomologyOperator(w, solve_projection(ProjectionProblem(w))) for w in windows
)
family = OperatorFamily((0, 1), windows, operators)

assert family.transport_rank(0, 1).value == 1
barcode = family.barcode()
assert barcode.state == "Computed"
assert family.track_mass((1, 1), 0, 1).value == 0
```

Barcodes come from `T_ij=P_j J_ij|ker(L_i)`. `barcode()` reads adjacent transport;
`barcode_basis()` and `rank_table()` explicitly request potentially quadratic
outputs. Intervals use half-open stage endpoints, with `None` for survival under
the declared constant terminal extension. Family snapshots default to schema 2;
schema 1 remains readable. See the [English guide](docs/en/USAGE.md#finite-filtrations).

## Capabilities and limits

| Capability | Current scope |
| --- | --- |
| F2 algebra | Explicit shapes, stable elimination, empty spaces, `AD=0` validation |
| Joint readouts | Same-P topology, representatives, geometry, transport, barcode, snapshots |
| Solvers | Five supported reference solvers; optional native selection within their stated domains |
| Weights | Arbitrary-precision integers/rationals and explicit floating-point semantics |
| Optional Rust | Packed algebra, reusable decompositions, multi-RHS, factorized/HC actions, geometry workspace |
| Backend integration | Visible same-solver fallback, cooperative cancellation, validated snapshot recovery |
| Further work | Wider scale and machine coverage, stability, application evidence, public releases |

Every solver output is independently checked for `P²=P`, `AP=0`, `PD=0`, and
preservation of cycle homology. Exact F2 algebra does not certify floating-point
geometry or the global optimum.

## Documentation, contribution, and citation

The [English documentation](docs/en/index.md) provides installation, quickstart,
task guides, API and mathematical references, and development instructions:

- [Installation](docs/en/getting-started/installation.md) and [quickstart](docs/en/getting-started/quickstart.md)
- [Python API](docs/en/INTERFACE.md)
- [Results and serialization](docs/en/RESULT_MODEL.md)
- [Mathematical conventions](docs/en/ARCHITECTURE.md) and [solver contract](docs/en/SOLVER_CONTRACT.md)
- [Development and validation](docs/en/VALIDATION.md)
- [Implementation status and evidence](docs/README.md)

Report issues through [GitHub Issues](https://github.com/proffitteoy/homology-operator/issues).
See [Contributing](CONTRIBUTING.md) before submitting changes. Frozen experiment
reports remain in their original Chinese form. API and native ABI
compatibility policies have not been frozen.

For research, cite the actual software version and commit. Machine-readable
metadata is provided in [CITATION.cff](CITATION.cff). The theory is tied to
[homology-operator-lab at a fixed commit](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88);
its code and validation results are not this package's runtime dependencies or
acceptance evidence. See [source and dependency notices](THIRD_PARTY_NOTICES.md).

## License and release status

The repository uses the [MIT License](LICENSE). No PyPI release is available.
Compatibility policies and the release process need to be finalized before a
public software release.
