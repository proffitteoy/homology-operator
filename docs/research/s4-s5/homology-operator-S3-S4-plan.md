# Homology Operator：S3 高性能开发与 S4 GUDHI 对拍计划

调研日期：2026-10-02  
调研基线：`proffitteoy/homology-operator @ 54ce78bccdcba619ffa2a4d76aeb450bfd24270e`  
性质：源码审查、外部算法/API 调研、独立有限算法原型验证与拟定实施计划；本次未实施原生后端、未运行新的性能实验，也未修改 GitHub。

## 1. 阶段与目标

采用本次指定的阶段名称：**S3：高性能开发；S4：GUDHI 对拍及真实性能汇报**。仓库中旧 `Phase 3` 指已经完成实现并合并的 solver/certification 工作；其历史 PR、报告与实验编号保持不变。新文档应显式区分旧 Phase 3 与本计划的新 S3，避免覆盖旧证据。

S3 的目标是在既有数学、查询、认证与失败语义下，降低统一算子的构造、查询、过滤和验证成本。S4 的目标是在相同输入和输出口径下，验证拓扑正确性，报告实际时间、内存、规模边界和额外几何输出成本。

本轮不把采样稳定性、真实应用有效性、新的一般最优搜索算法、正式发行或其他仓库集成设为前置任务。正式 benchmark 必须在 S3 的冻结版本上运行，但 S4 的输入规范、oracle 适配与小样本对拍可以与 S3 并行开发。

## 2. 本次核查得到的事实

以下是源码或仓库报告中的事实，不是本次 profiling 结果。[R1–R8]

| 位置 | 当前实现 | 对计划的影响 |
|---|---|---|
| `algebra.py / Matrix` | 行式 `tuple[tuple[int,...],...]`；乘法逐元素求和取模；消元逐项 XOR | 位压缩原生 F2 运算是明确的优化候选，但收益倍率须测量 |
| `rank/kernel_basis/image_basis/solve` | 分别调用 `rref()`；`solve` 新建增广矩阵 | 建立可复用消元分解和多右端项求解 |
| `solver.py / generalized_inverse` | 对 `[M | I]` 消元，显式生成广义逆 | 研究消元操作记录与隐式广义逆 action |
| `FeasibleSolver` | 显式构造 G、U 和 n×n 的 P，并通过矩阵乘法验证 | 从 packed 等价实现过渡到可验证的因子化表示 |
| `operator.py` | L 显式构造；kernel 有缓存，但 betti 仍通过 L.rank 计算；几何查询重复投影 | 复用同一算子的分解、代表与几何 batch workspace |
| `validation.py` | 显式验证 P²、L²、AP、PD；循环基向量逐个调用 D.solve | 批量 membership 与独立的因子证书验证是优化重点 |
| `family.py / transport` | 构造稠密 inclusion；对 chain action 每一列重新求目标核坐标 | inclusion 改索引嵌入；目标坐标分解一次、多右端项复用 |
| `family.py / barcode` | 遍历全部 i≤j 区间，并请求 transport/rank | 研究由相邻 transport 直接做区间分解，避免 barcode 默认生成二次量级区间表 |
| `family.py / to_result` | 调用 barcode，并保存已产生的查询 | 快照与查询历史本身也是成本；不得只优化内核后忽略序列化 |
| `result.py` | 身份绑定 input、basis、weight、action、tie-break；仅接受现有 Matrix/CyclicAction | 新 action 表示必须显式扩展身份、schema 与验证边界 |

旧 `BENCHMARKS.md` 明确说明其记录是**单次、启用 tracemalloc 的有限 solver 对照**，不是稳健速度排名；Python 分配峰值不等于进程 RSS。其中 T-B1 m=4 的一次记录为构造约 2.3 ms、额外独立重验约 61.9 ms、算子构造与审计约 1.67 s。这只提示必须测量完整路径，不能被当作当前主机的实测结论或未来加速依据。[R7]

