# Homology Operator：ARCHITECTURE

> 适用仓库：`proffitteoy/homology-operator`  
> 理论来源：`proffitteoy/homology-operator-lab @ 6143729669902ee875b211b58085e954c76cdf88`  
> 文档角色：定义工程对象、依赖边界、主计算路径和不可破坏的架构不变量。

## 1. 核心定位

本项目的核心不是一个“PH 算法 + 几何后处理”流水线，而是一个统一二元同调算子及其过滤上的算子族。

对固定次数 \(k\)，输入有限带基链窗口

\[
C_{k+1}\xrightarrow{D}C_k\xrightarrow{A}C_{k-1},
\qquad AD=0,
\]

以及正坐标权重

\[
w=(w_1,\ldots,w_n),\qquad w_i>0.
\]

选择满足

\[
AGA=A,\qquad DUD=D
\]

的广义逆后，定义

\[
R=I+GA,\qquad
Q=I+DU,\qquad
P=QR,\qquad
L=I+P.
\]

工程上，`HomologyOperator` 就是这一数学对象及其身份、证书和查询接口的封装。

所有拓扑与几何读取必须从同一个 \(P/L\) 身份产生：

\[
(A,D,w)
\longrightarrow
(P,L)
\longrightarrow
\begin{cases}
\text{homology readout},\\
\text{representative readout},\\
\text{metric/support readout},\\
\text{stretch/certificate readout}.
\end{cases}
\]

Persistent Homology 不是前置输入，也不是另一套主计算内核。对过滤而言，完整对象是算子族及其跨尺度传输。

---

## 2. 架构不变量

下面约束应视为仓库级工程宪法。后续实现语言、数据结构、并行策略、求解器和生态适配均不得破坏。

### 2.1 单一投影身份

每个阶段、次数的结果必须绑定唯一的：

- `input_id`
- `basis_id`
- `weight_id`
- `projection_id`
- `operator_id`
- `solver_run_id`

所有以下结果必须引用同一个 `projection_id`：

- 核与 Betti 维数；
- 选定代表 \(Pz\)；
- 类间距离；
- 支撑与共享支撑；
- stretch / objective；
- 跨尺度 transport 的目标投影。

禁止分别运行不相容的求解器，再把结果拼成一个“联合输出”。

### 2.2 PH 是算子族的读取

调用者不得被要求预先提供：

- barcode；
- persistence pairing；
- 同调基；
- 最短类代表表。

这些量若需要，必须从当前算子或算子族派生。

独立 PH reduction 只能位于：

```text
tests/oracle/
```

或 benchmark 对照路径中，不得成为主结果的隐藏来源。

### 2.3 拓扑与几何共同绑定原始链坐标

同调在基变换下保持，但以下几何量依赖当前链坐标：

- representative mass；
- support；
- shared support；
- union support；
- stretch；
- 类距离 \(m_w(P(z+y))\)。

因此 `basis_id` 和 `weight_id` 是结果语义的一部分，不是可丢弃的调试元数据。

### 2.4 精确拓扑不得静默退化

资源不足或后端缺失时，可以返回：

- `resource_exhausted`
- `unavailable`
- `heuristic`
- `certified_interval`

但不得把未验证 persistence 或近似拓扑结果标为 exact。

### 2.5 选定代表与最短代表严格分离

一般情况下

\[
m_w(Pz)\neq \mu_w([z]).
\]

公共 API 必须区分：

- `selected_mass`
- `minimum_class_mass`
- `minimum_mass_lower_bound`
- `minimum_mass_upper_bound`
- `stretch`
- `stretch_certificate`

禁止把 `mass(project(z))` 命名为 `shortest_length`。

---

## 3. 顶层对象关系

推荐对象关系如下：

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
    ├── Transport T_ij
    ├── rank invariant
    ├── barcode readout
    └── geometric class tracking
