# homology-operator 项目约定

默认使用中文回答。修改前先阅读相关文档，修改后同步检查文档、注释、测试和示例。优先最小可验证修改，沿用已有文件与类型，不为未来扩展提前抽象。

## 项目事实与入口

- 本仓库是边界数据原生的 F2 同调算子库，目前处于契约准备阶段；尚无数学实现、包管理器、运行环境配置或数学测试。
- 当前可执行工具只有文档检查脚本，要求 PowerShell 7；不据此锁定 reference backend 或高性能核心的语言。
- 开始任务先读 [README](README.md)、[文档索引](docs/README.md) 和相关契约。路线图中的目录、对象和版本号是开发目标，不能作为已实现的证据。
- 明确的用户要求优先；仓库的数学契约优先于通用模板和 skills。若以后出现更具体的 `AGENT.md` 或目录级 `AGENTS.md`，还需读取其适用规则。

## 数学与工程红线

- 输入为固定次数的带基链窗口 `C_{k+1} --D--> C_k --A--> C_{k-1}`，在 F2 上验证维数、`AD=0` 与正权重。
- 同一个 `HomologyOperator` 的拓扑、代表、距离、支撑和 stretch 必须来自同一个 `P`，保留 `input_id`、`basis_id`、`weight_id`、`projection_id`、`operator_id` 和 `solver_run_id`。
- 任何 solver 输出进入算子前，独立验证 `P²=P`、`AP=0`、`PD=0` 以及循环同调保持。前三项不能替代最后一项；零投影也可能满足前三项。
- `selected_mass(z)=m_w(Pz)` 不能被命名或序列化为真实最短类质量。合法投影、当前 objective 的精确计算、全局最优认证分别报告。
- F2 代数精确不代表浮点权重下的 objective 精确。`ExactOptimal` 必须有最优性证书；资源耗尽、不可用、未计算、空定义域与合法零值分别表达。
- 同调类查询默认只接受循环；原始 `project`、`apply_operator` 作用于全部链。不得静默把非循环解释成同调类。
- Persistence 从 `OperatorFamily` 的 `T_ij=P_j J_ij|ker(L_i)` 和 rank invariant 读取。独立 PH reduction 只允许作为 `tests/oracle/` 或性能对照，不能填充主结果。
- 理论来源固定在文档列出的研究提交；研究仓库的代码、依赖和验证成绩不能当作本仓库已有能力。迁移 fixture 必须记录来源和 hash。

## 目录与命令

- `docs/ARCHITECTURE.md`：对象职责和计算边界。
- `docs/INTERFACE.md`：输入域与逻辑查询接口。
- `docs/RESULT_MODEL.md`：身份、状态、几何语义与序列化。
- `docs/SOLVER_CONTRACT.md`：投影合法性、最优性、资源和并列策略。
- `docs/VALIDATION.md`：当前文档验证与后续数学验收。
- `docs/development/`：通用开发参考材料，与项目数学契约分开维护。
- `scripts/check_docs.ps1`：只读检查根目录和 `docs/` 下的 Markdown 及本地文件链接。
- 首次实现时按路线图建立实际需要的数学模块和测试；不要预建空的 `src/`、`tests/`、后端、数据库、部署或环境变量目录。

在仓库根目录运行：

```powershell
pwsh -NoProfile -File ./scripts/check_docs.ps1
git diff --check
```

文档检查涵盖未跟踪的 Markdown；`git diff --check` 只补充检查 Git 中已有文件的改动。当前没有启动、构建、数学测试、lint、format、typecheck 或发布命令；新增实现时必须同时提供真实命令和依赖说明。

## 变更与验证

- 修改数学定义、输入校验、投影构造或 solver 时，补独立代数不变量与失败输入测试；修改 transport 时补 composition、rank 和 oracle 对拍；修改身份或序列化时补 round-trip 与混用拒绝测试。具体门槛见验证文档。
- 普通文档变更运行文档检查；不要添加复述实现的测试。性能修改绑定源码提交、fixture、认证等级、运行环境和预算，不把不同认证等级的耗时直接比较。
- 不覆盖用户已有修改；不因冷启动更换框架、大规模重构或复制整个研究仓库。
- 最终汇报修改内容、实际验证和剩余风险，区分文档验证、数学测试、本地运行和远端 CI。

## 通用模板和 skills

- 普通代码、接口、测试任务默认直接依据本仓库契约，不要求专项 skill。
- 安全或输入边界审计按需参考 [代码审计](docs/development/代码审计.md)，将其来源校验原则应用到链输入、solver 输出与序列化数据。
- 调整目录边界时按需参考 [代码组织](docs/development/代码组织.md)，实际数学职责优先于模板。
- 数学证明、论文、PDF、LaTeX 等专项工作按任务使用相关 skill，并保留理论假设与证据层级。
- [通用架构模板](docs/development/通用项目架构模板.md) 与 [强前置条件约束](docs/development/强前置条件约束.md) 是参考材料，需按项目裁剪。Web、数据库、微服务、`datas`、`sizi.summarys` 和“只能胶水集成”等条款不适用于本算子库，不能据此阻止路线图要求的核心实现。
