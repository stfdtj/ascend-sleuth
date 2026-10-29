"""Checkpoint C validation: PR races, stale decisions, renames, TOCTOU.

Hand-made branches in a disposable clone; the repository is the seeded main with
VLLM-ASC-90001/90002. Every merge here is a real `git merge`; every recheck is a real
run of the prototype. The point is not that the report is right, but what it cannot
prevent: it is a file a human writes, and no CI job reads it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fixtures as F
import lab_common as L

PY = sys.executable
HERE = Path(__file__).parent
RECHECK = HERE.parent / "proto" / "merge_recheck.py"
PYB = HERE.parent / "proto" / "find_duplicates.py"
CASE_PATH = "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-92001.yaml"


def case(cid: str, **over):
    c = dict(F.CASE_X)
    c.update(over)
    c["id"] = cid
    return c


def write_case(repo: Path, rel: str, c: dict):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(F.case_text(c), encoding="utf-8")


def make_branch(repo: Path, name: str, fn, base: str = "main"):
    L.git(repo, "checkout", "-q", "-B", name, base)
    fn()
    L.git(repo, "add", "-A")
    rc, out, err = L.git(repo, "commit", "-m", f"{name}: scenario", env=L.GIT_ENV)
    assert rc == 0, (out, err)
    L.git(repo, "checkout", "-q", "main")


def run_recheck(repo: Path, branch: str, base: str = "main", report: Path | None = None):
    L.git(repo, "checkout", "-q", branch)
    args = [PY, str(RECHECK), "--root", str(repo), "--base", base, "--head", "HEAD", "--json"]
    if report:
        args += ["--report", str(report)]
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    L.git(repo, "checkout", "-q", "main")
    return p.returncode, json.loads(p.stdout) if p.returncode == 0 else ({}), p.stderr


def run_recheck_text(repo: Path, branch: str, base: str = "main"):
    L.git(repo, "checkout", "-q", branch)
    p = subprocess.run([PY, str(RECHECK), "--root", str(repo), "--base", base],
                       capture_output=True, text=True, encoding="utf-8")
    L.git(repo, "checkout", "-q", "main")
    return p.returncode, p.stdout, p.stderr


def merge(repo: Path, branch: str):
    rc, out, err = L.git(repo, "merge", "--no-ff", "-m", f"merge {branch}", branch, env=L.GIT_ENV)
    conflicted = []
    if rc != 0:
        _, names, _ = L.git(repo, "diff", "--name-only", "--diff-filter=U")
        conflicted = [n for n in names.splitlines() if n.strip()]
    return rc, conflicted, out


def main() -> int:
    rec = L.Recorder("checkpoint-c")
    L.seed_integrated_main()
    repo = L.fresh_clone("c-lab")
    L.git(repo, "config", "user.name", "integrator")
    L.git(repo, "config", "user.email", "integrator@lab.local")
    base_sha = L.git(repo, "rev-parse", "HEAD")[1].strip()
    rec.add("baseline", 0, base_sha)

    # branches from the same baseline
    make_branch(repo, "kb/add-92001", lambda: write_case(repo, CASE_PATH, case("VLLM-ASC-92001")))
    make_branch(repo, "kb/same-path", lambda: write_case(repo, CASE_PATH, case(
        "VLLM-ASC-92001", root_cause="HCCL 端口复用与 Mooncake kv_port 冲突",
        fix="把 kv_port 与 HCCL_IF_BASE_PORT 改成不冲突的端口段",
        symptoms=["多机启动卡在 HCCL init", "EADDRINUSE 与 kv_port 冲突"])))
    make_branch(repo, "kb/dup-different-id", lambda: write_case(
        repo, "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-92002.yaml",
        case("VLLM-ASC-92002", title="HCCL 端口冲突导致启动超时（另一个 ID）",
             symptoms=["多机初始化卡住", "日志里 HCCL 端口地址占用"],
             root_cause="多机并用固定 HCCL 端口，第二个进程 bind 失败",
             fix="export HCCL_IF_BASE_PORT=<不同端口> 后重启")))

    # 1. recheck before A merges: nothing to compare, report written
    rc, payload, err = run_recheck(repo, "kb/same-path")
    rec.add("C1 recheck same-path branch before any merge", rc,
            json.dumps({k: payload.get(k) for k in
                        ("target_main", "head", "merge_base", "same_path_added_both",
                         "both_changed_cases", "candidates")}, ensure_ascii=False),
            err)
    report = L.LOG_DIR / "c-report-before-merge.txt"
    rc, text, err = run_recheck_text(repo, "kb/same-path")
    report.write_text(text, encoding="utf-8")
    rec.add("C1 report written", rc, text[:600], err)

    # 2. A merges; the stale report now exists
    rc, conflicted, out = merge(repo, "kb/add-92001")
    rec.add("C2 merge kb/add-92001 (A) into main", rc, out, conflicted=conflicted)
    rc, payload, err = run_recheck(repo, "kb/same-path", report=report)
    rec.add("C2 recheck after A merged (same path now on both sides)", rc,
            json.dumps({k: payload.get(k) for k in
                        ("both_changed_cases", "same_path_added_both", "stale", "candidates")},
                       ensure_ascii=False), err, stale=payload.get("stale"))

    # 3. nothing blocks the merge: B merges with the old report in hand
    rc, conflicted, out = merge(repo, "kb/same-path")
    rec.add("C3 merge B while holding a stale report", rc, out, conflicted=conflicted)
    L.git(repo, "merge", "--abort")
    rec.add("C3 merge aborted (the conflict is git's doing, not the report's)", 0, "")

    # 4. different IDs, semantically equivalent: does C's comparison nominate?
    rc, payload, err = run_recheck(repo, "kb/dup-different-id")
    dup_pairs = [c for c in payload.get("candidates", [])
                 if {c["a"], c["b"]} == {"VLLM-ASC-92002", "VLLM-ASC-92001"}]
    rec.add("C4 different IDs, same problem: candidate surfaced?", rc,
            json.dumps({"pair": dup_pairs, "all_candidates": payload.get("candidates")},
                       ensure_ascii=False), err)

    # 5. both modify the same case in disjoint fields; C reports both touched
    def edit_compat():
        p = repo / CASE_PATH
        t = p.read_text(encoding="utf-8")
        p.write_text(t.replace('        ranges: ["==0.22.0"]',
                               '        ranges: ["==0.22.0", "==0.21.0"]'), encoding="utf-8")

    def edit_fix():
        p = repo / CASE_PATH
        t = p.read_text(encoding="utf-8")
        p.write_text(t.replace('fix: "export HCCL_IF_BASE_PORT=<不同端口> 后重启"',
                               'fix: "升级到 0.23.0 后改 HCCL_IF_BASE_PORT"'), encoding="utf-8")

    make_branch(repo, "kb/edit-compat", edit_compat)
    make_branch(repo, "kb/edit-fix", edit_fix)
    rc, conflicted, out = merge(repo, "kb/edit-compat")
    rec.add("C5 merge edit-compat into main", rc, out, conflicted=conflicted)
    rc, payload, err = run_recheck(repo, "kb/edit-fix")
    rec.add("C5 recheck edit-fix against main that edited the same case", rc,
            json.dumps({k: payload.get(k) for k in
                        ("both_changed_cases", "same_path_differing", "candidates")},
                       ensure_ascii=False), err)
    rc, conflicted, out = merge(repo, "kb/edit-fix")
    rec.add("C5 merge edit-fix (clean auto-merge produces the combined file)", rc, out,
            conflicted=conflicted)

    # 6. rename on one side, reference on the other
    def do_rename():
        L.git(repo, "mv", CASE_PATH,
              "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-92001R.yaml")
        p = repo / "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-92001R.yaml"
        p.write_text(p.read_text(encoding="utf-8").replace("VLLM-ASC-92001", "VLLM-ASC-92001R"),
                     encoding="utf-8")

    make_branch(repo, "kb/rename-92001", do_rename)
    write_case(repo, "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-92003.yaml",
               case("VLLM-ASC-92003", title="启动超时（引用 92001 的修复）",
                    fix="按 VLLM-ASC-92001 的端口方案处理"))
    L.git(repo, "add", "-A")
    rc, out, err = L.git(repo, "commit", "-m", "main: add 92003 referencing 92001", env=L.GIT_ENV)
    rec.add("C6 main adds a case whose text references 92001", rc, out, err)
    rc, payload, err = run_recheck(repo, "kb/rename-92001")
    rec.add("C6 recheck rename branch against main", rc,
            json.dumps({k: payload.get(k) for k in
                        ("renamed_or_deleted_ids", "dangling_mentions", "both_changed_cases")},
                       ensure_ascii=False), err)
    rc, conflicted, out = merge(repo, "kb/rename-92001")
    rec.add("C6 merge rename (clean?)", rc, out, conflicted=conflicted)
    dan = subprocess.run([PY, str(repo / "scripts/build_index.py"), "--check"],
                         cwd=repo, capture_output=True, text=True, encoding="utf-8")
    rec.add("C6 build_index --check after rename+new case (text reference not machine-checked)",
            dan.returncode, dan.stdout, dan.stderr)

    # 7. generated artifacts in the PR
    L.git(repo, "checkout", "-q", "-B", "kb/touch-generated", "main")
    idx = repo / "knowledge/_index.yaml"
    idx.write_text(idx.read_text(encoding="utf-8") + "\n# hand edit\n", encoding="utf-8")
    L.git(repo, "add", "knowledge/_index.yaml")
    L.git(repo, "commit", "-m", "touch generated", env=L.GIT_ENV)
    L.git(repo, "checkout", "-q", "main")
    rc, payload, err = run_recheck(repo, "kb/touch-generated")
    rec.add("C7 recheck branch that edits generated artifacts", rc,
            json.dumps({"generated_artifacts_touched": payload.get("generated_artifacts_touched")},
                       ensure_ascii=False), err)
    L.git(repo, "checkout", "-q", "kb/touch-generated")
    g = subprocess.run([PY, str(repo / "scripts/check_generated_untouched.py"), "--base", "main"],
                       cwd=repo, capture_output=True, text=True, encoding="utf-8")
    L.git(repo, "checkout", "-q", "main")
    rec.add("C7 generated-guard on the same branch", g.returncode, g.stdout, g.stderr)

    # 8. TOCTOU: report shas go stale after main advances / rebase
    report2 = L.LOG_DIR / "c-report-toctou.txt"
    rc, text, err = run_recheck_text(repo, "kb/dup-different-id")
    report2.write_text(text, encoding="utf-8")
    old_head = L.git(repo, "rev-parse", "kb/dup-different-id")[1].strip()
    # main advances once more
    write_case(repo, "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-92004.yaml",
               case("VLLM-ASC-92004", title="另一个并发进入的知识单元"))
    L.git(repo, "add", "-A")
    L.git(repo, "commit", "-m", "main advances after the recheck", env=L.GIT_ENV)
    new_main = L.git(repo, "rev-parse", "main")[1].strip()
    # rebase the head so its commit changes too
    L.git(repo, "checkout", "-q", "kb/dup-different-id")
    L.git(repo, "rebase", "main")
    new_head = L.git(repo, "rev-parse", "HEAD")[1].strip()
    L.git(repo, "checkout", "-q", "main")
    rc, payload, err = run_recheck(repo, "kb/dup-different-id", report=report2)
    rec.add("C8 recheck the same branch after main advanced and the branch was rebased",
            rc, json.dumps({"stale": payload.get("stale"), "old_head": old_head,
                            "new_head": new_head, "new_main": new_main,
                            "old_report_head": old_head}, ensure_ascii=False), err)
    # nothing in CI reads the report: a body quoting the old shas still passes
    body = ("## 背景与动机\n并发入库。\n\n## 预分诊结论\nnew_pattern。\n\n"
            "## 证据\n复核报告：目标 main " + new_main[:12] + "，待合入提交 " + old_head[:12]
            + "（旧号）。\n\n## 脱敏自查\n已脱敏。\n\n## 完整性\n- [x] 已复核\n")
    p = subprocess.run([PY, str(repo / "scripts/verify_pr_body.py")], cwd=str(repo),
                       input=body, capture_output=True, text=True, encoding="utf-8")
    rec.add("C8 PR body gate on a body quoting the OLD head sha", p.returncode, p.stdout, p.stderr)
    # and the merge still succeeds
    rc, conflicted, out = merge(repo, "kb/dup-different-id")
    rec.add("C8 merge the rebased branch (clean, no recheck enforcement)", rc, out,
            conflicted=conflicted)

    # 9. is any of this wired into CI?
    grep = subprocess.run(["git", "grep", "-n", "-E", "merge_recheck|合并前复核|recheck",
                           "--", ".github/workflows", "scripts", "skills"],
                          cwd=repo, capture_output=True, text=True, encoding="utf-8")
    rec.add("C9 is merge_recheck wired into CI / skills?", grep.returncode, grep.stdout, grep.stderr)

    rec.print_summary()
    print(f"\nrecord: {rec.dump()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
