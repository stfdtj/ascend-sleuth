#!/usr/bin/env python3
"""Main freshness heartbeat prototype: fail if the generated index is stale on main."""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    p = subprocess.run([sys.executable, str(root / "scripts/build_index.py"), "--check"],
                       cwd=root, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        print("STALE: generated knowledge index does not match sources on this checkout")
        print((p.stdout or p.stderr)[-1200:])
        return 1
    print("FRESH: generated knowledge index matches sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