旧联合验收报告记录 129 项本地测试、73 次冻结窗口支持运行及 44 个过滤配置；S3-01 要在冻结 main 上重新执行，而不能直接把旧分支报告当作新后端的验证。[R8]

## 3. S3 技术路线

### 3.1 后端选择与边界

建议采用 **Rust 原生计算核心 + 保留 Python reference 和现有 Python 公共入口**。

首轮使用 safe Rust、`Vec<u64>`、单线程和明确所有权；Python reference 继续作为独立的可审查数学 oracle。Python 侧不负责逐元素热循环。跨语言边界按整个矩阵、算子或一批查询传递，分别计量一次性转换和结果回传。PyO3 是拟采用的绑定方案；具体工具链和依赖版本在 S3-01/02 的可复现构建中锁定。[E4]

这是本次建议，不是此前已经确定的语言事实。最小纵向原型需要同时验证：正确性、构建、序列化、端到端收益及 Python 边界成本。原型不达标时，应先定位转换和算法成本，不同时维护两个新原生后端。

GUDHI 只作为测试/benchmark 的可选依赖，不成为主计算结果的来源。首轮不把 GPU、显式 SIMD、多层并行或 M4RI 外部库依赖作为目标。M4RI 的分块消元、PLE/PLUQ 和 Four Russians 算法可作为后续密集块优化参考，先建立普通 packed 消元基线。[E1]

### 3.2 保持数学与结果语义

继续从 `(A,D,w)` 构造同一个投影 P 和 L=I+P；拓扑、代表、质量、距离、支撑、伸长和过滤映射都来自它。`project/apply_operator` 定义在全部链上，同调类查询仍只接受循环。[R3,R5]

兼容后端必须保持原始坐标、确定性策略、并列选择及完整 P action。仅有相同 Betti 数或 barcode，不足以证明新后端与 reference 等价。对小型窗口应逐坐标生成元验证全部链空间上的 P 相等；对循环还应核验代表、质量、支撑和传输。

同一 solver/配置的实现优化与新 solver 策略分开。不得把 ExactOptimal 请求换为 Feasible 来制造加速。不同时间预算下的中断位置可不同，但失败状态、已验证候选、bounds 和认证的合法性必须保持；资源单位、枚举顺序或停止语义发生变化时必须记录，不可冒充完全相同的请求执行。

`selected_mass` 保留选定代表质量语义。拓扑 F2 精确、当前 Γ 精确、最优性认证和浮点几何近似分开报告。缓存内部是否已准备某个分解，不得无意改变公共 `NotComputed/Computed` 状态与快照历史。

### 3.3 第一优先级：packed F2 与共享消元

引入 packed 矩阵、行/列视图和不可变的 `PreparedElimination`（名称为拟议内部名）。一次分解提供 rank、kernel/image、membership、solve 和多右端项 solve。pivot 规则保持参考实现的稳定基顺序，不把列置换静默写回公共坐标。[R1,R2]

必须测试 0×n、n×0、秩亏、不可解，以及 63/64/65、127/128/129 等字边界。尾部填充位始终清零并纳入序列化检查。先使用明确的 packed 表示；稀疏边界与 dense workspace 分开，后续根据实测 fill-in 决定转换，不能假定稀疏输入会一直稀疏。

同一个边界矩阵在相邻同调次数中可共享只读存储；其可复用消元分解也应有独立身份。各次数的 solver 选择、权重和 projection 不因此合并。主框架维数通用，H0–H3 的既有语义回归都保留。

### 3.4 第二优先级：避免一般路径显式构造 n×n 投影

分两步推进，避免一次性改变数学实现和表示协议。

**第一步：packed 等价版本。** 保持同一显式 P 和原输出语义，用于独立确认底层代数迁移正确、得到可归因的收益。

**第二步：因子化 action。** 当前公式可以直接以作用实现：先计算 Rx=x+GAx，再计算 Px=Rx+DU(Rx)，最后 Lx=x+Px。G/U 可由消元操作记录提供 action，无需默认物化完整 G、U、P、L。这是既有公式的执行方式变化，不是新的最优求解算法。

