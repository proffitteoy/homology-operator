<h1 align="center">homology-operator</h1>

<p align="center">从 F2 边界矩阵读取同调、持久性与加权几何的 Python 库。</p>

<p align="center">
  <a href="https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml"><img src="https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml/badge.svg" alt="Reference checks"></a>
  <a href="https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml"><img src="https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml/badge.svg" alt="Native checks"></a>
  <a href="https://github.com/proffitteoy/homology-operator/actions/workflows/s5-oracle.yml"><img src="https://github.com/proffitteoy/homology-operator/actions/workflows/s5-oracle.yml/badge.svg" alt="GUDHI oracle"></a>
</p>

<p align="center">
  <a href="README.en.md">English</a> ·
  <a href="docs/index.md">Documentation</a> ·
  <a href="docs/INTERFACE.md">API</a> ·
  <a href="CONTRIBUTING.md">Contributing</a> ·
  <a href="LICENSE">MIT License</a>
</p>

`homology-operator` 是一个从边界矩阵构造同调算子的 Python 库。输入固定次数的带基链窗口
`C_{k+1} --D--> C_k --A--> C_{k-1}` 和正坐标权重，构造投影 `P` 与 `L=I+P`，
从同一个投影读取 Betti 数、类代表、质量、距离、支撑和 stretch。
有限过滤的 barcode 与类追踪由 `OperatorFamily` 的跨阶段传输读取。

目前提供 Python correctness reference 和可选 Rust 扩展，版本为开发快照 `0.0.2.dev0`。
采用 [MIT License](LICENSE)，尚未发行。已合并能力和 CI 证据见 [文档索引](docs/README.md)。

目前支持：

- F2 单尺度同调、类代表与同类判断；
- 同一投影下的选定质量、类距离、支撑与 stretch；
- 有限过滤的 transport、barcode 和类追踪；
- 五种限定 solver 与独立投影/最优证书验证；
- 可选 Rust packed 代数、因子化 action 与批查询；
- 保留输入、投影和求解身份的结果快照与恢复。

当前输入是链窗口与带序基。通用点云、Rips 构造器和复形前端需要调用者提供。
`selected_mass` 表示当前代表的质量；真实最短类质量查询尚不可用。

## 安装

Python 3.10+；reference 运行时仅依赖标准库。当前从源码安装：

```console
git clone https://github.com/proffitteoy/homology-operator.git
cd homology-operator
python -m pip install .
```

隔离环境、uv 与可选 Rust 构建见[安装](docs/getting-started/installation.md)。
Rust 扩展单独构建，不是 reference 的安装前提；平台范围见[平台支持](docs/platforms.md)。

## 基本用法

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

`barcode()` 使用相邻 transport。历史区间基和完整 rank 表分别由 `barcode_basis()`、
`rank_table()` 显式请求；完整输出可能有二次规模。过滤 schema 1/2、缓存与恢复见
[过滤说明](docs/S4_FILTRATION.md)和 [API](docs/INTERFACE.md#过滤与传输)。

## 性能与对照

| 冻结实验 | 范围与结论 |
| --- | --- |
| [S4](docs/S4_REPORT.md) | 27 个配置、1,880 个独立进程；部分同输出/认证路线有成本或 RSS 收益，4 组时间退化超过 20% |
| [S5](docs/S5_REPORT.md) | 77 份三方正确性输入、2,840 个正式进程；集成后端 68 个可比组没有一个 95% 配对区间完全低于 1 |

保留显式后端选择。上述数字绑定报告中的源码、输入、机器、预算与认证；完整失败和退化一并保留。
GUDHI 只对照拓扑，联合几何信息的成本单独报告。更大规模、采样稳定性和应用收益仍需各自验收。

## 文档

- [安装](docs/getting-started/installation.md)与[五分钟快速上手](docs/getting-started/quickstart.md)。
- [输入语义](docs/guide/input-semantics.md)、[单尺度与几何](docs/guide/single-scale.md)、[有限过滤](docs/guide/filtration.md)。
- [Python API 与 native 安装](docs/INTERFACE.md)：输入、查询、solver、过滤和批量代数。
- [结果与序列化](docs/RESULT_MODEL.md)：身份、状态、精确性、快照与缓存。
- [架构](docs/ARCHITECTURE.md) / [solver 契约](docs/SOLVER_CONTRACT.md)：数学定义和计算边界。
- [开发与验证](docs/VALIDATION.md)：测试、Ruff、构建、文档检查和 CI。
- [性能协议与冻结证据](docs/BENCHMARKS.md)：包含不利结果、完整成本及适用范围。
- [完整文档索引](docs/README.md)：当前状态、路线图、历史报告和研究材料。

贡献代码前阅读 [项目约定](AGENTS.md)，按 [验证说明](docs/VALIDATION.md) 运行与改动相关的检查。

## 开发

问题与改进建议见 [GitHub Issues](https://github.com/proffitteoy/homology-operator/issues)，
提交要求见 [贡献指南](CONTRIBUTING.md)。文档站可在本地构建，命令见
[文档构建](docs/VALIDATION.md#文档站构建)。公开 API 与 native ABI 尚未冻结兼容政策。

## 引用

研究工作中使用本包时，请引用实际软件版本与提交；机器可读信息见 [CITATION.cff](CITATION.cff)。
理论定义固定在 [homology-operator-lab 的研究提交](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88)；
研究实现与成绩不是本包的运行时依赖或验收证据。来源与依赖说明见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)。

## 许可证与发行状态

采用 [MIT License](LICENSE)。当前仓库已公开，尚无 PyPI 发行。
公开发行还需确定版本兼容政策和发布流程。
