"""discover(root) -> Candidate[] -- generation-design.md section 1.

Only enumerates top-level *.yaml files (non-recursive -- matches the real
traces/ convention: traces/evidence/, traces/exports/ are subdirectories and
must never be misread as session files). Never executes anything found in a
trace; never follows network URLs recorded in it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

MAX_TRACE_BYTES = 2 * 1024 * 1024  # generation-design.md: reject traces over 2 MiB
TERMINAL_STATUSES = {"resolved", "escalated", "archived"}


@dataclass
class Candidate:
    session_id: str
    path: Path
    status: str  # as recorded, or "unknown"
    summary: str
    updated_at: str
    terminal: bool

    def to_dict(self):
        return {"session_id": self.session_id, "path": str(self.path), "status": self.status,
                "summary": self.summary, "updated_at": self.updated_at, "terminal": self.terminal}


def read_candidate(path: Path) -> dict:
    """Safely parse one trace YAML file. Raises ValueError on anything that
    looks unsafe or malformed rather than guessing. yaml.safe_load already
    refuses custom tags (e.g. !!python/object); we additionally refuse
    oversized files before even opening them."""
    size = path.stat().st_size
    if size > MAX_TRACE_BYTES:
        raise ValueError(f"{path.name}: {size} bytes exceeds the {MAX_TRACE_BYTES}-byte limit")
    text = path.read_text(encoding="utf-8")
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"{path.name}: YAML parse error: {e}")
    if not isinstance(doc, dict):
        raise ValueError(f"{path.name}: top level is not a mapping")
    return doc


def discover(root: Path, include_in_progress: bool = False) -> list:
    """List candidates found directly under `root` (e.g. a traces/ dir).
    Does not recurse. Unreadable/invalid files are skipped with a note
    rather than raising, so one bad file cannot block discovery of the rest.
    """
    root = Path(root)
    out = []
    skipped = []
    if not root.is_dir():
        return out, skipped
    for p in sorted(root.glob("*.yaml")):
        try:
            doc = read_candidate(p)
        except ValueError as e:
            skipped.append({"path": str(p), "reason": str(e)})
            continue
        status = str(doc.get("status") or "unknown")
        terminal = status in TERMINAL_STATUSES
        if not terminal and not include_in_progress:
            continue
        out.append(Candidate(
            session_id=str(doc.get("session_id") or p.stem),
            path=p, status=status,
            summary=str(doc.get("summary") or "")[:160],
            updated_at=str(doc.get("updated_at") or ""),
            terminal=terminal,
        ))
    return out, skipped
