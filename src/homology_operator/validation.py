"""Independent exact F2 validation of a candidate homology projection."""

from collections.abc import Mapping
from fractions import Fraction
from itertools import product, combinations
from math import isfinite

from .algebra import Matrix, CyclicAction, CompactAction, validate_vector
from .chain import ChainWindow, matrix_from_data
from .result import QueryResult, content_id, make_identity


class ValidationError(ValueError):
    """A candidate cannot enter the operator as a validated projection."""

    status = "InternalValidationFailed"

    def __init__(self, failures):
        self.failures = tuple(failures)
        super().__init__("projection validation failed: " + ", ".join(self.failures))


def _batch_membership(matrix, vectors):
    """Independent Python image decomposition, reused for all residuals.

    No solver/native decomposition, P factors or reported ranks are trusted.
    Packed Python integers describe the original columns of D's image basis.
    """
    pivots = {}
    for column in matrix.image_basis():
        bits = sum(bit << i for i, bit in enumerate(column))
        while bits:
            pivot = bits.bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = bits
                break
            bits ^= pivots[pivot]
    output = []
    for vector in vectors:
        bits = sum(
            bit << i for i, bit in enumerate(validate_vector(vector, matrix.nrows))
        )
        while bits and bits.bit_length() - 1 in pivots:
            bits ^= pivots[bits.bit_length() - 1]
        output.append(bits == 0)
    return tuple(output)


