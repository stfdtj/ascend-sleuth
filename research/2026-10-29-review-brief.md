# 并发知识入库 V2：技术评审 Brief

**一句话：** 当前系统在单人、单 PR 时是可靠的；多工程师并发时，会出现“内容丢了、检查还是绿的”
静默失败。V2 的目标不是做一个分布式系统，而是用三件事把失败变可见、把关键决定变成平台强制：
**Draft 有唯一身份且读者严格**、**候选有优先级且人写决定**、**合入前对最新集成状态复核并由
required check + up-to-date 强制执行（merge queue 可选 P1）**。Provenance 和指标只承诺能验证的部分。

---

## 执行摘要（给技术 lead）

- **已复现：** 同名草稿并发 10/10 轮一方静默消失；两个 clone 对同一问题写不同 Case ID，两种合入
  顺序都 0 冲突、全部检查绿；解冲突取一边后另一边内容消失、全部检查绿；不相邻字段各自修改后
  合并出语义矛盾的 Case、全部检查绿；改 Case ID 后引用/使用记录报错但夹具只警告、trace 不检查；
  两台机器生成同期号指标，解冲突只留一份且无检查。
- **已确认的实现事实：** 生成物在 main 上由 job 重建（API 观测到 6 次运行，已查看的成功）；但
  仓库 ruleset 只要求 PR，**0 个批准、没有必需检查、没有“分支必须最新”**。所以“复核报告”今天
  只是一份文件，作者可以在检查红、分支旧的情况下合入。
- **新发现：** E11 全数字短 SHA 会让 entry-activity 生成器崩溃（post-merge job 停更）；E12 周快照
  生成器的输出被自己的校验器判红；E14 inbox 没有 reader contract。
- **V2 做法：** 保留 Git 协作模型，不引入服务器/锁/实时同步。新增 O 同步层（`kb_sync`、`pr_radar`）、
  A 草稿协议（UUID + DONE + 严格 reader）、B 候选（同一比较器、三层优先级、展示预算与 ack）、
  C 合入复核（字段级 diff、decision 文件、required check + up-to-date）、D provenance（committed
  manifest + 可选脱敏材料 + 如实标注 local-only）。
- **成本：** 开发 34–51 人天（P0 13–19，P1 13–20，P2 8–12），平台/管理员 2–4 人天，评审/发布 5–8
  人天；运行成本是每次 groom 多 20–40 分钟、每个 PR 多 5–15 分钟。
- **需要拍板：** 是否上 required check + 1 个非作者批准 + up-to-date（merge queue 可选 P1）、
  DEPLOY_KEY bypass；是否先做 P0；provenance 的材料政策；谁做 reviewer/owner。

---

## 1. 今天为什么“不安全”

先说结论：不是哪个脚本写错了，而是**检查的对象和并发的事实不匹配**。现有检查回答的是“这棵树自
不自洽”，不回答“另一个人有没有写同一件事、我手里的结论是不是过期了、解冲突有没有丢内容”。

三个真实复现的场景（合成内容、一次性 clone，未动生产）：

1. **两个工程师、两个 clone、同一个问题。**
   A 写成 `interrupt`（310P 不支持 bf16，启动失败），B 写成 `precision`（同一根因，表现为输出全 0）。
   两人的 groom 都只看自己 `(namespace × category)` 的索引视图，都判 `new_pattern`。
   先 A 后 B、先 B 后 A 两种顺序：**0 个 Git 冲突，所有检查通过，两条 Case 都进索引**。
   诊断时最多加载 5 条候选，两条重复各占一个名额，还会分散使用计数。

2. **同一个 inbox、同名草稿。**
   同一 clone 的两个 worktree 共享 `postmortems/inbox/`（`shared_dir.py` 的设计）。两个 writer 同时
   写 `VLLM-ASC-90001.case.yaml`：**10/10 轮只剩一个人的内容，文件仍是合法 YAML**；流式写 3/3 轮
   产生混合内容；崩溃留下半套材料，唯一的草稿检查不会跑，groom 看到的是一个正常文件名。

