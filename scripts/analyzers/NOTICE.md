# 来源、许可与改动说明

## 上游

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/hu669293657/skills |
| 提交 | `6519f6f73ba68c6eaf51d9374644e4b60c84be0c` |
| 作者 | hu669293657 |
| 上游许可 | **未声明**：仓库内没有 `LICENSE` / `COPYING` / `NOTICE` 文件，也没有源文件头部的 SPDX 标识 |

## 再分发状态

上游没有可确认的再分发许可。本仓只在实验分支的隔离工作区里保留了上游实现，用于验证「运行工具是否比只用知识更有增益」；**没有推送、没有合入 main**。

授权记录见实验提交 `33d4177` 中 `proposals/tool-analyzer-integration.md` 的「迁移批次」与「上游更新与维护归属」两节。公开分发以作者补充明确的开源许可或书面再分发许可为准：

- 不把 `scripts/analyzers/vendor/` 推到公开仓；
- 不把 `scripts/analyzers/vendor/` 打进对外发布的包；
- 对外只引用上游仓库与提交，不复制实现。

处理方式（任选其一，按可行性排序）：

1. 请作者在上游仓库补 `LICENSE`（或对本次迁入给出书面许可），然后正常提交；
2. 保持本分支为本地实验分支，只在隔离环境跑，不推送；
3. 若必须公开，改成「运行外部目录」模式：仓库只放适配器与说明，由使用者提供上游检出路径。该方式不满足「内置」目标，只作为许可未解决时的退路。

## 保留范围

| 上游目录 | 本地位置 | 是否保留 |
|---|---|---|
| `ibmc_analyzer/` | `scripts/analyzers/vendor/ibmc_analyzer/` | 是 |
| `issue-analyzer/` | `scripts/analyzers/vendor/issue-analyzer/` | 是 |
| `ascend-dump-analyzer/` | `scripts/analyzers/vendor/ascend-dump-analyzer/` | 是 |
| `prof-compare/` | `scripts/analyzers/vendor/prof-compare/` | 是 |
| `cluster-analysis/` | `scripts/analyzers/vendor/cluster-analysis/` | 是 |
| `cluster-compare/` | `scripts/analyzers/vendor/cluster-compare/` | 是 |
| `cpu-host-performance/` | `scripts/analyzers/vendor/cpu-host-performance/` | 是 |
| `vllm-ascend-tuning/` | `scripts/analyzers/vendor/vllm-ascend-tuning/` | 提示词、调优说明与配置模板 |

上游的 `tests/`、`README.md`、`SKILL.md` 随目录保留，供追溯与人工阅读；诊断流程不读它们。

## 对上游文件的改动

只改必要的行为边界，不改分析算法。逐文件记录：

| 文件 | 改动 | 原因 |
|---|---|---|
| `vendor/prof-compare/scripts/run_compare.py` | 删除 `pip_install`，`ensure_msprof` 缺工具时直接失败；`--skip_install` 变为兼容参数 | 禁止诊断过程中自动安装依赖 |
| `vendor/ascend-dump-analyzer/references/compare_dumps.py` | 读取 dump 时用 `utf-8-sig` | 接受带 BOM 的 JSON，避免 Windows 生成的 dump 被误判为解析失败 |
| `vendor/ibmc_analyzer/scripts/run_bmc_report.py` | zip 解包改为逐条校验，拒绝越界路径与符号链接；压缩包解压失败时不再把压缩包路径当目录继续解析 | 一键收集包可能含 `../` 条目，不能让解包写出输出目录；失败要明确返回，不能生成一份“空机器”报告 |
| `vendor/cpu-host-performance/analyzer/analyze_cpu_trace.py` | 启动时把 stdout/stderr 设为 UTF-8 | Windows 控制台默认代码页会让中文报告标题抛 `UnicodeEncodeError` |

其它文件逐字节来自上游固定提交。适配器与公共执行层是本仓代码，不在上游。

## 归属

上游作者与仓库在 `scripts/analyzers/README.md`、`scripts/analyzers/PROVENANCE.yaml` 与本文件中标注。上游实现内部的注释、模板与报告文案保持原样，不删除作者署名。
