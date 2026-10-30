#!/usr/bin/env python3
"""merge_recheck.py — Checkpoint C: revalidate a PR against the latest main.

Exit codes:
  0  clean and decisions complete
  1  decision is stale (main_sha/head_sha)
  2  decision missing/invalid, pair coverage incomplete, ack incomplete
  3  same-path add/add, overlapping field change, rename/delete hazard
  4  generated artifact touched
  5  git/merge-base failure
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

import case_diff
import case_match
import verify_decisions

GENERATED = ("knowledge/_index.yaml", "knowledge/_index/", "references/_summary-index.yaml",
             "references/_procedure-index.yaml", "references/_procedure-index/",
             "triage-tree.yaml", "metrics/timeline.yaml", "metrics/entry-activity/")


def git(root: Path, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


def show(root: Path, ref: str, path: str) -> str:
    rc, out, _ = git(root, "show", f"{ref}:{path}")
    return out if rc == 0 else ""


def is_generated(path: str) -> bool:
    return any(path == g or path.startswith(g) for g in GENERATED)


def case_id(text: str) -> str:
    m = re.search(r"^\s*-?\s*id:\s*([A-Za-z0-9_.-]+)", text, re.M)
    return m.group(1) if m else ""


def changes(root: Path, base: str, head: str) -> list[dict]:
    rc, out, err = git(root, "diff", "--name-status", "-M", base, head)
    if rc != 0:
        raise RuntimeError(err)
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        old_path = parts[1]
        new_path = parts[2] if status.startswith(("R", "C")) and len(parts) > 2 else old_path
        before = show(root, base, old_path) if status[0] in "MDR" else ""
        after = show(root, head, new_path) if status[0] != "D" else ""
        rows.append({"status": status[0], "path": new_path, "old_path": old_path,
                     "before": before, "after": after,
                     "id_before": case_id(before), "id_after": case_id(after),
                     "generated": is_generated(new_path)})
    return rows


def knowledge_content_hash(root: Path, base: str, head: str) -> str:
    """Stable hash over the knowledge files changed by this PR.

    The decision file itself is not included, so adding the decision does not change
    the hash. The hash binds the decision to the case bytes, independent of commit SHA.
    """
    import hashlib

    rc, out, _ = git(root, "diff", "--name-only", f"{base}...{head}", "--", "knowledge")
    if rc != 0:
        return ""
    h = hashlib.sha256()
    for path in sorted(p for p in out.splitlines() if p.endswith(".yaml")
                       and "_index" not in Path(p).parts):
        text = show(root, head, path)
        h.update(path.encode("utf-8"))
        h.update(b"\0")
        h.update(text.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def load_library_ref(root: Path, ref: str) -> list[dict]:
    rc, out, _ = git(root, "ls-tree", "-r", "--name-only", ref, "--", "knowledge")
    recs = []
    for path in sorted(out.splitlines()):
        if not path.endswith(".yaml") or "_index" in Path(path).parts or "_archive" in Path(path).parts:
            continue
        text = show(root, ref, path)
        try:
            doc = yaml.safe_load(text) or {}
        except Exception:
            continue
        parts = Path(path).parts
        ns = "/".join(parts[1:-2]) if len(parts) >= 4 else "/".join(parts[1:-1])
        for rec in case_match._records_from_doc(doc, path, ns, "library"):
            recs.append(rec)
    return recs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Checkpoint C merge recheck")
    ap.add_argument("--root", default=".")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--decision", default=None)
    ap.add_argument("--init-decision", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    _, base_sha, _ = git(root, "rev-parse", args.base)
    _, head_sha, _ = git(root, "rev-parse", args.head)
    if not base_sha or not head_sha:
        print("merge_recheck: cannot resolve base/head", file=sys.stderr)
        return 5
    base, head = base_sha.strip(), head_sha.strip()
    rc, mb, _ = git(root, "merge-base", base, head)
    if rc != 0:
        return 5
    merge_base = mb.strip()

    main_rows = changes(root, merge_base, base)
    head_rows = changes(root, merge_base, head)
    main_paths = {r["path"] for r in main_rows}
    head_paths = {r["path"] for r in head_rows}

    same_path_added = sorted({r["path"] for r in head_rows if r["status"] == "A"} &
                             {r["path"] for r in main_rows if r["status"] == "A"})
    both_modified = sorted({r["id_after"] for r in head_rows
                            if r["status"] == "M" and r["id_after"]} &
                           {r["id_after"] for r in main_rows
                            if r["status"] == "M" and r["id_after"]})
    generated = sorted({r["path"] for r in main_rows + head_rows if r["generated"]})
    deleted_ids = {r["id_before"] for r in head_rows if r["status"] == "D" and r["id_before"]}
    renamed = {(r["id_before"], r["id_after"]) for r in head_rows if r["status"] == "R"}
    dangling = []
    for r in main_rows:
        if r["status"] in "AM" and r["path"].startswith("knowledge/"):
            for old in deleted_ids | {o for o, _ in renamed}:
                if old and old in r["after"]:
                    dangling.append({"id": old, "mentioned_in": r["path"]})

    field_conflicts = []
    for path in [r["path"] for r in head_rows
                 if r["status"] in "AM" and r["path"].startswith("knowledge/")]:
        if path in main_paths:
            d = case_diff.diff_fields(case_diff.show_case(root, merge_base, path),
                                      case_diff.show_case(root, base, path),
                                      case_diff.show_case(root, head, path))
            overlap = {k: v for k, v in d.items() if v["overlap"]}
            if overlap:
                field_conflicts.append({"path": path, "fields": sorted(overlap)})

    library = load_library_ref(root, base)
    head_recs = case_match.load_changed(root, base, head)
    pairs = case_match.compare(head_recs, library)
    shown, hidden_high, _hidden_low = case_match.display(pairs)
    required = {p["pair_id"]: p["tier"] for p in pairs
                if p["pair_id"] in shown and p["tier"] in ("mandatory", "high")}
    same_case_ids = set(both_modified)

    decision_path = args.decision
    if not decision_path and head_recs:
        decision_path = str(root / "postmortems" / "decisions" / f"{head_recs[0]['_id']}.yaml")
    decision = verify_decisions.load(decision_path)
    content_hash = knowledge_content_hash(root, base, head)
    errors = verify_decisions.validate(decision, base=base, head=head,
                                       required=required, same_case_ids=same_case_ids,
                                       hidden_high=sum(hidden_high.values()),
                                       content_sha256=content_hash)

    if args.init_decision and not decision:
        target = Path(args.init_decision)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(
            {**case_match.decision_skeleton(head_recs[0]["_id"] if head_recs else "UNKNOWN",
                                             pairs, shown, sum(hidden_high.values()),
                                             base, head),
             "content_sha256": content_hash},
            allow_unicode=True, sort_keys=False), encoding="utf-8")

    payload = {
        "base": base, "head": head, "merge_base": merge_base,
        "same_path_added": same_path_added, "both_modified": both_modified,
        "field_conflicts": field_conflicts, "generated": generated,
        "deleted": sorted(deleted_ids), "renamed": [f"{a}->{b}" for a, b in sorted(renamed)],
        "dangling": dangling,
        "pairs": [{"pair_id": p["pair_id"], "a": p["draft_case"], "b": p["case"],
                   "tier": p["tier"], "score": p["score"],
                   "signals": [k for k, v in p["signals"].items() if v]}
                  for p in pairs if p["pair_id"] in shown],
        "hidden_high": sum(hidden_high.values()),
        "content_sha256": content_hash,
        "decision": {"path": decision_path, "present": bool(decision), "errors": errors},
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"base={base} head={head} merge_base={merge_base}")
        print(f"same_path_added={same_path_added} both_modified={both_modified}")
        print(f"field_conflicts={field_conflicts} generated={generated}")
        print(f"deleted={sorted(deleted_ids)} renamed={payload['renamed']} dangling={dangling}")
        print(f"pairs={len(required)} hidden_high={sum(hidden_high.values())}")
        for e in errors:
            print("ERROR:", e)

    if generated:
        return 4
    if same_path_added or field_conflicts or dangling:
        return 3
    if not decision:
        return 2 if (required or same_case_ids) else 0
    if any("main_sha" in e or "head_sha" in e for e in errors):
        return 1
    if errors:
        return 2
    return 0


if __name__ == "__main__":
    from _stdio import pin_utf8_stdio

    pin_utf8_stdio()
    sys.exit(main())
