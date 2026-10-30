"""V2 Checkpoint C end-to-end test in a temporary git repository."""
from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import merge_recheck  # noqa: E402

CASE = """cases:
  - id: {cid}
    title: "{title}"
    category: {category}
    symptoms: {symptoms}
    quickly_check:
      primary:
        command_template: "grep -c 'bfloat16' {{{{log_path}}}}"
        expected: "regex:^[1-9]"
    root_cause: "310P does not support bfloat16"
    fix: "change dtype to float16"
    platforms: [A2-310P]
    compat:
      - framework: vllm-ascend
        ranges: ["==0.22.0"]
"""


def git(repo, *args):
    p = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(p.stderr)
    return p.stdout.strip()


class MergeRecheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="v2-c-")
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "config", "user.email", "t@example.com")
        k = self.repo / "knowledge/inference/vllm-ascend/interrupt"
        k.mkdir(parents=True)
        (k / "VLLM-ASC-99101.yaml").write_text(CASE.format(
            cid="VLLM-ASC-99101", title="310P bf16 startup",
            category="interrupt", symptoms='["bfloat16 is not supported"]'), encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "base")
        git(self.repo, "checkout", "-b", "feature")
        (k / "VLLM-ASC-99102.yaml").write_text(CASE.format(
            cid="VLLM-ASC-99102", title="310P bf16 zeros",
            category="precision", symptoms='["bfloat16 is not supported", "zeros"]'), encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "case")
        self.decision = self.repo / "postmortems/decisions/VLLM-ASC-99102.yaml"

    def tearDown(self):
        self.tmp.cleanup()

    def run_c(self, *extra):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = merge_recheck.main(["--root", str(self.repo), "--base", "main",
                                     "--head", "feature", *extra])
        return rc, buf.getvalue()

    def test_no_decision_blocks(self):
        rc, out = self.run_c()
        self.assertEqual(rc, 2, out)
        self.assertIn("missing or empty", out)

    def test_init_then_fill_decision(self):
        rc, out = self.run_c("--init-decision", str(self.decision))
        self.assertEqual(rc, 2, out)
        self.assertTrue(self.decision.is_file())
        doc = yaml.safe_load(self.decision.read_text(encoding="utf-8"))
        self.assertEqual(doc["decision"], "TODO")
        doc["decision"] = "variant"
        for p in doc["pairs"]:
            p["decision"] = "variant"
            p["note"] = "same root cause; different category"
        self.decision.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                                 encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "decision")
        rc, out = self.run_c("--decision", str(self.decision))
        self.assertEqual(rc, 0, out)

    def test_todo_blocks(self):
        rc, out = self.run_c("--init-decision", str(self.decision))
        self.assertEqual(rc, 2)
        rc, out = self.run_c("--decision", str(self.decision))
        self.assertEqual(rc, 2)
        self.assertIn("not allowed", out)


if __name__ == "__main__":
    unittest.main()
