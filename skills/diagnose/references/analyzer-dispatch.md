# Analyzer Dispatch（整包数据 → 外部分析器）

**何时读**：步骤 5 深度排查，而工程师已经交来**整包数据**（不是几行报错）时。工具不在、或没有这个包，就跳过本节，走原路径。

**它解的是哪种缺口**：不是知识缺口，是**取证能力缺口**——手上有 prof 目录、`dump_info`、日志包、ftrace 采集包，但把它们读成结论要跑几百行分析代码。所以这里只决定「交给哪个分析器」，判读结论与 fix 仍归主持 agent。

## 按数据形态选

| 已确认的数据形态 | 分析器 | 不要用它的情形 |
|---|---|---|
| 一份 Prof 采集（单卡或多卡），或一份集群输出 | `cluster-analysis` | 明确是两次采集的对比 → 用下面两行 |
| 两份 Prof，各自单卡；或已有 compare 的 xlsx | `prof-compare` | 两份目录不能只凭数量判是单卡 |
| 两份集群采集或集群结果，各含多 rank / 集群 DB | `cluster-compare` | 先明确 A/B、同负载、rank/step/window；不可比时只交描述差异 |
| `dump_info/` 或 iBMC 一键收集包 | `ibmc_analyzer` | 不接 OS 日志；按内容判断，不按压缩包名 |
| 环境快照 JSON、配置 dump | `ascend-dump-analyzer` | 普通日志不是环境快照 |
| plog / slog / 框架日志 / dmesg 等日志包 | `issue-analyzer` | 时间窗缺失时只扫描，不推断跨机先后 |
| ftrace / Host 采集包，要调度证据 | `cpu-host-performance` | 只有环境 JSON 时不给调度根因 |
| vLLM 配置 + 已有 benchmark 结果 | `vllm-ascend-tuning` | 不按「慢」自动触发在线实验 |

数据形态判不出来就问一句，别猜。混在一个包里的，只选当前缺口那一个。

## 怎么调

```
sleuth_analyze(
  analyzer: <上表的名字>,
  inputs: <绝对路径，多个换行分隔>,
  purpose: <这次要回答的问题，一句话>,
  ab: <两包对比时写 A 或 B>,
  session_id: <当前 trace 的 session_id>
)
```

`inputs` 只收本机绝对路径：附件先落盘再传路径，不接受 URL。相对路径和不存在会被直接拒，不进入分析。

## 结果怎么读

返回四样：状态、≤500 字摘要、≤5 条关键发现、结构化结果文件路径。

- 摘要里的**事实**可以直接进 trace 与报告；分析器给出的**候选解释**要标"未验证"，不能当根因。
- 摘要已按预算截断（500 字，发现最多 5 条）：截断时返回里会说明"摘要已截断"，全文只在 `result.json` 里。**不要把 `result.json` 整份贴进上下文**——需要复核时按里面的证据位置去读原文。
- 证据文件（`result.json`）里有每条发现的原始位置与测量值；写报告时引用它，不要引用摘要。
- **报告与产物**：返回里的 `artifacts` 是分析器自己写出的 HTML / Markdown 报告位置。给用户时直接给路径（或链接），**不要把报告内容读进上下文**；需要引用其中结论时，按 `result.json` 里对应的发现转写。
- **fix、severity、report 仍由主持 agent 产出**。分析器没有 fix 权，也没有 severity 权。
- 出现新签名 → 回步骤 2/3 重判性质，不要就此定案。

## 失败与退化

一律返回 `ok:false` + `reason`，不抛异常、不重试：

| reason | 含义 | 动作 |
|---|---|---|
| `analyzer-disabled` | 插件里那一行没开 | 当它不存在，回原路径 |
| `analyzer-not-installed` | 实现还没随包分发 | 当它不存在；不要自己拼命令行去跑 |
| `no-python` | 本机没有可用解释器 | 回原路径；需要时让工程师装 |
| `bad-input` / `no-input` | 路径不对 | 纠正一次；仍不对就请工程师重给 |
| `timeout` | 超过预算（默认 600 s） | 请工程师按 rank / 时间窗裁剪后重给 |
| `no-result` | 跑完但没有 `result.json` | 当真失败，记下来 |

失败**不计入**「候选被排除」，也不能写成「没发现异常」。工具不在时整节跳过，诊断行为与没有它时一致。

## trace 记什么

复用现有 `run_check` 事件，不新增 action 词表（新增词表要同时改校验、回放与统计，见方案第 4 节）：

```yaml
- {action: run_check, step: 5, check: analyzer_run, analyzer: <名字>, analyzer_version: <版本或 unknown>,
   verdict: hit|empty|blocked|failed, evidence: <result.json 路径>, reason: <一句话>}
```

`analyzer_version` 取工具返回里的版本（解析自 `tools/<name>/meta.json` 或 `result.json`）；拿不到写 `unknown`，不要省略这个字段——版本与结论要能对上，否则下次结果变了分不清是数据变了还是实现变了。

结论被采纳时，在后续 `hit` 或 `output` 里写清用了哪一条发现；工具跑成功不等于诊断解决。
