<h1 align="center">homology-operator</h1>

<p align="center">Binary homology operators: kernels, linear representatives, weighted geometry, and persistent transport.</p>

<p align="center">
  <a href="https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml"><img src="https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml/badge.svg" alt="Reference checks"></a>
  <a href="https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml"><img src="https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml/badge.svg" alt="Native checks"></a>
  <a href="https://github.com/proffitteoy/homology-operator/actions/workflows/oracle.yml"><img src="https://github.com/proffitteoy/homology-operator/actions/workflows/oracle.yml/badge.svg" alt="GUDHI oracle"></a>
</p>

<p align="center">
  <a href="https://github.com/proffitteoy/homology-operator/blob/main/README.md">中文</a> ·
  <a href="https://proffitteoy.github.io/homology-operator/en/">Documentation</a> ·
  <a href="https://github.com/proffitteoy/homology-operator/blob/main/docs/en/INTERFACE.md">API</a> ·
  <a href="https://github.com/proffitteoy/homology-operator/blob/main/docs/en/MATHEMATICS.md">Mathematics</a> ·
  <a href="https://github.com/proffitteoy/homology-operator/blob/main/docs/en/VALIDATION.md">Development</a> ·
  <a href="https://github.com/proffitteoy/homology-operator/blob/main/LICENSE">MIT License</a>
</p>

