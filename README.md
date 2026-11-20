# 这 8 个 skill 被我们改成了什么（给原作者看）

项目原本的说明在 [main 分支](https://github.com/pillumina/ascend-sleuth)。**本分支是 C 组：把你的程序直接放进仓库，诊断时用普通命令启动。**

## 你的 skill 其实是两半

一半是说明文字，告诉 agent 遇到这类问题该怎么想；另一半是程序，真正去读数据、算数字、出报告。三个版本各取一部分：

- **A 组（原始 Sleuth）**：原有知识库与流程，不使用新增 Reference 或 Analyzer。
- **B 组（知识）**：只把说明里的经验写成 sleuth 知识条目，程序不进来；分支是 `kb/absorb-analyzers-refs`。
- **C 组（工具，本分支）**：把程序直接放进仓库，诊断时用普通 Python 命令启动；知识库不动。

## 程序现在放在哪

`analyzers/` 下，按你的 skill 名分目录：

```text
analyzers/
├── cli.py                 status / list / run
├── <name>/run.py          每个 skill 的适配器
└── vendor/<name>/         你的原始实现
```

没有插件包、没有插件注册、没有 `sleuth_analyze` 工具。调用方式和你在命令行手跑差不多：

```bash
python3 analyzers/cli.py run ibmc_analyzer --inputs /data/bmc/dump_info
```

它负责路径校验、超时、结果摘要和 `result.json`；报告仍由你的程序写，HTML / Markdown 的版式与结论不变。

## 还会有什么产出

**报告还在。** 你的程序照旧把 HTML / Markdown 写到自己的输出目录，sleuth 只拿路径、不读内容。每次调用会多留三份东西：`result.json`（结论摘要、每条发现的证据位置、缺了哪些数据）、`invocation.json`（哪个程序、哪个版本、什么输入、跑了多久）、`vendor.log`（你的程序原始输出）。

**A / B 组没有这些文件产出。** A 组没有新增内容；B 组的条目只影响诊断时的判断，sleuth 自己产一份 Markdown 定位报告，不是你那套 HTML。

## 什么时候会被调用

- 工程师交来整包数据时——一套 prof 目录、一个 `dump_info`、一个日志包、一份 ftrace 采集——会按数据形态挑一个程序；挑不准会先问一句，不猜。
- 工程师也可以直接点名：「用 ibmc 分析这个目录」。
- 不会被调用：只有几行报错、没有整包数据、或者实验开关没开。

## 怎么开、怎么关

默认关闭。C 组开：

```bash
# Linux / macOS
export SLEUTH_ANALYZERS=on

# Windows PowerShell
$env:SLEUTH_ANALYZERS = 'on'
```

A / B 组不设这个变量。关闭时调用入口直接返回 `analyzer-disabled`，不启动任何分析器。

## 不会替你做的事

- **不自动装包**：缺 Python 包或 `msprof-analyze` 时，返回「缺什么」和一条命令，装不装由工程师决定。
- **不改机器**：采集、绑核、改系统参数都不在自动调用范围内，只写进建议。
- **不把程序变成文档**：7 个有可执行实现的分析器都保留了原算法；`vllm-ascend-tuning` 没有可执行脚本，未迁入。

## 怎么比

同一批题，A、B、C 各跑一遍，每题开一个独立对话，只发相同的题干和材料。比三样：根因说对没有、第一轮问对关键事实没有、报告能不能直接拿来用。差异明显的题再各跑一次，结果全部保留。评审时先隐藏版本标签更好。

材料目录与答案分离：

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

## 来源与许可

上游来源、固定提交与许可状态见 [analyzers/NOTICE.md](analyzers/NOTICE.md)。上游没有声明许可证；当前按方案讨论中记录的作者口头授权在隔离工作区做实验，未推送、未发布。正式公开前需要作者补许可或给出书面再授权。

## skill 清单

<!-- BEGIN generated: skill-roster (scripts/build_docs_index.py；由 docs/_manifest.yaml 生成，勿手改) -->
本仓共 **14 个面向使用者的 skill**，按使用场景分 4 组：
- **日常问答**（1）：`ask`（一句话能问完的问题直接答（码、变量值、某类怎么定位、术语、库里有吗），症状定位转 diagnose）
- **日常诊断**（2）：`diagnose` · `resume-diagnosis`
- **知识沉淀**（4）：`to-postmortem` · `to-reference` · `issue-ingest` · `reference-ingest`
- **维护与演进**（7）：`eval-ingest`（评测集补充入口：从 GitHub/本地 issue 建 candidate，补答案、复核入池；不产 case、不自动 active） · `knowledge-groom` · `self-evolve` · `evolve-check`（内部协议，由内容流程收尾自动转接，不单独调用） · `skill-review`（内部协议，由用户显式触发做 skill 质量审视） · `preload-panel`（仅 DSH：按本机给模型的工具定装载路，有 cordis_define / cordis_run 热加载，有 plugin_manager 装常驻插件包，DSH Desktop 用安装目录自带的 dsh 命令行装（profile 记成 link），另有脚本经 /api 通路装与插件页粘贴两条备用路；含「装了但 tab 不出现」的排查顺序） · `doctor`（本机环境体检：一条命令报「哪些流程能跑、哪些会降级」并给修法；只读，不装包）
<!-- END generated: skill-roster -->
