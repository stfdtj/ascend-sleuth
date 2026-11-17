# Authorized local real-Trace validation

This procedure is for the engineer who has local authorization to inspect
historical Cases and source logs. It tests conversion fidelity after the
synthetic suite passes. It does not publish material or require network
services. Skip it when only the synthetic MVP demo is needed.

## Prerequisites

Use an authorized workstation and a separate local output/store directory.
Keep the source Trace and logs read-only. Install the package from the local
checkout with `python -m pip install -e ./learning-platform`.

Choose an evidence root that matches the relative paths in the Trace.
Use an opaque stable origin identifier for each independent source. Use an
opaque lineage identifier for each logical Case, especially if session IDs
are absent or sources will move. Keep that mapping locally.

## Steps

Run the following PowerShell commands with authorized local paths:

```powershell
$traceFile = 'D:/authorized/input/traces/example.yaml'
$evidenceRoot = 'D:/authorized/input'
$packageDir = 'D:/authorized/learning-check/package'
$storeDir = 'D:/authorized/learning-check/store'
$readerFile = 'D:/authorized/learning-check/reader.html'
python -m sleuth_learning.cli prepare --trace $traceFile --allow-root $evidenceRoot --dry-run --json
python -m sleuth_learning.cli prepare --trace $traceFile --allow-root $evidenceRoot --out $packageDir --not-synthetic --origin-id source-a --lineage-id case-a
python -m sleuth_learning.cli inspect --package $packageDir
$ingest = python -m sleuth_learning.cli ingest --package $packageDir --data-dir $storeDir --json | ConvertFrom-Json
$result = python -m sleuth_learning.cli generate --data-dir $storeDir --snapshot $ingest.snapshot_id --mode replay --json | ConvertFrom-Json
python -m sleuth_learning.cli validate --data-dir $storeDir --case $result.case_id
python -m sleuth_learning.cli render --data-dir $storeDir --case $result.case_id --out $readerFile
```

Open the HTML locally. Compare each displayed step against the original
Trace array position. Check recorded reasoning verbatim. Check tool-use text
without assuming every tool record is an executable command. Confirm absent
commands remain absent. Compare evidence excerpts and line numbers with the
authorized original files.

Repeat collection and ingestion with the same identifiers and unchanged
sources. Expect the same snapshot hash and generation revision. Make a
synthetic copy locally to test edits without changing the historical record;
keep identifiers only if deliberately testing a revision of that same case.
Independent Cases must use independent source/lineage identities.

## Verification

Record locally the source identifiers, package hash, case ID, revision,
findings and any source fields omitted from the Reader. Check these items:

1. Historical schema variants and missing fields match the actual local set.
2. Evidence roots resolve correctly across nodes/ranks and copied log bundles.
3. Missing, inaccessible and oversized files are accurately classified.
4. Non-UTF-8 logs, unusual `tool_calls` and unknown actions remain understandable.
5. Out-of-order timestamps do not imply chronology or causality.
6. Top-level incident/failure/upstream timelines are reviewed directly in the
   source; this MVP does not project them or collect their exclusive files.
7. Reader text and source packages remain within authorized storage boundaries.

A passing synthetic suite does not establish any of these real-data results.
The engineer must record the outcome of this comparison before claiming
compatibility with the tested historical Cases.

## Common failures

If a file is omitted, read its reason before changing the evidence root.
Do not broaden the allow-root to an entire drive. Absolute paths and paths
outside the root are withheld. Inspect the source pointer locally; do not
remove collection safety checks. Logs over 10 MiB remain omitted.

`validate` displays the findings saved during generation. After correcting
an authorized input copy, recollect and generate to obtain fresh findings.
Do not interpret zero blocking findings as proof that the diagnosis is right.

## Next step

Keep the comparison record local. Any defects returned for development should
use newly constructed synthetic reproductions. No customer logs are needed
for follow-up development. Publication, shared access and real model
integration remain outside this conversion experiment.