def validate_projection(
    window: ChainWindow, P: Matrix | CyclicAction | CompactAction
) -> dict:
    """Verify legality, including homology preservation on a full cycle basis.

    Idempotence and AP=PD=0 do not ensure preservation: the zero projection
    satisfies them even when the homology is nonzero. Membership in im(D) is
    checked independently by solving D b = z + P z for each kernel basis vector.
    The exactness reported here concerns F2 algebra, not weighted objectives.
    """
    if not isinstance(window, ChainWindow):
        raise ValidationError(("window_type",))
    if not isinstance(P, (Matrix, CyclicAction, CompactAction)):
        raise ValidationError(("projection_type",))
    if (P.nrows, P.ncols) != (window.n, window.n):
        raise ValidationError(("projection_shape",))

    if isinstance(P, (CyclicAction, CompactAction)):
        checks = dict.fromkeys(
            (
                "p_idempotent",
                "l_idempotent",
                "a_p_zero",
                "p_d_zero",
                "cycle_homology_preservation",
            ),
            True,
        )
        L = (
            P.complemented()
            if isinstance(P, CompactAction)
            else CyclicAction(P.m, not P.complement)
        )
        if isinstance(P, CompactAction):
            if P.form == "GeneralizedInverse":
                A, D, _, _ = P.factors
                checks["factor_window"] = A == window.A and D == window.D
                checks["a_g_a"] = all(
                    A.apply(P._inverse(0, column)) == column
                    for column in A.transpose().rows
                )
                checks["d_u_d"] = all(
                    D.apply(P._inverse(1, column)) == column
                    for column in D.transpose().rows
                )
            else:
                H, C = P.factors
                checks["a_h_zero"] = window.A @ H == Matrix.zero(window.m, H.ncols)
                checks["c_d_zero"] = C @ window.D == Matrix.zero(C.nrows, window.p)
                checks["c_h_identity"] = C @ H == Matrix.identity(C.nrows)
        for j in range(window.n):
            e = tuple(int(i == j) for i in range(window.n))
            p, image_l = P.apply(e), L.apply(e)
            checks["p_idempotent"] &= P.apply(p) == p
            checks["l_idempotent"] &= L.apply(image_l) == image_l
            checks["a_p_zero"] &= not any(window.A.apply(p))
        checks["p_d_zero"] = all(not any(P.apply(z)) for z in window.D.transpose().rows)
        residuals = (
            tuple(a ^ b for a, b in zip(z, P.apply(z))) for z in window.A.kernel_basis()
        )
        checks["cycle_homology_preservation"] = all(
            _batch_membership(window.D, residuals)
        )
    else:
        L = Matrix.identity(window.n) + P
        checks = {
            "p_idempotent": P @ P == P,
            "l_idempotent": L @ L == L,
            "a_p_zero": window.A @ P == Matrix.zero(window.m, window.n),
            "p_d_zero": P @ window.D == Matrix.zero(window.n, window.p),
            "cycle_homology_preservation": all(
                window.D.solve(
                    tuple(left ^ right for left, right in zip(z, P.apply(z)))
                )
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
        "verification_method": "ExactF2ActionGeneratorsAndCycleBasis"
        if isinstance(P, (CyclicAction, CompactAction))
        else "ExactF2MatrixAndCycleBasis",
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


def _replay_backend_details(solver, native, window):
    if not solver.get("method", "").startswith("Native"):
        return {}
    from .native import _integer_weights

    return {
        "certificate_replay_backend": "packed-rust-v1"
        if native
        else "python-reference",
        "certificate_mass_backend": "u128-normalized-rational"
        if native and _integer_weights(window.weights) is not None
        else "python-unbounded-rational",
    }


def _replay_native(solver):
    if solver.get("method") not in {
        "NativeExhaustiveExactSolver",
        "NativeGreedyCertifiedSolver",
        "NativeRank2ExactSolver",
        "NativeStructuredFamilySolver",
    }:
        return False
    from .native import _extension

    try:
        return hasattr(_extension(), "span_objective")
    except ImportError:
        return False


def _replay_objective(window, projection, basis, inputs, native):
    if native:
        from .native import _span_objective

        result = _span_objective(window, projection, basis, detail={})
        if result is not None:
            return result[0]
    return max(
        (
            Fraction(
                sum(w for w, bit in zip(window.weights, projection.apply(z)) if bit)
            )
            / mass
            for z, mass in inputs
        ),
        default=Fraction(0),
    )


def _reference_cycle_inputs(window, cycles):
    inputs = []
    for bits in product((0, 1), repeat=len(cycles)):
        z = tuple(
            sum(bit * vector[j] for bit, vector in zip(bits, cycles)) % 2
            for j in range(window.n)
        )
        if any(z):
            inputs.append((z, sum(w for w, bit in zip(window.weights, z) if bit)))
    return inputs


def validate_solver_certificate(window, projection, solver, certificate, identity):
    """Independently replay rational cycle bounds; never trust certification flags.

    CycleBounds uses a universal lower bound (0 if beta=0, otherwise 1).
    It proves exact optimality only when this meets a certified upper bound.
    Complete search certificates require a separate supported verifier.
    """
    native = _replay_native(solver)
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
        or proof.get("kind")
        not in {
            "CycleBounds",
            "ExhaustiveSearch",
            "Rank2Search",
            "CyclicTrace",
            "GreedyBasis",
        }
    ):
        raise ValidationError(("unsupported_optimality_certificate",))
    if certified:
        if isinstance(projection, CompactAction) and proof["kind"] != "CycleBounds":
            raise ValidationError(("unsupported_compact_certificate",))
        if isinstance(projection, CyclicAction) and proof["kind"] != "CyclicTrace":
            raise ValidationError(("unsupported_structured_certificate",))
        allowed_fields = {
            "CyclicTrace": {"kind", "m", "kernel_distance"},
            "CycleBounds": {"kind", "nonzero_cycles", "lower_bound_method"},
            "ExhaustiveSearch": {
                "kind",
                "candidate_count",
                "nonzero_cycles",
                "cycle_retraction",
                "tie_break_complete",
            },
            "Rank2Search": {
                "kind",
                "candidate_count",
                "nonzero_cycles",
                "cycle_retraction",
                "tie_break_complete",
                "structure",
                "searched_candidates",
                "quotient_generators",
                "class_minima",
                "initial_generators",
                "pareto_steps",
                "terminal_labels",
            },
            "GreedyBasis": {
                "kind",
                "nonzero_cycles",
                "selected_generators",
                "cycle_retraction",
                "theoretical_upper_bound",
                "hypotheses",
            },
        }[proof["kind"]]
        if set(proof) - allowed_fields or (
            "lower_bound_method" in proof
            and proof["lower_bound_method"] != "UniversalHomology"
        ):
            raise ValidationError(("unsupported_certificate_fields",))
    if certified and (
        upper is None
        or objective is None
        or objective.state not in {"Computed", "EmptyDomain"}
        or objective.exact is not True
    ):
        raise ValidationError(("certified_objective_and_upper_bound_required",))
    if level in {"CertifiedInterval", "ExactOptimal"} and lower is None:
        raise ValidationError(("certified_lower_bound_required",))
    if certified and proof["kind"] == "CyclicTrace":
        return _validate_cyclic_certificate(
            window, projection, proof, solver, objective, lower, upper, native
        )
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
        return {
            "objective_replayed": False,
            "bounds_verified": False,
            "optimality_verified": False,
        }
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
    if native:
        from .native import _span_table

        cycle_inputs = _span_table(window, cycles, detail={})
    else:
        cycle_inputs = None
    if cycle_inputs is None:
        cycle_inputs = _reference_cycle_inputs(window, cycles)
    if len(cycle_inputs) != cycle_count:
        raise ValidationError(("cycle_enumeration_count",))
    current = _replay_objective(window, projection, cycles, cycle_inputs, native)
    beta = len(cycles) - window.D.rank()

    universal_lower = int(beta > 0)
    replayed_optimum = None
    rank2_cut = None
    if certified and proof["kind"] == "Rank2Search":
        rank2_cut = _validate_rank2_reduction(
            window, projection, proof, cycle_inputs, solver, native
        )
    if certified and proof["kind"] in {"ExhaustiveSearch", "Rank2Search"}:
        replayed_optimum = _replay_exhaustive(
            window, projection, proof, cycles, cycle_inputs, rank2_cut, native
        )
    if certified and proof["kind"] == "GreedyBasis":
        theoretical = _replay_greedy(
            window, projection, proof, cycles, cycle_inputs, native
        )
        if current > theoretical:
            raise ValidationError(("greedy_theoretical_bound",))
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
            and proof["kind"] in {"ExhaustiveSearch", "Rank2Search", "GreedyBasis"}
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
        **_replay_backend_details(solver, native, window),
    }


