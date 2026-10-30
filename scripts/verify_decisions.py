#!/usr/bin/env python3
"""verify_decisions.py — structural checks for a human decision file.

It cannot judge whether the decision is correct. It rejects placeholders, missing pair
coverage, stale base/head SHAs, missing same-case decisions, and unacknowledged overflow.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ALLOWED = {"new", "variant", "covered", "deferred", "separate", "merge"}
PAIR_ALLOWED = {"separate", "variant", "merge", "covered", "defer"}


def load(path: str | Path | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def validate(decision: dict, *, base: str, head: str,
             required: dict[str, str] | None = None,
             same_case_ids: set[str] | None = None,
             hidden_high: int = 0,
             content_sha256: str | None = None) -> list[str]:
    required = required or {}
    same_case_ids = same_case_ids or set()
    errors: list[str] = []
    if not decision:
        return ["decision file is missing or empty"]
    if decision.get("case_id") in (None, "", "UNKNOWN"):
        errors.append("case_id is missing")
    overall = str(decision.get("decision") or "")
    if overall not in ALLOWED:
        errors.append(f"decision must be one of {sorted(ALLOWED)}, got {overall!r}")
    if str(decision.get("main_sha") or "") != str(base):
        errors.append("main_sha is not the current base")
    head_ok = str(decision.get("head_sha") or "") == str(head)
    content_ok = bool(content_sha256) and str(decision.get("content_sha256") or "") == str(content_sha256)
    if not head_ok and not content_ok:
        errors.append("head_sha is not the current head and content_sha256 does not match")
    if head_ok and content_sha256 and decision.get("content_sha256") \
            and str(decision["content_sha256"]) != str(content_sha256):
        errors.append("content_sha256 does not match the changed knowledge files")

    have = {}
    for p in decision.get("pairs") or []:
        if not isinstance(p, dict):
            errors.append("pairs[] contains a non-mapping")
            continue
        pid = str(p.get("pair_id") or "")
        have[pid] = p
        val = str(p.get("decision") or "")
        if val not in PAIR_ALLOWED:
            errors.append(f"pair {pid}: decision {val!r} is not allowed")
        if not str(p.get("note") or "").strip():
            errors.append(f"pair {pid}: note is empty")
    for pid, tier in required.items():
        if pid not in have:
            errors.append(f"missing pair {pid} ({tier})")
    for pid in have:
        if pid not in required:
            errors.append(f"decision contains stale/unknown pair {pid}")

    have_case = {str(c.get("case_id")) for c in decision.get("same_case") or []
                 if isinstance(c, dict)}
    for cid in same_case_ids:
        if cid not in have_case:
            errors.append(f"missing same_case decision for {cid}")
    for c in decision.get("same_case") or []:
        if not isinstance(c, dict):
            continue
        if str(c.get("decision") or "") not in PAIR_ALLOWED:
            errors.append(f"same_case {c.get('case_id')}: invalid decision")
        if not str(c.get("note") or "").strip():
            errors.append(f"same_case {c.get('case_id')}: note is empty")

    ov = decision.get("overflow") or {}
    if hidden_high > 0:
        ack = ov.get("ack")
        if not isinstance(ack, dict):
            errors.append(f"hidden_high={hidden_high} requires overflow.ack")
        else:
            if int(ack.get("hidden_count", -1)) != hidden_high:
                errors.append("overflow.ack.hidden_count does not match current hidden_high")
            if not str(ack.get("reason") or "").strip():
                errors.append("overflow.ack.reason is empty")
            if not str(ack.get("reviewer") or "").strip():
                errors.append("overflow.ack.reviewer is empty")
    return errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate a decision file")
    ap.add_argument("--decision", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--pairs-json", default=None,
                    help='JSON list of {"pair_id": "...", "tier": "..."}')
    ap.add_argument("--same-case", action="append", default=[])
    ap.add_argument("--hidden-high", type=int, default=0)
    ap.add_argument("--content-sha256", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    required = {}
    if args.pairs_json:
        for p in json.loads(args.pairs_json):
            required[str(p["pair_id"])] = str(p.get("tier") or "")
    errors = validate(load(args.decision), base=args.base, head=args.head,
                      required=required, same_case_ids=set(args.same_case),
                      hidden_high=args.hidden_high,
                      content_sha256=args.content_sha256)
    if args.json:
        print(json.dumps({"errors": errors}, ensure_ascii=False, indent=2))
    else:
        for e in errors:
            print("ERROR:", e)
        print("decision OK" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    from _stdio import pin_utf8_stdio

    pin_utf8_stdio()
    sys.exit(main())
