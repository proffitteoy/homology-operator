# Python API

本文描述实际 Python 入口及其输入域。安装和最小窗口见 [根 README](../README.md)，
数学职责见 [架构](ARCHITECTURE.md)，状态/schema 见 [结果模型](RESULT_MODEL.md)。
已合并与开发中功能的边界见 [文档索引](README.md)。

可选的 [source mapping 协议](en/guide/input-semantics.md#source-mapping-and-location)
规定单形、原始点 ID/坐标、单位、阶段与周期平移，并绑定输入和过滤身份。
`window.locate_chain(x, degree=0)` 定位原始链（次数偏移 -1/0/1）；
`op.locate_support(z)` 定位同 P 代表，`family.track_location(x,i,j)` 定位传输后的代表。
未提供来源映射时只返回支持集，不推测坐标。

## 导入与矩阵

公共 reference 类型从 `homology_operator` 导入；可选原生工具从 `homology_operator.native` 导入。
包名是 `homology-operator`，Python 导入名是 `homology_operator`。

```python
from homology_operator import Matrix

a = Matrix.from_rows(((1, 1, 0), (0, 1, 1)))
assert a.rank() == 2
assert a.kernel_basis() == ((1, 1, 1),)
assert a.apply((1, 1, 1)) == (0, 0)
assert Matrix.from_rows((), ncols=3) == Matrix.zero(0, 3)
```

`Matrix(nrows, ncols, rows)` 是不可变、保留显式形状的 F2 矩阵：

| 入口 | 返回 / 行为 |
| --- | --- |
| `zero(m,n)`、`identity(n)` | 显式矩阵；保留 0×n 和 m×0 |
| `from_rows(rows, ncols=None)` | 非空行可推断列数；空行集合需显式 ncols |
| `from_columns(columns, nrows)` | 以列向量构造，保留空形状 |
| `M + N`、`M @ N` | F2 加法/矩阵乘法；检查形状 |
| `apply(x)`、`transpose()` | tuple 坐标 / 转置矩阵 |
| `rref()` | `(reduced_matrix, pivot_columns)`；原列顺序不交换 |
| `rank()`、`kernel_basis()`、`image_basis()` | int / tuple of vectors；核与像在原坐标下 |
| `solve(b)` | 自由变量置零的确定性解；不可解为 None，合法空解为 `()` |

矩阵和向量只接受整数 0/1；bool、float、取模或截断输入均拒绝。
形状和坐标错误抛 ValueError。reference 是小规模显式正确性基线，不承诺大尺寸效率。

内部使用 Python 整数 bitset；构造参数、`rows` 的 tuple 坐标视图和 JSON 格式保持兼容。
导出时一次读取 `rows`，避免反复解码。稳定 RREF 与像坐标基按不可变矩阵分别懒准备、复用；
`solve_many(rhs)` 与 `solve(b)` 共享像坐标基。只查询秩不会分配平方规模行变换。
恢复对象的进程内缓存从空开始。

## 链窗口

实际构造签名：

```text
ChainWindow(k, A, D, basis_previous, basis_current, basis_next, weights,
            weight_semantics="abstract_positive_cost", unit=None,
            arithmetic="ExactRational", source_metadata={})
```

`A` 是 m×n，`D` 是 n×p，采用列向量约定；三组基分别对应 m、n、p。
构造时检查非负次数、形状、各基长度/唯一非空标识、`AD=0`、n 个有限严格正权。
允许空链空间。输入不合法抛 `InvalidInput`（ValueError 子类），不生成半合法算子。
基标识与顺序必须保留；支撑索引和几何量在 `basis_current` 下解释。

| arithmetic | 接受的权重 | 读取语义 |
| --- | --- | --- |
| `ExactInteger` | int，任意精度 | 几何精确，objective 比值用 Fraction |
| `ExactRational`（默认） | int / `fractions.Fraction` | 精确有理运算 |
| `FloatingPoint` | int / float / Fraction，显式转成有限正 binary64 | binary64 fsum；质量、距离及 stretch 数值结果非精确认证 |

权重的语义与单位由调用者声明，不从数值或几何名称推断面积/体积。
`to_dict()` / `from_dict(data)` 保存显式形状、权重类型与来源，读入时重新验证。
点云、Rips 和通用复形构造不是当前公共输入接口。

## 求解与构造算子

```text
ResourceLimits(state_limit=100000, wall_time_limit=10.0, matrix_entry_limit=1000000,
               packed_word_limit=None)
ProjectionProblem(window, resource_limits=ResourceLimits(),
                  objective="MinimumStretch", requested_certificate_level="Feasible",
                  tie_break_policy="StableBasisOrder", arithmetic_policy=None,
                  input_structure="GeneralChainWindow", matrix_free_output=False,
                  deterministic=True, solver_options={}, cancellation=None)
solve_projection(problem, backend="FeasibleSolver", *, fallback=False) → ProjectionSolution
HomologyOperator(window, solution, repository_revision="unknown")
```

默认预算的 wall time 单位为秒。限制在 checkpoint 检查；matrix-entry 是保守逻辑条目上限，
不是 RSS 硬上限。独立验证/证书重放及快照恢复成本另外发生，不能据该预算声称全流程抢占。
`arithmetic_policy=None` 沿用窗口的算术。请求不能通过标签扩大 solver 的支持域。

以下示例沿用根 README 的 `window`：

```python
from homology_operator import (
    HomologyOperator, ProjectionProblem, ResourceLimits, solve_projection,
)

problem = ProjectionProblem(
    window,
    resource_limits=ResourceLimits(state_limit=1000, wall_time_limit=10),
    requested_certificate_level="ExactOptimal",
)
solution = solve_projection(problem, "ExhaustiveExactSolver")
if solution.projection is None:
    raise RuntimeError((solution.status, solution.diagnostics))
op = HomologyOperator(window, solution)
assert solution.certificate_level == "ExactOptimal"
```

字符串调度支持 `FeasibleSolver`、`ExhaustiveExactSolver`、`GreedyCertifiedSolver`、
`Rank2ExactSolver`、`StructuredFamilySolver`。也可传入提供 `capabilities()` / `solve(problem)` 的对象；
四个限定 solver 另有 `NativeExhaustiveExactSolver`、`NativeGreedyCertifiedSolver`、
`NativeRank2ExactSolver`、`NativeStructuredFamilySolver` 字符串入口，或使用现有类的 `native=True`。
`NativeFeasibleSolver` 与 `NativeFactorizedSolver` 同时支持字符串和对象调用。
未知后端或不支持的请求返回 Unavailable。显式 `fallback=True` 仅在 native 显式可行构造或四种限定
solver 返回 Unavailable 时尝试同名 reference solver，保留支持域/认证请求，并在
`resource_usage.backend_selection` 保存 requested、selected、fallback_reason；对象的 `native=True` 同样适用。
`NativeFactorizedSolver` 没有 reference 后备，不把 matrix_free 请求降级成显式矩阵。

统一调度核对 capability、配置、并列策略、算术和报告预算，再独立验证返回投影与证书。
算子构造再次检查 `P²=P`、`AP=0`、`PD=0` 和循环同调保持；失败抛 `ValidationError`。
检查 `solution.projection` 是否存在后再构造算子。
ResourceExhausted 也可能保留合法候选；这时算子可为 Ready，但最优认证不能由停止状态推断。
solver 各自的结构、枚举/重放上限、并列与中断语义见 [solver 契约](SOLVER_CONTRACT.md)。

Finite H1/H2 pairs additionally support
[`OperatorFamily.optimal_volume`](en/INTERFACE.md#finite-pair-optimal-volume):
explicit death-stage upper costs, birth/death/intermediate constraints, original
filling/boundary geometry and independently replayed exact certificates. Infinite
pairs return `EmptyDomain` with `applicability="NotApplicable"`. This is separate
from fixed-boundary filling and does not change the family's P or PH.

## 单尺度查询

| 方法 | 输入域 | 返回值 / 定义 |
| --- | --- | --- |
| `project(x)` | 任意 C_k 链 | tuple，Px |
| `apply_operator(x)` | 任意 C_k 链 | tuple，Lx=x+Px |
| `kernel_basis()` | 无 | tuple of vectors，ker(L) 的基；按需缓存 |
| `betti()` | 无 | int，dim ker(L) |
| `is_cycle(x)`、`is_boundary(x)` | 任意链 | bool，Ax=0 / x∈im(D) |
| `class_representative(z)` | 循环 | tuple，Pz |
| `same_class(z,y)` | 两个循环 | bool，Pz=Py |
| `selected_mass(z)` | 循环 | 数值，m_w(Pz) |
| `class_distance(z,y)` | 两个循环 | 数值，m_w(P(z+y)) |
| `support(z)` | 循环 | tuple，supp(Pz) 的原基坐标索引 |
| `shared_support(z,y)`、`union_support(z,y)` | 两个循环 | tuple，投影支撑的交 / 并 |
| `readout(name, *args)` | 上述方法的输入域 | 带身份的 QueryResult，并记录查询参数/值 |
| `stretch(limits=None)` | 无 | QueryResult，当前 Γ_w(P) 及计算状态；独立于全局最优认证 |
| `minimum_class_mass(z, limits=None)` | 循环 | 预算内精确最短类质量、原链代表和边界见证的 QueryResult |
| `certificate()`、`metadata()` | 无 | 独立验证记录 / 身份与 provenance、权重元数据 |
| `to_result()` | 无 | OperatorResult 快照 |

标量方法返回直接值；`readout` 返回带状态/身份的记录。`readout` 支持从 project 到 union_support 的逻辑查询，
stretch 和最短质量采用自己的 QueryResult 入口。类查询遇到非循环抛 ValueError。
当前没有 `retraction_mode`；不能把原始 `project` 的非循环结果当作同调类。

`selected_mass` 是选定代表质量，不能填充真实最短类质量。
新增查询实现需要使用当前源码。`minimum_class_mass` 独立枚举 `z+im(D)` 的不同元素，不枚举全部循环或全部截面，
也不改变 P。整数/有理权受支持；浮点权和显式 `packed_word_limit` 返回 `Unavailable`。
`limits` 沿用 `ResourceLimits`，默认 100000 状态、10 秒、1000000 逻辑矩阵条目；
每个实际计算的边界计一个状态。逻辑存储保守上界为
`2*n*p + 2*n*min(n,p) + 8*(n+p) + 2*m`，不是 RSS 限制。
循环输入校验在预算之前；墙钟采用协作检查，包含最后的见证校验，不保证单步抢占。

完成时 `value` 为真实最短质量、`exact=True`；`details` 中的 `representative=y`、
`boundary_witness=b` 和 `input_cycle=z` 保留原基坐标，满足 `Ay=0`、`Py=Pz`、`Db=y+z`。
质量并列时选择原链二元坐标元组的字典序最小者。完整边界枚举或质量零的非负下界
可认证该类查询的 `ExactOptimal`；不改变 solver 的全局截面证书。
`lower_bound`、`upper_bound` 和 `optimality_gap` 均指该类最短质量。

中断时 `ResourceExhausted` 的 `value/exact` 为 None，details 保留合法候选、精确
`candidate_mass`、下界 0、候选上界、gap、`CertifiedInterval`、预算和用量。
超时后的候选即使为零也不改报完成。正常完成的零类、空同调最短值为合法的 `Computed` 0。
快照按类/预算保留请求，并在 `minimum_class_mass` 下保留最近一次结果。

共享支撑满足精确权下的恒等式
`m_w(Pz)+m_w(Py)=m_w(P(z+y))+2m_w(supp(Pz)∩supp(Py))`。
完整核向量表或类表可能有指数规模，API 不免费枚举全表。

stretch 定义为非零循环上 `m_w(Pz)/m_w(z)` 的最大值。
空循环域返回 `EmptyDomain` 与约定值 0；非空循环域但 Betti=0 时返回 Computed 的合法 0。
该约定来自 [固定理论正文 §1.2](https://github.com/proffitteoy/homology-operator-lab/blob/6143729669902ee875b211b58085e954c76cdf88/docs/proof/PROOF.md)，
资源耗尽或未计算不能用这个 0 替代。

## 固定边界最小填充

`minimum_filling(window, z, filling_window, *, limits=None, cancellation=None)`
与 `validate_minimum_filling` 从 `homology_operator` 导入；独立求解
`min m_{k+1}(c), D c=z`，不依赖投影，不附加出生/死亡配对，不改变 PH。

填充成本复用次数 k+1 的 `ChainWindow`：`A=window.D`，
`basis_previous=window.basis_current`，`basis_current=window.basis_next`，
基标识和顺序必须一致。上维窗口的 D 可以描述更高边界，但不约束本查询。
必须显式提供上维正权、unit 和非空字符串 `source_metadata["source"]`；
原窗口的当前维权重不用于填充质量。长度/面积/体积语义要求上维次数为 1/2/3，
unit 计数要求所有上维权重为 1。来源声明参与绑定，不自动证明实际几何测量正确。

返回现有 `QueryResult`：Computed 的 value 包含 chain、重算 boundary、上维 support 索引和 mass，
details 含独立复核的 ExactOptimal 证据及相等上下界。零边界返回合法零填充；
Infeasible 的 value=None 并附对偶不可行见证；ResourceExhausted 的 value=None，
保留 reason 和可选的可行 details.candidate，不宣称最优；Unavailable 表示浮点上维权、
显式 packed-word 请求或超出精确重放域。非循环、基/矩阵/次数/来源不匹配抛 ValueError。

整数/有理数搜索完整枚举 `c0+ker(D)`，最多 100,000 个可行填充，
即核维数最多 16；零边界与不可行证据不受该枚举上限约束。
并列按原上维坐标的 `sum(c_i*2**i)` 最小选择。
limits 复用 ResourceLimits，state 为已评估填充数，时间与逻辑条目在检查点核对。
输入验证/hash 和独立证书重放另计成本；没有 native 填充求解器或 RSS/硬抢占保证。
完整可执行例子见 [英文 API](en/INTERFACE.md#fixed-boundary-minimum-filling) 和
[single_scale.py](../examples/single_scale.py)。

## 过滤与传输

普通 `barcode()`
只消费相邻核坐标映射；历史区间基与全部区间 rank 按真实输出大小另行请求。
`cache_limit=64` 分别限制 action/transport/rank 及阶段核的 LRU 条目，0全部禁用。
`kernel_cache_byte_limit=16777216` 额外限制 Python 核基/坐标分解和原生核矩阵、
分解、传输工作区的合计核算字节；0禁用阶段保留。Python容器/整数按实际大小计费，
原生数据按payload与行开销估计；同一阶段的表示一起驱逐，超预算阶段只临时计算。
重复查询可能重新计算；family不填充operator的核/原生几何工作区缓存。
调用方输入/算子自身缓存、临时工作区、显式请求结果与分配器容量不在预算内，
这不是进程RSS硬限制。运行时策略不进入身份或两种快照schema，恢复采用默认策略。

```text
OperatorFamily(scales, windows, operators, weight_policy="Inherited",
               duplicate_policy="OrderedStages", terminal_extension="Constant",
               cache_limit=64, kernel_cache_byte_limit=16777216)
```

阶段非空、有序且同次数；允许合法零维窗口。包含由三个次数的基标识建立，验证链映射及复合相容。
`Inherited` 检查已有坐标权重继承；显式 `Variable` 允许变权，单位和权重语义保持一致。
重复 scale 保留不同阶段索引，末端为常量延拓。失败阶段传入失败 OperatorResult 并保留 Partial 状态。
调用者无需提供 PH、同调基、barcode 或最短类表。

| 方法 | 返回 / 来源 |
| --- | --- |
| `stage(i)` | 该阶段算子或失败记录 |
| `inclusion(i,j,degree=0)` | 指定次数偏移 −1/0/1 的坐标包含 Matrix |
| `transport(i,j)` | QueryResult，T_ij=P_j J_ij\|ker(L_i) |
| `transport_rank(i,j)` | QueryResult，rank(T_ij) |
| `transport_certificate(i,j)` | QueryResult，恒等、composition、目标核与诱导同调映射检查 |
| `barcode()` | QueryResult，从相邻核坐标传输读取区间多重集 |
| `barcode_basis()` | QueryResult，显式读取死亡回改后的历史区间基、原链代表与阶段身份 |
| `rank_table()` | QueryResult，显式读取全部区间 rank，输出量为 s(s+1)/2 |
| `track_class(x,i,j)` | QueryResult，源循环在目标原坐标的投影代表 |
| `track_mass`、`track_support` | 参数同 track_class；QueryResult，目标代表几何 |
| `track_shared_support(x,y,i,j)`、`track_union_support(x,y,i,j)` | QueryResult，两个源循环的目标支撑交 / 并 |
| `endpoint_mass_bound(x,i,j,limits=None)` | QueryResult，终点 stretch 与变权因子的质量控制 |
| `to_result(schema_version=None)` | 默认 schema 2 的 OperatorFamilyResult；可显式请求旧 schema 1 |

阶段索引要求 `0≤i≤j<len(scales)`。传输 value 包含 kernel 坐标的 `action` 和目标原链坐标的
`chain_action`，包括零维形状；记录目标六身份和 source/target 完整身份。
失败端点返回缺失状态。中间阶段失败不阻止合法端点的直达作用，但不能提供完整 composition 证书。

barcode 的 value 为区间记录 tuple：`[birth_stage, death_stage)`，multiplicity 合并相同端点；
`death_stage=None` 表示末端常量延拓下存活。不同阶段可具有相同 scale，
用 `zero_scale_length=True` 明示同尺度的跨阶段区间。有限阶段不能恢复未存的阶段内事件。
空 barcode 为 Computed 空 tuple，失败 rank 不能伪装成空表。
provenance 固定注明当前 operator_family，`oracle_used_for_result=false`。

tracking 只接受源循环，按索引嵌入计算目标投影的作用；死亡类返回合法零链、零质量与空支撑。
`endpoint_mass_bound` 使用终点 stretch、源选定质量与 `max(w_j/w_i)`，不乘中间 stretch。
浮点仅给数值观察，`bound_verified=None`。完整实例见 [examples/filtration.py](../examples/filtration.py)。

## 出生配对最短 H1 环

`family.optimal_1_cycle(reference, *, limits=None, cancellation=None)` 在特征出生阶段
完整搜索其已认证历史类，返回最短 F2 支撑、质量、出生算子的六身份和来源定位。
要求逐单形来源、H1，以及单位成本或经来源坐标核验的精确有理边长；边界秩最多 16。
该 `BirthHistoricalClass` 可行域区别于任意循环/阶段的固定类查询，也区别于只要求包含出生边的最短路。
资源中断保留显式状态和可选可行候选，不认证最优；不支持域返回 Unavailable。
结果是独立 QueryResult，JSON 解码后用公开的 `validate_optimal_1_cycle` 重放证书，
不写入 family 快照。完整支持域、历史相容性论证和 HomCloud 对照边界见
[英文 API](en/INTERFACE.md#birth-pair-optimal-1-cycle) 与
[过滤指南](en/guide/filtration.md#birth-pair-cycle-contract)。

## 可选 Rust 扩展

实际构建组合：Rust 1.98.1、PyO3 0.29.3、maturin 1.15.0，Cargo.lock 锁定依赖。
native CI 覆盖 Windows x64/MSVC + Python 3.10，以及 Linux x64 + Python 3.12；
其他组合未由该矩阵验证。Windows 需要 MSVC C++ 工具链，编译器固定在
[rust-toolchain.toml](../native/rust-toolchain.toml)。从根目录构建和安装：

```powershell
uv sync --locked --python 3.10
$pythonPath = uv run --locked python -c "import sys; print(sys.executable)"
$env:RUSTUP_TOOLCHAIN = '1.98.1'
uv tool run --from maturin==1.15.0 maturin build --manifest-path native/Cargo.toml --release --locked --interpreter $pythonPath --out .task-artifacts/native-wheels
# 选刚构建的 wheel，避免其他 Python 版本的旧 wheel 一起进入安装命令。
$wheel = Get-ChildItem .task-artifacts/native-wheels/*.whl | Sort-Object LastWriteTime -Descending | Select-Object -First 1
uv pip install --python $pythonPath $wheel.FullName
```

此后用 `uv run --locked --no-sync ...` 保留另行安装的扩展。
重新 `uv sync` 后需要再次安装 wheel。强制 native 测试、Rust lint 与构建检查见 [验证说明](VALIDATION.md)。

### 显式可行构造与批查询

以下沿用 README 的 `window`：

```python
from homology_operator.native import NativeFeasibleSolver, apply_batch, geometry_batch
from homology_operator import HomologyOperator, ProjectionProblem, solve_projection

solution = solve_projection(ProjectionProblem(window), NativeFeasibleSolver())
if solution.projection is None:
    raise RuntimeError((solution.status, solution.diagnostics))
op = HomologyOperator(window, solution)
actions = apply_batch(op, ((1, 0), (0, 1)))
geometry = geometry_batch(op, ((1, 0), (0, 1)), pairs=((0, 1),))
assert actions.state == geometry.state == "Computed"
assert geometry.value["class_distance"] == (0,)
```

`NativeFeasibleSolver` 只构造 StableBasisOrder/Feasible，支持多字链空间，受逻辑条目预算约束。
G/U/P 与 reference 完整相同，仍经独立 Python validator；不提供 native 优化认证。
states 使用 feasible checkpoint 单位，成功为 `5+m+n`。
`apply_batch` 返回 project/apply_operator/support；`geometry_batch` 先校验循环与 pair 索引，再复用 Pz。
两者返回绑定六身份的 QueryResult，默认不增加算子的查询历史。
显式后端的质量、距离及支撑交并使用 Python 精确整数/Fraction 或浮点 fsum，后备成本保存在 details。

### 多字 packed 代数与复用

```python
from homology_operator import Matrix
from homology_operator.native import PreparedMatrix, packed_add, packed_multiply

matrix = Matrix.from_rows(((1, 1, 0), (0, 1, 1)))
prepared = PreparedMatrix(matrix)
rhs = ((1, 0), (0, 1))
assert prepared.solve_many(rhs) == tuple(matrix.solve(b) for b in rhs)
assert prepared.membership_many(rhs) == (True, True)
assert prepared.statistics()["decomposition_count"] == 1
assert packed_add(matrix, matrix) == Matrix.zero(2, 3)
assert packed_multiply(matrix, Matrix.identity(3)) == matrix
```

`PreparedMatrix(matrix)` 持有一次稳定 RREF；提供 `rank`、`rref`、`kernel_basis`、`image_basis`、
`apply_many(vectors)`、`solve(b)`、`solve_many(rhs)`、`membership_many(rhs)` 和 `statistics()`。
支持多字矩形及空形状、原列坐标、确定性 canonical 解；与权重、投影选择无关。
statistics 是分解/非零位/存储 word 的诊断，不是峰值 RSS。

`PreparedMatrix(matrix, full=False, diagnostics=False)` 不保存平方规模行变换，
支持 rank/RREF/kernel/image/apply；solve、membership 和 inverse_rows 明确抛 ValueError。
默认 full=True 保留完整求解能力，diagnostics=True 保留兼容的填充统计。
关闭诊断时 peak_nonzero_bits 为 None；solver 内部关闭诊断并在请求内使用有界缓存。
HC 在 Rust 中从已准备 A/D 直接构造 H/C，不物化 P、不逐列调用 Python。
apply_batch 和未显式传 workspace 的 geometry_batch 懒准备并复用算子自己的原生作用与 scratch；
原始链查询仍接受非循环，几何查询仍只接受循环。句柄不进入快照，恢复继续独立重验。
适配器要求 binding API 3、F2 semantics 1；更新源码后须重建匹配扩展。
reference 保持纯 Python；显式 native 可行构造和批查询也支持多字维数。

缺扩展时，native solver/批查询返回 Unavailable；直接创建 PreparedMatrix 或调用 packed 工具抛 ImportError。
直接 packed 工具没有后备；solver 仅支持前述显式同 solver 后备。无效矩阵、RHS 或坐标明确拒绝。

### 因子化 action

[PR #80](https://github.com/proffitteoy/homology-operator/pull/80) 已合入 main，提供 `CompactAction` 和 `NativeFactorizedSolver`。
使用时构建匹配当前源码的扩展；旧版本 wheel 不能替代。调用形态为：

```python
from homology_operator.native import NativeFactorizedSolver
from homology_operator import HomologyOperator, ProjectionProblem, solve_projection

problem = ProjectionProblem(
    window, matrix_free_output=True, solver_options={"representation": "Factorized"},
)
solution = solve_projection(problem, NativeFactorizedSolver())
if solution.projection is None:
    raise RuntimeError((solution.status, solution.diagnostics))
op = HomologyOperator(window, solution)
assert op.same_class((1, 0), (0, 1))
```

`representation` 支持 Factorized / HC；Factorized 对应内部 GeneralizedInverse 因子表示，HC 表示 P=HC。
均保持参考构造在所有链上的同一个 P，包括非循环延拓；不构造完整 P/L。
Factorized 保存 A/D、完整增广消元所得逆的非零行与原 pivot 索引；
HC 流式读取同 P 的生成元构造规范像基 H，再逐列求 C。β 接近 n 时 HC 的真实输出仍可能平方大，
初始行变换消元也有平方 workspace，不声明所有中间量都线性。
返回 Feasible 与 NotComputed objective，不提供最优证书。
身份绑定具体表示；跨表示查询不能凭 action 等价直接混用。紧凑 handle 恢复规则见结果模型。
常规 A/D、因子、核基输出和 transport 仍可为显式矩阵，资源检查仍非硬 RSS 限制。


### 限定 native 认证求解

沿用本节的可选 release wheel 构建与安装命令。四个限定 solver 保留原支持域，
显式选择 native 实现，默认 reference 入口不变：

```python
from homology_operator import ProjectionProblem, solve_projection

problem = ProjectionProblem(window, requested_certificate_level="ExactOptimal")
solution = solve_projection(problem, "NativeExhaustiveExactSolver")
# 另有 NativeGreedyCertifiedSolver、NativeRank2ExactSolver、NativeStructuredFamilySolver。
# Greedy 不接受一般 ExactOptimal 请求；Rank2/Structured 仍要求各自已验证的结构。
```

也可用既有 solver 类的 `native=True` 参数。原生 packed 循环枚举、精确质量比值、
共享分解、多 RHS 与独立证书重放保持完整 action、并列和预算 state 语义。
归一化权重超出 u128 时显式保留任意精度后备；缺少扩展返回 Unavailable。
可行种子、候选外循环和部分代数仍在 Python，最终投影仍为原显式 Matrix 或
既有 CyclicAction。支持域、身份与恢复路径见 [solver 契约](SOLVER_CONTRACT.md)。



### 几何批查询与 workspace

`geometry_batch` 只接受循环，支持多字显式 Matrix 和 Factorized/HC；每批每条循环只投影一次，
由同一 packed Pz 的 XOR/AND/OR 计算距离与支撑交并，索引保持原基顺序。
沿用上方的 `op`，安装匹配当前源码的扩展后：

```python
from homology_operator.native import GeometryWorkspace, geometry_batch

cycles = ((1, 0), (0, 1))
workspace = GeometryWorkspace(op)
first = geometry_batch(op, cycles, pairs=((0, 1),), workspace=workspace)
second = geometry_batch(op, cycles, pairs=((0, 1),), workspace=workspace)
assert first.state == "Computed"
assert first.value == second.value
assert first.value["class_distance"] == (op.class_distance(*cycles),)
```

workspace 持有同一 action/边界/权重及私有缓冲，核对全部六身份，包括 solver_run_id；
准备和查询不改变算子或既有快照历史。省略 workspace 时每次建立临时准备对象；
输出记录独立不可变，准备对象不序列化。缓冲保留最大已用容量，不提供并发共享保证或 RSS 硬上限。
CyclicAction 的原生几何和缺少扩展返回 Unavailable，标量读取与过滤 tracking 仍可使用。

正整数及分母为1的 Fraction 使用检查溢出的 u64 求和；单项超界、求和溢出或非整数有理数
显式使用 Python 任意精度后备，浮点保持原坐标顺序的 binary64 fsum。浮点溢出抛出带
NumericalFailure 的 ValueError。exact 只描述几何算术，不升级 solver 认证。

QueryResult.details 分开记录准备/输入转换/原生/绑定/decode/权重后备成本、次数与原因；
准备子项不与准备总量重复相加，结果冻结计入调用者完整计时。statistics() 的 completed_batches
是原生步骤完成数，Python 浮点后备失败后也可能增加；projection_buffer_growths 用于检查复用。

## 后端可用性与协作取消

`homology_operator.native.backend_info()` 报告实际 extension 路径、平台、语义版本和可用性；
缺少或不兼容扩展为 Unavailable。native ABI 语义版本为1，旧 wheel 需要重建；reference 导入不依赖 Rust。
支持平台仍以本页 CI 矩阵为准，本地 Windows CPython 3.12 是额外验证，不扩大正式矩阵。

```python
from homology_operator import CancellationToken, ProjectionProblem, solve_projection

token = CancellationToken()
problem = ProjectionProblem(window, cancellation=token)
# 另一线程可以调用 token.cancel()；token 是一次性运行状态，不进入配置 hash 或快照。
solution = solve_projection(problem, "NativeFeasibleSolver", fallback=True)
```

取消在 solver checkpoint、native 可行构造、packed 分解和 span 枚举中检查；原生长循环释放 GIL。
solver 以 ResourceExhausted 和 diagnostics 中的 cancelled 报告，合法中断候选仍必须经过独立验证。
`geometry_batch(op, cycles, pairs=(), workspace=None, limits=None, cancellation=None)` 支持同一 token，
显式 limits 使用 ResourceLimits；state 单位为完成的循环投影数加 pair 数。
失败返回 ResourceExhausted、value=None、details.reason 与实际 resource_usage；空批且 state_limit=0 可合法 Computed。
默认 limits=None 保留原无预算批查询行为；取消/时间在原生循环及 Python 输出解码后检查，逻辑条目先检查。
`PreparedMatrix(matrix, cancellation=token)` 只在准备阶段检查 token；取消抛内部预算异常，不返回可用的半成品。

`apply_batch`、PreparedMatrix 的后续代数操作、过滤查询及独立 validator/证书重放未提供取消参数。
单步 Python 代数、输入验证、转换、workspace 准备、输出冻结也没有硬抢占保证；
geometry 的显式 wall 上限包含本次准备/转换的经过时间，但只能在检查点返回。
没有 RSS/OOM 硬控制，库内 cancelled/state_limit/wall_time_limit/matrix_entry_limit 与进程 timeout/OOM 分开。
必需独立验证、绑定、序列化和恢复重验/重放仍计入完整调用成本，不能因取消而省略。
solver.resource_usage.wall_time 是该 solver 的预算经过时间；后备失败尝试与调度/算子构造/恢复
需由调用者测量完整墙钟，不能把选中 solver 的 wall_time 当作全部入口成本。

`Matrix.from_sparse_columns(columns, nrows)` 按每列的非零行索引构造，保留空列；
索引必须为范围内不重复的整数，拒绝重复、bool 和越界值，不需要稠密坐标 tuple。
显式 native 计算在乘法、分解、HC、传输与批查询间保留不可变矩阵句柄；
坐标导出、内容身份、独立验证和 JSON 才懒解码 reference packed 视图。
reference 构造不会加载扩展，快照恢复仍无需 Rust。

原生矩阵每行至少八个 word 且非零索引数不超过稠密 word 总数的一半时，
使用有序稀疏列索引；消元实际填充超过该阈值后单向转为连续 packed 行。
较小或稠密矩阵直接使用 packed。statistics 新增 sparse_input、sparse_reduced
和 sparse_to_dense_switches；stored_words 计算 u64 或 usize 槽位，不含行头与容量，
不是 RSS。该阈值是存储策略，不是所有稀疏输入都会加速的承诺。

## Stable volume

`OperatorFamily.stable_volume(reference, epsilon, filling_window, *, epsilon_unit,
limits=None, cancellation=None)` 提供有限 H1/H2 配对的 Definition 6 精确查询。
epsilon 必须为正整数/有理数，单位声明对应过滤尺度，与上维代价单位分别记录。
两维均使用非严格阈值，没有出生系数非零约束；结果边界可能离开出生阶段。
最优证书与限定凸扇扰动保证分别记录，一般 H2 与跨数据重采样不继承该保证。
支持域、前提、失败状态及恢复校验见 [英文契约](en/INTERFACE.md#stable-volume)。
