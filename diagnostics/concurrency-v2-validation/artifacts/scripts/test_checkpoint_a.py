"""Checkpoint A V2 tests: UUID identity, strict reader, atomic DONE, reopen, legacy."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import lab_v2 as L
import fixtures as F

HERE = Path(__file__).parent
PROTO = HERE.parent / "proto"
PY = sys.executable
INBOX = PROTO / "inbox_v2.py"
READER = PROTO / "draft_queue.py"


def call(*args, cwd=None):
    return L.run([PY, str(INBOX), *args], cwd=cwd or HERE)


def new(root):
    rc, out, err = call("new", "--root", str(root))
    assert rc == 0, (out, err)
    return Path(out.strip().splitlines()[-1])


def fill(d: Path, cid="VLLM-ASC-93001", marker="x"):
    (d / "case.yaml").write_text(F.case_text(L.case(cid, title=f"V2 draft {marker}")), encoding="utf-8")
    (d / "postmortem.md").write_text(f"# {marker}\n", encoding="utf-8")


def finish(d: Path):
    return call("finish", str(d))


def state(d: Path):
    rc, out, err = call("list", "--root", str(d.parent.parent.parent), "--json")
    data = json.loads(out)
    return next((r for r in data["drafts"] if r["draft_id"] == d.name), None)


def main():
    L.reset_origin()
    repo = L.fresh("a2")
    rec = L.Rec("v2-a")
    # 8 concurrent creators
    procs = [subprocess.Popen([PY, str(INBOX), "new", "--root", str(repo)],
                              cwd=str(HERE), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding="utf-8") for _ in range(8)]
    outs = [p.communicate(timeout=60) for p in procs]
    dirs = [p for p in (repo / "postmortems/inbox").iterdir() if p.is_dir()]
    rec.add("8 concurrent UUID drafts", 0 if len(dirs) == 8 else 1,
            f"dirs={len(dirs)} unique={len({d.name for d in dirs})}")
    # complete one
    d = new(repo)
    fill(d)
    rc, out, err = finish(d)
    rec.add("finish complete", rc, out, err)
    rec.add("reader complete", 0, json.dumps(state(d), ensure_ascii=False))
    # repeated finish
    rc2, out2, err2 = finish(d)
    rec.add("repeated finish refused", 0 if rc2 != 0 else 1, out2, err2)
    # reopen a complete draft
    rc, out, err = call("reopen", str(d), "--reason", "fix typo")
    newd = Path(out.strip().splitlines()[-1]) if rc == 0 else None
    rec.add("reopen", rc, out, err)
    rec.add("old superseded", 0, json.dumps(state(d), ensure_ascii=False))
    rec.add("new complete", 0, json.dumps(state(newd), ensure_ascii=False) if newd else "none")
    if newd:
        # simulate a crash after the new draft is published but before the old marker
        (d / "SUPERSEDED").unlink(missing_ok=True)
        rec.add("reopen crash window: both complete", 0,
                json.dumps({"old": state(d)["state"], "new": state(newd)["state"]},
                           ensure_ascii=False))
        (d / "SUPERSEDED").write_text(yaml.safe_dump({"superseded_by": newd.name},
                                                      sort_keys=False), encoding="utf-8")
    # post-completion edit on a separate draft
    edited = new(repo)
    fill(edited)
    finish(edited)
    (edited / "case.yaml").write_text((edited / "case.yaml").read_text(encoding="utf-8") + "\n# edit\n",
                                      encoding="utf-8")
    rec.add("reader after edit", 0, json.dumps(state(edited), ensure_ascii=False))
    # crash points
    crash = new(repo)  # no files
    rec.add("crash after mkdir", 0, json.dumps(state(crash), ensure_ascii=False))
    partial = new(repo)
    (partial / "case.yaml").write_text("cases:\n  - id: VLLM-ASC-93009\n    title: \"half", encoding="utf-8")
    rec.add("partial file", 0, json.dumps(state(partial), ensure_ascii=False))
    trunc = new(repo)
    fill(trunc)
    (trunc / "DONE").write_text("completed_at: \"x\"\n", encoding="utf-8")
    rec.add("truncated DONE", 0, json.dumps(state(trunc), ensure_ascii=False))
    # two clones: UUIDs differ even with same deployment.yaml
    b = L.fresh("a2-b")
    (repo / "deployment.yaml").write_text("deployment:\n  id: shared-deployment\n", encoding="utf-8")
    (b / "deployment.yaml").write_text("deployment:\n  id: shared-deployment\n", encoding="utf-8")
    da, db = new(repo), new(b)
    rec.add("same deployment id, distinct draft UUIDs", 0 if da.name != db.name else 1,
            f"{da.name} vs {db.name}")
    fill(db)
    finish(db)
    # copied draft
    import shutil
    copied = repo / "postmortems/inbox" / (db.name + "-copy")
    shutil.copytree(db, copied)
    # sources draft_id no longer matches dir -> corrupt by design
    rec.add("copied draft with renamed dir", 0, json.dumps(state(copied), ensure_ascii=False))
    # legacy
    (repo / "postmortems/inbox/VLLM-ASC-LEGACY.case.yaml").write_text(
        F.case_text(L.case("VLLM-ASC-LEGACY")), encoding="utf-8")
    (repo / "postmortems/inbox/VLLM-ASC-LEGACY.md").write_text("# old\n", encoding="utf-8")
    rc, out, err = call("list", "--root", str(repo), "--json")
    rec.add("legacy flat listed", rc, out, err)
    # actual draft validator
    rc, out, err = L.py(repo / "scripts/verify_case_draft.py", str((newd or d) / "case.yaml"), cwd=repo)
    rec.add("verify_case_draft on draft case", rc, out, err)
    rec.show()
    print(rec.dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
