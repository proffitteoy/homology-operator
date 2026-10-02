# Homology Operator：RESULT_MODEL

> 文档角色：定义统一结果对象、身份字段、状态语义、读取视图、序列化要求和跨尺度结果模型。  
> 依赖：`ARCHITECTURE.md`。

## 1. 设计目标

结果模型必须表达一个核心事实：

> 拓扑读取和几何读取是同一个投影 \(P\) / 算子 \(L=I+P\) 的不同观察方式。

因此，结果模型不能把 PH、代表、距离、支撑和 stretch 组织成彼此独立、来源不明的结果包。

所有字段必须能够追溯到：

- 原输入；
- 原链基；
- 权重；
- 投影；
- solver；
- certificate。

---

## 2. 身份模型

S4-04 的 `CompactF2` 版本1保存 `form=GeneralizedInverse|HC`、严格显式形状的factors、原列pivots和boolean complement。GeneralizedInverse依次保存A/D/非零G行/非零U行，pivot确定散射到原坐标；HC保存H/C。旧Matrix/CyclicTrace仍可读，未知版本、额外字段、形状/索引污染拒绝。`projection_id`直接绑定因子内容和表示版本，不为hash展开P，不做跨表示身份归一化；恢复独立检验完整链action与循环同调保持。Feasible标签不证明最优，当前compact只另支持通用CycleBounds重放，其他优化proof格式明确拒绝，后续solver工作包另行实现。

对于已验证幂等action，`ker(L)=im(P)`、`ker(P)=im(L)`。流式生成坐标列形成完整像空间，不保留全P。Python整数行消元从最高原坐标向下选择pivot，并清除所有其他基向量中的该位，最后按pivot升序读取；得到该子空间唯一的右向左reduced basis。reference左向右RREF的canonical kernel每个向量在其自由坐标为1，其他自由坐标为0，非零pivot坐标都在该自由坐标之前，因此自由坐标恰为最高非零位。这也是上述唯一reduced basis，故完整核基及过滤坐标与reference一致。输出本身可能有平方大小，按实际核输出计费；这个论证依赖独立验证的幂等性，不用于接受非法候选。

结构族reference的projection字段可保存严格版本化handle `{kind: "CyclicTrace", version: 1, m: 2|3|4, complement: false}`；L由同一参数的补action生成。`projection_id`散列输入、原基、并列策略及handle，所有实际作用由固定且可验证的公式决定。它与显式矩阵表示使用不同内容身份，不声称跨表示归一化；同一handle重复求解或JSON往返保持projection/operator身份，solver_run仍独立。未知版本、额外字段和无效参数拒绝；恢复重新验证生成集、输入、认证与查询身份。链输入A/D的矩阵schema不接受action handle。

Phase 1 reference 的 `OperatorResult` 支持无投影失败记录：`projection=None` 时只能使用匹配的失败状态，认证为空，不能携带算子查询或生成算子缓存键。已验证输入可保留 input/basis/weight 与 solver_run 的部分身份，尚无合法输入时身份和输入均可为空；不生成 projection/operator 身份。嵌套 solver objective 也必须与有投影记录的完整六身份一致。

reference JSON 将 Fraction 编码为 `$fraction` 标签，普通单键 `$fraction` / `$mapping` 字典通过 `$mapping` 转义，避免用户数据与数值标签冲突。Phase 3 #19 已扩展统一认证记录：所有 P 重新验证合法性，已支持的 `CycleBounds` 在精确权重上独立重放当前 objective 和通用全局下界；没有支持证书的最优或区间标签仍拒绝。上下界与 gap、solver_config/config_id、诊断在单尺度和族恢复时均保留；无投影失败记录不携带算子 bounds。具体支持域见 [solver 契约](SOLVER_CONTRACT.md)。

建议所有主要对象使用不可混淆的稳定身份。

### 2.1 `InputIdentity`

```text
InputIdentity
├── input_id
├── chain_window_hash
├── dimension
├── scale_id
├── filtration_id?
└── source_metadata
```

`chain_window_hash` 至少覆盖：

- \(A\)；
- \(D\)；
- 坐标顺序；
- 次数 \(k\)。

### 2.2 `BasisIdentity`

