"""Independent exact F2 validation of a candidate homology projection."""

from collections.abc import Mapping
from fractions import Fraction
from itertools import product
from math import isfinite

from .algebra import Matrix, validate_vector
from .chain import ChainWindow, matrix_from_data
from .result import QueryResult, content_id, make_identity


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


def validate_solver_config(window, solver):
    """Verify configuration content identity, including records without an action."""
    config = solver.get("solver_config")
    if config is None and solver.get("solver_config_id") is not None:
        raise ValidationError(("solver_config",))
    if config is not None:
        if (
            not isinstance(config, Mapping)
            or window is None
            or solver.get("solver_config_id") != content_id("solver-config", config)
            or config.get("method") != solver.get("method")
            or config.get("arithmetic_policy") != window.arithmetic
            or config.get("tie_break_policy") != solver.get("tie_break_policy")
            or config.get("objective") != "MinimumStretch"
        ):
            raise ValidationError(("solver_config",))
    if window is not None and solver.get("arithmetic_policy") not in {
        None,
        window.arithmetic,
    }:
        raise ValidationError(("arithmetic_policy",))


def validate_solver_certificate(window, projection, solver, certificate, identity):
    """Independently replay rational cycle bounds; never trust certification flags.

    CycleBounds uses a universal lower bound (0 if beta=0, otherwise 1).
    It proves exact optimality only when this meets a certified upper bound.
    Complete search certificates require a separate supported verifier.
    """
    level = solver.get("certificate_level")
    if level not in {
        "Feasible",
        "Heuristic",
        "CertifiedUpperBound",
        "CertifiedInterval",
        "ExactOptimal",
    }:
        raise ValidationError(("certificate_level",))
    validate_solver_config(window, solver)
    objective = (
        None
        if "objective" not in solver
        else QueryResult.from_dict(solver["objective"])
    )
    if objective is not None and objective.identity != identity:
        raise ValidationError(("objective_identity",))
    if (
        objective is not None
        and objective.exact is True
        and window.arithmetic == "FloatingPoint"
        and objective.state in {"Computed", "EmptyDomain"}
    ):
        raise ValidationError(("floating_objective_is_not_exact",))
    bounds = tuple(solver.get(key) for key in ("lower_bound", "upper_bound"))
    for value in bounds:
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float, Fraction))
            or (isinstance(value, float) and not isfinite(value))
            or value < 0
        ):
            raise ValidationError(("invalid_bound",))
    lower, upper = bounds
    if lower is not None and upper is not None and lower > upper:
        raise ValidationError(("inverted_bounds",))
    expected_gap = None
    if lower is not None and upper is not None:
        expected_gap = {
            "absolute": upper - lower,
            "relative": None
            if lower == 0
            else Fraction(upper - lower) / Fraction(lower),
        }
    gap = solver.get("optimality_gap")
    if gap is not None and (
        not isinstance(gap, Mapping)
        or set(gap) != {"absolute", "relative"}
        or type(gap["absolute"]) not in {int, Fraction}
        or (
            gap["relative"] is not None and type(gap["relative"]) not in {int, Fraction}
        )
    ):
        raise ValidationError(("optimality_gap",))
    if gap != expected_gap:
        raise ValidationError(("optimality_gap",))
    certified = level in {"CertifiedUpperBound", "CertifiedInterval", "ExactOptimal"}
    proof = certificate.get("optimization")
    if certified and (
        not isinstance(proof, Mapping)
        or proof.get("kind") not in {"CycleBounds", "ExhaustiveSearch"}
    ):
        raise ValidationError(("unsupported_optimality_certificate",))
    if certified and (
        upper is None
        or objective is None
        or objective.state not in {"Computed", "EmptyDomain"}
        or objective.exact is not True
    ):
        raise ValidationError(("certified_objective_and_upper_bound_required",))
    if level in {"CertifiedInterval", "ExactOptimal"} and lower is None:
        raise ValidationError(("certified_lower_bound_required",))
    if (
        not certified
        and lower is None
        and upper is None
        and (
            objective is None
            or objective.state not in {"Computed", "EmptyDomain"}
            or objective.exact is not True
        )
    ):
        return {}
    if window.arithmetic not in {"ExactInteger", "ExactRational"} or any(
        value is not None and type(value) not in {int, Fraction} for value in bounds
    ):
        raise ValidationError(("bounds_require_exact_rational_arithmetic",))
    # Replay has its own explicit reference support cap, never a silent downgrade.
    cycles = window.A.kernel_basis()
    cycle_count = (1 << len(cycles)) - 1
    if cycle_count > 100_000:
        raise ValidationError(("certificate_replay_state_limit",))
    current = Fraction(0)
    cycle_inputs = []
    for bits in product((0, 1), repeat=len(cycles)):
        z = tuple(
            sum(bit * vector[j] for bit, vector in zip(bits, cycles)) % 2
            for j in range(window.n)
        )
        if not any(z):
            continue
        output = projection.apply(z)
        numerator = sum(w for w, bit in zip(window.weights, output) if bit)
        denominator = sum(w for w, bit in zip(window.weights, z) if bit)
        cycle_inputs.append((z, denominator))
        current = max(current, Fraction(numerator) / Fraction(denominator))
    beta = len(cycles) - window.D.rank()
    universal_lower = int(beta > 0)
    replayed_optimum = None
    if certified and proof["kind"] == "ExhaustiveSearch":
        replayed_optimum = _replay_exhaustive(
            window, projection, proof, cycles, cycle_inputs
        )
    if lower is not None and lower > (
        universal_lower if replayed_optimum is None else replayed_optimum
    ):
        raise ValidationError(("unsupported_lower_bound_proof",))
    if upper is not None and upper < current:
        raise ValidationError(("upper_bound_below_current_objective",))
    if objective is not None and objective.state in {"Computed", "EmptyDomain"}:
        expected_state = "EmptyDomain" if cycle_count == 0 else "Computed"
        if (
            objective.state != expected_state
            or type(objective.value) not in {int, Fraction}
            or objective.value != current
            or objective.exact is not True
        ):
            raise ValidationError(("objective_replay",))
        if "witness" in objective.details:
            witness = objective.details["witness"]
            if cycle_count == 0:
                if witness is not None:
                    raise ValidationError(("objective_witness",))
            else:
                witness = validate_vector(witness, window.n)
                if not any(witness) or window.A.apply(witness) != (0,) * window.m:
                    raise ValidationError(("objective_witness",))
                witness_mass = sum(w for w, bit in zip(window.weights, witness) if bit)
                output_mass = sum(
                    w
                    for w, bit in zip(window.weights, projection.apply(witness))
                    if bit
                )
                if Fraction(output_mass) / witness_mass != current:
                    raise ValidationError(("objective_witness",))
        if (
            certified
            and proof["kind"] == "ExhaustiveSearch"
            and "witness" not in objective.details
        ):
            raise ValidationError(("objective_witness_required",))
    if certified:
        if (
            type(proof.get("nonzero_cycles")) is not int
            or proof["nonzero_cycles"] != cycle_count
        ):
            raise ValidationError(("cycle_enumeration_count",))
        if (
            lower is not None
            and proof["kind"] == "CycleBounds"
            and proof.get("lower_bound_method") != "UniversalHomology"
        ):
            raise ValidationError(("lower_bound_method",))
    if level == "ExactOptimal" and not (lower == upper == current):
        raise ValidationError(("exact_optimal_requires_equal_proven_bounds",))
    if level == "CertifiedInterval" and lower == upper:
        raise ValidationError(("equal_proven_bounds_require_ExactOptimal",))
    return {
        "objective_replayed": True,
        "bounds_verified": lower is not None or upper is not None,
        "optimality_verified": level == "ExactOptimal",
    }


