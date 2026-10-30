# provenance/ — 来源与证据记录

每个需要追溯的 case 一份 `<case-id>.yaml`。只有 `committed: true` 的材料能被 CI 校验哈希；`local-only` / `declared` 只标注，不当成可恢复证据。

```yaml
case_id: VLLM-ASC-12345
materials:
  - draft_id: <uuid>
    deployment_id: <id>
    session: <session-id>
    files:
      - path: postmortems/materials/VLLM-ASC-12345/case.yaml
        sha256: <hash>
        committed: true
    fields:
      root_cause: [<uuid>]
      fix: [<uuid>]
evidence:
  - event_id: feedback:<session>:1
    kind: feedback
    independent: true
lineage:
  supersedes: null
  merged_into: null
  renamed_from: []
```

`python3 scripts/verify_provenance.py --root .` 检查：

- committed 文件存在且哈希匹配；
- local-only 只告警；
- `dropped` 标 `verified` 时目标必须存在；
- 同一 event_id 不能被两个 case 标成独立；
- lineage/redirect 目标存在。

它不保证 local-only 材料可恢复；不替代 `rename_case.py`（尚未实现）。
