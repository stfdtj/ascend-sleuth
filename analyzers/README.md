# analyzers（仓库内置分析器）

这 7 个分析器直接放在仓库里，用普通 Python 命令调用，不经过 DSH 插件注册、插件加载器或 `sleuth_analyze` 工具。分析算法保留上游实现，本目录只增加参数转换、开关、结果摘要和 `result.json`。

上游来源、固定提交与许可状态见 [NOTICE.md](NOTICE.md) 和 [PROVENANCE.yaml](PROVENANCE.yaml)。

## 目录

```text
analyzers/
├── cli.py                 status / list / run 三个入口
├── registry.py            分析器清单与输入形态
├── _lib.py                开关、路径校验、子进程、result.json
├── <name>/run.py          每个分析器的适配器（可直接执行）
├── requirements.txt       可选依赖（不自动安装）
└── vendor/<name>/         上游实现（逐字节保留，改动见 PROVENANCE.yaml）
```

## 开关：A / B / C 三组实验

分析器由环境变量 `SLEUTH_ANALYZERS` 控制，**默认关闭**。

| 组 | 内容 | 开关 |
|---|---|---|
| A | 原始 Sleuth，不使用新增 Reference 或 Analyzer | 不设或 `off` |
| B | Sleuth + Reference，只使用知识 | 不设或 `off`；用 `kb/absorb-analyzers-refs` 分支 |
| C | Sleuth + Reference + Analyzer，允许调用仓库内置分析工具 | `on` |

```bash
# Linux / macOS
export SLEUTH_ANALYZERS=on

# Windows PowerShell
$env:SLEUTH_ANALYZERS = 'on'
```

```bash
python3 analyzers/cli.py status
python3 analyzers/cli.py status --json
```

关闭时 `cli.py run` 和每个 `run.py` 都直接返回 `analyzer-disabled`，不启动任何上游脚本，也不创建输出目录。A/B 组不需要改代码或删目录；不设这个变量即可。

```bash
# 验证关闭：退出码 3，且输出目录不创建
SLEUTH_ANALYZERS=off python3 analyzers/cli.py run ibmc_analyzer --inputs /data/bmc/dump_info --out-dir /tmp/should-not-exist
```

开关只是实验分组，不是安装步骤。分析器随仓库检出，不需要单独安装插件、复制插件目录或改插件配置。

本分支只负责 C 组的 Analyzer 开关；B 组的 reference 词条在 `kb/absorb-analyzers-refs`。C 组要求同时具备 B 的知识面时，先把该分支的 reference 合入 C 的检出（不改检索机制），再设 `SLEUTH_ANALYZERS=on`。

## 直接调用

```bash
python3 analyzers/cli.py list
python3 analyzers/cli.py run <name> --inputs "<绝对路径 1>
<绝对路径 2>" --session-id <session_id> --purpose "<一句话>"
```

- `--inputs` 只收本机绝对路径；多个用换行分隔，或传 JSON 数组字符串。
- `--out-dir` 可省略；省略时落到主检出的 `traces/evidence/<session_id>/tool-runs/<call_id>/`。
- 两组数据比对时按 **A（基准）、B（对比）** 顺序传。
- 单个分析器也可直接跑：`python3 analyzers/<name>/run.py --inputs ... --out-dir ...`。

### 每个分析器的命令

| 分析器 | 输入 | 命令 |
|---|---|---|
| `ibmc_analyzer` | 一个或多个 `dump_info` 目录、机器目录或 iBMC 一键收集包 | `python3 analyzers/cli.py run ibmc_analyzer --inputs <路径>` |
| `issue-analyzer` | 一个日志目录，或一个/多个日志文件 | `python3 analyzers/cli.py run issue-analyzer --inputs <路径>` |
| `ascend-dump-analyzer` | 一份环境 dump JSON（配套核对）；两份及以上（漂移比对） | `python3 analyzers/cli.py run ascend-dump-analyzer --inputs "<A.json>\n<B.json>"` |
| `prof-compare` | 一份 compare xlsx；或两份单卡 prof 目录 | `python3 analyzers/cli.py run prof-compare --inputs <compare.xlsx>` |
| `cluster-analysis` | 一份 prof 目录或 `cluster_analysis_output` | `python3 analyzers/cli.py run cluster-analysis --inputs <prof 目录>` |
| `cluster-compare` | 两份集群数据目录（DB 或 TEXT） | `python3 analyzers/cli.py run cluster-compare --inputs "<A>\n<B>"` |
| `cpu-host-performance` | 一份 ftrace/Host 采集包、目录、trace 文本或 Chrome JSON | `python3 analyzers/cli.py run cpu-host-performance --inputs <trace>` |

