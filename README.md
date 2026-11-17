# 人工对照试用 B：在诊断中调用分析器

这条分支与另一版一起做人工对照试用：原作者选 4–6 个案例，每题让 A、B 各开一个独立对话，再人工看哪个更有用。先决定迁哪些能力、哪里需要改，不做总体准确率验收。

项目原本的说明在 [main 分支](https://github.com/pillumina/ascend-sleuth)。两版共同执行 [人工对照试用方案](proposals/analyzer-arms-experiment.md)，本页只说明开始方式与本版条件。

## 原作者怎么开始

准备每个案例的题干和脱敏材料。另写根因、正确处置、关键证据和可补充事实，答案仅留给原作者与评审者。案例包含一两个材料不足或分析器不适用的情形；用于开发的样例与正式试用案例分开。

```text
trial-input/case-01/question.md
trial-input/case-01/materials/
trial-input/case-02/...
review-only/answers.md           不给诊断对话访问
review-only/supplements/
review-only/comparison.md
```

准备完成后，向组织试用的 agent 提供材料目录，并说明本轮要比较的主题。答案不放入诊断工作区。组织者确认两版就绪后，为每题分别开 A、B 两个干净对话，只发相同题干与材料。

原作者按实际事实回答追问，记录补料及轮次。两份结果并排看，先隐藏版本标签更好；选「A 更好／B 更好／差不多／都不行」，写明具体理由。差异明显的案例，两版再各跑一次，保留全部结果。

## 本版开跑条件

本分支已有工具接入骨架，但八个分析器实现尚未分发。先迁入本轮需要的分析器，并修复超时、异常退出或损坏 JSON 被记成功的问题，再完成实际宿主验收。当前只能验收接线，不能比较诊断效果。

诊断按实际步骤 5 的条件调用分析器，不额外要求「有包必调」。工具发现只作证据或候选解释；失败、未调用和未采用都保留为 B 的结果。

## agent 执行边界

- 按共用方案隔离检出、状态目录和上下文。只开新对话或两个共享状态的 worktree 不够。
- 固定模型、两版提交、已有知识与通用工具权限；不让诊断 agent 读答案或继承开发讨论。
- 保留对话、trace、报告与补料记录；调用分析器时还保留结构化结果。正确停止或要求补证也能优于贸然给修复。
- 不替工程师安装依赖、改机器配置或运行现场实验。开发环境准备与正式试用分开。
- 不因未用新增能力而换组，不删除失败或双方全错的案例，不设准确率提升硬门槛。

## skill 清单

<!-- BEGIN generated: skill-roster (scripts/build_docs_index.py；由 docs/_manifest.yaml 生成，勿手改) -->
本仓共 **13 个面向使用者的 skill**，按使用场景分 4 组：
- **日常问答**（1）：`ask`（一句话能问完的问题直接答（码、变量值、某类怎么定位、术语、库里有吗），症状定位转 diagnose）
- **日常诊断**（2）：`diagnose` · `resume-diagnosis`
- **知识沉淀**（4）：`to-postmortem` · `to-reference` · `issue-ingest` · `reference-ingest`
- **维护与演进**（6）：`knowledge-groom` · `self-evolve` · `evolve-check`（内部协议，由内容流程收尾自动转接，不单独调用） · `skill-review`（内部协议，由用户显式触发做 skill 质量审视） · `preload-panel`（仅 DSH：按本机给模型的工具定装载路，有 cordis_define / cordis_run 热加载，有 plugin_manager 装常驻插件包，DSH Desktop 用安装目录自带的 dsh 命令行装（profile 记成 link），另有脚本经 /api 通路装与插件页粘贴两条备用路；含「装了但 tab 不出现」的排查顺序） · `doctor`（本机环境体检：一条命令报「哪些流程能跑、哪些会降级」并给修法；只读，不装包）
<!-- END generated: skill-roster -->
