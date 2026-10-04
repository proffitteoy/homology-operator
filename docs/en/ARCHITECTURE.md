# Mathematical conventions and architecture

[中文](../ARCHITECTURE.md)

The theory is tied to `homology-operator-lab @ 6143729669902ee875b211b58085e954c76cdf88`.
This page defines the current objects and computation boundaries. See the
[API](INTERFACE.md), [result model](RESULT_MODEL.md), and [solver contract](SOLVER_CONTRACT.md).

## Chain window and projection

For a fixed degree k, the input is a finite based window over F2:

$$
C_{k+1}\xrightarrow{D}C_k\xrightarrow{A}C_{k-1},\qquad AD=0,\qquad w_i>0.
$$

The reference selects generalized inverses with AGA=A and DUD=D and constructs

$$
R=I+GA,\qquad Q=I+DU,\qquad P=QR,\qquad L=I+P.
$$

Every candidate is independently checked for P²=P, AP=0, PD=0, and
`z+Pz∈im(D)` on a complete cycle basis. The last condition ensures preservation
of cycle homology. A zero projection can satisfy the first three conditions and
still lose nonzero homology. Other solver parameterizations use the same boundary.

`HomologyOperator` uses one P for topology, representatives, weighted geometry,
and stretch. Queries do not choose another representative or run independent PH
to populate the result. `ker(L)` identifies the selected homology representation.

## Geometry in original coordinates

For cycles z,y, define

$$
m_w(x)=\sum_i w_i x_i,\qquad
\operatorname{selected\_mass}(z)=m_w(Pz),\qquad
d_P([z],[y])=m_w(P(z+y)).
$$

Support and its intersection/union are read from the same projected coordinates.
A basis change may preserve homology while changing mass, support, and stretch.
Weight semantics and units belong to the input, not to an inferred geometric name.

True minimum class mass and the current/optimal projection objectives are different:

$$
\mu_w([z])=\min\{m_w(x):Ax=0,\ [x]=[z]\},\qquad
\Gamma_w(P)=\max_{0\ne z,\ Az=0}\frac{m_w(Pz)}{m_w(z)},\qquad
\Gamma_*=\min_P\Gamma_w(P).
$$

`minimum_class_mass` is currently unavailable. Feasibility, exact current Γ, and
global optimality are separate facts. Empty cycle space has declared stretch 0
with EmptyDomain; a nonempty cycle space with zero Betti has a legitimate computed
0. This is distinct from a separately defined section-accounting convention.
Exact F2 algebra does not certify floating-point geometry or optimality.

## Filtration transport

`OperatorFamily` accepts finite ordered windows and matching operators in one
degree. Basis identifiers define inclusions in all three degrees; chain-map,
coordinate, and weight policies are validated. Repeated scales preserve stage
order, and the terminal extension is constant.

$$
\mathcal H_i=\ker L_i,\qquad T_{ij}=P_jJ_{ij}|_{\mathcal H_i}.
$$

Transports retain kernel-coordinate action and original target chain action.
They must satisfy T_ii=I and `T_jl T_ij=T_il`, and agree with the induced homology
map under the chosen representation. Stage Betti alone does not determine this map.

`barcode()` reads adjacent kernel maps while preserving the full rank invariant.
`barcode_basis()` and `rank_table()` explicitly request larger historical/all-rank
outputs. Death yields a valid zero chain, mass, and support. Failed stages remain
missing rather than becoming empty spaces. The historical proof is retained in
the [S4 filtration record](../S4_FILTRATION.md).

## Existing modules

| Module | Responsibility |
| --- | --- |
| algebra.py | Explicit-shape F2 matrices and the supported CyclicAction |
| chain.py | Window, coordinate, AD=0, weight and source validation |
| solver.py | Requests, capabilities, budgets, solver records and dispatch |
| validation.py | Independent projection and optimization certificate validation |
| operator.py | Same-P single-scale readouts, query history and results |
| family.py | Inclusions, transport, rank/barcode, tracking and family snapshots |
| result.py | Six identities, query state, canonical JSON and cache boundaries |
| native.py / native/src | Optional safe Rust adaptation, packed algebra and supported batch operations |

No public LinearAction base class, universal sparse backend, or
FilteredChainComplex front end is implied by the roadmap.

## Action and native boundaries

Matrix stores explicit P/L. CyclicAction represents the fixed supported family.
CompactAction stores generalized-inverse or HC factors without materializing full
P/L. Every representation preserves the same action on all chains, including
noncycle extension, and undergoes independent validation and recovery.

NativeFeasibleSolver and explicit apply_batch remain limited to 64 dimensions;
geometry_batch supports multiword Matrix and Factorized/HC. GeometryWorkspace
binds all six identities and reuses process-local action/weight buffers. Checked
u64 mass and explicit exact/floating Python fallback preserve the arithmetic policy.
Different representations may have different content identities.

## Resource and evidence boundaries

Solver budgets are cooperative state, wall-time, and logical-entry checkpoints.
They are not hard RSS limits or a unified preemption budget for validation,
certificate replay, serialization, and recovery. Those costs remain part of the
complete call. Missing or uncomputed objective is never replaced by zero.

Independent PH reduction and GUDHI are test/measurement oracles. They do not
populate production barcodes, replace representatives, or fill missing results.
Performance comparisons match input, P, arithmetic, certificates and budgets,
and retain conversion, validation, query, snapshot and recovery costs.
Historical results and regressions remain in [S4](../S4_REPORT.md) and [S5](../S5_REPORT.md).
