"""Small independent F2 oracle: enumerate chains and column combinations.

This module imports no production code and performs no matrix elimination.
Packed integer bit i always denotes coordinate i in the fixture's current basis.
"""

from fractions import Fraction
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path


INPUT_FIELDS = (
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
)


def fixture_input_hash(fixture):
    payload = {key: fixture[key] for key in INPUT_FIELDS}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def columns(matrix):
    """Read explicitly shaped JSON matrices without importing Matrix."""
    nrows, ncols, rows = matrix["nrows"], matrix["ncols"], matrix["rows"]
    if type(nrows) is not int or type(ncols) is not int or min(nrows, ncols) < 0:
        raise ValueError("invalid matrix shape")
    if len(rows) != nrows or any(len(row) != ncols for row in rows):
        raise ValueError("matrix rows do not match explicit shape")
    if any(
        type(value) is not int or value not in (0, 1) for row in rows for value in row
    ):
        raise ValueError("matrix coordinates must be literal binary integers")
    return tuple(sum(row[j] << i for i, row in enumerate(rows)) for j in range(ncols))


def apply(column_values, chain):
    """XOR the selected columns; column_values is a tuple of packed integers."""
    if type(chain) is not int or not 0 <= chain < 1 << len(column_values):
        raise ValueError("chain does not fit the ordered input basis")
    result = 0
    for i, column in enumerate(column_values):
        if chain & (1 << i):
            result ^= column
    return result


def span(column_values):
    """Enumerate every column combination, including dependent combinations."""
    return tuple(
        sorted(
            {apply(column_values, choice) for choice in range(1 << len(column_values))}
        )
    )


def cycles(fixture):
    a = columns(fixture["A"])
    return tuple(
        chain for chain in range(1 << fixture["A"]["ncols"]) if apply(a, chain) == 0
    )


def boundaries(fixture):
    return span(columns(fixture["D"]))


def quotient_classes(fixture):
    """Return all cycle cosets, ordered by their smallest integer coordinate."""
    remaining = set(cycles(fixture))
    boundary_values = boundaries(fixture)
    classes = []
    while remaining:
        first = min(remaining)
        coset = tuple(sorted(first ^ boundary for boundary in boundary_values))
        if not set(coset) <= remaining:
            raise ValueError("boundary image is not contained in the cycle space")
        classes.append(coset)
        remaining.difference_update(coset)
    return tuple(classes)


def betti(fixture):
    count = len(quotient_classes(fixture))
    if count & (count - 1):
        raise ValueError("quotient cardinality must be a power of two")
    return count.bit_length() - 1


def weights(fixture):
    values = []
    for item in fixture["weights"]:
        if isinstance(item, dict):
            if (
                set(item) != {"numerator", "denominator"}
                or type(item["numerator"]) is not int
                or type(item["denominator"]) is not int
            ):
                raise ValueError("invalid exact rational weight")
            value = Fraction(item["numerator"], item["denominator"])
        elif type(item) is float and isfinite(item):
            value = item
        else:
            raise ValueError("weight must be an exact rational record or finite float")
        if value <= 0:
            raise ValueError("weight must be strictly positive")
        values.append(value)
    return tuple(values)


def mass(chain, weight_values):
    if type(chain) is not int or not 0 <= chain < 1 << len(weight_values):
        raise ValueError("chain does not fit the weight coordinates")
    return sum(weight for i, weight in enumerate(weight_values) if chain & (1 << i))


def support(chain):
    if type(chain) is not int or chain < 0:
        raise ValueError("support requires a nonnegative binary integer")
    return tuple(i for i in range(chain.bit_length()) if chain & (1 << i))


def shared_support(first, second):
    return tuple(sorted(set(support(first)) & set(support(second))))


def union_support(first, second):
    return tuple(sorted(set(support(first)) | set(support(second))))


def minimum_class_masses(fixture):
    """Oracle-only class minima; these are never substituted for selected mass."""
    values = weights(fixture)
    return tuple(
        min(mass(chain, values) for chain in coset)
        for coset in quotient_classes(fixture)
    )


def verify_projection(fixture, projection_columns):
    """Check every ambient chain and cycle independently; return a bool.

    The projection input is a tuple of n packed columns, never a production
    Matrix. All four requirements are checked, including class preservation.
    """
    n = fixture["A"]["ncols"]
    if len(projection_columns) != n or any(
        type(c) is not int or not 0 <= c < 1 << n for c in projection_columns
    ):
        return False
    a = columns(fixture["A"])
    boundary_values = set(boundaries(fixture))
    for chain in range(1 << n):
        image = apply(projection_columns, chain)
        if apply(projection_columns, image) != image or apply(a, image) != 0:
            return False
        if chain in boundary_values and image != 0:
            return False
        if apply(a, chain) == 0 and chain ^ image not in boundary_values:
            return False
    return True


def objective(fixture, projection_columns):
    """Current-P cycle norm, with the documented empty-domain value zero."""
    values = weights(fixture)
    return max(
        (
            mass(apply(projection_columns, chain), values) / mass(chain, values)
            for chain in cycles(fixture)
            if chain
        ),
        default=Fraction(0),
    )


def load_fixtures(path=None):
    if path is None:
        path = Path(__file__).resolve().parents[1] / "fixtures" / "reference.json"
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    fixtures = data["fixtures"]
    identifiers = set()
    for fixture in fixtures:
        if fixture["id"] in identifiers:
            raise ValueError("duplicate fixture id")
        identifiers.add(fixture["id"])
        if fixture_input_hash(fixture) != fixture["input_hash"]:
            raise ValueError("fixture input hash mismatch")
        a, d = columns(fixture["A"]), columns(fixture["D"])
        if fixture["D"]["nrows"] != len(a) or any(apply(a, c) for c in d):
            raise ValueError("fixture violates AD=0")
        for name, length in (
            ("basis_previous", fixture["A"]["nrows"]),
            ("basis_current", len(a)),
            ("basis_next", len(d)),
        ):
            if len(fixture[name]) != length or len(set(fixture[name])) != length:
                raise ValueError("fixture basis has wrong length or duplicate labels")
        if len(weights(fixture)) != len(a):
            raise ValueError("fixture weight count does not match current chain space")
        if betti(fixture) != fixture["expected"]["betti"]:
            raise ValueError("fixture Betti expectation does not match enumeration")
    return tuple(fixtures)