```text
BasisIdentity
├── basis_id
├── basis_{k+1}_id
├── basis_k_id
├── basis_{k-1}_id
└── coordinate_order_hash
```

支撑、质量和几何解释必须绑定 `basis_id`。

### 2.3 `WeightIdentity`

```text
WeightIdentity
├── weight_id
├── weight_hash
├── semantic_kind
├── unit?
└── inheritance_policy?
```

建议 `semantic_kind` 至少区分：

```text
unit
abstract_positive_cost
euclidean_length
euclidean_area
euclidean_volume
custom
```

### 2.4 `ProjectionIdentity`

```text
ProjectionIdentity
├── projection_id
├── representation_kind
├── projection_hash_or_handle
├── solver_run_id
└── tie_break_policy_id
```

同一个 `projection_id` 是联合输出一致性的核心锚点。

### 2.5 `OperatorIdentity`

```text
OperatorIdentity
├── operator_id
├── projection_id
├── input_id
├── basis_id
└── weight_id
```

---

## 3. 顶层 `OperatorResult`

推荐逻辑模型：

```text
OperatorResult
├── identity
├── status
├── action
├── algebraic_certificate
├── topology
├── geometry
├── stretch
├── provenance
└── resource_usage
```

其中 `topology`、`geometry`、`stretch` 只是同一个结果对象的读取视图。

---

## 4. 顶层状态

建议区分“Operator 是否成功构造”和“某个可选查询是否已计算”。

### 4.1 Operator 构造状态

```text
Ready
InvalidInput
SolverFailed
ResourceExhausted
Unavailable
InternalValidationFailed
```

语义：

- `Ready`：存在已验证合法投影，可执行基础联合读取；
- `InvalidInput`：例如 \(AD\neq0\)、权重非正、维数不匹配；
- `SolverFailed`：solver 没有返回合法解；
- `ResourceExhausted`：达到时间/内存/节点等资源限制；
- `Unavailable`：请求的 solver/backend 未实现；
- `InternalValidationFailed`：solver 返回结果，但工程边界复核失败。

只有 `Ready` 可以生成正常 `HomologyOperator`。

---

## 5. `OperatorAction`

公共结果模型不要求物化矩阵。

```text
OperatorAction
├── projection_action
├── operator_action
├── representation_kind
└── verification_handle
```

其中：

\[
P:\ C_k\to C_k,
\qquad
L=I+P.
\]

`representation_kind` 可以是：

```text
explicit_dense
explicit_bitpacked
sparse
matrix_free
structured
```

对外查询必须保持一致：

```text
project(z)
apply_operator(x)
```

---

## 6. `AlgebraicCertificate`

至少记录：

```text
AlgebraicCertificate
├── p_idempotent
├── l_idempotent
├── a_p_zero
├── p_d_zero
├── cycle_homology_preservation
├── exact_arithmetic
└── verification_method
```

对应：

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

对循环 \(z\)：

\[
z+Pz\in\operatorname{im}D.
\]

第一版 reference backend 可以把这些字段全部设为通过显式 F2 代数验证得到的 `true`。

高性能 matrix-free backend 则应记录实际验证方式，而不是无条件复制 `true`。

---

## 7. `TopologyView`

建议接口：

```text
TopologyView
├── betti
├── kernel_basis?
├── kernel_dimension
├── class_query
└── provenance
```

### 7.1 Betti

\[
\beta=\dim\ker L.
\]

`betti` 是合法零值：

```text
betti = 0
```

不能与 `not_computed` 混淆。

### 7.2 Kernel basis

完整基可以按需计算：

```text
kernel_basis:
    Computed(value)
    NotComputed
    ResourceExhausted
    Unavailable
```

因为完整核基可能昂贵，不应要求所有 backend 在构造时强制物化。

### 7.3 类查询

对循环 \(z\)：

```text
class_representative(z) = Pz
```

对循环 \(z,y\)：

```text
same_class(z,y)
```

满足：

\[
Pz=Py
\iff
[z]=[y].
\]

### 7.4 输入域

`same_class`、`class_representative` 的默认保证仅对循环成立。

非循环输入应：

- 拒绝；
- 或显式进入 `retraction_mode`。

不得静默套用循环上的同调语义。

---

## 8. `GeometryView`

推荐逻辑字段：

