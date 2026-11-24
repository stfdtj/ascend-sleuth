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
| `ascend-dump-analyzer/` | `scripts/analyzers/vendor/ascend-dump-analyzer/references/compare_dumps.py` | 环境快照字段比对脚本 |
| `prof-compare/` | `references/methodologies/performance-baseline-comparison-reading.yaml` | 性能基准对照的判读方法 |
| `cluster-analysis/` | `scripts/analyzers/vendor/cluster-analysis/` | 是 |
| `cluster-compare/` | `scripts/analyzers/vendor/cluster-compare/` | 是 |
| `cpu-host-performance/` | `scripts/analyzers/vendor/cpu-host-performance/` | 是 |
| `vllm-ascend-tuning/` | `scripts/analyzers/vendor/vllm-ascend-tuning/` | 提示词、调优说明与配置模板 |

完整保留的目录内，上游测试及说明供查阅。诊断使用本仓登记的分析入口。

## 对上游文件的改动

分析算法沿用上游实现。下表记录执行路径的改动。

| 文件 | 改动 | 原因 |
|---|---|---|
| `vendor/ascend-dump-analyzer/references/compare_dumps.py` | 读取 dump 时用 `utf-8-sig` | 接受带 BOM 的 JSON，避免 Windows 生成的 dump 被误判为解析失败 |
| `vendor/cluster-analysis/scripts/` 下的工作流、桥接器和报告生成器 | 移除内嵌的单卡 Prof 对比子报告，保留集群内双卡对比 JSON 和主报告 | 单卡 Prof 对比保留为判读方法 |
| `vendor/ibmc_analyzer/scripts/run_bmc_report.py` | zip 解包改为逐条校验，拒绝越界路径与符号链接；压缩包解压失败时不再把压缩包路径当目录继续解析 | 一键收集包可能含 `../` 条目，不能让解包写出输出目录；失败要明确返回，不能生成一份“空机器”报告 |
| `vendor/cpu-host-performance/analyzer/analyze_cpu_trace.py` | 启动时把 stdout/stderr 设为 UTF-8 | Windows 控制台默认代码页会让中文报告标题抛 `UnicodeEncodeError` |

集群分析的说明和回归测试随调用路径更新。适配器与公共执行层由 Sleuth 维护。

## 归属

上游作者与仓库记在本文件和 `scripts/analyzers/PROVENANCE.yaml`。保留原作者署名。
