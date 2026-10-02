# homology-operator

Boundary-native F2 homology operators with joint persistence and geometric outputs.

从有限带基链窗口 `C_{k+1} --D--> C_k --A--> C_{k-1}` 及正坐标权重出发，构造同调投影 `P` 与算子 `L=I+P`。拓扑、代表、距离、支撑与伸长来自同一个投影身份；过滤上的 persistence 由算子族的传输读取。


## 当前状态

2026-10-01 按 [冷启动计划](docs/冷启动.md) 完成项目规则、文档入口和验证工具初始化。2026-10-02 已实现 Phase 1 单尺度 reference，并通过本地 49 项测试；23 份 H0–H3/加权 fixture 有固定来源和独立 oracle。变更按 issue 提交 PR，全部合并进 main 后才推进 Phase 2。OperatorFamily/filtration、一般最优 solver 和高性能核心尚未实现，没有已发布版本。

初始化前本地 `HEAD` 与 `origin/main` 均为 `6ddce1b4e4d55c0aaff399c001e684d908026830`。理论来源固定为 [homology-operator-lab 的指定提交](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88)，研究代码及其依赖不构成本仓库的运行时依赖。

本次合并接入远端 `c0299c3b7750c8a12ced00bf479753236a7dbc85` 的原始接口与验证契约。开发任务由私有 [GitHub Project #3](https://github.com/users/proffitteoy/projects/3) 管理，依据 ARCHITECTURE、RESULT_MODEL、SOLVER_CONTRACT 拆为单尺度算子、过滤算子族、求解器与认证。

代数系数为 F2，几何权重为正实代价；高维权重可取有明确来源的实际面积或体积。普通投影谱只有 0、1，额外几何来自带权作用。研究定理不等于本仓库可运行实现；软件许可证尚未选择，发布或再分发前需明确授权。


## 开始使用

先读 [项目约定](AGENTS.md) 和 [文档索引](docs/README.md)。reference 使用 Python 3.10+ 标准库与 uv 0.11.5：显式 F2 代数与 Fraction 有理数便于独立审查，不锁定 Phase 4 高性能核心语言。运行时没有第三方依赖，开发依赖由 uv.lock 锁定；PowerShell 7 用于文档检查。开发快照版本 0.0.2.dev0 不是发行。

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
uv run --locked ruff check .
uv run --locked ruff format --check .
uv build --no-build-isolation
```

CI 执行相同入口，并在隔离环境安装 wheel、运行文档检查。包导入测试只证明工具链可用，不替代后续数学验收。

第一条检查必需文档、UTF-8、冲突标记和本地 Markdown 文件链接，涵盖尚未跟踪的文档；失败时退出码非零。第二条检查已有跟踪文件改动的空白错误。详细范围和数学实现的验收门槛见 [验证说明](docs/VALIDATION.md)。

| 入口 | 当前状态 |
| --- | --- |
| 文档检查 | `scripts/check_docs.ps1`，可运行 |
| reference 语言与依赖 | Python 3.10+、uv 0.11.5；运行时标准库，开发依赖锁定在 uv.lock |
| 导入、构建、测试 | uv 安装；Hatchling 打包；49 项单尺度数学/边界/身份测试 |
| 静态检查与格式 | Ruff；未配置独立 typecheck |
| 配置、迁移、种子数据、部署 | 当前没有对应需求或脚本 |
| CI、发布、LICENSE | Reference checks（Python 3.10/3.12）；未发布，许可证待选 |


## 仓库入口

| 路径 | 职责 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 项目操作规则、数学红线、命令与 skills 使用范围 |
| [HOMOLOGY_OPERATOR_ROADMAP.md](HOMOLOGY_OPERATOR_ROADMAP.md) | Phase 0–7 的开发目标和退出条件 |
| [docs/](docs/README.md) | 架构、接口、结果、solver、验证契约及冷启动入口 |
| [docs/development/](docs/development/) | 通用架构模板、约束、代码组织与审计参考材料 |
| [scripts/check_docs.ps1](scripts/check_docs.ps1) | 文档一致性检查工具 |

[源码](src/homology_operator/) 已实现 F2 代数、ChainWindow、FeasibleSolver、独立 validator、HomologyOperator 和结果身份；[数学测试](tests/) 与 [单尺度示例](examples/single_scale.py) 可运行。迁移来源见 [FIXTURES](docs/FIXTURES.md)，实际证据及源码/输入 hash 见 [Phase 1 验收报告](docs/PHASE1_REPORT.md)。其余路线图目录按实际需求创建。

`selected_mass` 表示当前投影选定代表的质量，不能声称是最短代表。可行投影、精确拓扑、全局最优伸长、稳定性和性能分别需要相应证据，见 [solver 契约](docs/SOLVER_CONTRACT.md) 和 [开发路线](HOMOLOGY_OPERATOR_ROADMAP.md)。


## 精确 F2 reference 代数

`from homology_operator import Matrix` 提供带显式形状的不可变矩阵；`from_rows([], ncols=n)` 保留 0×n，`zero(m,0)` 保留 m×0。外部坐标必须为整数 0/1（bool、float、取模输入均拒绝），消元不交换原列。支持 F2 加乘、`apply`、`rref`、`rank`、`kernel_basis`、`image_basis` 与 `solve`；不可解返回 None，空解是 tuple。自由变量置零，pivot 从左到右，结果可复现。

这是显式行存储的小规模 correctness reference，消元为多项式稠密运算，核/像枚举只在独立测试使用；不提供高性能保证。测试穷举所有至多 3×3 的 F2 矩阵，以独立向量枚举核对核、像、秩和可解性。
`ChainWindow(k,A,D,basis_previous,basis_current,basis_next,weights,...)` 在输入边界验证 AD=0、矩阵与三个带序基的形状、唯一非空基标识、有限严格正权；不合法抛 `InvalidInput`。它保留原坐标，支持空链空间及 H0 的 0×n 矩阵。`ExactRational` 只接受 int/Fraction，`ExactInteger` 只接受整数，`FloatingPoint` 显式采用浮点；权重语义和单位必须由调用者给出。`to_dict/from_dict` 保存显式形状及权重类型并重新校验输入。

## 身份、状态与序列化

`QueryResult` 区分 Computed 的合法 0、NotComputed、Unavailable、ResourceExhausted、EmptyDomain（允许约定值 0）和 NoClass，保留 exact 与六身份。`OperatorResult` 保存 schema_version=1、输入/基/权重/投影/operator/solver_run 身份、solver 状态与认证、bounds、provenance；JSON round-trip 保留 Fraction 并复核输入和内容 hash，拒绝混用其他算子查询。Ready 结果还必须重新运行独立 projection validator；独立 validator 已接入；当前结果记录只接受 Feasible solver 认证，stretch 查询可单独给当前投影的精确上界证据。Phase 1 不提供全局认证验证器，因此明确拒绝 ExactOptimal 等未经支持的 solver 认证标签。

内容身份使用规范 UTF-8 JSON SHA256，projection_id 与 operator_id 不包含每次独立 solver_run UUID。安全缓存包含输入、基、权重、投影、solver 配置、并列策略与 backend semantics，独立 run 仍保存在来源中；同一记录内的查询必须完全匹配六身份。

## 可行投影求解

`FeasibleSolver().solve(ProjectionProblem(window))` 用确定性广义逆构造 G/U，并精确复核 AGA=A、DUD=D，形成 P=(I+DU)(I+GA)。返回 FeasibleOnly/Feasible、独立 run UUID、稳定基顺序、实际资源计数及尚未计算的 objective。相同输入的 P 与内容身份可复现；这不证明最小伸长。

`ResourceLimits` 限制参考构造的 checkpoint/state 数、wall time 和保守矩阵条目数。输入规模先检查，时间在稠密代数步骤之间检查；它不是单步强制抢占或峰值 RSS 上限。不支持的 objective/认证/并列策略返回 Unavailable，非法问题返回 InvalidProblem，超限返回 ResourceExhausted 且不伪造投影。进入算子前仍需独立 validator。
`validate_projection(window,P)` 与 solver 独立，验证 P²=P、L²=L、AP=0、PD=0，且在 ker(A) 的完整基上验证 z+Pz 属于 im(D)。失败抛带 `InternalValidationFailed` 状态与具体失败项的 `ValidationError`。非零同调上的零投影即便前三项成立也被拒绝；Ready 序列化记录重新执行该验证，输入证书布尔值不作为信任来源。

## 同一算子的拓扑读取

`HomologyOperator(window,solution)` 在构造边界重新验证投影与六身份，仅接受可行解。`project/apply_operator` 对所有链执行 P/L 作用；`class_representative/same_class` 仅接受循环，非循环明确拒绝。`kernel_basis` 按需计算 ker(L)，`betti` 从其维数读取；空核基和未计算状态在 `to_result()` 中可区分。

`readout(name,*args)` 给原始数学返回值附上六身份与 exact 标记；`metadata/certificate/to_result` 保留同一 P、原基、权重、solver 和实际独立证书。JSON round-trip 会重新检验 P，篡改后的合法性声明不能绕过边界。repository_revision 默认 unknown；正式验收或实验须显式传入源码提交。

## 代表几何

同一对象提供 `selected_mass(z)=m_w(Pz)`、`class_distance(z,y)=m_w(P(z+y))` 以及原基索引上的 `support/shared_support/union_support`。循环域检查适用于全部几何类查询。精确权重求和保留 Fraction；浮点用 binary64 fsum，readout 标为 approximate 并记录舍入，不制造误差证书；非有限数值明确失败。

例如 A=0、D=(1,1)ᵀ、权重(10,1)时，当前确定性构造选择第一坐标代表，类质量为10，而同类第二坐标代表质量为1。selected_mass 不能用作 minimum_class_mass；后者在快照中仍为 NotComputed。独立坐标测试验证交并支撑、质量恒等式及距离非负、对称、零距离同类和三角不等式。

## 当前 stretch 与资源状态

`stretch(ResourceLimits(...))` 穷举非零循环，返回当前 Γ_w(P) 及见证；默认最多100000个状态、10秒、1000000个矩阵条目。有限有理/整数权给精确 Fraction objective 和全局 optimum 的合法上界，仍无最优性或 gap 认证。浮点 objective 标近似，不返回未经舍入认证的 optimum 上界。超限结果为 ResourceExhausted，无精确 value；已见有理比值仅是当前 objective 的下界，不能充当全局最优上界。

空循环空间按理论约定返回 EmptyDomain(value=0)；存在循环但 Betti=0 时返回 Computed(value=0)，两者与未查询区别。浮点溢出以 Unavailable/NumericalFailure 诊断报告。`minimum_class_mass(z)` 当前后端明确 Unavailable，未调用时快照为 NotComputed；不会填入选定质量。
## Phase 1 PR 与合并顺序

各PR只展示对应issue增量。前置合并后将后继PR转向main，保留原PR；全部Phase 1合并并在main验证后才开始Phase 2。用户负责审核与合并，监测不会自动合并。

| Issue | 增量 PR |
| --- | --- |
| #4 工具链 | [#30](https://github.com/proffitteoy/homology-operator/pull/30) |
| #5 F2 代数 | [#31](https://github.com/proffitteoy/homology-operator/pull/31) |
| #6 ChainWindow | [#32](https://github.com/proffitteoy/homology-operator/pull/32) |
| #7 身份与序列化 | [#33](https://github.com/proffitteoy/homology-operator/pull/33) |
| #8 可行 solver | [#34](https://github.com/proffitteoy/homology-operator/pull/34) |
| #9 独立 validator | [#35](https://github.com/proffitteoy/homology-operator/pull/35) |
| #10 拓扑 action | [#36](https://github.com/proffitteoy/homology-operator/pull/36) |
| #11 代表几何 | [#37](https://github.com/proffitteoy/homology-operator/pull/37) |
| #12 有限 stretch | [#38](https://github.com/proffitteoy/homology-operator/pull/38) |
| #13 sourced fixtures | [#39](https://github.com/proffitteoy/homology-operator/pull/39) |
| #26 独立联合验收 | [#40](https://github.com/proffitteoy/homology-operator/pull/40) |
| #1 Phase 1 汇总 | 本分支同步文档入口与阶段证据，最后合并 |

CI运行Python 3.10/3.12的实际测试、示例、Ruff、构建和隔离wheel导入；某个PR合并或检查通过不代表剩余PR已通过。数学源码与fixture内容身份见验收报告。