当 Betti 数 β 较小时，再研究保持同一 P 的低秩表示 `P=H C`，其中 H 为 n×β，C 为 β×n，且 `C H=I`。粗略表示规模由 n² 位变为约 2nβ 位，实际还要计入分解、输入、证书和缓存；β 较大时不保证更省，必须与 packed 显式表示比较。

H/C 必须保持完整 P，包括非循环上的延拓。只在 ker(A) 上同构但非循环 action 不同的构造属于不同 solver/action，不能当作无语义变化优化。构造 H/C 的算法也不能先物化 P 再宣称避免了其峰值内存。

新 action 使用版本化、可重放的紧凑表示。跨表示等价通过生成元作用验证，不直接强行共享身份。旧格式读取和语义继续支持；如需新的紧凑快照格式，显式提升 schema/表示版本。小规模可提供 canonical dense 导出用于诊断，但身份计算和普通查询不能暗中强制该导出。[R6]

### 3.5 第三优先级：验证与查询也使用高性能路径

先批量检查循环同调保持：对循环基 Z 的各列，验证 `Z+PZ` 落在 im(D)，复用一次 D 的求解分解。[R4]

对 `P=HC` 可研究独立验证 `AH=0`、`CD=0`、`CH=I`，并验证完整循环基的同调保持。这些恒等式共同推出 P 的所需性质；不能只验证其中前三项就接受。证书提供方与验证器职责分开，外部布尔标志不构成证明。

重复验证的去重必须先建立不可变对象、完整内容身份、validator 版本和不可伪造的进程内验证句柄。外部输入、JSON 恢复、修改过的 action 或不匹配身份仍需重验。首个原生版本可先保留重复验证，明确计入时间，不能通过关闭验证获得表面收益。

几何 batch 查询应复用同一批 Pz：support 为置位索引，共享/并集可利用位运算；质量和距离仍使用既定权重与算术政策。对于任意正有理权，固定整数宽度不足以替代 Fraction；采用溢出检查和大整数/有理后备。浮点不得打开改变数学语义的 fast-math；既定 fsum 口径不能默默换成普通累加。暂不能保持某个数值分支时，可明确保留 reference 读取，且计入其成本。

### 3.6 第四优先级：过滤的存储复用和相邻传输

共享只读边界与基标识；各尺度保存活动索引或增量视图，避免把每个窗口和 inclusion 都完整复制。inclusion 用原坐标索引嵌入执行，目标核坐标求解采用准备好的分解和多右端项。[R5]

首先优化相邻 `T(i,i+1)`，在该序列上进行区间分解，并保留基变换信息。原来的全区间 rank 公式作为小规模 oracle。相关可参考《The Space of Barcode Bases for Persistence Modules》中直接对线性映射序列计算 barcode 并追踪基变换的方法。[E2]

这条路径的输入仍是算子族的 transport，没有另行从边界计算一套 PH 后填入结果。需先证明与当前 rank 读取等价，再更新相应实现说明和测试。文献 CompPers 本身仍含过滤长度的二次复杂度项，追踪全部历史基变换还有额外成本；不能将其直接称为线性时间 streaming 算法。[E2]

本次另外实现了一个**仅计算区间端点**的独立原型：维护按 birth 排序的当前基；作用相邻映射；按从旧到新的顺序保留线性独立的像，依赖列对应的 birth 在当前 stage 死亡；最后补齐目标空间的基，将补入方向记为当前 stage 出生。它不输出历史 barcode bases，不能替代本项目的任意同调类几何跟踪。

其正确性论证入口是如下不变量：在当前 V_i 中，出生时间不晚于 b 的活动基向量张成 im(T(b,i))。应用下一个映射后，从旧到新做独立性筛选保持每个 birth 前缀的张成空间；目标补空间只增加新出生方向。因此该不变量可沿 stage 归纳保持，并恢复同一个 rank invariant。正式接入时仍需写成完整证明并覆盖公共 API 语义。

