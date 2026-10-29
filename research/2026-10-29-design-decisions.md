# Design decision log (V2)

Scope: every decision needed to make the V2 proposal implementable, with the rejected
alternatives and the evidence. “Evidence” references the validation reports under
`../diagnostics/concurrency-validation/` or the experiment records they cite.

Status legend: **Decided** (this proposal), **Decided-with-assumption**, **Open**
(requires team/admin; cannot be settled from existing evidence).

---

## DD-01 — Git is the only shared state; no draft server / locks / transactions

- **Problem:** independent clones cannot be globally synchronized during diagnosis.
- **Decision:** keep drafts/traces local; every artefact that reviewers need enters
  Git. Use `git fetch`/PR refs for early awareness, not for consistency.
- **Rejected:** centralized draft service, distributed locks, real-time sync, a
  transaction layer. They add availability/security/operations costs and contradict
  the existing multi-clone, gitignored-runtime model.
- **Consequence:** local drafts can be lost if the protocol is bypassed; provenance
  cannot verify local bytes. Both are stated as limits, not hidden.

## DD-02 — Draft identity is a random UUID; deployment id is not an identity key

- **Problem:** `(deployment, draft_id)` collides across clones/copied repos and changes
  when a checkout is renamed (validation report 03, Checkpoint A).
- **Decision:** `draft_id = uuid4()` per sedimentation; directory
  `postmortems/inbox/<uuid>/`. `deployment.id` is a random UUID in `deployment.yaml`
  used only for provenance/panel grouping; missing → `unknown`. It never participates in
  uniqueness.
- **Rejected:** `date-source-seq` (collides across clones), repo-name + hash (rename
  fragile), case-ID-as-directory (premature identity, collides with future cases).
- **Consequence:** human-readable labels move to `created_at/title/session`; UUID is
  not shown as the primary label in reports.
- **Assumption:** UUID4 collision is negligible (standard); not separately tested.

## DD-03 — Completed drafts are immutable; corrections use `reopen`, not re-finish

- **Problem:** `finish` can be re-run after edits, making “DONE + hash match” meaningless
  (prototype result).
- **Decision:** `finish` refuses when DONE exists. `reopen` marks the old draft
  `SUPERSEDED`, creates a new UUID with `supersedes`, copies files. The old bytes stay
  recoverable.
- **Rejected:** `--refinish` (loses the audit trail), in-place revision numbers (more
  state, same problem), delete-and-rewrite (destroys evidence).
- **Consequence:** every correction is a new draft and a provenance `revises`/`supersedes`
  link; slightly more directories, much clearer history.

## DD-04 — One reader contract, enforced by fixtures for both panels

- **Problem:** drafts have no state; half sets pass the only check; two panel
  implementations exist (`panel-host.js`, `dsh-sleuth-panels/lib/index.js`).
- **Decision:** `scripts/draft_queue.py list --json` defines `complete/incomplete/corrupt/
  superseded/legacy_flat`; groom, B, `sediment_batch`, `to-postmortem` and both panels
  consume it. Node panels are tested against the same fixture inboxes as the Python
  reader.
- **Rejected:** each consumer parsing files (drift, already observed in B ignoring DONE);
  a generated `drafts.json` snapshot (staleness).
- **Consequence:** reader changes are contract changes; fixtures are part of CI.

## DD-05 — Legacy flat drafts are read forever; no bulk conversion

- **Decision:** keep reading `<id>.md` + `<id>.case.yaml` as `legacy_flat`; new writes
  only group dirs. No conversion script.
- **Rejected:** one-shot migration (small volume, high risk of altering content),
  dropping legacy (loses queued material).
- **Consequence:** B reports `legacy: true` and axes `unknown` for legacy drafts; groom
  counts them separately.

## DD-06 — Checkpoint B separates generation from presentation and uses three tiers

- **Problem:** V1 generated 9/10 must-review pairs but displayed only 6/10 at a cap;
  one paraphrased duplicate was missed (report 03).