```text
GeometryView
├── selected_mass
├── class_distance
├── support
├── shared_support
├── union_support
├── minimum_class_mass?
└── geometry_provenance
```

### 8.1 Selected representative mass

对循环 \(z\)：

\[
\operatorname{selected\_mass}(z)=m_w(Pz).
\]

这不是默认的最短类质量。

### 8.2 Class distance

对循环 \(z,y\)：

\[
d_P([z],[y])=m_w(P(z+y)).
\]

必须满足：

- 非负；
- 对称；
- 同类当且仅当为零；
- 使用当前 `weight_id`；
- 使用当前 `projection_id`。

### 8.3 Support

```text
support(z) = supp(Pz)
```

支撑索引必须解释在当前 `basis_id` 下。

### 8.4 Shared / union support

```text
shared_support(z,y)
union_support(z,y)
```

应直接由同一个投影后的坐标计算，不应调用独立代表求解器。

### 8.5 原生批查询与进程内准备

S4-06 的 `geometry_batch` 在一个 QueryResult 中保存代表、selected_mass、距离及原坐标支撑交并，六身份来自传入的算子。`GeometryWorkspace` 持有同一 P/基/权重的原生准备与私有缓冲，复用时核对完整身份（含 solver_run_id）；准备对象不进入 OperatorResult，也不把 kernel/stretch 或未查询几何标为 Computed。批记录只有被调用者显式加入 query_results 时才进入快照，恢复继续复核身份与合法投影。

质量算术由 window.arithmetic 决定：u64 逐项检查求和，超界整数/溢出总和及非整数 Fraction 使用任意精度后备，浮点保留 binary64 fsum。details 保存准备/转换/原生/绑定/decode/后备分段、后备次数和原因；准备子项不得与准备总成本重复相加，结果冻结计入完整调用。后备不更换 P 或认证等级。空批为 Computed 空 tuple；合法零质量仍为0；缺少扩展或不支持的 action 为 Unavailable；非循环/混用拒绝，浮点溢出明确 NumericalFailure。

---

## 9. 最短类质量模型

真实最短类质量是可选优化结果：

\[
\mu_w([z])
=
\min\{m_w(x):x\in Z,\ [x]=[z]\}.
\]

建议统一表示为：

```text
MinimumClassMassResult
├── status
├── exact_value?
├── lower_bound?
├── upper_bound?
├── witness?
├── certificate?
└── method
```

`status` 可以是：

```text
Exact
CertifiedInterval
UpperBoundOnly
LowerBoundOnly
Heuristic
NotComputed
ResourceExhausted
Unavailable
```

禁止把 `selected_mass` 填入 `exact_value`。

---

## 10. `StretchView`

建议：

```text
StretchView
├── status
├── objective
├── lower_bound
├── upper_bound
├── optimality_gap
├── certificate_level
└── method
```

对当前投影 \(P\)：

\[
\Gamma_w(P)
=
\max_{0\ne z,\ Az=0}
\frac{m_w(Pz)}{m_w(z)}.
\]

对于最优值：

\[
\Gamma_*
=
\min_P \Gamma_w(P).
\]

