"""Small, exact F2 matrices in the caller's original ordered coordinates."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable


def _dimension(value: int, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def validate_vector(vector: Iterable[int], size: int) -> tuple[int, ...]:
    """Return immutable binary coordinates, without truncation or reduction."""
    _dimension(size, "vector size")
    try:
        result = tuple(vector)
    except TypeError as exc:
        raise ValueError("vector must be an iterable of binary integers") from exc
    if len(result) != size:
        raise ValueError(f"vector length must be {size}, got {len(result)}")
    if any(type(value) is not int or value not in (0, 1) for value in result):
        raise ValueError("F2 coordinates must be integers 0 or 1")
    return result


@dataclass(frozen=True)
class Matrix:
    """Immutable row storage with explicit dimensions, including empty shapes."""

    nrows: int
    ncols: int
    rows: tuple[tuple[int, ...], ...]

    def __post_init__(self) -> None:
        _dimension(self.nrows, "nrows")
        _dimension(self.ncols, "ncols")
        try:
            rows = tuple(validate_vector(row, self.ncols) for row in self.rows)
        except TypeError as exc:
            raise ValueError("matrix rows must be iterable") from exc
        if len(rows) != self.nrows:
            raise ValueError(f"matrix must have {self.nrows} rows, got {len(rows)}")
        object.__setattr__(self, "rows", rows)

    @classmethod
    def zero(cls, nrows: int, ncols: int) -> Matrix:
        _dimension(nrows, "nrows")
        _dimension(ncols, "ncols")
        return cls(nrows, ncols, ((0,) * ncols,) * nrows)

    @classmethod
    def identity(cls, size: int) -> Matrix:
        _dimension(size, "identity size")
        return cls(
            size,
            size,
            tuple(
                tuple(int(row == column) for column in range(size))
                for row in range(size)
            ),
        )

    @classmethod
    def from_rows(
        cls, rows: Iterable[Iterable[int]], ncols: int | None = None
    ) -> Matrix:
        try:
            data = tuple(tuple(row) for row in rows)
        except TypeError as exc:
            raise ValueError("matrix rows must be iterable") from exc
        if ncols is None:
            ncols = len(data[0]) if data else 0
        return cls(len(data), ncols, data)

    @classmethod
    def from_columns(cls, columns: Iterable[Iterable[int]], nrows: int) -> Matrix:
        _dimension(nrows, "nrows")
        try:
            data = tuple(validate_vector(column, nrows) for column in columns)
        except TypeError as exc:
            raise ValueError("matrix columns must be iterable") from exc
        return cls(
            nrows,
            len(data),
            tuple(tuple(column[row] for column in data) for row in range(nrows)),
        )

    def __add__(self, other: Matrix) -> Matrix:
        if not isinstance(other, Matrix):
            return NotImplemented
        if (self.nrows, self.ncols) != (other.nrows, other.ncols):
            raise ValueError("matrix addition requires equal shapes")
        return Matrix(
            self.nrows,
            self.ncols,
            tuple(
                tuple(left ^ right for left, right in zip(row, other_row))
                for row, other_row in zip(self.rows, other.rows)
            ),
        )

    def __matmul__(self, other: Matrix) -> Matrix:
        if not isinstance(other, Matrix):
            return NotImplemented
        if self.ncols != other.nrows:
            raise ValueError("matrix product requires matching inner dimensions")
        columns = other.transpose().rows
        return Matrix(
            self.nrows,
            other.ncols,
            tuple(
                tuple(
                    sum(left * right for left, right in zip(row, column)) % 2
                    for column in columns
                )
                for row in self.rows
            ),
        )

    def apply(self, vector: Iterable[int]) -> tuple[int, ...]:
        data = validate_vector(vector, self.ncols)
        return tuple(
            sum(left * right for left, right in zip(row, data)) % 2 for row in self.rows
        )

    def transpose(self) -> Matrix:
        return Matrix.from_columns(self.rows, nrows=self.ncols)

    def rref(self) -> tuple[Matrix, tuple[int, ...]]:
        """Eliminate rows left to right; never permute the caller's columns."""
        rows = [list(row) for row in self.rows]
        pivots = []
        pivot_row = 0
        for column in range(self.ncols):
            selected = next(
                (row for row in range(pivot_row, self.nrows) if rows[row][column]), None
            )
            if selected is None:
                continue
            rows[pivot_row], rows[selected] = rows[selected], rows[pivot_row]
            for row in range(self.nrows):
                if row != pivot_row and rows[row][column]:
                    rows[row] = [
                        left ^ right for left, right in zip(rows[row], rows[pivot_row])
                    ]
            pivots.append(column)
            pivot_row += 1
            if pivot_row == self.nrows:
                break
        return Matrix.from_rows(rows, ncols=self.ncols), tuple(pivots)

    def rank(self) -> int:
        return len(self.rref()[1])

    def kernel_basis(self) -> tuple[tuple[int, ...], ...]:
        reduced, pivots = self.rref()
        basis = []
        for free_column in range(self.ncols):
            if free_column in pivots:
                continue
            vector = [0] * self.ncols
            vector[free_column] = 1
            for row, pivot in enumerate(pivots):
                vector[pivot] = reduced.rows[row][free_column]
            basis.append(tuple(vector))
        return tuple(basis)

    def image_basis(self) -> tuple[tuple[int, ...], ...]:
        _, pivots = self.rref()
        return tuple(tuple(row[column] for row in self.rows) for column in pivots)

    def solve(self, vector: Iterable[int]) -> tuple[int, ...] | None:
        """Return a solution with free coordinates zero, or None if inconsistent."""
        data = validate_vector(vector, self.nrows)
        augmented = Matrix(
            self.nrows,
            self.ncols + 1,
            tuple(row + (value,) for row, value in zip(self.rows, data)),
        )
        reduced, pivots = augmented.rref()
        if self.ncols in pivots:
            return None
        solution = [0] * self.ncols
        for row, pivot in enumerate(pivots):
            solution[pivot] = reduced.rows[row][-1]
        return tuple(solution)


