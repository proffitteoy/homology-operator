# 开发与验证

本页提供实际开发命令、检查范围和数学变更的最低门槛。安装/API 见 [INTERFACE](INTERFACE.md)，
当前 main/CI 见 [文档索引](README.md)，阶段与性能证据见各报告和 [BENCHMARKS](BENCHMARKS.md)。

## Reference 开发环境

Python 3.10+、uv；运行时仅标准库，开发依赖由 uv.lock 锁定。
CI 使用 uv 0.11.5、Python 3.10/3.12。根目录运行：

```powershell
uv sync --locked --python 3.10
uv run --locked python -m unittest discover -s tests -v
uv run --locked python examples/single_scale.py
uv run --locked python examples/filtration.py
uv run --locked ruff check .
uv run --locked ruff format --check .
uv build --no-build-isolation
pwsh -NoProfile -File ./scripts/check_docs.ps1
git diff --check
```

unittest 的实际总数取决于 checkout。未安装扩展时 native 测试明确跳过，
reference 的通过不证明 native 路径已测试。包导入或构建通过也不替代数学测试。
目前没有独立 typecheck 或发行命令，`uv build` 只生成本地产物。

## Native 构建与检查

按 [API 的 Rust 安装章节](INTERFACE.md#可选-rust-扩展) 构建并安装匹配解释器的 release wheel，
随后在根目录运行：

```powershell
$env:HOMOLOGY_NATIVE_REQUIRED = '1'
uv run --locked --no-sync python -m unittest discover -s tests -v
cargo +1.98.1 fmt --manifest-path native/Cargo.toml --check
cargo +1.98.1 clippy --manifest-path native/Cargo.toml --locked --all-targets -- -D warnings
```

`HOMOLOGY_NATIVE_REQUIRED=1` 使缺扩展直接失败，避免全部跳过后误报 native 成功。
`--no-sync` 保留单独安装的扩展；重新 sync 后需要再次安装。
当前 native CI 覆盖 Windows/MSVC Python 3.10 与 Linux Python 3.12 的 release 构建、
fmt/Clippy 与强制 native 差分/回归测试。当前 Cargo test 没有独立 Rust 单元测试，
不能用它的 0 tests 结果替代 Python 差分/不变量测试。
工作区有 native 源码变动时先重建；旧二进制不能验证新源码。

## 文档变更

普通文档改动运行文档检查与 `git diff --check`。
改安装命令、API 或代码示例时，实际运行对应入口/示例；不要为文字改动增加复述实现的测试。
数学定义、构造或 schema 变更则按下方表格补独立测试。

[check_docs.ps1](../scripts/check_docs.ps1) 需要 PowerShell 7，可从任意目录调用。
它按脚本位置定位仓库，检查根目录与 docs 下全部 Markdown（含未跟踪文件）：
必需入口、严格 UTF-8、冲突标记、本地行内文件链接存在且位于仓库内。
失败退出 1，成功打印文件/链接数。

它不验证标题锚点、引用式链接、外网可达性或完整 Markdown 语法；围栏示例不进入链接检查。
`git diff --check` 仅补充检查已跟踪文件的改动。两者均不证明数学正确、最优性或运行时性能。

## CI 与打包

- [reference.yml](../.github/workflows/reference.yml)：Python 3.10/3.12 的测试、示例、Ruff、build、隔离 wheel 导入与文档/空白检查。
- [native.yml](../.github/workflows/native.yml)：可选扩展在声明平台的构建、Rust 检查和强制 native 测试。

这两条 workflow 在 main push / PR 上运行。配置存在、某次本地通过和远端 CI 通过是不同证据。
远端结论绑定准确 head SHA；当前已核对状态集中在文档索引，不把旧报告回写成最新结果。

reference wheel 的本地隔离验证可用：

```powershell
uv venv .task-artifacts/docs-wheel-env --python 3.10
$wheel = Get-ChildItem dist/homology_operator-*.whl | Sort-Object LastWriteTime -Descending | Select-Object -First 1
uv pip install --python .task-artifacts/docs-wheel-env/Scripts/python.exe $wheel.FullName
& .task-artifacts/docs-wheel-env/Scripts/python.exe -I -c "import homology_operator; print(homology_operator.__version__)"
```

上例是 Windows 路径，Linux 使用该环境的 `bin/python`。隔离导入检查只验证打包可用。
许可证、公开发行、发布权限及版本兼容政策仍需在 [路线图 Phase 7](../HOMOLOGY_OPERATOR_ROADMAP.md) 收口。

## 数学变更的最低验证

| 变更领域 | 独立验证与失败输入 |
| --- | --- |
| F2 代数与 ChainWindow | 加乘、消元、核/像/solve；形状、空空间、非二元坐标、AD≠0、非法权重与基顺序 |
| 投影构造 | AGA=A、DUD=D、P²=P、L²=L、AP=0、PD=0；完整循环基上 z+Pz∈im(D) |
| 拓扑联合读取 | 小实例枚举循环验证 Pz=0⇔z∈im(D)、Pz=Py⇔z+y∈im(D)、Betti；拒绝非循环类查询 |
| 几何 | 原坐标质量、距离、支撑与交/并；对称、三角不等式、同类 iff 距离零、质量恒等式与统一身份 |
| Solver / stretch | 合法性、当前 objective、最优证书分别验证；bounds、并列、预算中断、空循环域与非空零同调的不同 0 状态 |
| 身份 / schema | 基/权重/P/配置变动的身份；round-trip、跨run混用、handle/证书/查询篡改与合法零/缺失 |
| 过滤 / transport | T_ii=I、composition、与诱导同调共轭；全区间 rank/barcode 独立对拍，重复 scale、末端存活与几何追踪 |
| Native / packed | reference canonical 输出加独立向量枚举；矩形/空/秩亏/不可解、多 RHS、63/64/65 与 127/128/129、尾部位和原列坐标 |
| 因子 / HC action | 所有坐标生成元及循环上的同 P/L，包括非循环延拓；非法因子/零投影/版本与身份篡改、无完整 P 的恢复 |
| 性能 | 同 fixture/P/solver/认证/预算，源码与构建 hash；完整构造/查询/验证/恢复成本、独立 RSS 与失败记录 |

必留反例：非零同调窗口中的零投影满足前三个投影等式，但不保持循环同调，validator 必须拒绝。
外部输入与恢复始终重验；受支持优化证书独立重放。通用 solver 声明不能绕过入口验证。

## Fixture 与 oracle

[FIXTURES](FIXTURES.md) 描述当前迁移格式与来源；不要预建路线图中的空目录。
每份 fixture 记录唯一标识、来源仓库/提交/路径、内容 hash、次数、A/D 显式形状、
三组带序基、正权/单位/算术、独立预期值与证据。过滤另记阶段/包含/权重继承/末端约定。

覆盖空链、零同调、单/多类、非平凡边界与 H0–H3；人工正权与真实欧氏面积/体积来源分别记录。
迁移研究数据保留原证据；会写结果的研究脚本在隔离副本运行。
独立同调/PH oracle 仅在 tests/oracle 或测量对照路径，不能填充生产结果。
GUDHI 同输入 F2 正式对拍属于 S5，不把现有独立 reduction 或归档原型当成该验收。

## 历史证据与结论边界

| 记录 | 绑定范围 |
| --- | --- |
| [Phase 1](PHASE1_REPORT.md) / [Phase 2](PHASE2_REPORT.md) | 单尺度与有限过滤、57 / 81 项历史测试、迁移与隔离 wheel |
| [Phase 3](PHASE3_REPORT.md) | main 54ce78b、129 项数学测试，五限定 solver/认证、对照/no-go 与联合验收 |
| [S4-02 回归日志](../benchmarks/s4_native_verification.log) | 140 项历史全回归：129 数学 + 4 测量 + 7 原型；原型尺寸有限 |
| [S4-03 回归日志](../benchmarks/s4_packed_verification.log) | 144 项历史全回归，另增 4 packed 差分/枚举与复用测试；详细源码/成本见 BENCHMARKS |
| [S4-04 回归日志](../benchmarks/s4_compact_verification.log) | 152 项历史全回归与无扩展 wheel 恢复；源码及有限 time/RSS 记录见 BENCHMARKS |

[S4-04 / PR #80](https://github.com/proffitteoy/homology-operator/pull/80) 新增 8 项验收（其中 2 项不依赖 Rust），覆盖23窗口的因子/HC 全链作用与几何、
11过滤族的区间 transport/rank/barcode/恢复、完整增广逆及小窗口、字边界、
阻断完整 P/展开 G/U 路径、非法因子/零投影/身份版本篡改与资源失败。
这些新增实现尚不能引用上述历史 main CI 作认证；原生几何/workspace 仍需对应支持域和独立验收。
全后端性能、GUDHI、采样稳定性、应用收益与发行依各自门槛验收；有限检查不推出一般证明或通用加速。
阶段报告和原始实验保留当时状态、失败和不利结果。

理论固定为 `homology-operator-lab @ 6143729669902ee875b211b58085e954c76cdf88`。
[原始验证契约](https://github.com/proffitteoy/homology-operator/blob/c0299c3b7750c8a12ced00bf479753236a7dbc85/docs/VALIDATION.md)
保留研究父提交 cc6f9b637552d3eda4b948121b932576ae5eeec9 的 32 组检查来源记录（16 exact、16 auxiliary）；
未在本次文档整理中复跑，不能当作本库测试成绩。

整体研究门槛仍保留：可复现 reference、同输出优化与独立的稳定性/任务价值验证。
稳定性需声明网格族/权重/拓扑对应/恢复条件；应用需同预算 PH-only 与其他几何基线，
不能由形状正则、正权或小实例测试直接推出。
