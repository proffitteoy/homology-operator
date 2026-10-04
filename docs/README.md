# homology-operator 文档

[在线文档](https://proffitteoy.github.io/homology-operator/) · [English](en/index.md) · [贡献](../CONTRIBUTING.md)

| 需要做什么 | 阅读入口 |
| --- | --- |
| 理解这个算子的定义与数学意义 | [算子理论](MATHEMATICS.md)：核、线性截面、伸长、几何与持久传输的完整论证 |
| 安装并运行第一个例子 | [安装](getting-started/installation.md)、[快速上手](getting-started/quickstart.md) |
| 运行同时读取拓扑与几何的完整算例 | [六边精确算子](guide/single-scale.md#六边复形的精确算子) |
| 构造输入与查询单尺度/过滤 | [Python API](INTERFACE.md) |
| 构建 Rust、packed 代数与批查询 | [native 指南](guide/native.md) |
| 判断状态、身份与快照 | [结果模型](RESULT_MODEL.md) |
| 理解算子、transport 与 barcode 算法 | [数学与架构](ARCHITECTURE.md) |
| 选择 solver、理解支持域及认证 | [solver 契约](SOLVER_CONTRACT.md) |
| 开发、运行测试与构建 | [验证说明](VALIDATION.md)、[测试输入](FIXTURES.md) |
| 判断平台范围 | [平台支持](platforms.md) |

数学主线从新算子的定义出发：在原链空间构造 L=I+P，以核实现同调，以同一作用读取几何，
以核传输实现持久同调模。正式理论与 API、实现架构分别提供阅读入口。

产品包含标准库 Python 接口与可选 Rust 后端，保留同一个 P 的联合输出和独立认证。
Rust 提供 packed 代数、复用分解、Factorized/HC action、限定 solver 与几何批查询。
公开版本仍为源码开发快照 0.0.2.dev0，API/native ABI 兼容政策尚未冻结；采用 [MIT](../LICENSE)。
文档站由 main 的严格双语构建自动发布到 GitHub Pages；PR 只构建检查。
