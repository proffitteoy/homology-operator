"""Validated, based F2 chain windows with explicit weight arithmetic."""

from dataclasses import dataclass, field
from fractions import Fraction
from math import isfinite
from types import MappingProxyType
from collections.abc import Mapping, Set

from .algebra import Matrix, CyclicAction, CompactAction, validate_vector


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


def _validate_source_mapping(window):
    """Validate the optional v1 simplicial source protocol against actual A/D."""
    mapping = window.source_metadata.get("source_mapping")
    if "source_mapping" not in window.source_metadata:
        return
    fields = {
        "version",
        "source_hash",
        "stage_order",
        "stage",
        "scale",
        "vertices",
        "simplices",
        "embedding",
    }
    if not isinstance(mapping, Mapping) or set(mapping) != fields:
        raise InvalidInput("source_mapping has missing or unknown fields")
    if type(mapping["version"]) is not int or mapping["version"] != 1:
        raise InvalidInput("unsupported source mapping version")
    digest = mapping["source_hash"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise InvalidInput("source_hash must be a lowercase SHA-256 digest")
    order, stage = mapping["stage_order"], mapping["stage"]
    if (
        not isinstance(order, tuple)
        or not order
        or any(not isinstance(x, str) or not x for x in order)
        or len(set(order)) != len(order)
        or type(stage) is not int
        or not 0 <= stage < len(order)
    ):
        raise InvalidInput("source mapping requires a total stage order and index")
    if type(mapping["scale"]) not in (int, float):
        raise InvalidInput("source mapping scale must be a finite JSON number")
    vertices, simplices, embedding = (
        mapping["vertices"],
        mapping["simplices"],
        mapping["embedding"],
    )
    if not isinstance(vertices, Mapping) or not isinstance(simplices, Mapping):
        raise InvalidInput("vertices and simplices must be mappings")
    dimension, periods = 0, ()
    if embedding is not None:
        if not isinstance(embedding, Mapping) or set(embedding) != {
            "dimension",
            "unit",
            "metric",
            "periods",
        }:
            raise InvalidInput("invalid embedding fields")
        dimension, periods = embedding["dimension"], embedding["periods"]
        if (
            type(dimension) is not int
            or dimension <= 0
            or not isinstance(embedding["unit"], str)
            or not embedding["unit"]
            or embedding["metric"] != "euclidean"
            or not isinstance(periods, tuple)
            or len(periods) != dimension
            or any(
                p is not None and (type(p) not in (int, float) or p <= 0)
                for p in periods
            )
        ):
            raise InvalidInput(
                "embedding needs a unit and positive axis periods or null"
            )
        power = {"euclidean_length": 1, "euclidean_area": 2, "euclidean_volume": 3}.get(
            window.weight_semantics
        )
        if power is not None and (
            window.k != power
            or window.unit
            != (embedding["unit"] if power == 1 else f"{embedding['unit']}^{power}")
        ):
            raise InvalidInput("Euclidean weight degree/unit disagrees with embedding")
    original_ids = set()
    for vertex, record in vertices.items():
        if (
            not vertex
            or not isinstance(record, Mapping)
            or set(record) != {"original_id", "coordinates"}
        ):
            raise InvalidInput("vertices need original_id and coordinates")
        original = record["original_id"]
        if (
            type(original) not in (str, int)
            or original == ""
            or original in original_ids
        ):
            raise InvalidInput("original IDs must be unique strings or integers")
        original_ids.add(original)
        coordinates = record["coordinates"]
        if embedding is None:
            if coordinates is not None:
                raise InvalidInput("coordinates require a declared embedding")
        elif (
            not isinstance(coordinates, tuple)
            or len(coordinates) != dimension
            or any(type(c) not in (int, float) for c in coordinates)
            or any(
                p is not None and not 0 <= c < p for c, p in zip(coordinates, periods)
            )
        ):
            raise InvalidInput(
                "coordinates must be finite and in the periodic base cell"
            )
    bases = (window.basis_previous, window.basis_current, window.basis_next)
    if window.k == 0 and window.m:
        raise InvalidInput("source mapping uses unaugmented H0 with empty C_-1")
    labels = sum(bases, ())
    if len(set(labels)) != len(labels) or set(simplices) != set(labels):
        raise InvalidInput("source simplices must cover three globally distinct bases")
    for degree, basis in zip((window.k - 1, window.k, window.k + 1), bases):
        seen = set()
        for label in basis:
            record = simplices[label]
            if not isinstance(record, Mapping) or set(record) != {
                "vertices",
                "offsets",
            }:
                raise InvalidInput("simplices need vertices and offsets")
            ids, offsets = record["vertices"], record["offsets"]
            if (
                not isinstance(ids, tuple)
                or len(ids) != degree + 1
                or any(not isinstance(v, str) or v not in vertices for v in ids)
                or len(set(ids)) != len(ids)
                or frozenset(ids) in seen
            ):
                raise InvalidInput("invalid or duplicate simplex vertex set")
            seen.add(frozenset(ids))
            if embedding is None:
                if offsets is not None:
                    raise InvalidInput("offsets require an embedding")
            elif (
                not isinstance(offsets, tuple)
                or len(offsets) != len(ids)
                or any(
                    not isinstance(row, tuple)
                    or len(row) != dimension
                    or any(
                        type(x) is not int or (p is None and x != 0)
                        for x, p in zip(row, periods)
                    )
                    for row in offsets
                )
                or offsets[0] != (0,) * dimension
            ):
                raise InvalidInput(
                    "simplex offsets need integer lifts, first vertex zero"
                )
    for matrix, lower, upper in (
        (window.A, bases[0], bases[1]),
        (window.D, bases[1], bases[2]),
    ):
        if not lower and window.k == 0 and matrix is window.A:
            continue  # The unaugmented boundary of a vertex is zero.
        positions = {
            frozenset(simplices[x]["vertices"]): i for i, x in enumerate(lower)
        }
        expected_bits = [0] * matrix.nrows
        for column, label in enumerate(upper):
            record = simplices[label]
            ids = record["vertices"]
            facets = [frozenset(ids[:i] + ids[i + 1 :]) for i in range(len(ids))]
            if any(face not in positions for face in facets):
                raise InvalidInput("source simplex is missing a boundary face")
            expected = {positions[face] for face in facets}
            for row in expected:
                expected_bits[row] |= 1 << column
            if embedding is not None:
                lifts = dict(zip(ids, record["offsets"]))
                for row in expected:
                    face = simplices[lower[row]]
                    anchor = lifts[face["vertices"][0]]
                    if any(
                        tuple(a - b for a, b in zip(lifts[v], anchor)) != offset
                        for v, offset in zip(face["vertices"], face["offsets"])
                    ):
                        raise InvalidInput(
                            "periodic face lifts disagree across simplices"
                        )
        if tuple(expected_bits) != matrix._bits:
            raise InvalidInput("source simplices disagree with boundary matrices")


def matrix_data(matrix):
    """Preserve zero-dimensional matrix shapes in JSON-compatible data."""
    return {
        "nrows": matrix.nrows,
        "ncols": matrix.ncols,
        "rows": [list(Matrix._unpack(row, matrix.ncols)) for row in matrix._bits],
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


def _filling_request(window, z, filling_window):
    """Bind a fixed boundary to explicitly sourced upper-degree costs."""
    if not isinstance(window, ChainWindow) or not isinstance(
        filling_window, ChainWindow
    ):
        raise InvalidInput("minimum filling requires two validated ChainWindows")
    if (
        filling_window.k != window.k + 1
        or filling_window.A != window.D
        or filling_window.basis_previous != window.basis_current
        or filling_window.basis_current != window.basis_next
    ):
        raise InvalidInput(
            "filling window must match D and its ordered bases at degree k+1"
        )
    z = validate_vector(z, window.n)
    if any(window.A.apply(z)):
        raise InvalidInput("fixed-boundary filling requires a cycle")
    source = filling_window.source_metadata.get("source")
    if not isinstance(source, str) or not source.strip() or filling_window.unit is None:
        raise InvalidInput("upper weights require an explicit unit and nonempty source")
    semantics = filling_window.weight_semantics
    degrees = {"euclidean_length": 1, "euclidean_area": 2, "euclidean_volume": 3}
    if semantics in degrees and filling_window.k != degrees[semantics]:
        raise InvalidInput(
            "geometric weight dimension does not match the filling degree"
        )
    if semantics == "unit" and any(w != 1 for w in filling_window.weights):
        raise InvalidInput("unit counting requires every upper weight to equal one")
    from .result import content_id

    return z, content_id(
        "filling-problem",
        {
            "window": window.to_dict(),
            "boundary": z,
            "filling_window": filling_window.to_dict(),
        },
    )


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
        _validate_source_mapping(self)

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

    def locate_chain(self, chain, degree=0, source_mapping_id=None):
        """Locate a raw chain at degree offset -1/0/1, without class semantics."""
        if type(degree) is not int or degree not in (-1, 0, 1):
            raise InvalidInput("location degree offset must be -1, 0 or 1")
        basis = (self.basis_previous, self.basis_current, self.basis_next)[degree + 1]
        chain = validate_vector(chain, len(basis))
        identity = self.identity()
        mapping_id = identity.get("source_mapping_id")
        if source_mapping_id is not None and source_mapping_id != mapping_id:
            raise InvalidInput("source mapping identity mismatch")
        support = tuple(i for i, bit in enumerate(chain) if bit)
        mapping = self.source_metadata.get("source_mapping")
        objects = []
        for index in support:
            label = basis[index]
            item = {
                "index": index,
                "label": label,
                "vertices": None,
                "original_ids": None,
                "coordinates": None,
                "offsets": None,
            }
            if mapping is not None:
                simplex = mapping["simplices"][label]
                ids, offsets = simplex["vertices"], simplex["offsets"]
                records = [mapping["vertices"][v] for v in ids]
                coordinates = None
                if mapping["embedding"] is not None:
                    periods = mapping["embedding"]["periods"]
                    try:
                        coordinates = tuple(
                            tuple(
                                c if p is None else c + shift * p
                                for c, shift, p in zip(v["coordinates"], lift, periods)
                            )
                            for v, lift in zip(records, offsets)
                        )
                    except OverflowError as error:
                        raise InvalidInput(
                            "NumericalFailure: lifted coordinates overflow"
                        ) from error
                    if any(
                        isinstance(c, float) and not isfinite(c)
                        for row in coordinates
                        for c in row
                    ):
                        raise InvalidInput(
                            "NumericalFailure: lifted coordinates overflow"
                        )
                item.update(
                    vertices=ids,
                    original_ids=tuple(v["original_id"] for v in records),
                    coordinates=coordinates,
                    offsets=offsets,
                )
            objects.append(item)
        components = None
        if mapping is not None:
            remaining = set(support)
            vertex_sets = {x["index"]: set(x["vertices"]) for x in objects}
            by_vertex = {}
            for index, vertices in vertex_sets.items():
                for vertex in vertices:
                    by_vertex.setdefault(vertex, set()).add(index)
            components = []
            while remaining:
                pending = [min(remaining)]
                component = []
                remaining.remove(pending[0])
                while pending:
                    index = pending.pop()
                    component.append(index)
                    for vertex in vertex_sets[index]:
                        adjacent = by_vertex.pop(vertex, set()) & remaining
                        remaining -= adjacent
                        pending.extend(sorted(adjacent))
                components.append(tuple(sorted(component)))
        value = {
            "input_id": identity["input_id"],
            "basis_id": identity["basis_id"],
            "source_mapping_id": mapping_id,
            "degree": self.k + degree,
            "support": support,
            "simplices": objects,
            "components": components,
            "source_hash": None if mapping is None else mapping["source_hash"],
            "stage": None if mapping is None else mapping["stage"],
            "scale": None if mapping is None else mapping["scale"],
            "stage_order": None if mapping is None else mapping["stage_order"],
            "embedding": None if mapping is None else mapping["embedding"],
            "weight_semantics": self.weight_semantics,
            "weight_unit": self.unit,
            "weight_degree": self.k,
        }
        from .result import content_id

        value["location_id"] = content_id("location", value)
        return _freeze_metadata(value)

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
