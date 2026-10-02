# Homology Operator：SOLVER_CONTRACT

> 文档角色：定义投影求解问题、统一 solver 接口、返回状态、认证等级、资源约束和可比较性规则。  
> 依赖：`ARCHITECTURE.md`、`RESULT_MODEL.md`。

## 当前实现与阅读入口

调用和构造参数见 [Python API](INTERFACE.md)，main/CI 与开发中状态见 [文档索引](README.md)。
本文 §1–20 保留语言无关数学契约；其中扩展资源、算术与算法选项是契约允许的目标，
实际支持域以下表、`capabilities()` 和 §21–26 的实现说明为准，不因逻辑模型中出现名称就视为实现。

| solver / 入口 | 实际输出与支持域 | 认证与限制 |
| --- | --- | --- |
| `FeasibleSolver` | 一般链窗口、显式 Matrix；整数/有理/浮点权 | Feasible；objective 初始 NotComputed，不优化 stretch |
| `ExhaustiveExactSolver` | 精确权、小规模完整截面搜索 | 完成才认证全局最优；枚举/独立重放有上限 |
| `GreedyCertifiedSolver` | 精确权、穷举循环上的确定性贪心截面 | 理论 β 界与实算 Γ 分开；等界验证后才 ExactOptimal |
| `Rank2ExactSolver` | 精确权、β=2；实际验证的一般/图/三终端结构 | 完整支持搜索/证书；不凭几何名称启用归约 |
| `StructuredFamilySolver` | 明确 CyclicTrace，m=2/3/4、等精确正权；Matrix 或 CyclicAction | 固定公式与独立最优证书，不接受任意结构族 |
| `NativeFeasibleSolver`（对象调用） | 可选 Rust，三个链空间最多 64 维；同 reference G/U/P | Feasible，独立 Python 验证；缺扩展/超范围为 Unavailable |
| `NativeFactorizedSolver`（[PR #80](https://github.com/proffitteoy/homology-operator/pull/80) 已合并） | matrix_free_output=True；Factorized / HC | Feasible，紧凑作用经独立验证；尚未完成阶段验收 |

`PreparedMatrix` 是原生代数分解工具，不是 projection solver。
GeneralSearchSolver 未注册为公共后端；冻结局部搜索 no-go 见 [性能协议](BENCHMARKS.md)。
合法投影、当前 objective 精确计算与最优认证始终分别报告。

## 1. Solver 的职责

Solver 只负责回答：

> 在满足同调投影约束的候选中，选择一个什么样的投影 \(P\)？

Solver 不负责：

- 计算另一套 PH；
- 生成最终 barcode；
- 定义几何查询语义；
- 修改 `HomologyOperator` 的数学定义。

统一流程：

```text
ProjectionProblem
    ↓
ProjectionSolver
    ↓
ProjectionSolution
    ↓ validate
HomologyOperator
```

---

## 2. `ProjectionProblem`

固定次数 \(k\) 的输入：

\[
C_{k+1}\xrightarrow{D}C_k\xrightarrow{A}C_{k-1},
\qquad AD=0,
\qquad w_i>0.
\]

实际 Python 请求模型（输入与权重由 window 保存）：

```text
ProjectionProblem
├── window
├── resource_limits
├── objective
├── requested_certificate_level
├── tie_break_policy
├── arithmetic_policy
├── input_structure
├── matrix_free_output
├── deterministic
└── solver_options
```

---

## 3. 合法投影约束

无论 solver 类型如何，返回给 `HomologyOperator` 的投影必须满足统一合法性条件。

至少：

\[
P^2=P,
\]

\[
AP=0,
\]

\[
PD=0.
\]

并且对循环 \(z\)：

\[
z+Pz\in\operatorname{im}D.
\]

等价地，\(P|_Z\) 必须给出同调商

\[
H=Z/B
\]

的线性截面表示。

Solver 可以内部通过 \(G,U\) 构造：

\[
P=(I+DU)(I+GA),
\]

也可以使用任何等价参数化；但输出必须通过统一 validator。

---

## 4. Objective

第一主目标是最小化当前投影的最坏加权伸长：

\[
\Gamma_w(P)
=
\max_{0\ne z,\ Az=0}
\frac{m_w(Pz)}{m_w(z)}.
\]

全局目标：

\[
\Gamma_*
=
\min_{P\in\mathcal P(A,D)}\Gamma_w(P),
\]

其中 \(\mathcal P(A,D)\) 是所有合法同调投影。

建议：

```text
objective.kind = MinimumStretch
```

以后可以扩展其他 objective，但不得复用 `MinimumStretch` 名称表达不同目标。

---

## 5. 统一 Solver 接口

逻辑接口：

```text
ProjectionSolver
    solve(problem: ProjectionProblem)
        -> ProjectionSolution
```

solver 自身用 `capabilities()` 返回不可变或普通 mapping，调度实际读取：

```text
capabilities()
├── arithmetic_policies
├── input_structures
├── objectives
├── certificate_levels
├── tie_break_policies
├── resource_limits
├── supported_dimensions
├── supported_betti_range
├── matrix_free_output
├── deterministic
└── solver_options
```

这允许调度层在运行前判断请求是否可满足。

---

## 6. `ProjectionSolution`

实际 Python 解模型：

```text
ProjectionSolution
├── status
├── solver_run_id
├── projection
├── identity
├── certificate_level
├── objective               # QueryResult
├── lower_bound
├── upper_bound
├── optimality_gap          # 派生属性
├── certificate
├── method
├── tie_break_policy
├── arithmetic_policy
├── solver_config
├── solver_config_id        # 内容身份属性
├── generalized_inverse_a  # 可选
├── generalized_inverse_d  # 可选
├── resource_usage
└── diagnostics
```

其中 `projection` 可以是：

```text
Matrix
CyclicAction
CompactAction      # S4-04 / PR #80 已合并
```

---

## 7. Status 与认证等级

建议将“有没有合法解”和“最优性知道到什么程度”分开。

### 7.1 求解状态

```text
Solved
FeasibleOnly
ResourceExhausted
Unavailable
InvalidProblem
NumericalFailure
InternalError
```

### 7.2 认证等级

```text
Feasible
ExactOptimal
CertifiedUpperBound
CertifiedInterval
Heuristic
```

两者不是同一概念。

例如：

```text
status = ResourceExhausted
certificate_level = CertifiedInterval
```

是合法组合：solver 在耗尽资源前找到了可行解和下界，但没证明最优。

---

## 8. 各认证等级的严格语义

### 8.1 `Feasible`

必须已经验证当前投影合法。

已知：

\[
\Gamma_*\le \Gamma_w(P).
\]

不声称任何非平凡下界。

### 8.2 `ExactOptimal`

必须有：

- 合法投影 \(P\)；
- objective 精确值；
- 最优性证书，证明不存在更优合法投影。

即：

\[
\Gamma_w(P)=\Gamma_*.
\]

### 8.3 `CertifiedUpperBound`

有合法投影，因此有：

\[
\Gamma_*\le U.
\]

但没有足够下界证明 gap。

### 8.4 `CertifiedInterval`

有：

\[
L\le \Gamma_*\le U.
\]

若 \(L=U\)，应提升为 `ExactOptimal`，而不是继续保留 interval 状态。

### 8.5 `Heuristic`

可以有一个候选 action 或 objective，但如果没有经过合法性 validator，不能构造 `HomologyOperator`。

因此建议区分：

```text
heuristic_candidate
validated_feasible_projection
```

只有后者能进入主算子对象。

---

## 9. Bounds 与 gap

统一定义：

```text
lower_bound <= optimum <= upper_bound
```

如果当前有合法投影 \(P\)，通常：

```text
upper_bound <= objective_value
```

若 upper bound 就由当前投影给出，则二者相等。

推荐：

\[
\operatorname{gap}_{abs}=U-L,
\]

以及当 \(L>0\) 时：

\[
\operatorname{gap}_{rel}=\frac{U-L}{L}.
\]

不要把“当前解与 lower bound 的差”误称为 solver error。

---

## 10. Arithmetic policy

F2 代数部分应默认 exact。

权重与 objective 可以支持不同策略：

```text
ExactRational
ExactInteger
FloatingPoint
MixedCertified
```

若使用 floating point，certificate 必须说明：

- 哪些代数关系仍为 exact；
- 哪些 objective / bound 是数值近似；
- tolerance；
- rounding policy。

不得因为投影在 F2 上 exact，就自动把实权 stretch 标为 exact。

---

## 11. Tie-break policy

同一个最优 objective 可能对应多个投影。

必须允许固定可复现并列策略，例如：

```text
LexicographicProjection
LexicographicU
StableBasisOrder
StructuredCanonical
```

`ProjectionSolution` 必须记录实际 tie-break policy。

这对以下结果非常重要：

- representative；
- support；
- shared support；
- serialization hash；
- regression test。

最优值可以相同，但几何读取未必相同。

---

## 12. Resource limits

统一资源约束建议：

```text
ResourceLimits
├── wall_time_limit
├── memory_limit
├── node_limit
├── iteration_limit
├── state_limit
└── output_size_limit
```

达到限制时不得静默降级。

Solver 应返回：

```text
status = ResourceExhausted
```

并保留截至终止时已经证明的：

- best feasible；
- lower bound；
- upper bound；
- certificate。

---

## 13. Solver 层级

### 13.1 `FeasibleSolver`

目标：

- 快速找到任意合法投影；
- 不承诺最优。

用途：

- Phase 1 reference；
- fallback；
- correctness fixture。

### 13.2 `ExhaustiveExactSolver`

面向小规模实例。

职责：

- 枚举合法截面/投影；
- 给出 ground truth；
- 产生 regression corpus。

严禁在文档中包装成一般高效算法。

### 13.3 `GreedyCertifiedSolver`

实现通用可证明构造。

至少返回：

- 合法投影；
- objective；
- 理论保证；
- certificate level。

### 13.4 `Rank2ExactSolver`

针对 \(\beta=2\) 的特殊结构。

可以利用：

- Pareto 支撑消去；
- 三终端归约；
- 相关精确优化结构。

其输出仍必须符合统一 `ProjectionSolution`。

### 13.5 `StructuredFamilySolver`

对已知显式结构族，直接构造快速 action。

例如 solver 可以返回 matrix-free / structured projection，而不显式物化矩阵。

### 13.6 `GeneralSearchSolver`

后续研究：

- branch-and-bound；
- MILP；
- SAT / pseudo-Boolean；
- parameterized search；
- local improvement；
- approximation algorithms。

这些 solver 不得修改公共结果语义。

---

## 14. Solver 后验证

任何 solver 输出进入 `HomologyOperator` 前都必须经过独立 validator。

至少检查：

\[
P^2=P,\qquad AP=0,\qquad PD=0.
\]

对于小规模 exact fixture，再检查：

\[
\ker L\cong H,
\]

以及：

\[
Pz=0
\iff
z\in B
\quad
(z\in Z).
\]

若 solver 声称 `ExactOptimal`，还必须验证其最优性 certificate 的结构完整性。

solver 自己的单元测试不能替代这一边界验证。

---

## 15. 与 Operator 的职责边界

`HomologyOperator` 接受的是：

```text
ValidatedProjectionSolution
```

而不是任意 solver 私有对象。

Operator 不应知道：

- 是否通过 MILP；
- 是否通过 exhaustive；
- 是否通过 rank-2；
- 是否通过结构公式。

Operator 只依赖：

- 合法 action；
- identity；
- certificate；
- provenance。

因此 solver 更换不应改变：

```text
project
same_class
mass
distance
support
kernel
transport semantics
```

---

## 16. 与 OperatorFamily 的关系

默认情况下，每个尺度可以独立求一个合法/最优投影 \(P_i\)。

然后跨尺度：

\[
T_{ij}=P_jJ_{ij}|_{\ker L_i}.
\]

不要为了“让 transport 好看”而偷偷修改 \(P_i\) 的 objective。

如果未来研究联合跨尺度求解，应引入新的显式 objective，例如：

```text
CrossScaleProjectionProblem
```

而不是改变 `MinimumStretch` 的含义。

---

## 17. Benchmark 可比性

两个 solver 只有在以下条件一致时，性能数据才可直接比较：

- 同一个 `ProjectionProblem`；
- 同样的权重；
- 同样的 objective；
- 同样的 arithmetic policy；
- 同样的 certificate target；
- 同样的资源上限；
- 同样的 deterministic / tie-break 要求。

以下比较必须单独标注，不能直接混在一张“谁更快”表里：

```text
ExactOptimal vs Heuristic
ExactOptimal vs Feasible
CertifiedInterval vs UpperBoundOnly
```

---

## 18. Regression corpus

建议维护：

```text
tests/fixtures/solver/
├── trivial/
├── beta1/
├── beta2/
├── higher_rank/
├── euclidean_weighted/
├── abstract_weighted/
└── structured/
```

每个 fixture 至少记录：

```text
input_hash
known_betti
known_feasible_projection
known_optimum? 
known_bounds?
expected_certificate_level
```

小规模实例应尽量有 exhaustive ground truth。

---

## 19. 失败语义

### `InvalidProblem`

例如：

- \(AD\neq0\)；
- 权重非正；
- 维数不一致。

### `Unavailable`

请求了当前 solver 不支持的结构。

### `ResourceExhausted`

算法本身支持，但达到资源限制。

### `NumericalFailure`

浮点/外部优化器无法可靠完成请求。

### `InternalError`

实现 bug 或不变量被破坏。

这些状态不得被统一折叠成 `None`。

---

## 20. 最低验收条件

Solver framework 可视为冻结，至少满足：

1. 所有 solver 返回统一 `ProjectionSolution`；
2. 合法性 validator 独立于具体 solver；
3. `ExactOptimal` 有严格最优性语义；
4. `Feasible` 不会被误报为 optimal；
5. resource exhausted 能保留当前 bounds；
6. tie-break 可复现；
7. exact / floating arithmetic 被明确区分；
8. structured solver 可以返回 matrix-free action；
9. solver 更换不改变 `HomologyOperator` 查询定义；
10. benchmark 不混淆不同认证等级。

## 21. 当前 reference 支持范围（S3-01）

`FeasibleSolver.capabilities()` 与 `solve_projection` 已实现运行前能力匹配，无隐藏 fallback；FeasibleSolver 本身支持显式 Matrix、StableBasisOrder、ExactInteger/ExactRational/FloatingPoint 及 state/time/matrix-entry 三种实际资源限制。其他四个 reference solver 与结构族 matrix-free 输出已实现，支持域见 §22–26 和本页入口表，不能把 S3-01 的初始边界当作全部当前能力。

统一 ProjectionSolution 已保留 lower/upper、gap、不可变 solver_config 和内容配置身份。ResourceExhausted 可保留经独立验证的 action 和证书；HomologyOperator 的 Ready 与 solver 的停止状态分开。Heuristic 的 action 同样须经完整投影验证。

公开 certificate 的验证字段完全由独立 verifier 生成，未执行的 objective/bounds/optimality 验证明确为 false；原始 backend 声明只保留在 `solver_evidence`，不提升为公开验证标志。单尺度和族快照恢复采用相同规则，并保留已查询的阶段记录。统一调度还要求返回的完整配置、实际并列/算术策略和报告的资源限制匹配本次 ProjectionProblem；手工构造 solution 的兼容入口不能绕过调度的请求绑定。

独立证书 verifier 当前支持 `optimization={kind: "CycleBounds", nonzero_cycles: N, lower_bound_method: "UniversalHomology"}`。它枚举所有非零循环重算当前 Γ（重放上限100000个循环），校验精确 objective、U≥Γ，以及 L≤0（β=0）或 L≤1（β>0）。通用下界来自固定理论 T1/T4；非零合法投影在其非零像向量上恒等，所以扩张至少1。仅 L=U=Γ 且证书有效时接受 ExactOptimal；等界仍标 CertifiedInterval 则拒绝，须改用 ExactOptimal。空循环域的0与非空循环域的零同调0保留不同状态。

该证书不宣称完整最优搜索，不能认证大于1的全局下界。未知证明类型、篡改计数/objective/gap/配置身份、浮点等界或未经验证的 action 均拒绝。完整搜索证书已由 #20 实现，见 §22；证书重放是独立检查成本，不纳入 solver 构造时的 checkpoint 预算，尚无抢占式时间/RSS保证。固定研究提交的 native_operator、compressed_native_operator 和 T1 的历史阅读与 Git blob 核对是来源记录；其完整搜索成绩不作为本库实现成绩。

## 22. 小规模完整搜索（S3-02）

`ExhaustiveExactSolver` 使用固定研究提交 `compressed_native_operator` 的参数化：令 N 为循环基、F 为边界基，M 为 F 的循环坐标，解 Y M=I。每行解的自由度为 beta，因此恰有 `2^(rank(D)*beta)` 个候选；在固定 R 上形成 `P=R+FYT`，T 为 R 的循环坐标。所有非零循环直接参与 objective，构造不消费 PH、类标签或最短类表。

完整 `ExhaustiveSearch` 证书记录 R、候选数、循环数和完成标志。独立 verifier 改用 B 的基补到 Z、枚举商基的全部边界提升，重放最优值并核对所选投影。StableBasisOrder 和 LexicographicProjection 在此 solver 中均按原基坐标、固定 R 下的 packed 投影列字典序决胜；这不是所有非循环延拓上的全局字典序。objective witness 必须是实现 Γ 的非零循环，空循环域的 witness 为 None。

精确权重、state/time/matrix-entry 预算和独立重放上限为实际支持域：最多100000个非零循环，且候选数乘 `max(1,非零循环数)` 至多100000。状态预算计入可行种子的构造与实际循环求值，时间在 checkpoint 检查，matrix-entry 为保守条目上限。独立重放成本另外发生。中断时保留最后一个合法 P；未完成其 objective 时没有 bounds，完成后保留 U=Γ(P)、已跟踪的下界0和 CertifiedInterval。完整搜索结束前不报告 ExactOptimal；唯一候选完成求值即为完整搜索。

[solver 回归 corpus](../tests/fixtures/solver_reference.json) 绑定原23个窗口的 input hash：22个精确实例的最优值经固定上游 compressed 搜索核对，16个 n≤6 实例再经 native 搜索核对；浮点实例预期 Unavailable。本仓库另对49个1–3维输入独立枚举全部环境矩阵，检查全局最优值。高秩人工窗口、原 H0–H3/欧氏有理权、空域、零同调、候选计数/极值 witness 篡改、错误并列选择及中断快照均有回归。该有限指数算法不提供一般高效性结论。

## 23. 带理论界的贪心截面（S3-03）

`GreedyCertifiedSolver` 直接从全部循环按 `(质量, 原坐标 packed 整数)` 排序，依次选择模边界与已选循环独立的生成元；以它们和边界基构造截面，并沿固定 R 延拓成 P。不消费最短类质量表或 PH 结果。当前仅支持精确整数/有理正权、StableBasisOrder、显式一般链窗口以及 Feasible/CertifiedUpperBound/CertifiedInterval 请求；不能保证满足一般 ExactOptimal 请求。排序和循环枚举使它仍是小规模 reference，不是多项式算法。

理论依据是[固定 PROOF 的 T4](https://github.com/proffitteoy/homology-operator-lab/blob/6143729669902ee875b211b58085e954c76cdf88/docs/proof/PROOF.md#T4)：Rossman 贪心回缩论证的加权同调版本。β>0 时，依次最低质量的独立同调生成元给出 Γ≤β；β=0 的算子 Γ=0，与上游截面记账 κ=1 区别处理。`GreedyBasis` 证书记录 F2、严格正权、算术策略、β、选定生成元、R 和理论上界。verifier 不信任排序结果，每步重新扫描所有可选循环，核对质量与并列最小值，再重建完整 P；当前 Γ 与极值 witness 另外穷举验证。

完整输出保存 `objective=U=Γ(P)`、通用下界 L=1（β=0 时0）与 gap；L=U 才报告 ExactOptimal，其余为 CertifiedInterval。理论 β 界独立保存在已验证 proof 中，不能替代实算 objective 或最优性证明。22个精确 fixture 的 Γ 和所选生成元与固定 verify.py `model(optimize=False)` 一致；与 #20 的 optimum 对照均满足 optimum≤Γ≤β。K4 stage 4 的4/3只提供区间[1,4/3]，穷举最优是9/8。

独立重放限制为非零循环数乘 `max(1,β)` 至多100000；构造还受 state/time/matrix-entry 预算，循环表计入保守条目数。资源耗尽时保留可行种子：其 objective 未完成则只有 Feasible，已完成则保留 L=0、U=种子 Γ 的 CertifiedInterval 和 CycleBounds，不携带未完成的贪心理论保证。零同调种子完整求值后已经完成搜索，直接认证0。证书重放成本单独发生，排序/稠密代数检查点之间没有强制抢占或 RSS 保证。回归覆盖所有 state 中断位置、零时间/条目预算、重放上限、假设/并列/action/witness 篡改、身份混用与已查询快照反复往返；族恢复保留已验证的 tracking 历史。

## 24. Rank-2 结构求解（S3-04）

`Rank2ExactSolver` 支持精确整数/有理正权、β=2、显式矩阵和 StableBasisOrder。一般 `GeneralChainWindow` 路径枚举两个固定商生成元的边界修正，共 `4^rank(D)` 个；每个候选按固定理论 T5 消去支撑内非零边界，选择质量最大的成员颜色（并列按1、2、3），直到支撑中没有同调零循环。三类质量逐项不增，仍为同一线性截面。它从循环枚举计算三个商类的最短质量，再只用三个比值评价候选；类标签和最短质量不是外部必需输入，也不写入算子 selected_mass 的语义。

`GraphCycle` 在上述条件外验证 k=1、A 每列恰有两个1，表示允许平行边、不含自环的图；不据此推断平面性。`ThreeTerminalCut` 路径要求三个有序且互异的终端、对偶顶点数及与原链坐标一一对应的有序边。令 δ 为固定 t0 位势为0后的顶点割矩阵，验证 rank(δ)=V−1、Aδ=0、dim ker(A)=V−1，并验证内部顶点割张成 im(D)。这些等式直接证明归一化割位势与循环/同调商的对应，无需信任“平面”标签。平行边保留，环边和不连通对偶图拒绝。

在已验证的割模型上，T-A3 的重标号论证保证只需0、e1、e2三个标签，构造枚举 `3^(V−3)` 个划分，终端标签固定。三个精确分母仍从循环枚举独立算出；此 reference 未引入 max-flow 依赖或声称高效最小割。T-A1 的一般平面识别、相对同调、正亏格对偶割、欧氏平坦环面的连续星形几何均不在支持域。仅β=2或元数据中的几何名称不能启用这些归约；FloatingPoint、PlanarSurface、EuclideanFlatTorus及matrix-free请求返回Unavailable。

`Rank2Search` 保存R、完整候选/实际归约候选数、商生成元、三个精确最短质量、Pareto起点与消去轨迹，或三终端标签。独立 verifier 重新验证输入结构、归约步和action，从全部循环重放objective/witness，再完整枚举所有截面核对全局最优值（不使用消去搜索或三标签假设作最优性捷径）。StableBasisOrder在一般路径表示同调单射支撑候选中的packed投影列字典序；三终端路径表示三标签候选中的相同顺序；两者都固定R，不承诺在所有非循环延拓或所有未归约并列解中最小。

证书重放支持上限与完整搜索相同：`4^rank(D) * 非零循环数 <= 100000`。state计入种子、类分母枚举、候选及消去检查点；构造受时间与保守matrix-entry上限约束。输入结构验证和单次稠密代数步骤没有中途抢占；独立证书重放成本另计，不提供RSS保证。中断保留合法种子或已完成的更优解；objective未完成则无bounds，完成后保留L=0/U=当前Γ及CycleBounds，搜索未完成不标ExactOptimal。

验证来源固定为 `6143729669902ee875b211b58085e954c76cdf88`：PROOF T5、T-A1/T-A3/T-A4及T10，实际阅读了 `global-torus/verify_pruning.py`（Git blob `7a776660b10353928aae6035726a4816b9d53a3c`）、`planar/planar_homology_cut_check.py`（`f6c363e5107b19f6d58bc64320345402a8787e0f`）、`cutting-plane/planar_mincut.py`（`cbb87bff1ab4bb99bacc71c4c001dfc60cc041fd`）。没有移植其浮点容差为精确认证，也没有运行会写研究数据的main。

[rank-2回归](../tests/test_rank2.py) 复用原corpus中全部6个β=2输入及hash，与已有精确真值一致；另按固定PROOF公式生成T-A4宏观割族（δ=1/4、1/10、1/1000，得到 `(2−δ)/(2−2δ)`）和T10秩三反例，文件内记录理论提交及PROOF blob。32组小整数权重与ExhaustiveExactSolver对拍；验证非空消去轨迹、错误结构/终端/分母/标签/颜色、身份与witness篡改、所有state中断位置，以及单尺度和族往返。该有限reference不提供一般规模性能或连续几何最优性结论。

## 25. 可验证handle的循环结构族（S3-05）

`StructuredFamilySolver` 只接受显式声明 `input_structure="CyclicTrace"` 且实际满足固定T-B1的窗口：n=2^m−1、m∈{2,3,4}、A=0、im(D)=ker(P_m)、坐标权重为同一个正整数/有理数。P_m是m个二次幂循环移位的异或；等权的统一缩放不改变Γ。构造先检查D秩与各列被P消去，不依赖source_metadata中的名称。其他结构、变权、浮点、错误边界或更大m返回Unavailable，不回退为另一个solver。

`matrix_free_output=True` 产生只含m与补标志的CyclicAction；false产生同一公式的显式Matrix。StableBasisOrder和StructuredCanonical均选择指定公式，不承诺全体最优解的字典序。P/L的应用使用packed位循环移位，按二元坐标复杂度为O(nm)；构造、输入验证、核基输出与证书验证另计，未做性能优势声明。输入A/D仍是显式矩阵，结果中的版本1handle本身可恢复且身份稳定；不同表示身份不能混用，详见 [结果模型](RESULT_MODEL.md)。

合法性独立验证P²=P、L²=L、AP=0、PD=0和循环同调保持；CyclicAction在全部坐标生成集及完整循环基上验证，不使用“结构成立”布尔标志代替检查。`CyclicTrace`最优性证书另核对逐列公式及列质量m、所有质量≤m的非零向量均不在ker(P)、(I+P)e0是质量m+1的非零边界。于是核距离为m+1；若另一截面Γ<m，整数质量迫使每个坐标输出与原坐标的差为0，投影将成为恒等，与非零边界矛盾。当前Γ=m由全链空间等权下的最大列质量得到；objective witness、精确等界及gap分别复核。

来源为固定研究提交 `6143729669902ee875b211b58085e954c76cdf88` 的PROOF T-B1及 `structured/verify_exact.py`（Git blob `21adb77a258a7342312333c3b77d8a8406ce5037`）。循环码幂等、迹和连续零点的Vandermonde核距离机制属原文注明的经典编码论成分；此实现没有声称新的编码构造。当前m上限源自有限独立距离证书的成本，不把一般公式的适用范围冒充已支持参数。

[结构族测试](../tests/test_structured.py) 的输入由独立列公式生成并记录来源：m=2与通用exhaustive对照，m=3额外枚举4096个截面求得真值3，m=4由独立低重量距离证书给出4。三个m的全部列、秩和核距离实际与固定上游纯函数对照。测试覆盖project/L/同调/几何、显式与结构化表示、禁用dense identity时的构造与快照恢复、族transport、反复往返、handle和证书篡改、身份混用、输入识别及资源失败。solver有state/time/matrix-entry检查点；独立生成集与距离证书重放另计，构造中断无完整验证action时不携带可行或最优声明。

## 26. 算术、资源与并列验收（S3-07）

ExactInteger保存任意精度整数权，ExactRational保存int/Fraction；objective以Fraction计算，无浮点转换或容差。FloatingPoint只支持FeasibleSolver的精确F2构造及approximate几何查询，求和用binary64 fsum、除法用binary64最近偶数舍入；tolerance=None表示没有误差区间或近似相等认证。数值非有限时返回Unavailable/NumericalFailure，不填bounds。四个优化solver拒绝浮点权；MixedCertified尚无实现，ChainWindow拒绝该算术，显式solver请求返回Unavailable，不能回退为FloatingPoint。

ResourceLimits实际支持state_limit、wall_time_limit、matrix_entry_limit。node、iteration、memory/RSS及output_size参数未实现，构造参数明确拒绝；matrix-entry只约束保守分配条目，不能称为内存峰值。wall time在checkpoint检查，能力匹配、单步稠密代数及独立后验证没有强制抢占。五个solver以可控单调时钟测试正wall上限的全部检查点；三个搜索solver覆盖中断后无bounds的可行种子、已完整objective的CertifiedInterval及JSON恢复。未完整验证的候选不能进入Ready；完成前不升级ExactOptimal。已有逐solver测试遍历state位置及零条目/时间预算。

相同配置产生相同P与内容身份、不同solver_run；查询仍严格绑定六身份。相同P但不同并列策略改变projection_id；预算改变solver_config_id。cache_key调用者必须传实际solver_config_id、实际并列策略与backend语义版本，不能传固定占位名称代替配置身份。不同P的质量/支撑及cache分开，跨run/action查询混用被拒绝；当前并列策略的适用范围仍分别由各solver声明，不推断代表随权重连续。

[边界测试](../tests/test_solver.py) 复用固定研究PROOF T1/T4的正权前提和T-B1 m=2窗口A=0、D=(1,1,1)ᵀ，跨solver验证大于binary64精确整数范围的等权与有理缩放：当前Γ=2，但选定单坐标质量可随P不同。调度失败保留请求backend的method，返回solution后使用真实内部method，允许测量wrapper；未知GeneralSearch不再误记为FeasibleSolver。[冻结对照](BENCHMARKS.md)保留原源码下的历史记录，不回写为修复后的结果。
