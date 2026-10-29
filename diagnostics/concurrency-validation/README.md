# Concurrency validation — Ascend-Sleuth knowledge workflow

Independent, adversarial validation of the current knowledge workflow and of
`research/2026-10-28-unified-plan.md` (Checkpoints A/B/C, provenance, observability),
run against a disposable clone of baseline `28adab0` on 2026-10-28/29.

**Headline:** the single-contributor path works and every documented gate is green.
Concurrent contribution does not: the same knowledge entered twice under different IDs
with all gates green, a same-name draft was lost in 10/10 concurrent rounds, conflict
resolution silently discarded one side, disjoint edits merged into a self-contradictory
case, and a stale duplicate conclusion merged without any recheck. Generated artifacts
are genuinely rebuilt on main in this deployment (verified via the Actions API), which
resolves E7 conditionally. Checkpoint A works when used with a strict reader but is not
globally identified; B surfaces 9/10 must-review pairs but displays only 6/10; C detects
overlap and stale SHAs but nothing enforces it; provenance and the monthly metrics are
not checkable. Two new data-plane defects were found (all-digit SHA crash; snapshot
output rejected by its own validator). Recommendation: **ACCEPT WITH CHANGES** — enforce
the platform gate, fix the two defects, add a reader-contracted draft protocol and a
narrow duplicate step, then add provenance/observability.

## Read in this order

1. [01-current-workflow.md](01-current-workflow.md) — what the code actually does,
   which parts were executed vs inspected, and the real Git/CI/platform state.
2. [02-baseline-findings.md](02-baseline-findings.md) — end-to-end run, two-engineer
   experiments (shared inbox and separate clones), the ten original issues, and four
   newly discovered ones.
3. [03-solution-validation.md](03-solution-validation.md) — every proposed mechanism
   against runnable prototypes, classified PASS/PARTIAL/FAIL/UNTESTED.
4. [04-gaps-and-recommendations.md](04-gaps-and-recommendations.md) — missing
   protections, incorrect assumptions, simplifications, migration and priorities.
5. [05-test-matrix.md](05-test-matrix.md) — scenario-by-scenario before/after table
   with evidence references.
6. [06-final-assessment.md](06-final-assessment.md) — the decision and the ten
   required answers, with verified vs uncertain separated.

Reproduction: [artifacts/README.md](artifacts/README.md). Prototypes in
`artifacts/proto/`, harnesses in `artifacts/scripts/`, raw records and console logs in
`artifacts/logs/`.

The follow-up design proposal is in
[the V2 proposal](../../research/2026-10-29-concurrency-plan-v2.md),
with the decision log, review brief, and Q&A alongside it. That document makes the
design decisions; this directory remains the evidence base.

## Scope and honesty statement

- All content used for the experiments is **synthetic and invented**; no customer
  data, credentials, or production logs are included.
- No real branch, PR, draft, case, trace, or metric was modified. The real checkout
  shows only this untracked `diagnostics/` directory.
- GitHub-side behaviour (ruleset, workflow runs) was read from the public API; no PR
  was created and no CI run was triggered by this validation.
- Where a stage needed a human/agent (writing case YAML, choosing a category, judging a
  root cause), the harness performed the mechanical action and the report says so; it
  is not evidence that the judgement was correct.
