# homology-operator


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
贡献 <https://github.com/proffitteoy/homology-operator/blob/main/CONTRIBUTING.md>
实现与证据 <https://github.com/proffitteoy/homology-operator/blob/main/docs/README.md>
源代码 <https://github.com/proffitteoy/homology-operator>
```


[![Reference checks](https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml/badge.svg)](https://github.com/proffitteoy/homology-operator/actions/workflows/reference.yml)
[![Native checks](https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml/badge.svg)](https://github.com/proffitteoy/homology-operator/actions/workflows/native.yml)
[![GUDHI oracle](https://github.com/proffitteoy/homology-operator/actions/workflows/s5-oracle.yml/badge.svg)](https://github.com/proffitteoy/homology-operator/actions/workflows/s5-oracle.yml)


[English](en/index.md)

homology-operator 是一个从 F2 边界矩阵构造同调算子的 Python 库。
它从同一个投影读取 Betti 数、类代表、选定质量、类距离、支撑和 stretch，
并从跨阶段 transport 读取有限过滤的 barcode 与类追踪。

Python reference 仅依赖标准库，可选 Rust 扩展提供 packed 代数、限定 solver 与批查询。
当前输入为带序基链窗口；通用点云/Rips 前端需要调用者提供。

## 安装

Python 3.10+；当前为源码开发快照 `0.0.2.dev0`，尚未发布 PyPI 版本。

```console
git clone https://github.com/proffitteoy/homology-operator.git
cd homology-operator
python -m pip install .
```

详细说明见[安装](getting-started/installation.md)。

## 第一次计算

```python
from homology_operator import (
    ChainWindow, HomologyOperator, Matrix, ProjectionProblem, solve_projection,
)

window = ChainWindow(
    k=0, A=Matrix.zero(0, 2), D=Matrix.from_rows(((1,), (1,))),
    basis_previous=(), basis_current=("v0", "v1"), basis_next=("edge",),
    weights=(10, 1),
)
solution = solve_projection(ProjectionProblem(window))
if solution.projection is None:
    raise RuntimeError((solution.status, solution.diagnostics))
op = HomologyOperator(window, solution)

assert op.betti() == 1
assert op.same_class((1, 0), (0, 1))
assert op.selected_mass((0, 1)) == 10

```

这里选定质量为 10，另有质量 1 的同类代表；selected_mass 不是最短类质量。
继续阅读[五分钟快速上手](getting-started/quickstart.md)，或从左侧导航选择任务。

## 支持的操作

| 操作 | Python API |
| --- | --- |
| 单尺度同调与代表 | HomologyOperator.betti / class_representative / same_class |
| 同 P 几何 | selected_mass / class_distance / support |
| 有限过滤 | OperatorFamily.barcode / transport_rank / track_mass |
| 原生与复用 | PreparedMatrix / GeometryWorkspace / geometry_batch |

类查询接受循环；原始 project/apply_operator 接受全部链。
合法投影、当前 objective 与全局最优性分别报告。完整调用见[API](INTERFACE.md)，
身份与失败状态见[结果模型](RESULT_MODEL.md)。

## 性能

| 冻结对照 | 范围与结论 |
| --- | --- |
| [S4](S4_REPORT.md) | 27 配置、1,880 独立进程；部分路线有收益，4 组时间退化超过 20% |
| [S5](S5_REPORT.md) | 77 三方正确性输入、2,840 正式进程；集成后端 68 个可比组没有一个 95% 配对区间完全低于 1 |

后端选择保持显式。数字绑定各报告的源码、机器、输入、预算和认证；完整失败与退化保留。
GUDHI 对照覆盖拓扑，额外联合几何的成本单独报告。

## 开发与引用

构建、测试与贡献要求见[开发指南](VALIDATION.md)。项目采用 [MIT License](../LICENSE)。
研究使用请引用实际版本与提交，机器可读信息见 [CITATION.cff](../CITATION.cff)。
