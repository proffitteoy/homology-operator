# 五分钟快速上手

[English](../en/getting-started/quickstart.md)

本页从一个两顶点窗口开始，依次读取单尺度结果与有限过滤。

## 单尺度

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

选定代表的质量为 10，另一个同类代表的质量为 1；`selected_mass` 不是最短类质量。

## 有限过滤

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

死亡类返回合法零质量。继续阅读[单尺度查询](../guide/single-scale.md)与[有限过滤](../guide/filtration.md)。
