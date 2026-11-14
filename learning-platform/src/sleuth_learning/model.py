"""Learning Case object model -- data-contracts.md section 3, adapted for an
offline MVP with no server/SQLite layer (see README "Deviations from Astra").

These are plain dataclasses with to_dict()/from_dict(); schema/enum
enforcement lives in extraction.validation, not here, so partially-built
objects can exist during construction (e.g. while assembling a Step before
its evidence_links are linked).

One deliberate field deviation: data-contracts.md's Step has no `content`
field, written for traces where every event already has a uniform `output`.
The actual diagnose trace schema (skills/diagnose/references/diagnosis-trace.md)
gives `user` events a `content` field and `agent` events `output`/`reason`
instead. Step.output is populated from whichever the source event has, and
Step.role tells a reader which one it was -- see extraction/trace_adapter.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


def _clean(d):
    if isinstance(d, dict):
        return {k: _clean(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_clean(v) for v in d]
    return d


@dataclass
class SourcePointer:
    file_id: str
    json_pointer: Optional[str] = None
    lines: Optional[dict] = None  # {"start": int, "end": int}

    def to_dict(self):
        return _clean(asdict(self))

    @staticmethod
    def from_dict(d):
        return SourcePointer(file_id=d["file_id"], json_pointer=d.get("json_pointer"),
                              lines=d.get("lines"))


@dataclass
class Evidence:
    id: str
    file_id: Optional[str]
    pointer: Optional[SourcePointer]
    quote: Optional[str]
    lineage: dict  # {"original_lines": {...} | None, "transformed": bool}
    integrity: str  # unchecked | hash-checked | quote-matched | mismatch | unavailable
    support: str  # unassessed | observation-only | corroborated | disputed
    access_class: str = "internal"

    def to_dict(self):
        d = asdict(self)
        d["pointer"] = self.pointer.to_dict() if self.pointer else None
        return _clean(d)

    @staticmethod
    def from_dict(d):
        p = d.get("pointer")
        return Evidence(id=d["id"], file_id=d.get("file_id"),
                         pointer=SourcePointer.from_dict(p) if p else None,
                         quote=d.get("quote"), lineage=d.get("lineage") or {},
                         integrity=d.get("integrity", "unchecked"),
                         support=d.get("support", "unassessed"),
                         access_class=d.get("access_class", "internal"))


@dataclass
class Command:
    text: str
    source: SourcePointer
    execution: str  # suggested | recorded-tool-call | execution-confirmed | unknown
    output_evidence_ids: list = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        d["source"] = self.source.to_dict()
        return _clean(d)

    @staticmethod
    def from_dict(d):
        return Command(text=d["text"], source=SourcePointer.from_dict(d["source"]),
                        execution=d.get("execution", "unknown"),
                        output_evidence_ids=list(d.get("output_evidence_ids") or []))


@dataclass
class Link:
    evidence_id: str
    relation: str  # explicit | source-contained | unresolved
    basis: list = field(default_factory=list)  # list[SourcePointer]

    def to_dict(self):
        return {"evidence_id": self.evidence_id, "relation": self.relation,
                "basis": [p.to_dict() for p in self.basis]}

    @staticmethod
    def from_dict(d):
        return Link(evidence_id=d["evidence_id"], relation=d.get("relation", "unresolved"),
                    basis=[SourcePointer.from_dict(p) for p in (d.get("basis") or [])])


@dataclass
class Step:
    id: str
    source_index: int
    source_pointer: SourcePointer
    role: str  # as recorded in the source trace (user | agent)
    action: Optional[str]
    output: Optional[str]
    reason: Optional[str]
    observed_at: Optional[str] = None
    known_at: Optional[str] = None
    time_basis: list = field(default_factory=list)
    commands: list = field(default_factory=list)  # list[Command]
    evidence_links: list = field(default_factory=list)  # list[Link]
    case_refs: list = field(default_factory=list)  # list[SourcePointer]
    missing: list = field(default_factory=list)

    def to_dict(self):
        return {
            "id": self.id, "source_index": self.source_index,
            "source_pointer": self.source_pointer.to_dict(),
            "role": self.role, "action": self.action, "output": self.output,
            "reason": self.reason, "observed_at": self.observed_at,
            "known_at": self.known_at,
            "time_basis": [p.to_dict() for p in self.time_basis],
            "commands": [c.to_dict() for c in self.commands],
            "evidence_links": [l.to_dict() for l in self.evidence_links],
            "case_refs": [p.to_dict() for p in self.case_refs],
            "missing": list(self.missing),
        }

    @staticmethod
    def from_dict(d):
        return Step(
            id=d["id"], source_index=d["source_index"],
            source_pointer=SourcePointer.from_dict(d["source_pointer"]),
            role=d["role"], action=d.get("action"), output=d.get("output"),
            reason=d.get("reason"), observed_at=d.get("observed_at"),
            known_at=d.get("known_at"),
            time_basis=[SourcePointer.from_dict(p) for p in (d.get("time_basis") or [])],
            commands=[Command.from_dict(c) for c in (d.get("commands") or [])],
            evidence_links=[Link.from_dict(l) for l in (d.get("evidence_links") or [])],
            case_refs=[SourcePointer.from_dict(p) for p in (d.get("case_refs") or [])],
            missing=list(d.get("missing") or []),
        )


@dataclass
class Generator:
    mode: str  # replay | mock | agent | engineer
    version: str
    prompt_hash: Optional[str]
    model_id: Optional[str]
    parameters_hash: str
    dependency_hashes: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        return Generator(**d)


@dataclass
class Applicability:
    platforms: list
    versions: list
    assessment: str  # unknown | matched | mismatched | conflicting
    basis: list = field(default_factory=list)

    def to_dict(self):
        return {"platforms": list(self.platforms), "versions": list(self.versions),
                "assessment": self.assessment, "basis": [p.to_dict() for p in self.basis]}

    @staticmethod
    def from_dict(d):
        return Applicability(platforms=list(d.get("platforms") or []),
                              versions=list(d.get("versions") or []),
                              assessment=d.get("assessment", "unknown"),
                              basis=[SourcePointer.from_dict(p) for p in (d.get("basis") or [])])


@dataclass
class Diagnosis:
    source_status: Optional[str]
    feedback_outcome: Optional[str]
    stop_reason: Optional[str]
    teaching_class: str  # incomplete | success-reported | failure | undetermined
    basis: list = field(default_factory=list)

    def to_dict(self):
        return {"source_status": self.source_status, "feedback_outcome": self.feedback_outcome,
                "stop_reason": self.stop_reason, "teaching_class": self.teaching_class,
                "basis": [p.to_dict() for p in self.basis]}

    @staticmethod
    def from_dict(d):
        return Diagnosis(source_status=d.get("source_status"),
                          feedback_outcome=d.get("feedback_outcome"),
                          stop_reason=d.get("stop_reason"),
                          teaching_class=d.get("teaching_class", "undetermined"),
                          basis=[SourcePointer.from_dict(p) for p in (d.get("basis") or [])])


@dataclass
class Card:
    step_id: str
    purpose: Optional[str]
    explanation: Optional[str]
    question: Optional[str]
    origin: str  # recorded-agent | recorded-human | reconstructed
    citations: list = field(default_factory=list)  # list[SourcePointer]
    applicability: Optional[Applicability] = None

    def to_dict(self):
        return {"step_id": self.step_id, "purpose": self.purpose,
                "explanation": self.explanation, "question": self.question,
                "origin": self.origin, "citations": [p.to_dict() for p in self.citations],
                "applicability": self.applicability.to_dict() if self.applicability else None}

    @staticmethod
    def from_dict(d):
        a = d.get("applicability")
        return Card(step_id=d["step_id"], purpose=d.get("purpose"),
                    explanation=d.get("explanation"), question=d.get("question"),
                    origin=d.get("origin", "reconstructed"),
                    citations=[SourcePointer.from_dict(p) for p in (d.get("citations") or [])],
                    applicability=Applicability.from_dict(a) if a else None)


@dataclass
class View:
    style: str  # replay | agent | engineer
    state: str  # available | unavailable
    reason: Optional[str]
    cards: list = field(default_factory=list)  # list[Card]

    def to_dict(self):
        return {"style": self.style, "state": self.state, "reason": self.reason,
                "cards": [c.to_dict() for c in self.cards]}

    @staticmethod
    def from_dict(d):
        return View(style=d["style"], state=d.get("state", "unavailable"),
                    reason=d.get("reason"),
                    cards=[Card.from_dict(c) for c in (d.get("cards") or [])])


@dataclass
class Finding:
    code: str
    severity: str  # error | warning | review
    pointer: str
    message: str

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        return Finding(**d)


@dataclass
class LearningCase:
    schema_version: str
    id: str
    revision: int
    snapshot_hash: str
    source_identity: dict
    generator: Generator
    title: str
    applicability: Applicability
    diagnosis: Diagnosis
    steps: list  # list[Step]
    evidence: list  # list[Evidence]
    views: list  # list[View]
    validation: list  # list[Finding]
    created_at: str

    def to_dict(self):
        return {
            "schema_version": self.schema_version, "id": self.id, "revision": self.revision,
            "snapshot_hash": self.snapshot_hash, "source_identity": dict(self.source_identity),
            "generator": self.generator.to_dict(), "title": self.title,
            "applicability": self.applicability.to_dict(), "diagnosis": self.diagnosis.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
            "evidence": [e.to_dict() for e in self.evidence],
            "views": [v.to_dict() for v in self.views],
            "validation": [f.to_dict() for f in self.validation],
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d):
        return LearningCase(
            schema_version=d["schema_version"], id=d["id"], revision=d["revision"],
            snapshot_hash=d["snapshot_hash"], source_identity=dict(d.get("source_identity") or {}),
            generator=Generator.from_dict(d["generator"]), title=d["title"],
            applicability=Applicability.from_dict(d["applicability"]),
            diagnosis=Diagnosis.from_dict(d["diagnosis"]),
            steps=[Step.from_dict(s) for s in d.get("steps") or []],
            evidence=[Evidence.from_dict(e) for e in d.get("evidence") or []],
            views=[View.from_dict(v) for v in d.get("views") or []],
            validation=[Finding.from_dict(f) for f in d.get("validation") or []],
            created_at=d["created_at"],
        )
