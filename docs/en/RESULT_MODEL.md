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
queries. `OperatorResult.from_json` returns a record; it does not expose a
`to_operator()` method. Family records provide `to_family()` using the saved P.
Snapshots preserve unqueried states and do not compute every query on export.
See the [result contract](RESULT_MODEL.md).

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
