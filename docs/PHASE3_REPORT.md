# Phase 3 求解与认证联合验收（2026-10-02）

当前完成 reference 实现与本地联合验收，阶段仍等待逐 issue PR 审查合并；所有 head 进入 main 并通过 main 数学测试/CI 才能开始 Phase 4。理论固定于 [研究提交6143729669902ee875b211b58085e954c76cdf88](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88)。研究成绩、数学合法性、当前 objective 与全局最优认证分别记录。

## 实际支持域

| 后端 | 当前支持与认证 | 明确边界 |
| --- | --- | --- |
| FeasibleSolver | 一般固定次数链窗口，精确F2合法投影；整数/有理/浮点权 | FeasibleOnly/Feasible，objective尚未计算；不会调用隐藏优化器 |
| ExhaustiveExactSolver | 精确整数/有理权、固定R的全部循环截面，独立完整重放最优 | `2^(rank(D)*beta)`候选；候选数乘非零循环数上限100000；一般有限指数reference |
| GreedyCertifiedSolver | 精确最低总质量同调基及T4，实算Γ，L=1/U=Γ（beta=0为0） | CertifiedInterval；真实等界才ExactOptimal；循环枚举仍指数，不保证一般ExactOptimal请求 |
| Rank2ExactSolver | 精确权、beta=2；一般窗口/Pareto、图循环、经代数验证的三终端割 | 不推断平面性或连续欧氏几何；独立完整截面/循环重放受同样100000工作上限 |
| StructuredFamilySolver | T-B1循环族n=2^m−1、m=2/3/4、A=0、im(D)=ker(P)、统一精确权；Γ*=m | Matrix或版本1CyclicAction；其他结构/非等权/浮点/更大m拒绝；A/D和核/transport仍可显式 |
| GeneralSearchSolver | 明确Unavailable | #24的边界翻转原型有实测no-go，不注册公共后端，不借已有结果填充 |

具体并列、结构前提、证书与预算见 [solver契约](SOLVER_CONTRACT.md)。投影在精确F2上满足P²=P、AP=0、PD=0及循环同调保持；最优性另重放ExhaustiveSearch、GreedyBasis、Rank2Search或CyclicTrace证明，原始verified标志不能成为公共证据。selected_mass始终是同一P选定的质量，不等于类最短质量。

FloatingPoint几何为binary64 fsum/division最近偶数舍入，tolerance=None，无误差区间或最优bounds；非有限数值明确失败。MixedCertified未实现。资源实际支持state/time/matrix-entry三种，独立后验证另计，没有抢占式单步时间或RSS/node保证。

## 已执行的联合验收

Windows build26100、CPython3.10.11、uv0.11.5、Ruff0.11.13、PowerShell7.6.5。129项unittest包括原单尺度/过滤、各solver证书、算术/资源/身份、冻结对照及本项3个跨solver联合测试。

- 原23份H0–H3、人工/真实欧氏权窗口：Feasible23、Exhaustive22、Greedy22、Rank2的全部6个beta=2实例，共73次支持运行。独立packed链枚举验证P不变量、Betti、循环同调、质量/支撑、当前Γ、对应真值及bounds；已查询单尺度快照反复JSON往返。浮点优化和非beta=2的Rank2请求明确Unavailable。
- 原11个过滤族/变体分别使用Feasible、Exhaustive、Greedy与逐阶段混合策略，共44个配置；浮点阶段显式使用Feasible。独立循环像商空间核对全区间rank，独立全局边界列约化核对barcode。遍历源循环核对同一目标P的直达/多步transport、质量、支撑与composition，已有tracking的快照恢复不丢历史。
- 另一个T-B1 m=2的六阶段族在同一窗口混用全部五个solver、显式/结构化表示，全部21个区间rank=2、两条末端存活barcode；全8个源链验证composition与目标P几何。三次快照恢复及跨表示/run查询混用拒绝通过。m=3/4结构域独立距离证明、m=3的4096截面真值核验留在专用测试。
- 资源测试逐solver遍历state位置、拒绝未支持资源字段，并用单调假时钟复现正wall中断。保留合法种子与完整objective/bounds；不完整候选、伪造证书、错误witness、等界区间、浮点相等、配置与六身份混用均拒绝。空循环域、零同调、未查询、不可用与中断分别表达。

