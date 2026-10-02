# S4/S5 Project：同语义高性能开发与 GUDHI 对拍

日期：2026-10-02。管理入口：[GitHub Project #3](https://github.com/users/proffitteoy/projects/3)。
实现/调研基线：`main @ 54ce78bccdcba619ffa2a4d76aeb450bfd24270e`；历史 Phase 3 的 #49–#58 已合并，
该提交的 [Reference checks](https://github.com/proffitteoy/homology-operator/actions/runs/36998360788) 已通过。
本次交付是研究材料整合与可执行任务规划，未实现 Rust 后端、未运行正式 GUDHI 对拍或性能 benchmark。

## 1. 名称、范围与已有证据

- **S4：同语义高性能开发。** 保留 Python reference，首轮采用 safe Rust、`Vec<u64>`、单线程及批量 Python 绑定；降低完整调用链成本，保持同一个 P 的全部链 action、联合输出、认证和失败语义。
- **S5：GUDHI 对拍与真实性能报告。** 三方各按适用范围验收，冻结可比输入、负载、源码和测量协议，完整报告时间、RSS、规模边界及额外信息成本。
- 历史 `Phase 3` / `S3` 是 solver/certification 工作，报告、Stage 选项与 issue 标题保持不变。新性能任务使用 `S4-01…09` / `Stage=S4 · 高性能`，GUDHI 与测量任务使用 `S5-01…06` / `Stage=S5 · GUDHI`。
- 两阶段细化原路线图 **Phase 4：性能后端** 的实现与验收，不重新编号 Phase 0–7；采样稳定性、应用收益、一般新搜索算法与正式发行仍按原路线独立推进。
- 现有 129 项数学测试与历史报告属于 reference 证据。研究包的 5,689 例是独立端点算法有限检查，不是 native 集成、几何追踪、GUDHI 或性能证据。

原始材料按字节保留在 [研究计划](research/s4-s5/homology-operator-S3-S4-plan.md)、
[粘贴摘要](research/s4-s5/pasted-summary.md)、[独立原型](research/s4-s5/quiver_barcode_probe.py)、
[原始结果](research/s4-s5/quiver_barcode_probe_result.json)。
用户已将上传材料中的 S3/S4 更正为 S4/S5；原始文件名与正文按上传字节保留，不改写历史。原材料中的“未修改 GitHub”“拟创建任务”、sandbox 下载链接与旧状态保留为调研时记录；本文件是整合后的管理入口。
原型是归档研究脚本，保持来源/hash，不进入运行时或数学测试，Ruff 仅排除此归档文件。
Git 对此归档目录关闭换行规范化，并保留归档 Markdown 原有换行/尾空格，
避免 Windows checkout 或空白修整改变原始字节和 hash；普通文档仍遵循空白检查。

| 来源文件 | SHA256 |
| --- | --- |
| 上传压缩包 homology-operator-S3-S4-research.zip | db5227f167ebd551d009995e87e0bda94b7013a579f03adabcd422e02bb13b18 |
| 原计划 Markdown | 665fc1656e5422885c869fa1bb9a32ffded7a0f930874a33641db16f9d6393c1 |
| quiver_barcode_probe.py | c547670376b39512a6d7a9674b3deab2ebdc2c7cc9bca9598cd33b14e9121aa5 |
| 原始结果 JSON | 8ed4523b22fe07191fd25b478e60d765507f8d3853eab50333c7657c3aa4e089 |
| 粘贴摘要 Markdown | 7c7ee7d5239bcc47222130a75254b9715d23d3666a9fba94822600ee9321e115 |

压缩包原件保留在用户工作区；Git 管理解出的实际材料，避免重复存储二进制副本。
理论来源仍固定于 `homology-operator-lab @ 6143729669902ee875b211b58085e954c76cdf88`；
上传研究计划不是新的数学契约。

## 2. 管理与退出门槛

阶段总任务：[S4 #59](https://github.com/proffitteoy/homology-operator/issues/59)、[S5 #60](https://github.com/proffitteoy/homology-operator/issues/60)。
沿用 Project #3 的 Status、Stage、Kind、Area、Priority、Readiness 和原生 parent/sub-issue、blocked-by 关系；
历史 29 项及其状态保持不变。新增 2 个 Epic、15 个 Task。
所有新增项初始为 **Todo**；能开始规划/实现不表示功能完成。
S4-01、S5-01 为 Ready；其余 Task 按未完成前置为 Blocked；Epic 为 Gated。
只增加新阶段选项和标签，不复用历史 `stage:S3`。
父 Epic 统计各子任务，实际开发依赖直接写在 Task 上；不虚构负责人、排期或收益数字。

所有任务完成时附实现 PR/精确 SHA、命令、环境、fixture/output hash、独立验证、
原始结果与范围限制。依赖满足后更新 Readiness；关闭 issue、写报告或有限原型本身不能替代验收。

| 阶段 | 退出条件 |
| --- | --- |
| S4 | 完整联合输出与同 solver/认证等级一致；冻结负载中取得可复现端到端或绝对 RSS 改善，公开失败/退化；集成与实际合并/main CI核验通过，冻结供 S5 使用的版本 |
| S5 | 精确可比 corpus 的拓扑一致、联合语义另经 reference/独立 verifier 通过；正式原始样本、失败、完整成本与复跑证据齐全；允许更慢或仅重复查询划算的结论 |

S4 的一般规模线为合法投影、精确 F2 topology 与基本几何；认证求解线保留原支持域。
`2^(rank(D)·β)` 等有限指数工作不因原生化变为一般高效算法；
未计算 Γ/最优证书与合法零值分开。
优化准入与允许退化阈值在 pilot 后、正式采样前冻结，不用正式/holdout 数据选路线。

## 3. 验证与测量协议

[ARCHITECTURE](ARCHITECTURE.md)、[INTERFACE](INTERFACE.md)、[RESULT_MODEL](RESULT_MODEL.md)、
[SOLVER_CONTRACT](SOLVER_CONTRACT.md) 与 [VALIDATION](VALIDATION.md) 优先。
任何 action 入算子前仍独立验证 P²=P、AP=0、PD=0 和循环同调保持；
前三项不能接受非零同调上的零投影。兼容路径保持全部链的 P，包括非循环延拓。
紧凑表示有自己的版本/身份，生成元对拍证明跨表示等价；不能为 hash、构建 HC 或恢复偷偷展开完整 P。

| 对照 | 核查对象 |
| --- | --- |
| Native ↔ Python reference | 完整 P/L、代表、质量、距离、支撑、transport、barcode、认证、状态和恢复；不同身份混用仍拒绝 |
| Native ↔ GUDHI | 同显式 filtered simplicial complex 的 F2 Betti、barcode 多重集与区间 rank；不把 pairing/代表当作全部几何真值 |
| 一般 AD=0 链窗口 | 独立代数 verifier；无真实 SimplexTree 适配时 GUDHI=NotApplicable，不替换输入 |

manifest 记录 simplex、出生 stage、原 scale、坐标及正权/单位/算术，并重新导出核查实际建成的两边输入。
主 GUDHI 入口锁定实际版本，显式 F2、`min_persistence=0`、`persistence_dim_max=True`；
最高请求 Hq 的死亡需要共同输入的 q+1 次单形，max-dim 选项不补缺失单形。
整数 stage 保留重复尺度：同 stage 对角条丢弃，跨 stage 即使 scale 相同仍保留；
末端存活仅针对已声明的截断与常量末端延拓。
主基线使用同一显式复形；edge collapse/expansion 与 RipsPersistence 实际入口另列。

| 负载 | 请求与解释 |
| --- | --- |
| Topology readout | 经合法统一算子/族读取完整请求维数 barcode；与 GUDHI PH 比较完整成本，不走独立 PH 旁路 |
| Joint-basic | 加预声明的代表、质量、距离、支撑、tracking；Joint/GUDHI 比值表示不同输出集合的额外信息成本 |
| Joint-certified | 加指定 solver 的 Γ、bounds、证书和必需验证；只与同认证 reference 比较 |

性能 corpus 冻结小 β 大链、高 β、长过滤、中型 VR/网格；报告链维数、nnz、fill-in、rank、β、stage、查询量。
查询量可在 pilot 后冻结为 0/1/8/64/1024 等级；精确整数/有理与欧氏浮点分组。
冷启动端到端、已有对象的 warm batch、构造/验证/转换/几何/序列化互不重叠分段分别保存，
共同 frontend 公平计费。标准路径所有必需验证计入总成本。
时间实验关闭 profiler/tracemalloc；内存另用独立 worker 的操作系统级绝对峰值 RSS，
无可靠值填 null；矩阵条目预算不作为 RSS 硬限制。

建议至少 10 个独立进程区组×5 次有效重复；昂贵配置的较少重复须事先声明。
固定 seed 随机化顺序，先单线程；median/IQR 与进程区组配对置信区间有原始样本支撑。
timeout、OOM、killed、库内 resource_exhausted、unavailable、not-applicable 分开保留；
少样本不伪报尾分位，失败不删去或作成功耗时。
reference/native 只在同输入/输出/solver/认证组称加速比，
Joint-basic/GUDHI PH 称联合信息成本比；不预设必须胜过 GUDHI。

## 4. 工作包、依赖与实施顺序

原调研的 S3-01…09 映射为 S4-01…09，原调研的 S4-01…06 映射为 S5-01…06；上传原件中的旧名称只作来源记录。
22 条新 Task 前置边，加 S4-01 → 已完成历史 #3，共 23 条原生 blocked-by 边。
S5-01/02 的准备可与 S4 并行；正式三方验收及采样依赖集成和 S4 冻结。

| 编号 | 交付 | 前置 | Priority / Area |
| --- | --- | --- | --- |
| [S4-01 #61](https://github.com/proffitteoy/homology-operator/issues/61) | 冻结 main 基线、完整成本与 profiling 协议 | 历史 #3（已完成） | P0 / Infrastructure |
| [S4-02 #62](https://github.com/proffitteoy/homology-operator/issues/62) | 建立 safe Rust 纵向原型与批量 Python 入口 | S4-01 | P0 / Infrastructure |
| [S4-03 #63](https://github.com/proffitteoy/homology-operator/issues/63) | 实现 packed F2、稳定消元与多右端项复用 | S4-02 | P0 / Algebra |
| [S4-04 #64](https://github.com/proffitteoy/homology-operator/issues/64) | 实现同 P 的因子化 action 与独立验证 | S4-03 | P0 / Operator |
| [S4-05 #65](https://github.com/proffitteoy/homology-operator/issues/65) | 加速限定 solver 与独立证书重放 | S4-03、S4-04 | P1 / Solver |
| [S4-06 #66](https://github.com/proffitteoy/homology-operator/issues/66) | 实现几何批查询、精确权重与 workspace 复用 | S4-04 | P1 / Operator |
| [S4-07 #67](https://github.com/proffitteoy/homology-operator/issues/67) | 优化过滤共享存储、相邻 transport 与 barcode 读取 | S4-04、S4-06 | P0 / Filtration |
| [S4-08 #68](https://github.com/proffitteoy/homology-operator/issues/68) | 完成绑定、紧凑恢复、资源取消与后端集成 | S4-05、S4-06、S4-07 | P0 / Infrastructure |
| [S4-09 #69](https://github.com/proffitteoy/homology-operator/issues/69) | 验收同语义改善、消融并冻结 S5 源码 | S4-08 | P0 / Performance |
| [S5-01 #70](https://github.com/proffitteoy/homology-operator/issues/70) | 冻结 manifest 与同输入双构造器 | 无 | P0 / Filtration |
| [S5-02 #71](https://github.com/proffitteoy/homology-operator/issues/71) | 实现 GUDHI F2 oracle 与 stage 区间规范化 | S5-01 | P0 / Filtration |
| [S5-03 #72](https://github.com/proffitteoy/homology-operator/issues/72) | 完成三方 correctness corpus 与最小反例归档 | S5-02、S4-08 | P0 / Operator |
| [S5-04 #73](https://github.com/proffitteoy/homology-operator/issues/73) | 建立隔离进程计时、RSS 与失败采样 harness | S4-01、S5-01、S5-02 | P0 / Performance |
| [S5-05 #74](https://github.com/proffitteoy/homology-operator/issues/74) | 运行冻结负载、规模网格与 GUDHI 分组对照 | S4-09、S5-03、S5-04 | P0 / Performance |
| [S5-06 #75](https://github.com/proffitteoy/homology-operator/issues/75) | 交付真实性能审计报告与一键复现 | S5-05 | P0 / Performance |

### S4-01：冻结 main 基线、完整成本与 profiling 协议

现有对照是单次、启用 tracemalloc 的 solver 实验，不能作正式性能排名。先建立不带诊断开销的 R0，并绑定已合并 main。

实施交付：

- [ ] 固定 main SHA、23 份窗口来源/hash、既有过滤与 129 项数学回归；保存真实命令、环境、CI 与失败记录。
- [ ] 拆分输入/转换、solver、必需 validator、算子审计、transport/barcode、几何和序列化成本；诊断与无 profiler 的计时分开。
- [ ] 定义 benchmark manifest、查询负载、资源上限、认证分组和 pilot；在正式采样前冻结准入/退化阈值。

验收条件：

- [ ] main 数学回归、示例和构建可重放；旧分支报告不代替新基线。
- [ ] R0 有冷启动总成本与分段原始样本；嵌套计时不重复相加。
- [ ] 明确 RSS 方法与不可用值，不以 Python 分配峰值冒充进程 RSS；不预设加速倍率。

前置：历史 #3（已完成）；在 main 上重跑并冻结基线仍属本任务。依据：原计划 §2、§3.1、§4；BENCHMARKS / VALIDATION。

### S4-02：建立 safe Rust 纵向原型与批量 Python 入口

保留标准库 Python reference，先用一个真实链窗口验证原生后端的完整调用链，再扩展性能内核。

实施交付：

- [ ] 锁定 Rust、PyO3 与构建工具版本；首轮 safe Rust、Vec<u64>、单线程，保持现有 Python 公共入口。
- [ ] 一个真实窗口走通输入→同一 P/L→拓扑/代表/质量/距离/支撑→结果恢复；先保持显式等价表示。
- [ ] 按矩阵/算子/批查询跨绑定边界，分别记录转换、原生计算、回传与后备路径成本。

验收条件：

- [ ] reference 可独立安装运行，主结果无 GUDHI 依赖，原生热循环没有逐元素 Python 往返。
- [ ] 生成元 action、循环与非循环查询、身份和恢复均与 reference 对拍。
- [ ] 可复现 release 构建与最小端到端测量；若未获收益，记录瓶颈而不扩建多个原生后端。

前置：S4-01。依据：原计划 §3.1–3.2、§4；INTERFACE / RESULT_MODEL。

### S4-03：实现 packed F2、稳定消元与多右端项复用

rank、核、像和 solve 当前重复消元。用同一不可变分解复用代数结果，并保持原坐标和 stable pivot 策略。

实施交付：

- [ ] 实现 packed 加乘/action、稳定消元；一次分解支持 rank、kernel/image、membership、solve 和 multi-RHS。
- [ ] 沿用现有类型边界，只在实际复用需要时引入内部 prepared 表示；各次数只共享只读边界/分解，不共享权重或投影选择。
- [ ] 测量稀疏输入 fill-in 与 workspace；首轮保留普通 packed 基线，M4RI/显式 SIMD 仅作后续候选。

验收条件：

- [ ] 独立枚举与 reference canonical 输出一致，涵盖 0×n、n×0、秩亏、不可解与非法输入。
- [ ] 覆盖 63/64/65、127/128/129 字边界；尾部位清零，形状和原列坐标保留。
- [ ] 相同 RHS 结果一致；保存分解次数及完整成本消融，不能只报告内核时间。

前置：S4-02。依据：原计划 §3.3、§4；algebra.py / VALIDATION。

### S4-04：实现同 P 的因子化 action 与独立验证

先确认 packed 显式 P 等价，再避免一般路径默认物化 G/U/P/L；非循环延拓也属于兼容语义。

实施交付：

- [ ] 先实现 packed 等价构造，再以 Rx=x+GAx、Px=Rx+DU(Rx) 提供因子 action；按 β/n 研究同一个 P 的 HC 表示。
- [ ] 批量验证循环基 Z+PZ 属于 im(D)，复用 D 分解；HC 路径验证 AH=0、CD=0、CH=I 与循环同调保持。
- [ ] 身份绑定紧凑内容/表示版本；生成元验证跨表示等价，不强迫不同表示共用 projection_id。
- [ ] 外部输入/恢复/篡改始终重验；只有不可变完整身份与真实进程内验证来源支持时才研究验证去重。

验收条件：

- [ ] 小窗口全部坐标生成元的 P/L action 一致，涵盖非循环延拓与零投影反例。
- [ ] 独立 verifier 拒绝非法因子、身份/版本篡改和未经验证候选；合法性与最优性分开。
- [ ] 常规构造、查询、身份与证书不隐藏展开 n×n P；HC 构建不能先物化 P；保存显式/因子路线时间和 RSS。

前置：S4-03。依据：原计划 §3.4–3.5；ARCHITECTURE / RESULT_MODEL / SOLVER_CONTRACT。

### S4-05：加速限定 solver 与独立证书重放

一般规模可行线和认证求解线分别优化，Rust 降低常数不能消除已有指数搜索或扩大证明支持域。

实施交付：

- [ ] 优化 Exhaustive、Greedy、Rank2、Structured 的 packed 枚举、重复代数、权重计算和证书重放。
- [ ] 保持原支持域、候选/并列策略、配置、算术与认证；一般搜索现有 no-go 不自动重开。
- [ ] 记录 solver 与独立重放分别及合计成本；保留预算中断前合法候选、bounds 与 diagnostics。

验收条件：

- [ ] 同 solver/配置在可完成请求中保持质量、完整 action、认证和证书；ExactOptimal 始终有独立证据。
- [ ] 资源耗尽、未计算、不可用、失败和合法零分开；不同墙钟中断点只核验合法性，不伪称执行轨迹相同。
- [ ] 记录 2^(rank(D)·β) 与其他枚举边界；预算单位/停止语义变更显式说明，不能换成 Feasible 制造加速。

前置：S4-03、S4-04。依据：原计划 §3.2、§3.7；SOLVER_CONTRACT / PHASE3_REPORT。

### S4-06：实现几何批查询、精确权重与 workspace 复用

几何查询重复投影；同一批 Pz 可以复用，但质量、距离、支撑必须仍来自同一 P 与原权重。

实施交付：

- [ ] 批量复用 Pz，位运算计算支撑/共享/并集，保留原坐标索引与身份。
- [ ] 整数溢出检测并提供大整数/有理后备，Fraction 不被固定字宽近似；浮点保持既有 fsum 政策。
- [ ] 复用内部 workspace，记录原生/转换/后备成本；不修改已持有的算子或快照。

验收条件：

- [ ] 代表、selected_mass、distance、支撑与 reference 一致；涵盖任意正有理权、溢出、浮点与非循环拒绝。
- [ ] 不同 projection/weight/basis 混用拒绝，内部缓存准备不改变 NotComputed/Computed 与快照历史。
- [ ] 批查询 0/1/8/64/1024 等预声明负载可重复测量；任何 reference fallback 可见且计入总成本。

前置：S4-04。依据：原计划 §3.5；INTERFACE / RESULT_MODEL。

### S4-07：优化过滤共享存储、相邻 transport 与 barcode 读取

本地实现与完整证明见 [过滤读取](S4_FILTRATION.md)，冻结性能源码为e0e3183，保存36个
冷worker样本。普通barcode已改为相邻transport，并实现独立历史基及任意类tracking。
以下勾选表示本PR的实现/本地证据，不表示任务退出；仍需本PR合并、精确main/CI与
#64/#66的依赖联合验收。#64已提交源码的隔离HC兼容smoke不替代其PR合并。

实施交付：

- [x] 共享只读边界、基与活动索引；inclusion 用索引嵌入，目标核坐标采用一次分解和 multi-RHS。
- [x] 由相邻 T(i,i+1) 做区间分解；写出 birth 前缀张成空间不变量的完整证明，原全区间 rank 算法保留作小规模 oracle。
- [x] 接入端点原型时保留其 5689 例证据；历史 barcode bases 与任意类 tracking 另外实现/验证，不用端点原型替代。
- [x] 任意区间 rank/transport 按需计算和受控缓存；旧快照读取/状态与新紧凑版本显式兼容。

验收条件：

- [x] composition、共轭、全区间 rank/barcode、重复 scale 的有序 stage、末端延拓、身份和几何追踪一致。
- [x] barcode 普通请求不默认展开全部 chain action；要求完整 rank 表仍按真实二次输出计费。
- [x] 生产结果无独立 PH 旁路；缓存/workspace 不修改旧算子；长过滤消融保存时间/RSS，有限原型不冒充性能或一般证明。

前置：S4-04、S4-06。依据：原计划 §3.6；family.py / ARCHITECTURE / RESULT_MODEL。

### S4-08：完成绑定、紧凑恢复、资源取消与后端集成

在前述优化形成完整调用链后，收口安装、身份、快照、资源和验证行为；绑定成本与恢复成本属于真实成本。

实施交付：

- [ ] 锁定原生工具链/依赖，声明实际支持平台；支持 Python reference 与 native 选择及可见 fallback。
- [ ] 版本化紧凑 action/快照，保留旧 Matrix/CyclicAction/族格式的读入与重验，不为 hash 隐藏 dense 导出。
- [ ] 打通资源/取消、失败状态、转换、查询历史与集成 CI，记录执行入口和成本边界。

验收条件：

- [ ] 支持平台 release 安装及隔离打包真实通过；原有 129 项回归加新增 native 不变量、round-trip、篡改和混用拒绝测试通过。
- [ ] 取消延迟/库资源耗尽/进程 timeout/OOM 分开；不支持的限制明确表达，矩阵条目预算不冒称 RSS 硬限制。
- [ ] 外部输入和反序列化重新验证，标准路径必需 validator、转换与序列化成本全部可见。

前置：S4-05、S4-06、S4-07。依据：原计划 §3.1、§3.4–3.6、§4；RESULT_MODEL / VALIDATION。

### S4-09：验收同语义改善、消融并冻结 S5 源码

S4 的退出要求可复现端到端或内存改善，不能只完成理论上更快的重构，也不预设必须胜过 GUDHI。

实施交付：

- [ ] 在 pilot 后已冻结的准入阈值和负载下比较 R0、单项优化与完整后端；绑定源码、fixture、solver/认证、环境和查询量。
- [ ] 汇总一般规模线与认证求解线的质量、状态、失败、退化及 RSS/时间，给出支持域和规模边界。
- [ ] 提交 S4 实际验收报告，冻结供 S5 使用的精确 SHA/构建/参数/原始数据 hash。

验收条件：

- [ ] 完整联合输出与相同认证等级一致；至少目标负载中有可复现端到端或绝对 RSS 改善。
- [ ] 不利与失败数据完整；优化效果不能由关闭验证、隐藏转换、改变 P 或降低认证产生。
- [ ] 精确冻结版本可安装复跑，main/PR/CI 证据区分；未达到性能门槛如实记录，不能宣称 S4 通过。

前置：S4-08。依据：原计划 §4、§9；VALIDATION / BENCHMARKS。

### S5-01：冻结 manifest 与同输入双构造器

S5 输入规范可与 S4 并行准备。只有相同显式 filtered simplicial complex 才能与 GUDHI 拓扑对拍。

实施交付：

- [ ] manifest 保存 canonical simplex、出生 stage、原始 scale、坐标标识、正权/单位/算术、来源与 hash。
- [ ] 分别生成链窗口与 SimplexTree，再导出两边实际 simplex/filtration/维数计数与边界，核查面闭包和单调出生。
- [ ] 主比较以整数 stage 保留重复尺度；记录截断次数/阈值；一般 AD=0 窗口无适配时标 NotApplicable。

验收条件：

- [ ] 双边实际构造 hash/计数一致，插入面导致的 filtration 修改可检出；不换点云冒充同输入。
- [ ] stage 可被 GUDHI 数值无损表示；同 stage 对角条与跨 stage 相同 scale 条区分。
- [ ] 空/非法/退化权重与 H0–H3 截断约定可复现；零长度权不暗加 epsilon。

前置：无，可与 S4 基线并行准备。依据：原计划 §5.1–5.3、§6.1。

### S5-02：实现 GUDHI F2 oracle 与 stage 区间规范化

GUDHI 仅验证拓扑，不提供本项目全部几何或伸长认证的真值；参数默认值不能作为契约。

实施交付：

- [ ] 锁定实际 GUDHI 版本、wheel/源码与构建来源；主入口显式 coefficient=2、min_persistence=0、persistence_dim_max=True。
- [ ] 规范化同 stage 对角配对、跨 stage 重复 scale、末端存活与 multiplicity；由 barcode 核对全区间 rank 和 stage Betti。
- [ ] 主基线使用同一显式复形 SimplexTree；edge collapse→expansion 与 RipsPersistence 的实际入口另列次基线。

验收条件：

- [ ] 小实例各请求次数 Betti、barcode 多重集、全区间 rank 一致，H2 死亡需要共同输入的三维单形。
- [ ] 不要求算法配对/基/代表逐项相同；GUDHI 不被用作距离、支撑、Γ、最优证书 oracle。
- [ ] oracle 与主结果边界明确；max-dim 参数不补缺失单形，修改复形的次基线不冒充原链几何保持。

前置：S5-01。依据：原计划 §5.1–5.4；tests/oracle / ARCHITECTURE。

### S5-03：完成三方 correctness corpus 与最小反例归档

小样本 oracle 可提前开发；正式 Native↔reference↔GUDHI 联合验收需要集成后端，不混淆各方能证明的范围。

实施交付：

- [ ] 冻结空复形、孤点、环/填充、球面/三维填充、断连、多类、重复值/stage、末端存活、坐标重排和 H0/H1/H2/受控 H3。
- [ ] Native↔reference 核对完整 action、几何、transport、认证、状态与恢复；一般链窗口用独立代数 verifier。
- [ ] 随机测试保存 seed/manifest/hash；出现差异归档最小反例、两边结果与分类，分别统计 mismatch/N/A/Unavailable/中断。

验收条件：

- [ ] 精确可比 corpus 拓扑 mismatch=0，并准确声明已测范围；权重改变不改变同链/过滤 topology。
- [ ] 非循环 action、非法 AD、零投影、身份混用、证书与快照篡改回归通过。
- [ ] 有限测试不声称一般性证明；几何与认证通过 reference/独立 verifier 而非 GUDHI 配对。

前置：S5-02、S4-08。依据：原计划 §5.1、§6.1；VALIDATION。

### S5-04：建立隔离进程计时、RSS 与失败采样 harness

正式测量需要真实总成本、操作系统内存和完整失败记录；诊断工具与计时样本分开。

实施交付：

- [ ] 实现隔离 worker，保存 cold end-to-end、warm batch、互不重叠阶段计时与未分配开销；共同 frontend 公平计费。
- [ ] 独立内存运行记录操作系统绝对峰值 RSS、方法/单位/进程范围；tracemalloc/profiler 仅诊断，缺失填 null。
- [ ] 冻结 wall/RSS、取消和错误分类；保留库内资源耗尽及进程 timeout/OOM/killed/unavailable/not-applicable。
- [ ] 固定 seed 随机运行顺序；建议 10 个独立进程区组×5 次有效重复，昂贵样本降低次数须预先声明。

验收条件：

- [ ] 小样本可重放总时间和阶段边界，嵌套计时不双加，转换/必需验证/序列化不隐藏。
- [ ] RSS 不是分配代理或扣基线数；时间测量没有 profiler/tracemalloc，单线程主结果无隐性过度并行。
- [ ] 原始样本包含 SHA、fixture/output hash、规模、solver/config/certificate、负载、环境/构建/依赖、trial 与全部失败。

前置：S4-01、S5-01、S5-02。依据：原计划 §6.3、§7.1–7.3、§8。

### S5-05：运行冻结负载、规模网格与 GUDHI 分组对照

正式实验在冻结 S4 版本上执行，先冻结 pilot 与规模网格，不能运行后筛掉不利实例。

实施交付：

- [ ] 固定小 β 大链、高 β、长过滤、中型 VR/网格四类输入；保存维数、nnz、fill-in、rank、β、stage 与 query 规模。
- [ ] 分别跑 Topology readout、Joint-basic、Joint-certified；整数/有理与欧氏浮点分组，查询量和合法输入生成预先声明。
- [ ] 分开 reference/native 同输出同认证、GUDHI 显式复形主基线和适用的优化次基线，以及 cold/warm/并行。
- [ ] 保存 R0/单项/全后端消融、所有原始样本与失败，pilot 不混入正式统计。

验收条件：

- [ ] 正式源码固定 S4 SHA；每条成功输出先核对，认证与停止状态分别分组。
- [ ] 报告 median/IQR 和独立进程区组配对置信区间；少样本不伪报尾分位，timeout 不作成功耗时。
- [ ] reference/native 为同功能加速；Joint-basic/GUDHI 为额外信息成本比；允许更慢或只适合重复查询的结论。

前置：S4-09、S5-03、S5-04。依据：原计划 §6.2–6.3、§7、§8。

### S5-06：交付真实性能审计报告与一键复现

S5 的退出条件是正确、完整、可复现的结论，不能要求结果必须胜过 GUDHI。

实施交付：

- [ ] 报告适用域、三方 correctness、冷/热总成本与分段、绝对 RSS、规模上限、认证线与联合信息边际成本。
- [ ] 图表/统计可回溯 raw、manifest、environment、source/build/output hash；列出失败、缺失和不利结果。
- [ ] 提供真实安装/复跑/审计命令与隔离复跑记录，核对冻结版本和报告产物。

验收条件：

- [ ] 独立复跑能重建报告关键表格和 correctness 结果，计时容差/统计口径预先声明。
- [ ] 同输出加速与不同输出成本比无混用；许可证/发行、采样稳定性、应用收益不由本实验推导。
- [ ] 全部工作包真实完成并核验实际合并/main CI后退出；规划文档或有限原型不替代功能与性能验收。

前置：S5-05。依据：原计划 §7.4、§8–9；VALIDATION。

## 5. 研究材料复现与本次边界

从仓库根目录运行以下独立复现；输出写入临时路径，保留原始 JSON：

```powershell
$probeOutput = Join-Path $env:TEMP 'homology-quiver-barcode-recheck.json'
uv run --locked python docs/research/s4-s5/quiver_barcode_probe.py --cases 5000 --seed 20261002 --output $probeOutput
uv run --locked python -c "import json, pathlib, sys; a=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')); b=json.loads(pathlib.Path(sys.argv[2]).read_text(encoding='utf-8')); assert a == b; print('Probe record matches archived result')" docs/research/s4-s5/quiver_barcode_probe_result.json $probeOutput
pwsh -NoProfile -File ./scripts/check_docs.ps1
git diff --check
```

原型只接受其内部生成的有限小 F2 映射序列，不是公共输入接口。
其日期字段固定为研究日期，不代表每次复跑的真实运行日期。
原始记录的 corpus/script hash 应随上述比较完全一致；研究脚本保持原字节内容。

本次研究包整合只新增规划与归档材料，并更新文档入口/归档 Ruff 范围。
本项目的原生实现、GUDHI 依赖安装、正式测量入口与实际报告由对应工作包交付；
原研究计划建议的空报告、空 benchmark 目录和未来类型不提前建立。

本次本地核验：129 项既有 reference 数学测试及两个示例通过，Ruff lint/format、
文档检查（22 个 Markdown、108 个本地链接）和 `git diff --check` 通过。
独立原型在更正后的目录复跑 5,689 例、0 mismatch，结果 JSON 与归档记录完全相同，
四份上传文件的 SHA256 保持不变。上述成绩不是 Rust、GUDHI 或正式性能验收。
