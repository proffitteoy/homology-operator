# Results, identity, and serialization

[中文](../RESULT_MODEL.md)

Birth-pair cycle queries use standalone `QueryResult` records with the birth
operator's six identities, full family/feature/pairing binding and a content-based
problem ID. Their `BirthHistoricalClass` objective is separate from same-P selected
mass, arbitrary fixed-class minima and birth-edge-only cycles. Computed means
independently replayed ExactOptimal with equal bounds over the declared finite
fiber; interrupted candidates have only Feasible evidence. F2 supports and source
locations can have multiple components. JSON decoding is structural; call
`validate_optimal_1_cycle(family, reference, result)` for semantic verification.
The family snapshot schema is unchanged and does not retain these standalone
optimization records. See [API and limits](INTERFACE.md#birth-pair-optimal-1-cycle).

`QueryResult` contains `state`, `value`, `identity`, `exact`, and `details`.

| State | Meaning |
| --- | --- |
| `Computed` | A value exists, including valid zero, false, or empty output |
| `NotComputed` | This run has not evaluated the query |
| `Unavailable` | The backend or interface does not support it |
| `ResourceExhausted` | Attempt stopped at the budget |
| `EmptyDomain` | Explicitly empty domain; empty-cycle stretch has the declared value 0 |
| `NoClass` | Explicit absence of a class, distinct from a dead class's zero representative |
| `Infeasible` | Fixed boundary has no filling; value is None, with a verified obstruction |

`exact` describes the query arithmetic, not global optimality. Nonempty cycle
space with Betti zero has a legitimate computed stretch of 0.

`minimum_class_mass(z, limits=None)` keeps the scalar class minimum in `value`
only when `Computed`. Details retain `input_cycle`, `representative`, the original
next-degree `boundary_witness`, `candidate_mass`, class `lower_bound`/`upper_bound`,
`optimality_gap`, `certificate_level`, `optimality_proof`, boundary counts, request
limits, and resource usage. `ExactOptimal` refers only to that fixed class;
the projection solver's certificate is unchanged. Floating weights are unsupported.
On interruption `value/exact` are null, while a valid candidate and its certified
interval remain in details. Valid minimum zero is `Computed`, including empty
homology. The search does not alter the projection or its selected masses.

History stores a content key for each cycle/limits request and a latest-result
alias `minimum_class_mass`. Recovery checks `Ay=0`, `Py=Pz`, and `Db=y+z` against
the actual stored A/D/P, then independently builds the boundary image and replays
any complete-enumeration optimum and lexicographic tie claim. The mass-zero proof
uses positive weights. Recovery has a separate enumeration cost and never runs a
projection solver. Earlier NotComputed/unimplemented records remain readable.

Results carry six identifiers: `input_id`, `basis_id`, `weight_id`,
`projection_id`, `operator_id`, and `solver_run_id`. Independent runs cannot mix
query records even when they produce the same content projection. Different
action representations may have different projection identities.

```python
# Continue after constructing op above.
from homology_operator import OperatorResult

op.readout("selected_mass", (0, 1))
record = op.to_result()
restored = OperatorResult.from_json(record.to_json())
record.require_same_identity(restored)
assert restored.to_dict() == record.to_dict()
```

Reading JSON revalidates inputs, projection, identity, certificates, and saved
queries. `OperatorResult.from_json` returns a record; its `to_operator()` restores
the saved P without solving again. Family records provide `to_family()`.
Snapshots preserve unqueried states and do not compute every query on export.
See the [result contract](RESULT_MODEL.md).

## Standalone filling results

Fixed-boundary filling reuses `QueryResult` with `identity=None`: there is no
projection/operator/run to which the six operator IDs could refer. Instead,
`details.problem_id` hashes both complete window encodings (including ordered
bases, upper costs, units, arithmetic and source metadata) and the target boundary.
Verification checks that binding against the supplied inputs, and separately
recomputes feasibility and optimality. It never fills operator query history.

`QueryResult.to_dict/from_dict` preserves the evidence and exact fractions but
only checks record structure. On untrusted recovery call
`validate_minimum_filling(window, z, filling_window, result)`; returned checks,
rather than saved verification flags, establish acceptance. Retain both inputs
and z alongside the record. Existing operator/family schemas remain unchanged.

## Finite-pair volume results

`OperatorFamily.optimal_volume` returns a standalone `QueryResult`. Its six IDs
are those of the death-stage operator (the final stage for an infinite or missing
history); they identify the family context, not an optimized projection.
`details` also binds the family/filtration, full feature reference, actual simplex
pairing, permitted indices, upper weight semantics/unit and a `problem_id` hashing
the family identity, reference and complete upper-window encoding. Changing upper
costs or any provenance requires a new problem binding. The locations bind both
degrees' original source mappings; externally supplied coordinates and dataset
hashes still require caller verification against actual data.

`Computed`/`ExactOptimal` carries complete affine enumeration evidence, equal
optimal bounds and fresh independent checks. An infinite pair has `EmptyDomain`
with `applicability="NotApplicable"`, no value and no optimality claim.
`ResourceExhausted` may retain a feasible candidate; `Unavailable` supplies no
optimum. No new QueryResult state or family wire schema is introduced.

The volume result itself is not cached or exported inside family snapshots.
Save it with the family, reference and upper cost window. `QueryResult.from_dict`
checks only structure; call `validate_optimal_volume(family, reference,
filling_window, result)` after recovery. It checks actual inputs and independently
replays constraints and optimality; saved verification flags cannot replace it.
The family's source/pairing and existing historical references continue to use
schema 3 with their existing independent recovery checks.

Stable-volume results use the same standalone wire model and upper input, with
`StableVolumeDefinition6`, positive exact epsilon, its declared scale unit,
`Obayashi2023Definition6-F2-v1`, cutoff, allowed/zero indices and source binding.
`CompleteStableAffineEnumeration` certifies a complete affine fiber. Algebraic
exactness, exact positive-cost optimization, conditional filtration robustness,
and resampling stability are separate: the last is always unclaimed.
`guarantee_level` is absent in meaning (`None`) for unfinished or unsupported
results. `robust_domain` reports geometric eligibility, not a completed guarantee.
`validate_stable_volume` rejects changed epsilon/units, costs, geometry, pair,
constraint set, proof, location and guarantee. Family schema versions do not change.

## Single-scale wire format

`OperatorResult` uses schema 1 with `status`, `identity`, `input_data`, `projection`,
`solver`, `certificate`, `provenance`, and `query_results`. Input shapes, arithmetic,
weights, and source metadata are retained. Fractions use a `$fraction` tag;
reserved plain mapping keys are escaped with `$mapping`.

Readers reject duplicate JSON keys, nonfinite numbers, unknown schema/fields,
mixed identities, modified queries, and unsupported/tampered certificates.
Backend claims remain in solver evidence; public validation flags come from the
independent verifier. A feasible interrupted candidate may produce a Ready
operator while its solver status remains ResourceExhausted.

## Source mapping identity

The optional [source protocol](guide/input-semantics.md#source-mapping-and-location)
is validated against actual boundary incidence before hashing. A mapped
`ChainWindow.identity()` additionally exposes `source_mapping_id`, hashing the
complete mapping, algebraic `chain_window_hash`, `basis_id`, weight semantics and
weight unit. Its `input_id` binds the algebraic window and this mapping ID. Thus
changing coordinates, original IDs, source hash, metric, periods, lifts, units,
stage order/index or scale changes the input identity and dependent projection
and operator identities. The six-field operator/query identity remains unchanged
in shape. Family identities include all mapped stage input identities.

`locate_chain` and `locate_support` return a `location_id` hash of their complete
location payload. A `track_location` query also binds the filtration and endpoint
operator identities in its details. Snapshot recovery revalidates mappings and
identities and replays recorded location queries from the saved P; replacing a
mapping or a saved drawing payload while retaining old identities is rejected.
The original dataset hash is caller supplied: applications must compare it with
their actual source bytes and retain the expected input/filtration identity.
Content hashes provide integrity against those retained identities, not external
attestation or protection against an author replacing every hash and input.

Unmapped legacy windows retain their existing IDs and schema-1/2 wire formats.
Their arbitrary descriptive metadata is not authenticated as geometric source
data and cannot supply location coordinates. No new wire version or runtime
dependency is needed for the optional metadata protocol.

## Action representations

| Projection encoding | Supported representation |
| --- | --- |
| nrows/ncols/rows | Explicit Matrix, retaining empty shapes |
| CyclicTrace, version 1 | Fixed m=2/3/4 parameter handle |
| CompactF2, version 1 | GeneralizedInverse or HC factors, pivots and complement |

Recovery checks the complete action and cycle homology independently. Factorized
recovery checks agreement with A/D and AGA=A, DUD=D. HC checks AH=0, CD=0, CH=I and
homology preservation. Supported compact actions recover without the Rust extension
and without materializing full P. Representations may have different content IDs.

## Family snapshots

Family schema 2 shares immutable final-stage boundaries and ordered bases, storing
each stage's active indices and input metadata. Stage results reference inputs
and retain their own weights, projections, solver runs, certificates and failures.
Transports, rank/barcode/tracking readouts and requested historical interval bases
are saved with source/target identities. Schema 1 remains readable and is reissued
at its original version; `to_result(schema_version=1)` requests legacy output.

Supplying `simplex_source` or calling `features()` upgrades the family to schema 3.
It extends schema 2 with `simplex_source` and `features_readout`, and permits
`resolve_feature` / `feature_pairing` in `tracking_readout`. Schemas 1/2 remain
readable and reissue their original format until these new APIs are used.
Downgrading a family with feature references or a source is rejected to avoid
dropping provenance. Each stored feature, historical basis and query is replayed;
duplicate/replaced references, missing dependencies, forged certificates and
source/boundary disagreement are rejected. Recovery retains the original solver
runs and requires no solver or research dependency.

A reference's content hash binds family/filtration IDs, degree, stage and scale
endpoints, endpoint occurrence, birth chain basis, `AdjacentBirthPrefixV1` policy,
and a hash of all historical vectors with their six identities. It is stable
across JSON restoration of that family; a fresh solve, different total order,
projection, basis, weights or stream is a different reference. It does not name
a canonical geometric class independently of the chosen interval basis.
`NoClass` means the selected interval is unborn/dead at the requested stage;
it differs from `track_class` returning the zero image of a previously living class.

`OperatorFamilyResult.from_json` revalidates the family and recorded results.
`to_family()` uses saved projections, not a new solve. Partial does not become
Ready and failure does not become an empty stage or barcode. Rechecking saved
readouts is a real recovery cost.

## Cache and runtime provenance

`cache_key(solver_config_id, tie_break_policy_id, backend_semantics_version)` binds
input/basis/weight/projection/operator content identities and actual configuration.
The solver-run identifier stays in provenance, not the reusable content key.
Caching geometry only by A/D is unsafe. GeometryWorkspace is a process-local,
six-identity prepared object and is not part of the snapshot schema.

Cancellation tokens are runtime state, outside content IDs and JSON. Explicit
fallback records requested/selected backend and reason. Missing RSS/CPU is missing,
not zero; logical entries and stored words are not process peak RSS.