def _replay_exhaustive(
    window, projection, proof, cycle_basis, inputs, rank2_cut=None, native=False
):
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
    if native:
        from .native import PreparedMatrix

        solved = PreparedMatrix(coordinate_basis).solve_many(R.transpose().rows)
    else:
        solved = (coordinate_basis.solve(z) for z in R.transpose().rows)
    coordinates = Matrix.from_columns(solved, nrows=len(full))
    optimum, global_value = None, None
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
        if native:
            from .native import packed_multiply

            candidate = packed_multiply(section, coordinates)
        else:
            candidate = section @ coordinates
        value = _replay_objective(window, candidate, cycle_basis, inputs, native)
        global_value = value if global_value is None else min(global_value, value)
        if proof["kind"] == "Rank2Search":
            if rank2_cut is None:
                # Independent test of the T5 terminal condition: no supported B.
                F = Matrix.from_columns(boundary_basis, nrows=window.n)
                if (
                    Matrix.from_rows(
                        (
                            row
                            for j, row in enumerate(F.rows)
                            if not any(z[j] for z in lifts)
                        ),
                        ncols=r,
                    ).rank()
                    != r
                ):
                    continue
            else:
                delta, vertices, terminals, _ = rank2_cut
                # delta omits t0; terminal columns represent the fixed hole basis.
                nonroot = [v for v in range(vertices) if v != terminals[0]]
                holes = [
                    delta.transpose().rows[nonroot.index(t)] for t in terminals[1:]
                ]
                potentials = [delta.solve(candidate.apply(z)) for z in holes]
                if any(a + 2 * b == 3 for a, b in zip(*potentials)):
                    continue
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
    current = _replay_objective(window, projection, cycle_basis, inputs, native)
    if (current, declared_key) != optimum or current != global_value:
        raise ValidationError(("optimal_projection_or_tie_break",))
    return optimum[0]


