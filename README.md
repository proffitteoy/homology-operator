# homology-operator

Boundary-native F2 homology operators with joint persistence and geometric outputs.

从有限带基链窗口 `C_{k+1} --D--> C_k --A--> C_{k-1}` 及正坐标权重出发，构造同调投影 `P` 与算子 `L=I+P`。拓扑、代表、距离、支撑与伸长来自同一个投影身份；过滤上的 persistence 由算子族的传输读取。


## 当前状态

2026-10-01 按 [冷启动计划](docs/冷启动.md) 完成初始化。2026-10-02 Phase 1 的 PR #30–#41 和 Phase 2 的 PR #42–#48 已全部合入 main；Phase 2 main `f83d4c6` 的81项测试及 Python 3.10/3.12 CI通过。Phase 3 统一认证、完整搜索、贪心、rank-2、限定循环族、对照协议、算术/资源边界与一般搜索no-go已由 #49–#56 合入 main `6ab2232`，该main CI通过。本分支完成跨solver联合验收与阶段汇总，129项本地数学测试、两个示例、隔离wheel、静态/文档检查通过，证据见 [Phase 3报告](docs/PHASE3_REPORT.md)。#57/#58仍待用户审核合并；这些准确head全部进入main并通过main数学测试/CI后才进入Phase 4。

Phase 3的[solver对照协议](docs/BENCHMARKS.md)保存324条基线和144条局部搜索支持、失败、中断与完整成本记录，认证等级分别报告；源码提交、输入与结果hash可核对。联合验收覆盖73次冻结窗口支持运行、44个过滤配置和五solver混合表示族。高性能、采样稳定性、应用收益、许可证与发行仍待后续阶段。

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
uv run --locked python examples/filtration.py
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
| [docs/development/](docs/development/) | 通用架构模板、约束、代码组织与审计参考材料 |
| [scripts/check_docs.ps1](scripts/check_docs.ps1) | 文档一致性检查工具 |

[源码](src/homology_operator/) 已实现 F2 代数、ChainWindow、FeasibleSolver、独立 validator、HomologyOperator、OperatorFamily 和完整结果身份；[数学测试](tests/)、[单尺度示例](examples/single_scale.py) 与 [过滤示例](examples/filtration.py) 可运行。迁移来源见 [FIXTURES](docs/FIXTURES.md)，实际证据及源码/输入 hash 见 [Phase 1](docs/PHASE1_REPORT.md) 和 [Phase 2 验收报告](docs/PHASE2_REPORT.md)。

`selected_mass` 表示当前投影选定代表的质量，不能声称是最短代表。可行投影、精确拓扑、全局最优伸长、稳定性和性能分别需要相应证据，见 [solver 契约](docs/SOLVER_CONTRACT.md) 和 [开发路线](HOMOLOGY_OPERATOR_ROADMAP.md)。


## 精确 F2 reference 代数

`from homology_operator import Matrix` 提供带显式形状的不可变矩阵；`from_rows([], ncols=n)` 保留 0×n，`zero(m,0)` 保留 m×0。外部坐标必须为整数 0/1（bool、float、取模输入均拒绝），消元不交换原列。支持 F2 加乘、`apply`、`rref`、`rank`、`kernel_basis`、`image_basis` 与 `solve`；不可解返回 None，空解是 tuple。自由变量置零，pivot 从左到右，结果可复现。

这是显式行存储的小规模 correctness reference，消元为多项式稠密运算，核/像枚举只在独立测试使用；不提供高性能保证。测试穷举所有至多 3×3 的 F2 矩阵，以独立向量枚举核对核、像、秩和可解性。
`ChainWindow(k,A,D,basis_previous,basis_current,basis_next,weights,...)` 在输入边界验证 AD=0、矩阵与三个带序基的形状、唯一非空基标识、有限严格正权；不合法抛 `InvalidInput`。它保留原坐标，支持空链空间及 H0 的 0×n 矩阵。`ExactRational` 只接受 int/Fraction，`ExactInteger` 只接受整数，`FloatingPoint` 显式采用浮点；权重语义和单位必须由调用者给出。`to_dict/from_dict` 保存显式形状及权重类型并重新校验输入。

