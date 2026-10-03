# 结果、身份与序列化

本文描述 [result.py](../src/homology_operator/result.py) 与
[family.py](../src/homology_operator/family.py) 的实际结果类型和 JSON 契约。
拓扑、代表和几何来自同一个 P；不要把不同投影的输出拼成一个联合结果。
调用入口见 [API](INTERFACE.md)，认证细节见 [solver 契约](SOLVER_CONTRACT.md)。

## 六身份

`QueryResult.identity` 和合法 `OperatorResult.identity` 包含且只包含：

| 字段 | 绑定内容 |
| --- | --- |
| `input_id` | 次数、A/D 的形状/元素、三组带序基 |
| `basis_id` | 三组基标识及坐标顺序 |
| `weight_id` | 权重、算术、语义与单位 |
| `projection_id` | 输入/基身份、投影矩阵或版本化 handle、并列策略 |
| `operator_id` | 输入、基、权重与投影身份 |
| `solver_run_id` | 此次独立求解 run；不进入 projection/operator 内容 hash |

内容身份使用规范 UTF-8 JSON 的 SHA256。相同输入/配置可重复产生相同 P 和内容身份，
但 solver_run 独立。`require_same_identity(other)` 比较全部六字段，独立 run 的查询也不能直接混用。
相同数学作用的 Matrix、CyclicAction 或紧凑表示可以有不同 projection_id；当前没有跨表示身份归一化。
几何解释同时需要 basis_id 与 weight_id，不能只保留边界矩阵 hash。

## QueryResult

实际字段为 `state`、`value`、`identity`、`exact`、`details`。
value/details 复制为不可变容器；`to_dict()` / `from_dict()` 提供 wire 编码。

| state | value 规则 / 意义 |
| --- | --- |
| `Computed` | 必须有值；0、False、空 tuple 都是合法值 |
| `NotComputed` | None；本次尚未计算 |
| `Unavailable` | None；当前后端或接口不支持 |
| `ResourceExhausted` | None；已尝试但预算终止 |
| `EmptyDomain` | 空定义域；允许明确约定值，例如空循环域 stretch=0 |
| `NoClass` | None；显式表达无类，与死亡类的合法零代表不同 |

`exact` 是 bool 或 None：精确 F2 的拓扑与坐标读取可为 True；
浮点质量/距离/stretch 为 False，缺失或未定计算可为 None。
它不表示全局最优。`details` 保存算术、舍入政策、查询参数、端点身份或计算成本等实际来源。

普通标量查询返回直接值。`op.readout(name, *args)` 返回 QueryResult，
并在内部历史中保留 query 名称与 arguments；`stretch` / `minimum_class_mass` 使用自己的记录入口。
native 批查询默认不改变算子历史，需保存时显式加入记录的 query_results。

## OperatorResult 的实际格式

顶层 schema_version 为 1，`to_dict()` 的字段集合是：

```text
schema_version
status
identity
input_data
projection
solver
certificate
provenance
query_results
```

`input_data` 保存 ChainWindow，`projection` 保存显式矩阵或受支持的 handle，
`solver` 保存 method、求解状态、认证等级、objective、上下界/gap、配置与配置身份、预算/diagnostics。
`certificate` 是独立 verifier 的结论；backend 原始声明只留在 solver_evidence，
不能凭 true 字段或标签接受合法性/最优性。`provenance` 保存源码/理论/后端/solver/算术等来源。

当前没有单独的 TopologyView、GeometryView、StretchView 或 InputIdentity 类；
它们是数学观察方式，通过 query_results 与身份字段表达，不是额外 JSON 顶层字段。

`op.to_result()` 默认包含 betti，kernel_basis 在未读取时为 NotComputed；
stretch 和 minimum_class_mass 同样保留是否计算的状态，并加入已记录的其他查询。
保存快照不自动运行全表查询、stretch 或另一个 solver。

以下沿用 README 的 `op`：

```python
from homology_operator import OperatorResult

op.readout("selected_mass", (0, 1))
record = op.to_result()
restored = OperatorResult.from_json(record.to_json())
record.require_same_identity(restored)
assert restored.to_dict() == record.to_dict()
```

`from_json` 返回已验证记录；Ready 记录可调用 `to_operator()`，使用保存的 P、配置、run 和 provenance，
不重新求解。读取及转换都重新验证投影/认证，并重放带官方 query/arguments 的 Computed 标量历史、
betti 和已计算核基，拒绝同身份但值被篡改的记录；未读取的 kernel/stretch 保持 NotComputed。
自定义无参数绑定的查询仅复核状态与身份，不宣称其任意内容获得数学认证。
失败记录不能转换为算子。恢复重验/重放有实际成本，调用者需计入完整恢复计时。

