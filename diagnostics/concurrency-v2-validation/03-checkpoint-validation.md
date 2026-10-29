# 03 — Checkpoint and provenance validation

Classification: **PASS** (executed, required behavior shown in the tested scope),
**PARTIAL**, **FAIL** (a reproduced counterexample), **UNTESTED**, **N/A**.
Prototype code is under `artifacts/proto/`; it is not production code.

---

## A. Checkpoint A — draft identity and atomic publication

**Verdict: PARTIAL** (core PASS; reopen atomicity and consumer migration incomplete).

Prototype: `draft_queue.py` (reader), `inbox_v2.py` (new/finish/reopen/abort/list).
Record: `v2-a-030836.json`.

| Test | Result | Evidence |
|---|---|---|
| 8 simultaneous creators | PASS: 8 dirs, 8 UUIDs | `v2-a-030836.json`, step 1 |
| UUID identity across two clones with the same deployment id | PASS: distinct UUIDs | same |
| Concurrent flat writers (V1 control) | 10/10 rounds one survivor | `v2-s1-025934.json` |
| Complete draft + `DONE` hash | PASS: `complete` | `v2-a-030836.json` |
| Repeated finish | PASS: refused (`DONE already exists`) | same |
| Edit after completion | PASS: `corrupt` (hash mismatch) | same |
| Crash after mkdir / partial file / truncated DONE | PASS: `incomplete` / `incomplete` / `corrupt` | same |
| Reopen | PASS: old `superseded`, new `complete`, `supersedes` set | same |
| Reopen crash window (new complete, old marker missing) | **FAIL**: both are `complete`; reader does not cross-check `supersedes` | same, step "reopen crash window" |
| Copied draft with renamed directory | PASS by design: `corrupt` (`draft_id` mismatch) | same |
| Legacy flat draft | PASS: listed as `legacy_flat` | same |
| Draft case accepted by real validator | PASS: `verify_case_draft` 0 | same |
| Groom and both panels honor the reader | **UNTESTED**: B uses the reader; groom/panel migration was not built | code inspection; B test |

Why PARTIAL: the reader contract exists and B honors it, but the two panels and groom
were not migrated in this validation. A bypass remains possible if any consumer reads
files directly. The reopen window is a real race: the new draft is published before the
old marker, so a crash leaves two consumable drafts; the reader should treat a draft as
superseded when another complete draft declares `supersedes: <this>`, or the marker
must be written first (which creates the inverse window: old suppressed, new missing —
that is recoverable and should be preferred).

---

## B. Checkpoint B — duplicate discovery

**Verdict: PARTIAL** (labelled recall PASS; overflow gate and cross-namespace not).

Prototype: `find_duplicates_v2.py`; record `v2-b-024503.json`. Inputs: the 11 labelled
drafts copied into UUID directories (unique sessions, D9 keeps the shared evidence
reference) against the real 173-case library plus the two synthetic cases.

### B.1 D1–D11

| Target | Expected | Observed | Tier | Displayed |
|---|---|---|---|---|
| D1 cross-category same root | surface | yes | high | yes |
| D2 paraphrased (same root/fix text) | surface | yes | high | yes |
| D3 same signature, different root | surface + hint | yes | mandatory | yes |
| D4/D5 same upstream, two problems | surface + hint | yes | mandatory (draft-draft) | yes |
| D6 same fix, different version | surface + hint | yes | high | yes |
| D7 overlapping conditions | surface | yes | high | yes |
| D8 contradictory fix, disjoint condition | surface + hints | yes | mandatory | yes |
| D9 same verification event | surface | yes | high (fixture has only session; event-id mandatory is design) | yes |
| D10 same diagnosis, different sessions | surface | yes | high | yes |
| D11 unrelated control | not shown | not shown | — | no |

Counts: drafts 11, library 173, generated **327**, mandatory **6**, high **36**,
low **285**, displayed **46**, hidden high **6**, hidden low **275**.
With `--high-cap 2`: displayed 18, hidden high 34 — the cap behavior is explicit.

### B.2 What works

- mandatory (shared upstream, same ID/path/event, strong discriminator) is never
  subject to the display cap;
- D2 is now generated via root/fix overlap (the V1 miss);
- D1 is generated and displayed across categories;
- low-value lexical pairs are capped (2/draft, 10 global) and counted as unreviewed;
- hidden high is counted per draft.

### B.3 What is not sufficient

1. **Hidden high is not blocked at groom.** B reports `hidden_high=6`; no groom gate
   prevents promotion or requires an ack. The V2 design says it must; the prototype
   only reports. At merge, C checks `overflow.ack` only if the same pair set appears
   (N5).
2. **High-priority false positives.** C's same-case scenario produced high pairs with
   symptom score `0.087` and `0.043` because root/fix overlap passed the threshold;
   this forces decisions on unrelated cases and increases fatigue (N6).
3. **Cross-namespace** training↔inference was not exercised; the wildcard rule is
   design only.
4. **Event-ID evidence** is in the provenance prototype, not in the library; D9 used
   session overlap, not event identity. The same-event mandatory rule is UNTESTED.
5. **Same-path** is not effective for UUID drafts (`inbox/<uuid>/case.yaml` vs
   knowledge path); it is meaningful for C/changed inputs. This is documented in V2,
   but the original "always surfaces same path" acceptance criterion needs that nuance.
6. **Recall is not guaranteed.** A duplicate whose title, symptoms, root cause and fix
   are all rephrased will not be generated. No lexical system can claim complete
   semantic recall; the report must not say "no duplicates".

---

