#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Host/CPU trace 离线分析适配器。

上游实现：scripts/analyzers/vendor/cpu-host-performance/analyzer/analyze_cpu_trace.py
只做离线解析；采集脚本、绑核执行入口不在本适配器调用范围内。
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

ANALYZER = "cpu-host-performance"
VERSION = UPSTREAM_COMMIT
VENDOR = ROOT / "vendor" / "cpu-host-performance"
ENTRY = VENDOR / "analyzer" / "analyze_cpu_trace.py"


def analyze(inputs, out_dir: Path, args) -> dict:
    if not ENTRY.is_file():
        raise AnalyzerError("analyzer-not-installed", f"缺上游入口：{ENTRY}", status="failed")
    if len(inputs) != 1:
        raise AnalyzerError("bad-input", "一次只接受一份 trace 采集包/目录/文件。")
    target = inputs[0]["path"]

    proc = run_process(
        [sys.executable, str(ENTRY), target, "-o", str(out_dir), "-q"],
        cwd=VENDOR,
        timeout=args.timeout,
        log_path=out_dir / "vendor.log",
    )
    if proc.get("timed_out"):
        raise AnalyzerError("timeout", f"超过 {args.timeout}s", status="failed")
    data_path = out_dir / "report_data.json"
    if not data_path.is_file():
        detail = tail((proc.get("stderr") or "") + "\n" + (proc.get("stdout") or ""), 800)
        reason = "bad-input" if proc.get("exit_code") == 3 else "analyzer-failed"
        raise AnalyzerError(reason, detail or "没有生成 report_data.json", status="failed")

    data = read_json(data_path)
    diag = data.get("diagnosis") or {}
    findings_data = diag.get("findings") or []
    primary = diag.get("primary") or {}
    findings = []
    if primary:
        evidence = primary.get("evidence") or []
        evidence_text = "；".join(
            f"{item.get('metric')}={item.get('value')}" for item in evidence[:3] if isinstance(item, dict)
        )
        findings.append(
            {
                "claim": (
                    f"{primary.get('title')}｜{primary.get('severity')}｜"
                    f"置信度 {primary.get('confidence')}｜{clip(evidence_text, 180)}"
                ),
                "evidence": "report_data.json diagnosis.primary",
                "kind": "fact",
            }
        )
        if primary.get("possible_root_cause"):
            findings.append(
                {
                    "claim": f"候选根因：{primary.get('possible_root_cause')}",
                    "evidence": "report_data.json diagnosis.primary.possible_root_cause",
                    "kind": "candidate",
                }
            )
    for item in findings_data[:3]:
        if not isinstance(item, dict) or item.get("title") == primary.get("title"):
            continue
        findings.append(
            {
                "claim": f"{item.get('title')}｜{item.get('severity')}｜{item.get('confidence')}",
                "evidence": "report_data.json diagnosis.findings",
                "kind": "fact",
            }
        )
    findings.append(
        {
            "claim": "bind_cpu.sh 是上游给出的绑核建议脚本，本次没有执行；执行前需人工核对 PID/线程身份与回退。",
            "evidence": str(out_dir / "bind_cpu.sh"),
            "kind": "fact",
        }
    )

    missing = []
    if not findings_data and not primary:
        missing.append("诊断没有给出任何问题项；可能事件不足或 trace 格式不受支持")
    if primary.get("causality") == "UNPROVEN":
        missing.append("Host 侧风险已观测，但 NPU 因果未证明；不能单独当作根因")
    summary = (
        f"Host 状态 {diag.get('host_status', 'UNKNOWN')}；"
        f"核心问题：{primary.get('title') if primary else '未发现明显问题'}。"
        f"报告：{out_dir / 'hostbound_report.html'}"
    )

    artifacts = [str(item) for item in (
        out_dir / "hostbound_report.html",
        data_path,
        out_dir / "bind_cpu.sh",
    ) if item.is_file()]
    return {
        "status": "ok",
        "summary": clip(summary, 500),
        "findings": findings[:5],
        "missing": missing[:8],
        "artifacts": artifacts,
    }


if __name__ == "__main__":
    sys.exit(run_adapter(ANALYZER, VERSION, analyze, "Host/CPU trace 离线分析"))