真实入口（根目录）：

本次另重建wheel并在独立venv安装，用`python -I`从site-packages验证五种solver、混合族rank/几何、已有查询的JSON恢复及非法零投影拒绝；两个公开示例实际运行。该隔离安装验证与完整数学测试分别报告，均不等于尚未核对的PR/main CI。

```powershell
uv run --locked python -m unittest discover -s tests -v
uv run --locked python examples/single_scale.py
uv run --locked python examples/filtration.py
uv run --locked ruff check .
uv run --locked ruff format --check .
uv build --no-build-isolation
pwsh -NoProfile -File ./scripts/check_docs.ps1
git diff --check
```

## 冻结对照与一般搜索准入

[对照协议与原始产物](BENCHMARKS.md) 保存干净源码、环境、输入/配置hash、构造、独立重验和算子审计完整成本。#25为324行、114个保留action；#24为144行、120个保留action；全部记录的action在当前测试重验及JSON恢复。旧产物不被后续修复覆盖。

K4贪心Γ=4/3，Exhaustive/Rank2最优9/8；T-A4一般路径贪心13/8，精确7/6。局部翻转将K4改善到9/8但只能给[1,9/8]，同预算已有exact可认证最优；人工beta=3无质量收益。本轮no-go限于这个准入原型，不否定未来其他搜索。单次、不同认证等级的时间不混作速度排名；m=4结构构造约2.3ms，独立重验约61.9ms、额外审计约1.67s的完整成本仍保留。

## 数学源码与fixture身份

以下均为UTF-8/LF规范化SHA256，按sorted/compact path:hash映射计算聚合；报告和实验产物不进入数学源码hash。生产源码已随#55进入main，后续#24/#29不改变它；CI需核对各PR的准确head，不能用此清单代替CI。

| 生产文件 | SHA256 |
| --- | --- |
| `src/homology_operator/__init__.py` | `ac8e3119f9a6a15b3330769ed18656e84209a59f16a94005b63aea2216549f82` |
| `src/homology_operator/algebra.py` | `3289bf88534e072222550d6c387c73851c8177a7c8ca8989f80efab3db605740` |
| `src/homology_operator/chain.py` | `6d4c0e09ab5cc943fc0680e66acf715352a695f6aa4b7f4cf635f1522c605015` |
| `src/homology_operator/family.py` | `331256ae66316866273978081aead421ab0c77bd2d551d077c42d9bb242a6fd2` |
| `src/homology_operator/operator.py` | `57bd463579b168137783ae07b51e58507a4862233672c3dbf0510fd2c417ae11` |
| `src/homology_operator/result.py` | `04dbae591a4e3a210d1f4df18e6776aa06030462b0565d0b7d6e3fcc05abd1fe` |
| `src/homology_operator/solver.py` | `91e3c0ac665c76ff4529359cb209b8ea4ffc2321e5eacef39def7b1e47fdadb5` |
| `src/homology_operator/validation.py` | `5deff7029dfc486e59665fa0f439622ee2406d9a17694e5211d6a952b3a494d3` |

源码聚合`3d6288e21dc8d04f0c0f7734e1ccb2ffff3efe0fcef94938918de81202afcbb4`；原23窗口文件`593fb2784a2b5ea25bc62d7ee3c0180fa3185fefc6b42cf87a7203f7b111d7e2`；solver真值/贪心corpus文件`1bcd53fc250949346299e3aa216f042b9f59dc014879b1e506879645999203f1`。迁移来源、原始路径/hash见 [fixture记录](FIXTURES.md)；各solver契约保存固定上游代码的Git blob及逐项对照，未复制整个研究依赖或把其run_tests成绩当成本库成绩。

## 剩余门槛

当前是有限correctness reference。没有一般高效搜索、浮点认证、MixedCertified、峰值RSS/抢占预算、一般链映射、采样/网格稳定性、应用收益或发行保证。版本0.0.2.dev0不是发行，许可证待选。阶段合并门槛见根README，Phase 4语言与性能决策尚未开始。
