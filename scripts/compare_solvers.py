"""Frozen Phase-3 solver comparison; preserves unsupported and interrupted runs.

Run with the installed reference package: uv run python scripts/compare_solvers.py
--output benchmarks/phase3_reference.json. This is not a speed-ranking benchmark.
"""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
import tracemalloc

from homology_operator import (
    Matrix,
    ChainWindow,
    ProjectionProblem,
    ResourceLimits,
    HomologyOperator,
    FeasibleSolver,
    ExhaustiveExactSolver,
    GreedyCertifiedSolver,
    Rank2ExactSolver,
    StructuredFamilySolver,
    solve_projection,
    validate_solution,
)
from homology_operator.result import canonical_json, content_id, input_identity
from homology_operator.chain import action_data
from homology_operator.solver import _Budget, _Exhausted, _cycle_objective
from homology_operator.solver import ProjectionSolution
from homology_operator.result import QueryResult, make_identity
from homology_operator.validation import validate_projection

ROOT = Path(__file__).resolve().parents[1]
SOLVERS = {
    solver.__name__: solver
    for solver in (
        FeasibleSolver,
        ExhaustiveExactSolver,
        GreedyCertifiedSolver,
        Rank2ExactSolver,
        StructuredFamilySolver,
    )
}


class BoundaryFlipExperiment(FeasibleSolver):
    """Experimental T11 one-entry local descent; never registered as a backend.

    Starting from the greedy section, toggle one boundary basis coefficient of
    one homology generator. Require strict objective improvement; choose packed
    projection columns for equal improving candidates. A local fixed point is
    not an optimality certificate. All objective evaluations use full cycles.
    """

    def capabilities(self):
        return dict(super().capabilities()) | {
            "arithmetic_policies": ("ExactInteger", "ExactRational"),
            "certificate_levels": (
                "Feasible",
                "CertifiedUpperBound",
                "CertifiedInterval",
            ),
        }

    def solve(self, problem):
        window = problem.window
        method = type(self).__name__
        config = problem.solver_config(method)
        budget = _Budget(problem.resource_limits)
        seed = GreedyCertifiedSolver().solve(problem)
        if seed.projection is None:
            return replace(seed, method=method, solver_config=config)
        budget.states = seed.resource_usage["states"]
        best, value = seed.projection, seed.objective.value
        witness = seed.objective.details.get("witness")
        exhausted = seed.diagnostics[0] if seed.status == "ResourceExhausted" else None
        visited, improvements, local_complete = 0, 0, False
        cycles = Matrix.from_columns(window.A.kernel_basis(), nrows=window.n)
        beta = window.n - window.A.rank() - window.D.rank()
        try:
            if exhausted is not None:
                raise _Exhausted(exhausted)
            budget.step()
            boundaries = window.D.image_basis()
            outputs = Matrix.from_columns(best.image_basis(), nrows=window.n)
            coordinates = Matrix.from_columns(
                (outputs.solve(z) for z in best.transpose().rows), nrows=beta
            )
            budget.entries(6 * window.n**2 + window.n * (cycles.ncols + beta))
            while True:
                origin, initial_value = best, value
                choice = None
                for boundary in boundaries:
                    for row in coordinates.rows:
                        budget.step()
                        delta = Matrix.from_rows(
                            tuple(tuple(bit * c for c in row) for bit in boundary),
                            ncols=window.n,
                        )
                        candidate = origin + delta
                        validate_projection(window, candidate)
                        candidate_value, candidate_witness = _cycle_objective(
                            window, candidate, cycles, budget
                        )
                        visited += 1
                        key = tuple(
                            sum(bit << j for j, bit in enumerate(column))
                            for column in candidate.transpose().rows
                        )
                        if candidate_value < initial_value and (
                            choice is None or (candidate_value, key) < choice[:2]
                        ):
                            choice = candidate_value, key, candidate, candidate_witness
                            # Keep completed improvements when a sweep is interrupted.
                            value, _, best, witness = choice
                            improvements += 1
                if choice is None:
                    local_complete = True
                    break
        except _Exhausted as error:
            exhausted = str(error)
        identity = make_identity(
            window, best, seed.solver_run_id, problem.tie_break_policy
        )
        count = (1 << cycles.ncols) - 1
        lower = (
            Fraction(0 if exhausted else int(beta > 0)) if value is not None else None
        )
        level = (
            "Feasible"
            if value is None
            else "ExactOptimal"
            if lower == value
            else "CertifiedInterval"
        )
        return ProjectionSolution(
            "ResourceExhausted" if exhausted else "Solved",
            seed.solver_run_id,
            best,
            identity,
            level,
            QueryResult(
                "ResourceExhausted"
                if value is None
                else "EmptyDomain"
                if count == 0
                else "Computed",
                value,
                identity,
                None if value is None else True,
                {"witness": witness, "nonzero_cycles": count},
            ),
            {}
            if value is None
            else {
                "optimization": {
                    "kind": "CycleBounds",
                    "nonzero_cycles": count,
                    "lower_bound_method": "UniversalHomology",
                }
            },
            {
                **budget.usage(),
                "neighbors_evaluated": visited,
                "improvements": improvements,
                "local_complete": local_complete,
            },
            (exhausted,) if exhausted else (),
            problem.tie_break_policy,
            method=method,
            arithmetic_policy=window.arithmetic,
            lower_bound=lower,
            upper_bound=value,
            solver_config=config,
        )


