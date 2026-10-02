"""Run one based chain window through the complete single-scale reference."""

import subprocess

from homology_operator import (
    ChainWindow,
    HomologyOperator,
    Matrix,
    ProjectionProblem,
    ResourceLimits,
    solve_projection,
)


def main():
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    # Two homologous coordinates: the deterministic selected mass is 10,
    # while the other representative has mass 1. No shortest solver is used.
    window = ChainWindow(
        0,
        Matrix.zero(0, 2),
        Matrix.from_rows(((1,), (1,))),
        (),
        ("v0", "v1"),
        ("edge",),
        (10, 1),
        source_metadata={"source": "hand-derived H0 interval", "input_basis": "v0,v1"},
    )
    limits = ResourceLimits(
        state_limit=100, wall_time_limit=10, matrix_entry_limit=1000
    )
    solution = solve_projection(ProjectionProblem(window, limits))
    op = HomologyOperator(window, solution, repository_revision=revision)
    for name, args in (
        ("betti", ()),
        ("kernel_basis", ()),
        ("class_representative", ((0, 1),)),
        ("selected_mass", ((0, 1),)),
        ("class_distance", ((1, 0), (0, 1))),
        ("support", ((0, 1),)),
        ("shared_support", ((1, 0), (0, 1))),
        ("union_support", ((1, 0), (0, 1))),
    ):
        op.readout(name, *args)
    op.stretch(limits)
    print(op.to_result().to_json())


if __name__ == "__main__":
    main()
