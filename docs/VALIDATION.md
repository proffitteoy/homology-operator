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
fmt/Clippy 与强制 native 差分/回归测试。S4-05 另提供精确比值商余比较的 Rust 单测；
Rust 单测不能替代 Python 差分/不变量测试，实际本地命令与证据见下方 S4-05 记录。
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

### S4-06 几何与工作区

S4-06 增加6项几何 workspace 回归：显式/Factorized/HC 在 0/1/63/64/65/127/128/129 维上的原坐标输出；u64 最大值、单次求和溢出与超大整数/任意正有理权；binary64 fsum、subnormal 与浮点溢出；0/1/8/64/1024 两次批查询和真实缓冲扩容复用；非循环/非法坐标/索引拒绝；projection/weight/basis/run 混用、查询 JSON 往返和 NotComputed/Computed 快照历史。既有23个冻结窗口的几何对拍继续经过新入口，独立原坐标质量与共享质量恒等式同时核对。缺少扩展显式返回 Unavailable，native CI 强制这些测试实际运行；有限性能采样另见 [BENCHMARKS](BENCHMARKS.md)，不替代 S4/S5 准入。

### S4-04–07 联合回归

`tests/test_s4_integration.py` 在同一过滤中组合四种限定 solver 与 CyclicAction、
HC、Factorized，检查几何 workspace、全部区间传输、历史基、schema 1/2 与无扩展恢复。
原生组合测试要求重建后的当前扩展；reference-only 测试不把跳过解释为 native 通过。
整合前 main `f0c15265` 的163项以及各工作包历史日志保持原记录；本次候选的实际测试数、
命令与最终 CI 另按准确 head 记录，不用旧分支成绩替代。

### S4-07 过滤验收

S4-07 新增相邻映射/历史基的5689个原 corpus 对拍、共享快照 schema 1/2 篡改/往返、
受控缓存与长过滤读取测试；44个冻结过滤/solver配置继续核对 composition、rank、PH、几何及历史基。
此前同步 main 的 S4-04 后，整合源码 `9f69cb4` 的156项本地强制 native 测试无跳过地通过；
原始日志、归纳证明及有限消融边界见 [过滤验收](S4_FILTRATION.md)。
随后同步 main `63138fc` 的文档与 S4-05，实现源码整合后163项强制 native 回归无跳过地通过；
四 native solver 与 Cyclic/HC/Factorized 混合过滤、schema 1/2 往返及无扩展恢复另通过。
本地结果不替代远端 CI 及其他工作包的 native 联合验收。

### S4-05 本地与整合验证

S4-05 增加7项 native solver 验证：原23窗口的支持/拒绝、三种搜索的完整 P/objective/
证书/并列/state 对拍；三终端及 m=2/3/4 两种结构表示；全部 state 中断位置与零时间/
条目预算；任意精度整数/互素大分母后备与 u128 比值交叉乘积溢出；0/1及63/64/65、
127/128/129宽度的独立 objective；两条重放路径的证书/action/witness 篡改拒绝；
缺少扩展的 Unavailable 与 portable reference 恢复。所有合法 native 解另强制由
原 Python verifier 重新验收；连续 JSON 往返、projection_id 与配置/run 区分有检查。
Rust 单测独立检查商余比较的全部小比值及 u128 极端边界。

本地完整151项强制native测试无跳过地通过，含新增7项；原始日志与700样本测量见
[性能协议](BENCHMARKS.md)。reference wheel的真实无扩展隔离安装及native快照的
完整reference恢复另实际通过。新增测试纳入现有native CI的强制入口；Windows Rust单测命令为：

```powershell
$env:PYO3_PYTHON = Join-Path (Get-Location) '.venv/Scripts/python.exe'
cargo +1.98.1 test --manifest-path native/Cargo.toml --locked --lib
```

Rust 单测本轮只在 Windows 执行；跨平台 release 构建与 Python differential 已接入
现有 native CI，远端成绩仍以该分支精确 SHA 的实际 checks 为据。


本分支普通 merge 同步已合并 S4-04 的 main `520ecc9` 后，重新构建 release 扩展，
完整159项强制 native 回归无跳过地通过（137.268秒）；整合日志追加保存在
[同一验证日志](../benchmarks/s4_solver_verification.log)，原151项记录保留。
Rust 单测/fmt/Clippy、Ruff、文档检查、reference sdist/wheel、真实无扩展安装下的
四 solver 与旧 native 快照重放及两示例也通过。性能样本仍属于 `99adf07`，未重新测量整合源码。

