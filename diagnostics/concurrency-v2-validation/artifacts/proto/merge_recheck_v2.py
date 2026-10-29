#!/usr/bin/env python3
"""V2 Checkpoint C prototype: revalidate a PR against latest main.

Exit codes:
  0 clean / decisions complete
  1 decision stale (base or head changed)
  2 missing decision coverage or unacknowledged high overflow
  3 same-path add/add, both-modified overlapping field, delete/rename hazard
  4 generated artifact touched
  5 no common ancestor / git failure
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case_diff  # noqa: E402
import find_duplicates_v2 as B  # noqa: E402

GENERATED = ("knowledge/_index.yaml", "knowledge/_index/", "references/_summary-index.yaml",
             "references/_procedure-index.yaml", "references/_procedure-index/",
             "triage-tree.yaml", "metrics/timeline.yaml", "metrics/entry-activity/")


def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


def show(root, ref, path):
    rc, out, _ = git(root, "show", f"{ref}:{path}")
    return out if rc == 0 else ""


def is_generated(path):
    return any(path == g or path.startswith(g) for g in GENERATED)


def changes(root, base, head):
    rc, out, err = git(root, "diff", "--name-status", "-M", base, head)
    if rc != 0:
        raise RuntimeError(err)
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        st = parts[0]
        old_path = parts[1]
        new_path = parts[2] if st.startswith(("R", "C")) and len(parts) > 2 else old_path
        before = show(root, base, old_path) if st[0] in "MDR" else ""
        after = show(root, head, new_path) if st[0] != "D" else ""
        rows.append({"status": st[0], "path": new_path, "old_path": old_path,
                     "before": before, "after": after,
                     "id_before": case_id(before), "id_after": case_id(after),
                     "generated": is_generated(new_path)})
    return rows


def case_id(text):
    m = re.search(r"^\s*-?\s*id:\s*([A-Za-z0-9_.-]+)", text, re.M)
    return m.group(1) if m else None


def load_library_ref(root, ref):
    rc, out, _ = git(root, "ls-tree", "-r", "--name-only", ref, "--", "knowledge")
    recs = []
    for path in sorted(out.splitlines()):
        if not path.endswith(".yaml") or "_index" in Path(path).parts:
            continue
        text = show(root, ref, path)
        try:
            doc = yaml.safe_load(text) or {}
        except Exception:
            continue
        parts = Path(path).parts
        ns = "/".join(parts[1:-2]) if len(parts) >= 4 else "/".join(parts[1:-1])
        for c in doc.get("cases") or []:
            if isinstance(c, dict):
                rec = dict(c)
                rec["_id"] = str(c.get("id") or "")
                rec["_ns"] = ns
                rec["_path"] = path
                rec["_source"] = "library"
                recs.append(rec)
    return recs


def load_head_cases(root, ref, rows):
    recs = []
    for r in rows:
        if r["generated"] or r["status"] == "D" or not r["path"].startswith("knowledge/"):
            continue
        try:
            doc = yaml.safe_load(r["after"]) or {}
        except Exception:
            continue
        parts = Path(r["path"]).parts
        ns = "/".join(parts[1:-2]) if len(parts) >= 4 else "/".join(parts[1:-1])
        for c in doc.get("cases") or []:
            if isinstance(c, dict):
                rec = dict(c)
                rec["_id"] = str(c.get("id") or "")
                rec["_draft_id"] = rec["_id"]
                rec["_ns"] = ns
                rec["_path"] = r["path"]
                rec["_source"] = "head"
                recs.append(rec)
    return recs


def load_decision(path):
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V2 Checkpoint C prototype")
    ap.add_argument("--root", required=True)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--decision", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    _, base_sha, _ = git(root, "rev-parse", args.base)
    _, head_sha, _ = git(root, "rev-parse", args.head)
    rc, mb, _ = git(root, "merge-base", base_sha.strip(), head_sha.strip())
    if rc != 0:
        return 5
    base = base_sha.strip()
    head = head_sha.strip()
    base_merge = mb.strip()
    main_rows = changes(root, base_merge, base)
    head_rows = changes(root, base_merge, head)

    same_path_added = sorted({r["path"] for r in head_rows if r["status"] == "A"} &
                             {r["path"] for r in main_rows if r["status"] == "A"})
    both_modified = sorted({r["id_after"] for r in head_rows if r["status"] == "M" and r["id_after"]} &
                           {r["id_after"] for r in main_rows if r["status"] == "M" and r["id_after"]})
    generated = sorted({r["path"] for r in main_rows + head_rows if r["generated"]})
    deleted = {r["id_before"] for r in head_rows if r["status"] == "D" and r["id_before"]}
    renamed = {(r["id_before"], r["id_after"]) for r in head_rows if r["status"] == "R"}
    dangling = []
    for r in main_rows:
        if r["status"] in "AM" and r["path"].startswith("knowledge/"):
            for old in deleted | {o for o, _ in renamed}:
                if old and old in r["after"]:
                    dangling.append({"id": old, "mentioned_in": r["path"]})

    field_conflicts = []
    for path in [r["path"] for r in head_rows if r["status"] in "AM" and r["path"].startswith("knowledge/")]:
        if path in {r["path"] for r in main_rows if r["status"] in "AM"}:
            d = case_diff.diff_fields(case_diff.show_case(root, base_merge, path),
                                      case_diff.show_case(root, base, path),
                                      case_diff.show_case(root, head, path))
            overlap = {k: v for k, v in d.items() if v["overlap"]}
            if overlap:
                field_conflicts.append({"path": path, "fields": sorted(overlap)})

    library = load_library_ref(root, base)
    head_recs = load_head_cases(root, head, head_rows)
    pairs = B.compare(head_recs, library)
    shown, hidden_high, hidden_low = B.display(pairs)
    shown_pairs = [p for p in pairs if p["pair_id"] in shown and p["tier"] in ("mandatory", "high")]
    required_ids = {p["pair_id"] for p in shown_pairs}
    decision = load_decision(args.decision)
    decision_status = {"present": bool(decision), "stale": False, "missing_pairs": [],
                       "missing_ack": False, "missing_same_case": [],
                       "main_sha": (decision or {}).get("main_sha")}
    same_case_ids = set(both_modified)
    if decision:
        if str(decision.get("main_sha")) != base:
            decision_status["stale"] = True
        have = {p.get("pair_id") for p in (decision.get("pairs") or [])}
        decision_status["missing_pairs"] = sorted(required_ids - have)
        ov = decision.get("overflow") or {}
        if sum(hidden_high.values()) > 0 and not ov.get("ack"):
            decision_status["missing_ack"] = True
        have_case = {c.get("case_id") for c in (decision.get("same_case") or [])}
        decision_status["missing_same_case"] = sorted(same_case_ids - have_case)
    needs_decision = bool(required_ids) or bool(same_case_ids)

    payload = {
        "base": base, "head": head, "merge_base": base_merge,
        "same_path_added": same_path_added,
        "both_modified": both_modified,
        "field_conflicts": field_conflicts,
        "generated": generated,
        "deleted": sorted(deleted),
        "renamed": [f"{a}->{b}" for a, b in sorted(renamed)],
        "dangling": dangling,
        "pairs": [{"pair_id": p["pair_id"], "a": p["draft"], "b": p["case"],
                   "tier": p["tier"], "score": p["score"]} for p in shown_pairs],
        "hidden_high": sum(hidden_high.values()),
        "decision": decision_status,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"base={base} head={head} merge_base={base_merge}")
        print(f"same_path_added={same_path_added} both_modified={both_modified}")
        print(f"field_conflicts={field_conflicts} generated={generated}")
        print(f"deleted={sorted(deleted)} renamed={payload['renamed']} dangling={dangling}")
        print(f"pairs={len(shown_pairs)} hidden_high={sum(hidden_high.values())} decision={decision_status}")

    if generated:
        return 4
    if same_path_added or field_conflicts or dangling:
        return 3
    if not decision:
        return 2 if needs_decision else 0
    if decision_status["stale"]:
        return 1
    if (decision_status["missing_pairs"] or decision_status["missing_ack"]
            or decision_status["missing_same_case"]):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
