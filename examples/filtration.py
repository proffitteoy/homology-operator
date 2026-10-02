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
    print(
        json.dumps(
            {
                "family_result": family.to_result().to_dict(),
                "endpoint_mass_control": controls,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
