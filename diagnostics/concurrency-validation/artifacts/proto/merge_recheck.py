#!/usr/bin/env python3
"""Prototype of the proposed `scripts/merge_recheck.py` (Checkpoint C).

It computes the merge-base, the two change sets, maps paths to case ids, nominates
candidate pairs (reusing the Checkpoint B prototype), flags git-level overlap and
renamed/deleted ids that the other side still mentions, and prints a report skeleton
whose decision fields are for a human.

It is advisory by construction: nothing here can stop a merge. Whether a stale report
blocks a merge depends on a CI gate + branch protection that the repository does not
have today.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import find_duplicates as FD  # noqa: E402

GENERATED = [
    "knowledge/_index.yaml", "knowledge/_index/", "references/_summary-index.yaml",
    "references/_procedure-index.yaml", "references/_procedure-index/", "triage-tree.yaml",
    "metrics/timeline.yaml", "metrics/entry-activity/",
]


def git(root: Path, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


def is_generated(path: str) -> bool:
    return any(path == g or path.startswith(g) for g in GENERATED)


def show(root: Path, ref: str, path: str) -> str:
    rc, out, _ = git(root, "show", f"{ref}:{path}")
    return out if rc == 0 else ""


def changes(root: Path, base: str, head: str) -> dict:
    """name-status with rename detection, plus the case id of each side."""
    rc, out, err = git(root, "diff", "--name-status", "-M", base, head)
    if rc != 0:
        raise RuntimeError(f"git diff {base} {head}: {err}")
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        if status.startswith("R") or status.startswith("C"):
            old_path, new_path = parts[1], parts[2]
        else:
            old_path = new_path = parts[1]
        before = show(root, base, old_path) if status[0] in "MD R".replace(" ", "") else ""
        after = show(root, head, new_path) if status[0] != "D" else ""
        rows.append({
            "status": status[0],
            "path": new_path,
            "old_path": old_path if old_path != new_path else None,
            "id_before": case_id(before),
            "id_after": case_id(after),
            "generated": is_generated(new_path),
        })
    return {"base": base, "head": head, "rows": rows}


def case_id(text: str) -> str | None:
    m = re.search(r"^\s*-?\s*id:\s*([A-Za-z0-9_.-]+)", text, re.M)
    return m.group(1) if m else None


def load_side_cases(root: Path, ref: str, rows) -> list[dict]:
    """Load the case records of one side's changed case files (for B-style compare)."""
    out = []
    for row in rows:
        if row["generated"] or row["status"] == "D" or not row["path"].startswith("knowledge/"):
            continue
        text = show(root, ref, row["path"])
        if not text:
            continue
        try:
            doc = __import__("yaml").safe_load(text) or {}
        except Exception:
            continue
        parts = Path(row["path"]).parts
        ns = "/".join(parts[1:-2]) if len(parts) >= 4 else "/".join(parts[1:-1])
        for case in doc.get("cases") or []:
            if isinstance(case, dict):
                rec = dict(case)
                rec["_id"] = str(case.get("id") or "")
                rec["_ns"] = ns
                rec["_path"] = row["path"]
                rec["_source"] = f"changed:{ref}"
                out.append(rec)
    return out


def load_library_ref(root: Path, ref: str) -> list[dict]:
    """Case records as they exist at `ref` (main side), without checking it out."""
    rc, out, _ = git(root, "ls-tree", "-r", "--name-only", ref, "--", "knowledge")
    recs = []
    for path in sorted(out.splitlines()):
        if not path.endswith(".yaml") or "_index" in Path(path).parts:
            continue
        text = show(root, ref, path)
        try:
            doc = __import__("yaml").safe_load(text) or {}
        except Exception:
            continue
        parts = Path(path).parts
        ns = "/".join(parts[1:-2]) if len(parts) >= 4 else "/".join(parts[1:-1])
        for case in doc.get("cases") or []:
            if isinstance(case, dict):
                rec = dict(case)
                rec["_id"] = str(case.get("id") or "")
                rec["_ns"] = ns
                rec["_path"] = path
                rec["_source"] = "library"
                recs.append(rec)
    return recs


