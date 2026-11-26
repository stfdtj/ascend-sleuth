# 在工作机上用 Agentless 方式试改 iBMC 分析器

状态：已落地。可用下文的示例补丁跑完一轮验证。

## 做完得到什么

你会拿到同一批日志在原脚本和候选脚本下的逐条结果、一份可以审查的代码差异，以及原有分析器测试的输出。这轮只研究一件事：iBMC 管理日志无法证明有几张 NPU 卡时，脚本是否还会报告“疑似丢卡”。

## 前置条件

准备 Git、Python 3.10 或更高版本和 PyYAML。工作机需能拉取分支，并有空间临时检出一份仓库。评分使用仓库自带的合成日志，本轮可在普通 CPU 上完成。使用随附示例时可以离线评分，自己生成补丁时用工作机上已有的模型会话。

在 PowerShell 或终端运行以下命令。已有其他实验在跑时，给本次实验单独克隆一个目录。

```sh
git clone --branch kb/agentless-analyzer-rsi --single-branch https://github.com/stfdtj/ascend-sleuth.git sleuth-agentless
cd sleuth-agentless
python -m pip install PyYAML
python scripts/evolve.py experiment resolve --target tooling --algorithm agentless
```

最后一条应显示 `algorithm: agentless` 和 `scope: tooling`。下面命令均从这个检出的根目录运行。Linux 若只有 `python3`，把 `python` 换成 `python3`。

## 步骤

1. 选一个新的实验目录，跑原脚本取得基准分。PowerShell 如下。

   ```powershell
   $runs = python scripts/shared_dir.py proposals-experiments | Select-Object -Last 1
   $run = Join-Path $runs ("ibmc-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
   python scripts/evolve.py experiment agentless prepare --run-dir "$run"
   ```

   Linux 的同一步如下。后面几条 Python 命令通用。

   ```bash
   runs="$(python scripts/shared_dir.py proposals-experiments | tail -n 1)"
   run="$runs/ibmc-$(date +%Y%m%d-%H%M%S)"
   python scripts/evolve.py experiment agentless prepare --run-dir "$run"
   ```

2. 第一次可先用随附的手写示例补丁，在隔离检出里重跑同一批日志。终端会打印本次结果文件的完整路径。

   ```sh
   python scripts/evolve.py experiment agentless evaluate --run-dir "$run" --response eval/analyzers/example-response.md
   ```

3. 要试自己的模型，把实验目录里的 `request.md` 发给工作机的模型会话。它包含故障说明、固定版本的源码和回复格式。请模型**只返回指定代码块**，把回复按 UTF-8 保存为同目录的 `my-response.md`。这一步相当于让模型找出负责误判的代码，写出修改前后两段文本。运行：

   ```sh
   python scripts/evolve.py experiment agentless evaluate --run-dir "$run" --response "$run/my-response.md"
   ```

4. 如果某条没过，把该条的实际输出和上次回复一起交给模型，让它针对 `request.md` 中的**原始源码**重新给出完整候选。再次运行第 3 步。每次评估写一个新目录，所以可以比较多次尝试。此入口由你选择模型和轮数。

### 让模型自动试几轮

如果工作机装有已登录的 Codex CLI，可以从新目录直接跑以下命令。它会先测原脚本，然后向模型发送题目、验证回复，把上一次回复和失败样本交回模型再改。候选通过就提前停，`--attempts 3` 限制最多调用模型三次。

```sh
python scripts/evolve.py experiment agentless run --run-dir "${run}-auto" --attempts 3 --model-command codex exec --skip-git-repo-check --ephemeral --sandbox read-only -
```

`${run}-auto` 会在实验路径末尾追加 `-auto`。换模型时替换 `--model-command` 后面的命令和参数，命令需从标准输入接收 UTF-8 题目，在标准输出返回补丁，诊断信息写标准错误。每轮的 `prompt.md` 和 `model.log` 保存在对应的 `attempt-001` 等目录中。

模型命令从空的临时目录启动，随附示例没有放进题目。自有模型脚本请传绝对路径。Git 临时检出隔离文件版本，候选 Python 在当前账户权限下执行。评估外部生成的代码时，使用只有实验数据的开发环境。

### 文件放在哪里

