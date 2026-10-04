# Installation

[中文](../../getting-started/installation.md)

## Install the reference from source

Python 3.10+ is required. The current version is `0.0.2.dev0`, with no PyPI release:

```console
git clone https://github.com/proffitteoy/homology-operator.git
cd homology-operator
python -m pip install .
```

The reference uses only the standard library; Rust, NumPy, and GUDHI are optional.

## Virtual environments

Windows:

```console
python -m venv .venv
.venv\Scripts\python.exe -m pip install .
.venv\Scripts\python.exe examples/single_scale.py
```

Linux:

```console
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python examples/single_scale.py
```

Development with uv:

```console
uv sync --locked --python 3.10
uv run --locked python examples/single_scale.py
```

The example prints JSON with identities, solver and validation records, and readouts.
Continue with the [quickstart](quickstart.md).

## Optional Rust extension

Build and install a matching release wheel separately. See [platform support](../platforms.md)
and [native and batch operations](../guide/native.md). Installing the reference does
not establish native availability.
