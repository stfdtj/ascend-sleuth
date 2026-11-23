#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三组确定性对照：A 原 diagnose / B 加 references / C 加 references 与分析器。

三组的读材料权限相同：都能 grep 与读原文件。差别只在知识（B/C 有词条）与工具（C 有分析器）。

- A：没有 BMC 词条，只能盲搜整个包；能搜到字面，但不知道该看哪份、数怎么算。
- B：词条点名了该看哪些文件，可以定向读到同样的字面证据；仍然要自己解析数值与单位。
- C：分析器把这些读成结构化结果，Agent 只读摘要与发现/观察项。

所以本脚本测的是「同样的证据，各臂要读多少、要几步」，不是「B 读不到」。
它**不评「诊断是否正确」**——那要人判或真实模型参与。

用法：
  python3 scripts/analyzer_ab.py
  python3 scripts/analyzer_ab.py --json-out <路径>
  python3 scripts/analyzer_ab.py --case case-03-healthy
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "analyzers" / "cli.py"
CASES = ROOT / "tests" / "fixtures" / "analyzers" / "cases.json"
KNOWLEDGE = ROOT / "knowledge"
REFERENCES = ROOT / "references"
BMC_TERMS = ("bmc", "ibmc", "dump_info", "一键收集")

sys.path.insert(0, str(ROOT / "scripts" / "analyzers"))
from _lib import force_utf8  # noqa: E402

# 中文为主的文本，粗估 1 token ≈ 1.6 字符；只比较相对量级，不当计费依据。
CHARS_PER_TOKEN = 1.6


