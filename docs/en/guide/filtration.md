# Finite filtrations and tracking

[中文](../../guide/filtration.md)

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
the family and stored readouts. See [filtration guide](../ARCHITECTURE.md).

## Feature references and simplex sources

```python
references = family.features()
if references.state == "Computed":
    for reference in references.value:
        generator = family.resolve_feature(reference, reference["birth_stage"])
        assert generator.state == "Computed"
        assert generator.identity == family.stage(reference["birth_stage"]).identity
        pairing = family.feature_pairing(reference)
        # Algebra-only windows explicitly return Unavailable for simplex provenance.
```

`features()` reuses the death-corrected `barcode_basis()` histories. References
distinguish repeated endpoints by a zero-based occurrence in stable elimination
order. Birth-prefix elimination retains older independent images first, using
the original stable kernel-basis order for ties; dependent dying histories are
corrected backwards by earlier surviving histories. `AdjacentBirthPrefixV1`
names this generator choice. Equal scales never identify different stages or
generators. Empty homology yields `Computed` with an empty tuple. Failed stages
propagate `Unavailable`/`ResourceExhausted`. Malformed, replaced, or foreign-family
references raise `ValueError`; inactive stages return `NoClass` with `NotBorn` or
`Dead` in details. The original barcode and class-tracking semantics are unchanged.

An optional source supplies the complete face-first simplex insertion order and
its coordinate labels. For example, three H0 stages after inserting two vertices
and their edge can be bound with:

```python
from dataclasses import replace

source = {
    "stage_convention": "AfterInsertion",
    "simplices": [
        {"vertices": (0,), "label": "v0"},
        {"vertices": (1,), "label": "v1"},
        {"vertices": (0, 1), "label": "edge"},
    ],
}
# family.windows must already describe exactly these three prefixes.
bound_family = replace(family, simplex_source=source)
```

Vertices are strictly increasing, distinct nonnegative integers; events and
labels are unique, and every face must occur before its coface, including at equal
scales. No sorting, automatic face insertion, filtration repair or PH result is
accepted in place of the supplied stream. Each window's three bases must equal
the relevant prefix simplices (coordinate order may vary); both A and D are
independently rebuilt from faces and compared. Weights retain the existing family
policy. Original scales remain in `family.scales` and feature endpoints. The
source, total order and convention enter filtration identity.

`AfterInsertion` has N stages: stage 0 is after event 0. This matches research
`dynamic.simplex_filtration`. `EmptyInitial` has N+1 stages: stage 0 is empty,
event 0 first appears at stage 1. This matches research `incremental.replay`.
The stage offset is explicit and never inferred from equal scales. An empty
stream is supported with one `EmptyInitial` stage. General algebraic windows
without this source retain valid feature queries and unavailable simplex pairing.

`feature_pairing` binds each reference to actual vertex tuples and labels,
records the source hash and convention, and uses `None` for an infinite death.
It does not merge separately computed PH results by endpoints. The source is the
input trust root: internal boundary/history consistency does not authenticate an
external data provider. Schemas 3 references and sources restore together and
reject changed sources or saved pairings; legacy snapshots keep their existing
format until feature APIs are requested.

## Birth-pair cycle contract

For an H1 reference with birth b, let z be its certified historical representative
at b. `optimal_1_cycle` searches exactly `z + im(D_b)` in the original edge
coordinates and returns the least `(mass, coordinate_bitset)`. It does not change
the interval generator, P, transport, barcode, or the default representative.
`FixedClassMinimum` permits an arbitrary cycle/stage; this birth-pair specialization
requires a genuine one-simplex birth, its total order, and the whole chosen
interval history. The result explicitly records `BirthHistoricalClass`, rather
than claiming an unrestricted birth-pair or birth-edge optimum.

**Feasibility and history.** The source protocol independently rebuilds all
boundaries. Face-first insertion means no triangle already present at b can
contain the new birth edge. Every vector in `im(D_b)` therefore has zero on that
edge, while z has coefficient one. Every candidate is a cycle and uses that edge.
Conversely, every cycle in this fixed historical class is z plus such a boundary,
so enumerating an independent image basis covers the entire feasible set exactly
once. Independent verification reduces raw D columns again, checks the birth
class and cycle/edge conditions, and replays all exact masses/ties. Equal lower
and upper bounds follow from this finite coverage, not from the search counter.

