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


def persistence_ranks(stages):
    """Independent image-coset enumeration; no projection or elimination input."""
    ranks = {}
    for i, source in enumerate(stages):
        for j in range(i, len(stages)):
            target = stages[j]
            positions = {
                label: index for index, label in enumerate(target["basis_current"])
            }
            target_boundaries = boundaries(target)
            cosets = set()
            for cycle in cycles(source):
                included = sum(
                    ((cycle >> index) & 1) << positions[label]
                    for index, label in enumerate(source["basis_current"])
                )
                cosets.add(min(included ^ boundary for boundary in target_boundaries))
            count = len(cosets)
            if count & (count - 1):
                raise ValueError("image quotient is not an F2 vector space")
            ranks[i, j] = count.bit_length() - 1
    return ranks


def persistence_barcode(stages):
    """Standard global boundary-column reduction on a truncated based filtration.

    C_(k-1) has zero outgoing boundary in the truncated complex, which preserves
    degree-k homology. Same-stage transient pairs are omitted from stored ranks.
    The implementation imports no production code and consumes no expected bars.
    """
    k = stages[0]["k"]
    cells, seen = [], set()
    for stage_index, stage in enumerate(stages):
        for degree, name in (
            (k - 1, "basis_previous"),
            (k, "basis_current"),
            (k + 1, "basis_next"),
        ):
            for coordinate, label in enumerate(stage[name]):
                cell = (degree, label)
                if cell in seen:
                    continue
                seen.add(cell)
                if degree == k - 1:
                    boundary = ()
                else:
                    matrix, row_names = (
                        (stage["A"], stage["basis_previous"])
                        if degree == k
                        else (stage["D"], stage["basis_current"])
                    )
                    boundary = tuple(
                        (degree - 1, row_names[row])
                        for row, values in enumerate(matrix["rows"])
                        if values[coordinate]
                    )
                cells.append((cell, stage_index, boundary))
    positions = {cell: index for index, (cell, _, _) in enumerate(cells)}
    pivots, births, paired, intervals = {}, {}, set(), []
    for index, (cell, stage_index, boundary) in enumerate(cells):
        column = {positions[face] for face in boundary}
        if any(row >= index for row in column):
            raise ValueError("a boundary must precede its cell")
        while column and max(column) in pivots:
            column ^= pivots[max(column)]
        if not column:
            births[index] = (cell[0], stage_index)
        else:
            pivot = max(column)
            pivots[pivot] = column
            paired.add(pivot)
            degree, birth = births[pivot]
            if degree == k and birth < stage_index:
                intervals.append((birth, stage_index))
    intervals.extend(
        (birth, None)
        for index, (degree, birth) in births.items()
        if degree == k and index not in paired
    )
    return tuple(
        sorted(intervals, key=lambda x: (x[0], len(stages) if x[1] is None else x[1]))
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


def rank_barcode(dimensions, maps):
    """Old full-interval rank formula; enumerate all images independently.

    Maps are packed columns. Only a small-scale test oracle, never a result
    source or a performance backend.
    """
    from collections import Counter

    ranks = {}
    for start, dimension in enumerate(dimensions):
        image = set(range(1 << dimension))
        ranks[start, start] = dimension
        for end in range(start + 1, len(dimensions)):
            image = {apply(maps[end - 1], vector) for vector in image}
            ranks[start, end] = len(image).bit_length() - 1

    def rank(i, j):
        return 0 if i < 0 or j >= len(dimensions) else ranks[i, j]

    result = Counter()
    for birth in range(len(dimensions)):
        for death in range(birth + 1, len(dimensions) + 1):
            count = (
                rank(birth, death - 1)
                - rank(birth - 1, death - 1)
                - rank(birth, death)
                + rank(birth - 1, death)
            )
            if count < 0:
                raise ValueError("negative interval multiplicity")
            if count:
                result[birth, None if death == len(dimensions) else death] = count
    return result, ranks
