"""Coverage for converting Agentless model responses into bounded Sleuth edits."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from evolve.algorithms.agentless import SOURCE, candidate_from_response
from evolve.targets.registry import resolve_optimizer
from eval.analyzers.ibmc_presence import assess


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
            result = {"findings": [{"claim": f"NPU 数量 {n} < 标准 16，疑似丢卡"} for n in counts],
                      "missing": []}
            self.assertFalse(assess(result, expected)["pass"])

    def test_malformed_response_is_rejected_in_full(self):
        edit = block("npu = 0", "npu = 1")
        for response in (edit + "\n" + edit, edit + "\n" + block("ecc = 0", "ecc = 3", "other.py"),
                         block("absent", "new"), edit + "\ntrailing text", ""):
            with self.subTest(response=response), self.assertRaises(ValueError):
                candidate_from_response(response, self.source, "HEAD")
