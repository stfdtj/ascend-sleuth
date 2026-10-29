#!/usr/bin/env python3
"""V2 same-case field diff (prototype): compare one case at three Git refs."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

FIELDS = ("title", "category", "symptoms", "quickly_check", "diagnosis", "root_cause",
          "fix", "fix_on_mismatch", "compat", "platforms", "severity", "fix_type",
          "tags", "verification", "validation_record")


def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


def show_case(root: Path, ref: str, path: str) -> dict | None:
    rc, out, _ = git(root, "show", f"{ref}:{path}")
    if rc != 0:
        return None
    try:
        doc = yaml.safe_load(out) or {}
    except Exception:
        return None
    cases = doc.get("cases") or []
    return cases[0] if cases and isinstance(cases[0], dict) else None


def diff_fields(base, main, head) -> dict:
    """Return {field: {base, main, head, main_changed, head_changed, overlap}}."""
    out = {}
    for f in FIELDS:
        b = (base or {}).get(f)
        m = (main or {}).get(f)
        h = (head or {}).get(f)
        mc, hc = m != b, h != b
        out[f] = {"base": b, "main": m, "head": h, "main_changed": mc,
                  "head_changed": hc, "overlap": mc and hc and m != h}
    return out


def main(argv=None) -> int:
    ap = __import__("argparse").ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--main", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--path", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    b = show_case(root, args.base, args.path)
    m = show_case(root, args.main, args.path)
    h = show_case(root, args.head, args.path)
    d = diff_fields(b, m, h)
    changed = {k: v for k, v in d.items() if v["main_changed"] or v["head_changed"]}
    overlap = {k: v for k, v in d.items() if v["overlap"]}
    out = {"path": args.path, "changed": changed, "overlap": overlap}
    import json
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 3 if overlap else 0


if __name__ == "__main__":
    sys.exit(main())
