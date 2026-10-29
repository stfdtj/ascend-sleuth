"""Stage I / B2-B5, B7: two independent engineers, separate clones, same baseline.

Scenario 2 of the task ("separate deployments"): each engineer has their own clone,
own inbox, own traces; neither can see the other's local draft before integration.
Knowledge is integrated through a shared bare remote, in two orders.

Also covers:
  - B3 (E4/E5): same case id/path, different content -> Git conflict; resolve by
    taking one side; run every gate -> green while the other side's content is gone.
  - B4 (E6): disjoint line edits to one case -> clean merge producing a
    semantically contradictory file; every gate green.
  - B7 (E7): generated artifacts absent from PRs (no conflict, guard passes);
    guard rejects a PR that carries generated artifacts; the post-merge rebuild job
    is what makes main consistent, and without it main is silently stale.

Order comparison detail: both integration clones are made from the same baseline
BEFORE either integration pushes main, so order A->B and order B->A really start
from the same tree.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fixtures as F
import lab_common as L

CASE_A = F.CASE_A
CASE_B = F.CASE_B
CASE_X_A = F.CASE_X
CASE_X_B = dict(F.CASE_X,
                detail="工程师 B 的现场：改 HCCL_IF_BASE_PORT 后仍然偶发",
                root_cause="HCCL 端口复用与 Mooncake kv_port 冲突",
                fix="把 kv_port 与 HCCL_IF_BASE_PORT 都改成不冲突的端口段",
                symptoms=["多机启动卡在 HCCL init", "日志出现 EADDRINUSE 与 kv_port 冲突"])

CASE_Y = {
    "id": "VLLM-ASC-90004",
    "title": "310P 上 torch_npu 版本不匹配导致 import 失败",
    "category": "interrupt",
    "tags": ["310p", "torch-npu", "import"],
    "platforms": ["A2-310P"],
    "ranges": ["==0.22.0"],
    "symptoms": ["import torch_npu 报 undefined symbol"],
    "cmd": "grep -c 'undefined symbol' {{log_path}}",
    "expected": "regex:^[1-9]",
    "cheks": [("check", "torch_npu 与 torch 版本是否匹配")],
    "severity": "service-affecting",
    "fix_type": "env-var",
    "detail": "换匹配版本的 torch_npu wheel 后 import 正常",
    "root_cause": "torch_npu 与 torch 版本不匹配",
    "fix": "安装与 torch 版本匹配的 torch_npu wheel",
    "session": "2026-10-28-conc-d01",
}


def shared_dir(repo: Path, name: str) -> Path:
    rc, out, err = L.py(repo / "scripts/shared_dir.py", name, cwd=repo)
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    assert rc == 0 and lines, f"shared_dir {name}: {rc} {out} {err}"
    return Path(lines[-1])


def work(repo: Path, case: dict, ns: str, cat: str, tag: str, rec,
         novelty: str = "new_pattern"):
    """diagnosis trace -> draft -> verify -> gate -> promote -> source-only commit."""
    sid = case["session"]
    F.write_trace(repo, sid,
                  summary=f"{case['title']}（工程师 {tag} 的 session）",
                  user_msg=case["symptoms"][0],
                  cand=f"{case['title']}；同格视图无候选",
                  active_case=None, feedback_outcome=None)
    inbox = shared_dir(repo, "inbox")
    case_path, _md = F.write_draft(inbox, case, novelty, sid,
                                   needle=case["symptoms"][0], body=case["detail"])
    rc, out, err = L.py(repo / "scripts/verify_case_draft.py", str(case_path), cwd=repo)
    rec.add(f"{tag}: verify_case_draft draft", rc, out, err)
    rc, out, err = L.py(repo / "scripts/verify_case_draft.py", "--gate", str(case_path),
                        "--root", str(repo), cwd=repo)
    rec.add(f"{tag}: promotion gate", rc, out, err)
    dest = F.promote(case_path, repo, ns, cat)
    rc, out, err = L.git(repo, "checkout", "-b", f"kb/{tag}")
    rec.add(f"{tag}: create branch kb/{tag}", rc, out, err)
    L.git(repo, "add", str(dest.relative_to(repo)))
    rc, out, err = L.git(repo, "commit", "-m", f"kb: {case['id']} ({tag})", env=L.GIT_ENV)
    rec.add(f"{tag}: commit source-only", rc, out, err)
    rc, out, err = L.git(repo, "push", "-q", "-u", "origin", f"kb/{tag}")
    rec.add(f"{tag}: push", rc, out, err)
    return dest


def post_merge_job(repo: Path, rec, label: str, push: bool = True):
    """Exact semantics of .github/workflows/rebuild-generated.yml, run locally."""
    rc, out, err = L.py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
    rec.add(f"{label}: rebuild job --check", rc, out, err)
    rc, dirty, _ = L.git(repo, "status", "--porcelain")
    rec.add(f"{label}: rebuild job sees dirty generated artifacts", rc, dirty,
            dirty=bool(dirty.strip()))
    if dirty.strip():
        L.git(repo, "add", "-A")
        rc, out, err = L.git(repo, "commit", "-m", "chore: rebuild generated views", env=L.GIT_ENV)
        rec.add(f"{label}: rebuild job commits generated views", rc, out, err)
        if push:
            rc, out, err = L.git(repo, "push", "origin", "main")
            rec.add(f"{label}: rebuild job pushes main", rc, out, err)
    return bool(dirty.strip())


def merge_pr(repo: Path, branch: str, rec, label: str):
    rc, out, err = L.git(repo, "merge", "--no-ff", "-m", f"merge PR {branch}",
                         f"origin/{branch}", env=L.GIT_ENV)
    conflicted = []
    if rc != 0:
        _, names, _ = L.git(repo, "diff", "--name-only", "--diff-filter=U")
        conflicted = [n for n in names.splitlines() if n.strip()]
    rec.add(f"{label}: merge {branch}", rc, out, err, conflicted=conflicted)
    return rc, conflicted


def run_gates(repo: Path, rec, label: str):
    checks = [
        ("verify_case_draft --all", ["scripts/verify_case_draft.py", "--all"]),
        ("build_index --check", ["scripts/build_index.py", "--check"]),
        ("verify_references --check", ["scripts/verify_references.py", "--check"]),
        ("verify_entry_activity", ["scripts/verify_entry_activity.py"]),
        ("verify_metrics --check", ["scripts/verify_metrics.py", "--check"]),
        ("holdout --check", ["scripts/holdout.py", "--check"]),
        ("eval_scorecard --check", ["scripts/eval_scorecard.py", "--check"]),
    ]
    results = {}
    for name, args in checks:
        rc, out, err = L.py(repo / args[0], *args[1:], cwd=repo)
        rec.add(f"{label}: {name}", rc, out, err)
        results[name] = rc
    return results


def index_contains(repo: Path, cid: str) -> dict:
    out = {}
    for rel in ("knowledge/_index.yaml",
                "knowledge/_index/inference__vllm-ascend.list",
                "knowledge/_index/inference__vllm-ascend__interrupt.list",
                "knowledge/_index/inference__vllm-ascend__precision.list"):
        p = repo / rel
        out[rel] = (cid in p.read_text(encoding="utf-8")) if p.exists() else None
    return out


def clone_with_identity(name: str) -> Path:
    repo = L.fresh_clone(name)
    L.git(repo, "config", "user.name", name)
    L.git(repo, "config", "user.email", f"{name}@lab.local")
    return repo


def main() -> int:
    rec = L.Recorder("engineers")
    base = L.reset_origin()
    rec.note(f"baseline: {base}")

    # ---------------------------------------------------------------- setup
    engA, engB = clone_with_identity("engA"), clone_with_identity("engB")

    # ---------------------------------------------------------------- 1. both diagnose
    work(engA, CASE_A, "inference/vllm-ascend", "interrupt", "a1", rec)
    work(engB, CASE_B, "inference/vllm-ascend", "precision", "b1", rec)

    # B's documented pre-triage source: its own (namespace x category) cell view.
    view = engB / "knowledge/_index/inference__vllm-ascend__precision.list"
    txt = view.read_text(encoding="utf-8")
    rec.add("B pre-triage: read own cell view", 0,
            f"rows={len(txt.splitlines())}; contains A id={CASE_A['id'] in txt}; "
            f"contains A title keyword={'310P' in txt}")
    rec.add("B local index does not contain A (B never fetched A's branch)", 0,
            f"contains A id in B's _index.yaml: "
            f"{CASE_A['id'] in (engB / 'knowledge/_index.yaml').read_text(encoding='utf-8')}")

    # ---------------------------------------------------------------- 2. two orders, same base
    int_ab, int_ba = L.fresh_clone("int_ab"), L.fresh_clone("int_ba")
    for repo in (int_ab, int_ba):
        L.git(repo, "config", "user.name", "integrator")
        L.git(repo, "config", "user.email", "integrator@lab.local")

    merge_pr(int_ab, "kb/a1", rec, "order A-first")
    post_merge_job(int_ab, rec, "order A-first", push=False)
    rec.add("order A-first: A visible right after A merged", 0,
            json.dumps(index_contains(int_ab, CASE_A["id"])))
    rc_ab, conf_ab = merge_pr(int_ab, "kb/b1", rec, "order A-first")
    post_merge_job(int_ab, rec, "order A-first", push=False)
    gates_ab = run_gates(int_ab, rec, "order A-first")

    merge_pr(int_ba, "kb/b1", rec, "order B-first")
    post_merge_job(int_ba, rec, "order B-first", push=False)
    rc_ba, conf_ba = merge_pr(int_ba, "kb/a1", rec, "order B-first")
    post_merge_job(int_ba, rec, "order B-first", push=False)
    gates_ba = run_gates(int_ba, rec, "order B-first")

    rec.add("ORDER COMPARISON", 0,
            f"A-first conflicts={conf_ab}; B-first conflicts={conf_ba}; "
            f"gates A-first={gates_ab}; gates B-first={gates_ba}",
            conflicts_a_first=conf_ab, conflicts_b_first=conf_ba)
    for label, repo in (("A-first", int_ab), ("B-first", int_ba)):
        rec.add(f"{label}: both duplicate cases present in the class views", 0,
                json.dumps({cid: index_contains(repo, cid) for cid in (CASE_A["id"], CASE_B["id"])}),
                both_present=all(index_contains(repo, cid)[
                    "knowledge/_index/inference__vllm-ascend__interrupt.list"] or
                    index_contains(repo, cid)[
                    "knowledge/_index/inference__vllm-ascend__precision.list"]
                    for cid in (CASE_A["id"], CASE_B["id"])))

    dup = L.run(["git", "grep", "-n", "-E", "find_duplicates|merge_recheck|查重|重复候选",
                 "--", "scripts", ".github/workflows", "skills"], cwd=int_ab)
    rec.add("repository-wide duplicate-check / merge-recheck implementation present?", dup[0],
            dup[1], dup[2])

    # latest main = A-first integration (both cases present); publish it as the new main
    L.git(int_ab, "push", "origin", "main")
    rec.add("publish integrated main (A then B) to the lab remote", 0, "")

    # ---------------------------------------------------------------- 3. stale novelty (E8)
    rec.add("stale-check: B's novelty conclusion was produced against base", 0,
            f"base={base}; B's merged index already has A: "
            f"{CASE_A['id'] in (engB / 'knowledge/_index.yaml').read_text(encoding='utf-8')}")
    rc, out, err = L.py(int_ab / "scripts/find_duplicates.py", "--drafts", "postmortems/inbox",
                        "--library", "knowledge/", cwd=int_ab)
    rec.add("attempt to run the proposal's duplicate finder on the merged repo", rc, out, err)
    rec.add("duplicate check at merge time (no recheck step in workflow)", 0,
            "no script, no workflow step, no PR-template field; see grep above")

    # ---------------------------------------------------------------- 4. E4/E5 same path conflict
    engA2, engB2 = clone_with_identity("engA2"), clone_with_identity("engB2")
    work(engA2, CASE_X_A, "inference/vllm-ascend", "interrupt", "x-a", rec)
    work(engB2, CASE_X_B, "inference/vllm-ascend", "interrupt", "x-b", rec)
    int_x = L.fresh_clone("int_x")
    L.git(int_x, "config", "user.name", "integrator")
    L.git(int_x, "config", "user.email", "integrator@lab.local")
    merge_pr(int_x, "kb/x-a", rec, "same-path")
    post_merge_job(int_x, rec, "same-path", push=False)
    rc, conflicted = merge_pr(int_x, "kb/x-b", rec, "same-path")
    rec.note(f"same-path conflicted files: {conflicted}")
    for f in conflicted:
        L.git(int_x, "checkout", "--ours", "--", f)
    L.git(int_x, "add", "-A")
    rc, out, err = L.git(int_x, "commit", "-m", "merge kb/x-b (ours)", env=L.GIT_ENV)
    rec.add("same-path: resolve by taking A's whole file", rc, out, err)
    post_merge_job(int_x, rec, "same-path", push=False)
    run_gates(int_x, rec, "same-path")
    merged_text = (int_x / "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-90003.yaml"
                   ).read_text(encoding="utf-8")
    rec.add("same-path: B's unique content present in merged result?", 0,
            f"B root_cause present={'Mooncake' in merged_text}; B fix present={'kv_port' in merged_text}; "
            f"A root_cause present={'固定 HCCL 端口' in merged_text}",
            b_lost=("Mooncake" not in merged_text))

    # ---------------------------------------------------------------- 5. E6 clean merge, contradictory
    engA3, engB3 = clone_with_identity("engA3"), clone_with_identity("engB3")
    target = "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-90001.yaml"
    edits = [
        (engA3, "patch-a", '        ranges: ["==0.22.0"]',
         '        ranges: ["==0.22.0", "==0.21.0"]'),
        (engB3, "patch-b", "    severity: service-affecting",
         '      - step: 3\n'
         '        check: "该问题是否只在 0.22.0 出现（0.21.0 没有这条路径）"\n'
         "    severity: service-affecting"),
    ]
    for repo, tag, old, new in edits:
        p = repo / target
        text = p.read_text(encoding="utf-8")
        assert old in text, (repo, old)
        p.write_text(text.replace(old, new, 1), encoding="utf-8")
        L.git(repo, "checkout", "-b", f"kb/{tag}")
        L.git(repo, "add", target)
        rc, out, err = L.git(repo, "commit", "-m", f"{tag}: disjoint edit of 90001", env=L.GIT_ENV)
        rec.add(f"E6 {tag}: commit", rc, out, err)
        L.git(repo, "push", "-q", "-u", "origin", f"kb/{tag}")
    int_e6 = L.fresh_clone("int_e6")
    L.git(int_e6, "config", "user.name", "integrator")
    L.git(int_e6, "config", "user.email", "integrator@lab.local")
    merge_pr(int_e6, "kb/patch-a", rec, "E6")
    post_merge_job(int_e6, rec, "E6", push=False)
    rc, conflicted = merge_pr(int_e6, "kb/patch-b", rec, "E6")
    rec.add("E6: merge result (rc=0 and no conflicts means a clean auto-merge)", rc,
            f"conflicted={conflicted}")
    text = (int_e6 / target).read_text(encoding="utf-8")
    rec.add("E6: merged file content", 0, text)
    post_merge_job(int_e6, rec, "E6", push=False)
    run_gates(int_e6, rec, "E6")
    rec.note("E6 merged file contains both the widened compat range and the "
             "'only 0.22.0' step: semantically contradictory, mechanically green")

    # ---------------------------------------------------------------- 6. E7 generated plane
    # (a) current discipline: a source-only PR branch -> guard passes
    rc, out, err = L.py(engA2 / "scripts/check_generated_untouched.py", "--base", "origin/main",
                        cwd=engA2)
    rec.add("E7: generated-guard on a source-only PR branch (kb/x-a)", rc, out, err)
    # (b) old discipline: a PR that carries generated artifacts -> guard rejects
    engC = clone_with_identity("engC")
    idx = engC / "knowledge/_index.yaml"
    idx.write_text(idx.read_text(encoding="utf-8") + "\n# hand edit\n", encoding="utf-8")
    L.git(engC, "checkout", "-b", "kb/with-generated")
    L.git(engC, "add", "knowledge/_index.yaml")
    L.git(engC, "commit", "-m", "kb: carries generated index (old discipline)", env=L.GIT_ENV)
    rc, out, err = L.py(engC / "scripts/check_generated_untouched.py", "--base", "origin/main",
                        cwd=engC)
    rec.add("E7: generated-guard on a PR that carries generated artifacts", rc, out, err)
    # (c) deployment without the post-merge job: main stays stale, no CI signal
    engD = clone_with_identity("engD")
    work(engD, CASE_Y, "inference/vllm-ascend", "interrupt", "y-a", rec)
    int_nojob = L.fresh_clone("int_nojob")
    L.git(int_nojob, "config", "user.name", "int_nojob")
    L.git(int_nojob, "config", "user.email", "int_nojob@lab.local")
    merge_pr(int_nojob, "kb/y-a", rec, "E7-nojob")
    rc, out, err = L.py(int_nojob / "scripts/build_index.py", "--check", cwd=int_nojob)
    rec.add("E7-nojob: build_index --check on merged main WITHOUT running the rebuild job",
            rc, out, err)
    rc, out, err = L.py(int_nojob / "scripts/verify_case_draft.py", "--all", cwd=int_nojob)
    rec.add("E7-nojob: verify_case_draft --all still green", rc, out, err)
    rec.add("E7-nojob: new case visible in index?", 0,
            json.dumps(index_contains(int_nojob, CASE_Y["id"])))

    path = rec.dump()
    rec.print_summary()
    print(f"\nrecord: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
