# Solver contract

[中文](../SOLVER_CONTRACT.md) · [API](INTERFACE.md)

## Responsibility and validation

A solver chooses a projection for one `ProjectionProblem`. It does not define
query semantics, generate a separate barcode, or modify the mathematical
meaning of `HomologyOperator`. Before acceptance, independently validate
P²=P, AP=0, PD=0 and cycle homology preservation `z+Pz∈im(D)`.

The objective is minimum worst weighted cycle stretch:

$$
\Gamma_w(P)=\max_{0\ne z,\ Az=0}\frac{m_w(Pz)}{m_w(z)},\qquad
\Gamma_*=\min_{P\ \mathrm{legal}}\Gamma_w(P).
$$

Selected mass is not true minimum class mass. Changing a solver can change the
selected P and therefore representatives/geometry, while query definitions remain
fixed. Do not modify a stage objective to make filtration transport look preferable.

## Request binding

`ProjectionProblem` carries the window, resource limits, objective, requested
certificate level, tie-break and arithmetic policies, declared input structure,
matrix-free output, determinism, solver options and an optional cancellation token.
Dispatch checks `capabilities()` before running and validates the returned complete
configuration, arithmetic, tie policy and reported limits against that request.
Labels do not enlarge an algorithm's domain.

`ProjectionSolution` retains status, projection, six identities, solver run,
certificate level, current objective, lower/upper bounds and gap, method and
configuration, generalized inverses where present, resource usage and diagnostics.
A failed request does not create a usable projection. An interrupted but validated
candidate can be retained without pretending the search finished.

## Certificate levels

| Level | Meaning |
| --- | --- |
| Feasible | Independent projection legality; no global optimum claim |
| ExactOptimal | Legal projection, exact objective, supported independently replayed optimality proof |
| CertifiedUpperBound | Proven upper bound on the optimum |
| CertifiedInterval | Independently valid L≤Γ*≤U |
| Heuristic | Algorithmic evidence alone; any accepted action still requires full legality validation |

Equal certified bounds with an exact objective and supported proof must be
reported as ExactOptimal. Exact F2 does not make floating-point bounds exact.
Public verification fields come from the verifier, not a backend Boolean.

Status and certificate level are independent: ResourceExhausted may carry a
validated candidate and valid bounds. Missing objective/bounds remain missing.
Empty cycle space and nonempty zero homology have different query states even
when the declared/current value is 0.

## Supported reference solvers

| Solver | Current input and output domain |
| --- | --- |
| FeasibleSolver | General based windows; integer/rational/float weights; explicit Matrix, StableBasisOrder |
| ExhaustiveExactSolver | Small exact-weight windows; full section search and explicit optimum certificate |
| GreedyCertifiedSolver | Exact weights; cycle enumeration, deterministic greedy section and certified bounds |
| Rank2ExactSolver | Exact weights, Betti=2; general or explicitly validated graph/three-terminal structure |
| StructuredFamilySolver | Declared CyclicTrace, m=2/3/4, equal exact positive weights; Matrix or CyclicAction |

GeneralSearchSolver is not a registered public backend.

## Certificate replay and search limits

CycleBounds enumerates nonzero cycles, recomputes the current Γ and validates
the universal lower bound: 0 for zero Betti and at most 1 for nonzero Betti.
Replay allows at most 100,000 nonzero cycles. It cannot certify a global lower
bound greater than 1 by itself.

ExhaustiveExactSolver searches `2^(rank(D)*β)` sections of the cycle quotient
using a fixed noncycle retraction. Independent replay uses a separate quotient
basis-lift enumeration. The supported limit is at most 100,000 nonzero cycles and
at most 100,000 for candidate count times `max(1, nonzero cycle count)`.
Tie-breaking is deterministic in the original coordinates under the fixed
retraction, not a claim of global lexicographic order over every noncycle extension.
Only completed exhaustive evaluation certifies ExactOptimal.

GreedyCertifiedSolver sorts all cycles by mass then packed original-coordinate
order and chooses independent homology generators modulo boundaries. Its
independently checked theoretical bound Γ≤β for β>0 is separate from the actual
computed Γ and global optimality. β=0 has Γ=0. Ordinary ExactOptimal requests are
not generally supported; a completed equal-bound result can independently certify
optimality. Replay requires `nonzero cycles * max(1, β) ≤ 100000`.
Interrupted seeds do not acquire unfinished greedy guarantees.

Rank2ExactSolver requires β=2 and checks structure rather than trusting its name.
The general path searches boundary corrections of two quotient generators;
graph/three-terminal reductions use their own validated hypotheses. Unsupported
structure or replay scale returns Unavailable. StructuredFamilySolver accepts
only the declared fixed family and verifies its formula and certificate.
The detailed reduction records remain in the [Chinese contract](../SOLVER_CONTRACT.md).

## Optional native selection

NativeFeasibleSolver requires each chain space at most 64 dimensions and returns
the same deterministic G/U/P as the reference. NativeFactorizedSolver requires
matrix_free_output=True and provides Factorized or HC action with Feasible and
uncomputed objective; it does not add an optimality certificate.

The four supported optimization solvers allow Native-prefixed dispatch names or
`native=True`. Domains, objective, tie-breaking, budgets and independent replay
remain those of the corresponding solver. Exact mass beyond the native integer
range uses explicit arbitrary-precision fallback. PreparedMatrix is a decomposition
tool, not a projection solver.

Fallback is explicit, visible and restricted to the corresponding supported
reference solver. Factorized output has no reference fallback to an explicit
matrix. Unknown/unavailable extensions or domains are reported as Unavailable.

## Resources, cancellation, and comparison

State, wall-time and logical matrix-entry budgets are checked cooperatively.
Independent certificate replay and operator/recovery validation have separate
costs; there is no hard RSS or step-preemption guarantee. Cooperative cancellation
is ResourceExhausted with a reason. Any retained candidate remains validated.

Benchmark comparisons match the problem, weights, objective, arithmetic,
certificate request and achieved level, budget, determinism and tie policy.
ExactOptimal, feasibility-only, bounds and heuristic timings are not interchangeable.
Record source/build/input/output identities, conversion and mandatory validation,
query and recovery costs, and all interrupted/unavailable/failure cases.
