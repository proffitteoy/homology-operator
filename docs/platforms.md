# 平台支持

[English](en/platforms.md)

| 组件 | 要求与实际 CI 范围 |
| --- | --- |
| Python reference | Python 3.10+；Linux CI 3.10/3.12；运行时只用标准库 |
| 可选 Rust | Rust 1.98.1、PyO3 0.29.3、maturin 1.15.0；Windows x64/MSVC + Python 3.10、Linux x64 + Python 3.12 |
| GUDHI oracle | 锁定测试依赖；Windows Python 3.12、Linux Python 3.10/3.12 |
| 文档 | Python 3.11+；CI 用 3.12 与固定 Sphinx/MyST/Furo 依赖 |

其他 native 平台/解释器组合不在当前 CI 矩阵内。本地构建成功不扩大支持范围。
当前无 PyPI wheel 发行，API 与 native ABI 兼容政策仍未冻结。
安装入口见[安装](getting-started/installation.md)，具体检查见[开发与验证](VALIDATION.md)。
