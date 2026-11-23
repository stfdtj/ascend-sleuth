# 来源、许可与改动说明

## 上游

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/hu669293657/skills |
| 提交 | `6519f6f73ba68c6eaf51d9374644e4b60c84be0c` |
| 作者 | hu669293657 |
| 上游许可 | **未声明**：仓库内没有 `LICENSE` / `COPYING` / `NOTICE` 文件，也没有源文件头部的 SPDX 标识 |

## 再分发状态

实验组织者此前确认了作者对迁入和再分发的口头授权。记录保留在本地实验提交 `33d4177` 的 `proposals/tool-analyzer-integration.md` 中，见「迁移批次」与「上游更新与维护归属」两节。上游仍未声明开源许可，当前也无书面许可记录。

本次按实验组织者的要求，将保留的文件放在公开 fork 的 `kb/analyzer-model-trial` 分支，供工作机运行对照实验。来源与原作者署名随文件保留。

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
