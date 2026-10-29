# 10 — Platform enforcement spike plan

## Why this runs first

`07-final-assessment.md` and `05-new-findings.md` (N11) name GitHub enforcement as the
critical blocker: the integrated workflow's "merge blocked" result is a harness
simulation, not an observed GitHub behavior. DD-13
(`research/2026-10-29-design-decisions.md`) specifies a required aggregator check, one
non-author approval, dismiss-stale-review, last-push approval, and up-to-date; those
settings have only been read from the API, never exercised.

If `kb-required` / up-to-date / `merge_group` do not behave as assumed, B and C's
"decision required before merge" guarantee has no teeth regardless of how well the
comparator or decision schema works. A negative result should change the design before
A/B/C code is written.

**Sequence rule:** do not start P0-3/P0-4 code work (full B, provenance, panel
migration) until this spike passes or the design is amended to match GitHub's observed
behavior.

This plan deliberately contains no duration estimates. It is a test plan, not a
resourcing plan.

---

## 1. Objective

Determine, empirically, in a repository nobody depends on:

- whether a missing / red / skipped required check actually blocks a merge;
- whether a stale branch is blocked by up-to-date;
- whether approvals are dismissed on push and whether self-approval counts;
- whether a bot/deploy key can push generated artifacts while humans cannot;
- whether check names stay stable under the real workflow shape;
- whether `merge_group` base/head semantics match what C needs.

## 2. Non-goals

- No changes to this repository's ruleset, branch protection, or CODEOWNERS.
- No PRs against this repository.
- No production secrets. The test repo uses a throwaway deploy key/bot token scoped to
  that repo only.
- Not testing B's comparator, C's field diff, or the decision schema; those are covered
  by `03-checkpoint-validation.md`.
- Merge queue is informational; it is not a P0 requirement.

---

## 3. Setup

1. Create a private throwaway repository, not a fork. Seed it with:
   - a trimmed copy of the `kb-checks.yml` job graph: one always-pass job, one
     toggle-to-fail job, one path-filtered job, one bot-push job, and a stub
     `kb-required` aggregator (`needs: [...]`, `if: always()`);
   - a two-line README so `main` has an initial commit.
2. Configure a ruleset on `main`:
   - require a pull request;
   - require status checks: only `kb-required`;
   - require branches to be up to date;
   - require 1 approval; dismiss stale approvals on push; require approval of the most
     recent push;
   - restrict direct pushes, with the bot/deploy-key identity in the bypass list for
     that rule only.
3. Export the ruleset as JSON before and after each scenario.
4. Save evidence under `artifacts/logs/platform-spike-<id>.json` (redact tokens and
   cookies).

### 3.1 Test identities

- Author A.
- Non-author reviewer B.
- Bot/deploy key with write access.
- A no-write account to confirm it cannot bypass.

### 3.2 Evidence per scenario

- PR number and branch;
- check-run names and conclusions;
- review state;
- merge button/API result;
- ruleset JSON;
- for failures, the exact API response.

---

## 4. Scenario matrix

| # | Scenario | Setup | Expected | Observed |
|---|---|---|---|---|
| S1 | No required check has run | Open PR, disable Actions, attempt merge | Blocked; check never reports | |
| S2 | Required check red | Toggle failing job; aggregator `if: always()` | Blocked | |
| S3 | Stale branch | Merge unrelated commit to `main` after PR checks; do not update PR | Blocked by up-to-date | |
| S4 | Approval dismissed on push | Get approval, push a new commit | Old approval gone; blocked until re-approved | |
| S5 | Author self-approval | Author approves own PR | Rejected / not counted | |
| S6 | Path-filtered job skipped, but should have run | PR changes a file that the job should check; trigger does not match | Aggregator fails; PR blocked | |
| S7 | Legitimately skipped job | PR has nothing for that job to check | Aggregator passes; PR not blocked forever | |
| S8 | Bot push | Deploy key pushes generated artifact to `main` | Allowed by bypass; human direct push still blocked | |
| S9 | Check-name stability | Use the real job names and a matrix job; configure required check | Required name matches the reported check-run name | |
| S10 | Merge queue (informational) | Two PRs enter queue; inspect `merge_group.base_sha` / head | Workflow runs on the queue commit; base is current main tip | |
| S11 | `changes` output empty / diff failure | Force `git diff` failure or empty output | Aggregator fails; no "zero changes = green" | |
| S12 | Docs-only PR | Change only `docs/**`; workflow-level `paths` may not match | Aggregator still runs or the design removes workflow-level `paths` | |
| S13 | Admin / bypass behavior | Admin attempts merge without checks | Record who can bypass and whether it is audited; do not count it as protection | |
| S14 | Workflow / job rename | Rename `kb-required` or a dependency | Old required name leaves PR waiting forever; new name must be updated | |

