#!/usr/bin/env python3
"""V2 draft queue reader (prototype).

One contract for every consumer: `complete`, `incomplete`, `corrupt`, `superseded`,
`legacy_flat`. The directory name is a UUID; `sources.yaml.draft_id` must match it.
`DONE` is the completion marker and carries sha256 for the three files.
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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_draft(path: Path) -> dict:
    path = Path(path)
    out = {"draft_id": path.name, "path": str(path), "state": "incomplete", "reasons": []}
    if not path.is_dir():
        return {**out, "state": "missing", "reasons": ["not a directory"]}
    if (path / SUPERSEDED).exists():
        try:
            marker = yaml.safe_load((path / SUPERSEDED).read_text(encoding="utf-8")) or {}
        except Exception as exc:
            marker = {"error": str(exc)}
        return {**out, "state": "superseded", "superseded_by": marker.get("superseded_by"),
                "reasons": ["SUPERSEDED marker"]}
    done = path / DONE
    if not done.is_file():
        return out
    try:
        payload = yaml.safe_load(done.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {**out, "state": "corrupt", "reasons": [f"DONE parse failed: {exc}"]}
    if not payload.get("completed_at"):
        return {**out, "state": "corrupt", "reasons": ["DONE missing completed_at"]}
    files = payload.get("files")
    if not isinstance(files, dict) or set(files) != set(REQUIRED):
        return {**out, "state": "corrupt", "reasons": [f"DONE.files invalid: {files!r}"]}
    bad = []
    for name in REQUIRED:
        p = path / name
        if not p.is_file():
            bad.append(f"{name} missing")
        elif sha256(p) != files[name]:
            bad.append(f"{name} hash mismatch")
    if bad:
        return {**out, "state": "corrupt", "reasons": bad}
    try:
        src = yaml.safe_load((path / "sources.yaml").read_text(encoding="utf-8")) or {}
        case = yaml.safe_load((path / "case.yaml").read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {**out, "state": "corrupt", "reasons": [f"YAML parse failed: {exc}"]}
    if src.get("draft_id") != path.name:
        return {**out, "state": "corrupt",
                "reasons": [f"sources.draft_id={src.get('draft_id')!r} != dir {path.name!r}"]}
    if not isinstance(case.get("cases"), list) or not case["cases"]:
        return {**out, "state": "corrupt", "reasons": ["case.yaml has no non-empty cases"]}
    return {**out, "state": "complete", "completed_at": payload["completed_at"],
            "sources": src, "case": case}


def scan(inbox: Path) -> dict:
    inbox = Path(inbox)
    rows, legacy = [], []
    if not inbox.is_dir():
        return {"drafts": rows, "legacy_flat_files": legacy,
                "complete": 0, "incomplete": 0, "corrupt": 0, "superseded": 0}
    for child in sorted(inbox.iterdir()):
        if child.is_dir():
            rows.append(read_draft(child))
        elif child.name.endswith(".case.yaml") and child.name != "README.md":
            legacy.append(child.name)
    counts = {s: sum(1 for r in rows if r["state"] == s)
              for s in ("complete", "incomplete", "corrupt", "superseded")}
    return {"drafts": rows, "legacy_flat_files": legacy, **counts}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V2 draft queue reader")
    ap.add_argument("--root", default=".")
    ap.add_argument("--inbox", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    inbox = Path(args.inbox) if args.inbox else root / "postmortems" / "inbox"
    data = scan(inbox)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"drafts={len(data['drafts'])} complete={data['complete']} "
              f"incomplete={data['incomplete']} corrupt={data['corrupt']} "
              f"superseded={data['superseded']} legacy={len(data['legacy_flat_files'])}")
        for r in data["drafts"]:
            print(f"  [{r['state']}] {r['draft_id']}" +
                  (f"：{'；'.join(r['reasons'])}" if r["reasons"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
