# 06 — Final engineering assessment

**Decision: ACCEPT WITH CHANGES.**

The plan's direction is right and several of its mechanisms work in isolation, but as
written it does not make concurrent knowledge contribution safe in this repository. Two
of its three checkpoints stop short of the guarantee they claim (B's report can hide
the pairs it found; C has no enforcement), and the provenance/observability legs have
no checked data source. The changes needed are concrete and smaller than the full
plan: enforce the merge gate on the platform, fix two data-plane defects, add a
minimal draft protocol with a reader contract, keep the duplicate finder to explainable
rules, and make provenance machine-checkable. With those, the design is worth
shipping; without them, it produces documents that a careful reviewer could use and an
unhurried author could ignore.

## 1. Does the current workflow safely support multiple independent engineers?

**No.** Executed evidence:

- two clones independently produced the same knowledge under different IDs and
  different categories; both merge orders had **zero conflicts and all gates green**
  (E2/E3/E8);
- two writers to one inbox lost one draft in **10/10** rounds, with valid YAML, and
  produced mixed content in **3/3** chunked rounds (E1);
- resolving a same-path conflict by taking one side discarded the other side's root
  cause and every check stayed green (E4/E5);
- disjoint edits merged cleanly into a self-contradictory case, all gates green (E6);
- renaming a case stranded usage counts (red if deleted, silently double-counted if
  archived), left fixtures pointing at the old ID with only a warning, and left local
  traces untouched (E9);
- two machines produced the same period filename with different readings; after
  resolution nothing reported the missing reading (E10);
- the platform requires a PR but **0 approvals, no required checks, no up-to-date
  rule** (E13), so even a well-written report changes nothing mechanically.

The single-contributor path is fine: a full diagnosis → draft → groom → PR → merge →
post-merge rebuild run passed every gate and the new case became visible to retrieval
(`e2e-baseline-153803.json`). The failure is specifically concurrency and recovery.

## 2. Which of the original ten were reproduced?

| ID | Reproduced in the current configuration | Note |
|---|---|---|
| E1 | yes | silent overwrite, silent mixture, half set |
| E2 | yes | both merge orders, no conflict, gates green |
| E3 | yes | pre-triage reads one cell; cross-category duplicate invisible |
| E4 | yes | `CONFLICT (add/add)` on the case file |
| E5 | yes | taking one side lost the other's content; gates green |
| E6 | yes | clean merge, contradictory `compat` vs diagnosis prose |
| E7 | **not in the current configuration** | source-only PRs: no generated conflicts; guard works; the inspected post-merge job runs succeeded (six runs in total). Reproduced in the historical pre-job discipline (local test) and in a no-job deployment (main stale, red index, no signal) |
| E8 | yes | B's conclusion stale; merge succeeds; no recheck |
| E9 | yes | refs/usage red on delete, fixtures warn, traces/provenance unchecked, archive double-counts |
| E10 | yes | same period name, different readings, conflict, silent loss after resolution |

So: nine of ten in the current deployment; E7 is conditionally resolved rather than
absent — the condition is "the post-merge job exists and succeeds".

## 3. Additional problems discovered

- **E11:** an all-digit short SHA is written as a YAML integer and crashes the
  entry-activity generator (`TypeError` in `sorted()`), which is part of the
  post-merge rebuild job. Reproduced deterministically; the validator passes the same
  rows.
- **E12:** the documented weekly `metrics_snapshot.py` output fails
  `verify_metrics.py --check` (one field outside the whitelist, six metrics without a
  strength declaration). The observability step cannot land.
- **E13:** the repository's protection is weaker than the workflow documentation
  assumes: PR required, 0 approvals, no required checks, no branch freshness.
- **E14:** the inbox has no reader contract: half sets pass the only draft check;
  truncated/mixed files are caught only if someone runs the check; any new protocol
  must define consumer states, not just writer behaviour.

## 4. Does Checkpoint A prevent draft loss?

**PARTIAL — the mechanism does, the design as written does not fully.**

