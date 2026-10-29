# 01 — Current production workflow (as implemented)

Validation date: 2026-10-28/29 (Asia/Shanghai).
Baseline under test: local `main` = `28adab0d1db1f00989b5416dfeaf8206df71ca4a`
(`origin` = `git@github.com:pillumina/ascend-sleuth.git`; the upstream `main` had
already advanced to `dd3e6b33ff06affe7443fdf29c21d1e1a2edf139`, PR #378, while this
validation ran). Every experiment started from the baseline commit.

Environment: Windows 11, Python 3.12.2, PyYAML 6.0.3, git 2.45.1, Node 25.9.0.
`gh` CLI is **not installed**, so GitHub checks below were read from the public API
and from repository configuration, not exercised through `gh`.

This document separates four kinds of statements:

- **executed** — a command in this repository was run and its output recorded;
- **inspected** — code/config/docs were read (with `file:line`);
- **simulated** — a GitHub-side behaviour was reproduced locally by running the same
  script the workflow runs (never by calling GitHub);
- **proposed** — the unified plan, not implemented.

---

## 1. Repository and Git state

| Fact | Value | Evidence |
|---|---|---|
| Local `main` | `28adab0` | `git rev-parse HEAD` |
| Upstream `main` at validation time | `dd3e6b3` (PR #378) | GitHub API `branches/main` |
| Remotes | `origin` = pillumina/ascend-sleuth, `fork` = stfdtj/ascend-sleuth | `git remote -v` |
| Existing worktrees | 2 additional (`kb/preload-panel-desktop`, `pr-366`) | `git worktree list` |
| Generated artifacts in git | 6 files + 15 index views + 3 procedure shards + 1 entry-activity file | `scripts/generated_plane.py:12-25` |
| KB scale | 171 active cases, 166 postmortems, 273 references, 28 golden fixtures, 11 sealed holdout entries, 8 timeline periods | counted at baseline |
| Traces | `traces/` empty (gitignored runtime) | `Get-ChildItem traces` |

**Branch protection (executed against the public API, not local scripts).** The
repository has an active ruleset `main-protection` (id 25950697, created
2026-10-27). Its rules are: `deletion`, `non_fast_forward`, and `pull_request` with
`required_approving_review_count: 0`, `require_code_owner_review: false`, and **no
required status checks and no "branch up to date" rule**. The legacy branch
protection object is `protected: true` but `protection.enabled: false`
(`api.github.com/repos/pillumina/ascend-sleuth/branches/main`). Practical meaning:
direct pushes/deletions are blocked, a PR is required, and **nothing else is**. A PR
with zero approvals and red CI can be merged; a stale branch can be merged.

This contradicts `docs/guide/git-workflow.md:16` ("当前仓库尚未开启") in one
direction (protection now exists) and the plan's "平台配置" suggestion in the other
(no approvals, no required checks). It is the single most important fact for
Checkpoint C: a locally produced report cannot be enforced by the platform today.

**Generated-artifact rebuild on main (executed via public API).** The workflow
`rebuild-generated` runs on `push` to `main` with `contents: write` and pushes a bot
commit when the tree is dirty (` .github/workflows/rebuild-generated.yml:13-29,57-87`).
The GitHub Actions API reports six runs in total for this workflow; every run inspected
(including the latest, for `dd3e6b3`, 2026-10-28T13:56Z) is `success`, and the history
contains a bot commit `057c9cc` "chore: rebuild generated views". So the plan's claim
"generated artifacts are rebuilt on main" is **true for this deployment** (as of
2026-10-28; six runs is the whole history, so this is a recent, thin sample). It is not
a repository invariant: it depends on the `DEPLOY_KEY` secret, the key bypassing the
ruleset, Actions being enabled, and the merged paths matching the workflow's `paths:`
list. `docs/guide/git-workflow.md:10-12` documents the DEPLOY_KEY requirement;
`rebuild-generated.yml:86-87` fails loudly when the push is rejected.

## 2. The three loops and their real entry points

The repository's own framing (`CLAUDE.md`) is three loops. What actually executes:

| Loop | Entry | Executable? | Human/agent judgement | External dependency |
|---|---|---|---|---|
| Diagnosis | `skills/diagnose/SKILL.md` | Agent procedure; no single command | All routing, candidate verification, fix choice | none (engineer pastes evidence) |
| Sedimentation | `skills/to-postmortem/SKILL.md`, `skills/issue-ingest/SKILL.md` | Agent procedure + `scripts/verify_case_draft.py` | Extract symptoms/root cause/fix; namespace; `novelty`; `verification` | none |
| Grooming | `skills/knowledge-groom/SKILL.md` | Agent procedure + a dozen scripts | pre-triage accept/adjust/reject, promotion, high-risk sign-off | none |
| Git/PR | `docs/guide/git-workflow.md` | `git`, `scripts/check_generated_untouched.py`, CI scripts | template choice, review, merge | GitHub (ruleset, Actions, secrets) |

Commands that really exist and were executed somewhere in this validation:
`scripts/shared_dir.py`, `scripts/sediment_batch.py`, `scripts/verify_case_draft.py`
(+`--gate`, `--all`), `scripts/rebuild_generated.py` (+`--check`),
`scripts/build_index.py --check`, `scripts/build_triage_tree.py --check-sources
--check-coverage`, `scripts/verify_references.py --check`,
`scripts/verify_entry_activity.py`, `scripts/verify_metrics.py --check`,
`scripts/holdout.py --check`, `scripts/eval_scorecard.py --check/--build`,
`scripts/check_generated_untouched.py`, `scripts/verify_pr_body.py`,
`scripts/settle_trace_feedback.py`, `scripts/build_entry_activity.py`,
`scripts/metrics_snapshot.py`, `scripts/score_entries.py`,
`scripts/rename_ref.py`.

Commands the task description implies but that **do not exist**:
`scripts/inbox_put.py`, `scripts/find_duplicates.py`, `scripts/merge_recheck.py`,
`scripts/verify_provenance.py`. Nothing in `scripts/`, `.github/workflows/`,
`skills/` references a repository-wide duplicate scan or a merge-time recheck
(`git grep` in the lab; see `artifacts/logs/engineers-*.json`, step
"repository-wide duplicate-check ... implementation present?").

## 3. Input → diagnosis → draft

### 3.1 Diagnosis trace

Each diagnosis appends to `traces/<session_id>.yaml`. Schema is
`skills/diagnose/references/diagnosis-trace.md`; the event list is the top-level
`trace:` key (not `events:`), `feedback: {case, outcome, confirmed_at}` and
`sedimented: {state, case_id, inbox_path}` are top-level. `traces/` is gitignored and
**anchored to the main checkout**: `scripts/shared_dir.py --list` shows
`traces → <main checkout>/traces`, and `scripts/exec_log_path.py:204-211` is the
resolver. Consequence executed in the lab: two worktrees of one clone see the same
traces and the same inbox; two clones do not.

There is no command that *creates* a diagnosis; it is an agent conversation. For the
E2E run I produced a schema-compatible trace by hand and then ran the repository's
own reader:

- executed: `scripts/sediment_batch.py --json` listed the session as actionable
  (`actionable: ["session:2026-10-28-conc-a01"]`), reading `status`, `report_file`,
  `sediment_candidates` (log `e2e-baseline-153803.json`).

### 3.2 Sedimentation (draft creation)

`skills/to-postmortem/SKILL.md:123-138` is the authoritative output spec:

- resolve the inbox with `python scripts/shared_dir.py inbox` (main checkout);
- write `postmortems/inbox/<case-id>.md` and `postmortems/inbox/<case-id>.case.yaml`;
- the case YAML is the same shape as a knowledge case (`cases:` list);
- run `scripts/verify_case_draft.py <draft>` (the only deterministic check while a
  draft is in the inbox);
- write back `sedimented.state: submitted` on the source trace.

There is **no atomic write, no unique draft directory, no completion marker** in the
current implementation. The naming key is the case ID, which the draft itself
proposes. Two agents that propose the same case ID write the same two paths.
`postmortems/inbox/README.md:1-10` calls the directory a queue; nothing in it enforces
queue semantics.

### 3.3 Reference sedimentation

`skills/to-reference/SKILL.md` writes `references/**` with `status: active` directly;
PR review is the gate. `scripts/verify_references.py --check` validates schema,
`ref_knowledge` targets, and case citations. This path was inspected, not exercised
end-to-end (no reference was promoted in the E2E run).

## 4. Grooming: pre-triage, gates, promotion

`skills/knowledge-groom/SKILL.md` (executed in the lab as the documented procedure,
with the agent's judgement performed by the lab script):

1. read the inbox (group dirs first in the plan; today only flat files);
2. per draft, pre-triage `new_pattern` / `variant_of` / `covered_by` using **only**
   the `(namespace × category)` read-side view (`knowledge/_index/<ns>__<category>.list`,
   `skills/knowledge-groom/SKILL.md:60-62`); category undetermined falls back to the
   namespace view;
3. for `new_pattern`, run `verify_case_draft.py --gate <draft>
   --root <repo>` (`skills/knowledge-groom/SKILL.md:67-71`);
4. promote by copying the case body into `knowledge/<workload>/<framework>/<category>/<id>.yaml`;
5. run `rebuild_generated.py --check` for a local preview; on an auto-deployment the
   PR does not carry generated files (`skills/knowledge-groom/SKILL.md:116`);
6. high-risk changes (new `common/` record, `expected`, `fix_on_mismatch`, `compat`,
   `score_override`) require two owner signatures
   (`skills/knowledge-groom/SKILL.md:173-181`);
7. a weekly snapshot via `metrics_snapshot.py` (`:118`).

The gate is real and was executed: it passed a no-hit, `status: resolved` trace and
printed `升格闸门：通过 1 · 需双签 0 · 拦下 0 · 跳过 0`
(`e2e-baseline-153803.json`). The gate checks **structural validity plus trace
closure**, not semantic quality, and it only runs for drafts the groomer chose to
promote.

`build_index.py` enforces three identity rules (`scripts/build_index.py:494-500`,
`:578-614`):

- case ID unique across the library;
- file stem equals case ID;
- directory category equals the case's `category` field.

It does not compare two different IDs' content. `verify_case_draft.py:53-54` lists
nine required fields and three enums; `ref_knowledge` targets must exist and be
`active` (`:156-166`). References must cite existing cases
(`scripts/verify_references.py:115-181`).

## 5. Generated artifacts and the PR plane

Generated (tracked) artifacts: `knowledge/_index.yaml`, `knowledge/_index/*.list`,
`triage-tree.yaml`, `references/_summary-index.yaml`,
`references/_procedure-index.yaml` + shards, `references/errors/_code-gaps.yaml`,
`metrics/timeline.yaml`, `metrics/entry-activity/` (`scripts/generated_plane.py:12-25`).
`scripts/rebuild_generated.py:28-48` runs seven generators and nine checks.

Current discipline (executed): a source-only PR passes
`check_generated_untouched.py --base origin/main` (`生成物未改动`); a branch that
touches `knowledge/_index.yaml` is rejected with a repair command
(`artifacts/logs/engineers-*.json`, E7 steps). The merge-time job is simulated
locally by running the exact job body (`rebuild_generated.py --check`, then commit
`chore: rebuild generated views` if dirty, then push) — it produced a 4-file generated
commit, matching the shape of the real bot commit in the public history.

If the job does not run (no `DEPLOY_KEY`, rejected push, Actions disabled), main is
silently stale: executed in the lab, after merging a new case without the job,
`build_index.py --check` is **red** (3 missing rows) while `verify_case_draft --all`
is still green, and no other check on main looks at index freshness
(`artifacts/logs/engineers-*.json`, E7-nojob). The next diagnosis will simply not see
the new case.

## 6. CI: what is checked, and what is not

`.github/workflows/kb-checks.yml` runs 14 jobs with per-area `if:` conditions;
`pr-template.yml` runs `verify_pr_body.py` on every PR.

| Job | Command(s) | Checks |
|---|---|---|
| `changes` | shell | which areas changed (9 booleans); degrades to "all" |
| `generated-guard` | `check_generated_untouched.py --base origin/$BASE_REF` | PR must not hand-edit generated files |
| `index-freshness` | rebuild action, `build_index.py --check`, `build_triage_tree.py --check-sources/--check-coverage` | index coverage, route sources/aggregate |
| `case-structure` | `verify_case_draft.py --all`, `score_entries.py --check-overrides` | case fields/enums/refs, override reasons |
| `reference-validation` | `verify_references.py --check`, three index checks | reference schema/citations |
| `metrics-validation` | `verify_metrics.py --check`, `build_timeline.py --check`, `verify_entry_activity.py`, `build_entry_activity.py --check` | metrics structure, timeline source↔generator, usage rows |
| `proposal-audit` | `verify_proposals.py --check` | EV cards |
| `docs-index` | `build_docs_index.py --check` | docs manifest |
| `holdout-integrity` | `holdout.py --check` + label gate | sealed fixture bytes |
| `eval-scorecard` | `eval_scorecard.py --check`, workload-type coverage | fixture ledger, stale fixtures are warnings |
| `unit-tests` | `python3 -m unittest discover tests` | scripts' unit tests |
| `panel-checks` | 8 node/python checks | panel rendering/bundles |
| `skill-self-contained` | greps | skills contain no ADR/date/card numbers |
| `pr-template` | `verify_pr_body.py` | required `## ` headings only |

What no job checks (verified by running the commands, not only by reading):
different IDs with identical meaning; duplicated content across paths; that a
duplicate-check conclusion is still valid; that a conflict resolution preserved both
sides; that a renamed case's historical counts follow it; that a metrics period is
missing; that a PR body's quoted commit SHAs match the branch.

`verify_pr_body.py:41-67` only detects a template and required headings; checkbox
contents and SHAs are not validated.

## 7. Metrics, traces, provenance

- Usage records: source `metrics/entry-activity.d/<week>.yaml`, one self-contained row
  per `(run, kind, id)`; generated view `metrics/entry-activity/<deployment>.yaml`
  (`scripts/entry_activity.py:99-106,405-418`). Rows are keyed by case ID.
- Timeline: source `metrics/timeline.d/<period>.yaml`, generated
  `metrics/timeline.yaml`; `build_timeline.py` rejects `period ≠ filename`, duplicate
  periods, conflict markers (`scripts/build_timeline.py:52-101`).
- Period allocation is **local**: `metrics_snapshot.next_available_period`
  (`scripts/metrics_snapshot.py:181-207`) scans only the current checkout; the live
  base is `f"{week}-live-{MMDD}"` (`:254`).
- Provenance: does not exist. `postmortems/` stores postmortems only; no
  `*.provenance.yaml` anywhere; `git grep "provenance.yaml|verify_provenance"` over
  `scripts/`, `.github/workflows`, `docs/guide` returns nothing.
- Local traces have no CI coverage (gitignored, by design).

## 8. What the E2E run executed vs what was only inspected

Executed end-to-end in a disposable clone (`D:\working\asv\e2e`, from `28adab0`):

1. wrote a schema-compatible trace; `sediment_batch.py` listed it;
2. resolved the inbox with `shared_dir.py`; wrote the two flat draft files;
3. `verify_case_draft.py` on the draft (pass);
4. read the cell view; `verify_case_draft.py --gate` (pass);
5. promoted the case; `rebuild_generated.py --check` (pass; generated files dirty);
6. restored generated files, committed source-only branch, pushed;
7. ran every PR gate listed above (all pass);
8. merged with `--no-ff`; ran the post-merge job body; pushed main;
9. verified retrieval: case ID appears in class view, namespace view and master index;
10. ran the `quickly_check` keyword scan against a synthetic log (match).

Inspected only, not executed: reference promotion; `issue-ingest` (no `gh`); the
panel (`dsh-plugins/*` require Node/DSh host); GitHub's own CI; branch-protection
enforcement; any customer environment.

## 9. Implemented / documented / proposed

| Capability | Actual status | Evidence |
|---|---|---|
| Diagnosis trace + shared dirs | implemented | `exec_log_path.py`, `shared_dir.py` |
| Flat drafts + case-ID naming | implemented | `to-postmortem/SKILL.md:123-138` |
| Draft gate (structure + closure) | implemented | `verify_case_draft.py` |
| Per-cell pre-triage (index view) | implemented (procedure) | `knowledge-groom/SKILL.md:60-62` |
| Repository-wide duplicate candidates | **absent** | `git grep` in lab |
| Merge-time recheck | **absent** | `git grep` in lab |
| Generated artifacts via main job | implemented and working | workflow + 6 successful runs |
| Generated guard | implemented | `kb-checks.yml:144-158` |
| Rename-aware references / usage / fixtures | partially: refs+usage hard, fixtures warn | `verify_references.py:178`, `verify_entry_activity.py:104`, `eval_scorecard.py:252` |
| Provenance sidecar | **absent** | no files, no code |
| Draft directory/DONE/hash protocol | **absent** | no `inbox_put.py` |
| Merge enforcement (approvals/checks) | **absent** | ruleset with 0 approvals, no required checks |

The plan is therefore not a description of the current system. It proposes four new
scripts, two skill rewrites, two panel implementations, template fields, and a
platform configuration. Stage I below measures what the current system does when two
engineers use it as documented.
