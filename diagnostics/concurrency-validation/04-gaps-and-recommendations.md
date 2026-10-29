# 04 — Gaps, incorrect assumptions, and recommendations

This is an adversarial read of the unified plan against the measured system. It is
not a defence of the proposal. "Prevents" means the failure was reproduced in Stage I
and the change addresses the reproduced mechanism; "tradeoff" is what the change costs.

---

## 1. Missing protections (ordered by damage per unit of effort)

### P0 — required before calling the workflow concurrency-safe

**1. Make the platform enforce something.**
The active ruleset requires a PR but has 0 approvals, no required status checks and no
up-to-date rule (public API, 2026-10-28). Consequences already measured: a stale
branch merges (C8), a PR body with old SHAs passes `verify_pr_body`, and a red
`merge_recheck` would not block anything.

Do: require status checks for `changes`, `generated-guard`, `case-structure`,
`reference-validation`, `metrics-validation`, `index-freshness`, `pr-template`;
require ≥1 non-author approval; require branches to be up to date or enable a merge
queue; add the `DEPLOY_KEY` bypass for the rebuild job and document it.
**Prevents:** E8 and the whole "recheck is advisory" problem; also E5/E6 (a second
reader sees the conflict before merge).
**Tradeoff:** every PR re-runs on update (minutes), a second person becomes a
bottleneck at low volume, and the admin must maintain bypasses. Without this, the rest
of C is theatre.

**2. Fix the two data-plane defects (E11, E12).**
- E11: quote or stringify `checkout`/`kb_rev` in `settle_trace_feedback.py:286-287`
  (and coerce in `entry_activity.py:414`), add a regression test with an all-digit
  SHA. Prevented: the post-merge rebuild job crashing, leaving main stale.
- E12: align `metrics_snapshot.py`'s emitted fields with `verify_metrics.py`'s
  whitelist and `metrics/gates.yaml`'s strength registry (or make the validator accept
  them and declare strengths). Prevented: the documented weekly step cannot pass CI.
**Tradeoff:** small; choosing "accept + declare" adds six metric strengths that must
be maintained.

