# decisions/ — 机器可读的重复/冲突决定

每个相关 case 一份 `<case-id>.yaml`，随 PR 进 Git。`merge_recheck.py` 只读这个文件，不读 PR 描述。

```yaml
case_id: VLLM-ASC-12345
decision: variant          # new | variant | covered | deferred | separate | merge
main_sha: <扫描时的 origin/main>
head_sha: <扫描时的 HEAD>
content_sha256: <变更知识文件的内容哈希>
pairs:
  - pair_id: <stable id>
    other: VLLM-ASC-12344
    tier: mandatory
    decision: variant      # separate | variant | merge | covered | defer
    note: "同一 root cause；本单补 A3 的验证"
same_case:
  - case_id: VLLM-ASC-12345
    fields: [fix, compat]
    decision: separate
    note: "两条修复条件互斥，保留两段"
overflow:
  hidden_high: 0
  ack: null                # >0 时必须是 {hidden_count, reason, reviewer}
```

规则：

- `decision` 不能是 `TODO` 或空值；
- 每个 mandatory/high pair 必须有对应项和非空 note；
- `main_sha` 必须等于当前 base；
- `head_sha` 或 `content_sha256` 必须绑定当前变更；
- 同 case 字段冲突必须有 `same_case`；
- `hidden_high > 0` 时 ack 的 `hidden_count` 必须等于实际值。

`python3 scripts/verify_decisions.py ...` 可以单独校验；`merge_recheck.py` 在 PR 阶段调用同一套检查。人工判断是否同一根因、是否合并，脚本不替代。
