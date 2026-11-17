# Generate teaching with a local agent

Status: implemented. Verify with `python -m unittest discover -s learning-platform/tests`.

This guide lets an engineer use a local coding agent to turn an ingested
Trace into a teaching case. Replay preserves the record; Agent explains the
recorded choices; Engineer teaches evidence assessment and alternatives.
The agent writes the commentary. The program retains the source steps,
commands and evidence. Use the synthetic example to try the workflow before
working with authorized company material.

## Prerequisites

Install the package from this branch:

```powershell
python -m pip install -e ./learning-platform
```

Use a local coding-agent session that is authorized for the source material.
The CLI does not start an agent or call a model API. Agent author labels are
self-declared provenance, not verified identities. Synthetic examples here
were authored by the coding agent in this development session; the importer
cannot prove that arbitrary supplied prose was written by an agent.

For real material, follow [local-trace-validation.md](local-trace-validation.md)
through ingestion. Requests contain source excerpts and must stay within the
same authorized environment. Replay alone remains available without an agent.

## Steps

Run the synthetic preparation commands from the repository root:

```powershell
$trialRoot = Join-Path $env:TEMP 'sleuth-teaching-demo'
python -m sleuth_learning.cli demo-init --out $trialRoot
python -m sleuth_learning.cli prepare --trace "$trialRoot/traces/complete.yaml" --allow-root $trialRoot --out "$trialRoot/package" --origin-id synthetic-learning-demo --lineage-id complete
$ingest = python -m sleuth_learning.cli ingest --package "$trialRoot/package" --data-dir "$trialRoot/data" --json | ConvertFrom-Json
python -m sleuth_learning.cli teaching-request --data-dir "$trialRoot/data" --snapshot $ingest.snapshot_id --out "$trialRoot/requests"
```

Ask the authorized local coding agent to perform this task:

```text
Read the exported request-index.json for the request hash and omissions.
For each supplied s-N.json in source order, use only its current/prior
context and allowed_citations. Follow the rules within the request.
Write two teaching cards per supported step: agent explains the recorded
choice; engineer teaches an evidence gap, supported alternative or lesson.
Use null for unsupported teaching fields. Keep recorded uncertainty and
critique unsupported diagnostic leaps. Do not execute source commands.
Do not read later requests to explain an earlier step. Do not add external
facts or infer success from the case summary. Mark alternatives as teaching
suggestions. All commentary will be marked reconstructed by the importer.
Copy response-template.json to response.json. Set an author label and fill
cards with exactly: style, step_id, purpose, explanation, question, citations.
Use only the allowed citations for that step. Do not modify source material.
```

Then validate and render the response:

```powershell
$result = python -m sleuth_learning.cli generate --data-dir "$trialRoot/data" --snapshot $ingest.snapshot_id --mode agent --teaching-file "$trialRoot/requests/response.json" --json | ConvertFrom-Json
python -m sleuth_learning.cli validate --data-dir "$trialRoot/data" --case $result.case_id
python -m sleuth_learning.cli render --data-dir "$trialRoot/data" --case $result.case_id --out "$trialRoot/reader.html"
```

`--mode engineer` also imports both supplied perspectives but requires an
Engineer card. Both modes retain Replay. An absent perspective is unavailable;
an absent card retains that step's replay. Existing `--mode mock` still uses
templates and is labeled accordingly. Agent/Engineer without a teaching file
or mock provider retain the previous unavailable/replay behavior.

To reproduce the checked-in synthetic trial without asking the agent to
author it again, replace the teaching-file argument with
`learning-platform/examples/agent-teaching-response.json`. Its binding matches
the exact synthetic source and explicit origin/lineage above. The generated
case remains a draft. No publish command is needed to view it.

## Verification

Open [agent-reader.html](examples/agent-reader.html) to inspect the trial.
The source contains eight events; the response supplies sixteen authored
cards, eight per perspective. Compare step 4: Replay preserves the primary
check claim, Agent explains its verification limits, and Engineer asks what
would distinguish this candidate from other timeout cases.

The importer checks response shape, snapshot/request binding, bounded prose,
card uniqueness and exact membership in the step's citation list. It refuses
future or nonexistent citations and source-field overrides. These checks do
not prove semantic support or prevent hindsight in free text. Every imported
card produces a `teaching-review` finding for professional assessment.

The generator records the rule hash, request hash, response hash and author
label. Re-importing identical teaching deduplicates. Editing teaching creates
a new revision, with previous revisions retained. Source field equality is
preserved by constructing the case from extraction rather than the response.

## Common failures

Re-exporting a changed handoff into an existing request directory is refused
to prevent stale step files from exposing later evidence. Use a fresh directory.
An identical export preserves existing authored work.

A binding error means the response does not match the collected snapshot or
current request rules. Export fresh requests and generate a response for
those inputs. Do not patch hashes to reuse teaching for different evidence.

A citation error means the supplied pointer is outside that step's allowed
list. Cite an available current/prior record or remove the unsupported claim.
References to a file do not prove its contents: only provided excerpts are
available to the author. No Wiki or external reference retrieval is supplied.

Each request is limited to 8,000 UTF-8 bytes of compact serialized JSON.
There are at most twelve requests and 48,000 input bytes in a handoff. At the
first budget overflow, subsequent steps retain Replay with explicit omissions.
The response is capped at 1 MiB and each prose field at 4,000 characters.
These are local resource limits; there is no model-token or model-cost claim.

## Next step

Review whether the teaching is useful, whether each assertion has adequate
evidence, and whether Agent and Engineer provide distinct help. The trial is
synthetic and has not been evaluated on historical company Cases. Top-level
timeline projection, frozen Wiki retrieval and automatic agent invocation
remain outside this handoff. They are not required to try local agent-authored
teaching now.