**3. Detect a missing post-merge rebuild.**
The workflow is empirically working (six runs in total; the runs inspected, including
the latest, succeeded), but it can fail silently from the repository's point of view
(missing DEPLOY_KEY, rejected push, Actions off). Add a scheduled job (or a check on
the next PR's base) that runs `build_index.py --check` on main and opens an issue if
red. **Prevents:** "new case invisible to diagnosis with no error" (E7-nojob).
**Tradeoff:** one more job and a known failure mode to triage.

**4. Draft write protocol with a reader contract.**
`inbox_put.py new/finish/list/abort` + `DONE` + hashes, plus an explicit reader state
machine (`complete`/`incomplete`/`corrupt`) used by groom, the panel (both copies) and
the duplicate finder. Add a **random `deployment.id`** generated once in
`deployment.yaml`; never derive identity from the checkout path/name.
**Prevents:** E1/E14 (silent overwrite, mixture, half set), and the "same
(deployment, draft_id)" collision.
**Tradeoff:** two commands per sedimentation; weekly reporting of incomplete dirs;
panel work in two codebases; old flat drafts need a compatibility path.

### P1 — before scaling to more than one contributor

**5. A duplicate candidate report with a narrow, explainable rule set.**
Ship rules 1–3 (shared source, same ID, same path) as **always shown**, rule 4
(same-cell lexical) as capped with an explicit unshown count, and the five structural
contradiction hints. Drop whole-library keyword nomination (rule 6) initially: it
added 78 unshown pairs in a small sample and no unique must-surface pair.
**Prevents:** E2/E3 for pairs that share a source or keyword overlap (9/10 generated in
the test). **Tradeoff:** paraphrased duplicates still miss (D2); reviewers see 20+
pairs per groom; the tool must never be described as "no duplicates".

**6. A merge recheck bound to the final head, as a required check.**
`merge_recheck.py --base origin/main --head $HEAD` with a non-zero exit on
`same-path-add`, `both-modified-same-case`, `stale-report`, plus a machine-readable
decision file keyed by the three SHAs. For same-case edits, produce a **field-level
diff of the two versions** (the plan's "call six-axis" does not define this).
**Prevents:** E8 (stale conclusion), partly E5/E6 (forces a decision record, not a
correct one). **Tradeoff:** re-run after every rebase; the decision file adds a step
per PR.

**7. Minimal, checkable provenance + an ID-change command.**
Keep `materials[]` with `deployment.id`, `draft_id`, file hashes; `dropped[]` with a
destination path that must exist; `supersedes` / `merged_into` links in both
directions; `verification[].event` must resolve to a trace/usage event id.
Add `scripts/rename_case.py` that moves the file, rewrites `id:`, `ref_knowledge`/
reference citations, fixture `case_id`s, usage rows, traces (best effort) and
provenance, and prints a mapping. **Prevents:** E9, E5 recovery gaps, E10 attribution.
**Tradeoff:** requires schema decisions (deployment id, event id) and a migration of
existing cases (can start with new cases only, as the plan says, but the checker must
not pretend old cases are covered).

### P2 — measurement, after the data exists

**8. Structured decision record + labelled set.**
Add a small YAML/JSON block to the two knowledge PR templates (candidate pairs,
decision, main SHA) and have `verify_pr_body.py` require its presence (not its truth).
Create a 30–50 pair labelled duplicate/non-duplicate set in `eval/` (not holdout).
**Prevents:** the observability metrics being unfalsifiable narratives.
**Tradeoff:** review minutes per PR; labels rot and need maintenance.

**9. One inbox reader, one panel.** Factor the draft reader into one module (Python
CLI + JSON) and have both Node plugins call the same data shape (or ship one plugin).
**Prevents:** new drafts invisible in one panel (a change that the plan already
identifies as a risk). **Tradeoff:** refactor of an area that is currently duplicated;
test cost in `panel_render_check.js`.

**10. Case-file semantic contradictions: do not build a CI gate.** The plan correctly
refuses to judge semantics in CI. Instead, require the recheck's decision record for
PRs that touch an existing case. Do not add "same expected + different fix" as a hard
CI failure: it would block legitimate condition-specific fixes (the test's D8 is a
correct fix under a different condition).

---

## 2. Incorrect or unverified assumptions in the plan

| Assumption in the plan | What the experiments show |
|---|---|
| Generated-artifact conflicts "基本消失" and are rebuilt on main | True for this deployment (six runs in total, inspected runs successful, bot commit); false as a repository guarantee. Without the job, main is stale and `build_index --check` is red (executed). The plan treats this as solved; it is solved *conditionally*. |
| `deployment + draft_id` identifies a draft globally | False with a human-chosen/deployment-config id: two clones with the same id produce the same pair; renaming the checkout changes the fallback label. Needs a random id created once. |
| The six axes' data sources contain enough to compare | Source unknown for ~30 % of cases; evidence ("same verification event") is not representable (no event ids; `source_session` on 1/173); fix/root exist twice in a draft (`case` vs `semantic_summary`). |
| "对双方都碰到的 case，调用检查点 B 的六轴比较" | Undefined: B compares two records; comparing two versions of the same case is a field-level diff. The prototype can only say "both touched". |
| Cross-category duplicates will appear in the candidate table | Generated yes (D1), displayed no at the cap; a paraphrased duplicate is not generated at all (D2). |
| The report's three commit SHAs make staleness detectable | Detectable, not enforced. The platform accepts a PR with red/absent checks and 0 approvals; `verify_pr_body` accepts old SHAs. |
| Monthly metrics can be calculated from existing records | None of the five metrics is computable today; two of the data-plane pieces are broken (E11, E12), and reviewer decisions do not exist. |
| 12–20 engineering days | 20–30 plus platform/governance, because of the two panel implementations, the labelled set, the reader contract in every consumer, and the enforcement work (see §3 of report 03). |
| A merge is a clean "materials → one case" operation | Archiving the duplicate keeps both usage rows and passes `verify_entry_activity`; the counts do not transfer. Merging is a statistical event, not only an edit. |
| "Docs say protection is not enabled" | Protection now exists (ruleset, 2026-10-27) but is weaker than the workflow docs assume: no approvals, no required checks. Every plan step that says "review checks the report" currently has no mechanism. |

---

## 3. Unnecessary complexity / architecture weaknesses

1. **A parallel comparator.** B re-implements tokenisation, range parsing and platform
   matching. The index already extracts `sig`/`tok` (`build_index.py`). Reusing them
   avoids two thresholds drifting apart.
2. **Whole-library keyword nomination.** Produces most of the volume and none of the
   unique hits in this sample. Keep it behind a flag for audits.
3. **Provenance as free text.** Fields like `fields_dropped` and `independent` are
   narratives that no check can falsify. Machine-checkable facts are: material exists,
   hash matches, destination exists, links resolve.
4. **Identity is spread over path, filename, `id`, namespace and category.** Renaming
   is an operation but not an event; no log, no redirect, no history. This is the root
   cause behind E9/E10 and the `next_on_fail`/fixture/usage gaps.
5. **The draft queue is a mutable directory with no state.** Any protocol must define
   its readers, not only its writer; otherwise "no DONE" is just another filename.
6. **Deployment shape is prose, not data.** Whether the post-merge job exists is
   documented in `docs/guide/git-workflow.md` but not declared in `deployment.yaml`;
   scripts cannot adapt (e.g. `rebuild_generated --sync` vs job). Add
   `generated.plane: auto|manual` and `deployment.id` to `deployment.yaml`.
7. **Two sources of truth for the same case content** in the draft (`case.yaml` vs
   `sources.yaml.semantic_summary`). Pick the case as authoritative and use the summary
   only for matching, or detect divergence.
8. **CI is advisory under the current ruleset.** Every "reviewer checks X" claim must
   be read as a convention; the repository's own docs already say this
   (`docs/guide/git-workflow.md:236-252`), but the plan's acceptance criteria drift
   toward "the check protects".

---

## 4. Migration problems

| Change | Migration issue | Recommendation |
|---|---|---|
| Group drafts + `DONE` | existing flat drafts have no sources/DONE; reader precedence and double-counting (same case in both formats) | read flat as legacy forever; never convert in place; groom reports which format each came from |
| `deployment.id` | old drafts/provenance have none; fallback labels differ | backfill only for open drafts; treat missing as `unknown` and refuse to merge provenance without an id |
| Provenance file naming tied to case ID | rename leaves an orphan; no tool moves it | name sidecars by `case_id` + a stable material id, or require the rename tool to move them |
| PR template new sections | `verify_pr_body.REQUIRED_SECTIONS` becomes stricter; old/open PRs and external contributors break | add sections as optional in the first release, require them after one release; keep the heading check separate from content |
| CODEOWNERS / approvals | `CODEOWNERS.example` is a placeholder; enabling required approvals now would block merges | name owners first; then enable 1 approval + non-author; keep the bot bypass |
| Metrics period naming | suffixing with deployment changes the live-period regex and existing files | add deployment to the suffix, update `verify_metrics.LIVE_PERIOD_RE`, add a gap check |
| Duplicate labels for evaluation | `eval/holdout.yaml` is sealed by hash; adding duplicate pairs there would force reseals | keep the duplicate labelled set outside holdout, e.g. `eval/duplicates/` with its own ledger |

---

## 5. Operational risks and mitigations

| Risk | Signal | Mitigation |
|---|---|---|
| The post-merge job fails and nobody notices | main's index is red but no CI runs on push | scheduled freshness check + issue; declare `generated.plane` in deployment.yaml |
| Reviewer fatigue from candidate volume | 101 pairs / 11 drafts, 78 unshown | always-show only shared source/id/path; cap lexical pairs; print unshown; review time budget |
| Alert fatigue on incomplete drafts | weekly count grows | age threshold + ownership; abort tool; don't auto-delete |
| Two panels drift | one shows new drafts, one doesn't | one reader, or a shared JSON contract; add a fixture to `panel_render_check` |
| Required checks block an urgent fix | author cannot merge | documented admin bypass; keep `kb/high-risk` separate |
| E11 recurs on a random shorter SHA | job failure with a TypeError | quote SHAs; add a unit test with an all-digit SHA |
| Weekly snapshot fails CI | `metrics-validation` red after following the docs | E12 fix; add the snapshot command to the same test that validates the emitted YAML |
| Renamed case's counts silently stranded | `verify_entry_activity` red (delete) or green (archive) with wrong numbers | `rename_case.py` + provenance link + "counts moved" decision; never sum two IDs |
| Merge with stale branch | no rule requires up-to-date | merge queue / up-to-date rule |

---

## 6. Recommended implementation order (smallest safe set)

1. **Week 1 — platform + defects (P0.1–P0.3).** Ruleset: required checks, 1 non-author
   approval, up-to-date/merge queue, DEPLOY_KEY bypass. Fix E11/E12 with tests.
   Add the main-freshness detector. No new knowledge machinery.
2. **Week 2 — draft protocol (P0.4).** `deployment.id`, `inbox_put.py`, strict reader,
   one skill rewrite (`to-postmortem`), groom reads both formats, both panels. Acceptance:
   the 13 prototype tests plus a two-worktree live test with a killed writer.
3. **Week 3–4 — duplicate candidates (P1.5).** Narrow rules; JSON + report; always-show
   set; thresholds from the labelled set; wire into groom's batch summary and the
   knowledge_intake template (as an optional block first).
4. **Week 5 — merge recheck (P1.6).** Exit codes, same-case field diff, decision file,
   required check binding the final head. Acceptance: C8 must fail the check, not just
   report stale.
5. **Week 6 — provenance + rename (P1.7).** Minimal checkable schema; `rename_case.py`;
   run on new/merged cases only; old cases marked `legacy: true`.
6. **After one quarter — observability (P2.8).** Decision record + labelled set, then
   compute the five metrics on real data; until then, publish no production numbers.

Do **not** ship: a full six-axis comparator as a gate, automatic merges, whole-library
keyword scanning as a default, union merge for case files, or provenance prose without
a checker. Do keep: human decides, machine nominates, shared-source always shown, no
semantic CI failure, generated artifacts on main.

## 7. What to keep from the plan

- The checkpoint framing (A/B/C) matches where the measured failures happen and is a
  good vocabulary.
- "Machine nominates, human decides" is the right split; my prototype's hints never
  assert duplication.
- "Always show shared source / same ID / same path" is the single highest-value rule
  (it is the only one that surfaced D4/D5 and the real 10303 case).
- "Do not add `merge=union` to nested case YAML" is correct: a row-level union cannot
  preserve field relationships.
- "Do not judge root cause with a model in CI" is correct: the tested contradictions
  (E6) are invisible to string checks and require a reader.

The proposal's direction is sound; its weakest link is not the algorithms but the
assumption that a report changes behaviour. In this repository, only a required check
plus an up-to-date rule changes behaviour.
