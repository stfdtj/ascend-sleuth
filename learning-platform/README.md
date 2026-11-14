# Ascend Sleuth Learning Platform -- offline MVP

This is a working, offline-only implementation of the smallest complete
vertical slice of the Learning Platform design in
`../proposals/learning-platform/` (the "Astra" design, branch
`kb/learning-platform-design`): `implementation-plan.md`,
`data-contracts.md`, `generation-design.md`, `deployment-design.md`, and
`claude-implementation-handoff.md`.

Pipeline implemented end to end, with no network calls anywhere:

```
Local Trace -> Collector -> Ingestion -> Generator -> Validation -> Stored Learning Case -> Reader
```

Nothing here touches a real company environment, a real model, or real
customer data. Every trace/evidence file this package ships is synthetic
and hand-written for this MVP (`src/sleuth_learning/fixtures/`).

## Quickstart

```bash
python -m pip install -e ./learning-platform
sleuth-learn demo-init --out /tmp/sleuth-learning-demo
sleuth-learn demo-run --root /tmp/sleuth-learning-demo
python -m unittest discover -s learning-platform/tests
```

`demo-run` does the whole pipeline in one shot and ends by writing
`/tmp/sleuth-learning-demo/demo-case.html` -- open that file directly in a
browser, no server needed.

If `sleuth-learn` isn't on your PATH after an editable install (common on
Windows), use `python -m sleuth_learning.cli ...` instead -- every example
below works with either form.

### Step by step

```bash
sleuth-learn discover --root /tmp/sleuth-learning-demo
sleuth-learn prepare --trace /tmp/sleuth-learning-demo/traces/complete.yaml \
    --allow-root /tmp/sleuth-learning-demo \
    --out /tmp/sleuth-learning-demo/packages/complete
sleuth-learn inspect --package /tmp/sleuth-learning-demo/packages/complete
sleuth-learn ingest --package /tmp/sleuth-learning-demo/packages/complete \
    --data-dir /tmp/sleuth-learning-demo/data
# snapshot id printed above, e.g. 836a6e62-...
sleuth-learn generate --data-dir /tmp/sleuth-learning-demo/data \
    --snapshot <snapshot-id> --mode replay
sleuth-learn validate --data-dir /tmp/sleuth-learning-demo/data --case <case-id>
sleuth-learn publish --data-dir /tmp/sleuth-learning-demo/data \
    --case <case-id> --revision 1 --i-have-authorization
sleuth-learn render --data-dir /tmp/sleuth-learning-demo/data \
    --case <case-id> --out /tmp/sleuth-learning-demo/reader.html
```

`--mode replay` is Mode C -- deterministic, rule-based extraction, no LLM at
all. To also see Mode A/Mode B teaching cards (built from an offline,
clearly-labeled mock model, never a real one), use `--mode mock --model
mock`, or `--mode agent --model mock` / `--mode engineer --model mock` for
one style at a time. Without `--model mock`, requesting `agent`/`engineer`
mode downgrades to replay and marks that view `state: unavailable` --
exactly like `generation-design.md`'s "no model -> replay" rule.

A ready-made example is checked into `examples/`:
[`examples/example-learning-case.json`](examples/example-learning-case.json)
is a full Learning Case produced by `demo-run`, and
[`examples/example-reader.html`](examples/example-reader.html) is the
corresponding static reader page -- open it directly, no server required.

## Command reference

| Command | Does |
|---|---|
| `demo-init --out DIR` | Write the synthetic demo traces/evidence/data dirs |
| `discover --root DIR [--include-in-progress]` | List candidate sessions under `DIR/traces` |
| `prepare --trace F --allow-root DIR --out DIR [--dry-run] [--not-synthetic]` | Build a local collector package |
| `inspect --package DIR` | Show a package's manifest, re-verify blob integrity |
| `ingest --package DIR --data-dir DIR` | Idempotently import a package into the local store |
| `generate --data-dir DIR --snapshot ID --mode {replay,mock,agent,engineer} [--model {none,mock}] [--platform-registry F] [--force]` | Run extraction + generation |
| `validate --data-dir DIR --case ID [--revision N]` | Show stored validation findings |
| `publish --data-dir DIR --case ID --revision N --i-have-authorization [--allow-non-synthetic]` | Publish a revision |
| `withdraw --data-dir DIR --case ID [--reason TEXT]` | Withdraw a case from publication |
| `list --data-dir DIR` | List snapshots and cases |
| `render --data-dir DIR --case ID [--revision N] --out FILE.html` | Render the static HTML reader |
| `demo-run --root DIR` | Run the whole pipeline once on the synthetic demo |

Every command accepts `--json` for machine-readable output.

## Tests and execution results

```bash
$ python -m unittest discover -s tests -v
...
Ran 32 tests in 1.6s
OK
```

