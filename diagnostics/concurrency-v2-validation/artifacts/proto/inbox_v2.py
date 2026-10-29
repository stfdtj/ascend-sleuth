#!/usr/bin/env python3
"""V2 draft writer (prototype): UUID directory, strict finish, reopen, list, abort."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import draft_queue as DQ  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def deployment_id(root: Path) -> str:
    cfg = root / "deployment.yaml"
    if cfg.is_file():
        try:
            doc = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
            dep = doc.get("deployment") if isinstance(doc.get("deployment"), dict) else {}
            if dep.get("id"):
                return str(dep["id"])
        except Exception:
            pass
    return "unknown"


def inbox_root(root: Path) -> Path:
    return root / "postmortems" / "inbox"


def write_sources(path: Path, draft_id: str, source: str, session: str,
                  supersedes: str | None = None):
    src = {
        "draft_id": draft_id,
        "created_at": now(),
        "source": {"kind": {"diag": "diagnosis", "issue": "issue", "manual": "manual"}.get(source, source),
                   "deployment_id": deployment_id(path.parent.parent.parent.parent),
                   "session": session or None},
        "sessions": [session] if session else [],
    }
    if supersedes:
        src["supersedes"] = supersedes
    path.write_text(yaml.safe_dump(src, allow_unicode=True, sort_keys=False), encoding="utf-8")


def cmd_new(args) -> int:
    root = Path(args.root).resolve()
    base = inbox_root(root)
    base.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        draft_id = str(uuid.uuid4())
        target = base / draft_id
        try:
            os.mkdir(target)
        except FileExistsError:
            continue
        write_sources(target / "sources.yaml", draft_id, args.source, args.session or "")
        print(target)
        return 0
    print("inbox_v2: UUID allocation failed", file=sys.stderr)
    return 2


def cmd_finish(args) -> int:
    target = Path(args.draft).resolve()
    if not target.is_dir():
        print(f"inbox_v2: not a directory: {target}", file=sys.stderr)
        return 2
    if (target / DQ.SUPERSEDED).exists():
        print("inbox_v2: draft is superseded; create a new draft", file=sys.stderr)
        return 2
    if (target / DQ.DONE).exists():
        print("inbox_v2: DONE already exists; use reopen", file=sys.stderr)
        return 2
    missing = [f for f in DQ.REQUIRED if not (target / f).is_file()]
    if missing:
        print(f"inbox_v2: missing files {missing}", file=sys.stderr)
        return 2
    try:
        src = yaml.safe_load((target / "sources.yaml").read_text(encoding="utf-8")) or {}
        case = yaml.safe_load((target / "case.yaml").read_text(encoding="utf-8")) or {}
    except Exception as exc:
        print(f"inbox_v2: YAML parse failed: {exc}", file=sys.stderr)
        return 2
    if src.get("draft_id") != target.name:
        print("inbox_v2: sources.draft_id != directory name", file=sys.stderr)
        return 2
    if not isinstance(case.get("cases"), list) or not case["cases"]:
        print("inbox_v2: case.yaml has no non-empty cases", file=sys.stderr)
        return 2
    payload = {"completed_at": now(), "files": {f: DQ.sha256(target / f) for f in DQ.REQUIRED}}
    tmp = target / (DQ.DONE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(yaml.safe_dump(payload, sort_keys=False))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target / DQ.DONE)
    print(f"inbox_v2: complete {target.name}")
    return 0


def cmd_reopen(args) -> int:
    old = Path(args.draft).resolve()
    state = DQ.read_draft(old)
    if state["state"] != "complete":
        print(f"inbox_v2: reopen requires complete, got {state['state']}", file=sys.stderr)
        return 2
    root = old.parent.parent.parent
    base = old.parent
    new_id = str(uuid.uuid4())
    new = base / new_id
    os.mkdir(new)
    for name in DQ.REQUIRED:
        shutil.copy2(old / name, new / name)
    src = yaml.safe_load((new / "sources.yaml").read_text(encoding="utf-8")) or {}
    src["draft_id"] = new_id
    src["created_at"] = now()
    src["supersedes"] = old.name
    (new / "sources.yaml").write_text(yaml.safe_dump(src, allow_unicode=True, sort_keys=False),
                                      encoding="utf-8")
    payload = {"completed_at": now(), "files": {f: DQ.sha256(new / f) for f in DQ.REQUIRED}}
    (new / DQ.DONE).write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    (old / DQ.SUPERSEDED).write_text(yaml.safe_dump(
        {"superseded_by": new_id, "at": now(), "reason": args.reason or "reopen"},
        allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(new)
    return 0


def cmd_abort(args) -> int:
    target = Path(args.draft).resolve()
    if not args.force:
        print("inbox_v2: abort requires --force", file=sys.stderr)
        return 2
    if (target / DQ.DONE).exists() or (target / DQ.SUPERSEDED).exists():
        print("inbox_v2: refuse to delete completed/superseded draft", file=sys.stderr)
        return 2
    shutil.rmtree(target)
    print(f"inbox_v2: removed {target.name}")
    return 0


def cmd_list(args) -> int:
    return DQ.main(["--root", args.root, "--json"] + (["--inbox", args.inbox] if args.inbox else []))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V2 draft writer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--root", required=True)
    n.add_argument("--source", choices=["diag", "issue", "manual"], default="diag")
    n.add_argument("--session", default="")
    f = sub.add_parser("finish")
    f.add_argument("draft")
    r = sub.add_parser("reopen")
    r.add_argument("draft")
    r.add_argument("--reason", default="")
    a = sub.add_parser("abort")
    a.add_argument("draft")
    a.add_argument("--force", action="store_true")
    li = sub.add_parser("list")
    li.add_argument("--root", required=True)
    li.add_argument("--inbox", default=None)
    li.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    return {"new": cmd_new, "finish": cmd_finish, "reopen": cmd_reopen,
            "abort": cmd_abort, "list": cmd_list}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