本次实际执行的有限检查结果：穷举所有源/目标维数均在 0–3 的两阶段 F2 映射，共 689 例；再生成 5,000 组随机映射序列，stage 数 1–9，各空间维数 0–6，seed=20261002。以独立的完整像集枚举计算所有区间 rank，再由 rank 公式恢复 barcode，与该原型对照：**总计 5,689 例，0 个 mismatch**。包含 2,448 个至少有一个零维空间的实例。

复现文件为 `quiver_barcode_probe.py` 与 `quiver_barcode_probe_result.json`，随调研包提供。该检查不导入本仓库或 GUDHI，不测性能，不验证几何跟踪、solver、序列化或完整集成；它是有限正确性证据，不能替代一般性证明与仓库回归。

barcodes 默认不应强制生成所有 `T(i,j)` 的 chain action。任意区间 rank/transport 保留按需查询与受控缓存；要求完整 rank 表的调用仍按实际二次输出规模计费。不能宣称所有全区间查询都变为线性复杂度。

跨尺度增量消元属于后续优化实验：必须与逐尺度的稳定 canonical 结果对拍。保持 barcode 而改变 P_i、代表几何或并列策略的增量更新，不能进入兼容路径。workspace 复用不允许修改调用者已经持有的旧算子或快照。

### 3.7 solver 优化的适用范围

S3 同时保留两条明确的性能线。[R8]

- **一般规模线**：FeasibleSolver + 精确 F2 topology + 同一 P 的基本几何读取。未请求或未能完成的 Γ/最优证书保持缺失状态，不能改称“高性能最小伸长求解”。
- **认证求解线**：同一支持域内优化 Exhaustive、Greedy、Rank2、Structured 的 packed 枚举、重复代数、权重计算和独立证书重放。以相同 solver 与认证等级比较完整成本。

完整搜索仍有 `2^(rank(D)·β)` 候选；Greedy 和部分 verifier 也保留有限指数枚举。提升常数并不改变这一复杂度。新搜索策略、扩展结构族或更强证书需要独立数学与准入证据，本轮不以“原生化”为理由自动放行。

## 4. S3 工作包与验收

以下为拟定工作包，尚未创建 issue 或提交实现。

| 编号 | 交付 | 关键验收 | 依赖 |
|---|---|---|---|
| S3-01 | 冻结基线、重跑数学回归、分阶段 profiler、benchmark manifest | 绑定 main SHA；明确旧数据与新测量；保存不带 profiler 的端到端样本 | 无 |
| S3-02 | Rust 最小纵向后端与 Python 适配 | 一个真实窗口完成输入→P/L→联合读取→恢复；reference 仍可独立运行；无 GUDHI 主路径依赖 | 01 |
| S3-03 | packed F2、稳定消元与 prepared/multi-RHS | 原代数回归及字边界通过；同输入 canonical 结果一致；可量化分解复用 | 02 |
| S3-04 | packed/因子化投影及独立验证 | 完整链 action 等价；非循环回归；常规查询、身份计算不偷偷物化 P | 03 |
| S3-05 | 限定 solver 和证书的原生加速 | 同支持域、同质量、同认证；bounds 和中断合法；分别记录求解与重放成本 | 03、04 |
| S3-06 | 几何 batch、精确权重、复用 workspace | 代表/质量/距离/支撑同输出；正有理数与溢出边界；浮点策略明确 | 04 |
| S3-07 | 过滤共享存储、相邻 transport、区间分解 | 与原全区间 rank/barcode 一致；composition、重复尺度、身份和旧快照回归通过 | 04；06 提供几何跟踪 |
| S3-08 | 绑定、紧凑序列化、资源/取消与集成收口 | release 构建、支持平台安装、验证成本和转换成本可见；无隐藏 fallback | 05–07 |
| S3-09 | S3 验收与消融报告 | 固定负载中有可复现端到端或 RSS 改善；退化/失败公开；冻结供 S4 使用的版本 | 08 |

