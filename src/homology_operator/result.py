"""Stable content identities and lossless, validated result serialization."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from hashlib import sha256
import json
from math import isfinite
from types import MappingProxyType

from .algebra import Matrix
from .chain import ChainWindow, matrix_data, matrix_from_data


IDENTITY_FIELDS = (
    "input_id",
    "basis_id",
    "weight_id",
    "projection_id",
    "operator_id",
    "solver_run_id",
)
QUERY_STATES = {
    "Computed",
    "NotComputed",
    "Unavailable",
    "ResourceExhausted",
    "EmptyDomain",
    "NoClass",
}


def _encode(value):
    if isinstance(value, Fraction):
        return {"$fraction": [value.numerator, value.denominator]}
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("JSON keys must be strings")
        encoded = {key: _encode(item) for key, item in value.items()}
        if set(encoded) in ({"$fraction"}, {"$mapping"}):
            return {"$mapping": encoded}
        return encoded
    if isinstance(value, (tuple, list)):
        return [_encode(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    raise ValueError("result data must contain finite JSON values or Fractions")


def _decode(value):
    if isinstance(value, Mapping):
        if set(value) == {"$mapping"}:
            items = value["$mapping"]
            if not isinstance(items, Mapping):
                raise ValueError("invalid escaped mapping")
            return {key: _decode(item) for key, item in items.items()}
        if set(value) == {"$fraction"}:
            pair = value["$fraction"]
            if (
                not isinstance(pair, (tuple, list))
                or len(pair) != 2
                or any(type(x) is not int for x in pair)
            ):
                raise ValueError("invalid rational result value")
            try:
                return Fraction(*pair)
            except ZeroDivisionError as error:
                raise ValueError("invalid rational denominator") from error
        return {key: _decode(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_decode(item) for item in value]
    return value


def _freeze(value):
    # Validate before copying so NaN and unsupported objects cannot hide in metadata.
    _encode(value)
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    return value


def canonical_json(value):
    """Canonical UTF-8 JSON text; dictionary order does not affect content IDs."""
    return json.dumps(
        _encode(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_id(kind, value):
    if not isinstance(kind, str) or not kind:
        raise ValueError("identity kind must be a nonempty string")
    return f"{kind}:{sha256(canonical_json(value).encode('utf-8')).hexdigest()}"


def input_identity(window):
    if not isinstance(window, ChainWindow):
        raise ValueError("identity requires a validated ChainWindow")
    data = window.to_dict()
    basis = {
        key: data[key] for key in ("basis_previous", "basis_current", "basis_next")
    }
    chain = {"k": window.k, "A": data["A"], "D": data["D"], **basis}
    weights = {
        key: data[key] for key in ("weights", "arithmetic", "weight_semantics", "unit")
    }
    return {
        "input_id": content_id("input", chain),
        "chain_window_hash": content_id("chain", chain),
        "basis_id": content_id("basis", basis),
        "weight_id": content_id("weight", weights),
    }


def make_identity(
    window, projection, solver_run_id, tie_break_policy="StableBasisOrder"
):
    if not isinstance(projection, Matrix) or (projection.nrows, projection.ncols) != (
        window.n,
        window.n,
    ):
        raise ValueError("projection shape must match C_k")
    if not isinstance(solver_run_id, str) or not solver_run_id:
        raise ValueError("solver_run_id must be a nonempty string")
    if not isinstance(tie_break_policy, str) or not tie_break_policy:
        raise ValueError("tie-break policy must be a nonempty string")
    inputs = input_identity(window)
    identity = {key: inputs[key] for key in ("input_id", "basis_id", "weight_id")}
    identity["projection_id"] = content_id(
        "projection",
        {
            "input_id": identity["input_id"],
            "basis_id": identity["basis_id"],
            "action": matrix_data(projection),
            "tie_break_policy": tie_break_policy,
        },
    )
    identity["operator_id"] = content_id("operator", identity)
    identity["solver_run_id"] = solver_run_id
    return identity


def _identity(identity):
    if not isinstance(identity, Mapping) or set(identity) != set(IDENTITY_FIELDS):
        raise ValueError("result identity requires exactly six identity fields")
    if any(
        not isinstance(identity[key], str) or not identity[key]
        for key in IDENTITY_FIELDS
    ):
        raise ValueError("identity fields must be nonempty strings")
    return _freeze(identity)


def require_same_identity(left, right):
    """Reject mixing readouts belonging to different inputs, coordinates or actions."""
    if hasattr(left, "identity"):
        left = left.identity
    if hasattr(right, "identity"):
        right = right.identity
    if _identity(left) != _identity(right):
        raise ValueError("results belong to different operator identities")


@dataclass(frozen=True)
class QueryResult:
    state: str
    value: object = None
    identity: Mapping | None = None
    exact: bool | None = None
    details: Mapping = field(default_factory=dict)

    def __post_init__(self):
        if self.state not in QUERY_STATES:
            raise ValueError("unknown query state")
        if self.exact is not None and type(self.exact) is not bool:
            raise ValueError("exact must be boolean or None")
        if self.state == "Computed" and self.value is None:
            raise ValueError("Computed queries require a value; zero is valid")
        if (
            self.state in {"NotComputed", "Unavailable", "ResourceExhausted", "NoClass"}
            and self.value is not None
        ):
            raise ValueError("missing query states cannot carry a computed value")
        if not isinstance(self.details, Mapping):
            raise ValueError("query details must be a mapping")
        object.__setattr__(self, "value", _freeze(self.value))
        object.__setattr__(self, "details", _freeze(self.details))
        if self.identity is not None:
            object.__setattr__(self, "identity", _identity(self.identity))

    def to_dict(self):
        return {
            "state": self.state,
            "value": _encode(self.value),
            "identity": _encode(self.identity),
            "exact": self.exact,
            "details": _encode(self.details),
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, Mapping) or set(data) != {
            "state",
            "value",
            "identity",
            "exact",
            "details",
        }:
            raise ValueError("invalid query result fields")
        return cls(
            data["state"],
            _decode(data["value"]),
            data["identity"],
            data["exact"],
            _decode(data["details"]),
        )

    def require_same_identity(self, other):
        require_same_identity(self, other)


@dataclass(frozen=True)
class OperatorResult:
    """A content-checked single-scale result record; Ready additionally validates P."""

    identity: Mapping | None
    input_data: ChainWindow | Mapping | None
    projection: Matrix | Mapping | None
    solver: Mapping
    certificate: Mapping
    provenance: Mapping
    status: str = "Ready"
    schema_version: int = 1
    query_results: Mapping = field(default_factory=dict)

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("unsupported result schema version")
        if self.status not in {
            "Ready",
            "InvalidInput",
            "SolverFailed",
            "ResourceExhausted",
            "Unavailable",
            "InternalValidationFailed",
        }:
            raise ValueError("unknown operator status")
        window = (
            None
            if self.input_data is None
            else (
                self.input_data
                if isinstance(self.input_data, ChainWindow)
                else ChainWindow.from_dict(self.input_data)
            )
        )
        projection = (
            None
            if self.projection is None
            else (
                self.projection
                if isinstance(self.projection, Matrix)
                else matrix_from_data(self.projection)
            )
        )
        if not isinstance(self.solver, Mapping):
            raise ValueError("solver data must be a mapping")
        solver = _freeze(self.solver)
        from .validation import validate_solver_config

        validate_solver_config(window, solver)
        if solver.get("status") not in {
            "Solved",
            "FeasibleOnly",
            "ResourceExhausted",
            "Unavailable",
            "InvalidProblem",
            "NumericalFailure",
            "InternalError",
        }:
            raise ValueError("unknown solver status")
        for name in ("lower_bound", "upper_bound"):
            value = solver.get(name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float, Fraction))
                or (isinstance(value, float) and not isfinite(value))
                or value < 0
            ):
                raise ValueError("bounds must be finite nonnegative numbers or None")
        lower, upper = solver.get("lower_bound"), solver.get("upper_bound")
        if lower is not None and upper is not None and lower > upper:
            raise ValueError("lower bound cannot exceed upper bound")
        if not isinstance(self.certificate, Mapping) or not isinstance(
            self.provenance, Mapping
        ):
            raise ValueError("certificate and provenance must be mappings")
        certificate = dict(self.certificate)
        if projection is None:
            failure_statuses = {
                "InvalidInput": {"InvalidProblem"},
                "SolverFailed": {"NumericalFailure", "InternalError"},
                "ResourceExhausted": {"ResourceExhausted"},
                "Unavailable": {"Unavailable"},
                "InternalValidationFailed": {"InternalError"},
            }
            if solver["status"] not in failure_statuses.get(self.status, set()):
                raise ValueError(
                    "missing projection requires a matching failure status"
                )
            if (
                solver.get("certificate_level") is not None
                or certificate
                or self.query_results
                or lower is not None
                or upper is not None
                or solver.get("optimality_gap") is not None
            ):
                raise ValueError(
                    "missing projection cannot carry certification or operator queries"
                )
            identity = None
            if self.identity is not None:
                fields = {"input_id", "basis_id", "weight_id", "solver_run_id"}
                if (
                    not isinstance(self.identity, Mapping)
                    or set(self.identity) != fields
                ):
                    raise ValueError(
                        "failure identity must omit projection and operator IDs"
                    )
                if window is None or any(
                    not isinstance(value, str) or not value
                    for value in self.identity.values()
                ):
                    raise ValueError(
                        "partial identity requires validated input and a solver run"
                    )
                expected = input_identity(window)
                if any(
                    self.identity[key] != expected[key]
                    for key in fields - {"solver_run_id"}
                ):
                    raise ValueError("failure input identity mismatch")
                identity = _freeze(self.identity)
        else:
            identity = _identity(self.identity)
            tie_break = solver.get("tie_break_policy", "StableBasisOrder")
            expected = make_identity(
                window, projection, identity["solver_run_id"], tie_break
            )
            if identity != expected:
                raise ValueError("result content does not match its declared identity")
        if identity is not None and (
            solver.get("solver_run_id", identity["solver_run_id"])
            != identity["solver_run_id"]
        ):
            raise ValueError("solver run identity mismatch")
        if "objective" in solver:
            objective = QueryResult.from_dict(solver["objective"])
            if projection is None:
                if objective.identity is not None or objective.state in {
                    "Computed",
                    "EmptyDomain",
                }:
                    raise ValueError(
                        "missing projection cannot carry an operator objective"
                    )
            else:
                require_same_identity(identity, objective.identity)
        if projection is not None:
            from .validation import validate_projection, validate_solver_certificate

            certificate.update(validate_projection(window, projection))
            certificate.update(
                validate_solver_certificate(
                    window, projection, solver, certificate, identity
                )
            )
        if self.status == "Ready":
            if solver["status"] not in {"Solved", "FeasibleOnly", "ResourceExhausted"}:
                raise ValueError(
                    "Ready requires a solver status that can retain a feasible projection"
                )
        if not isinstance(self.query_results, Mapping):
            raise ValueError("query_results must be a mapping")
        queries = {}
        for name, query in self.query_results.items():
            if not isinstance(name, str) or not name:
                raise ValueError("query names must be nonempty strings")
            if not isinstance(query, QueryResult):
                query = QueryResult.from_dict(query)
            if query.identity is None:
                raise ValueError("operator queries must carry the operator identity")
            require_same_identity(identity, query.identity)
            queries[name] = query
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "input_data", window)
        object.__setattr__(self, "projection", projection)
        object.__setattr__(self, "solver", solver)
        object.__setattr__(self, "certificate", _freeze(certificate))
        object.__setattr__(self, "provenance", _freeze(self.provenance))
        object.__setattr__(self, "query_results", MappingProxyType(queries))

    def to_dict(self):
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "identity": _encode(self.identity),
            "input_data": None
            if self.input_data is None
            else self.input_data.to_dict(),
            "projection": None
            if self.projection is None
            else matrix_data(self.projection),
            "solver": _encode(self.solver),
            "certificate": _encode(self.certificate),
            "provenance": _encode(self.provenance),
            "query_results": {
                name: query.to_dict() for name, query in self.query_results.items()
            },
        }

    def to_json(self):
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    @classmethod
    def from_dict(cls, data):
        fields = {
            "schema_version",
            "status",
            "identity",
            "input_data",
            "projection",
            "solver",
            "certificate",
            "provenance",
            "query_results",
        }
        if not isinstance(data, Mapping) or set(data) != fields:
            raise ValueError("invalid operator result fields")
        return cls(
            data["identity"],
            data["input_data"],
            data["projection"],
            _decode(data["solver"]),
            _decode(data["certificate"]),
            _decode(data["provenance"]),
            data["status"],
            data["schema_version"],
            data["query_results"],
        )

    @classmethod
    def from_json(cls, text):
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON keys are not allowed")
                result[key] = value
            return result

        def reject_constant(value):
            raise ValueError(f"nonfinite JSON constant: {value}")

        return cls.from_dict(
            json.loads(
                text, object_pairs_hook=unique_object, parse_constant=reject_constant
            )
        )

    def cache_key(
        self, solver_config_id, tie_break_policy_id, backend_semantics_version
    ):
        if self.projection is None:
            raise ValueError("missing projection has no operator cache key")
        for value in (solver_config_id, tie_break_policy_id, backend_semantics_version):
            if not isinstance(value, str) or not value:
                raise ValueError("cache policy fields must be nonempty strings")
        return content_id(
            "cache",
            {
                **{
                    key: self.identity[key]
                    for key in IDENTITY_FIELDS
                    if key != "solver_run_id"
                },
                "solver_config_id": solver_config_id,
                "tie_break_policy_id": tie_break_policy_id,
                "backend_semantics_version": backend_semantics_version,
            },
        )

    def require_same_identity(self, other):
        require_same_identity(self, other)
