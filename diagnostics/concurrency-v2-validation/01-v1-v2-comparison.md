# 01 — V1 → V2 comparison

Validation baseline: current `main` = `dd3e6b3` (the previous investigation used `28adab0`;
the diff between the two is limited to `dsh-plugins/dsh-sleuth-vllm-kb/**` and
`scripts/check_vllm_kb.js`, so the knowledge workflow scripts are byte-identical).
All V2 prototypes are under `artifacts/proto/`; all harnesses under `artifacts/scripts/`;
all records under `artifacts/logs/`.

Legend: **V1** = current production behavior (also the baseline that was re-run here);
**V2** = the proposal in `research/2026-10-29-concurrency-plan-v2.md` plus this
validation's narrow prototypes.

| Mechanism | V1 design | V1 experimental failure | V2 modification | Expected protection | V2 validation result |
|---|---|---|---|---|---|
| Draft identity | `postmortems/inbox/<case-id>.case.yaml` + `.md`; case ID chosen by the author | Same ID in one inbox: 10/10 rounds one writer's bytes replaced the other; files remained valid YAML | UUID directory `inbox/<uuid>/`; `DONE` with sha256; one reader; immutable completion; `reopen` creates a new UUID | No overwrite; no incomplete/corrupt consumption; identity survives clones/copies/renames | **PASS (core)** — 8/8 concurrent UUIDs; crash shapes rejected; hash mismatch rejected; reopen works. **PARTIAL overall** — a crash window between new DONE and old `SUPERSEDED` leaves two `complete` drafts (finding N1) |
| Reader contract | No reader; groom/to-postmortem/panels each read files | Half set passed `verify_case_draft`; B loaded incomplete drafts | `draft_queue.py` states `complete/incomplete/corrupt/superseded/legacy_flat`; all consumers must use it | One contract; no bypass | **PARTIAL** — B honors it and excluded an incomplete draft; groom and the two panels were not rewired/tested |
| Draft identity vs deployment | `(deployment, draft_id)` proposed in V1 | Two clones with the same label collide; rename changes fallback label | Draft = UUID; `deployment.id` only for provenance/diagnostics | Global draft identity without deployment coupling | **PASS** — two clones with the same `deployment.id` produced distinct UUIDs; copied draft under a renamed directory is `corrupt` by design |
| Legacy drafts | Flat files are the only format | — | Flat files remain `legacy_flat`, accepted with warning; no migration | Backward compatibility | **PASS** — listed and readable; B can include them (not exercised with a populated legacy set) |
| B candidate generation | One list from cell view + ad-hoc similarity; 101 candidates for 11 drafts; 9/10 must-review generated, 6/10 displayed | Cross-category pair hidden by cap; paraphrase missed | Generation vs display; mandatory/high/low; root/fix/expected/event signals; global high cap; low watchlist | 9/9 must-review displayed; D11 not; bounded workload; no silent high-priority hiding | **PASS for the labelled set** — 9/9 displayed; D11 absent; mandatory 6, high 36, low 285, displayed 46, hidden_high 6, hidden_low 275. **PARTIAL** — the 6 hidden high pairs are only reported by B; the groom-time ack gate is not implemented; high-priority false positives observed |
| B cross-category | Per-cell only | E3: same root cause in another category invisible | Same-namespace cross-category rule; `common/` always | Cross-category candidate | **PASS** — D1 (interrupt vs precision) displayed. Cross-namespace training↔inference is **UNTESTED**; the wildcard rule is design only |
| B evidence reuse | No event identity | E9/duplicate evidence | Event IDs in provenance; same-session high, same-event mandatory | Evidence reuse surfaced | **PARTIAL** — same-session high (D9) displayed; event IDs are only in the provenance prototype; no library case has one, so same-event mandatory was not exercised |
| B display/overflow | One top-N cap | 6/10 displayed; hidden pair counted only | Mandatory all; high global cap 30; low 2/draft + 10 global; hidden counts; ack | High-priority overflow blocks/acknowledges | **PARTIAL** — B reports 6 hidden high; the groom does not block; C checks an `overflow.ack` only when the same pairs appear at merge time (not tested with >30 high) |
| B/C comparator | Two separate algorithms | Duplicate logic drift | One `case_match`/`find_duplicates_v2` reused by `merge_recheck_v2` | One source of truth | **PASS** — C calls the B comparator; no second detector |
| C revalidation | Report with SHAs; no enforcement | C8 merged with stale report; PR body with old SHA passed | Explicit base/head; field diff; decision coverage; base freshness; exit codes; blocked simulation | Detect stale decisions; require decision before integration | **PARTIAL** — C returns 1 on stale base, 2 on missing decision, 3 on path/field/rename, 4 on generated; decision passes at 0. **TODO and head-SHA gaps** (N2/N3); GitHub enforcement **UNTESTED** |
| C same-case fields | Whole-file keep-one-side | E5/E6 lost content/contradiction; gates green | `case_diff.py` per-field diff; `same_case` decision | Force a decision; no silent take-one-side | **PASS for detection** — overlapping fields → 3; disjoint fields → 2 without decision, 0 with `same_case`; semantic correctness remains human |
| Decision record | None | Review notes not machine-readable | `postmortems/decisions/<case>.yaml`; pair IDs, tier, decision, note, main/head SHA, overflow ack | Coverage + freshness; audit trail | **PARTIAL** — coverage/freshness work; `TODO` and empty notes pass; `head_sha` is not checked; `same_case` is not in the V2 design schema (prototype extension) |
| Provenance | None | Local drafts/traces unverifiable; hash-only claims in V1 | Committed manifest; optional committed material; `local-only/declared`; event IDs; lineage; redirects | Traceability always; integrity/recoverability only when accessible | **PARTIAL** — committed hash changes detected; missing committed/dropped destinations detected; duplicate independent event IDs detected; lineage/redirects pass. Local-only is a warning, not recoverability; rename tool/usage/refs/fixtures migration not implemented |
| Usage counts | Per case ID; append-only | Rename strands counts; archive double-counts; gates green | No count transfer; `redirects.yaml`; `incident_key` for incident-level metrics | No double count; historical usage preserved | **UNTESTED** — no redirects-aware `verify_entry_activity` prototype; the previous baseline behavior (orphan/red or archive/green with both counts) remains |
| E10 period collision | `YYYY-Www-live-MMDD` from local checkout | Two clones choose the same period; different readings; conflict; no gap check | Add deployment id suffix; extend live-period regex; keep old files | No collision across deployments | **UNTESTED / PARTIAL** — current code still chooses the same period in two clones (`2026-W44-live-1029`); the V2 naming change is not implemented |
| E11 numeric SHA | `settle_trace_feedback` writes unquoted SHA; `entry_activity` sorts | `TypeError` on mixed int/str; post-merge job dies | Quote/coerce; regression test | Generator never crashes on an all-digit SHA | **PASS (prototype)** — current code raises `TypeError`; the one-line coerce fix makes the generator pass |
| E12 snapshot/validator | Snapshot emits fields outside live whitelist/strength registry | `verify_metrics --check` red after the documented weekly step | Add `external_record_violations_total` to whitelist and six metrics to strength registry (or stop emitting them) | Snapshot output passes its own validator | **PASS (prototype)** — current snapshot produces 2 validator errors; the prototype whitelist/strength patch makes it pass |
| E13 merge protection | Ruleset requires PR only | 0 approvals, no required checks, no up-to-date | Required `kb-required` aggregator, 1 non-author approval, up-to-date (queue optional), bot bypass | Stale/red PR cannot merge | **UNTESTED** — static API facts only; no authorized test repository, no ruleset change |
| E14 inbox reader | No strict contract | Half set/mixture/truncated DONE | Same as A reader | Strict consumption | **PARTIAL** — reader works; groom/panel migration not done |

