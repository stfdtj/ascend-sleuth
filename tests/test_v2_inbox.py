"""V2 inbox reader/writer tests: UUID, DONE, reopen, legacy, migration."""
from __future__ import annotations

import io
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import yaml

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import draft_queue  # noqa: E402
import inbox_put  # noqa: E402

CASE = """cases:
  - id: {cid}
    title: "test {cid}"
    category: interrupt
    symptoms: ["symptom"]
    root_cause: "root"
    fix: "fix"
"""


class InboxV2Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="v2-inbox-")
        self.root = Path(self.tmp.name) / "repo"
        self.inbox = self.root / "postmortems" / "inbox"
        self.inbox.mkdir(parents=True)
        (self.root / "deployment.yaml").write_text("deployment:\n  id: test-dep\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _new(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = inbox_put.main(["new", "--root", str(self.root), "--inbox", str(self.inbox)])
        self.assertEqual(rc, 0)
        return Path(buf.getvalue().strip().splitlines()[-1])

    def _fill(self, d: Path, cid="VLLM-ASC-99001"):
        (d / "case.yaml").write_text(CASE.format(cid=cid), encoding="utf-8")
        (d / "postmortem.md").write_text("# p\n", encoding="utf-8")

    def _finish(self, d: Path):
        return inbox_put.main(["finish", str(d)])

    def _state(self, d: Path):
        return next(r for r in draft_queue.scan(self.inbox)["drafts"] if r["draft_id"] == d.name)

    def test_uuid_and_complete(self):
        d = self._new()
        self._fill(d)
        self.assertEqual(self._finish(d), 0)
        self.assertEqual(self._state(d)["state"], "complete")
        self.assertEqual(self._state(d)["case_id"], "VLLM-ASC-99001")
        self.assertEqual(self._finish(d), 2)  # repeated finish refused

    def test_hash_mismatch_is_corrupt(self):
        d = self._new()
        self._fill(d)
        self._finish(d)
        (d / "case.yaml").write_text((d / "case.yaml").read_text(encoding="utf-8") + "\n# edit\n",
                                     encoding="utf-8")
        self.assertEqual(self._state(d)["state"], "corrupt")

    def test_reopen_marks_old_and_creates_new(self):
        d = self._new()
        self._fill(d)
        self._finish(d)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = inbox_put.main(["reopen", str(d), "--reason", "fix"])
        self.assertEqual(rc, 0)
        new = Path(buf.getvalue().strip().splitlines()[-1])
        self.assertEqual(self._state(d)["state"], "superseded")
        self.assertEqual(self._state(new)["state"], "complete")
        self.assertEqual(self._state(new)["sources"]["supersedes"], d.name)

    def test_concurrent_new_gets_distinct_uuids(self):
        out = []
        lock = threading.Lock()

        def worker():
            p = subprocess.run([sys.executable, str(ROOT / "scripts" / "inbox_put.py"),
                                "new", "--root", str(self.root), "--inbox", str(self.inbox)],
                               capture_output=True, text=True, encoding="utf-8")
            with lock:
                out.append(p.stdout.strip().splitlines()[-1])

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(out), 8)
        self.assertEqual(len(set(out)), 8)

    def test_legacy_flat_is_consumable(self):
        (self.inbox / "VLLM-ASC-99002.case.yaml").write_text(
            CASE.format(cid="VLLM-ASC-99002"), encoding="utf-8")
        (self.inbox / "VLLM-ASC-99002.md").write_text("# old\n", encoding="utf-8")
        row = draft_queue.scan(self.inbox)["drafts"][0]
        self.assertEqual(row["state"], "legacy_flat")

    def test_legacy_missing_md_is_incomplete(self):
        (self.inbox / "VLLM-ASC-99003.case.yaml").write_text(
            CASE.format(cid="VLLM-ASC-99003"), encoding="utf-8")
        row = draft_queue.scan(self.inbox)["drafts"][0]
        self.assertEqual(row["state"], "incomplete")

    def test_migrate_and_rollback(self):
        (self.inbox / "VLLM-ASC-99004.case.yaml").write_text(
            CASE.format(cid="VLLM-ASC-99004"), encoding="utf-8")
        (self.inbox / "VLLM-ASC-99004.md").write_text("# old\n", encoding="utf-8")
        rc = inbox_put.main(["migrate", "--root", str(self.root), "--inbox", str(self.inbox), "--apply"])
        self.assertEqual(rc, 0)
        self.assertEqual(draft_queue.scan(self.inbox)["complete"], 1)
        self.assertTrue((self.inbox / "_legacy").is_dir())
        rc = inbox_put.main(["migrate", "--root", str(self.root), "--inbox", str(self.inbox), "--rollback"])
        self.assertEqual(rc, 0)
        self.assertEqual(draft_queue.scan(self.inbox)["legacy_flat"], 1)
        self.assertTrue((self.inbox / "VLLM-ASC-99004.case.yaml").is_file())


if __name__ == "__main__":
    unittest.main()
