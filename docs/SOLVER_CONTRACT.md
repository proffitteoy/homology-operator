# Solver 契约

[English](en/SOLVER_CONTRACT.md) · [API](INTERFACE.md) · [目标的定义与证明](MATHEMATICS.md)

## 职责与合法性

Solver 为一个 ProjectionProblem 选择投影，不定义读取语义、不生成独立 barcode，
不改变 HomologyOperator 的数学含义。所有输出进入算子前独立验证：

$$
P^2=P,\quad AP=0,\quad PD=0,\quad z+Pz\in\operatorname{im}D\ \ (Az=0).
$$

前三项不足以保证同调保持：非零同调窗口的零投影也可能满足它们。
当前目标为最小化最坏加权循环 stretch：

$$
\Gamma_w(P)=\max_{0\ne z,Az=0}\frac{m_w(Pz)}{m_w(z)},\qquad
\Gamma_*=\min_{P\ \mathrm{legal}}\Gamma_w(P).
$$

selected_mass 是当前 P 的选定质量，不是真实最短类质量。
换 solver 可以改变代表与几何，但不改变查询定义；不得为过滤传输另改阶段目标。

## 请求与结果绑定

ProjectionProblem 绑定窗口、ResourceLimits、目标、请求认证、并列策略、算术、
声明结构、matrix_free_output、确定性、solver_options 及可选取消 token。
调度先检查 capabilities()，再核对返回的完整配置、算术、并列与预算。
结构标签不能代替结构验证，也不能扩大算法支持域。

ProjectionSolution 保留 status、projection、六身份、solver run、认证、当前 objective、
下/上界及 gap、方法/配置、可用的广义逆、资源用量和诊断。
没有合法投影的失败不能构造可用算子；耗尽前的合法候选可保留，但不伪装完成搜索。
状态与认证等级独立，缺失 objective/bounds 保持缺失。

## 认证等级

| 等级 | 含义 |
| --- | --- |
| Feasible | 已独立验证投影合法，不声明全局最优 |
| ExactOptimal | 合法投影、精确 objective 和独立重放的支持域内最优性证明 |
| CertifiedUpperBound | 有效的全局最优值上界 |
| CertifiedInterval | 独立有效的 L≤Γ*≤U |
| Heuristic | 算法性证据；接受的投影仍须完整合法性验证 |

精确 objective、相等有效界和支持的证明共同成立时报告 ExactOptimal。
F2 代数精确不等于浮点最优界精确；验证字段来自独立 verifier。
空循环空间与循环非空但零同调分别表达，即使约定/当前值都是 0。

## Reference 支持域

| Solver | 当前范围 |
| --- | --- |
| FeasibleSolver | 一般带基窗口，整数/有理/浮点权，显式 Matrix，StableBasisOrder；objective 初始未计算 |
| ExhaustiveExactSolver | 小规模精确权，完整截面搜索与最优证书 |
| GreedyCertifiedSolver | 精确权，穷举循环、确定性贪心截面与独立 bounds |
| Rank2ExactSolver | 精确权且 Betti=2；一般或显式验证的图/三终端结构 |
| StructuredFamilySolver | 声明 CyclicTrace，m=2/3/4、等精确正权；Matrix 或 CyclicAction |

GeneralSearchSolver 未注册为公共后端。实际选项与返回类型见 [API](INTERFACE.md)。

## 证书重放与搜索限制

CycleBounds 枚举非零循环，重算当前 Γ 并验证通用下界：Betti=0 为 0，非零 Betti 至多给出 1。
重放最多 100,000 个非零循环，不能凭此认证大于 1 的全局下界。

ExhaustiveExactSolver 在固定非循环 retraction 下搜索 `2^(rank(D)*β)` 个商截面；
独立 verifier 使用另一个商基提升枚举。最多 100,000 非零循环，且
`candidate_count * max(1, nonzero_cycle_count) ≤ 100000`。
并列按固定 retraction 下的原坐标确定，不宣称所有非循环延拓的全局字典序。
只有完成全部搜索才认证 ExactOptimal。

GreedyCertifiedSolver 按质量及 packed 原坐标排序，选择模边界独立的同调生成元。
理论 Γ≤β（β>0）与实际 Γ、全局最优性分开；β=0 时 Γ=0。
重放要求 `nonzero_cycle_count * max(1, β) ≤ 100000`。
普通 ExactOptimal 请求通常不支持；完整且等界的结果可独立认证最优。
中断种子不能继承未完成的贪心保证。

Rank2ExactSolver 要求 β=2，并实际验证声明结构。一般路径搜索两个商生成元的边界修正；
图/三终端归约分别验证自己的前提。不支持的结构/重放规模返回 Unavailable。
StructuredFamilySolver 仅接受固定声明族，并验证结构公式和独立证书。

## Rust 后端

NativeFeasibleSolver 的三个链空间最多 64 维，返回与 reference 相同的确定性 G/U/P。
NativeFactorizedSolver 要求 matrix_free_output=True，输出 Factorized 或 HC；
认证为 Feasible、objective 初始未计算，不额外提供全局最优证书。
PreparedMatrix 是代数分解工具，不是投影 solver。

四种限定优化 solver 可用 Native 前缀或 native=True 选择；保持对应 reference 的支持域、
objective、并列、预算和独立证书重放。超出原生整数质量范围时显式后备到任意精度计算。
后备只能到对应的已支持 reference solver，原因可见；Factorized 输出没有转成显式矩阵的隐式后备。
扩展不可用、不相容或域不支持时返回 Unavailable。

## 资源与取消

state、wall-time、逻辑 matrix-entry 预算通过协作检查点执行。
证书重放、算子构造和恢复验证有独立成本；没有 RSS 硬限制或单步抢占保证。
取消返回 ResourceExhausted 并保存原因；保留的任何候选仍须独立验证。
读取、恢复和后备的实际行为见 [结果模型](RESULT_MODEL.md)和 [API](INTERFACE.md)。
