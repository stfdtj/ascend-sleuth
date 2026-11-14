import tempfile
import unittest
from pathlib import Path

from sleuth_learning.collector import discovery as discovery_mod
from sleuth_learning.collector import package as package_mod
from sleuth_learning.collector import snapshot as snapshot_mod
from sleuth_learning.errors import PathSafetyError
from sleuth_learning.fixtures import fixtures_root


class DiscoveryTests(unittest.TestCase):
    def test_discovers_terminal_sessions_only_by_default(self):
        candidates, skipped = discovery_mod.discover(fixtures_root() / "sample_traces")
        ids = {c.session_id for c in candidates}
        self.assertIn("demo-2026-11-14-ep-hang", ids)
        self.assertNotIn("demo-incomplete", ids)  # status=in_progress, excluded by default
        self.assertEqual(skipped, [])

    def test_include_in_progress(self):
        candidates, _ = discovery_mod.discover(fixtures_root() / "sample_traces", include_in_progress=True)
        ids = {c.session_id for c in candidates}
        self.assertIn("demo-incomplete", ids)

    def test_oversized_trace_is_skipped_not_raised(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "huge.yaml"
            p.write_text("status: resolved\nsession_id: huge\n" + "x" * (3 * 1024 * 1024))
            candidates, skipped = discovery_mod.discover(Path(td))
            self.assertEqual(candidates, [])
            self.assertEqual(len(skipped), 1)
            self.assertIn("exceeds", skipped[0]["reason"])


class PathSafetyTests(unittest.TestCase):
    def test_rejects_traversal_outside_allow_root(self):
        with self.assertRaises(PathSafetyError):
            snapshot_mod.resolve_ref("../../etc/passwd", fixtures_root())

    def test_rejects_absolute_path(self):
        with self.assertRaises(PathSafetyError):
            snapshot_mod.resolve_ref("/etc/passwd", fixtures_root())

    def test_plan_sources_omits_rather_than_raises(self):
        root = fixtures_root()
        trace_path = root / "sample_traces" / "invalid_evidence_ref.yaml"
        doc = discovery_mod.read_candidate(trace_path)
        plan = snapshot_mod.plan_sources(doc, trace_path, root)
        reasons = {o.reason for o in plan.omitted}
        self.assertIn("missing", reasons)        # does-not-exist.log
        self.assertIn("not-authorized", reasons)  # ../../outside-allow-root.log
        self.assertEqual(plan.resolved, [])


class PackageTests(unittest.TestCase):
    def test_prepare_seal_inspect_roundtrip(self):
        root = fixtures_root()
        trace_path = root / "sample_traces" / "complete.yaml"
        doc = discovery_mod.read_candidate(trace_path)
        plan = snapshot_mod.plan_sources(doc, trace_path, root)
        self.assertEqual(len(plan.resolved), 1)
        self.assertEqual(plan.omitted, [])

        with tempfile.TemporaryDirectory() as td:
            staging = Path(td) / "staging"
            out_dir = Path(td) / "package"
            captured = snapshot_mod.capture_stable(plan, staging, settle_seconds=0.0)
            manifest = package_mod.project_and_seal(captured, plan, out_dir,
                                                    session_id="complete-test", synthetic=True)

            self.assertEqual(package_mod.validate_manifest_shape(manifest), [])
            self.assertEqual(package_mod.verify_blob_integrity(out_dir, manifest), [])
            self.assertTrue(manifest["snapshot_hash"].startswith("sha256:"))

            # tamper with a blob -> integrity re-check must catch it
            trace_file = next(f for f in manifest["content"]["files"] if f["kind"] == "trace")
            blob_path = out_dir / "blobs" / trace_file["blob_hash"].split(":", 1)[1]
            original = blob_path.read_bytes()
            blob_path.write_bytes(original + b"tampered")
            problems = package_mod.verify_blob_integrity(out_dir, manifest)
            self.assertEqual(len(problems), 1)
            self.assertIn("hash mismatch", problems[0]["problem"])

    def test_source_file_is_never_modified(self):
        root = fixtures_root()
        trace_path = root / "sample_traces" / "complete.yaml"
        before = trace_path.read_bytes()
        doc = discovery_mod.read_candidate(trace_path)
        plan = snapshot_mod.plan_sources(doc, trace_path, root)
        with tempfile.TemporaryDirectory() as td:
            snapshot_mod.capture_stable(plan, Path(td) / "staging", settle_seconds=0.0)
        after = trace_path.read_bytes()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
