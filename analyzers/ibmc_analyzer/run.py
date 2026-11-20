#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iBMC 一键收集日志分析适配器。

上游实现：analyzers/vendor/ibmc_analyzer/scripts/run_bmc_report.py
本文件只做参数转换、结果摘要与产物登记，不改上游判据。
"""
from __future__ import annotations

import glob
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

ANALYZER = "ibmc_analyzer"
VERSION = UPSTREAM_COMMIT
VENDOR = ROOT / "vendor" / "ibmc_analyzer"
ENTRY = VENDOR / "scripts" / "run_bmc_report.py"


def _machine_label(machine: dict) -> str:
    ident = machine.get("identity") or {}
    name = ident.get("product_name") or (machine.get("versions") or {}).get("product_name") or ""
    sn = ident.get("product_sn") or machine.get("machine_tag") or ""
    label = " / ".join(part for part in (name, sn) if part)
    return label or Path(str(machine.get("source_root") or "unknown")).name


def analyze(inputs, out_dir: Path, args) -> dict:
    if not ENTRY.is_file():
        raise AnalyzerError("analyzer-not-installed", f"缺上游入口：{ENTRY}", status="failed")
    cmd = [sys.executable, str(ENTRY), *[item["path"] for item in inputs], "-o", str(out_dir)]
    proc = run_process(cmd, cwd=VENDOR, timeout=args.timeout, log_path=out_dir / "vendor.log")
    if proc.get("timed_out"):
        raise AnalyzerError("timeout", f"超过 {args.timeout}s，已终止；完成的部分在 {out_dir}", status="failed")
    if proc.get("spawn_error"):
        raise AnalyzerError("no-python", tail(proc.get("stderr")), status="failed")

    jsons = sorted(glob.glob(str(out_dir / "*_bmc.json")))
    jsons = [item for item in jsons if "all_machines" not in os.path.basename(item)]
    htmls = sorted(glob.glob(str(out_dir / "*.html")))
    if not jsons:
        raise AnalyzerError(
            "analyzer-failed",
            "没有生成任何机器 JSON。退出码 {code}；stderr：{err}".format(
                code=proc.get("exit_code"), err=tail(proc.get("stderr"), 600)
            ),
            status="failed",
        )

    machines = []
    parse_errors = []
    for path in jsons:
        try:
            machines.append(read_json(path))
        except (OSError, ValueError) as exc:
            parse_errors.append(f"{os.path.basename(path)}: {exc}")

    findings = []
    missing = []
    verdicts = []
    counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for path, machine in zip(jsons, machines):
        label = _machine_label(machine)
        health = machine.get("health") or {}
        verdict = health.get("verdict") or "UNKNOWN"
        verdicts.append(f"{label}={verdict}")
        machine_counts = health.get("counts") or {}
        for level in counts:
            counts[level] += int(machine_counts.get(level) or 0)
        issues = [item for item in (health.get("issues") or []) if isinstance(item, dict)]
        severe = [item for item in issues if item.get("level") in ("P0", "P1")]
        for issue in severe[:3]:
            findings.append(
                {
                    "claim": f"{label}｜{issue.get('level')}｜{issue.get('topic')}：{issue.get('detail')}",
                    "evidence": f"{Path(path).name} health.issues",
                    "kind": "fact",
                }
            )
        if not severe:
            findings.append(
                {
                    "claim": f"{label}｜判定 {verdict}；未发现 P0/P1 项",
                    "evidence": f"{Path(path).name} health.verdict",
                    "kind": "fact",
                }
            )
        parsed = len(machine.get("parsed_files") or [])
        if parsed == 0:
            missing.append(f"{label}：没有解析到可用文件")
        if machine.get("collected_at") in ("", None):
            missing.append(f"{label}：缺采集时间")
        if not (machine.get("current_event") or {}).get("file_exists"):
            missing.append(f"{label}：缺 current_event.txt")

    status = "ok"
    if proc.get("exit_code") not in (0, None):
        status = "partial"
    if missing:
        status = "partial"
    if parse_errors:
        status = "partial"
        findings.append(
            {
                "claim": "部分机器 JSON 解析失败：" + "；".join(parse_errors),
                "evidence": "适配器读取结果",
                "kind": "fact",
            }
        )

    summary = (
        f"解析 {len(machines)} 台机器；判定：{'；'.join(verdicts)}。"
        f"P0={counts['P0']}，P1={counts['P1']}，P2={counts['P2']}，P3={counts['P3']}。"
        f"每台机器的结构化结果与 HTML 报告在 {out_dir}。"
    )
    if missing:
        summary += f" 缺数据 {len(missing)} 项（见 missing）。"

    artifacts = [*jsons, *htmls]
    return {
        "status": status,
        "summary": clip(summary, 500),
        "findings": findings[:5],
        "missing": missing[:8],
        "artifacts": [str(Path(item)) for item in artifacts[:20]],
        "raw_exit_code": proc.get("exit_code"),
    }


if __name__ == "__main__":
    sys.exit(run_adapter(ANALYZER, VERSION, analyze, "iBMC 一键收集日志 → JSON + HTML 报告"))
