"""Candidate projection checks against independent finite vector enumeration."""

from itertools import product
import unittest

from homology_operator.algebra import Matrix
from homology_operator.chain import ChainWindow
from homology_operator.validation import ValidationError, validate_projection


def vectors(size):
    return tuple(product((0, 1), repeat=size))


def apply_rows(rows, vector):
    return tuple(
        sum(value for value, bit in zip(row, vector) if bit) & 1 for row in rows
    )


def add(left, right):
    return tuple((x + y) & 1 for x, y in zip(left, right))


def all_matrices(nrows, ncols):
    return tuple(
        Matrix(
            nrows,
            ncols,
            tuple(entries[row * ncols : (row + 1) * ncols] for row in range(nrows)),
        )
        for entries in vectors(nrows * ncols)
    )


def chain(A, D):
    return ChainWindow(
        k=1,
        A=A,
        D=D,
        basis_previous=tuple(f"previous-{i}" for i in range(A.nrows)),
        basis_current=tuple(f"current-{i}" for i in range(A.ncols)),
        basis_next=tuple(f"next-{i}" for i in range(D.ncols)),
        weights=(1,) * A.ncols,
    )


def enumerated_checks(window, projection):
    # Enumerate all vectors directly; do not use elimination, solve, or products.
    domain = vectors(window.n)
    boundaries = {apply_rows(window.D.rows, vector) for vector in vectors(window.p)}
    cycles = {
        vector
        for vector in domain
        if apply_rows(window.A.rows, vector) == (0,) * window.m
    }

    def p(vector):
        return apply_rows(projection.rows, vector)

    def operator_action(vector):
        return add(vector, p(vector))

    return {
        "p_idempotent": all(p(p(vector)) == p(vector) for vector in domain),
        "l_idempotent": all(
            operator_action(operator_action(vector)) == operator_action(vector)
            for vector in domain
        ),
        "a_p_zero": all(
            apply_rows(window.A.rows, p(vector)) == (0,) * window.m for vector in domain
        ),
        "p_d_zero": all(p(vector) == (0,) * window.n for vector in boundaries),
        "cycle_homology_preservation": all(
            add(vector, p(vector)) in boundaries for vector in cycles
        ),
    }


class ProjectionValidationTests(unittest.TestCase):
    def test_zero_projection_cannot_erase_nonzero_homology(self):
        window = chain(Matrix.zero(0, 2), Matrix.zero(2, 0))
        projection = Matrix.zero(2, 2)
        expected = enumerated_checks(window, projection)
        self.assertTrue(expected["p_idempotent"])
        self.assertTrue(expected["a_p_zero"])
        self.assertTrue(expected["p_d_zero"])
        with self.assertRaises(ValidationError) as caught:
            validate_projection(window, projection)
        self.assertEqual(caught.exception.status, "InternalValidationFailed")
        self.assertEqual(caught.exception.failures, ("cycle_homology_preservation",))

    def test_bad_projection_invariants_are_identified(self):
        cases = (
            (
                chain(Matrix.from_rows(((1, 0),)), Matrix.zero(2, 0)),
                Matrix.identity(2),
                {"a_p_zero"},
            ),
            (
                chain(Matrix.zero(0, 2), Matrix.from_columns(((1, 0),), 2)),
                Matrix.identity(2),
                {"p_d_zero"},
            ),
            (
                chain(Matrix.zero(0, 2), Matrix.zero(2, 0)),
                Matrix.from_rows(((0, 1), (0, 0))),
                {"p_idempotent", "l_idempotent", "cycle_homology_preservation"},
            ),
        )
        for window, projection, failures in cases:
            with self.subTest(projection=projection, failures=failures):
                with self.assertRaises(ValidationError) as caught:
                    validate_projection(window, projection)
                self.assertEqual(set(caught.exception.failures), failures)

    def test_empty_domain_and_zero_homology_are_legal(self):
        empty = chain(Matrix.zero(2, 0), Matrix.zero(0, 2))
        acyclic = chain(Matrix.zero(0, 2), Matrix.identity(2))
        for window, projection in (
            (empty, Matrix.zero(0, 0)),
            (acyclic, Matrix.zero(2, 2)),
        ):
            with self.subTest(n=window.n):
                report = validate_projection(window, projection)
                self.assertTrue(
                    all(report[name] for name in enumerated_checks(window, projection))
                )
                self.assertIs(report["exact_arithmetic"], True)
                self.assertEqual(
                    report["verification_method"], "ExactF2MatrixAndCycleBasis"
                )
                self.assertEqual(
                    set(report),
                    {
                        "p_idempotent",
                        "l_idempotent",
                        "a_p_zero",
                        "p_d_zero",
                        "cycle_homology_preservation",
                        "exact_arithmetic",
                        "verification_method",
                    },
                )

    def test_shape_and_type_failures_are_structured(self):
        window = chain(Matrix.zero(0, 2), Matrix.zero(2, 0))
        for projection in (Matrix.zero(0, 0), Matrix.zero(1, 2), Matrix.zero(2, 3)):
            with self.assertRaises(ValidationError) as caught:
                validate_projection(window, projection)
            self.assertEqual(caught.exception.failures, ("projection_shape",))
        with self.assertRaises(ValidationError) as caught:
            validate_projection(window, ((1, 0), (0, 1)))
        self.assertEqual(caught.exception.failures, ("projection_type",))
        with self.assertRaises(ValidationError) as caught:
            validate_projection(None, Matrix.identity(2))
        self.assertEqual(caught.exception.failures, ("window_type",))

    def test_all_small_windows_and_projections_match_vector_enumeration(self):
        matrices = {
            (nrows, ncols): all_matrices(nrows, ncols)
            for nrows, ncols in product(range(3), repeat=2)
        }
        for m, n, p in product(range(3), repeat=3):
            for A, D in product(matrices[m, n], matrices[n, p]):
                # Establish AD=0 using the oracle before constructing the window.
                boundaries = {apply_rows(D.rows, vector) for vector in vectors(p)}
                if any(apply_rows(A.rows, vector) != (0,) * m for vector in boundaries):
                    continue
                window = chain(A, D)
                for projection in matrices[n, n]:
                    expected = enumerated_checks(window, projection)
                    failures = tuple(
                        name for name, valid in expected.items() if not valid
                    )
                    with self.subTest(
                        shape=(m, n, p), A=A.rows, D=D.rows, P=projection.rows
                    ):
                        if failures:
                            with self.assertRaises(ValidationError) as caught:
                                validate_projection(window, projection)
                            self.assertEqual(caught.exception.failures, failures)
                        else:
                            report = validate_projection(window, projection)
                            self.assertEqual(
                                {name: report[name] for name in expected}, expected
                            )


if __name__ == "__main__":
    unittest.main()