`vllm-ascend-tuning` 没有迁入：上游这一项是提示词与文档，没有可执行分析脚本，不把它当工具暴露。

## 结果

每次调用在输出目录写：

| 文件 | 内容 |
|---|---|
| `result.json` | `status` / `summary` / `findings` / `missing` / `artifacts` / `analyzer_version` / `duration_ms` 等 |
| `invocation.json` | 分析器、版本、输入、开关、Python、开始时间 |
| `vendor.log` | 上游命令的 stdout/stderr（图、大段日志不进入上下文） |
| 上游报告 | HTML / Markdown / JSON / xlsx，路径登记在 `result.json` 的 `artifacts` |

`status` 取 `ok` / `partial` / `blocked` / `failed`。成功判据是「上游进程正常结束 + 产物可读」，不是「目录里出现过文件」。失败时 `data_needed` 给出这个分析器的最小输入形态；`missing` 是本次缺的具体项。开关未开、缺依赖、超时不填 `data_needed`，不要拿它向用户要材料。

## 依赖

| 分析器 | 运行时 |
|---|---|
| `ibmc_analyzer` / `issue-analyzer` / `ascend-dump-analyzer` / `cluster-analysis` / `cluster-compare` / `cpu-host-performance` | Python 3.8+ 标准库 |
| `prof-compare` 读 xlsx | `openpyxl` |
| `prof-compare` 从两份 prof 目录生成 compare | `msprof-analyze`（本机预装） |

缺依赖时返回 `dependency-missing` 并写明缺什么，**不自动安装**。

## 手动采集入口（不在自动调用范围）

分析路径本身是离线的：适配器只读已有输入，不调用下面的采集脚本。没有现成数据时返回缺路径/缺数据，由工程师决定是否现场采集；采集不在自动调用图里。

上游随包保留了这些会接触客户机器的脚本，本目录**不会自动执行**，只作为人工操作参考：

- `vendor/cpu-host-performance/scripts/cpu_trace_collect.sh`：ftrace 采集，需要 root 与现场授权。
- `vendor/cpu-host-performance/scripts/ascend_bind.py`、`hostbind/`：绑核与回滚，会修改进程 affinity。
- `vendor/ascend-dump-analyzer/references/msprechecker_dump.py`：在目标机采集环境快照。
- `vendor/issue-analyzer/references/log-structure.md`：现场日志采集命令速查（plog 打包、`npu-smi`、`dmesg` 等），只作文本参考。
- `vendor/ibmc_analyzer/README.md`：iBMC Web「一键收集」的导出说明；仓库里没有发起采集的脚本。
- `vendor/prof-compare/`、`vendor/cluster-compare/` 的 README/SKILL：提到用 `msprof-analyze` 在宿主机生成 compare 或 `cluster_analysis_output`；适配器只读已有输出，不执行生成步骤。

`cpu-host-performance` 生成的 `bind_cpu.sh` 是建议脚本，本次不执行；执行前需人工核对 PID、线程身份与回退。

## 测试

```bash
python3 -m unittest tests.test_analyzers -v
```

测试用临时目录现造合成输入，覆盖开关、坏路径、缺依赖、zip 越界、7 个分析器的输入到报告输出。真实客户包与超过 260 字符的路径不在测试里。

## 已知限制

- `cluster-analysis` 在多卡模式下沿用上游行为，会在 prof 根目录写 `cluster_analysis_output/`；需要输入只读时，先把 prof 目录复制到工作区。
- `cluster-compare` 的 HTML 模板引用 CDN 图表脚本；离线打开时图表可能不显示，表格与 Markdown 报告仍可读。
- `prof-compare` 从两份 prof 目录生成 compare 依赖 `msprof-analyze`；没有该工具时只支持已有 compare xlsx。
- `ascend-dump-analyzer` 单份输入只做版本配套核对；完整单份报告仍按上游模板由主持 agent 填写。
