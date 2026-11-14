"""Shared test plumbing: prepare + ingest one of the shipped synthetic
fixtures into a fresh temp package/data dir, without going through the CLI
(the CLI itself is exercised separately in test_cli.py)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sleuth_learning import storage
from sleuth_learning.collector import discovery as discovery_mod
from sleuth_learning.collector import package as package_mod
from sleuth_learning.collector import snapshot as snapshot_mod
from sleuth_learning.fixtures import fixtures_root


def prepare_package(trace_name: str, out_dir: Path, *, synthetic: bool = True):
    root = fixtures_root()
    trace_path = root / "sample_traces" / f"{trace_name}.yaml"
    doc = discovery_mod.read_candidate(trace_path)
    plan = snapshot_mod.plan_sources(doc, trace_path, root)
    with tempfile.TemporaryDirectory(prefix="sleuth-learn-test-staging-") as td:
        captured = snapshot_mod.capture_stable(plan, Path(td), settle_seconds=0.0)
        manifest = package_mod.project_and_seal(
            captured, plan, out_dir, session_id=doc.get("session_id") or trace_name,
            synthetic=synthetic)
    return manifest, plan


def ingest(package_dir: Path, data_dir: Path):
    return storage.ingest_package(package_dir, data_dir)


def prepare_and_ingest(trace_name: str, tmp_root: Path, *, synthetic: bool = True):
    package_dir = tmp_root / "package" / trace_name
    data_dir = tmp_root / "data"
    manifest, plan = prepare_package(trace_name, package_dir, synthetic=synthetic)
    result = ingest(package_dir, data_dir)
    return {"manifest": manifest, "plan": plan, "data_dir": data_dir,
           "package_dir": package_dir, "snapshot_id": result["snapshot_id"],
           "ingest_duplicate": result["duplicate"]}


def prepare_and_ingest_from_path(trace_path: Path, allow_root: Path, tmp_root: Path,
                                 package_name: str, *, synthetic: bool = True):
    doc = discovery_mod.read_candidate(trace_path)
    plan = snapshot_mod.plan_sources(doc, trace_path, allow_root)
    package_dir = tmp_root / "package" / package_name
    data_dir = tmp_root / "data"
    with tempfile.TemporaryDirectory(prefix="sleuth-learn-test-staging-") as td:
        captured = snapshot_mod.capture_stable(plan, Path(td), settle_seconds=0.0)
        manifest = package_mod.project_and_seal(
            captured, plan, package_dir, session_id=doc.get("session_id") or package_name,
            synthetic=synthetic)
    result = ingest(package_dir, data_dir)
    return {"manifest": manifest, "plan": plan, "data_dir": data_dir,
           "package_dir": package_dir, "snapshot_id": result["snapshot_id"],
           "ingest_duplicate": result["duplicate"]}
