#!/usr/bin/env python3
"""Prototype of the proposed `scripts/find_duplicates.py` (Checkpoint B).

Scope: candidate generation + six-axis side-by-side extraction + the five structural
contradiction hints. It never decides "duplicate"; it only nominates pairs and shows
evidence. This is a proof of concept for design validation, not product code.

Inputs (as proposed in research/2026-10-28-unified-plan.md §3.1):
  --drafts DIR        group dirs (case.yaml + sources.yaml) or legacy flat drafts
  --library DIR       knowledge/
  --changed-from REF  git ref; the added/modified case files are treated as drafts
  --json              machine-readable output

Machine work (as in §7): align six axes, nominate, flag structural contradictions.
Human work: whether it is one root cause, whether fixes/conditions can merge.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from itertools import combinations
from pathlib import Path

import yaml

# ------------------------------------------------------------------ tokenisation
ASCII = re.compile(r"[a-z0-9_][a-z0-9_.\-]{1,}")
CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
STOP = set("the and with for from that this are was were will can not you your our "
           "the a an of to in on at by is it be as or if then than into when while "
           "grep echo sed awk cat print log path file step check expected command "
           "template rank selector primary fallback all_failed coordinator".split())


def tokens(*texts) -> set[str]:
    out: set[str] = set()
    for text in texts:
        if not text:
            continue
        blob = str(text).lower()
        out |= {w for w in ASCII.findall(blob) if w not in STOP and not w.isdigit()}
        for run in CJK_RUN.findall(blob):
            out |= {run[i:i + 2] for i in range(len(run) - 1)}
    return out


def overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))       # containment: a short draft vs a long case


# ------------------------------------------------------------------ version ranges
VER = re.compile(r"(\d+)\.(\d+)\.(\d+)([a-z0-9.+]*)")


def parse_range(text: str):
    """Return (lo, lo_inc, hi, hi_inc) or None. Understands ==, >=, >, <=, <, x.y.z."""
    text = str(text).strip().strip('"').strip("'")
    if not text:
        return None
    m = VER.search(text)
    if not m:
        return None
    ver = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if text.startswith("=="):
        return ver, True, ver, True
    if text.startswith(">="):
        return ver, True, None, False
    if text.startswith(">"):
        return ver, False, None, False
    if text.startswith("<="):
        return None, False, ver, True
    if text.startswith("<"):
        return None, False, ver, False
    return ver, True, ver, True                   # bare version == that version


def intersect(a, b):
    if a is None or b is None:
        return None
    lo = max([x for x in (a[0], b[0]) if x is not None]) if (a[0] or b[0]) else None
    hi = min([x for x in (a[2], b[2]) if x is not None]) if (a[2] or b[2]) else None
    lo_inc = a[1] if a[0] == lo else b[1]
    hi_inc = a[3] if a[2] == hi else b[3]
    if lo is None or hi is None:
        return (lo, lo_inc, hi, hi_inc)
    if lo > hi:
        return None
    if lo == hi and not (lo_inc and hi_inc):
        return None
    return (lo, lo_inc, hi, hi_inc)


def ranges_of(record) -> list[tuple]:
    out = []
    for item in record.get("compat") or []:
        if isinstance(item, dict):
            for r in item.get("ranges") or []:
                pr = parse_range(r)
                if pr:
                    out.append(pr)
    return out


def conditions_relation(a, b) -> str:
    ar, br = ranges_of(a), ranges_of(b)
    if not ar or not br:
        return "unknown"
    for x in ar:
        for y in br:
            if intersect(x, y) is not None:
                return "overlap"
    return "disjoint"


def platforms_relation(a, b) -> str:
    pa, pb = set(a.get("platforms") or []), set(b.get("platforms") or [])
    if not pa or not pb:
        return "unknown"
    for x in pa:
        for y in pb:
            xs, ys = x.split("-"), y.split("-")
            if x == y or xs[:min(len(xs), len(ys))] == ys[:min(len(xs), len(ys))]:
                return "overlap"
    return "disjoint"


# ------------------------------------------------------------------ records
def load_case_file(path: Path, root: Path) -> list[dict]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return [{"_error": f"{path}: {exc}"}]
    out = []
    rel = path.relative_to(root).as_posix()
    parts = path.relative_to(root).parts
    ns = "/".join(parts[1:-2]) if len(parts) >= 4 else "/".join(parts[1:-1])
    for case in doc.get("cases") or []:
        if isinstance(case, dict):
            rec = dict(case)
            rec["_path"] = rel
            rec["_id"] = str(case.get("id") or "")
            rec["_ns"] = ns
            rec["_source"] = "library"
            out.append(rec)
    return out


def load_library(root: Path, subdir: str = "knowledge") -> list[dict]:
    kdir = root / subdir
    out = []
    for path in sorted(kdir.rglob("*.yaml")):
        if "_index" in path.parts:
            continue
        out.extend(load_case_file(path, root))
    return [r for r in out if "_error" not in r]


def load_draft_dir(path: Path, root: Path) -> list[dict]:
    case = path / "case.yaml"
    if not case.is_file():
        return []
    recs = load_case_file(case, path)
    sources = {}
    if (path / "sources.yaml").is_file():
        sources = yaml.safe_load((path / "sources.yaml").read_text(encoding="utf-8")) or {}
    out = []
    for rec in recs:
        rec["_path"] = path.name + "/case.yaml"
        cond = sources.get("conditions") or {}
        # The plan's sources.yaml has no namespace/category field: derive the
        # namespace from workload_type + framework (the only available keys).
        ns = ""
        if cond.get("framework"):
            ns = (f"{cond['workload_type']}/" if cond.get("workload_type") else "") + str(cond["framework"])
        rec["_ns"] = ns
        rec["_source"] = "draft"
        rec["_id"] = str(rec.get("id") or "")
        rec["_draft_id"] = sources.get("draft_id") or path.name
        rec["_deployment"] = (sources.get("source") or {}).get("deployment")
        rec["_sessions"] = sources.get("sessions") or []
        rec["_conditions"] = cond
        rec["_verification"] = sources.get("verification") or []
        rec["_summary"] = sources.get("semantic_summary") or {}
        if cond.get("versions"):
            version = ".".join(str(v) for v in cond["versions"].values())
            if not rec.get("compat") and cond.get("framework"):
                rec["compat"] = [{"framework": cond.get("framework", ""), "ranges": [version]}]
        if cond.get("platform") and not rec.get("platforms"):
            rec["platforms"] = [cond["platform"]]
        rec["_upstream"] = (sources.get("source") or {}).get("upstream") or rec.get("upstream")
        out.append(rec)
    return out


def load_drafts(inbox: Path) -> list[dict]:
    out = []
    if not inbox.is_dir():
        return out
    for child in sorted(inbox.iterdir()):
        if child.is_dir():
            out.extend(load_draft_dir(child, inbox))
        elif child.name.endswith(".case.yaml"):
            recs = load_case_file(child, inbox)
            for rec in recs:
                rec["_source"] = "legacy-flat"
                rec["_draft_id"] = child.name[:-len(".case.yaml")]
            out.extend(recs)
    return [r for r in out if "_error" not in r]


def load_changed(root: Path, ref: str) -> list[dict]:
    r = subprocess.run(["git", "diff", "--name-status", f"{ref}...HEAD"], cwd=root,
                       capture_output=True, text=True, encoding="utf-8")
    out = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        if not path.startswith("knowledge/") or not path.endswith(".yaml"):
            continue
        if "_index" in Path(path).parts:
            continue
        full = root / path
        if status.startswith("D") or not full.is_file():
            continue
        for rec in load_case_file(full, root):
            rec["_source"] = f"changed:{status}"
            out.append(rec)
    return out


# ------------------------------------------------------------------ candidate rules
def upstream_of(rec):
    up = rec.get("_upstream") or rec.get("upstream")
    items = up if isinstance(up, list) else ([up] if isinstance(up, dict) else [])
    out = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("repo") and item.get("issue"):
            out.add((str(item["repo"]), "issue", str(item["issue"])))
        if item.get("repo") and item.get("pr"):
            out.add((str(item["repo"]), "pr", str(item["pr"])))
    return out


def qc_of(rec):
    qc = rec.get("quickly_check") or {}
    branches = {}
    for name, branch in qc.items():
        if isinstance(branch, dict):
            branches[name] = {"command": str(branch.get("command_template") or ""),
                              "expected": str(branch.get("expected") or ""),
                              "selector": str(branch.get("rank_selector") or "")}
    return branches


def expected_norm(rec) -> set[str]:
    qc = qc_of(rec)
    primary = qc.get("primary") or {}
    e = primary.get("expected") or ""
    e = e[len("regex:"):] if e.startswith("regex:") else e
    return tokens(e)


def text_of(rec) -> set[str]:
    return tokens(rec.get("title"), " ".join(str(x) for x in (rec.get("tags") or [])),
                  " ".join(str(x) for x in (rec.get("symptoms") or [])))


CODE = re.compile(r"\b[A-Z]{2,}[A-Z0-9_]*\d{3,}\b")
OP = re.compile(r"\b[a-z0-9_]+\.(?:py|cpp|cc|h)\b")


def strong_tokens(rec) -> set[str]:
    blob = " ".join(str(x) for x in [
        rec.get("title"), " ".join(rec.get("symptoms") or []),
        rec.get("root_cause"), rec.get("fix")])
    return set(CODE.findall(blob)) | set(OP.findall(blob))


def root_tokens(rec) -> set[str]:
    summary = rec.get("_summary") or {}
    return tokens(summary.get("root_cause") or rec.get("root_cause"))


def fix_tokens(rec) -> set[str]:
    summary = rec.get("_summary") or {}
    return tokens(summary.get("fix") or rec.get("fix"))


def sessions_of(rec) -> set[str]:
    out = set(rec.get("_sessions") or [])
    if rec.get("source_session"):
        out.add(str(rec["source_session"]))
    for v in rec.get("_verification") or []:
        if isinstance(v, dict) and v.get("ref"):
            out.add(str(v["ref"]))
    return out


def verification_events(rec) -> set[str]:
    return {str(v.get("ref")) for v in (rec.get("_verification") or [])
            if isinstance(v, dict) and v.get("ref")}


def candidate_reasons(a, b, score: float) -> list[str]:
    reasons = []
    if a.get("_id") and a.get("_id") == b.get("_id"):
        reasons.append("same-id")
    if a.get("_path") and a.get("_path") == b.get("_path"):
        reasons.append("same-path")
    if upstream_of(a) & upstream_of(b):
        reasons.append("shared-upstream")
    if a.get("_source") == "library" and b.get("_source") == "library":
        return reasons
    cell_a = (a.get("_ns") or "", a.get("category"))
    cell_b = (b.get("_ns") or "", b.get("category"))
    if cell_a == cell_b and score >= 0.28:
        reasons.append("same-cell-overlap")
    elif cell_a[0] and cell_a[0] == cell_b[0] and cell_a[1] != cell_b[1] and score >= 0.20:
        reasons.append("same-namespace-cross-category")
    if strong_tokens(a) & strong_tokens(b):
        reasons.append("shared-strong-keyword")
    if not reasons and score >= 0.34:
        reasons.append("whole-library-keyword")
    return reasons


def axis_report(a, b) -> dict:
    up_a, up_b = upstream_of(a), upstream_of(b)
    if up_a and up_b:
        source = "same" if up_a & up_b else "different"
    else:
        source = "unknown"
    sess_a, sess_b = sessions_of(a), sessions_of(b)
    ev_a, ev_b = verification_events(a), verification_events(b)
    if ev_a and ev_b:
        evidence = "same" if ev_a & ev_b else "different"
    elif sess_a and sess_b:
        evidence = "same" if sess_a & sess_b else "different"
    else:
        evidence = "unknown"
    ea, eb = expected_norm(a), expected_norm(b)
    if ea and eb:
        discriminator = "same" if ea == eb else (
            "partial" if ea & eb else "different")
    else:
        discriminator = "unknown"
    cond = conditions_relation(a, b)
    plat = platforms_relation(a, b)
    if cond == "disjoint" or plat == "disjoint":
        conditions = "disjoint"
    elif cond == "overlap" and plat in ("overlap", "unknown"):
        conditions = "overlap"
    else:
        conditions = "unknown"
    return {
        "source": source,
        "root_cause": "needs-human-read",
        "discriminator": discriminator,
        "fix": "needs-human-read",
        "conditions": conditions,
        "evidence": evidence,
        "_detail": {"compat": cond, "platforms": plat,
                    "upstream_a": sorted(up_a), "upstream_b": sorted(up_b),
                    "sessions_a": sorted(sess_a), "sessions_b": sorted(sess_b)},
    }


def contradiction_hints(a, b) -> list[str]:
    hints = []
    ea, eb = expected_norm(a), expected_norm(b)
    fa, fb = fix_tokens(a), fix_tokens(b)
    if ea and eb and ea == eb and fa and fb and overlap(fa, fb) < 0.25:
        hints.append("same-check-two-fixes：同一期望值、修复词重合低，需要确认")
    ar, br = ranges_of(a), ranges_of(b)
    for rec in (a, b):
        for step in rec.get("diagnosis") or []:
            if not isinstance(step, dict):
                continue
            fix = str(step.get("fix_on_mismatch") or "")
            m = VER.search(fix)
            if not m:
                continue
            ver = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            for rng in ar + br:
                if intersect(rng, (ver, True, ver, True)):
                    hints.append("affected-version-vs-fix-version：fix_on_mismatch 提到的版本"
                                 f" {'.'.join(map(str, ver))} 落在受影响区间内")
                    break
    sa, sb = sessions_of(a), sessions_of(b)
    if sa and sb and sa & sb:
        hints.append("same-session-two-cases：同一 session 被两处引用，确认是否重复结算")
    ua, ub = upstream_of(a), upstream_of(b)
    if ua & ub and overlap(root_tokens(a), root_tokens(b)) < 0.25:
        hints.append("same-issue-different-root-cause：同一 issue 根因词重合低，可能含多个问题")
    ta, tb = text_of(a), text_of(b)
    if ta and tb and overlap(ta, tb) >= 0.45 and conditions_relation(a, b) == "disjoint":
        hints.append("same-symptom-disjoint-ranges：同现象、版本区间不相交，确认一条还是两条")
    return sorted(set(hints))


def pair_key(a, b):
    x, y = a.get("_id") or "?", b.get("_id") or "?"
    return tuple(sorted((x, y))) + tuple(sorted((a.get("_path") or "", b.get("_path") or "")))


def build_pairs(records, library, limit: int):
    nominated = {}
    for a in records:
        for b in library:
            if a is b:
                continue
            if a.get("_id") and a.get("_id") == b.get("_id") and a.get("_path") == b.get("_path"):
                continue                      # a record compared with itself
            if a.get("_source") == "library" and b.get("_source") == "library":
                continue
            score = overlap(text_of(a), text_of(b))
            reasons = candidate_reasons(a, b, score)
            if not reasons:
                continue
            key = pair_key(a, b)
            if key in nominated:
                nominated[key]["reasons"] |= set(reasons)
                continue
            nominated[key] = {"a": a, "b": b, "score": round(score, 3),
                              "reasons": set(reasons)}
    # draft-vs-draft (batch-internal comparison the design requires)
    drafts = [r for r in records if r.get("_source") != "library"]
    for a, b in combinations(drafts, 2):
        score = overlap(text_of(a), text_of(b))
        reasons = candidate_reasons(a, b, score)
        if not reasons:
            continue
        key = pair_key(a, b)
        if key in nominated:
            nominated[key]["reasons"] |= set(reasons)
        else:
            nominated[key] = {"a": a, "b": b, "score": round(score, 3),
                              "reasons": set(reasons)}
    ordered = sorted(nominated.values(),
                     key=lambda p: (-(bool({"shared-upstream", "same-id", "same-path"} & p["reasons"])),
                                    -p["score"]))
    always = [p for p in ordered if p["reasons"] & {"shared-upstream", "same-id", "same-path"}]
    scored = [p for p in ordered if p not in always]
    if limit <= 0:
        shown = always + scored
    else:
        shown = always + scored[:limit]
    return shown, len(ordered) - len(shown)


def render(pairs, dropped: int, library: list[dict], drafts: list[dict]) -> str:
    lines = [f"# 候选对报告（原型）",
             f"库内 case {len(library)} 条；本次输入 {len(drafts)} 条；"
             f"展示 {len(pairs)} 对；未展示 {dropped} 对（分数低于阈值或超出展示上限）",
             "相似度只用于排序与提名，不是判定。根因与修复需要人读。", ""]
    for p in pairs:
        a, b = p["a"], p["b"]
        axes = axis_report(a, b)
        hints = contradiction_hints(a, b)
        lines.append(f"对：{a.get('_draft_id') or a.get('_id')} ↔ {b.get('_draft_id') or b.get('_id')}")
        lines.append(f"  关联理由：{', '.join(sorted(p['reasons']))}；症状重合 {p['score']}")
        lines.append(f"  来源：{axes['source']}；判别：{axes['discriminator']}；"
                     f"条件：{axes['conditions']}；证据：{axes['evidence']}")
        lines.append(f"  根因：需要人读")
        lines.append(f"    A：{str(a.get('root_cause') or (a.get('_summary') or {}).get('root_cause'))[:160]}")
        lines.append(f"    B：{str(b.get('root_cause') or (b.get('_summary') or {}).get('root_cause'))[:160]}")
        ax = qc_of(a).get("primary", {}).get("expected", "")
        bx = qc_of(b).get("primary", {}).get("expected", "")
        lines.append(f"  判别式 A/B：{ax[:80]} | {bx[:80]}")
        lines.append(f"  修复 A/B：{str(a.get('fix') or '')[:90]} | {str(b.get('fix') or '')[:90]}")
        if hints:
            lines.append("  矛盾提示：" + "；".join(hints))
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="原型：重复候选发现（Checkpoint B）")
    ap.add_argument("--root", type=Path, required=True, help="仓库根（决定 knowledge/ 与 inbox 的位置）")
    ap.add_argument("--drafts", default="postmortems/inbox")
    ap.add_argument("--library", default="knowledge")
    ap.add_argument("--changed-from", default=None)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    library = load_library(root, args.library)
    drafts = []
    if args.changed_from:
        drafts = load_changed(root, args.changed_from)
    else:
        inbox = Path(args.drafts)
        drafts = load_drafts(inbox if inbox.is_absolute() else root / inbox)
    pairs, dropped = build_pairs(drafts, library, args.limit)

    if args.json:
        payload = []
        for p in pairs:
            a, b = p["a"], p["b"]
            payload.append({
                "a": a.get("_draft_id") or a.get("_id"),
                "b": b.get("_draft_id") or b.get("_id"),
                "a_case_id": a.get("_id"),
                "b_case_id": b.get("_id"),
                "score": p["score"],
                "reasons": sorted(p["reasons"]),
                "axes": {k: v for k, v in axis_report(a, b).items() if not k.startswith("_")},
                "hints": contradiction_hints(a, b),
            })
        print(json.dumps({"pairs": payload, "unshown": dropped,
                          "library_cases": len(library), "inputs": len(drafts)},
                         ensure_ascii=False, indent=2))
        return 0
    print(render(pairs, dropped, library, drafts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
