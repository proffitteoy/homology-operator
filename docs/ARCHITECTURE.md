# 架构与计算边界

理论来源固定为 `homology-operator-lab @ 6143729669902ee875b211b58085e954c76cdf88`。
算子的正式定义、完整证明、投影族和六边算例见[算子理论](MATHEMATICS.md)。
本文描述当前模块职责和必须保持的数学契约。调用方法见 [API](INTERFACE.md)，
状态、身份与快照见 [结果模型](RESULT_MODEL.md)，阶段状态见 [文档索引](README.md)。

## 数学对象

固定次数 k 的输入为有限带基链窗口与正坐标权重：

\[
C_{k+1}\xrightarrow{D}C_k\xrightarrow{A}C_{k-1},\qquad AD=0,\qquad w_i>0.
\]

参考构造选择 `AGA=A`、`DUD=D` 的广义逆，得到

\[
R=I+GA,\qquad Q=I+DU,\qquad P=QR,\qquad L=I+P.
\]

`HomologyOperator` 以同一个 P 提供拓扑、代表、质量、距离、支撑和 stretch：

```text
ChainWindow → ProjectionProblem → solver → ProjectionSolution
                                               ↓ 独立验证
                                        HomologyOperator
                                               ↓
                               拓扑 / 代表 / 几何 / stretch
```

查询不会另选代表或另跑 PH 来补充结果。合法性不依赖采用广义逆构造：所有 solver 输出都要验证
`P²=P`、`AP=0`、`PD=0`，以及循环基上 `z+Pz∈im(D)`。
前三项不够：非零同调窗口中的零投影可满足它们，却不保持同调。

## 当前对象与模块

| 文件 / 对象 | 职责 |
| --- | --- |
| [algebra.py](../src/homology_operator/algebra.py) / `Matrix` | 显式形状 F2 代数、稳定消元、核/像/solve；`CyclicAction` 提供限定结构族作用 |
| [chain.py](../src/homology_operator/chain.py) / `ChainWindow` | 校验次数、矩阵、带序基、`AD=0`、正权与算术；保留原坐标及输入来源 |
| [solver.py](../src/homology_operator/solver.py) | 请求、资源、能力匹配、五 reference solver 与求解记录；不定义读取语义 |
| [validation.py](../src/homology_operator/validation.py) | 独立验证投影和证书；求解、算子构造和外部恢复均使用该边界 |
| [operator.py](../src/homology_operator/operator.py) / `HomologyOperator` | 同 P 的单尺度读取、查询历史、stretch 和结果生成 |
| [family.py](../src/homology_operator/family.py) / `OperatorFamily` | 包含关系、transport、rank/barcode、几何追踪、族快照与重验 |
| [result.py](../src/homology_operator/result.py) | 六身份、`QueryResult`、单尺度结果、规范 JSON、内容 hash 和缓存边界 |
| [native.py](../src/homology_operator/native.py) | 可选扩展适配、显式可行构造、批查询、packed 代数与 `PreparedMatrix` |
| [native/src/](../native/src/) | safe Rust / PyO3 实现；单字宽构造与多字 packed 代数 |
| [tests/oracle/reference.py](../tests/oracle/reference.py) | 独立同调与 PH 测试 oracle；不能填充主结果 |

Python 包位于 `src/homology_operator/`，采用上述现有文件。
`examples/` 提供可运行用法，`tests/` 保留独立产品回归，`scripts/check_docs.ps1` 检查文档。

## 联合输出的身份与几何

每个结果绑定 `input_id`、`basis_id`、`weight_id`、`projection_id`、`operator_id` 和 `solver_run_id`。
同一算子的所有查询使用同一个 P；transport 还保存源与目标的身份。

几何依赖原链坐标和权重。基变换保持同调并不保证质量、支撑或 stretch 不变。
内容等价不自动允许混用两个独立 solver run 的查询；序列化与缓存规则见结果模型。

对循环 z 和 y：

\[
\operatorname{selected\_mass}(z)=m_w(Pz),\qquad
d_P([z],[y])=m_w(P(z+y)),\qquad m_w(x)=\sum_i w_i x_i.
\]

`selected_mass` 不等于真实最短类质量。`minimum_class_mass` 当前返回 Unavailable。
当前投影 Γ 的精确计算、最优 Γ 的 bounds、全局最优证书分别表达。
精确 F2 拓扑不意味着浮点几何或浮点 objective 精确。

原始 `project` / `apply_operator` 接受所有链；类代表、同类、几何查询默认拒绝非循环。
合法零、未计算、不可用、资源耗尽、空定义域和无类按 [结果模型](RESULT_MODEL.md) 区分。

## 有限过滤主路径

输入同次数的有限有序窗口、对应算子和 scales。`OperatorFamily` 由三个次数的基标识建立包含映射，
校验链映射、坐标与权重政策。重复 scale 保留阶段顺序，末端采用常量延拓。
不存在单独的公共 `FilteredChainComplex` 类型。