S6/S7/S11 are the core of the spike: the current production ruleset has no required
checks at all, and DD-13's aggregator exists to close the "skipped job passes" hole. If
the aggregator cannot distinguish "skipped because irrelevant" from "skipped because
misconfigured", the required check either blocks every PR or silently passes the wrong
ones.

S12 decides whether the workflow-level `paths:` must be removed. S14 decides whether the
required check name is stable enough to configure by hand.

---

## 5. Aggregator design to test

```yaml
kb-required:
  if: always()
  needs: [changes, generated-guard, index-freshness, case-structure,
          reference-validation, metrics-validation, proposal-audit, docs-index,
          holdout-integrity, eval-scorecard, unit-tests, panel-checks,
          skill-self-contained]
  runs-on: ubuntu-latest
  steps:
    - name: fail on dependency failure/cancel
      if: contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled')
      run: exit 1
    - name: fail on unexpected skip
      if: contains(needs.*.result, 'skipped')
      run: |
        echo "one or more required jobs skipped; inspect the job-level rules"
        exit 1
```

The second step is intentionally too strict; S7 exists to force a better rule. Do not
ship this pseudo-code unchanged. The spike must produce a rule that:

- fails when `changes` fails or reports empty;
- fails when a job that should have run is skipped;
- passes when a job is legitimately irrelevant (docs-only path, etc.);
- keeps the required check name stable.

Possible implementation: each job gets an explicit `if:` and writes a result artifact;
the aggregator reads the expected matrix, not just `needs.*.result`. Test that version
too if the simple `skipped` rule cannot distinguish S6 from S7.

---

## 6. Decision table

| Outcome | Consequence |
|---|---|
| S1–S9, S11, S12, S14 pass | DD-13 is implementable; proceed to production enablement after P0-1–P0-4 code |
| S6/S7/S11 fail | Redesign the aggregator before enabling; do not enable `kb-required` |
| S3/S4 differ | Re-read GitHub ruleset behavior for the account/plan; amend DD-13 and PR instructions |
| S9/S14 fail | Flatten/rename jobs or generate the required-check name from a single source; retest |
| S8 fails | Change generated-artifact rebuild to a bot PR or manual post-merge step; do not rely on direct bypass |
| S10 unreliable | Drop merge queue from P1; keep up-to-date only |
| Required checks unavailable on the plan | Record as a platform limit; V2 can only claim detection, not prevention |

A "should work" answer is not a pass. Each row needs a PR/check/API record.

---

## 7. Production changes if the spike passes

1. Remove workflow-level `paths`; keep job-level `changes` logic.
2. Add `kb-required` and put every job in its `needs`.
3. Move `pr-template` into `kb-checks.yml` so it cannot be filtered out.
4. Require only `kb-required` in the ruleset.
5. Require 1 non-author approval; dismiss stale reviews; up-to-date.
6. Put the rebuild deploy key / app in the bypass list; restrict it to generated
   artifacts.
7. Store the ruleset as code (export/import) to avoid manual drift.

Unchanged: A/B/C comparators, decision schema, provenance schema.

---

## 8. If the spike fails

- Missing required check: fix workflow triggers/names before A/B/C code.
- Skipped treated as pass: fix aggregator; otherwise the gate is decorative.
- Bot cannot push: change rebuild to bot PR or manual post-merge; otherwise indexes go
  stale after every merge.
- Merge queue unusable: keep up-to-date; accept the rebase cost.
- Approval cannot be enforced: use an external gate or reduce the claim to "process
  convention"; do not say CI enforces it.

---

## 9. Rollback

- Delete the test repo/ruleset; production is untouched.
- Export the production ruleset before any later change; restore it if the gate blocks
  normal merges.
- Keep `kb-required` as reporting-only if enforcement must be paused.

---

## 10. What this spike does not answer

- How often the collision actually happens. That is `11-evidence-and-batch-collision-plan.md`.
- B's precision/recall on real data.
- Whether reviewers read decisions or rubber-stamp them.
- Whether the batch-ingest path produces overlapping drafts.

Platform enforcement is necessary but not sufficient; the evidence plan runs alongside
it, before B becomes a hard gate.

---

## 11. Minimum evidence package

- Test repo URL or reproducible creation script.
- Ruleset JSON before/after.
- PR numbers and check results for S1–S9, S11, S12, S14.
- Verbatim API responses for S6/S7/S11.
- Production enablement checklist.
- A record of what failed and which design changed.

Without this, E13 remains **UNTESTED**.
