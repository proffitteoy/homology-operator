# Homology Operator：逻辑接口

> 当前是语言无关的工程契约，尚无可调用实现。对象职责见 [ARCHITECTURE](ARCHITECTURE.md)，身份与状态见 [RESULT_MODEL](RESULT_MODEL.md)，求解行为见 [SOLVER_CONTRACT](SOLVER_CONTRACT.md)。

本契约延续固定理论正文的 D1、T2、T3 与第 3 节；不另建一套算子定义。

## 输入与构造边界

固定非负次数 `k`，采用列向量约定：`A` 为 `m × n`，`D` 为 `n × p`，分别作用于 `C_k` 与 `C_{k+1}`。`ChainWindow` 必须保存三个链空间的维数、带序基及 `n` 个正权重。

- 矩阵和查询向量在 F2 上；外部输入应提供明确的 0/1 坐标，不能静默截断、取模或改变基顺序。
- 构造时验证矩阵形状、各基长度、基内标识唯一、权重长度和 `AD=0`。允许零维链空间，但须保留 `0 × n` 等矩阵形状，不从空数组猜测维数。
- 权重必须有限且严格正，并记录其语义、单位及算术策略；几何单位不由正权重本身推断。
- 非法输入对应 `InvalidInput`；不得返回半合法算子。查询向量长度或输入域错误应返回明确的校验错误，具体异常类型在首次语言实现时确定。

不要求调用者先提供 PH、同调基或最短类表。内部消元和循环空间计算必须计入完整成本。

主构造路径为 `ChainWindow → ProjectionProblem → ProjectionSolver → ProjectionSolution → 独立验证 → HomologyOperator`。后验证至少包括 `P²=P`、`AP=0`、`PD=0`，以及所有循环 `z` 的 `z+Pz∈im(D)`。验证全部循环可通过验证 `ker(A)` 的一组基完成；不能只验证前三项。

参考构造可用满足 `AGA=A`、`DUD=D` 的广义逆，形成 `P=(I+DU)(I+GA)`、`L=I+P`。合法算子具有 `Ready` 状态；solver 的求解状态与认证等级单独保留。

## 单尺度查询

所有查询引用同一 `projection_id`；支撑和权重分别按当前 `basis_id`、`weight_id` 解释。

| 逻辑接口 | 输入域 | 定义或保证 |
| --- | --- | --- |
| `project(x)` | 任意 `C_k` 链 | `Px`，仅线性作用，不赋予非循环同调语义 |
| `apply_operator(x)` | 任意 `C_k` 链 | `Lx=x+Px` |
| `kernel_basis()` | 无 | `ker(L)` 的基；可选计算状态与空基区分 |
| `betti()` | 无 | `dim ker(L)`，0 是合法值 |
| `is_cycle(x)` | 任意链 | `Ax=0` |
| `is_boundary(x)` | 任意链 | `x∈im(D)`；非循环必为 false |
| `class_representative(z)` | 循环 | `Pz` |
| `same_class(z,y)` | 两个循环 | `Pz=Py` |
| `selected_mass(z)` | 循环 | `m_w(Pz)` |
| `class_distance(z,y)` | 两个循环 | `m_w(P(z+y))` |
| `support(z)` | 循环 | `supp(Pz)`，返回当前基中的坐标索引 |
| `shared_support(z,y)` | 两个循环 | `supp(Pz)∩supp(Py)` |
| `union_support(z,y)` | 两个循环 | `supp(Pz)∪supp(Py)` |
| `stretch()` | 无 | 当前投影 objective 的结果和计算状态 |
| `certificate()`、`metadata()` | 无 | 代数、solver 认证和完整身份/provenance |

质量定义为 `m_w(x)=Σ_i w_i x_i`，其中 `x_i∈{0,1}`。类查询遇到非循环时默认拒绝；第一版不要求提供 `retraction_mode`。路线图中的 `mass_of_projection`、`support_of_projection`、`projection_metadata` 是同一语义的描述，首次实现统一采用上表与架构契约的命名，不需建立重复别名。

真实最短类质量 `minimum_class_mass` 是独立的可选优化查询，不能用 `selected_mass` 填充。同样，精确算出当前 `Γ_w(P)` 不等于证明其为 `Γ_*`；认证等级依 solver 契约。

核通过循环的商映射与原同调显式对应。共享支撑须同时与加权质量恒等式核对：`m_w(Pz)+m_w(Py)=m_w(P(z+y))+2m_w(supp(Pz)∩supp(Py))`。核基可按需查询；列出全部核向量或全类表可能有指数规模，不能承诺全表免费。

## 过滤与传输

Phase 2 支持有限有序过滤、包含映射 `J_ij`、坐标对应、权重继承和明确末端延拓规则。`OperatorFamily` 的逻辑入口是 `stage(i)`、`transport(i,j)`、`transport_rank(i,j)`、`barcode()`、类/质量/支撑追踪及 transport 证书。

输入映射必须满足链映射与复合相容性；第一版仅要求过滤包含映射。跨尺度权重是否继承必须显式记录。

`T_ij=P_j J_ij|ker(L_i)` 绑定源与目标算子身份，须满足 `T_ii=I` 与 composition。Barcode 从这些传输的 rank invariant 恢复；逐尺度 Betti 和外部 PH 结果不能替代该来源。重复尺度、区间端点与末端存活的编码在 Phase 2 实现前明确并测试。

## 失败与缺失

构造状态、solver 状态、认证等级和可选查询状态是不同字段。`0`、`NotComputed`、`Unavailable`、`ResourceExhausted`、`EmptyDomain`、`NoClass` 按结果契约分别表示。

资源不足不能静默退化为近似 PH；尚未实现的求解后端明确返回 `Unavailable`。精确有理证书、数值上下界和启发式结果分别标识。

按固定理论提交主证明 §1.2 的约定，若 `ker(A)={0}`，stretch 的内层最大值取 0；结果同时标明空定义域，不能把这个约定值当成缺失。若存在非零循环但 Betti 为 0，则 `P` 在循环上为 0，当前 stretch 同样为合法零值。后续实现须分别验证数值与定义域信息。该数值约定见 [固定理论正文](https://github.com/proffitteoy/homology-operator-lab/blob/6143729669902ee875b211b58085e954c76cdf88/docs/proof/PROOF.md)。
