"""Validated, based F2 chain windows with explicit weight arithmetic."""

from dataclasses import dataclass, field
from fractions import Fraction
from math import isfinite
from types import MappingProxyType
from collections.abc import Mapping, Set

from .algebra import Matrix, CyclicAction, CompactAction


class InvalidInput(ValueError):
    """A chain window violates the public input contract."""


def _freeze_metadata(value):
    """Copy JSON metadata into immutable containers, rejecting lossy values."""
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise InvalidInput("metadata keys must be strings")
        return MappingProxyType(
            {key: _freeze_metadata(item) for key, item in value.items()}
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_metadata(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    raise InvalidInput("metadata must contain finite JSON values")


def _thaw_metadata(value):
    if isinstance(value, Mapping):
        return {key: _thaw_metadata(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_metadata(item) for item in value]
    return value


def matrix_data(matrix):
    """Preserve zero-dimensional matrix shapes in JSON-compatible data."""
    return {
        "nrows": matrix.nrows,
        "ncols": matrix.ncols,
        "rows": [list(row) for row in matrix.rows],
    }


def matrix_from_data(data):
    if not isinstance(data, Mapping) or set(data) != {"nrows", "ncols", "rows"}:
        raise InvalidInput("matrix data requires explicit nrows, ncols and rows")
    try:
        return Matrix(data["nrows"], data["ncols"], data["rows"])
    except (TypeError, ValueError) as error:
        raise InvalidInput(str(error)) from error


def action_data(action):
    if isinstance(action, CompactAction):
        return {
            "kind": "CompactF2",
            "version": 1,
            "form": action.form,
            "factors": [matrix_data(x) for x in action.factors],
            "pivots": [list(row) for row in action.pivots],
            "complement": action.complement,
        }
    if isinstance(action, CyclicAction):
        return {
            "kind": "CyclicTrace",
            "version": 1,
            "m": action.m,
            "complement": action.complement,
        }
    return matrix_data(action)


def action_from_data(data):
    if isinstance(data, Mapping) and data.get("kind") == "CompactF2":
        if (
            set(data) != {"kind", "version", "form", "factors", "pivots", "complement"}
            or type(data["version"]) is not int
            or data["version"] != 1
            or not isinstance(data["factors"], (tuple, list))
            or not isinstance(data["pivots"], (tuple, list))
        ):
            raise InvalidInput("unsupported compact action handle")
        return CompactAction(
            data["form"],
            tuple(matrix_from_data(x) for x in data["factors"]),
            data["pivots"],
            data["complement"],
        )
    if isinstance(data, Mapping) and data.get("kind") == "CyclicTrace":
        if (
            set(data) != {"kind", "version", "m", "complement"}
            or type(data["version"]) is not int
            or data["version"] != 1
        ):
            raise InvalidInput("unsupported cyclic action handle")
        return CyclicAction(data["m"], data["complement"])
    return matrix_from_data(data)


@dataclass(frozen=True)
class ChainWindow:
    """C_(k+1) --D--> C_k --A--> C_(k-1), using column coordinates."""

    k: int
    A: Matrix
    D: Matrix
    basis_previous: tuple
    basis_current: tuple
    basis_next: tuple
    weights: tuple
    weight_semantics: str = "abstract_positive_cost"
    unit: str | None = None
    arithmetic: str = "ExactRational"
    source_metadata: Mapping = field(default_factory=dict)

    def __post_init__(self):
        if type(self.k) is not int or self.k < 0:
            raise InvalidInput("k must be a nonnegative integer")
        if not isinstance(self.A, Matrix) or not isinstance(self.D, Matrix):
            raise InvalidInput("A and D must be explicit F2 matrices")
        if self.A.ncols != self.D.nrows:
            raise InvalidInput("A columns must equal D rows")
        for name, size in (
            ("basis_previous", self.A.nrows),
            ("basis_current", self.A.ncols),
            ("basis_next", self.D.ncols),
        ):
            if isinstance(getattr(self, name), (str, bytes, bytearray, Set, Mapping)):
                raise InvalidInput(
                    f"{name} must be ordered, not text or an unordered container"
                )
            try:
                basis = tuple(getattr(self, name))
            except TypeError as error:
                raise InvalidInput(f"{name} must be an ordered sequence") from error
            if len(basis) != size:
                raise InvalidInput(f"{name} length does not match its chain space")
            if any(not isinstance(label, str) or not label for label in basis):
                raise InvalidInput("basis identifiers must be nonempty strings")
            if len(set(basis)) != size:
                raise InvalidInput(f"{name} identifiers must be unique")
            object.__setattr__(self, name, basis)
        if self.A @ self.D != Matrix.zero(self.m, self.p):
            raise InvalidInput("chain condition AD=0 is required")
        if not isinstance(self.weight_semantics, str) or self.weight_semantics not in {
            "unit",
            "abstract_positive_cost",
            "euclidean_length",
            "euclidean_area",
            "euclidean_volume",
            "custom",
        }:
            raise InvalidInput("unknown weight semantics")
        if self.unit is not None and (not isinstance(self.unit, str) or not self.unit):
            raise InvalidInput("unit must be a nonempty string or None")
        if not isinstance(self.arithmetic, str) or self.arithmetic not in {
            "ExactInteger",
            "ExactRational",
            "FloatingPoint",
        }:
            raise InvalidInput("unsupported weight arithmetic")
        if isinstance(self.weights, (str, bytes, bytearray, Set, Mapping)):
            raise InvalidInput(
                "weights must be ordered, not text or an unordered container"
            )
        try:
            weights = tuple(self.weights)
        except TypeError as error:
            raise InvalidInput("weights must be a sequence") from error
        if len(weights) != self.n:
            raise InvalidInput("weight length does not match C_k")
        normalized = []
        for weight in weights:
            if isinstance(weight, bool):
                raise InvalidInput("boolean weights are not numeric costs")
            if self.arithmetic == "ExactInteger":
                if type(weight) is not int or weight <= 0:
                    raise InvalidInput("ExactInteger weights must be positive integers")
                normalized.append(weight)
            elif self.arithmetic == "ExactRational":
                if not isinstance(weight, (int, Fraction)) or weight <= 0:
                    raise InvalidInput(
                        "ExactRational weights must be positive integers or Fractions"
                    )
                normalized.append(Fraction(weight))
            else:
                if not isinstance(weight, (int, float, Fraction)):
                    raise InvalidInput("FloatingPoint weights must be numeric")
                try:
                    value = float(weight)
                except (OverflowError, ValueError) as error:
                    raise InvalidInput("weights must be finite") from error
                if not isfinite(value) or value <= 0:
                    raise InvalidInput("weights must be finite and strictly positive")
                normalized.append(value)
        object.__setattr__(self, "weights", tuple(normalized))
        if not isinstance(self.source_metadata, Mapping):
            raise InvalidInput("source_metadata must be a mapping")
        object.__setattr__(
            self, "source_metadata", _freeze_metadata(self.source_metadata)
        )

    @property
    def m(self):
        return self.A.nrows

    @property
    def n(self):
        return self.A.ncols

    @property
    def p(self):
        return self.D.ncols

    def identity(self):
        """Content identity of the validated input, coordinate bases and weights."""
        from .result import input_identity

        return input_identity(self)

    def to_dict(self):
        weights = []
        for weight in self.weights:
            if isinstance(weight, Fraction):
                weights.append(
                    {
                        "type": "rational",
                        "numerator": weight.numerator,
                        "denominator": weight.denominator,
                    }
                )
            else:
                weights.append(
                    {
                        "type": "float" if isinstance(weight, float) else "integer",
                        "value": weight,
                    }
                )
        return {
            "k": self.k,
            "A": matrix_data(self.A),
            "D": matrix_data(self.D),
            "basis_previous": list(self.basis_previous),
            "basis_current": list(self.basis_current),
            "basis_next": list(self.basis_next),
            "weights": weights,
            "weight_semantics": self.weight_semantics,
            "unit": self.unit,
            "arithmetic": self.arithmetic,
            "source_metadata": _thaw_metadata(self.source_metadata),
        }

    @classmethod
    def from_dict(cls, data):
        fields = {
            "k",
            "A",
            "D",
            "basis_previous",
            "basis_current",
            "basis_next",
            "weights",
            "weight_semantics",
            "unit",
            "arithmetic",
            "source_metadata",
        }
        if not isinstance(data, Mapping) or set(data) != fields:
            raise InvalidInput("chain data has missing or unknown fields")
        weights = []
        try:
            for item in data["weights"]:
                if not isinstance(item, Mapping):
                    raise InvalidInput("weights require explicit arithmetic tags")
                if item.get("type") == "rational" and set(item) == {
                    "type",
                    "numerator",
                    "denominator",
                }:
                    if (
                        type(item["numerator"]) is not int
                        or type(item["denominator"]) is not int
                    ):
                        raise InvalidInput(
                            "rational numerator and denominator must be integers"
                        )
                    weights.append(Fraction(item["numerator"], item["denominator"]))
                elif item.get("type") in {"integer", "float"} and set(item) == {
                    "type",
                    "value",
                }:
                    if item["type"] == "integer" and type(item["value"]) is not int:
                        raise InvalidInput("integer weight tag requires an integer")
                    if item["type"] == "float" and type(item["value"]) is not float:
                        raise InvalidInput("float weight tag requires a float")
                    weights.append(item["value"])
                else:
                    raise InvalidInput("invalid weight encoding")
            return cls(
                data["k"],
                matrix_from_data(data["A"]),
                matrix_from_data(data["D"]),
                data["basis_previous"],
                data["basis_current"],
                data["basis_next"],
                weights,
                data["weight_semantics"],
                data["unit"],
                data["arithmetic"],
                data["source_metadata"],
            )
        except (TypeError, KeyError, ZeroDivisionError) as error:
            raise InvalidInput("invalid chain encoding") from error
