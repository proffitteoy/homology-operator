# Results, identity, and serialization

[中文](../RESULT_MODEL.md)

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
queries. `OperatorResult.from_json` returns a record; `to_operator()` restores
the saved P. Family records provide `to_family()` using the saved P.
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
