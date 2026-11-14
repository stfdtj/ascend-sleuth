"""Program-assembled LearningCase from an ExtractedCase + generated Views --
generation-design.md section 5, "程序组装原始字段" (the program copies raw
fields; a model/mock only ever contributes Card content). Nothing here calls
a model; it only wires together what extraction and generation already
produced.
"""

from __future__ import annotations

import time
import uuid

from ..hashing import content_hash
from ..model import Generator, LearningCase

SCHEMA = "learning-case/1"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_generator(mode: str, *, provider=None, prompt_hash: str = None) -> Generator:
    model_id = getattr(provider, "model_id", None) if provider else None
    return Generator(
        mode=mode, version="1",
        prompt_hash=prompt_hash if provider else None,
        model_id=model_id,
        parameters_hash=content_hash({"mode": mode}),
        dependency_hashes=[],
    )


def assemble_case(extracted, manifest: dict, mode: str, views: list, *,
                  case_id: str = None, revision: int = 1, provider=None,
                  prompt_hash: str = None) -> LearningCase:
    return LearningCase(
        schema_version=SCHEMA,
        id=case_id or str(uuid.uuid4()),
        revision=revision,
        snapshot_hash=manifest["snapshot_hash"],
        source_identity=dict(manifest["content"]["source_identity"]),
        generator=build_generator(mode, provider=provider, prompt_hash=prompt_hash),
        title=extracted.title,
        applicability=extracted.applicability,
        diagnosis=extracted.diagnosis,
        steps=extracted.steps,
        evidence=extracted.evidence,
        views=views,
        validation=[],
        created_at=_now_iso(),
    )
