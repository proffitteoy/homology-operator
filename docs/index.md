# homology-operator

```{toctree}
:hidden:
:caption: 数学

算子定义与性质 <MATHEMATICS>
```

```{toctree}
:hidden:
:caption: 快速开始

getting-started/installation
getting-started/quickstart
```

```{toctree}
:hidden:
:caption: 使用指南

guide/input-semantics
guide/single-scale
guide/filtration
guide/native
```

```{toctree}
:hidden:
:caption: 参考

INTERFACE
RESULT_MODEL
ARCHITECTURE
SOLVER_CONTRACT
platforms
```

```{toctree}
:hidden:
:caption: 项目

VALIDATION
贡献 <https://github.com/proffitteoy/homology-operator/blob/main/CONTRIBUTING.zh-CN.md>
产品说明 <https://github.com/proffitteoy/homology-operator/blob/main/docs/README.md>
源代码 <https://github.com/proffitteoy/homology-operator>
```

[![Reference checks](https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml/badge.svg)](https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml)
[![Native checks](https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml/badge.svg)](https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml)
[![GUDHI oracle](https://github.com/proffitteoy/homology-operator/actions/workflows/oracle.yml/badge.svg)](https://github.com/proffitteoy/homology-operator/actions/workflows/oracle.yml)

[English](en/index.md)

## 从边界构造、以核实现同调的二元算子

本项目提出一种定义在原链空间上的二元同调算子。
给定有限带基链窗口及正坐标权重，构造线性投影 $`P`$ 与算子 $`L=I+P`$：

```math
C_{k+1}\xrightarrow{D}C_k\xrightarrow{A}C_{k-1},\quad AD=0,
\qquad P=(I+DU)(I+GA),\quad L=I+P.
```

广义逆满足 $`AGA=A`$、$`DUD=D`$。算子的核心关系是

```math
\boxed{\ker L=\mathrm{im}\,P\cong H_k(C;\mathbf F_2).}
```

核中的向量是每个同调类唯一的选定循环代表。对循环 $`z`$，$`Pz`$ 保持原类，
并满足 $`P(z+y)=Pz+Py`$；因此代表选择是一条同时约束全部类的线性规则。
同一个 $`P`$ 的带权作用给出质量、距离和共享支撑；
过滤中核之间的投影传输给出完整持久同调模及其 barcode。

从[算子理论](MATHEMATICS.md)开始阅读定义、构造和证明，
或直接运行[六边完整算例](guide/single-scale.md#六边复形的精确算子)。

## 一个算子，三种读取

| 读取层次 | 数学对象 | 能回答的问题 |
| --- | --- | --- |
| 同调 | $`\ker L`$、$`Pz`$ | 有多少独立类？这个循环属于哪个类？选定代表在哪里？ |
| 加权几何 | $`m_w(Pz)`$、$`m_w(P(z+y))`$、支撑交/并 | 实现这个类要多少代价？类之差如何实现？哪些坐标共享并抵消？ |
| 持久性 | $`T_{ij}=P_jJ_{ij}\vert_{\ker L_i}`$ | 类如何跨尺度传输、合并或死亡？相应区间是什么？ |

类距离为零恰好表示同类；非零值记录差类的选定实现成本。
几何单位来自输入权重。$`L`$ 的特征值只有 $`0,1`$，新增几何信息由带权作用读取。

## 最小伸长：同时控制全部线性组合

可行投影通常不唯一。以最坏循环质量比选择投影，得到最小伸长目标

```math
\Gamma_w(P)=\max_{0\ne z,\ Az=0}\frac{m_w(Pz)}{m_w(z)},\qquad
\Gamma_*=\min_{P\ \mathrm{legal}}\Gamma_w(P).
```

它与最小伸长线性截面问题等价：每个类输出一个代表，同时保持所有组合的线性关系。
当 Betti 数 $`\beta>0`$ 时，$`1\le\Gamma_*\le\beta`$。

六边复形的三个非零类最短质量为 $`(8,8,9)`$。
最小总质量基产生输出 $`(8,8,12)`$，伸长 $`4/3`$；最小伸长算子产生 $`(8,9,9)`$，伸长 $`9/8`$。
共享支撑的抵消解释了这个选择。完整四截面枚举、矩阵与证明见[数学算例](MATHEMATICS.md#6-六边复形完整算例)。

## 运行这个算子

```python
from fractions import Fraction
from homology_operator import (
    ChainWindow, HomologyOperator, Matrix, ProjectionProblem, solve_projection,
)

window = ChainWindow(
    k=1,
    A=Matrix.from_rows((
        (1, 1, 1, 0, 0, 0),
        (1, 0, 0, 1, 1, 0),
        (0, 1, 0, 1, 0, 1),
        (0, 0, 1, 0, 1, 1),
    )),
    D=Matrix.from_rows(((1,), (1,), (0,), (1,), (0,), (0,))),
    basis_previous=("v0", "v1", "v2", "v3"),
    basis_current=("01", "02", "03", "12", "13", "23"),
    basis_next=("012",),
    weights=(2, 4, 2, 3, 4, 2),
)
solution = solve_projection(
    ProjectionProblem(window, requested_certificate_level="ExactOptimal"),
    "ExhaustiveExactSolver",
)
if solution.projection is None:
    raise RuntimeError((solution.status, solution.diagnostics))
op = HomologyOperator(window, solution)

z = (1, 0, 1, 0, 1, 0)
y = (0, 1, 1, 0, 0, 1)
assert solution.certificate_level == "ExactOptimal"
assert solution.objective.value == Fraction(9, 8)
assert op.betti() == 2
assert op.selected_mass(z) == 8
assert op.selected_mass(y) == 9
assert op.class_distance(z, y) == 9
assert op.shared_support(z, y) == (0, 2)
assert op.stretch().value == Fraction(9, 8)

```

代码中的投影经独立合法性与最优证书验证。默认 `FeasibleSolver` 则构造合法算子，
保持同一读取语义；solver 支持域、搜索代价和认证见[契约](SOLVER_CONTRACT.md)。
`selected_mass` 表示选定代表质量，真正最短类质量查询当前不可用。

## 安装与计算后端

Python 3.10+；reference 运行时仅依赖标准库。Python 包版本为 `0.0.2`；PyPI 上传状态和安装命令见[安装](getting-started/installation.md)。

```console
git clone https://github.com/proffitteoy/homology-operator.git
cd homology-operator
python -m pip install .
```

可选 Rust 后端提供 packed 代数、复用分解、Factorized/HC action、限定 solver 与批查询。
两种后端实现同一算子契约。输入由调用者提供带基边界窗口；
一般点云、Rips 和复形构造前端须另外提供。
详细说明见[安装](getting-started/installation.md)和[native 指南](guide/native.md)。

## 按问题继续阅读

- [算子理论](MATHEMATICS.md)：定义、核定理、投影族、伸长界、几何与持久传输证明。
- [输入语义](guide/input-semantics.md)与[快速上手](getting-started/quickstart.md)：把实际边界数据变成算子。
- [单尺度与几何](guide/single-scale.md)、[有限过滤](guide/filtration.md)：读取代表、距离和追踪。
- [API](INTERFACE.md)、[solver 契约](SOLVER_CONTRACT.md)、[结果模型](RESULT_MODEL.md)：支持域、认证、身份与恢复。
- [架构](ARCHITECTURE.md)与[开发验证](VALIDATION.md)：模块、测试和文档构建。

项目采用 [MIT License](../LICENSE)。研究引用请记录实际版本与提交，见 [CITATION.cff](../CITATION.cff)。