```

这里的“readout”不是独立算法对象，而是同一个 `HomologyOperator` 的查询视图。

---

## 4. 单尺度对象职责

### 4.1 `ChainWindow`

表示固定尺度、固定次数的局部链复形：

```text
ChainWindow
├── dimension: k
├── basis_{k+1}
├── basis_k
├── basis_{k-1}
├── D
├── A
├── weights
└── metadata
```

构造时必须验证：

\[
AD=0.
\]

权重必须满足：

\[
w_i>0.
\]

输入验证失败应立即返回结构化错误，不得产生半合法算子。

### 4.2 `ProjectionProblem`

把数学输入与求解约束冻结为求解器消费的对象：

```text
ProjectionProblem
├── chain_window
├── objective
├── tie_break_policy
├── arithmetic_policy
├── resource_limits
└── requested_certificate_level
```

它描述“要找什么投影”，但不负责实际搜索。

### 4.3 `ProjectionSolution`

由 solver 返回。它至少携带：

- 一个合法投影的显式矩阵或 matrix-free action；
- solver 状态；
- objective；
- bounds；
- certificate；
- provenance。

详细语义见 `SOLVER_CONTRACT.md`。

### 4.4 `HomologyOperator`

`HomologyOperator` 是单尺度主对象。

逻辑上必须能够执行：

```text
project(z)                  -> Pz
apply_operator(x)           -> Lx
kernel_basis()              -> ker(L)
betti()                     -> dim ker(L)
is_cycle(z)
is_boundary(z)
same_class(z, y)
selected_mass(z)
class_distance(z, y)
support(z)
shared_support(z, y)
union_support(z, y)
stretch()
certificate()
metadata()
```

这些查询必须引用同一个 `projection_id`。

---

## 5. 单尺度主计算路径

主路径建议固定为：

```text
ChainWindow
    ↓ validate
ProjectionProblem
    ↓ solve
ProjectionSolution
    ↓ validate solution
HomologyOperator
    ↓