@dataclass(frozen=True)
class CyclicAction:
    """Version-1 handle for pinned T-B1 P_m, or I+P_m, without dense storage.

    The reference certificate currently supports m=2,3,4. Kernel readouts may
    allocate their output basis; apply needs only linear temporary storage.
    """

    m: int
    complement: bool = False

    def __post_init__(self):
        if type(self.m) is not int or not 2 <= self.m <= 4:
            raise ValueError("CyclicAction requires 2 <= m <= 4")
        if type(self.complement) is not bool:
            raise ValueError("complement must be a boolean")

    @property
    def nrows(self):
        return (1 << self.m) - 1

    @property
    def ncols(self):
        return self.nrows

    def apply(self, vector):
        vector = validate_vector(vector, self.ncols)
        n = self.nrows
        packed = sum(bit << j for j, bit in enumerate(vector))
        mask = (1 << n) - 1
        output = packed if self.complement else 0
        for i in range(self.m):
            shift = 1 << i
            output ^= ((packed << shift) & mask) | (packed >> (n - shift))
        return tuple((output >> j) & 1 for j in range(n))

    def __matmul__(self, other):
        if not isinstance(other, Matrix):
            return NotImplemented
        if self.ncols != other.nrows:
            raise ValueError("action product requires matching inner dimensions")
        return Matrix.from_columns(
            (self.apply(z) for z in other.transpose().rows), nrows=self.nrows
        )

    def rank(self):
        rank = 1 << (self.m - 1)
        return self.nrows - rank if self.complement else rank

    def kernel_basis(self):
        # For an idempotent, ker(P)=im(I+P). Stream columns instead of building P.
        other = CyclicAction(self.m, not self.complement)
        pivots, selected = {}, []
        for j in range(self.ncols):
            z = other.apply(tuple(int(i == j) for i in range(self.ncols)))
            packed = sum(bit << i for i, bit in enumerate(z))
            while packed:
                pivot = packed.bit_length() - 1
                if pivot not in pivots:
                    pivots[pivot] = packed
                    selected.append(z)
                    break
                packed ^= pivots[pivot]
        return tuple(selected)


