# Homology Operator：SOLVER_CONTRACT

> 文档角色：定义投影求解问题、统一 solver 接口、返回状态、认证等级、资源约束和可比较性规则。  
> 依赖：`ARCHITECTURE.md`、`RESULT_MODEL.md`。

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

推荐模型：

```text
ProjectionProblem
├── input_identity
├── A
├── D
├── weights
├── objective
├── arithmetic_policy
├── tie_break_policy
├── resource_limits
├── requested_certificate_level
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

建议 solver 自身声明 capability：

```text
SolverCapabilities
├── exact
├── certified_bounds
├── heuristic
├── supported_dimensions?
├── supported_betti_range?
├── matrix_free_output
└── deterministic
```

这允许调度层在运行前判断请求是否可满足。

---

## 6. `ProjectionSolution`

推荐模型：

```text
ProjectionSolution
├── status
├── projection
├── objective_value
├── lower_bound
├── upper_bound
├── optimality_gap
├── certificate
├── method
├── solver_run_id
├── tie_break_result
├── resource_usage
└── diagnostics
```

其中 `projection` 可以是：

```text
ExplicitMatrix
MatrixFreeAction
StructuredAction
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

`FeasibleSolver.capabilities()` 与 `solve_projection` 已实现运行前能力匹配，无隐藏 fallback；当前构造只支持显式 Matrix、StableBasisOrder、ExactInteger/ExactRational/FloatingPoint 及 state/time/matrix-entry 三种实际资源限制。其他 solver 和 matrix-free 输出随后续 issue 实现。

统一 ProjectionSolution 已保留 lower/upper、gap、不可变 solver_config 和内容配置身份。ResourceExhausted 可保留经独立验证的 action 和证书；HomologyOperator 的 Ready 与 solver 的停止状态分开。Heuristic 的 action 同样须经完整投影验证。

独立证书 verifier 当前支持 `optimization={kind: "CycleBounds", nonzero_cycles: N, lower_bound_method: "UniversalHomology"}`。它枚举所有非零循环重算当前 Γ（重放上限100000个循环），校验精确 objective、U≥Γ，以及 L≤0（β=0）或 L≤1（β>0）。通用下界来自固定理论 T1/T4；非零合法投影在其非零像向量上恒等，所以扩张至少1。仅 L=U=Γ 且证书有效时接受 ExactOptimal；等界仍标 CertifiedInterval 则拒绝，须改用 ExactOptimal。空循环域的0与非空循环域的零同调0保留不同状态。

该证书不宣称完整最优搜索，不能认证大于1的全局下界。未知证明类型、篡改计数/objective/gap/配置身份、浮点等界或未经验证的 action 均拒绝。完整搜索证书属于 #20；证书重放是独立检查成本，不纳入 solver 构造时的 checkpoint 预算，尚无抢占式时间/RSS保证。固定研究提交的 native_operator、compressed_native_operator 和 T1 已逐项阅读，并在线核对缓存的 Git blob hash；它们的完整搜索成绩不作为本项实现成绩。
