#!/usr/bin/env python3
"""V2 provenance checker prototype.

Checks only what is accessible in the repository: manifest shape, committed material
hashes, dropped destinations marked verified, field attribution consistency, event-id
uniqueness across active cases, and lineage/redirect targets. Local-only material is
reported as a limitation, never as verified.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import yaml

EVENT = re.compile(r"^(feedback:[^:]+:\d+|upstream:[^#]+#[^@]+@[A-Za-z_-]+|fixture:[A-Za-z0-9_.-]+|report:[^#]+#[0-9a-f]{7,40}|none)$")
FIELDS = {"title", "category", "symptoms", "quickly_check", "diagnosis", "root_cause",
          "fix", "compat", "platforms", "severity", "fix_type", "tags", "verification",
          "validation_record", "source_session", "upstream", "ref_knowledge"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def case_exists(root: Path, cid: str) -> bool:
    for p in (root / "knowledge").rglob(f"{cid}.yaml"):
        return True
    return False


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def check_one(root: Path, path: Path, all_manifests: list[Path]):
    errors, warnings = [], []
    doc = load_yaml(path)
    cid = str(doc.get("case_id") or "")
    if path.stem != cid:
        errors.append(f"filename {path.stem} != case_id {cid}")
    if not case_exists(root, cid):
        errors.append(f"case {cid} not found in knowledge/")
    materials = doc.get("materials") or []
    draft_ids = set()
    for m in materials:
        did = str(m.get("draft_id") or "")
        draft_ids.add(did)
        for f in m.get("files") or []:
            p = root / str(f.get("path") or "")
            if f.get("committed"):
                if not p.is_file():
                    errors.append(f"committed material missing: {f.get('path')}")
                elif sha256(p) != f.get("sha256"):
                    errors.append(f"committed material hash mismatch: {f.get('path')}")
            else:
                warnings.append(f"local-only material: {f.get('path')} ({f.get('recoverability')})")
        fields = m.get("fields") or {}
        for name, sources in fields.items():
            if name not in FIELDS:
                errors.append(f"unknown field attribution: {name}")
            if not isinstance(sources, list) or not sources:
                errors.append(f"field {name} has no source")
            for s in sources or []:
                if str(s) not in draft_ids:
                    errors.append(f"field {name} cites unknown draft {s}")
            if isinstance(sources, list) and len(sources) > 1 and not m.get("merged"):
                errors.append(f"field {name} has multiple sources but no merged flag")
    dropped_items = list(doc.get("dropped") or [])
    for m in materials:
        dropped_items += list(m.get("dropped") or [])
    for d in dropped_items:
        if d.get("recoverability") == "verified":
            dest = d.get("destination")
            if not dest:
                errors.append("dropped destination marked verified but has no destination")
            elif not (root / str(dest)).is_file():
                errors.append(f"dropped destination missing: {dest}")
            elif d.get("sha256") and sha256(root / str(dest)) != d["sha256"]:
                errors.append(f"dropped destination hash mismatch: {dest}")
        else:
            warnings.append(f"dropped content not verifiable: {d.get('field')} ({d.get('recoverability')})")
    for ev in doc.get("evidence") or []:
        eid = str(ev.get("event_id") or "")
        if not EVENT.match(eid):
            errors.append(f"invalid event_id: {eid}")
    lineage = doc.get("lineage") or {}
    for key in ("supersedes", "merged_into", "renamed_from"):
        val = lineage.get(key)
        targets = [val] if isinstance(val, str) else (val or [])
        for target in targets:
            if not case_exists(root, str(target)) and not list((root / "knowledge/_archive").rglob(f"{target}.yaml")):
                errors.append(f"lineage {key} target missing: {target}")
    return errors, warnings


def check_all(root: Path):
    manifests = sorted((root / "postmortems/provenance").glob("*.yaml"))
    errors, warnings = [], []
    for p in manifests:
        e, w = check_one(root, p, manifests)
        errors += [f"{p.name}: {x}" for x in e]
        warnings += [f"{p.name}: {x}" for x in w]
    # same event id must not be independently claimed by two manifests
    seen = {}
    for p in manifests:
        doc = load_yaml(p)
        for ev in doc.get("evidence") or []:
            eid = str(ev.get("event_id") or "")
            if eid == "none" or not eid:
                continue
            if ev.get("independent"):
                seen.setdefault(eid, []).append((p.name, doc.get("case_id")))
    for eid, owners in seen.items():
        if len(owners) > 1:
            errors.append(f"event {eid} independently claimed by {owners}")
    redirects = root / "postmortems/redirects.yaml"
    if redirects.is_file():
        for row in load_yaml(redirects) or []:
            old, new = row.get("old_id"), row.get("new_id")
            if not new or not case_exists(root, str(new)):
                errors.append(f"redirect {old}->{new}: target missing")
            if old and case_exists(root, str(old)):
                warnings.append(f"redirect {old}->{new}: old id still active")
    return errors, warnings, len(manifests)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    errors, warnings, n = check_all(root)
    if args.json:
        import json
        print(json.dumps({"manifests": n, "errors": errors, "warnings": warnings},
                         ensure_ascii=False, indent=2))
    else:
        print(f"manifests={n} errors={len(errors)} warnings={len(warnings)}")
        for e in errors:
            print("  ✗", e)
        for w in warnings:
            print("  ⚠", w)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