```text
sleuth-agentless/
├─ scripts/
│  ├─ evolve.py                         命令行总入口
│  ├─ evolve/
│  │  ├─ cli.py                         experiment agentless 子命令
│  │  ├─ algorithms/agentless.py          准备请求，把模型回复转换成补丁，运行评分
│  │  ├─ algorithms/registry.py          登记算法名 agentless
│  │  ├─ targets/registry.py             把算法挂到 tooling（工具脚本）目标
│  │  ├─ regions.py                      登记本轮允许修改的文件
│  │  └─ candidate.py                    校验补丁，在隔离检出应用修改
│  └─ analyzers/
│     ├─ agentless-rsi.md                 本操作指南
│     └─ ibmc_analyzer/run.py             实际接受优化的脚本
├─ eval/analyzers/
│  ├─ ibmc_presence.py                   生成日志并检查分析器的真实 CLI 输出
│  └─ example-response.md                首次试跑用的手写补丁
├─ tests/test_analyzers.py               既有分析器回归测试
└─ proposals/experiments/ibmc-…/          实验产物（位于同一克隆的主检出）
   ├─ request.md                         给模型的题目和源码
   ├─ baseline.json                      原脚本在每条样本上的得分和提交号
   ├─ probe.log / regression.log         原脚本的探测错误输出和测试记录
   └─ attempt-…/                         每次评估单独一份
      ├─ response.md / candidate.json    原始回复和框架可读取的补丁
      ├─ candidate.diff                  原脚本到候选脚本的 Git 差异
      ├─ probe.log / regression.log      候选的探测错误输出和测试记录
      └─ result.json                     每条样本的实际告警、未知项和总结果
```

## 怎么确认做对了

`baseline.json` 中 `samples` 的键就是样本编号。例如 `timeout` 是采集文件里只有超时文字，`zero` 是完整表头且没有数据行，后者按现有分析器约定应保留零卡告警。每个编号通过得 1 分。

| 样本编号 | 输入 | 怎样才得分 |
|---|---|---|
| `empty`、`timeout`、`truncated`、`missing` | 空文件、超时文字、表头后只有错误文字、文件缺失 | 报告在位未知，移除丢卡告警，并保留被移除告警的证据位置 |
| `zero`、`one` | 有效零卡记录、一张卡的记录 | 分别保留 0 张或 1 张卡的数量告警 |
| `eight` | 正常八卡 | 数量告警、在位未知提示和被抑制的丢卡告警均为空 |

在这个分支上，原脚本应为 **4/7**，示例应为 **7/7**。`decision: pass` 要求候选严格优于原脚本、七条全部通过、原脚本和候选均通过已有回归测试。`result.json` 可查看 `alerts`（报告里给人的告警）、`unknown`（在位未知提示）、`suppressed`（被移除的告警和依据）。这些分数描述合成样本，现场误报率要另外用独立的历史故障和正常日志测量。

## 出错了怎么办

- `File exists` 表示实验目录已存在。继续评估直接用 `evaluate`，重新测基准则换一个新目录。
- `SEARCH must match` 通常是缩进、上下文或源码版本不一致。让模型对照这轮的 `request.md` 逐行复制要改的原文。每块注明同一个目标文件，去掉代码块以外的解释。
- `regression_ok=False` 时打开对应目录的 `regression.log`，查第一个 `FAIL` 或 `ERROR`。`probe.log` 记录样本运行错误。评估退出码 0 表示通过，1 表示评分未达标，2 表示输入或执行故障。早期失败的尝试可能只有原始回复。

## 怎么退回去

每个候选在临时 Git 检出中运行，结束后自动移除。保留实验目录即可继续比较或复核；执行 `git status --short` 可查看工作机检出的状态。要把有效改动交给同事评审，可以分享通过的 `candidate.diff` 和对应的 `result.json`。

## 与上游 Agentless 的关系

本分支适配了上游修复阶段的 `SEARCH/REPLACE` 回复格式。文件已由误报限定，模型负责在文件内定位，Sleuth 负责应用补丁、复现误报和检查回归。运行时只需这份 Sleuth 分支。官方的仓库级定位、SWE-bench Docker 环境和候选多数投票不在本次实验范围。[上游修复实现（固定版本）](https://github.com/OpenAutoCoder/Agentless/blob/5ce5888/agentless/repair/repair.py)