## 身份、状态与序列化

`QueryResult` 区分 Computed 的合法 0、NotComputed、Unavailable、ResourceExhausted、EmptyDomain（允许约定值 0）和 NoClass，保留 exact 与六身份。`OperatorResult` 保存 schema_version=1、输入/基/权重/投影/operator/solver_run 身份、solver 状态与认证、bounds、provenance；JSON round-trip 保留 Fraction 并复核输入和内容 hash，拒绝混用其他算子查询。所有记录的 P 均重新经过独立 projection validator；认证还要独立重放支持的证书，不能凭标签或 true 标志接受最优性。

内容身份使用规范 UTF-8 JSON SHA256，projection_id 与 operator_id 不包含每次独立 solver_run UUID。安全缓存包含输入、基、权重、投影、solver 配置、并列策略与 backend semantics，独立 run 仍保存在来源中；同一记录内的查询必须完全匹配六身份。

## 可行投影求解

`FeasibleSolver().solve(ProjectionProblem(window))` 用确定性广义逆构造 G/U，并精确复核 AGA=A、DUD=D，形成 P=(I+DU)(I+GA)。返回 FeasibleOnly/Feasible、独立 run UUID、稳定基顺序、实际资源计数及尚未计算的 objective。相同输入的 P 与内容身份可复现；这不证明最小伸长。

`ResourceLimits` 限制参考构造的 checkpoint/state 数、wall time 和保守矩阵条目数。输入规模先检查，时间在稠密代数步骤之间检查；它不是单步强制抢占或峰值 RSS 上限。不支持的 objective/认证/并列策略返回 Unavailable，非法问题返回 InvalidProblem，超限返回 ResourceExhausted 且不伪造投影。进入算子前仍需独立 validator。

`solve_projection(problem, backend="FeasibleSolver")` 在运行前核对 `capabilities()` 的算术、结构、次数/Betti范围、认证、matrix-free、确定性、并列与资源能力，未知后端或不支持的请求返回 Unavailable；也可传入声明相同接口的 solver 对象。所有返回 action 经 `validate_solution`，构造算子和 JSON恢复时再次验证。当前 FeasibleSolver 只宣称 Feasible，不会隐藏调用其他优化器。

`ProjectionSolution` 保存上下界、绝对/相对 gap、不可变配置及 `solver_config_id`，独立 run 不改变配置身份。合法的中断解可保持 ResourceExhausted 与 CertifiedInterval，算子仍为 Ready。`CycleBounds` 证书在精确有理/整数权上独立枚举全部非零循环，证明当前 objective 和上界，并支持通用下界0/1；`ExhaustiveSearch` 另以完整枚举证明最优。只有经过验证的等界可标 ExactOptimal；未知最优性证明仍不支持。Heuristic 候选必须独立证明投影合法才能构造算子。浮点不提供认证 bounds。证书重放成本独立于 solver 构造预算记录，不是高性能或抢占式资源保证。

`solve_projection(ProjectionProblem(window, requested_certificate_level="ExactOptimal"), "ExhaustiveExactSolver")` 固定循环回缩 R，枚举 `2^(rank(D) * beta)` 个循环上的边界回缩，并逐个计算当前 Γ；非循环延拓不被重复当作同调优化候选。仅支持精确有理/整数权，并列按原坐标投影列的 packed 整数字典序。独立 verifier 用商空间基的全部提升重放完整搜索，核对 objective、极值循环 witness、候选数、最优投影及并列选择。证书重放限制为候选数乘非零循环数至多100000（空循环按1计）；超限或求解中断保留已验证投影和已完成 objective 的上界，搜索完成前下界只跟踪0，不宣称 ExactOptimal。冻结的22个精确 fixture 与固定上游最优值一致，1个浮点 fixture 明确 Unavailable；K4 stage 4 得到9/8，可行构造的4/3不再被当作最优值。
`solve_projection(ProjectionProblem(window, requested_certificate_level="CertifiedInterval"), "GreedyCertifiedSolver")` 在精确正权下按质量、原坐标 packed 整数依次选择模边界独立的循环，构造最小总质量同调基的截面。独立 `GreedyBasis` 重放每步最小选择、并列和完整 action；固定理论 T4 的 Rossman 贪心回缩加权版本给出 Γ≤beta。返回实际 Γ、全局下界1（零同调为0）和理论假设，只有等界时标 ExactOptimal。K4 stage 4 的贪心4/3大于穷举最优9/8，报告 CertifiedInterval。仅支持 StableBasisOrder 与有限循环枚举；不支持浮点认证或请求通用 ExactOptimal。中断保留可行种子及已完成的 bounds，查询后的单尺度和族快照保留历史。详细支持域与来源见 [solver 契约](docs/SOLVER_CONTRACT.md)。

