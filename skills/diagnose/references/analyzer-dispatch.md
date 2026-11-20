# Analyzer Dispatch（整包数据 → 仓库内置分析器）

**何时读**：步骤 5 深度排查，而工程师已经交来**整包数据**（不是几行报错）时。先看开关；关着、或没有这个包，就跳过本节，走原路径。

**它解的是哪种缺口**：不是知识缺口，是**取证能力缺口**——手上有 prof 目录、`dump_info`、日志包、ftrace 采集包，但把它们读成结论要跑几百行分析代码。所以这里只决定「交给哪个分析器」，判读结论与 fix 仍归主持 agent。

## 先看开关

```bash
python3 analyzers/cli.py status
```

输出 `analyzers: enabled` 才往下走。`disabled` 时**不要**直接跑 `run.py`，也不要把「没分析」写成「没发现异常」；本次诊断与没有分析器时一致。开关由环境变量 `SLEUTH_ANALYZERS` 控制：`on` 启用，未设置或 `off` 关闭。这是实验分组开关，不是安装步骤。

## 按数据形态选

| 已确认的数据形态 | 分析器 | 不要用它的情形 |
|---|---|---|
| 一份 Prof 采集（单卡或多卡），或一份集群输出 | `cluster-analysis` | 明确是两次采集的对比 → 用下面两行 |
| 一份已有的 compare xlsx；或两份单卡 Prof 目录 | `prof-compare` | 两份目录不能只凭数量判是单卡；两份目录需要本机已有 `msprof-analyze` |
| 两份集群采集或集群结果，各含多 rank / 集群 DB 或 TEXT | `cluster-compare` | 先明确 A/B、同负载、rank/step/window；不可比时只交描述差异 |
| `dump_info/` 或 iBMC 一键收集包 | `ibmc_analyzer` | 不接 OS 日志；按内容判断，不按压缩包名 |
| 环境快照 JSON、配置 dump | `ascend-dump-analyzer` | 普通日志不是环境快照；单份只做版本配套核对 |
| plog / slog / 框架日志 / dmesg 等日志包 | `issue-analyzer` | 时间窗缺失时只扫描，不推断跨机先后 |
| ftrace / Host 采集包，要调度证据 | `cpu-host-performance` | 只有环境 JSON 时不给调度根因；采集与绑核不在自动调用范围 |

数据形态判不出来就问一句，别猜。混在一个包里的，只选当前缺口那一个。

## 怎么调

```bash
python3 analyzers/cli.py run <分析器名> \
  --inputs "<绝对路径 1>
<绝对路径 2>" \
  --session-id <当前 trace 的 session_id> \
  --purpose "<这次要回答的问题，一句话>"
```

- `--inputs` 只收本机绝对路径：附件先落盘再传路径，不接受 URL。相对路径和不存在会被直接拒，不进入分析。
- 多个路径用换行分隔，也可以传 JSON 数组字符串。
- 两组数据比对时，**按 A、B 顺序**传（A 是基准，B 是对比）；`--ab` 只作记录。
- `--out-dir` 可省略；省略时落到主检出的 `traces/evidence/<session_id>/tool-runs/<call_id>/`。
- 也可以直接跑单个适配器：`python3 analyzers/<分析器名>/run.py --help`。它们和 CLI 共用同一开关与结果格式。

## 结果怎么读

命令会打印四样：状态、≤500 字摘要、≤5 条关键发现、结构化结果路径；末行 `RESULT_JSON=<路径>` 给机器读。

- 摘要里的**事实**可以直接进 trace 与报告；分析器给出的**候选解释**会标 `kind: candidate`，要标「未验证」，不能当根因。
- 完整结果在 `result.json` 的 `findings` / `missing` / `artifacts` 里。**不要把 `result.json` 整份贴进上下文**——需要复核时按里面的证据位置去读原文。
- `artifacts` 是分析器自己写出的 HTML / Markdown 报告位置。给用户时直接给路径，**不要把报告内容读进上下文**；需要引用其中结论时，按 `result.json` 里对应的发现转写。
- **fix、severity、report 仍由主持 agent 产出**。分析器没有 fix 权，也没有 severity 权。
- 出现新签名 → 回步骤 2/3 重判性质，不要就此定案。

