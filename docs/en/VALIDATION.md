# Development and validation

[中文](../VALIDATION.md) · [Contributing](../../CONTRIBUTING.en.md)

## Reference environment

Python 3.10+ and uv are required; the runtime uses only the standard library.
Run from the repository root:

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

The test count belongs to the exact checkout. Native tests explicitly skip when
the optional extension is absent; a reference pass does not validate native code.
`uv build` creates local artifacts, not a release. There is no separate typecheck
or public publishing command.

## Native and oracle checks

Build/install the matching release wheel using the [native guide](guide/native.md).
In PowerShell:

```powershell
$env:HOMOLOGY_NATIVE_REQUIRED = '1'
uv run --locked --no-sync python -m unittest discover -s tests -v
cargo +1.98.1 fmt --manifest-path native/Cargo.toml --check
cargo +1.98.1 clippy --manifest-path native/Cargo.toml --locked --all-targets -- -D warnings
```

`--no-sync` retains a separately installed extension. Rebuild after native source
changes; an old binary cannot validate new source. Requiring native availability
prevents a skip-only suite from appearing to certify the backend.

The S5 oracle environment uses locked optional dependencies:

```powershell
uv sync --locked --group oracle --group oracle-secondary --python 3.12
$env:HOMOLOGY_GUDHI_REQUIRED = '1'
uv run --locked --group oracle --group oracle-secondary python -m unittest discover -s tests -p "test_s5*.py" -v
uv run --locked --group oracle --group oracle-secondary python scripts/check_s5_inputs.py --output .task-artifacts/s5-inputs.json
uv run --locked --group oracle --group oracle-secondary python scripts/check_s5_oracle.py --require-secondary --output .task-artifacts/s5-oracle.json
```

Oracles supply independent comparison evidence and never populate production
projections, representatives or barcodes.

## Documentation builds

Like Topp, the site uses Sphinx + MyST + Furo with separate Chinese and English
source roots and builds. Documentation requires Python 3.11+; CI uses 3.12.
This does not raise the library's Python 3.10 requirement.

```console
uv venv .task-artifacts/docs-env --python 3.12
uv pip install --python .task-artifacts/docs-env/Scripts/python.exe -r docs/requirements.txt
.task-artifacts/docs-env/Scripts/python.exe -m sphinx -E -n -W --keep-going -b html docs .task-artifacts/docs-site
.task-artifacts/docs-env/Scripts/python.exe -m sphinx -E -n -W --keep-going -b html docs/en .task-artifacts/docs-site/en
```

On Linux, use `.task-artifacts/docs-env/bin/python`. The homepages are
`.task-artifacts/docs-site/index.html` and `en/index.html`. Build warnings fail the
job. Also run the PowerShell 7 source-link checker; it checks root/docs Markdown,
including untracked files, UTF-8, conflict markers and repository-local file links.
It does not check heading anchors or external availability. Execute modified
code snippets separately; site builds do not run mathematical tests.

The documentation workflow uploads a site artifact. Hosting remains a separate
configuration and is not implied by a successful build.

## Minimum change-specific validation

| Change | Required independent evidence |
| --- | --- |
| Algebra/window | Shapes, empty spaces, illegal coordinates/weights, AD≠0, basis ordering |
| Projection/solver | P²=P, AP=0, PD=0, full-cycle homology preservation; supported certificate replay and failures |
| Geometry | Same-P mass, distance and support identities; zero, arithmetic and mixed-identity failures |
| Transport | Identity/composition, induced homology agreement, full-rank and independent barcode comparison |
| Identity/schema | Round-trip, tampering/mixing rejection, legacy restoration, valid zero vs missing |
| Native/packed | Canonical reference output and independent vector enumeration, rectangular/rank-deficient/empty and word-boundary cases |
| Performance | Matched fixture/P/solver/certificate/budget, source/build hashes, full costs, independent RSS and all failures |

Retain the zero-projection counterexample in nonzero homology: the first three
projection equalities do not ensure cycle homology preservation. Read the relevant
contracts before editing and keep the implementation small.

## CI, provenance, and frozen evidence

Reference CI covers Linux Python 3.10/3.12, tests/examples/lint/build, isolated
wheel import and Markdown checks. Native CI covers the stated Windows/Linux
matrix with required native differential checks. S5 oracle CI forces its locked
oracle checks. Documentation CI strictly builds both languages.

Configuration, local success and remote success are separate evidence. Remote
claims must cite the exact SHA; [implementation status](../README.md) records the
verified baseline. Historical [Phase 3](../PHASE3_REPORT.md), [S4](../S4_REPORT.md)
and [S5](../S5_REPORT.md) reports retain their original source, results and limits.
Do not reuse old performance samples as measurements of a new commit.

The project uses the [MIT License](../../LICENSE). API/native ABI compatibility
policies and the public release process remain development work.