- **Decision:** generate all pairs above a low floor; classify mandatory / high / low;
  present by budget; mandatory never hidden; high overflow requires an explicit per-draft
  ack; low is a counted watchlist, not reviewed.
- **Rejected:** single score with a top-N cap (hides the relevant pair), “show everything”
  (review fatigue), no cap (unbounded), LLM/embedding ranking (non-deterministic,
  unjustifiable in CI).
- **Evidence:** V2 design experiment
  (`../diagnostics/concurrency-validation/artifacts/logs/checkpoint-b-v2.json`, synthetic):
  4 mandatory, 17 high, 279 low, 31 displayed, 0 hidden high; all 9 must-review pairs
  generated and displayed, D11 not. **Not production precision** (fixtures share root
  text; real thresholds must be calibrated).

## DD-07 — Mandatory = identity-level only; same session is high, not blocking

- **Problem:** V2 experiment initially made every same-session/contradictory pair
  mandatory: 44 blocking pairs for 11 drafts, mostly false positives from a broad
  version-vs-fix rule.
- **Decision:** mandatory = shared upstream (repo+issue/pr), same Case ID, same path,
  same verification **event id**, or a **strong discriminator** (same normalized full
  expected + shared `sig_literals` length ≥6 or command token overlap ≥0.6). Same
  session = high with a “confirm evidence reuse” hint. Contradiction hints never promote
  a pair by themselves; they only colour a pair that already passed relevance.
- **Rejected:** raw `expected` equality as mandatory (generic `regex:^[1-9]` is shared
  widely); session as mandatory (one incident can legitimately produce several cases).
- **Consequence:** 4 blocking draft-vs-library pairs (+1 draft-vs-draft pair) for 11
  drafts in the synthetic set; decisions are about identity, not semantic similarity.

## DD-08 — Display budget: mandatory + high up to 30; low 2/draft + 10 global; overflow ack

- **Decision:** all mandatory; high all up to 30 pairs; if high >30, block the draft until
  `--show-all-high` or a per-draft `ack_overflow {hidden_count, reason, reviewer}`;
  low top 2/draft and 10 global, rest only counted. Report always prints hidden counts.
- **Rejected:** hiding high silently; blocking per pair (too many decisions); a single
  global cap that drops mandatory.
- **Consequence:** a reviewer can see ~20–30 core pairs per groom; the ack is an explicit
  “I did not review these”, not a review.
- **Open:** the exact cap (30) must be tuned on real groom data; it is a parameter.

## DD-09 — Cross-namespace search only with a justification

- **Decision:** always compare `common/`; compare training↔inference when the draft's
  `workload_type` is unknown/missing, framework is `common`/cross-framework, or there is a
  shared strong keyword/upstream/event, or root/fix overlap ≥0.5, or conditions intersect.
  Otherwise do not do cross-namespace lexical scanning.
- **Rejected:** always scan all namespaces (volume, unrelated training/inference pairs),
  never scan (loses justified cross-namespace duplicates).
- **Consequence:** some cross-namespace duplicates remain undetected; the report labels
  unscanned pairs as “not searched”, never “no duplicates”.

## DD-10 — One comparator, reusing the index tokenizer

- **Decision:** new `scripts/case_match.py` wraps `scripts/_lexical.tokens_of` and
  `build_index.sig_literals`, plus compat/platform/upstream/event parsing. B and C both
  call it; `build_index.py` imports it instead of maintaining a second tokenizer.
- **Rejected:** B owning a private tokenizer (drift), C implementing its own six axes
  (two systems).
- **Consequence:** small refactor of `build_index` with regression tests; one place to
  tune thresholds.

## DD-11 — Decisions are a machine-readable file in Git, not PR prose

