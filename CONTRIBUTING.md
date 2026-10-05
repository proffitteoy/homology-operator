# 为 homology-operator 贡献

[README](README.md) · [English](CONTRIBUTING.en.md) · [开发与验证](docs/VALIDATION.md)

欢迎提交文档、示例、输入校验、正确性、性能和跨平台构建改进。
开始前阅读 [项目约定](AGENTS.md)及改动领域的契约；提交小范围改动，说明触发条件、
最终行为与实际运行的检查。问题与建议可提交到 [GitHub Issues](https://github.com/proffitteoy/homology-operator/issues)。

## 开发环境

Python 3.10+ 和 uv；reference 运行时只依赖标准库。仓库根目录执行：

```console
uv sync --locked --python 3.10
uv run --locked python -m unittest discover -s tests -v
uv run --locked ruff check .
uv run --locked ruff format --check .
pwsh -NoProfile -File ./scripts/check_docs.ps1
git diff --check
```

未安装扩展时 native 测试会明确跳过。改动 Rust 或 native 适配必须重建匹配扩展，
并用 `HOMOLOGY_NATIVE_REQUIRED=1` 运行适用测试；命令见[验证说明](docs/VALIDATION.md)。
GUDHI 是可选测试 oracle，须使用锁定依赖并强制运行对应检查。

## 修改与验收

| 改动 | 随改动提交的内容 |
| --- | --- |
| 文档或示例 | 更新实际入口；运行本地链接检查与严格站点构建；新增/修改代码片段实际执行 |
| 输入、F2 代数、投影或 solver | 独立不变量、失败输入、循环同调保持、认证与资源状态测试 |
| transport / barcode | composition、全区间 rank、独立 oracle 对拍、重复尺度与末端存活 |
| 身份、schema 或恢复 | round-trip、混用与篡改拒绝、旧格式兼容、合法零与缺失状态 |
| 性能 | 同输入/P/认证/预算的完整成本；源码、构建、环境、样本与失败/退化记录 |

完整门槛以 [VALIDATION](docs/VALIDATION.md) 为准。请同步检查 API、注释、README、测试及示例。
不将 `selected_mass` 表述为最短类质量，不将合法投影升级为最优认证，
不以独立 PH reduction 或 GUDHI 输出填充主结果。

## 文档站

站点沿用现有 Markdown；Python 3.11+ 的文档依赖独立安装，命令见
[文档构建](docs/VALIDATION.md#文档站构建)。中英文公开入口变更需同步检查示例和能力边界。
仓库只保留产品实现、测试、示例与文档；临时测量或调研材料放入忽略目录。

## Pull request

描述问题与最终行为，注明修改范围、实际验证、跳过项和剩余限制。
涉及性能时链接可复现命令与绑定源码的证据；所有退化与失败一起公开。
不要提交虚拟环境、构建缓存、wheel 或临时测量产物。
0.x 发行的兼容政策和 Trusted Publisher 流程见[发行说明](docs/VALIDATION.md#公开发行)。
