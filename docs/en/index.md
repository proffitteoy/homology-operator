# homology-operator

```{toctree}
:hidden:
:caption: Operator theory

MATHEMATICS
```

```{toctree}
:hidden:
:caption: Getting started

getting-started/installation
getting-started/quickstart
```

```{toctree}
:hidden:
:caption: Guides

guide/input-semantics
guide/single-scale
guide/filtration
guide/native
USAGE
```

```{toctree}
:hidden:
:caption: Reference

INTERFACE
RESULT_MODEL
ARCHITECTURE
SOLVER_CONTRACT
platforms
```

```{toctree}
:hidden:
:caption: Project

VALIDATION
Contributing <https://github.com/proffitteoy/homology-operator/blob/main/CONTRIBUTING.md>
Source <https://github.com/proffitteoy/homology-operator>
```

[![Reference checks](https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml/badge.svg)](https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml)
[![Native checks](https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml/badge.svg)](https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml)
[![GUDHI oracle](https://github.com/proffitteoy/homology-operator/actions/workflows/oracle.yml/badge.svg)](https://github.com/proffitteoy/homology-operator/actions/workflows/oracle.yml)

[中文](../index.md)

## A binary operator that realizes homology as its kernel

This project introduces a binary homology operator on the original chain space.
Given a finite based chain window and positive coordinate weights, construct a
linear projection $P$ and operator $L=I+P$:

$$
C_{k+1}\xrightarrow{D}C_k\xrightarrow{A}C_{k-1},\quad AD=0,
\qquad P=(I+DU)(I+GA),\quad L=I+P.
$$

The generalized inverses satisfy $AGA=A$ and $DUD=D$. Its central relation is

$$
\boxed{\ker L=\operatorname{im}P\cong H_k(C;\mathbf F_2).}
$$

Each kernel vector is the unique selected cycle representative of its class.
For cycles, $Pz$ preserves the class and $P(z+y)=Pz+Py$; the selection rule
therefore couples all class representatives. Weighted action of the same $P$
gives mass, distance, and shared support. Projected transport between kernels
realizes the entire persistence module and its barcode.

Read [operator theory](MATHEMATICS.md) for definitions, construction, and proofs,
or run the [complete six-edge example](guide/single-scale.md#an-exact-operator-on-the-six-edge-complex).

## One operator, three readouts

| Readout | Mathematical object | Questions it answers |
| --- | --- | --- |
| Homology | $\ker L$, $Pz$ | How many independent classes? Which class? Where is its selected representative? |
| Weighted geometry | $m_w(Pz)$, $m_w(P(z+y))$, support intersection/union | What is its realization cost? How is a difference class realized? Which coordinates are shared and cancel? |
| Persistence | $T_{ij}=P_jJ_{ij}|_{\ker L_i}$ | How do classes travel, merge, or die across stages? What are their intervals? |

Zero class distance means exactly equal homology classes. Positive distances
measure the selected realization cost of the difference class. Units come from
input weights. The eigenvalues of $L$ are only $0,1$; weighted action supplies
additional geometry.

## Minimum stretch controls every linear combination

Legal projections need not be unique. Selecting by worst cycle mass ratio gives

$$
\Gamma_w(P)=\max_{0\ne z,\ Az=0}\frac{m_w(Pz)}{m_w(z)},\qquad
\Gamma_*=\min_{P\ \mathrm{legal}}\Gamma_w(P).
$$

This equals the minimum-stretch linear section problem: choose representatives
for all classes while preserving all linear relations. For Betti number
$\beta>0$, $1\le\Gamma_*\le\beta$.

The six-edge complex has minimum nonzero class masses $(8,8,9)$.
A minimum-total-mass basis produces $(8,8,12)$ with stretch $4/3$; the
minimum-stretch operator produces $(8,9,9)$ with stretch $9/8$.
Cancellation of shared support explains the choice. The exhaustive four-section
table, matrix, and proof are in the [mathematical example](MATHEMATICS.md#6-a-complete-six-edge-example).

## Run this operator

```python
from fractions import Fraction
from homology_operator import (
    ChainWindow, HomologyOperator, Matrix, ProjectionProblem, solve_projection,
)

window = ChainWindow(
    k=1,
    A=Matrix.from_rows((
        (1, 1, 1, 0, 0, 0),
        (1, 0, 0, 1, 1, 0),
        (0, 1, 0, 1, 0, 1),
        (0, 0, 1, 0, 1, 1),
    )),
    D=Matrix.from_rows(((1,), (1,), (0,), (1,), (0,), (0,))),
    basis_previous=("v0", "v1", "v2", "v3"),
    basis_current=("01", "02", "03", "12", "13", "23"),
    basis_next=("012",),
    weights=(2, 4, 2, 3, 4, 2),
)
solution = solve_projection(
    ProjectionProblem(window, requested_certificate_level="ExactOptimal"),
    "ExhaustiveExactSolver",
)
if solution.projection is None:
    raise RuntimeError((solution.status, solution.diagnostics))
op = HomologyOperator(window, solution)

z = (1, 0, 1, 0, 1, 0)
y = (0, 1, 1, 0, 0, 1)
assert solution.certificate_level == "ExactOptimal"
assert solution.objective.value == Fraction(9, 8)
assert op.betti() == 2
assert op.selected_mass(z) == 8
assert op.selected_mass(y) == 9
assert op.class_distance(z, y) == 9
assert op.shared_support(z, y) == (0, 2)
assert op.stretch().value == Fraction(9, 8)

```

The projection undergoes independent legality and optimality verification.
The default `FeasibleSolver` constructs a legal operator with the same readout
semantics. Domains, search cost, and certificates are in the [solver contract](SOLVER_CONTRACT.md).
`selected_mass` measures the selected representative; true minimum class mass
is currently unavailable as a public query.

## Installation and backends

Python 3.10+ is required. The reference runtime uses only the standard library.
The current version is a source development snapshot, `0.0.2.dev0`.

```console
git clone https://github.com/proffitteoy/homology-operator.git
cd homology-operator
python -m pip install .
```

The optional Rust backend provides packed algebra, reusable decompositions,
Factorized/HC actions, supported solvers, and batch queries. Both backends
implement the same operator contract. Callers supply based boundary windows;
general point-cloud, Rips, and complex-building frontends are external.
See [installation](getting-started/installation.md) and the [native guide](guide/native.md).

## Continue by question

- [Operator theory](MATHEMATICS.md): definition, kernel theorem, projection space, stretch bounds, geometry, and transport proofs.
- [Input semantics](guide/input-semantics.md) and [quickstart](getting-started/quickstart.md): turn boundary data into an operator.
- [Single scale and geometry](guide/single-scale.md), [finite filtrations](guide/filtration.md): read representatives, distances, and tracking.
- [API](INTERFACE.md), [solver contract](SOLVER_CONTRACT.md), [result model](RESULT_MODEL.md): domains, certification, identities, and recovery.
- [Architecture](ARCHITECTURE.md) and [development validation](VALIDATION.md): modules, tests, and documentation builds.

The project uses the [MIT License](../../LICENSE). For research citations, record
the actual software version and commit; see [CITATION.cff](../../CITATION.cff).
