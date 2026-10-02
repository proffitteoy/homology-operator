# 文档索引与冷启动结论

## 项目级契约

建议按以下顺序阅读：

1. [根 README](../README.md) 和 [项目 AGENTS](../AGENTS.md)：当前能力、目录与真实命令。
2. [开发路线](../HOMOLOGY_OPERATOR_ROADMAP.md)：阶段目标与退出条件。
3. [ARCHITECTURE](ARCHITECTURE.md)：统一算子、算子族和 oracle 边界。
4. [INTERFACE](INTERFACE.md)：链窗口输入、查询域和逻辑接口。
5. [RESULT_MODEL](RESULT_MODEL.md)：身份、状态、几何量和序列化。
6. [SOLVER_CONTRACT](SOLVER_CONTRACT.md)：合法投影、认证等级与资源约束。
7. [VALIDATION](VALIDATION.md)：当前检查入口及后续数学验证。

单尺度和有限过滤接口已在 Python reference 中落地，安装/API 命令见根 README。[Fixture 迁移说明](FIXTURES.md) 记录23个窗口、真实几何来源及 hash；[Phase 1](PHASE1_REPORT.md) 记录57项单尺度验收，[Phase 2](PHASE2_REPORT.md) 记录81项测试、11个族/变体的独立 PH 对拍、隔离 wheel 与范围限制。Phase 1–3 全部 PR 已合入 main `54ce78b`，该提交 CI 通过。Phase 3 的129项测试包含五种solver、独立证书、算术/资源/身份、冻结对照/no-go与联合同调/PH/几何验收；支持域及历史证据见 [solver 契约](SOLVER_CONTRACT.md) 与 [Phase 3报告](PHASE3_REPORT.md)。[S4/S5 项目计划](S4_S5_PROJECT.md) 管理下一轮高性能实现与 GUDHI/真实测量，仍属待实现任务；稳定性、应用与发行另行验收。

## 参考材料

- [S4/S5 项目与研究材料](S4_S5_PROJECT.md)：9 个同语义性能任务、6 个 GUDHI/测量任务、Project #3 依赖与验收、上传原始材料及独立原型复现。

- [Phase 3 求解与认证联合验收](PHASE3_REPORT.md)：当前支持域、跨solver同调/PH与几何、证书边界、固定源码/hash及剩余门槛。

- [Phase 3 solver对照协议与冻结结果](BENCHMARKS.md)：同问题、认证、预算与完整成本边界，保留不利和失败记录。

- [冷启动](冷启动.md)：从仓库事实裁剪项目规则的流程。
- [通用项目架构模板](development/通用项目架构模板.md)：按需裁剪，不直接套用 Web 或数据项目结构。
- [强前置条件约束](development/强前置条件约束.md)：备选规则集合；适用范围由项目 AGENTS 说明。
- [代码组织](development/代码组织.md)：目录边界调整时参考。
- [代码审计](development/代码审计.md)：输入、solver 输出和反序列化边界审计时参考。

项目契约保留在 `docs/`，通用开发材料集中到 `docs/development/`，内容保持原样；用户指定的 `docs/冷启动.md` 保留原路径。可执行工具放在 `scripts/`，源码、数学测试和 benchmark 目录随对应实现建立。

## 冷启动结论（2026-10-01）

初始化前本地仅跟踪一份两行 README；工作区已有路线图与设计文档，根 README 处于删除状态。没有 `AGENT.md` / `AGENTS.md`、源码、测试、依赖清单、配置、CI 或发布脚本。本次按冷启动要求重新建立根 README，保留已有研究与设计材料，补项目约定、逻辑接口、验证说明及可运行的文档检查脚本。

| 模板规则 | 裁剪结果 |
| --- | --- |
| 中文、先读上下文、最小修改、文档测试同步、证据化汇报 | 保留并落实到根 AGENTS |
| 技术栈、启动/测试/构建命令、目录和模块边界 | 按实际状态改写；当前只有 PowerShell 文档工具，数学实现语言尚未选定 |
| 安全与校验 | 应用于链窗口、solver 输出与结果身份；不套用 JWT、数据库或 Web 服务规则 |
| Web、微服务、数据库、`.env`、部署、所有项目仅能胶水集成 | 从项目约定中排除，参考原文保留 |
| 无证据的空目录、包版本、测试与性能宣称 | 不纳入项目规则 |
| 专项 skills | 普通任务不强制；数学、文档制品或专项审计按需使用 |

修正了冷启动计划中指向缺失 `docs/AGENTS.md` 的链接、路线图的本地基线与已有文档描述，并将 solver 状态和认证等级统一到 solver 契约。在结果模型中补明固定理论提交的空循环域 stretch=0 约定；已有核心数学设计保留。

以上是2026-10-01冷启动历史记录。2026-10-02 Phase 1、Phase 2 已合入 main 并验收，Phase 3 已开始，具体范围与证据见根 README 和验收报告。文档检查仍只证明文档完整性；完整优化 solver、性能、许可证和发行仍待办。