每项优化应保存 R0 与单项增量的消融。不能只提交“理论上更快”的重构；基础兼容改造可以作为依赖，但最终高性能验收需要真实收益。优化准入阈值应在 pilot 后、正式采样前冻结，例如明确允许的小样本退化范围和中大样本目标；本计划不虚构尚未测量的加速倍率。

S3 不要求所有已支持请求都达到大规模，也不要求比 GUDHI 快。它要求同语义可复现改进、资源行为明确，并如实限定各 solver 的规模边界。

## 5. S4 对拍范围与 GUDHI 适配

### 5.1 三方验证各自承担什么

**Native ↔ Python reference：** 验证完整 P/L action、代表、质量、距离、支撑、transport、barcode、认证、状态和序列化。改变表示时允许表示身份不同，但必须验证语义等价并保持跨身份混用拒绝。

**Native ↔ GUDHI：** 对确实来自相同 filtered simplicial complex 的实例，比较 F2 Betti、各维 barcode 的多重集和区间 rank。不同算法选择的同调基、代表或 birth/death simplex pairing 可不同，不把它们逐项相等作为一般正确性条件。

**独立代数 verifier：** 对一般 AD=0 链窗口继续验证算子合法性、循环同调保持与证书。任意链窗口未必存在当前 SimplexTree 适配；没有真实适配的样本明确标 `GUDHI: NotApplicable`，不能用另一张点云冒充相同输入。

GUDHI persistence 与 generators/pairs 接口提供的是其文档声明的拓扑/配对信息，不自动提供本项目同一 P 的最小伸长、全体类距离或共享支撑真值。相关几何与证书正确性由 reference/独立验证器负责。[E3]

### 5.2 唯一输入 manifest

基线包含每个 simplex 的 canonical 顶点集合、维数、出生 stage、原始 scale、原始坐标标识，以及各次数正权重、权重单位和算术政策。由该 manifest 分别构造本项目边界数据与 GUDHI SimplexTree。

构造适配器后，重新导出两边的 simplices、filtration 与各维计数并比较 hash；检查所有面存在且出生不晚于余面。GUDHI 插入 simplex 会处理其面并可能改变已有面过滤值，因此不能只核对输入脚本、不核对实际建出的复形。[E3]

第一轮 correctness 以 stage 整数作为 GUDHI filtration value。这样可以保留本仓库 OrderedStages 中“数值 scale 相同但有序 stage 不同”的情形。拓扑对拍先在 stage 域完成，再映射到物理尺度显示。stage 编号必须可被实际 GUDHI 数值表示无损表达。

同一个 stage 内产生和消失的算法配对不属于阶段端点之间的非零区间，规范化时丢弃其对角条。跨不同 stage 的区间即使映射后 scale 长度为零，也必须保留。`min_persistence=-1` 只用于额外诊断全部配对，不能把其原始输出直接与阶段 barcode 混比。

终点仍存活的区间与 reference 的常量末端延拓一致；另标明阈值和复形截断。不能把有限阈值处存活解释成未截断完整几何过程中的永久类。

### 5.3 GUDHI 参数与维数

主正确性入口使用明确版本的 `SimplexTree.compute_persistence(homology_coeff_field=2, min_persistence=0, persistence_dim_max=True)`，读取目标维数并按前述 stage 规则规范化。官方参考中系数域默认是 11，最大复形维的计算默认关闭，因此不能依赖默认值。[E3]

请求最高同调次数 q 时，共同输入通常应至少提供 q+1 次单形以描述 Hq 的死亡；例如 H2 要包含相应四面体。`persistence_dim_max=True` 不能补回缺失的上维单形。确实只给截断骨架的实验，明确按该截断复形解释，两边保持一致。

GUDHI 的实际版本、wheel/源码来源、构建选项和使用入口在执行时记录并锁定；不能把 `latest` 文档页面标签当成机器已安装版本。

