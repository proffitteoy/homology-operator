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

## Historical certificate and cost

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
