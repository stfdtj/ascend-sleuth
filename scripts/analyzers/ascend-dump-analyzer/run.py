#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ascend 环境快照比对适配器。

上游实现：scripts/analyzers/vendor/ascend-dump-analyzer/references/compare_dumps.py
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
COMPARE = VENDOR / "references" / "compare_dumps.py"


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
    upstream_status = data.get("status")
    if upstream_status not in {"success", "partial"}:
        raise AnalyzerError("bad-input", f"比对未成功：{data.get('status')}；{data.get('error', '')}")
    summary = data.get("summary") or {}
    diff_count = int(summary.get("diff_count") or 0)
    similarity = summary.get("similarity")
    compared_count = len(data.get("files") or paths)
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
                "claim": f"{compared_count} 份已比对的快照未发现差异（相似度 {similarity}%）。",
                "evidence": "diff.json summary",
                "kind": "fact",
            }
        )
    skipped = data.get("skipped_files") or []
    status = "partial" if upstream_status == "partial" else "ok"
    text = (
        f"比对 {compared_count} 份快照：总路径 {summary.get('total_paths', 0)}，"
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
    if not COMPARE.is_file():
        raise AnalyzerError("analyzer-not-installed", f"缺上游入口：{COMPARE}", status="failed")
    if len(inputs) < 2:
        raise AnalyzerError("bad-input", "环境快照比对需要至少两份环境 dump JSON。")
    paths = []
    for item in inputs:
        path = item["path"]
        if item["kind"] != "file" or Path(path).suffix.lower() not in {".json", ".log", ".txt"}:
            raise AnalyzerError("bad-input", f"{path} 不是环境快照文件。输入须包含 JSON 文本。")
        paths.append(path)
    return _compare(paths, out_dir, args)


if __name__ == "__main__":
    sys.exit(run_adapter(ANALYZER, VERSION, analyze, "Ascend 环境快照比对"))
