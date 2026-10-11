# Native and batch operations

[中文](../../guide/native.md)

## Optional Rust extension

The locked build uses Rust 1.98.1, PyO3 0.29.3, and maturin 1.15.0. Native CI
covers Windows x64/MSVC with Python 3.10 and Linux x64 with Python 3.12. Other
combinations are outside that matrix. Windows also needs MSVC build tools.
From the repository root in PowerShell:

```powershell
uv sync --locked --python 3.10
$pythonPath = uv run --locked python -c "import sys; print(sys.executable)"
$env:RUSTUP_TOOLCHAIN = '1.98.1'
uv tool run --from maturin==1.15.0 maturin build --manifest-path native/Cargo.toml --release --locked --interpreter $pythonPath --out .task-artifacts/native-wheels
$wheel = Get-ChildItem .task-artifacts/native-wheels/*.whl | Sort-Object LastWriteTime -Descending | Select-Object -First 1
uv pip install --python $pythonPath $wheel.FullName
```

Use `uv run --locked --no-sync ...` afterward to retain the separately installed
extension; reinstall it after another sync. `backend_info()` in
`homology_operator.native` reports actual availability and extension provenance.

| Native entry | Scope |
| --- | --- |
| `NativeFeasibleSolver` | StableBasisOrder/Feasible; multiword chain spaces, subject to logical-entry budgets |
| `NativeFactorizedSolver` | Same-P Factorized/HC action; `matrix_free_output=True`; no optimality certificate |
| `PreparedMatrix` | Multiword packed stable decomposition and reusable multi-RHS; not a projection solver |
| `GeometryWorkspace` / `geometry_batch` | Same-P cyclic geometry for Matrix and Factorized/HC; six-identity binding |

Native geometry does not support CyclicAction. Integer mass uses checked u64
where possible; noninteger rational weights, large integers, and overflow use
explicit exact Python fallback. Floating geometry retains binary64 `fsum`.
Workspace reuse does not alter saved snapshots or query history and does not
provide a concurrent sharing or RSS limit guarantee.

Missing or incompatible extensions produce `Unavailable` for supported solver
and batch entries. Direct packed tools and workspace creation require an
extension and raise `ImportError` when missing. There is no implicit fallback.

Rank/kernel/image preparation can use
`PreparedMatrix(matrix, full=False, diagnostics=False)` to omit the square row
transform and fill counters. Solves and membership require `full=True`.
HC factors are built in Rust without materializing P; implicit batch calls reuse
an operator-owned action workspace. These handles remain process-local and do
not skip independent validation or snapshot recovery. See the [API](../INTERFACE.md)
for cache and diagnostic behavior, and rebuild from matching source for binding API 3.

## Budgets and cancellation

`ResourceLimits` provides state, wall-time, and logical matrix-entry limits.
Compact Factorized/HC construction uses the separate `packed_word_limit`
(None selects 8,000,000 words); see the [accounting contract](../SOLVER_CONTRACT.md#resources-cancellation-and-comparison).
Checks are cooperative checkpoints, not hard process memory or step preemption.
Independent validation, certificate replay, serialization, and recovery have
their own costs and cannot be omitted from complete timing.

`CancellationToken` can be supplied to `ProjectionProblem` and supported native
geometry. Cancellation is reported as `ResourceExhausted` with a reason, and any
retained candidate must still pass independent validation. Not all algebra or
filtration operations accept a cancellation token; see the [API](../INTERFACE.md).

Native matrix handles, adaptive sparse fill and section-search reuse are described
in the [API](../INTERFACE.md) and [solver contract](../SOLVER_CONTRACT.md).