def _validate_cyclic_certificate(
    window, projection, proof, solver, objective, lower, upper, native=False
):
    m = proof.get("m")
    if (
        type(m) is not int
        or not 2 <= m <= 4
        or type(proof.get("kernel_distance")) is not int
        or proof["kernel_distance"] != m + 1
    ):
        raise ValidationError(("cyclic_parameters",))
    if (
        window.arithmetic not in {"ExactInteger", "ExactRational"}
        or window.n != (1 << m) - 1
        or window.A.rank() != 0
        or len(set(window.weights)) != 1
    ):
        raise ValidationError(("cyclic_input_structure",))
    # Formula, full-cube operator norm, and distance obstruction are independent
    # of the solver's construction; no optimization flag or rank formula is trusted.
    for j in range(window.n):
        e = tuple(int(i == j) for i in range(window.n))
        expected = tuple(
            int((i - j) % window.n in {1 << s for s in range(m)})
            for i in range(window.n)
        )
        if projection.apply(e) != expected or sum(expected) != m:
            raise ValidationError(("cyclic_formula",))
    for weight in range(1, m + 1):
        vectors = tuple(
            tuple(int(i in support) for i in range(window.n))
            for support in combinations(range(window.n), weight)
        )
        if native:
            from .native import _apply_many

            outputs = _apply_many(projection, vectors)
        else:
            outputs = (projection.apply(z) for z in vectors)
        if any(not any(z) for z in outputs):
            raise ValidationError(("cyclic_kernel_distance",))
    e0 = (1,) + (0,) * (window.n - 1)
    b = tuple(a ^ c for a, c in zip(e0, projection.apply(e0)))
    if sum(b) != m + 1 or window.D.solve(b) is None or window.D.rank() == 0:
        raise ValidationError(("cyclic_distance_witness",))
    if (
        solver["certificate_level"] != "ExactOptimal"
        or any(
            type(x) not in {int, Fraction} or x != m
            for x in (lower, upper, objective.value)
        )
        or objective.state != "Computed"
        or objective.exact is not True
    ):
        raise ValidationError(("cyclic_equal_exact_bounds",))
    witness = validate_vector(objective.details.get("witness", ()), window.n)
    if not any(witness) or Fraction(sum(projection.apply(witness)), sum(witness)) != m:
        raise ValidationError(("objective_witness",))
    return {
        "objective_replayed": True,
        "bounds_verified": True,
        "optimality_verified": True,
        **_replay_backend_details(solver, native, window),
    }


def validate_rank2_structure(window, structure, options):
    """Prove a cut-space witness algebraically; never infer a planar embedding."""
    if window.n - window.A.rank() - window.D.rank() != 2:
        raise ValidationError(("rank_two_required",))
    if structure in {"GeneralChainWindow", "GraphCycle"}:
        if options:
            raise ValidationError(("unexpected_structure_options",))
        if structure == "GraphCycle" and (
            window.k != 1
            or any(sum(column) != 2 for column in window.A.transpose().rows)
        ):
            raise ValidationError(("graph_incidence_required",))
        return None
    if structure != "ThreeTerminalCut" or set(options) != {
        "dual_vertex_count",
        "dual_edges",
        "terminals",
    }:
        raise ValidationError(("unsupported_rank2_structure",))
    vertices, edges, terminals = (
        options[name] for name in ("dual_vertex_count", "dual_edges", "terminals")
    )
    if type(vertices) is not int or not 3 <= vertices <= window.n + 1:
        raise ValidationError(("dual_vertex_count",))
    if (
        not isinstance(terminals, (tuple, list))
        or len(terminals) != 3
        or any(type(t) is not int or not 0 <= t < vertices for t in terminals)
        or len(set(terminals)) != 3
    ):
        raise ValidationError(("three_distinct_terminals_required",))
    if (
        not isinstance(edges, (tuple, list))
        or len(edges) != window.n
        or any(
            not isinstance(e, (tuple, list))
            or len(e) != 2
            or any(type(v) is not int or not 0 <= v < vertices for v in e)
            or e[0] == e[1]
            for e in edges
        )
    ):
        raise ValidationError(("dual_edge_coordinates",))
    delta = Matrix.from_rows(
        (
            tuple(
                int(u == t) ^ int(v == t) for t in range(vertices) if t != terminals[0]
            )
            for u, v in edges
        ),
        ncols=vertices - 1,
    )
    internal = tuple(t for t in range(vertices) if t not in terminals)
    interior = Matrix.from_columns(
        (tuple(int(u == t) ^ int(v == t) for u, v in edges) for t in internal),
        nrows=window.n,
    )
    if (
        delta.rank() != vertices - 1
        or window.A @ delta != Matrix.zero(window.m, vertices - 1)
        or vertices - 1 != window.n - window.A.rank()
    ):
        raise ValidationError(("cycles_are_not_dual_cuts",))
    if interior.rank() != window.D.rank() or any(
        window.D.solve(z) is None for z in interior.transpose().rows
    ):
        raise ValidationError(("boundaries_are_not_internal_cuts",))
    return delta, vertices, tuple(terminals), internal


