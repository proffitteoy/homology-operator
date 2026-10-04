# 输入语义

[English](../en/guide/input-semantics.md)

## 链窗口

输入固定次数的 `C_{k+1} --D--> C_k --A--> C_{k-1}`，`A` 为 m×n，`D` 为 n×p，采用列向量。
提供三个次数的带序基与 n 个严格正权，构造时独立校验形状、基标识和 `AD=0`。
允许空链空间；基标识必须唯一且非空。非法输入抛 `InvalidInput`，不自动修复。

## F2 坐标

矩阵与向量接受整数 0/1，不接受 bool、float、取模或截断。
空矩阵保留显式形状；`Matrix.from_rows((), ncols=3)` 表示 0×3。
消元不交换原列顺序，核、像与支撑始终按原基解释。

## 权重

| 算术 | 输入与语义 |
| --- | --- |
| ExactInteger | 任意精度 int，几何精确，objective 比值用 Fraction |
| ExactRational | int/Fraction，默认的精确有理运算 |
| FloatingPoint | 显式转为有限正 binary64，几何使用 fsum，非精确最优认证 |

调用者声明权重的语义和单位；正权不自动代表面积或体积。
F2 代数精确性与浮点几何精确性分别报告。完整构造签名见[Python API](../INTERFACE.md#链窗口)。