def id_sets(rows):
    added = {r["id_after"] for r in rows if r["status"] == "A" and r["id_after"]}
    modified = {r["id_after"] for r in rows if r["status"] == "M" and r["id_after"]}
    deleted = {r["id_before"] for r in rows if r["status"] == "D" and r["id_before"]}
    renamed = {(r["id_before"], r["id_after"]) for r in rows
               if r["status"] == "R" and r["id_before"] and r["id_after"]}
    return added, modified, deleted, renamed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="原型：合入前复核（Checkpoint C）")
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--report", default=None, help="既有报告：校验其中三个提交号是否仍一致")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    _, main_sha, _ = git(root, "rev-parse", args.base)
    _, head_sha, _ = git(root, "rev-parse", args.head)
    rc, mb, _ = git(root, "merge-base", args.base, args.head)
    if rc != 0:
        print("merge_recheck: 无共同祖先，无法复核", file=sys.stderr)
        return 2
    base_sha = mb.strip()
    main_side = changes(root, base_sha, args.base)
    head_side = changes(root, base_sha, args.head)
    a_add, a_mod, a_del, a_ren = id_sets(main_side["rows"])
    b_add, b_mod, b_del, b_ren = id_sets(head_side["rows"])
    both = {
        "added_both": sorted(a_add & b_add),
        "modified_both": sorted(a_mod & b_mod),
        "deleted_by_main_modified_by_head": sorted(a_del & b_mod),
        "modified_by_main_deleted_by_head": sorted(a_mod & b_del),
        "added_by_main_renamed_by_head": sorted((a_add & {o for o, _ in b_ren})),
    }
    paths_main = {r["path"]: r["status"] for r in main_side["rows"]}
    same_path = sorted({r["path"] for r in head_side["rows"]
                        if r["path"] in paths_main and r["status"] == "A"
                        and paths_main[r["path"]] == "A"})
    # same path touched on both sides with different content
    differing = []
    for r in head_side["rows"]:
        if r["status"] in "AMD" and r["path"] in paths_main:
            m = show(root, args.base, r["path"])
            b = show(root, args.head, r["path"])
            base_text = show(root, base_sha, r["path"])
            if m != base_text and b != base_text and m != b:
                differing.append(r["path"])
    generated = sorted({r["path"] for r in main_side["rows"] + head_side["rows"] if r["generated"]})
    # dangling mentions of renamed/deleted ids in the other side's added/modified text
    dangling = []
    gone = {o for o, _ in b_ren} | b_del
    for row in main_side["rows"]:
        if row["status"] in "AM" and row["path"].startswith("knowledge/"):
            text = show(root, args.base, row["path"])
            for old in gone:
                if old and old in text:
                    dangling.append({"id": old, "mentioned_in": row["path"]})
    gone_main = {o for o, _ in a_ren} | a_del
    for row in head_side["rows"]:
        if row["status"] in "AM" and row["path"].startswith("knowledge/"):
            text = show(root, args.head, row["path"])
            for old in gone_main:
                if old and old in text:
                    dangling.append({"id": old, "mentioned_in": row["path"]})

    # candidate comparison: head-side changed cases vs the latest main library
    library = load_library_ref(root, args.base)
    head_cases = load_side_cases(root, args.head, head_side["rows"])
    pairs, dropped = FD.build_pairs(head_cases, library, 20)
    candidates = []
    for p in pairs:
        a, b = p["a"], p["b"]
        candidates.append({
            "a": a.get("_id"), "b": b.get("_id"), "score": p["score"],
            "reasons": sorted(p["reasons"]),
            "hints": FD.contradiction_hints(a, b),
        })
    stale = None
    if args.report:
        report = Path(args.report).read_text(encoding="utf-8")

        def grab(label):
            m = re.search(label + r"[：:]\s*([0-9a-f]{7,40})", report)
            return m.group(1) if m else None

        recorded = {"main": grab("目标 main"), "head": grab("待合入提交"),
                    "base": grab("共同祖先")}
        now = {"main": main_sha.strip(), "head": head_sha.strip(), "base": base_sha}
        stale = {
            "recorded": recorded,
            "current": now,
            "matches_current": all(
                recorded[k] and now[k].startswith(recorded[k]) for k in ("main", "head", "base")),
        }

    payload = {
        "target_main": main_sha.strip(),
        "head": head_sha.strip(),
        "merge_base": base_sha,
        "main_changes": main_side["rows"],
        "head_changes": head_side["rows"],
        "both_changed_cases": both,
        "same_path_added_both": same_path,
        "same_path_differing": differing,
        "renamed_or_deleted_ids": sorted([f"{o}->{n}" for o, n in (b_ren | a_ren)]),
        "dangling_mentions": dangling,
        "generated_artifacts_touched": generated,
        "candidates": candidates,
        "candidates_unshown": dropped,
        "decision": "TODO（人填）",
        "evidence_destination": "TODO（人填）",
        "open_items": "TODO（人填）",
        "owner": "TODO（人填）",
        "stale": stale,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"# 合入前复核报告（原型）")
    print(f"目标 main：{payload['target_main']}")
    print(f"待合入提交：{payload['head']}")
    print(f"共同祖先：{payload['merge_base']}")
    print(f"双方都改的 case：{json.dumps(both, ensure_ascii=False)}")
    print(f"同路径双方都新增：{same_path}")
    print(f"同路径双方内容不同：{differing}")
    print(f"重命名/删除的 id：{payload['renamed_or_deleted_ids']}")
    print(f"另一侧仍提到已改名的 id：{dangling}")
    print(f"碰到的生成物：{generated}")
    print(f"候选对（{len(candidates)} 对，另有 {dropped} 对未展示）：")
    for c in candidates:
        print(f"  - {c['a']} ↔ {c['b']}（{c['score']}；{', '.join(c['reasons'])}）")
        if c["hints"]:
            print(f"    矛盾提示：{'；'.join(c['hints'])}")
    print("决定：TODO（人填）")
    print("证据去向：TODO（人填）")
    print("未决项：TODO（人填）")
    print("负责人：TODO（人填）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
