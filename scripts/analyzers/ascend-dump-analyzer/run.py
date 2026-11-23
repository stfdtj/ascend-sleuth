#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ascend 环境 dump 适配器：单份做版本配套核对，多份做配置漂移比对。

上游实现：scripts/analyzers/vendor/ascend-dump-analyzer/references/{check_compatibility,compare_dumps}.py
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

ANALYZER = "ascend-dump-analyzer"
VERSION = UPSTREAM_COMMIT
VENDOR = ROOT / "vendor" / "ascend-dump-analyzer"
CHECK = VENDOR / "references" / "check_compatibility.py"
COMPARE = VENDOR / "references" / "compare_dumps.py"


def _compat(paths, out_dir: Path, args) -> dict:
    output = out_dir / "compatibility.json"
    proc = run_process(
        [sys.executable, str(CHECK), paths[0], "--output", str(output)],
        cwd=VENDOR,
        timeout=args.timeout,
        log_path=out_dir / "vendor.log",
    )
    if proc.get("timed_out"):
        raise AnalyzerError("timeout", f"超过 {args.timeout}s", status="failed")
    if not output.is_file():
        raise AnalyzerError(
            "analyzer-failed",
            "没有生成 compatibility.json。退出码 {code}；stderr：{err}".format(
                code=proc.get("exit_code"), err=tail(proc.get("stderr"), 600)
            ),
            status="failed",
        )
    data = read_json(output)
    software = data.get("software") or {}
    host = data.get("host") or {}
    status_value = software.get("status") or "unknown"
    findings = []
    if software.get("reason"):
        findings.append(
            {
                "claim": f"软件配套：{status_value}｜{software.get('reason')}",
                "evidence": "compatibility.json software",
                "kind": "fact",
            }
        )
    checks = software.get("checks") or {}
    for name, check in list(checks.items())[:3]:
        if not isinstance(check, dict):
            continue
        findings.append(
            {
                "claim": f"{name}：{check.get('status') or 'unknown'}｜{clip(check.get('reason') or '', 160)}",
                "evidence": f"compatibility.json software.checks.{name}",
                "kind": "fact",
            }
        )
    for name, item in list(host.items())[:2]:
        if isinstance(item, dict):
            findings.append(
                {
                    "claim": f"宿主机 {name}：{item.get('status') or 'unknown'}｜{clip(item.get('reason') or '', 160)}",
                    "evidence": f"compatibility.json host.{name}",
                    "kind": "fact",
                }
            )
    if not findings:
        findings.append(
            {
                "claim": f"版本配套核对完成，软件状态 {status_value}。",
                "evidence": "compatibility.json",
                "kind": "fact",
            }
        )
    missing = []
    if status_value == "unknown":
        missing.append("关键组件版本缺失，核对结果为 unknown；这不是「配套正常」")
    summary = (
        f"单份环境 dump 版本配套：场景 {data.get('scene') or 'auto'}，"
        f"软件状态 {status_value}。"
        + (f"{software.get('reason')}" if software.get("reason") else "")
        + f" 结果在 {output}。"
    )
    return {
        "status": "partial" if status_value == "unknown" else "ok",
        "summary": clip(summary, 500),
        "findings": findings[:5],
        "missing": missing,
        "artifacts": [str(output)],
    }


def _compare(paths, out_dir: Path, args) -> dict:
    output = out_dir / "diff.json"
    html = out_dir / "diff.html"
    proc = run_process(
        [sys.executable, str(COMPARE), *paths, "--json", str(output), "--html", str(html)],
        cwd=VENDOR,
        timeout=args.timeout,
        log_path=out_dir / "vendor.log",
    )
    if proc.get("timed_out"):
        raise AnalyzerError("timeout", f"超过 {args.timeout}s", status="failed")
    if not output.is_file():
        raise AnalyzerError(
            "analyzer-failed",
            "没有生成 diff.json。退出码 {code}；stderr：{err}".format(
                code=proc.get("exit_code"), err=tail(proc.get("stderr"), 900)
            ),
            status="failed",
        )
    data = read_json(output)
    if data.get("status") != "success":
        raise AnalyzerError("bad-input", f"比对未成功：{data.get('status')}；{data.get('error', '')}")
    summary = data.get("summary") or {}
    diff_count = int(summary.get("diff_count") or 0)
    similarity = summary.get("similarity")
    findings = []
    for section, diffs in (data.get("diffs") or {}).items():
        if not isinstance(diffs, dict):
            continue
        for item in (diffs.get("modified") or [])[:2]:
            values = item.get("values") or {}
            pairs = "；".join(f"{Path(name).name}={value}" for name, value in values.items())
            findings.append(
                {
                    "claim": f"{section}｜{item.get('path')}｜{clip(pairs, 200)}",
                    "evidence": "diff.json diffs",
                    "kind": "fact",
                }
            )
        for item in (diffs.get("only_in") or [])[:1]:
            present = "、".join(str(name) for name in (item.get("present_in") or []))
            findings.append(
                {
                    "claim": f"{section}｜仅存在于 {present or '部分文件'}：{item.get('path')}",
                    "evidence": "diff.json diffs.only_in",
                    "kind": "fact",
                }
            )
    if not findings:
        findings.append(
            {
                "claim": f"{len(paths)} 份 dump 未发现差异（相似度 {similarity}%）。",
                "evidence": "diff.json summary",
                "kind": "fact",
            }
        )
    skipped = data.get("skipped_files") or []
    status = "partial" if skipped else "ok"
    text = (
        f"比对 {len(data.get('files') or paths)} 份 dump：总路径 {summary.get('total_paths', 0)}，"
        f"一致 {summary.get('identical_paths', 0)}，差异 {diff_count}，相似度 {similarity}%。"
    )
    if skipped:
        text += f" 跳过 {len(skipped)} 个文件（见 missing）。"
    artifacts = [str(item) for item in (output, html) if item.is_file()]
    return {
        "status": status,
        "summary": clip(text, 500),
        "findings": findings[:5],
        "missing": [f"跳过：{item}" for item in skipped][:8],
        "artifacts": artifacts,
    }


def analyze(inputs, out_dir: Path, args) -> dict:
    for entry in (CHECK, COMPARE):
        if not entry.is_file():
            raise AnalyzerError("analyzer-not-installed", f"缺上游入口：{entry}", status="failed")
    paths = [item["path"] for item in inputs]
    for path in paths:
        if Path(path).suffix.lower() not in (".json", ".log", ".txt"):
            raise AnalyzerError(
                "bad-input",
                f"{path} 不是 dump JSON/日志文件；单份或对比都只接受 JSON 文本。",
            )
    if len(paths) == 1:
        return _compat(paths, out_dir, args)
    return _compare(paths, out_dir, args)


if __name__ == "__main__":
    sys.exit(run_adapter(ANALYZER, VERSION, analyze, "Ascend 环境版本配套 / 多份 dump 漂移比对"))
