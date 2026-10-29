"""Checkpoint B validation: candidate discovery + six-axis evidence + contradictions.

Builds a labelled synthetic draft set on top of the real 173-case library, runs the
prototype, and reports:
  * must-surface recall (each pair the proposal promises to surface),
  * structured contradiction hints,
  * how many axes came back `unknown` and why (missing schema fields),
  * nomination volume / runtime / unshown count,
  * what happens with legacy flat drafts (no sources.yaml).

The synthetic labels are hand-made and are NOT production data. The library is the
real repository library at the baseline commit, unmodified.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fixtures as F
import lab_common as L

import yaml

PY = sys.executable
HERE = Path(__file__).parent
FINDER = HERE.parent / "proto" / "find_duplicates.py"

BASE = dict(F.CASE_A)


def case(prefix: str, **over) -> dict:
    c = dict(BASE)
    c.update(over)
    c["id"] = prefix
    if "expected" not in over:
        c["expected"] = "regex:signature-" + prefix.rsplit("-", 1)[-1]
    return c


def put_group(root: Path, draft_id: str, case_dict: dict, sources: dict):
    d = root / "postmortems/inbox" / draft_id
    d.mkdir(parents=True, exist_ok=True)
    case_dict = dict(case_dict)
    sid = (sources.get("source") or {}).get("session")
    if sid:
        case_dict["session"] = sid          # the draft's own diagnosis session
    (d / "case.yaml").write_text(F.case_text(case_dict), encoding="utf-8")
    (d / "postmortem.md").write_text(f"# {draft_id}\n", encoding="utf-8")
    sources = dict(sources)
    if not sources.get("verification"):
        sid = (sources.get("source") or {}).get("session")
        sources["verification"] = [{"kind": "feedback", "ref": sid}] if sid else []
    src = {"draft_id": draft_id, "created_at": "2026-10-28T10:00:00+08:00",
           "source": sources.get("source"), "sessions": sources.get("sessions", []),
           "conditions": sources.get("conditions", {}),
           "verification": sources.get("verification", []),
           "semantic_summary": sources.get("semantic_summary", {})}
    summary = dict(src["semantic_summary"] or {})
    summary["root_cause"] = case_dict.get("root_cause")
    summary["fix"] = case_dict.get("fix")
    src["semantic_summary"] = summary
    (d / "sources.yaml").write_text(yaml.safe_dump(src, allow_unicode=True, sort_keys=False),
                                    encoding="utf-8")
    return d


def main() -> int:
    rec = L.Recorder("checkpoint-b")
    L.seed_integrated_main()
    repo = L.fresh_clone("b-lab")
    inbox = repo / "postmortems/inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    common_src = {
        "source": {"kind": "diagnosis", "deployment": "b-lab", "session": "2026-10-28-d1"},
        "sessions": ["2026-10-28-d1"],
        "conditions": {"workload_type": "inference", "framework": "vllm-ascend",
                       "versions": {"vllm-ascend": "0.22.0"},
                       "platform": "A2-310P", "stage": "启动"},
        "verification": [],
        "semantic_summary": {"root_cause": BASE["root_cause"], "fix": BASE["fix"],
                             "signature": "npu-smi 310P, bf16 not supported"},
    }

    # D1: same root cause as library case 90001, filed under another category
    put_group(repo, "2026-10-28-diag-001", case("VLLM-ASC-91001", category="precision",
              title="310P 上 qwen3-tts 推理音频为空：bf16 dtype 不受支持",
              symptoms=["音频输出全为 0", "npu-smi 显示 310P", "日志 dtype=bfloat16"]), dict(common_src))
    # D2: same semantic problem, paraphrased so that lexical overlap collapses
    put_group(repo, "2026-10-28-diag-002", case("VLLM-ASC-91002", category="precision",
              title="推理结果为零值：精度设置未生效",
              symptoms=["端到端结果全为零", "设备为 A2 推理卡", "配置文件的精度项被忽略"]),
              {**common_src, "sessions": ["2026-10-28-d2"],
               "source": {"kind": "diagnosis", "deployment": "b-lab", "session": "2026-10-28-d2"}})
    # D3: identical discriminator, different root cause
    put_group(repo, "2026-10-28-diag-003", case("VLLM-ASC-91003", category="interrupt",
              title="启动报 bf16 不被支持（驱动版本不匹配）",
              symptoms=["启动即失败", "日志 bfloat16 is not supported", "npu-smi 显示 310P"],
              root_cause="NPU 驱动与固件版本不匹配，算子选择失败",
              fix="升级驱动与固件到配套版本", expected=BASE["expected"]),
              {**common_src, "sessions": ["2026-10-28-d3"],
              "source": {"kind": "diagnosis", "deployment": "b-lab", "session": "2026-10-28-d3"}})
    # D4/D5: one upstream issue, two independent problems
    for i, (rid, root, fix) in enumerate([
            ("2026-10-28-diag-004", "镜像缺 vllm-omni 依赖，启动 import 失败", "源码安装 vllm-omni"),
            ("2026-10-28-diag-005", "CUDA 版 torch 与 torch_npu 混装", "卸载 CUDA 版 torch 重装")]):
        put_group(repo, rid, case(f"VLLM-ASC-9100{i+4}", category="interrupt",
                  title=f"同一个上游 issue 的另一个问题 {i+1}",
                  symptoms=[f"issue 10303 的另一个现场 {i+1}", "启动失败"],
                  root_cause=root, fix=fix),
                  {**common_src, "source": {"kind": "issue", "deployment": "b-lab",
                                            "upstream": {"repo": "vllm-project/vllm-ascend",
                                                         "issue": 10303}},
                   "sessions": [f"2026-10-28-d{i+4}"],
                   "semantic_summary": {"root_cause": root, "fix": fix}})
    # D6: same fix, different version constraint
    put_group(repo, "2026-10-28-diag-006", case("VLLM-ASC-91006", category="interrupt",
              title="310P 启动 bf16 报错（0.23 版本现场）",
              symptoms=["启动报 bfloat16 is not supported", "npu-smi 310P", "dtype 为 bfloat16"],
              ranges=["==0.23.0"]),
              {**common_src, "sessions": ["2026-10-28-d6"],
               "conditions": {**common_src["conditions"], "versions": {"vllm-ascend": "0.23.0"}}})
    # D7: overlapping but non-identical conditions
    put_group(repo, "2026-10-28-diag-007", case("VLLM-ASC-91007", category="interrupt",
              title="310P 上 bf16 启动失败（0.22 系列）",
              symptoms=["npu-smi 310P", "bfloat16 is not supported", "dtype 配置 bf16"],
              ranges=[">=0.22.0,<0.23.0"], platforms=["A2"]),
              {**common_src, "sessions": ["2026-10-28-d7"],
               "conditions": {**common_src["conditions"], "versions": {"vllm-ascend": "0.22.1"},
                              "platform": "A2"}})
    # D8: contradictory fix, correct under a different condition
    put_group(repo, "2026-10-28-diag-008", case("VLLM-ASC-91008", category="interrupt",
              title="310P bf16 启动失败（降级方案）",
              symptoms=["npu-smi 显示 310P", "bfloat16 is not supported"],
              fix="降级到 0.21.0 规避", root_cause="310P 不支持 bfloat16",
              ranges=["==0.21.0"], expected=BASE["expected"]),
              {**common_src, "sessions": ["2026-10-28-d8"],
               "conditions": {**common_src["conditions"], "versions": {"vllm-ascend": "0.21.0"}}})
    # D9: same verification event as library case 90001's source_session
    put_group(repo, "2026-10-28-diag-009", case("VLLM-ASC-91009", category="interrupt",
              title="310P bf16 启动失败（复用同一现场回报）",
              symptoms=["npu-smi 310P", "bfloat16 is not supported", "dtype bfloat16"]),
              {**common_src, "sessions": [],
               "source": {"kind": "diagnosis", "deployment": "b-lab", "session": None},
               "verification": [{"kind": "feedback", "ref": "2026-10-28-conc-a01"}]})
    # D10: same diagnosis, different sessions
    put_group(repo, "2026-10-28-diag-010", case("VLLM-ASC-91010", category="interrupt",
              title="310P bf16 启动失败（另一次诊断）",
              symptoms=["npu-smi 310P", "bfloat16 is not supported", "dtype 为 bfloat16"]),
              {**common_src, "sessions": ["2026-10-28-d10"],
               "source": {"kind": "diagnosis", "deployment": "b-lab", "session": "2026-10-28-d10"},
               "verification": [{"kind": "feedback", "ref": "2026-10-28-d10"}]})
    # D11: unrelated negative control
    put_group(repo, "2026-10-28-diag-011", case("VLLM-ASC-91011", category="performance",
              title="VERL 训练吞吐下降：actor 与 rollout 配比不当",
              symptoms=["每秒样本数下降", "actor 卡在等待", "rollout 队列积压"],
              root_cause="actor 与 rollout 资源配比不当", fix="调整 actor 数量与 batch 配比"),
              {**common_src, "sessions": ["2026-10-28-d11"],
               "conditions": {"workload_type": "training", "framework": "verl",
                              "versions": {"verl": "1.2.0"}, "platform": "A3-910C"},
               "source": {"kind": "diagnosis", "deployment": "b-lab", "session": "2026-10-28-d11"},
               "semantic_summary": {"root_cause": "actor 与 rollout 资源配比不当", "fix": "调整配比"}})

    t0 = time.perf_counter()
    proc = __import__("subprocess").run(
        [PY, str(FINDER), "--root", str(repo), "--json"],
        capture_output=True, text=True, encoding="utf-8")
    elapsed = round(time.perf_counter() - t0, 2)
    proc_all = __import__("subprocess").run(
        [PY, str(FINDER), "--root", str(repo), "--json", "--limit", "0"],
        capture_output=True, text=True, encoding="utf-8")
    rec.add("find_duplicates --json (11 synthetic drafts vs real 173-case library)", proc.returncode,
            proc.stdout[:200], proc.stderr)
    rec.add("find_duplicates --json --limit 0 (no display cap)", proc_all.returncode,
            proc_all.stdout[:200], proc_all.stderr)
    payload = json.loads(proc.stdout) if proc.returncode == 0 else {"pairs": [], "unshown": 0}
    payload_all = json.loads(proc_all.stdout) if proc_all.returncode == 0 else {"pairs": []}

    def make_lookup(pl):
        def find(a, b):
            for p in pl["pairs"]:
                if {p.get("a_case_id"), p.get("b_case_id")} == {a, b}:
                    return p
            return None
        return find
    find_display = make_lookup(payload)
    find_all = make_lookup(payload_all)

    def probe(a, b):
        shown, any_ = find_display(a, b), find_all(a, b)
        return {
            "generated": any_ is not None,
            "displayed": shown is not None,
            "reasons": (any_ or {}).get("reasons", []),
            "axes": (any_ or {}).get("axes", {}),
            "hints": (any_ or {}).get("hints", []),
        }

    pairs = payload["pairs"]
    def find(a, b):
        for p in pairs:
            if {p.get("a_case_id"), p.get("b_case_id")} == {a, b}:
                return p
        return None
    def has(a, b):
        return find(a, b) is not None
    def reasons(a, b):
        p = find(a, b)
        return p["reasons"] if p else []
    def hints(a, b):
        p = find(a, b)
        return p["hints"] if p else []
    def axes(a, b):
        p = find(a, b)
        return p["axes"] if p else {}

    findings = {
        "D1 same root cause, other category vs 90001": probe("VLLM-ASC-91001", "VLLM-ASC-90001"),
        "D1b same draft vs sibling case 90002": probe("VLLM-ASC-91001", "VLLM-ASC-90002"),
        "D2 paraphrase vs 90001 (expected lexical miss)": probe("VLLM-ASC-91002", "VLLM-ASC-90001"),
        "D3 same signature different root cause": probe("VLLM-ASC-91003", "VLLM-ASC-90001"),
        "D4/D5 same issue two problems": probe("VLLM-ASC-91004", "VLLM-ASC-91005"),
        "D6 same fix different version": probe("VLLM-ASC-91006", "VLLM-ASC-90001"),
        "D7 overlapping non-identical conditions": probe("VLLM-ASC-91007", "VLLM-ASC-90001"),
        "D8 contradictory fix, disjoint condition": probe("VLLM-ASC-91008", "VLLM-ASC-90001"),
        "D9 same verification event": probe("VLLM-ASC-91009", "VLLM-ASC-90001"),
        "D10 same diagnosis different sessions": probe("VLLM-ASC-91010", "VLLM-ASC-90001"),
        "D11 unrelated control vs 90001": probe("VLLM-ASC-91011", "VLLM-ASC-90001"),
    }
    rec.add("must-surface results (generated vs displayed)", 0,
            json.dumps(findings, ensure_ascii=False, indent=2))
    (L.LOG_DIR / "checkpoint-b-findings.json").write_text(
        json.dumps({"findings": findings, "pairs": pairs,
                    "pairs_all": len(payload_all["pairs"]),
                    "unshown": payload.get("unshown"),
                    "library_cases": payload.get("library_cases")},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(findings, ensure_ascii=False, indent=2))
    rec.add("nomination volume and runtime", 0,
            f"displayed={len(pairs)}; generated={len(payload_all['pairs'])}; "
            f"unshown={payload.get('unshown')}; library={payload.get('library_cases')}; "
            f"inputs={payload.get('inputs')}; seconds={elapsed}")

    # an incomplete draft (no DONE, no sources.yaml) is still consumed by the finder
    partial = repo / "postmortems/inbox/2026-10-28-diag-099"
    partial.mkdir(parents=True, exist_ok=True)
    (partial / "case.yaml").write_text(F.case_text(case("VLLM-ASC-91099",
        expected=BASE["expected"],
        symptoms=["npu-smi 310P", "bfloat16 is not supported", "dtype bfloat16"])), encoding="utf-8")
    proc2 = __import__("subprocess").run(
        [PY, str(FINDER), "--root", str(repo), "--json", "--limit", "0"],
        capture_output=True, text=True, encoding="utf-8")
    payload2 = json.loads(proc2.stdout) if proc2.returncode == 0 else {"pairs": []}
    consumed = any("VLLM-ASC-91099" in (p.get("a_case_id") or "", p.get("b_case_id") or "")
                   for p in payload2["pairs"])
    rec.add("incomplete draft (no DONE) consumed by Checkpoint B?", 0,
            json.dumps({"inputs": payload2.get("inputs"), "appears_in_candidates": consumed,
                        "note": "the proposed finder does not read DONE; groom does"}),
            consumed=consumed)

    # axis coverage on the real library
    lib = []
    for p in (repo / "knowledge").rglob("*.yaml"):
        if "_index" in p.parts:
            continue
        try:
            doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        lib.extend([c for c in doc.get("cases") or [] if isinstance(c, dict)])
    total = len(lib)
    cov = {
        "cases": total,
        "upstream": sum(1 for c in lib if c.get("upstream")),
        "source_session": sum(1 for c in lib if c.get("source_session")),
        "validation_record": sum(1 for c in lib if c.get("validation_record")),
        "compat": sum(1 for c in lib if c.get("compat")),
        "platforms": sum(1 for c in lib if c.get("platforms")),
        "fix_on_mismatch_step": sum(1 for c in lib if any(
            isinstance(s, dict) and s.get("fix_on_mismatch") for s in (c.get("diagnosis") or []))),
        "verification_event_ids": sum(1 for c in lib if c.get("source_session")),
    }
    rec.add("six-axis data coverage in the real library", 0, json.dumps(cov))

    # legacy flat drafts: no sources.yaml -> conditions/evidence/source unknown
    flat_root = L.fresh_clone("b-flat")
    inbox_flat = flat_root / "postmortems/inbox"
    inbox_flat.mkdir(parents=True, exist_ok=True)
    (inbox_flat / "VLLM-ASC-91001.case.yaml").write_text(F.case_text(
        case("VLLM-ASC-91001", category="precision",
             title="310P 上 qwen3-tts 推理音频为空：bf16 dtype 不受支持",
             symptoms=["音频输出全为 0", "npu-smi 显示 310P", "日志 dtype=bfloat16"])), encoding="utf-8")
    proc = __import__("subprocess").run(
        [PY, str(FINDER), "--root", str(flat_root), "--json"],
        capture_output=True, text=True, encoding="utf-8")
    flat_pairs = json.loads(proc.stdout)["pairs"] if proc.returncode == 0 else []
    target = [p for p in flat_pairs if {p["a"], p["b"]} == {"VLLM-ASC-91001", "VLLM-ASC-90001"}]
    rec.add("legacy flat draft (no sources.yaml): axes available?", 0,
            json.dumps({"nominated": bool(target), "axes": target[0]["axes"] if target else None},
                       ensure_ascii=False))

    rec.print_summary()
    print(f"\nrecord: {rec.dump()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
