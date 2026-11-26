# analyzers（仓库内置分析器）

当前有 6 个分析器通过 Python 命令调用。环境快照分析保留字段比对，`vllm-ascend-tuning` 提供调优说明和配置模板。单卡性能对比的读法见[性能基准对照](../../references/methodologies/performance-baseline-comparison-reading.yaml)。

上游来源、固定提交与许可状态见 [NOTICE.md](NOTICE.md) 和 [PROVENANCE.yaml](PROVENANCE.yaml)。

## 目录

```text
scripts/analyzers/
├── cli.py                 status / list / run 三个入口
├── registry.py            分析器清单与输入形态
├── _lib.py                开关、路径校验、子进程、result.json
├── <name>/run.py          每个分析器的适配器（可直接执行）
└── vendor/<name>/         保留的上游脚本和资料
```

## 启用分析器

分析器由环境变量 `SLEUTH_ANALYZERS` 控制，**默认关闭**。

```bash
# Linux / macOS
export SLEUTH_ANALYZERS=on
```

```powershell
$env:SLEUTH_ANALYZERS = 'on'
```

```bash
python3 scripts/analyzers/cli.py status
python3 scripts/analyzers/cli.py status --json
```

关闭时，`cli.py run` 和各 `run.py` 返回 `analyzer-disabled`，退出码为 `3`。

```bash
# 验证关闭：退出码 3，且输出目录不创建
SLEUTH_ANALYZERS=off python3 scripts/analyzers/cli.py run ibmc_analyzer --inputs /data/bmc/dump_info --out-dir /tmp/should-not-exist
```

## 直接调用

```bash
python3 scripts/analyzers/cli.py status            # 开关与安装状态（人读）
python3 scripts/analyzers/cli.py status --json     # 同上，给机器读
python3 scripts/analyzers/cli.py list --json       # 这台机器上有哪些分析器、各自的输入形态
python3 scripts/analyzers/cli.py run <name> --inputs "<绝对路径 1>
<绝对路径 2>" --session-id <session_id> --purpose "<一句话>"
```

- `--inputs` 只收本机绝对路径；多个用换行分隔，或传 JSON 数组字符串。
- `--out-dir` 可省略；省略时落到主检出的 `traces/evidence/<session_id>/tool-runs/<call_id>/`。
- 两组数据比对时按 **A（基准）、B（对比）** 顺序传。
- 单个分析器也可直接跑：`python3 scripts/analyzers/<name>/run.py --inputs ... --out-dir ...`。
- 输出统一转 UTF-8：Windows 默认代码页（cp1252）下中文摘要不会抛 UnicodeEncodeError。

### 每个分析器的命令

| 分析器 | 输入 | 命令 |
|---|---|---|
| `ibmc_analyzer` | 一个或多个 `dump_info` 目录、机器目录或 iBMC 一键收集包 | `python3 scripts/analyzers/cli.py run ibmc_analyzer --inputs <路径>` |
| `issue-analyzer` | 一个日志目录，或一个/多个日志文件 | `python3 scripts/analyzers/cli.py run issue-analyzer --inputs <路径>` |
| `ascend-dump-analyzer` | 至少两份含 JSON 内容的环境快照 | `python3 scripts/analyzers/cli.py run ascend-dump-analyzer --inputs '["<A.json>","<B.json>"]'` |
| `cluster-analysis` | 一份 prof 目录或 `cluster_analysis_output` | `python3 scripts/analyzers/cli.py run cluster-analysis --inputs <prof 目录>` |
| `cluster-compare` | 两份集群数据目录（DB 或 TEXT） | `python3 scripts/analyzers/cli.py run cluster-compare --inputs "<A>\n<B>"` |
| `cpu-host-performance` | 一份 ftrace/Host 采集包、目录、trace 文本或 Chrome JSON | `python3 scripts/analyzers/cli.py run cpu-host-performance --inputs <trace>` |

`vllm-ascend-tuning` 的上游内容是提示词、调优文档和配置模板。调优时从 [上游说明](vendor/vllm-ascend-tuning/README.md) 进入，命令和参数按部署版本核对。

从开发分支试跑 `diagnose` 时，运行 `python3 scripts/build_ref_summary_index.py` 和 `python3 scripts/build_procedure_index.py`，让诊断能查到本分支新增的工具说明和判读方法。主干会自动生成索引。

## 结果

每次调用在输出目录写：