Verified: exclusive `mkdir` (8/8 creators), three crash shapes (`incomplete`/`corrupt`,
never consumed), hash mismatch reported, atomic DONE publish, legacy flat files listed,
abort restricted.

Not solved: `(deployment, draft_id)` is not globally unique (two clones with the same
deployment label produce the same pair; the fallback label changes on rename);
`finish` can be re-run with `--refinish` and legitimises edits; consumers must all use
the strict reader, and the prototype's own duplicate finder already consumed an
incomplete draft; the two panel implementations were not exercised. A direct
file write bypasses the protocol entirely.

## 5. Does Checkpoint B reliably surface important duplicates?

**No — PARTIAL.** On a labelled set of 11 drafts against 173 real cases: 10 pairs had
to surface; **9 were generated, 6 were displayed** at the cap. The three dropped pairs
were the cross-classification duplicate (D1↔90001), the same-signature/different-root-
cause pair (D3), and the shared-verification pair (D9). A paraphrased duplicate (D2)
was not generated at all. The structural contradiction hints work (same check/two
fixes, same issue/two problems, disjoint ranges, shared session), but the six axes are
uneven: `source` is unknown for ~30 % of the library, `evidence` cannot represent a
verification event (no event IDs; `source_session` on 1/173), and a draft carries two
possible fixes (`case.fix` vs `semantic_summary.fix`). The report never asserts
duplication — that part is correct — but "not shown" is not the same as "not present",
and the cap can hide the finding.

## 6. Does Checkpoint C protect against stale decisions and concurrent merges?

**No — FAIL as a protection; PARTIAL as a report.** It detects same-path additions,
both-modified cases, renames, dangling mentions, generated artifacts, and stale report
SHAs (C2/C6/C8). It does not: compare two versions of the same case field by field;
stop a merge (C3/C8 merged anyway); or bind the report to the final head — a PR body
quoting the old SHA passes `verify_pr_body`. The platform's ruleset (0 approvals, no
required checks, no up-to-date rule) leaves the time-of-check/time-of-use window fully
open. A merge queue or "require branches up to date" plus a required recheck job is the
minimum; without it the report is advice.

## 7. Does provenance preserve information and evidence?

**PARTIAL.** It answers "which materials" and "which field names" at material level.
It does not answer, in a checkable way: which bytes of a shared field came from which
draft; whether a discarded destination exists (a nonexistent path passed); whether two
verification events are independent (a human `independent: false` is unverifiable);
whether a renamed case's sidecar followed it (it does not; the sidecar remains
`<old-id>.provenance.yaml` and no check notices). Archiving a duplicate keeps its usage
counts and keeps `verify_entry_activity` green, so the statistics remain wrong while
the referential check passes — the exact distinction the task asked to test. Nothing
in `scripts/`, `.github/workflows` or `docs/guide` reads the proposed sidecar.

## 8. Are the observability metrics feasible?

**Not today.** Candidate precision needs reviewer decisions (none stored); recall needs
a labelled duplicate set (none; `eval/golden` is retrieval regression); merge rework
needs a merge event record (none); post-merge misdiagnosis needs counts mapped across a
merge (they are not transferred); evidence duplication needs per-event IDs (they do not
exist). Two data-plane defects (E11, E12) block the underlying collection. A pilot on
synthetic labels is possible now; production numbers are not, and the plan should say
so.

## 9. What is excessive, insufficient, or based on a wrong assumption?

**Excessive**
- A separate six-axis comparator with its own tokenizer/ranges, instead of reusing the
  index's `sig`/`tok`;
- whole-library keyword nomination (78 unshown pairs in a 11-draft sample, no unique
  must-surface hit);
- provenance as narrative prose (`fields_dropped`, `independent`) with no checker;
- per-pair review of every lexical candidate (101 pairs) as the default workload.

**Insufficient**
- No enforcement: B's report and C's report are files; the platform accepts a PR with
  red CI and no approval;