class _MeasuredSolver:
    """Time the existing backend while keeping production dispatch/validation."""

    def __init__(self, backend):
        self.backend = backend
        self.seconds = self.peak_bytes = None

    def capabilities(self):
        return self.backend.capabilities()

    def solve(self, problem):
        tracemalloc.start()
        started = perf_counter()
        try:
            return self.backend.solve(problem)
        finally:
            self.seconds = perf_counter() - started
            self.peak_bytes = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()


def compare(problem, backend_name):
    """One immutable problem and backend; construction and post-check costs split."""
    if tracemalloc.is_tracing():
        raise ValueError("comparison requires exclusive tracemalloc ownership")
    config = problem.solver_config(backend_name)
    common_config = {key: value for key, value in config.items() if key != "method"}
    problem_id = content_id(
        "comparison-problem", {**input_identity(problem.window), **common_config}
    )
    measured = (
        _MeasuredSolver(
            (
                BoundaryFlipExperiment
                if backend_name == "BoundaryFlipExperiment"
                else SOLVERS[backend_name]
            )()
        )
        if backend_name in SOLVERS or backend_name == "BoundaryFlipExperiment"
        else None
    )
    started = perf_counter()
    solution = solve_projection(
        problem, measured if measured is not None else backend_name
    )
    dispatch_seconds = perf_counter() - started
    verification, validation_seconds, validation_peak = None, None, None
    readout, readout_seconds = None, None
    if solution.projection is not None:
        tracemalloc.start()
        started = perf_counter()
        try:
            verification = validate_solution(problem.window, solution)
        finally:
            validation_seconds = perf_counter() - started
            validation_peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
        # An extra audit readout never upgrades the solver's own certificate.
        started = perf_counter()
        op = HomologyOperator(problem.window, solution)
        readout = op.stretch(problem.resource_limits).to_dict()
        readout_seconds = perf_counter() - started
    construction_seconds = None if measured is None else measured.seconds
    return {
        "problem_id": problem_id,
        "backend": backend_name,
        "input_identity": input_identity(problem.window),
        "request": config,
        "comparison_group": content_id(
            "comparison-group",
            (problem_id, solution.certificate_level, solution.status),
        ),
        "solver": solution.solver_metadata(),
        "projection": None
        if solution.projection is None
        else action_data(solution.projection),
        "identity": solution.identity,
        "certificate": solution.certificate,
        "independent_validation": verification,
        "audit_current_objective": readout,
        "costs": {
            "construction_seconds": construction_seconds,
            "construction_python_peak_bytes": None
            if measured is None
            else measured.peak_bytes,
            "dispatch_seconds": dispatch_seconds,
            "dispatch_overhead_including_validation_seconds": dispatch_seconds
            - (construction_seconds or 0),
            "independent_revalidation_seconds": validation_seconds,
            "independent_revalidation_python_peak_bytes": validation_peak,
            "operator_construction_and_audit_readout_seconds": readout_seconds,
            "total_measured_seconds": dispatch_seconds
            + (validation_seconds or 0)
            + (readout_seconds or 0),
            "rss_peak_bytes": None,
        },
    }


def fixture_problem(fixture):
    weights = tuple(
        Fraction(x["numerator"], x["denominator"]) if isinstance(x, dict) else x
        for x in fixture["weights"]
    )
    A, D = (
        Matrix(x["nrows"], x["ncols"], x["rows"]) for x in (fixture["A"], fixture["D"])
    )
    window = ChainWindow(
        fixture["k"],
        A,
        D,
        fixture["basis_previous"],
        fixture["basis_current"],
        fixture["basis_next"],
        weights,
        fixture["weight_semantics"],
        fixture["unit"],
        fixture["arithmetic"],
        source_metadata={
            "fixture_id": fixture["id"],
            "input_hash": fixture["input_hash"],
            "source": fixture["source"],
        },
    )
    return ProjectionProblem(window)


