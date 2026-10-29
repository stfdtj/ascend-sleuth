# 08 — 评审摘要（10 分钟）

## 结论

V2 的方向成立，核心机制在原型里跑通；当前版本不能直接上生产。结论为 **ACCEPT WITH CHANGES**：先做 P0 实施和平台强制试点，暂不把 V2 当作已经具备保护能力的系统。

验证基于当前 `main` 的 `dd3e6b3`。V1 的 10 次同名草稿并发写，10 次只剩一个写者的内容；V2 的 8 个并发 UUID 草稿，得到 8 个不同目录。

## 测了什么

在独立克隆和临时远端上执行了这些测试：

1. 单人端到端：诊断 trace、沉淀、草稿校验、升格、PR 检查、合并、重建、检索。
2. 两名工程师从同一 `main` 出发，写同一根因、不同 case ID、不同 category，先合 A，再让 B 基于新 `main` 重跑检查。
3. 共享 inbox 的并发写、崩溃点、重复 finish、完成后修改、`reopen`、旧格式草稿。
4. D1–D11 标注集上的候选生成与展示。
5. C 的过期 decision、same-path 冲突、同 case 字段冲突、rename、生成物改动。
6. provenance 的 committed/local-only、缺失目标、重复 event ID、lineage、redirect。
7. E10、E11、E12 的当前行为与原型修复；S9 的索引过期检测。

## 通过了什么

- **Checkpoint A 主路径**：UUID 目录、原子 `DONE`、sha256、严格 reader、重复 finish 拒绝、完成后修改报 `corrupt`、`reopen` 生成新 UUID。8 个并发创建无覆盖。
- **Checkpoint B 标注集**：D1–D11 中 9 个应展示的 pair 全部展示，D11 未展示。11 个草稿对 173 条库，mandatory 6、high 36、low 285，展示 46；high 上限 30，隐藏 high 6、low 275，隐藏数量有计数。
- **Checkpoint C 检测**：不同 ID 同问题、无 decision 时退出 2；decision 完整时退出 0；`main` 前进后退出 1；same-path 冲突退出 3；同 case 字段重叠退出 3；生成物改动退出 4；rename 加另一侧引用退出 3。
- **集成流程**：A 先合入并重建；B rebase 后 C 返回 1，模拟 required check 挡住合并；B 补 decision 后 C 返回 0，合并、重建、检索都能找到两个 case。
- **E11/E12 原型修复**：当前 E11 在 `entry_activity.py:495` 抛 `TypeError`，改 `sorted(str(x) for x in checkouts)` 后通过；当前 E12 的 snapshot 被自己的 validator 报 2 个错误，补 live 白名单和 6 个 strength 声明后通过。
- **S9**：不重建索引时心跳返回 1，重建后返回 0。

## 没通过、没测到什么

- **`reopen` 崩溃窗口**：新草稿先完成、旧草稿的 `SUPERSEDED` 后写；在两步之间崩溃，两个目录都是 `complete`。reader 不反查新草稿的 `supersedes`。
- **decision 占位符可以通过**：把 pair 的 `decision` 写成 `TODO`，C 仍返回 0；`same_case` 的 `TODO` 也返回 0。
- **decision 没有绑定被合并的内容**：decision 记录 `head_sha`，但 C 不比较；decision 通过后再改 case，只要 pair 集合不变，C 仍返回 0。
- **high overflow 没有在 groom 处拦住**：B 报 `hidden_high=6`，但没有 promotion gate；C 只在 PR 阶段检查 `overflow.ack`，且不校验 ack 里的隐藏数量。
- **reader 只迁了 B**：groom、`to-postmortem`、`sediment_batch` 和两个 panel 没有做契约测试；绕过 reader 仍可能读到半套文件。
- **provenance 的可恢复性有限**：committed 材料能校验哈希；local-only/declared 只能标注，不能恢复；rename 工具、usage/refs/fixtures 迁移没有实现。
- **E10 仍未修**：两个克隆仍选同一个 `2026-W44-live-1029` 期号；V2 的 deployment id 后缀没有落地。
- **E13 没有实测**：当前 ruleset 仍是 0 required approvals、无 required checks、无 up-to-date；集成里的“挡住”是 harness 模拟，不是 GitHub 行为。
- **跨 namespace、真实大规模、NFS/SMB**：没有测；B 的数字来自合成标注集，不能当生产 precision/recall。

