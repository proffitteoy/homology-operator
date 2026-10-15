# Development and validation

[中文](../VALIDATION.md) · [Contributing](../../CONTRIBUTING.md)

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
validate native code. `uv build` creates local artifacts; public uploading follows
the release procedure below. There is no independent typecheck command.

The standalone fixed-boundary query has a focused standard-library test command:

```console
uv run --locked python -m unittest discover -s tests -p test_filling.py -v
```

It checks independent all-chain optima for H1 areas/H2 volumes, small F2 matrices,
infeasibility obstructions, source/basis binding, interrupted results, exact
arithmetic, wire round trips and untrusted certificate replay. No new dependency
or native extension is required. `examples/single_scale.py` also runs a filling query.

## Birth-pair cycle checks

```console
uv run --locked python -m unittest discover -s tests -p test_optimal_cycle.py -v
uv run --locked python examples/filtration.py
```

The standard-library suite compares every chain on small birth windows, including
filled faces, wrong historical classes, repeated scales, both stage conventions,
finite/infinite features, original basis permutations, equal-cost ties, exact
3-4-5 geometry, original-point IDs, disconnected chains, cancellation/budgets,
the rank-17 unsupported case and untrusted certificate replay. Frozen HomCloud
outputs retain different-objective rows as representative comparisons only.

Optional source replay uses the fixed official HomCloud 5.4.0 archive, without
installing HomCloud or its compiled extension. From the repository root:

```powershell
New-Item -ItemType Directory -Force .task-artifacts | Out-Null
Invoke-WebRequest 'https://files.pythonhosted.org/packages/2c/14/0e520f2019bbea4e027adb464cd19055323bd892c220b03190685e32d058/homcloud-5.4.0.tar.gz' -OutFile .task-artifacts/homcloud-5.4.0.tar.gz
$archiveHash = (Get-FileHash .task-artifacts/homcloud-5.4.0.tar.gz -Algorithm SHA256).Hash.ToLowerInvariant()
if ($archiveHash -ne '41a095599249cbc0092a835d6888eb252a6c4cd7935ac71481cd37e00f9e883b') { throw 'HomCloud archive hash mismatch' }
tar -xf .task-artifacts/homcloud-5.4.0.tar.gz -C .task-artifacts homcloud-5.4.0/homcloud/optimal_one_cycle.py
$env:HOMOLOGY_HOMCLOUD_SOURCE = (Resolve-Path .task-artifacts/homcloud-5.4.0/homcloud/optimal_one_cycle.py).Path
uv run --locked python -m unittest discover -s tests -p test_optimal_cycle.py -v
Remove-Item Env:HOMOLOGY_HOMCLOUD_SOURCE
```

The test verifies the file hash and executes only the unchanged upstream pure
Python functions, excluding the unused native import/entry. Public Pair or C++
integration is outside this comparison. Without this environment variable, only
the live source replay is skipped; frozen comparisons and independent enumeration
still run. No new locked/runtime dependency is required.

## Stable-volume and shared geometry checks

```console
uv run --locked python -m unittest discover -s tests -p test_stable_volume.py -v
uv run --locked --group oracle --group oracle-secondary python -m unittest discover -s tests -p test_stable_volume.py -v
uv run --locked python examples/filtration.py
```

The standard-library suite checks the frozen T1--T5 corpus with independent set
enumeration, nonunique minima, histories, epsilon equality, upper and boundary
constraints, conditional convex geometry, fixed-order perturbation sandwiches,
units, cancellation/budgets, source/cost/death tampering and standalone recovery.
The oracle environment additionally runs GUDHI 3.11.0 with F2 and exact integer
insertion stages; original equal scale levels are preserved separately.

For live HomCloud LP replay, reuse the verified archive download above, extract
the following source and install the explicitly optional comparison dependency:

```powershell
tar -xf .task-artifacts/homcloud-5.4.0.tar.gz -C .task-artifacts homcloud-5.4.0/homcloud/optvol.py
uv pip install --python .venv/Scripts/python.exe pulp==3.3.0
$env:HOMOLOGY_HOMCLOUD_VOLUME_SOURCE = (Resolve-Path .task-artifacts/homcloud-5.4.0/homcloud/optvol.py).Path
.venv/Scripts/python.exe -m unittest discover -s tests -p test_stable_volume.py -v
Remove-Item Env:HOMOLOGY_HOMCLOUD_VOLUME_SOURCE
```

