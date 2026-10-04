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
| `NativeFeasibleSolver` | StableBasisOrder/Feasible; each chain space at most 64 dimensions |
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

## Budgets and cancellation

`ResourceLimits` provides state, wall-time, and logical matrix-entry limits.
Checks are cooperative checkpoints, not hard process memory or step preemption.
Independent validation, certificate replay, serialization, and recovery have
their own costs and cannot be omitted from complete timing.

`CancellationToken` can be supplied to `ProjectionProblem` and supported native
geometry. Cancellation is reported as `ResourceExhausted` with a reason, and any
retained candidate must still pass independent validation. Not all algebra or
filtration operations accept a cancellation token; see the [API](../INTERFACE.md).