32/32 pass, covering (see `tests/` for the full mapping, and
`src/sleuth_learning/fixtures/sample_traces/*.yaml` for the synthetic fixtures
themselves):

- complete diagnostic sequence, full coverage, quote verified (`test_e2e.py`, `test_extraction_validation.py`)
- missing evidence (`missing_evidence.yaml`)
- incomplete trace (`incomplete.yaml`, `teaching_class=incomplete`)
- invalid/unsafe evidence references -- missing file and a path-traversal
  attempt, both rejected/omitted rather than followed (`invalid_evidence_ref.yaml`,
  `test_collector.py::PathSafetyTests`)
- duplicate ingestion (idempotent by `snapshot_hash`) and duplicate
  generation jobs (idempotent by job key) (`test_storage_and_pipeline.py`)
- source changes and regeneration -- a corrected trace produces a new
  revision of the *same* case; the already-published revision is untouched
  (`test_source_change_creates_new_revision_and_keeps_old_published`)
- failed diagnosis / knowledge miss (`failed_diagnosis.yaml`, `teaching_class=failure`)
- conflicting reference information -- a hit case on a platform not in the
  supplied applicability registry produces a non-blocking `review` finding,
  never an auto-promoted "matched" (`conflicting_reference.yaml`)
- unsafe/unauthorized publication attempts -- no `--i-have-authorization`,
  blocking validation errors present, or non-synthetic material without
  `--allow-non-synthetic`, are all refused (`PublicationAuthorizationTests`)

The reader's inline JS was also syntax-checked with `node --check` against
the generated HTML (not run inside this session's own browser tooling,
which only renders local files as static snapshots, not an interactive DOM
-- please actually open `demo-case.html` / `examples/example-reader.html`
yourself to confirm the visual result).

## Module-by-module summary

```
learning-platform/
  src/sleuth_learning/
    model.py            Learning Case object model (data-contracts.md section 3)
    hashing.py          sha256 content hashing, canonical JSON
    errors.py           typed errors with a {code, message} envelope
    collector/
      discovery.py       discover() -- list candidate sessions, safe YAML parse
      snapshot.py         plan_sources() / capture_stable() -- path-safety + stable copy
      package.py           project_and_seal() -- manifest.json + content-addressed blobs
    extraction/
      trace_adapter.py    extract() -- real diagnose trace -> Step/Evidence/Diagnosis
      evidence_linker.py  link_evidence() / verify_quotes() -- quote re-verification
      validation.py        validate_artifact() -- schema/pointer/quote/coverage/binding/
                           applicability/generated_claims checks
    generation/
      providers.py         ModelProvider protocol + the offline MockModelProvider
      replay.py             Mode C -- deterministic, no model
      teaching.py           Mode A/B -- agent-style / engineer-style via a provider
      assemble.py           assemble_case() -- programs assembles raw fields + Views
    storage.py           local JSON-file store: snapshots, case revisions,
                         publish/withdraw, idempotency by job key
    render.py             static, self-contained HTML reader (textContent only)
    cli.py                `sleuth-learn` command-line entry point
    fixtures/             synthetic demo traces + evidence, shipped with the package
  tests/                 32 unit/integration tests (see above)
  examples/              a generated Learning Case + reader page, checked in
```

## Deviations from the Astra design (and why)

The task that produced this MVP explicitly said: verify Astra's design
against the actual repository, document mismatches rather than inventing an
integration, and prioritize the smallest complete vertical slice over
building services that cannot run. Three things in the full design do not
exist as described, or were deliberately cut for the offline MVP:

1. **No HTTP server, no SQLite, no worker process.**
   `deployment-design.md` specifies FastAPI + Uvicorn + a SQLite control
   database + a polling worker + role-based review states
   (quarantined/safety-approved/content-approved/publication-approved).
   None of that is needed to prove the pipeline end to end offline, and
   building it would mean "numerous abstractions that cannot run" against
   an approved deployment that does not exist yet. This MVP implements the
   same *behaviors* the SQLite layer exists for -- idempotent upload,
   atomic publish, job dedup, revision history -- as a local JSON-file
   store (`storage.py`) with atomic writes (write-temp-then-replace). There
   is no `transport.py`/network layer at all: `ingest` reads a package
   directory directly off local disk. Growing this into the real design
   means replacing `storage.py`'s functions with calls to the real API,
   keeping the `Package`/`LearningCase` JSON shapes as the contract
   boundary.

