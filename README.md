<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
    <img alt="ascend-sleuth" src="docs/assets/logo.svg" width="460">
  </picture>
</p>

<h1 align="center">昇腾 NPU 训练与推理故障诊断知识库</h1>

<p align="center">
  <a href="https://www.hiascend.com/"><img alt="platform: Ascend NPU" src="https://img.shields.io/badge/platform-Ascend%20NPU-CC0000?logo=huawei&logoColor=white"></a>
  <a href="https://agentskills.io/"><img alt="Agent Skills compliant" src="https://img.shields.io/badge/Agent%20Skills-compliant-8B5CF6.svg"></a>
  <a href="https://opensource.org/licenses/MIT"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
</p>

训练或推理在昇腾 NPU 上中断、精度异常、性能退化时，把日志与版本信息交给 agent。它按症状路由，查先验知识（官方文档与已沉淀事实）框定方向，再加载候选 case 逐条验证。未命中时继续深度排查，可按版本拉源码分析。输出定位结论与修复方案。

定位结束后，新知识进待审队列，每周例行维护去重、升格为 case，同类问题下次直接命中。共性另归纳成先验知识。系统也按使用记录演进：未命中、执行出错、条目过期先记为 signal；深度轮只分诊，确定性 bug 走回归测试，内容缺口走内容 skill，行为质量才显式进入 RSI，高风险改动另做授权。所有改动最终仍走 PR 人审。