`solve_projection(ProjectionProblem(window, requested_certificate_level="ExactOptimal"), "Rank2ExactSolver")` 仅支持精确正权且 β=2。一般链窗口枚举两个生成元的边界修正，用 T5 的三色 Pareto 消去减少支撑，以三个类的精确最短质量计算 objective；独立 verifier 仍用全部循环与完整截面搜索核对最优性。`GraphCycle` 额外验证 k=1 与图关联矩阵。`ThreeTerminalCut` 要求 solver_options 中明确给出 `dual_vertex_count`、按原链坐标排序的 `dual_edges` 和三个有序 `terminals`，验证 ker(A)=对偶割空间、im(D)=内部顶点割空间后，按 T-A3 搜索三标签划分。此代数证书不声称识别平面嵌入；无几何假设的平面/欧氏环面请求明确不支持。支持域、证书、确定性及有限资源限制见 [solver 契约](docs/SOLVER_CONTRACT.md)。

`StructuredFamilySolver` 仅识别固定 T-B1 的循环族：n=2^m−1、m=2/3/4、A=0、im(D)=ker(P_m)，且所有权重相同且精确。P_m为移位1、2、…、2^(m−1)的异或；理论来源的循环码、迹和Vandermonde论证保留经典编码论归属。`matrix_free_output=True` 返回版本化 CyclicAction handle，直接project/L/身份/序列化不物化完整P。独立生成集验证合法性，再以列质量与低重量核向量穷举认证 Γ*=m；不将研究定理标签当成验证标志。

```python
window = ChainWindow(1, Matrix.zero(0, 3),
                     Matrix.from_columns(((1, 1, 1),), nrows=3),
                     (), ("x", "y", "z"), ("b",), (1, 1, 1))
solution = solve_projection(ProjectionProblem(
    window, input_structure="CyclicTrace", matrix_free_output=True,
    requested_certificate_level="ExactOptimal"), "StructuredFamilySolver")
op = HomologyOperator(window, solution)
assert op.project((1, 0, 0)) == (0, 1, 1)
assert solution.objective.value == 2
```

输入A/D仍是显式矩阵，核基和transport输出可分配矩阵；matrix-free只描述P/L的存储与作用。结构化handle与显式矩阵采用不同表示身份，跨表示查询混用会被拒绝；同一handle往返身份稳定。未声明此结构、非等权、浮点或m≥5的请求明确不支持。

`validate_projection(window,P)` 与 solver 独立，验证 P²=P、L²=L、AP=0、PD=0，且在 ker(A) 的完整基上验证 z+Pz 属于 im(D)。Matrix使用显式代数，CyclicAction使用完整坐标生成集。失败抛带 `InternalValidationFailed` 状态与具体失败项的 `ValidationError`。非零同调上的零投影即便前三项成立也被拒绝；Ready 序列化记录重新执行该验证，输入证书布尔值不作为信任来源。

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

各PR只展示对应issue增量。前置合并后将后继PR转向main，保留原PR；全部Phase 1合并并在main验证后才开始Phase 2。本批 Phase 1 已获用户授权直接合并；后续阶段由用户审核合并，监测不会自动合并。

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
| #1 Phase 1 汇总 | [#41](https://github.com/proffitteoy/homology-operator/pull/41)，已合并 |

