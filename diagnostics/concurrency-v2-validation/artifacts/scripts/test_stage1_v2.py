#!/usr/bin/env python3
"""Stage I: current end-to-end workflow on the current HEAD (control)."""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab_v2 as L

HERE = Path(__file__).parent
PY = sys.executable
ID = "VLLM-ASC-95001"
SESSION = "v2-20261029-95001"


def main():
    L.reset_origin()
    repo = L.fresh("s1")
    rec = L.Rec("v2-stage1")
    c = L.case(ID, title="310P bf16 启动失败（V2 control）", session=SESSION,
               root_cause="310P 不支持 bfloat16", fix="dtype 改 float16",
               symptoms=["npu-smi 310P", "bfloat16 is not supported"])
    L.F.write_trace(repo, SESSION, summary="V2 control diagnosis",
                    user_msg="310P bf16 startup", cand="new case", active_case=None)
    rc, out, err = L.py(repo / "scripts/sediment_batch.py", "--json", cwd=repo)
    rec.add("sediment_batch", rc, out, err)
    inbox = repo / "postmortems/inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    draft = inbox / f"{ID}.case.yaml"
    md = inbox / f"{ID}.md"
    draft.write_text(L.F.case_text(c), encoding="utf-8")
    md.write_text("# control\n", encoding="utf-8")
    rc, out, err = L.py(repo / "scripts/verify_case_draft.py", str(draft), cwd=repo)
    rec.add("draft verify", rc, out, err)
    rc, out, err = L.py(repo / "scripts/verify_case_draft.py", "--gate", str(draft), "--root", str(repo), cwd=repo)
    rec.add("gate", rc, out, err)
    dest = repo / "knowledge/inference/vllm-ascend/interrupt" / f"{ID}.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = draft.read_text(encoding="utf-8")
    dest.write_text(body[body.index("cases:"):], encoding="utf-8")
    rc, out, err = L.py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
    rec.add("rebuild", rc, out, err)
    L.git(repo, "checkout", "--", ".")
    L.git(repo, "checkout", "-q", "-B", "kb/s1", "main")
    L.commit(repo, "kb: add " + ID)
    rc, out, err = L.py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
    rec.add("CI emulation: rebuild before index check", rc, out, err)
    rc, out, err = L.py(repo / "scripts/build_index.py", "--check", cwd=repo)
    rec.add("gate index (after CI rebuild action)", rc, out, err)
    L.git(repo, "checkout", "--", ".")
    for name, args in (("case structure", ["scripts/verify_case_draft.py", "--all"]),
                       ("references", ["scripts/verify_references.py", "--check"]),
                       ("entry", ["scripts/verify_entry_activity.py"]),
                       ("metrics", ["scripts/verify_metrics.py", "--check"]),
                       ("holdout", ["scripts/holdout.py", "--check"])):
        rc, out, err = L.py(repo / args[0], *args[1:], cwd=repo)
        rec.add("gate " + name, rc, out, err)
    L.git(repo, "push", "-q", "origin", "kb/s1")
    integ = L.fresh("s1-int")
    rc, out, err = L.git(integ, "merge", "--no-ff", "-m", "merge kb/s1", "origin/kb/s1")
    rec.add("merge", rc, out, err)
    rc, out, err = L.py(integ / "scripts/rebuild_generated.py", "--check", cwd=integ)
    rec.add("post-merge rebuild", rc, out, err)
    L.commit(integ, "chore: rebuild generated views")
    L.git(integ, "push", "origin", "main")
    text = (integ / "knowledge/_index/inference__vllm-ascend__interrupt.list").read_text(encoding="utf-8")
    rec.add("retrieval", 0 if ID in text else 1, f"present={ID in text}")
    rec.show()
    print(rec.dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
