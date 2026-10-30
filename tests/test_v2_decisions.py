"""V2 decision validation and case_match tier tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import case_match  # noqa: E402
import verify_decisions  # noqa: E402


def base_decision(**over):
    d = {
        "case_id": "VLLM-ASC-99002",
        "decision": "variant",
        "main_sha": "BASE",
        "head_sha": "HEAD",
        "pairs": [{"pair_id": "p1", "other": "VLLM-ASC-99001", "tier": "mandatory",
                   "decision": "variant", "note": "same root, different platform"}],
        "overflow": {"hidden_high": 0, "ack": None},
        "same_case": [],
    }
    d.update(over)
    return d


class DecisionTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(verify_decisions.validate(base_decision(), base="BASE", head="HEAD",
                                                   required={"p1": "mandatory"}), [])

    def test_todo_pair_rejected(self):
        d = base_decision()
        d["pairs"][0]["decision"] = "TODO"
        self.assertTrue(any("not allowed" in e for e in verify_decisions.validate(
            d, base="BASE", head="HEAD", required={"p1": "mandatory"})))

    def test_missing_pair_rejected(self):
        d = base_decision()
        d["pairs"] = []
        self.assertTrue(any("missing pair" in e for e in verify_decisions.validate(
            d, base="BASE", head="HEAD", required={"p1": "mandatory"})))

    def test_stale_main_rejected(self):
        self.assertTrue(any("main_sha" in e for e in verify_decisions.validate(
            base_decision(), base="NEW", head="HEAD", required={"p1": "mandatory"})))

    def test_content_hash_accepts_decision_commit(self):
        d = base_decision(head_sha="OLD")
        d["content_sha256"] = "HASH"
        self.assertEqual(verify_decisions.validate(d, base="BASE", head="NEW",
                                                   required={"p1": "mandatory"},
                                                   content_sha256="HASH"), [])

    def test_content_hash_mismatch_rejected(self):
        d = base_decision(head_sha="OLD")
        d["content_sha256"] = "OTHER"
        self.assertTrue(any("content_sha256" in e for e in verify_decisions.validate(
            d, base="BASE", head="NEW", required={"p1": "mandatory"},
            content_sha256="HASH")))

    def test_overflow_ack_count(self):
        d = base_decision(overflow={"hidden_high": 2, "ack": {"hidden_count": 1,
                                                               "reason": "x", "reviewer": "r"}})
        self.assertTrue(any("hidden_count" in e for e in verify_decisions.validate(
            d, base="BASE", head="HEAD", required={"p1": "mandatory"}, hidden_high=2)))

    def test_same_case_required(self):
        d = base_decision()
        d["same_case"] = [{"case_id": "VLLM-ASC-99002", "fields": ["fix"],
                           "decision": "separate", "note": "disjoint"}]
        self.assertEqual(verify_decisions.validate(d, base="BASE", head="HEAD",
                                                   required={"p1": "mandatory"},
                                                   same_case_ids={"VLLM-ASC-99002"}), [])


class CaseMatchTest(unittest.TestCase):
    def rec(self, cid, **over):
        r = {"_id": cid, "_draft_id": cid, "_path": f"{cid}.yaml", "_ns": "inference/vllm-ascend",
             "title": "310P bf16 failure", "category": "interrupt",
             "symptoms": ["bfloat16 is not supported", "npu-smi 310P"],
             "quickly_check": {"primary": {"command_template": "grep bfloat16",
                                           "expected": "regex:^[1-9]"}},
             "root_cause": "310P does not support bfloat16",
             "fix": "change dtype to float16",
             "platforms": ["A2-310P"],
             "compat": [{"framework": "vllm-ascend", "ranges": ["==0.22.0"]}],
             "_summary": {"root_cause": "310P does not support bfloat16",
                          "fix": "change dtype to float16"}}
        r.update(over)
        return r

    def test_shared_upstream_is_mandatory(self):
        a = self.rec("A", upstream={"repo": "x", "issue": 1}, _upstream={"repo": "x", "issue": 1})
        b = self.rec("B", upstream={"repo": "x", "issue": 1}, _upstream={"repo": "x", "issue": 1})
        pairs = case_match.compare([a], [b])
        self.assertEqual(pairs[0]["tier"], "mandatory")

    def test_cross_category_is_high(self):
        a = self.rec("A")
        b = self.rec("B", category="precision")
        pairs = case_match.compare([a], [b])
        self.assertIn(pairs[0]["tier"], ("high", "mandatory"))
        self.assertTrue(pairs[0]["cross_cat"])

    def test_unrelated_is_not_a_pair(self):
        a = self.rec("A")
        b = self.rec("B", title="completely different", category="interrupt",
                     symptoms=["other"], root_cause="other", fix="other",
                     quickly_check={"primary": {"expected": "regex:^[0]"}},
                     _summary={"root_cause": "other", "fix": "other"})
        self.assertEqual(case_match.compare([a], [b]), [])


if __name__ == "__main__":
    unittest.main()
