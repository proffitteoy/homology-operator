**S3 定为“同语义高性能开发”，S4 定为“GUDHI 对拍与真实性能报告”。第一轮源码调研已经完成，并做了一项独立的 barcode 读取算法验证。**

建议的主线是：**保留 Python reference，新增 Rust 后端，优先解决重复消元、显式投影存储和全区间 transport 展开；随后用 GUDHI 核对拓扑，并报告完整计算成本。**

[完整调研与开发计划（Markdown）](sandbox:/mnt/data/homology-operator-S3-S4-plan.md)
[调研包：计划、算法原型、原始验证记录](sandbox:/mnt/data/homology-operator-S3-S4-research.zip)

本次核查基于 `main @ 54ce78b`。没有修改 GitHub，也没有运行新的仓库性能 benchmark。仓库历史上的 `Phase 3` 仍指已有 solver/certification 工作，新 S3/S4 应另行命名，避免覆盖历史报告。

## 一、当前具体应该优化什么

从源码看，优化入口已经比较明确；下面是静态审查结果，实际耗时占比仍需 profiling。

| 当前路径             | 已确认的问题                               | S3 对应方向                      |
| ---------------- | ------------------------------------ | ---------------------------- |
| `algebra.py`     | 矩阵按 Python 整数逐元素运算，多个查询重复执行 `rref()` | 位压缩 F2、共享消元分解、多右端项求解         |
| `FeasibleSolver` | 显式生成广义逆及 \(n\times n\) 的投影，并进行矩阵乘法   | 先实现 packed 等价版本，再做因子化 action |
| `validation.py`  | 循环基逐向量求解边界归属；还有投影矩阵乘法验证              | 批量 membership、复用分解、独立因子证书    |
| `family.py`      | transport 逐列重解坐标；barcode 请求所有尺度区间    | 共享坐标分解、相邻 transport、区间分解     |

这些问题分别可以直接在矩阵实现、投影构造、验证器和过滤读取源码中定位。

还有一个必须纠正的性能口径：现有 `BENCHMARKS.md` 是**单次、启用 tracemalloc 的 solver 对照**，它自己也明确不提供稳健速度排名。其中记录的构造成本与完整验证、审计成本相差很大。因此 S3 的优化对象必须覆盖完整调用链，S4 也不能沿用这些数据作为正式性能结论。

## 二、S3：高性能开发路线

### 1. Rust 核心保留现有数学与 Python 接口

建议首轮采用 **safe Rust、`Vec<u64>`、单线程基线，以及批量 Python 绑定**。Python reference 保持独立，继续承担数学对拍；原生热循环不再逐元素往返 Python。绑定层可以使用 PyO3，但具体版本在构建原型中锁定，转换成本必须单独测量。PyO3 官方性能指南也明确讨论了跨解释器边界和长时间原生计算的处理。([PyO3][1])

首轮不同时铺开 GPU、显式 SIMD、多层并行和多个原生后端。先确认普通位压缩与算法复用的收益，再考虑更低层优化。

### 2. 先消除重复消元

增加一个内部可复用的消元分解，让同一份分解支持 `rank`、核与像、边界归属、单次求解和多右端项求解。

这里必须保持原坐标、稳定 pivot 顺序和并列策略。不能因为新的消元过程得到相同 Betti 数，就认定它与旧投影等价。

后续密集块优化可以参考 M4RI 的分块消元、PLE/PLUQ 和 Four Russians 方法；普通 packed 消元应先成为可对照基线。([Malb][2])

### 3. 让投影以因子化方式执行

当前公式允许直接计算作用：

\(Rx=x+GAx\)，然后 \(Px=Rx+DU(Rx)\)，最后 \(Lx=x+Px\)。

因此，建议逐步把广义逆表示成消元操作或可复用求解 action，减少默认物化完整 \(G,U,P,L\) 的需求。这是在现有构造公式上改变执行方式。

在 Betti 数 \(\beta\) 较小时，再研究保持同一个 \(P\) 的低秩表示 \(P=HC\)，其中 \(H\) 为 \(n\times\beta\)，\(C\) 为 \(\beta\times n\)。单看表示规模，可以从 \(n^2\) 位转为约 \(2n\beta\) 位；是否真正省内存，还要计入分解、证书、输入和缓存。

