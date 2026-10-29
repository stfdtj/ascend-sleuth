# Reproduction artifacts — concurrency validation

Everything here is a lab artifact. The prototypes are proofs of concept for design
validation, **not** product code, and none of them is wired into the repository.

## Layout

```
diagnostics/concurrency-validation/
  01-current-workflow.md
  02-baseline-findings.md
  03-solution-validation.md
  04-gaps-and-recommendations.md
  05-test-matrix.md
  06-final-assessment.md
  artifacts/
    proto/
      inbox_put.py            # Checkpoint A prototype (new/finish/list/abort + reader)
      _inbox_worker.py        # child process for real concurrency/crash tests
      test_inbox_put.py       # 13 tests (8 concurrent creators, 3 crash shapes, hashes, identity)
      find_duplicates.py      # Checkpoint B prototype (candidates + six axes + hints)
      merge_recheck.py        # Checkpoint C prototype (base/head change sets, stale SHAs)
    scripts/
      lab_common.py           # lab paths, git helpers, recorder, origin reset/seed
      fixtures.py             # synthetic case/trace/render helpers (line-editable YAML)
      run_e2e.py              # Stage I: one complete production-like run
      run_engineers.py        # Stage I: two engineers, both merge orders, E4/E5/E6/E7/E8
      run_inbox_race.py       # Stage I: shared inbox, concurrent/crash writes (E1)
      run_id_metrics.py       # Stage I: E9 rename/delete/archive, E10 period collision
      repro_e11.py            # E11 deterministic reproduction (all-digit SHA)
      test_find_duplicates.py # Stage II: labelled draft set vs real library
      analyze_b_v2.py         # targeted design experiment: core/weak tiers
      test_merge_recheck.py   # Stage II: C1–C9 scenarios
      test_provenance.py      # Stage II: provenance + observability data audit
      setup_lab.ps1           # creates the disposable lab root and bare remote
    logs/                     # every JSON record and console transcript quoted in the reports
```

## Environment used

Windows 11, Python 3.12.2, PyYAML 6.0.3, git 2.45.1.windows.1, Node 25.9.0.
`gh` is absent. Baseline commit `28adab0d1db1f00989b5416dfeaf8206df71ca4a`
(upstream main was `dd3e6b3` while this ran). The real checkout was not modified;
the only addition is this `diagnostics/` directory (untracked).

## Setup

The lab uses a **separate bare remote and clones** under `ASV_ROOT`
(default `D:\working\asv`), never the real repository:

```powershell
pwsh -File artifacts/scripts/setup_lab.ps1
# or manually:
git clone --bare --branch main --single-branch D:\working\ascend-sleuth $env:ASV_ROOT\origin.git
```

Each harness calls `reset_origin()` (moves the lab `main` back to the baseline and
deletes lab branches) and, where needed, `seed_integrated_main()` (publishes a main
with `VLLM-ASC-90001/90002`). They are therefore runnable in any order and repeatable.

## Run

```powershell
$env:PYTHONUTF8 = "1"
$env:ASV_ROOT = "D:\working\asv"     # optional

python diagnostics/concurrency-validation/artifacts/scripts/run_e2e.py
python diagnostics/concurrency-validation/artifacts/scripts/run_engineers.py
python diagnostics/concurrency-validation/artifacts/scripts/run_inbox_race.py
python diagnostics/concurrency-validation/artifacts/scripts/run_id_metrics.py
python diagnostics/concurrency-validation/artifacts/scripts/repro_e11.py
python diagnostics/concurrency-validation/artifacts/scripts/test_find_duplicates.py
python diagnostics/concurrency-validation/artifacts/scripts/analyze_b_v2.py
python diagnostics/concurrency-validation/artifacts/scripts/test_merge_recheck.py
python diagnostics/concurrency-validation/artifacts/scripts/test_provenance.py

python diagnostics/concurrency-validation/artifacts/proto/test_inbox_put.py
```

New records are written to `$ASV_ROOT/logs/` (JSON + console). The copies under
`artifacts/logs/` are the ones quoted in the reports; they are not regenerated in
place, so a rerun produces new timestamped files rather than overwriting evidence.

## Exit codes

- Harnesses return `0` when the experiment ran (the interesting result is often a
  non-zero check inside it); they print each step's `rc`.
- `test_inbox_put.py`: `0` = 13/13 pass.
- `repro_e11.py`: `0` = the quoted-SHA variant succeeds (the crash is asserted by the
  record, not by the exit code).
- Probes (`verify_*`, `build_index --check`) keep their own codes; the recorder stores
  each one.

## Caveats (also stated in the reports)

- Paths in the records are Windows absolute paths of the lab; the synthetic content is
  invented and contains no customer data.
- The two Node panel implementations were inspected, not exercised (no DSH host here).
- GitHub enforcement was read from the public API, not tested by creating PRs.
- The lab uses `mkdir`/`os.replace` on NTFS; NFS/SMB and Linux `flock` were not tested.
- `research/` (including the unified plan) is gitignored in this repository, so the
  plan is not part of the checked-in tree; the report quotes it by section number.
