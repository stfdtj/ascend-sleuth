# Learning Platform synthetic validation report

Dates: 2026-11-16–17. Status: implemented; synthetic validation passed.

This report records the gap fixes on `kb/learning-platform-mvp` for the
maintainer preparing a local real-Case conversion experiment. It covers the
offline Collector, conversion pipeline and Reader. It makes no claim about
customer-data compatibility or production readiness. For execution steps,
use [local-trace-validation.md](local-trace-validation.md).

## Results

| Status | Finding and result |
|---|---|
| FIXED | New case identity uses origin plus lineage/session, independently of content hashes. Re-import deduplicates; changed content creates another revision. Missing session IDs no longer share a sentinel. |
| FIXED | Collection uses stable path-derived origin by default. Explicit origin/lineage overrides support relocation. Separate Python executions produce identical snapshot hashes. |
| FIXED | Packages retain explicit source-reference mappings. Evidence exposes its Trace pointer, scoped source path, package file ID, line and omission reason. Quotes cannot borrow files from another event. |
| FIXED | Reader shows recorded tool-use text, its step and source pointer. Missing commands and reasoning are explicit. It never executes commands or claims independently confirmed execution. |
| FIXED | YAML date/datetime values serialize; malformed event fields degrade without inventing events. Source order stays unchanged. Legacy workload fields and recorded event context remain visible. |
| FIXED | Platform applicability stays unknown without a supplied registry. Recorded reasoning cites its own Trace field. |
| FIXED | Ingestion verifies the content hash, strict blob hash names, byte limits and blob sizes; it copies only declared blobs. Symlink resolution checks the original reference path. |
| FIXED | Reader JSON embedding escapes HTML delimiters and substitutes template tokens in one pass. A regression caught and removed restricted absolute paths from generated missing-file messages. |
| VERIFIED | Existing explicit publication grants, source read-only behavior, bounded evidence collection, quote mismatch blocking, unknown-event coverage and no-model replay already worked. Existing tests still pass. |
| DEFERRED | Services, real model APIs, Wiki/RAG, authentication and optimization remain outside this task. |
| DEFERRED | Top-level incident/failure/upstream timelines and revision history remain in the packaged Trace but are not projected into diagnostic Steps. Files referenced only there are not collected. The Reader warns when these fields are present. This is a known coverage limit for local evaluation. |
| BLOCKED | Empirical compatibility with authorized historical company Cases has not been measured. No synthetic test was blocked by missing real data. |

## Fixture basis and historical compatibility

Fixtures were constructed after reading these production sources:

- `scripts/trace_begin.py::build_header`: current header writer. A regression calls this pure function with synthetic values; it performs no network sync.
- `scripts/_trace_content.py::to_jsonable` and `tests/test_trace_content.py`: unquoted YAML dates, optional modern timeline fields, legacy traces without them.
- `scripts/_trace_state.py::derive` and `tests/test_trace_state.py`: partial events and evidence-missing fallback.
- `scripts/verify_evidence.py` and `skills/diagnose/references/diagnosis-trace.md`: user `content`, agent `output`/`reason`, `evidence.files/quotes/inline/sources/missing`, and tool-use records.
- The same Trace contract explicitly documents historical `side`/`side_source` names. Both these and current `workload_type` fields survive as recorded context; the source is not rewritten.
- Public `examples/` and the existing Learning Platform synthetic fixtures were inspected. No real diagnostic Trace or customer log was used.

Missing roles, scalar file references, malformed fields and out-of-order
event metadata are robustness inputs. They are not asserted to be named,
versioned historical schemas. Unsupported fields remain in the packaged
Trace. No timestamp proximity creates an evidence or causal link.

## Identity, fingerprint and schema contract

`learning-package/1` remains readable. New collection identifies its changed
projection with `projection_policy: selected-evidence-v2` and
`collector_version: 2`. The snapshot hash still covers exactly `content`;
creation time and authorization metadata remain outside that hash.

V2 content contains stable source identity, synthetic status, consistency,
projection policy, file metadata/hashes, omissions and related sources.
Trace JSON keys are sorted; YAML dates become ISO strings. Trace timestamps
are source content and therefore affect revisions. The evidence bytes are
not normalized. This is not a universal semantic hash of all equivalent YAML.

The default origin hashes the resolved Trace path. It stores no additional
absolute path. The logical identifier is explicit lineage, otherwise session;
a missing session gets path-derived lineage. Two sources with the same
session ID have distinct default origins. Moving or renaming a source changes
the default identity. Operators must reuse opaque `--origin-id` and
`--lineage-id` values when continuity across relocation is required.

Legacy v1 packages retain their original session-only IDs on regeneration.
Existing revisions and publication pointers are not rewritten. Recollection
under v2 intentionally creates a separate case; there is no automatic merge
of potentially collided legacy histories. Back up the local store before
experimentation. Historical collisions require human source comparison.

The Learning Case schema remains `/1` with optional `source_context` and
Step `recorded_context`; old objects default to empty dictionaries. Evidence
`lineage` adds Trace pointers, safe source references and availability.
Generator version is now `2` so changed extraction can create a new revision
for an existing legacy snapshot. Older rendered HTML remains unchanged until
rerendered.

## Validation

From the repository worktree, PowerShell:

```powershell
$env:PYTHONPATH=(Resolve-Path learning-platform/src).Path
$env:PYTHONUTF8='1'
python -m unittest discover -s learning-platform/tests
```