### 5.4 主基线与优化基线

**主基线：同一显式复形 + SimplexTree persistence。** 不做 edge collapse、不改点集或 filtration，目的是建立严格同输入对拍与实现成本比较。

**次基线：同一原始 VR 输入的 GUDHI 优化 PH 路径。** 在其适用条件下分别记录 edge collapse→expansion→persistence，或 `RipsPersistence` 的实际入口。edge collapse 文档保证适用 flag filtration 的 PH 保持，但不自动保证原始链坐标上的几何代表不变；`RipsPersistence` 也可能使用 Ripser 分支。[E5,E6]

次基线用于衡量用户完成 PH 任务的现实成本，不与“同一个链窗口”主基线混在一列，也不能用其修改后的几何代表代替本项目输出。次基线不得省略 collapse、expansion、距离构造或数据转换时间。

## 6. S4 测试与规模设计

### 6.1 correctness corpus

保留旧精确回归与反例；补充单纯形输入域中的空复形、孤立顶点、环及其填充、球面及三维填充、断连、多类、重复 filtration 值、重复 stage 和末端存活。覆盖 H0/H1/H2，H3 使用受控小实例。

原坐标重排、相同尺度批量插入、不同权重与不合法 AD≠0 分别测试。权重改变可影响选定 P/几何，但相同链与过滤的 topology 不应改变。含零长度的退化几何权重不能偷偷加 epsilon；可作为拒绝输入回归，或明确改用单位权的拓扑样本。

随机失败保留最小反例、seed、完整 manifest、两边结果和差异类别。每个精确可比样本要求 barcode 多重集与 rank 一致；不可比/不可用与 mismatch 分开。

### 6.2 性能 corpus

预先固定四类结构：小 Betti 的大链窗口、高 Betti 的链窗口、长过滤序列，以及中等规模的 VR/网格实例。精确权采用单位/整数/有理；实际欧氏浮点权单独列组，不用浮点结果冒充精确最优认证。

规模描述至少包括 `(dim C[k-1], dim C[k], dim C[k+1])`、各边界 nnz、消元 fill-in、rank、Betti 数、stage 数与查询量，不能只写点数。

先用确定性 pilot 确认不会整组立即超时的级别，然后冻结 manifest 和规模网格，再进行正式重复测量。pilot 与正式结果分别保存；不能运行后删掉不利样本。真实性能不要求把合成数据称作真实业务数据。

### 6.3 输出负载

| 负载 | 要求的结果 | 用途 |
|---|---|---|
| Topology readout | 从合法统一算子/算子族得到完整请求维数 barcode；不请求全部几何/最优 Γ | 与 GUDHI PH 总成本比较；不得走独立 PH 旁路 |
| Joint-basic | 同一对象的 barcode、预先声明的代表/质量/距离/支撑/跟踪查询 | 衡量本项目提供联合信息的实际成本 |
| Joint-certified | 声明 solver 的 Γ、bounds、证书与必需验证，再加相同查询 | 与相同认证级别的 reference 比较；GUDHI 无对应认证输出时不填伪比较值 |

Joint-basic 查询量建议按 0、1、8、64、1024 等级预先冻结，并区分已有算子上的 warm batch 与从输入开始的 cold 请求。query 输入合法性、生成方式和零类/非零类构成写入 manifest；必要的生成成本归入相应准备阶段。

## 7. 真实性能测量协议

### 7.1 时间边界

同时保存一个用户可见总计时和互不重叠的阶段计时：输入读取/转换、复形或边界构建、输入验证、消元/投影构造、solver 优化、必需独立验证、transport/barcode、几何查询、绑定转换和序列化。嵌套计时不直接相加；记录未分配的总开销，防止双计费。

共同复形上的 kernel 对照与原始点云开始的 end-to-end 对照分开。使用 GUDHI 构造输入再导出给本项目时，必须明确这是共享 frontend；本项目不能计时免费，GUDHI 却承担全流程。公开 headline 以可复现的 cold end-to-end 为主，warm/reuse 单列。