CI运行Python 3.10/3.12的实际测试、示例、Ruff、构建和隔离wheel导入；某个PR合并或检查通过不代表剩余PR已通过。数学源码与fixture内容身份见验收报告。

## 有限过滤与 Phase 2

`OperatorFamily(scales, windows, operators, weight_policy="Inherited")` 接受同次数的 ChainWindow 和已验证算子，按基标识生成三个次数的坐标包含。`Variable` 显式允许变权，单位/语义仍一致；重复尺度保留有序阶段，末端常量延拓。

`transport(i,j)` 的 QueryResult 保存 kernel 坐标作用、目标原链作用和 source/target 完整身份；`transport_rank` 与 `transport_certificate` 从同一作用读取。`barcode()` 只读 transport rank，半开阶段端点保留重数与 None 末端；失败保持缺失，合法零同调给 Computed 空表。

`track_class(x,i,j)` 接受源循环；质量、支撑、共享/总支撑从目标 P 读取。`endpoint_mass_bound` 只使用终点当前 stretch、源选定质量和显式变权因子，浮点不称认证。`to_result()` 快照保存完整阶段/传输/rank/barcode/tracking；`OperatorFamilyResult.from_json` 重验内容，`to_family()` 恢复原 P。当前是稠密有限 reference，无族级抢占预算。

| Issue | 增量 PR |
| --- | --- |
| #14 过滤输入与阶段身份 | [#42](https://github.com/proffitteoy/homology-operator/pull/42) |
| #15 transport/composition/rank | [#43](https://github.com/proffitteoy/homology-operator/pull/43) |
| #16 rank barcode 与末端 | [#44](https://github.com/proffitteoy/homology-operator/pull/44) |
| #17 跨尺度几何与终点界 | [#45](https://github.com/proffitteoy/homology-operator/pull/45) |
| #27 族身份与序列化 | [#46](https://github.com/proffitteoy/homology-operator/pull/46) |
| #18 独立联合验收 | [#47](https://github.com/proffitteoy/homology-operator/pull/47) |
| #2 Phase 2 汇总 | [#48](https://github.com/proffitteoy/homology-operator/pull/48)，已合并 |

后继 PR 依赖前置，前置合并后转向 main；监测根据实际 main 的代码与 CI 推进，后续阶段 PR 由用户合并。

## Phase 3 PR 与合并门槛

| Issue | 增量 PR与当前状态 |
| --- | --- |
| #19 统一能力/认证 | [#49](https://github.com/proffitteoy/homology-operator/pull/49)，已合并 |
| #20 完整搜索 | [#50](https://github.com/proffitteoy/homology-operator/pull/50)，已合并 |
| #21 贪心认证 | [#51](https://github.com/proffitteoy/homology-operator/pull/51)，已合并 |
| #22 rank-2结构 | [#52](https://github.com/proffitteoy/homology-operator/pull/52)，已合并 |
| #23 循环结构族 | [#53](https://github.com/proffitteoy/homology-operator/pull/53)，已合并 |
| #25 同问题对照 | [#54](https://github.com/proffitteoy/homology-operator/pull/54)，已合并 |
| #28 算术/资源/身份 | [#55](https://github.com/proffitteoy/homology-operator/pull/55)，已合并 |
| #24 一般搜索准入 | [#56](https://github.com/proffitteoy/homology-operator/pull/56)，no-go实验，已合并 |
| #29 跨solver联合验收 | [#57](https://github.com/proffitteoy/homology-operator/pull/57)，待合并 |
| #3 Phase 3汇总 | [#58](https://github.com/proffitteoy/homology-operator/pull/58)，最后合并 |

认证支持域和固定证据见报告与solver契约。Phase 3没有自动合并授权；前置合并后原后继PR转向main并核对准确head，不替换PR或强推。监测是否启用以Codex自动化实际状态为准，不能把已提交PR或本地测试通过写成阶段已合并。
