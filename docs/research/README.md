# 研究代码与成果索引

本页把数学契约、生产实现、独立验证、实验数据和报告连起来。
截至 2026-10-04，软件基线为 `22436d3687daa21d6f062e4f043e0de1c4e0cc0e`；
S4/S5 正式测量仍绑定报告原有的源码、构建、机器与协议。
本页汇总已交付的研究结果，不把有限验证写成一般定理，也不回写原始报告的历史状态。

## 核心成果与代码

| 成果 | 数学与实现入口 | 独立证据与边界 |
| --- | --- | --- |
| 边界原生 F2 同调算子 | [架构](../ARCHITECTURE.md)、[algebra.py](../../src/homology_operator/algebra.py)、[operator.py](../../src/homology_operator/operator.py) | 同一个 P 满足四项投影条件；`ker(L)` 表示同调；[23 份迁移窗口](../FIXTURES.md)和[独立 oracle](../../tests/oracle/reference.py) |
| 同 P 的几何读取 | [operator.py](../../src/homology_operator/operator.py)、[结果模型](../RESULT_MODEL.md) | 原坐标正权的代表、质量、距离、支撑与 stretch；[几何测试](../../tests/test_geometry.py)。选定质量不是最短类质量 |
| 有限过滤、相邻 transport 与历史基 | [family.py](../../src/homology_operator/family.py)、[S4-07 的算法与归纳论证](../S4_FILTRATION.md) | 生产 barcode 从 transport/rank 读取；[联合 PH 对拍](../../tests/test_family_joint.py)、[5,689 例与历史基](../../tests/test_family.py)；原型见 [research](../../research/README.md) |
| 有限最优认证与结构路线 | [solver.py](../../src/homology_operator/solver.py)、[validation.py](../../src/homology_operator/validation.py)、[契约](../SOLVER_CONTRACT.md) | Exhaustive、Rank2、限定 T-B1 的独立证书；[最优真值](../../tests/fixtures/solver_reference.json)、[Phase 3](../PHASE3_REPORT.md)。仅在声明的支持域成立 |
| 可选 native、多字代数与紧凑 action | [Rust 实现](../../native/src/)、[native.py](../../src/homology_operator/native.py) | packed、PreparedMatrix、Factorized/HC 与 geometry workspace 的同 P 差分；[联合测试](../../tests/test_s4_integration.py)、[S4 全成本](../S4_REPORT.md) |
| 同输入的外部拓扑对照 | [显式单形 adapter](../../tests/oracle/simplicial.py)、[GUDHI oracle](../../tests/oracle/gudhi_oracle.py) | [77 份三方 corpus](../../tests/fixtures/s5_correctness.json)、[S5 契约](../S5_GUDHI.md)。GUDHI 只对照 F2 拓扑，不提供生产几何/主结果 |
| 身份、认证与可恢复结果 | [result.py](../../src/homology_operator/result.py)、[六身份与 schema](../RESULT_MODEL.md) | [旧快照](../../tests/fixtures/legacy_results.json)、[混用/恢复测试](../../tests/test_legacy_results.py)；零值、失败、未计算与资源耗尽分别保存 |

理论来源为 [homology-operator-lab 的固定提交](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88)。
源文件、字节 hash、迁移步骤及本地补充见 [FIXTURES](../FIXTURES.md)和 [SOLVER_CONTRACT](../SOLVER_CONTRACT.md)。
本库实现与理论来源分开引用；使用研究成绩时引用实际输入、源码与报告。

## 保留的实验结论

| 结果 | 冻结证据 | 结论适用范围 |
| --- | --- | --- |
| Phase 1 单尺度、Phase 2 过滤 | [Phase 1](../PHASE1_REPORT.md)、[Phase 2](../PHASE2_REPORT.md) | 历史 57/81 项验证；不是当前滚动测试数 |
| Phase 3 solver 与一般搜索 no-go | [Phase 3](../PHASE3_REPORT.md)、[对照数据](../../benchmarks/phase3_reference.json)、[局部搜索](../../benchmarks/phase3_local_search.json) | K4 贪心 Γ=4/3，精确 9/8；局部翻转虽可到 9/8，只有有限 bounds，未形成准入收益；不否定其他搜索路线 |
| S4 正式同语义测量 | [S4 报告](../S4_REPORT.md)、[全部原值](../../benchmarks/s4_acceptance_formal.json)、[统计](../../benchmarks/s4_acceptance_summary.csv) | 27 配置、1,880 独立进程；部分收益，4 组时间退化超过 20%；保留显式后端选择 |
| S5 三方正确性与完整成本 | [S5 报告](../S5_REPORT.md)、[77 份复审](../../benchmarks/s5_correctness_review_audit.json)、[完整 gzip 原值](../../benchmarks/s5_performance_formal.json.gz) | 20 配置、2,840 进程；68 个集成可比组没有一个 95% 配对区间完全低于 1，不能宣称全局加速 |
| 独立端点算法原型 | [脚本与结果](../../research/README.md) | 5,689 有限例、零端点差异；没有性能测量或生产几何验收 |

S4/S5 正式生产源码固定 `7fa812d5e76ca80ac16316cb212d133c0639bfd7`，
S5 原测量 helper/清单固定 `f4b0d58148c7b94b83dcb5ae5bfe79857deb2c73`。
Cold、warm、独立绝对 RSS、额外几何信息成本与 solver 认证分开解释。
全部失败、资源耗尽、不可用、NotApplicable、pilot、profiling 和退化一并保留。

## 复现与维护入口

- [实验及数据清单](../../benchmarks/README.md)：完整 SHA256 清单、只读检查、原型和 S5 表格复现。
- [实际检查与测量脚本](../../scripts/README.md)：每项入口、依赖及输出用途。
- [上传原件和归档代码](../../research/README.md)：保留原始字节及旧编号。
- [开发验证](../VALIDATION.md)：reference/native/GUDHI、构建与 CI。
- [当前状态](../README.md)：精确软件/CI 身份；原始阶段报告保持验收时记录。

普通研究复跑写到 `.task-artifacts/`。新采样应先声明新输入、源码、二进制、环境和预算；
不能用当前 main 的运行冒名复现原机器的耗时。

## 尚未获得的成果

真实最短类质量、一般高效全局搜索、浮点最优认证、无限族或网格采样稳定性、
应用任务收益以及跨机器/更大规模通用加速仍需各自证明或验收。
S5 的 journal 尾行截断恢复边界保留在原报告中；本轮不依赖旧 journal 续跑。
数学测试、有限例重跑和统计重建分别报告；三者不能互相替代，也不宣告阶段 Epic 的最终退出。
