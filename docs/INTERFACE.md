# Python API

本文描述实际 Python 入口及其输入域。安装和最小窗口见 [根 README](../README.md)，
数学职责见 [架构](ARCHITECTURE.md)，状态/schema 见 [结果模型](RESULT_MODEL.md)。
已合并与开发中功能的边界见 [文档索引](README.md)。

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
ResourceLimits(state_limit=100000, wall_time_limit=10.0, matrix_entry_limit=1000000)
ProjectionProblem(window, resource_limits=ResourceLimits(),
                  objective="MinimumStretch", requested_certificate_level="Feasible",
                  tie_break_policy="StableBasisOrder", arithmetic_policy=None,
                  input_structure="GeneralChainWindow", matrix_free_output=False,
                  deterministic=True, solver_options={})
solve_projection(problem, backend="FeasibleSolver") → ProjectionSolution
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
S4-05 四个限定 solver 另有 `NativeExhaustiveExactSolver`、`NativeGreedyCertifiedSolver`、
`NativeRank2ExactSolver`、`NativeStructuredFamilySolver` 字符串入口，或使用现有类的 `native=True`。
`NativeFeasibleSolver` 与 `NativeFactorizedSolver` 仍采用对象调用。
未知后端或不支持的请求返回 Unavailable，不静默选择其他 solver。

统一调度核对 capability、配置、并列策略、算术和报告预算，再独立验证返回投影与证书。
算子构造再次检查 `P²=P`、`AP=0`、`PD=0` 和循环同调保持；失败抛 `ValidationError`。
检查 `solution.projection` 是否存在后再构造算子。
ResourceExhausted 也可能保留合法候选；这时算子可为 Ready，但最优认证不能由停止状态推断。
solver 各自的结构、枚举/重放上限、并列与中断语义见 [solver 契约](SOLVER_CONTRACT.md)。

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
| `minimum_class_mass(z)` | 循环 | 当前为 Unavailable 的 QueryResult |
| `certificate()`、`metadata()` | 无 | 独立验证记录 / 身份与 provenance、权重元数据 |
| `to_result()` | 无 | OperatorResult 快照 |

标量方法返回直接值；`readout` 返回带状态/身份的记录。`readout` 支持从 project 到 union_support 的逻辑查询，
stretch 和最短质量采用自己的 QueryResult 入口。类查询遇到非循环抛 ValueError。
当前没有 `retraction_mode`；不能把原始 `project` 的非循环结果当作同调类。

`selected_mass` 是选定代表质量，不能填充真实最短类质量。
共享支撑满足精确权下的恒等式
`m_w(Pz)+m_w(Py)=m_w(P(z+y))+2m_w(supp(Pz)∩supp(Py))`。
完整核向量表或类表可能有指数规模，API 不免费枚举全表。

stretch 定义为非零循环上 `m_w(Pz)/m_w(z)` 的最大值。
空循环域返回 `EmptyDomain` 与约定值 0；非空循环域但 Betti=0 时返回 Computed 的合法 0。
该约定来自 [固定理论正文 §1.2](https://github.com/proffitteoy/homology-operator-lab/blob/6143729669902ee875b211b58085e954c76cdf88/docs/proof/PROOF.md)，
资源耗尽或未计算不能用这个 0 替代。

## 过滤与传输

S4-07 实现、birth 前缀证明与成本见 [过滤读取](S4_FILTRATION.md)。普通 `barcode()`
只消费相邻核坐标映射；历史区间基与全部区间 rank 按真实输出大小另行请求。
`cache_limit=64` 分别限制 action/transport/rank 的 LRU 条目，0禁用；内部按索引嵌入，
不物化公共 inclusion。核坐标分解随不同投影保留，缓存条目上限不是字节/RSS硬限制。

```text
OperatorFamily(scales, windows, operators, weight_policy="Inherited",
               duplicate_policy="OrderedStages", terminal_extension="Constant",
               cache_limit=64)
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

### 可行原型与批查询（已合并）

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

`NativeFeasibleSolver` 只构造 StableBasisOrder/Feasible，三个链空间均至多 64 维。
G/U/P 与 reference 完整相同，仍经独立 Python validator；不提供 native 优化认证。
states 沿用原型的 feasible checkpoint 单位，成功为 `5+m+n`。
`apply_batch` 返回 project/apply_operator/support；`geometry_batch` 先校验循环与 pair 索引，再复用 Pz。
两者返回绑定六身份的 QueryResult，默认不增加算子的查询历史。
已合并原型的质量、距离及支撑交并使用 Python 精确整数/Fraction 或浮点 fsum，后备成本保存在 details。

### 多字 packed 代数与复用（已合并）

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
这组多字工具不解除上节单字宽可行原型的限制，也未自动替换全部 reference 路径。

缺扩展时，native solver/批查询返回 Unavailable；直接创建 PreparedMatrix 或调用 packed 工具抛 ImportError。
没有隐式 reference fallback。无效矩阵、RHS 或坐标明确拒绝。

### 因子化 action（S4-04）

[PR #80](https://github.com/proffitteoy/homology-operator/pull/80) 已合入 main，提供 `CompactAction` 和 `NativeFactorizedSolver`。
使用时构建匹配当前源码的扩展；旧原型 wheel 不能替代。调用形态为：

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
正式性能与集成验收属于 [S4/S5 工作包](S4_S5_PROJECT.md)。


### 限定 native 认证求解（S4-05）

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

[S4-05 有限同 solver 协议](BENCHMARKS.md) 分别记录构造、独立重放和完整读取/恢复成本；
它不替代 S4-04 因子表示、S4-08 全后端集成或 S5 正式验收。