- no global identity for drafts (`deployment + draft_id`);
- no reader contract for the queue;
- no event identity for evidence and no count-transfer rule for merges;
- no same-case two-version comparison in C;
- no fix for E11/E12, which the observability leg depends on;
- no answer for the "no post-merge job" deployment.

**Incorrect assumptions**
- `deployment + draft_id` is globally unique;
- the six axes' sources contain enough information (source/evidence are not);
- cross-category duplicates will appear in the table the reviewer reads (generated ≠
  displayed);
- report SHAs protect against staleness (detect, not enforce);
- monthly metrics are computable from existing data;
- 12–20 engineering days (closer to 20–30 plus platform/governance, because of two
  panels, the labelled set, and enforcement);
- the repository's protection matches the docs (it is a ruleset with zero approvals
  and no required checks).

## 10. Smallest set of changes for acceptable production safety

1. **Platform gate (admin, days):** required checks (`changes`, `generated-guard`,
   `case-structure`, `reference-validation`, `metrics-validation`, `index-freshness`,
   `pr-template`), ≥1 non-author approval, "require branches up to date" or a merge
   queue, DEPLOY_KEY in the ruleset bypass. *Prevents:* E8/C8/E13; makes any recheck
   meaningful. *Tradeoff:* friction and one more reviewer.
2. **Fix E11/E12 and add the main-freshness detector.** *Prevents:* a dead post-merge
   job and a broken weekly snapshot; makes "new case is visible" a checked property.
3. **Draft protocol with a reader contract and a random deployment id**
   (`inbox_put.py` + one reader used by groom/panels/finder). *Prevents:* E1/E14 and
   the global-key collision.
4. **A narrow duplicate-candidate step at groom:** shared source/ID/path always shown,
   same-cell overlap capped with a printed unshown count, the five contradiction hints,
   no whole-library keyword rule. *Prevents:* E2/E3 for source-linked and
   same-cell pairs; does not claim recall. *Tradeoff:* reviewer minutes, and
   paraphrased duplicates still miss.
5. **A merge recheck as a required check bound to the final head**, with the two
   versions' field diff and a decision record. *Prevents:* E8 (and forces E5/E6
   decisions); without item 1 it is advisory.
6. **Minimal checkable provenance + `rename_case.py`** (materials/hashes exist,
   destinations exist, links resolve, IDs migrate across refs/fixtures/usage/traces).
   *Prevents:* E9 and the archive double count.

Items 1–3 are the minimum to stop silent loss; 4–6 make the knowledge flow reviewable
and measurable. Do not build a semantic CI gate, automatic merges, union of case files,
or a production metrics report before the decision record exists.

## Verified vs uncertain

**Verified (executed in disposable clones):** the single-contributor E2E path; both
merge orders and the duplicate outcome; the 10/10 overwrite and 3/3 mixture; crash
shapes; the same-path conflict and the loss after "take ours"; the clean contradictory
merge; the generated-artifact guard and the no-job staleness; the rename detection
matrix (refs/usage/fixture/trace); the period collision; A's 13 tests; B's 9/10 vs
6/10; C's detection set and stale SHAs; the archive double count; E11's crash and fix;
E12's validator rejection.

**Uncertain / not verified:** GitHub enforcement of any proposed check (API-read only,
no PRs); the DSh panel with the new format; two real deployments exchanging drafts;
scale beyond 173 cases/11 drafts; human review time and error rate; NTFS versus
Linux/NFS atomicity for `mkdir`/`replace`.

## Recommendation

**ACCEPT WITH CHANGES.** Adopt the checkpoint vocabulary and the machine-nominates/
human-decides split. Do not adopt the plan's cost or protection claims as written. Land
items 1–3 above first; they are the difference between "the team has a process" and
"the process survives two engineers and a crash". Then add 4–6 with explicit labels:
B is a candidate generator, not a duplicate detector; C is a decision record, not a
gate, unless the platform requires it; provenance is a checked index, not a narrative;
and the monthly metrics are a pilot until the decision record exists. E7 is genuinely
improved by the main-rebuild job in this deployment — keep it, and add a heartbeat so
its failure is visible rather than silent.