def _validate_rank2_reduction(window, projection, proof, inputs, solver, native=False):
    config = solver.get("solver_config")
    if not isinstance(config, Mapping) or config["input_structure"] != proof.get(
        "structure"
    ):
        raise ValidationError(("rank2_structure_config",))
    cut = validate_rank2_structure(window, proof["structure"], config["solver_options"])
    r = window.D.rank()
    if (4**r) * len(inputs) > 100_000:
        raise ValidationError(("certificate_replay_state_limit",))
    expected_count = 4**r if cut is None else 3 ** len(cut[3])
    if (
        type(proof.get("searched_candidates")) is not int
        or proof["searched_candidates"] != expected_count
    ):
        raise ValidationError(("rank2_search_count",))
    H = proof.get("quotient_generators")
    if not isinstance(H, (tuple, list)) or len(H) != 2:
        raise ValidationError(("rank2_quotient_generators",))
    H = tuple(validate_vector(z, window.n) for z in H)
    basis = Matrix.from_columns(window.D.image_basis() + H, nrows=window.n)
    if basis.rank() != r + 2 or any(any(window.A.apply(z)) for z in H):
        raise ValidationError(("rank2_quotient_generators",))
    minima = [None] * 3
    if native:
        from .native import PreparedMatrix

        coordinates = PreparedMatrix(basis).solve_many(z for z, _ in inputs)
    else:
        coordinates = (basis.solve(z) for z, _ in inputs)
    for (_, mass), coordinate in zip(inputs, coordinates):
        h = coordinate[-2] + 2 * coordinate[-1]
        if h:
            minima[h - 1] = mass if minima[h - 1] is None else min(mass, minima[h - 1])
    if content_id("minima", tuple(minima)) != content_id(
        "minima", proof.get("class_minima")
    ):
        raise ValidationError(("rank2_class_minima",))
    initial = proof.get("initial_generators")
    if not isinstance(initial, (tuple, list)) or len(initial) != 2:
        raise ValidationError(("pareto_initial_pair",))
    pair = tuple(validate_vector(z, window.n) for z in initial)
    if any(
        window.D.solve(tuple(a ^ b for a, b in zip(z, h))) is None
        for z, h in zip(pair, H)
    ):
        raise ValidationError(("pareto_initial_classes",))
    steps = proof.get("pareto_steps")
    if not isinstance(steps, (tuple, list)) or len(steps) > window.n:
        raise ValidationError(("pareto_steps",))
    for step in steps:
        if not isinstance(step, Mapping) or set(step) != {"boundary", "color"}:
            raise ValidationError(("pareto_step_fields",))
        b, color = validate_vector(step["boundary"], window.n), step["color"]
        x, y = pair
        if (
            not any(b)
            or window.D.solve(b) is None
            or any(bit and not (a or c) for bit, a, c in zip(b, x, y))
        ):
            raise ValidationError(("pareto_supported_boundary",))
        masses = [
            sum(
                w
                for w, bit, a, c in zip(window.weights, b, x, y)
                if bit and a + 2 * c == j
            )
            for j in (1, 2, 3)
        ]
        if type(color) is not int or color != max(
            (1, 2, 3), key=lambda j: (masses[j - 1], -j)
        ):
            raise ValidationError(("pareto_heaviest_color",))
        pair = tuple(
            tuple(a ^ (bit if color & (1 << i) else 0) for a, bit in zip(z, b))
            for i, z in enumerate(pair)
        )
    if pair != tuple(projection.apply(z) for z in H):
        raise ValidationError(("pareto_final_action",))
    if cut is None:
        if proof.get("terminal_labels") is not None:
            raise ValidationError(("unexpected_terminal_labels",))
    else:
        delta, vertices, terminals, _ = cut
        labels = proof.get("terminal_labels")
        if (
            not isinstance(labels, (tuple, list))
            or len(labels) != vertices
            or any(type(a) is not int or a not in (0, 1, 2) for a in labels)
            or tuple(labels[t] for t in terminals) != (0, 1, 2)
            or steps
        ):
            raise ValidationError(("three_terminal_labels",))
        nonroot = [v for v in range(vertices) if v != terminals[0]]
        expected_holes = tuple(
            delta.transpose().rows[nonroot.index(t)] for t in terminals[1:]
        )
        if H != expected_holes or pair != tuple(
            delta.apply(tuple((labels[v] >> i) & 1 for v in nonroot)) for i in (0, 1)
        ):
            raise ValidationError(("three_terminal_action",))
    return cut


