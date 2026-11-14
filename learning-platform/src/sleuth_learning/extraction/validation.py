"""validate_artifact -- generation-design.md section 5: schema, pointer,
quote, coverage, binding, applicability, generated_claims checks, in that
order. Machine validation passing never means the diagnosis is correct --
only that the artifact's shape and references are internally consistent.
"""

from __future__ import annotations

from pathlib import Path

from ..model import Finding, LearningCase

GENERATOR_MODES = {"replay", "mock", "agent", "engineer"}
TEACHING_CLASSES = {"incomplete", "success-reported", "failure", "undetermined"}
ASSESSMENTS = {"unknown", "matched", "mismatched", "conflicting"}
INTEGRITY_VALUES = {"unchecked", "hash-checked", "quote-matched", "mismatch", "unavailable"}
SUPPORT_VALUES = {"unassessed", "observation-only", "corroborated", "disputed"}
VIEW_STYLES = {"replay", "agent", "engineer"}
VIEW_STATES = {"available", "unavailable"}


def _err(code, pointer, message):
    return Finding(code=code, severity="error", pointer=pointer, message=message)


def _review(code, pointer, message):
    return Finding(code=code, severity="review", pointer=pointer, message=message)


def _warn(code, pointer, message):
    return Finding(code=code, severity="warning", pointer=pointer, message=message)


def _check_schema(case: LearningCase) -> list:
    out = []
    if case.generator.mode not in GENERATOR_MODES:
        out.append(_err("schema", "/generator/mode", f"unknown generator.mode: {case.generator.mode!r}"))
    if case.diagnosis.teaching_class not in TEACHING_CLASSES:
        out.append(_err("schema", "/diagnosis/teaching_class",
                        f"unknown teaching_class: {case.diagnosis.teaching_class!r}"))
    if case.applicability.assessment not in ASSESSMENTS:
        out.append(_err("schema", "/applicability/assessment",
                        f"unknown assessment: {case.applicability.assessment!r}"))
    for i, ev in enumerate(case.evidence):
        if ev.integrity not in INTEGRITY_VALUES:
            out.append(_err("schema", f"/evidence/{i}/integrity", f"unknown integrity: {ev.integrity!r}"))
        if ev.support not in SUPPORT_VALUES:
            out.append(_err("schema", f"/evidence/{i}/support", f"unknown support: {ev.support!r}"))
    for i, v in enumerate(case.views):
        if v.style not in VIEW_STYLES:
            out.append(_err("schema", f"/views/{i}/style", f"unknown view style: {v.style!r}"))
        if v.state not in VIEW_STATES:
            out.append(_err("schema", f"/views/{i}/state", f"unknown view state: {v.state!r}"))
    return out


def _check_pointer(case: LearningCase, file_ids: set) -> list:
    out = []
    for i, ev in enumerate(case.evidence):
        if ev.file_id is not None and ev.file_id not in file_ids:
            out.append(_err("pointer", f"/evidence/{i}", f"file_id {ev.file_id!r} not in package"))
    for i, step in enumerate(case.steps):
        if step.source_pointer.file_id not in file_ids:
            out.append(_err("pointer", f"/steps/{i}/source_pointer",
                            f"file_id {step.source_pointer.file_id!r} not in package"))
        for j, cmd in enumerate(step.commands):
            if cmd.source.file_id not in file_ids:
                out.append(_err("pointer", f"/steps/{i}/commands/{j}",
                                f"file_id {cmd.source.file_id!r} not in package"))
    return out


def _check_quote(case: LearningCase) -> list:
    out = []
    for i, ev in enumerate(case.evidence):
        if ev.integrity == "mismatch":
            out.append(_err("quote", f"/evidence/{i}",
                            "quote does not match the packaged source file; this evidence "
                            "cannot support any conclusion until re-verified"))
    return out


def _check_coverage(case: LearningCase, source_event_count: int) -> list:
    out = []
    seen = {}
    for i, step in enumerate(case.steps):
        seen.setdefault(step.source_index, []).append(i)
    for idx in range(source_event_count):
        hits = seen.get(idx, [])
        if not hits:
            out.append(_err("coverage", f"/trace/{idx}", f"no Step covers source trace index {idx}"))
        elif len(hits) > 1:
            out.append(_err("coverage", f"/trace/{idx}",
                            f"source trace index {idx} is covered by {len(hits)} Steps"))
    extra = {k for k in seen if k >= source_event_count or k < 0}
    for idx in sorted(extra):
        out.append(_err("coverage", f"/steps/source_index={idx}",
                        "Step references a source_index outside the source trace"))
    return out


def _check_binding(case: LearningCase, manifest: dict) -> list:
    out = []
    if case.snapshot_hash != manifest["snapshot_hash"]:
        out.append(_err("binding", "/snapshot_hash",
                        "LearningCase.snapshot_hash does not match the ingested package's "
                        "snapshot_hash"))
    return out


def _check_applicability(case: LearningCase) -> list:
    out = []
    if case.applicability.assessment in ("mismatched", "conflicting"):
        out.append(_review("applicability", "/applicability",
                           f"applicability is {case.applicability.assessment!r} -- needs human "
                           f"review before this case is treated as applicable"))
    return out


def _check_generated_claims(case: LearningCase, file_ids: set) -> list:
    """Citations are SourcePointers into the package (same file_id space as
    Step.source_pointer / Evidence.pointer) -- they are not Evidence ids, so
    they must be checked against the package's file ids, not evidence ids."""
    out = []
    for vi, view in enumerate(case.views):
        for ci, card in enumerate(view.cards):
            where = f"/views/{vi}/cards/{ci}"
            if card.explanation and not card.citations:
                out.append(_review("generated-claims", where,
                                   "card has an explanation but no citations -- needs human "
                                   "review of whether the explanation is grounded"))
            for pi, ptr in enumerate(card.citations):
                if ptr.file_id not in file_ids:
                    out.append(_err("generated-claims", f"{where}/citations/{pi}",
                                    f"citation references unknown id {ptr.file_id!r}"))
    return out


def validate_artifact(case: LearningCase, *, package_dir: Path, manifest: dict,
                      source_event_count: int) -> list:
    file_ids = {f["id"] for f in manifest["content"]["files"]}
    findings = []
    findings += _check_schema(case)
    findings += _check_pointer(case, file_ids)
    findings += _check_quote(case)
    findings += _check_coverage(case, source_event_count)
    findings += _check_binding(case, manifest)
    findings += _check_applicability(case)
    findings += _check_generated_claims(case, file_ids)
    return findings


def has_blocking_errors(findings: list) -> bool:
    return any(f.severity == "error" for f in findings)
