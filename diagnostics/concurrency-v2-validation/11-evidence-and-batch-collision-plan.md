# 11 — Evidence and batch-collision plan

## Why this exists

The V2 validation used a synthetic 11-draft set and a two-engineer scenario. Those tests
show the mechanisms can work; they do not show how often the collision happens, or
whether the dominant source is two engineers diagnosing by hand.

The repository's own admission rule for a hard CI gate requires a rule to be
mechanically checkable, have deterministic consequences, and be proven recurrent. The
first two are satisfied for parts of V2; the third is not measured. This plan collects
that evidence before B becomes a blocking gate.

No duration estimates and no headcount assumptions.

---

## 1. Questions to answer

1. How often do two drafts or a draft and an existing case describe the same problem?
2. How often does a draft arrive after another contributor has already merged the same
   knowledge?
3. How often do two batch-ingest runs overlap on the same upstream issue pool?
4. How often do reviewers accept a decision without reading the candidates?
5. Which signals (upstream issue, event ID, root/fix text, same session) actually
   predict a real duplicate in this repository?

If the answers are "rare", B stays a logging/advice tool. If they are frequent, B earns
a gate. The decision is data-driven, not architectural preference.

---

## 2. Observation phase (B logging-only)

During observation:

- B generates candidates and writes a report, but does not block groom or promotion.
- No `kb-required` check depends on B.
- Reviewers see the same report they will see later, so the observation measures the
  real workflow, not a toy.
- The report is stored with the draft/PR record.

### 2.1 What to log

For each groom/PR:

```yaml
observation_id: <uuid>
case_id: <draft or PR case>
draft_uuid: <uuid or null>
source: diagnosis | issue | manual
candidate_pairs:
  - pair_id: <stable>
    tier: mandatory | high | low
    signals: [shared_upstream, same_expected, root_overlap, fix_overlap, same_session, same_event]
    score: <number>
reviewer_action: accepted | rejected | deferred | no_review
final_action: new | variant | covered | merged | abandoned
near_miss: true | false
```

`near_miss` is set when a reviewer later finds a duplicate that B did not display, or
when a merged case is later identified as a duplicate. This is the only way to measure
false negatives without a labelled corpus.

### 2.2 Privacy

- Store case IDs, draft UUIDs, pair IDs, scores, and signal names.
- Do not store raw logs, customer names, or local paths.
- Keep the observation file in the local runtime area; aggregate numbers can be
  committed later without case content.

### 2.3 Metrics

- candidate pairs per draft (mandatory/high/low);
- displayed vs hidden high;
- reviewer action distribution;
- duplicate rate: pairs marked `variant`/`covered` / total groomed drafts;
- near-miss rate: `near_miss=true` / total;
- time from draft completion to groom;
- batch overlap count.

Do not report precision/recall from the synthetic D1–D11 set as production metrics.

---

## 3. Batch-ingest collision test

The two-engineer scenario is not the only source. `issue-ingest` and `self-evolve` can
run in parallel and produce PRs faster than a human pair.

### 3.1 Setup

- Two independent worktrees/clones from the same `main`.
- The same upstream issue fixture pool (sanitized), with at least:
  - two issues that share the same root cause but different titles;
  - one issue already covered by an existing case;
  - one unrelated control.
- Both runs start at the same time; both use the real `issue-ingest` path and real
  `to-postmortem`/writer.
- No shared draft directory: each checkout has its own inbox, as in production.

### 3.2 Expected observations

- Both may assign the same suggested case ID or closely related IDs.
- Both may create a draft for the same issue.
- Both may open a PR; A merges first; B's candidate report and decision become stale.
- The C recheck should surface the pair and require a decision.
- If B never sees A's draft, C is the only safety net; this is the intended design.

### 3.3 Variants

1. Same issue, same title, same root cause.
2. Same issue, different title/category.
3. One issue already covered: both should classify `covered`/`variant`, not `new`.
4. One batch run crashes mid-ingest; restart must not duplicate an existing draft.
5. One run writes while the other is between `new` and `finish`; reader must not consume
   the incomplete draft.

### 3.4 Pass criteria

- No overwrite of a draft.
- Incomplete drafts are not consumed.
- Both PRs are either merged with a recorded decision or one is closed; no silent
  duplicate.
- C's pair ID is stable across the two runs; the decision file covers it.
- The final index has one case or two explicitly decided cases, not an unreviewed pair.

---

## 4. Red-team the new mechanisms

The validation found that each new layer can relocate a race. Red-team the new layer
before it becomes a gate:

| Target | Attack | Expected |
|---|---|---|
| `reopen` | crash after new DONE, before old `SUPERSEDED` | at most one consumable draft |
| decision | write `TODO` / empty note | C rejects |
| decision | change head after approval, keep pair set | C rejects |
| decision | same-case disjoint fields, no `same_case` | C rejects |
| overflow | hidden high > 0, ack count 0 | C rejects |
| reader | copy a complete draft under a new directory | `corrupt`, not silently accepted |
| B | fully rephrased duplicate | may miss; record near-miss; do not claim recall |
| platform | docs-only PR / skipped job / renamed check | required check cannot silently pass |
| batch | two runs same issue pool | C catches at merge; no silent duplicate |

Record each attack as a test, not as a theoretical note.

---

## 5. Reviewer-quality audit

The gate checks presence, not judgment. A decision with `note: "looks fine"` is
mechanically valid.

Sampling audit:

- sample decisions across mandatory/high pairs, including accepted and rejected;
- a second reviewer reads the candidate report and the decision note;
- score: did the note name the evidence, the chosen action, and the reason?
- record disagreements and near-misses.

If the audit shows notes are consistently empty or generic, the gate is not providing
the intended protection. Fix the template/reviewer instructions before claiming the
decision gate works.

This audit is part of the observation phase, not a later reporting nicety: without it,
the decision gate can pass without a decision.

---

## 6. Decision rules

| Observation | Action |
|---|---|
| Duplicate rate low, near-miss low | Keep B logging/advice; do not add a hard B gate |
| Duplicate rate high, B display catches most | Make B a gate after C binding is fixed |
| Near-miss high | Improve B before gating; add signals from the missed pairs |
| Batch overlap is the dominant source | Prioritize batch-level dedupe and C; the two-human scenario is not the main model |
| Review notes are generic | Fix template/audit before treating the gate as effective |
| Platform spike fails | Fix platform first; B gate cannot compensate |

The decision is recorded with the observation data, not with an estimate.

---

## 7. Artifacts

- `artifacts/logs/observation-<id>.json` — one row per groom/PR.
- `artifacts/logs/batch-collision-<id>.json` — two-run test record.
- `artifacts/logs/red-team-<id>.json` — attack results.
- `artifacts/logs/review-audit-<id>.json` — sample and scores.

Do not commit raw case content. Aggregate counts can be committed.

---

## 8. What this does not do

- It does not prove B's semantic recall; it measures the observed miss rate.
- It does not replace C; C remains the merge-time check.
- It does not justify a hard gate by itself; the platform spike must also pass.
- It does not turn a synthetic 9/9 into a production precision claim.
