"""Independent exhaustive checks for the small F2 reference algebra."""

from dataclasses import FrozenInstanceError
from itertools import product
import unittest

from homology_operator.algebra import Matrix, validate_vector


def vectors(size):
    return tuple(product((0, 1), repeat=size))


def multiply_rows(rows, vector):
    # Direct finite-field oracle using integer bit parity.
    return tuple(
        sum(row[index] for index, value in enumerate(vector) if value) & 1
        for row in rows
    )


def span(basis, dimension):
    return {
        tuple(
            sum(
                coefficient * vector[index]
                for coefficient, vector in zip(coefficients, basis)
            )
            & 1
            for index in range(dimension)
        )
        for coefficients in vectors(len(basis))
    }


class MatrixInputTests(unittest.TestCase):
    def test_construction_preserves_coordinates_and_immutability(self):
        rows = [[1, 0], [0, 1]]
        matrix = Matrix(2, 2, rows)
        rows[0][0] = 0
        self.assertEqual(matrix.rows, ((1, 0), (0, 1)))
        with self.assertRaises(FrozenInstanceError):
            matrix.nrows = 3
        self.assertEqual(Matrix.from_columns(((1, 0), (0, 1)), 2), matrix)
        self.assertEqual(validate_vector(iter((1, 0)), 2), (1, 0))

    def test_invalid_coordinates_and_dimensions(self):
        for value in (-1, 2, 0.0, 1.0, True, False, "1", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_vector((value,), 1)
                with self.assertRaises(ValueError):
                    Matrix.from_rows(((value,),))
        for size in (-1, 1.0, True, "2"):
            with self.subTest(size=size):
                with self.assertRaises(ValueError):
                    Matrix.zero(size, 2)
                with self.assertRaises(ValueError):
                    Matrix.zero(2, size)
                with self.assertRaises(ValueError):
                    Matrix.identity(size)
        for vector in ((0,), (0, 1, 0), None):
            with self.assertRaises(ValueError):
                validate_vector(vector, 2)
        for operation in (
            lambda: Matrix(2, 1, ((1,),)),
            lambda: Matrix(1, 2, ((1,),)),
            lambda: Matrix.from_rows(((1, 0), (1,))),
            lambda: Matrix.from_rows(((1, 0),), ncols=3),
            lambda: Matrix.from_columns(((1,),), nrows=2),
            lambda: Matrix.from_rows(None),
            lambda: Matrix.from_columns(None, nrows=0),
        ):
            with self.assertRaises(ValueError):
                operation()

    def test_empty_shapes(self):
        for nrows, ncols in ((0, 0), (0, 3), (3, 0)):
            matrix = Matrix.zero(nrows, ncols)
            self.assertEqual((matrix.nrows, matrix.ncols), (nrows, ncols))
            self.assertEqual(matrix.transpose().transpose(), matrix)
            self.assertEqual(matrix @ Matrix.identity(ncols), matrix)
            self.assertEqual(Matrix.identity(nrows) @ matrix, matrix)
            self.assertEqual(matrix.rank(), 0)
            self.assertEqual(matrix.apply((0,) * ncols), (0,) * nrows)
            self.assertEqual(matrix.solve((0,) * nrows), (0,) * ncols)
        self.assertEqual(Matrix.from_rows((), ncols=3), Matrix.zero(0, 3))
        self.assertEqual(Matrix.from_columns((), nrows=3), Matrix.zero(3, 0))
        self.assertEqual(Matrix.zero(2, 0) @ Matrix.zero(0, 3), Matrix.zero(2, 3))
        self.assertEqual(Matrix.zero(0, 3).kernel_basis(), Matrix.identity(3).rows)
        self.assertIsNone(Matrix.zero(3, 0).solve((0, 1, 0)))


class MatrixAlgebraTests(unittest.TestCase):
    def test_rectangular_products_and_f2_addition(self):
        left = Matrix.from_rows(((1, 1, 0), (0, 1, 1)))
        right = Matrix.from_rows(((1, 0), (1, 1), (0, 1)))
        self.assertEqual((left @ right).rows, ((0, 1), (1, 0)))
        self.assertEqual(left + left, Matrix.zero(2, 3))
        self.assertEqual(left + Matrix.zero(2, 3), left)
        self.assertEqual(
            (left @ right).transpose(), right.transpose() @ left.transpose()
        )
        self.assertEqual(left.apply((1, 1, 0)), (0, 1))
        for operation in (
            lambda: left + right,
            lambda: left @ left,
            lambda: left.apply((1,)),
            lambda: left.solve((1,)),
            lambda: left.apply((1, 2, 0)),
            lambda: left.solve((1, 2)),
        ):
            with self.assertRaises(ValueError):
                operation()

    def test_deterministic_elimination_retains_original_columns(self):
        matrix = Matrix.from_rows(((0, 1, 1, 1), (0, 0, 1, 1), (0, 1, 0, 0)))
        reduced, pivots = matrix.rref()
        self.assertEqual(pivots, (1, 2))
        self.assertEqual(reduced.rows, ((0, 1, 0, 0), (0, 0, 1, 1), (0, 0, 0, 0)))
        self.assertEqual(matrix.kernel_basis(), ((1, 0, 0, 0), (0, 0, 1, 1)))
        self.assertEqual(matrix.image_basis(), ((1, 0, 1), (1, 1, 0)))
        self.assertEqual(matrix.solve((1, 1, 0)), (0, 0, 1, 0))
        self.assertIsNone(matrix.solve((1, 0, 0)))
        self.assertEqual(reduced.rref(), (reduced, pivots))

    def test_exhaustive_small_matrices_against_enumerated_vectors(self):
        # Every matrix of each shape up to 3 x 3, including zero-dimensional ones.
        for nrows, ncols in product(range(4), repeat=2):
            inputs = vectors(ncols)
            for entries in vectors(nrows * ncols):
                rows = tuple(
                    entries[row * ncols : (row + 1) * ncols] for row in range(nrows)
                )
                matrix = Matrix(nrows, ncols, rows)
                with self.subTest(shape=(nrows, ncols), rows=rows):
                    image = {multiply_rows(rows, vector) for vector in inputs}
                    kernel = {
                        vector
                        for vector in inputs
                        if multiply_rows(rows, vector) == (0,) * nrows
                    }
                    kernel_basis = matrix.kernel_basis()
                    image_basis = matrix.image_basis()
                    self.assertEqual(span(kernel_basis, ncols), kernel)
                    self.assertEqual(span(image_basis, nrows), image)
                    self.assertEqual(len(kernel), 2 ** len(kernel_basis))
                    self.assertEqual(len(image), 2 ** len(image_basis))
                    self.assertEqual(matrix.rank(), len(image).bit_length() - 1)
                    self.assertEqual(matrix.rank() + len(kernel_basis), ncols)
                    for vector in inputs:
                        self.assertEqual(
                            matrix.apply(vector), multiply_rows(rows, vector)
                        )
                    for rhs in vectors(nrows):
                        solution = matrix.solve(rhs)
                        self.assertEqual(solution is not None, rhs in image)
                        if solution is not None:
                            self.assertEqual(multiply_rows(rows, solution), rhs)


if __name__ == "__main__":
    unittest.main()
