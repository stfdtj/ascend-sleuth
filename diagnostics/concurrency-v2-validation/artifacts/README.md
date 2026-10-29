# Artifacts

- `proto/`: minimal executable prototypes used to test V2 mechanisms.
- `scripts/`: harnesses. They create clones under `D:\working\asv2` and write JSON
  records to `D:\working\asv2\logs`.
- `logs/`: selected final records copied from the lab. Other historical runs remain in
  the lab and are not part of this bundle.

The prototypes are not production code. They exist to answer specific questions:
whether UUID drafts survive concurrency/crashes, whether the labelled duplicates are
displayed, whether C detects stale/conflicting changes and rejects missing decisions,
and whether provenance claims can be checked from the repository.
