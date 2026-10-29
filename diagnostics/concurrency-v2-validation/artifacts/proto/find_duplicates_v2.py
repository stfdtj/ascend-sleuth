#!/usr/bin/env python3
"""V2 Checkpoint B prototype: candidate generation + tiered display + decision file.

Uses the validated extraction helpers from the first validation (`find_duplicates.py`)
but implements the V2 tiering/presentation contract. Drafts are read through the V2
reader; incomplete/corrupt drafts are not inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import draft_queue as DQ  # noqa: E402

OLD_PROTO = Path(r"D:\working\ascend-sleuth\diagnostics\concurrency-validation\artifacts\proto")
sys.path.insert(0, str(OLD_PROTO))
import find_duplicates as FD  # noqa: E402

HIGH_CAP = 30
LOW_PER_DRAFT = 2
LOW_GLOBAL = 10


def load_library(root: Path) -> list[dict]:
    return FD.load_library(root)


def load_v2_drafts(root: Path) -> list[dict]:
    inbox = root / "postmortems" / "inbox"
    scan = DQ.scan(inbox)
    complete = {r["draft_id"] for r in scan["drafts"] if r["state"] == "complete"}
    loaded = FD.load_drafts(inbox)
    out = []
    for rec in loaded:
        if rec.get("_draft_id") in complete:
            rec["_v2_state"] = "complete"
            out.append(rec)
    # legacy flat drafts remain supported, marked as legacy
    legacy_names = {n[:-len(".case.yaml")] for n in scan.get("legacy_flat_files", [])}
    for rec in loaded:
        if rec.get("_draft_id") in legacy_names:
            rec["_v2_state"] = "legacy_flat"
            out.append(rec)
    return out


def stable_pair_id(draft_id: str, case_id: str) -> str:
    return hashlib.sha1(f"{draft_id}:{case_id}".encode("utf-8")).hexdigest()[:16]


def sig(rec) -> dict:
    return {
        "root_overlap": FD.overlap(FD.root_tokens(rec), FD.root_tokens(rec)),
    }


def pair_signals(a, b) -> dict:
    ra, rb = FD.root_tokens(a), FD.root_tokens(b)
    fa, fb = FD.fix_tokens(a), FD.fix_tokens(b)
    ea, eb = FD.expected_norm(a), FD.expected_norm(b)
    return {
        "root_overlap": round(FD.overlap(ra, rb), 3),
        "fix_overlap": round(FD.overlap(fa, fb), 3),
        "root_tokens": min(len(ra), len(rb)),
        "fix_tokens": min(len(fa), len(fb)),
        "same_expected": bool(ea and eb and ea == eb),
        "same_session": bool(FD.sessions_of(a) & FD.sessions_of(b)),
        "same_event": bool(FD.verification_events(a) & FD.verification_events(b)),
        "shared_upstream": bool(FD.upstream_of(a) & FD.upstream_of(b)),
        "same_id": bool(a.get("_id") and a.get("_id") == b.get("_id")),
        "same_path": bool(a.get("_path") and a.get("_path") == b.get("_path")),
    }


def sig_literals(rec) -> set[str]:
    out = set()
    for group in (rec.get("quickly_check") or {}).values():
        exp = str((group or {}).get("expected") or "")
        if not exp.startswith("regex:"):
            continue
        for alt in exp[len("regex:"):].split("|"):
            alt = alt.strip()
            if 6 <= len(alt) <= 32 and all(c.isalnum() or c in "._- " for c in alt):
                out.add(alt)
    return out


def strong_discriminator(a, b, s) -> bool:
    if not s["same_expected"]:
        return False
    if sig_literals(a) & sig_literals(b):
        return True
    ta = FD.tokens(FD.qc_of(a).get("primary", {}).get("command", ""))
    tb = FD.tokens(FD.qc_of(b).get("primary", {}).get("command", ""))
    return bool(ta and tb and FD.overlap(ta, tb) >= 0.6)


def is_core(p) -> bool:
    s = p["signals"]
    return ((s["root_overlap"] >= 0.6 and s["root_tokens"] >= 4)
            or (s["fix_overlap"] >= 0.6 and s["fix_tokens"] >= 4)
            or s["same_session"]
            or (p["score"] >= 0.45 and (s["root_overlap"] >= 0.5 or s["fix_overlap"] >= 0.5))
            or (p.get("cross_cat") and p["score"] >= 0.45))


def tier_of(a, b, s, score) -> str | None:
    same_ns = bool(a.get("_ns")) and a.get("_ns") == b.get("_ns")
    cross_cat = same_ns and a.get("category") != b.get("category")
    cross_ns = bool(a.get("_ns")) and bool(b.get("_ns")) and a.get("_ns") != b.get("_ns")
    strong = bool(FD.strong_tokens(a) & FD.strong_tokens(b))
    cond = FD.conditions_relation(a, b)
    if (s["shared_upstream"] or s["same_id"] or s["same_path"] or s["same_event"]
            or strong_discriminator(a, b, s)):
        return "mandatory"
    if cross_cat and score >= 0.20:
        return "high"
    if not cross_ns and score >= 0.28:
        return "high"
    if s["root_overlap"] >= 0.5 and s["root_tokens"] >= 3:
        return "high"
    if s["fix_overlap"] >= 0.5 and s["fix_tokens"] >= 3:
        return "high"
    if cross_ns and (not a.get("_ns") or not b.get("_ns") or strong):
        return "high"
    if s["same_session"]:
        return "high"
    if cond == "overlap" and score >= 0.20:
        return "high"
    if FD.contradiction_hints(a, b) and score >= 0.20:
        return "high"
    if score >= 0.30 or strong or s["root_overlap"] >= 0.25 or s["fix_overlap"] >= 0.25:
        return "low"
    return None


def compare(drafts, library) -> list[dict]:
    pairs = []
    for a in drafts:
        for b in library:
            if a.get("_id") == b.get("_id") and a.get("_path") == b.get("_path"):
                continue
            score = FD.overlap(FD.text_of(a), FD.text_of(b))
            s = pair_signals(a, b)
            tier = tier_of(a, b, s, score)
            if tier is None:
                continue
            same_ns = bool(a.get("_ns")) and a.get("_ns") == b.get("_ns")
            pairs.append({
                "pair_id": stable_pair_id(a["_draft_id"], b["_id"]),
                "draft": a["_draft_id"], "draft_case": a["_id"], "case": b["_id"],
                "tier": tier,
                "score": round(score, 3), "signals": s,
                "cross_cat": same_ns and a.get("category") != b.get("category"),
                "reasons": [],
                "hints": FD.contradiction_hints(a, b),
            })
    # draft-vs-draft
    for i, a in enumerate(drafts):
        for b in drafts[i + 1:]:
            score = FD.overlap(FD.text_of(a), FD.text_of(b))
            s = pair_signals(a, b)
            tier = tier_of(a, b, s, score)
            if tier is None:
                continue
            pairs.append({
                "pair_id": stable_pair_id(a["_draft_id"], b["_id"]),
                "draft": a["_draft_id"], "draft_case": a["_id"], "case": b["_id"],
                "other_uuid": b["_draft_id"], "tier": tier,
                "score": round(score, 3), "signals": s,
                "cross_cat": False, "reasons": [],
                "hints": FD.contradiction_hints(a, b),
            })
    for p in pairs:
        p["tier"] = p["tier"] if p["tier"] != "high" or is_core(p) else "low"
    return pairs


def display(pairs, high_cap=HIGH_CAP, low_per=LOW_PER_DRAFT, low_global=LOW_GLOBAL):
    shown = set()
    mandatory = [p for p in pairs if p["tier"] == "mandatory"]
    high = [p for p in pairs if p["tier"] == "high"]
    low = [p for p in pairs if p["tier"] == "low"]
    for p in mandatory:
        shown.add(p["pair_id"])
    high_sorted = sorted(high, key=lambda p: (-bool(p["hints"]),
                                              -p["signals"]["root_overlap"],
                                              -p["signals"]["fix_overlap"],
                                              -p["score"], p["pair_id"]))
    for p in high_sorted[:high_cap]:
        shown.add(p["pair_id"])
    low_by_draft = {}
    for p in low:
        low_by_draft.setdefault(p["draft"], []).append(p)
    low_rows = []
    for draft, rows in low_by_draft.items():
        low_rows += sorted(rows, key=lambda p: (-p["score"], p["pair_id"]))[:low_per]
    for p in low_rows[:low_global]:
        shown.add(p["pair_id"])
    hidden_high, hidden_low = {}, {}
    for p in high:
        if p["pair_id"] not in shown:
            hidden_high[p["draft"]] = hidden_high.get(p["draft"], 0) + 1
    for p in low:
        if p["pair_id"] not in shown:
            hidden_low[p["draft"]] = hidden_low.get(p["draft"], 0) + 1
    return shown, hidden_high, hidden_low


def report(pairs, shown, hidden_high, hidden_low) -> str:
    out = ["# V2 candidate report", ""]
    for p in pairs:
        if p["pair_id"] not in shown:
            continue
        out.append(f"{p['tier']:9} {p['draft']} <-> {p['case']}  score={p['score']}  "
                   f"root={p['signals']['root_overlap']} fix={p['signals']['fix_overlap']}")
        if p["hints"]:
            out.append("         hints: " + "；".join(p["hints"]))
    out.append("")
    out.append(f"hidden_high={sum(hidden_high.values())} hidden_low={sum(hidden_low.values())}")
    return "\n".join(out)


def decision_skeleton(case_id, pairs, shown, main_sha, head_sha) -> dict:
    return {
        "case_id": case_id,
        "decision": "TODO",
        "main_sha": main_sha,
        "head_sha": head_sha,
        "tool_version": "v2-prototype",
        "pairs": [{"pair_id": p["pair_id"], "other": p["case"], "tier": p["tier"],
                   "signals": [k for k, v in p["signals"].items() if v],
                   "decision": "TODO", "note": ""}
                  for p in pairs if p["pair_id"] in shown and p["tier"] in ("mandatory", "high")],
        "overflow": {"hidden_high": 0, "ack": None},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V2 Checkpoint B prototype")
    ap.add_argument("--root", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--high-cap", type=int, default=HIGH_CAP)
    ap.add_argument("--low-per-draft", type=int, default=LOW_PER_DRAFT)
    ap.add_argument("--low-global", type=int, default=LOW_GLOBAL)
    ap.add_argument("--decision", default=None, help="write a decision skeleton for this case id")
    ap.add_argument("--decision-case", default="UNKNOWN")
    ap.add_argument("--main-sha", default="UNKNOWN")
    ap.add_argument("--head-sha", default="UNKNOWN")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    library = load_library(root)
    drafts = load_v2_drafts(root)
    pairs = compare(drafts, library)
    shown, hidden_high, hidden_low = display(pairs, args.high_cap, args.low_per_draft, args.low_global)
    if args.json:
        payload = {
            "pairs": [p for p in pairs if p["pair_id"] in shown],
            "counts": {
                "drafts": len(drafts), "library": len(library), "generated": len(pairs),
                "mandatory": sum(1 for p in pairs if p["tier"] == "mandatory"),
                "high": sum(1 for p in pairs if p["tier"] == "high"),
                "low": sum(1 for p in pairs if p["tier"] == "low"),
                "displayed": len(shown),
                "hidden_high": sum(hidden_high.values()),
                "hidden_low": sum(hidden_low.values()),
            },
            "hidden_high_by_draft": hidden_high,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(report(pairs, shown, hidden_high, hidden_low))
    if args.decision:
        target = Path(args.decision)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(
            decision_skeleton(args.decision_case or "UNKNOWN", pairs, shown,
                              args.main_sha, args.head_sha),
            allow_unicode=True, sort_keys=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
