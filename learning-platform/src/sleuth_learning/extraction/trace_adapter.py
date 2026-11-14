"""extract(package) -> ExtractedCase -- generation-design.md section 2,
adapted to the real diagnose trace schema in
skills/diagnose/references/diagnosis-trace.md (role: user|agent; user events
carry `content` + `evidence`; agent events carry `action`/`output`/`reason`
and action-specific fields such as `case`, `candidates`, `tool_calls`).

Never modifies the package. Every `trace[]` array index becomes exactly one
Step, regardless of whether its role/action is recognized -- coverage must
never drop an event just because a field was unfamiliar (generation-design.md
section 5, "coverage").
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..model import Applicability, Command, Diagnosis, Evidence, SourcePointer, Step
from ..collector.snapshot import iter_evidence_refs

TERMINAL_STATUSES = {"resolved", "escalated", "archived"}


@dataclass
class ExtractedCase:
    session_id: str
    title: str
    steps: list  # list[Step]
    evidence: list  # list[Evidence]
    applicability: Applicability
    diagnosis: Diagnosis
    source_event_count: int = 0
    warnings: list = field(default_factory=list)


def _load_trace_json(package_dir: Path, manifest: dict) -> dict:
    files = {f["id"]: f for f in manifest["content"]["files"]}
    trace_file = files["trace"]
    hexdigest = trace_file["blob_hash"].split(":", 1)[1]
    blob = package_dir / "blobs" / hexdigest
    return json.loads(blob.read_text(encoding="utf-8"))


def _ref_to_file_id(trace_doc: dict, manifest: dict) -> dict:
    """Reconstruct which packaged evidence file id a trace-recorded path maps
    to, by replaying the same dedup-by-first-seen order the collector used
    when it walked evidence.files (collector.snapshot.iter_evidence_refs /
    plan_sources) -- the manifest itself carries no such mapping, since
    data-contracts.md's file-entry schema has no room for one.
    """
    omitted_refs = {o["source_pointer"] for o in manifest["content"]["omitted"]}
    seen = set()
    included_order = []
    for ref in iter_evidence_refs(trace_doc):
        if ref in seen:
            continue
        seen.add(ref)
        if ref not in omitted_refs:
            included_order.append(ref)
    file_ids = [f["id"] for f in manifest["content"]["files"] if f["kind"] == "evidence"]
    return dict(zip(included_order, file_ids))


def _sp(file_id: str, pointer: Optional[str] = None, lines: Optional[dict] = None) -> SourcePointer:
    return SourcePointer(file_id=file_id, json_pointer=pointer, lines=lines)


def _clip(text, limit: int = 2000) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _extract_evidence_for_event(idx: int, event: dict, ref_to_file_id: dict) -> tuple:
    """-> (evidence_list, missing_notes) for one user event."""
    ev_out, missing = [], []
    evd = event.get("evidence")
    if not isinstance(evd, dict):
        return ev_out, missing

    inline = evd.get("inline")
    if inline:
        ev_out.append(Evidence(
            id=f"e-{idx}-inline", file_id=None, pointer=None, quote=_clip(inline),
            lineage={"original_lines": None, "transformed": False},
            integrity="unavailable", support="observation-only",
        ))

    files = evd.get("files")
    if isinstance(files, str):
        files = [files]
    for j, ref in enumerate(files or []):
        file_id = ref_to_file_id.get(str(ref))
        if file_id is None:
            missing.append(f"referenced evidence file not in package: {ref}")
            ev_out.append(Evidence(
                id=f"e-{idx}-file-{j}", file_id=None, pointer=None, quote=None,
                lineage={"original_lines": None, "transformed": False},
                integrity="unavailable", support="observation-only",
            ))
            continue
        ev_out.append(Evidence(
            id=f"e-{idx}-file-{j}", file_id=file_id,
            pointer=_sp(file_id), quote=None,
            lineage={"original_lines": None, "transformed": False},
            integrity="unchecked", support="observation-only",
        ))

    quotes = evd.get("quotes")
    for k, q in enumerate(quotes or []):
        if not isinstance(q, dict):
            continue
        file_id = ref_to_file_id.get(str(q.get("file") or ""))
        line = q.get("line")
        lines = {"start": line, "end": line} if isinstance(line, int) else None
        ev_out.append(Evidence(
            id=f"e-{idx}-quote-{k}", file_id=file_id,
            pointer=_sp(file_id, lines=lines) if file_id else None,
            quote=str(q.get("quote") or ""),
            lineage={"original_lines": lines, "transformed": False},
            integrity="unchecked" if file_id else "unavailable",
            support="observation-only",
        ))

    sources = evd.get("sources")
    for k, url in enumerate(sources or []):
        ev_out.append(Evidence(
            id=f"e-{idx}-source-{k}", file_id=None, pointer=None, quote=str(url),
            lineage={"original_lines": None, "transformed": False},
            integrity="unavailable", support="observation-only",
        ))

    raw_missing = evd.get("missing")
    if raw_missing:
        missing.append(str(raw_missing))
    return ev_out, missing


def _extract_commands(idx: int, event: dict) -> list:
    """Only lifts commands from fields explicitly meant to record tool use
    (`tool_calls`, per diagnosis-trace.md's source_analysis convention) --
    never invents a Command from free text in `output`/`reason`."""
    calls = event.get("tool_calls")
    if not isinstance(calls, list):
        return []
    out = []
    for i, item in enumerate(calls):
        out.append(Command(
            text=str(item), source=_sp("trace", pointer=f"/trace/{idx}/tool_calls/{i}"),
            execution="unknown",
        ))
    return out


def extract(package_dir: Path, manifest: dict, platform_registry: Optional[dict] = None) -> ExtractedCase:
    """`platform_registry`, if given, is {case_id: [platform, ...]} of
    explicitly-authorized known-applicable platforms -- the offline stand-in
    for generation-design.md's FrozenWikiIndex/retrieve_wiki (no real Wiki
    integration exists in this MVP; see README). When the trace's hit case
    is in the registry, applicability is "matched" or "conflicting" against
    it; machine code never promotes an unknown case to "matched" on its own.
    """
    trace_doc = _load_trace_json(package_dir, manifest)
    ref_to_file_id = _ref_to_file_id(trace_doc, manifest)
    warnings = []

    steps, evidence = [], []
    events = trace_doc.get("trace")
    if not isinstance(events, list):
        warnings.append("source trace has no trace[] array; producing zero steps")
        events = []

    for idx, event in enumerate(events):
        if not isinstance(event, dict):
            steps.append(Step(id=f"s-{idx}", source_index=idx,
                              source_pointer=_sp("trace", pointer=f"/trace/{idx}"),
                              role="unknown", action=None, output=None, reason=None,
                              missing=["trace event was not a mapping"]))
            continue
        role = str(event.get("role") or "unknown")
        action = event.get("action")
        if role == "user":
            text_payload = event.get("content")
            reason = None
        else:
            text_payload = event.get("output")
            reason = event.get("reason")

        step_evidence, missing = _extract_evidence_for_event(idx, event, ref_to_file_id)
        evidence.extend(step_evidence)

        if action is not None and action not in KNOWN_ACTIONS:
            warnings.append(f"step {idx}: unrecognized action {action!r} kept as-is")

        steps.append(Step(
            id=f"s-{idx}", source_index=idx,
            source_pointer=_sp("trace", pointer=f"/trace/{idx}"),
            role=role, action=action,
            output=_clip(text_payload) if text_payload is not None else None,
            reason=_clip(reason) if reason is not None else None,
            commands=_extract_commands(idx, event),
            missing=missing,
        ))

    session_id = str(trace_doc.get("session_id") or "")
    status = trace_doc.get("status")
    feedback = trace_doc.get("feedback") or {}
    outcome = feedback.get("outcome") if isinstance(feedback, dict) else None
    if outcome == "resolved":
        teaching_class = "success-reported"
    elif outcome == "not_resolved":
        teaching_class = "failure"
    elif status == "in_progress" or status is None:
        teaching_class = "incomplete"
    else:
        teaching_class = "undetermined"

    diagnosis = Diagnosis(
        source_status=status, feedback_outcome=outcome,
        stop_reason=trace_doc.get("stop_reason") or None,
        teaching_class=teaching_class,
        basis=[_sp("trace", pointer="/status"), _sp("trace", pointer="/feedback/outcome")],
    )

    platform = trace_doc.get("detected_platform")
    active_case = trace_doc.get("active_case")
    assessment = "matched" if active_case else "unknown"
    if active_case and platform_registry and active_case in platform_registry:
        known = set(platform_registry[active_case])
        assessment = "matched" if platform in known else "conflicting"
    applicability = Applicability(
        platforms=[platform] if platform else [],
        versions=[],
        assessment=assessment,
        basis=[_sp("trace", pointer="/detected_platform"), _sp("trace", pointer="/active_case")],
    )

    title = (str(trace_doc.get("summary") or "")[:120] or session_id or "Untitled learning case")

    return ExtractedCase(session_id=session_id, title=title, steps=steps, evidence=evidence,
                         applicability=applicability, diagnosis=diagnosis,
                         source_event_count=len(events), warnings=warnings)


KNOWN_ACTIONS = {
    "triage", "load_index", "quickly_check", "load_full", "run_check", "hit", "miss", "tier3",
    "feedback", "reference_lookup", "triage_semantic", "source_analysis", "attribution", "resume",
    "procedure_follow", "report", "external_lookup",
}
