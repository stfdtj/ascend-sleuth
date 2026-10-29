# 05 — New findings, flawed assumptions, and regressions

Severity is for production knowledge integrity, not for test effort.
“Experiment” means reproduced in this validation; “theoretical” means identified from
the code/design without a reproduction.

---

## N1 — `reopen` crash window leaves two `complete` drafts (High, experiment)

**What:** `inbox_v2.py reopen` writes the new complete draft first and then writes the
`SUPERSEDED` marker on the old one. A crash between the two steps leaves both
directories `complete`. The reader does not inspect the new draft's `supersedes` link,
so both are consumable; B would nominate both, groom could promote both.

**Reproduction:** `v2-a-030836.json`, step "reopen crash window: both complete"
(delete the old marker to emulate the crash; both states are `complete`).

**Fix:** make the old marker the first write (`SUPERSEDED` pointing to the new draft),
then publish the new DONE; a crash leaves the old draft suppressed and the new draft
missing (recoverable, not duplicated). Additionally, the reader should treat a draft as
`superseded` when a complete draft declares `supersedes: <this>` even if the marker is
missing. Add a test for both crash orders.

---

## N2 — Placeholder decisions satisfy the gate (High, experiment)

**What:** `merge_recheck_v2.py` checks that each required `pair_id` appears in the
decision file, but not that `decision` is a real value. A file with `decision: TODO`
(even for every pair, and for `same_case`) returns exit 0.

**Reproduction:** `v2-c-030729.json`, steps "placeholder TODO decision accepted?" and
"same-case TODO accepted?" — both exit 0.

**Fix:** reject `TODO`, empty, and unknown decision values; require a non-empty `note`
for every mandatory/high pair; validate `same_case` entries the same way. This is a
mechanical check and belongs in `verify_decisions`.

---

## N3 — `head_sha` is recorded but not enforced (High, experiment)

**What:** after a decision passes, B can change the case (a new commit on the same
branch) and C still returns 0 if the pair set is unchanged. The decision's `head_sha`
is never compared with the current head/content.

**Reproduction:** `v2-c-030729.json`, step "C head changed after decision
(head_sha unchecked)" — exit 0 after appending to the case.

**Fix:** bind the decision to the content, not only the commit: require
`head_sha == current head` or a hash over the changed case files; any change invalidates
the decision. A commit SHA is fragile under rebase/squash; a content hash of the
changed knowledge files plus the decision pair set is more robust. This must be checked
by C and by the required check.

---

## N4 — Same-case decisions are outside the V2 schema (High, design)