默认安全配置中的必需 validator 全部计入。开发期额外审计也单独记录，不把它与标准生产路径混用；如果发布路径确实还调用了审计，就必须计入该路径总成本。

### 7.2 内存与资源

时间测量关闭 tracemalloc、采样 profiler 和调试检查器；诊断运行另保存。内存实验使用独立 worker 的操作系统级峰值 RSS，记录测量方法、进程范围和单位；Python 分配峰值只作补充。[R7,E7]

绝对进程 RSS、可测的原生 workspace 峰值和输入大小分别保存。运行环境基线可以补充展示，不能把扣除后的代理量替代绝对峰值。没有可靠 RSS 采样时填缺失并说明原因，不填写 0，也不以 tracemalloc 代替。

每个配置冻结 wall time 与内存上限，进程级超限归类为 timeout/OOM/killed。库内资源耗尽与进程外强制终止分开，取消延迟另测。矩阵条目限额不是 RSS 硬上限；分配预算也不自动包含 Python 解释器和所有第三方分配。

### 7.3 重复与统计

建议从至少 10 个独立进程区组、每组 5 次有效重复开始；昂贵样本可采用预先声明的较少次数，不能不作说明。进程内预热不复用已完成 persistence 的输入对象作为 cold 结果。各实现运行顺序按固定 seed 随机化。

保存所有原始样本，主报告提供 median、IQR 与基于独立进程区组的配对置信区间。样本不足时不报告看似精确的尾分位。各实例先计算自身比值，再在同负载/同认证组聚合；不能只选最优一次，也不把 timeout 当作成功完成的耗时。

先单线程给出主结果；随后才单独报告并行吞吐量、线程数、并行层级和总 RSS，防止进程数×原生线程数的隐性过度并行。

### 7.4 结论口径

`T(reference)/T(native)`：仅用于相同 solver、认证、输入和输出的实现加速。

`T(operator topology)/T(GUDHI PH)`：表示为了通过本项目统一算子得到 PH 付出的相对成本，低于 1 才是这项负载下更快。

`T(Joint-basic)/T(GUDHI PH)`：表示不同输出集合之间的联合信息成本比，不命名为同功能加速比。额外几何的边际开销另通过本项目相同配置下的 Topology/Joint 两种负载分析；不假定它必然为正且可忽略测量噪声。

报告允许出现“本项目慢数倍”“只有重复查询时合算”“某个认证 solver 仍只能处理小规模”。S4 的通过标准是结论真实、输入可比、数据完整，而非必须赢过 GUDHI。

## 8. S4 工作包与产物

| 编号 | 工作 | 验收 |
|---|---|---|
| S4-01 | manifest 与双输入构造器 | simplex/filtration/boundary 身份可核对；无隐式改尺度 |
| S4-02 | GUDHI oracle adapter 与规范化 | 固定 F2/维数/重复 stage/末端规则；小实例全区间 rank 对拍 |
| S4-03 | correctness corpus、随机测试与反例归档 | mismatch=0 的范围精确声明；N/A、失败、中断单独统计 |
| S4-04 | 隔离进程 benchmark 与 RSS harness | 总成本、阶段成本、构建环境、原始样本与失败完整保存 |
| S4-05 | 冻结 corpus 正式运行与消融 | 使用冻结 S3 SHA；同 solver/认证分组；cold/warm/优化 GUDHI 基线分开 |
| S4-06 | 审计报告与一键复现入口 | 图表可追溯原始记录；复跑通过；不足与规模边界明确 |

拟议文档与产物（逐项有实际内容时才创建，不预建空目录）：

- `docs/S3_HIGH_PERFORMANCE_PLAN.md`：设计、支持域、依赖与验收。
- `docs/S4_GUDHI_VALIDATION_PLAN.md`：GUDHI 适配与规范化。
- `docs/S3_PERFORMANCE_REPORT.md`、`docs/S4_GUDHI_REPORT.md`：实际结果与限制。
- `benchmarks/s4/manifest.json`、`environment.json`、`raw.jsonl`、`summary.csv`：可复现证据。

