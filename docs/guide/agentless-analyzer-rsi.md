# 工作机上用 Agentless 改进 iBMC 丢卡告警

状态：已落地。按第 3 节运行手写示例，可以核对评分与产物。

## 1 做完得到什么

同一份采集记录，原脚本说「疑似丢卡」，改过的脚本能否指出「这份记录看不出有几张卡」？这次 RSI 实验让模型找出误判代码并提出补丁，由工作机运行脚本打分。你会拿到改前、改后的逐条结果和代码差异。

适用于能运行 Git 和 Python 的工作机。首次试跑直接用仓库的示例；要看模型能否自己修好，再用工作机会话的子代理（subagent），或本机可用的 codeAgent。只想看结果时读第 4 节即可。

## 2 前置条件

准备 Git、Python 3.10 或更高版本、PyYAML 和一个可写的临时目录。七条合成日志由脚本现场生成，普通 CPU 即可。本轮的起点是 Git 提交里的 iBMC 源码，取代以前文本优化实验里手工准备的 `seed.txt`。这轮也不需要填写真实故障或启动整套诊断的 `pilot` 对照实验。

首次取代码，在终端运行：

```sh
git clone --branch kb/agentless-analyzer-rsi --single-branch https://github.com/stfdtj/ascend-sleuth.git sleuth-agentless
cd sleuth-agentless
```

昨天已经克隆了该分支，直接在该目录运行以下命令。确认第一条显示 `kb/agentless-analyzer-rsi`，再更新。

```sh
git branch --show-current
git pull --ff-only
```

下面的命令均从仓库根目录运行。Linux 如果只有 `python3`，把命令中的 `python` 换成 `python3`。

```sh
python --version
python -c "import yaml; print(yaml.__version__)"
python scripts/evolve.py experiment resolve --target tooling --algorithm agentless
```

缺 `yaml` 时，在工作机的 Python 环境执行 `python -m pip install PyYAML`，内网机器可使用已有包源或本地 wheel。最后一条应显示 `algorithm: agentless` 和 `scope: tooling`。这里的 `tooling` 表示优化对象是工具脚本。

## 3 步骤

### 第一步：原脚本跑一遍，保存基准

PowerShell 用这一段。变量 `$run` 是本次实验目录，后面的命令沿用同一个窗口。

```powershell
$runs = python scripts/shared_dir.py proposals-experiments | Select-Object -Last 1
$run = Join-Path $runs ("ibmc-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
python scripts/evolve.py experiment agentless prepare --run-dir "$run"
```

Linux Bash 用这一段。

```bash
runs="$(python scripts/shared_dir.py proposals-experiments | tail -n 1)"
run="$runs/ibmc-$(date +%Y%m%d-%H%M%S)"
python scripts/evolve.py experiment agentless prepare --run-dir "$run"
```

终端打印原脚本得分和 `request.md` 的绝对路径。`request.md` 是给模型的题目，含误报现象、固定版本的源码和回复格式。`baseline.json` 是改前成绩，`base_rev` 是实验锁定的 Git 提交。

### 第二步：用手写示例确认环境

```sh
python scripts/evolve.py experiment agentless evaluate --run-dir "$run" --response examples/agentless/ibmc-presence-response.md
```

预期看到 `pass: 4 -> 7/7, regression_ok=True`。终端会打印这次 `result.json` 的路径。示例已经带有修法，这一步验证工作机能跑通流程；想测模型的能力，交给它的初始材料只有 `request.md`。

### 第三步：把下面这段交给工作机 agent

可以整段复制给当前会话。把第一行的括号内容换成第一步打印的实际路径，后续由工作机 agent 操作。