def _reduced_span(vectors, size):
    """Canonical span basis, with rightmost pivots in increasing order.

    The canonical kernel of a left-to-right RREF has exactly this form:
    each free coordinate is the last nonzero bit of its basis vector.
    Streaming vectors avoids constructing a matrix of all action columns.
    """
    pivots = {}
    for vector in vectors:
        bits = sum(bit << i for i, bit in enumerate(validate_vector(vector, size)))
        for pivot in sorted(pivots, reverse=True):
            if bits >> pivot & 1:
                bits ^= pivots[pivot]
        if not bits:
            continue
        pivot = bits.bit_length() - 1
        for other in pivots:
            if pivots[other] >> pivot & 1:
                pivots[other] ^= bits
        pivots[pivot] = bits
    return tuple(
        tuple((pivots[p] >> i) & 1 for i in range(size)) for p in sorted(pivots)
    )


@dataclass(frozen=True)
class CompactAction:
    """Version-1 linear action, without an explicit G/U/P/L.

    GeneralizedInverse stores A,D and only nonzero inverse rows, indexed by
    original pivot coordinates. HC stores H,C. Shapes are checked here;
    projection legality is independently checked at the operator boundary.
    Kernel uses im(I+P)=ker(P), so this readout requires verified idempotence.
    """

    form: str
    factors: tuple[Matrix, ...]
    pivots: tuple[tuple[int, ...], ...] = ()
    complement: bool = False

    def __post_init__(self):
        factors = tuple(self.factors)
        pivots = tuple(tuple(row) for row in self.pivots)
        if (
            any(not isinstance(factor, Matrix) for factor in factors)
            or type(self.complement) is not bool
        ):
            raise ValueError(
                "compact action requires immutable matrices and boolean complement"
            )
        if self.form == "GeneralizedInverse" and len(factors) == 4 and len(pivots) == 2:
            A, D, g, u = factors
            if (
                A.ncols != D.nrows
                or (g.nrows, g.ncols) != (len(pivots[0]), A.nrows)
                or (u.nrows, u.ncols) != (len(pivots[1]), D.nrows)
            ):
                raise ValueError("compact inverse factor shapes differ")
            for indices, limit in zip(pivots, (A.ncols, D.ncols)):
                if (
                    any(type(i) is not int or not 0 <= i < limit for i in indices)
                    or tuple(sorted(set(indices))) != indices
                ):
                    raise ValueError(
                        "compact inverse pivots must preserve original coordinates"
                    )
        elif self.form == "HC" and len(factors) == 2 and not pivots:
            H, C = factors
            if H.ncols != C.nrows or H.nrows != C.ncols:
                raise ValueError("HC factor shapes differ")
        else:
            raise ValueError("unsupported compact action form")
        object.__setattr__(self, "factors", factors)
        object.__setattr__(self, "pivots", pivots)

    @property
    def nrows(self):
        return (
            self.factors[0].ncols
            if self.form == "GeneralizedInverse"
            else self.factors[0].nrows
        )

    @property
    def ncols(self):
        return self.nrows

    def _inverse(self, index, vector):
        matrix = self.factors[index + 2]
        size = self.factors[index].ncols
        output = [0] * size
        for pivot, bit in zip(self.pivots[index], matrix.apply(vector)):
            output[pivot] = bit
        return tuple(output)

    def apply(self, vector):
        x = validate_vector(vector, self.ncols)
        if self.form == "GeneralizedInverse":
            A, D, _, _ = self.factors
            ga = self._inverse(0, A.apply(x))
            r = tuple(a ^ b for a, b in zip(x, ga))
            du = D.apply(self._inverse(1, r))
            p = tuple(a ^ b for a, b in zip(r, du))
        else:
            H, C = self.factors
            p = H.apply(C.apply(x))
        return tuple(a ^ b for a, b in zip(x, p)) if self.complement else p

    def complemented(self):
        return CompactAction(self.form, self.factors, self.pivots, not self.complement)

    def image_basis(self):
        return _reduced_span(
            (
                self.apply(tuple(int(i == j) for i in range(self.ncols)))
                for j in range(self.ncols)
            ),
            self.nrows,
        )

    def kernel_basis(self):
        return self.complemented().image_basis()

    def rank(self):
        return len(self.image_basis())

    def __matmul__(self, other):
        if not isinstance(other, Matrix):
            return NotImplemented
        if self.ncols != other.nrows:
            raise ValueError("action product requires matching dimensions")
        return Matrix.from_columns(
            (self.apply(x) for x in other.transpose().rows), nrows=self.nrows
        )
