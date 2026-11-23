#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单份 prof 的端到端分析适配器。

上游实现：scripts/analyzers/vendor/cluster-analysis/scripts/run_workflow.py
固定 --no-native：优先用上游内置 fallback，不要求本机安装 msprof-analyze。
"""
from __future__ import annotations

import os
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

ANALYZER = "cluster-analysis"
VERSION = UPSTREAM_COMMIT
VENDOR = ROOT / "vendor" / "cluster-analysis"
ENTRY = VENDOR / "scripts" / "run_workflow.py"


def analyze(inputs, out_dir: Path, args) -> dict:
    if not ENTRY.is_file():
        raise AnalyzerError("analyzer-not-installed", f"缺上游入口：{ENTRY}", status="failed")
    if len(inputs) != 1 or inputs[0]["kind"] != "dir":
        raise AnalyzerError(
            "bad-input",
            "接受一份 prof 目录（单卡目录、多卡根目录或 cluster_analysis_output 目录）。",
        )
    root = inputs[0]["path"]
    cmd = [
        sys.executable,
        str(ENTRY),
        "--input", root,
        "--output-dir", str(out_dir),
        "--no-native",
        "--timeout", str(max(60, min(args.timeout, 300))),
    ]
    started = os.path.getmtime(root)
    proc = run_process(cmd, cwd=VENDOR, timeout=args.timeout, log_path=out_dir / "vendor.log")
    if proc.get("timed_out"):
        raise AnalyzerError("timeout", f"超过 {args.timeout}s；已完成阶段在 {out_dir}", status="failed")

    status_json = out_dir / "workflow_status.json"
    detect_json = out_dir / "detect_result.json"
    if not status_json.is_file() or not detect_json.is_file():
        raise AnalyzerError(
            "analyzer-failed",
            "没有生成 workflow_status.json / detect_result.json。退出码 {code}；stderr：{err}".format(
                code=proc.get("exit_code"), err=tail(proc.get("stderr"), 800)
            ),
            status="failed",
        )

    status = read_json(status_json)
    detect = read_json(detect_json)
    advisor = read_json(out_dir / "advisor" / "advisor.json") if (out_dir / "advisor" / "advisor.json").is_file() else {}
    workflow_status = status.get("status") or "failed"
    stages = status.get("stages") or {}
    unsupported = [name for name, item in stages.items() if isinstance(item, dict) and item.get("status") == "unsupported"]
    failed = [name for name, item in stages.items() if isinstance(item, dict) and item.get("status") == "failed"]

    findings = []
    if advisor:
        findings.append(
            {
                "claim": (
                    f"{advisor.get('scope')}｜{advisor.get('dominant', '未知')}｜"
                    f"计算 {advisor.get('computing_ratio')} / 通信 {advisor.get('communication_ratio')} / "
                    f"空闲 {advisor.get('free_ratio')}｜Stage {advisor.get('stage_ms')} ms"
                ),
                "evidence": "advisor/advisor.json",
                "kind": "fact",
            }
        )
        for advice in (advisor.get("advice") or [])[:3]:
            findings.append(
                {
                    "claim": f"[{advice.get('level')}] {advice.get('text')}",
                    "evidence": "advisor/advisor.json advice",
                    "kind": "candidate" if advice.get("level") in ("Medium", "High") else "fact",
                }
            )
    coverage = status.get("coverage") or {}
    findings.append(
        {
            "claim": (
                f"覆盖 {len(coverage.get('observed_ranks') or [])} 个 rank、"
                f"{coverage.get('unique_step_count', 0)} 个 step；模式 {detect.get('mode')}"
            ),
            "evidence": "workflow_status.json coverage",
            "kind": "fact",
        }
    )
    if unsupported:
        findings.append(
            {
                "claim": "部分阶段无数据、已跳过：" + "、".join(unsupported),
                "evidence": "workflow_status.json stages",
                "kind": "fact",
            }
        )

    missing = [f"阶段 {name} 无可用数据" for name in unsupported]
    missing.extend(f"阶段失败：{name}" for name in failed)
    if detect.get("mode") == "cluster":
        cluster_out = Path(root) / "cluster_analysis_output"
        if cluster_out.is_dir() and cluster_out.stat().st_mtime >= started:
            missing.append(
                "上游在多卡 prof 根目录下写了 cluster_analysis_output（输入目录被写入）；"
                "需要输入只读时先把 prof 复制到工作区"
            )

    html = out_dir / "performance_report.html"
    artifacts = [str(item) for item in (
        html,
        out_dir / "advisor" / "advisor.md",
        out_dir / "insight_bottlenecks.md",
        out_dir / "insight_bottlenecks.html",
        detect_json,
        status_json,
    ) if item.is_file()]

    summary = (
        f"{detect.get('mode', 'unknown')} 模式，{len(coverage.get('observed_ranks') or [])} 个 rank，"
        f"{coverage.get('unique_step_count', 0)} 个 step；"
        f"workflow {workflow_status}"
    )
    if advisor:
        summary += f"；{advisor.get('dominant')}（计算 {advisor.get('computing_ratio')}、通信 {advisor.get('communication_ratio')}、空闲 {advisor.get('free_ratio')}）"
    summary += f"。报告：{html}"

    tool_status = "ok" if workflow_status == "complete" else "partial"
    if workflow_status == "failed":
        tool_status = "failed"
    return {
        "status": tool_status,
        "summary": clip(summary, 500),
        "findings": findings[:5],
        "missing": missing[:8],
        "artifacts": artifacts,
    }


if __name__ == "__main__":
    sys.exit(run_adapter(ANALYZER, VERSION, analyze, "单份 Prof 的端到端性能分析"))
