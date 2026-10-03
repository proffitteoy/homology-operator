# homology-operator

Boundary-native F2 homology operators with persistence and geometric readouts.

`homology-operator` 是一个从边界矩阵构造同调算子的 Python 库。输入固定次数的带基链窗口
`C_{k+1} --D--> C_k --A--> C_{k-1}` 和正坐标权重，构造投影 `P` 与 `L=I+P`，
从同一个投影读取 Betti 数、类代表、质量、距离、支撑和 stretch。
有限过滤的 barcode 与类追踪由 `OperatorFamily` 的跨阶段传输读取。

目前提供 Python correctness reference 和可选 Rust 扩展，版本为开发快照 `0.0.2.dev0`。
尚未发行，许可证待选。已合并能力、开发中功能和 CI 证据见 [文档索引](docs/README.md)。

## 安装

Python 3.10+；reference 运行时仅依赖标准库。从源码使用 [uv](https://docs.astral.sh/uv/) 安装：

```powershell
git clone https://github.com/proffitteoy/homology-operator.git
cd homology-operator
uv sync --locked --python 3.10
uv run --locked python examples/single_scale.py
```

已有 Python 环境也可在仓库根目录执行 `python -m pip install .` 安装 reference。
Rust 扩展单独构建，不是 reference 的安装前提；工具链、平台和构建命令见
[可选 Rust 扩展](docs/INTERFACE.md#可选-rust-扩展)。

## 一个最小例子

两个顶点由一条边连接，`D=(1,1)^T`，因此两个顶点表示同一个 H0 类：

```python
from homology_operator import (
    ChainWindow, HomologyOperator, Matrix, ProjectionProblem, solve_projection,
)

window = ChainWindow(
    k=0,
    A=Matrix.zero(0, 2),
    D=Matrix.from_rows(((1,), (1,))),
    basis_previous=(),
    basis_current=("v0", "v1"),
    basis_next=("edge",),
    weights=(10, 1),
)
solution = solve_projection(ProjectionProblem(window))
if solution.projection is None:
    raise RuntimeError((solution.status, solution.diagnostics))
op = HomologyOperator(window, solution)

assert op.betti() == 1
assert op.same_class((1, 0), (0, 1))
assert op.class_distance((1, 0), (0, 1)) == 0
assert op.class_representative((0, 1)) == (1, 0)
assert op.selected_mass((0, 1)) == 10

query = op.readout("selected_mass", (0, 1))
assert query.state == "Computed" and query.exact
record = op.to_result()  # 包含已查询的结果、六身份、solver 和独立验证信息
```

`selected_mass` 是当前投影选定代表的质量。上例另有质量 1 的同类代表，
所以选定质量 10 不能被解释成最短类质量。`FeasibleSolver` 构造合法投影，
不认证最小 stretch；限定优化 solver 的适用域见 [solver 契约](docs/SOLVER_CONTRACT.md)。

`project` 和 `apply_operator` 接受所有链；`same_class`、代表、质量、距离及支撑查询要求输入是循环。
矩阵和向量坐标必须是整数 0/1；非法输入明确拒绝。返回类型、失败处理和序列化见
[Python API](docs/INTERFACE.md) 与 [结果模型](docs/RESULT_MODEL.md)。

## 有限过滤

给每个阶段提供同次数窗口和对应算子；包含关系由三个次数的带序基标识确定：

```python
from dataclasses import replace
from homology_operator import OperatorFamily

before = replace(window, D=Matrix.zero(2, 0), basis_next=())
windows = (before, window)
operators = tuple(
    HomologyOperator(w, solve_projection(ProjectionProblem(w))) for w in windows
)
family = OperatorFamily((0, 1), windows, operators)

assert family.transport_rank(0, 1).value == 1
barcode = family.barcode()  # QueryResult；阶段半开区间，末端存活以 None 表示
assert barcode.state == "Computed"
assert family.track_mass((1, 1), 0, 1).value == 0  # 这一个类在阶段 1 死亡
```

barcode 来自 `T_ij=P_j J_ij|ker(L_i)` 的 rank invariant。
重复尺度、变权、失败阶段和末端延拓见 [过滤 API](docs/INTERFACE.md#过滤与传输)。
完整输出示例：

```powershell
uv run --locked python examples/filtration.py
```

S4-07 的 `OperatorFamily.barcode()` 只读取相邻 transport，内部使用索引嵌入和可复用
packed 核坐标分解。`barcode_basis()` 返回经过死亡回改的历史区间基；`rank_table()`
显式请求二次大小的完整 rank 表。`cache_limit=64` 限制各查询缓存条目，0禁用。
默认过滤快照采用共享边界/基/活动索引的 schema 2，旧 schema 1 可读并原版本重发；
`to_result(schema_version=1)` 显式输出旧格式，单尺度快照版本保持原契约。
证明、状态边界及复跑命令见 [S4-07说明](docs/S4_FILTRATION.md)。

四种限定 solver 可显式选择 native 加速与独立证书重放；默认 reference 入口保持不变。
调用及支持域见 [native 认证求解](docs/INTERFACE.md#限定-native-认证求解s4-05)。

几何批查询可显式复用 `GeometryWorkspace`，支持 Matrix 与 Factorized/HC 的同一 P，
保留精确权重后备和六身份；调用与限制见 [几何 workspace](docs/INTERFACE.md#几何批查询与-workspaces4-06)。

## 能力与边界

| 能力 | 当前范围 |
| --- | --- |
| F2 代数与输入 | 显式形状、稳定消元、空链空间、`AD=0` 校验、原坐标保留 |
| 单尺度与有限过滤 | 同 P 联合查询、transport、rank/barcode、几何追踪、结果快照 |
| 求解与认证 | 五种限定 reference solver；投影合法性、objective 计算、最优认证分别报告 |
| 权重 | 任意精度整数/有理数；显式浮点政策，浮点几何不提供精确最优证书 |
| 可选 Rust | 单字宽可行原型与批查询；多字 packed 代数、可复用分解、多 RHS、同 P 的因子/HC action、限定 solver/证书重放及几何 workspace |
| 后端集成 | 显式选择与可见同 solver 后备、协作取消、旧快照与紧凑 action 恢复；支持范围见 API |
| S4 性能验收 | 冻结27个配置、1880个独立进程；共享过滤/部分规模收益，保留退化与可选后端，见 [S4报告](docs/S4_REPORT.md) |
| 开发目标 | S5/GUDHI 正式对拍、稳定性与应用实验 |

当前输入是链窗口与带序基。点云、Rips 构造器和通用复形前端仍需调用者或后续适配提供。
真实最短类质量查询尚不可用。本轮有限负载已有同输出/认证的端到端及绝对RSS收益；
4组时间退化超过20%，不作全局默认后端替换。更大规模、采样稳定性和应用收益仍需各自验收。

## 文档与开发

- [Python API 与 native 安装](docs/INTERFACE.md)：输入、查询、solver、过滤和批量代数。
- [结果与序列化](docs/RESULT_MODEL.md)：身份、状态、精确性、快照与缓存。
- [架构](docs/ARCHITECTURE.md) / [solver 契约](docs/SOLVER_CONTRACT.md)：数学定义和计算边界。
- [开发与验证](docs/VALIDATION.md)：测试、Ruff、构建、文档检查和 CI。
- [性能协议与冻结证据](docs/BENCHMARKS.md)：包含不利结果、完整成本及适用范围。
- [完整文档索引](docs/README.md)：当前状态、路线图、历史报告和研究材料。

贡献代码前阅读 [项目约定](AGENTS.md)，按 [验证说明](docs/VALIDATION.md) 运行与改动相关的检查。
理论定义固定在 [homology-operator-lab 的研究提交](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88)；
研究实现与成绩不是本包的运行时依赖或验收证据。公开发行还需确定许可证、版本兼容政策和发布流程。
