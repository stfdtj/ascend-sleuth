"""Mode A (engineer-style) and Mode B (agent-style) teaching generation --
generation-design.md section 4, simplified for the offline MVP: no real
token-budget bookkeeping (the mock provider is cheap and deterministic, so
rate-limiting it would be theater) and no Wiki retrieval (no FrozenWikiIndex
exists yet -- see README "Deviations from Astra"). The structural rule that
matters is still enforced: the generator only ever returns
{cards:[{step_id,purpose,explanation,question,citations}]}; every citation
must come from the step's own already-linked evidence, so the provider
cannot invent a reference.
"""

from __future__ import annotations

from ..errors import ModelUnavailableError
from ..model import Card, SourcePointer, View


def _step_request(step, style: str) -> dict:
    citations = [p.to_dict() for link in step.evidence_links for p in link.basis]
    return {
        "style": style,
        "step": {
            "id": step.id, "role": step.role, "action": step.action,
            "output": step.output, "reason": step.reason, "missing": list(step.missing),
        },
        "allowed_citation_pointers": citations,
    }


def generate_teaching_view(extracted, provider, style: str) -> View:
    """style is "agent" or "engineer". Raises ModelUnavailableError if the
    provider refuses (e.g. NoModelProvider) -- caller decides whether to
    fall back to an "unavailable" View or propagate the error."""
    cards = []
    for step in extracted.steps:
        request = _step_request(step, style)
        result = provider.generate(request)
        for c in result.get("cards") or []:
            citations = [SourcePointer.from_dict(p) for p in c.get("citations") or []]
            cards.append(Card(
                step_id=c.get("step_id") or step.id, purpose=c.get("purpose"),
                explanation=c.get("explanation"), question=c.get("question"),
                origin="reconstructed", citations=citations,
            ))
    return View(style=style, state="available", reason=None, cards=cards)


def unavailable_view(style: str, reason: str) -> View:
    return View(style=style, state="unavailable", reason=reason, cards=[])


def generate_view_or_unavailable(extracted, provider, style: str) -> View:
    if provider is None:
        return unavailable_view(style, "no model configured; run generate with --model mock "
                                        "to produce this view, or use mode=replay")
    try:
        return generate_teaching_view(extracted, provider, style)
    except ModelUnavailableError as e:
        return unavailable_view(style, str(e))
