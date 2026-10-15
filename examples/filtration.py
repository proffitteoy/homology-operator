"""Joint finite filtration output, using no oracle or precomputed barcode."""

from dataclasses import replace
import subprocess
import json

from homology_operator import (
    ChainWindow,
    FeasibleSolver,
    HomologyOperator,
    Matrix,
    OperatorFamily,
    ProjectionProblem,
    ResourceLimits,
    validate_optimal_1_cycle,
)


def main():
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    first = ChainWindow(
        0,
        Matrix.zero(0, 2),
        Matrix.zero(2, 0),
        (),
        ("v0", "v1"),
        (),
        (10, 1),
        source_metadata={"source": "hand-derived H0 merge", "stage": 0},
    )
    second = replace(
        first,
        D=Matrix.from_rows(((1,), (1,))),
        basis_next=("edge",),
        source_metadata={"source": "hand-derived H0 merge", "stage": 1},
    )
    limits = ResourceLimits(
        state_limit=100, wall_time_limit=10, matrix_entry_limit=1000
    )
    windows = (first, second, second)
    operators = tuple(
        HomologyOperator(
            w, FeasibleSolver().solve(ProjectionProblem(w, limits)), revision
        )
        for w in windows
    )
    family = OperatorFamily((0, 1, 1), windows, operators)
    controls = []
    for i in range(3):
        for j in range(i, 3):
            family.transport_certificate(i, j)
            family.track_class((1, 1), i, j)
            family.track_mass((0, 1), i, j)
            family.track_support((0, 1), i, j)
            family.track_shared_support((1, 0), (0, 1), i, j)
            family.track_union_support((1, 0), (0, 1), i, j)
            controls.append(family.endpoint_mass_bound((0, 1), i, j, limits).to_dict())
    # Historical interval generators are an opt-in output, unlike endpoints.
    family.barcode_basis()
    for reference in family.features().value:
        family.resolve_feature(reference, reference["birth_stage"])
        assert family.feature_pairing(reference).state == "Unavailable"
    # A source binds actual one-simplex prefixes, including their full order.
    vertex = replace(
        first,
        A=Matrix.zero(0, 1),
        D=Matrix.zero(1, 0),
        basis_current=("v0",),
        weights=(10,),
    )
    vertex_op = HomologyOperator(
        vertex, FeasibleSolver().solve(ProjectionProblem(vertex, limits)), revision
    )
    simplex_family = OperatorFamily(
        (0, 0, 1),
        (vertex, first, second),
        (vertex_op, operators[0], operators[1]),
        simplex_source={
            "stage_convention": "AfterInsertion",
            "simplices": [
                {"vertices": (0,), "label": "v0"},
                {"vertices": (1,), "label": "v1"},
                {"vertices": (0, 1), "label": "edge"},
            ],
        },
    )
    for reference in simplex_family.features().value:
        assert simplex_family.feature_pairing(reference).state == "Computed"
        simplex_family.resolve_feature(reference, 2)
    # A finite H1 birth pair, with unit costs and an explicit simplex order.
    stream = ((0,), (1,), (2,), (0, 1), (1, 2), (0, 2), (0, 1, 2))
    cycle_windows = []
    for count in range(1, len(stream) + 1):
        cells = tuple(
            tuple(s for s in stream[:count] if len(s) == d) for d in (1, 2, 3)
        )
        boundaries = tuple(
            Matrix.from_columns(
                (tuple(int(set(r) < set(c)) for r in rows) for c in columns), len(rows)
            )
            for rows, columns in zip(cells, cells[1:])
        )
        cycle_windows.append(
            ChainWindow(
                1,
                *boundaries,
                *(tuple(map(str, group)) for group in cells),
                (1,) * len(cells[1]),
                weight_semantics="unit",
            )
        )
    cycle_family = OperatorFamily(
        tuple(range(len(stream))),
        tuple(cycle_windows),
        tuple(
            HomologyOperator(w, FeasibleSolver().solve(ProjectionProblem(w)))
            for w in cycle_windows
        ),
        simplex_source={
            "stage_convention": "AfterInsertion",
            "simplices": [{"vertices": s, "label": str(s)} for s in stream],
        },
    )
    feature = cycle_family.features().value[0]
    cycle = cycle_family.optimal_1_cycle(feature)
    assert cycle.state == "Computed" and cycle.value["mass"] == 3
    assert validate_optimal_1_cycle(cycle_family, feature, cycle)["optimality_verified"]
    print(
        json.dumps(
            {
                "family_result": family.to_result().to_dict(),
                "simplex_family_result": simplex_family.to_result().to_dict(),
                "endpoint_mass_control": controls,
                "optimal_1_cycle": cycle.to_dict(),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