2. **No real authorization/review workflow -- a local, explicit flag
   instead.** `deployment-design.md` section 4 describes seven roles and a
   multi-stage approval state machine backed by real grants. This MVP has
   no identity system to build that on, so it implements one explicit
   authorization boundary instead of pretending automatic redaction is
   enough (per the task's own instruction): `publish` refuses without
   `--i-have-authorization`, and additionally refuses non-synthetic
   (real) material without `--allow-non-synthetic`. Neither flag does
   any actual review -- they are a placeholder for "a human confirmed this
   should go out," to be replaced by the real safety/content/publisher
   sign-offs once that workflow exists.

3. **No Wiki retrieval, no real token-budget enforcement.**
   `generation-design.md` section 4 specifies a `FrozenWikiIndex` and
   `retrieve_wiki()` for background facts, plus per-request/per-case token
   budgets. No such index exists in this repository or this MVP. Instead,
   `extract()` takes an optional `platform_registry` (a simple
   `{case_id: [platform, ...]}` JSON file) as the smallest possible stand-in
   for "explicitly supplied authorized reference documents" -- enough to
   demonstrate a non-matching platform producing a `review` finding
   (`conflicting_reference.yaml` / its test) without inventing a document
   store. Token budgeting is skipped because the only provider that exists
   is a deterministic, free, offline mock -- rate-limiting it would be
   theater. A real model integration must add both back.

4. **Generator mode is never claimed dishonestly.** `data-contracts.md`'s
   `Generator.mode` enum is `replay | mock | agent | engineer`. Since this
   MVP has no real model, requesting `--mode agent` or `--mode engineer`
   without `--model mock` downgrades the *recorded* mode to `replay` (per
   `generation-design.md`'s own "no model -> replay" rule); requesting it
   *with* `--model mock` records the mode as `mock`, never as `agent` or
   `engineer` -- this package never lets mock output pass as a real model's
   teaching judgement, per the task's explicit instruction not to.

5. **Case identity is keyed by `session_id`, not by `snapshot_hash`** (a
   design choice this MVP had to make that data-contracts.md leaves to the
   server implementation). A corrected trace produces a new snapshot (new
   `snapshot_hash`) but must land as a new revision of the *same* case, not
   a new case, so the previously-published revision survives untouched --
   see `storage.case_id_for_session`.

6. **Smaller, real gaps, not design choices:**
   - `Step.commands` is only ever populated from an event's own
     `tool_calls` field (the one place `diagnosis-trace.md` already
     records tool use); nothing is parsed out of free-text `output`/`reason`.
   - `Step.case_refs` (pointers to *other* Case/Postmortem files) is always
     empty -- those files are not part of a Collector package in this MVP;
     the underlying fact is still visible in plain text (e.g. a `hit`
     event's own `output`/`reason`), just not structurally linked yet.
   - `evidence_linker` resolves a quote's `file` reference only against
     the same event's `evidence.files` list (exact string match); it does
     not attempt fuzzy matching across events.

## Limitations and unimplemented production integrations

- No real `IdentityProvider`/`AuthorizationProvider` -- see deviation 2.
- No `ModelProvider` talking to an approved internal model -- the
  `ModelProvider` interface (`generation/providers.py`) is real and stable,
  but the only implementation is the offline `MockModelProvider`.
- No `WikiProvider`/Wiki retrieval -- see deviation 3.
- No HTTP API, no multi-tenant isolation, no audit log, no backup/retention
  policy, no CDN/no-store cache headers (there is no server to set them on).
- No resumable/chunked blob upload (there is no upload at all -- `ingest`
  reads a local directory).
- The reader has no search/pagination; it is one static page per case.
- Glossary tooltips are a small hardcoded dictionary, not derived from
  `references/`.

## Integration checklist (for the authorized company environment)

Per `claude-implementation-handoff.md` section 5 and
`deployment-design.md`: keep `Package`, `LearningCase` and the
`ModelProvider`/`WikiProvider`/`IdentityProvider`/`AuthorizationProvider`
interfaces unchanged as the contract boundary, then:

1. Replace `storage.py`'s local-file functions with calls to the real API
   (`POST /uploads`, `/finalize`, `/jobs`, etc. per `data-contracts.md`
   section 4), behind a feature flag so `offline` mode keeps working.
2. Stand up the approved `IdentityProvider`/`AuthorizationProvider` and
   replace the `--i-have-authorization`/`--allow-non-synthetic` flags with
   real grant checks.
3. Configure an approved internal `ModelProvider` and wire it in next to
   `MockModelProvider`; keep `generator.mode` honest (deviation 4) --
   only record `agent`/`engineer` once a real model actually produced the
   view.
4. Build the real `WikiProvider`/`FrozenWikiIndex` and replace the
   `--platform-registry` stand-in with real retrieval, enforcing the token
   budgets in `generation-design.md` section 4.
5. Add the resumable blob-upload transport, SQLite control tables, and
   worker process from `deployment-design.md`, running the existing
   `extraction`/`generation`/`validation` modules unchanged inside the
   worker.
6. Run the existing test suite against the new backend before enabling it
   for anything beyond synthetic material; add the same nine scenarios as
   integration tests against the real API.
7. Get the real safety/content/publisher review workflow in place before
   ever flipping `--allow-non-synthetic` on for real customer data -- this
   MVP's authorization flags are a placeholder, not a review process.
