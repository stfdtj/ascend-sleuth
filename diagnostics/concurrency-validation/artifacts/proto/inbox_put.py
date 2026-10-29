#!/usr/bin/env python3
"""Prototype of the proposed `scripts/inbox_put.py` (Checkpoint A).

NOT part of the product tree: this is a narrow, runnable proof of concept used to
test the design against real concurrency, crashes and cross-clone identity. The
directory layout and CLI follow `research/2026-10-28-unified-plan.md` §2.3.

Design choices that the plan leaves open (each is exercised by test_inbox_put.py):

  * `new` allocates by `mkdir` (exclusive) in a loop; it never does "check then write".
  * `DONE` is published atomically: write `DONE.tmp`, fsync, `os.replace` -> `DONE`.
  * `finish` refuses to overwrite an existing DONE unless `--refinish` is passed.
    The plan says readers compare hashes; without this rule an author can silently
    re-issue DONE after editing, which makes "hash matches" meaningless.
  * the reader requires `completed_at` AND a complete `files` map; a truncated DONE
    that happens to be valid YAML is NOT accepted.
  * `deployment` defaults to a value derived from the git common dir, because the
    plan's example (`deployment: ascend-sleuth`) is the same string in every clone
    and therefore cannot disambiguate two clones' `...-diag-001`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

CASE = "case.yaml"
MD = "postmortem.md"
SOURCES = "sources.yaml"
DONE = "DONE"
REQUIRED = (CASE, MD, SOURCES)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def default_deployment(root: Path) -> str:
    """Deployment label for a draft.

    Preferred source: `deployment.yaml` -> `deployment.id` (explicit, stable under
    directory rename). Fallback: repo name + hash of the git common dir, which is
    distinct per clone but changes if the checkout directory is renamed.
    """
    cfg = root / "deployment.yaml"
    if cfg.is_file():
        try:
            doc = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
            explicit = (doc.get("deployment") or {}).get("id") if isinstance(doc.get("deployment"), dict) else None
            if explicit:
                return str(explicit)
        except Exception:
            pass
    try:
        r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                           cwd=str(root), capture_output=True, text=True)
        common = Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    except Exception:
        common = None
    name = root.name or "checkout"
    if common is None:
        return name
    digest = hashlib.sha256(str(common).encode("utf-8")).hexdigest()[:8]
    return f"{name}-{digest}"


def inbox_root(root: Path) -> Path:
    return root / "postmortems" / "inbox"


def cmd_new(args) -> int:
    root = Path(args.root).resolve()
    dest_root = inbox_root(root)
    dest_root.mkdir(parents=True, exist_ok=True)
    deployment = args.deployment or default_deployment(root)
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    for seq in range(1, 1000):
        draft_id = f"{date}-{args.source}-{seq:03d}"
        target = dest_root / draft_id
        try:
            os.mkdir(target)          # exclusive create: the whole protocol's lock
        except FileExistsError:
            continue
        except OSError as exc:
            print(f"inbox_put: 无法创建 {target}：{exc}", file=sys.stderr)
            return 2
        (target / SOURCES).write_text(yaml.safe_dump({
            "draft_id": draft_id,
            "created_at": now(),
            "source": {
                "kind": {"diag": "diagnosis", "issue": "issue", "manual": "manual"}.get(
                    args.source, args.source),
                "deployment": deployment,
                "session": args.session or None,
            },
            "sessions": [args.session] if args.session else [],
        }, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(target)
        return 0
    print("inbox_put: 序号用尽（001..999）", file=sys.stderr)
    return 2


def cmd_finish(args) -> int:
    target = Path(args.draft).resolve()
    if not target.is_dir():
        print(f"inbox_put: 不是目录：{target}", file=sys.stderr)
        return 2
    done = target / DONE
    if done.exists() and not args.refinish:
        print(f"inbox_put: {DONE} 已存在，拒绝重写（确需重写加 --refinish）", file=sys.stderr)
        return 2
    missing = [f for f in REQUIRED if not (target / f).is_file()]
    if missing:
        print(f"inbox_put: 缺文件 {missing}，目录保持未完成", file=sys.stderr)
        return 2
    try:
        src = yaml.safe_load((target / SOURCES).read_text(encoding="utf-8")) or {}
        case = yaml.safe_load((target / CASE).read_text(encoding="utf-8")) or {}
    except Exception as exc:
        print(f"inbox_put: YAML 解析失败：{exc}", file=sys.stderr)
        return 2
    if src.get("draft_id") != target.name:
        print(f"inbox_put: sources.draft_id={src.get('draft_id')!r} 与目录名 {target.name!r} 不一致",
              file=sys.stderr)
        return 2
    if not isinstance(case.get("cases"), list) or not case["cases"]:
        print("inbox_put: case.yaml 顶层缺非空 cases", file=sys.stderr)
        return 2
    payload = {"completed_at": now(), "files": {f: sha256(target / f) for f in REQUIRED}}
    tmp = target / (DONE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(yaml.safe_dump(payload, sort_keys=False))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, done)            # atomic publish; readers never see a partial DONE
    print(f"inbox_put: 完成 {target.name}")
    return 0


def read_draft(target: Path) -> dict:
    """Consumer view. Only `complete` drafts are consumable."""
    target = Path(target)
    if not target.is_dir():
        return {"draft_id": target.stem, "state": "missing", "reasons": ["不是目录"]}
    done = target / DONE
    if not done.exists():
        return {"draft_id": target.name, "state": "incomplete", "reasons": ["无 DONE"]}
    try:
        payload = yaml.safe_load(done.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {"draft_id": target.name, "state": "corrupt", "reasons": [f"DONE 解析失败：{exc}"]}
    if not payload.get("completed_at"):
        return {"draft_id": target.name, "state": "corrupt", "reasons": ["DONE 缺 completed_at"]}
    files = payload.get("files")
    if not isinstance(files, dict) or set(files) != set(REQUIRED):
        return {"draft_id": target.name, "state": "corrupt",
                "reasons": [f"DONE.files 不完整：{files}"]}
    bad = []
    for name in REQUIRED:
        p = target / name
        if not p.is_file():
            bad.append(f"{name} 缺失")
        elif sha256(p) != files[name]:
            bad.append(f"{name} 哈希不符")
    if bad:
        return {"draft_id": target.name, "state": "corrupt", "reasons": bad}
    return {"draft_id": target.name, "state": "complete", "reasons": [],
            "completed_at": payload["completed_at"]}


def cmd_list(args) -> int:
    root = Path(args.root).resolve()
    dest_root = inbox_root(root)
    rows, legacy = [], []
    if dest_root.is_dir():
        for child in sorted(dest_root.iterdir()):
            if child.is_dir():
                rows.append(read_draft(child))
            elif child.name.endswith((".case.yaml", ".md")) and child.name != "README.md":
                legacy.append(child.name)
    summary = {"drafts": rows, "legacy_flat_files": legacy,
               "complete": sum(1 for r in rows if r["state"] == "complete"),
               "incomplete": sum(1 for r in rows if r["state"] == "incomplete"),
               "corrupt": sum(1 for r in rows if r["state"] == "corrupt")}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"草稿 {len(rows)} 组：完整 {summary['complete']} · 未完成 {summary['incomplete']} · "
              f"损坏 {summary['corrupt']}；旧平铺文件 {len(legacy)}")
        for r in rows:
            print(f"  [{r['state']}] {r['draft_id']}" + (f"：{'；'.join(r['reasons'])}" if r["reasons"] else ""))
    return 0


def cmd_abort(args) -> int:
    target = Path(args.draft).resolve()
    if not args.force:
        print("inbox_put: abort 需要 --force（不自动删）", file=sys.stderr)
        return 2
    if (target / DONE).exists():
        print("inbox_put: 已完成的草稿不删", file=sys.stderr)
        return 2
    shutil.rmtree(target)
    print(f"inbox_put: 删除未完成草稿 {target.name}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="原型：inbox 组目录（Checkpoint A）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--root", required=True)
    n.add_argument("--source", choices=["diag", "issue", "manual"], default="diag")
    n.add_argument("--session", default="")
    n.add_argument("--deployment", default=None)
    n.add_argument("--date", default=None)
    f = sub.add_parser("finish")
    f.add_argument("draft")
    f.add_argument("--refinish", action="store_true")
    li = sub.add_parser("list")
    li.add_argument("--root", required=True)
    li.add_argument("--json", action="store_true")
    a = sub.add_parser("abort")
    a.add_argument("draft")
    a.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    return {"new": cmd_new, "finish": cmd_finish, "list": cmd_list, "abort": cmd_abort}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
