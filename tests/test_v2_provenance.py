"""V2 provenance checker tests."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_provenance  # noqa: E402

CASE = """cases:
  - id: VLLM-ASC-99301
    title: "p"
    category: interrupt
    symptoms: ["s"]
    root_cause: "r"
    fix: "f"
"""


class ProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="v2-prov-")
        self.root = Path(self.tmp.name)
        (self.root / "knowledge/inference/vllm-ascend/interrupt").mkdir(parents=True)
        (self.root / "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-99301.yaml").write_text(
            CASE, encoding="utf-8")
        self.mat = self.root / "postmortems/materials/VLLM-ASC-99301/case.yaml"
        self.mat.parent.mkdir(parents=True)
        self.mat.write_text(CASE, encoding="utf-8")
        self.manifest = self.root / "postmortems/provenance/VLLM-ASC-99301.yaml"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, *, committed=True, dropped=None):
        h = hashlib.sha256(self.mat.read_bytes()).hexdigest()
        doc = {
            "case_id": "VLLM-ASC-99301",
            "decision": "merged",
            "materials": [{
                "draft_id": "d1", "files": [
                    {"path": "postmortems/materials/VLLM-ASC-99301/case.yaml",
                     "sha256": h, "committed": committed}],
                "fields": {"fix": ["d1"]},
                "dropped": dropped or [],
            }],
            "evidence": [{"event_id": "feedback:s1:1", "independent": True}],
            "lineage": {},
        }
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        self.manifest.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                                 encoding="utf-8")

    def test_valid(self):
        self.write()
        errors, warnings, _ = verify_provenance.check_all(self.root)
        self.assertEqual(errors, [])

    def test_hash_mismatch(self):
        self.write()
        self.mat.write_text(CASE + "\n# edit\n", encoding="utf-8")
        errors, _, _ = verify_provenance.check_all(self.root)
        self.assertTrue(any("hash mismatch" in e for e in errors))

    def test_local_only_warns(self):
        self.write(committed=False)
        errors, warnings, _ = verify_provenance.check_all(self.root)
        self.assertEqual(errors, [])
        self.assertTrue(any("local-only" in w for w in warnings))

    def test_dropped_verified_missing(self):
        self.write(dropped=[{"field": "diagnosis", "destination": "missing.yaml",
                             "recoverability": "verified"}])
        errors, _, _ = verify_provenance.check_all(self.root)
        self.assertTrue(any("dropped destination missing" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