def knowledge_coverage() -> dict:
    """A 臂：知识库本体里有没有 BMC 相关的 case。"""
    hits = []
    for path in KNOWLEDGE.rglob("*.yaml"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        low = text.lower()
        if any(term in low for term in BMC_TERMS):
            hits.append(str(path.relative_to(ROOT)))
    return {"hits": len(hits), "files": hits[:5]}


def reference_coverage() -> dict:
    """B/C 臂共用：active 的 BMC 词条。"""
    entries = []
    for path in REFERENCES.rglob("*.yaml"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "status: active" not in text:
            continue
        low = text.lower()
        if not any(term in low for term in BMC_TERMS):
            continue
        entries.append({"file": str(path.relative_to(ROOT)), "text": text})
    return {
        "count": len(entries),
        "files": [item["file"] for item in entries],
        "chars": sum(len(item["text"]) for item in entries),
        "entries": entries,
    }


def scan_raw(case: dict, ref_text: str) -> dict:
    """模拟「有读文件权限的 agent」在新日志上要付的成本。

    blind_bytes：不知道看哪份时的成本，等于整包文本体积。
    targeted_bytes：词条点名了文件之后的成本，只看被点名的那些。
    needles：字面证据能不能被搜到（三组都能，差别在解释与聚合）。
    """
    base = ROOT / case["path"]
    needles = case.get("gt_needles") or []
    blind = 0
    targeted = 0
    found = set()
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        size = path.stat().st_size
        blind += size
        if path.name in ref_text:
            targeted += size
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for needle in needles:
            if needle in text:
                found.add(needle)
    return {
        "blind_bytes": blind,
        "targeted_bytes": targeted,
        "needles_found": len(found),
        "needles_total": len(needles),
        "found_needles": sorted(found),
    }


def run_c(case: dict, out_root: Path, enabled: bool) -> dict:
    out = out_root / case["id"]
    started = time.time()
    proc = subprocess.run(
        [
            sys.executable, str(CLI), "run", case["expected_analyzer"],
            "--inputs", json.dumps([str((ROOT / case["path"]).resolve())]),
            "--out-dir", str(out),
            "--session-id", "ab-deterministic",
            "--purpose", case["id"],
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "SLEUTH_ANALYZERS": "on" if enabled else "off", "PYTHONUTF8": "1"},
        timeout=600,
    )
    wall_ms = int((time.time() - started) * 1000)
    result_path = out / "result.json"
    result = {}
    if result_path.is_file():
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except ValueError:
            result = {}
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout or "",
        "wall_ms": wall_ms,
        "out_dir": str(out),
        "result": result,
    }


def evaluate_c(case: dict, run: dict) -> dict:
    result = run["result"]
    findings = result.get("findings") or []
    claims = [str(item.get("claim") or "") for item in findings if isinstance(item, dict)]
    observations = result.get("observations") or []
    obs_text = " ".join(f"{item.get('topic')} {item.get('detail')}" for item in observations)
    # 交给 agent 当发现看的是 summary + findings + missing；observations 是「观察」不是「结论」。
    visible = " ".join([str(result.get("summary") or "")] + claims + [str(item) for item in (result.get("missing") or [])])
    measured = " ".join(claims + [obs_text])
    needles = case.get("gt_needles") or []
    return {
        "status": result.get("status") or "no-result",
        "evidence_hit": len([needle for needle in needles if needle in measured]),
        "evidence_needles": len(needles),
        "violations": [needle for needle in (case.get("must_not_appear") or []) if needle in visible],
        "findings": len(findings),
        "observations": len(observations),
        "findings_with_evidence": sum(1 for item in findings if isinstance(item, dict) and item.get("evidence")),
        "suppressed": len(result.get("suppressed") or []),
        "missing": len(result.get("missing") or []),
        "agent_visible_chars": len(visible) + len(obs_text),
        "duration_ms": result.get("duration_ms"),
        "wall_ms": run["wall_ms"],
        "exit_code": run["exit_code"],
    }


def switch_checks(case: dict, out_root: Path) -> dict:
    off = run_c(case, out_root / "off", enabled=False)
    bad_case = dict(case)
    bad_case["path"] = "tests/fixtures/analyzers/does-not-exist"
    bad = run_c(bad_case, out_root / "bad", enabled=True)
    return {
        "disabled_exit": off["exit_code"],
        "disabled_created_output": (Path(off["out_dir"]) / "result.json").exists(),
        "bad_input_exit": bad["exit_code"],
        "bad_input_reason": (bad["result"] or {}).get("reason"),
        "bad_input_data_needed": bool((bad["result"] or {}).get("data_needed")),
    }


def main(argv=None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", default=None, help="只跑指定案例 id，可重复")
    parser.add_argument("--json-out", default="", help="结构化结果写到这里")
    args = parser.parse_args(argv)

    manifest = json.loads(CASES.read_text(encoding="utf-8"))
    cases = [case for case in manifest["cases"] if not args.case or case["id"] in args.case]
    knowledge = knowledge_coverage()
    refs = reference_coverage()
    ref_text = "\n".join(item["text"] for item in refs["entries"])

    listing = subprocess.run(
        [sys.executable, str(CLI), "list", "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    try:
        available = [item["name"] for item in json.loads(listing.stdout)]
    except (ValueError, KeyError):
        available = []

    rows = []
    with tempfile.TemporaryDirectory(prefix="ab-bmc-") as tmp:
        out_root = Path(tmp)
        for case in cases:
            run = run_c(case, out_root / "c", enabled=True)
            row = {
                "case": case["id"],
                "gt": case["gt"],
                "expected_analyzer": case["expected_analyzer"],
                "discovered": case["expected_analyzer"] in available,
                "a_knowledge_hits": knowledge["hits"],
                **scan_raw(case, ref_text),
                **evaluate_c(case, run),
            }
            rows.append(row)
            print(f".. {row['case']} C={row['status']} 证据 {row['evidence_hit']}/{row['evidence_needles']}", file=sys.stderr)
        switch = switch_checks(cases[0], out_root / "switch")

    needles = sum(row["needles_total"] for row in rows)
    raw_hits = sum(row["needles_found"] for row in rows)
    c_hits = sum(row["evidence_hit"] for row in rows)
    violations = sum(len(row["violations"]) for row in rows)
    blind_bytes = sum(row["blind_bytes"] for row in rows)
    targeted_bytes = sum(row["targeted_bytes"] for row in rows)
    c_chars = sum(row["agent_visible_chars"] for row in rows)

    print()
    print("| 案例 | A 盲读字节 | B 定向字节 | A/B 可搜到 | C 证据 | C 违反 | C 发现/观察/抑制 | C 可见字符 | C 耗时 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for row in rows:
        print(
            f"| {row['case']} | {row['blind_bytes']} | {row['targeted_bytes']} | "
            f"{row['needles_found']}/{row['needles_total']} | {row['evidence_hit']}/{row['evidence_needles']} | "
            f"{len(row['violations'])} | {row['findings']}/{row['observations']}/{row['suppressed']} | "
            f"{row['agent_visible_chars']} | {row['duration_ms']} |"
        )
    print()
    print(f"- A 臂：知识库含 BMC 相关词的文件 {knowledge['hits']} 个；不看词条时只能盲读整包 {blind_bytes} 字节。")
    print(f"- B 臂：active 相关词条 {refs['count']} 条（{refs['chars']} 字符）；按词条点名读到 {targeted_bytes} 字节；"
          f"同样能搜到 {raw_hits}/{needles} 的字面证据，数值要自己解析。")
    print(f"- C 臂：调用 {len(rows)} 次；证据命中 {c_hits}/{needles}；不该出现的结论 {violations} 条；"
          f"Agent 只需读 {c_chars} 字符（≈{round(c_chars / CHARS_PER_TOKEN)} tokens，估计值）。")
    print(f"- 读材料成本比：B 定向 {targeted_bytes} 字节 对 C {c_chars} 字符；A 盲读 {blind_bytes} 字节。")
    print(f"- 退化：关开关退出码 {switch['disabled_exit']}、建产物={switch['disabled_created_output']}；"
          f"坏输入退出码 {switch['bad_input_exit']}、原因 {switch['bad_input_reason']}、"
          f"给了 data_needed={switch['bad_input_data_needed']}。")
    print()
    print("说明：可搜到不等于能判对；A/B 要靠人把字面读成结论。C 的诊断正确性同样未评估。")

    if args.json_out:
        payload = {
            "schema_version": 3,
            "note": "确定性三组对照：三组读材料权限相同（可 grep/读文件），差别在词条与工具；不含模型判读",
            "knowledge_coverage": knowledge,
            "reference_coverage": {key: refs[key] for key in ("count", "files", "chars")},
            "listed_analyzers": available,
            "rows": rows,
            "totals": {
                "a_knowledge_hits": knowledge["hits"],
                "raw_needles_found": raw_hits,
                "needles_total": needles,
                "blind_bytes": blind_bytes,
                "targeted_bytes": targeted_bytes,
                "c_calls": len(rows),
                "c_evidence_hit": c_hits,
                "violations": violations,
                "c_visible_chars": c_chars,
            },
            "switch_checks": switch,
        }
        Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
