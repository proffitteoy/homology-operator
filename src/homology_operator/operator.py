"""Joint readouts of one independently validated single-scale projection."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import fsum, isfinite
from types import MappingProxyType

from .algebra import Matrix, validate_vector
from .chain import ChainWindow
from .result import OperatorResult, QueryResult, make_identity
from .solver import ProjectionSolution
from .validation import ValidationError, validate_projection

THEORY_REVISION = "6143729669902ee875b211b58085e954c76cdf88"


@dataclass(frozen=True)
class HomologyOperator:
    window: ChainWindow
    solution: ProjectionSolution
    repository_revision: str = "unknown"
    _kernel: object = field(init=False, default=None, repr=False, compare=False)
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
        if self.solution.certificate_level != "Feasible":
            raise ValueError("Unavailable: this reference accepts Feasible solutions")
        certificate = validate_projection(self.window, self.solution.projection)
        identity = make_identity(
            self.window,
            self.solution.projection,
            self.solution.solver_run_id,
            self.solution.tie_break_policy,
        )
        if self.solution.identity != identity:
            raise ValidationError(("solution_identity",))
        if (
            not isinstance(self.solution.objective, QueryResult)
            or self.solution.objective.identity != identity
        ):
            raise ValidationError(("objective_identity",))
        if (
            not isinstance(self.repository_revision, str)
            or not self.repository_revision
        ):
            raise ValueError("repository_revision must be a nonempty string")
        object.__setattr__(self, "P", self.solution.projection)
        object.__setattr__(self, "L", Matrix.identity(self.window.n) + self.P)
        object.__setattr__(self, "identity", MappingProxyType(identity))
        object.__setattr__(self, "_certificate", MappingProxyType(certificate))
        object.__setattr__(
            self,
            "_provenance",
            MappingProxyType(
                {
                    "repository_revision": self.repository_revision,
                    "theory_revision": THEORY_REVISION,
                    "backend": "python-dense-reference",
                    "backend_version": "0.0.2.dev0",
                    "solver": self.solution.method,
                    "solver_version": "0.0.2.dev0",
                    "arithmetic_mode": self.window.arithmetic,
                    "tie_break_policy": self.solution.tie_break_policy,
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
        return self.window.n - self.L.rank()

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

    def shared_support(self, z, y):
        return tuple(sorted(set(self.support(z)) & set(self.support(y))))

    def union_support(self, z, y):
        return tuple(sorted(set(self.support(z)) | set(self.support(y))))

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
            "shared_support",
            "union_support",
        }:
            raise ValueError("unknown readout")
        value = getattr(self, name)(*args)
        exact = not (
            name in {"selected_mass", "class_distance"}
            and self.window.arithmetic == "FloatingPoint"
        )
        details = {"arithmetic_policy": self.window.arithmetic}
        if not exact:
            details.update(
                {"rounding_policy": "binary64 fsum; nearest-even", "tolerance": None}
            )
        query = QueryResult("Computed", value, self.identity, exact, details)
        # Store arguments too: a snapshot must preserve which chain was queried.
        from .result import content_id

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
        queries["minimum_class_mass"] = QueryResult(
            "NotComputed", identity=self.identity
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