3. **同路径冲突，取一边。**
   A/B 都新建 `VLLM-ASC-90003`，根因不同。Git 给 `add/add` 冲突；最快的解法 `--ours` 后，B 的根因
   和修复完全消失；重建索引后 `verify_case_draft`、`build_index`、`verify_references`、
   `verify_entry_activity`、`verify_metrics`、`holdout`、`eval_scorecard` **全部通过**。
   检查证明不了“贡献还在”。

另外三个已复现：同一 Case 的不相邻字段各自修改 → 干净合并出“compat 说 0.21 也受影响、diagnosis 说
只有 0.22 有这条路径”的矛盾；A 合入后 B 的“新增”判断过期但没有任何 recheck；两台机器同一天生成
同期号（同一周的同一天），内容不同，解冲突只留一份，指标检查不报“少了一期”。

**为什么以前没暴露：** 单人时这些条件不成立；一旦两人并发，Git 的文本合并成功被误读成“知识合并
成功”。这正是验证报告里 E1–E10 的共同结构。

---

## 2. 实验到底证明了什么（可信边界）

评审时请区分四类结论，不要把原型当生产：

| 类别 | 例子 | 可信度 |
|---|---|---|
| 已核实的实现事实 | inbox 锚主检出、14 个 CI job、生成物 job 存在且运行成功、ruleset 只有 PR 规则、`verify_entry_activity` 认 `_archive` | 代码/配置/API 读取 |
| 已复现的问题 | E1–E6、E8–E10；E7 在“无 job 的部署”下复现；E11/E12/E14 | 一次性 clone 真跑仓库脚本 |
| 原型结论 | A 的 13 个测试（8 并发、3 种崩溃、hash、legacy）；B 的 D1–D11；C 的六场景 | 原型代码，不是产品实现 |
| 未验证 | GitHub required check/up-to-date/approval/bypass 的真实行为；两个面板；真实规模；NFS；真实标注集 | 必须在生产前验证 |

**关于数字：** B 的 V2 设计实验在 11 个合成 Draft × 173 条真实 Case 上得到：4 个 mandatory（另有
1 个 draft-draft 对）、17 个 high、279 个 low、展示 31 个、隐藏 high = 0；D1–D11 的 9 个必审对全部
生成并展示，D11 无关对照不展示。但合成夹具的 root/fix 文本高度相同，**真实库的召回和工作量必须用
真实标注样本重跑**，这个数字只能证明机制，不能当生产准确率。

**GitHub 侧：** 只读了公开 API，没有创建 PR、没有改 ruleset。当前事实是已生效的
`main-protection` ruleset：PR 必需，`required_approving_review_count=0`、无 required status checks、
无 up-to-date。这个事实必须作为评审前提，而不是“文档说已经保护了”。

---

## 3. V2 架构：三层，一个比较器

```
诊断 ── trace(kb_rev) ──► A 草稿队列 ──► B 候选+决定 ──► PR ──► C 合入复核 ──► up-to-date ──► main
   ▲                         UUID/目录/       同一比较器      decision   字段级 diff/       required      │
   │                         DONE/严格 reader  tiers/预算      file       过期检测          kb-required   │
   └── O 同步层：kb_sync（诊断/PR 前对齐 main）、pr_radar（groom 时看开放 PR）                          ▼
                                                                                     post-merge 重建 + 心跳
                                                                                              │
                                                                                    Provenance / refs / metrics
```

一句话解释每个 Checkpoint：

- **A（Draft 安全）**：每次沉淀生成一个 UUID 目录，写 `case.yaml/postmortem.md/sources.yaml`，最后
  原子发布 `DONE`（tmp + `os.replace`）。所有消费者用同一个 reader：`complete/incomplete/corrupt/
  superseded/legacy_flat`，只消费 `complete` 和旧平铺。UUID 解决“同名覆盖”，DONE+hash 解决“半套被
  消费”，`reopen` 解决“完成后修改”。
