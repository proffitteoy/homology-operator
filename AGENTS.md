# homology-operator 项目约定

默认使用中文回答。修改前阅读 README、docs 与相关代码，沿用现有文件和类型；
修改后检查文档、注释、测试和示例。做最小可验证修改，不覆盖用户已有工作。

## 产品范围

仓库保留 Python 公共接口、Rust 计算后端、产品回归测试、示例和双语文档。
研究原型、阶段计划、历史实验原值/报告与一次性测量工具不进入当前产品目录。
`src/homology_operator/` 和 `native/src/` 都是维护中的产品代码。
reference 运行时仅依赖 Python 3.10+ 标准库；Rust 扩展单独构建，支持域见 docs/INTERFACE.md。

## 数学与工程红线

- 输入为固定次数的带基链窗口 `C_{k+1} --D--> C_k --A--> C_{k-1}`，在 F2 上验证维数、`AD=0` 与正权重。
- 同一个 `HomologyOperator` 的拓扑、代表、距离、支撑和 stretch 必须来自同一个 `P`，保留 `input_id`、`basis_id`、`weight_id`、`projection_id`、`operator_id` 和 `solver_run_id`。
- 任何 solver 输出进入算子前，独立验证 `P²=P`、`AP=0`、`PD=0` 以及循环同调保持。前三项不能替代最后一项；零投影也可能满足前三项。
- `selected_mass(z)=m_w(Pz)` 不能被命名或序列化为真实最短类质量。合法投影、当前 objective 的精确计算、全局最优认证分别报告。
- F2 代数精确不代表浮点权重下的 objective 精确。`ExactOptimal` 必须有最优性证书；资源耗尽、不可用、未计算、空定义域与合法零值分别表达。
- 同调类查询默认只接受循环；原始 `project`、`apply_operator` 作用于全部链。不得静默把非循环解释成同调类。
- Persistence 从 `OperatorFamily` 的 `T_ij=P_j J_ij|ker(L_i)` 和 rank invariant 读取。独立 PH reduction 只允许作为 `tests/oracle/` 或性能对照，不能填充主结果。
- 理论来源固定在文档列出的研究提交；研究仓库的代码、依赖和验证成绩不能当作本仓库已有能力。迁移 fixture 必须记录来源和 hash。


## 文档与验证

- README 与 docs/index.md：安装、能力、用法和站点入口。
- docs/INTERFACE.md：实际 API、支持域与 native 安装。
- docs/ARCHITECTURE.md、docs/SOLVER_CONTRACT.md：数学定义、模块边界、算法与认证。
- docs/RESULT_MODEL.md：身份、状态、几何语义、序列化与恢复。
- docs/FIXTURES.md：产品测试输入与来源。
- docs/VALIDATION.md：reference/native/oracle、打包、文档与 CI 的真实命令。

普通文档改动运行：

```powershell
pwsh -NoProfile -File ./scripts/check_docs.ps1
git diff --check
```

数学、投影、solver、transport、身份或恢复改动补独立不变量与失败输入测试。
Rust 改动重建扩展并强制 native 差分；未安装扩展的跳过不能当作 native 通过。
需要保留的产品兼容性样本与 oracle 位于 tests/fixtures 和 tests/oracle。
临时构建、测量和运行日志写入忽略的 .task-artifacts，不提交到产品目录。
最终报告实际修改、验证、跳过项和剩余限制，区分本地与远端 CI。
具体数学契约优先于通用 skills；明确的用户要求优先。
