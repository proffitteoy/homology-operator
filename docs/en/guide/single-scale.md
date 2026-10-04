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
