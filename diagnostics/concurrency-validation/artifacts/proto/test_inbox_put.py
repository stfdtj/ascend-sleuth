"""Checkpoint A validation: concurrency, crashes, hashes, identity, compatibility.

Run:  python test_inbox_put.py
Exit: 0 = all assertions pass; 1 = a claim in the proposal is not met.

The test intentionally runs real child processes (not threads/mocks) because the
question is what happens when two *separate* agents write at the same time.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import inbox_put as IP  # noqa: E402

HERE = Path(__file__).resolve().parent
WORKER = HERE / "_inbox_worker.py"
PY = sys.executable
LAB = Path(os.environ.get("ASV_ROOT", r"D:\working\asv")) / "inbox-proto"


def fresh(name: str) -> Path:
    root = LAB / name
    if root.exists():
        import stat

        def onerror(func, p, exc):
            os.chmod(p, stat.S_IWRITE)
            func(p)
        shutil.rmtree(root, onerror=onerror)
    root.mkdir(parents=True)
    (root / "deployment.yaml").write_text("evolution:\n  mode: full\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def write_three(draft: Path, draft_id: str, marker: str = "x"):
    (draft / "sources.yaml").write_text(f"draft_id: {draft_id}\nmarker: {marker}\n", encoding="utf-8")
    (draft / "case.yaml").write_text(
        f"cases:\n  - id: VLLM-ASC-90001\n    title: \"{marker}\"\n", encoding="utf-8")
    (draft / "postmortem.md").write_text(f"# {marker}\n", encoding="utf-8")


def run(cmd, cwd=None):
    p = subprocess.run([str(c) for c in cmd], cwd=str(cwd) if cwd else None, capture_output=True,
                       text=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


def start(mode: str, root: Path, go: Path, index: int = 0):
    return subprocess.Popen([PY, str(WORKER), mode, str(root), str(go), str(index)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8")


class CheckpointA(unittest.TestCase):
    maxDiff = None

    # ---------------------------------------------------------------- 1. concurrency
    def test_eight_simultaneous_creators_get_unique_dirs(self):
        root = fresh("concurrent")
        go = root / "GO"
        procs = [start("new", root, go, i) for i in range(8)]
        time.sleep(0.4)
        go.write_text("go", encoding="utf-8")
        outs = [p.communicate(timeout=60) for p in procs]
        dirs = sorted(p.name for p in (root / "postmortems/inbox").iterdir() if p.is_dir())
        self.assertEqual(len(dirs), 8, (dirs, outs))
        self.assertEqual(len(set(dirs)), 8)
        self.assertEqual([d.endswith(("001", "002", "003", "004", "005", "006", "007", "008"))
                          for d in dirs], [True] * 8, dirs)

    def test_naive_check_then_create_collides(self):
        """The control: the same 8 writers with 'scan then mkdir' lose drafts."""
        root = fresh("naive")
        go = root / "GO"
        procs = [start("naive", root, go, i) for i in range(8)]
        time.sleep(0.4)
        go.write_text("go", encoding="utf-8")
        for p in procs:
            p.communicate(timeout=60)
        dirs = [p for p in (root / "postmortems/inbox").iterdir() if p.is_dir()]
        self.assertEqual(len(dirs), 1, f"expected the check-then-act collision, got {dirs}")
        title = (dirs[0] / "case.yaml").read_text(encoding="utf-8")
        self.assertEqual(sum(f"writer {i}" in title for i in range(8)), 1,
                         "one writer's content overwrote the others")

    # ---------------------------------------------------------------- 2. crashes
    def test_crash_after_mkdir_is_not_consumed(self):
        root = fresh("crash-mkdir")
        run([PY, str(WORKER), "crash_mkdir", str(root), str(root / "no-go")])
        draft = root / "postmortems/inbox/2026-10-28-diag-001"
        self.assertTrue(draft.is_dir())
        self.assertEqual(IP.read_draft(draft)["state"], "incomplete")
        rc, out, err = run([PY, HERE / "inbox_put.py", "finish", str(draft)])
        self.assertNotEqual(rc, 0)

    def test_crash_mid_file_write_is_not_consumed(self):
        root = fresh("crash-files")
        run([PY, str(WORKER), "crash_files", str(root), str(root / "no-go")])
        draft = root / "postmortems/inbox/2026-10-28-diag-002"
        self.assertEqual(IP.read_draft(draft)["state"], "incomplete")
        rc, out, err = run([PY, HERE / "inbox_put.py", "finish", str(draft)])
        self.assertNotEqual(rc, 0)

    def test_truncated_done_is_rejected(self):
        """A crash while publishing DONE must not create a consumable draft."""
        root = fresh("crash-done")
        run([PY, str(WORKER), "crash_done", str(root), str(root / "no-go")])
        draft = root / "postmortems/inbox/2026-10-28-diag-003"
        state = IP.read_draft(draft)
        self.assertEqual(state["state"], "corrupt", state)
        rc, out, err = run([PY, HERE / "inbox_put.py", "list", "--root", str(root), "--json"])
        payload = json.loads(out)
        self.assertEqual(payload["complete"], 0)
        self.assertEqual(payload["corrupt"], 1)

    # ---------------------------------------------------------------- 3. hashes
    def test_hash_mismatch_after_completion_is_reported(self):
        root = fresh("hash")
        draft = root / "postmortems/inbox/2026-10-28-diag-001"
        draft.mkdir(parents=True)
        write_three(draft, draft.name, "before")
        rc, out, err = run([PY, HERE / "inbox_put.py", "finish", str(draft)])
        self.assertEqual(rc, 0, (out, err))
        self.assertEqual(IP.read_draft(draft)["state"], "complete")
        (draft / "case.yaml").write_text(
            "cases:\n  - id: VLLM-ASC-90001\n    title: \"after\"\n", encoding="utf-8")
        state = IP.read_draft(draft)
        self.assertEqual(state["state"], "corrupt")
        self.assertIn("case.yaml", " ".join(state["reasons"]))

    def test_repeated_finish_cannot_silently_reissue(self):
        root = fresh("refinish")
        draft = root / "postmortems/inbox/2026-10-28-diag-001"
        draft.mkdir(parents=True)
        write_three(draft, draft.name, "v1")
        self.assertEqual(run([PY, HERE / "inbox_put.py", "finish", str(draft)])[0], 0)
        (draft / "case.yaml").write_text(
            "cases:\n  - id: VLLM-ASC-90001\n    title: \"v2\"\n", encoding="utf-8")
        rc, out, err = run([PY, HERE / "inbox_put.py", "finish", str(draft)])
        self.assertNotEqual(rc, 0, "plain finish must refuse to re-stamp an edited draft")
        self.assertEqual(IP.read_draft(draft)["state"], "corrupt")
        rc, out, err = run([PY, HERE / "inbox_put.py", "finish", str(draft), "--refinish"])
        self.assertEqual(rc, 0, (out, err))
        # residual: an explicit re-finish legitimises the edit; nothing records the change
        self.assertEqual(IP.read_draft(draft)["state"], "complete")

    # ---------------------------------------------------------------- 4. identity
    def test_two_clones_generate_distinct_deployment_labels(self):
        a, b = fresh("clone-a"), fresh("clone-b")
        la = subprocess.run([PY, HERE / "inbox_put.py", "new", "--root", str(a)],
                            capture_output=True, text=True, encoding="utf-8").stdout.strip()
        lb = subprocess.run([PY, HERE / "inbox_put.py", "new", "--root", str(b)],
                            capture_output=True, text=True, encoding="utf-8").stdout.strip()
        # the local draft ids are the same by design (both start at 001);
        # what must differ is the deployment label in sources.yaml
        import yaml
        sa = yaml.safe_load((Path(la) / "sources.yaml").read_text(encoding="utf-8"))
        sb = yaml.safe_load((Path(lb) / "sources.yaml").read_text(encoding="utf-8"))
        self.assertNotEqual(sa["source"]["deployment"], sb["source"]["deployment"])
        self.assertNotEqual(IP.default_deployment(a), IP.default_deployment(b))

    def test_same_explicit_deployment_collides_across_clones(self):
        """Two clones configured with the same deployment label produce the same key."""
        a, b = fresh("same-a"), fresh("same-b")
        for root in (a, b):
            (root / "deployment.yaml").write_text("deployment:\n  id: prod-east\n", encoding="utf-8")
        pa = subprocess.run([PY, HERE / "inbox_put.py", "new", "--root", str(a)],
                            capture_output=True, text=True, encoding="utf-8").stdout.strip()
        pb = subprocess.run([PY, HERE / "inbox_put.py", "new", "--root", str(b)],
                            capture_output=True, text=True, encoding="utf-8").stdout.strip()
        self.assertEqual(Path(pa).name, Path(pb).name)
        self.assertEqual(IP.default_deployment(a), IP.default_deployment(b))
        # (deployment, draft_id) is therefore not a globally unique key

    def test_renaming_the_checkout_changes_the_fallback_label_but_not_an_explicit_id(self):
        root = fresh("rename-me")
        before = IP.default_deployment(root)
        explicit = root / "deployment.yaml"
        explicit.write_text("deployment:\n  id: stable-id\n", encoding="utf-8")
        with_id = IP.default_deployment(root)
        moved = root.with_name("renamed")
        if moved.exists():
            shutil.rmtree(moved)
        root.rename(moved)
        try:
            after_id = IP.default_deployment(moved)
            self.assertEqual(with_id, "stable-id")
            self.assertEqual(after_id, "stable-id")
            (moved / "deployment.yaml").unlink()
            fallback_after = IP.default_deployment(moved)
            self.assertNotEqual(before, fallback_after,
                                "fallback label must be shown to be rename-fragile")
        finally:
            moved.rename(root)

    # ---------------------------------------------------------------- 5. compatibility
    def test_legacy_flat_drafts_are_listed_but_not_consumed_as_groups(self):
        root = fresh("legacy")
        inbox = root / "postmortems/inbox"
        inbox.mkdir(parents=True)
        (inbox / "OLD-CASE.case.yaml").write_text("cases: []\n", encoding="utf-8")
        (inbox / "OLD-CASE.md").write_text("# old\n", encoding="utf-8")
        rc, out, err = run([PY, HERE / "inbox_put.py", "list", "--root", str(root), "--json"])
        payload = json.loads(out)
        self.assertEqual(payload["drafts"], [])
        self.assertEqual(sorted(payload["legacy_flat_files"]),
                         ["OLD-CASE.case.yaml", "OLD-CASE.md"])

    def test_abort_only_removes_incomplete_drafts(self):
        root = fresh("abort")
        incomplete = root / "postmortems/inbox/2026-10-28-diag-001"
        complete = root / "postmortems/inbox/2026-10-28-diag-002"
        incomplete.mkdir(parents=True)
        complete.mkdir(parents=True)
        write_three(complete, complete.name)
        run([PY, HERE / "inbox_put.py", "finish", str(complete)])
        self.assertNotEqual(run([PY, HERE / "inbox_put.py", "abort", str(incomplete)])[0], 0)
        self.assertEqual(run([PY, HERE / "inbox_put.py", "abort", str(incomplete), "--force"])[0], 0)
        self.assertNotEqual(run([PY, HERE / "inbox_put.py", "abort", str(complete), "--force"])[0], 0)
        self.assertTrue(complete.is_dir())

    # ---------------------------------------------------------------- 6. panel surface
    def test_two_panel_implementations_need_the_same_change(self):
        repo = Path(os.environ.get("ASV_REPO", r"D:\working\ascend-sleuth"))
        files = [repo / "dsh-plugins/ascend-panel/panel-host.js",
                 repo / "dsh-plugins/dsh-sleuth-panels/lib/index.js"]
        hits = {}
        for f in files:
            text = f.read_text(encoding="utf-8") if f.exists() else ""
            hits[f.name] = text.count("inbox")
        self.assertGreater(hits.get("panel-host.js", 0), 0)
        self.assertGreater(hits.get("index.js", 0), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