## 失败与退化

失败一律返回非零退出码，并在 `result.json` 写 `status` + `reason`，不抛异常、不重试：

| reason | 含义 | 动作 |
|---|---|---|
| `analyzer-disabled` | `SLEUTH_ANALYZERS` 没开 | 当它不存在，回原路径；不要自己改开关 |
| `dependency-missing` | 缺 `openpyxl` / `msprof-analyze` 等依赖 | 当它不存在；需要时请工程师在预配环境安装，不在诊断里装 |
| `bad-input` / `no-input` | 路径或数据形态不对 | 纠正一次；仍不对就请工程师重给 |
| `timeout` | 超过预算（默认 600 s） | 请工程师按 rank / 时间窗裁剪后重给 |
| `analyzer-failed` | 上游入口非零退出 / 没生成结果 | 当真失败，记下来；不要重跑同一输入 |
| `analyzer-crashed` | 适配器捕获到未预期异常 | 当真失败，记下来；附 `detail` |
| `analyzer-not-installed` | 仓库内实现缺失 | 当它不存在；不要自己拼命令行 |

失败**不计入**「候选被排除」，也不能写成「没发现异常」。工具不在时整节跳过，诊断行为与没有它时一致。

## 缺数据时怎么问

`status` 是 `blocked` 或 `failed` 时先读 `result.json` 的 `data_needed`。它为空表示不是缺数据（例如开关没开、缺依赖、超时），不要向用户要材料；非空时把它翻成一句具体的话，只问缺的那一项：

| 分析器 | 要用户补的最小数据 |
|---|---|
| `issue-analyzer` | plog / slog / host / device / framework / dmesg 日志目录或文件 |
| `ascend-dump-analyzer` | 环境 dump JSON；比对时需要两份 |
| `cpu-host-performance` | ftrace / Host 采集包、解包目录、trace 文本或 Chrome JSON |
| `ibmc_analyzer` | `dump_info` 目录或 iBMC 一键收集包 |
| `prof-compare` | 一份 compare xlsx，或两份单卡 prof 目录 |
| `cluster-analysis` | 一份 prof 目录，或 `cluster_analysis_output` |
| `cluster-compare` | 两份集群数据目录，各含 DB 或 TEXT |

`partial` 的 `missing` 是可选数据缺口：可以写进结论的覆盖范围，但不阻塞本次分析；不要因为有可选缺口就要求用户重采整包。一次只问当前分析器缺的那一项，不要把七个分析器的输入清单一起发给用户。

## trace 记什么

复用现有 `run_check` 事件，不新增 action 词表：

```yaml
- {action: run_check, step: 5, check: analyzer_run, analyzer: <名字>, analyzer_version: <版本或 unknown>,
   verdict: hit|empty|blocked|failed, evidence: <result.json 路径>, reason: <一句话>}
```

`analyzer_version` 取 `result.json` 里的 `analyzer_version`；拿不到写 `unknown`，不要省略这个字段——版本与结论要能对上，否则下次结果变了分不清是数据变了还是实现变了。

结论被采纳时，在后续 `hit` 或 `output` 里写清用了哪一条发现；工具跑成功不等于诊断解决。

## 不做什么

- 不在诊断里 `pip install`、`apt install` 或下载第三方脚本。
- 不自动执行采集脚本、`cpu_trace_collect.sh`、`bind_cpu.sh`、`taskset` 或任何会改客户机器状态的命令。上游随包保留了这些手动入口，只作人工操作说明。
- 不把分析器输出直接当根因；不把报告文件内容整份读进上下文。