The test verifies the source SHA256 before executing unchanged upstream Python
functions and the actual CBC LP solver. PuLP is not a runtime or locked core
test dependency. Missing the source variable skips only live source replay.
The [scope ledger](../FIXTURES.md#geometry-query-corpus-t1-to-t5) records the signed
continuous/binary distinction and the unequal-cutoff negative control.

Local verification on 2026-10-15 / CPython 3.12.13: 270 tests, 226 passed and
44 optional backend tests skipped, with actual GUDHI and both HomCloud source
replays enabled. Separate hash-verified research replay matched all 54 finite
pair/epsilon queries in T1--T5. The isolated installed wheel passed the focused
10-test suite (two optional external-oracle skips) and the filtration example.
Ruff, both examples, wheel/sdist build, Markdown/link checks and strict English
and Chinese Sphinx builds passed. These are local results, not remote CI or a
published release; the skipped native paths receive no new validation claim.

### Complete geometry-query cost admission, 2026-10-15

This bounded local comparison binds the exhaustive reference `7094739` to
the anchor optimization `186db3e330c4b26992cf2c8363db56bd7c145adc`.
Every Python module's byte SHA256 is recorded and was checked against those
sources. The frozen T1--T5 inputs are supplemented by n-vertex polygon fans
(n=8,12,16): close `(0,i,i+1)` under faces, sort by dimension/vertices, use levels
0/1/3 by dimension, unit costs and epsilon=2. No embedding theorem is claimed
for these abstract performance inputs. The fixture and generated-input hashes,
budgets and exact output records are retained per sample.
The assumed combined baseline tree was subsequently checked byte-for-byte
against actual merged main `7d7861979868707135051cac7860329715a61a84`; it is
identical. Synchronizing that main introduces no runtime-source change.

Each workflow measures source conversion, construction, history/pair preparation,
minimum class mass, birth-pair cycle (explicitly unavailable for H2), ordinary
pair volume, fixed-boundary filling, stable volume, original-coordinate location,
independent validation, JSON storage and full family/upper/query restoration with
independent query replay. Cold timings start with source conversion; warm timings
reuse a prepared family but still perform queries, storage and restoration.
Whole child-process latency, including imports/startup, is also recorded.
Nested search/validation/location durations are overlapping costs, not additive
phases. Process peaks use Windows `GetProcessMemoryInfo` peak working set;
logical entry limits are not RSS caps.

Environment: Windows 11 build 26100, CPython 3.12.13 AMD64, Intel64 family 6
model 170 stepping 4; reference Python only. Three fresh processes per variant,
input and cold/warm mode, with alternating variant order; the table reports
medians in milliseconds and the maximum process peak across those samples.
All 96 successful matched samples have identical five-query values, states,
source locations, exactness and certificate grades. The two stable-volume proof
kinds differ but both independently certify `ExactOptimal`. Both variants use
100000 states, 10 seconds and 1000000 logical entries, with no packed-word request.

| Input | Cold before / after ms | Cold ratio | Warm before / after ms | Warm ratio | Peak before / after MiB |
| --- | --- | --- | --- | --- | --- |
| T1 | 164.77 / 159.44 | 1.033 | 131.01 / 134.47 | 0.974 | 30.18 / 30.18 |
| T2 | 157.44 / 159.05 | 0.990 | 123.86 / 122.81 | 1.009 | 30.09 / 30.13 |
| T3 | 165.00 / 173.95 | 0.949 | 144.30 / 140.87 | 1.024 | 30.25 / 30.15 |
| T4 | 199.13 / 216.11 | 0.921 | 168.95 / 169.06 | 0.999 | 30.54 / 30.65 |
| T5 | 194.79 / 191.50 | 1.017 | 167.59 / 171.83 | 0.975 | 30.66 / 30.78 |
| fan8 | 498.79 / 500.71 | 0.996 | 413.55 / 400.43 | 1.033 | 32.79 / 32.72 |
| fan12 | 1273.51 / 1257.91 | 1.012 | 1009.95 / 969.43 | 1.042 | 35.80 / 35.95 |
| fan16 | 4236.32 / 3231.54 | 1.311 | 3729.34 / 2763.70 | 1.349 | 39.40 / 38.80 |

The pre-change profile exposed independent replay and snapshot restoration as
substantial costs. The selected optimization removes an avoidable exhaustive
stable fiber: fan16 visits 8192 candidates before, one after. Its cold median
stable query drops from 678.32 to 17.46 ms, while ordinary pair volume remains
about 687--694 ms. Storage remains about 659--672 ms and restoration/replay
1648.52/1311.18 ms. The actual five-query cold workflow improves only 1.311x;
whole-process medians are 4630.26/3667.36 ms. Small-input regressions remain in
the table, including 8.5% cold T4. Three local samples do not establish general
efficiency, a machine-independent speedup, or new graph/mesh complexity results.
Admission is restricted to the independently proven singleton-anchor case;
all other inputs retain exhaustive search.

This remains a correctness reference with bounded acceleration evidence.
Further performance work must measure independent validation, optimal search
and cross-scale construction as complete workflows. PH-only timings from GUDHI
omit projection construction and geometric certification, so they do not compare
equivalent functionality or establish this library's PH competitiveness.

Six additional negative/domain samples retain state-limit-zero exhaustion,
unsupported packed-word requests and fan20. On fan20 the ordinary affine query
remains unavailable (nullity 17); its dependent fixed-boundary query is explicitly
not run. Stable volume changes from unavailable to an exact singleton-anchor
certificate. That support-domain expansion is not counted as a speed ratio.

One-time harnesses and raw data are preserved in the separate
[PR #110 evidence archive](https://github.com/proffitteoy/homology-operator/tree/570f390ce4daebb76998f3ffb39b95a9e4e00702),
commit `570f390ce4daebb76998f3ffb39b95a9e4e00702` on
`archive/pr110-geometry-cost-20261015`. They are extracted to ignored
`.task-artifacts`, keeping measurement tools and results outside the product tree.
`geometry-cost.jsonl` (102 rows) SHA256 is
`a71b0e8122d181d815152deaaaeb5b9b733c38aacf914206cf730df6b375c3fe`.
The matched-sample harness `geometry_cost_matched.py` SHA256 is
`56b249de732654cb89c59176ef91477467a689715fa88acbb46e59df0c352226`;
the fan20 negative-domain harness `geometry_cost.py` SHA256 is
`db25720efabebd4a2d812e736a13081d6f6c1da12dd584952c404de058d230a0`.
The latter handles the unavailable upstream boundary explicitly. The archive's
standard-library `reproduce.py` verifies the original bytes, all recorded module
hashes against the pinned Git sources, the frozen fixture, sample coverage and
matched output equality. It reconstructs the table and exports source/test trees
directly from Git, without depending on an unpublished baseline directory.
From a fresh repository clone, with Git and Python 3.12 on PATH:

```powershell
git fetch origin archive/pr110-geometry-cost-20261015
New-Item -ItemType Directory -Force .task-artifacts | Out-Null
git -c core.autocrlf=false -c core.eol=lf archive --format=zip --output=.task-artifacts/pr110-cost.zip 570f390ce4daebb76998f3ffb39b95a9e4e00702
Expand-Archive .task-artifacts/pr110-cost.zip -DestinationPath .task-artifacts/pr110-cost
python .task-artifacts/pr110-cost/reproduce.py verify
python .task-artifacts/pr110-cost/reproduce.py summarize
python .task-artifacts/pr110-cost/reproduce.py run
```

The archive command disables Git's line-ending conversion so the original
byte hashes remain valid even when a Windows clone defaults to `autocrlf=true`.
Verification and table reconstruction are portable. Rerunning the unchanged
historical harness requires Windows for `GetProcessMemoryInfo`; it writes 102
fresh records to `replay.jsonl`, never replacing the original data. Timings and
memory peaks depend on the host. The archive README documents smaller runs and
output selection. The archive is research evidence, not a runtime dependency.

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

Pair-volume and fixed-boundary filling use only the reference runtime and the
existing locked development dependencies. Run their independent enumeration,
geometry/source, budget, wire-recovery and certificate-tampering checks with:

```console
uv run --locked python -m unittest discover -s tests -p test_filling.py -v
```

The pair tests enumerate original simplex sets for all finite pairs of four
fixed total orders, including equal scales, both stage conventions and reversed
coordinate orders. They separately measure triangle area and tetrahedral volume,
distinguish upper mass from boundary mass and fixed-boundary optimization, and
verify that semantic replay does not call the solver's solve/kernel routines.

Sphinx + MyST + Furo requires Python 3.11+; CI uses 3.12.

```console
uv venv .task-artifacts/docs-env --python 3.12
uv pip install --python .task-artifacts/docs-env/Scripts/python.exe -r docs/requirements.txt
.task-artifacts/docs-env/Scripts/python.exe -m sphinx -E -n -W --keep-going -b html docs/en .task-artifacts/docs-site
.task-artifacts/docs-env/Scripts/python.exe -m sphinx -E -n -W --keep-going -b html docs .task-artifacts/docs-site/zh
.task-artifacts/docs-env/Scripts/python.exe -m sphinx -E -n -W --keep-going -b html -D html_baseurl=https://proffitteoy.github.io/homology-operator/en/ docs/en .task-artifacts/docs-site/en
```

On Linux use `bin/python`. English is served at `index.html` by default; Chinese
is served at `zh/index.html`. Existing `en/index.html` URLs remain available.
Run the PowerShell 7 Markdown checker and execute changed
code snippets separately. The checker rejects inconsistent table widths and unprotected
math delimiters. Use GitHub backtick-protected inline math and math fences; shared
Sphinx configuration converts them to MyST math nodes at build time. The checker
rejects GitHub's forbidden `\operatorname`; use `\mathrm{...}` for upright names.
It does not fully validate TeX syntax, remote availability, or heading anchors.
After editing formulas, also check GitHub's client rendering.
Successful main builds deploy both languages to
[GitHub Pages](https://proffitteoy.github.io/homology-operator/); pull requests only build.

## Change-specific validation and CI

Validate input shapes/AD=0/positive weights; all four projection conditions;
same-P geometry and arithmetic; transport composition/rank/oracle agreement;
certificate replay; identity mixing/tampering; JSON and legacy round trips.
Native changes require independent reference/enumeration checks and word boundaries.

Reference CI checks Linux Python 3.10/3.12 and isolated reference wheels. Native CI
checks Windows Python 3.10 and Linux Python 3.12 with Rust fmt/Clippy,
`cargo test --lib`, required Python native differential tests and isolated dual
wheels. Oracle CI forces GUDHI comparisons. Documentation CI builds
both languages strictly and deploys main. Local and remote results belong to their
exact source identities. Temporary outputs and wheels stay in ignored directories.

Feature reference/source changes can be checked independently with
`python -m unittest discover -s tests -p test_family.py -v` and
`python -m unittest discover -s tests -p test_backend_integration.py -v` in the
locked environment. The former includes independent coset/rank/PH comparisons,
both stage conventions, raw source and full-history rejection, fixed research
pairs, and schema 3 round trips. The latter checks references across the existing
portable/compact/native action families, including restoration without native.
Run `python examples/filtration.py` to exercise both algebra-only and simplex
provenance paths. No additional runtime or test dependency is required.

## Public releases

The `homology-operator` distribution provides an OS-independent wheel and source
archive. Version 0.0.2 has a standard-library-only runtime. The optional Rust
package is built separately from matching source and is not uploaded to PyPI.
During 0.x, patch releases preserve the public API; breaking changes require a
minor-version increase and release notes. Regression tests cover existing schema
1/2 restoration and preserve historical fixture versions/hashes.

Before release, synchronize pyproject.toml, `__version__`, uv.lock, CITATION.cff,
and the documentation version. Run the checks above, including strict builds of
both documentation languages, and verify all main CI for the release commit.
New result provenance reports the installed package version.

Register a [pending publisher on PyPI](https://pypi.org/manage/account/publishing/)
with project `homology-operator`, owner `proffitteoy`, repository `homology-operator`,
workflow `release.yml`, and environment `pypi`.
[The release workflow](../../.github/workflows/release.yml) runs on a published
GitHub Release whose tag is `v` plus the package version, such as `v0.0.2`.
It tests Python 3.10/3.12, builds/checks wheel and sdist metadata, and runs the full
applicable suite against the isolated wheel before uploading those same artifacts.
The publishing job uses the `pypi` environment and short-lived OIDC identity.

```console
uv build --no-build-isolation
uv tool run --from twine==6.2.0 twine check --strict dist/*
gh release create v0.0.2 --target <verified-commit-sha> --title "homology-operator 0.0.2" --notes-file <release-notes-file>
```

Verify the workflow, [PyPI version record](https://pypi.org/project/homology-operator/0.0.2/),
uploaded SHA-256 digests, and a fresh installation from PyPI. A GitHub Release or
successful build alone does not prove that PyPI uploading completed.
