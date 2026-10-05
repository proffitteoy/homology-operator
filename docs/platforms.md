# 平台支持

[English](en/platforms.md)

| 组件 | 要求与实际 CI 范围 |
| --- | --- |
| Python reference | Python 3.10+；Linux CI 3.10/3.12；运行时只用标准库 |
| 可选 Rust | Rust 1.98.1、PyO3 0.29.3、maturin 1.15.0；Windows x64/MSVC + Python 3.10、Linux x64 + Python 3.12 |
| GUDHI oracle | 锁定测试依赖；Windows Python 3.12、Linux Python 3.10/3.12 |
| 文档 | Python 3.11+；CI 用 3.12 与固定 Sphinx/MyST/Furo 依赖 |

其他 native 平台/解释器组合不在当前 CI 矩阵内。本地构建成功不扩大支持范围。
Python 发行提供 `py3-none-any` reference wheel；native 扩展暂从源码构建。
0.x 的 API 兼容政策见[发行说明](VALIDATION.md#公开发行)，native ABI 独立按语义版本校验。
安装入口见[安装](getting-started/installation.md)，具体检查见[开发与验证](VALIDATION.md)。