**这一优化必须保持全部链上的 action，包括非循环上的延拓。** 只有同调相同、barcode 相同，仍不足以说明代表、距离、支撑和原始 `project` 语义相同。现有 API 本来就将原始 action 与仅接受循环的同调类查询分开。

### 4. 验证器、身份与序列化一起优化

不能只把 solver 改快，仍让 validator 用旧稠密算法重新算一遍。

优先做批量边界归属验证、复用目标坐标分解，再研究独立验证因子恒等式。重复验证的去重，需要不可变对象、完整内容身份及明确的验证来源；外部输入和反序列化恢复仍须重验。

新表示也必须接入身份与序列化协议。当前 `projection_id` 绑定 action 的具体内容，新后端不能为了算 hash 又偷偷展开整个 \(P\)，也不能强迫不同表示使用相同身份。

### 5. 过滤读取是另一条重点优化线

当前 `barcode()` 会遍历全部 \(i\le j\) 区间，每个区间又可能构造 chain action、求坐标并求秩。长过滤下，这部分值得单独处理。

建议改为研究：

**共享边界与尺度索引 → 相邻 transport → 区间分解 → 任意区间查询按需计算。**

PH 仍然由同一算子族的传输读取，原来的全区间 rank 公式保留为小规模 oracle。《The Space of Barcode Bases for Persistence Modules》提供了直接处理线性映射序列并追踪基变换的方法，但其算法仍有过滤长度的二次复杂度项，不能直接拿来宣称线性加速。([arxiv.org][3])

**这一方向我额外做了一个独立原型验证。** 原型只维护按出生时间排序的当前基，应用相邻映射后保留独立像、记录死亡，再补入新出生方向。它与独立的“完整像集枚举 → 全区间 rank → barcode”方法对拍：

| 检查                           |        实际结果 |
| ---------------------------- | ----------: |
| 源、目标维数均为 0–3 的两阶段映射穷举        |       689 例 |
| 随机映射序列，1–9 个 stage、各空间维数 0–6 |     5,000 例 |
| 总计                           | **5,689 例** |
| barcode 不一致                  |     **0 例** |

原型、seed 和原始结果已经放入调研包。**它是有限正确性证据，不是性能结果，也没有验证本仓库的几何跟踪、solver 或序列化集成。**

### 6. solver 必须分两条性能线

**一般规模线**优化合法投影、精确 F2 topology 与同一 \(P\) 的基本几何查询；未计算的伸长和最优证书继续明确缺失。

**认证求解线**在原支持域内优化 Exhaustive、Greedy、Rank2、Structured，并保持相同质量和认证等级。现有完整搜索有 \(2^{\operatorname{rank}(D)\beta}\) 个候选，Greedy 和部分证书重放也含指数枚举。Rust 可以降低常数，不能被当作已解决一般最优求解的可扩展性。

这两条线都属于 S3，但报告不能把它们混成“高性能最小伸长算法”。

## 三、S4：GUDHI 对拍怎么做

### 对拍应当分清验证对象

**Native ↔ Python reference** 核对完整联合输出：投影、代表、质量、距离、支撑、transport、barcode、认证、状态和恢复行为。

**Native ↔ GUDHI** 核对同一个 filtered simplicial complex 上的 F2 Betti、barcode 多重集和区间 rank。

**一般 AD=0 链窗口**继续由独立代数 verifier 核查。没有真实 SimplexTree 适配的输入，标记为不适用，不能换成另一组点云假装完成同输入对拍。GUDHI 的 SimplexTree 接口面向过滤单纯复形，其 persistence 配对也不能自动作为本项目全部几何查询和伸长认证的真值。([GUDHI library][4])

### 统一输入与参数

建议冻结一份包含 simplex、出生 stage、原始 scale、坐标标识及权重的 manifest，由它分别生成两边输入，并重新导出检查实际构造结果。

主正确性入口显式使用 F2。GUDHI 官方参考中的默认系数域是 11，而且默认不计算复形的最大维同调，不能依赖默认参数。计算 H2 时，也要保证共同输入具有所需的三维单形；打开最大维选项不会补回缺失的四面体。([GUDHI library][5])

