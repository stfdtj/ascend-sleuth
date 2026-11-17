# 臂 A：把 8 个分析器沉淀成先验知识

本分支是对照实验里的**臂 A**，相对 `main` 只允许加 `references/` 下的词条，不改诊断流程、不加工具。对照方案见 [`analyzer-arms-experiment.md`](analyzer-arms-experiment.md)。

## 要做的事

把外部 8 个分析器里**与具体事故无关**的判据、阈值、读法沉淀成 reference 词条。代码不搬：脚本、HTML 模板、采集动作都留在外面。

按六个面推进，每面产出若干词条：

| 面 | 主要来源 | 拟落类型 | 备注 |
|---|---|---|---|
| BMC / 硬件 | `judgement.md`、`versions.md` | platform-fact + methodology | sleuth 现在 0 条，整面空白；阈值要核官方 |
| Host / CPU | `analysis_v2.md`、`binding_workflow.md`、`npu_numa_binding.md` | tool + methodology + command-side-effect | 绑核副作用要单独一条 |
| Prof 判读 | `recipes_catalog.md`、`analysis_methodology.md`、`db_schema.md` | tool + methodology | 官方来源可核，优先级最高的第一批 |
| 故障日志取证 | `fault-patterns.md`、`log-structure.md`、`analysis-strategy.md` | methodology + tool | 重点是「逐字回验」与「首个错误」 |
| 环境 / 版本配套 | `dump_format.md`、`version_compatibility.md`、`compatibility_matrix.json` | compat-matrix + software-fact | 与仓内 4 份 compat 矩阵去重 |
| 推理调优 | 18 篇 references、19 个模型配置 | methodology + software-fact | 补推理侧空白 |

## agent 要做什么

逐条走 `to-reference` 的流程：提取 → 判类型 → grill 确认 → 去重 → 产 `references/<type-dir>/<id>.yaml`（`status: active`）→ 随 PR 提交。**每个词条必须回答三件事**：补的是哪个诊断缺口、适用范围（平台 / 版本 / 性质）、什么情况下不成立。

来源分级不许混：能逐字对到官方原文的标 `official-doc` + `cross-checked-source`；只有作者手记的标 `engineer-input`。上游没有官方出处的阈值，**不得**标 `official-doc`。

## 产出

- `references/<type-dir>/<id>.yaml`：词条本体；
- PR body 的「来源与验证状态」：每条词条一行，写来源类型、核到哪一页、还缺什么；
- 一份本期新增清单：`id / 类型 / 补的缺口 / 来源类型`。

## 验收看什么

1. 每条词条能指到具体缺口——做不到就是复述，不算融合；
2. 来源标注与来源能力一致（拿不出官方原文的不许标官方）；
3. 与现有词条不重复：新增前先跑一次去重扫描，重复的并进 `applies_to` 或标为变体；
4. 读侧成本：新增后跑 `python3 scripts/index_read_cost.py`，类视图不超线（软 8000 / 硬 20000 token）。

## 现状

分支里还没有词条，等第一批（建议从 Prof 判读与故障日志取证开始，官方来源可核）。词条进库后，本臂相对基线的差异就是「诊断时能读到这些条目」，其它一切不变。
