# 03 — Proposed solution validation (Stage II)

Prototypes and tests are in `artifacts/proto/` and `artifacts/scripts/`; they are
narrow proofs of concept, not product code, and they were run against disposable
clones. Classification used below: **PASS** (executed, required behaviour shown within
the tested scope), **PARTIAL**, **FAIL** (a reproduced case where the claimed
protection does not hold), **UNTESTED**, **NOT APPLICABLE**.

Summary:

| Mechanism | Verdict | One-line reason |
|---|---|---|
| A — draft directory + DONE + hashes | **PARTIAL** (mechanism PASS, integration/identity PARTIAL) | exclusive create and strict reader work; `(deployment, draft_id)` is not a global key, re-finish legitimises edits, Checkpoint B ignores DONE |
| B — six-axis candidate discovery | **PARTIAL** | 9/10 must-surface pairs generated, 6/10 displayed at the cap; a paraphrased duplicate is missed; two axes are starved of data |
| C — merge-time recheck | **FAIL as protection / PARTIAL as a report** | detects overlap and stale SHAs, but nothing enforces it; the platform lets the author merge anyway; same-case two-version comparison is not implemented |
| Provenance | **PARTIAL** | material-level attribution works; field-level, discarded-path, independence and rename linkage are unchecked |
| Observability | **FAIL (not computable today)** | none of the five monthly metrics has a complete data source; two generator/validator defects block the data plane |

---

## 1. Checkpoint A — draft safety

Prototype: `artifacts/proto/inbox_put.py` (`new`/`finish`/`list`/`abort`), tests:
`artifacts/proto/test_inbox_put.py` (13 tests, `Ran 13 tests ... OK`,
`artifacts/logs/test_inbox_put.console.txt`). The implementation follows the plan's
§2.3 and adds three rules the plan leaves open, each tested: `finish` refuses to
re-stamp an existing DONE without `--refinish`; DONE is published via
`tmp + os.replace`; the reader requires `completed_at` **and** a complete `files` map.

| Test | Expected | Observed | Verdict |
|---|---|---|---|
| 8 processes create drafts simultaneously | 8 unique dirs | 8 unique (`001..008`) | PASS |
| control: 8 processes with "scan → sleep → mkdir" | collision | 1 dir, 1 writer's content survives | PASS (control) |
| crash after `mkdir`, before files | not consumable | `incomplete`; `finish` non-zero | PASS |
| crash during file write | not consumable | `incomplete`; `finish` non-zero | PASS |
| crash while publishing DONE (truncated, valid YAML) | rejected | `corrupt`; `list` complete=0 | PASS |
| file modified after DONE | reported, not consumed | `corrupt` (hash mismatch) | PASS |
| repeated `finish` after an edit | must not silently re-stamp | plain `finish` refused; `--refinish` re-stamps | PASS (with new rule; residual risk below) |
| two clones, default deployment label | distinct labels | distinct (repo name + hash of git common dir) | PASS |
| two clones with the same explicit deployment id | same `(deployment, draft_id)` | same — **not globally unique** | FAIL for the global-key claim |
| checkout renamed | label stable | explicit id stable; fallback label changes | PARTIAL |
| legacy flat drafts | listed, not consumed as groups | listed under `legacy_flat_files` | PASS |
| abort | only incomplete, needs `--force` | refuses complete and refuses without force | PASS |
| panel coverage | both implementations handle groups | two separate implementations exist and both mention inbox; not exercised | UNTESTED |

What the prototype does **not** solve, and the plan does not acknowledge:

1. **Global identity.** §2.2 says "用 `deployment` 加 `draft_id` 一起定位". With the
   plan's example label (`deployment: ascend-sleuth`) every clone can produce the same
   pair. A per-clone random/explicit id fixes clones, but two clones configured with
   the same id (a copied `deployment.yaml`) still collide, and a rename of the
   checkout changes the fallback label. The only durable key is a random id generated
   once and never reused; provenance then needs that id, not a human-chosen name.
