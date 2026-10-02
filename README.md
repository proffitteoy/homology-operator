# homology-operator

Boundary-native F2 homology operators with joint persistence and geometric outputs.

从有限带基链窗口 `C_{k+1} --D--> C_k --A--> C_{k-1}` 及正坐标权重出发，构造同调投影 `P` 与算子 `L=I+P`。拓扑、代表、距离、支撑与伸长来自同一个投影身份；过滤上的 persistence 由算子族的传输读取。

## 当前状态

2026-10-01 按 [冷启动计划](docs/冷启动.md) 完成项目规则、文档入口和验证工具初始化。现已建立 Phase 1 reference 工具链；数学算子、solver、filtration 和 fixture corpus 将按 issue 逐项实现，没有已发布版本。

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
| 导入、构建、测试 | uv 安装；Hatchling 打包；unittest，当前首先验证包导入 |
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

`src/homology_operator/` 与 `tests/` 已用于包导入验收；其余路线图目录按需求创建。首个实现按路线图推进：F2 代数与 `ChainWindow` → 合法投影和独立 validator → 同一算子的完整联合读取与小规模 fixture 验证。实现和运行环境建立后同步更新真实命令。

`selected_mass` 表示当前投影选定代表的质量，不能声称是最短代表。可行投影、精确拓扑、全局最优伸长、稳定性和性能分别需要相应证据，见 [solver 契约](docs/SOLVER_CONTRACT.md) 和 [开发路线](HOMOLOGY_OPERATOR_ROADMAP.md)。

## 精确 F2 reference 代数

`from homology_operator import Matrix` 提供带显式形状的不可变矩阵；`from_rows([], ncols=n)` 保留 0×n，`zero(m,0)` 保留 m×0。外部坐标必须为整数 0/1（bool、float、取模输入均拒绝），消元不交换原列。支持 F2 加乘、`apply`、`rref`、`rank`、`kernel_basis`、`image_basis` 与 `solve`；不可解返回 None，空解是 tuple。自由变量置零，pivot 从左到右，结果可复现。

这是显式行存储的小规模 correctness reference，消元为多项式稠密运算，核/像枚举只在独立测试使用；不提供高性能保证。测试穷举所有至多 3×3 的 F2 矩阵，以独立向量枚举核对核、像、秩和可解性。
`ChainWindow(k,A,D,basis_previous,basis_current,basis_next,weights,...)` 在输入边界验证 AD=0、矩阵与三个带序基的形状、唯一非空基标识、有限严格正权；不合法抛 `InvalidInput`。它保留原坐标，支持空链空间及 H0 的 0×n 矩阵。`ExactRational` 只接受 int/Fraction，`ExactInteger` 只接受整数，`FloatingPoint` 显式采用浮点；权重语义和单位必须由调用者给出。`to_dict/from_dict` 保存显式形状及权重类型并重新校验输入。
## 身份、状态与序列化

`QueryResult` 区分 Computed 的合法 0、NotComputed、Unavailable、ResourceExhausted、EmptyDomain（允许约定值 0）和 NoClass，保留 exact 与六身份。`OperatorResult` 保存 schema_version=1、输入/基/权重/投影/operator/solver_run 身份、solver 状态与认证、bounds、provenance；JSON round-trip 保留 Fraction 并复核输入和内容 hash，拒绝混用其他算子查询。Ready 结果还必须重新运行独立 projection validator；validator 尚未接入时明确拒绝。Phase 1 不提供最优性证书验证器，因此明确拒绝 ExactOptimal 标签。

内容身份使用规范 UTF-8 JSON SHA256，projection_id 与 operator_id 不包含每次独立 solver_run UUID。安全缓存包含输入、基、权重、投影、solver 配置、并列策略与 backend semantics，独立 run 仍保存在来源中；同一记录内的查询必须完全匹配六身份。
## 可行投影求解

`FeasibleSolver().solve(ProjectionProblem(window))` 用确定性广义逆构造 G/U，并精确复核 AGA=A、DUD=D，形成 P=(I+DU)(I+GA)。返回 FeasibleOnly/Feasible、独立 run UUID、稳定基顺序、实际资源计数及尚未计算的 objective。相同输入的 P 与内容身份可复现；这不证明最小伸长。

`ResourceLimits` 限制参考构造的 checkpoint/state 数、wall time 和保守矩阵条目数。输入规模先检查，时间在稠密代数步骤之间检查；它不是单步强制抢占或峰值 RSS 上限。不支持的 objective/认证/并列策略返回 Unavailable，非法问题返回 InvalidProblem，超限返回 ResourceExhausted 且不伪造投影。进入算子前仍需独立 validator。