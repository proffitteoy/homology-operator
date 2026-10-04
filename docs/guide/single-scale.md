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