\[
\mathcal H_i=\ker L_i,\qquad T_{ij}=P_jJ_{ij}|_{\mathcal H_i}.
\]

传输保存源 kernel 坐标到目标 kernel 坐标的 action，以及到目标原链坐标的 chain_action。
合法阶段之间必须满足 `T_ii=I`、`T_jl T_ij=T_il`，且与原诱导同调映射共轭。
barcodes 从 `rank(T_ij)` 恢复；逐阶段 Betti 或外部 PH 配对不能替代传输来源。

barcode() 只读取相邻核坐标传输；历史区间基和完整 rank 表由显式查询请求，
按实际输出大小计算。算法不变量见下文。
任意类的 tracking 使用源代表、包含及目标投影；死亡类是合法零链、零质量和空支撑。
Partial 族保留失败阶段，不能以空链空间补齐缺失结果。

## 作用表示与 Rust 边界

| 表示 | 实际范围 |
| --- | --- |
| `Matrix` | reference 的显式 P/L；单字宽 `NativeFeasibleSolver` 也回传显式 G/U/P |
| `CyclicAction` | 已合并的固定 T-B1 结构族，m∈{2,3,4}；参数 handle，无完整 P 存储 |
| `PreparedMatrix` | 已合并的不可变多字 packed 消元 handle；复用 rank/kernel/image/membership/solve，独立于权重与投影选择 |
| `CompactAction` / `NativeFactorizedSolver` | 广义逆因子或 HC 表示，不物化完整 P/L |
| `GeometryWorkspace` | 已合并的六身份绑定准备对象，复用 Matrix / Factorized / HC 的循环几何批查询 |

多字代数已经存在；`NativeFeasibleSolver` 与 `apply_batch` 的显式构造仍有 64 维限制，
`geometry_batch` 另支持多字 Matrix 与 Factorized/HC。
reference 安装无需扩展；扩展缺失或 solver 不支持请求时，solver/批查询返回 Unavailable。
直接使用 packed 代数工具需要安装扩展，缺失时抛 ImportError。
原生几何对同一 packed Pz 做 XOR/AND/OR，整数质量使用 checked u64；
有理/大整数/溢出与浮点按算术政策显式后备，原因和成本在详情中可见。
workspace 不改变结果快照或查询历史；完整支持域见 API 的几何批查询章节。

作用表示改变不能改变全部链上的 P/L 行为，包括非循环延拓。
不同表示可以有不同内容身份；不要声称跨表示 hash 归一化。
紧凑表示仍须独立验证、身份绑定、恢复重验；A/D、核基输出和 transport 矩阵仍是显式对象。
API 不引入尚未存在的 `LinearAction` 基类、全流程稀疏 backend 或性能承诺。

## 验证、资源与测量

`solve_projection` 先匹配 capability 和请求配置，再独立验证返回结果；
`HomologyOperator` 构造和快照恢复再次验证。不能因为 solver 声称成功就跳过该边界。
优化证书另经独立重放，合法投影与最优认证分别报告。

资源限制是 solver checkpoint 的 state、wall time 和保守逻辑矩阵条目，
不是硬 RSS 上限、单步抢占或整个构造/恢复流程的统一预算。
未计算的 objective 不用 0 填充，中断只保留完成验证的候选与证据。

独立 PH reduction 和GUDHI 适配仅用于测试或测量对照。
禁止 oracle 填充 `OperatorResult`、补齐缺失 barcode 或替换当前 P 的代表。
正式性能比较必须包括绑定/转换、必需验证、查询、序列化及恢复，并匹配输入、P 与认证等级。

## 相邻映射与历史基

记 V_i=ker(L_i)、f_i=T(i,i+1)。活动向量按 birth 非降序排列，保持两个不变量：
它们是 V_i 的基；对于任意 b≤i，birth≤b 的前缀张成 im T(b,i)。
初始单位基出生于 0。按旧到新 birth 作用 f_i，保留独立像；被丢弃的像由更早前缀张成，
因此每个旧 birth 前缀的像空间保持。再按目标坐标次序补独立单位向量并标记在 i+1 出生，
得到目标的基。归纳后，j 阶段 birth≤b 的存活数等于 rank T(b,j)。
恰在 b 出生、d 死亡的重数为：

```text
r(b,d-1) - r(b-1,d-1) - r(b,d) + r(b-1,d)
```

负索引 rank 约定为 0；末阶段存活在 Constant 延拓下给出 death=None。
仅丢弃依赖像不足以生成历史基：当新向量的像由更早像组合表示时，
barcode_basis 在其全部活跃历史阶段加上同一组合，使死亡阶段的像为零。
这些更早向量的历史覆盖所需阶段，修改是可逆初等变换，保留历史基和逐阶段传输相容性。
该归纳适用于有限 F2 映射序列；重复 scale 不改变 stage 次序。
实现由独立全区间 rank、向量枚举、历史相容性与过滤 PH 回归验证。
