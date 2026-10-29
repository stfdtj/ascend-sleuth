"""Checkpoint C V2 tests: stale decisions, field diff, same-path, rename, generated, block."""
from __future__ import annotations
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import lab_v2 as L

HERE = Path(__file__).parent
PROTO = HERE.parent / "proto"
C = PROTO / "merge_recheck_v2.py"
PY = sys.executable
CASE = "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-93001.yaml"


def c_run(repo, base, head, decision=None):
    args = [PY, str(C), "--root", str(repo), "--base", base, "--head", head, "--json"]
    if decision:
        args += ["--decision", str(decision)]
    rc, out, err = L.run(args, cwd=HERE)
    return rc, (json.loads(out) if rc in (0, 1, 2, 3, 4) and out.strip().startswith("{") else None), err


def branch(repo, name, fn, base="main"):
    L.git(repo, "checkout", "-q", "-B", name, base)
    fn()
    rc, out, err = L.commit(repo, name)
    assert rc == 0, (out, err)
    L.git(repo, "checkout", "-q", "main")


def main():
    L.reset_origin()
    repo = L.fresh("c2")
    L.write_case(repo, CASE, L.case("VLLM-ASC-93001"))
    L.commit(repo, "base case")
    base = L.git(repo, "rev-parse", "main")[1]
    rec = L.Rec("v2-c")

    def add_dup():
        L.write_case(repo, "knowledge/inference/vllm-ascend/precision/VLLM-ASC-93002.yaml",
                     L.case("VLLM-ASC-93002", category="precision",
                            title="HCCL 端口冲突导致启动超时（precision 视角）",
                            symptoms=["多机初始化卡住", "日志里 HCCL 端口地址占用"],
                            root_cause="多机并用固定 HCCL 端口，第二个进程 bind 失败",
                            fix="export HCCL_IF_BASE_PORT=<不同端口> 后重启"))

    branch(repo, "kb/dup", add_dup)
    rc, payload, err = c_run(repo, base, "kb/dup")
    rec.add("C duplicate/no decision", rc, json.dumps(payload, ensure_ascii=False)[:4000], err)
    if payload and payload.get("pairs"):
        L.git(repo, "checkout", "-q", "kb/dup")
        (repo / "postmortems/decisions").mkdir(parents=True, exist_ok=True)
        dec = repo / "postmortems/decisions/VLLM-ASC-93002.yaml"
        dec.write_text(yaml.safe_dump({
            "case_id": "VLLM-ASC-93002", "decision": "separate",
            "main_sha": payload["base"], "head_sha": payload["head"],
            "pairs": [{"pair_id": p["pair_id"], "other": p["b"], "tier": p["tier"],
                       "decision": "separate", "note": "same incident, keep both"} for p in payload["pairs"]],
            "overflow": {"hidden_high": payload["hidden_high"],
                         "ack": {"hidden_count": payload["hidden_high"], "reason": "reviewed top set",
                                 "reviewer": "v2-test"}},
            "same_case": [],
        }, allow_unicode=True, sort_keys=False), encoding="utf-8")
        L.commit(repo, "decision")
        rc2, payload2, err2 = c_run(repo, base, "kb/dup", dec)
        rec.add("C duplicate/with decision", rc2, json.dumps(payload2, ensure_ascii=False)[:3000], err2)
        # placeholder decision still satisfies coverage
        d0 = yaml.safe_load(dec.read_text(encoding="utf-8"))
        d0["pairs"][0]["decision"] = "TODO"
        dec.write_text(yaml.safe_dump(d0, allow_unicode=True, sort_keys=False), encoding="utf-8")
        L.commit(repo, "placeholder decision")
        rc_todo, payload_todo, err_todo = c_run(repo, base, "kb/dup", dec)
        rec.add("C placeholder TODO decision accepted?", rc_todo,
                json.dumps(payload_todo, ensure_ascii=False)[:1500], err_todo)
        d0["pairs"][0]["decision"] = "separate"
        dec.write_text(yaml.safe_dump(d0, allow_unicode=True, sort_keys=False), encoding="utf-8")
        L.commit(repo, "restore decision")
        # change the head after the decision: head_sha is recorded but not enforced
        case_path = repo / "knowledge/inference/vllm-ascend/precision/VLLM-ASC-93002.yaml"
        case_path.write_text(case_path.read_text(encoding="utf-8") + "\n    # post-decision edit\n",
                             encoding="utf-8")
        L.commit(repo, "post-decision head change")
        rc_head, payload_head, err_head = c_run(repo, base, "kb/dup", dec)
        rec.add("C head changed after decision (head_sha unchecked)", rc_head,
                json.dumps(payload_head, ensure_ascii=False)[:1200], err_head)
        # main advances after the decision
        L.git(repo, "checkout", "-q", "main")
        L.write_case(repo, "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-93003.yaml",
                     L.case("VLLM-ASC-93003"))
        L.commit(repo, "main advances")
        newbase = L.git(repo, "rev-parse", "main")[1]
        L.git(repo, "checkout", "-q", "kb/dup")
        rc3, payload3, err3 = c_run(repo, newbase, "kb/dup", dec)
        rec.add("C stale decision after main advances", rc3, json.dumps(payload3, ensure_ascii=False)[:2000], err3)
        # refresh main_sha; head unchanged
        d = yaml.safe_load(dec.read_text(encoding="utf-8"))
        d["main_sha"] = newbase
        d["pairs"] = [{"pair_id": p["pair_id"], "other": p["b"], "tier": p["tier"],
                       "decision": "separate", "note": "refreshed after main advance"}
                      for p in (payload3["pairs"] if payload3 else [])]
        dec.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
        L.commit(repo, "refresh decision")
        rc4, payload4, err4 = c_run(repo, newbase, "kb/dup", dec)
        rec.add("C refreshed decision", rc4, json.dumps(payload4, ensure_ascii=False)[:1500], err4)
        # merge
        L.git(repo, "checkout", "-q", "main")
        L.git(repo, "merge", "--no-ff", "-m", "merge kb/dup", "kb/dup")
        rec.add("C merge after gate", 0, "merged")

    # same-path add/add from a fresh baseline without 93001
    repo2 = L.fresh("c2b")
    L.write_case(repo2, "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-93011.yaml", L.case("VLLM-ASC-93011"))
    L.commit(repo2, "other base")
    b2 = L.git(repo2, "rev-parse", "main")[1]
    branch(repo2, "kb/a", lambda: L.write_case(repo2, "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-93012.yaml", L.case("VLLM-ASC-93012")))
    branch(repo2, "kb/b", lambda: L.write_case(repo2, "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-93012.yaml",
                                                L.case("VLLM-ASC-93012", root_cause="different root cause",
                                                       fix="different fix")))
    L.git(repo2, "checkout", "-q", "main")
    L.git(repo2, "merge", "--no-ff", "-m", "merge a", "kb/a")
    rc, payload, err = c_run(repo2, "main", "kb/b")
    rec.add("C same-path add/add", rc, json.dumps(payload, ensure_ascii=False)[:2000], err)

    # both modify same case: main fixes, branch changes compat
    repo3 = L.fresh("c2c")
    L.write_case(repo3, CASE, L.case("VLLM-ASC-93001"))
    L.commit(repo3, "base")
    b3 = L.git(repo3, "rev-parse", "main")[1]
    branch(repo3, "kb/compat", lambda: (repo3 / CASE).write_text(
        (repo3 / CASE).read_text(encoding="utf-8").replace('        ranges: ["==0.22.0"]',
                                                           '        ranges: ["==0.22.0", "==0.21.0"]'),
        encoding="utf-8"))
    branch(repo3, "kb/fix", lambda: (repo3 / CASE).write_text(
        (repo3 / CASE).read_text(encoding="utf-8").replace(
            'fix: "export HCCL_IF_BASE_PORT=<不同端口> 后重启"',
            'fix: "升级到 0.23.0 后改 HCCL_IF_BASE_PORT"'), encoding="utf-8"))
    L.git(repo3, "checkout", "-q", "main")
    L.git(repo3, "merge", "--no-ff", "-m", "merge compat", "kb/compat")
    rc, payload, err = c_run(repo3, "main", "kb/fix")
    rec.add("C both modify disjoint fields/no decision", rc, json.dumps(payload, ensure_ascii=False)[:2500], err)
    if payload:
        L.git(repo3, "checkout", "-q", "kb/fix")
        (repo3 / "postmortems/decisions").mkdir(parents=True, exist_ok=True)
        dec = repo3 / "postmortems/decisions/VLLM-ASC-93001.yaml"
        dec.write_text(yaml.safe_dump({
            "case_id": "VLLM-ASC-93001", "decision": "separate",
            "main_sha": payload["base"], "head_sha": payload["head"],
            "pairs": [{"pair_id": p["pair_id"], "other": p["b"], "tier": p["tier"],
                       "decision": "separate", "note": "reviewed"} for p in payload["pairs"]],
            "overflow": {"hidden_high": payload["hidden_high"], "ack": None},
            "same_case": [{"case_id": "VLLM-ASC-93001", "fields": ["compat", "fix"],
                           "decision": "keep_both", "note": "conditions disjoint"}],
        }, allow_unicode=True, sort_keys=False), encoding="utf-8")
        L.commit(repo3, "same-case decision")
        rc2, payload2, err2 = c_run(repo3, "main", "kb/fix", dec)
        rec.add("C both modify/disjoint with decision", rc2, json.dumps(payload2, ensure_ascii=False)[:1800], err2)
        d3 = yaml.safe_load(dec.read_text(encoding="utf-8"))
        if d3.get("same_case"):
            d3["same_case"][0]["decision"] = "TODO"
            dec.write_text(yaml.safe_dump(d3, allow_unicode=True, sort_keys=False), encoding="utf-8")
            L.commit(repo3, "same-case placeholder")
            rc_t, payload_t, err_t = c_run(repo3, "main", "kb/fix", dec)
            rec.add("C same-case TODO accepted?", rc_t, json.dumps(payload_t, ensure_ascii=False)[:1200], err_t)

    # generated artifact
    repo4 = L.fresh("c2d")
    L.write_case(repo4, CASE, L.case("VLLM-ASC-93001"))
    L.commit(repo4, "base")
    b4 = L.git(repo4, "rev-parse", "main")[1]
    branch(repo4, "kb/gen", lambda: (repo4 / "knowledge/_index.yaml").write_text(
        (repo4 / "knowledge/_index.yaml").read_text(encoding="utf-8") + "\n# hand edit\n", encoding="utf-8"))
    rc, payload, err = c_run(repo4, b4, "kb/gen")
    rec.add("C generated artifact", rc, json.dumps(payload, ensure_ascii=False)[:1200], err)

    # rename on one side, reference on the other
    repo5 = L.fresh("c2e")
    L.write_case(repo5, CASE, L.case("VLLM-ASC-93001"))
    L.commit(repo5, "base")

    def do_rename():
        L.git(repo5, "mv", CASE, "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-93001R.yaml")
        p = repo5 / "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-93001R.yaml"
        p.write_text(p.read_text(encoding="utf-8").replace("VLLM-ASC-93001", "VLLM-ASC-93001R"),
                     encoding="utf-8")

    branch(repo5, "kb/rename", do_rename)
    L.git(repo5, "checkout", "-q", "main")
    L.write_case(repo5, "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-93002.yaml",
                 L.case("VLLM-ASC-93002", fix="follow VLLM-ASC-93001 port fix"))
    L.commit(repo5, "main adds reference")
    rc, payload, err = c_run(repo5, "main", "kb/rename")
    rec.add("C rename vs reference", rc, json.dumps(payload, ensure_ascii=False)[:2000], err)

    rec.show()
    print(rec.dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
