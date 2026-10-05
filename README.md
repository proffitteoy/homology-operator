<h1 align="center">homology-operator</h1>

<p align="center">从边界构造二元同调算子：核、线性代表、加权几何与持久传输。</p>

<p align="center">
  <a href="https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml"><img src="https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml/badge.svg" alt="Reference checks"></a>
  <a href="https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml"><img src="https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml/badge.svg" alt="Native checks"></a>
  <a href="https://github.com/proffitteoy/homology-operator/actions/workflows/oracle.yml"><img src="https://github.com/proffitteoy/homology-operator/actions/workflows/oracle.yml/badge.svg" alt="GUDHI oracle"></a>
</p>

<p align="center">
  <a href="README.en.md">English</a> ·
  <a href="https://proffitteoy.github.io/homology-operator/">Documentation</a> ·
  <a href="docs/INTERFACE.md">API</a> ·
  <a href="docs/MATHEMATICS.md">Mathematics</a> ·
  <a href="CONTRIBUTING.md">Contributing</a> ·
  <a href="LICENSE">MIT License</a>
</p>

本项目提出一种定义在原链空间上的**二元同调算子**，并提供它的 Python/Rust 实现。
算子的核实现同调，配套投影为全部类选择线性一致的循环代表。
同一个带权作用给出代表质量、类距离和支撑；核之间的传输实现有限过滤的持久同调模。
定义、构造与证明集中在[数学文档](docs/MATHEMATICS.md)，本页的[数学章节](#数学)概述核心关系。

提供 Python 公共接口和可选 Rust 计算后端，Python 包版本为 `0.0.2`，属于早期发行。
采用 [MIT License](LICENSE)。PyPI 上传状态以[版本记录](https://pypi.org/project/homology-operator/0.0.2/)为准。完整产品说明见 [在线文档](https://proffitteoy.github.io/homology-operator/)。

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

Python 3.10+；reference 运行时仅依赖标准库。从 PyPI 安装：

```console
python -m pip install homology-operator==0.0.2
```

也可从源码安装：

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
[过滤说明](docs/guide/filtration.md)和 [API](docs/INTERFACE.md#过滤与传输)。

## 数学

### 定义与构造

输入固定次数的有限带基链窗口与正坐标权重：

```math
C_{k+1}\xrightarrow{D}C_k\xrightarrow{A}C_{k-1},\qquad AD=0.
```

选择 $`AGA=A`$、$`DUD=D`$ 的代数广义逆，构造

```math
P=(I+DU)(I+GA),\qquad L=I+P,\qquad
\boxed{\ker L=\mathrm{im}\,P\cong H_k(C;\mathbf F_2).}
```

核中的向量是每个同调类唯一的选定循环代表。$`P`$ 保持循环的原同调类，
并使全部代表遵守线性关系：$`P(z+y)=Pz+Py`$。
同一个带权作用同时给出拓扑、代表质量、类距离、共享支撑和最坏伸长；
有限过滤中核之间的投影传输实现整个持久同调模，并由传输读取 barcode。
完整定义与证明见[算子理论](docs/MATHEMATICS.md)。

### 最小伸长

合法投影通常不唯一。最小伸长目标同时控制所有循环，而非只控制某组基代表：

```math
\Gamma_w(P)=\max_{0\ne z,\ Az=0}\frac{m_w(Pz)}{m_w(z)},\qquad
\Gamma_*=\min_{P\ \mathrm{legal}}\Gamma_w(P),\qquad
m_w(x)=\sum_{i:x_i=1}w_i.
```

它与同调商的最小伸长线性截面问题等价；非零 Betti 数为 $`\beta`$ 时，$`1\le\Gamma_*\le\beta`$。
四顶点六边复形上，最小总质量基给出质量 $`(8,8,12)`$、伸长 $`4/3`$；
最小伸长算子给出 $`(8,9,9)`$、伸长 $`9/8`$。这个选择通过共享支撑的抵消控制组合类。
[完整算例](docs/MATHEMATICS.md#6-六边复形完整算例)列出全部四个截面、矩阵及证明；
[可运行代码](docs/guide/single-scale.md#六边复形的精确算子)从同一个算子读取这些结果。

默认 solver 构造合法算子；支持域内的精确 solver 与独立证书才认证最优。
$`L`$ 的特征值只有 $`0,1`$，几何信息由带权作用读取。

## 文档

- [算子理论](docs/MATHEMATICS.md)：正式定义、构造、核定理、投影空间、最小伸长、几何与持久传输证明。
- [安装](docs/getting-started/installation.md)与[五分钟快速上手](docs/getting-started/quickstart.md)。
- [输入语义](docs/guide/input-semantics.md)、[单尺度与几何](docs/guide/single-scale.md)、[有限过滤](docs/guide/filtration.md)。
- [Python API 与 native 安装](docs/INTERFACE.md)：输入、查询、solver、过滤和批量代数。
- [结果与序列化](docs/RESULT_MODEL.md)：身份、状态、精确性、快照与缓存。
- [架构](docs/ARCHITECTURE.md) / [solver 契约](docs/SOLVER_CONTRACT.md)：数学定义和计算边界。
- [开发与验证](docs/VALIDATION.md)：测试、Ruff、构建、文档检查和 CI。
- [完整文档索引](docs/README.md)：产品 API、后端、测试与使用文档。

贡献代码前阅读 [项目约定](AGENTS.md)，按 [验证说明](docs/VALIDATION.md) 运行与改动相关的检查。

## 开发

问题与改进建议见 [GitHub Issues](https://github.com/proffitteoy/homology-operator/issues)，
提交要求见 [贡献指南](CONTRIBUTING.md)。文档站由 main 自动发布到 GitHub Pages，本地构建命令见
[文档构建](docs/VALIDATION.md#文档站构建)。公开 API 与 native ABI 尚未冻结兼容政策。

## 引用

研究工作中使用本包时，请引用实际软件版本与提交；机器可读信息见 [CITATION.cff](CITATION.cff)。
理论定义固定在 [homology-operator-lab 的研究提交](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88)；
研究实现与成绩不是本包的运行时依赖或验收证据。来源与依赖说明见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)。

## 许可证与发行状态

采用 [MIT License](LICENSE)。Python 包提供通用 wheel 与源码包，发布流程见
[发行说明](docs/VALIDATION.md#公开发行)。0.x 是早期 API：补丁版本保持公共接口，
不兼容变更提升次版本并在发行记录说明。结果恢复继续覆盖已有 schema 1/2；
native ABI 独立按语义版本校验，扩展暂从匹配源码构建。
