# 06 — Recommendations

优先级表示实施顺序，不表示工期。P0 不做，V2 不能作为生产保护机制；P1 决定多人协作是否可靠；P2 是后续改进。结构与迁移细节见 `09-implementation-design-and-migration.md`。

---

## P0 — 生产采用前必须完成

### P0-0. 平台强制 spike（先于 A/B/C 生产代码）

**改什么：** 在一次性测试仓库验证 required check、approval、up-to-date、skipped job、bot bypass、check-name、merge queue。方案见 `10-platform-enforcement-spike-plan.md`。

**结构影响：** 先决定 workflow 的 job 图、required check 名称、生成物重建方式；spike 通过前不写完整 B/provenance/panel 迁移。

**验收：** 缺 check、红 check、skipped、过期分支、approval 后 push 都不能合；bot 能推生成物；S6/S7/S11 的语义有证据。

### P0-1. Decision 绑定内容并拒绝占位符

**改什么：** `verify_decisions` 拒绝 `TODO`、空值、未知值；C 比较 `head_sha` 和变更知识文件的内容哈希；decision schema 增加 `same_case`；`overflow.ack` 的隐藏数量与实际计数一致。

**结构影响：** 每个相关 PR 多一个 decision YAML；同 case 修改多一个 `same_case` 段；C 的退出码增加“绑定不一致”。

**验收：** `TODO`、空 note、改 head、改内容、缺 `same_case`、ack 数量不符都返回非零。

### P0-2. `reopen` 原子性

**改什么：** 先写旧目录的 `SUPERSEDED`，再发布新 `DONE`；reader 对“新 complete 声明 `supersedes` 旧 draft”也判旧 draft superseded。

**结构影响：** 旧目录保留；崩溃后最多一个可消费草稿；恢复路径从“两个 complete”变成“旧 suppressed、新缺失”。

**验收：** 两个写入顺序各注入一次崩溃，均最多一个 `complete`。

### P0-3. 所有 consumer 走 reader

**改什么：** `knowledge-groom`、`to-postmortem`、`sediment_batch`、两个 panel 改为 `draft_queue.py` 的 JSON；增加契约 fixture。

**结构影响：** 草稿读取从“各自扫文件”变成“一个接口”；两套面板代码都要改；兼容期同时有 UUID 和 `legacy_flat`。

**验收：** 同一 inbox 在 groom、两个 panel、B 中得到相同的 `complete/incomplete/corrupt/superseded/legacy_flat` 计数。

### P0-4. E10/E11/E12 生产修复

**改什么：** live 期号加 deployment 后缀并扩 `LIVE_PERIOD_RE`；SHA 在写入和读取两侧字符串化；补 live 白名单和 6 个 `metric_strength` 声明。

**结构影响：** timeline.d 多一个命名维度；旧期号仍可读；metrics 校验规则变更。

**验收：** 两个部署不撞期号；混合 SHA 能生成 entry-activity；干净克隆的 weekly snapshot 通过 `verify_metrics --check`。

### P0-5. 平台强制启用（P0-0 通过后）

**改什么：** 按 spike 结果增加 `kb-required` 聚合 job（全部 job 走 `needs`、`if: always()`）；workflow 级 `paths` 去掉；`pr-template` 并入 `kb-checks`；1 名非作者 approval；dismiss stale review；up-to-date；生成物 bot bypass。

**结构影响：** 分支保护从“只要求 PR”变成“要求一个聚合 check + 一个 approval + 最新分支”；docs-only PR 也跑聚合 job；生成物重建仍能推 main。

**验收：** 缺 check、红 check、过期分支、approval 后新 push、skipped `changes` job 均不能合入；bot 能推生成物。

---

## P1 — 多人协作可靠所需

B 的强制门先不要上。按 `11-evidence-and-batch-collision-plan.md` 先做 logging-only 观测和 batch-ingest 双实例测试；数据支持后再把 B 变成门。

### P1-1. Groom 处的 overflow gate

B 的 `hidden_high` 进入草稿 decision 的 `overflow.ack`；没有 ack 不允许升格。低优先级 watchlist 也给一个轻量确认字段。

**结构影响：** groom 多一个阻断条件；decision 文件多一个 ack 段。

### P1-2. B 阈值校准与负样本

给 high 增加第二个信号（强关键词/错误码、条件重叠、symptom 下限），建立包含负样本的标注集，记录 precision/recall。

**结构影响：** `case_match.py` 的 tier 规则变化；已有 decision 的 pair 集合可能变化，旧 PR 需要重跑。

### P1-3. Rename 与 usage/reference/fixture 迁移

实现 `rename_case.py`、`redirects.yaml`、redirects-aware `verify_entry_activity`；迁移引用、fixture、provenance；不自动重封 holdout。

**结构影响：** 新增 `postmortems/redirects.yaml`；改 ID 后旧 ID 不再硬红；归档不再双计。

### P1-4. 跨 namespace 与 panel 契约测试

覆盖 training↔inference 候选、两个 panel 构建、UUID inbox 的空/满/损坏状态。

**结构影响：** 测试 fixture 增加；不改变生产格式。

### P1-5. Merge queue 评估

在 up-to-date 可用后，验证 `merge_group` 的 base/head 语义和聚合 job 是否在 queue commit 上运行；不通过就保持 up-to-date。

**结构影响：** 可能增加一个队列入口；不改变 C 的检查逻辑。

---

## P2 — 后续改进

- 事故级指标按 `incident_key` 聚合；usage 仍按 case 历史保留，不迁移、不相加。
- 合并两个 panel 实现，保留一个 reader、一个渲染器。
- 记录候选 precision、review 时长、local-only 比例；用真实样本替代合成标注集。
- 对高价值 case 要求至少一份脱敏 committed material；报告 local-only 比例。

---

## 结构代价汇总

| 面 | 改动 | 影响 |
|---|---|---|
| 草稿 | 平铺文件 → UUID 目录 + 四文件 | 所有路径假设要改；旧草稿保留 `legacy_flat` |
| Reader | 新增统一接口 | groom/panel/sediment 都要迁移；兼容期两套路径 |
| Decision | 新增进 Git 的 YAML | 每个相关 PR 多一个文件；评审多一步 |
| Provenance | 新增进 Git 的 manifest；材料可选 | 只有 committed 材料可恢复；local-only 要标注 |
| CI | 聚合 required check、approval、up-to-date | PR 全量跑；docs-only 也跑；bot 需要 bypass |
| 指标 | 期号后缀、白名单/强度 | 旧期号兼容；schema 变更 |
| 历史数据 | 不迁移 | 已合入 case/reference/fixture/usage 不动；rename 才迁移 |

## 最小可上线范围

P0 全部完成。P1 中至少先做 overflow gate 和 rename/usage 迁移，否则“候选可见”和“引用不丢”仍不完整。P2 不阻塞上线。