This project introduces a **binary homology operator** on the original chain
space and provides its Python/Rust implementation. Its kernel realizes homology;
the accompanying projection selects cycle representatives that obey all linear
relations. Weighted action supplies class mass, distance, and support. Transport
between kernels realizes the persistence module of a finite filtration.
Definitions and proofs are in the [mathematics document](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/MATHEMATICS.md);
the separate [Mathematics section](#mathematics) below gives the core relations.

The Python correctness reference uses only the standard library. An optional Rust
extension provides packed algebra, compact actions, supported solvers, and batch
queries. The Python package version is `0.0.2`, an early release. Check the
[PyPI version record](https://pypi.org/project/homology-operator/0.0.2/) for upload status. The project uses the [MIT License](https://github.com/proffitteoy/homology-operator/blob/main/LICENSE).

## When to use it

Use the library when you already have F2 boundary matrices and need homology and
weighted geometry in the original ordered coordinates, or a finite sequence of
chain windows for joint persistence and geometric tracking. Inputs, projections,
solver records, and results can be saved and independently checked.

The public input is a chain window. General point-cloud, Rips, and complex builders
must be supplied by the caller. True minimum class mass is currently unavailable;
`selected_mass` measures the representative selected by the current projection.

## Installation

Python 3.10+ is required. Install from PyPI:

```console
python -m pip install homology-operator==0.0.2
```

The reference can also be installed from source:

```console
git clone https://github.com/proffitteoy/homology-operator.git
cd homology-operator
python -m pip install .
python examples/single_scale.py
```

Virtual environments, uv, and optional Rust builds are covered in
[installation](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/getting-started/installation.md) and [platform support](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/platforms.md).

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
schema 1 remains readable. See the [English guide](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/USAGE.md#finite-filtrations).

## Mathematics

### Definition and construction

The input is a finite based chain window in a fixed degree with positive coordinate weights:

```math
C_{k+1}\xrightarrow{D}C_k\xrightarrow{A}C_{k-1},\qquad AD=0.
```

Choose algebraic generalized inverses with $`AGA=A`$ and $`DUD=D`$ and construct

```math
P=(I+DU)(I+GA),\qquad L=I+P,\qquad
\boxed{\ker L=\mathrm{im}\,P\cong H_k(C;\mathbf F_2).}
```

Each kernel vector uniquely represents a homology class. $`P`$ preserves cycle
classes and enforces linear relations between all representatives:
$`P(z+y)=Pz+Py`$. The same weighted action supplies topology, representative mass,
class distance, shared support, and worst stretch. Projected transport between
kernels realizes the entire persistence module of a finite filtration, from
which the barcode is read. Definitions and proofs are in [operator theory](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/MATHEMATICS.md).

### Minimum stretch

Legal projections need not be unique. Minimum stretch controls every cycle:

```math
\Gamma_w(P)=\max_{0\ne z,\ Az=0}\frac{m_w(Pz)}{m_w(z)},\qquad
\Gamma_*=\min_{P\ \mathrm{legal}}\Gamma_w(P),\qquad
m_w(x)=\sum_{i:x_i=1}w_i.
```

This equals the minimum-stretch linear section problem for the homology
quotient. If $`\beta>0`$, $`1\le\Gamma_*\le\beta`$. In the six-edge complex, a
minimum-total-mass basis gives masses $`(8,8,12)`$ and stretch $`4/3`$; a
minimum-stretch operator gives $`(8,9,9)`$ and stretch $`9/8`$. Shared-support
cancellation controls the combined class.
The [complete example](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/MATHEMATICS.md#6-a-complete-six-edge-example)
exhausts all four sections; [runnable code](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/guide/single-scale.md#an-exact-operator-on-the-six-edge-complex)
reads all values from the actual operator.

The default solver constructs a legal operator. Exact solvers certify optimality
within their domains through independent certificates. The eigenvalues of $`L`$
are only $`0,1`$; its weighted action supplies geometry.

## Capabilities and limits

| Capability | Current scope |
| --- | --- |
| F2 algebra | Explicit shapes, stable elimination, empty spaces, `AD=0` validation |
| Joint readouts | Same-P topology, representatives, geometry, transport, barcode, snapshots |
| Solvers | Five supported reference solvers; optional native selection within their stated domains |
| Weights | Arbitrary-precision integers/rationals and explicit floating-point semantics |
| Optional Rust | Packed algebra, reusable decompositions, multi-RHS, factorized/HC actions, geometry workspace |
| Backend integration | Visible same-solver fallback, cooperative cancellation, validated snapshot recovery |
| Further work | Wider scale and machine coverage, stability, application evidence |

Every solver output is independently checked for `P²=P`, `AP=0`, `PD=0`, and
preservation of cycle homology. Exact F2 algebra does not certify floating-point
geometry or the global optimum.

## Documentation, contribution, and citation

The [English documentation](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/index.md) provides installation, quickstart,
task guides, API and mathematical references, and development instructions:

- [Operator theory](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/MATHEMATICS.md): definition, kernel theorem, sections, stretch, geometry, and transport
- [Installation](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/getting-started/installation.md) and [quickstart](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/getting-started/quickstart.md)
- [Python API](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/INTERFACE.md)
- [Results and serialization](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/RESULT_MODEL.md)
- [Implementation architecture](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/ARCHITECTURE.md) and [solver contract](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/SOLVER_CONTRACT.md)
- [Development and validation](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/VALIDATION.md)
- [Implementation status and evidence](https://github.com/proffitteoy/homology-operator/blob/main/docs/README.md)

Report issues through [GitHub Issues](https://github.com/proffitteoy/homology-operator/issues).
See [Contributing](https://github.com/proffitteoy/homology-operator/blob/main/CONTRIBUTING.en.md) before submitting changes. The early-release
compatibility policy and publishing procedure are in [development](https://github.com/proffitteoy/homology-operator/blob/main/docs/en/VALIDATION.md#public-releases).

For research, cite the actual software version and commit. Machine-readable
metadata is provided in [CITATION.cff](https://github.com/proffitteoy/homology-operator/blob/main/CITATION.cff). The theory is tied to
[homology-operator-lab at a fixed commit](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88);
its code and validation results are not this package's runtime dependencies or
acceptance evidence. See [source and dependency notices](https://github.com/proffitteoy/homology-operator/blob/main/THIRD_PARTY_NOTICES.md).

## License and release status

The repository uses the [MIT License](https://github.com/proffitteoy/homology-operator/blob/main/LICENSE). The Python distribution provides
an OS-independent wheel and source archive. During 0.x, patch releases preserve
the public API; breaking changes require a minor-version increase and release
notes. Existing schema 1/2 snapshots remain covered by restoration tests. Native
ABI compatibility is checked independently by semantics version; the extension
is built separately from matching source.
