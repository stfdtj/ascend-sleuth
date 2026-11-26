"""Coverage for converting Agentless model responses into bounded Sleuth edits."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from evolve.algorithms.agentless import SOURCE, candidate_from_response
from evolve.targets.registry import resolve_optimizer
from evolve.evaluations.ibmc_presence import assess


def block(old, new, path=SOURCE):
    return f"```python\n### {path}\n<<<<<<< SEARCH\n{old}\n=======\n{new}\n>>>>>>> REPLACE\n```"


class AgentlessTest(unittest.TestCase):
    source = "npu = 0\nkeep = 1\necc = 0\n"

    def test_registry_and_converter(self):
        _, optimizer = resolve_optimizer("tooling", "agentless")
        response = block("ecc = 0", "ecc = 2") + "\n" + block("npu = 0", "npu = 1")
        candidate = candidate_from_response(response, self.source, "HEAD")
        self.assertEqual(candidate["old_text"], self.source)
        self.assertEqual(candidate["new_text"], "npu = 1\nkeep = 1\necc = 2\n")
        self.assertEqual(candidate["region"], optimizer.propose("tooling", [], None, {}).target_component)
        with self.assertRaises(ValueError):
            resolve_optimizer("skill", "agentless")

    def test_count_alerts_must_be_exact_and_consistent(self):
        for counts, expected in [([10], "one"), ([0, 7], "zero")]:
            result = {"status": "ok", "missing": [],
                      "findings": [{"claim": f"NPU 数量 {n} < 标准 16，疑似丢卡",
                                    "evidence": "bmc.json health.issues"} for n in counts]}
            self.assertFalse(assess(result, expected)["pass"])

    def test_empty_or_failed_report_cannot_pass_as_healthy(self):
        for status, findings in [("ok", []), ("failed", [{"claim": "完成", "evidence": "bmc.json"}])]:
            with self.subTest(status=status):
                self.assertFalse(assess({"status": status, "findings": findings, "missing": []},
                                        "eight")["pass"])

    def test_suppressed_count_claim_without_evidence_stays_visible_and_fails(self):
        for expected in ["eight", "one", "zero", "unknown"]:
            claim = {"one": "NPU 数量 1 < 标准 8", "zero": "NPU 数量 0 < 标准 8"}.get(expected, "概要")
            suppressed = [{"claim": "疑似丢卡", "evidence": " "}]
            report = {"status": "partial", "findings": [{"claim": claim, "evidence": "bmc.json"}],
                      "missing": ["NPU 在位未知"] if expected == "unknown" else [],
                      "suppressed": suppressed}
            with self.subTest(expected=expected):
                result = assess(report, expected)
                self.assertFalse(result["pass"])
                self.assertEqual(result["suppressed"], suppressed)

    def test_unrelated_npu_gap_does_not_change_presence_verdict(self):
        report = {"status": "partial", "findings": [{"claim": "概要", "evidence": "bmc.json"}],
                  "missing": ["NPU 温度未知"],
                  "suppressed": [{"claim": "疑似丢卡", "evidence": "bmc.json health.issues"}]}
        self.assertFalse(assess(report, "unknown")["pass"])
        report["suppressed"] = []
        self.assertTrue(assess(report, "eight")["pass"])

    def test_count_finding_needs_its_own_evidence(self):
        report = {"status": "partial", "missing": [],
                  "findings": [{"claim": "电源正常", "evidence": "bmc.json"},
                               {"claim": "NPU 数量 1 < 标准 8，疑似丢卡"}]}
        self.assertFalse(assess(report, "one")["pass"])

    def test_malformed_response_is_rejected_in_full(self):
        edit = block("npu = 0", "npu = 1")
        for response in (edit + "\n" + edit, edit + "\n" + block("ecc = 0", "ecc = 3", "other.py"),
                         block("absent", "new"), edit + "\ntrailing text", ""):
            with self.subTest(response=response), self.assertRaises(ValueError):
                candidate_from_response(response, self.source, "HEAD")
