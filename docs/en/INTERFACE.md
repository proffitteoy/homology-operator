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

`Matrix` stores rows as Python integer bitsets. Its constructor and `rows`
coordinate view retain binary tuples and the existing JSON format; read `rows`
once when exporting coordinates. Rank, kernel and image reuse a lazy stable
reduction; `solve_many(rhs)` shares a separate lazy image-coordinate basis with
`solve(b)`. Rank-only work does not allocate a row-transform matrix. Restored
matrices start with fresh process-local caches.

| `arithmetic` | Accepted weights | Geometry |
| --- | --- | --- |
| `ExactInteger` | Arbitrary-precision integers | Exact; objective ratios use `Fraction` |
| `ExactRational` (default) | Integers and `fractions.Fraction` | Exact rational arithmetic |
| `FloatingPoint` | Integers, floats, fractions converted to finite positive binary64 | Numerical `fsum`; no exact geometric optimality certificate |

The caller declares `weight_semantics` and `unit`. Positive costs do not imply
that weights are areas or volumes. Original coordinates determine geometry.
The optional [source mapping protocol](guide/input-semantics.md#source-mapping-and-location)
binds simplex vertices, original point IDs/coordinates, units, stages and periodic
lifts to input and filtration identities. `window.locate_chain(x, degree=0)`
locates a raw chain at degree offset -1/0/1, without treating it as a class.

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
| `locate_support(z, source_mapping_id=None)` | Cycle; source-bound location of `Pz`, or support only without a mapping |
| `shared_support(z,y)` / `union_support(z,y)` | Two cycles; intersection / union indices |
| `readout(name, *args)` | Corresponding query domain; recorded `QueryResult` |
| `stretch(limits=None)` | `QueryResult` for the current projection's worst cycle mass ratio |
| `minimum_class_mass(z, limits=None)` | Cycle; budgeted exact minimum mass, representative and boundary witness in a `QueryResult` |
| `to_result()` | Immutable `OperatorResult` snapshot |

Class queries reject noncycles. No implicit conversion turns a raw chain into a
homology class. `selected_mass` is not the true minimum mass of a class.
Feasibility, exact evaluation of the current stretch, and minimum possible
stretch over projections are separate facts.

The new `minimum_class_mass` implementation requires this source revision. It
enumerates the distinct elements of `im(D)` for the requested
cycle's coset, rather than all cycles or all linear sections. Independent boundary
columns give a bijection from binary coefficient vectors onto `im(D)`; Gray-code
updates visit each exactly once. Thus a complete search proves minimality, with
`2**rank(D)` candidate evaluations and linear coordinate work per candidate, in
addition to boundary reduction. Positive weights give the lower bound zero.
Integer/rational
weights are supported; floating weights and explicit `packed_word_limit` requests
return `Unavailable`. `limits` is a `ResourceLimits` with the existing defaults:
100,000 states, 10 seconds, and 1,000,000 logical matrix entries. Each evaluated
boundary counts as one state. Logical storage is conservatively bounded by
`2*n*p + 2*n*min(n,p) + 8*(n+p) + 2*m` entries; this is not a process RSS limit.
Wall time is cooperative, including final witness checking, without single-step
preemption. Input cycle validation precedes the query budget.

On completion, `value` is the true minimum, `exact=True`, and `details` contains
`representative=y`, `boundary_witness=b` in the original next-degree basis, and
`input_cycle=z`, with `Ay=0`, `Py=Pz`, and `Db=y+z`. Equal masses choose the
lexicographically smallest binary coordinate tuple. Complete enumeration or a
candidate of mass zero certifies `ExactOptimal` **for this class query**.
`lower_bound`, `upper_bound`, and `optimality_gap` then certify that class minimum.
This does not change P, the selected representative, or the solver certificate.

An interrupted query has `state="ResourceExhausted"`, `value=None`, and
`exact=None`. Its details retain a valid candidate, exact `candidate_mass`, the
universal lower bound 0, candidate upper bound, gap, `CertifiedInterval`, request
limits, reason, and resource usage. Even a zero candidate after a deadline does
not become a completed query. The zero class, including empty homology, otherwise
has the legitimate `Computed` minimum 0. A snapshot retains each class/limits
request and the latest result under `minimum_class_mass`.

```python
# Continue with the two-vertex window from the quick start.
minimum = op.minimum_class_mass((1, 0))
assert minimum.state == "Computed" and minimum.value == 1
assert minimum.details["representative"] == (0, 1)
assert minimum.details["boundary_witness"] == (1,)
assert op.selected_mass((1, 0)) == 10
```


## Fixed-boundary minimum filling

`minimum_filling(window, z, filling_window, *, limits=None, cancellation=None)`
minimizes upper-chain mass subject to `window.D c=z`. Import it and
`validate_minimum_filling` from `homology_operator`. This is a standalone query;
it does not select a projection or impose persistence birth/death pairing.

Reuse `ChainWindow` at degree k+1 for the upper costs: its `A` must equal
`window.D`, its `basis_previous` must equal `window.basis_current`, and its
`basis_current` must equal `window.basis_next`, including order. Its `D` may
describe higher boundaries but does not constrain this fixed-boundary problem.
Supply its own positive `weights`, explicit `unit`, and nonempty string
`source_metadata["source"]`. The original window's weights are never used for
filling mass. Geometric length/area/volume semantics require upper degree 1/2/3;
`unit` counting requires all weights to be 1. A declared source binds provenance,
but does not itself establish the physical correctness of measured weights.

```python
from homology_operator import ChainWindow, Matrix, minimum_filling, validate_minimum_filling

window = ChainWindow(0, Matrix.zero(0, 2), Matrix.from_rows(((1,), (1,))),
                     (), ("v0", "v1"), ("edge",), (10, 1))
upper = ChainWindow(1, window.D, Matrix.zero(1, 0), window.basis_current,
                    window.basis_next, (), (3,), unit="cost",
                    source_metadata={"source": "hand-derived edge cost"})
result = minimum_filling(window, (1, 1), upper)
assert result.state == "Computed" and result.value["mass"] == 3
assert validate_minimum_filling(window, (1, 1), upper, result)["optimality_verified"]
```

Noncycles and mismatched input/source contracts raise `ValueError`. Computed
`value` contains `chain`, its recomputed `boundary`, upper-basis support indices,
and exact `mass`; details contain equal optimal bounds and independently checked
evidence. Zero boundary has the certified zero filling, including empty spaces.
`Infeasible` has `value=None` and an exact dual obstruction. `ResourceExhausted`
has `value=None`, a checkpoint reason and optionally a feasible `details.candidate`;
it never certifies an optimum. `Unavailable` covers floating upper costs,
explicit packed-word requests, and more than 100,000 feasible fillings.
Integer/rational search enumerates `c0+ker(D)`; the finite replay cap means
`dim ker(D) <= 16`, except for zero-boundary and infeasibility proofs.
Ties minimize `sum(c_i*2**i)` in the original upper basis.

`limits` reuses `ResourceLimits`: states count evaluated fillings; time and
logical-entry guards are cooperative. Input validation/hashing and mandatory
independent verification have separate costs. There is no native filling solver
or hard RSS/preemption guarantee. See [certification](SOLVER_CONTRACT.md#fixed-boundary-filling-certificates)
and [result binding](RESULT_MODEL.md#standalone-filling-results).

## Finite-pair optimal volume

`family.optimal_volume(reference, filling_window=None, *, limits=None,
cancellation=None)` minimizes the upper-chain mass for a certified finite H1 or
H2 pair. It requires a face-first `simplex_source` and an exact feature reference
from this family's `features()`. Equal scales retain their event order, including
the explicit `AfterInsertion`/`EmptyInitial` stage convention.

For birth/death event stages b,d, require death coefficient 1, permit other upper
simplices only at stages strictly between b and d, set boundary coefficients at
k-simplices strictly between b and d to zero, and require birth coefficient 1.
All vectors use the original ordered bases of `family.windows[d]`. The objective
is upper mass, not boundary mass. This is the F2 support-count version of
[Obayashi 2018, section 4, Definitions 2/3](https://doi.org/10.1137/17M1159439)
for unit weights; arbitrary positive rational costs are an explicit extension.
The approved definition and compatibility argument are pinned in
[D-GQ1/T-GQ1](https://github.com/proffitteoy/homology-operator-lab/blob/d1c76bc7ed276a7a65b7aab97c4fbfcdad2530da/docs/proof/PROOF.md#D-GQ1).

`filling_window` is the same degree-k+1 cost input as for
[fixed-boundary filling](#fixed-boundary-minimum-filling), aligned to the death
window's D and ordered bases. It must declare positive costs, a unit, and
`source_metadata["source"]`. If either degree has a source mapping, both must
agree on dataset, original vertex IDs/coordinates, embedding, periods, stage,
scale/order, and shared simplex records. An abstract source needs no embedding.

```python
# family is a supported simplex family; reference has finite death.
from homology_operator import ChainWindow, Matrix, validate_optimal_volume

death = family.windows[reference["death_stage"]]
upper = ChainWindow(death.k + 1, death.D, Matrix.zero(death.p, 0),
                    death.basis_current, death.basis_next, (), (1,) * death.p,
                    unit="simplices", source_metadata={"source": "unit counting"})
result = family.optimal_volume(reference, upper)
if result.state == "Computed":
    assert validate_optimal_volume(family, reference, upper, result)["optimality_verified"]
    assert death.D.apply(result.value["chain"]) == result.value["boundary"]
```

This example assumes an unmapped family; mapped inputs supply the matching upper
mapping as well. Computed values contain `chain`, `boundary`, `support`, `mass`,
`filling_simplices`, `boundary_simplices`, and both `filling_location` and
`boundary_location`. Locations include original IDs and lifted coordinates when
supplied, and explicitly missing coordinates otherwise. The Boolean
`same_history_class` independently checks the resulting boundary against the
preselected historical generator in the birth-stage quotient. Pair constraints
permit a different historical class; this flag is informative, not an added
optimization constraint. Neither this query nor its output changes P or PH.

An infinite interval returns `EmptyDomain`, `value=None`, `exact=None`, and
`details.applicability="NotApplicable"`, because it has no finite death anchor.
Other degrees, missing simplex provenance, floating costs, explicit packed-word
requests, or constraint nullity above 16 return `Unavailable`. Malformed/foreign
references and mismatched upper inputs raise `ValueError`. Cooperative budgets
and cancellation return `ResourceExhausted`; any `details.candidate` is feasible
only, with no optimal bound. States count evaluated feasible fillings. Search
and independent replay support at most 65,536 candidates; ties minimize packed
original upper coordinates. Input/history certification, source binding and
independent verification are outside the search time/entry budget. No native
solver, general scalability or hard RSS limit is claimed.

The result is standalone: save the family, reference and upper input alongside
`QueryResult.to_dict()`. On untrusted recovery call `validate_optimal_volume`;
JSON decoding alone does not verify semantics. See
[certification](SOLVER_CONTRACT.md#finite-pair-volume-certificates) and
[binding](RESULT_MODEL.md#finite-pair-volume-results).

## Finite filtrations

`OperatorFamily(scales, windows, operators, weight_policy="Inherited",
duplicate_policy="OrderedStages", terminal_extension="Constant", cache_limit=64,
kernel_cache_byte_limit=16777216, simplex_source=None)`
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
`cache_limit` bounds entries in each LRU query cache and the stage-kernel LRU;
0 disables all of them. `kernel_cache_byte_limit` additionally bounds the shared
charge for retained Python kernel bases/coordinate decompositions and native
kernel matrices, preparations and transport workspaces. It defaults to 16 MiB;
0 disables stage retention. Charges use Python container/integer sizes and
native payload/row overhead estimates. Eviction removes all representations of
that stage together; oversized stages are computed without retention. Repeated
queries may therefore recompute a kernel. Family queries do not populate the
operator's kernel or native geometry workspace. Caller-owned input/action caches,
temporary computation, requested readouts and allocator capacity are outside
this budget; it is not a hard process RSS cap. Runtime cache policies are absent
from identities and all snapshot schemas; recovery uses the defaults.

Default family snapshots use schema 2 with shared boundary/basis storage. Legacy
schema 1 is readable and reissued at its original version; use
`to_result(schema_version=1)` to request old-format output without the new
historical basis. Feature queries or an explicit simplex source use schema 3;
they cannot be down-converted to schemas 1/2. Single-scale schema remains 1. Recovery independently checks
the family and stored readouts. See [filtration guide](guide/filtration.md).

`features()` returns a `QueryResult` containing stable references to the existing
historical interval generators. `resolve_feature(reference, stage)` returns the
original chain representative, kernel coordinates, target basis and six identities;
an inactive interval returns `NoClass`. `feature_pairing(reference)` returns
certified birth/death simplices, or `Unavailable` without a simplex source.
References bind the entire family/run and full generator history, including an
occurrence index for repeated endpoints. See [feature references and simplex
sources](guide/filtration.md#feature-references-and-simplex-sources) for input format,
numbering, certificate and resource boundaries.

## Birth-pair optimal 1-cycle

`family.optimal_1_cycle(reference, *, limits=None, cancellation=None)` minimizes
edge mass **at the reference's birth stage**, in its certified historical class.
It supports H1, the complete one-simplex insertion source used by
`feature_pairing`, and exact integer/rational costs: `weight_semantics="unit"`
requires every cost to be 1; `"euclidean_length"` requires a source embedding
and verifies each squared edge length against its lifted coordinates. The
embedding's length unit must match the weights. General irrational lengths
stored as floating point are currently `Unavailable` for this exact query.
Both finite and terminally surviving features are supported, with either stage
convention and repeated scales. Stage indices, the simplex order, and the full
history remain authoritative.

This is the restricted `BirthPairOptimalCycle` objective with feasible set
`BirthHistoricalClass`: all cycles in `z_birth + im(D_birth)`, including the birth
edge. It anchors an existing feature, unlike `FixedClassMinimum` with an arbitrary
caller cycle/stage. It also differs from minimizing **all** birth-edge-containing
cycles: that larger set can select another historical class. See the
[proof and HomCloud comparison](guide/filtration.md#birth-pair-cycle-contract).

The existing `QueryResult` carries the birth operator's six identities. Its
Computed value contains the F2 `chain`, original-coordinate `support`, `mass`,
an unordered support collection `edges` in simplex-source vertex IDs, and
`location` from `window.locate_chain(chain)`. Mapped inputs include original point
IDs/coordinates and support components; unmapped inputs retain support only.
These are F2 support edges, possibly disconnected, without a polygon/traversal
claim. Details bind the feature/history, source, pairing, stage, weight/unit,
objective, original-coordinate tie policy, and `problem_id`.

The exact reference enumerates the boundary image, with rank at most 16 (at most
65,536 distinct chains). Equal masses choose the smallest original-coordinate
bitset `sum(chain[i]*2**i)`. Computed includes equal lower/upper bounds,
`ExactOptimal`, and independent full-coverage replay. `ResourceExhausted` has no
value or optimal bound; it may retain a verified feasible `details.candidate`.
Unsupported degree/source/cost/replay domain or packed-word requests return
`Unavailable`. Feature-history failures preserve their missing state. Malformed
or foreign references, inconsistent unit costs or measured lengths raise ValueError.
Valid references always have a feasible chain; this query has no empty-domain or
infeasible fallback.

`ResourceLimits`/`CancellationToken` apply at search checkpoints. Input binding,
full-history construction, independent replay and location have additional costs;
these limits are neither hard preemption nor RSS bounds. The result is standalone
and does not enter family snapshots. After a QueryResult JSON round trip, call
`validate_optimal_1_cycle(family, reference, result)` (public package import) to
replay its semantics. Decoding alone is not certification. The complete runnable
example is [examples/filtration.py](../../examples/filtration.py); no new runtime
dependency or native solver is required.

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
| `NativeFeasibleSolver` | StableBasisOrder/Feasible; multiword chain spaces, subject to logical-entry budgets |
| `NativeFactorizedSolver` | Same-P Factorized/HC action; `matrix_free_output=True`; no optimality certificate |
| `PreparedMatrix` | Multiword packed stable decomposition and reusable multi-RHS; not a projection solver |
| `GeometryWorkspace` / `geometry_batch` | Same-P cyclic geometry for Matrix and Factorized/HC; six-identity binding |

`PreparedMatrix(matrix, full=False, diagnostics=False)` retains the original and
reduced packed rows for rank, RREF, kernel, image and application. It omits the
square row transform: solve, membership and inverse-row requests then raise
`ValueError`. Default `full=True` retains those operations. Fill tracking is
optional; with `diagnostics=False`, `peak_nonzero_bits` is `None`. Default
diagnostics remain enabled for compatibility. Solver-internal preparations
disable diagnostics and use a bounded per-request cache.

HC construction computes H/C in Rust from prepared A/D, without a dense P or
per-column Python calls. `apply_batch` and implicit `geometry_batch` prepare one
operator-owned workspace lazily and reuse its packed action and scratch. Raw
application accepts noncycles; geometric queries still require cycles. Native
handles and caches do not enter snapshots. Rebuild the extension from matching
source: the adapter requires binding API 3 and F2 semantics 1.

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

`Matrix.from_sparse_columns(columns, nrows)` accepts the nonzero row indices of
each column, including empty columns. Indices must be unique integers in range;
duplicates, booleans and out-of-range indices are rejected. No dense coordinate
tuples are needed to construct a boundary matrix.

Optional native algebra retains immutable matrix handles between products,
decomposition, HC construction, transport and batch queries. The reference packed
view is decoded lazily for coordinates, identity hashing, independent verification
and JSON. Reference-only construction does not load the extension.

Native matrices of at least eight words per row start with sorted sparse column
indices when their count fits within half the dense word count. Actual elimination
fill triggers a one-way switch to contiguous packed rows; small/dense matrices use
packed rows directly. `PreparedMatrix.statistics()` adds `sparse_input`,
`sparse_reduced`, and `sparse_to_dense_switches`. `stored_words` counts u64 slots or
usize index slots, excluding row headers/capacity; it remains distinct from RSS.
The threshold is a storage rule, not a promise that every sparse input is faster.
