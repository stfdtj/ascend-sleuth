"""Targeted design experiment for Checkpoint B v2 (2026-10-29).

Question it settles: if candidate generation adds field-level signals (root cause,
fix, discriminator identity, verification events) and splits results into
mandatory/high/low tiers, does the labelled D1-D11 set get generated *and displayed*
without exploding the review workload?

It reuses the already-labelled `b-lab` (11 drafts vs the seeded 173-case library) and
the v1 prototype's loaders. It does not modify the lab or the repository.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "proto"))
import find_duplicates as FD  # noqa: E402

LAB = Path(r"D:\working\asv\b-lab")
OUT = HERE.parent / "logs" / "checkpoint-b-v2.json"
HIGH_PER_DRAFT = 5
LOW_PER_DRAFT = 2
LOW_GLOBAL = 10


def field_signals(a, b):
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


def strong_discriminator(a, b, sig):
    """Same full expected AND a shared distinctive literal (or nearly identical command).

    The raw expected set is not enough: generic checks such as `regex:^[1-9]` are shared
    by many unrelated cases. Reuse `build_index.sig_literals` semantics.
    """
    if not sig["same_expected"]:
        return False
    la = {x for x in _sig_literals(a) if len(x) >= 6}
    lb = {x for x in _sig_literals(b) if len(x) >= 6}
    if la & lb:
        return True
    ca = FD.qc_of(a).get("primary", {}).get("command", "")
    cb = FD.qc_of(b).get("primary", {}).get("command", "")
    ta, tb = FD.tokens(ca), FD.tokens(cb)
    return bool(ta and tb and FD.overlap(ta, tb) >= 0.6)


def _sig_literals(rec):
    import re
    out = []
    for group in (rec.get("quickly_check") or {}).values():
        exp = str((group or {}).get("expected") or "")
        if not exp.startswith("regex:"):
            continue
        for alt in exp[len("regex:"):].split("|"):
            alt = alt.strip()
            if re.fullmatch(r"[\w.\- ]{5,32}", alt):
                out.append(alt)
    return out


def tier_of(a, b, sig, score):
    same_ns = bool(a.get("_ns")) and a.get("_ns") == b.get("_ns")
    cross_cat = same_ns and a.get("category") != b.get("category")
    cross_ns = bool(a.get("_ns")) and bool(b.get("_ns")) and a.get("_ns") != b.get("_ns")
    strong = bool(FD.strong_tokens(a) & FD.strong_tokens(b))
    cond = FD.conditions_relation(a, b)
    hard_contradiction = bool(FD.contradiction_hints(a, b))
    # class 1 (blocking decision): identity-level signals
    if (sig["shared_upstream"] or sig["same_id"] or sig["same_path"] or sig["same_event"]
            or strong_discriminator(a, b, sig)):
        return "mandatory"
    if sig["same_session"]:
        return "high"
    # class 2 (must display; overflow needs an explicit per-draft ack)
    if cross_cat and score >= 0.20:
        return "high"
    if not cross_ns and score >= 0.28:
        return "high"
    if sig["root_overlap"] >= 0.5 and sig["root_tokens"] >= 3:
        return "high"
    if sig["fix_overlap"] >= 0.5 and sig["fix_tokens"] >= 3:
        return "high"
    if hard_contradiction:
        return "high"
    if cross_ns and (not a.get("_ns") or not b.get("_ns") or strong):
        return "high"
    if cond == "overlap" and score >= 0.20:
        return "high"
    # class 3: low-value lexical
    if (score >= 0.30 or strong or sig["root_overlap"] >= 0.25
            or sig["fix_overlap"] >= 0.25):
        return "low"
    return None


def why(a, b, sig, score):
    reasons = []
    if sig["shared_upstream"]:
        reasons.append("shared-upstream")
    if sig["same_id"]:
        reasons.append("same-id")
    if sig["same_path"]:
        reasons.append("same-path")
    if sig["same_event"]:
        reasons.append("same-event")
    if sig["same_expected"]:
        reasons.append("same-expected")
    if sig["root_overlap"] >= 0.5:
        reasons.append(f"root-overlap={sig['root_overlap']}")
    if sig["fix_overlap"] >= 0.5:
        reasons.append(f"fix-overlap={sig['fix_overlap']}")
    if sig["same_session"]:
        reasons.append("same-session")
    if score >= 0.2:
        reasons.append(f"lexical={score}")
    return reasons


def main():
    lib = FD.load_library(LAB)
    drafts = [d for d in FD.load_drafts(LAB / "postmortems/inbox")
              if (d.get("_id") or "").startswith("VLLM-ASC-91") and d.get("_id") != "VLLM-ASC-91099"]
    pairs = []
    for a in drafts:
        for b in lib:
            if a.get("_id") == b.get("_id") and a.get("_path") == b.get("_path"):
                continue
            score = FD.overlap(FD.text_of(a), FD.text_of(b))
            sig = field_signals(a, b)
            tier = tier_of(a, b, sig, score)
            if tier is None:
                continue
            pairs.append({"draft": a["_id"], "case": b["_id"], "tier": tier,
                          "score": round(score, 3), "signals": sig,
                          "cross_cat": bool(a.get("_ns")) and a.get("_ns") == b.get("_ns")
                          and a.get("category") != b.get("category"),
                          "reasons": why(a, b, sig, score),
                          "hints": FD.contradiction_hints(a, b)})
    # Class 2 is the *core* set only. A weak lexical high is demoted to low: it is
    # printed as an optional watchlist, never as a pair that was reviewed.
    def is_core(p):
        s = p["signals"]
        return (
            (s["root_overlap"] >= 0.6 and s["root_tokens"] >= 4)
            or (s["fix_overlap"] >= 0.6 and s["fix_tokens"] >= 4)
            or (s["same_session"])
            or (p["score"] >= 0.45 and (s["root_overlap"] >= 0.5 or s["fix_overlap"] >= 0.5))
            or (p.get("cross_cat") and p["score"] >= 0.45)
        )

    for p in pairs:
        if p["tier"] == "high" and not is_core(p):
            p["tier"] = "low"

    displayed = set()
    for draft in sorted({p["draft"] for p in pairs}):
        rows = [p for p in pairs if p["draft"] == draft]
        mandatory = [p for p in rows if p["tier"] == "mandatory"]
        core = [p for p in rows if p["tier"] == "high"]
        low = sorted([p for p in rows if p["tier"] == "low"],
                     key=lambda p: (-bool(p["hints"]), -p["score"]))
        for p in mandatory + core:
            displayed.add((p["draft"], p["case"]))
        for p in low[:LOW_PER_DRAFT]:
            displayed.add((p["draft"], p["case"]))
    # global low cap: drop extra low-only rows beyond LOW_GLOBAL
    low_disp = [p for p in pairs if p["tier"] == "low" and (p["draft"], p["case"]) in displayed]
    for p in low_disp[LOW_GLOBAL:]:
        displayed.discard((p["draft"], p["case"]))

    targets = {
        "D1 cross-category": ("VLLM-ASC-91001", "VLLM-ASC-90001"),
        "D2 paraphrase": ("VLLM-ASC-91002", "VLLM-ASC-90001"),
        "D3 same signature diff root": ("VLLM-ASC-91003", "VLLM-ASC-90001"),
        "D4/D5 same upstream": ("VLLM-ASC-91004", "VLLM-ASC-91005"),
        "D6 same fix diff version": ("VLLM-ASC-91006", "VLLM-ASC-90001"),
        "D7 overlapping conditions": ("VLLM-ASC-91007", "VLLM-ASC-90001"),
        "D8 contradictory fix": ("VLLM-ASC-91008", "VLLM-ASC-90001"),
        "D9 shared evidence": ("VLLM-ASC-91009", "VLLM-ASC-90001"),
        "D10 different sessions": ("VLLM-ASC-91010", "VLLM-ASC-90001"),
        "D11 unrelated": ("VLLM-ASC-91011", "VLLM-ASC-90001"),
    }
    result = {}
    for name, (a, b) in targets.items():
        hit = next((p for p in pairs if {p["draft"], p["case"]} == {a, b}), None)
        result[name] = {
            "generated": bool(hit),
            "tier": hit["tier"] if hit else None,
            "displayed": bool(hit and (hit["draft"], hit["case"]) in displayed),
            "reasons": hit["reasons"] if hit else [],
            "hints": hit["hints"] if hit else [],
        }
    # draft-draft pair D4/D5 is not in draft-vs-library; add it
    d4 = next(d for d in drafts if d["_id"] == "VLLM-ASC-91004")
    d5 = next(d for d in drafts if d["_id"] == "VLLM-ASC-91005")
    score = FD.overlap(FD.text_of(d4), FD.text_of(d5))
    sig = field_signals(d4, d5)
    tier = tier_of(d4, d5, sig, score) or "none"
    result["D4/D5 same upstream (draft-draft)"] = {
        "generated": tier != "none", "tier": tier, "displayed": tier in ("mandatory", "high"),
        "reasons": why(d4, d5, sig, score),
        "hints": FD.contradiction_hints(d4, d5),
    }
    counts = {
        "drafts": len(drafts), "library": len(lib),
        "generated": len(pairs),
        "mandatory": sum(1 for p in pairs if p["tier"] == "mandatory"),
        "high": sum(1 for p in pairs if p["tier"] == "high"),
        "low": sum(1 for p in pairs if p["tier"] == "low"),
        "displayed": len(displayed),
        "hidden_high": sum(1 for p in pairs if p["tier"] == "high"
                           and (p["draft"], p["case"]) not in displayed),
        "hidden_low": sum(1 for p in pairs if p["tier"] == "low"
                          and (p["draft"], p["case"]) not in displayed),
    }
    payload = {"targets": result, "counts": counts,
               "pairs": sorted(pairs, key=lambda p: (p["tier"], p["draft"], p["case"]))}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"targets": result, "counts": counts}, ensure_ascii=False, indent=2))
    print(f"\nrecord: {OUT}")


if __name__ == "__main__":
    main()
