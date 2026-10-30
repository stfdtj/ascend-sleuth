#!/usr/bin/env python3
"""draft_queue.py — one reader contract for the postmortem inbox.

States:
  complete      DONE parses, exactly the three files, hashes match, draft_id matches,
                case.yaml has a non-empty cases list.
  incomplete    directory without DONE (or a flat .case.yaml without .md).
  corrupt       DONE/YAML unparsable, missing file, hash mismatch, draft_id mismatch.
  superseded    SUPERSEDED marker present (reopen); never consumed.
  legacy_flat   old <id>.case.yaml + <id>.md pair; consumable with a warning.

The inbox is a runtime directory. By default it is resolved through
`exec_log_path.resolve_checkout_dir("inbox", root)`, which anchors it to the main
checkout so worktrees share one queue. `--inbox` is for tests and deliberate isolation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

REQUIRED = ("case.yaml", "postmortem.md", "sources.yaml")
DONE = "DONE"
SUPERSEDED = "SUPERSEDED"
SKIP_DIRS = {"_legacy", "_quarantine", "_migrated"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_inbox(root: Path, explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    from exec_log_path import resolve_checkout_dir

    path, _where, _rel = resolve_checkout_dir("inbox", Path(root).resolve())
    return path


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _case_info(case: dict) -> tuple[str, str]:
    cases = case.get("cases") if isinstance(case, dict) else None
    if not isinstance(cases, list) or not cases or not isinstance(cases[0], dict):
        return "", ""
    first = cases[0]
    return str(first.get("id") or ""), str(first.get("title") or "")


def read_draft(path: Path) -> dict:
    path = Path(path)
    base = {"draft_id": path.name, "path": str(path), "state": "incomplete",
            "reasons": [], "case_id": "", "title": ""}
    if not path.is_dir():
        return {**base, "state": "missing", "reasons": ["not a directory"]}

    if (path / SUPERSEDED).exists():
        try:
            marker = _load_yaml(path / SUPERSEDED)
        except Exception as exc:
            marker = {"error": str(exc)}
        return {**base, "state": "superseded",
                "superseded_by": marker.get("superseded_by"),
                "reasons": ["SUPERSEDED marker"]}

    done_path = path / DONE
    if not done_path.is_file():
        return base

    try:
        done = _load_yaml(done_path)
    except Exception as exc:
        return {**base, "state": "corrupt", "reasons": [f"DONE parse failed: {exc}"]}
    if not done.get("completed_at"):
        return {**base, "state": "corrupt", "reasons": ["DONE missing completed_at"]}
    files = done.get("files")
    if not isinstance(files, dict) or set(files) != set(REQUIRED):
        return {**base, "state": "corrupt", "reasons": [f"DONE.files invalid: {files!r}"]}

    bad = []
    for name in REQUIRED:
        p = path / name
        if not p.is_file():
            bad.append(f"{name} missing")
        elif sha256(p) != files[name]:
            bad.append(f"{name} hash mismatch")
    if bad:
        return {**base, "state": "corrupt", "reasons": bad}

    try:
        sources = _load_yaml(path / "sources.yaml")
        case = _load_yaml(path / "case.yaml")
    except Exception as exc:
        return {**base, "state": "corrupt", "reasons": [f"YAML parse failed: {exc}"]}
    if sources.get("draft_id") != path.name:
        return {**base, "state": "corrupt",
                "reasons": [f"sources.draft_id={sources.get('draft_id')!r} != {path.name!r}"]}
    case_id, title = _case_info(case)
    if not case_id:
        return {**base, "state": "corrupt", "reasons": ["case.yaml has no non-empty cases"]}
    return {**base, "state": "complete", "completed_at": done["completed_at"],
            "case_id": case_id, "title": title, "sources": sources, "case": case}


def read_flat(path: Path) -> dict:
    """Read one legacy flat pair (<id>.case.yaml + <id>.md)."""
    case_path = Path(path)
    case_id = case_path.name[:-len(".case.yaml")] if case_path.name.endswith(".case.yaml") else case_path.stem
    md_path = case_path.with_name(case_path.name[:-len(".case.yaml")] + ".md")
    base = {"draft_id": case_id, "path": str(case_path), "state": "incomplete",
            "reasons": [], "case_id": case_id, "title": ""}
    if not md_path.is_file():
        return {**base, "state": "incomplete", "reasons": ["legacy draft missing .md"]}
    try:
        case = _load_yaml(case_path)
    except Exception as exc:
        return {**base, "state": "corrupt", "reasons": [f"legacy case parse failed: {exc}"]}
    parsed_id, title = _case_info(case)
    if not parsed_id:
        return {**base, "state": "corrupt", "reasons": ["legacy case has no non-empty cases"]}
    return {**base, "state": "legacy_flat", "case_id": parsed_id, "title": title,
            "reasons": ["legacy flat draft: no DONE/hash; consumable with warning"]}


def scan(inbox: Path) -> dict:
    inbox = Path(inbox)
    drafts: list[dict] = []
    if not inbox.is_dir():
        return {"inbox": str(inbox), "drafts": [], "complete": 0, "incomplete": 0,
                "corrupt": 0, "superseded": 0, "legacy_flat": 0}
    for child in sorted(inbox.iterdir()):
        if child.is_dir():
            if child.name in SKIP_DIRS:
                continue
            drafts.append(read_draft(child))
        elif child.name.endswith(".case.yaml"):
            drafts.append(read_flat(child))
    counts = {s: sum(1 for r in drafts if r["state"] == s)
              for s in ("complete", "incomplete", "corrupt", "superseded", "legacy_flat")}
    return {"inbox": str(inbox), "drafts": drafts, **counts}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Inbox reader (one state contract)")
    ap.add_argument("--root", default=".", help="repository root")
    ap.add_argument("--inbox", default=None, help="override inbox path (tests/isolation)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    inbox = resolve_inbox(Path(args.root), args.inbox)
    data = scan(inbox)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"inbox={inbox}")
        print(f"complete={data['complete']} incomplete={data['incomplete']} "
              f"corrupt={data['corrupt']} superseded={data['superseded']} "
              f"legacy_flat={data['legacy_flat']}")
        for row in data["drafts"]:
            extra = f" — {'; '.join(row['reasons'])}" if row["reasons"] else ""
            print(f"  [{row['state']}] {row['draft_id']} ({row['case_id']}){extra}")
    return 0


if __name__ == "__main__":
    from _stdio import pin_utf8_stdio

    pin_utf8_stdio()
    sys.exit(main())