- **B（升格前候选）**：`case_match.py` 是唯一比较器，复用索引已有的 `sig`/`tok`。候选分三层：
  **mandatory**（共享 upstream/同 ID/同路径/同 event/强判别式）永远展示且必须有决定；
  **high**（同格/跨分类/有理由的跨 namespace/root-fix 重叠/条件重叠/证据复用）最多展示 30 对，超了
  必须写 `ack_overflow`（明确“没看”，不是“已审核”）；**low** 只报数量，不要求决定。
  人把 `new/variant/covered/deferred/separate` 写进 `postmortems/decisions/<case>.yaml`。
- **C（合入复核）**：同一个比较器，对最新 `origin/main` 与 PR head（或 merge candidate）重跑；同 Case
  做**字段级 diff**（不是整份取一边）；检查同路径 add/add、删除/重命名+引用、生成物、decision 过期。
  退出码 0/1/2/3/4 直接给 CI。C 不判断语义。
- **D（Provenance）**：每个新/合并 Case 一个 manifest，记录 materials、字段归属、被舍弃内容去向、
  event_id、lineage、incident_key。**提交到 Git 的只有脱敏结构化材料**；本地原始日志/trace 标
  `local-only`，CI 不假装能验证。能验证的 hash/存在性才叫 `verified`。
- **O（同步层）**：`kb_sync.py` 在诊断开始记录 `kb_rev`/落后状态，在 groom/PR 前
  要求最新；`pr_radar.py` 在 groom 时看开放 PR 的 Case（已验证 378 个 PR ref 可见、单个 head 可 fetch）。
  这两件事降低“完全没看见”的概率，但**不替代 C 的 required check**。

---

## 4. 关于 pull / 搜 PR / 诊断前更新的建议：采纳，但要分层

> “PR 前/groom 时 `git pull`，搜一下已有 PR；诊断前更新知识库。”

**方向完全正确，V2 采纳为 O1/O2。** 但要避免把它当成安全保证：

- `git pull` 只把你更新到某一时刻；之后 main 再前进，你的复核又旧了。没有“分支必须最新”，平台
  仍允许合入旧分支（merge queue 可选，不是 P0）。
- 搜开放 PR 很值：A 的 PR 还没合入时，B 的 groom 就能看到 A 的 Case，提前判 variant/covered。但
  依赖网络/权限；PR 可能在你检查后更新；没有 token 时只能按 PR 编号取最近 N 个，无法区分 open/closed。
- 诊断前更新知识库改善候选质量，但诊断读的是本地检出；更新必须记录 `kb_rev`，且不能中途变，否则
  一次诊断的结论无法复现。
- 这三条都不解决本地草稿覆盖——草稿不在 Git 里，pull 看不到。

所以 V2 把它们做成脚本（可执行、可记录、失败可降级），把“阻止”留给平台。**如果平台改动未获批准，
V2 只能承诺“检测与记录”，不能承诺“阻止合入”**，这句话要写进评审结论。

---

## 5. 解决了什么、没解决什么

| 问题 | V2 后 | 说明 |
|---|---|---|
| 同名草稿覆盖 | **预防** | UUID 目录 + 独占 mkdir；绕过工具直接写仍不受保护 |
| 半套/损坏草稿被消费 | **预防** | DONE + hash + reader；崩溃目录只报告 |
| 同问题不同 ID 入库 | **检测 + 决定** | mandatory/high 候选 + decision；语义相同但措辞完全不同的仍可能漏 |
| 跨分类/跨 namespace 重复 | **部分检测** | 跨分类默认查；跨 namespace 有理由才查；不保证完整召回 |
| 同路径冲突丢内容 | **检测 + 人决定** | C 报双方 + 字段 diff；CI 不能保证人合对 |
| 干净合并但语义矛盾 | **只能人判断** | C 报“同 Case 修改/字段重叠”，不判语义 |
| 合入时判断过期 | **平台强制** | decision 的 main_sha/head_sha + required check + up-to-date；依赖管理员 |
| 改 ID 破坏引用/夹具/记录 | **大部分强制** | refs/entry 硬检查，fixtures 警告，trace/provenance 靠工具与 manifest |
| 同期号指标冲突 | **预防/检测** | 期号带 deployment id；旧文件兼容；仍需平台/周报确认 |
| 数字 SHA 崩生成器 | **修复** | P0，字符串化 + 回归测试 |
| 周快照被自己的校验器判红 | **修复** | P0，白名单/强度档 + 生成-校验测试 |
| 生成物 job 失败 | **可见** | 每日 main 心跳开 issue；不替代 job |
| 规则集无效 | **平台改动** | required check + 1 批准 + 最新 + bot bypass |