## What V2 actually changes

1. **Identity**: the draft is no longer keyed by the case ID or a deployment label. It is a
   UUID; completion is a separate atomic marker; correction is a new draft (`reopen`).
2. **Two-layer candidates**: generation is separated from what a reviewer sees; mandatory
   pairs cannot be capped; high overflow is counted and must be acknowledged; low pairs
   are an explicitly unreviewed watchlist.
3. **One comparator**: C reuses B; it does not implement a second duplicate detector.
4. **Decision as data**: a committed YAML record replaces prose; CI can check coverage
   and freshness (but not truth).
5. **Provenance split**: only accessible material is hashed/verified; local-only
   evidence is labelled, not pretended.
6. **Enforcement is separate from reporting**: the design correctly says required checks
   + approvals + up-to-date/merge queue are necessary. This validation could not exercise
   them; it is the largest remaining blocker.

## What the previous report said vs what this validation found

| Previous conclusion | This validation |
|---|---|
| V2 A would prevent draft loss | Core yes; **reopen crash window** can still leave two complete drafts (N1) |
| V2 B would display 9/10 | It displays 9/9 on the labelled set, but 6 high pairs are hidden at the cap and only reported; groom does not block (N5) |
| V2 C detects stale decisions | Detection works; **TODO decisions** and **head changes after the decision** pass (N2/N3) |
| V2 provenance claims | Checker enforces committed/local-only distinctions; **local-only is still not recoverable**; rename/usage migration absent |
| E10/E11/E12 are addressed | E11/E12 fixes work in a clone; **E10 naming is not implemented** |
| Platform enforcement is required | Confirmed; **not exercised**; cannot claim protection |

## Evidence

- `artifacts/logs/v2-stage1-025922.json` — current workflow control.
- `artifacts/logs/v2-baseline-duplicate-030450.json` — two clones, duplicate enters.
- `artifacts/logs/v2-a-030836.json` — A tests including the reopen window.
- `artifacts/logs/v2-b-024503.json` — B D1–D11 and overflow.
- `artifacts/logs/v2-c-030729.json` — C scenarios, TODO/head-SHA/same-case.
- `artifacts/logs/v2-provenance-030157.json` — provenance checks.
- `artifacts/logs/v2-defects-025306.json` — E11/E12.
- `artifacts/logs/v2-integrated-025550.json` — integrated A/B workflow.
