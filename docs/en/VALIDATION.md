# Development and validation

[中文](../VALIDATION.md) · [Contributing](../../CONTRIBUTING.en.md)

## Reference environment

Python 3.10+ and uv; the runtime uses only the standard library. From the repository root:

```console
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

Missing native dependencies explicitly skip native tests. A reference pass does not
validate native code. There is no independent typecheck or public release command.

## Native and oracle checks

Build/install the matching wheel using the [native guide](guide/native.md).

```powershell
$env:HOMOLOGY_NATIVE_REQUIRED = '1'
uv run --locked --no-sync python -m unittest discover -s tests -v
cargo +1.98.1 fmt --manifest-path native/Cargo.toml --check
cargo +1.98.1 clippy --manifest-path native/Cargo.toml --locked --all-targets -- -D warnings
$env:PYO3_PYTHON = Join-Path (Get-Location) '.venv/Scripts/python.exe'
cargo +1.98.1 test --manifest-path native/Cargo.toml --locked --lib
```

Use `.venv/bin/python` on Linux. Rebuild after Rust changes; `--no-sync` retains the extension.
The optional GUDHI test environment is locked independently:

```powershell
uv sync --locked --group oracle --group oracle-secondary --python 3.12
$env:HOMOLOGY_GUDHI_REQUIRED = '1'
uv run --locked --group oracle --group oracle-secondary python -m unittest discover -s tests -p test_simplicial_inputs.py -v
uv run --locked --group oracle --group oracle-secondary python -m unittest discover -s tests -p test_gudhi_oracle.py -v
uv run --locked --group oracle --group oracle-secondary python -m unittest discover -s tests -p test_oracle_corpus.py -v
```

These tests compare actual simplicial inputs and F2 stage Betti/barcode/rank results.
The 77-input regression also checks same-P geometry and snapshot restoration.
Oracles never populate production results. See [fixture provenance](../FIXTURES.md).

## Documentation and GitHub Pages

Sphinx + MyST + Furo requires Python 3.11+; CI uses 3.12.

```console
uv venv .task-artifacts/docs-env --python 3.12
uv pip install --python .task-artifacts/docs-env/Scripts/python.exe -r docs/requirements.txt
.task-artifacts/docs-env/Scripts/python.exe -m sphinx -E -n -W --keep-going -b html docs .task-artifacts/docs-site
.task-artifacts/docs-env/Scripts/python.exe -m sphinx -E -n -W --keep-going -b html docs/en .task-artifacts/docs-site/en
```

On Linux use `bin/python`. Run the PowerShell 7 Markdown checker and execute changed
code snippets separately. Successful main builds deploy both languages to
[GitHub Pages](https://proffitteoy.github.io/homology-operator/); pull requests only build.

## Change-specific validation and CI

Validate input shapes/AD=0/positive weights; all four projection conditions;
same-P geometry and arithmetic; transport composition/rank/oracle agreement;
certificate replay; identity mixing/tampering; JSON and legacy round trips.
Native changes require independent reference/enumeration checks and word boundaries.

Reference CI checks Linux Python 3.10/3.12 and isolated reference wheels. Native CI
checks Windows Python 3.10 and Linux Python 3.12 with required native tests and
isolated dual wheels. Oracle CI forces GUDHI comparisons. Documentation CI builds
both languages strictly and deploys main. Local and remote results belong to their
exact source identities. Temporary outputs and wheels stay in ignored directories.
