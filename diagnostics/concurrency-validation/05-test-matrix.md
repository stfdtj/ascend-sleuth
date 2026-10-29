# 05 — Test matrix

Columns: **Scenario** — what was exercised; **Baseline** — result with the system as
implemented; **Proposed solution** — result with the Stage II prototype or the
plan's mechanism; **Evidence** — record + step (all under `artifacts/logs/`);
**Remaining risk** — what the test does not settle.

`PASS`/`PARTIAL`/`FAIL` in the proposed column follow report 03's classification.
"Not tested" is used where a mechanism needs a platform or a host that is unavailable.

## 1. Original ten issues

| Scenario | Baseline | Proposed solution | Evidence | Remaining risk |
|---|---|---|---|---|
| E1 same-name draft overwrite, two writers in one inbox | 10/10 rounds one writer survives; 3/3 chunked rounds produce mixed YAML that still parses; control with different IDs fine | A: exclusive `mkdir` loop → 8/8 unique; naive scan-then-create control collapses to 1 dir | `inbox-race-153215.json`; `test_inbox_put.console.txt` | protocol is bypassable by writing files directly; panel readers ×2; collision across clones remains |
| E1b crash during draft creation | empty dir / half file / truncated valid-YAML DONE | A: all three are `incomplete`/`corrupt`; strict reader never consumes; `finish` refuses | `test_inbox_put.console.txt` (13 tests OK) | a crash *after* a correct DONE but before publish of a revision is not modelled; re-finish legitimises edits |
| E1c half set (case.yaml, no postmortem.md) | passes `verify_case_draft`; nothing requires the pair | A requires three files | `inbox-race-153215.json` (half set step); `test_inbox_put.py` | a user can still ignore the `.md` content; A validates presence, not usefulness |
| E2 duplicate cases under different IDs, separate clones | both orders merge with 0 conflicts; all gates green; both IDs active | B: generated for this pair (same cell, D1↔90002), but the cross-category pair D1↔90001 is generated and **not displayed** at the cap | `engineers-154251.json` (ORDER COMPARISON); `checkpoint-b-findings.json` | paraphrased duplicates are missed (D2); the cap can hide the true duplicate; reviewer behaviour not measured |
| E3 cross-classification duplicates | pre-triage reads only the (ns × category) view; B's view lacks A's ID; A's clone absent | B: rule 5 generates the pair (`same-namespace-cross-category`), display cap drops it; if the namespace differs (training vs inference), no rule applies | `engineers-154251.json` (B pre-triage); `checkpoint-b-findings.json` | cross-namespace duplicates are not covered at all; `sources.yaml` has no namespace/category field |
| E4 same path / same ID conflict | `CONFLICT (add/add)` on the case file; Git is the only signal | C: reports `same_path_added_both` and `added_both`; still a human merge | `engineers-154251.json` (same-path); `checkpoint-c-160531.json` (C2) | C cannot choose; conflict resolution quality unmeasured |
| E5 losing one side during resolution | taking ours removes B's root cause; all seven gates green | C: shows both sides + decision fields; no check verifies that both sides were considered; no enforcement | `engineers-154251.json`; `checkpoint-c-160531.json` (C3) | unless the decision record is machine-checked, a "we considered it" narrative is unfalsifiable |
| E6 clean merge, contradictory content | disjoint edits merge clean; gates green; file contradicts itself | C: only says `modified_both`/`same_path_differing`; no field-level contradiction check. B's six-axis is between records, not versions | `engineers-154251.json` (E6); `checkpoint-c-160531.json` (C5) | semantic contradiction cannot be mechanically judged; the decision record is the only lever |
| E7 generated-artifact conflicts | source-only PRs: 0 generated conflicts; guard rejects hand edits; the post-merge job runs succeed for the inspected runs (six in total) | Plan's "job rebuilds main" verified statically + by running the job body locally; guard verified | `engineers-154251.json` (E7); GitHub Actions API + `rebuild-generated.yml:57-87` | no-job deployments go stale with a red `build_index --check` and no CI signal (`E7-nojob`); `DEPLOY_KEY`/ruleset bypass are deployment facts |
| E8 stale duplicate conclusion before merge | B's clone never has A; no recheck script exists; merge succeeds, gates green | C: `stale.matches_current=false` after main advances/rebase; report SHAs can be checked by eye; nothing blocks | `engineers-154251.json` (stale-check); `checkpoint-c-160531.json` (C8) | detection only; `verify_pr_body` accepts old SHAs (executed) |
| E9 ID change breaks refs/fixtures/usage/traces/metrics | refs red, usage red, fixture warn, trace untouched, index green after rebuild; delete strands both IDs; archive keeps double counts and stays green | Provenance + rename tool: material-level attribution works; field-level/rename/dropped-path checks absent; no CI reads the sidecar | `id-metrics-154910.json`; `provenance-161356.json` | counts transfer semantics undefined; archive path hides the problem; traces are local-only |
| E10 same-period snapshot collision | both machines pick `2026-W44-live-1028`, different readings; add/add conflict; resolve → timeline check green; metrics check red only for E12's field/strength mismatch, not for the missing reading; no gap check | Not addressed by A/B/C; the plan's §5.4 is a manual procedure. Prototype confirms the collision and the silence | `id-metrics-154910.json` | deployment-scoped period naming is a schema change the plan defers; old snapshots remain ambiguous |