2. **Re-finish.** `finish` is the only thing that makes a draft consumable. If it can
   be re-run after an edit (and the plan does not forbid it), "DONE + matching hash"
   no longer means "complete and unchanged": it means "the last `finish` call saw
   these bytes". My prototype's `--refinish` gate closes the default path but does not
   leave a revision record; a stronger design keeps the first DONE and writes
   revisions elsewhere, or makes each completion a new directory.
3. **Readers.** The plan specifies writer behaviour but not reader states. In my
   prototype, `list` classifies `complete/incomplete/corrupt`; without that contract, a
   truncated DONE that is valid YAML passes a naive `if DONE.exists()` reader. The
   tested prototype's strictness is a design decision that must be written into the
   plan and into every consumer (groom, panel ×2, any duplicate finder).
4. **Integration gap already observed.** `artifacts/logs/test_find_duplicates.console.txt`
   step "incomplete draft (no DONE) consumed by Checkpoint B?" shows the proposed
   duplicate finder loads an incomplete group (inputs 11 → 12) and nominates it. B
   must share A's reader or it will compare half-written material.
5. **Panel risk is real.** There are two independent inbox readers
   (`dsh-plugins/ascend-panel/panel-host.js`,
   `dsh-plugins/dsh-sleuth-panels/lib/index.js`); the plan lists both. Forgetting one
   makes new drafts invisible. The prototype cannot test the Node host here.

Residual failure after A (with a strict reader and a global random id): a draft that
is complete but *semantically* wrong is still consumable; A is a loss-prevention
mechanism, not a quality gate, and the plan says so.

---

## 2. Checkpoint B — candidate discovery and six axes

Prototype: `artifacts/proto/find_duplicates.py`; harness:
`artifacts/scripts/test_find_duplicates.py`; results:
`artifacts/logs/checkpoint-b-findings.json` and `test_find_duplicates.console.txt`.
The library is the real 173-case (seeded) library; the 11 drafts are synthetic and
labelled by hand.

### 2.1 Must-surface pairs: generation vs display

`--limit 0` disables the display cap, so "generated" is candidate generation and
"displayed" is the reviewer-visible report (cap 20).

| Pair | Semantics | Generated | Displayed | Notes |
|---|---|---|---|---|
| D1 ↔ 90001 | same root cause, different category | yes (`same-namespace-cross-category`) | **no** | dropped by the cap |
| D1 ↔ 90002 | same draft vs the sibling case | yes | yes | |
| D2 ↔ 90001 | same problem, paraphrased symptoms | **no** | no | lexical miss |
| D3 ↔ 90001 | identical discriminator, different root cause | yes | **no** | contradiction hint fires (`same-check-two-fixes`) |
| D4 ↔ D5 | one upstream issue, two problems | yes (`shared-upstream`) | yes | hint `same-issue-different-root-cause` fires |
| D6 ↔ 90001 | same fix, different version constraint | yes | yes | hint `same-symptom-disjoint-ranges` fires |
| D7 ↔ 90001 | overlapping version/platform conditions | yes | yes | axes: conditions=overlap |
| D8 ↔ 90001 | contradictory fix under a different condition | yes | yes | `same-check-two-fixes` + disjoint ranges |
| D9 ↔ 90001 | shared verification event | yes | **no** | axes evidence=same; hint fires; not covered by any nomination rule, only surfaced via symptoms |
| D10 ↔ 90001 | same diagnosis, different sessions | yes | yes | axes evidence=different |
| D11 ↔ 90001 | unrelated negative control | no | no | correct |

Generation recall on the 10 must-surface pairs: **9/10**; display recall: **6/10**.
The three dropped pairs are not low-value: they are the cross-classification duplicate,
the same-signature/different-root-cause case, and the shared-evidence case. The cap is
not described with a number in the plan ("只展示前 N 对"); whatever N is chosen, the
report can hide exactly the pairs the design exists to find, and it only prints a
count of the unshown.

