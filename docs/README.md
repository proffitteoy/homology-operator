# homology-operator 文档

## 使用库

| 需要做什么 | 阅读入口 |
| --- | --- |
| 安装并跑第一个例子 | [根 README](../README.md) |
| 构造输入、选择 solver、查询单尺度或过滤 | [Python API](INTERFACE.md) |
| 安装 Rust、复用 packed 分解、批量查询 | [API 的可选 Rust 扩展章节](INTERFACE.md#可选-rust-扩展) |
| 保存结果、判断缺失/精确性、避免身份混用 | [结果模型](RESULT_MODEL.md) |
| 相邻 barcode、历史区间基与过滤快照 | [S4-07 过滤读取](S4_FILTRATION.md) |
| 理解 P/L 和 transport 的来源 | [架构](ARCHITECTURE.md) |
| 判断 solver 支持域与最优证书 | [solver 契约](SOLVER_CONTRACT.md) |
| 贡献、测试、构建或复跑实验 | [验证说明](VALIDATION.md)、[性能协议](BENCHMARKS.md) |

## 实现状态（2026-10-03 核对）

已核验通过的 `main` CI 基线为 `7fa812d5e76ca80ac16316cb212d133c0639bfd7`。
该提交的 [Reference checks](https://github.com/proffitteoy/homology-operator/actions/runs/37111993987)
和 [Native prototype checks](https://github.com/proffitteoy/homology-operator/actions/runs/37111993984)
均已完成并通过。CI 结论仅绑定这个提交，不覆盖尚未合入该提交的开发工作。

| 范围 | 已有实现或证据 | 边界 |
| --- | --- | --- |
| Phase 1–3 reference | 单尺度、有限过滤、五种限定 solver、身份/证书/恢复；原 PR 已合并 | 129 项数学测试是 Phase 3 的历史验收数，见下方报告 |
| S4-01 / PR #77 | R0 完整成本基线、采样与 profiling | 有限基线，非 S4/S5 最终验收 |
| S4-02 / PR #78 | 可选 safe Rust 可行构造及批查询 | 原型三个链空间最多 64 维；真实窗口记录包含退化 |
| S4-03 / PR #79 | 多字 packed F2、`PreparedMatrix`、多 RHS 与复用消融 | 不解除单字宽 `NativeFeasibleSolver` 的限制；不代表全算子加速 |
| S4-04 / [PR #80](https://github.com/proffitteoy/homology-operator/pull/80) | `6c40b93` 提供 `CompactAction` / `NativeFactorizedSolver`、因子与 HC 表示、测试和测量记录 | 已合并；保留同 P 语义与有限测量，非 S4 总验收 |
| S4-06 / [PR #81](https://github.com/proffitteoy/homology-operator/pull/81) | 几何批查询、精确权重与 workspace | PR #81 原先只合入 `s4/64-factorized-action`；已由 [PR #85](https://github.com/proffitteoy/homology-operator/pull/85) 集成到 main e920de0 |
| S4-05 / [PR #84](https://github.com/proffitteoy/homology-operator/pull/84) | 四种限定 native solver、精确质量后备与独立证书重放；159项整合回归、700条有限性能样本 | 已合入 main `63138fc`；认证 solver 输出仍为 Matrix/CyclicAction，后端集成另验收 |
| S4-07 / [PR #82](https://github.com/proffitteoy/homology-operator/pull/82) | 相邻 transport barcode、历史区间基、受控缓存与 schema 2 共享过滤快照 | 已合入 main `f0c15265`；保留 schema 1 兼容和有限合成性能范围 |
| S4-08 / [PR #86](https://github.com/proffitteoy/homology-operator/pull/86) | 后端选择/可见后备、取消、旧格式与紧凑恢复、隔离 wheel CI | 已合并至上述 main；Windows/Linux强制native和隔离wheel CI通过，见 [VALIDATION](VALIDATION.md#s4-08-后端集成验收) |
| S4-09 / [验收报告](S4_REPORT.md) | 27配置、1880独立进程、同P/认证/联合输出、完整成本/RSS/消融与S5源码冻结 | 性能门槛通过；4组时间退化，保留可选后端；最终合并/main CI以 [S4 Epic](https://github.com/proffitteoy/homology-operator/issues/59)记录为据 |
| S5 | GUDHI 三方正确性与正式对照测量 | 本轮没有实施；S4数据不替代S5 |
| 公开发行 | 包名 `homology-operator`，开发快照 `0.0.2.dev0` | 当前 GitHub 仓库为 public，未选择 LICENSE，发行/API 兼容政策未冻结 |

上述main已包含S4-01–08；S4-09的生产被测源码也固定在同一7fa812d，
新增harness/数据/报告的源码身份另列，不冒充新main测量。旧分支与原始数据保留。
使用说明对应当前源码；整合前CI、各工作包历史证据与最终验收分别记录；S4性能门槛与最终合并/CI分开，S5仍独立验收。
测试总数以指定 checkout 的实际运行结果为准，历史报告中的计数不作为滚动状态。

## 开发计划与证据

- [项目约定](../AGENTS.md)：修改规则与数学红线。
- [路线图](../HOMOLOGY_OPERATOR_ROADMAP.md)：Phase 0–7 的目标和退出条件；目录/版本建议不是实现清单。
- [S4/S5 工作包](S4_S5_PROJECT.md)：性能和 GUDHI 验收的依赖与条件。
- [Fixture 来源](FIXTURES.md)：迁移窗口、几何权重来源与 hash。
- [性能协议](BENCHMARKS.md)：R0、S4-02/03 与历史 solver 对照，源码/输入/输出身份和失败记录。

## 历史报告与研究归档

以下文档保留验收时的事实，不用今天的状态回写原始记录：

| 报告 | 当时验收范围 |
| --- | --- |
| [Phase 1](PHASE1_REPORT.md) | 57 项单尺度测试与迁移证据 |
| [Phase 2](PHASE2_REPORT.md) | 81 项测试、11 个族/变体的独立 PH 对拍、隔离 wheel |
| [Phase 3](PHASE3_REPORT.md) | 129 项数学测试、五 solver 与独立证书、冻结对照/no-go、联合验收；基线 `54ce78b` |
| [S4](S4_REPORT.md) | 正式同语义性能/RSS、消融、失败与退化、源码/构建/原始数据冻结 |
| [S4/S5 研究材料](research/s4-s5/) | 上传原件和 5,689 例独立 barcode 端点原型；来源/hash 见工作包文档 |

归档的研究原型不是公共 API、生产计算路径或 GUDHI 验收。
原始字节、文件名、旧阶段编号和 hash 保持不变。

[冷启动](冷启动.md) 和 [通用开发参考](development/) 面向维护者，按需使用。
其中 Web、数据库及微服务模板不适用于本库；具体规则以项目约定和数学契约为准。

维护文档时把安装/能力摘要放在根 README，实际 API 放在 INTERFACE，身份/schema 放在 RESULT_MODEL，
数学与 solver 约束放在各契约，状态汇总放在本页，原始测量与阶段证据保留在对应报告。
