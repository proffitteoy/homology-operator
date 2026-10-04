# 单尺度与加权几何

[English](../en/guide/single-scale.md)

## 构造与查询

从 `ChainWindow` 建立 `ProjectionProblem`，通过 `solve_projection` 得到解。
确认 `solution.projection` 存在，再构造 `HomologyOperator`。最小代码见[快速上手](../getting-started/quickstart.md)。

所有查询来自同一个 P；`L=I+P`，`betti()` 返回 `dim ker(L)`。

| 查询 | 定义 |
| --- | --- |
| project / apply_operator | 任意链上的 Px / Lx |
| class_representative | 循环的 Pz |
| same_class | 两循环投影是否相同 |
| selected_mass | 当前代表的加权质量 m_w(Pz) |
| class_distance | m_w(P(z+y)) |
| support / shared_support / union_support | 原基上的投影支撑及其交/并 |

类查询拒绝非循环。原始 project 的输出不会自动把非循环解释成同调类。

## 质量与认证

同类代表可以有不同质量；selected_mass 仅报告当前 P 的选择。
真实最短类质量 `minimum_class_mass` 当前为 Unavailable。
`stretch()` 计算当前 P 在非零循环上的最大质量比；合法性、当前 objective、全局最优性分开验证。
空循环域为 EmptyDomain 与约定值 0；非空循环域但 Betti=0 为 Computed 的合法 0。

## 保存结果

标量方法返回值，`readout` 返回带身份与状态的 QueryResult 并记录查询。
`to_result()` 保留已查询结果；未计算的 stretch 和最短质量不会自动求值。
返回字段与 JSON 恢复见[结果模型](../RESULT_MODEL.md)，求解范围见[solver 契约](../SOLVER_CONTRACT.md)。


## 六边复形的精确算子

四顶点完全图有三个循环方向。填充面 $012$ 后，删去一个边界方向，留下二维 $H_1$。
按边序 $(01,02,03,12,13,23)$ 使用权重 $(2,4,2,3,4,2)$。
[数学算例](../MATHEMATICS.md#6-六边复形完整算例)穷尽全部四个线性截面，证明最小伸长为 $9/8$。
下面从实际窗口求解算子，同时读取拓扑和几何。

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

assert op.class_representative(z) == (1, 0, 1, 0, 1, 0)
assert op.class_representative(y) == (1, 0, 1, 1, 0, 1)
assert op.union_support(z, y) == (0, 2, 3, 4, 5)
assert sum(window.weights[i] for i in op.shared_support(z, y)) == 4
assert sum(window.weights[i] for i in op.union_support(z, y)) == 13
assert op.P @ op.P == op.P
assert window.A @ op.P == Matrix.zero(4, 6)
assert op.P @ window.D == Matrix.zero(6, 1)

unit_window = ChainWindow(
    k=window.k, A=window.A, D=window.D,
    basis_previous=window.basis_previous,
    basis_current=window.basis_current,
    basis_next=window.basis_next, weights=(1,) * 6,
)
unit_solution = solve_projection(
    ProjectionProblem(unit_window, requested_certificate_level="ExactOptimal"),
    "ExhaustiveExactSolver",
)
unit_op = HomologyOperator(unit_window, unit_solution)
assert unit_op.betti() == op.betti()
assert unit_solution.certificate_level == "ExactOptimal"
assert unit_solution.objective.value == Fraction(4, 3)

```

这里 $z$ 是三角圈 $013$，$y$ 是三角圈 $023$，各自最短质量均为八。
当前投影给 $y$ 加上面 $012$ 的边界，选定质量为九；这一选择让组合输出的质量由十二降为九。
共享边 $01,03$ 总质量四，支撑并的总质量十三。所有输出都来自当前存储的同一个 $P$，其核实现 $H_1$。

单位权变体具有相同边界与 Betti 数，却有不同的最优伸长 $4/3$。
这些几何量描述输入坐标的代价。完整证明和四截面表见[算子理论](../MATHEMATICS.md)。
独立 solver verifier 在这个小规模支持域内认证全局最优；默认可行 solver 不给该认证。