The [complete historical certificate](#historical-certificate-and-cost) establishes
the interval-module isomorphism first. A birth-class boundary remains a boundary
under all forward inclusions; hence a candidate has the same class as every
selected historical vector and dies at the certified death when finite. The
validator additionally checks these residuals against each stage's raw boundary
image and the actual death boundary space. A future face is never used to justify
birth-class membership. Thus neither containing the birth edge nor vanishing at
some later stage replaces full history certification.

**Shortest-path boundary.** With positive edge costs, any F2 cycle containing a
specified edge contains an endpoint path after deleting that edge. Keeping this
path and the edge cannot increase mass; a shortest such path solves the larger
birth-edge-only problem. It solves our historical-class problem only with an
additional equivalence certificate. For example, if beta1 at birth equals one,
any difference of two birth-edge cycles avoids the new edge, comes from the
previous stage, and belongs to its zero homology. Their classes therefore agree.
With more surviving classes this argument fails, even if faces are filled later.
The present implementation always enumerates the certified fiber and uses no
shortest-path shortcut.

**HomCloud scope.** The frozen unit-cost comparisons in
[optimal_cycles.json](../../../tests/fixtures/optimal_cycles.json) execute the
unchanged Python `search` functions from
[HomCloud 5.4.0 source](https://files.pythonhosted.org/packages/2c/14/0e520f2019bbea4e027adb464cd19055323bd892c220b03190685e32d058/homcloud-5.4.0.tar.gz),
`homcloud/optimal_one_cycle.py`. The archive and file SHA-256, entry and exact
simplex order are recorded in the fixture. This is source-function replay; the
compiled extension and public Pair integration were not executed. Both inputs
use F2 edge supports, the same insertion order, birth edge, birth prefix and unit
costs. Triangle/previously-filled-face examples have beta1=1 and equal feasible
sets, so their optimal values agree; tie support equality is not promised.
A separate example has an older class: HomCloud returns a 3-edge birth cycle
while the chosen death-compatible history requires 4 edges. That row compares
representatives of different objectives and makes no equality/speed claim.

HomCloud's default source path takes no death or historical-class constraint;
its separate weighted graph path uses filtration values as costs and rejects
repeated birth values. Our actual-length query separates filtration scales,
total order and geometric costs, so it is not claimed as a reproduction of that
weighted mode. Research definitions and the original counterexample are fixed in
[D-GQ1/T-GQ1](https://github.com/proffitteoy/homology-operator-lab/blob/d1c76bc7ed276a7a65b7aab97c4fbfcdad2530da/docs/proof/PROOF.md#D-GQ1).
This product test uses directly specified simplices and all-chain enumeration;
research code is not a product dependency or imported validation score.

## Stable-volume definition and guarantee

For a finite pair (b,d), set

```math
\mathcal A_{\varepsilon,q}=\{\sigma_j:\dim\sigma_j=q,\ j<d,
  r_j\ge r_b+\varepsilon\}.
```

Minimize the positive upper cost of
`c = sigma_d + sum(t_omega * omega)` with free simplices in
`A_(epsilon,k+1)` and zero boundary rows in `A_(epsilon,k)`.
There is no condition on the birth coefficient. These are precisely the F2
constraints of [Obayashi 2023](https://doi.org/10.1007/s41468-023-00119-8),
Definition 6, p.691. The affine solver solves these rows, enumerates the entire
kernel fiber, and orders equal masses by the smallest original-coordinate
bitset. Independent replay rebuilds faces from the simplex source and computes
its own elimination and kernel; it does not use the search's solve/kernel cache.
Positive exact costs and complete coverage establish the declared optimum.

The stronger robustness label uses only the certified polygon-fan category of
[research reference 4349866166962e25d515fa1cec1f0460e7f659a4](https://github.com/proffitteoy/homology-operator-lab/blob/4349866166962e25d515fa1cec1f0460e7f659a4/candidates/minimum-stretch/geometry_queries.py).
Strict convexity certifies that triangles `(v0,vi,vi+1)` embed a pure contractible
disk. Their dual incidence, including the outside node, propagates a forced
death coefficient along zero-constrained edges; remaining components can be
zero. Positive costs make extra components unfavorable. For unit costs this is
the tree stable volume of Definition 3, p.682, by Theorem 4.1, p.691. The common
robust-part interpretation then uses Theorem 3.1, p.683, with the exact
[API assumptions](../INTERFACE.md#stable-volume). No general-k robustness theorem
is inferred from exact binary optimization.

In the square fixture, outer edges have value 1, the diagonal value 2 and the
two triangles values 3 and 4. The outer H1 pair has stable support both triangles
for `0 < epsilon <= 1`, and only the death triangle for `epsilon > 1`. The
latter boundary contains the diagonal and is not a birth-stage class. Keeping
the order fixed and perturbing levels by at most delta gives the checked tree
sandwich `S(epsilon+2*delta) subset S'(epsilon) subset S(epsilon-2*delta)` when
epsilon > 2*delta. This permits support jumps at the threshold and does not
promise a Lipschitz representative or stability across resampling.

## Historical certificate and cost

Finite H1/H2 references can additionally request
[`optimal_volume`](../INTERFACE.md#finite-pair-optimal-volume) with a death-stage
upper cost window. This minimizes the pair-constrained filling's mass and returns
both the filling and its boundary in original coordinates, with an independent
exact certificate in the supported finite domain. It preserves the existing
barcode and projection choices. A separate `same_history_class` flag reports
whether the boundary matches the preselected birth-stage generator. Infinite
intervals explicitly have no finite-pair volume. Save standalone volume results
and their upper inputs separately from family snapshots.

At every stage the certificate checks cycles fixed by the same P, agreement with
stored kernel coordinates and six identities, and
`rank([D,H]) = rank(D) + beta`, with exactly beta active historical columns.
Consequently their classes form the entire homology basis, rather than merely
individual nonzero cycles. Each historical vector satisfies
`h_(i+1) = P_(i+1) J h_i`; at death its included chain belongs to the actual
boundary space. These equations give an isomorphism of the full interval module
with the product's persistence module, so every interval multiplicity and every
transport rank agree. The birth-prefix rule fixes generator choices within that
decomposition, including backward corrections at deaths.

For a simplex source, the birth vector must use the newly inserted k-simplex
with coefficient 1. At a finite death caused by a new (k+1)-simplex tau, the
included final generator g must satisfy `g + boundary(tau) in im(D_old)`.
Because only one simplex enters per step, this identifies the new birth quotient
or the one-dimensional dying kernel. Together with the full historical module
isomorphism, it certifies exact simplex pairing for this total order. Checking
only the birth and death endpoints would not establish that isomorphism.

Query details record `FullHistoricalBasisV1`, stages/vectors checked, raw-boundary
and transport checks, and resource policy. These APIs opt into retaining the full
history, hashing it, and checking ranks; there is no additional time/entry/RSS cap
or incremental-performance claim. Existing stage solver resource failures remain
explicit missing results. Snapshot validation repeats these checks. The history
can have quadratic output size and its temporary storage is outside the LRU
kernel/cache budgets. There are no new runtime dependencies.