## 构造状态、求解状态与认证

OperatorResult 构造状态包括 Ready、InvalidInput、SolverFailed、ResourceExhausted、Unavailable、
InternalValidationFailed。只有 Ready 携带可用于正常读取的已验证投影。
Python 非法输入通常在 ChainWindow 构造时抛 InvalidInput；状态枚举并不表示每个异常自动生成结果记录。

solver 的 Optimal、FeasibleOnly、ResourceExhausted 等状态与 certificate_level 单独保存。
合法中断候选可构成 Ready 算子，但 solver 仍是 ResourceExhausted。
没有 projection 的失败记录不能携带算子查询、bounds 或投影/operator 身份，不能生成算子缓存键。
已验证输入可保留 input/basis/weight/solver_run 的部分身份；没有合法输入时均可为空。

认证分别说明：

- 合法投影：P²=P、AP=0、PD=0 与循环同调保持已验证。
- 当前 objective：Γ_w(P) 是否已计算、是否精确。
- 最优值：全局 bounds 和支持的最优证书是否独立重放成功。

Feasible 不认证最小 stretch；ExactOptimal 必须有受支持且重放成功的最优性证书。
精确 F2 不认证浮点 objective。证书类别、重放上限和中断候选边界见 solver 契约。

## 几何与 stretch 的语义

对循环，selected_mass=m_w(Pz)，class_distance=m_w(P(z+y))，支撑及交/并由同一 Pz 得到。
这些量绑定原基和权重。真实最短类质量

\[
\mu_w([z])=\min\{m_w(x):Ax=0,\ [x]=[z]\}
\]

是不同的优化问题；当前 minimum_class_mass 返回 Unavailable。
selected_mass 不得命名或序列化为真实最短值。

当前投影的 stretch 与最优投影目标分别为

\[
\Gamma_w(P)=\max_{0\ne z,\ Az=0}\frac{m_w(Pz)}{m_w(z)},\qquad
\Gamma_*=\min_P\Gamma_w(P).
\]

当前 objective 的精确值可以给出最优值的上界，不能单凭该值报告 ExactOptimal。
循环域为空时按固定理论 §1.2 取 stretch=0 并标 EmptyDomain；
非空循环域且 Betti=0 时，当前/最优 stretch 是合法 0，不能与另行约定的截面记账 κ=1 混用。
死亡类是零代表、零质量、空支撑，不是缺失或 NoClass。

## 作用表示和恢复

