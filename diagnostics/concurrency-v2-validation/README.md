# Concurrency V2 validation — evidence bundle

This directory is the independent second validation of the V2 proposal. It contains
documents only; no production knowledge, workflow, ruleset, or V2 design document was
modified.

## Documents

| File | Purpose |
|---|---|
| `01-v1-v2-comparison.md` | V1 → V2 mechanism matrix and what changed |
| `02-production-workflow-tests.md` | Commands, exit codes, control workflow, S1/S8/S9, E11/E12 |
| `03-checkpoint-validation.md` | A/B/C/provenance verdicts with evidence and limitations |
| `04-integrated-concurrency-tests.md` | Two-engineer workflow, before/after, simulated gate |
| `05-new-findings.md` | New failures, severity, corrective action |
| `06-recommendations.md` | P0/P1/P2, structural cost, acceptance, tradeoffs |
| `07-final-assessment.md` | ACCEPT WITH CHANGES decision and the 12 required answers |
| `08-friday-review-summary.md` | Chinese 10-minute review summary |
| `09-implementation-design-and-migration.md` | Target layout, component changes, inbox migration, structural cost |
| `10-platform-enforcement-spike-plan.md` | Plan (not yet run) for verifying GitHub required-check/up-to-date/approval/merge_group behavior in a disposable repo, ahead of N11/E13 |
| `11-evidence-and-batch-collision-plan.md` | Observation metrics, batch-ingest collision test, red-team and reviewer audit |

## Evidence

- `artifacts/proto/` — executable prototypes (A reader/writer, B comparator, C recheck,
  provenance checker, freshness heartbeat). They are intentionally small and live only
  here.
- `artifacts/scripts/` — harnesses that create disposable clones under
  `D:\working\asv2`, seed synthetic cases, and record exit codes.
- `artifacts/logs/` — JSON records copied from the lab. Each row contains the command
  result and the captured stdout/stderr tail.

## Reproduce

The harnesses expect `ASV2_ROOT` (default `D:\working\asv2`) with a bare
`origin.git` cloned from the repository, plus a `base` clone. The scripts reset
`origin/main` before each scenario. They never touch the real checkout.

```powershell
$env:ASV2_ROOT = "D:\working\asv2"
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_stage1_v2.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_checkpoint_a.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_checkpoint_b_v2.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_checkpoint_c_v2.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\run_integrated_v2.py
```

The synthetic IDs (`VLLM-ASC-95xxx`…`98xxx`) do not exist in the real library.
Experiments that write data run in disposable clones; the real GitHub remote is not
used.
