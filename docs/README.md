# homology-operator documentation

[Online documentation](https://proffitteoy.github.io/homology-operator/) · [中文](index.md) · [Contributing](../CONTRIBUTING.md)

English is the default documentation language. The site root serves English;
Chinese documentation is available at [/zh/](https://proffitteoy.github.io/homology-operator/zh/).
The existing [/en/](https://proffitteoy.github.io/homology-operator/en/) URLs remain available.

| Task | Start here |
| --- | --- |
| Understand the operator and its mathematical meaning | [Operator theory](en/MATHEMATICS.md): kernels, linear sections, stretch, geometry, and persistent transport |
| Install and run the first example | [Installation](en/getting-started/installation.md), [quickstart](en/getting-started/quickstart.md) |
| Run a complete joint topology and geometry example | [Exact six-edge operator](en/guide/single-scale.md#an-exact-operator-on-the-six-edge-complex) |
| Construct inputs and query a single scale or filtration | [Python API](en/INTERFACE.md) |
| Build Rust, use packed algebra and batch queries | [Native guide](en/guide/native.md) |
| Interpret states, identities, and snapshots | [Result model](en/RESULT_MODEL.md) |
| Understand the operator, transport, and barcode algorithms | [Mathematics and architecture](en/ARCHITECTURE.md) |
| Select a solver and understand its domain and certificates | [Solver contract](en/SOLVER_CONTRACT.md) |
| Develop, test, and build | [Validation](en/VALIDATION.md), [test inputs](FIXTURES.md) |
| Check platform support | [Platforms](en/platforms.md) |

The mathematical starting point is the operator itself: construct L=I+P on the
original chain space, realize homology through its kernel, read geometry from the
same action, and realize the persistence module through transport between kernels.
The formal theory, API, and implementation architecture have separate entry points.

The product includes a standard-library Python interface and an optional Rust
backend, with joint readouts from the same P and independent certification.
Rust provides packed algebra, reusable decompositions, Factorized/HC actions,
supported solvers, and geometric batch queries. The Python package version is
0.0.2 and uses [MIT](../LICENSE). Check the [PyPI version record](https://pypi.org/project/homology-operator/0.0.2/)
for upload status; the compatibility policy and Trusted Publisher procedure are
in [public releases](en/VALIDATION.md#public-releases).
Strict bilingual builds on main publish GitHub Pages automatically; pull requests
only run build checks.
