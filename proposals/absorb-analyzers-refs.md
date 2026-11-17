# 版本 A：把分析经验沉淀成先验知识

本分支是人工对照试用的版本 A，相对固定共同起点只增加先验词条及对应生成索引，不改诊断流程、不加工具。试用方案见 [`analyzer-arms-experiment.md`](analyzer-arms-experiment.md)。

## 要做的事

把外部 8 个分析器里**与具体事故无关**的判据、阈值、读法沉淀成 reference 词条。代码不搬：脚本、HTML 模板、采集动作都留在外面。

以下是六个候选方向，本轮按试用主题选取，不要求每个方向都产出词条：

| 面 | 主要来源 | 拟落类型 | 备注 |
|---|---|---|---|
| BMC / 硬件 | `judgement.md`、`versions.md` | platform-fact + methodology | 先查现有覆盖；硬件阈值要核原始规范 |
| Host / CPU | `analysis_v2.md`、`binding_workflow.md`、`npu_numa_binding.md` | tool + methodology + command-side-effect | 绑核副作用要单独一条 |
| Prof 判读 | `recipes_catalog.md`、`analysis_methodology.md`、`db_schema.md` | tool + methodology | 逐项核实来源，不预先承诺全部为官方 |
| 故障日志取证 | `fault-patterns.md`、`log-structure.md`、`analysis-strategy.md` | methodology + tool | 重点是「逐字回验」与「首个错误」 |
| 环境 / 版本配套 | `dump_format.md`、`version_compatibility.md`、`compatibility_matrix.json` | compat-matrix + software-fact | 与仓内现有 compat 矩阵去重 |
| 推理调优 | 上游调优 references 与模型配置 | methodology + software-fact | 补推理侧空白 |

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
4. 跑 `python3 scripts/verify_references.py --check`；按 `references/README.md` 生成并检查读侧索引，确认新词条可检索。试用检出中的生成物不作为手改内容提交。
5. 跑 `python3 scripts/index_read_cost.py` 记录实际读量；区分先验层与 case 索引，不能把 case 类视图的阈值直接当成先验容量门槛。

## 现状

分支里还没有词条。先按开发材料准备本轮主题相关内容；正式试用案例与答案不用于编写词条。知识来源逐项核实，不把作者经验标成官方。

试用时按自然诊断路径读取；未采用新词条仍是 A 的结果，记录原因。试用只支持本批案例的工程判断，不设准确率提升门槛。