**明确不保证：** 候选 100% 召回；CI 判断语义；reviewer 一定认真；本地-only 证据可复核；没有平台
改动时能阻止合入。

---

## 6. 成本与优先级

| 阶段 | 内容 | 开发 | 平台/管理员 | 运行成本 |
|---|---|---|---|---|
| **P0** | `kb-required` + 批准 + 最新；E11/E12 + main 心跳；A 草稿协议 + reader；最小 C（字段 diff/decision/过期） | 13–19 人天 | 1–2 天 | 每次沉淀 +2 命令；每 PR +5–15 分钟 |
| **P1** | B 完整（tiers/预算/ack/跨 ns/radar）；provenance + rename；E10；面板契约 | 13–20 人天 | 0 | 每 groom +20–40 分钟 |
| **P2** | 决策指标/标注集；事故级计数；文档/技能收尾 | 8–12 人天 | 0 | 每月 1–2 小时 |
| 合计 | | **34–51 人天**（中位 ~42） | 2–4 天 | 评审/发布 5–8 天 |

V1 估算 20–30 人天；V2 增加了 decision 检查、PR radar、provenance 检查和面板契约测试，减少了独立
六轴比较器和全库关键词扫描。**这是工程判断，不是承诺**；P0 可以独立验证、独立回滚。

---

## 7. 需要拍板

1. **平台：** 是否批准 required `kb-required`、1 个非作者批准、dismiss stale/last-push approval、
   up-to-date（merge queue 可选）、DEPLOY_KEY 只给 rebuild job bypass。
2. **范围：** 是否接受“P0 = A + 最小 C + E11/E12/心跳”，B 完整版放 P1。
3. **Provenance：** 是否接受“manifest 必交、脱敏材料可选提交、local-only 如实标注”的政策；谁定
   隐私边界。
4. **人：** 谁做 CODEOWNERS/reviewer，谁承担每周 20–40 分钟 groom。
5. **表述：** 是否接受公开写“候选不保证召回、CI 不判断语义、没有平台强制就没有阻止”。

---

## 8. 风险、回滚、下一步

**主要风险：** 平台不批 → C 退化；reviewer 疲劳 → 走过场；候选漏报 → 重复仍入库；decision 造假 →
机器门失效；面板两份实现漂移；local-only 证据无法复核；E11/E12 不修则数据面继续坏。

**回滚：** 每一步先 report-only 观察 1–2 周，再改 required；平台回滚只需移除 required check；
A 保留旧平铺 reader；B/C 关闭 CI job 即回旧检查；provenance 可从 block 降为 report-only；生成物始终
由 job 或 `rebuild_generated --sync` 重建。

**评审后的第一步：** 在测试仓库/测试 PR 上验证 required check、批准失效、分支落后、bot 推送；同时修
E11/E12 与 main 心跳。验证通过后再动生产 ruleset。

---

## 9. 证据入口

- 总览与复现说明：`../diagnostics/concurrency-validation/README.md`
- 当前实现：`../diagnostics/concurrency-validation/01-current-workflow.md`；基线复现：`../diagnostics/concurrency-validation/02-baseline-findings.md`
- A/B/C 原型验证：`../diagnostics/concurrency-validation/03-solution-validation.md`、`../diagnostics/concurrency-validation/05-test-matrix.md`
- 决策与开放问题：[设计决策日志](2026-10-29-design-decisions.md)
- Q&A：[评审 Q&A](2026-10-29-review-qa.md)
- 原始记录：`../diagnostics/concurrency-validation/artifacts/logs/`
- V2 B 设计实验：`../diagnostics/concurrency-validation/artifacts/logs/checkpoint-b-v2.json`（合成夹具，仅机制验证）