## 2. Newly discovered issues

| Scenario | Baseline | Proposed solution | Evidence | Remaining risk |
|---|---|---|---|---|
| E11 all-digit short SHA in usage rows | `TypeError` in `entry_activity.aggregate` when a str and an int SHA coexist; `verify_entry_activity` passes; post-merge job dies | Not in the plan. Prototype fix: quote/coerce SHAs; regression test | `e11-sha-type-154622.json` | any other numeric-looking scalar in a row can repeat this class (run ids, counts) |
| E12 weekly snapshot vs validator | generator emits `external_record_violations_total` (not whitelisted) + six metrics without strength; CI red | Not addressed; small fix needed | `id-metrics-154910.json` (verify_metrics after rebuild) | strength registry additions become maintenance; the "human review" step still needs a checklist |
| E13 repository protection vs docs | ruleset: PR required, 0 approvals, no required checks, no up-to-date; docs say "not enabled" | Plan's "parallel platform configuration" is a prerequisite, not a parallel nicety | public GitHub API (`branches/main`, `rulesets/25950697`) | API facts may change; admin action not exercised |
| E14 inbox has no reader contract | half set passes; truncated/mixed files only caught if the check is run | A defines reader states but consumers (groom, panels, B) must all adopt them; B currently ignores DONE (executed: inputs 11→12) | `test_inbox_put.console.txt`; `test_find_duplicates.console.txt` | a consumer that reads files without the reader reintroduces the old behaviour |

## 3. Proposal acceptance criteria (plan §10)

| Criterion | Result | Evidence | Gap |
|---|---|---|---|
| A: two processes write the same draft, both preserved | PASS (8/8 unique dirs; no overwrite) | `test_inbox_put.console.txt` | only with the prototype; not wired into the skills |
| A: interrupted dirs not consumed | PASS (strict reader; three crash shapes) | same | reader contract must be adopted by every consumer |
| A: legacy flat drafts still readable | PASS (listed as legacy) | same | groom/panel read path not changed/tested |
| A: panel sees the new format | UNTESTED (two implementations exist; no DSH host here) | `test_inbox_put.py` panel test (static only) | risk of one panel missing new drafts |
| B: cross-category, shared-source, same-ID pairs appear | PARTIAL: generated 9/10; displayed 6/10 at the cap | `checkpoint-b-findings.json` | display cap can hide cross-category; paraphrased miss |
| B: structural contradiction fires on E6 | PASS on the synthetic equivalent (D3/D8): `same-check-two-fixes` + disjoint ranges | `checkpoint-b-findings.json` | E6's actual contradiction (compat vs a diagnosis step) is not one of the five rules |
| B: same signature, different root cause not judged duplicate | PASS (hint only; no hard error) | same | a reviewer may still merge; no decision record |
| C: A merged after B's report ⇒ report identified as stale | PASS (SHA mismatch detected) | `checkpoint-c-160531.json` (C2/C8) | detection only; merge still succeeds |
| C: same-path conflict keeps both versions | PARTIAL: recheck shows both sides; the conflict resolution can still discard one | `checkpoint-c-160531.json` (C2/C3) | no enforcement; no content-level check |
| C: report SHAs equal the merged commits | PASS as detection; FAIL as a gate | `checkpoint-c-160531.json` (C8); `verify_pr_body` accepts old SHA | no CI binding; platform allows stale branch |
| Provenance: "where did the other material go" | PARTIAL: materials + dropped destinations exist; destination not checked; archive keeps counts | `provenance-161356.json` | no checker; rename orphans the sidecar |
| Provenance: ID change checked across refs/fixtures/usage/traces | PARTIAL: refs/usage hard, fixtures warn, traces/provenance unchecked | `id-metrics-154910.json` | local traces have no CI and no migration tooling |
| Observability: candidate precision, rework, post-merge misdiagnosis | FAIL: no decision record, no merge record, no event ids | `provenance-161356.json` | needs data collection first; do not publish production numbers |