对于仓库已有的重复尺度语义，建议先用**整数 stage 编号**对拍。不同 stage 即使物理 scale 相等，仍保留其阶段区间；同一 stage 内的零长度配对则按统一规则处理。这样不会在浮点尺度或重复值规范化中丢掉参考实现保留的信息。

### GUDHI 主基线与优化基线分开

主基线采用**同一显式复形 + SimplexTree persistence**，不做会改变链坐标的预处理。

另外可以报告同一原始 VR 输入上的 GUDHI 优化路径，例如 edge collapse 后再 expansion。还需要区分 `RipsPersistence`，因为它可能使用 Ripser 分支。两类结果都应记录真实入口；修改复形后的 PH 保持，不自动意味着原始几何代表保持。([GUDHI library][6])

## 四、S4 的“真实性能”必须回答什么

我建议冻结三类负载，而不是只做一个总耗时排行榜：

| 负载               | 实际请求                              | 如何解释                  |
| ---------------- | --------------------------------- | --------------------- |
| Topology readout | 经合法统一算子得到完整请求维数的 barcode          | 与 GUDHI PH 成本比较       |
| Joint-basic      | barcode 加预先声明的代表、质量、距离、支撑与跟踪查询    | 衡量联合信息的实际成本           |
| Joint-certified  | 同类查询加指定 solver 的 Γ、bounds、证书及必需验证 | 与相同认证等级的 reference 比较 |

其中 Topology readout 也不能绕开算子，偷偷运行另一套 PH。

正式报告同时给出冷启动端到端时间、已有算子上的批量查询时间、构造与验证等分段成本，以及进程峰值 RSS。时间实验与 profiler/tracemalloc 诊断分开；Python 分配峰值不能代替操作系统级 RSS。([Python documentation][7])

所有结果绑定源码 SHA、fixture hash、solver/认证、构建模式、机器、线程数和查询量。超时、OOM、资源耗尽、不可用和不适用分别保留，不能只汇总成功样本。

最后应明确区分两种比值：

**reference/native** 可以表示同输出、同认证的实现加速；**Joint-basic/GUDHI PH** 表示为额外联合信息付出的成本，不能命名为同功能加速比。

因此，S4 可以得出“比 GUDHI 慢”“只在大量重复查询时划算”“某个认证 solver 仍只能处理小规模”。这些都是合格结果，前提是输入可比、测量完整、结论可复现。

## 五、实际开发顺序

完整文档已经拆成 **9 个 S3 工作包和 6 个 S4 工作包**。主依赖顺序建议固定为：

**冻结基线 → packed F2 与共享消元 → 因子化投影及独立验证 → solver/几何批量查询 → 过滤读取 → 集成收口 → GUDHI 正式对拍与性能报告。**

S4 的 manifest、参数规范和小样本 oracle 应与 S3 并行准备，避免后端写完才发现对拍输入不一致。

**S3 的验收是同语义下获得可复现的端到端或内存改善；S4 的验收是完整、可复现地报告正确性与实际性能。** 当前最值得优先验证的三个工程假设，就是共享消元、因子化投影，以及避免 barcode 默认展开全部区间。

[1]: https://pyo3.rs/v0.29.2/performance.html "https://pyo3.rs/v0.29.2/performance.html"
[2]: https://malb.bitbucket.io/m4ri/echelonform_8h.html "https://malb.bitbucket.io/m4ri/echelonform_8h.html"
[3]: https://arxiv.org/html/2111.03700v2 "The Space of Barcode Bases for Persistence Modules"
[4]: https://gudhi.inria.fr/python/3.13.0/simplex_tree_ref.html "https://gudhi.inria.fr/python/3.13.0/simplex_tree_ref.html"
[5]: https://gudhi.inria.fr/python/latest/simplex_tree_ref.html "https://gudhi.inria.fr/python/latest/simplex_tree_ref.html"
[6]: https://gudhi.inria.fr/python/latest/rips_complex_user.html "https://gudhi.inria.fr/python/latest/rips_complex_user.html"
[7]: https://docs.python.org/3/library/tracemalloc.html "https://docs.python.org/3/library/tracemalloc.html"
