# 07 — Final assessment

## Decision

**ACCEPT WITH CHANGES.**

V2 is the right direction and the core mechanisms work in narrow prototypes. It is not
ready for production adoption: the decision gate accepts placeholders and is not bound
to the merged bytes; a `reopen` crash can leave two complete drafts; only B was moved
onto the reader; E10's naming fix is not implemented; and GitHub enforcement was not
exercised. These are scoped changes, not a reason to discard the architecture.

The implementation should start with **P0 and an enforcement pilot**, not with a claim
that the current V2 is already protective.

---

## Answers to the required questions

### 1. Does V2 address the original concurrency problems?

It addresses the main mechanism gaps, but not all outcomes:

- **Draft overwrite** (E1) is prevented by UUID directories and atomic `DONE` in the
  prototype. The V1 flat-file race reproduced 10/10; V2 produced 8/8 distinct drafts.
- **Duplicate discovery** (E2/E3) is materially better: 9/9 labelled must-review pairs
  are displayed, including the cross-category D1 and the paraphrased D2.
- **Merge-time revalidation** (E4–E8) is detected by C: same-path, field overlap,
  rename, generated artifacts, stale base, missing decision. Detection is not
  prevention unless the platform gate is enabled.
- **Provenance** is more precise: committed material is hash-checked; local-only is
  labelled, not pretended. Recoverability remains limited to committed material.
- **E10/E13/E14** are not closed by the validated implementation.

### 2. Which E1–E14 failures remain reproducible?

On the current system (production code, not prototypes):

- **E10**: two clones still choose the same live period; the V2 suffix is not
  implemented.
- **E11**: mixed int/str `checkout` still raises `TypeError` at
  `entry_activity.py:495`.
- **E12**: the snapshot still fails its own validator with two errors until the
  whitelist/strength patch is applied.
- **E13**: the ruleset still has 0 required approvals, no required status checks, and no
  up-to-date rule; a stale/red PR can merge.
- **E14**: the inbox has no strict reader in production; V2's reader is a prototype and
  only B uses it.
- **E2–E9**: the production workflow is still V1; the baseline duplicate test at the
  current commit merged both cases with all gates green. V2 prototypes detect these
  cases, but the production path is unchanged.

On the V2 prototypes:

- E1 is prevented for normal completion; the `reopen` crash window is a new failure.
- E2/E3 are surfaced, not prevented.
- E4/E5/E6 are detected; a human decision is required, and a `TODO` decision passes.
- E7 is detected by the heartbeat prototype; the main rebuild job still has no alert.
- E8 is detected when `main_sha` is stale; a changed head after the decision passes.
- E9 is partially checked; rename/usage/refs/fixtures migration is absent.

### 3. Which V1 failures are actually prevented by V2?

Only the draft-overwrite class is clearly prevented in the tested scope (E1), plus the
incomplete/corrupt-consumption class through the strict reader. E2–E8 move from
"invisible" to "detected and requiring a decision"; they are not automatically
prevented. E10–E14 are not prevented by the validated code.

### 4. Are all important duplicate candidates visible?

For the labelled D1–D11 set: **yes, 9/9 must-review pairs are displayed; D11 is not.**
For the real library: **not proven.** Six high pairs are hidden by the global cap and
only counted; the groom does not block on that count. Cross-namespace pairs were not
tested. A fully rephrased duplicate can be missed; lexical similarity is not semantic
equivalence. The report must not say "all duplicates were found".

### 5. Can stale decisions still enter main?

**Yes, in production.** C returns 1 when `main_sha` is stale, but:

- a decision with `TODO` values passes;
- a head change after the decision passes because `head_sha` is not checked;
- the platform does not run C as a required check, has no approval requirement, and
  does not require a branch to be up to date.

The prototype stops a stale base only when the harness chooses to honor exit 1. That is
not a merge block.

### 6. Can knowledge still be silently lost?

**Yes.**

- A `reopen` crash leaves two complete drafts; the reader does not cross-check
  `supersedes`.
- C can detect same-path/field overlap, but a `TODO` decision or a human "keep ours"
  can still discard content; C does not judge semantics.
- Local-only provenance is not recoverable; a case can cite evidence CI cannot see.
- Rename/delete can strand usage/references; the migration tool is absent.

The V2 mechanisms reduce silent loss; they do not eliminate it.

### 7. Is provenance verifiable and recoverable as claimed?

**Verifiable:** for committed material, yes — hash mismatch, missing committed file,
missing verified destination, duplicate independent event ID, broken lineage, and bad
redirect are detected.

**Recoverable:** only for committed, hash-matched material. A local-only or `declared`
artifact is a claim, not a recoverable source. The current manifest can be complete and
still not allow a reviewer to reconstruct the evidence. V2 must state this limitation;
it should not be sold as full evidence recoverability.