[S4-04 / PR #80](https://github.com/proffitteoy/homology-operator/pull/80) 新增 8 项验收（其中 2 项不依赖 Rust），覆盖23窗口的因子/HC 全链作用与几何、
11过滤族的区间 transport/rank/barcode/恢复、完整增广逆及小窗口、字边界、
阻断完整 P/展开 G/U 路径、非法因子/零投影/身份版本篡改与资源失败。
这些历史记录不替代当前整合 head 的回归；原生几何/workspace 已纳入上述联合测试。
全后端性能、GUDHI、采样稳定性、应用收益与发行依各自门槛验收；有限检查不推出一般证明或通用加速。
阶段报告和原始实验保留当时状态、失败和不利结果。

理论固定为 `homology-operator-lab @ 6143729669902ee875b211b58085e954c76cdf88`。
[原始验证契约](https://github.com/proffitteoy/homology-operator/blob/c0299c3b7750c8a12ced00bf479753236a7dbc85/docs/VALIDATION.md)
保留研究父提交 cc6f9b637552d3eda4b948121b932576ae5eeec9 的 32 组检查来源记录（16 exact、16 auxiliary）；
未在本次文档整理中复跑，不能当作本库测试成绩。

整体研究门槛仍保留：可复现 reference、同输出优化与独立的稳定性/任务价值验证。
稳定性需声明网格族/权重/拓扑对应/恢复条件；应用需同预算 PH-only 与其他几何基线，
不能由形状正则、正权或小实例测试直接推出。

### S4-08 后端集成验收

本分支正常 merge 同步已完成前置的 main `e920de0`，不重写原工作包的性能数据。
[集成原始日志](../benchmarks/s4_integration_verification.log) 保存计算源码、逐文件 LF hash、
实际加载的扩展/wheel hash、完整命令与结果；129项是 Phase 3 历史基线，当前计数另记。
reference/native 的入口与取消支持边界见 [API](INTERFACE.md#后端可用性与协作取消s4-08)。

新增17项（9项集成、8项旧格式兼容）核对显式后端选择/同 solver 后备、非法/旧 ABI、
取消与预算原因区分、无重求解恢复、官方参数绑定的质量篡改拒绝、查询历史和六身份、
65维 Factorized/HC 不展开完整 P/L 的恢复、族 schema 1/2、真实另一线程取消原生枚举。
7份旧快照的来源/hash见 [FIXTURES](FIXTURES.md#s4-08-冻结旧快照)。
S4-04–07 的联合回归同时保留并运行，不替换它们的不变量和 oracle 检查。

本地 Windows x64 / CPython 3.12.13，Rust 1.98.1、PyO3 0.29.3、maturin 1.15.0：
计算源码 `e295ea17e1f694ff8c43607cf3bed870e741f41d` 的189项强制native全回归通过，
无跳过（179.368秒）。随后修正 backend_info 的真实 `.pyd` 路径、预算提前返回的非循环拒绝和
失败经过时间；最终计算源码为 `9596723`，189项强制native回归再次全部通过，无跳过（167.089秒）；
隔离两个wheel的17项全部通过；无扩展环境14项通过、6项原生测试明确跳过。
后续验收追加在同一日志，不覆盖首次结果。
Rust fmt/Clippy(-D warnings)与精确比值单测通过，reference sdist/wheel和native release wheel构建通过。
两示例、Ruff check/format和文档/完整diff whitespace检查另实际运行。

隔离安装从 site-packages 导入，用 Python `-I` 排除源码与环境变量路径污染。
安装两个wheel时强制native，运行9项集成和8项旧格式；另建只装reference的环境，
确认 backend_info 为 Unavailable，运行reference边界/旧格式/S4联合测试，原生项明确跳过。
此外实际native构造65维Factorized/HC的单尺度及两版族快照，在另一无扩展环境恢复并重验，
输出hash一致。日志保存具体快照wire hash与生成/恢复命令；UUID/time导致wire hash每次可不同，
不据此宣称性能。两个表示的读取输出均为
`portable-output:76c9c01dec4a743edd09ae718014430976a292f607200b362e5aa7ee667b61b1`。

复跑打包边界（Windows；Linux将 Scripts/python.exe 换为 bin/python）：

```powershell
uv build --no-build-isolation
uv venv .task-artifacts/installed-env --python .venv/Scripts/python.exe
uv pip install --python .task-artifacts/installed-env/Scripts/python.exe dist/homology_operator-0.0.2.dev0-py3-none-any.whl .task-artifacts/native-wheels/homology_operator_native-0.0.2.dev0-cp312-cp312-win_amd64.whl
$env:HOMOLOGY_NATIVE_REQUIRED = '1'
& .task-artifacts/installed-env/Scripts/python.exe -I -m unittest discover -s tests -p test_integration.py -v
& .task-artifacts/installed-env/Scripts/python.exe -I -m unittest discover -s tests -p test_legacy_results.py -v
# 无扩展隔离环境：只安装reference wheel，移除强制native变量。
Remove-Item Env:HOMOLOGY_NATIVE_REQUIRED
uv venv .task-artifacts/reference-env --python .venv/Scripts/python.exe
uv pip install --python .task-artifacts/reference-env/Scripts/python.exe dist/homology_operator-0.0.2.dev0-py3-none-any.whl
& .task-artifacts/reference-env/Scripts/python.exe -I -m unittest discover -s tests -p test_integration.py -v
& .task-artifacts/reference-env/Scripts/python.exe -I -m unittest discover -s tests -p test_legacy_results.py -v
& .task-artifacts/reference-env/Scripts/python.exe -I -m unittest discover -s tests -p test_s4_integration.py -v
```

wheel文件名必须匹配实际解释器/平台；CI分别在Windows Python3.10和Linux Python3.12构建后选择产物，
reference CI的两种Python版本另验证真实无扩展安装。远端结果绑定最终PR精确head，不以本地成绩替代。

取消样本只验证协作响应：8192坐标、16维循环基、quota=100000，另一线程发出cancel后返回
cancelled且实际states在0与65535之间，验收上界为2秒。日志保留3次实际延迟/states与复跑源代码，
不承诺一般规模的最坏延迟。库内失败原因、外层timeout/OOM和合法0分别表达；本轮没有故意制造进程OOM。
矩阵条目是逻辑预算，非RSS；独立validator、证书重放、冻结/转换及恢复重算都有成本，仍需完整计时。
本轮完成绑定/安装/恢复一致性检查，不提供新的端到端提速结论，S4-09与S5仍独立验收。

### S4-09 冻结验收与安装

正式采样、父进程写入中断/续跑审计、全部统计组、准确源码/构建/hash和一键复跑命令见
[S4报告](S4_REPORT.md)。生产源码固定7fa812d，协议e288236，续跑harness9f3537f；
1880进程，计时/RSS各10区组；普通配置每进程5次重建，昂贵配置预声明1次。
采样结束后本地强制native完整193项通过、零跳过（125.177秒）；
新增4项harness测试覆盖不完整/不同输出准入、独立RSS缺失/退化、非循环P/L恢复审计、
Windows原子替换失败的数据保全。没有为复述实现添加测试。

reference-only独立wheel的20项集成/旧格式/联合恢复中14项通过，6项native按预期跳过；
双wheel独立环境同20项全部通过。Ruff、Rustfmt/Clippy、精确比值Rust单测、
打包、公开示例和文档检查通过；远端CI成绩与本地/Windows性能数据分开。

## S5 显式输入与 GUDHI oracle

[输入契约与真实命令](S5_GUDHI.md)提供可选 `oracle` 依赖组。GUDHI 3.11.0/NumPy 2.2.6
只用于 tests/oracle 与测量对照。新增 S5 workflow 强制安装锁定组，覆盖 Windows3.12/Linux3.10/3.12。
普通 reference/native 检查缺该组时明确跳过 GUDHI 专项测试；`HOMOLOGY_GUDHI_REQUIRED=1` 阻止静默跳过。
manifest 的标准库校验和链构造始终执行。S5-01 双边输入导出通过不等于 PH 或性能验收。

### S5-05/06 正式证据与报告重建

[S5报告](S5_REPORT.md)合并交付#74/#75，保存20配置、2840进程全部原值/失败、全部284组median/IQR/配对区间和分段。
review后对已有raw重新汇总，原summary未变；本次按用户要求取消追加隔离采样/correctness，不能记为新运行。
report_s5.py使用标准库和本包，在完整Git历史中核对冻结来源并重建两张CSV；真实命令/hash对拍见报告。
旧正式测量仍只绑定f4b0d58及S4生产源码/原二进制环境；当前review后helper拒绝旧freeze冒名运行。
本地correctness8项、采样9项、同步后采样10项分别通过，不冒充新的整仓或main CI成绩。
