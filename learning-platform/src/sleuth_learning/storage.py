"""Local JSON-file store -- the offline stand-in for data-contracts.md's
SQLite control tables + blob store (deployment-design.md section 3). No
SQLite, no server process, no network: see README "Deviations from Astra"
for why an MVP demo doesn't need that infrastructure, and what would need
to change to grow into it.

Layout under `data_dir`:
    snapshots/index.json              snapshot_hash -> snapshot_id (dedup)
    snapshots/<snapshot_id>/manifest.json
    snapshots/<snapshot_id>/blobs/<hex>
    cases/<case_id>/HEAD.json          {latest_revision, published_revision,
                                        generation_status, publication_status,
                                        synthetic, jobs: {job_key: revision}}
    cases/<case_id>/<revision>/learning-case.json

A case id is derived deterministically from its snapshot_hash (uuid5), so
re-ingesting/regenerating from the same snapshot always lands on the same
case, growing its revision history instead of spawning duplicates.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

from .collector.package import validate_manifest_shape, verify_blob_integrity
from .errors import AuthorizationError, IntegrityError, NotFoundError, SchemaError, \
    ValidationBlockedError
from .extraction.validation import has_blocking_errors
from .hashing import content_hash
from .model import LearningCase

CASE_NAMESPACE = uuid.UUID("b7e6a1b0-7a4b-4c9e-9b3e-7e3b1b9b7a11")


def _read_json(path: Path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False),
                   encoding="utf-8")
    os.replace(tmp, path)


def case_id_for_session(session_id: str) -> str:
    """Case identity is keyed by the source session, not the snapshot hash:
    re-ingesting a corrected version of the same session's trace produces a
    new snapshot (new snapshot_hash) but must land as a new revision of the
    *same* case, not a brand-new one -- otherwise "source changes and
    regeneration" could never retain the old published revision as
    data-contracts.md requires. An empty/unknown session_id still needs a
    stable identity, so it falls back to a fixed sentinel rather than
    colliding with a real session named "" from two different packages.
    """
    key = session_id or "unknown-session"
    return str(uuid.uuid5(CASE_NAMESPACE, key))


# ---- snapshots / ingestion --------------------------------------------------

def ingest_package(package_dir: Path, data_dir: Path) -> dict:
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.is_file():
        raise NotFoundError(f"no manifest.json in {package_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    errs = validate_manifest_shape(manifest)
    if errs:
        raise SchemaError("package manifest failed schema validation", errors=errs)

    problems = verify_blob_integrity(package_dir, manifest)
    if problems:
        raise IntegrityError("package blobs failed integrity re-check", problems=problems)

    snapshot_hash = manifest["snapshot_hash"]
    index_path = data_dir / "snapshots" / "index.json"
    index = _read_json(index_path, {})
    if snapshot_hash in index:
        return {"snapshot_id": index[snapshot_hash], "snapshot_hash": snapshot_hash,
                "duplicate": True, "manifest": manifest}

    snapshot_id = str(uuid.uuid4())
    dest = data_dir / "snapshots" / snapshot_id
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest_path, dest / "manifest.json")
    shutil.copytree(package_dir / "blobs", dest / "blobs", dirs_exist_ok=True)

    index[snapshot_hash] = snapshot_id
    _write_json(index_path, index)
    return {"snapshot_id": snapshot_id, "snapshot_hash": snapshot_hash, "duplicate": False,
           "manifest": manifest}


def get_snapshot(data_dir: Path, snapshot_id: str) -> dict:
    d = data_dir / "snapshots" / snapshot_id
    manifest = _read_json(d / "manifest.json")
    if manifest is None:
        raise NotFoundError(f"no such snapshot: {snapshot_id}")
    return {"snapshot_id": snapshot_id, "dir": d, "manifest": manifest}


def list_snapshots(data_dir: Path) -> list:
    root = data_dir / "snapshots"
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and (d / "manifest.json").is_file():
            m = _read_json(d / "manifest.json")
            out.append({"snapshot_id": d.name, "snapshot_hash": m.get("snapshot_hash"),
                       "session_id": m["content"]["source_identity"].get("session_id"),
                       "synthetic": m["content"].get("synthetic")})
    return out


# ---- case revisions ----------------------------------------------------------

def _head_path(data_dir: Path, case_id: str) -> Path:
    return data_dir / "cases" / case_id / "HEAD.json"


def load_head(data_dir: Path, case_id: str) -> dict:
    return _read_json(_head_path(data_dir, case_id), {
        "latest_revision": 0, "published_revision": None,
        "generation_status": "none", "publication_status": "draft",
        "synthetic": None, "jobs": {},
    })


def job_key(snapshot_hash: str, mode: str, generator_version: str, model_id, prompt_hash) -> str:
    return content_hash({"snapshot_hash": snapshot_hash, "mode": mode,
                         "generator_version": generator_version,
                         "model_id": model_id, "prompt_hash": prompt_hash})


def save_case_revision(data_dir: Path, case: LearningCase, findings: list, *,
                       manifest: dict, key: str, force: bool = False) -> dict:
    """Idempotent by `key` (see job_key): if this exact job already produced
    a revision for this case and `force` is false, returns that revision
    unchanged instead of creating a new one. Otherwise creates a new revision
    -- it never overwrites an existing revision directory, and never touches
    `published_revision`."""
    case_id = case.id
    head = load_head(data_dir, case_id)
    if not force and key in head["jobs"]:
        rev = head["jobs"][key]
        return {"case_id": case_id, "revision": rev, "duplicate": True}

    rev = head["latest_revision"] + 1
    case.revision = rev
    case.validation = findings
    rev_dir = data_dir / "cases" / case_id / str(rev)
    rev_dir.mkdir(parents=True, exist_ok=True)
    _write_json(rev_dir / "learning-case.json", case.to_dict())

    head["latest_revision"] = rev
    head["generation_status"] = "failed" if has_blocking_errors(findings) else "generated"
    head["synthetic"] = manifest["content"].get("synthetic")
    head["jobs"][key] = rev
    _write_json(_head_path(data_dir, case_id), head)
    return {"case_id": case_id, "revision": rev, "duplicate": False}


def get_case(data_dir: Path, case_id: str, revision: int = None) -> LearningCase:
    head = load_head(data_dir, case_id)
    rev = revision if revision is not None else head["latest_revision"]
    if not rev:
        raise NotFoundError(f"case {case_id} has no revisions")
    path = data_dir / "cases" / case_id / str(rev) / "learning-case.json"
    d = _read_json(path)
    if d is None:
        raise NotFoundError(f"case {case_id} revision {rev} not found")
    return LearningCase.from_dict(d)


def list_cases(data_dir: Path) -> list:
    root = data_dir / "cases"
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and (d / "HEAD.json").is_file():
            head = load_head(data_dir, d.name)
            out.append({"case_id": d.name, **head})
    return out


def publish(data_dir: Path, case_id: str, revision: int, *, authorized: bool,
           allow_non_synthetic: bool = False) -> dict:
    head = load_head(data_dir, case_id)
    if revision > head["latest_revision"] or revision < 1:
        raise NotFoundError(f"case {case_id} has no revision {revision}")
    case = get_case(data_dir, case_id, revision)
    if has_blocking_errors(case.validation):
        raise ValidationBlockedError(
            f"case {case_id} revision {revision} has unresolved error-severity findings; "
            f"fix them (or regenerate) before publishing")
    if not authorized:
        raise AuthorizationError(
            "publish refused: no local authorization grant. This offline MVP has no real "
            "safety/content/publisher review workflow (deployment-design.md section 4) -- "
            "pass authorized=True (CLI: --i-have-authorization) only once a human has actually "
            "reviewed this revision")
    if head.get("synthetic") is False and not allow_non_synthetic:
        raise AuthorizationError(
            "publish refused: this case was derived from a non-synthetic (real) trace. "
            "Publishing real material requires --allow-non-synthetic in addition to "
            "--i-have-authorization -- this tool never uploads or publishes real customer "
            "data by default")
    head["published_revision"] = revision
    head["publication_status"] = "published"
    _write_json(_head_path(data_dir, case_id), head)
    return head


def withdraw(data_dir: Path, case_id: str, reason: str = "") -> dict:
    head = load_head(data_dir, case_id)
    head["publication_status"] = "withdrawn"
    head["withdraw_reason"] = reason
    _write_json(_head_path(data_dir, case_id), head)
    return head


def get_published_case(data_dir: Path, case_id: str) -> LearningCase:
    head = load_head(data_dir, case_id)
    if head["publication_status"] != "published" or head["published_revision"] is None:
        raise NotFoundError(f"case {case_id} has no published revision")
    return get_case(data_dir, case_id, head["published_revision"])
