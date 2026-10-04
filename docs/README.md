# homology-operator 文档

[在线文档](https://proffitteoy.github.io/homology-operator/) · [English](en/index.md) · [贡献](../CONTRIBUTING.md)

| 需要做什么 | 阅读入口 |
| --- | --- |
| 安装并运行第一个例子 | [安装](getting-started/installation.md)、[快速上手](getting-started/quickstart.md) |
| 构造输入与查询单尺度/过滤 | [Python API](INTERFACE.md) |
| 构建 Rust、packed 代数与批查询 | [native 指南](guide/native.md) |
| 判断状态、身份与快照 | [结果模型](RESULT_MODEL.md) |
| 理解算子、transport 与 barcode 算法 | [数学与架构](ARCHITECTURE.md) |
| 选择 solver、理解支持域及认证 | [solver 契约](SOLVER_CONTRACT.md) |
| 开发、运行测试与构建 | [验证说明](VALIDATION.md)、[测试输入](FIXTURES.md) |
| 判断平台范围 | [平台支持](platforms.md) |

产品包含标准库 Python 接口与可选 Rust 后端，保留同一个 P 的联合输出和独立认证。
Rust 提供 packed 代数、复用分解、Factorized/HC action、限定 solver 与几何批查询。
公开版本仍为源码开发快照 0.0.2.dev0，API/native ABI 兼容政策尚未冻结；采用 [MIT](../LICENSE)。
文档站由 main 的严格双语构建自动发布到 GitHub Pages；PR 只构建检查。
