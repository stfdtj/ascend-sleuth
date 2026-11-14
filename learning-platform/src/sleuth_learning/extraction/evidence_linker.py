"""link_evidence / verify quote integrity -- generation-design.md section 3.

Linking here is simpler than the general design calls for: because
trace_adapter only ever builds an Evidence record from the very event that
carried it, every link is `relation="explicit"` by construction -- there is
no "same-event vs adjacent-event" ambiguity to resolve, and adjacent user
output is never auto-attached to a preceding command (generation-design.md
explicitly forbids that).

Quote integrity re-verification reuses the judgement from
scripts/verify_evidence.py: exact match after whitespace normalization, or
explicit `...`-delimited segments matched in order. No fuzzy/semantic
matching, no case/width normalization -- see that script's header comment
for the rationale this MVP inherits unchanged.
"""

from __future__ import annotations

from pathlib import Path

from ..model import Link, SourcePointer
from .trace_adapter import ExtractedCase


def _norm(text) -> str:
    return " ".join(str(text).split())


def _norm_segments(quote) -> list:
    return [s for s in (_norm(p) for p in str(quote).split("...")) if s]


def compare_quote(actual: str, quote: str) -> bool:
    segs = _norm_segments(quote)
    if not segs:
        return False
    a = _norm(actual)
    if len(segs) == 1:
        return segs[0] == a
    pos = 0
    for seg in segs:
        i = a.find(seg, pos)
        if i < 0:
            return False
        pos = i + len(seg)
    return True


def _step_index(evidence_id: str) -> int:
    return int(evidence_id.split("-")[1])


def link_evidence(extracted: ExtractedCase) -> None:
    """Attach each Evidence to the evidence_links of the Step that produced
    it (mutates extracted.steps in place)."""
    steps_by_index = {s.source_index: s for s in extracted.steps}
    for ev in extracted.evidence:
        idx = _step_index(ev.id)
        step = steps_by_index.get(idx)
        if step is None:
            continue
        basis = [ev.pointer] if ev.pointer else []
        step.evidence_links.append(Link(evidence_id=ev.id, relation="explicit", basis=basis))


def _blob_path(package_dir: Path, manifest: dict, file_id: str) -> Path:
    files = {f["id"]: f for f in manifest["content"]["files"]}
    f = files[file_id]
    hexdigest = f["blob_hash"].split(":", 1)[1]
    return package_dir / "blobs" / hexdigest


def verify_quotes(extracted: ExtractedCase, package_dir: Path, manifest: dict) -> None:
    """Upgrade each quote-bearing Evidence's integrity from "unchecked" to
    "quote-matched" or "mismatch" by re-reading the packaged copy of the
    referenced file at the recorded line. Mutates extracted.evidence in
    place; never touches anything outside package_dir."""
    for ev in extracted.evidence:
        if ev.integrity != "unchecked" or not ev.file_id or not ev.quote:
            continue
        if not ev.pointer or not ev.pointer.lines:
            ev.integrity = "unavailable"
            continue
        try:
            blob_path = _blob_path(package_dir, manifest, ev.file_id)
            line_no = ev.pointer.lines.get("start")
            with open(blob_path, "r", encoding="utf-8", errors="strict") as f:
                actual = None
                for i, line in enumerate(f, 1):
                    if i == line_no:
                        actual = line.rstrip("\r\n")
                        break
        except (OSError, UnicodeDecodeError, KeyError):
            ev.integrity = "unavailable"
            continue
        if actual is None:
            ev.integrity = "unavailable"
        elif compare_quote(actual, ev.quote):
            ev.integrity = "quote-matched"
        else:
            ev.integrity = "mismatch"
