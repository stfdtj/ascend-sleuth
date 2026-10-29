"""Integrated V2 two-engineer workflow: A merges first, B must revalidate and decide."""
from __future__ import annotations
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import lab_v2 as L

HERE = Path(__file__).parent
PROTO = HERE.parent / "proto"
PY = sys.executable
INBOX = PROTO / "inbox_v2.py"
C = PROTO / "merge_recheck_v2.py"


def new_draft(repo):
    rc, out, err = L.run([PY, str(INBOX), "new", "--root", str(repo)], cwd=HERE)
    assert rc == 0, (out, err)
    return Path(out.strip().splitlines()[-1])


def finish_draft(d, c):
    (d / "case.yaml").write_text(L.F.case_text(c), encoding="utf-8")
    (d / "postmortem.md").write_text(f"# {c['id']}\n", encoding="utf-8")
    rc, out, err = L.run([PY, str(INBOX), "finish", str(d)], cwd=HERE)
    assert rc == 0, (out, err)


def promote(repo, c, branch):
    rel = f"knowledge/inference/vllm-ascend/{c['category']}/{c['id']}.yaml"
    L.git(repo, "checkout", "-q", "-B", branch, "main")
    L.write_case(repo, rel, c)
    return rel


def decision(path, case_id, base, head, pairs, hidden=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({
        "case_id": case_id, "decision": "separate",
        "main_sha": base, "head_sha": head,
        "pairs": [{"pair_id": p["pair_id"], "other": p["b"], "tier": p["tier"],
                   "decision": "separate", "note": "same incident, keep both"} for p in pairs],
        "overflow": {"hidden_high": hidden,
                     "ack": {"hidden_count": hidden, "reason": "reviewed top set",
                             "reviewer": "integrated-test"} if hidden else None},
        "same_case": [],
    }, allow_unicode=True, sort_keys=False), encoding="utf-8")


def c_run(repo, base, head, dec):
    rc, out, err = L.run([PY, str(C), "--root", str(repo), "--base", base, "--head", head,
                          "--json", "--decision", str(dec)], cwd=HERE)
    payload = json.loads(out) if out.strip().startswith("{") else None
    return rc, payload, err


def main():
    L.reset_origin()
    A = L.fresh("i2a")
    B = L.fresh("i2b")
    base = L.git(A, "rev-parse", "main")[1]
    rec = L.Rec("v2-integrated")
    ca = L.case("VLLM-ASC-96001", title="310P bf16 启动失败（A）", category="interrupt",
                root_cause="310P 不支持 bfloat16", fix="把 dtype 改为 float16")
    cb = L.case("VLLM-ASC-96002", title="310P 上输出全 0：dtype 为 bf16（B）", category="precision",
                symptoms=["音频输出全为 0", "npu-smi 310P", "dtype bfloat16"],
                root_cause="310P 不支持 bfloat16", fix="把 dtype 改为 float16")
    da, db = new_draft(A), new_draft(B)
    finish_draft(da, ca)
    finish_draft(db, cb)
    rec.add("A/B drafts complete", 0,
            json.dumps({"A": str(da), "B": str(db)}, ensure_ascii=False))
    rel_a = promote(A, ca, "kb/a")
    L.commit(A, "A: add 96001")
    L.git(A, "push", "-q", "origin", "kb/a")
    rel_b = promote(B, cb, "kb/b")
    dec_b = B / "postmortems/decisions/VLLM-ASC-96002.yaml"
    decision(dec_b, "VLLM-ASC-96002", base, base, [], 0)
    L.commit(B, "B: add 96002 + initial decision")
    L.git(B, "push", "-q", "origin", "kb/b")
    # A merges first through an integration clone
    integ = L.fresh("i2int")
    rc, out, err = L.git(integ, "merge", "--no-ff", "-m", "merge A", "origin/kb/a")
    rec.add("A merge", rc, out, err)
    rc, out, err = L.py(integ / "scripts/rebuild_generated.py", "--check", cwd=integ)
    rec.add("A post-merge rebuild", rc, out, err)
    L.commit(integ, "chore: rebuild after A")
    L.git(integ, "push", "origin", "main")
    # B rebases onto the advanced main
    L.git(B, "fetch", "-q", "origin")
    L.git(B, "rebase", "origin/main")
    newbase = L.git(B, "rev-parse", "origin/main")[1]
    head = L.git(B, "rev-parse", "HEAD")[1]
    rc, payload, err = c_run(B, newbase, head, dec_b)
    rec.add("B C before refresh (stale/missing pair)", rc,
            json.dumps(payload, ensure_ascii=False)[:3000], err)
    rec.add("simulated required check before decision", 1 if rc != 0 else 0,
            f"merge blocked={rc != 0}")
    if payload and payload.get("pairs"):
        decision(dec_b, "VLLM-ASC-96002", newbase, head, payload["pairs"], payload.get("hidden_high", 0))
        L.commit(B, "B: refresh decision after A")
        rc2, payload2, err2 = c_run(B, newbase, head, dec_b)
        rec.add("B C after decision refresh", rc2,
                json.dumps(payload2, ensure_ascii=False)[:2500], err2)
        rec.add("simulated required check after decision", 1 if rc2 != 0 else 0,
                f"merge blocked={rc2 != 0}")
        if rc2 == 0:
            L.git(B, "push", "-q", "origin", "kb/b")
            rc, out, err = L.git(integ, "fetch", "-q", "origin")
            rc, out, err = L.git(integ, "merge", "--no-ff", "-m", "merge B", "origin/kb/b")
            rec.add("B merge after gate", rc, out, err)
            rc, out, err = L.py(integ / "scripts/rebuild_generated.py", "--check", cwd=integ)
            rec.add("post-merge rebuild after B", rc, out, err)
            L.commit(integ, "chore: rebuild after B")
            text = (integ / "knowledge/_index.yaml").read_text(encoding="utf-8")
            rec.add("retrieval both cases", 0 if "VLLM-ASC-96001" in text and "VLLM-ASC-96002" in text else 1,
                    f"96001={'VLLM-ASC-96001' in text} 96002={'VLLM-ASC-96002' in text}")
    rec.show()
    print(rec.dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
