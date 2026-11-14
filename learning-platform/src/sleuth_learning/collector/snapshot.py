"""Source Snapshot -- generation-design.md section 1 (plan_sources /
capture_stable / project_snapshot), scoped for an offline, single-machine MVP.

Safety invariants enforced here:
  - every referenced evidence path must resolve inside an explicit
    `allow_root` (no path traversal, no absolute paths, no symlinks);
  - the source trace file is never modified (read-only open, copy-out only);
  - omissions are always recorded with a reason -- never silently dropped.

What this does NOT provide (see README "Deviations from Astra"): a real
filesystem transactional snapshot. `capture_stable` does a double-stat +
short settle window, which catches concurrent edits in the common case but
is not a guarantee -- same admission generation-design.md itself makes.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..errors import PathSafetyError, SourceUnstableError

MAX_EVIDENCE_BYTES = 10 * 1024 * 1024  # data-contracts.md section 2: 10 MiB/file
MEDIA_TYPES = {
    ".txt": "text/plain", ".log": "text/plain", ".md": "text/markdown",
    ".json": "application/json", "": "text/plain",
}
OMIT_REASONS = {"missing", "permission-denied", "not-selected", "not-authorized",
                 "too-large", "unsupported", "unstable"}


@dataclass
class ResolvedFile:
    ref: str  # as written in the trace (original relative path)
    abs_path: Path
    size: int


@dataclass
class Omission:
    source_pointer: str
    reason: str

    def to_dict(self):
        assert self.reason in OMIT_REASONS
        return {"source_pointer": self.source_pointer, "reason": self.reason}


@dataclass
class SourcePlan:
    trace_path: Path
    resolved: list = field(default_factory=list)  # list[ResolvedFile]
    omitted: list = field(default_factory=list)  # list[Omission]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _has_symlink_component(path: Path, root: Path) -> bool:
    """True if `path` or any ancestor between it and `root` is a symlink."""
    cur = path
    while True:
        try:
            if cur.is_symlink():
                return True
        except OSError:
            return True
        if cur == root or cur.parent == cur:
            return False
        cur = cur.parent


def resolve_ref(ref: str, allow_root: Path) -> Path:
    """Resolve a trace-recorded evidence path against allow_root, rejecting
    absolute paths and traversal outside the root. Raises PathSafetyError;
    callers that want a soft "omit" instead should catch it."""
    raw = str(ref or "").strip().replace("\\", "/")
    if not raw:
        raise PathSafetyError("empty evidence reference")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        raise PathSafetyError(f"absolute paths are not accepted as evidence refs: {ref!r}")
    allow_root = allow_root.resolve()
    candidate = (allow_root / raw).resolve()
    if not _is_within(candidate, allow_root):
        raise PathSafetyError(f"evidence ref escapes allow-root: {ref!r}")
    if candidate.exists() and _has_symlink_component(candidate, allow_root):
        raise PathSafetyError(f"evidence ref resolves through a symlink: {ref!r}")
    return candidate


def iter_evidence_refs(trace_doc: dict):
    """Yield every evidence.files[] reference from `user` events, in the
    order they appear (duplicates kept -- dedup is the caller's choice)."""
    for event in trace_doc.get("trace") or []:
        if not isinstance(event, dict):
            continue
        evidence = event.get("evidence")
        if not isinstance(evidence, dict):
            continue
        files = evidence.get("files")
        if isinstance(files, str):
            files = [files]
        for f in files or []:
            yield str(f)


def plan_sources(trace_doc: dict, trace_path: Path, allow_root: Path) -> SourcePlan:
    plan = SourcePlan(trace_path=trace_path)
    seen = set()
    for ref in iter_evidence_refs(trace_doc):
        if ref in seen:
            continue
        seen.add(ref)
        try:
            abs_path = resolve_ref(ref, allow_root)
        except PathSafetyError:
            plan.omitted.append(Omission(ref, "not-authorized"))
            continue
        if not abs_path.exists() or not abs_path.is_file():
            plan.omitted.append(Omission(ref, "missing"))
            continue
        try:
            size = abs_path.stat().st_size
        except OSError:
            plan.omitted.append(Omission(ref, "permission-denied"))
            continue
        if size > MAX_EVIDENCE_BYTES:
            plan.omitted.append(Omission(ref, "too-large"))
            continue
        if abs_path.suffix.lower() not in MEDIA_TYPES:
            plan.omitted.append(Omission(ref, "unsupported"))
            continue
        plan.resolved.append(ResolvedFile(ref=ref, abs_path=abs_path, size=size))
    return plan


def _fingerprint(path: Path) -> tuple:
    st = path.stat()
    return (st.st_size, st.st_mtime_ns)


def capture_stable(plan: SourcePlan, staging_dir: Path, settle_seconds: float = 0.2,
                   retries: int = 3) -> dict:
    """Copy every planned file into staging_dir, verifying a stable fingerprint
    (size + mtime_ns) before and after the copy, with a short settle window
    and limited retries. Returns {"trace_text": str, "files": [{ref, staged_path, size}]}.
    Never writes to any of the original source paths.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    all_paths = [plan.trace_path] + [r.abs_path for r in plan.resolved]

    for attempt in range(1, retries + 1):
        before = {p: _fingerprint(p) for p in all_paths}
        trace_text = plan.trace_path.read_text(encoding="utf-8")
        staged_files = []
        ok = True
        for r in plan.resolved:
            dst = staging_dir / f"ev-{len(staged_files)}{r.abs_path.suffix}"
            try:
                data = r.abs_path.read_bytes()
            except OSError:
                ok = False
                break
            dst.write_bytes(data)
            staged_files.append({"ref": r.ref, "staged_path": dst, "size": len(data)})
        if ok:
            time.sleep(settle_seconds)
            after = {p: _fingerprint(p) for p in all_paths if p.exists()}
            if after == before and len(after) == len(all_paths):
                return {"trace_text": trace_text, "files": staged_files}
        for f in staged_files:
            try:
                os.remove(f["staged_path"])
            except OSError:
                pass
    raise SourceUnstableError(
        f"source files changed while capturing a stable snapshot after {retries} attempts "
        f"(SOURCE_BUSY) -- not uploading; try again once the trace is not being edited")