## C. Checkpoint C — revalidation and enforcement

**Verdict: PARTIAL** (detection PASS; decision enforcement has bypasses; GitHub
enforcement UNTESTED).

Prototype: `merge_recheck_v2.py` + `case_diff.py`; record `v2-c-030729.json`.

| Scenario | Exit | Behavior |
|---|---|---|
| Different IDs, same problem, no decision | 2 | mandatory pair; blocked in the harness |
| Same + complete decision | 0 | pair coverage and `main_sha` pass |
| Decision pair value `TODO` | **0** | placeholder accepted (N2) |
| Head changed after decision | **0** | `head_sha` recorded but not checked (N3) |
| Main advanced after decision | 1 | stale `main_sha`; new pair missing |
| Refresh decision | 0 | coverage updated |
| Same-path add/add | 3 | path + field overlap |
| Both modify same case, disjoint fields, no decision | 2 | `both_modified` requires decision |
| Same + `same_case` decision | 0 | disjoint fields accepted |
| `same_case.decision = TODO` | **0** | placeholder accepted (N2) |
| Generated artifact | 4 | `knowledge/_index.yaml` |
| Rename + reference on the other side | 3 | renamed ID + dangling mention |

### C.1 What C guarantees (in the prototype)

- it computes the actual merge base and both sides' changes;
- it catches same-path add/add, same-case field overlap, rename/delete hazards,
  generated artifacts, missing decision coverage, and stale base;
- it reuses the B comparator (no second detector).

### C.2 What it does not guarantee

- **No GitHub enforcement.** The harness blocks the merge when C is non-zero; no
  required check/ruleset/approval/up-to-date was exercised. This is the largest
  **UNTESTED** item.
- **Placeholder decisions pass** (`TODO`), and **head changes after the decision pass**
  because `head_sha` is not enforced. The decision is not bound to the content that is
  being merged.
- **Same-case decision is not in the V2 schema.** The prototype added `same_case`; the
  V2 document only defines `pairs` + `overflow`. Without it, a same-case disjoint-field
  change has no place to record the decision.
- **Semantic contradiction is not judged.** A mechanically clean merge with
  incompatible conditions still needs a human; C can only force a decision.
- **Overflow ack is not validated**: the prototype checks that `overflow.ack` is
  truthy, not that its `hidden_count` matches the current hidden count.
- **C assumes `--base` is the latest main.** If CI passes an old base, the same
  comparison can pass on stale data. The design must make the base explicit and
  required (up-to-date/merge queue).

---

## D. Provenance

**Verdict: PARTIAL** (checkable manifest; recoverability only for committed material;
rename/usage/refs/fixtures not implemented).

Prototype: `provenance_check.py`; record `v2-provenance-030157.json`.

| Test | Result |
|---|---|
| Valid manifest with committed material + matching hash | PASS (0 errors) |
| Altered committed material | PASS as a check: hash mismatch detected |
| Missing local-only material | PASS with warning; **not recoverable/verified** |
| Dropped destination marked `verified` but missing | detected (error) |
| Dropped content marked `declared` | accepted with warning |
| Multi-source field without `merged` | detected |
| Same event ID independently claimed by two cases | detected |
| `merged_into` target exists | pass |
| Redirect old→new with existing new | pass; old active is a warning |

What this means:

- **Traceability** is always recorded (case, materials, draft UUID, session,
  deployment, event IDs, lineage).
- **Integrity** is verified only for `committed: true` files. A hash of a local-only
  file is a claim; CI cannot read it.
- **Recoverability** is `verified` only when the destination is committed and
  hash-matched; `declared`/`local-only` are explicitly not recoverable by CI.
- **Evidence independence** is a human assertion; the checker can only detect the same
  `event_id` being marked independent in two manifests. Without a real event ID on the
  library side, this is not reliable.
- The **rename tool** and **redirects-aware `verify_entry_activity`** are not
  implemented; references/fixtures/usage migration is not exercised. The checker can
  validate lineage/redirects if they are written correctly, but nothing writes them.
- **Field attribution** is top-level only; a multi-source field is flagged, but the
  checker cannot prove which bytes came from which draft.
- **Usage counts** are not migrated; the previous baseline finding (orphan rows red on
  delete, archive keeps both counts) is unchanged. V2's `incident_key` view is design
  only.

---

## E. E10–E14 re-test

| ID | Current behavior | V2/prototype | Verdict |
|---|---|---|---|
| E10 | Two clones choose the same `2026-W44-live-1029` period | suffix design only | **FAIL/UNTESTED** — no fix implemented |
| E11 | `TypeError` with int/str `checkout` | coerce-to-str prototype passes | **PASS (prototype)** |
| E12 | snapshot output fails validator (2 errors) | whitelist/strength prototype passes | **PASS (prototype)** |
| E13 | ruleset: PR only, 0 approvals, no required checks, no up-to-date | required aggregator/approval/up-to-date design | **UNTESTED** — no authorized remote test |
| E14 | no strict inbox reader | A reader prototype; B honors it | **PARTIAL** — groom/panels not migrated |

---

## F. Limitations

- The library is 173 cases; performance at 10× and 50 drafts is not measured.
- The B fixtures are synthetic; root/fix text is more similar than in production, so
  recall/workload numbers are optimistic.
- The C tests use local branches, not GitHub PRs; required-check and approval behavior
  is not exercised.
- The two panel implementations were inspected, not executed (no DSH host).
- NFS/SMB and Linux `flock` semantics were not tested; experiments ran on Windows/NTFS.
- Human review quality is not measured; only the decision-coverage mechanics are.