## 4. Additional concurrency / crash / identity tests (not in the ten)

| Scenario | Baseline | Proposed | Evidence | Remaining risk |
|---|---|---|---|---|
| 8 simultaneous draft creators | (no protocol) | 8/8 unique | `test_inbox_put.console.txt` | NTFS/local FS only; NFS/SMB `mkdir` semantics not tested |
| naive check-then-act control | 1 dir, 1 survivor | exclusive create avoids it | same | an implementation that scans before mkdir reintroduces it; the plan must keep the mkdir loop explicit |
| two clones, same draft id | both produce `...-001`; labels differ by default | explicit shared deployment id collides; random id needed | same | a copied `deployment.yaml` can still collide unless the id is random |
| checkout rename | fallback label changes; explicit id stable | provenance keyed by id survives; keyed by name does not | same | no migration for old names |
| re-finish after edit | (no protocol) | plain finish refuses; `--refinish` re-stamps and the reader accepts | same | explicit re-finish has no revision history |
| merge order A→B vs B→A | 0 conflicts, all gates green, both IDs present in both orders | same (no mechanism changes order) | `engineers-154251.json` | order only matters for who reviews; the duplicate is order-independent |
| main advances + branch rebase after recheck | report stale; merge still succeeds | C detects stale; no enforcement | `checkpoint-c-160531.json` (C8) | merge queue/up-to-date rule required |
| generated artifacts in PR | guard rejects | same | `checkpoint-c-160531.json` (C7) | other platforms need the same call; doc says so |
| renaming a case while another PR references it | C detects rename + dangling mention; merge clean; index red only for staleness | C report lists it | `checkpoint-c-160531.json` (C6) | no check scans free-text references; a name in prose is not machine-readable |
| archive instead of delete after merge | checks green, both IDs keep counts | provenance would need to force a transfer decision | `provenance-161356.json` | the plan does not define count migration; "archive" is the silent path |

## 5. Not tested (state, not omission)

- GitHub Actions/branch-protection enforcement of any proposed check (no `gh`, no PRs
  created; public API facts only).
- The DSh panel host with group drafts (`panel-host.js`,
  `dsh-sleuth-panels/lib/index.js`); only static structure was inspected.
- `issue-ingest` and `to-reference` end-to-end (no `gh`, no external issue source).
- Two real deployments with distinct `deployment.yaml` files, exchanging a draft.
- Scale: 171 cases / 11 drafts; a 10× library and 50 concurrent drafts may change
  candidate volume, runtime and reviewer load.
- Human review time and error rate: the plan's 1–2 min/pair is an estimate, not a
  measurement.
- Cross-platform: experiments ran on Windows/NTFS; Linux `flock`/`rename` semantics and
  NFS behaviour were not exercised.

## 6. Evidence index

| File | Contents |
|---|---|
| `artifacts/logs/e2e-baseline-153803.json` | single-engineer E2E: all gates, generated diff, post-merge job, retrieval |
| `artifacts/logs/engineers-154251.json` | two clones, both merge orders, pre-triage blind spot, E4/E5, E6, E7, E8 |
| `artifacts/logs/inbox-race-153215.json` | shared inbox, 10 small rounds, 3 chunked rounds, kill test, half set, control |
| `artifacts/logs/id-metrics-154910.json` | E9 rename (refs/usage/fixture/trace), delete vs archive, E10 collision |
| `artifacts/logs/e11-sha-type-154622.json` | E11 crash and the quoted-SHA fix |
| `artifacts/logs/checkpoint-b-findings.json` | B: generated vs displayed, all pairs, axes, hints, unshown count |
| `artifacts/logs/checkpoint-c-160531.json` | C1–C9, stale SHA detection, dangling rename, generated artifacts |
| `artifacts/logs/provenance-161356.json` | provenance questions, archive double count, observability data audit |
| `artifacts/logs/test_inbox_put.console.txt` | 13 A tests |
| `artifacts/logs/test_merge_recheck.console.txt` | C runs |
| `artifacts/logs/c-report-before-merge.txt`, `c-report-toctou.txt` | the actual report text C produces |
| `artifacts/proto/*.py` | prototypes (A/B/C, inline E11 test) |
| `artifacts/scripts/*.py` | harnesses for every Stage I/II experiment |
