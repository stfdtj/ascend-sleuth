# 04 — Integrated two-engineer concurrency test

Harness: `artifacts/scripts/run_integrated_v2.py`; record
`artifacts/logs/v2-integrated-025550.json`.
Baseline comparison: `artifacts/logs/v2-baseline-duplicate-030450.json`.
This is the most important test: it connects A, B, C, the PR sequence, the post-merge
rebuild, and retrieval in one workflow.

---

## 1. Scenario

Two independent clones at the same `main` (`dd3e6b3`):

- **A** diagnoses 310P bf16 startup failure and creates `VLLM-ASC-96001`
  (`interrupt`), draft UUID `e9d4c0f5-…`.
- **B** diagnoses the same root cause as zero output and creates `VLLM-ASC-96002`
  (`precision`), draft UUID `82423c6d-…`.
- Both drafts are written through the V2 A prototype (`new` → case/postmortem →
  `finish`), so both are `complete` and independently retained.
- B's initial groom runs against main only. A's branch is not merged and B does not
  fetch it, so B's first decision contains no pair (the realistic "stale groom" state).
- A's branch is merged first; the post-merge rebuild runs and main advances.
- B fetches, rebases onto the advanced main, and runs Checkpoint C.

A human/reviewer decision is simulated: the harness writes the decision file. The
decision *content* is not judged by C; only coverage/freshness is.

## 2. Before/after

### Baseline (no V2 gate)

`v2-baseline-duplicate-030450.json`: two clones add `VLLM-ASC-97001` (interrupt) and
`VLLM-ASC-97002` (precision) for the same root cause; merge A then B; rebuild each;
all gates green; both IDs are in `_index.yaml`. **No decision, no duplicate alert.**

### V2 integrated

| Step | Result |
|---|---|
| A/B drafts complete | 0; both UUID dirs retained |
| A merge | 0; `VLLM-ASC-96001` enters main |
| A post-merge rebuild | 0; generated artifacts committed |
| B rebase | clean |
| C before refresh | **exit 1** (`main_sha` stale; new pair with 96001 missing) |
| Simulated required check | **merge blocked** (harness does not merge on non-zero C) |
| B decision refresh | pairs added: `96002 ↔ 96001` mandatory; `96002 ↔ 10303` high; `main_sha` updated |
| C after refresh | **exit 0** |
| Simulated required check | **not blocked** |
| B merge | 0; case + decision file enter main |
| Post-merge rebuild | 0; generated artifacts committed |
| Retrieval | both `VLLM-ASC-96001` and `VLLM-ASC-96002` present |

The integrated test therefore changes the outcome from "both merge unconditionally" to
"B must see the new pair and record a decision before the simulated gate permits
merge". It does **not** prove that B's decision is semantically right (the harness
wrote `separate`), and it does **not** prove GitHub would block the merge: the required
check is simulated.

## 3. What the integrated workflow demonstrates

1. **A works with real workflow structure**: UUID drafts, completion, and the promoted
   case coexist with the existing knowledge tree.
2. **B's stale state is real**: B's original decision has no pair because it did not
   see A; C detects both the stale base and the new mandatory pair.
3. **C is the integration point**: it uses the same comparator as B; one pair ID is
   shared; the decision is a file in Git, not prose.
4. **Post-merge generated artifacts still work**: the rebuild after A and after B
   succeeds; retrieval sees both cases.
5. **The gate is conditional on the platform**: the harness blocks, but no GitHub
   ruleset/required check/approval/up-to-date was exercised.

## 4. Where the integrated result is weak

- **Decision placeholder**: if B writes `decision: TODO` for all pairs, C returns 0
  (see `v2-c-030729.json`). The integrated gate would pass a non-decision.
- **Head change after decision**: C checks `main_sha` only; if B amends the case after
  the decision and the pair set is unchanged, C still returns 0. The decision is not
  bound to the bytes being merged.
- **Same-case field decisions** are not in the V2 schema; the prototype added
  `same_case`. An integrated same-case edit would need this extension.
- **High-priority noise**: B's decision includes `96002 ↔ 10303` at symptom score
  `0.286` because root/fix overlap raised it to high. This is a real case pair in the
  library, but the evidence is weak; the reviewer has to decide on it.
- **The gate can be bypassed** by any actor who merges without the required check, or
  by an admin bypass. That is a platform/process control, not code.
- **No provenance/usage migration** was exercised in the integrated flow. The
  decision file is committed; no provenance manifest, reference update, fixture
  migration, or usage-count transfer is part of this scenario.

## 5. Verdict

**Integrated workflow: PARTIAL PASS (conditional).**

- It passes as a *simulated* end-to-end workflow: A/B drafts retained; A merges; B's
  stale decision is detected; a decision is required; B merges; rebuild and retrieval
  succeed.
- It is not a production PASS: required-check enforcement, approval, branch freshness,
  and merge-queue behavior are **UNTESTED**; decision placeholders and post-decision
  head changes are **not blocked**; semantic correctness is not judged.

The conclusion is: **V2 changes the workflow from “no gate” to “a gate that can
be enforced if the platform is configured and the decision checks are hardened”.**
The current prototype is not hardened enough to call it production-ready.
