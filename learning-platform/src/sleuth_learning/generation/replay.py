"""Mode C -- deterministic replay. generation-design.md section 4: "replay
完全不用模型" (replay uses no model at all). This is the one generation
mode guaranteed to work with no model configured, and the task's required
baseline ("must function without any LLM and must be implemented first").

A replay Card never adds anything -- explanation is exactly the step's own
recorded `reason` (when the source trace wrote one), never a paraphrase.
"""

from __future__ import annotations

from ..model import Card, View


def generate_replay_view(extracted) -> View:
    cards = []
    for step in extracted.steps:
        citations = [p for link in step.evidence_links for p in link.basis]
        explanation = step.reason if step.role == "agent" else None
        origin = "recorded-agent" if step.role == "agent" else "recorded-human"
        cards.append(Card(step_id=step.id, purpose=None, explanation=explanation,
                          question=None, origin=origin, citations=citations))
    return View(style="replay", state="available", reason=None, cards=cards)