## 和 V1 的主要变化

1. 草稿身份从“case ID + 人起名”改为 UUID；完成状态与文件内容分离，reader 统一返回 `complete/incomplete/corrupt/superseded/legacy_flat`。
2. 候选生成和展示分开：mandatory 不受展示上限影响；high 有全局上限和隐藏计数；low 是明确未审的 watchlist。
3. B 和 C 共用一个比较器；C 不再另写一套重复检测。
4. decision 从 PR 描述变成提交进仓库的 YAML；CI 可以检查覆盖和过期，但不能判断语义。
5. provenance 区分 committed、local-only、declared；不再把本地路径加哈希当成可恢复证据。
6. 平台强制被单独列为必要项，不再把“报告里有警告”当成“合并被阻止”。

## 推荐架构

保留 V2 的四层：UUID 草稿与严格 reader；一个 B 比较器加分层展示；C 在最新 `main` 上重算并检查 decision；provenance 只对可访问材料承诺完整性。平台侧使用 required `kb-required`、1 名非作者 approval、up-to-date；merge queue 先做 spike，验证 `merge_group` 语义后再决定。

## 实施顺序与结构代价

**P0（生产前必须做）**

1. 平台强制 spike：在一次性仓库验证 required check、approval、up-to-date、skipped、bot bypass、check name；见 [10 平台强制 Spike 方案](10-platform-enforcement-spike-plan.md)。
2. decision 绑定内容：拒绝 `TODO`/空值，校验 `head_sha` 或内容哈希，补 `same_case` schema，校验 ack 数量。
3. `reopen` 原子性：先写旧 `SUPERSEDED`，再发布新 `DONE`；reader 反查 `supersedes`。
4. 所有 consumer 走 reader，补 groom/panel 契约测试。
5. E10/E11/E12 生产修复。
6. 按 spike 结果启用 required checks、approval、up-to-date、bot bypass。

**P1**：B 先做 logging-only 观测和 batch-ingest 双实例测试，数据支持后再上 groom overflow gate；B 阈值校准和真实负样本；rename/usage/refs/fixtures 迁移；跨 namespace 与 panel 测试；merge queue 评估。见 [11 证据与批量并发方案](11-evidence-and-batch-collision-plan.md)。

**P2**：incident 级指标、panel 合并、review 时长与候选精度观测、local-only 比例报告。

结构代价集中在五处：

- 草稿从平铺文件变成 UUID 目录加四文件，所有路径假设要改；旧草稿保留 `legacy_flat`。
- reader 成为唯一入口，groom、panel、`sediment_batch` 都要迁移；兼容期同时有两套路径。
- decision 和 provenance 成为进 Git 的文件，PR 多一个 YAML；只有 committed 材料可恢复。
- CI 增加聚合 required check、approval、up-to-date；docs-only PR 也要跑。
- 历史 case/reference/fixture/usage 不迁移；rename 才触发迁移。

现有 inbox 草稿不做强制批量迁移，继续按 `legacy_flat` 读取；需要继续使用的逐份迁移，迁移工具、备份和回滚见 [09 实现设计与迁移方案](09-implementation-design-and-migration.md)。

## 一句话

V2 把没有检查的流程改成了有检查、有 decision 记录的流程；检查还没有绑定到被合并的内容。先做平台 spike，再按 P0 修 decision/reader/E10-E12；required check 用受控远端验证能阻止不合格合并，之后才谈生产采用。