joint readouts
```

其中 `validate solution` 不能省略。无论 solver 自己声称什么，Operator 构造边界都应验证至少：

\[
P^2=P,\qquad AP=0,\qquad PD=0.
\]

对于显式 \(P\)，可直接验证；对于 matrix-free action，应采用等价的可验证证书或基于生成集的验证方式。

对循环 \(z\)，还应验证或保证：

\[
z+Pz\in \operatorname{im}D.
\]

---

## 6. 过滤上的算子族

对过滤

\[
K_0\subseteq K_1\subseteq\cdots\subseteq K_N,
\]

每个尺度、次数构造：

\[
P_i,\qquad L_i=I+P_i,\qquad
\mathcal H_i=\ker L_i.
\]

第一版仅要求支持过滤包含映射 \(J_{ij}\)。

跨尺度传输定义为

\[
T_{ij}=P_jJ_{ij}|_{\mathcal H_i}.
\]

`OperatorFamily` 至少应提供：

```text
stage(i)
transport(i, j)
transport_rank(i, j)
barcode()
track_class(x, i, j)
track_mass(x, i, j)
track_support(x, i, j)
transport_certificate(i, j)
```

### 6.1 必须保持的 transport 不变量

\[
T_{ii}=I,
\]

\[
T_{j\ell}T_{ij}=T_{i\ell}.
\]

并且 transport 与原诱导同调映射共轭。

### 6.2 Barcode 的位置

`barcode()` 可以存在于 `filtration/` 模块中，但职责仅是从

\[
r(i,j)=\operatorname{rank}T_{ij}
\]

读取区间分解。

它不得拥有另一套隐藏 PH 内核。

---

## 7. Oracle 路径边界

独立 PH 实现是必要的，但只能用于验证。

推荐目录：

```text
tests/oracle/
├── standard_reduction
├── gudhi_adapter
├── ripser_adapter
└── expected_fixtures
```

允许用途：

- 对拍 Betti；
- 对拍 barcode；
- 对拍 rank invariant；
- 回归测试；
- 性能基线。

禁止用途：

- 直接填充 `OperatorResult.topology`；
- 为主路径补齐算子没有计算出的 persistence；
- 用 oracle 的代表元冒充当前 \(P\) 的代表。

---

## 8. 显式矩阵与 Matrix-Free 后端

当前 reference 除 Matrix 外已接入 `CyclicAction(m, complement)`，实现固定T-B1族的P或L，m限定2、3、4。handle只存参数和表示版本；生成集validator、project/L、身份和快照恢复无需物化完整P。核基读取流式选择像空间基；transport先把源核嵌入目标链，再应用目标action，避免先形成P乘整个包含矩阵。A/D及输出核基、transport矩阵仍是显式对象，不提供全流程稀疏或高性能承诺。具体支持域见 [solver契约](SOLVER_CONTRACT.md)。

公共语义不应依赖实现是否显式存储 \(P\) 或 \(L\)。

统一抽象建议为：

```text
LinearAction
├── apply(x)
├── domain_dimension
├── codomain_dimension
├── representation_kind
└── verification_handle
```

第一版 reference backend 可以显式矩阵化：

```text
P: dense / bit matrix
L: dense / bit matrix
```

高性能阶段可以替换为：

```text
P(x) = Q(R(x))
L(x) = x + P(x)
```

或者更结构化的快速作用。

只要：

- 结果语义一致；
- `projection_id` 稳定绑定具体作用；
- 证书能够验证；

就不应要求所有后端物化完整矩阵。

---

## 9. 推荐源码组织

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

这里故意不设置三个彼此独立的主目录：

```text
src/homology/
src/geometry/
src/persistence/
```

因为这种结构容易重新把统一算子拆成三个独立计算内核。

---

## 10. 阶段与架构的对应关系

### Phase 0：契约冻结

完成：

- 本文档；
- `RESULT_MODEL.md`；
- `SOLVER_CONTRACT.md`。

### Phase 1：单尺度 reference operator

实现：

- `ChainWindow`
- `ProjectionProblem`
- 最简单 `ProjectionSolver`
- `ProjectionSolution`
- `HomologyOperator`
- 全部联合读取。

### Phase 2：OperatorFamily

实现：

- filtration；
- transport；
- rank invariant；
- barcode readout；
- representative tracking。

### Phase 3：Solver framework

扩展：

- exhaustive exact；
- greedy certified；
- rank-2 specialized；
- structured family；
- general approximate/search。

### Phase 4：高性能后端

替换内部数据结构和作用表示，但不改变公共语义。

### Phase 5 以后

研究：

- 网格/采样稳定性；
- 几何恢复；
- 实际任务价值；
- 发行与生态。

---

## 11. 禁止出现的架构模式

### 11.1 PH 旁路

禁止：

```text
input
├── standard PH engine -> barcode
└── operator engine    -> geometry
```

然后把二者合并成一个结果。

### 11.2 几何后处理伪统一

禁止：

```text
PH representatives
    ↓
separate shortest-cycle solver
    ↓
geometry features
```

再声称这些量属于当前 `HomologyOperator`。

### 11.3 Solver 泄漏到读取层

读取函数不应根据 solver 类型改变数学语义。

例如：

```text
mass(z)
distance(x,y)
same_class(x,y)
```

必须对所有合法 solver 保持同一定义。

### 11.4 合法零值与缺失值混淆

以下状态必须可区分：

- `0`
- `None / not_computed`
- `unavailable`
- `resource_exhausted`
- `empty_domain`
- `no_class`

---

## 12. 架构验收条件

架构可以视为冻结，至少要满足：

1. 一次完整单尺度计算由什么对象表示，有唯一答案；
2. 所有 readout 都能追溯到同一个 `projection_id`；
3. Operator 与 Solver 的职责边界明确；
4. OperatorFamily 不依赖另一套 PH 主内核；
5. oracle 只能用于验证；
6. matrix-free 和显式矩阵后端共享同一结果语义；
7. basis / weights / solver provenance 不会在序列化中丢失；
8. exact、approximate、unavailable 等状态不会被混淆。
