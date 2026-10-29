# 02 — Production-workflow tests (current repository)

All tests used disposable clones of `D:\working\asv2\origin.git` (bare clone of the
current repository at `dd3e6b3`). The real checkout was not modified; only this
`diagnostics/` directory is untracked. Synthetic IDs are `VLLM-ASC-95001`…`98001`.

Commands below are the actual ones; the full stdout/stderr is preserved in
`artifacts/logs/`. Where a human/agent decision was simulated, it is marked.

---

## 1. Stage I control — existing workflow end to end

Harness: `artifacts/scripts/test_stage1_v2.py`; record `v2-stage1-025922.json`.

| Step | Command | Exit | Observation |
|---|---|---|---|
| Trace | synthetic `traces/v2-20261029-95001.yaml` (schema-compatible) | — | `sediment_batch --json` lists the session |
| Sedimentation | flat `postmortems/inbox/VLLM-ASC-95001.case.yaml` + `.md` (current V1 format; agent action simulated) | — | files written |
| Draft validation | `python scripts/verify_case_draft.py <draft>` | 0 | pass |
| Promotion gate | `python scripts/verify_case_draft.py --gate <draft> --root .` | 0 | pass (trace closed) |
| Promotion | copy `cases:` body to `knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-95001.yaml` (agent action) | — | file created |
| Local rebuild | `python scripts/rebuild_generated.py --check` | 0 | 4 generated files dirty |
| PR CI emulation | restore generated files; commit source-only branch; run `rebuild_generated.py --check` then `build_index.py --check` | 0 / 0 | index is green only after the rebuild action, as CI does |
| Other gates | `verify_case_draft --all`, `verify_references`, `verify_entry_activity`, `verify_metrics`, `holdout` | 0 | all green |
| Merge | `git merge --no-ff kb/s1` in integration clone | 0 | 1 file |
| Post-merge rebuild | `rebuild_generated.py --check` + commit bot-style | 0 | 4 generated files committed |
| Retrieval | grep `VLLM-ASC-95001` in the class view and `_index.yaml` | 0 | present |

**Result: PASS (control).** The single-contributor path still works on the current
commit. The first run showed `build_index --check` red before the CI rebuild action;
that is expected in the source-only-PR discipline and is why the control runs the
rebuild action first.

**Boundary:** the diagnosis conversation and the YAML authoring were performed by the
harness, not by a full agent. The trace is schema-compatible, not a real diagnostic
session. This is a workflow control, not evidence about diagnosis quality.

---

## 2. S2/S3 baseline — two clones, same problem, different IDs/categories

Harness: `artifacts/scripts/test_baseline_duplicate_v2.py`; record
`v2-baseline-duplicate-030450.json`.

- A: `VLLM-ASC-97001`, `interrupt`, root cause "310P does not support bfloat16".
- B: `VLLM-ASC-97002`, `precision`, same root cause, different symptoms wording.
- Merge A then B; run the post-merge rebuild each time; then run gates.

Observed: both merges `rc=0`; `rebuild_generated --check` green; `verify_case_draft`
green; `build_index --check` green; `verify_references` green; `verify_entry_activity`
green; both `VLLM-ASC-97001` and `VLLM-ASC-97002` are in the master index.

**Result: baseline failure reproduced on the current commit.** No decision was
requested; no duplicate was surfaced; both cases are active.

---

## 3. S1 — shared inbox, real concurrency

Harness: `artifacts/scripts/test_s1_v2.py`; record `v2-s1-025934.json`.

- V1: two threads synchronized with a `Barrier` write the same
  `VLLM-ASC-97001.case.yaml`; 10 rounds. Result: **0 rounds with both writers'
  markers, 10 rounds with exactly one** — silent overwrite.
- V2: eight simultaneous processes call `inbox_v2.py new`; result: **8 directories,
  8 distinct UUIDs**.
- Additional V2 cases (`v2-a-030836.json`): finish complete; repeated finish refused;
  edit after DONE → `corrupt`; crash after mkdir/partial file/truncated DONE →
  `incomplete`/`corrupt`; same `deployment.id` in two clones → distinct UUIDs;
  copied draft under a different directory → `corrupt` (identity mismatch); legacy flat
  listed; `verify_case_draft` accepts the draft's case file.

**V2 reopen crash window (new finding N1).** After a successful `reopen`, deleting the
old `SUPERSEDED` marker (simulating a crash after the new draft is published but
before the old marker) leaves **both directories `complete`**; the reader does not
cross-check the new `supersedes` link. Recorded in `v2-a-030836.json`.

---

## 4. S4/S5/S6/S7 — Checkpoint C scenarios

Harness: `artifacts/scripts/test_checkpoint_c_v2.py`; record `v2-c-030729.json`.