def _replay_exhaustive(window, projection, proof, cycle_basis, inputs):
    """Enumerate lifts of a quotient basis, independently of retraction rows Y."""
    R = matrix_from_data(proof.get("cycle_retraction"))
    if (
        (R.nrows, R.ncols) != (window.n, window.n)
        or R @ R != R
        or window.A @ R != Matrix.zero(window.m, window.n)
        or any(R.apply(z) != z for z in cycle_basis)
        or projection @ R != projection
    ):
        raise ValidationError(("cycle_retraction",))
    boundary_basis = window.D.image_basis()
    full = list(boundary_basis)
    quotient_basis = []
    for z in cycle_basis:
        if Matrix.from_columns((*full, z), nrows=window.n).rank() > len(full):
            full.append(z)
            quotient_basis.append(z)
    r, beta = len(boundary_basis), len(quotient_basis)
    count = 1 << (r * beta)
    if (
        type(proof.get("candidate_count")) is not int
        or proof["candidate_count"] != count
        or proof.get("tie_break_complete") is not True
    ):
        raise ValidationError(("complete_search_count",))
    if count * max(1, len(inputs)) > 100_000:
        raise ValidationError(("certificate_replay_state_limit",))
    coordinate_basis = Matrix.from_columns(full, nrows=window.n)
    coordinates = Matrix.from_columns(
        (coordinate_basis.solve(z) for z in R.transpose().rows), nrows=len(full)
    )
    optimum = None
    for parameters in product((0, 1), repeat=r * beta):
        lifts = tuple(
            tuple(
                z[j]
                ^ (
                    sum(parameters[i * r + b] * boundary_basis[b][j] for b in range(r))
                    % 2
                )
                for j in range(window.n)
            )
            for i, z in enumerate(quotient_basis)
        )
        section = Matrix.from_columns(((0,) * window.n,) * r + lifts, nrows=window.n)
        candidate = section @ coordinates
        value = max(
            (
                Fraction(
                    sum(w for w, bit in zip(window.weights, candidate.apply(z)) if bit)
                )
                / denominator
                for z, denominator in inputs
            ),
            default=Fraction(0),
        )
        key = tuple(
            sum(bit << j for j, bit in enumerate(column))
            for column in candidate.transpose().rows
        )
        if optimum is None or (value, key) < optimum:
            optimum = value, key
    declared_key = tuple(
        sum(bit << j for j, bit in enumerate(column))
        for column in projection.transpose().rows
    )
    current = max(
        (
            Fraction(
                sum(w for w, bit in zip(window.weights, projection.apply(z)) if bit)
            )
            / denominator
            for z, denominator in inputs
        ),
        default=Fraction(0),
    )
    if (current, declared_key) != optimum:
        raise ValidationError(("optimal_projection_or_tie_break",))
    return optimum[0]


def validate_solution(window, solution):
    """Validate any solver output at the action/identity/certificate boundary."""
    from .solver import ProjectionSolution

    if not isinstance(solution, ProjectionSolution) or solution.status not in {
        "Solved",
        "FeasibleOnly",
        "ResourceExhausted",
    }:
        raise ValidationError(("solution_status",))
    checks = validate_projection(window, solution.projection)
    identity = make_identity(
        window, solution.projection, solution.solver_run_id, solution.tie_break_policy
    )
    if solution.identity != identity:
        raise ValidationError(("solution_identity",))
    if (
        not isinstance(solution.objective, QueryResult)
        or solution.objective.identity != identity
    ):
        raise ValidationError(("objective_identity",))
    checks.update(
        validate_solver_certificate(
            window,
            solution.projection,
            solution.solver_metadata(),
            solution.certificate,
            identity,
        )
    )
    return checks