每行原始记录至少含 repo SHA、source/fixture hash、输入规模、degree、stage、solver/config/certificate、query profile、backend/representation、build mode、依赖版本、CPU/OS/内存、线程数、trial、状态、总/分段时间、RSS、output hash 和 correctness 结果。

## 9. 推荐执行顺序

先冻结 S3-01 基线，并行制定 S4-01/02 的输入与对拍口径。随后完成 packed + 共享消元，再推进因子化投影/验证、solver/几何与过滤读取。每一阶段保留可独立运行的 reference 对照。最后冻结 S3 版本，运行 S4 正式大样本测量。

优先判断三个工程假设：**共享消元能否降低全链路成本；因子化是否在目标 β/n 区间节省时间和 RSS；相邻 transport 的区间分解能否在长过滤上消除全区间展开成本。** 这三项都有明确的正确性对照与否证条件。

本次调研产生了上述独立算法原型的有限正确性结果，没有产生新性能数字。下一项实际工程交付应当是冻结基线、最小原生纵向原型和可重放的测量入口，而非提前撰写加速结论。

## 来源

仓库引用均固定至 `54ce78bccdcba619ffa2a4d76aeb450bfd24270e`；文档中的旧“待合并”状态不作为当前合并事实依据。

[R1] [algebra.py](https://github.com/proffitteoy/homology-operator/blob/54ce78bccdcba619ffa2a4d76aeb450bfd24270e/src/homology_operator/algebra.py)

[R2] [solver.py](https://github.com/proffitteoy/homology-operator/blob/54ce78bccdcba619ffa2a4d76aeb450bfd24270e/src/homology_operator/solver.py)

[R3] [operator.py](https://github.com/proffitteoy/homology-operator/blob/54ce78bccdcba619ffa2a4d76aeb450bfd24270e/src/homology_operator/operator.py)

[R4] [validation.py](https://github.com/proffitteoy/homology-operator/blob/54ce78bccdcba619ffa2a4d76aeb450bfd24270e/src/homology_operator/validation.py)

[R5] [family.py](https://github.com/proffitteoy/homology-operator/blob/54ce78bccdcba619ffa2a4d76aeb450bfd24270e/src/homology_operator/family.py)

[R6] [result.py](https://github.com/proffitteoy/homology-operator/blob/54ce78bccdcba619ffa2a4d76aeb450bfd24270e/src/homology_operator/result.py)

[R7] [旧 BENCHMARKS.md](https://github.com/proffitteoy/homology-operator/blob/54ce78bccdcba619ffa2a4d76aeb450bfd24270e/docs/BENCHMARKS.md)

[R8] [旧 PHASE3_REPORT.md](https://github.com/proffitteoy/homology-operator/blob/54ce78bccdcba619ffa2a4d76aeb450bfd24270e/docs/PHASE3_REPORT.md)

[E1] [M4RI elimination 官方文档](https://malb.bitbucket.io/m4ri/echelonform_8h.html)

[E2] [Jacquard–Nanda–Tillmann, The Space of Barcode Bases for Persistence Modules](https://arxiv.org/html/2111.03700v2)

[E3] [GUDHI 3.13.0 SimplexTree 官方参考](https://gudhi.inria.fr/python/3.13.0/simplex_tree_ref.html)

[E4] [PyO3 performance 官方指南](https://pyo3.rs/v0.29.2/performance.html)

[E5] [GUDHI Rips complex 官方手册](https://gudhi.inria.fr/python/latest/rips_complex_user.html)

[E6] [GUDHI RipsPersistence 官方参考](https://gudhi.inria.fr/python/latest/rips_complex_sklearn_itf_ref.html)

[E7] [Python tracemalloc 官方文档](https://docs.python.org/3/library/tracemalloc.html)
