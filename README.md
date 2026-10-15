# PR #110 complete geometry-query cost archive

This branch is a research evidence archive, separate from the product tree.
It preserves the original 102 JSONL records and both original harnesses byte for
byte. `manifest.json` binds their SHA256 values and the full before/after source
commits. The added standard-library `reproduce.py` verifies those bindings,
reconstructs the published median table, and reruns the complete experiment.
The source/test trees are exported from the pinned Git commits, without checkout
line-ending conversion. No local unpublished baseline directory is required.

From a clone of `proffitteoy/homology-operator`, extract this archive into
`.task-artifacts/pr110-cost`, then use Python 3.12 (the original used 3.12.13):

```powershell
python .task-artifacts/pr110-cost/reproduce.py verify
python .task-artifacts/pr110-cost/reproduce.py summarize
python .task-artifacts/pr110-cost/reproduce.py run
```

Verification and table reconstruction work with standard-library Python and Git
on any supported host. Rerunning the unchanged harness requires Windows because
it records peak working set through `GetProcessMemoryInfo`. The matched runs use
T1--T5/fan8/fan12/fan16, cold/warm modes, three fresh processes per variant and
alternating variant order. Six additional controls cover zero states,
unsupported packed-word requests and fan20. This produces 102 new records.

Use `--cases T2 fan16 --repeats 1` for a smaller check, or `--skip-controls` to
omit domain controls. `--output` selects a new JSONL path; existing output and
the frozen data are protected against replacement. A replay checks five-query
output equality between variants. Timings and process peaks are new observations;
they are not expected to equal the original Windows measurements.

The full workflow includes conversion, construction, preparation, five queries,
independent validation, source locations, storage and restoration. Nested phase
durations overlap and must not be summed. Warm runs reuse prepared objects.
The fan20 change expands the stable-volume support domain and is not a speed
ratio. Small-input regressions remain in the data. Three local samples do not
establish general performance, PH-only competitiveness, or arbitrary point-cloud
geometry certification. Original `source` fields identify the historical local
paths; file hashes and pinned Git objects provide the portable provenance.
