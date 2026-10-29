# 02 — Baseline findings (Stage I: the system as it is today)

All experiments ran in disposable clones of the baseline commit
`28adab0d1db1f00989b5416dfeaf8206df71ca4a`, under `D:\working\asv`, with synthetic,
invented content. No production file, branch, trace, draft, case or metric of the real
checkout was modified. The report directory is the only addition to the real
repository (`git status`: `?? diagnostics/`).

Evidence lives in `artifacts/logs/`; each finding names the record and step. Console
transcripts are the same runs, untruncated. No GitHub CI run was executed; GitHub-side
facts are from the public API and are labelled as such.

Test data (synthetic):

| ID | Meaning |
|---|---|
| `VLLM-ASC-90001` | 310P, bf16 unsupported, startup failure, `interrupt`, `inference/vllm-ascend` |
| `VLLM-ASC-90002` | same problem expressed as zero-output, `precision`, same namespace |
| `VLLM-ASC-90003` | HCCL port collision (used for the same-path conflict) |
| `VLLM-ASC-92001/2/3` | branches for Checkpoint C races |

---

## 1. End-to-end run, one engineer (control)

**Result: the documented path works, and every gate is green.**

Executed (`artifacts/logs/e2e-baseline-153803.json`): trace → `sediment_batch --json`
→ draft in `<main checkout>/postmortems/inbox` → `verify_case_draft` → cell-view read
→ `--gate` → promote → `rebuild_generated --check` → restore generated files →
source-only branch → every PR gate → merge `--no-ff` → run the post-merge job body →
push main → retrieval check.

Notable readings:

- inbox resolved to `D:\...\e2e\postmortems\inbox` and the same absolute path from a
  second worktree (`inbox-race-153215.json`, step "shared inbox identical across
  worktrees?");
- `rebuild_generated --check` took ≈20 s and dirtied 4 generated artifacts;
- PR-side gates all `rc=0`; after the merge, the job produced
  `chore: rebuild generated views` (4 files) and `VLLM-ASC-90001` appeared in the
  class view, namespace view and master index;
- the case's `quickly_check.primary` regex matched a synthetic log line
  (`bfloat16 is not supported`).

So the baseline is not broken for a single contributor. The failures below need
concurrency, a crash, or a second interpretation of the same evidence.

---

## 2. Scenario 2 — two engineers, independent clones (`engineers-154251.json`)

Setup: `engA`, `engB` cloned from the same baseline, separate inboxes and traces.
A produced `90001` (`interrupt`); B produced `90002` (`precision`) for the **same root
cause**, with different symptom wording and a different discriminator. Both ran the
documented pre-triage against their own clone's index view and both concluded
`new_pattern`.

### 2.1 What the pre-triage can and cannot see (E3 precondition)

- B's own cell view `inference/vllm-ascend__precision.list` had 32 rows and did
  contain the token `310P` (from unrelated real cases), but **not** A's case ID —
  A's case lives in the `interrupt` cell and in a clone B never fetched.
- B's `_index.yaml` does not contain A's ID. No command makes B fetch or compare
  before grooming; `git fetch` is a discipline, not a step in the grooming procedure.

This is the documented two-phase retrieval (`CLAUDE.md` Tier 2) doing exactly what it
says: read the hit `(namespace × category)` view. A cross-category duplicate is
invisible **by construction**, not by accident.

### 2.2 Merge in both orders

Two integration clones were made from the same baseline before either order pushed:

| Order | Merge conflicts | Gate results after each merge | Both cases in the class views |
|---|---|---|---|
| A then B | 0 | all 7 gates `rc=0` | yes |
| B then A | 0 | all 7 gates `rc=0` | yes |

The two knowledge units are now both active. The `interrupt` cell and the `precision`
cell each contain one of them; a diagnosis that matches one will not necessarily
load the other (candidate cap is 5, and they live in different cells). The
duplicate is semantically obvious (same root cause, same fix, same 310P platform)
and mechanically invisible.

**E2 / E3 reproduced, both directions.**

### 2.3 Staleness of the pre-triage conclusion (E8)

B's conclusion was produced against the baseline. A merged afterwards. B's clone
still lacks A (`engineers-154251.json`, "stale-check"). The repository has no
merge-time recheck: after merging B, all gates are green and both IDs remain. The
proposal's command does not exist (`find_duplicates.py` run in the lab returns
`can't open file`).

---

## 3. Scenario 1 — two writers, one inbox (`inbox-race-153215.json`)

