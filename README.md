# 这 8 个 skill 被我们改成了什么（给原作者看）

项目原本的说明在 [main 分支](https://github.com/pillumina/ascend-sleuth)。**本分支是版本 B：把你的程序一起装进来。**

## 你的 skill 其实是两半

一半是说明文字，告诉 agent 遇到这类问题该怎么想；另一半是程序，真正去读数据、算数字、出报告。两个版本各取一半：

- **版本 A**：只搬说明里的经验，写成 sleuth 的知识条目；程序不进来。
- **版本 B（本分支）**：把程序装进一个插件，诊断时能启动它们；知识库不动。

## 被打包成了什么

版本 B 打成一个插件包。装一次，sleuth 就能在诊断里启动你的程序，和你现在手跑 `python xxx.py` 差不多，只是路径、超时、结果格式由它管。8 个程序各占一行开关，可以单独关掉；关掉就等于 sleuth 不知道有这个东西。

版本 A 不是包，是知识条目，一条一个文件。

## 还会有什么产出

**版本 B 报告还在。** 你的程序照旧把 HTML / Markdown 写到自己的输出目录，sleuth 只拿路径、不读内容——版式、图、结论和你现在的一模一样。每次调用会多留两份东西：一份 `result.json`（结论摘要、每条发现的证据位置、缺了哪些数据），一份调用记录（哪个程序、哪个版本、什么输入、跑了多久）。

**版本 A 没有文件产出。** 条目只影响诊断时的判断。sleuth 自己会产一份 Markdown 定位报告，那是它自己的格式，不是你那套 HTML。

## 什么时候会被调用

- agent 发现手上有整包数据时——一套 prof 目录、一个 `dump_info`、一个日志包、一份 ftrace 采集——会按数据形态挑一个程序；挑不准会先问一句，不猜。
- 工程师也可以直接点名：「用 ibmc 分析这个目录」。
- 不会被调用：只有几行报错、没有整包数据、或者那个程序那一行开关是关的。

所以「材料是整包还是片段」这件事，直接决定你的程序用不用得上。

## 怎么开始

准备一个目录，准备完把路径贴过来，再说清这轮要比什么：

```text
trial-input/
├── case-01/
│   ├── question.md      题干
│   └── materials/       脱敏后的材料
├── case-02/...
review-only/
├── answers.md           根因与正确处置，不给诊断对话看
├── supplements/         可选补充事实
└── comparison.md        评审记录
```

答案放在 `review-only/`，不要放进诊断用的工作区。

## 不会替你做的事

- **不自动装包**：缺 Python 包或 `msprof-analyze` 时，返回「缺什么」和一条命令，装不装由工程师决定。
- **不改机器**：采集、绑核、改系统参数都不在自动调用范围内，只写进建议。

## 怎么比

同一批题，原版 sleuth、版本 A、版本 B 各跑一遍，每题开一个独立对话，只发相同的题干和材料。比三样：根因说对没有、第一轮问对关键事实没有、报告能不能直接拿来用。差异明显的题再各跑一次，结果全部保留。评审时先隐藏版本标签更好。

## skill 清单

<!-- BEGIN generated: skill-roster (scripts/build_docs_index.py；由 docs/_manifest.yaml 生成，勿手改) -->
本仓共 **13 个面向使用者的 skill**，按使用场景分 4 组：
- **日常问答**（1）：`ask`（一句话能问完的问题直接答（码、变量值、某类怎么定位、术语、库里有吗），症状定位转 diagnose）
- **日常诊断**（2）：`diagnose` · `resume-diagnosis`
- **知识沉淀**（4）：`to-postmortem` · `to-reference` · `issue-ingest` · `reference-ingest`
- **维护与演进**（6）：`knowledge-groom` · `self-evolve` · `evolve-check`（内部协议，由内容流程收尾自动转接，不单独调用） · `skill-review`（内部协议，由用户显式触发做 skill 质量审视） · `preload-panel`（仅 DSH：按本机给模型的工具定装载路，有 cordis_define / cordis_run 热加载，有 plugin_manager 装常驻插件包，DSH Desktop 用安装目录自带的 dsh 命令行装（profile 记成 link），另有脚本经 /api 通路装与插件页粘贴两条备用路；含「装了但 tab 不出现」的排查顺序） · `doctor`（本机环境体检：一条命令报「哪些流程能跑、哪些会降级」并给修法；只读，不装包）
<!-- END generated: skill-roster -->