Result: **60 passed, 0 failed, 0 skipped**, including the original 32 tests,
16 gap regression tests, ten teaching-handoff regressions and two actual Edge
browser tests. The browser test
requires `python -m pip install playwright` and an installed Microsoft Edge.
It ran against Edge 157.0.4341.60 in this session. Without Playwright it is
explicitly skipped; a missing Edge installation fails with its launch error.

The CLI acceptance test runs Collect → Ingest → Extract → Generate Replay →
Validate → Render. Regression tests additionally cover origins, missing IDs,
recollection, revisions, restricted paths, oversized/missing logs, malformed
YAML, legacy packages, current production writer output and injection text.
The browser test checks the rendered DOM, command placement, evidence line
numbers, unavailable states and absence of script execution errors.

The inspected synthetic artifact is available as
[regression-reader.html](examples/regression-reader.html), with its
[Learning Case JSON](examples/regression-learning-case.json). It is a draft;
no publication operation was used to create it.

Repository-wide command (same worktree, before the teaching-handoff addition):

```powershell
$env:PYTHONUTF8='1'
python -m unittest discover -s tests
```

Result: **1,369 discovered; 1,366 passed, 0 failed, 3 skipped** in
1,533.519 seconds. The three pre-existing opt-in live-network tests in
`tests/test_src_fetch.py` were not enabled (`ASCEND_SLEUTH_NETWORK_TESTS`
was unset): `test_ambiguous_signature_does_not_clone`,
`test_single_candidate_is_fetched_and_reused`, and
`test_org_catalog_reports_descriptions`. They enumerate or clone external
repositories, so they are outside this synthetic-only validation. None was
skipped for lack of real Cases or customer logs.

`git diff --check` also passed. Full local outputs are retained as ignored `test-results.txt` and
`repository-test-results.txt`; these machine-local logs are not pushed.
No unrelated workflow code was changed.

## Agent teaching trial

FIXED: the file handoff exports current/prior step context with source-order
boundaries. A local coding agent supplies substantive teaching prose for
Agent and Engineer. The importer only accepts bounded prose and allowed
citations, binds it to the snapshot and request, and marks it reconstructed.
Request/rule/response hashes participate in provenance and job deduplication.
No model API or automatic agent invocation is added.

The coding agent authored sixteen distinct cards for the eight-event
synthetic complete Trace. Agent explains choices and evidentiary limits;
Engineer teaches checks, alternatives and reusable lessons. The trial
explicitly challenges the unsupported jump from a timeout signature to a
buffer mechanism and separates reported improvement from isolated causation.
No original event or command was added by teaching generation.

[Agent Reader](examples/agent-reader.html),
[Learning Case](examples/agent-learning-case.json), and
[authored response](examples/agent-teaching-response.json) are checked in.
[agent-teaching.md](agent-teaching.md) contains the reproduction commands.
The import produced zero errors and sixteen `teaching-review` findings.
These findings request semantic assessment; they are not a passing quality
score or evidence of real-Case compatibility.

## Review and remaining risks

Independent agent pre-commit review approved the final reviewed scope
(`MERGE_READY: yes`). Its counterexamples found stale request files on changed
exports and a publication check using the latest revision's synthetic flag.
Changed exports now require a fresh directory. Publication and rendering read
the selected revision's own immutable snapshot provenance. Two targeted
regressions and both independent reproductions passed after the fixes.
Readability, logic and jargon judgments all passed.

A separate diff-review pass checked collision and fingerprint inputs,
legacy read behavior, evidence association, path handling, HTML embedding
and unsupported applicability claims. It found the missing-message path leak,
scalar-reference pointer errors and missing ingestion byte checks; each was
corrected before the final Learning Platform run.

The store remains a single-process local store; no transactional concurrency
guarantee was added. Stable-read collection uses stat checks, not filesystem
transactions. Imported free text and source packages are not anonymized:
commands, quoted logs or summaries can themselves contain identifiers.
Reader output must remain within the authorized local environment.

Quote verification is UTF-8 in this MVP; other encodings remain unavailable.
Oversized files are explicitly omitted, not excerpted. File references are
relative to the selected allow-root. An absolute historical path is withheld
and points back to the original local Trace for review. These are specific
items for the local experiment, not reasons to wait for customer logs here.

Readability review: changes name the source, unavailable state and action.
Logic review: recorded facts, inferred relationships and real-world claims
remain separate. Terminology review: identity and revision use separate terms.
The implementation follows the repository principles of verification before
delivery, reversible changes and observable evidence boundaries.

## Modified files

All changes are under `learning-platform/`:

- `src/sleuth_learning/cli.py`, `storage.py`, `model.py`, `render.py`
- `src/sleuth_learning/collector/package.py`, `collector/snapshot.py`
- `src/sleuth_learning/extraction/trace_adapter.py`, `extraction/validation.py`
- `src/sleuth_learning/generation/assemble.py`, `generation/replay.py`, `generation/handoff.py`
- `tests/test_collector.py`, `tests/test_gap_regressions.py`, `tests/test_reader_browser.py`, `tests/test_teaching_handoff.py`
- `README.md`, this report, `local-trace-validation.md`, `agent-teaching.md`, `.gitignore`
- `examples/regression-reader.html`, `examples/regression-learning-case.json`
- `examples/agent-reader.html`, `examples/agent-learning-case.json`, `examples/agent-teaching-response.json`

Delivery branch: `kb/learning-platform-mvp` on `stfdtj/ascend-sleuth`.
The user authorized a normal push. No remote PR or upstream merge is part of
this delivery. Git integration tests used temporary fixture repositories.