按固定理论提交主证明 §1.2，循环空间为零时，定义域为空且当前 stretch 约定为 0；结果须保留空定义域信息。Betti 为零时实际扩张率 `Γ_w(P)=Γ_*=0`，不能与截面近似界中另行约定的记账值 `κ=1` 混用。参见 [固定理论正文](https://github.com/proffitteoy/homology-operator-lab/blob/6143729669902ee875b211b58085e954c76cdf88/docs/proof/PROOF.md)。

必须严格区分：

- 当前投影 objective；
- 全局最优值；
- 全局最优下界；
- 全局最优上界。

例如一个可行投影可以有：

```text
objective = 1.5
upper_bound_on_optimum = 1.5
lower_bound_on_optimum = 1.0
certificate_level = CertifiedInterval
```

但不能标成 `ExactOptimal`。

---

## 11. 缺失、空集与合法零值

必须显式区分以下情况。

### 11.1 合法零值

例如：

```text
betti = 0
distance = 0
selected_mass = 0
```

这些是正常数学值。

### 11.2 `NotComputed`

理论上可计算，但当前请求没有计算。

### 11.3 `Unavailable`

当前 backend / solver 不支持。

### 11.4 `ResourceExhausted`

尝试过，但资源上限终止。

### 11.5 `EmptyDomain`

例如某个次数的链空间为空。

### 11.6 `NoClass`

用于明确表示查询不存在对应非零同调类，而不是返回缺失。

---

## 12. Provenance

推荐：

```text
Provenance
├── repository_revision
├── theory_revision
├── backend
├── backend_version
├── solver
├── solver_version
├── arithmetic_mode
├── deterministic_seed?
├── tie_break_policy
├── build_info
└── created_at
```

如果结果将用于论文、benchmark 或缓存，必须能够复现：

- 输入；
- solver；
- tie-break；
- arithmetic；
- backend revision。

---

## 13. Resource usage

建议所有昂贵计算可附带：

```text
ResourceUsage
├── wall_time
├── cpu_time?
├── peak_memory?
├── solver_nodes?
├── iterations?
└── query_count?
```

这些字段不是数学结果的一部分，但 benchmark 和性能回归需要统一格式。

---

## 14. `OperatorFamilyResult`

`OperatorFamily.to_result()` 保存阶段结果、scales/policies、族身份、保留的传输/rank查询、barcode和tracking。S4-07默认family schema_version=2，共享末阶段边界/带序基和活动索引，stage_results使用input_ref，另保存显式请求的barcode_basis_readout。schema 1可读并原版本重发；`to_result(schema_version=1)`显式输出旧格式。单尺度schema不变。读取重验窗口/投影/证书/族身份并重算持久化readout，拒绝来源/作用/几何/历史基篡改。`to_family()`从合法P恢复而不重求解。失败阶段保留为Partial，合法零值与缺失严格区分。成本与兼容细节见[S4-07](S4_FILTRATION.md)。

过滤上的顶层结果建议为：

```text
OperatorFamilyResult
├── filtration_identity
├── stage_results[]
├── transports
├── rank_readout
├── barcode_readout
├── tracking_readout
├── provenance
└── status
```

每个 `stage_results[i]` 都是完整 `OperatorResult`。

### 14.1 `TransportResult`

```text
TransportResult
├── source_operator_id
├── target_operator_id
├── source_scale
├── target_scale
├── action
├── rank
├── certificate
└── status
```

其数学对象：

\[
T_{ij}=P_jJ_{ij}|_{\ker L_i}.
\]

### 14.2 Transport 证书

至少验证：

\[
T_{ii}=I,
\]

以及在已构造三元组上：

\[
T_{j\ell}T_{ij}=T_{i\ell}.
\]

### 14.3 Barcode readout

Barcode 必须记录其来源：

```text
barcode.provenance = {
    rank_invariant_source: operator_family,
    oracle_used_for_result: false
}
```

oracle 可以参与测试，但不能成为结果 provenance。

---

## 15. 序列化要求

序列化格式必须保留：

- 所有 identity；
- solver status；
- certificate level；
- basis / weight metadata；
- exact vs approximate；
- bounds；
- provenance。

不得只保存：

```text
barcode
mass
distance
```

而丢失它们属于哪个 \(P\)。

### 15.1 Schema version

顶层建议加入：

```text
schema_version
```

任何破坏语义的字段变更必须提升 schema major version。

---

## 16. 缓存规则

缓存键至少应包含：

```text
input_id
basis_id
weight_id
solver_config_id
tie_break_policy_id
backend_semantics_version
```

仅以边界矩阵 hash 缓存几何输出是不安全的，因为权重和投影选择会改变结果。

---

## 17. 最低验收测试

结果模型冻结前至少应覆盖：

1. `betti=0` 与 `NotComputed` 可区分；
2. `distance=0` 与缺失可区分；
3. 两个不同 `projection_id` 的几何结果不能被自动合并；
4. `selected_mass` 不会被序列化成 `minimum_class_mass`；
5. `ExactOptimal` 必须同时具备合法投影和最优性证书；
6. matrix-free backend 仍能提供稳定 `projection_id`；
7. `OperatorFamilyResult` 中每个 transport 明确引用 source/target operator；
8. barcode provenance 明确来自当前 OperatorFamily；
9. resource exhausted 不会被转换为合法空结果；
10. basis/weight metadata 在 round-trip serialization 后保持。
