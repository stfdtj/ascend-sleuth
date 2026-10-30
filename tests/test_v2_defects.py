"""E11/E12 regression slices for the production fixes."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import entry_activity  # noqa: E402
import verify_metrics  # noqa: E402


class DefectRegressionTest(unittest.TestCase):
    def test_numeric_sha_is_quoted(self):
        text = entry_activity.format_row({
            "run": "2026-10-30-1200", "deployment": "d", "checkout": "8675309",
            "kb_rev": "8675309", "sessions": 1, "kind": "case", "id": "CASE-1",
            "selected": 0, "loaded": 0, "resolved": 0, "misdiagnosed": 0,
            "self_resolved": 0, "excluded": 0,
        })
        self.assertIn("checkout: '8675309'", text)
        self.assertIn("kb_rev: '8675309'", text)

    def test_external_violation_field_is_live(self):
        self.assertIn("external_record_violations_total", verify_metrics.LIVE_FIELDS)

    def test_metric_strength_declared(self):
        gates = yaml.safe_load((ROOT / "metrics/gates.yaml").read_text(encoding="utf-8"))
        strength = gates["metric_strength"]
        for key in ("external_record_violations_total", "considered_candidates_events",
                    "parallel_group_events", "stop_reason_unrecorded",
                    "trace_record_violations_total", "triage_miss_classes"):
            self.assertIn(key, strength)


if __name__ == "__main__":
    unittest.main()
