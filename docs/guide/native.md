# 原生与批查询

[English](../en/guide/native.md)

## 安装

可选扩展使用 Rust 1.98.1、PyO3 0.29.3 与 maturin 1.15.0，构建匹配当前源码的 release wheel。
Windows 需要 MSVC；正式平台见[平台支持](../platforms.md)。根目录 PowerShell：

```powershell
uv sync --locked --python 3.10
$pythonPath = uv run --locked python -c "import sys; print(sys.executable)"
$env:RUSTUP_TOOLCHAIN = '1.98.1'
uv tool run --from maturin==1.15.0 maturin build --manifest-path native/Cargo.toml --release --locked --interpreter $pythonPath --out .task-artifacts/native-wheels
$wheel = Get-ChildItem .task-artifacts/native-wheels/*.whl | Sort-Object LastWriteTime -Descending | Select-Object -First 1
uv pip install --python $pythonPath $wheel.FullName
```

此后用 `uv run --locked --no-sync ...` 保留扩展；重新 sync 后需再次安装。

## 支持范围

| 入口 | 范围 |
| --- | --- |
| NativeFeasibleSolver | 三个链空间至多 64 维、StableBasisOrder/Feasible |
| NativeFactorizedSolver | 同 P 的 Factorized/HC，matrix_free_output=True，无最优证书 |
| PreparedMatrix | 多字 packed 分解、多 RHS 与复用，独立于投影选择 |
| GeometryWorkspace / geometry_batch | Matrix 与 Factorized/HC 的循环几何；六身份绑定 |

四种限定优化 solver 支持显式 native 选择，支持域与认证要求保持原契约。
GeometryWorkspace 不支持 CyclicAction 原生几何；准备/批查询不改变已有快照与查询历史。
u64 质量检查溢出；非整数有理数、大整数或求和溢出显式精确后备，浮点保持 fsum。

## 缺失、后备与取消

backend_info 报告实际扩展来源与可用性。缺扩展时 solver/批入口为 Unavailable；直接 packed
工具与 workspace 创建抛 ImportError。后备仅显式 fallback=True，记录 requested/selected/reason。
Factorized 没有 reference 后备，不把 matrix-free 请求改为显式矩阵。
CancellationToken 在受支持检查点协作取消，报告 ResourceExhausted；不提供 RSS 硬限制或全流程抢占。
完整签名、缓冲与失败语义见[Python API](../INTERFACE.md#后端可用性与协作取消)。