- **Decision:** `postmortems/decisions/<case_id>.yaml` with pair_id, tier, decision, note,
  `main_sha`, `head_sha`, overflow ack. Drafts that do not become a Case
  (`covered/deferred/archived`) get `postmortems/decisions/drafts/<draft_uuid>.yaml` so
  every consumed material has a destination. `verify_decisions.py` checks coverage/
  completeness/freshness, **not** correctness.
- **Rejected:** PR body prose (only headings are checked), JSON in a comment (not
  reviewable in Git history), separate dataset (out of band), “no file for covered
  drafts” (silent discard).
- **Consequence:** a PR without a decision file fails; a fabricated decision still passes —
  the reviewer and the audit are the remaining controls.

## DD-12 — Checkpoint C reuses B and is bound to the integration candidate

- **Decision:** `merge_recheck.py` computes base/head, field diff, generated/rename/delete,
  then calls B’s generator against `origin/main` (and optionally open PRs). Exit codes
  0/1/2/3/4 as defined. It never judges semantics.
- **Rejected:** a separate duplicate detector in CI (two systems), running only on
  `HEAD` (misses the merge result), checking only paths (misses same ID different path).
- **Consequence:** one comparator, two inputs; CI needs up-to-date (or a validated
  merge queue) to make the base it checks the base that lands.

## DD-13 — Enforcement: required aggregator, approvals, up-to-date (merge queue optional), remove `paths` filter

- **Facts:** current ruleset requires a PR but has 0 approvals, no required checks, no
  up-to-date; `kb-checks.yml` has a workflow-level `paths:` filter, and a skipped job is
  reported as success (report 01/03). A required check that is never created would block
  PRs forever; a required job that is skipped would pass.
- **Decision:** single required check `kb-required` that depends on **all jobs of
  `kb-checks.yml`** (the current 14 plus the new `merge-recheck`), runs with
  `if: always()`, and fails on failure/cancelled or “should have run but skipped”; move
  `pr-template` into the same workflow (GitHub `needs` cannot cross workflows); remove
  workflow-level `paths:` (job-level `if:` remains); require 1 non-author approval, dismiss
  stale reviews, require last-push approval; P0 uses up-to-date; merge queue is P1 optional (needs merge_group validation);
  deploy key only for the rebuild job bypass. `merge_group` runs use
  `github.event.merge_group.base_sha`, not `GITHUB_BASE_REF`.
- **Rejected:** requiring every individual job (skipped = success loophole; path-filter
  workflow never reports), advisory-only process (cannot prevent stale merges).
- **Consequence:** platform admin work is a prerequisite; without it, C is advisory and
  the proposal must say so.
- **Open/unverified:** GitHub ruleset/up-to-date/approval/bypass behavior must be validated in
  a staging repo (report 03 says this was not done).

## DD-14 — Same-case conflicts use a field-level diff; no semantic CI gate

- **Decision:** `case_diff.py` reports per-field changes for both sides; overlapping fields
  require a decision; disjoint fields pass with a report. CI cannot judge whether the
  combined content is semantically consistent; the decision note + non-author approval are
  the controls.
- **Rejected:** whole-file “take one side” (loses content); automated semantic merge;
  treating clean Git merge as correct.
- **Consequence:** E5/E6 remain human decisions; the proposal does not claim CI solves them.

## DD-15 — Provenance: committed manifest + optional committed materials + honest local-only

- **Decision:** every new/merged case has a committed `postmortems/provenance/<case>.yaml`.
  It records material hashes for files that are committed; local-only/archive-declared
  materials are labelled as such and **not** verified by CI. `recoverability` is one of
  `verified / declared / local-only`.
- **Rejected:** CI checking `deployment+draft_id+hash` for inaccessible local drafts (fake
  verification); committing raw logs (privacy); requiring all materials in Git (blocks
  legitimate local evidence and bloats the repo).
- **Consequence:** the manifest gives traceability always, integrity/recoverability only
  when the target is accessible; the limitation is visible to reviewers.

