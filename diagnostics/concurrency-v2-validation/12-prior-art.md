# 12 — Prior art: duplicate detection, review gates, provenance

## 0. 结论

V2 不是新发明。它把四类成熟做法拼在一起：

1. 重复 bug/issue 检测：候选生成 + 排序 + 人确认；
2. entity resolution / record linkage：相似度、blocking、人工裁决；
3. PR 合并门：required check、approval、up-to-date、merge queue；
4. provenance / decision record：来源、派生、决定、审计。

真正需要自己补的不是“有没有类似系统”，而是 **在 Ascend-Sleuth 这个知识库上的标注数据、阈值和评审质量**。

---

## 1. 重复 bug / issue 检测

这是最接近 B 的工程领域。代表性工作：

- Runeson, Alexandersson, Nyholm, *Detection of Duplicate Defect Reports Using Natural Language Processing*, ICSE 2007。用 NLP 文本相似度判断重复缺陷报告。
- Sun et al., *A discriminative model approach for accurate duplicate bug report retrieval*, ICSE 2010。把重复检测做成排序/检索问题，用判别模型组合多类特征。
- Nguyen et al., *Duplicate bug report detection with a combination of information retrieval and topic modeling*, ASE 2012。把 IR 与 topic model 结合。
- Qian et al., *A Survey on Bug Deduplication and Triage Methods from Multiple Points of View*, Applied Sciences 2023。综述重复 bug 检测与分诊方法。

共同模式：

```text
文本/结构化特征
  → 候选检索（IR / blocking）
  → 排序或分类
  → 人工确认 duplicate
  → 关闭/链接到原报告
```

对我们的直接启发：

- 只做词面相似会漏“换一种说法”的重复；论文里也普遍需要多特征或语义模型。
- 评价不能只看“9/9 都展示了”，要看 recall@k、precision@k、reviewer workload。
- 候选生成和最终判定要分开；自动系统通常只做“possible duplicate”，不自动关闭。

差异：我们目前是确定性规则，不是学习排序；可解释性好，召回上限低。要提升，先加真实标注，不要直接上 embedding。

---

## 2. Entity resolution / record linkage

重复 case 也可以看成一类 record linkage 问题：

- Fellegi & Sunter, *A Theory for Record Linkage*, JASA 1969。经典的 probabilistic record linkage：比较向量、match/non-match 权重、阈值。
- 现代 entity resolution 通常分为 blocking、pairwise matching、clustering、human adjudication 四步。
- *Learning-Based Methods with Human-in-the-Loop for Entity Resolution*, CIKM 2019。人给标签/判断，系统学习匹配规则。
- *View-Driven Deduplication with Active Learning*。主动选择最有信息量的 pair 让人标注，降低标注量。

对我们的直接启发：

- B 现在是 `draft × library` 全量比较；173 条可以，规模上来需要 blocking/index。
- 规则阈值应该用真实 pair 校准，而不是凭感觉定 0.5。
- 人工判断不是失败，是 entity resolution 的标准组成部分；关键是让人只看高信息量 pair。
- 观测期可以用 active learning 的思路挑 pair 做标注，而不是随机抽样。

差异：我们没有概率模型，也没有聚类；两份 draft 各自保留，由 decision 决定合并/变体。

---

## 3. 人工在环与评审质量

- Bacchelli & Bird, *Expectations, Outcomes, and Challenges of Modern Code Review*, ICSE 2013。现代代码评审的实证研究：评审能发现缺陷，但受理解成本、评审者经验、变更大小影响，不是纯机械门。
- Stack Overflow 的 duplicate question 机制：社区投票、关闭为 duplicate、链接到原问题；保留原问题，不删除。
- Bugzilla 的 duplicate 关系：标记 duplicate、指向原 bug；保留历史。

对我们的直接启发：

- decision gate 只能保证“有人做了记录”，不能保证“记录质量”。
- 需要抽样审计 note 是否说明证据、选择和理由；否则会变成 `note: "looks fine"`。
- duplicate 处理应该保留原内容并建立链接，而不是静默删除；我们的 `covered`/`merge` + provenance/redirect 应该保留来源。

差异：Stack Overflow 是社区投票，我们是小团队 + agent；投票信号弱，审计更重要。

---

## 4. PR 合并门与 merge queue

这是 C 和平台强制的直接 prior art：

- GitHub required status checks：
  - required check 必须在最新 commit SHA 上通过；
  - 成功状态包括 `success`、`skipped`、`neutral`；
  - workflow 被 path/branch/message 过滤掉时，check 会停在 pending 并阻塞；
  - job 被条件跳过时，check 可能报告 success；
  - 依赖 job 失败导致 dependent job skipped 时，可能不阻塞；
  - 需要 required check 依赖其他 job 时，用 `always()` + `needs`。
