# 安装

[English](../en/getting-started/installation.md)

## 从 PyPI 安装

需要 Python 3.10+。[0.0.2 已在 PyPI 发行](https://pypi.org/project/homology-operator/0.0.2/)，执行：

```console
python -m pip install homology-operator==0.0.2
```

该 reference wheel 不依赖操作系统，无需 Rust 编译器。

## 从源码安装

也可直接克隆仓库安装：

```console
git clone https://github.com/proffitteoy/homology-operator.git
cd homology-operator
python -m pip install .
```

reference 运行时仅使用标准库，不需要 Rust、NumPy 或 GUDHI。

## 隔离环境

Windows：

```console
python -m venv .venv
.venv\Scripts\python.exe -m pip install .
.venv\Scripts\python.exe examples/single_scale.py
```

Linux：

```console
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python examples/single_scale.py
```

开发环境可用 uv：

```console
uv sync --locked --python 3.10
uv run --locked python examples/single_scale.py
```

示例打印包含身份、solver、验证记录与读取结果的 JSON。继续阅读[快速上手](quickstart.md)。

## 可选 Rust 扩展

扩展单独构建和安装。使用当前源码匹配的 release wheel；支持平台见[平台支持](../platforms.md)，
完整步骤见[原生与批查询指南](../guide/native.md)。reference 安装成功不证明 native 已安装。
