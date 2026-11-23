#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两张 Prof 数据比对适配器。

上游实现：scripts/analyzers/vendor/prof-compare/scripts/{run_compare,main_analyzer}.py
两种输入：
  - 一份已有的 compare xlsx：直接解析出 HTML / JSON / 中文 xlsx；
  - 两份 prof 目录：需要本机已安装 msprof-analyze，先 compare 再解析。
本适配器不安装任何依赖；缺依赖返回 blocked。
"""
from __future__ import annotations

import glob
import importlib.util
import shutil
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

ANALYZER = "prof-compare"
VERSION = UPSTREAM_COMMIT
VENDOR = ROOT / "vendor" / "prof-compare"
RUN_COMPARE = VENDOR / "scripts" / "run_compare.py"
MAIN_ANALYZER = VENDOR / "scripts" / "main_analyzer.py"


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _summarize(out_dir: Path) -> dict:
    json_path = out_dir / "compare_analysis_result.json"
    if not json_path.is_file():
        raise AnalyzerError("analyzer-failed", f"没有生成 {json_path}", status="failed")
    data = read_json(json_path)
    analysis = data.get("analysis_summary") or {}
    improvements = [str(item) for item in (analysis.get("improvements") or [])]
    risks = [str(item) for item in (analysis.get("risks") or [])]
    unavailable = [str(item) for item in (analysis.get("unavailable_sheets") or [])]
    findings = []
    for text in risks[:3]:
        findings.append({"claim": clip(text, 200), "evidence": "compare_analysis_result.json analysis_summary.risks", "kind": "fact"})
    for text in improvements[:2]:
        findings.append({"claim": clip(text, 200), "evidence": "compare_analysis_result.json analysis_summary.improvements", "kind": "fact"})
    if not findings:
        findings.append(
            {
                "claim": "对比完成，但没有生成可解释的改善/劣化条目；检查输入是否包含 OverallMetrics 等 Sheet。",
                "evidence": "compare_analysis_result.json",
                "kind": "fact",
            }
        )
    overall = data.get("overall_metrics") or {}
    e2e = overall.get("e2e") or {}
    summary = "Prof 比对完成"
    if e2e:
        summary += (
            f"：E2E {e2e.get('base')} → {e2e.get('comp')}，"
            f"差 {e2e.get('diff')}（比率 {e2e.get('ratio')}）"
        )
    summary += f"；改善 {len(improvements)} 条、劣化 {len(risks)} 条。"
    if unavailable:
        summary += f" 未提供的分析页：{'、'.join(unavailable[:5])}。"
    artifacts = sorted(glob.glob(str(out_dir / "*.html")))
    for name in ("compare_analysis_result.json", "chinese_xlsx/compare_chinese_result.xlsx"):
        candidate = out_dir / name
        if candidate.is_file():
            artifacts.append(str(candidate))
    status = "partial" if unavailable else "ok"
    return {
        "status": status,
        "summary": clip(summary, 500),
        "findings": findings[:5],
        "missing": [f"缺少分析页：{item}" for item in unavailable][:8],
        "artifacts": artifacts,
    }


def analyze(inputs, out_dir: Path, args) -> dict:
    for entry in (RUN_COMPARE, MAIN_ANALYZER):
        if not entry.is_file():
            raise AnalyzerError("analyzer-not-installed", f"缺上游入口：{entry}", status="failed")

    files = [item["path"] for item in inputs if item["kind"] == "file"]
    dirs = [item["path"] for item in inputs if item["kind"] == "dir"]

    if len(inputs) == 1 and files and files[0].lower().endswith(".xlsx"):
        if not _has_module("openpyxl"):
            raise AnalyzerError(
                "dependency-missing",
                "解析 compare xlsx 需要 openpyxl；本仓库不自动安装。请在预配环境执行 "
                "`python -m pip install openpyxl` 后重跑。",
            )
        proc = run_process(
            [sys.executable, str(MAIN_ANALYZER), files[0], "-o", str(out_dir)],
            cwd=VENDOR,
            timeout=args.timeout,
            log_path=out_dir / "vendor.log",
        )
        if proc.get("timed_out"):
            raise AnalyzerError("timeout", f"超过 {args.timeout}s", status="failed")
        if proc.get("exit_code") not in (0, None) and not (out_dir / "compare_analysis_result.json").is_file():
            detail = tail((proc.get("stderr") or "") + "\n" + (proc.get("stdout") or ""), 800)
            raise AnalyzerError("bad-input", f"xlsx 无法解析或不是 msprof-analyze compare 结果：{detail}", status="failed")
        return _summarize(out_dir)

    if len(dirs) == 2 and not files:
        if not (shutil.which("msprof-analyze") or _has_module("msprof_analyze")):
            raise AnalyzerError(
                "dependency-missing",
                "两份 prof 目录需要先跑 msprof-analyze compare；本机未安装 msprof-analyze，"
                "本仓库不自动安装。可在预配环境安装，或直接提供已有的 compare xlsx。",
            )
        base, comp = dirs[0], dirs[1]
        proc = run_process(
            [
                sys.executable,
                str(RUN_COMPARE),
                "-d", comp,
                "-bp", base,
                "-o", str(out_dir),
                "--skip_install",
            ],
            cwd=VENDOR,
            timeout=args.timeout,
            log_path=out_dir / "vendor.log",
        )
        if proc.get("timed_out"):
            raise AnalyzerError("timeout", f"超过 {args.timeout}s", status="failed")
        if proc.get("exit_code") not in (0, None):
            detail = tail((proc.get("stderr") or "") + "\n" + (proc.get("stdout") or ""), 900)
            raise AnalyzerError(
                "analyzer-failed",
                f"run_compare 退出码 {proc.get('exit_code')}；{detail}",
                status="failed",
            )
        return _summarize(out_dir)

    raise AnalyzerError(
        "bad-input",
        "接受两种输入：一份 compare xlsx；或两份单卡 prof 目录（inputs[0]=A 基准，inputs[1]=B 对比）。",
    )


if __name__ == "__main__":
    sys.exit(run_adapter(ANALYZER, VERSION, analyze, "compare xlsx / 两份单卡 Prof 的细粒度比对"))
