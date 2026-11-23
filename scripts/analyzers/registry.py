#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内置分析器清单（名称、适配器、上游入口、输入形态）。

新增分析器只改这里与 `scripts/analyzers/vendor/`、适配器目录；CLI 不写死名字。
"""
from __future__ import annotations

ANALYZERS = [
    {
        "name": "ibmc_analyzer",
        "adapter": "ibmc_analyzer/run.py",
        "vendor": "vendor/ibmc_analyzer",
        "entry": "scripts/run_bmc_report.py",
        "inputs": "一个或多个 dump_info 目录、机器目录，或 iBMC 一键收集压缩包（.zip/.tar.gz/.tgz/.tar）",
        "purpose": "解析 iBMC 一键收集日志，判断服务器硬件健康，输出每机 JSON 与 HTML 报告",
    },
    {
        "name": "issue-analyzer",
        "adapter": "issue-analyzer/run.py",
        "vendor": "vendor/issue-analyzer",
        "entry": "scripts/log_analyzer.py",
        "inputs": "一个日志包目录，或一个/多个日志文件",
        "purpose": "对 plog/slog/host/device/framework/dmesg 日志做清单、错误提取、聚合与回验",
    },
    {
        "name": "ascend-dump-analyzer",
        "adapter": "ascend-dump-analyzer/run.py",
        "vendor": "vendor/ascend-dump-analyzer",
        "entry": "references/compare_dumps.py",
        "inputs": "一份环境 dump JSON 做版本配套核对；两份及以上做配置漂移比对",
        "purpose": "核对 Ascend 环境版本配套，或比对多份 dump 的配置差异",
    },
    {
        "name": "prof-compare",
        "adapter": "prof-compare/run.py",
        "vendor": "vendor/prof-compare",
        "entry": "scripts/main_analyzer.py",
        "inputs": "一份已有的 compare xlsx；或两份单卡 prof 目录（A 基准、B 对比，需要 msprof-analyze）",
        "purpose": "解析 msprof-analyze compare 结果，输出中文 HTML、JSON 与 xlsx 报告",
    },
    {
        "name": "cluster-analysis",
        "adapter": "cluster-analysis/run.py",
        "vendor": "vendor/cluster-analysis",
        "entry": "scripts/run_workflow.py",
        "inputs": "一份 prof 目录（单卡目录或多卡根目录），或已生成的 cluster_analysis_output",
        "purpose": "单份 prof 的端到端性能分析：advisor、泳道、瓶颈定位与 HTML 报告",
    },
    {
        "name": "cluster-compare",
        "adapter": "cluster-compare/run.py",
        "vendor": "vendor/cluster-compare",
        "entry": "scripts/generate_cluster_report.py",
        "inputs": "两份集群数据目录（各含 cluster_analysis_output 的 DB 或 TEXT），A 基准、B 对比",
        "purpose": "比对两个集群的 profiling 数据，输出劣化归因 HTML 与 Markdown 报告",
    },
    {
        "name": "cpu-host-performance",
        "adapter": "cpu-host-performance/run.py",
        "vendor": "vendor/cpu-host-performance",
        "entry": "analyzer/analyze_cpu_trace.py",
        "inputs": "一份 ftrace/Host 采集包（cpu_trace_*.tar.gz、zip、解包目录、trace 文本或 Chrome JSON）",
        "purpose": "离线解析 Host/CPU trace，输出调度、中断、频率与绑核建议报告",
    },
]

BY_NAME = {item["name"]: item for item in ANALYZERS}


def find(name: str) -> dict | None:
    return BY_NAME.get(name)


def names() -> list[str]:
    return [item["name"] for item in ANALYZERS]