**What:** V2 defines `pairs` + `overflow`; a same-case edit (two branches touching one
case's disjoint fields) produces no `pair_id`, so there is nowhere to record the field
decision. The C prototype added `same_case`, but the V2 document does not define it, and
the earlier plan does not mention it.

**Consequence:** without a schema extension, C either blocks all same-case edits or
lets them pass with no record. The prototype requires `same_case` for disjoint changes;
this is a design addition that must be written into V2 and the PR template.

**Fix:** add `same_case: [{case_id, fields, decision, note, reviewer}]` to the decision
schema and to `verify_decisions`; require it for every `both_modified` case.

---

## N5 — High-priority overflow is only reported at groom (Medium-High, experiment)

**What:** B's display returns `hidden_high=6` for 11 drafts and 36 high pairs (cap 30).
B does not block promotion or demand an ack; the V2 design says it must. The ack check
exists only in C, when the same pair set reaches a PR. At groom, a reviewer can proceed
without acknowledging the hidden pairs.

**Reproduction:** `v2-b-024503.json`, counts and "high overflow" with `--high-cap 2`
(hidden 34). No groom gate exists.

**Fix:** implement the ack in the groom/decision producer: if `hidden_high > 0`, the
decision file for the draft must contain an `overflow.ack` with the hidden count,
reason, and reviewer; otherwise the draft cannot be promoted. B should exit non-zero for
an unacknowledged overflow (or write the decision skeleton in a blocked state).

---

## N6 — Root/fix overlap admits weak high-priority pairs (Medium, experiment)

**What:** the V2 "high" rule `root_overlap >= 0.5` / `fix_overlap >= 0.5` (with ≥3/4
tokens) produces high pairs whose symptom overlap is `0.087` and `0.043` in the C
same-case test. Those pairs force decisions and add noise; worse, they can make a weak
pair look like a mandatory review item.

**Reproduction:** `v2-c-030729.json`, "C both modify disjoint fields/no decision" pairs
`93001 ↔ 13050` (score 0.087) and `93001 ↔ 12030` (0.043), both tier high.

**Fix:** require an additional signal for high (shared strong keyword/error code,
conditions overlap, or a minimum symptom score), raise the root/fix floor for short
fields, and never let a single low-text root/fix match promote a pair above low. Add a
negative control set to the labelled data.

---

## N7 — The reader contract is not adopted by all consumers (High, design)

**What:** B uses `draft_queue.py`; groom, `to-postmortem`, `sediment_batch` and both
panels were not migrated/tested. Any direct file read reintroduces the old behavior
(half set, corrupt, superseded).

**Consequence:** the V2 A guarantee is only as strong as the weakest consumer. The
previous validation already showed B consuming an incomplete draft; this time B was
fixed, but the other consumers are untested.

**Fix:** route every consumer through one CLI/JSON contract; add fixture-based contract
tests for both panels and for groom; fail a test if a consumer reads inbox files
directly. Publish the contract as a versioned interface.

---

## N8 — Local-only provenance is not recoverable (High, by design)

**What:** the checker correctly reports local-only/declared material as a warning, not
an error. The warning is correct, but the V2 claim "recoverability" only holds for committed
material. A merged case whose evidence stays local cannot be reconstructed by a
reviewer or CI.

**Consequence:** the proposal is a **traceability** mechanism for most evidence, not a
recoverability guarantee. This must be stated in the review brief and in the PR
template; otherwise reviewers will read "provenance present" as "evidence recoverable".

**Fix:** require at least one committed, sanitized material for merged cases (policy
choice), or mark the case `recoverability: local-only` and report the percentage of
such cases. Do not claim verified recoverability for local-only.

---

## N9 — Rename/usage/refs/fixtures migration is absent (Medium-High, design)

**What:** V2 describes `rename_case.py` and redirects, but this validation has no
implementation. The checker validates lineage/redirects if written; nothing writes
them. The previous baseline failure remains: references/usage are hard checks, fixtures
are a warning, traces are local, and usage counts are not migrated.

**Consequence:** E9 is not resolved by V2 as validated; a rename can still strand
counts or break citations until the tool exists.

**Fix:** implement the tool and a `verify_entry_activity` redirects exception; test a
rename with a reference, fixture, usage row, trace, and provenance. Do not auto-reseal
holdout.

---

## N10 — E10 naming fix is not implemented (Medium)

**What:** two clones still choose `2026-W44-live-1029`; the V2 deployment-id suffix is
design only. This validation could not test the fix.

**Fix:** implement the suffix, extend `LIVE_PERIOD_RE`, migrate old period files
compatibly, and test two deployments with different `deployment.id`.

---

## N11 — GitHub enforcement is unverified (Critical blocker)

**What:** the current ruleset requires a PR but has 0 approvals, no required checks, no
up-to-date; V2 proposes `kb-required`, approvals, and up-to-date. No authorized test
repository/PR was available; the integrated gate is a harness simulation.

**Consequence:** the answer to "can a stale decision enter main?" remains **yes** in
production until the platform configuration is tested and enabled. Do not present the
prototype as production protection.

**Fix:** in a test repository, verify: missing check blocks, red check blocks, stale
branch blocks, approval invalidation on push, bot can push generated artifacts,
`changes` skipped does not pass. Then enable the same rules for the real repository.

---

## N12 — E11/E12 fixes are prototype-only (Medium)

**What:** the one-line E11 coercion and the E12 whitelist/strength additions work in a
disposable clone; the production scripts are unchanged. The post-merge job and the
weekly snapshot remain broken until the fixes land.

**Fix:** implement both with regression tests; E11 should quote/normalize at write time,
not only coerce at read time.

---

## N13 — B "same path" is not effective for UUID drafts (Low)

**What:** B compares `_path`; UUID drafts have `postmortems/inbox/<uuid>/case.yaml`, not
a knowledge path. Same-path is meaningful for C and `changed-from` inputs; for UUID
drafts, same ID covers the conflict. The V2 acceptance wording ("always surfaces same
path") must be qualified.

**Fix:** define same-path as a C/legacy-owned rule; for drafts, use same ID and the
promotion target path. Document it; do not claim a protection that cannot trigger.

---

## N14 — C's base argument is correctness-critical (Medium)

**What:** C computes `main` changes as `merge-base..--base`. If CI passes an old base or
a wrong ref, the main side is under-approximated and the check can pass. The prototype
expects `--base` to be the latest main.

**Fix:** the CI job must pass the event's base SHA and verify it is the current main;
`up-to-date`/merge queue makes this true. Add an assertion in C that the base is an
ancestor of the target and equals `origin/main` (or the merge-group base).

---

## N15 — Panels and groom are not tested against the reader (Medium)

**What:** two independent panel implementations exist; neither was exercised with a
UUID inbox. A panel that lists only flat files shows an empty queue even though drafts
exist.

**Fix:** fixture-based contract tests for both panels; a shared JSON reader contract;
P2 consolidation.

---

## N16 — Decision `ack` is not count-validated (Medium, theoretical)

**What:** C treats any truthy `overflow.ack` as sufficient. A fabricated ack with
`hidden_count: 0` passes even when B found hidden high pairs.

**Fix:** compare `ack.hidden_count` with the current hidden count; require a reviewer
and reason; fail if the count differs.

---

## N17 — B low watchlist is explicitly unreviewed, but its count is easy to ignore
(Low)

**What:** B prints `hidden_low=275` for 11 drafts. A reviewer can accept the report
without reading the count. That is by design, but the decision file only records high
overflow, not "I saw N low and did not review them".

**Fix:** add `low_watchlist: {shown, hidden, acknowledged}` to the decision; make the
acknowledgement a one-line, low-cost field.

---

## N18 — Test fixtures overstate B recall/workload (Medium, measurement)

**What:** the 11 labelled drafts share root/fix text more than real cases; the D1–D11
set is synthetic. B's displayed 9/9 and 46 pairs are mechanism evidence, not production
precision/recall or workload.

**Fix:** build a real labelled sample (≥30 pairs) with owners; report precision/recall
and review time against that sample. Do not publish the synthetic numbers as production
metrics.

---

## N19 — Current commit diff reduces, but does not eliminate, baseline uncertainty
(Low)

**What:** the current HEAD differs from the previous baseline only in vllm-kb plugin
files; the knowledge workflow scripts are unchanged. The baseline results are therefore
valid for this commit, but the validation did not re-run every E1–E9 scenario on the
current tree; it re-ran the control, duplicate, C, and A/B cases.

**Fix:** when the workflow scripts change, re-run the full matrix; record the commit
hash in every report.

---

## Summary table

| ID | Severity | Type | Fix owner |
|---|---|---|---|
| N1 | High | V2 race | A |
| N2 | High | V2 check gap | C/decision |
| N3 | High | V2 binding gap | C/decision |
| N4 | High | V2 schema gap | design/C |
| N5 | Medium-High | V2 gate gap | B/groom |
| N6 | Medium | V2 signal quality | B |
| N7 | High | migration gap | A/consumers |
| N8 | High | explicit limit | provenance policy |
| N9 | Medium-High | migration gap | rename/provenance |
| N10 | Medium | unimplemented | metrics |
| N11 | Critical | platform | admin |
| N12 | Medium | unimplemented | E11/E12 |
| N13 | Low | wording | B |
| N14 | Medium | CI binding | C/CI |
| N15 | Medium | consumer | panels |
| N16 | Medium | check gap | C/decision |
| N17 | Low | UX | B/groom |
| N18 | Medium | evidence quality | B/owners |
| N19 | Low | coverage | validation |