| 文件 | 内容 |
|---|---|
| `result.json` | `status` / `summary` / `findings` / `missing` / `artifacts` / `analyzer_version` / `duration_ms` 等；iBMC 另带 `suppressed` / `observations` / `reconciled` |
| `invocation.json` | 分析器、版本、输入、开关、Python、开始时间 |
| `vendor.log` | 上游命令的 stdout/stderr（图、大段日志不进入上下文） |
| 上游报告 | HTML、Markdown 或 JSON，路径登记在 `result.json` 的 `artifacts` |

`suppressed` 是适配层从发现里移出的判定，每条带 `reason` 与原因说明，原始数值仍留在上游 JSON 产物里。它不属于 `findings`：读到它说明「这条判定缺少证据，别当异常用」，不是「这里有问题」。当前只有 `ibmc_analyzer` 用它：缺 `npu_info` 时上游会把 NPU 在位判成数量 0（疑似丢卡），适配层改为未知并抑制该条。

`observations` 是低优先级项（工具判 P2/P3，以及状态不是 ok 的传感器读数），带原始值、单位、等级与证据位置。它不是结论也不是噪音：`findings` 只收 P0/P1，P2 若直接丢掉会让「温度越限」这类项从 Agent 眼前消失；但直接塞进 `findings` 又会把工具关注项说成已证实的异常。传感器读数旁的阈值归属未经核对，只在观察项里给数，不给判定。

`reconciled` 记录适配层补读过的证据（当前只有 ECC）：上游用 `encoding="utf-8"` 读 `npu_ecc_info.json`，带 BOM 的真实输入会抛异常并被吞成空，表现为「ECC 全 0」。适配层用 `utf-8-sig` 复读一次，读到计数就补进 `findings` 并在此留痕；读不出来则写进 `missing`，不写成 0。

`status` 取 `ok` / `partial` / `blocked` / `failed`。成功判据是「上游进程正常结束 + 产物可读」，不是「目录里出现过文件」。失败时 `data_needed` 给出这个分析器的最小输入形态；`missing` 是本次缺的具体项。

`partial` 把本次未分析的材料写入 `missing`，`data_needed` 保持为空。报告按实际覆盖范围引用结果。开关未开、缺依赖或超时也保持 `data_needed` 为空。

## 依赖

当前分析器用 Python 3.8+ 标准库生成主要结果。集群分析可附带生成工作簿，集群对比从已有集群结果开始。

## 手动采集入口（不在自动调用范围）

分析路径本身是离线的：适配器只读已有输入，不调用下面的采集脚本。没有现成数据时返回缺路径/缺数据，由工程师决定是否现场采集；采集不在自动调用图里。

上游随包保留了这些会接触客户机器的脚本，本目录**不会自动执行**，只作为人工操作参考：

- `vendor/cpu-host-performance/scripts/cpu_trace_collect.sh`：ftrace 采集，需要 root 与现场授权。
- `vendor/cpu-host-performance/scripts/ascend_bind.py`、`hostbind/`：绑核与回滚，会修改进程 affinity。
- `vendor/issue-analyzer/references/log-structure.md`：现场日志采集命令速查（plog 打包、`npu-smi`、`dmesg` 等），只作文本参考。
- `vendor/ibmc_analyzer/README.md`：iBMC Web「一键收集」的导出说明；仓库里没有发起采集的脚本。
- `vendor/cluster-compare/README.md`：说明如何在现场生成集群分析结果。Sleuth 适配器从已有结果开始比对。

`cpu-host-performance` 生成的 `bind_cpu.sh` 是建议脚本，本次不执行；执行前需人工核对 PID、线程身份与回退。

iBMC 在位误报的优化实验可从[工作机运行指南](agentless-rsi.md)启动，指南包含目录图、示例补丁与逐条评分方法。

## 测试

```bash
python3 -m unittest tests.test_analyzers -v
```

测试用临时目录里的合成输入，覆盖开关、坏路径、压缩包路径校验和 6 个分析器的报告输出。环境快照还验证了单份输入的提示及部分成功时的差异报告。

## 已知限制

- `cluster-analysis` 在多卡模式下沿用上游行为，会在 prof 根目录写 `cluster_analysis_output/`；需要输入只读时，先把 prof 目录复制到工作区。
- `cluster-compare` 的 HTML 模板引用 CDN 图表脚本；离线打开时图表可能不显示，表格与 Markdown 报告仍可读。