### 2.2 Volume, precision, runtime

For 11 drafts against 173 cases: **101 candidate pairs generated, 23 displayed, 78
unshown**, 2.3–2.8 s (single process, Python). The displayed set is dominated by
same-cell lexical pairs from the real library; only the synthetic drafts carry a
hand label, so no precision number is claimed for the real pairs. A reviewer looking
at 23 pairs per groom is a new, recurring workload; the plan estimates 1–2 minutes per
pair, i.e. 20–45 minutes per groom in this small sample, before the "unshown 78"
question.

I did not invent a precision number for real pairs (no labelled production data). On
the labelled synthetic subset, the three "must-review" classes (same signature,
contradictory fix, shared evidence) were all generated; the false-positive control
(D11) was not.

### 2.3 Are the six axes' data sources sufficient?

| Axis | Machine work | Data actually available | Verdict |
|---|---|---|---|
| Source | same/different/unknown | library: `upstream` 120/173, `source_session` 1/173 (3/175 with the two synthetic cases); drafts: `sources.yaml` | PARTIAL: 30 % of the library has no source anchor; drafts without `sources.yaml` are unknown |
| Root cause | side-by-side, no judgement | present in both | PASS (as designed: human reads) |
| Discriminator | same/partial/different | `quickly_check` present; `expected` is a regex string; normalisation is a heuristic | PARTIAL: "same regex" ≠ "same check"; command, selector and value type are not compared |
| Fix | side-by-side | present, but two sources: `sources.yaml.semantic_summary.fix` and `case.fix` | PARTIAL: which is authoritative is undefined; my harness had to force them to agree |
| Conditions | overlap/disjoint/unknown | `compat.ranges` (166/173), `platforms` (99 non-empty), drafts `conditions` | PARTIAL: platform "overlap" is prefix matching, because the library has no platform hierarchy; version parser handles the observed `>=`, `<`, `==` forms but not `0.18.0rc0+...` |
| Evidence | same/different/unknown | `source_session` 1/173; `validation_record` counts, not event ids; drafts `verification[].ref` | FAIL for "same verification event": the library has no per-event identifier, so "same" can only be inferred from a session string, which exists in ~0.6 % of cases |

Concrete data-model gaps that block the proposal without a schema change:

1. **`sources.yaml` has no namespace/category.** The finder must derive the
   namespace from `conditions.workload_type` + `framework`. A draft filed under
   `common/` but describing a vllm-ascend problem cannot be placed; cross-filing is
   invisible.
2. **`source_session` is single-valued and almost unpopulated.** "Same diagnosis
   supported by different sessions" is representable on the draft side (`sessions`
   list) but not on the library side; "two cases sharing one verification event"
   cannot be represented at all (no event id).
3. **Two fix/root-cause sources.** A draft has `case.fix` and
   `sources.semantic_summary.fix`; if they disagree the "fix" axis is ambiguous. The
   plan's table says "draft: fix and fix_on_mismatch", but the draft file it defines
   also carries a summary. Pick one and detect divergence.
4. **`validation_record` is a count, not evidence.** Reusing one upstream fix in two
   cases is not observable from the count; `verify_upstream_outcomes.py` writes it per
   case with no shared event identity.

### 2.4 What works

- shared upstream, same ID and same path are always shown (no cap), and they produced
  the right hints;
- the five structural contradiction rules fired on exactly the intended pair types
  (D3, D4/D5, D6, D8, D9);
- the finder never merges or rejects; it only nominates, which keeps the human
  decision separate;
- legacy flat drafts still load, with `source/conditions/evidence` degraded to
  `unknown`/inferred values — visible in the report, not silently guessed.

### 2.5 Verdict

