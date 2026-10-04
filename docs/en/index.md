# homology-operator


```{toctree}
:hidden:
:caption: Getting started

getting-started/installation
getting-started/quickstart
```

```{toctree}
:hidden:
:caption: Usage guides

guide/input-semantics
guide/single-scale
guide/filtration
guide/native
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
USAGE
Contributing <https://github.com/proffitteoy/homology-operator/blob/main/CONTRIBUTING.en.md>
Implementation and evidence <https://github.com/proffitteoy/homology-operator/blob/main/docs/README.md>
Source code <https://github.com/proffitteoy/homology-operator>
```


[![Reference checks](https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml/badge.svg)](https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml)
[![Native checks](https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml/badge.svg)](https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml)
[![GUDHI oracle](https://github.com/proffitteoy/homology-operator/actions/workflows/s5-oracle.yml/badge.svg)](https://github.com/proffitteoy/homology-operator/actions/workflows/s5-oracle.yml)


[中文](../index.md)

homology-operator constructs homology operators from based F2 boundary windows.
One projection supplies Betti numbers, class representatives, selected mass,
class distances, support, and stretch. Finite-filtration barcodes and tracking
come from transport between stage operators.

The Python reference uses only the standard library. Optional Rust operations
provide packed algebra, supported solvers and batch queries. General point-cloud
and Rips builders must be supplied by the caller.

## Install

Python 3.10+ is required. This is the source snapshot `0.0.2.dev0`, with no PyPI release.

```console
git clone https://github.com/proffitteoy/homology-operator.git
cd homology-operator
python -m pip install .
```

See [installation](getting-started/installation.md).

## First calculation

```python
from homology_operator import (
    ChainWindow, HomologyOperator, Matrix, ProjectionProblem, solve_projection,
)

window = ChainWindow(
    k=0, A=Matrix.zero(0, 2), D=Matrix.from_rows(((1,), (1,))),
    basis_previous=(), basis_current=("v0", "v1"), basis_next=("edge",),
    weights=(10, 1),
)
solution = solve_projection(ProjectionProblem(window))
if solution.projection is None:
    raise RuntimeError((solution.status, solution.diagnostics))
op = HomologyOperator(window, solution)

assert op.betti() == 1
assert op.same_class((1, 0), (0, 1))
assert op.selected_mass((0, 1)) == 10

```

The selected mass is 10 even though a homologous representative has mass 1;
selected_mass does not minimize class mass. Continue with the
[five-minute quickstart](getting-started/quickstart.md), or select a task from the navigation.

## Supported operations

| Operation | Python API |
| --- | --- |
| Single-scale homology and representatives | HomologyOperator.betti / class_representative / same_class |
| Same-P geometry | selected_mass / class_distance / support |
| Finite filtration | OperatorFamily.barcode / transport_rank / track_mass |
| Native reuse | PreparedMatrix / GeometryWorkspace / geometry_batch |

Class queries require cycles; raw project/apply_operator accept all chains.
Projection feasibility, current objective and global optimality remain separate.
See the [API](INTERFACE.md), [mathematical conventions](ARCHITECTURE.md), and
[result states](RESULT_MODEL.md).

## Performance

| Frozen comparison | Scope and conclusion |
| --- | --- |
| [S4](../S4_REPORT.md) | 27 configurations, 1,880 independent processes; some routes improve, while four time groups regress by more than 20% |
| [S5](../S5_REPORT.md) | 77 three-way correctness inputs, 2,840 formal processes; none of 68 comparable integrated groups has a paired 95% interval entirely below 1 |

Backend selection remains explicit. Measurements belong to the recorded source,
machine, input, budget and certificate; failures and regressions remain public.
GUDHI compares topology, while additional joint geometry has its own cost.
Frozen reports are retained in their original Chinese form.

## Development and citation

See [development](VALIDATION.md) for builds, tests and contribution requirements.
The project uses [MIT](../../LICENSE). For research, cite the actual version and
commit using [CITATION.cff](../../CITATION.cff).
