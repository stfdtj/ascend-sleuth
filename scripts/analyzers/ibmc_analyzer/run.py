#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iBMC 一键收集日志分析适配器。

上游实现：scripts/analyzers/ibmc_analyzer/scripts/run_bmc_report.py
本文件负责参数转换、结果摘要与产物登记；上游判定不改，只在两处补证据：
缺失文件造成的在位误判（按未知处理），以及上游读不出 ECC 计数时的复读。
"""
from __future__ import annotations

import glob
import json
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
TOOL_DIR = HERE
ENTRY = TOOL_DIR / "scripts" / "run_bmc_report.py"


def _machine_label(machine: dict) -> str:
    ident = machine.get("identity") or {}
    name = ident.get("product_name") or (machine.get("versions") or {}).get("product_name") or ""
    sn = ident.get("product_sn") or machine.get("machine_tag") or ""
    label = " / ".join(part for part in (name, sn) if part)
    return label or Path(str(machine.get("source_root") or "unknown")).name


def _npu_source(machine: dict) -> str | None:
    """返回 npu_info 的实际路径；文件不在就返回 None。

    上游解析器把「文件缺失」和「解析结果为 0 张卡」都折叠成数量 0，
    于是缺文件会变成「疑似丢卡」。适配层按磁盘上有没有这个文件区分两者：
    有文件时 0 张卡是真的 0 张，没有文件时在位情况属于未知。
    """
    root = machine.get("source_root")
    if not root:
        return None
    base = Path(str(root))
    if not base.is_dir():
        return None
    direct = base / "AppDump" / "CpuMem" / "npu_info"
    if direct.is_file():
        return str(direct)
    for candidate in base.rglob("npu_info"):
        if candidate.is_file() and candidate.parent.name == "CpuMem":
            return str(candidate)
    return None


def _is_npu_presence_issue(issue: dict) -> bool:
    topic = str(issue.get("topic") or "")
    detail = str(issue.get("detail") or "")
    return "NPU" in topic or "NPU 数量" in detail or "丢卡" in detail


def _find_under(machine: dict, name: str) -> str | None:
    root = machine.get("source_root")
    if not root:
        return None
    base = Path(str(root))
    if not base.is_dir():
        return None
    direct = base / "AppDump" / "CpuMem" / name
    if direct.is_file():
        return str(direct)
    for candidate in base.rglob(name):
        if candidate.is_file() and candidate.parent.name == "CpuMem":
            return str(candidate)
    return None


def _ecc_from_disk(machine: dict) -> dict | None:
    """适配层直接读 npu_ecc_info.json。

    上游用 `encoding="utf-8"` 打开这个文件，带 BOM 的真实输入会抛异常并被吞成 `{}`，
    表现为「ECC 全 0」的静默漏报。这里用 `utf-8-sig` 复读一次：读得出计数就补进结论，
    读不出就明确写「存在但解析失败」，两种都不留给上游当作 0。
    返回 None 表示文件不存在。
    """
    path = _find_under(machine, "npu_ecc_info.json")
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"path": path, "error": True, "counts": {}}
    counts = {}
    for item in data.get("EccInfo") or []:
        name = str(item.get("Name") or "unknown")
        counts[name] = {
            "single": _as_int((item.get("SingleBitEcc") or {}).get("Count")),
            "multi": _as_int((item.get("MultiBitEcc") or {}).get("Count")),
        }
    return {"path": path, "error": False, "counts": counts}


def _as_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _sensor_observations(machine: dict, label: str, json_name: str) -> list:
    """非 ok 的传感器读数：保留原始值、单位、状态与证据来源，作为低优先级观察项。

    这里不判断「是否超过正常范围」——阈值词条仍在待审，工具侧等级只代表工具优先级。
    """
    rows = []
    for sensor in machine.get("sensors") or []:
        if not isinstance(sensor, dict):
            continue
        status = str(sensor.get("status") or "").strip()
        if status.lower() in ("", "ok", "normal"):
            continue
        rows.append(
            {
                "level": "observation",
                "topic": f"{label}｜传感器状态 {status}",
                "detail": (
                    f"{sensor.get('name')} 读数 {sensor.get('value')}{sensor.get('unit') or ''}；"
                    "阈值归属未核（见平台事实词条待审），只作观察项"
                ),
                "evidence": f"{json_name} sensors[{sensor.get('name')}]",
            }
        )
    return rows[:3]


def analyze(inputs, out_dir: Path, args) -> dict:
    if not ENTRY.is_file():
        raise AnalyzerError("analyzer-not-installed", f"缺上游入口：{ENTRY}", status="failed")
    cmd = [sys.executable, str(ENTRY), *[item["path"] for item in inputs], "-o", str(out_dir)]
    proc = run_process(cmd, cwd=TOOL_DIR, timeout=args.timeout, log_path=out_dir / "vendor.log")
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
    suppressed = []
    observations = []
    reconciled = []
    verdicts = []
    counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for path, machine in zip(jsons, machines):
        label = _machine_label(machine)
        health = machine.get("health") or {}
        verdict = health.get("verdict") or "UNKNOWN"
        verdicts.append(f"{label}={verdict}")
        issues = [item for item in (health.get("issues") or []) if isinstance(item, dict)]
        npu_source = _npu_source(machine)
        kept = []
        for issue in issues:
            if npu_source is None and _is_npu_presence_issue(issue):
                # 原始判定留在产物 JSON 里可追溯，但不作为证据交给主持 agent。
                suppressed.append(
                    {
                        "claim": f"{label}｜{issue.get('level')}｜{issue.get('topic')}：{issue.get('detail')}",
                        "reason": "npu-info-missing",
                        "detail": "未找到 AppDump/CpuMem/npu_info，在位数量未知，不据此判定丢卡",
                        "evidence": f"{Path(path).name} health.issues",
                    }
                )
                continue
            kept.append(issue)
            level = str(issue.get("level") or "")
            if level in counts:
                counts[level] += 1
        if npu_source is None:
            missing.append(f"{label}：NPU 在位未知（未找到 npu_info），相关在位判定已从发现里移除")
        severe = [item for item in kept if item.get("level") in ("P0", "P1")]
        for issue in severe[:3]:
            findings.append(
                {
                    "claim": f"{label}｜{issue.get('level')}｜{issue.get('topic')}：{issue.get('detail')}",
                    "evidence": f"{Path(path).name} health.issues",
                    "kind": "fact",
                }
            )
        if not severe:
            note = "未发现 P0/P1 项"
            if verdict != "正常" and any(item["claim"].startswith(f"{label}｜") for item in suppressed):
                note = "可见 P0/P1 项已因缺证据移除（见 suppressed），判定需补材料后才能确认"
            findings.append(
                {
                    "claim": f"{label}｜判定 {verdict}；{note}",
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

        # 低优先级项单独放 observations：保留原始值与等级，但不混进 findings，
        # 免得 Agent 把「工具关注项」当成「已证实的异常」。
        for issue in kept:
            if issue.get("level") in ("P2", "P3"):
                observations.append(
                    {
                        "level": issue.get("level"),
                        "topic": f"{label}｜{issue.get('topic')}",
                        "detail": str(issue.get("detail") or ""),
                        "evidence": f"{Path(path).name} health.issues",
                    }
                )
        observations.extend(_sensor_observations(machine, label, Path(path).name))

        # 上游 ECC 解析对 BOM 敏感：它读不出时按「空」处理。这里复读一次兜住。
        ecc_disk = _ecc_from_disk(machine)
        vendor_ecc = machine.get("npu_ecc") or {}
        if ecc_disk is not None and not vendor_ecc:
            if ecc_disk.get("error"):
                missing.append(f"{label}：npu_ecc_info.json 存在但解析失败，ECC 计数不可用")
            elif ecc_disk.get("counts"):
                hot = [
                    f"{name} 单bit={counts['single']} 多bit={counts['multi']}"
                    for name, counts in ecc_disk["counts"].items()
                    if (counts.get("multi") or 0) > 0 or (counts.get("single") or 0) > 0
                ]
                if hot:
                    findings.append(
                        {
                            "claim": f"{label}｜NPU ECC（适配层复读）：{'；'.join(hot)}",
                            "evidence": f"{Path(ecc_disk['path']).name}",
                            "kind": "fact",
                        }
                    )
                    reconciled.append(f"{label}：上游未读到 ECC 计数，适配层从 npu_ecc_info.json 补读")
                else:
                    observations.append(
                        {
                            "level": "observation",
                            "topic": f"{label}｜NPU ECC 复读",
                            "detail": "上游未读到计数；适配层复读后为全 0（无异常）",
                            "evidence": f"{Path(ecc_disk['path']).name}",
                        }
                    )

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
    if suppressed:
        summary += f" 另有 {len(suppressed)} 条判定因缺证据未作为发现（见 suppressed）。"
    if observations:
        summary += f" 低优先级观察 {len(observations)} 条（见 observations，未证实）。"

    artifacts = [*jsons, *htmls]
    payload = {
        "status": status,
        "summary": clip(summary, 500),
        "findings": findings[:5],
        "missing": missing[:8],
        "artifacts": [str(Path(item)) for item in artifacts[:20]],
        "raw_exit_code": proc.get("exit_code"),
    }
    if suppressed:
        # 被移除的判定连同原因一起留下：原始 JSON 里仍有它，这里给主持 agent 一个可追溯的入口，
        # 但它在 findings 之外，不会被当成已证实的异常。
        payload["suppressed"] = suppressed[:5]
    if observations:
        # P2/P3 与传感器非 ok 读数：带原始值、单位、等级与证据位置，交给 agent 自己判要不要追。
        payload["observations"] = observations[:6]
    if reconciled:
        payload["reconciled"] = reconciled[:3]
    return payload


if __name__ == "__main__":
    sys.exit(run_adapter(ANALYZER, VERSION, analyze, "iBMC 一键收集日志 → JSON + HTML 报告"))
