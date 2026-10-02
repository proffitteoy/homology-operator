# homology-operator

Boundary-native F2 homology operators with joint persistence and geometric outputs.

从有限带基链窗口 `C_{k+1} --D--> C_k --A--> C_{k-1}` 及正坐标权重出发，构造同调投影 `P` 与算子 `L=I+P`。拓扑、代表、距离、支撑与伸长来自同一个投影身份；过滤上的 persistence 由算子族的传输读取。


## 当前状态

2026-10-01 按 [冷启动计划](docs/冷启动.md) 完成初始化。2026-10-02 Phase 1 的 PR #30–#41、Phase 2 的 #42–#48 和 Phase 3 的 #49–#58 已全部合入 main。当前 reference 基线为 `54ce78bccdcba619ffa2a4d76aeb450bfd24270e`，该提交的 [Reference checks](https://github.com/proffitteoy/homology-operator/actions/runs/36998360788) 通过。129项数学测试、五种限定solver与证书、冻结对照/no-go、73次窗口支持运行和44个过滤配置的历史证据见 [Phase 3报告](docs/PHASE3_REPORT.md)；历史报告保留当时状态。

下一轮由同一私有 [Project #3](https://github.com/users/proffitteoy/projects/3) 管理：[S4/S5 项目计划](docs/S4_S5_PROJECT.md) 将 S4 定为同语义高性能开发、S5 定为 GUDHI 对拍与真实性能报告，细化原 Phase 4。新 S4 性能任务与 S5 对拍任务保留原有 S3 solver 阶段。上传研究计划、barcode 原型与原始记录已整合；可选 Rust 纵向原型已提供；完整高性能后端、GUDHI 正式对拍和性能报告仍按工作包推进。

Phase 3的[solver对照协议](docs/BENCHMARKS.md)保存324条基线和144条局部搜索支持、失败、中断与完整成本记录，认证等级分别报告；源码提交、输入与结果hash可核对。联合验收覆盖73次冻结窗口支持运行、44个过滤配置和五solver混合表示族。高性能、采样稳定性、应用收益、许可证与发行仍待后续阶段。

初始化前本地 `HEAD` 与 `origin/main` 均为 `6ddce1b4e4d55c0aaff399c001e684d908026830`。理论来源固定为 [homology-operator-lab 的指定提交](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88)，研究代码及其依赖不构成本仓库的运行时依赖。

本次合并接入远端 `c0299c3b7750c8a12ced00bf479753236a7dbc85` 的原始接口与验证契约。开发任务由私有 [GitHub Project #3](https://github.com/users/proffitteoy/projects/3) 管理，依据 ARCHITECTURE、RESULT_MODEL、SOLVER_CONTRACT 拆为单尺度算子、过滤算子族、求解器与认证。

代数系数为 F2，几何权重为正实代价；高维权重可取有明确来源的实际面积或体积。普通投影谱只有 0、1，额外几何来自带权作用。研究定理不等于本仓库可运行实现；软件许可证尚未选择，发布或再分发前需明确授权。


## 开始使用

先读 [项目约定](AGENTS.md) 和 [文档索引](docs/README.md)。reference 使用 Python 3.10+ 标准库与 uv 0.11.5：显式 F2 代数与 Fraction 有理数便于独立审查。S4-02 可选 Rust 原型使用 Rust 1.98.1、PyO3 0.29.3、maturin 1.15.0，依赖锁定在 native/Cargo.lock；安装与支持域见下文。reference 运行时没有第三方依赖，开发依赖由 uv.lock 锁定；PowerShell 7 用于文档检查。开发快照版本 0.0.2.dev0 不是发行。

在仓库根目录运行：

```powershell
pwsh -NoProfile -File ./scripts/check_docs.ps1
git diff --check
```


reference 安装与检查（仓库根目录）：

```powershell
uv sync --locked --python 3.10
uv run --locked python -m unittest discover -s tests -v
uv run --locked python examples/single_scale.py
uv run --locked python examples/filtration.py
uv run --locked ruff check .
uv run --locked ruff format --check .
uv build --no-build-isolation
```

CI 执行相同入口，并在隔离环境安装 wheel、运行文档检查。包导入测试只证明工具链可用，不替代后续数学验收。

S4-01新增[reference R0入口与复跑协议](docs/BENCHMARKS.md)，固定已合并main的计算源码，
分开冷进程计时、互斥分段、操作系统绝对峰值RSS与profiling。
这是native开发前的有限基线；Rust后端与S5正式GUDHI/性能验收仍按issue逐项推进。

第一条检查必需文档、UTF-8、冲突标记和本地 Markdown 文件链接，涵盖尚未跟踪的文档；失败时退出码非零。第二条检查已有跟踪文件改动的空白错误。详细范围和数学实现的验收门槛见 [验证说明](docs/VALIDATION.md)。

| 入口 | 当前状态 |
| --- | --- |
| 文档检查 | `scripts/check_docs.ps1`，可运行 |
| reference 语言与依赖 | Python 3.10+、uv 0.11.5；运行时标准库，开发依赖锁定在 uv.lock |
| 导入、构建、测试 | uv 安装；Hatchling 打包；129 项单尺度/过滤数学、solver 边界与身份测试 |
| 静态检查与格式 | Ruff；未配置独立 typecheck |
| 配置、迁移、种子数据、部署 | 当前没有对应需求或脚本 |
| CI、发布、LICENSE | Reference checks（Python 3.10/3.12）；未发布，许可证待选 |


## 仓库入口

| 路径 | 职责 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 项目操作规则、数学红线、命令与 skills 使用范围 |
| [HOMOLOGY_OPERATOR_ROADMAP.md](HOMOLOGY_OPERATOR_ROADMAP.md) | Phase 0–7 的开发目标和退出条件 |
| [docs/](docs/README.md) | 架构、接口、结果、solver、验证契约及冷启动入口 |
| [S4/S5 项目计划](docs/S4_S5_PROJECT.md) | 9 个性能工作包、6 个 GUDHI/测量工作包、依赖、验收与原始研究材料 |
| [docs/development/](docs/development/) | 通用架构模板、约束、代码组织与审计参考材料 |
| [scripts/check_docs.ps1](scripts/check_docs.ps1) | 文档一致性检查工具 |

[源码](src/homology_operator/) 已实现 F2 代数、ChainWindow、FeasibleSolver、独立 validator、HomologyOperator、OperatorFamily 和完整结果身份；[数学测试](tests/)、[单尺度示例](examples/single_scale.py) 与 [过滤示例](examples/filtration.py) 可运行。迁移来源见 [FIXTURES](docs/FIXTURES.md)，实际证据及源码/输入 hash 见 [Phase 1](docs/PHASE1_REPORT.md) 和 [Phase 2 验收报告](docs/PHASE2_REPORT.md)。

`selected_mass` 表示当前投影选定代表的质量，不能声称是最短代表。可行投影、精确拓扑、全局最优伸长、稳定性和性能分别需要相应证据，见 [solver 契约](docs/SOLVER_CONTRACT.md) 和 [开发路线](HOMOLOGY_OPERATOR_ROADMAP.md)。


## 精确 F2 reference 代数

### 可选 Rust 纵向原型（S4-02）

reference 的安装保持独立。额外构建可选原型（Windows x64/MSVC 或 Linux x64，CI 分别验证 Python 3.10/3.12）：

```powershell
uv sync --locked --python 3.10
$pythonPath = uv run --locked python -c "import sys; print(sys.executable)"
$env:RUSTUP_TOOLCHAIN = '1.98.1'
uv tool run --from maturin==1.15.0 maturin build --manifest-path native/Cargo.toml --release --locked --interpreter $pythonPath --out .task-artifacts/native-wheels
$wheel = Get-ChildItem .task-artifacts/native-wheels/*.whl
uv pip install --python $pythonPath $wheel.FullName
$env:HOMOLOGY_NATIVE_REQUIRED = '1'
uv run --locked --no-sync python -m unittest discover -s tests -v
cargo +1.98.1 fmt --manifest-path native/Cargo.toml --check
cargo +1.98.1 clippy --manifest-path native/Cargo.toml --locked --all-targets -- -D warnings
```

`native/rust-toolchain.toml` 固定编译器；在 native 目录运行 Cargo 可省略版本选择。Windows 还需要 MSVC C++ 工具链。`--no-sync` 保留另行安装的原型 wheel；重新 `uv sync` 后需要再次安装该 wheel。

```python
from homology_operator.native import NativeFeasibleSolver, apply_batch, geometry_batch

solution = solve_projection(ProjectionProblem(window), NativeFeasibleSolver())
op = HomologyOperator(window, solution)
actions = apply_batch(op, chains)       # 所有链的 P/L；一次绑定调用
geometry = geometry_batch(op, cycles, pairs=[(0, 1)])
record = OperatorResult.from_json(op.to_result().to_json())
```

safe Rust、单线程、每行一个 u64，三个链空间暂限至多64维；超出范围或缺少扩展明确返回 Unavailable。只提供 StableBasisOrder/Feasible 构造，P/G/U 与 reference 完整相同，仍通过独立 Python 广义逆和同调保持验证。现有标量入口使用显式 Matrix，拓扑、stretch、身份和恢复沿用 reference。批量 P/L 与支撑在 Rust 中计算；质量、距离及支撑交并暂由 Python 对同一 Pz 计算，任意精确有理数和浮点 fsum 政策不变，成本后备可见。批查询返回六身份的 QueryResult，默认不改变原算子的查询历史；需要保存时可在 `OperatorResult.query_results` 中显式加入该记录。

资源 states 沿用 feasible 的 checkpoint 单位（成功为5+m+n），matrix_entry_limit 是保守逻辑条目上限，wall_time 在阶段间检查，独立 projection validator/恢复成本在构造预算外。没有抢占、RSS硬上限或优化认证。更大尺寸分解、紧凑action、原生几何和全面集成由后续工作包实现。[最小完整成本协议](docs/BENCHMARKS.md) 保留有限采样与未获收益结果。

`from homology_operator import Matrix` 提供带显式形状的不可变矩阵；`from_rows([], ncols=n)` 保留 0×n，`zero(m,0)` 保留 m×0。外部坐标必须为整数 0/1（bool、float、取模输入均拒绝），消元不交换原列。支持 F2 加乘、`apply`、`rref`、`rank`、`kernel_basis`、`image_basis` 与 `solve`；不可解返回 None，空解是 tuple。自由变量置零，pivot 从左到右，结果可复现。

这是显式行存储的小规模 correctness reference，消元为多项式稠密运算，核/像枚举只在独立测试使用；不提供高性能保证。测试穷举所有至多 3×3 的 F2 矩阵，以独立向量枚举核对核、像、秩和可解性。
`ChainWindow(k,A,D,basis_previous,basis_current,basis_next,weights,...)` 在输入边界验证 AD=0、矩阵与三个带序基的形状、唯一非空基标识、有限严格正权；不合法抛 `InvalidInput`。它保留原坐标，支持空链空间及 H0 的 0×n 矩阵。`ExactRational` 只接受 int/Fraction，`ExactInteger` 只接受整数，`FloatingPoint` 显式采用浮点；权重语义和单位必须由调用者给出。`to_dict/from_dict` 保存显式形状及权重类型并重新校验输入。

## 身份、状态与序列化

### 同 P 的紧凑因子与 HC（S4-04）

`from homology_operator.native import NativeFactorizedSolver` 后，通过 `solve_projection(ProjectionProblem(window, matrix_free_output=True, solver_options={"representation": "Factorized"}), NativeFactorizedSolver())` 获取 Feasible 解。`"HC"` 显式选择同一个P的另一表示。支持多字输入，仍受原逻辑matrix_entry/state/wall预算限制；不支持的认证/选项/缺失扩展明确返回Unavailable。现有五个reference solver和64维原型入口保持不变。

Factorized 的 `CompactAction` 保存A/D、广义逆的非零行及原pivot索引，通过 `Rx=x+GAx`、`Px=Rx+DU(Rx)` 作用，G/U/P/L不展开。Rust先复用stable packed分解，再继续消元整个 `[M|I]` 的右半部分，保持reference的非循环延拓。HC先流式读取该P的坐标生成元，构造H的规范像基，再逐列求唯一C坐标，保存 `P=HC`；不先构造n×n P。β接近n时HC真实输出仍可能有平方大小，初始消元行变换也有平方workspace，本项不宣称所有中间量都线性。

两种表示都保存不可变的版本1因子内容；同P跨表示projection_id不同，各自恢复身份稳定，不能混用查询。Scalar P/L、拓扑、几何和JSON恢复在没有Rust时仍能消费该内容；批量P/L通过一个native调用，精确质量/距离后备政策保持。身份与证书只散列因子，不隐藏生成dense P；读取必要的核基/transport仍按实际输出大小分配。

独立Python verifier检查完整生成元的P²=P/L²=L/AP=0、PD=0与循环基 `Z+PZ∈im(D)`，D的像分解只做一次，不使用solver提供的分解或true标签。Factorized另查AGA/DUD及A/D与窗口一致，HC另查AH=0/CD=0/CH=I。算子构造、快照与外部恢复均重验；没有验证去重或未经认证最优标签。拓扑的规范核基由幂等式 `ker(L)=im(P)` 流式生成，并用从右向左的规范基消元匹配reference的自由坐标顺序，说明见[结果模型](docs/RESULT_MODEL.md)。

Factorized成功checkpoint数仍为5+m+n，HC额外2n个生成元构造checkpoint；wall在阶段间检查，validator/恢复在构造预算外，不是硬抢占/RSS上限。完整表示/β比率/时间与RSS比较见[测量协议](docs/BENCHMARKS.md)，不自动以有限测量选择表示。


