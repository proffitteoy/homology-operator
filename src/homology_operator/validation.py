"""Independent exact F2 validation of a candidate homology projection."""

from .algebra import Matrix
from .chain import ChainWindow


class ValidationError(ValueError):
    """A candidate cannot enter the operator as a validated projection."""

    status = "InternalValidationFailed"

    def __init__(self, failures):
        self.failures = tuple(failures)
        super().__init__("projection validation failed: " + ", ".join(self.failures))


def validate_projection(window: ChainWindow, P: Matrix) -> dict:
    """Verify legality, including homology preservation on a full cycle basis.

    Idempotence and AP=PD=0 do not ensure preservation: the zero projection
    satisfies them even when the homology is nonzero. Membership in im(D) is
    checked independently by solving D b = z + P z for each kernel basis vector.
    The exactness reported here concerns F2 algebra, not weighted objectives.
    """
    if not isinstance(window, ChainWindow):
        raise ValidationError(("window_type",))
    if not isinstance(P, Matrix):
        raise ValidationError(("projection_type",))
    if (P.nrows, P.ncols) != (window.n, window.n):
        raise ValidationError(("projection_shape",))

    L = Matrix.identity(window.n) + P
    checks = {
        "p_idempotent": P @ P == P,
        "l_idempotent": L @ L == L,
        "a_p_zero": window.A @ P == Matrix.zero(window.m, window.n),
        "p_d_zero": P @ window.D == Matrix.zero(window.n, window.p),
        "cycle_homology_preservation": all(
            window.D.solve(tuple(left ^ right for left, right in zip(z, P.apply(z))))
            is not None
            for z in window.A.kernel_basis()
        ),
    }
    failures = tuple(name for name, valid in checks.items() if not valid)
    if failures:
        raise ValidationError(failures)
    return {
        **checks,
        "exact_arithmetic": True,
        "verification_method": "ExactF2MatrixAndCycleBasis",
    }
