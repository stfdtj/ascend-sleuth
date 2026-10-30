#!/usr/bin/env python3
"""case_diff.py — field-level diff for one case at three Git refs."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

FIELDS = ("title", "category", "symptoms", "quickly_check", "diagnosis", "root_cause",
          "fix", "fix_on_mismatch", "compat", "platforms", "severity", "fix_type",
          "tags", "verification", "validation_record")


def git(root: Path, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


def show_case(root: Path, ref: str, path: str):
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
    out = {}
    for field in FIELDS:
        b = (base or {}).get(field)
        m = (main or {}).get(field)
        h = (head or {}).get(field)
        mc, hc = m != b, h != b
        out[field] = {"base": b, "main": m, "head": h,
                      "main_changed": mc, "head_changed": hc,
                      "overlap": mc and hc and m != h}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Field diff at base/main/head")
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
    print(json.dumps({"path": args.path, "changed": changed, "overlap": overlap},
                     ensure_ascii=False, indent=2, default=str))
    return 3 if overlap else 0


if __name__ == "__main__":
    from _stdio import pin_utf8_stdio

    pin_utf8_stdio()
    sys.exit(main())