def _replay_greedy(window, projection, proof, cycle_basis, inputs, native=False):
    """Verify each greedy minimum against every eligible cycle, then reconstruct P."""
    boundary_basis = window.D.image_basis()
    beta = len(cycle_basis) - len(boundary_basis)
    hypotheses = {
        "coefficient_field": "F2",
        "positive_weights": True,
        "arithmetic_policy": window.arithmetic,
        "betti": beta,
    }
    if content_id("hypotheses", proof.get("hypotheses")) != content_id(
        "hypotheses", hypotheses
    ):
        raise ValidationError(("greedy_hypotheses",))
    if (
        type(proof.get("theoretical_upper_bound")) is not int
        or proof["theoretical_upper_bound"] != beta
    ):
        raise ValidationError(("greedy_theoretical_bound",))
    if len(inputs) * max(1, beta) > 100_000:
        raise ValidationError(("certificate_replay_state_limit",))
    selected = proof.get("selected_generators")
    if not isinstance(selected, (tuple, list)) or len(selected) != beta:
        raise ValidationError(("greedy_generator_count",))
    R = matrix_from_data(proof.get("cycle_retraction"))
    if (
        (R.nrows, R.ncols) != (window.n, window.n)
        or R @ R != R
        or window.A @ R != Matrix.zero(window.m, window.n)
        or any(R.apply(z) != z for z in cycle_basis)
        or projection @ R != projection
    ):
        raise ValidationError(("cycle_retraction",))
    full = list(boundary_basis)
    for candidate in selected:
        z = validate_vector(candidate, window.n)
        span = Matrix.from_columns(full, nrows=window.n)
        if window.A.apply(z) != (0,) * window.m or span.solve(z) is not None:
            raise ValidationError(("greedy_independence",))
        actual = (
            sum(w for w, bit in zip(window.weights, z) if bit),
            sum(bit << j for j, bit in enumerate(z)),
        )
        if native:
            from .native import PreparedMatrix

            membership = PreparedMatrix(span).membership_many(x for x, _ in inputs)
        else:
            membership = (span.solve(x) is not None for x, _ in inputs)
        minimum = min(
            (cost, sum(bit << j for j, bit in enumerate(x)))
            for (x, cost), member in zip(inputs, membership)
            if not member
        )
        if actual != minimum:
            raise ValidationError(("greedy_minimum_or_tie_break",))
        full.append(z)
    basis = Matrix.from_columns(full, nrows=window.n)
    if native:
        from .native import PreparedMatrix

        solved = PreparedMatrix(basis).solve_many(R.transpose().rows)
    else:
        solved = (basis.solve(z) for z in R.transpose().rows)
    coordinates = Matrix.from_columns(solved, nrows=len(full))
    section = Matrix.from_columns(
        ((0,) * window.n,) * len(boundary_basis) + tuple(selected), nrows=window.n
    )
    if section @ coordinates != projection:
        raise ValidationError(("greedy_section_action",))
    return beta


def _validated_certificate(evidence, checks, level):
    """Keep backend claims separate from the independently generated public checks.

    Re-reading an already normalized record preserves its original evidence without
    nesting another evidence layer on every round trip. Only a supported, replayed
    optimization proof is retained at the public certificate's top level.
    """
    certificate = {
        "solver_evidence": evidence.get("solver_evidence", evidence),
        **checks,
    }
    if level in {"CertifiedUpperBound", "CertifiedInterval", "ExactOptimal"}:
        certificate["optimization"] = evidence["optimization"]
    return certificate


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
