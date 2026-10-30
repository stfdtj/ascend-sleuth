#!/usr/bin/env python3
"""inbox_put.py — writer for the V2 draft queue.

Commands:
  new       create an exclusive UUID directory and sources.yaml
  finish    validate three files, hash them, atomically publish DONE
  reopen    mark old draft SUPERSEDED, copy it to a new UUID, publish new DONE
  abort     remove an incomplete draft (requires --force)
  list      print the shared reader output
  migrate   copy valid legacy flat drafts to UUID directories, back up originals

The directory name is the draft UUID. `sources.yaml.draft_id` must equal it.
Completed drafts are immutable; edit through `reopen`.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from draft_queue import (
    DONE,
    REQUIRED,
    SUPERSEDED,
    read_draft,
    resolve_inbox,
    scan,
    sha256,
)

MIGRATION = "_migration.json"
LEGACY = "_legacy"
MIGRATED = "_migrated"


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def deployment_id(root: Path) -> str:
    cfg = Path(root) / "deployment.yaml"
    if cfg.is_file():
        try:
            doc = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
            dep = doc.get("deployment") if isinstance(doc.get("deployment"), dict) else {}
            if dep.get("id"):
                return str(dep["id"])
        except Exception:
            pass
    return "unknown"


def _write_yaml(path: Path, data: dict):
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")


def _sources(draft_id: str, source: str, session: str, root: Path,
             supersedes: str | None = None, legacy_path: str | None = None) -> dict:
    src = {
        "draft_id": draft_id,
        "created_at": now(),
        "source": {
            "kind": {"diag": "diagnosis", "issue": "issue", "manual": "manual",
                     "legacy": "legacy-migration"}.get(source, source),
            "deployment_id": deployment_id(root),
            "session": session or None,
        },
        "sessions": [session] if session else [],
        "verification": [{"event_id": "none", "kind": "legacy"}] if source == "legacy"
                        else [{"event_id": "none", "kind": source}],
    }
    if supersedes:
        src["supersedes"] = supersedes
    if legacy_path:
        src["legacy_path"] = legacy_path
        src["migrated_at"] = now()
    return src


def cmd_new(args) -> int:
    root = Path(args.root).resolve()
    inbox = resolve_inbox(root, args.inbox)
    inbox.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        draft_id = str(uuid.uuid4())
        target = inbox / draft_id
        try:
            os.mkdir(target)
        except FileExistsError:
            continue
        _write_yaml(target / "sources.yaml",
                    _sources(draft_id, args.source, args.session or "", root))
        print(target)
        return 0
    print("inbox_put: UUID allocation failed", file=sys.stderr)
    return 2


def _validate_finish(target: Path) -> tuple[dict | None, str | None]:
    if not target.is_dir():
        return None, f"not a directory: {target}"
    if (target / SUPERSEDED).exists():
        return None, "draft is superseded; create a new draft"
    if (target / DONE).exists():
        return None, "DONE already exists; use reopen"
    missing = [f for f in REQUIRED if not (target / f).is_file()]
    if missing:
        return None, f"missing files {missing}"
    try:
        sources = yaml.safe_load((target / "sources.yaml").read_text(encoding="utf-8")) or {}
        case = yaml.safe_load((target / "case.yaml").read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return None, f"YAML parse failed: {exc}"
    if sources.get("draft_id") != target.name:
        return None, "sources.draft_id != directory name"
    cases = case.get("cases") if isinstance(case, dict) else None
    if not isinstance(cases, list) or not cases:
        return None, "case.yaml has no non-empty cases"
    payload = {"completed_at": now(),
               "files": {f: sha256(target / f) for f in REQUIRED}}
    return payload, None


def _publish_done(target: Path, payload: dict):
    tmp = target / (DONE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(yaml.safe_dump(payload, sort_keys=False))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target / DONE)


def cmd_finish(args) -> int:
    target = Path(args.draft).resolve()
    payload, err = _validate_finish(target)
    if err:
        print(f"inbox_put: {err}", file=sys.stderr)
        return 2
    _publish_done(target, payload)
    print(f"inbox_put: complete {target.name}")
    return 0


def cmd_reopen(args) -> int:
    old = Path(args.draft).resolve()
    state = read_draft(old)
    if state["state"] != "complete":
        print(f"inbox_put: reopen requires complete, got {state['state']}", file=sys.stderr)
        return 2
    root = old.parent.parent.parent
    new_id = str(uuid.uuid4())
    new = old.parent / new_id
    # Publish the old marker first: a crash leaves at most the old draft suppressed,
    # never two complete drafts.
    _write_yaml(old / SUPERSEDED, {"superseded_by": new_id, "at": now(),
                                   "reason": args.reason or "reopen"})
    try:
        os.mkdir(new)
        for name in REQUIRED:
            shutil.copy2(old / name, new / name)
        src = yaml.safe_load((new / "sources.yaml").read_text(encoding="utf-8")) or {}
        src["draft_id"] = new_id
        src["created_at"] = now()
        src["supersedes"] = old.name
        _write_yaml(new / "sources.yaml", src)
        payload = {"completed_at": now(),
                   "files": {f: sha256(new / f) for f in REQUIRED}}
        _publish_done(new, payload)
    except Exception as exc:
        print(f"inbox_put: reopen failed after old marker: {exc}", file=sys.stderr)
        print("inbox_put: old draft is suppressed; recover files from git/backup", file=sys.stderr)
        return 2
    print(new)
    return 0


def cmd_abort(args) -> int:
    target = Path(args.draft).resolve()
    if not args.force:
        print("inbox_put: abort requires --force", file=sys.stderr)
        return 2
    if (target / DONE).exists() or (target / SUPERSEDED).exists():
        print("inbox_put: refuse to delete completed/superseded draft", file=sys.stderr)
        return 2
    shutil.rmtree(target)
    print(f"inbox_put: removed {target.name}")
    return 0


def cmd_list(args) -> int:
    inbox = resolve_inbox(Path(args.root), args.inbox)
    data = scan(inbox)
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    return 0


def _legacy_target(inbox: Path, case_id: str, case_path: Path) -> Path:
    digest = sha256(case_path)[:10]
    return inbox / LEGACY / f"{case_id}-{digest}"


def _migration_entries(inbox: Path) -> list[dict]:
    p = inbox / MIGRATION
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_migration(inbox: Path, entries: list[dict]):
    (inbox / MIGRATION).write_text(json.dumps(entries, ensure_ascii=False, indent=2),
                                   encoding="utf-8")


def cmd_migrate(args) -> int:
    root = Path(args.root).resolve()
    inbox = resolve_inbox(root, args.inbox)
    if args.rollback:
        entries = _migration_entries(inbox)
        if not entries:
            print("inbox_put: no migration ledger", file=sys.stderr)
            return 2
        for e in reversed(entries):
            new = inbox / e["new"]
            old = inbox / e["old"]
            if not new.is_dir() or not old.is_dir():
                print(f"inbox_put: skip rollback {e['new']} -> {e['old']}", file=sys.stderr)
                continue
            archived = inbox / MIGRATED / e["new"]
            archived.parent.mkdir(parents=True, exist_ok=True)
            if archived.exists():
                shutil.rmtree(archived)
            shutil.move(str(new), str(archived))
            for name in ("case.yaml", "postmortem.md"):
                src = old / name
                if src.is_file():
                    shutil.move(str(src), str(inbox / (e["case_id"] + (".case.yaml" if name == "case.yaml" else ".md"))))
            shutil.rmtree(old, ignore_errors=True)
        _save_migration(inbox, [])
        print("inbox_put: rollback complete")
        return 0

    data = scan(inbox)
    entries = _migration_entries(inbox)
    planned = []
    for row in data["drafts"]:
        if row["state"] != "legacy_flat":
            if row["state"] in ("incomplete", "corrupt"):
                planned.append((row["draft_id"], row["state"], "skip"))
            continue
        old = Path(row["path"])
        planned.append((row["case_id"], row["state"], "migrate"))
        if not args.apply:
            continue
        target = inbox / str(uuid.uuid4())
        os.mkdir(target)
        shutil.copy2(old, target / "case.yaml")
        shutil.copy2(old.with_name(old.name[:-len(".case.yaml")] + ".md"),
                     target / "postmortem.md")
        _write_yaml(target / "sources.yaml",
                    _sources(target.name, "legacy", "", root,
                             legacy_path=str(old.relative_to(inbox))))
        payload = {"completed_at": now(),
                   "files": {f: sha256(target / f) for f in REQUIRED}}
        _publish_done(target, payload)
        backup = _legacy_target(inbox, row["case_id"], old)
        backup.mkdir(parents=True, exist_ok=True)
        for name in ("case.yaml", "postmortem.md"):
            src = old if name == "case.yaml" else old.with_name(old.name[:-len(".case.yaml")] + ".md")
            shutil.move(str(src), str(backup / name))
        entries.append({"case_id": row["case_id"], "old": str(backup.relative_to(inbox)),
                        "new": target.name, "at": now()})
        _save_migration(inbox, entries)
    for case_id, state, action in planned:
        print(f"{action:8} {state:12} {case_id}")
    if not args.apply:
        print("dry-run; pass --apply to migrate")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V2 inbox writer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new")
    n.add_argument("--root", default=".")
    n.add_argument("--inbox", default=None)
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
    li.add_argument("--root", default=".")
    li.add_argument("--inbox", default=None)

    m = sub.add_parser("migrate")
    m.add_argument("--root", default=".")
    m.add_argument("--inbox", default=None)
    m.add_argument("--apply", action="store_true")
    m.add_argument("--rollback", action="store_true")

    args = ap.parse_args(argv)
    return {"new": cmd_new, "finish": cmd_finish, "reopen": cmd_reopen,
            "abort": cmd_abort, "list": cmd_list, "migrate": cmd_migrate}[args.cmd](args)


if __name__ == "__main__":
    from _stdio import pin_utf8_stdio

    pin_utf8_stdio()
    sys.exit(main())
