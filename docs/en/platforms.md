# Platforms and support

[中文](../platforms.md)

| Component | Required environment and verified CI scope |
| --- | --- |
| Python reference | Python 3.10+; Linux CI uses 3.10 and 3.12; standard library runtime |
| Optional Rust | Rust 1.98.1, PyO3 0.29.3, maturin 1.15.0; Windows x64/MSVC + Python 3.10, Linux x64 + Python 3.12 |
| GUDHI oracle | Locked test-only dependencies; Windows Python 3.12 and Linux Python 3.10/3.12 |
| Documentation | Python 3.11+; build CI uses 3.12 and pinned Sphinx/MyST/Furo dependencies |

Other native platforms and interpreter combinations are outside the current CI
matrix. A successful local build does not expand the public support claim.
The Python distribution provides a `py3-none-any` reference wheel. Native wheels
are built separately from source. The 0.x API policy is in
[public releases](VALIDATION.md#public-releases); native ABI uses its own semantics version. See [installation](getting-started/installation.md) and
[development checks](VALIDATION.md).