```text
请在当前 Sleuth 仓库继续 iBMC 优化实验。题目是（粘贴 request.md 的绝对路径），其父目录是本次实验目录。
1. 先查看当前会话是否支持启动 subagent。如果支持，开一个干净的子代理，只给它 request.md 的正文，请它返回题目指定的 SEARCH/REPLACE 补丁。让子代理只读题目，示例答案、测试代码和前一位模型的对话留在主持会话。
2. 由你把子代理的最终回复按 UTF-8 保存为实验目录里的 my-response-01.md。在仓库根目录运行 python scripts/evolve.py experiment agentless evaluate --run-dir "<实验目录>" --response "<回复文件的绝对路径>"。只将补丁文件交给实验入口，保留当前检出的源码。
3. 若返回 reject 或 invalid，读取这次的 result.json；回归测试失败时也读 regression.log 的失败段。把上次补丁、失败原因和原始 request.md 给子代理，请它相对同一份原始源码重新输出完整补丁。给新的回复单独编号，最多试三次，通过即停。
4. 若当前会话不能启动子代理，在本机查找 codeAgent 的可执行文件、已安装工具或本地项目入口。查其帮助或 README 并做一次短输入试验。支持非交互文本输入输出时，按指南第四步用它运行；只有交互界面时，把题目交给它，保存最终回复，沿用第二条的 evaluate 命令。
5. 最后报告实际用的是哪个模型入口、试了几轮、三组的改前与改后分数，以及 result.json 和 candidate.diff 的绝对路径。若只有示例可运行，请说明模型实验还缺哪个入口。
```

`SEARCH/REPLACE` 是模型回复的格式：它要指出目标文件，逐行给出原代码以及替换代码。原代码在固定版本中必须能唯一匹配。主持会话负责运行、记录结果；子代理只负责提议怎么改。

### 第四步：用本机 codeAgent 跑自动多轮（可选）

先让工作机 agent 确定安装方式。下面命令可检查 PATH 和当前项目中的线索；若团队有专门的工具目录，也可让 agent 在那个目录运行文件名搜索。

```powershell
Get-Command codeAgent,code-agent,code_agent -All -ErrorAction SilentlyContinue |
    Select-Object CommandType,Name,Source
rg --files --hidden -g '!.git' | rg -i 'code[-_]?agent'
```

```bash
command -v codeAgent || command -v code-agent || command -v code_agent
rg --files --hidden -g '!.git' | rg -i 'code[-_]?agent'
```

从找到的工具帮助或本地 README 核对启动参数、登录状态、提示词输入方式和最终回复的输出位置。用「只输出 OK」验证能否在空目录收到输入、输出纯文本并正常退出。终端别名或界面按钮可由主持会话使用；自动运行需要可执行文件，或可由 Python 等解释器启动的本地脚本。

自动入口把 UTF-8 题目送到子进程的标准输入，从标准输出读完整的最终回复。若 codeAgent 需要文件参数或返回 JSON，可让工作机 agent 用本地接口编写一个转换脚本，读取标准输入、按该工具的实际接口调用并仅打印最终回复。进度日志写标准错误。不要把令牌写进命令或提示词。

以下是调用模板。把尖括号整段替换为验证过的命令及参数；带空格的可执行文件或脚本路径单独加引号。模型命令从空的临时目录启动，脚本和配置文件使用绝对路径。

```sh
python scripts/evolve.py experiment agentless run --run-dir "${run}-auto" --attempts 3 --model-command <已验证的本机模型命令及参数>
```

`run` 会在新目录中自行跑基准。每轮保存 `prompt.md`、`model.log` 和 `response.md`，再执行相同的 `evaluate` 检查。通过就停止，否则把实际失败结果送进下一轮，最多三轮。`--model-command` 放最后，其后的参数都交给模型程序。

### 调用顺序与目录

```text
prepare  → 固定代码版本 → 运行原版分析器 → baseline.json + request.md
                               ↓
               子代理或 codeAgent 读题，生成候选补丁
                               ↓
evaluate → 临时检出应用补丁 → 同样的七条输入 + 已有分析器回归测试
                               ↓
               result.json + candidate.diff → 通过或带失败样本再试
```

