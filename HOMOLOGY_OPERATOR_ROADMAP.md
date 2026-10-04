# Homology Operator：工程架构与分阶段开发路线

> 适用仓库：`proffitteoy/homology-operator`  
> 冷启动前本地基线：`main @ 6ddce1b4e4d55c0aaff399c001e684d908026830`（2026-10-01 核实）  
> 合并的远端契约基线：`main @ c0299c3b7750c8a12ced00bf479753236a7dbc85`（2026-10-01 在线核实）
> 理论来源：`proffitteoy/homology-operator-lab @ 6143729669902ee875b211b58085e954c76cdf88`

> 本文是阶段目标与退出条件，不是安装说明或当前 API 清单。Phase 1–3 的 `54ce78b` / 129 项数学测试保留为历史验收基线；S4-01–04 已合并，当前 main/CI 与本地开发边界见 [文档索引](docs/README.md)。Phase 4 完整集成和验收、Phase 5–7 仍有未完成目标。私有 [Project #3](https://github.com/users/proffitteoy/projects/3) 管理 [S4/S5](docs/S4_S5_PROJECT.md)：S4 同语义高性能开发、S5 GUDHI 对拍与真实性能报告，细化本路线的 Phase 4；不覆盖历史 Phase 3 的 solver/certification 或旧 S3 编号。

## 1. 文档目的

本项目不是“先计算 Persistent Homology，再附加几何特征”的流水线，也不是把 PH、最短代表、距离、支撑分别交给不同算法后拼接结果。

项目的核心对象从一开始就是统一的二元同调算子。对每个尺度、次数，输入链复形局部数据与权重

\[
C_{k+1}\xrightarrow{D}C_k\xrightarrow{A}C_{k-1},
\qquad AD=0,
\qquad w>0,
\]

构造

\[
R=I+GA,
\qquad
Q=I+DU,
\qquad
P=QR,
\qquad
L=I+P.
\]

之后所有拓扑与几何信息都从同一投影身份读取：

\[
\boxed{
(A,D,w)\longrightarrow (P,L)\longrightarrow
\begin{cases}
\text{Homology / PH readout},\\
\text{Representative readout},\\
\text{Metric / support readout},\\
\text{Stretch / certificate readout}.
\end{cases}}
\]

因此，下面的“阶段”表示工程成熟度和验证门槛，不表示运行时必须依次执行若干彼此独立的数学模块。

---

## 2. 不可破坏的架构不变量

下面这些约束应当视为整个仓库的工程宪法。后续性能优化、后端替换、并行化和生态接入都不得破坏。

### 2.1 单一投影身份

每个阶段、次数的结果必须绑定同一个投影身份：

- `projection_id`
- `operator_id`
- `basis_id`
- `weight_id`
- 输入边界矩阵与坐标顺序
- solver / certificate provenance

PH、代表、质量、距离、共享支撑和伸长信息不得分别来自不兼容的求解结果。

### 2.2 PH 是算子族的读取，不是前置输入

调用者不得被要求先提供：

- PH barcode；
- 同调基；
- 每个同调类的最短代表；
- 预先计算的 persistence pairing。

这些信息若需要，必须由算子或算子族内部结构派生。

独立 PH reduction 只允许作为测试 oracle、回归基线和性能对照，不允许偷偷进入主结果对象。

### 2.3 拓扑与几何共同依赖原始链坐标

基变换不改变同调，但几何量依赖：

- 原链基；
- 权重；
- 投影选择；
- 跨尺度权重继承规则。

因此几何输出必须保留 provenance，不能把仅在某个坐标系统下成立的质量或支撑解释为无条件内禀量。

### 2.4 精确拓扑不得静默近似

资源不足时：

- 可以返回 `resource_exhausted`；
- 可以返回某个几何优化的上下界；
- 可以返回启发式投影并明确认证等级；

但不能把近似或未验证的 persistence 结果伪装成精确 PH。

### 2.5 “选定代表”与“最短代表”严格分离

一般情况下

\[
m_w(Pz)
\]

只是当前线性截面选择出的代表质量，不等于该类真实最短质量

\[
\mu_w([z]).
\]

所有 API、文档和 benchmark 必须严格区分：

- selected representative mass；
- exact minimum class mass；
- certified lower / upper bound；
- stretch ratio / stretch certificate。

---

# 3. Phase 0：冻结数学—工程契约

## 3.1 目标

在写高性能代码以前，先把理论对象转成不会随实现变化而漂移的工程契约。

冷启动前工作区已提供 `ARCHITECTURE.md`、`RESULT_MODEL.md` 和 `SOLVER_CONTRACT.md`；根 README 缺失，`INTERFACE.md` 与 `VALIDATION.md` 尚未建立。本次初始化补齐了这些入口，形成逻辑契约；fixture corpus、语言 API 与运行时验证尚待首次 reference 实现落地。

## 3.2 应完成的文档

现有核心契约：

```text
/docs/ARCHITECTURE.md
/docs/RESULT_MODEL.md
/docs/SOLVER_CONTRACT.md
```

其中：

### `ARCHITECTURE.md`

定义：

- 单尺度算子对象；
- 过滤上的算子族；
- `P`、`L`、transport 的关系；
- 主计算路径与 oracle 路径的边界；
- 后端替换不得破坏的 invariants。

### `RESULT_MODEL.md`

定义一个结果对象中必须携带的身份与状态：

```text
OperatorResult
├── input_identity
├── projection_identity
├── P / matrix-free action
├── L / matrix-free action
├── algebraic_certificate
├── topology_view
├── geometry_view
├── stretch_view
└── provenance
```

### `SOLVER_CONTRACT.md`

规定不同 solver 的共同返回语义：

```text
ProjectionSolution
├── status
├── projection
├── objective
├── lower_bound
├── upper_bound
├── certificate
├── method
└── resource_usage
```

## 3.3 退出条件

Phase 0 完成的判据不是“文档很多”，而是以下问题均有唯一答案：

1. 什么对象代表一次完整计算？
2. PH 和几何输出如何证明来自同一个投影？
3. 什么时候可以声称“exact optimal”？
4. 什么时候只能声称“feasible”或“heuristic”？
5. 哪些状态必须与合法零值区分？
6. 哪些量对基、权重或尺度延拓规则敏感？

---

# 4. Phase 1：单尺度统一算子的可复现参考实现

## 4.1 目标

实现第一个真正可执行的 `HomologyOperator`。

这一阶段不追求速度，也不追求一般最优投影；目标是让理论定义逐项对应到代码，并保证同一个算子对象已经能够联合产生拓扑与几何读取。

## 4.2 核心输入

```text
ChainWindow
├── C_{k+1}, C_k, C_{k-1}
├── D : C_{k+1} -> C_k
├── A : C_k -> C_{k-1}
├── basis metadata
├── positive weights w
└── validation policy
```

必须验证：

\[
AD=0.
\]

输入错误必须在构造阶段失败，而不是在后续查询时产生不可解释结果。

## 4.3 核心构造

参考实现至少能够：

1. 构造满足

\[
AGA=A
\]

的广义逆 `G`；

2. 构造满足

\[
DUD=D
\]

的合法 `U`；

3. 构造或提供矩阵自由作用：

\[
R=I+GA,
\quad
Q=I+DU,
\quad
P=QR,
\quad
L=I+P.
\]

第一版可以显式矩阵化，后续再切换到 matrix-free backend。

## 4.4 一个对象内的联合读取

第一版 `HomologyOperator` 至少暴露：

```text
project(z)              -> Pz
apply_operator(x)       -> Lx
kernel_basis()          -> ker(L)
betti()                 -> dim ker(L)
is_cycle(z)
is_boundary(z)
same_class(z, y)
mass_of_projection(z)
class_distance(z, y)
support_of_projection(z)
shared_support(z, y)
union_support(z, y)
projection_metadata()
certificate()
```

这些 API 不是不同数学模块的结果拼接，而是对同一 `P/L` 的不同查询。

## 4.5 必须验证的代数不变量

对所有 reference fixture，显式检查：

\[
P^2=P,
\qquad
L^2=L,
\]

\[
AP=0,
\qquad
PD=0.
\]

对循环 `z`：

\[
z+Pz\in \operatorname{im}D.
\]

并验证：

\[
Pz=0
\iff
[z]=0,
\]

以及对循环 `z,y`：

\[
Pz=Py
\iff
[z]=[y].
\]

## 4.6 几何读取的验证

对循环 `z,y`：

\[
d_P([z],[y])=m_w(P(z+y)).
\]

验证：

- 非负；
- 同类当且仅当距离为零；
- F2 加法下的对称性；
- 共享支撑和总支撑与直接坐标计算一致；
- 质量与支撑权重求和一致。

## 4.7 测试对象

应从研究仓库迁移足够小、可手算的：

- 零同调；
- 单洞；
- 多洞；
- 非平凡边界；
- H0 / H1 / H2 / H3；
- 空链空间；
- 人工正权；
- 真实长度 / 面积 / 体积权重实例。

## 4.8 退出条件

Phase 1 完成时必须可以说：

> 给定一个有限 F2 链窗口及正权重，本仓库能够从边界数据构造一个可验证的统一同调算子，并从同一投影读取其同调表示与配套几何信息。

此时还不能声称：

- 已高效；
- 已得到一般最小伸长投影；
- 已支持完整 filtration；
- 已有稳定性结论。

---

# 5. Phase 2：过滤上的算子族与完整 Persistence 读取

## 5.1 目标

从“一个算子”推广为“一个算子族”，而不是添加一个独立 PH 子系统。

对过滤

\[
K_0\subseteq K_1\subseteq\cdots\subseteq K_N,
\]

每个尺度和次数都有：

\[
P_i,
\qquad
L_i=I+P_i,
\qquad
\mathcal H_i=\ker L_i.
\]

跨尺度结构由

\[
T_{ij}=P_jJ_{ij}|_{\mathcal H_i}
\]

给出。

整体对象应抽象为：

```text
OperatorFamily
├── stages[]
├── transports
├── rank queries
├── barcode readout
└── class tracking
```

## 5.2 Filtration 输入契约

至少支持：

- 有序有限尺度；
- 第一版过滤包含映射；
- 明确的末端延拓约定；
- 坐标身份与包含关系；
- 跨尺度权重继承信息。

以后可以推广到一般链映射，但第一版不应同时扩大所有边界。

## 5.3 Transport 必须满足

验证：

\[
T_{ii}=I,
\]

\[
T_{j\ell}T_{ij}=T_{i\ell}.
\]

并检查其与原诱导同调映射共轭。

## 5.4 Persistence 读取

从

\[
r(i,j)=\operatorname{rank}T_{ij}
\]

恢复 barcode。

重要原则：

- 不允许仅凭逐尺度 Betti 数猜 barcode；
- 不允许先运行独立 Ripser/GUDHI 再把结果塞回 OperatorFamily；
- 独立 PH 实现只作为测试 oracle。

## 5.5 跨尺度几何读取

同一个算子族还应支持：

```text
track_class(x, i, j)
track_mass(x, i, j)
track_support(x, i, j)
transport_certificate(i, j)
```

对于继承权重，应验证理论中的终点伸长控制。

因此 Phase 2 的目标不是“终于有 PH”，而是：

\[
\boxed{
\text{同一个 OperatorFamily 同时携带 persistence 与代表演化。}
}
\]

## 5.6 Oracle 对拍

对小型 fixture：

- barcode 与标准 PH reduction 一致；
- rank invariant 一致；
- birth / death / essential class 一致；
- 重复尺度和末端存活约定一致。

## 5.7 退出条件

Phase 2 完成后可以正式声称：

> 算子族在有限单参数过滤上恢复完整 Persistent Homology module，并同时提供与同一投影族绑定的几何代表演化信息。

---

# 6. Phase 3：投影求解器与认证体系

## 6.1 目标

前两个阶段回答“一个合法算子是什么、它能读出什么”。

Phase 3 开始回答真正困难的问题：

> 在所有合法线性同调截面中，应该选择哪个投影？

核心目标是

\[
\Gamma_*(A,D,w)
=
\min_{P}\Gamma_w(P).
\]

## 6.2 Solver 必须与 Operator 分离

推荐接口：

```text
ProjectionSolver
    solve(problem) -> ProjectionSolution
```

然后：

```text
ProjectionSolution
    -> HomologyOperator
```

`HomologyOperator` 不应知道投影是通过穷举、结构公式、贪心还是启发式获得的；它只消费一个带认证信息的合法解。

## 6.3 Solver 层级

建议逐步实现：

### A. Feasible solver

只要求得到合法投影。

用途：

- reference implementation；
- 正确性验证；
- fallback。

### B. Exhaustive exact solver

仅面向小规模实例。

用途：

- 产生 ground truth；
- 验证其他 solver；
- 建立 regression corpus。

不得包装成通用高效算法。

### C. Greedy certified solver

实现理论上的通用上界，例如基于 Betti 数的可证明近似构造。

返回：

- feasible objective；
- 已知理论上界；
- certificate level。

### D. Rank-2 exact / specialized solver

利用秩二特殊结构、Pareto 消去和相应精确归约。

这是第一个真正值得单独优化的结构 solver。

### E. Structured family solver

对研究仓库已经给出显式结构的族，直接使用结构公式或快速作用，不必回退到一般搜索。

### F. General approximate / search solver

只有在前述基线全部稳定后，再研究：

- branch-and-bound；
- MILP / SAT / combinatorial search；
- parameterized algorithms；
- local improvement；
- approximation schemes；
- problem-specific heuristics。

## 6.4 认证等级

认证等级（以 `SOLVER_CONTRACT.md` 为准）：

```text
Feasible
ExactOptimal
CertifiedUpperBound
CertifiedInterval
Heuristic
```

求解状态单独记录 `Solved`、`FeasibleOnly`、`ResourceExhausted`、`Unavailable`、`InvalidProblem`、`NumericalFailure`、`InternalError`。状态与认证等级可以组合，不能把资源耗尽或后端不可用当成认证等级。

推荐结果至少包含：

```text
objective
lower_bound
upper_bound
optimality_gap
certificate
method
runtime
memory
```

## 6.5 退出条件

Phase 3 完成后，用户必须能够明确知道：

- 当前投影是否合法；
- 是否全局最优；
- 若非最优，有什么上下界；
- 结果是否来自启发式；
- 资源不足发生在哪里。

任何数值都不能脱离认证等级单独报告。

2026-10-02的本地实现证据见 [Phase 3联合验收](docs/PHASE3_REPORT.md) 与 [对照/no-go协议](docs/BENCHMARKS.md)。Reference明确支持精确整数/有理的五类构造，浮点仅可行与数值读取；证书和失败分别表达，一般搜索本轮不准入。129项本地测试、隔离wheel和文档检查不替代合并门槛：全部原PR准确head进入main后，重新核对main数学测试与CI，再按Phase 4目标选择语言和性能实验。

---

# 7. Phase 4：同语义高性能实现

## 7.1 目标

在不改变 Phase 0–3 语义的前提下，把 reference operator 替换或补充为高性能后端。

核心原则是：

> 优化实现，而不是重新定义问题。

## 7.2 优化维度

分别测量：

1. 输入验证；
2. F2 消元；
3. 广义逆 / 合法投影构造；
4. solver 时间；
5. `Pz` 查询；
6. kernel 查询；
7. transport；
8. rank 查询；
9. barcode recovery；
10. support / distance 查询；
11. serialization；
12. peak RSS。

不要只给“总耗时”，否则无法知道瓶颈来自算子构造还是优化问题。

## 7.3 数据结构演化

可逐步从：

```text
Dense reference matrices
```

演化到：

```text
Bit-packed F2 columns
Sparse boundary structures
Matrix-free projection actions
Cached elimination state
Prepared filtration workspace
Batch query workspace
```

## 7.4 后端语言

这一阶段才需要正式锁定高性能核心语言。

推荐保持：

```text
Stable mathematical contract
        ↓
Reference backend
        ↓
Optimized backend
        ↓
Bindings / integrations
```

而不是让语言或生态先决定数学 API。

如果采用 Rust，Rust core 应实现既有 contract，而不是重新设计一套与 reference 不一致的对象。

## 7.5 Benchmark 规范

每个 benchmark 必须绑定：

- git revision；
- fixture hash；
- compiler / interpreter；
- build mode；
- machine；
- thread count；
- solver level；
- exact / approximate status；
- peak RSS；
- query mix。

严禁把 exact solver 和 heuristic solver 的耗时直接当作同等级性能比较。

## 7.6 退出条件

Phase 4 完成的标准不是“比某个库快”，而是：

> 在冻结的联合输出语义和认证等级不变的情况下，高性能后端与 reference backend 逐项同输出，并在目标规模上具有可复现的性能数据。

---

# 8. Phase 5：稳定性与离散几何有效性

## 8.1 目标

解决固定有限链复形之外的问题。

此前的代数正确性不能自动推出：

- 点云重采样稳定；
- 网格细化稳定；
- 几何代表在不同 triangulation 下可比较；
- 人工链权能够逼近连续几何量。

这些都必须作为独立研究问题处理。

## 8.2 研究问题

至少需要分别研究：

### 网格族稳定性

给定细化序列

\[
K_0\prec K_1\prec K_2\prec\cdots,
\]

确定：

- 同调类对应；
- 权重继承；
- 投影对应；
- 代表质量是否收敛；
- support 如何比较。

### 采样稳定性

对点云输入，需要明确：

```text
point cloud
   ↓
filtration construction
   ↓
chain weights
   ↓
operator family
```

每一步扰动如何传播。

### 几何语义

区分：

- 单位权；
- 人为正代价；
- 欧氏边长；
- 面积；
- 体积。

只有在明确的几何实现与恢复条件下，才能把链质量解释为连续几何量的离散近似。

## 8.3 退出条件

任何“stable”“geometric”“mesh-independent”之类的公开表述，都必须指向明确的定理、假设或实验协议。

---

# 9. Phase 6：真实任务价值验证

## 9.1 目标

回答最终最重要的工程问题：

> 相比只使用 PH，这个统一算子额外付出的计算成本，换来了多少可用信息？

## 9.2 基线

至少比较：

1. PH only；
2. PH + 常见简单几何统计；
3. 其他带代表或谱信息的方法；
4. Homology Operator joint output。

所有方法必须在相同数据、相同预算、相同训练/评估协议下比较。

## 9.3 评估维度

不仅看下游准确率，还应看：

- 信息增益；
- 鲁棒性；
- 可解释性；
- 查询成本；
- 构造成本；
- 内存；
- 对噪声、重采样和尺度变化的敏感性。

## 9.4 合适的应用方向

优先选择真正会利用“代表几何”的任务，而不是为了展示 barcode 再跑一次分类器。

例如：

- 同一 Betti / barcode 下的几何形态区分；
- 洞代表位置、长度、重叠模式发生变化的动态数据；
- 多尺度结构追踪；
- 需要解释“哪个具体链支撑了拓扑信号”的任务。

## 9.5 退出条件

只有这一阶段完成后，项目才适合对外宣称“额外几何输出在某类真实任务中具有实证价值”。

---

# 10. Phase 7：发行与生态集成

## 10.1 目标

在数学语义、正确性、认证等级和性能都稳定后，再冻结公共 API 并进入生态。

## 10.2 可能的发行层

最终可以形成：

```text
Core library
├── F2 algebra
├── HomologyOperator
├── OperatorFamily
├── Solver framework
└── certificates

Bindings
├── Python
└── other language bindings

Integrations
├── point-cloud / filtration frontend
├── dataframe / analytical workflows
└── TDA ecosystem adapters
```

生态适配器必须建立在统一结果对象上，不能因为某个平台只需要 barcode 就绕开核心算子重新计算一遍 PH。

## 10.3 发布前条件

- LICENSE 明确；
- API versioning 明确；
- CI 建立；
- reference / optimized backend 对拍；
- 文档标清 exact / approximate；
- fixture corpus 固定；
- benchmark protocol 固定；
- 失败状态稳定；
- serialization schema 稳定。

---

# 11. 历史目录建议（非当前源码结构）

以下保留实现前的目录设计建议，不要求按图拆分文件或预建目录。当前 Python 包采用 `src/homology_operator/` 的现有模块，可选 Rust 位于 `native/`；实际职责和路径见 [ARCHITECTURE](docs/ARCHITECTURE.md)。目录调整仍以实际数学需求和最小修改为准。

```text
homology-operator/
├── README.md
├── docs/
│   ├── INTERFACE.md
│   ├── VALIDATION.md
│   ├── ARCHITECTURE.md
│   ├── RESULT_MODEL.md
│   ├── SOLVER_CONTRACT.md
│   └── BENCHMARKS.md
│
├── src/
│   ├── algebra/
│   │   ├── f2
│   │   ├── elimination
│   │   └── linear_maps
│   │
│   ├── chain/
│   │   ├── complex
│   │   ├── basis
│   │   └── weights
│   │
│   ├── operator/
│   │   ├── construct
│   │   ├── action
│   │   ├── result
│   │   ├── readout
│   │   └── certificate
│   │
│   ├── filtration/
│   │   ├── family
│   │   ├── transport
│   │   └── barcode
│   │
│   ├── solver/
│   │   ├── feasible
│   │   ├── exhaustive
│   │   ├── greedy
│   │   ├── rank2
│   │   └── structured
│   │
│   └── api/
│
├── tests/
│   ├── fixtures/
│   ├── algebra/
│   ├── operator/
│   ├── filtration/
│   ├── solver/
│   ├── regression/
│   └── oracle/
│
└── benches/
```

这里故意不设计彼此独立的：

```text
src/homology/
src/geometry/
src/persistence/
```

因为那种目录结构容易把一个统一算子重新拆成三个独立计算内核。

`barcode` 可以存在于 `filtration/` 中，但其职责只是从 OperatorFamily 的 transport/rank 信息读取 persistence，而不是拥有另一套 PH 算法。

---

# 12. 推荐公共对象关系

```text
ChainWindow
    │
    ▼
ProjectionProblem
    │
    ▼
ProjectionSolver
    │
    ▼
ProjectionSolution
    │
    ▼
HomologyOperator
    │
    ├── topology readout
    ├── representative readout
    ├── metric readout
    ├── support readout
    └── stretch readout

FilteredChainComplex
    │
    ▼
OperatorFamily
    │
    ├── HomologyOperator[i]
    ├── T_ij
    ├── rank invariant
    ├── barcode readout
    └── geometric class tracking
```

这是整个项目最重要的软件结构图。

---

# 13. 版本里程碑建议

以下是开发目标，不是已发布版本清单。当前包元数据仍为 `0.0.2.dev0`，已包含后续阶段功能；阶段完成不自动改包版本或创建发行。项目已采用 [MIT License](LICENSE)；公开发行前需另行确定 API/schema 兼容政策与发布流程。

## v0.0.1 — Contract Freeze

- ARCHITECTURE / RESULT_MODEL / SOLVER_CONTRACT；
- fixture schema；
- 状态与认证等级冻结。

## v0.0.2 — Single-Scale Reference Operator

- 单尺度 `P/L`；
- 完整联合读取；
- 代数不变量测试；
- 小规模 oracle 对拍。

## v0.0.3 — Operator Family

- filtration；
- `T_ij`；
- composition；
- rank invariant；
- barcode recovery；
- 跨尺度代表追踪。

## v0.0.4 — Solver Framework

- feasible；
- exhaustive exact；
- greedy certified；
- rank-2 / structured solver；
- 统一 certificate。

## v0.0.5 — Optimized Backend

- bit-packed / sparse / matrix-free；
- reference backend 同输出；
- benchmark protocol。

## v0.0.6 — Stability Experiments / Theory Interface

- mesh / sampling protocol；
- 权重与几何语义；
- 稳定性实验与理论接口。

## v0.1.0 — First Public Research Release

必须满足：

- 统一算子语义稳定；
- 单尺度与 filtration 均可运行；
- solver 认证等级稳定；
- reference 与 optimized backend 对拍；
- 文档和 benchmark 完整；
- LICENSE / CI / packaging 完成。

---

# 14. 当前最优先的实际开发顺序

从当前仓库状态看，建议严格按以下顺序执行：

```text
P0. 冻结 ARCHITECTURE / RESULT_MODEL / SOLVER_CONTRACT
        ↓
P1. 写最小 F2 algebra + ChainWindow
        ↓
P2. 构造第一个完整 HomologyOperator(P, L)
        ↓
P3. 同一个对象一次性接齐所有联合读取
        ↓
P4. 迁移研究仓库 fixtures，建立 exact oracle regression
        ↓
P5. 建 OperatorFamily + T_ij + barcode readout
        ↓
P6. 建 ProjectionSolver 框架与 certificate
        ↓
P7. 做性能后端
        ↓
P8. 稳定性与真实应用
```

其中 P2 与 P3 不能被拆成“先同调后几何”两个产品阶段。它们属于同一个 `HomologyOperator` 的实现完成度。

---

# 15. 项目的核心判断标准

后续每提出一个新模块、优化或生态集成，都应该先问三个问题：

1. **它是否仍然以同一个投影身份为事实来源？**
2. **它是在优化 / 读取统一算子，还是偷偷引入第二套不兼容计算？**
3. **它给出的数值是否明确标注了数学语义与认证等级？**

只要这三条守住，这个项目就不会退化成“PH + feature engineering”的普通流水线。

最终产品应当保持下面这一句话始终为真：

\[
\boxed{
\text{Homology Operator 是一个统一的同调表示对象；Persistent Homology 与几何信息都是它的联合读取。}
}
\]
