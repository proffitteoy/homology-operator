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
