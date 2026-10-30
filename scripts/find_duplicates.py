#!/usr/bin/env python3
"""find_duplicates.py — Checkpoint B: generate and display duplicate candidates.

It never merges or promotes. It writes a report; optional `--decision` writes a
skeleton with `decision: TODO`, which a human must complete before promotion/merge.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

import case_match
from draft_queue import resolve_inbox


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Checkpoint B duplicate candidates")
    ap.add_argument("--root", default=".")
    ap.add_argument("--inbox", default=None)
    ap.add_argument("--ns", default=None, help="namespace for drafts (e.g. inference/vllm-ascend)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--decision", default=None)
    ap.add_argument("--decision-case", default="UNKNOWN")
    ap.add_argument("--main-sha", default="UNKNOWN")
    ap.add_argument("--head-sha", default="UNKNOWN")
    ap.add_argument("--high-cap", type=int, default=case_match.HIGH_CAP)
    ap.add_argument("--low-per-draft", type=int, default=case_match.LOW_PER_DRAFT)
    ap.add_argument("--low-global", type=int, default=case_match.LOW_GLOBAL)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    inbox = resolve_inbox(root, args.inbox)
    library = case_match.load_library(root)
    drafts = case_match.load_drafts(root, inbox, namespace=args.ns)
    pairs = case_match.compare(drafts, library)
    shown, hidden_high, hidden_low = case_match.display(
        pairs, args.high_cap, args.low_per_draft, args.low_global)
    visible = [p for p in pairs if p["pair_id"] in shown]

    if args.json:
        print(json.dumps({
            "inbox": str(inbox),
            "counts": {
                "drafts": len(drafts), "library": len(library), "generated": len(pairs),
                "mandatory": sum(1 for p in pairs if p["tier"] == "mandatory"),
                "high": sum(1 for p in pairs if p["tier"] == "high"),
                "low": sum(1 for p in pairs if p["tier"] == "low"),
                "displayed": len(shown),
                "hidden_high": sum(hidden_high.values()),
                "hidden_low": sum(hidden_low.values()),
            },
            "hidden_high_by_draft": hidden_high,
            "pairs": visible,
        }, ensure_ascii=False, indent=2, default=str))
    else:
        print(case_match.render_report(pairs, shown, hidden_high, hidden_low,
                                       len(drafts), len(library)))

    if args.decision:
        target = Path(args.decision)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(
            case_match.decision_skeleton(args.decision_case, pairs, shown,
                                         sum(hidden_high.values()),
                                         args.main_sha, args.head_sha),
            allow_unicode=True, sort_keys=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    from _stdio import pin_utf8_stdio

    pin_utf8_stdio()
    sys.exit(main())