| projection 编码 | 支持范围 |
| --- | --- |
| `{nrows, ncols, rows}` | 显式 Matrix；空形状保留 |
| `{kind: "CyclicTrace", version: 1, m, complement}` | 已合并，m=2/3/4 的固定结构族；P 的 complement=false |
| `{kind: "CompactF2", version: 1, form, factors, pivots, complement}` | [S4-04 / PR #80](https://github.com/proffitteoy/homology-operator/pull/80) 已合并，GeneralizedInverse / HC 紧凑作用 |

CyclicTrace handle 由受支持公式决定全部链上的 action；L 使用同参数的补作用。
未知版本、额外字段、非法形状/参数和身份篡改拒绝；链输入 A/D 始终只接受 Matrix schema。
紧凑表示的声明不等于已完成发行兼容政策。

当前 CompactF2 恢复由 Python 从因子/坐标重建作用并独立验证，不要求 Rust 扩展；
普通 project/L、身份与 handle 保存不展开完整 P。生成集、广义逆或 HC 条件及循环同调保持仍需验证。
HC 独立检查 AH=0、CD=0、CH=I，并拒绝不保持同调的零投影。
Compact action 当前另支持通用 CycleBounds 重放，其他优化 proof 格式明确拒绝；后续 solver 工作包另行实现。
此项由 [PR #80](https://github.com/proffitteoy/homology-operator/pull/80) 合入 main；准确源码、回归和测量记录见性能协议。
Factorized 验证还检查 A/D 与窗口一致、AGA=A、DUD=D；D 的像分解独立建立一次并复用，
不使用 solver 提供的分解或 true 标签。拓扑的规范核基由 ker(L)=im(P) 流式生成，
从最高原坐标向下选 pivot 并清除其他基向量中的该位，按 pivot 升序读取，得到该子空间唯一的右向左 reduced basis。
reference 左向右 RREF 的 canonical kernel 向量在自己的自由坐标为1，其他自由坐标为0；
非零 pivot 坐标都在该自由坐标之前，故自由坐标就是最高非零位，同样给出上述唯一 reduced basis。
因此完整核基与过滤坐标和 reference 一致；该论证依赖独立验证的幂等性，不用于接受非法候选。
核基/transport 输出本身可能平方大，按实际输出大小分配。

JSON 将 Fraction 编码为 `$fraction` 标签；普通单键 `$fraction` / `$mapping` 字典用 `$mapping` 转义。
读取拒绝重复 JSON 键、非有限数、未知字段/schema、混用身份和篡改证书/查询。
读取和算子构造均重新验证投影；优化认证额外重放证书。规范编码与容器冻结不替代数学验证。
破坏格式/语义的变化需版本化；保留旧 Matrix 与受支持 handle 的明确恢复边界。

## 原生几何批查询与进程内准备

S4-06 的 `geometry_batch` 在一个 QueryResult 中保存代表、selected_mass、距离及原坐标支撑交并，六身份来自传入的算子。`GeometryWorkspace` 持有同一 P/基/权重的原生准备与私有缓冲，复用时核对完整身份（含 solver_run_id）；准备对象不进入 OperatorResult，也不把 kernel/stretch 或未查询几何标为 Computed。批记录只有被调用者显式加入 query_results 时才进入快照，恢复继续复核身份与合法投影。

质量算术由 window.arithmetic 决定：u64 逐项检查求和，超界整数/溢出总和及非整数 Fraction 使用任意精度后备，浮点保留 binary64 fsum。details 保存准备/转换/原生/绑定/decode/后备分段、后备次数和原因；准备子项不得与准备总成本重复相加，结果冻结计入完整调用。后备不更换 P 或认证等级。空批为 Computed 空 tuple；合法零质量仍为0；缺少扩展或不支持的 action 为 Unavailable；非循环/混用拒绝，浮点溢出明确 NumericalFailure。

## OperatorFamilyResult

`family.to_result()` 返回不可变族快照，默认 schema_version=2。两个版本共有字段包括：

```text
identity, status, scales, windows, stage_results
weight_policy, duplicate_policy, terminal_extension
transports, rank_readout, barcode_readout, tracking_readout, provenance
```

schema 2 的 windows 共享末阶段边界/带序基和各阶段活动索引；stage_results 以 input_ref 引用输入，
另保存显式请求的 barcode_basis_readout。schema 1 可读并原版本重发；
`to_result(schema_version=1)` 显式输出旧格式。单尺度 schema 不变，schema 2 需要读取客户端升级。
仅不可变边界/基共享，不合并权重、投影或 solver run；细节见 [S4-07](S4_FILTRATION.md)。

每个阶段保留 OperatorResult 的身份、投影、证书、查询与失败记录。传输引用源/目标算子完整身份，
保存 T_ij 的 kernel 坐标 action、目标原链 chain_action、rank 与证书记录。
barcode 必须由该族相邻传输读取并保持 rank invariant，provenance 声明 operator_family 与 oracle_used_for_result=false。

```python
from homology_operator import OperatorFamilyResult

# 沿用 README 的 family。
record = family.to_result()
restored = OperatorFamilyResult.from_json(record.to_json())
recovered_family = restored.to_family()
assert recovered_family.transport_rank(0, 1).value == 1
```

恢复重新验证窗口、投影与认证、族身份、已存传输/rank/barcode/tracking、几何值及历史区间基；
`to_family()` 使用记录中的合法 P，不重新求解。恢复可能重新计算保存的读取结果，成本需要计入测量。
Partial 不转换为 Ready，失败不转换为空阶段或空 barcode。

## 缓存、资源和验收

`record.cache_key(solver_config_id, tie_break_policy_id, backend_semantics_version)`
包含 input/basis/weight/projection/operator 内容身份以及实际配置、并列策略和 backend 语义版本；
solver_run 保留在 provenance 中，不进入可复用内容键。调用者应传真实配置，不能传占位名称。
仅以 A/D hash 缓存几何不安全，不同 P 或权重需分开。

resource_usage 保存实际 states、wall_time、limits 和后端提供的诊断。
CancellationToken 是运行期状态，不进入 solver_config、内容身份或 JSON。取消原因是 cancelled，
不将 ResourceExhausted 改成合法0；外部 timeout/OOM 由执行入口另记。
显式后备的 requested/selected/reason 保存在 resource_usage.backend_selection。
缺少 CPU/RSS 等指标不伪造为 0；逻辑条目、stored_words 或 tracemalloc 都不是操作系统峰值 RSS。
solver 预算、独立验证/恢复成本和外部 timeout/OOM 按 [性能协议](BENCHMARKS.md) 分别记录。

修改身份/schema/action 后必须验证 round-trip、跨投影/权重/基/run 混用拒绝、
非法 handle 与证书篡改、合法零/缺失状态和族源/目标绑定。
当前测试入口与历史证据见 [验证说明](VALIDATION.md)。