### 8. Are references and metrics preserved correctly?

**Partially.**

- References/fixtures were not migrated in this validation; the previous rename
  behavior remains until P1-3.
- E11 and E12 fixes work in a clone; production is not fixed.
- E10 still collides; the V2 naming change is not implemented.
- Usage counts are not transferred; the redirects-aware verifier is absent.
- The integrated run rebuilt indexes after each merge and retrieval found both cases;
  that covers the normal path, not rename/archive/delete.

### 9. Does the integrated workflow pass?

**Conditionally, as a simulation.** A/B drafts were retained; A merged; B's stale
decision was detected; the harness blocked B before the decision; after the decision,
C passed; B merged; the post-merge rebuild succeeded; retrieval found both cases.

It is not a production pass: the required check is simulated, the decision content is
written by the harness, and TODO/head-change bypasses remain. See
`04-integrated-concurrency-tests.md`.

### 10. What are the remaining production risks?

1. Platform enforcement is absent/unverified; a stale or red PR can merge (E13).
2. Decision placeholders and head changes can pass the gate (N2/N3).
3. `reopen` can duplicate a draft (N1).
4. Groom/panels can bypass the reader (N7/N15).
5. Local-only evidence is not recoverable (N8).
6. Rename/usage/reference migration can strand data (N9).
7. B can miss a fully rephrased duplicate and can over-alert on weak root/fix overlap
   (N6/N18).
8. E10 metrics collision remains (N10).
9. E11/E12 production fixes are not landed (N12).
10. Reviewer fatigue from high-priority noise; the decision becomes a rubber stamp.

### 11. What is the minimum implementation scope?

The P0 set in `06-recommendations.md`:

- platform enforcement spike first (`10-platform-enforcement-spike-plan.md`);
- decision binding + placeholder rejection + `same_case` schema + ack count;
- reopen atomicity and reader cross-check;
- reader migration for groom/panels/`sediment_batch`;
- E10/E11/E12 production fixes;
- platform enforcement enablement after the spike.

Without the platform spike/enablement, V2 is a report generator, not a protection
mechanism. Without decision binding and reopen atomicity, the gate can pass a
non-decision and the draft layer can duplicate.

B's hard gate also waits for the observation and batch-collision evidence in
`11-evidence-and-batch-collision-plan.md`; a synthetic 9/9 is not enough to justify it.

### 12. Is V2 ready to present at the review?

**Yes, as an ACCEPT WITH CHANGES proposal.** Present the architecture and the tested
mechanisms, the baseline failures, the 9/9 recall result, the C detection matrix, and
the explicit limits. Do not present V2 as production-ready or as having prevented
E10/E13/E14.

The implementation order is P0 first; P1/P2 follow after the P0 acceptance tests pass.

---

## Readiness matrix

| Area | Status | Basis |
|---|---|---|
| Architecture direction | **PASS** | UUID drafts, one comparator, decision record, provenance split |
| A — identity/atomic publish | **PARTIAL** | 8/8 UUIDs, crash shapes, reopen; reopen window fails |
| B — candidate recall/display | **PARTIAL** | 9/9 labelled displayed; overflow not gated; cross-ns untested |
| C — revalidation | **PARTIAL** | detects stale/path/field/rename/generated; TODO/head bypass |
| Provenance | **PARTIAL** | committed integrity + lineage; local-only not recoverable |
| E10 | **FAIL** | same period still chosen; fix absent |
| E11/E12 | **PASS (prototype)** | current failures reproduced; clone fixes pass |
| E13 enforcement | **UNTESTED** | static ruleset only; no authorized remote test |
| E14 reader | **PARTIAL** | A/B use it; groom/panels not migrated |
| Integrated workflow | **PARTIAL PASS** | simulated gate; real merge/rebuild/retrieval |
| Production readiness | **NOT READY** | P0 items above |

## Evidence index

- Comparison: `01-v1-v2-comparison.md`
- Production workflow and defect tests: `02-production-workflow-tests.md`
- Checkpoints: `03-checkpoint-validation.md`
- Integrated workflow: `04-integrated-concurrency-tests.md`
- New findings: `05-new-findings.md`
- Recommendations: `06-recommendations.md`
- Review summary: `08-friday-review-summary.md`
- Implementation and migration: `09-implementation-design-and-migration.md`
- Platform spike: `10-platform-enforcement-spike-plan.md`
- Evidence and batch collision: `11-evidence-and-batch-collision-plan.md`
- Raw records: `artifacts/logs/`
- Prototypes: `artifacts/proto/`
- Harnesses: `artifacts/scripts/`