| Scenario | V2 C exit | Evidence |
|---|---|---|
| Different IDs, same problem, no decision | 2 | pair `VLLM-ASC-93002 ↔ 93001`, mandatory |
| Same, with decision (pairs + main SHA) | 0 | decision coverage + freshness pass |
| Decision pair value `TODO` | **0** | placeholder accepted (N2) |
| Change the PR head after the decision | **0** | recorded `head_sha` not checked (N3) |
| Main advances, old decision | 1 | stale base; missing new pair |
| Refresh decision after main advanced | 0 | coverage updated |
| Same-path add/add, different content | 3 | `same_path_added` + field conflicts |
| Both modify same case, disjoint fields, no decision | 2 | `both_modified` requires decision |
| Same, with `same_case` decision | 0 | disjoint fields accepted |
| `same_case.decision = TODO` | **0** | placeholder accepted (N2) |
| Generated artifact changed | 4 | `knowledge/_index.yaml` |
| Rename on one side, reference on other | 3 | `renamed` + `dangling` mention |

**Boundary:** the “required check” is simulated by the harness: when C exits non-zero,
the harness does not merge. No GitHub ruleset/required check was exercised. The
difference between “report says X” and “merge blocked” is real and is not claimed as
verified.

---

## 5. S8 — concurrent metric snapshots

Harness: `artifacts/scripts/test_e10_v2.py`; record `v2-e10-030746.json`.

Two clones with separate traces run the real `metrics_snapshot.py --json`. Both choose
the same period `2026-W44-live-1029`. In this run the numeric readings happened to be
identical (the trace fixture did not change `sessions_total`); the collision is in the
**filename/period**, not in the diff. The previous baseline at `28adab0` had different
readings and a Git add/add conflict; the code path is unchanged. V2's proposed
deployment-id suffix is **not implemented**, so the current behavior still allows two
deployments to write the same path.

**Result: E10 remains; V2 fix UNTESTED.**

---

## 6. E11 — numeric-looking SHA

Harness: `artifacts/scripts/test_defects_v2.py`; record `v2-defects-025306.json`.

Current code: two `entry-activity.d` rows with `checkout: 8577483` (parsed as int) and
`checkout: 55c20dc` (str) → `build_entry_activity.py`:
`TypeError: '<' not supported between instances of 'str' and 'int'` at
`entry_activity.py:495` (`sorted(checkouts)`); exit 1.

Prototype fix in the disposable clone: `sorted(str(x) for x in checkouts)` → exit 0,
both deployment artifacts rebuilt.

**E11 reproduced; fix works as a one-line prototype.** The writer side
(`settle_trace_feedback.py:286-287`) still writes unquoted values; production fix must
also quote/normalize there.

---

## 7. E12 — snapshot output vs its validator

Current code: `metrics_snapshot.py --emit-yaml` → write the period file → rebuild
timeline → `verify_metrics.py --check` returns 1 with two errors:

- `external_record_violations_total` is outside the live whitelist;
- six metrics lack a `metric_strength` declaration:
  `considered_candidates_events`, `external_record_violations_total`,
  `parallel_group_events`, `stop_reason_unrecorded`, `trace_record_violations_total`,
  `triage_miss_classes`.

Prototype fix: add the missing live field and the six strength entries in the clone →
`verify_metrics --check` returns 0.

**E12 reproduced; fix works as a prototype.** This blocks the documented weekly
snapshot step until implemented.

---

## 8. S9 — stale generated index / rebuild failure

Harness: `artifacts/scripts/test_s9_v2.py`; record `v2-s9-025814.json`.
`check_main_freshness.py` is a thin wrapper around `build_index.py --check`.

- Add a case without rebuilding: heartbeat returns **1**, printing the missing index
  rows.
- Run `rebuild_generated.py --check`: 0; heartbeat returns **0** (`FRESH`).

**Detection works in a prototype.** It is not wired into CI; the existing
`rebuild-generated` job remains the primary mechanism, and a failed job still has no
alert without this heartbeat or an equivalent scheduled check.

---

## 9. Real vs simulated

| Item | Real execution | Simulated / inspected |
|---|---|---|
| Current workflow, A/B merge, gates, rebuild, retrieval | yes | diagnosis conversation and YAML authoring |
| Shared-inbox concurrency | yes (threads/processes) | human inbox operator |
| Duplicate cases | yes (real Git merges) | reviewer decisions |
| Checkpoint A reader/crash | yes (prototype CLI) | groom/panel integration |
| Checkpoint B | yes (prototype over real library) | reviewer reading the report |
| Checkpoint C | yes (prototype over real Git refs) | GitHub required check/approval/queue |
| Required enforcement | no | harness blocks on non-zero C; GitHub **UNTESTED** |
| Provenance | yes (checker over files) | rename/usage/refs/fixtures migration |
| E11/E12 | yes (current + patched clone) | production deployment |
| E10 | yes (current naming) | V2 naming fix |
| E13 | static API read only | actual enforcement **UNTESTED** |

## 10. Commands (abbreviated)

```powershell
$env:ASV2_ROOT = "D:\working\asv2"
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_stage1_v2.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_baseline_duplicate_v2.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_s1_v2.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_checkpoint_a.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_checkpoint_b_v2.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_checkpoint_c_v2.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_provenance_v2.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_defects_v2.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_e10_v2.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\test_s9_v2.py
python diagnostics\concurrency-v2-validation\artifacts\scripts\run_integrated_v2.py
```