## DD-16 — Event IDs, incident key, and no usage-count transfer

- **Decision:** evidence entries use stable `event_id`
  (`feedback:<session>:<n>` where n is the 1-based feedback-event index in the trace,
  `upstream:<repo>#<id>@<state>`, `fixture:<case>`, `report:<path>#<sha>`).
  Same event_id across cases must be marked `independent: false`; `verify_provenance`
  flags duplicate independent claims. Usage records stay historical per Case ID; a
  `redirects.yaml` lets old IDs resolve; incident-level metrics aggregate by `incident_key`,
  never by summing IDs. Legacy drafts without UUID use `legacy:<case-id>:<filename>` as the
  material id in provenance.
- **Rejected:** rewriting usage history (lossy, hard to audit); summing merged IDs
  (double counts); using `source_session` as an event ID (single-valued, 1/173 coverage).
- **Consequence:** existing metrics remain per-ID; incident metrics are a separate view
  (P2). `verify_entry_activity` needs a redirects-aware exception, not silent orphan errors.

## DD-17 — Rename is a tool + redirects, not a manual grep

- **Decision:** `rename_case.py` moves the file, changes `id`, updates `ref_knowledge`,
  reference `sources[].cases`, fixture `case_id`s, provenance filename/content, appends a
  redirect, and best-effort updates local traces (report only). References/fixtures/usage
  are machine-checked; traces are local and reported. If a sealed fixture changes, the
  tool does **not** reseal; it prints the required `holdout.py --reseal` / `holdout-change`
  step for a maintainer.
- **Rejected:** `rename_ref.py` alone (paths only; does not update IDs/fixtures/usage),
  deleting old IDs (dangling history), rewriting usage rows (double counting risk),
  auto-resealing holdout (defeats the sealed-set gate).
- **Consequence:** redirects are permanent; `verify_references` should resolve through
  them for historical citations or the rename tool must update all of them (tool does).

## DD-18 — E10: period = week-live-MMDD-deployment8

- **Decision:** add `deployment.id` short suffix to the live period; extend
  `verify_metrics.LIVE_PERIOD_RE`; old files stay valid. Two deployments/ clones produce
  distinct period files instead of overwriting one path.
- **Rejected:** relying on `-2` bump (local only, validation report E10), a global
  sequence (server), keeping one file per week (collision).
- **Consequence:** the timeline has multiple live periods in a week (per deployment); the
  trend reader groups by deployment (already documented as per-deployment data).
- **Migration:** old files without suffix remain; no rewrite.

## DD-19 — E11/E12 are P0, not “later”

- **E11:** quote/coerce SHAs; test with `8577483` + `55c20dc`. It crashes the post-merge
  generator, so main stops updating.
- **E12:** add the missing metric(s) to the whitelist/strength registry or stop emitting
  them; test that `metrics_snapshot --emit-yaml` passes `verify_metrics --check`. The
  documented weekly step currently cannot pass CI.
- **Rejected:** documenting a workaround (the data plane stays broken), suppressing the
  validator (field drift across periods).

## DD-20 — Observability is staged behind decisions/event IDs

- **Decision:** no production precision/recall/rework/misdiagnosis numbers until the
  decision files and event IDs exist; first quarter reports are labelled pilot/synthetic.
- **Rejected:** computing from existing data (none of the five has a complete source; see
  report 03 §5), inventing denominators.
- **Consequence:** P2 work; monthly report states data source and sample.

## DD-21 — Adopt sync / PR-search suggestions as O1/O2, not as enforcement

- **Decision:** `kb_sync.py` (fetch/behind/kb_rev/`--require-fresh`) and `pr_radar.py`
  (open PR heads via API or `git ls-remote`/selective fetch) are added to the workflow:
  before diagnosis (check + record), before groom/PR (`--require-fresh`), during groom
  (radar). They reduce stale decisions and catch A’s open PR early.
