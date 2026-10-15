"""Joint readouts of one independently validated single-scale projection."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from fractions import Fraction
from math import fsum, isfinite
from types import MappingProxyType

from . import __version__
from .algebra import Matrix, CyclicAction, CompactAction, validate_vector
from .chain import ChainWindow
from .result import OperatorResult, QueryResult, _freeze, content_id, make_identity
from .solver import ProjectionSolution, ResourceLimits, _Budget, _Exhausted
from .validation import (
    _validated_certificate,
    validate_minimum_class_query,
    validate_solution,
)

THEORY_REVISION = "6143729669902ee875b211b58085e954c76cdf88"


@dataclass(frozen=True)
class HomologyOperator:
    window: ChainWindow
    solution: ProjectionSolution
    repository_revision: str = "unknown"
    _kernel: object = field(init=False, default=None, repr=False, compare=False)
    _native_workspace: object = field(
        init=False, default=None, repr=False, compare=False
    )
    _queries: dict = field(init=False, default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.window, ChainWindow):
            raise ValueError("InvalidInput: a validated ChainWindow is required")
        if (
            not isinstance(self.solution, ProjectionSolution)
            or self.solution.projection is None
            or self.solution.status
            not in {"Solved", "FeasibleOnly", "ResourceExhausted"}
        ):
            raise ValueError("SolverFailed: no feasible projection")
        certificate = validate_solution(self.window, self.solution)
        identity = make_identity(
            self.window,
            self.solution.projection,
            self.solution.solver_run_id,
            self.solution.tie_break_policy,
        )
        if (
            not isinstance(self.repository_revision, str)
            or not self.repository_revision
        ):
            raise ValueError("repository_revision must be a nonempty string")
        object.__setattr__(self, "P", self.solution.projection)
        object.__setattr__(
            self,
            "L",
            self.P.complemented()
            if isinstance(self.P, CompactAction)
            else CyclicAction(self.P.m, not self.P.complement)
            if isinstance(self.P, CyclicAction)
            else Matrix.identity(self.window.n) + self.P,
        )
        object.__setattr__(self, "identity", MappingProxyType(identity))
        object.__setattr__(
            self,
            "_certificate",
            _freeze(
                _validated_certificate(
                    self.solution.certificate,
                    certificate,
                    self.solution.certificate_level,
                )
            ),
        )
        object.__setattr__(
            self,
            "_provenance",
            MappingProxyType(
                {
                    "repository_revision": self.repository_revision,
                    "theory_revision": THEORY_REVISION,
                    "backend": "python-compact-f2"
                    if isinstance(self.P, CompactAction)
                    else "python-structured-reference"
                    if isinstance(self.P, CyclicAction)
                    else "python-dense-reference",
                    "backend_version": __version__,
                    "solver": self.solution.method,
                    "solver_version": __version__,
                    "arithmetic_mode": self.window.arithmetic,
                    "tie_break_policy": self.solution.tie_break_policy,
                    "solver_config_id": self.solution.solver_config_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
        )

    def project(self, x):
        return self.P.apply(x)

    def apply_operator(self, x):
        return self.L.apply(x)

    def kernel_basis(self):
        if self._kernel is None:
            object.__setattr__(self, "_kernel", self.L.kernel_basis())
        return self._kernel

    def betti(self):
        # Legality was checked at construction; ranks belong to these immutable
        # boundary matrices, and do not require elimination of P or I+P.
        return self.window.n - self.window.A.rank() - self.window.D.rank()

    def is_cycle(self, x):
        return self.window.A.apply(x) == (0,) * self.window.m

    def is_boundary(self, x):
        x = validate_vector(x, self.window.n)
        return self.window.D.solve(x) is not None

    def _cycle(self, z):
        z = validate_vector(z, self.window.n)
        if not self.is_cycle(z):
            raise ValueError("class queries require a cycle (Az=0)")
        return z

    def class_representative(self, z):
        return self.project(self._cycle(z))

    def same_class(self, z, y):
        return self.class_representative(z) == self.class_representative(y)

    def _mass(self, chain):
        costs = [weight for weight, bit in zip(self.window.weights, chain) if bit]
        if self.window.arithmetic == "FloatingPoint":
            try:
                value = fsum(costs)
            except OverflowError as error:
                raise ValueError("NumericalFailure: floating mass overflow") from error
            if not isfinite(value):
                raise ValueError("NumericalFailure: nonfinite floating mass")
            return value
        return sum(costs)

    def selected_mass(self, z):
        return self._mass(self.class_representative(z))

    def class_distance(self, z, y):
        z, y = self._cycle(z), self._cycle(y)
        return self._mass(self.project(tuple(a ^ b for a, b in zip(z, y))))

    def support(self, z):
        return tuple(i for i, bit in enumerate(self.class_representative(z)) if bit)

    def locate_support(self, z, source_mapping_id=None):
        """Locate the same-P representative; H0 remains a set of points."""
        return self.window.locate_chain(
            self.class_representative(z), source_mapping_id=source_mapping_id
        )

    def shared_support(self, z, y):
        return tuple(sorted(set(self.support(z)) & set(self.support(y))))

    def union_support(self, z, y):
        return tuple(sorted(set(self.support(z)) | set(self.support(y))))

    def minimum_class_mass(self, z, limits=None):
        """Minimize one exact-weight cycle coset, independently of P's section.

        Enumerate each element of im(D) once, using Gray-code updates of stable
        independent original columns. Ties use lexicographic chain coordinates.
        An interrupted candidate is an upper bound, never a computed minimum.
        """
        z = self._cycle(z)
        limits = ResourceLimits() if limits is None else limits
        if not isinstance(limits, ResourceLimits):
            raise ValueError("minimum_class_mass limits must be ResourceLimits")
        budget = _Budget(limits)
        details = {
            "method": "BoundaryCosetEnumeration",
            "input_cycle": z,
            "request_limits": asdict(limits),
            "arithmetic_policy": self.window.arithmetic,
            "tie_break_policy": "LexicographicChain",
        }
        if (
            self.window.arithmetic == "FloatingPoint"
            or limits.packed_word_limit is not None
        ):
            details["reason"] = (
                "exact weights required"
                if self.window.arithmetic == "FloatingPoint"
                else "unsupported resource limits: packed_word_limit"
            )
            result = QueryResult("Unavailable", identity=self.identity, details=details)
        else:
            n, p = self.window.n, self.window.p
            best, best_chain, best_boundary = self._mass(z), z, (0,) * p
            total, proof, reason = None, None, None
            try:
                # Conservative logical entry bound for reduction, independent
                # checking, basis columns, candidate and original-basis witness.
                budget.entries(
                    2 * n * p + 2 * n * min(n, p) + 8 * (n + p) + 2 * self.window.m
                )
                budget.step(0)
                pivots = self.window.D._reduction[1]
                basis = self.window.D.image_basis()
                total = 1 << len(basis)
                current, boundary = z, [0] * p
                for index in range(total):
                    budget.step()
                    if index:
                        changed = (index & -index).bit_length() - 1
                        current = tuple(a ^ b for a, b in zip(current, basis[changed]))
                        boundary[pivots[changed]] ^= 1
                    mass = self._mass(current)
                    if (mass, current) < (best, best_chain):
                        best, best_chain, best_boundary = mass, current, tuple(boundary)
                    if best == 0:
                        proof = "NonnegativeMass"
                        break
                if proof is None:
                    proof = "CompleteBoundaryEnumeration"
                budget.step(0)
            except _Exhausted as error:
                reason, proof = str(error), None
            details.update(
                {
                    "candidate_mass": best,
                    "representative": best_chain,
                    "boundary_witness": best_boundary,
                    "lower_bound": best if proof else 0,
                    "upper_bound": best,
                    "optimality_gap": 0 if proof else best,
                    "certificate_level": "ExactOptimal"
                    if proof
                    else "CertifiedInterval",
                    "optimality_proof": proof,
                    "total_boundaries": total,
                    "enumerated_boundaries": budget.states,
                    "resource_usage": budget.usage(),
                }
            )
            if reason is not None:
                details["reason"] = reason
            result = QueryResult(
                "Computed" if proof else "ResourceExhausted",
                best if proof else None,
                self.identity,
                True if proof else None,
                details,
            )
            # Check actual A/D/P and the original-coordinate boundary witness;
            # snapshot recovery additionally replays the optimality certificate.
            validate_minimum_class_query(self.window, self.P, result, replay=False)
            try:
                budget.step(0)
            except _Exhausted as error:
                proof = None
                details.update(
                    {
                        "reason": str(error),
                        "optimality_proof": None,
                        "lower_bound": 0,
                        "optimality_gap": best,
                        "certificate_level": "CertifiedInterval",
                    }
                )
            details["resource_usage"] = budget.usage()
            result = QueryResult(
                "Computed" if proof else "ResourceExhausted",
                best if proof else None,
                self.identity,
                True if proof else None,
                details,
            )
        key = content_id("minimum_class_mass", (z, asdict(limits)))
        self._queries[key] = result
        self._queries["minimum_class_mass"] = result
        return result

    def stretch(self, limits=None):
        """Enumerate nonzero cycles for this P; never certify global optimality."""
        limits = ResourceLimits() if limits is None else limits
        if not isinstance(limits, ResourceLimits):
            raise ValueError("stretch limits must be ResourceLimits")
        budget = _Budget(limits)
        exact = self.window.arithmetic != "FloatingPoint"
        best, witness = Fraction(0) if exact else 0.0, None
        total = None
        try:
            budget.entries(self.window.m * self.window.n + self.window.n**2)
            budget.step(0)
            cycles = self.window.A.kernel_basis()
            budget.step(0)
            total = (1 << len(cycles)) - 1
            for mask in range(1, total + 1):
                budget.step()
                z = tuple(
                    sum(basis[i] for j, basis in enumerate(cycles) if mask >> j & 1) % 2
                    for i in range(self.window.n)
                )
                numerator, denominator = self._mass(self.project(z)), self._mass(z)
                ratio = (
                    Fraction(numerator, denominator)
                    if exact
                    else numerator / denominator
                )
                if not exact and not isfinite(ratio):
                    raise ValueError("NumericalFailure: nonfinite floating stretch")
                if witness is None or ratio > best:
                    best, witness = ratio, z
            budget.step(0)
            details = {
                "method": "NonzeroCycleEnumeration",
                "witness": witness,
                "domain_empty": total == 0,
                "total_states": total,
                "resource_usage": budget.usage(),
                "current_objective_lower_bound": best if exact else None,
                "lower_bound_on_optimum": None,
                "upper_bound_on_optimum": best if exact else None,
                "optimality_gap": None,
                "certificate_level": "CertifiedUpperBound" if exact else "Feasible",
                "arithmetic_policy": self.window.arithmetic,
            }
            if not exact:
                details.update(
                    {
                        "rounding_policy": "binary64 fsum/division; nearest-even",
                        "tolerance": None,
                        "certified_numeric_bounds": False,
                    }
                )
            result = QueryResult(
                "EmptyDomain" if total == 0 else "Computed",
                best,
                self.identity,
                exact,
                details,
            )
        except _Exhausted as error:
            result = QueryResult(
                "ResourceExhausted",
                identity=self.identity,
                details={
                    "reason": str(error),
                    "domain_empty": total == 0 if total is not None else None,
                    "total_states": total,
                    "resource_usage": budget.usage(),
                    "current_objective_lower_bound": best
                    if exact and witness is not None
                    else None,
                    "sampled_value": best if witness is not None else None,
                    "witness": witness,
                    "upper_bound_on_optimum": None,
                    "lower_bound_on_optimum": None,
                    "optimality_gap": None,
                    "certificate_level": "Feasible",
                },
            )
        except ValueError as error:
            result = QueryResult(
                "Unavailable",
                identity=self.identity,
                details={
                    "reason": "NumericalFailure",
                    "diagnostic": str(error),
                    "resource_usage": budget.usage(),
                },
            )
        self._queries["stretch"] = result
        return result

    def readout(self, name, *args):
        """Attach the complete identity to a scalar/vector query result."""
        if name not in {
            "project",
            "apply_operator",
            "kernel_basis",
            "betti",
            "is_cycle",
            "is_boundary",
            "class_representative",
            "same_class",
            "selected_mass",
            "class_distance",
            "support",
            "locate_support",
            "shared_support",
            "union_support",
        }:
            raise ValueError("unknown readout")
        value = getattr(self, name)(*args)
        exact = not (
            name in {"selected_mass", "class_distance"}
            and self.window.arithmetic == "FloatingPoint"
        )
        if name == "locate_support":
            # Coordinates are declared data, not a metric certificate.
            exact = None
        details = {"arithmetic_policy": self.window.arithmetic}
        if exact is False:
            details.update(
                {"rounding_policy": "binary64 fsum; nearest-even", "tolerance": None}
            )
        query = QueryResult("Computed", value, self.identity, exact, details)
        # Store arguments too: a snapshot must preserve which chain was queried.
        key = content_id(name, args)
        self._queries[key] = QueryResult(
            query.state,
            query.value,
            query.identity,
            query.exact,
            {**details, "query": name, "arguments": args},
        )
        return query

    def certificate(self):
        return self._certificate

    def metadata(self):
        return {
            "identity": dict(self.identity),
            "status": "Ready",
            "provenance": dict(self._provenance),
            "weight_metadata": {
                "arithmetic": self.window.arithmetic,
                "semantic_kind": self.window.weight_semantics,
                "unit": self.window.unit,
            },
        }

    def to_result(self):
        queries = dict(self._queries)
        queries["betti"] = QueryResult("Computed", self.betti(), self.identity, True)
        queries["kernel_basis"] = QueryResult(
            "NotComputed" if self._kernel is None else "Computed",
            self._kernel,
            self.identity,
            True if self._kernel is not None else None,
        )
        queries["stretch"] = queries.get(
            "stretch", QueryResult("NotComputed", identity=self.identity)
        )
        queries["minimum_class_mass"] = queries.get(
            "minimum_class_mass", QueryResult("NotComputed", identity=self.identity)
        )
        return OperatorResult(
            self.identity,
            self.window,
            self.P,
            self.solution.solver_metadata(),
            self.certificate(),
            self._provenance,
            query_results=queries,
        )
