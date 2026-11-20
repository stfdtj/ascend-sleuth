#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两个集群 profiling 数据的比对适配器。

上游实现：analyzers/vendor/cluster-compare/scripts/{cluster_data_extractor,generate_cluster_report,generate_cluster_md}.py
输入按 A（基准）、B（对比）顺序给两份集群数据目录；只接受已有 cluster_analysis_output（DB/TEXT），
不在诊断里安装 msprof-analyze、也不从原始采集数据自动生成。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from _lib import (  # noqa: E402
    AnalyzerError,
    UPSTREAM_COMMIT,
    clip,
    read_json,
    run_adapter,
    run_process,
    tail,
)

ANALYZER = "cluster-compare"
VERSION = UPSTREAM_COMMIT
VENDOR = ROOT / "vendor" / "cluster-compare"
EXTRACT = VENDOR / "scripts" / "cluster_data_extractor.py"
REPORT = VENDOR / "scripts" / "generate_cluster_report.py"
REPORT_MD = VENDOR / "scripts" / "generate_cluster_md.py"


def _extract(path: str, output: Path, args) -> dict:
    proc = run_process(
        [sys.executable, str(EXTRACT), "--data-dir", path, "--output", str(output), "--no-advanced"],
        cwd=VENDOR,
        timeout=args.timeout,
        log_path=output.with_suffix(".log"),
    )
    if proc.get("timed_out"):
        raise AnalyzerError("timeout", f"数据提取超过 {args.timeout}s", status="failed")
    if not output.is_file():
        raise AnalyzerError(
            "bad-input",
            f"{path} 不是可用的集群数据目录（需 cluster_analysis_output 下 DB 或 "
            f"cluster_step_trace_time.csv + communication_group.json）。stderr：{tail(proc.get('stderr'), 500)}",
        )
    return read_json(output)


def _step_diff(data_a: dict, data_b: dict) -> dict:
    steps_a = data_a.get("step_summary") or {}
    steps_b = data_b.get("step_summary") or {}
    common = [step for step in steps_a if step in steps_b]
    if not common:
        return {}
    def mean(key):
        values = []
        for step in common:
            a = (steps_a.get(step) or {}).get(key)
            b = (steps_b.get(step) or {}).get(key)
            if a is not None and b is not None:
                values.append((float(b) - float(a)) / 1000.0)
        return sum(values) / len(values) if values else None
    return {
        "steps": len(common),
        "stage_ms": mean("avg_stage"),
        "compute_ms": mean("avg_compute"),
        "comm_ms": mean("avg_comm"),
        "free_ms": mean("avg_free"),
    }


def analyze(inputs, out_dir: Path, args) -> dict:
    for entry in (EXTRACT, REPORT, REPORT_MD):
        if not entry.is_file():
            raise AnalyzerError("analyzer-not-installed", f"缺上游入口：{entry}", status="failed")
    if len(inputs) != 2 or any(item["kind"] != "dir" for item in inputs):
        raise AnalyzerError(
            "bad-input",
            "接受两份集群数据目录，顺序为 A（基准）、B（对比）；每份需含 cluster_analysis_output 的 DB 或 TEXT。",
        )

    data_a_path = out_dir / "data_a.json"
    data_b_path = out_dir / "data_b.json"
    data_a = _extract(inputs[0]["path"], data_a_path, args)
    data_b = _extract(inputs[1]["path"], data_b_path, args)

    html = out_dir / "cluster_compare_report.html"
    md = out_dir / "cluster_compare_report.md"
    proc = run_process(
        [sys.executable, str(REPORT), "--data-a", str(data_a_path), "--data-b", str(data_b_path),
         "--output", str(html)],
        cwd=VENDOR,
        timeout=args.timeout,
        log_path=out_dir / "report.log",
    )
    if proc.get("timed_out"):
        raise AnalyzerError("timeout", f"报告生成超过 {args.timeout}s", status="failed")
    if not html.is_file():
        raise AnalyzerError("analyzer-failed", f"HTML 报告没有生成：{tail(proc.get('stderr'), 600)}", status="failed")

    proc_md = run_process(
        [sys.executable, str(REPORT_MD), "--data-a", str(data_a_path), "--data-b", str(data_b_path),
         "--output", str(md)],
        cwd=VENDOR,
        timeout=args.timeout,
        log_path=out_dir / "report_md.log",
    )

    diff = _step_diff(data_a, data_b)
    if not diff:
        raise AnalyzerError("bad-input", "两份数据没有共同的 Step，无法比对；先确认两次采集的 step 范围。")

    findings = [
        {
            "claim": (
                "共同 {steps} 个 Step：Stage 平均差 {stage:+.3f} ms，计算 {compute:+.3f} ms，"
                "通信 {comm:+.3f} ms，空闲 {free:+.3f} ms（B−A）"
            ).format(
                steps=diff["steps"],
                stage=diff.get("stage_ms") or 0.0,
                compute=diff.get("compute_ms") or 0.0,
                comm=diff.get("comm_ms") or 0.0,
                free=diff.get("free_ms") or 0.0,
            ),
            "evidence": "data_a.json / data_b.json step_summary",
            "kind": "fact",
        }
    ]
    tables_empty = sorted(set(data_a.get("tables_empty") or []) | set(data_b.get("tables_empty") or []))
    if tables_empty:
        findings.append(
            {
                "claim": "缺失的可选数据：" + "、".join(tables_empty) + "；通信带宽/矩阵相关结论不可用。",
                "evidence": "data_a.json tables_empty",
                "kind": "fact",
            }
        )
    findings.append(
        {
            "claim": "完整差异、慢卡与通信算子排行见 HTML/Markdown 报告；本摘要只给共同 Step 的均值差。",
            "evidence": str(html),
            "kind": "fact",
        }
    )

    summary = (
        f"集群比对（A 基准 → B 对比）：共同 {diff['steps']} 个 Step，"
        f"Stage 平均差 {diff.get('stage_ms') or 0.0:+.3f} ms（正值为 B 更慢）。"
        f"报告：{html}"
    )
    artifacts = [str(item) for item in (html, md, data_a_path, data_b_path) if item.is_file()]
    return {
        "status": "partial" if tables_empty else "ok",
        "summary": clip(summary, 500),
        "findings": findings[:5],
        "missing": [f"缺可选表：{item}" for item in tables_empty][:8],
        "artifacts": artifacts,
    }


if __name__ == "__main__":
    sys.exit(run_adapter(ANALYZER, VERSION, analyze, "两个集群 profiling 数据的劣化归因比对"))