def suite():
    fixtures = json.loads(
        (ROOT / "tests/fixtures/reference.json").read_text(encoding="utf-8")
    )["fixtures"]
    for fixture in fixtures:
        base = fixture_problem(fixture)
        for target in ("Feasible", "ExactOptimal"):
            yield fixture["id"], replace(base, requested_certificate_level=target)
    k4 = next(f for f in fixtures if f["id"] == "h1_k4_stage_4")
    for states in (100_000, 0, 20):
        yield (
            f"h1_k4_stage_4_interval_states_{states}",
            replace(
                fixture_problem(k4),
                requested_certificate_level="CertifiedInterval",
                resource_limits=ResourceLimits(state_limit=states),
            ),
        )
    # T-A4 macro cut model, with its equivalence witness declared separately.
    edges = ((3, 0), (3, 1), (3, 4), (4, 0), (4, 2))
    delta = Matrix.from_rows(
        (tuple(int(u == t) ^ int(v == t) for t in (1, 2, 3, 4)) for u, v in edges)
    )
    A = Matrix.from_rows(delta.transpose().kernel_basis(), ncols=5)
    D = Matrix.from_columns(delta.transpose().rows[2:], nrows=5)
    window = ChainWindow(
        1,
        A,
        D,
        ("relation",),
        ("U0", "U1", "UV", "V0", "V2"),
        ("U", "V"),
        (1, Fraction(3, 2), Fraction(3, 4), 1, Fraction(7, 4)),
        source_metadata={
            "source": "pinned PROOF T-A4",
            "revision": "6143729669902ee875b211b58085e954c76cdf88",
            "delta": "1/4",
        },
    )
    yield (
        "cut_macro_general",
        ProjectionProblem(window, requested_certificate_level="CertifiedInterval"),
    )
    yield (
        "cut_macro_specialized",
        ProjectionProblem(
            window,
            requested_certificate_level="ExactOptimal",
            input_structure="ThreeTerminalCut",
            solver_options={
                "dual_vertex_count": 5,
                "dual_edges": edges,
                "terminals": (0, 1, 2),
            },
        ),
    )
    # Independent fixed T-B1 formula, using explicit D but requesting compact P.
    for m in (2, 3, 4):
        n = (1 << m) - 1
        P = Matrix.from_columns(
            (
                tuple(int((i - j) % n in {1 << s for s in range(m)}) for i in range(n))
                for j in range(n)
            ),
            nrows=n,
        )
        D = Matrix.from_columns((Matrix.identity(n) + P).image_basis(), nrows=n)
        window = ChainWindow(
            1,
            Matrix.zero(0, n),
            D,
            (),
            tuple(f"e{i}" for i in range(n)),
            tuple(f"b{i}" for i in range(D.ncols)),
            (1,) * n,
            source_metadata={
                "source": "pinned PROOF T-B1",
                "revision": "6143729669902ee875b211b58085e954c76cdf88",
                "m": m,
            },
        )
        yield (
            f"cyclic_m{m}",
            ProjectionProblem(
                window,
                input_structure="CyclicTrace",
                matrix_free_output=True,
                requested_certificate_level="ExactOptimal",
            ),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiment", choices=("boundary-flips",))
    args = parser.parse_args()
    source_paths = sorted((ROOT / "src").rglob("*.py")) + [
        Path(__file__).resolve(),
        ROOT / "tests/fixtures/reference.json",
        ROOT / "tests/fixtures/solver_reference.json",
        ROOT / "uv.lock",
    ]
    manifest = {
        str(path.relative_to(ROOT)).replace("\\", "/"): sha256(
            path.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for path in source_paths
    }
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()
    )
    rows, problems = [], {}
    if args.experiment:
        fixtures = json.loads(
            (ROOT / "tests/fixtures/reference.json").read_text(encoding="utf-8")
        )["fixtures"]
        cases = [(f["id"], fixture_problem(f)) for f in fixtures]
        cases.append(
            (
                "two-boundaries-beta3",
                ProjectionProblem(
                    ChainWindow(
                        2,
                        Matrix.zero(0, 5),
                        Matrix.from_columns(
                            ((1, 1, 1, 1, 0), (1, 1, 0, 0, 1)), nrows=5
                        ),
                        (),
                        ("a", "b", "c", "d", "e"),
                        ("f", "g"),
                        (5, 7, 4, 2, 6),
                    )
                ),
            )
        )
        cases = [
            (name, replace(problem, resource_limits=ResourceLimits(state_limit=limit)))
            for name, problem in cases
            for limit in (20, 2000)
        ]
        backends = (
            "GreedyCertifiedSolver",
            "ExhaustiveExactSolver",
            "BoundaryFlipExperiment",
        )
    else:
        cases, backends = suite(), (*SOLVERS, "GeneralSearchSolver")
    for fixture_id, problem in cases:
        for backend in backends:
            row = compare(problem, backend)
            row["fixture_id"] = fixture_id
            problems[row["problem_id"]] = problem.window.to_dict()
            rows.append(row)
        print(
            f"completed {fixture_id} / {problem.requested_certificate_level}",
            flush=True,
        )
    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_revision": revision,
        "working_tree_dirty": dirty,
        "source_manifest_sha256_lf": manifest,
        "source_snapshot_id": content_id("source-snapshot", manifest),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "protocol": {
            "timing": "perf_counter; construction and independent revalidation each run with tracemalloc enabled",
            "memory": "Python traced allocation peak, not process RSS; unavailable RSS is null",
            "cost_boundary": "production dispatch includes capability checks, construction and production validation; separate revalidation and operator/audit readout costs are additionally recorded",
            "comparison": "same problem_id is necessary; compare only identical requested configuration and actual certificate/status groups; unsupported rows are retained",
            "runs_per_case": 1,
            "ranking_claim": False,
            "general_search": "unimplemented backend is explicitly recorded as Unavailable, not omitted",
            "experiment": args.experiment,
        },
        "rows": rows,
        "problem_windows": problems,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes((canonical_json(report) + "\n").encode("utf-8"))
    print(f"wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
