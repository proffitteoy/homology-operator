# Python API

[中文](../INTERFACE.md)

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

## Solving and validation

Create `ProjectionProblem(window)` and call `solve_projection`. The default
`FeasibleSolver` constructs a deterministic projection without minimizing stretch.
Always check `solution.projection` before constructing `HomologyOperator`:

```python
# Continue after the window definition in the quick start.
from homology_operator import HomologyOperator, ProjectionProblem, solve_projection

solution = solve_projection(ProjectionProblem(window))
if solution.projection is None:
    raise RuntimeError((solution.status, solution.diagnostics))
op = HomologyOperator(window, solution)
```

| Solver | Supported scope |
| --- | --- |
| `FeasibleSolver` | General based windows; exact or floating weights; feasibility only |
| `ExhaustiveExactSolver` | Small exact-weight problems with complete search and certificate replay limits |
| `GreedyCertifiedSolver` | Exact weights; deterministic cycle enumeration and certified bounds |
| `Rank2ExactSolver` | Exact weights, Betti number 2, explicitly validated structural conditions |
| `StructuredFamilySolver` | Declared CyclicTrace family, m=2/3/4, equal exact positive weights |

The four optimization solvers support explicit native selection through their
`Native...` names or existing solver classes with `native=True`. Native selection
preserves each solver's input and certification domain. Unknown or unsupported
requests return `Unavailable`.

`solve_projection(problem, "NativeFeasibleSolver", fallback=True)` can explicitly
fall back to the corresponding reference solver. Requested/selected backend and
fallback reason are recorded in `resource_usage.backend_selection`. The same
policy applies to supported native optimization solvers. Factorized matrix-free
output has no reference fallback to an explicit matrix.

Before entering an operator, every candidate is independently validated for
`P²=P`, `AP=0`, `PD=0`, and `z+Pz∈im(D)` on a cycle basis. The first three
equalities alone are insufficient: a zero projection can satisfy them and lose
nonzero homology. Global optimality additionally requires supported independent
certificate replay. See the [solver contract](SOLVER_CONTRACT.md).

## Single-scale queries

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

## Finite filtrations

`OperatorFamily(scales, windows, operators, weight_policy="Inherited",
duplicate_policy="OrderedStages", terminal_extension="Constant", cache_limit=64)`
accepts a nonempty ordered sequence in one degree. Basis identifiers establish
inclusions in the previous, current, and next spaces; chain-map conditions are
validated. `Inherited` requires inherited coordinate weights; explicit
`Variable` allows changed weights with compatible units and semantics.

Repeated scales retain separate ordered stages. Barcodes use half-open stage
intervals with multiplicity; `death_stage=None` means survival under constant
terminal extension. A cross-stage interval at the same scale remains explicit.

The main result comes from `T_ij=P_j J_ij|ker(L_i)`. `barcode()` reads adjacent
transport; `transport_rank(i,j)` reads one interval rank. `rank_table()` requests
the full s(s+1)/2 table. `barcode_basis()` requests a historical interval basis
with corrected dying generators, original chain representatives, and identities.
Those larger outputs are explicit requests and can have quadratic cost.

`track_class`, `track_mass`, and support tracking accept source cycles and use
the target projection. A dead class yields a zero chain, zero mass, and empty
support. Failed stages remain missing; a failed rank is never an empty barcode.
`cache_limit` bounds entries in each LRU query cache, not bytes or process RSS.

Default family snapshots use schema 2 with shared boundary/basis storage. Legacy
schema 1 is readable and reissued at its original version; use
`to_result(schema_version=1)` to request old-format output without the new
historical basis. Single-scale schema remains 1. Recovery independently checks
the family and stored readouts. See [filtration guide](guide/filtration.md).

## Optional Rust extension

The locked build uses Rust 1.98.1, PyO3 0.29.3, and maturin 1.15.0. Native CI
covers Windows x64/MSVC with Python 3.10 and Linux x64 with Python 3.12. Other
combinations are outside that matrix. Windows also needs MSVC build tools.
From the repository root in PowerShell:

```powershell
uv sync --locked --python 3.10
$pythonPath = uv run --locked python -c "import sys; print(sys.executable)"
$env:RUSTUP_TOOLCHAIN = '1.98.1'
uv tool run --from maturin==1.15.0 maturin build --manifest-path native/Cargo.toml --release --locked --interpreter $pythonPath --out .task-artifacts/native-wheels
$wheel = Get-ChildItem .task-artifacts/native-wheels/*.whl | Sort-Object LastWriteTime -Descending | Select-Object -First 1
uv pip install --python $pythonPath $wheel.FullName
```

Use `uv run --locked --no-sync ...` afterward to retain the separately installed
extension; reinstall it after another sync. `backend_info()` in
`homology_operator.native` reports actual availability and extension provenance.

| Native entry | Scope |
| --- | --- |
| `NativeFeasibleSolver` | StableBasisOrder/Feasible; each chain space at most 64 dimensions |
| `NativeFactorizedSolver` | Same-P Factorized/HC action; `matrix_free_output=True`; no optimality certificate |
| `PreparedMatrix` | Multiword packed stable decomposition and reusable multi-RHS; not a projection solver |
| `GeometryWorkspace` / `geometry_batch` | Same-P cyclic geometry for Matrix and Factorized/HC; six-identity binding |

Native geometry does not support CyclicAction. Integer mass uses checked u64
where possible; noninteger rational weights, large integers, and overflow use
explicit exact Python fallback. Floating geometry retains binary64 `fsum`.
Workspace reuse does not alter saved snapshots or query history and does not
provide a concurrent sharing or RSS limit guarantee.

Missing or incompatible extensions produce `Unavailable` for supported solver
and batch entries. Direct packed tools and workspace creation require an
extension and raise `ImportError` when missing. There is no implicit fallback.

## Budgets and cancellation

`ResourceLimits` provides state, wall-time, and logical matrix-entry limits.
Checks are cooperative checkpoints, not hard process memory or step preemption.
Independent validation, certificate replay, serialization, and recovery have
their own costs and cannot be omitted from complete timing.

`CancellationToken` can be supplied to `ProjectionProblem` and supported native
geometry. Cancellation is reported as `ResourceExhausted` with a reason, and any
retained candidate must still pass independent validation. Not all algebra or
filtration operations accept a cancellation token; see the [API](INTERFACE.md).

See [result serialization](RESULT_MODEL.md), [solver certificates](SOLVER_CONTRACT.md), and the [quickstart](getting-started/quickstart.md).
