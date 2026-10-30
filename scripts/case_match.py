#!/usr/bin/env python3
"""case_match.py — the one comparator used by Checkpoint B and Checkpoint C.

This is deliberately lexical/structural, not embedding-based. It nominates candidate
pairs and labels them mandatory/high/low; it never decides that two cases are the same
problem. The human decision is recorded in `postmortems/decisions/<case-id>.yaml`.

The module is importable: `find_duplicates.py` and `merge_recheck.py` both call
`compare()`, so there is no second duplicate-detection implementation.
"""
from __future__ import annotations

import hashlib
import re
from itertools import combinations
from pathlib import Path

import yaml

ASCII = re.compile(r"[a-z0-9_][a-z0-9_.\-]{1,}")
CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
STOP = set("the and with for from that this are was were will can not you your our "
           "a an of to in on at by is it be as or if then than into when while "
           "grep echo sed awk cat print log path file step check expected command "
           "template rank selector primary fallback all_failed coordinator".split())
VER = re.compile(r"(\d+)\.(\d+)\.(\d+)([a-z0-9.+]*)")
CODE = re.compile(r"\b[A-Z]{2,}[A-Z0-9_]*\d{3,}\b")
OP = re.compile(r"\b[a-z0-9_]+\.(?:py|cpp|cc|h)\b")
HIGH_CAP = 30
LOW_PER_DRAFT = 2
LOW_GLOBAL = 10


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
    return len(a & b) / min(len(a), len(b))


def parse_range(text: str):
    text = str(text).strip().strip('"').strip("'")
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
    return ver, True, ver, True


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


def ranges_of(rec) -> list[tuple]:
    out = []
    for item in rec.get("compat") or []:
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
    return "overlap" if any(intersect(x, y) is not None for x in ar for y in br) else "disjoint"


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


def _first(case: dict) -> dict:
    cases = case.get("cases") if isinstance(case, dict) else None
    return cases[0] if isinstance(cases, list) and cases and isinstance(cases[0], dict) else {}


def _records_from_doc(doc: dict, path: str, ns: str, source: str) -> list[dict]:
    out = []
    for case in doc.get("cases") or []:
        if not isinstance(case, dict):
            continue
        rec = dict(case)
        rec["_id"] = str(case.get("id") or "")
        rec["_path"] = path
        rec["_ns"] = ns
        rec["_source"] = source
        out.append(rec)
    return out


def load_library(root: Path, subdir: str = "knowledge") -> list[dict]:
    out = []
    for path in sorted((root / subdir).rglob("*.yaml")):
        if "_index" in path.parts or "_archive" in path.parts:
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        rel = path.relative_to(root)
        parts = rel.parts
        ns = "/".join(parts[1:-2]) if len(parts) >= 4 else "/".join(parts[1:-1])
        out.extend(_records_from_doc(doc, rel.as_posix(), ns, "library"))
    return [r for r in out if r["_id"]]


def _draft_record(case: dict, sources: dict, path: str, draft_id: str, source: str,
                  namespace: str | None) -> dict:
    rec = dict(case)
    rec["_id"] = str(case.get("id") or "")
    rec["_path"] = path
    rec["_source"] = source
    rec["_draft_id"] = draft_id
    cond = sources.get("conditions") or {}
    ns = namespace or ""
    if not ns and cond.get("framework"):
        ns = (f"{cond.get('workload_type')}/" if cond.get("workload_type") else "") + str(cond["framework"])
    rec["_ns"] = ns
    rec["_deployment"] = (sources.get("source") or {}).get("deployment_id")
    rec["_sessions"] = list(sources.get("sessions") or [])
    rec["_verification"] = list(sources.get("verification") or [])
    rec["_summary"] = sources.get("semantic_summary") or {}
    rec["_upstream"] = (sources.get("source") or {}).get("upstream") or rec.get("upstream")
    if cond.get("versions") and not rec.get("compat") and cond.get("framework"):
        rec["compat"] = [{"framework": cond["framework"],
                          "ranges": [".".join(str(v) for v in cond["versions"].values())]}]
    if cond.get("platform") and not rec.get("platforms"):
        rec["platforms"] = [cond["platform"]]
    return rec