目录与 Sleuth 的分工如下。分析器在 `scripts/analyzers/`，实验命令在 `scripts/evolve/`。上游分析器位于 `vendor/`，本轮限定的修改范围是 iBMC 的适配脚本。[clean 分支的分析器目录](https://github.com/stfdtj/ascend-sleuth/tree/0b9ef65b66f515e5990ee04569492a18c4e2aca9/scripts/analyzers)

```text
仓库根目录/
├─ docs/guide/agentless-analyzer-rsi.md          本指南
├─ scripts/
│  ├─ analyzers/
│  │  ├─ cli.py                                 平时诊断和本次评测共用的分析器入口
│  │  ├─ ibmc_analyzer/run.py                   候选补丁唯一能改的文件
│  │  └─ vendor/ibmc_analyzer/                  上游 iBMC 解析实现
│  ├─ evolve.py                                 你启动的 RSI 命令
│  └─ evolve/
│     ├─ cli.py                                 解析 prepare、evaluate、run
│     ├─ algorithms/agentless.py                生成请求、接收补丁、控制轮数
│     ├─ evaluations/ibmc_presence.py           生成七种输入、运行分析器、判定结果
│     ├─ regions.py                             登记允许修改的文件
│     └─ candidate.py                           校验并应用代码替换
├─ examples/agentless/ibmc-presence-response.md  环境验证用的手写补丁
└─ tests/
   ├─ test_analyzers.py                         分析器已有的回归检查
   └─ fixtures/analyzers/                       已有回归检查使用的日志样例
```

运行结果在同一克隆的主检出 `proposals/experiments/ibmc-…/`。基准文件在顶层，手动评估每次创建一个 `attempt-…/`，自动多轮依次写入 `attempt-001/` 等目录。通过解析的补丁另存为 `candidate.json`；应用成功后才有 `candidate.diff`。格式错误时可先看 `result.json` 的 `error`。

## 4 怎么确认做对了

**可共用的是评测办法，每个工具要定义自己的正确答案。** 固定原版、候选、输入和运行环境，逐条判断结果，再看既有回归是否通过。换一个提出补丁的算法，只要仍在比较这道 iBMC 题，就应使用同一套评分；换成另一个分析器，就要替换输入、预期结论和证据要求。

**本题按样本计分。** `sample_id` 指一条输入的编号，在 JSON 里就是 `samples` 下的键，例如 `timeout`。每条样本要同时满足该行的要求才得 1 分，否则得 0 分。分组统计在 `by_group`，每组各有自己的分母。

| 检查哪种能力 | 样本与分母 | 得 1 分的条件 | 本分支原版 → 手写示例 |
|---|---|---|---|
| 证据不足时能否说未知（`insufficient_evidence`） | 空文件 `empty`、超时文字 `timeout`、表头后只有错误文字 `truncated`、文件缺失 `missing`，共 4 条 | 移除丢卡告警，在缺口中标出 NPU 在位未知，并保留被抑制告警的证据位置 | 1/4 → 4/4 |
| 真有数量异常时能否保留告警（`confirmed_fault`） | 有效零卡表 `zero`、一张卡 `one`，共 2 条 | 只报告一条相应数量告警，数量准确、有证据位置，无冲突的未知或抑制记录 | 2/2 → 2/2 |
| 正常时是否误报（`healthy`） | 正常八卡 `eight`，共 1 条 | 报告中没有数量告警、在位未知或被抑制的丢卡告警 | 1/1 → 1/1 |

三个组都要求工具交付有效报告：状态是 `ok` 或 `partial`，且至少有一条带证据位置的发现。缺口按现有报告约定识别 `NPU 在位未知`，其他项目如温度未知可以同时存在。证据检查的是输出字段，具体引用能否支撑诊断还要回到原件核实。完整表头且没有数据行算「有效零卡」是本工具现有回归规定的输入语义。

**本题通过条件**是候选七条全对、总分严格高于基准、基准样本执行正常，且改前和改后都通过原有分析器回归。那 30 项回归单独记录为 `regression_ok`，不会算进七分。比较不同模型时，还应固定原始提交、样本和最多尝试次数，记录每轮结果。

**先看分组，再看总分。** 原版的三个失败来自证据不足组；在这套合成输入中，真实少卡和正常八卡原本都过了。想知道现场误报率，需要另外准备经人工核对的独立日志，分别统计已知正常、已知故障和材料不足的样本。比如换做 ECC 计数，正确答案应区分「有效的 0」「有效的非零」「读不到计数」，并核对对应的卡和来源。

正式报告可另外算三项：已知正常样本中误报警的比例，已知故障样本中漏掉目标告警的比例，以及证据不足样本中仍下确定结论的比例。每项写清分子和分母；某类没有样本时标为「无法估计」。本次的 `by_group` 记录每组有几条满足全部条件，其中也检查数量和证据，所以不能用「未得分的条数」直接代替误报数。

### 整个诊断流程怎么评

脚本测试通过后，若要回答「使用这个工具，最终诊断变好了吗」，使用仓库已有的诊断盲评。每题先固定可接受结论、必需证据和应保留的未知项。两位评审分别对**结论、原始证据、观察项处理、缺证据处理、补证**五项打 0–2 分，总分 10 分。材料不足时，准确说明未知并提出所需补证也能得满分。[工作机诊断对照计划](../../README.md#第四步盲评诊断质量再算效率)

脚本的 7 分和报告的 10 分各自回答一个问题，分别报告。要量效率，只在同题两组诊断质量都达标后比较工具调用数、补证轮数、有效耗时和读取的文本量，保留各项原值与差值。[分析器效率实验](../../scripts/analyzers/efficiency-trial.md)

### 第一次读结果时看哪里

先打开 `baseline.json` 和某次 `attempt-…/result.json`，在两份文件里搜 `timeout`。对照 `alerts`（报出的丢卡告警）、`unknown`（在位未知提示）、`suppressed`（移除的告警和证据位置）。然后看 `one`：有效的一卡告警在改后仍应存在。打开同目录的 `candidate.diff` 就能看到哪几行代码造成了差异。

旧实验可以在更新后继续 `evaluate`，仍按其 `base_rev` 中的评分器执行。要使用本版增加的有效报告与告警证据检查，并在两侧都看到 `by_group`，请用新目录重新 `prepare`。

## 5 出错了怎么办

| 现象 | 处理 |
|---|---|
| `File exists` | 准备新实验时换一个目录名。继续已有实验用 `evaluate`。 |
| 终端显示 `invalid` 或 `SEARCH must match` | 检查 `result.json` 的 `error`。代码块之外的解释、缩进变化或使用上一轮改过的源码都可能导致失败。 |
| 候选得分不够或 `regression_ok=False` | 查看失败样本与当前尝试的 `regression.log`。运行样本时的异常信息在 `probe.log`。 |
| codeAgent 能在界面里用，自动命令没有纯文本输出 | 先用交互界面生成，保存回复后跑 `evaluate`。能确认程序接口后再接自动多轮。 |
| 模型程序提前退出或超时 | 查看对应 `attempt-…/model.log` 和 `prompt.md`，从临时目录核对工具路径、登录状态和实际参数。单次模型调用等待上限为 600 秒。 |

`evaluate` 退出码 0 表示通过，1 表示本次候选未达标，2 表示回复格式错误或执行故障。`run` 耗尽尝试次数仍未通过时返回 1。

## 6 怎么退回去

候选只应用在本轮创建的临时 Git 检出，结束后由程序清理。实验目录保留输入、回复、分数和差异。需要他人复核时，提供提交号、该次 `candidate.diff`、`result.json` 和 `regression.log` 即可。候选 Python 用当前账户执行，工作机宜使用日常的开发测试环境。

## 人话版

你负责给模型出一道可以验答案的题：日志都没采全，工具怎么就说卡丢了？先让老程序做一遍，再让子代理或本机 codeAgent 改几行，用同一批日志重考。新程序既要能说「这次看不出来」，也要在真的只剩一张卡时继续报警。

明天先跑示例，确认能看到 **4/7 → 7/7**；然后复制第 3 节给工作机 agent，让它自己找模型、出补丁、交给脚本判分。最后问它三件事：哪条误报消失了，哪条真告警保住了，证据和代码差异放在哪。
