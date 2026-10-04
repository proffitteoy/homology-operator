# 开发与验证

从仓库根目录执行以下命令。安装和支持域见 [API](INTERFACE.md)、[平台支持](platforms.md)。

## Reference 环境

Python 3.10+、uv；运行时仅标准库，开发依赖由 uv.lock 锁定。

```powershell
uv sync --locked --python 3.10
uv run --locked python -m unittest discover -s tests -v
uv run --locked python examples/single_scale.py
uv run --locked python examples/filtration.py
uv run --locked ruff check .
uv run --locked ruff format --check .
uv build --no-build-isolation
pwsh -NoProfile -File ./scripts/check_docs.ps1
git diff --check
```

测试数绑定实际 checkout；缺少扩展时 native 测试明确跳过。
reference 通过不证明 native 路径通过。`uv build` 生成本地产物，尚无独立 typecheck 或公开发布命令。

## Rust 后端

按 [native 安装](INTERFACE.md#可选-rust-扩展)构建并安装匹配解释器的 release wheel：

```powershell
$env:HOMOLOGY_NATIVE_REQUIRED = '1'
uv run --locked --no-sync python -m unittest discover -s tests -v
cargo +1.98.1 fmt --manifest-path native/Cargo.toml --check
cargo +1.98.1 clippy --manifest-path native/Cargo.toml --locked --all-targets -- -D warnings
$env:PYO3_PYTHON = Join-Path (Get-Location) '.venv/Scripts/python.exe'
cargo +1.98.1 test --manifest-path native/Cargo.toml --locked --lib
```

`--no-sync` 保留单独安装的扩展；改 Rust 源码必须重建。强制变量防止用跳过冒充验证。
Linux 的 PYO3_PYTHON 使用 `.venv/bin/python`。Rust 单测和 Python 差分分别验证内部边界与公共结果。

## 独立拓扑 oracle

GUDHI 只用于产品测试，不填充生产投影、几何或 barcode。

```powershell
uv sync --locked --group oracle --group oracle-secondary --python 3.12
$env:HOMOLOGY_GUDHI_REQUIRED = '1'
uv run --locked --group oracle --group oracle-secondary python -m unittest discover -s tests -p test_simplicial_inputs.py -v
uv run --locked --group oracle --group oracle-secondary python -m unittest discover -s tests -p test_gudhi_oracle.py -v
uv run --locked --group oracle --group oracle-secondary python -m unittest discover -s tests -p test_oracle_corpus.py -v
```

oracle 核对实际显式复形、F2、stage 语义、Betti、barcode 多重集和全区间 rank。
普通回归保留 77 份输入的同 P 几何和恢复检查；native 环境另比较其拓扑/投影。
来源与输入 hash 见 [fixtures](FIXTURES.md)。

## 文档站构建

Sphinx + MyST + Furo；文档要求 Python 3.11+，CI 使用 3.12。

```powershell
uv venv .task-artifacts/docs-env --python 3.12
uv pip install --python .task-artifacts/docs-env/Scripts/python.exe -r docs/requirements.txt
.task-artifacts/docs-env/Scripts/python.exe -m sphinx -E -n -W --keep-going -b html docs .task-artifacts/docs-site
.task-artifacts/docs-env/Scripts/python.exe -m sphinx -E -n -W --keep-going -b html docs/en .task-artifacts/docs-site/en
```

Linux 使用该环境的 `bin/python`。两语言首页为 `index.html` 和 `en/index.html`。
文档检查需要 PowerShell 7，只读检查根目录与 docs 下的 Markdown、UTF-8、冲突标记和本地文件链接。
它不验证外网可达性或标题锚点；修改代码片段后单独运行。
main 构建通过后自动部署 [GitHub Pages](https://proffitteoy.github.io/homology-operator/)；PR 只执行检查。

## 按变更验证

| 变更 | 最低独立验证 |
| --- | --- |
| 输入/F2 代数 | 形状、空空间、非法坐标/正权、AD≠0、基次序 |
| 投影/solver | P²=P、AP=0、PD=0、全循环同调保持；证书重放、失败和资源耗尽 |
| 几何 | 同 P 质量/距离/支撑、合法零、算术与身份混用 |
| transport/barcode | 恒等/复合、诱导同调映射、全区间 rank 和独立 PH 对拍 |
| 身份/恢复 | JSON 往返、篡改/混用拒绝、旧格式、缺失与零值 |
| native/packed | reference 及独立枚举差分，矩形、秩亏、空矩阵与字边界 |

## CI 与打包边界

- [reference.yml](../.github/workflows/reference.yml)：Linux Python 3.10/3.12，回归、示例、Ruff、构建与无扩展隔离 wheel。
- [native.yml](../.github/workflows/native.yml)：Windows/MSVC Python 3.10 与 Linux Python 3.12，Rust 检查、强制 native 与隔离双 wheel。
- [oracle.yml](../.github/workflows/oracle.yml)：锁定 GUDHI 的 Windows/Linux 拓扑差分。
- [docs.yml](../.github/workflows/docs.yml)：严格双语构建及 main 的 Pages 部署。

配置、本地通过和远端 CI 通过分别报告，远端结论绑定实际提交。
临时结果、构建缓存和 wheel 写入 `.task-artifacts/` 或 `dist/`，不提交到产品目录。