- **Rejected as sufficient:** “just `git pull`” (window after pull; no enforcement),
  “just search PRs” (network/permissions; PR changes after scan), “update KB before
  diagnosis” alone (does not touch drafts or merge).
- **Evidence:** 378 PR refs visible via `git ls-remote`; one PR head fetched successfully
  in a disposable repo. No claim about GitHub API rate limits or full fetch
  cost yet.
- **Consequence:** the honest guarantee still comes from DD-13; O1/O2 are optional
  prerequisites for quality, not gates.

## DD-22 — Candidate recall is not guaranteed; acceptance uses labelled data

- **Decision:** acceptance requires 9/9 must-review pairs displayed on D1–D11 plus a real
  labelled sample (≥30 pairs) at P1; the report always includes hidden counts and
  “not searched” scopes. Lexical similarity is never called semantic equivalence.
- **Rejected:** claiming “no duplicates” on empty output; tuning to the synthetic set and
  reporting it as production precision.
- **Open:** the real label set must be built by owners; thresholds will be calibrated on it.

## DD-23 — Two panel implementations must pass one contract test (or be consolidated)

- **Decision:** P0 adds fixture-based contract tests for both panels; P2 consolidates to
  one reader/one data shape.
- **Rejected:** changing only one panel (the plan’s own risk list already flags it).
- **Consequence:** panel work is part of A’s estimate, not a footnote.

## DD-24 — Rollout: report-only → required; no big-bang

- **Decision:** Phase 1 (P0) ships scripts and a non-required `merge-recheck` job in
  report-only mode for 1–2 weeks; Phase 2 turns on `kb-required` + approvals + up-to-date;
  Phase 3 P1 features; each phase has a rollback (remove required check, disable job).
- **Rejected:** enabling all required checks on day one (blocks unrelated work, no data on
  false positives); shipping code without platform change (cannot claim protection).
- **Consequence:** the review approves the target and the first phase; not all at once.

---

## Open decisions / assumptions (cannot be settled here)

| # | Question | Why open | Who decides | Needed by |
|---|---|---|---|---|
| O-1 | Approve required checks + 1 approval + up-to-date (merge queue optional P1)? | admin/governance | repo admin + team | Review |
| O-2 | Who are CODEOWNERS / weekly groom reviewer? | ownership | team lead | P0-1 |
| O-3 | Commit sanitized materials or local-only for merged cases? | privacy policy | security/owner | P1-2 |
| O-4 | Display cap 30 / low caps | real groom data | maintainers | P1-1 calibration |
| O-5 | Which real labelled pairs for P1 acceptance? | needs owners | domain owners | P1-1 |
| O-6 | Does PR radar use API token in local workflows? | security/network | team | P1-1 |
| O-7 | Is NFS/SMB supported? | deployment | ops | P0-3 documentation |
| O-8 | Do we accept `local-only` evidence as sufficient for merge? | risk appetite | owner | P1-2 |

## Decision traceability

| Decision | Evidence |
|---|---|
| DD-02/03/04/05 | validation report 03 §1 (13 A tests; identity collision; refinish) |
| DD-06/07/08/09/22 | report 03 §2; `checkpoint-b-findings.json`; `checkpoint-b-v2.json` (design experiment record) |
| DD-10 | `scripts/build_index.py:74,207`, `scripts/_lexical.py:31` |
| DD-11/12/13/14/24 | report 01/03 §3; ruleset API facts; `kb-checks.yml:15-20` |
| DD-15/16/17 | report 03 §4; `provenance-161356.json`; `verify_entry_activity.py:104` |
| DD-18 | report 02 §8; `metrics_snapshot.py:181-207,254`; `verify_metrics.py:94` |
| DD-19 | `e11-sha-type-154622.json`; `id-metrics-154910.json` (E12) |
| DD-21 | `git ls-remote` 378 refs; one PR head fetch |
| DD-23 | `panel-host.js`, `dsh-sleuth-panels/lib/index.js` |








