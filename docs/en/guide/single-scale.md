# Single-scale queries and geometry

[中文](../../guide/single-scale.md)

## Single-scale queries

Create `op` using the [quickstart](../getting-started/quickstart.md).

Let `L=I+P` and `m_w(x)=sum(w_i*x_i)` in the original coordinates.

| Method | Domain and result |
| --- | --- |
| `project(x)` / `apply_operator(x)` | Any chain; tuple `Px` / `Lx` |
| `is_cycle(x)` / `is_boundary(x)` | Any chain; Boolean |
| `kernel_basis()` / `betti()` | Basis of `ker(L)` / its dimension |
| `class_representative(z)` | Cycle; tuple `Pz` |
| `same_class(z,y)` | Two cycles; Boolean `Pz==Py` |
| `selected_mass(z)` | Cycle; `m_w(Pz)` |
| `class_distance(z,y)` | Two cycles; `m_w(P(z+y))` |
| `support(z)` | Cycle; original coordinate indices of `Pz` |
| `shared_support(z,y)` / `union_support(z,y)` | Two cycles; intersection / union indices |
| `readout(name, *args)` | Corresponding query domain; recorded `QueryResult` |
| `stretch(limits=None)` | `QueryResult` for the current projection's worst cycle mass ratio |
| `minimum_class_mass(z)` | Cycle; currently `Unavailable` |
| `to_result()` | Immutable `OperatorResult` snapshot |

Class queries reject noncycles. No implicit conversion turns a raw chain into a
homology class. `selected_mass` is not the true minimum mass of a class.
Feasibility, exact evaluation of the current stretch, and minimum possible
stretch over projections are separate facts.


## An exact operator on the six-edge complex

The complete graph on four vertices has three cycle directions. Filling face
$`012`$ removes one boundary direction, leaving two-dimensional $`H_1`$.
Use edge weights $`(2,4,2,3,4,2)`$ in order $`(01,02,03,12,13,23)`$.
The [mathematical example](../MATHEMATICS.md#6-a-complete-six-edge-example)
exhausts all four linear sections and proves that minimum stretch is $`9/8`$.
This code constructs the actual operator and reads topology and geometry together.

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

assert op.class_representative(z) == (1, 0, 1, 0, 1, 0)
assert op.class_representative(y) == (1, 0, 1, 1, 0, 1)
assert op.union_support(z, y) == (0, 2, 3, 4, 5)
assert sum(window.weights[i] for i in op.shared_support(z, y)) == 4
assert sum(window.weights[i] for i in op.union_support(z, y)) == 13
assert op.P @ op.P == op.P
assert window.A @ op.P == Matrix.zero(4, 6)
assert op.P @ window.D == Matrix.zero(6, 1)

unit_window = ChainWindow(
    k=window.k, A=window.A, D=window.D,
    basis_previous=window.basis_previous,
    basis_current=window.basis_current,
    basis_next=window.basis_next, weights=(1,) * 6,
)
unit_solution = solve_projection(
    ProjectionProblem(unit_window, requested_certificate_level="ExactOptimal"),
    "ExhaustiveExactSolver",
)
unit_op = HomologyOperator(unit_window, unit_solution)
assert unit_op.betti() == op.betti()
assert unit_solution.certificate_level == "ExactOptimal"
assert unit_solution.objective.value == Fraction(4, 3)

```

Here $`z`$ is triangle $`013`$ and $`y`$ is triangle $`023`$. Their individually shortest
representatives both cost eight. The selected representative for $`y`$ adds the
boundary of $`012`$ and costs nine. This lets the combined output cost nine rather
than twelve. Shared edges $`01,03`$ have total mass four; the union has mass thirteen.
All these readouts come from the same stored $`P`$, whose kernel realizes $`H_1`$.

The unit-weight variant has identical boundaries and Betti number, but a different
optimal stretch, $`4/3`$. These geometric values describe the chosen coordinate
costs. The proof and the four-section table are in the [operator theory](../MATHEMATICS.md).
The independent solver verifier establishes global optimality in this supported
small domain; the default feasible solver would not make that claim.