skill 按 [Agent Skills](https://agentskills.io/) 标准打包。可在 pi、Claude Code、Codex、DeepSeek Harness（DSH）等支持该标准的 agent 中运行。

## 在工作机上跑 iBMC 诊断对照

本轮比较新增参考词条和分析器是否能让诊断更准确、补证更具体。实验组织者在能读取原始日志的工作机上，用一个 Codex 对话调度 6 个子代理。普通使用者可直接看下方「快速开始」。

实验分支保留的上游文件适用其各自的许可记录。[分析器来源和许可](scripts/analyzers/NOTICE.md)

日志、环境快照、单卡对比、单次集群、双集群和 Host 性能的材料与评分见[六项工作机试验及复跑版本](scripts/analyzers/model-trials.md)。当前工具范围见[分析器用法](scripts/analyzers/README.md)。

新一轮保留原诊断质量评分，增加工具调用、补证轮数、诊断耗时和工具返回文本量四项指标。[分析器效率对照](scripts/analyzers/efficiency-trial.md)

### 做完得到什么

得到两道题各三份诊断报告，以及一份人工评分表。逐题比较证据准确性、处置建议和补证质量。本轮结果用于判断这两类 iBMC 案例中的收益。

### 准备材料

用未参与迁移开发或测试的两个已定位案例。每题保留首轮可见的原始材料和文件结构，供三组读取相同的只读副本。

| 要找的案例 | 首轮材料 |
|---|---|
| 已确认 NPU 多 bit ECC 异常 | 一键收集包或完整 `dump_info/`。优先找含 `AppDump/CpuMem/npu_info`、`AppDump/CpuMem/npu_ecc_info.json` 的包，保留能核对卡号和计数的原始文件。 |
| 已确认电源输入异常，同时缺 NPU 在位证据 | 一键收集包或完整 `dump_info/`，保留 `AppDump/sensor_alarm/current_event.txt`、`AppDump/BMC/psu_info.txt`。优先选原包就缺 `AppDump/CpuMem/npu_info` 的案例。若用完整包模拟缺文件，先在副本中移除该文件，再为三组复制同一份输入。评审标记为模拟缺项。 |

每题另备一份简短题干，写现场现象、发生时间和当时已知的环境。另存评审答案，写已核实的根因、关键证据所在文件和原值、当时采取的处置及结果，以及首轮不能确定的事项。若允许追问，提前写好可补充的事实。

新增词条已有电源输入丢失、缺 `npu_info` 的示例。第二题选独立的现场事件，用不同的告警或读数检验能否把规则用到新材料上。

案例目录和题干文件用中性编号，包内文件名保持原样。评审答案、工单结论和事后分析放在实验检出之外，评审时再打开。日志与报告留在工作机的获准目录，使用该环境获准处理日志的模型。

### 步骤

1. **检出实验分支。** 工作机需要 Git、Python 3、PyYAML 和可用子代理的 Codex。在工作机的实验目录运行以下命令。已有本分支的克隆时，在该目录执行 `git pull --ff-only`，再检查 Python 依赖并记录本轮提交。

   ```powershell
   git clone --single-branch --branch kb/analyzer-model-trial https://github.com/stfdtj/ascend-sleuth.git analyzer-model-trial
   Set-Location analyzer-model-trial
   python -c "import yaml"
   $trialCommit = git rev-parse HEAD
   $trialCommit
   ```

   把打印的提交固定为 C 组版本。原版诊断固定在 `75f6e39ff8e24afb1b9560a1e66f1b816d493b48`。[分析器目录和用法](scripts/analyzers/README.md)

2. **建 6 个独立本地克隆。** 每个案例和版本组合各用一个克隆。在各克隆检出表中指定的提交，把诊断记录、报告和工具产物写到该次运行的独立目录。此仓库同一克隆内的多个 worktree 默认共享 `traces/`，因此这里用独立克隆。

   | 版本 | 检出 | 提供给子代理的能力 |
   |---|---|---|
   | A | `75f6e39` | 原版 `diagnose`。 |
   | B | `75f6e39` | 原版 `diagnose`，加一份从 `$trialCommit` 导出的 `references/tools/bmc-dump-analyzer.yaml`。 |
   | C | `$trialCommit` | 与 B 同一份参考词条，加内置分析器及其调用流程。 |

   在 C 的两个克隆各运行 `python scripts/build_ref_summary_index.py`，让诊断能查到本分支新增的词条。

   每个克隆将 `.local/settings.json` 的 `sync.enabled`、`sync.auto_merge`、`sync.check_enabled` 设为 `false`。建诊断记录时给 `scripts/trace_begin.py` 传 `--no-sync`，C 调用分析器时显式传本次运行的 `--out-dir`。实验期间停用自动同步和知识沉淀。

   由主代理为 C 组的 `status`、`list` 和 `run` 命令提供 `SLEUTH_ANALYZERS=on`。若命令各用一个新 shell，就在每条命令的同一 shell 中设置。A、B 的开关为 `off`。

3. **从一个 Codex 对话派发。** 把下面这段交给主代理，同时给它两个题干和日志路径。并发不足时分批运行，每题每版仍使用全新子代理。

   ```text
   按本节的 A、B、C 设置，从两个案例各新建三个独立子代理。每个子代理只接收对应的题干、只读材料路径、工作目录、输出目录、允许使用的参考词条和工具。使用相同模型和推理设置，启动时不继承主对话。各版用同一条诊断要求：按 diagnose 从本次材料独立排查，给出证据、判断、下一步和待补材料。

   所有子代理跳过 knowledge/、postmortems/、历次 traces、proposals/、eval/、tests/fixtures/ 和实验说明。三组都可以读日志、搜索文本、运行通用 Python，按需使用共同已有的参考词条。B、C 还可以读本轮新增的同一份 iBMC 词条。C 可以按本版流程调用分析器，并读所需的工具使用说明。跳过联网检索和生产操作。题干与材料以外的信息只按统一的补充规则提供。

   收齐六份结果再汇总。保留每次运行的提交、模型、报告、诊断记录、用时和工具状态。需要复跑时换干净目录和全新子代理，保留原结果。
   ```

### 怎么确认做对了

开跑前核对同一题三组的输入副本一致，记录各工作目录的 `git rev-parse HEAD`。从每个克隆运行 `python scripts/shared_dir.py traces`，确认 6 个输出路径各自独立。在 C 的运行环境执行 `python scripts/analyzers/cli.py status --json`，确认 `enabled` 为 `true`，`ibmc_analyzer` 的 `installed` 为 `true`。C 若调用失败或没有调用也保留结果和原因。

六份报告收齐后，隐藏版本标签，交两位评审独立打分。分别评根因、证据、观察项处理、缺证据处理、补证。每项 0–2 分，满分 10 分。记录分歧及其依据，另记工具执行状态。

每项按同一尺度打分。0 分表示错误或漏答，1 分表示方向合理但说不清证据或动作，2 分表示判断与证据一致，或行动具体且适合现有证据。首轮确实缺证据时，说明未知并准确提出补证，也可得满分。

### 出错了怎么办

- 检出 `75f6e39` 时报提交不存在，检查克隆是否用了 `--depth`。浅克隆可从实验分支执行 `git fetch --unshallow` 补齐历史。
- 找不到合适的真实材料时，可用仓库样例试跑流程，将结果标为开发验收。后续用两份新案例做效果对照。
- 任一子代理读到了历史案例、答案或其他组结果时，保留该次记录，用干净目录重跑该次。并发不足时，按案例分两批。

### 怎么结束和清理

把报告、评分表和版本记录移到工作机上指定的留存目录，再移除临时克隆。原始材料和评审答案保留在各自的目录。

## 快速开始

### 安装

```bash
git clone https://github.com/pillumina/ascend-sleuth.git
cd ascend-sleuth
python3 scripts/enable_agent_skills.py
```

脚本检测本机已安装的 agent，为它们建项目级 skills 链接（幂等，可重复执行）。Linux 与 macOS 上 DSH 不跑这个脚本也够用：`.dsh/skills` 是仓库跟踪的 symlink，clone 后即可用。`git pull` 更新 SKILL.md 即时生效。

诊断开单会自动同步知识库：`trace_begin.py` 建单时 fetch 远端，条件满足时做一次快进合并。

配置与开关（`sync.remote` / `sync.branch` / `sync.enabled` / `sync.auto_merge` / `sync.check_enabled` / `sync.check_minutes` / `sync.check_full_access`）在 `.local/settings.json`。`sync.enabled` 与 `sync.auto_merge` 只管诊断读侧的自动路径，groom 不受影响；`sync.check_enabled` / `sync.check_minutes` 是诊断状态条的知识库提醒开关与检查间隔（可在「Ascend Sleuth · 知识库」页设置）。没有这个文件时用默认值：`origin`、当前分支上游（取不到用 `main`）、同步开、自动合并开。

当前状态用 `python3 scripts/kb_sync.py --show` 查看（只读，不联网）。

Windows 上 Git 默认不还原 symlink，`.dsh/skills` 会落成一个内容为 `../skills` 的文本文件，agent 发现不了 skills，而 `git status` 此时可能是干净的。脚本会把这条 symlink 建好；自动检测认不出的 agent 用 `--all`。`--check` 只读自检状态（不写盘），`--fix-copy` 把 Git Bash 建出的目录副本换成链接。自检与两条修法见 [windows-setup.md](docs/guide/windows-setup.md)。

装完在 agent 中调用 `/skill:<name>`。

### 使用示例

在 agent 中调用 `/skill:diagnose`，把客户给的症状、框架版本与日志片段粘贴给它：

```
/skill:diagnose

客户 A5-950 训练在 step ~3000 hang，all_to_all timeout，world_size=128。
框架 mindspeed-llm 2.5.0。报错栈尾：
[粘贴相关 rank 的日志片段]
```

agent 按症状路由到 `training/mindspeed-llm/`，匹配并验证 case。命中时输出四段：结论、依据链（含命中的 `<CASE-ID>`、历史 `hits` 与 `misdiagnoses`）、修复方案与 rollback、可靠度与残余风险。未命中时转深度排查。信息不足时，agent 指出还要向客户补什么。

诊断全程写 trace。被打断时可用 `/skill:resume-diagnosis` 续接。

### 在其他项目中试用

```bash
npx skills@latest add pillumina/ascend-sleuth -s diagnose -s to-postmortem -s to-reference -s issue-ingest -s knowledge-groom -s resume-diagnosis
```

该方式安装的是 `skills/` 副本，更新需重新安装，也不沉淀回本仓。要在其他仓库中沉淀知识，按 [知识获取：三种起步形态](docs/guide/knowledge-acquisition.md) 配置。

## 背景

昇腾训练与推理的日常问题集中在三类：中断（hang、crash、OOM）、精度异常（loss 发散、FP8 衰减）、性能退化（吞吐下降、通信占比过高）。根因高度重复，相关知识却散落在个人笔记、IM 聊天与各处 wiki。新 case 每周都在出现，A2-910B / A3-910C / A5-950 三代平台的差异还在扩大，靠个人手工维护的知识库跟不上这个速度。

ascend-sleuth 把这些经验沉淀为结构化知识库。诊断时按症状路由到已验证的 case。定位结束后，新知识进入待审队列，由例行维护完成去重、升格与退休。人工沉淀按周批处理，自动化导入源可以直接升格。

## 工作原理

知识分三层按需加载，控制进 agent 上下文的量：

| 层 | 内容 | 加载时机 |
|---|---|---|
| Tier 1 | `triage-tree.yaml`：症状到命名空间的映射 | 始终加载 |
| Tier 2 | `knowledge/` 下的 case 规则 | 命中症状后两阶段加载：先读该命名空间与类别的读侧视图过滤候选，再加载全文验证 |
| Tier 3 | `postmortems/` 下的原始定位记录 | 前两层未命中时关键词检索 |

知识库本体在 `knowledge/`，按框架与类别分目录：

```
knowledge/
├── _index.yaml / _index/   总表与读侧视图（scripts/build_index.py 生成；合入后由主干 job 重建）
├── training/{mindspeed-llm,mindspeed-mm,verl}/
├── inference/{vllm-ascend,sglang}/
├── common/                 多框架共用的权威记录（由 groom 提升）
└── _archive/               软退休的过期 case
```

命名空间下面按性质分目录（如 `inference/vllm-ascend/interrupt/`）。先验知识层在 `references/`，放官方文档与案例沉淀的事实、工具词条与流程，不参与候选路由。

问题按两个维度拆。在哪查：训练还是推理、用什么框架，决定命名空间（如 `training/mindspeed-llm/`）。什么性质：中断、精度还是性能，决定匹配形态（中断用错误签名 grep，精度用数值阈值断言，性能用 profiler 指标比对），三者不混用。

诊断全程写 trace：加载了哪些命名空间、按什么顺序做了哪些检查、工程师提供了什么证据。误诊归因靠它区分 case 错（改知识 YAML）与执行错（改 skill 正文）。两者的修法不同，混在一起会改坏本来正确的 case。

三个闭环驱动整个系统：

| 闭环 | 什么时候发生 | 入口 | 产出 |
|---|---|---|---|
| 诊断闭环 | 每次问题（分钟级） | `/skill:diagnose` | 修复建议 + trace |
| 沉淀闭环 | 定位结束后 / 定期批量 | `/skill:to-postmortem`、`/skill:to-reference`、`/skill:issue-ingest` | 待审队列 → case / reference 词条 |
| 演进闭环 | 内容流程收尾 / 全库体检轮 | `/skill:evolve-check`、`/skill:self-evolve` | signal → 分诊 → 确定性修复 / 内容 / 显式 RSI / 高风险授权 → PR（人审） |

![ascend-sleuth 架构](docs/diagrams/ascend-sleuth-architecture.png)

每个机制配了什么护栏、每周实际要做什么，见 [自演进元机制](docs/mechanism/rsi-mechanism.md)。

## 适用范围与限制

- 诊断 agent 不访问客户环境，也不改生产：日志、版本与报错由工程师提供，修复建议由人应用。
- 诊断质量随 agent 变化：prompt 纪律是概率性的，换一个 agent 或换一次会话，结果与 trace 质量可能不同。团队内建议统一 agent。跨 agent 对比时先归因执行差异，再判断是不是知识本身错。
- `data-loss-risk` 的根因不给修复方案，只输出停机、保留现场、通知 owner。
- 版本匹配是软判据：`compat` 不匹配只降 confidence，不排除 case。
- 输出是给人看的建议，不对接 on-call 或 IM 通知链路。

## skill 清单

<!-- BEGIN generated: skill-roster (scripts/build_docs_index.py；由 docs/_manifest.yaml 生成，勿手改) -->
本仓共 **14 个面向使用者的 skill**，按使用场景分 4 组：
- **日常问答**（1）：`ask`（一句话能问完的问题直接答（码、变量值、某类怎么定位、术语、库里有吗），症状定位转 diagnose）
- **日常诊断**（2）：`diagnose` · `resume-diagnosis`
- **知识沉淀**（4）：`to-postmortem` · `to-reference` · `issue-ingest` · `reference-ingest`
- **维护与演进**（7）：`eval-ingest`（评测集补充入口：从 GitHub/本地 issue 建 candidate，补答案、复核入池；不产 case、不自动 active） · `knowledge-groom` · `self-evolve` · `evolve-check`（内部协议，由内容流程收尾自动转接，不单独调用） · `skill-review`（内部协议，由用户显式触发做 skill 质量审视） · `preload-panel`（仅 DSH：按本机给模型的工具定装载路，有 cordis_define / cordis_run 热加载，有 plugin_manager 装常驻插件包，DSH Desktop 用安装目录自带的 dsh 命令行装（profile 记成 link），另有脚本经 /api 通路装与插件页粘贴两条备用路；含「装了但 tab 不出现」的排查顺序） · `doctor`（本机环境体检：一条命令报「哪些流程能跑、哪些会降级」并给修法；只读，不装包）
<!-- END generated: skill-roster -->

每个 skill 的触发条件与操作细节见各自的 `skills/<name>/SKILL.md`。

## 文档

- [文档总目录](docs/README.md)：全部文档按"什么时候读"分层
- [演示走查](docs/demo-walkthrough.md)：从一次诊断到知识演化的完整演示，不需要动手
- [诊断面板](dsh-plugins/ascend-panel/README.md)：DSH 会话中的可视化面板（可选增强）
- [知识获取](docs/guide/knowledge-acquisition.md)：三种起步形态与稀疏拉取白名单
- [部署与协作](docs/guide/git-workflow.md)：集中式与框架式 fork 两种部署、目录归属、审核与门控
- [术语表](CONTEXT.md)：case / postmortem / groom / trace / reference 的规范定义

## 许可

MIT，见 [LICENSE](LICENSE)。
