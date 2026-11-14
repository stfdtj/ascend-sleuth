"""Content hashing helpers, matching data-contracts.md section 1:
content digest = sha256:<64 lowercase hex>; JSON digests use UTF-8, sorted
keys, no extra whitespace, no NaN, stable array order."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HASH_PREFIX = "sha256:"
CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return HASH_PREFIX + h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return HASH_PREFIX + hashlib.sha256(data).hexdigest()


def canonical_json(value) -> str:
    """Sorted-key, no-whitespace JSON text. Rejects float NaN/Infinity by
    construction (json.dumps with allow_nan=False)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def content_hash(value) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def short(h: str, n: int = 12) -> str:
    """Short display form, e.g. sha256:ab12cd34ef56... for logs/CLI output."""
    if h.startswith(HASH_PREFIX):
        return HASH_PREFIX + h[len(HASH_PREFIX):len(HASH_PREFIX) + n] + "…"
    return h