**PARTIAL.** It is a useful candidate generator for pairs with a shared source, ID,
path, or strong lexical overlap in the same cell. It does **not** reliably surface
cross-category duplicates, paraphrased duplicates, or evidence-reuse pairs; and the
display cap can hide the very pairs it found. The plan's acceptance criterion ("跨分类、
同来源、同 ID 的对都能出现在候选表") is met only in the generation set, not in the
report the reviewer reads.

---

## 3. Checkpoint C — merge-time recheck

Prototype: `artifacts/proto/merge_recheck.py`; harness:
`artifacts/scripts/test_merge_recheck.py`; results
`artifacts/logs/checkpoint-c-160531.json`, `c-report-*.txt`. It computes the merge
base, both change sets (`--name-status -M`), maps paths to IDs, reuses B's candidate
logic, flags generated artifacts, and parses a previous report's three SHAs to detect
staleness.

| Scenario | Recheck output | Then what actually happened | Verdict |
|---|---|---|---|
| C1 report before any merge | 0 candidates, 3 SHAs | — | PARTIAL (report skeleton only) |
| C2 A merged after the report | `same_path_added_both`, `added_both=[ID]`, `stale.matches_current=false` | — | PASS (detection) |
| C3 merge B holding the stale report | — | Git conflict; nothing blocked the attempt | FAIL (no protection) |
| C4 different IDs, same problem | candidate pair surfaced (`same-cell-overlap`) | — | PASS (inherits B's recall) |
| C5 both edit the same case in disjoint fields | `modified_both=[ID]`, `same_path_differing=[path]`, **no semantic comparison** | clean auto-merge produces the combined file | PARTIAL: it says "both touched", not "contradictory" |
| C6 rename on one side, reference on the other | `renamed: ID→IDR`, `dangling_mentions=[{old_id, file}]` | clean merge; `build_index --check` red only because the index is stale, not because of the dangling reference | PASS (detection), no enforcement |
| C7 generated artifacts in the PR | `generated_artifacts_touched=[_index.yaml]` | `generated-guard` reds | PASS |
| C8 main advances + rebase, then recheck | `stale.matches_current=false`, old/new SHAs differ | merge still succeeds; a PR body quoting the **old** SHA passes `verify_pr_body` | FAIL (TOCTOU) |
| C9 wired into CI? | no `merge_recheck` reference in workflows/skills | — | FAIL (advisory only) |

Why C cannot protect today:

1. **The report is a text file.** Nothing in CI reads it; `verify_pr_body.py` checks
   headings only, and the PR template has a "核对的版本" field that is not validated.
   A body with an outdated SHA passes.
2. **The platform does not require checks or freshness.** The active ruleset has 0
   required approvals, no required status checks, and no "up-to-date" rule. Even if a
   `merge_recheck` CI job existed, the author could merge with it red; even if it were
   required, a branch could be merged after main advanced unless "require branches to
   be up to date" (or a merge queue) is on.
3. **Same-case semantic comparison is missing.** For "both modify the same case", the
   plan says "调用检查点 B 的六轴比较", but B compares a case against *other* cases;
   comparing two versions of the same case is a different operation (field-level diff).
   My prototype falls back to "both touched + paths differ", which is honest but not
   the claimed guarantee.
4. **The time-of-check/time-of-use window is real and measured.** In C8 the report's
   target main and head both changed after the report; the merge still went through.
   The only mechanical mitigation is a merge queue or a required check that re-runs on
   the final head; the plan mentions "分支保护、必需检查、合并队列" only as a parallel
   suggestion, not as a prerequisite for C's claim.

### Verdict

**FAIL as a protection; PARTIAL as an engineering aid.** It makes the conflict and the
staleness visible to a careful reviewer, which is worth having. It cannot stop a merge,
and today's platform configuration guarantees the window stays open.

---

## 4. Provenance

Harness: `artifacts/scripts/test_provenance.py`; record
`artifacts/logs/provenance-161356.json`. The sidecar was written by hand exactly as
§5.2 shows; no product code reads it (`git grep "provenance.yaml|verify_provenance"`
over `scripts/`, `.github/workflows`, `docs/guide` returns nothing).

| Question | Answer with the proposed record | Verdict |
|---|---|---|
| Where did the final case originate? | `materials[]` with `draft_id` + `deployment` + `fields_kept` | PASS at material level |
| Which draft contributed each field? | only field-name lists; when both materials keep `symptoms`, attribution is ambiguous (`{"symptoms": ["draft-001", "draft-002"]}`) | PARTIAL |
| What was discarded? | free-text `fields_dropped` per material | PARTIAL (narrative, not enumerable) |
| Where is discarded information recoverable? | `dropped_destinations[].ref`; the test used a path that never existed, and no check reported it | FAIL (unchecked) |
| Is the verification evidence independent? | `independent: false` is a human assertion; nothing links it to a trace or session; the test shows `checked_by: nothing` | FAIL |
| Was the case merged/renamed/archived/replaced? | `decision: merged` for this decision, but after a rename the sidecar filename still says `VLLM-ASC-90001.provenance.yaml`, the content still says the old ID, and no check notices | FAIL |
| Can evidence be double-counted after a merge? | yes: archiving the duplicate keeps its usage row, `verify_entry_activity` stays green, and both IDs show `resolved: 1` | FAIL |

The ID-migration checklist in §5.3 is the strongest part: references and usage rows
are hard-checked today (`verify_references.py:178`, `verify_entry_activity.py:104`),
fixtures are a warning (`eval_scorecard.py:252`), traces and provenance are not
checked. A successful referential-integrity run does not prove the statistics are
semantically right, exactly as the task hypothesised.

### Verdict

**PARTIAL.** A provenance file is better than none, but in the proposed form it
records *narratives* that no check can falsify. To be useful it needs: machine-
checkable material existence (deployment id + draft id + file hashes), a
`dropped_destinations` existence check, a rename linkage (`supersedes` / `merged_into`
in both directions), per-event ids that also appear in traces/usage rows, and a check
in CI.

---

## 5. Observability

The five monthly metrics and their data sources were audited in
`provenance-161356.json` (step "monthly observability: data availability"):

| Metric | Required data | What exists | Computable |
|---|---|---|---|
| Duplicate-candidate precision | candidate list + reviewer decision per pair | candidate list only in a prototype; no decision field in templates, PR body, or metrics | no |
| Candidate recall | labelled duplicate/non-duplicate set | `eval/golden` is retrieval regression (28 fixtures), not duplicate labels; no labelled set | no |
| Merge rework rate | record of each merge and later split/rewrite | only free-form git history; no machine-readable merge event | no |
| Post-merge misdiagnosis | usage counts mapped across the merge | counts per case ID; merging does not transfer them; `source_session` on 1/173 cases | no |
| Duplicate verification evidence rate | per-event IDs / case→event mapping | `validation_record` is counts; no event ID; `source_session` on 1/173 | no |
| Reviewer decisions auditable | structured decision record | PR body free text; CI checks headings only | no |

Two further blockers were executed:

- E11 (all-digit SHA) crashes the entry-activity generator, which is part of the
  post-merge rebuild job;
- E12 (snapshot fields outside the validator whitelist / strength registry) makes the
  documented weekly snapshot step fail CI.

### Verdict

**FAIL today.** A synthetic evaluation of candidate precision is possible with the
prototype (the labels must be created by hand), but it is not a production
measurement. The plan should either (a) define the decision record as a structured
file/field first, or (b) label the monthly figures as "pilot on synthetic data" for the
first quarters. Label them as such; do not report them as production readings.

---

## 6. Production practicality and the 12–20 day estimate

The plan's cost table assumes: A 4–6 d, B 4–6 d, C 2–4 d, provenance 1–2 d,
observability 1–2 d. Against the actual code:

- **A** touches one new script, two skills, **two independent panel implementations**
  (`panel-host.js`, `dsh-sleuth-panels/lib/index.js`), the inbox README, the batch
  sediment tool, and tests. The panel work alone (reading, changing, rendering checks
  in `panel_render_check.js`/`check_panel_bundle.js`) is not 1–2 days; my estimate is
  5–8 days including tests, the global deployment id migration, and the reader
  contract in every consumer (groom, panel ×2, B).
- **B** is 4–6 days for the algorithm as prototyped, but the prototype is ~500 lines
  and the real cost is the labelled data and threshold tuning. Two axes need schema
  decisions (deployment id/event id, namespace/category in sources.yaml); those are
  not in the plan's scope and add review cycles. 6–9 days.
- **C** is 2–4 days for the report, plus platform configuration (required checks,
  approvals, up-to-date/merge queue) that the plan lists as "parallel" but is
  **prerequisite** for the claimed guarantee. Platform change requires admin access
  and a review process; it is not engineering time in the same sense.
- **Provenance** as proposed is 1–2 days only if nothing checks it. Adding a real
  checker (material existence, dropped-path existence, rename linkage, event ids)
  doubles it and needs schema/reference changes. 2–4 days.
- **Observability** is 1–2 days only after the decision record exists and E11/E12 are
  fixed; otherwise the data does not exist. 2–3 days after prerequisites.

Realistic total: **20–30 engineering days plus platform/governance work**, before
review and rework. The plan's 12–20 is optimistic but not absurd for the code alone;
it omits the two-panel surface, the labelled set, and the enforcement work.

Operational cost measured or inferred:

- 101 candidate pairs for 11 drafts (23 shown) → reviewer workload grows with library
  size and with the number of drafts per groom; the plan's "1–2 min per pair" × 23 is
  25–45 min per groom in this sample;
- `find_duplicates` 2.3 s for 173 cases × 11 drafts — negligible runtime;
- `rebuild_generated --check` ≈20 s per run; the existing job already pays it;
- A adds two commands per sedimentation (new/finish) and a new failure mode
  (incomplete/corrupt drafts) that groom must report every week;
- C adds one run + one report per PR (10–20 min per the plan) and a re-run after every
  rebase; with the platform not requiring freshness, the re-run is voluntary.

### Simplifications worth taking

1. **Do not build a six-axis comparator as a new subsystem.** Reuse
   `build_index`'s token extraction (`sig`/`tok`) and the existing read-side views;
   make B a thin reporter over data the index already produces. This removes a
   parallel tokenizer/threshold implementation and a class of drift.
2. **Drop whole-library keyword nomination (rule 6) for the first release.** In this
   sample it added noise (101 pairs, most irrelevant) and no unique must-surface pair.
   Keep rules 1–5; print "not searched" rather than a weak match.
3. **Make C a required CI check, not a document.** `merge_recheck.py --base
   origin/main --head $HEAD --fail-on same-path|both-modified|stale` with a fixed
   exit code, plus "require branches to be up to date" (or a merge queue). Without
   that, C is a ritual that the author can skip.
4. **Make provenance a small structured index, not prose.** Two machine-checkable
   facts per merge: `materials[]` (deployment id + draft id + file hashes, all must
   exist) and `dropped[]` (destination + hash). Narrative stays in the postmortem.
5. **One deployment ID, generated once.** Add `deployment.id` to `deployment.yaml`
   (random UUID), never derive identity from the checkout path or repo name.

## 7. What was not tested

- GitHub enforcement (approvals, required checks, rulesets, merge queue) — public API
  read only; no PRs created.
- The real DSh panel host with the new draft format (Node checks need the host).
- Two real deployments with different `deployment.yaml` and a real inbox merge.
- `issue-ingest` (no `gh`).
- Scale: 171 cases and 11 drafts; 10× library and 50 drafts may change candidate
  volume and runtime.
- Human review time: estimates, not measurements.
