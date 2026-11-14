"""Collector Package -- data-contracts.md section 2, adapted for local disk
(no transport.py / HTTP upload layer in this MVP -- see README "Deviations
from Astra"). manifest.json + blobs/<sha256hex>, not a ZIP, so integrity can
be re-checked blob by blob.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from ..errors import IntegrityError, SchemaError
from ..hashing import HASH_PREFIX, content_hash, sha256_bytes
from .snapshot import MEDIA_TYPES, SourcePlan

SCHEMA = "learning-package/1"
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_FILES = 200
ALLOWED_MEDIA_TYPES = {"application/json", "text/plain", "text/markdown"}
ALLOWED_KINDS = {"trace", "evidence", "wiki", "case", "postmortem", "reference"}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write_blob(blobs_dir: Path, data: bytes) -> tuple:
    h = sha256_bytes(data)
    hexdigest = h[len(HASH_PREFIX):]
    blobs_dir.mkdir(parents=True, exist_ok=True)
    dst = blobs_dir / hexdigest
    if not dst.exists():
        tmp = dst.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(dst)
    return h, len(data)


def project_and_seal(captured: dict, plan: SourcePlan, out_dir: Path, *,
                     session_id: str, origin_id: Optional[str] = None,
                     lineage_id: Optional[str] = None, synthetic: bool = True,
                     authorization_ref: str = "local-cli") -> dict:
    """Project the captured snapshot into package files, then seal it into a
    manifest.json with a snapshot_hash covering `content`. Returns the
    manifest dict (also written to out_dir/manifest.json)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    blobs_dir = out_dir / "blobs"

    trace_obj = yaml.safe_load(captured["trace_text"])
    trace_json = json.dumps(trace_obj, ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8")
    trace_hash, trace_bytes = _write_blob(blobs_dir, trace_json)

    files = [{
        "id": "trace", "path": "source/trace.json", "blob_hash": trace_hash,
        "bytes": trace_bytes, "media_type": "application/json", "kind": "trace",
    }]
    for i, f in enumerate(captured["files"]):
        staged_path = Path(f["staged_path"])
        data = staged_path.read_bytes()
        blob_hash, nbytes = _write_blob(blobs_dir, data)
        media_type = MEDIA_TYPES.get(staged_path.suffix.lower(), "text/plain")
        files.append({
            "id": f"ev-{i}", "path": f"source/evidence/ev-{i}/{Path(f['ref']).name}",
            "blob_hash": blob_hash, "bytes": nbytes, "media_type": media_type, "kind": "evidence",
        })

    total_bytes = sum(x["bytes"] for x in files)
    if len(files) > MAX_FILES:
        raise SchemaError(f"package has {len(files)} files, exceeding the {MAX_FILES} limit")
    if total_bytes > MAX_TOTAL_BYTES:
        raise SchemaError(f"package is {total_bytes} bytes, exceeding the {MAX_TOTAL_BYTES} limit")
    for x in files:
        if x["bytes"] > MAX_FILE_BYTES:
            raise SchemaError(f"{x['path']} is {x['bytes']} bytes, exceeding the per-file limit")
        if x["media_type"] not in ALLOWED_MEDIA_TYPES:
            raise SchemaError(f"{x['path']}: unsupported media_type {x['media_type']!r}")

    content = {
        "source_identity": {
            "origin_id": origin_id or str(uuid.uuid4()),
            "session_id": session_id,
            "lineage_id": lineage_id,
        },
        "synthetic": bool(synthetic),
        "consistency": "stable-read",
        "projection_policy": "selected-evidence-v1",
        "files": files,
        "omitted": [o.to_dict() for o in plan.omitted],
        "related_sources": [],
    }
    manifest = {
        "schema_version": SCHEMA,
        "snapshot_hash": content_hash(content),
        "content": content,
        "created_at": _now_iso(),
        "collector_version": "1",
        "authorization_ref": authorization_ref,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False), encoding="utf-8")
    return manifest


REQUIRED_TOP = {"schema_version", "snapshot_hash", "content", "created_at",
                "collector_version", "authorization_ref"}
REQUIRED_CONTENT = {"source_identity", "synthetic", "consistency", "projection_policy",
                    "files", "omitted", "related_sources"}
REQUIRED_FILE = {"id", "path", "blob_hash", "bytes", "media_type", "kind"}


def validate_manifest_shape(manifest: dict) -> list:
    """Shape/enum checks only (schema gate). Returns a list of error strings;
    empty means the manifest passes structural validation."""
    errs = []
    if not isinstance(manifest, dict):
        return ["manifest is not a JSON object"]
    missing_top = REQUIRED_TOP - set(manifest)
    if missing_top:
        errs.append(f"manifest missing top-level fields: {sorted(missing_top)}")
    if manifest.get("schema_version") != SCHEMA:
        errs.append(f"unsupported schema_version: {manifest.get('schema_version')!r}")
    content = manifest.get("content")
    if not isinstance(content, dict):
        errs.append("content must be an object")
        return errs
    missing_content = REQUIRED_CONTENT - set(content)
    if missing_content:
        errs.append(f"content missing fields: {sorted(missing_content)}")
    files = content.get("files")
    if not isinstance(files, list) or not files:
        errs.append("content.files must be a non-empty list")
    else:
        ids, paths = set(), set()
        has_trace = False
        for f in files:
            if not isinstance(f, dict) or REQUIRED_FILE - set(f):
                errs.append(f"file entry missing fields: {f!r}")
                continue
            if f["id"] in ids:
                errs.append(f"duplicate file id: {f['id']!r}")
            ids.add(f["id"])
            if f["path"] in paths:
                errs.append(f"duplicate file path: {f['path']!r}")
            paths.add(f["path"])
            if f["kind"] not in ALLOWED_KINDS:
                errs.append(f"file {f['id']}: unknown kind {f['kind']!r}")
            if f["kind"] == "trace":
                has_trace = True
            if not isinstance(f["bytes"], int) or f["bytes"] < 0:
                errs.append(f"file {f['id']}: bytes must be a non-negative integer")
        if not has_trace:
            errs.append("content.files has no file with kind=trace")
    return errs


def verify_blob_integrity(package_dir: Path, manifest: dict) -> list:
    """Re-hash every blob referenced by the manifest. Returns a list of
    {file_id, path, expected, actual_or_error} for mismatches/missing blobs."""
    problems = []
    blobs_dir = package_dir / "blobs"
    for f in manifest.get("content", {}).get("files", []):
        hexdigest = f["blob_hash"][len(HASH_PREFIX):] if f["blob_hash"].startswith(HASH_PREFIX) else f["blob_hash"]
        blob_path = blobs_dir / hexdigest
        if not blob_path.is_file():
            problems.append({"file_id": f["id"], "path": f["path"], "expected": f["blob_hash"],
                              "problem": "blob missing"})
            continue
        actual = sha256_bytes(blob_path.read_bytes())
        if actual != f["blob_hash"]:
            problems.append({"file_id": f["id"], "path": f["path"], "expected": f["blob_hash"],
                              "problem": f"hash mismatch: got {actual}"})
    return problems
