# Homology Operator：验证说明

## 三阶段开发管理

阶段名称沿用远端 `main @ c0299c3b7750c8a12ced00bf479753236a7dbc85` 的 [原始三阶段文档](https://github.com/proffitteoy/homology-operator/blob/c0299c3b7750c8a12ced00bf479753236a7dbc85/docs/VALIDATION.md)，详细路线将每一阶段展开为多个数学与工程步骤。

| 原始阶段 | 详细路线对应 | 核心退出条件 |
| --- | --- | --- |
| S1：可复现参考实现 | Phase 0–2 与最小 feasible/stretch 能力 | 边界数据构造算子，完整 PH 与几何联合读取，H0–H3、过滤与独立 oracle 验证 |
| S2：同输出优化 | Phase 3–4 | solver 认证、reference/optimized 同输出、分项成本与 peak RSS 可复现 |
| S3：独立研究门槛 | Phase 5–7 | 网格/采样/几何恢复与应用分别建立证据，授权、包/API/schema、CI 和发行候选明确 |

私有 [GitHub Project #3](https://github.com/users/proffitteoy/projects/3) 管理三个阶段总任务与详细子任务。准备状态、优先级和原生 blocked-by 关系用于排定工作；创建 issue 不代表实现完成。研究任务允许保留条件限制或形成有证据的 no-go。

## 当前可执行验证

当前只有文档与只读检查工具，没有数学实现或数学测试成绩。需要 Git 与 PowerShell 7，在仓库根目录运行：

```powershell
pwsh -NoProfile -File ./scripts/check_docs.ps1
git diff --check
```

文档脚本也可从其他工作目录调用，仓库位置由脚本路径决定。它检查根目录与 `docs/` 下所有 Markdown（含未跟踪文件）：必需入口存在、严格 UTF-8 解码、无 Git 冲突标记、行内 Markdown 的本地文件链接存在且位于仓库内。失败时退出码 1，成功时打印文件数和本地链接数。

该轻量检查不解析完整 Markdown 语法，不检查链接的标题锚点、引用式链接或外网可达性；代码围栏中的示例不作为链接检查。`git diff --check` 补充检查跟踪文件的改动，不能覆盖未跟踪文件。检查通过不证明数学正确、最优性或运行时性能。当前没有 CI 执行记录。

## 首次数学实现的验证门槛

以下是后续验收要求，尚未执行。首次实现时同步记录依赖、真实测试命令与 fixture 来源，语言与测试框架由实现决定。主路径只消费链输入和合法 solver 解，独立 oracle 留在 `tests/oracle/`。

| 变更领域 | 最低验证 |
| --- | --- |
| F2 代数与 `ChainWindow` | 矩阵乘法、消元、核与像；`A`/`D` 维数、空链空间、非二元坐标、`AD≠0`、权重非正/非有限/长度错误及基顺序 |
| 投影构造与后验证 | `AGA=A`、`DUD=D`、`P²=P`、`L²=L`、`AP=0`、`PD=0`；在 `ker(A)` 的基上验证 `z+Pz∈im(D)` |
| 拓扑联合读取 | 小实例穷举循环，验证 `Pz=0⇔z∈im(D)`、`Pz=Py⇔z+y∈im(D)`、`betti=dim ker(L)`；拒绝非循环类查询 |
| 几何联合读取 | 按原坐标独立计算质量、距离、共享/并集支撑；距离非负、对称、三角不等式、同类当且仅当为 0；统一身份 |
| Solver 与 stretch | 可行与最优区分；objective 精确值与最优认证区分；bounds、并列策略、资源中断；空循环域遵循理论的 stretch=0 约定并保留空域信息，与非空循环域的 Betti 0 情形分别验证 |
| 身份与结果 | 权重/基顺序/投影变化导致相应身份变化；不同投影不可自动合并；序列化 round-trip 保留身份、状态、精确性和 provenance |
| Phase 2 过滤 | `T_ii=I`、composition、与诱导同调映射共轭；rank invariant 与独立 reduction 对拍；重复尺度和末端存活约定；几何追踪 |
| Phase 4 性能 | 同 fixture、同联合输出、同认证与预算对照；报告提交、输入 hash、环境、线程、构造/查询成本及 peak RSS |

后验证必须包含一个反例回归：在非零同调窗口提交零投影。它满足 `P²=P`、`AP=0`、`PD=0`，但不保持循环同调，必须拒绝。

## Fixture 记录契约

首次迁移时只建立真正使用的 `tests/fixtures/` 与 oracle 文件，不预建路线图中的全部空目录。每个 fixture 至少包含以下事实；具体存储格式在实现时确定。

| 字段 | 内容 |
| --- | --- |
| 身份 | 唯一 fixture 标识、来源仓库/提交/路径及输入内容 hash |
| 链输入 | 次数 `k`，`A`/`D` 显式形状与 F2 元素，三个空间的有序基 |
| 权重 | 正权重精确值或浮点表示、算术策略、语义、单位 |
| 预期 | 已知 Betti、独立同调/几何结果、已知可行投影（若有） |
| 认证 | 已知 optimum 或 bounds（若有），预期认证等级与证据来源 |
| 过滤（若有） | 阶段、包含映射、权重继承、预期 rank/barcode、末端约定 |

至少覆盖零同调、单洞、多洞、非平凡边界、H0–H3、空链空间、人工正权和有明确几何来源的权重。手工 fixture 标明推导；迁移研究 fixture 保留原证据，在隔离副本中执行会写文件的研究脚本，不把研究仓库验证冒充为本仓库验证。

## 阶段结论边界

当前冷启动完成项目规则、接口/验证文档与文档检查入口。Phase 0 的逻辑契约已经齐备；fixture corpus、运行时结果模型和具体语言 API 的落地尚待 reference 实现验证，公开版本号尚未冻结。

Phase 1 完成需有可运行的单尺度算子、完整联合读取和上述数学测试。Phase 2–7 依 [路线图](../HOMOLOGY_OPERATOR_ROADMAP.md) 分别验收，不能从文档检查或有限小实例测试推导通用效率、稳定性与应用价值。