Precondition executed with repository code: `scripts/shared_dir.py inbox` resolves to
the **main checkout**, so two worktrees (two agent sessions) of one clone share one
queue. That is exactly the "shared local deployment" case.

### 3.1 Same-file concurrent writes

Writer = `Path.write_text` (the same open/write/close the agent's file tool performs).
Two threads synchronised on a barrier, 10 rounds, realistic draft size (~1.2 KB):

- 10/10 rounds: **exactly one** writer's content survived (0 rounds with both);
- 10/10 resulting files parsed as valid YAML — so the loss is **silent**: a subsequent
  structural check would pass;
- control: writes to different IDs both survive.

Sequential re-sedimentation with the same ID is even simpler: the second write
replaces the first; `to-postmortem/SKILL.md:131-136` only warns against re-running the
skill, not against a colliding ID from another engineer.

### 3.2 Large/chunked writes

3 rounds, two writers streaming 3 MB into the same file with flushes:

- 3/3 produced **mixed** content (both writers' markers present);
- 3/3 still parsed as YAML (the interleaving stayed inside a quoted scalar). The
  structural check then validates a single self-consistent-looking document; it cannot
  tell which writer any field came from. In this run the mixture happened to be
  incomplete (only `id`/`title` survived), so `verify_case_draft.py` rejected it on
  missing fields — that rejection does not restore the lost content, and with two
  complete drafts the surviving mixture can satisfy every structural rule while mixing
  fields from both writers.

### 3.3 Crashes

- Killed mid-write: a 35 KB truncated file remains; `verify_case_draft.py` returns 1
  (`YAML 解析失败`). Detection exists **only if someone runs the draft check**; the
  queue itself has no state, so a human/agent reading the queue sees a normal-looking
  file name.
- Half set: `case.yaml` complete, `postmortem.md` missing → `verify_case_draft.py`
  passes; nothing in groom requires the `.md`. The `README` prose says the pair is
  the output format; no check enforces it.

**E1 reproduced in three forms: silent overwrite, silent mixture, and a half-set that
looks complete.**

---

## 4. Same case ID / same path (E4, E5) — `engineers-154251.json`

A and B each created `VLLM-ASC-90003` at the same path with different root causes
(HCCL fixed-port reuse vs Mooncake `kv_port` clash):

- `git merge` → `CONFLICT (add/add)`, one conflicted file (the case YAML);
- resolving by `git checkout --ours` (the fastest "取一边" action):
  - B's root cause (`Mooncake` / `kv_port`) is **absent** from the merged file;
  - A's root cause is present;
- after resolving: `rebuild_generated --check` passes, `verify_case_draft --all`,
  `build_index --check`, `verify_references`, `verify_entry_activity`,
  `verify_metrics`, `holdout`, `eval_scorecard` **all pass**.

This is the exact failure mode the plan's §0 table lists as "仍在": the loss is not
detected by any check because every check asks whether the tree is self-consistent,
not whether a contribution disappeared. Only the Git conflict hinted that a judgement
was needed, and Git cannot force the judgement to be correct.

---

## 5. Clean merge, contradictory content (E6) — `engineers-154251.json`

A edited `compat.ranges` of `VLLM-ASC-90001` to `["==0.22.0", "==0.21.0"]`; B appended
a diagnosis step asserting "only 0.22.0 has this path". The edits are disjoint lines.

- merge: `rc=0`, **no conflict**; the resulting file contains both claims;
- gates: `verify_case_draft --all` `rc=0`, `build_index --check` `rc=0`, all others
  green;
- no check reads `compat` against the `diagnosis` prose, so the contradiction is
  invisible.

**E6 reproduced.** This is also the case where a "keep both versions" policy is not
enough: both versions are already present, and the result is wrong.

---

## 6. Generated artifacts (E7)

- With the current discipline (source-only PR), two concurrent knowledge PRs in the
  same or different cells produced **no generated-artifact conflicts**; the
  `generated-guard` passed on the source-only branch
  (`engineers-154251.json`, "E7 generated-guard on a source-only PR branch").
- A branch that carries `knowledge/_index.yaml` is rejected by
  `check_generated_untouched.py` (`rc=1`, repair command printed).
- The post-merge job, run locally with the workflow's exact body, commits the 4
  regenerated files. The public Actions API reports six runs in total for this
  workflow, and every run inspected (including the latest) succeeded; the history
  contains bot commits on `main`.

So **E7 is resolved for this deployment**, with two caveats that were executed:

1. on a deployment where the job does not run, main is stale and
   `build_index.py --check` is red while every semantic check is green
   (`engineers-154251.json`, "E7-nojob"); the failure is a missing index row, not a
   loud error;
2. the resolution is deployment-dependent, not repository-guaranteed (DEPLOY_KEY,
   ruleset bypass, Actions enabled).

Historical local evidence (`tests/test_concurrent_submit.py`) reproduces the old
generated-artifact conflicts when each contributor commits generated files; I ran it:
`same-ns before` = 6 generated conflicts, 2 judgement conflicts, gate red after three
merges; `same-ns after` (route-source union) = 0 judgement conflicts. That test's
"before" policy is the pre-job discipline, so it is a historical baseline, not the
current one.

---

## 7. ID changes: references, fixtures, usage records, traces (E9)

Setup (`id-metrics-154910.json`): a real usage row was produced by
`settle_trace_feedback.py --apply` for a case; a real reference cited the case; a
golden fixture pointed at it; then the case ID/file was renamed `90001 → 90001R`.

| Surface | After rename | Detection |
|---|---|---|
| case structure | green | `verify_case_draft --all` |
| index | green after rebuild | `build_index --check` |
| reference `sources[].cases` | **red** | `verify_references --check` (1 finding) |
| usage record `metrics/entry-activity.d/<week>.yaml` | **red** | `verify_entry_activity` (orphan ID) |
| golden fixture `case_id` | **warning only** | `eval_scorecard --check` (`待复核 1 条`, `rc=0`) |
| local trace `active_case` / `source_session` | still old ID | no CI (gitignored) |
| provenance | does not exist | — |
| generated index | rebuilt | green |

Then the duplicate case was deleted (the "merge" action): `rebuild_generated` passed,
but `verify_entry_activity` turned red for **both** orphan IDs — i.e. the counts are
lost/stranded, not migrated. `score_entries.py` gives the new ID only its prior.

A second variant (`provenance-161356.json`) **archives** the duplicate instead of
deleting it (`knowledge/_archive/...`): `verify_entry_activity` is **green**, the
generated artifact keeps counts under **both** IDs (`90001R` resolved=1 and `90002`
resolved=1), and `score_entries` sees 4 recorded cases. That is the semantic trap the
task asks about: referential integrity passes while the statistics double-count one
incident across two IDs (one of them archived).

**E9 reproduced**, with a distinction the plan does not make: the hard checks catch
references and usage rows; fixtures are advisory; traces/provenance are not checked
at all; and archival keeps the counts so the check stops complaining without the
numbers becoming right.

`scripts/rename_ref.py` (inspected, dry-run executed) rewrites path strings only; it
does not touch `id:` values, fixture `case_id`s, usage-record `id`s, or traces.
`verify_upstream_outcomes.py` keeps a cursor keyed by case ID and is not in CI; a
rename orphans that key silently (inspected, `scripts/verify_upstream_outcomes.py`,
cursor section).

---

## 8. Same-period metric snapshots (E10) — `id-metrics-154910.json`

Two "machines" (clones at the same main) each ran the real
`scripts/metrics_snapshot.py`:

- both chose `2026-W44-live-1028`;
- contents differed (`sessions_total` 2 vs 1); SHA-256 of the emitted YAML differed;
- `next_available_period` on each clone only sees its own file, so the collision is
  not prevented;
- merging the two branches → `CONFLICT (add/add)` on the same path;
- resolving by keeping one side → after the post-merge rebuild,
  `build_timeline.py --check` is green. `verify_metrics.py --check` is red, but only
  because the generator emits fields outside its whitelist/strength registry (E12) —
  it does **not** report that one period's reading disappeared. Nothing else does
  either.

**E10 reproduced**; the damage is silent after the conflict resolution.

---

## 9. Newly discovered issues

### E11 — an all-digit short SHA crashes the entry-activity generator

`settle_trace_feedback.py:286-287` writes `checkout` and `kb_rev` as plain YAML
scalars. A 7-character short SHA made only of digits (e.g. `8577483`) is read back as
an **integer**; `entry_activity.py:414` puts checkouts in a set and `:495` calls
`sorted()`. With one string SHA and one integer SHA in the same deployment, this
raises `TypeError: '<' not supported between instances of 'str' and 'int'`.

Reproduced deterministically (`e11-sha-type-154622.json`): mixed rows → crash; the
same rows with the numeric-looking SHA quoted → success. `verify_entry_activity`
passes on the crashing source rows, so the failure is only visible when the generator
runs. Since `build_entry_activity.py` is part of `rebuild_generated.py`, the
**post-merge job fails**, main stays stale, and no other CI job looks at it. The
probability of a short SHA being all digits is non-trivial (≈3.7 % for 7 hex chars if
uniform), so over a year of merges this is a real hazard.

### E12 — the metrics snapshot generator emits fields its own validator rejects

`metrics_snapshot.py --emit-yaml` output, placed in `metrics/timeline.d/` exactly as
`knowledge-groom/SKILL.md:118` instructs, fails `verify_metrics.py --check` with two
errors (executed in `int_snap`):

1. `live 字段超出白名单 ['external_record_violations_total']`;
2. six metrics present in the period lack a strength declaration in
   `metrics/gates.yaml` (`considered_candidates_events`,
   `external_record_violations_total`, `parallel_group_events`,
   `stop_reason_unrecorded`, `trace_record_violations_total`, `triage_miss_classes`).

So the weekly observability step is currently broken end-to-end: the human runs the
documented command, commits the period file, and CI reds on a field the generator
itself produced. This is independent of concurrency but directly damages the plan's
"observability" leg.

### E13 — the repository claims protection it does not have

`docs/guide/git-workflow.md:16` says protection is not enabled. The API shows an
active ruleset that requires a PR but **0 approvals, no code-owner review, no required
status checks, no up-to-date requirement**. This is not a code bug, but every plan
step that says "评审时核对" or "合入前复核" currently has no enforcement: the author
can merge their own PR with red CI and a stale branch. This is the precondition that
makes E8/Checkpoint C unable to protect anything.

### E14 — the draft queue has no reader contract

The plan introduces `DONE`; the current queue has no equivalent. Executed
consequences: a half-set passes the only draft check; a killed writer leaves a file
that is only caught if someone runs the check; a chunked interleaving parses as YAML
and therefore cannot be distinguished from a single writer's document by structure
alone. Any new protocol must define the **reader** (which states are consumable), not
only the **writer**.

---

## 10. Issue-by-issue assessment

Severity: S1 = silent knowledge/evidence loss, S2 = wrong statistics or wrong merge,
S3 = friction. Likelihood is for a team of ≥2 engineers contributing weekly.

| ID | Precondition | Reproduced | Detected by existing checks | Damage state | Severity / likelihood |
|---|---|---|---|---|---|
| E1 | same case ID proposed in one clone (two worktrees/sessions) | yes, 10/10 silent; 3/3 mixed | no (the surviving file is valid YAML; loss invisible) | prevented: no; detected: only parse errors | S1 / high |
| E2 | two clones, same problem, different IDs | yes, both merge orders | no | prevented: no; detected: no | S1 / high |
| E3 | duplicates in different categories/namespaces | yes (pre-triage reads one cell) | no | prevented: no; detected: no | S1 / high |
| E4 | same case ID/path, different content | yes (add/add conflict) | Git only | prevented: no; detected: Git conflict | S2 / medium |
| E5 | resolve a case conflict by keeping one side | yes, B's content gone, gates green | no | prevented: no; detected: no; recoverable only from the branch | S1 / high |
| E6 | disjoint-field edits to one case | yes, clean merge, gates green | no | prevented: no; detected: no | S1 / high |
| E7 | concurrent knowledge PRs | generated conflicts: none now; guard works; no-job deployment goes stale | guard + index-freshness per-PR | prevented: yes (this deployment); deployment-dependent | S3 / low here, S2 without job |
| E8 | A merges after B's pre-triage | yes, both cases remain, gates green | no | prevented: no; detected: no | S1 / high |
| E9 | rename/merge/delete a case ID | yes | refs + usage hard; fixtures warn; traces/provenance unchecked | prevented: no; detected: partially | S1 / medium |
| E10 | two machines, same day, live snapshot | yes | Git conflict only; after resolution nothing | prevented: no; detected: no | S2 / medium |
| E11 | one all-digit short SHA + one string SHA in usage rows | yes (crash) | validator passes; generator crashes | prevented: no; detected: at generation time, only if it runs | S2 / low-medium |
| E12 | run the documented weekly snapshot step | yes | CI reds on generator output | prevented: no; detected: yes (after commit) | S2 / certain until fixed |
| E13 | PR with red CI / stale branch | API facts | ruleset | prevented: no | S1 / high (governance) |
| E14 | crash or half-write in inbox | yes | parse errors only | prevented: no; detected: partially | S1 / high |

Reproduction commands and full transcripts: `artifacts/logs/` (`e2e-baseline-*`,
`engineers-*`, `inbox-race-*`, `id-metrics-*`, `e11-sha-type-*`), plus the test
scripts in `artifacts/scripts/`.