- GitHub rulesets：required checks、approval、dismiss stale review、up-to-date。
- GitHub merge queue：用 `merge_group` 事件在队列的临时合并 commit 上运行检查。
- Zuul project gating：speculative execution、pipeline window、cross-project gating；在合并结果上跑测试。
- Bors / bors-ng：PR 排队、在合并结果上验证、失败重试。

对我们的直接启发：

- 我们的 S6/S7 担心是对的，而且比想象的更细：**不能依赖“job skipped 会红”**。必须让 `kb-required` 自己始终运行，并检查 `needs` 的结果。
- required check 必须看最新 SHA；up-to-date/merge queue 不是装饰。
- workflow 级 `paths` 会让 required check 永远不出现；这是必须去掉的。
- merge queue 的 `merge_group` 语义需要单独验证；不要假设它和 `pull_request` 一样。

差异：我们没有采用 Zuul 的 speculative execution；GitHub merge queue 是可选 P1，P0 先用 up-to-date。

---

## 5. Provenance / decision record

- W3C PROV（PROV-Overview、PROV-DM）：entity、activity、agent、derivation、attribution、bundle；用来描述“谁、在什么活动中、从什么实体产生了什么”。
- Architecture Decision Record（ADR）：记录决定的上下文、选项、后果；和我们的 decision YAML 同构。
- 数据 provenance 研究通常区分“来源记录”和“可重现性”；有记录不等于材料可恢复。

对我们的直接启发：

- 我们的 `sources.yaml` / `provenance.yaml` 可以映射到 PROV 的核心关系，但不必引入 RDF。
- PROV 能表达“derived from / attributed to / used”，不能保证本地文件可恢复；这和我们的 `local-only` 限制一致。
- decision 文件应该像 ADR：记录背景、候选、选择、后果，而不只是 `decision: separate`。

差异：我们的 manifest 是领域简化版，没有 PROV 的正式约束和验证器；换来的可读性和 Git diff 友好。

---

## 6. 我们的设计相对 prior art 的位置

| 能力 | 成熟做法 | V2 当前 | 差距 |
|---|---|---|---|
| 候选生成 | IR + 多特征 + 学习排序 | 词法/结构规则 + tier | 缺真实标注、缺 blocking |
| 人工确认 | possible duplicate + 人关闭 | decision 文件 | 缺质量审计 |
| 合并门 | required check + queue | C + `kb-required` 设计 | 平台未实测 |
| 来源 | PROV / manifest | provenance YAML | 无正式约束；local-only 不可恢复 |
| 决定记录 | ADR / Bugzilla duplicate | decision YAML | 缺背景/后果字段；TODO 可过 |

## 7. 最值得借的五件事

1. **把 B 当排序问题评估**：recall@k、precision@k、reviewer workload；不要用“9/9 展示”当准确率。
2. **加 blocking/index**：先按 namespace/category、strong token、upstream 缩小候选，再做 pairwise；173 条不需要，规模上来必须。
3. **主动学习选 pair**：观测期优先标注边界 pair，而不是随机抽样。
4. **decision 按 ADR 写**：背景、候选、选择、后果、证据；拒绝只有一句 `looks fine`。
5. **平台检查按 GitHub 语义设计**：required check 永远运行、检查 `needs`、看最新 SHA；不要依赖 skipped job 报红。

## 8. 最不值得照搬的

- 不要为了“更自动”直接上 embedding/LLM 判重；没有标注时，语义模型也会把“同症状不同根因”判成重复。
- 不要自动关闭/自动合并 duplicate；Bugzilla/Stack Overflow 都保留人工确认。
- 不要引入完整 PROV/RDF 栈；当前规模用 YAML manifest 足够，先保证字段和校验。
- 不要假设 merge queue 能解决语义问题；它只保证“在最新合并结果上跑检查”。

## 9. 参考

- Runeson et al., ICSE 2007: https://dl.acm.org/doi/abs/10.1109/ICSE.2007.32
- Sun et al., ICSE 2010: https://dl.acm.org/doi/10.1145/1806799.1806811
- Nguyen et al., ASE 2012: https://dblp.org/rec/conf/kbse/NguyenNNLS12.html
- Bug dedup survey, Applied Sciences 2023: https://ouci.dntb.gov.ua/en/works/9j1603gl/
- Fellegi & Sunter, JASA 1969: https://doi.org/10.1080/01621459.1969.10501049
- Human-in-the-loop ER, CIKM 2019: https://dl.acm.org/doi/10.1145/3357384.3360316
- Active-learning dedup: https://arxiv.org/abs/1606.05708
- GitHub required checks troubleshooting: https://docs.github.com/en/enterprise-cloud@latest/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks
- GitHub rulesets: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets
- GitHub merge queue: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
- Zuul gating: https://zuul-ci.org/docs/zuul/latest/gating.html
- W3C PROV overview: https://www.w3.org/TR/prov-overview/
- W3C PROV-DM: https://www.w3.org/TR/prov-dm/
- Modern code review: https://zenodo.org/records/1401198
- Stack Overflow duplicates: https://stackoverflow.com/help/duplicates
- ADR: https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