def load_drafts(root: Path, inbox: Path, namespace: str | None = None) -> list[dict]:
    from draft_queue import read_draft, read_flat, scan

    out = []
    for row in scan(inbox)["drafts"]:
        if row["state"] not in ("complete", "legacy_flat"):
            continue
        if row["state"] == "complete":
            path = Path(row["path"]) / "case.yaml"
            try:
                case = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                sources = yaml.safe_load((Path(row["path"]) / "sources.yaml").read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            recs = _records_from_doc(case, f"{row['draft_id']}/case.yaml", "", "draft")
            for rec in recs:
                out.append(_draft_record(rec, sources, rec["_path"], row["draft_id"], "draft", namespace))
        else:
            path = Path(row["path"])
            try:
                case = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            recs = _records_from_doc(case, path.name, "", "legacy-flat")
            for rec in recs:
                out.append(_draft_record(rec, {}, rec["_path"], row["draft_id"], "legacy-flat", namespace))
    return [r for r in out if r["_id"]]


def load_changed(root: Path, base: str, head: str = "HEAD") -> list[dict]:
    import subprocess

    p = subprocess.run(["git", "diff", "--name-status", f"{base}...{head}"], cwd=root,
                       capture_output=True, text=True, encoding="utf-8")
    out = []
    for line in p.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        if not path.startswith("knowledge/") or not path.endswith(".yaml"):
            continue
        if "_index" in Path(path).parts or status.startswith("D"):
            continue
        shown = subprocess.run(["git", "show", f"{head}:{path}"], cwd=root,
                               capture_output=True, text=True, encoding="utf-8")
        if shown.returncode != 0:
            continue
        try:
            doc = yaml.safe_load(shown.stdout) or {}
        except Exception:
            continue
        rel = Path(path)
        ns = "/".join(rel.parts[1:-2]) if len(rel.parts) >= 4 else "/".join(rel.parts[1:-1])
        for rec in _records_from_doc(doc, path, ns, f"changed:{status}"):
            rec["_draft_id"] = rec["_id"]
            out.append(rec)
    return out


def upstream_of(rec) -> set:
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


def qc_of(rec) -> dict:
    out = {}
    for name, branch in (rec.get("quickly_check") or {}).items():
        if isinstance(branch, dict):
            out[name] = {"command": str(branch.get("command_template") or ""),
                         "expected": str(branch.get("expected") or ""),
                         "selector": str(branch.get("rank_selector") or "")}
    return out


def expected_norm(rec) -> set[str]:
    e = (qc_of(rec).get("primary") or {}).get("expected") or ""
    e = e[len("regex:"):] if e.startswith("regex:") else e
    return tokens(e)


def text_of(rec) -> set[str]:
    return tokens(rec.get("title"), " ".join(str(x) for x in (rec.get("tags") or [])),
                  " ".join(str(x) for x in (rec.get("symptoms") or [])))


def strong_tokens(rec) -> set[str]:
    blob = " ".join(str(x) for x in [rec.get("title"), " ".join(rec.get("symptoms") or []),
                                     rec.get("root_cause"), rec.get("fix")])
    return set(CODE.findall(blob)) | set(OP.findall(blob))


def root_tokens(rec) -> set[str]:
    return tokens((rec.get("_summary") or {}).get("root_cause") or rec.get("root_cause"))


def fix_tokens(rec) -> set[str]:
    return tokens((rec.get("_summary") or {}).get("fix") or rec.get("fix"))


def sessions_of(rec) -> set[str]:
    out = set(rec.get("_sessions") or [])
    if rec.get("source_session"):
        out.add(str(rec["source_session"]))
    for v in rec.get("_verification") or []:
        if isinstance(v, dict) and v.get("ref"):
            out.add(str(v["ref"]))
    return out


def verification_events(rec) -> set[str]:
    return {str(v["ref"]) for v in (rec.get("_verification") or [])
            if isinstance(v, dict) and v.get("ref")}


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
    ta = tokens(qc_of(a).get("primary", {}).get("command", ""))
    tb = tokens(qc_of(b).get("primary", {}).get("command", ""))
    return bool(ta and tb and overlap(ta, tb) >= 0.6)


def pair_signals(a, b) -> dict:
    s = {
        "root_overlap": round(overlap(root_tokens(a), root_tokens(b)), 3),
        "fix_overlap": round(overlap(fix_tokens(a), fix_tokens(b)), 3),
        "root_tokens": min(len(root_tokens(a)), len(root_tokens(b))),
        "fix_tokens": min(len(fix_tokens(a)), len(fix_tokens(b))),
        "same_expected": bool(expected_norm(a) and expected_norm(a) == expected_norm(b)),
        "same_session": bool(sessions_of(a) & sessions_of(b)),
        "same_event": bool(verification_events(a) & verification_events(b)),
        "shared_upstream": bool(upstream_of(a) & upstream_of(b)),
        "same_id": bool(a.get("_id") and a.get("_id") == b.get("_id")),
        "same_path": bool(a.get("_path") and a.get("_path") == b.get("_path")),
    }
    return s


def contradiction_hints(a, b) -> list[str]:
    hints = []
    if pair_signals(a, b)["same_expected"] and overlap(fix_tokens(a), fix_tokens(b)) < 0.25:
        hints.append("same-check-two-fixes")
    if overlap(text_of(a), text_of(b)) >= 0.45 and conditions_relation(a, b) == "disjoint":
        hints.append("same-symptom-disjoint-ranges")
    if sessions_of(a) & sessions_of(b):
        hints.append("same-session-two-cases")
    if upstream_of(a) & upstream_of(b) and overlap(root_tokens(a), root_tokens(b)) < 0.25:
        hints.append("same-issue-different-root-cause")
    return sorted(set(hints))


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
    strong = bool(strong_tokens(a) & strong_tokens(b))
    cond = conditions_relation(a, b)
    if (s["shared_upstream"] or s["same_id"] or s["same_path"] or s["same_event"]
            or strong_discriminator(a, b, s)):
        return "mandatory"
    if cross_cat and score >= 0.20:
        return "high"
    if not cross_ns and score >= 0.28:
        return "high"
    if s["root_overlap"] >= 0.5 and s["root_tokens"] >= 4:
        return "high"
    if s["fix_overlap"] >= 0.5 and s["fix_tokens"] >= 4:
        return "high"
    if cross_ns and strong:
        return "high"
    if s["same_session"]:
        return "high"
    if cond == "overlap" and score >= 0.20:
        return "high"
    if contradiction_hints(a, b) and score >= 0.20:
        return "high"
    if score >= 0.30 or strong or s["root_overlap"] >= 0.25 or s["fix_overlap"] >= 0.25:
        return "low"
    return None


def stable_pair_id(draft_id: str, case_id: str) -> str:
    return hashlib.sha1(f"{draft_id}:{case_id}".encode("utf-8")).hexdigest()[:16]


def compare(drafts: list[dict], library: list[dict]) -> list[dict]:
    pairs: dict[tuple, dict] = {}

    def add(a, b, source: str):
        if a is b:
            return
        if a.get("_id") and a.get("_id") == b.get("_id") and a.get("_path") == b.get("_path"):
            return
        score = overlap(text_of(a), text_of(b))
        s = pair_signals(a, b)
        tier = tier_of(a, b, s, score)
        if tier is None:
            return
        same_ns = bool(a.get("_ns")) and a.get("_ns") == b.get("_ns")
        key = (a.get("_id"), b.get("_id"), a.get("_path"), b.get("_path"))
        if key in pairs:
            return
        pairs[key] = {
            "pair_id": stable_pair_id(a.get("_draft_id") or a.get("_id") or "",
                                      b.get("_id") or b.get("_draft_id") or ""),
            "draft": a.get("_draft_id") or a.get("_id"),
            "draft_case": a.get("_id"),
            "case": b.get("_id") or b.get("_draft_id"),
            "other_uuid": b.get("_draft_id") if source == "draft-draft" else None,
            "tier": tier, "score": round(score, 3), "signals": s,
            "cross_cat": same_ns and a.get("category") != b.get("category"),
            "hints": contradiction_hints(a, b),
            "source": source,
        }

    for a in drafts:
        for b in library:
            add(a, b, "draft-library")
    for a, b in combinations(drafts, 2):
        add(a, b, "draft-draft")
    out = list(pairs.values())
    for p in out:
        if p["tier"] == "high" and not is_core(p):
            p["tier"] = "low"
    return out


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
    for rows in low_by_draft.values():
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


def decision_skeleton(case_id: str, pairs: list[dict], shown: set, hidden_high: int,
                      main_sha: str = "UNKNOWN", head_sha: str = "UNKNOWN") -> dict:
    return {
        "case_id": case_id,
        "decision": "TODO",
        "main_sha": main_sha,
        "head_sha": head_sha,
        "content_sha256": "",
        "tool_version": "v2",
        "pairs": [{"pair_id": p["pair_id"], "other": p["case"], "tier": p["tier"],
                   "signals": [k for k, v in p["signals"].items() if v],
                   "decision": "TODO", "note": ""}
                  for p in pairs if p["pair_id"] in shown and p["tier"] in ("mandatory", "high")],
        "overflow": {"hidden_high": hidden_high, "ack": None},
        "same_case": [],
    }


def render_report(pairs, shown, hidden_high, hidden_low, drafts_count, library_count) -> str:
    lines = [
        "# Duplicate candidate report",
        f"drafts={drafts_count} library={library_count} generated={len(pairs)} "
        f"displayed={len(shown)} hidden_high={sum(hidden_high.values())} "
        f"hidden_low={sum(hidden_low.values())}",
        "",
    ]
    by_draft = {}
    for p in pairs:
        if p["pair_id"] in shown:
            by_draft.setdefault(p["draft"], []).append(p)
    for draft, rows in by_draft.items():
        lines.append(f"=== draft {draft} ===")
        for p in rows:
            lines.append(f"{p['tier']:9} {p['draft_case']} <-> {p['case']}  score={p['score']}")
            lines.append("          signals=" + ", ".join(k for k, v in p["signals"].items() if v))
            if p["hints"]:
                lines.append("          hints=" + ", ".join(p["hints"]))
            lines.append("          decision: TODO")
        lines.append("")
    return "\n".join(lines)
