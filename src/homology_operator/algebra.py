"""Small, exact F2 matrices in the caller's original ordered coordinates."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from functools import cached_property


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


@dataclass(frozen=True, init=False, eq=False)
class Matrix:
    """Immutable packed rows; binary tuples remain the public coordinate view.

    Elimination and image coordinates are prepared lazily on this matrix only.
    Neither decoded rows nor a quadratic row-transform matrix are retained.
    """

    nrows: int
    ncols: int
    rows: tuple[tuple[int, ...], ...]

    def __init__(self, nrows, ncols, rows):
        _dimension(nrows, "nrows")
        _dimension(ncols, "ncols")
        try:
            bits = tuple(
                sum(bit << i for i, bit in enumerate(validate_vector(row, ncols)))
                for row in rows
            )
        except TypeError as exc:
            raise ValueError("matrix rows must be iterable") from exc
        if len(bits) != nrows:
            raise ValueError(f"matrix must have {nrows} rows, got {len(bits)}")
        object.__setattr__(self, "nrows", nrows)
        object.__setattr__(self, "ncols", ncols)
        object.__setattr__(self, "_bits", bits)

    @classmethod
    def _from_packed(cls, rows, ncols):
        _dimension(ncols, "ncols")
        rows = tuple(rows)
        if any(
            type(row) is not int or row < 0 or row.bit_length() > ncols for row in rows
        ):
            raise ValueError("packed rows must have nonnegative bits within ncols")
        matrix = object.__new__(cls)
        object.__setattr__(matrix, "nrows", len(rows))
        object.__setattr__(matrix, "ncols", ncols)
        object.__setattr__(matrix, "_bits", rows)
        return matrix

    @classmethod
    def _from_native(cls, handle):
        matrix = object.__new__(cls)
        object.__setattr__(matrix, "nrows", handle.nrows)
        object.__setattr__(matrix, "ncols", handle.ncols)
        object.__setattr__(matrix, "_native_matrix", handle)
        return matrix

    @cached_property
    def _bits(self):
        # A native result stays resident until reference validation, coordinates,
        # hashing or the JSON wire format actually needs its packed Python view.
        return tuple(
            sum(word << (64 * j) for j, word in enumerate(row))
            for row in self._native_matrix.rows()
        )

    def _reference(self):
        """Fresh reference view with no backend or solver decomposition caches."""
        return Matrix._from_packed(self._bits, self.ncols)

    @property
    def rows(self):
        return tuple(self._unpack(row, self.ncols) for row in self._bits)

    @staticmethod
    def _unpack(bits, size):
        return tuple((bits >> i) & 1 for i in range(size))

    def __repr__(self):
        return f"Matrix(nrows={self.nrows}, ncols={self.ncols}, rows={self.rows!r})"

    def __eq__(self, other):
        if type(other) is not type(self):
            return NotImplemented
        return (self.nrows, self.ncols, self._bits) == (
            other.nrows,
            other.ncols,
            other._bits,
        )

    def __hash__(self):
        return hash((self.nrows, self.ncols, self._bits))

    @classmethod
    def zero(cls, nrows: int, ncols: int) -> Matrix:
        _dimension(nrows, "nrows")
        _dimension(ncols, "ncols")
        return cls._from_packed((0,) * nrows, ncols)

    @classmethod
    def identity(cls, size: int) -> Matrix:
        _dimension(size, "identity size")
        return cls._from_packed((1 << i for i in range(size)), size)

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
        rows, count = [0] * nrows, 0
        try:
            for column in columns:
                for i, bit in enumerate(validate_vector(column, nrows)):
                    if bit:
                        rows[i] |= 1 << count
                count += 1
        except TypeError as exc:
            raise ValueError("matrix columns must be iterable") from exc
        return cls._from_packed(rows, count)

    @classmethod
    def from_sparse_columns(cls, columns, nrows):
        """Construct from nonzero row indices, rejecting duplicate coordinates."""
        _dimension(nrows, "nrows")
        rows, count = [0] * nrows, 0
        try:
            for column in columns:
                seen = set()
                for i in column:
                    if type(i) is not int or not 0 <= i < nrows or i in seen:
                        raise ValueError(
                            "sparse column indices must be unique and in range"
                        )
                    seen.add(i)
                    rows[i] |= 1 << count
                count += 1
        except TypeError as exc:
            raise ValueError("sparse columns must be iterable") from exc
        return cls._from_packed(rows, count)

    def __add__(self, other: Matrix) -> Matrix:
        if not isinstance(other, Matrix):
            return NotImplemented
        if (self.nrows, self.ncols) != (other.nrows, other.ncols):
            raise ValueError("matrix addition requires equal shapes")
        if hasattr(self, "_native_matrix") or hasattr(other, "_native_matrix"):
            from .native import _matrix_handle

            return Matrix._from_native(_matrix_handle(self).add(_matrix_handle(other)))
        return Matrix._from_packed(
            (a ^ b for a, b in zip(self._bits, other._bits)), self.ncols
        )

    def __matmul__(self, other: Matrix) -> Matrix:
        if not isinstance(other, Matrix):
            return NotImplemented
        if self.ncols != other.nrows:
            raise ValueError("matrix product requires matching inner dimensions")
        if hasattr(self, "_native_matrix") or hasattr(other, "_native_matrix"):
            from .native import _matrix_handle

            return Matrix._from_native(
                _matrix_handle(self).product(_matrix_handle(other))
            )
        rows = []
        for bits in self._bits:
            output = 0
            while bits:
                low = bits & -bits
                output ^= other._bits[low.bit_length() - 1]
                bits ^= low
            rows.append(output)
        return Matrix._from_packed(rows, other.ncols)

    def apply(self, vector: Iterable[int]) -> tuple[int, ...]:
        data = validate_vector(vector, self.ncols)
        bits = sum(bit << i for i, bit in enumerate(data))
        return tuple((row & bits).bit_count() & 1 for row in self._bits)

    def transpose(self) -> Matrix:
        if hasattr(self, "_native_matrix"):
            return Matrix._from_native(self._native_matrix.transpose())
        rows = [0] * self.ncols
        for i, bits in enumerate(self._bits):
            while bits:
                low = bits & -bits
                rows[low.bit_length() - 1] |= 1 << i
                bits ^= low
        return Matrix._from_packed(rows, self.nrows)

    @cached_property
    def _reduction(self):
        rows = list(self._bits)
        pivots = []
        pivot_row = 0
        for column in range(self.ncols):
            selected = next(
                (
                    row
                    for row in range(pivot_row, self.nrows)
                    if rows[row] >> column & 1
                ),
                None,
            )
            if selected is None:
                continue
            rows[pivot_row], rows[selected] = rows[selected], rows[pivot_row]
            for row in range(self.nrows):
                if row != pivot_row and rows[row] >> column & 1:
                    rows[row] ^= rows[pivot_row]
            pivots.append(column)
            pivot_row += 1
            if pivot_row == self.nrows:
                break
        return tuple(rows), tuple(pivots)

    def rref(self) -> tuple[Matrix, tuple[int, ...]]:
        """Eliminate left to right, preserving the original stable pivot policy."""
        if hasattr(self, "_native_matrix"):
            return self._native_reduction.rref()
        rows, pivots = self._reduction
        return Matrix._from_packed(rows, self.ncols), pivots

    def rank(self) -> int:
        if hasattr(self, "_native_matrix"):
            return self._native_reduction.rank()
        return len(self._reduction[1])

    @cached_property
    def _native_reduction(self):
        from .native import PreparedMatrix

        return PreparedMatrix(self, full=False, diagnostics=False)

    def kernel_basis(self) -> tuple[tuple[int, ...], ...]:
        if hasattr(self, "_native_matrix"):
            return self._native_reduction.kernel_basis()
        reduced, pivots = self._reduction
        pivot_set = set(pivots)
        basis = []
        for free_column in range(self.ncols):
            if free_column in pivot_set:
                continue
            vector = [0] * self.ncols
            vector[free_column] = 1
            for row, pivot in enumerate(pivots):
                vector[pivot] = (reduced[row] >> free_column) & 1
            basis.append(tuple(vector))
        return tuple(basis)

    def image_basis(self) -> tuple[tuple[int, ...], ...]:
        if hasattr(self, "_native_matrix"):
            return self._native_reduction.image_basis()
        return tuple(
            tuple((row >> column) & 1 for row in self._bits)
            for column in self._reduction[1]
        )

    @cached_property
    def _image_solver(self):
        # Coordinates in the stable independent columns give the same solution
        # as augmented RREF with all free coordinates zero, without storing E.
        pivots = {}
        for column in self._reduction[1]:
            bits = sum(((row >> column) & 1) << i for i, row in enumerate(self._bits))
            coordinates = 1 << column
            while bits:
                pivot = bits.bit_length() - 1
                if pivot not in pivots:
                    pivots[pivot] = (bits, coordinates)
                    break
                other, coefficients = pivots[pivot]
                bits ^= other
                coordinates ^= coefficients
        return pivots

    def solve_many(self, vectors):
        """Solve a batch using one cached image-coordinate decomposition."""
        pivots = self._image_solver
        output = []
        for vector in vectors:
            data = validate_vector(vector, self.nrows)
            bits = sum(bit << i for i, bit in enumerate(data))
            coordinates = 0
            while bits:
                pivot = bits.bit_length() - 1
                if pivot not in pivots:
                    break
                other, coefficients = pivots[pivot]
                bits ^= other
                coordinates ^= coefficients
            output.append(None if bits else self._unpack(coordinates, self.ncols))
        return tuple(output)

    def solve(self, vector: Iterable[int]) -> tuple[int, ...] | None:
        """Return a solution with free coordinates zero, or None if inconsistent."""
        return self.solve_many((vector,))[0]


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
        if self.form == "HC" and not self.complement:
            H, C = self.factors
            # Check the small coordinate identity even for a directly constructed
            # action; shape checks alone do not establish rank(HC)=rank(H).
            if C @ H == Matrix.identity(C.nrows):
                return _reduced_span(H.transpose().rows, self.nrows)
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
