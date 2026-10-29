"""Stage I / B1: one complete production-like run in a disposable clone.

Input -> trace -> draft -> verify -> groom (gate, pre-triage, promote) -> local
validation -> PR branch -> simulated review/merge -> post-merge rebuild job ->
retrieval check.

Every step runs the repository's real command (verify_case_draft.py, sediment_batch.py,
rebuild_generated.py, build_index.py, verify_references.py, ...). Steps that are
human/agent judgement in production (writing the YAML, choosing the category) are
performed here by this script because there is no executable implementation of them;
the report labels those as "agent-performed" rather than "command-executed".
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fixtures as F
import lab_common as L


def shared_dir(repo: Path, name: str) -> Path:
    rc, out, err = L.py(repo / "scripts/shared_dir.py", name, cwd=repo)
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    assert rc == 0 and lines, f"shared_dir {name} failed: {rc} {out} {err}"
    return Path(lines[-1])


def main() -> int:
    rec = L.Recorder("e2e-baseline")
    L.reset_origin()
    repo = L.fresh_clone("e2e")
    git = lambda *a: L.git(repo, *a)
    rec.note(f"baseline commit: {L.git(repo, 'rev-parse', 'HEAD')[1]}")
    assert not (repo / "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-90001.yaml").exists(), \
        "fixture id collides with a real case; pick another synthetic id"

    # ---- 1. diagnosis: a real trace file in the shared traces/ dir -------------
    sid = "2026-10-28-conc-a01"
    F.write_trace(
        repo, sid,
        summary="310P 上 qwen3-tts 启动报 bf16 不支持，改 dtype 为 fp16 后恢复",
        user_msg="310P 机器起 qwen3-tts 直接崩，日志里写 bfloat16 is not supported；配置里 dtype 是 bfloat16",
        cand="310P 不支持 bf16，dtype 需改 fp16；无现有 case 命中",
        active_case=None,
    )
    rc, out, err = L.py(repo / "scripts/sediment_batch.py", "--json", cwd=repo)
    rec.add("sediment_batch --json (workflow entry point for 'what to sediment')", rc, out, err,
            groups=json.loads(out).get("actionable") if rc == 0 else None)

    # ---- 2. sedimentation: to-postmortem output (agent step) -------------------
    inbox = shared_dir(repo, "inbox")
    rec.note(f"inbox resolved by scripts/shared_dir.py: {inbox}")
    case_yaml, md = F.write_draft(
        inbox, F.CASE_A, "new_pattern", sid,
        needle="bfloat16 is not supported on this device",
        body="310P 机器启动 qwen3-tts 即崩，日志尾部报 bfloat16 不被支持；"
             "npu-smi 确认芯片为 310P；把 qwen3_tts.yaml 的 dtype 改成 float16 后启动成功。",
    )
    rec.add("draft files created", 0, stdout=str(case_yaml) + "\n" + str(md),
            draft=str(case_yaml), postmortem=str(md))

    # ---- 3. draft-level structural check --------------------------------------
    rc, out, err = L.py(repo / "scripts/verify_case_draft.py", str(case_yaml), cwd=repo)
    rec.add("verify_case_draft <draft>", rc, out, err)

    # ---- 4. groom: pre-triage against the cell view ---------------------------
    view = repo / "knowledge/_index" / "inference__vllm-ascend__interrupt.list"
    rc, out, err = L.run(["python", "-c",
                          "import sys,pathlib;print(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))",
                          str(view)], cwd=repo)
    rec.add("read cell view (documented candidate source for pre-triage)", rc, out, err,
            view=str(view.relative_to(repo)), lines=len(out.splitlines()))

    rc, out, err = L.py(repo / "scripts/verify_case_draft.py", "--gate", str(case_yaml),
                        "--root", str(repo), cwd=repo)
    rec.add("verify_case_draft --gate (promotion gate)", rc, out, err)

    # ---- 5. promote (groom's structural action) -------------------------------
    dest = F.promote(case_yaml, repo, "inference/vllm-ascend", "interrupt")
    rec.add("promote draft -> knowledge/...", 0, stdout=str(dest.relative_to(repo)),
            dest=str(dest.relative_to(repo)))

    # ---- 6. local generated-artifact check (what groom step 8 runs) -----------
    rc, out, err = L.py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
    rec.add("rebuild_generated --check (groom step 8, regenerates in worktree)", rc, out, err)
    rc2, out2, _ = git("status", "--porcelain")
    rec.add("git status after rebuild (generated artifacts touched, not committed)", rc2, out2)
    gen_changed = [l[3:].strip() for l in out2.splitlines() if l.strip()]
    rec.note(f"generated artifacts changed by rebuild: {gen_changed}")

    # current discipline: PR carries sources only -> restore generated files
    rc, out, err = git("checkout", "--", ".")
    rec.add("restore generated artifacts before committing the PR (source-only PR)", rc, out, err)

    # ---- 7. all PR-side gates the workflow runs -------------------------------
    gates = [
        ("verify_case_draft --all", ["scripts/verify_case_draft.py", "--all"]),
        ("verify_references --check", ["scripts/verify_references.py", "--check"]),
        ("verify_entry_activity", ["scripts/verify_entry_activity.py"]),
        ("holdout --check", ["scripts/holdout.py", "--check"]),
        ("eval_scorecard --check", ["scripts/eval_scorecard.py", "--check"]),
        ("build_triage_tree --check-sources", ["scripts/build_triage_tree.py", "--check-sources"]),
        ("build_triage_tree --check-coverage", ["scripts/build_triage_tree.py", "--check-coverage"]),
        ("check_generated_untouched --base origin/main", ["scripts/check_generated_untouched.py", "--base", "origin/main"]),
    ]
    for name, args in gates:
        rc, out, err = L.py(repo / args[0], *args[1:], cwd=repo)
        rec.add(name, rc, out, err)
    # index-freshness job: rebuild action runs first, then build_index --check
    rc, out, err = L.py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
    rec.add("index-freshness emulation: rebuild_generated --check", rc, out, err)
    rc, out, err = L.py(repo / "scripts/build_index.py", "--check", cwd=repo)
    rec.add("index-freshness emulation: build_index --check", rc, out, err)
    rc, out, err = git("checkout", "--", ".")
    rec.add("restore generated artifacts again", rc, out, err)

    # ---- 8. PR body gate ------------------------------------------------------
    body = ("## 背景与动机\n310P 启动即崩，知识库未覆盖。\n\n"
            "## 预分诊结论\nnew_pattern，同格视图无候选。\n\n"
            "## 证据\nsource_session 2026-10-28-conc-a01 已闭环。\n\n"
            "## 脱敏自查\n已脱敏。\n\n## 完整性\n- [x] 已跑 verify_case_draft\n")
    pr_body = L.LOG_DIR / "e2e-pr-body.md"
    pr_body.write_text(body, encoding="utf-8")
    import subprocess
    p = subprocess.run([L.PY, str(repo / "scripts/verify_pr_body.py")], cwd=str(repo),
                       input=body, capture_output=True, text=True, encoding="utf-8")
    rec.add("verify_pr_body (CI pr-template job)", p.returncode, p.stdout, p.stderr)

    # ---- 9. branch + PR + merge ----------------------------------------------
    rc, out, err = git("checkout", "-b", "kb/e2e-90001")
    rec.add("create branch kb/e2e-90001", rc, out, err)
    rc, out, err = git("add", "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-90001.yaml")
    rec.add("git add (source only)", rc, out, err)
    rc, out, err = git("status", "--porcelain")
    rec.add("staged tree", rc, out)
    rc, out, err = L.git(repo, "commit", "-m", "kb: add VLLM-ASC-90001 (synthetic)", env=L.GIT_ENV)
    rec.add("commit", rc, out, err)
    rc, out, err = git("push", "-q", "-u", "origin", "kb/e2e-90001")
    rec.add("push branch to origin", rc, out, err)

    integr = L.fresh_clone("int1")
    rc, out, err = L.git(integr, "merge", "--no-ff", "-m", "merge PR kb/e2e-90001",
                         "origin/kb/e2e-90001", env=L.GIT_ENV)
    rec.add("integration clone: merge PR", rc, out, err)

    # ---- 10. post-merge rebuild job (exact logic of rebuild-generated.yml) ----
    rc, out, err = L.py(integr / "scripts/rebuild_generated.py", "--check", cwd=integr)
    rec.add("post-merge job: rebuild_generated --check", rc, out, err)
    rc, dirty, _ = L.git(integr, "status", "--porcelain")
    rec.add("post-merge job: git status", rc, dirty)
    if dirty:
        L.git(integr, "add", "-A")
        rc, out, err = L.git(integr, "commit", "-m", "chore: rebuild generated views",
                             env=L.GIT_ENV)
        rec.add("post-merge job: commit generated views", rc, out, err)
        rc, out, err = L.git(integr, "push", "origin", "main")
        rec.add("post-merge job: push main", rc, out, err)

    # ---- 11. retrieval: is the new case visible to diagnosis? ----------------
    for rel in ("knowledge/_index/inference__vllm-ascend__interrupt.list",
                "knowledge/_index/inference__vllm-ascend.list",
                "knowledge/_index.yaml"):
        p = integr / rel
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        rec.add(f"retrieval: VLLM-ASC-90001 present in {rel}", 0 if "VLLM-ASC-90001" in text else 1,
                f"present={('VLLM-ASC-90001' in text)}")
    log = integr / "logs" / "qwen3-tts-310p.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("...\nRuntimeError: bfloat16 is not supported on this device\n", encoding="utf-8")
    rc, out, err = L.run(["python", "-c",
                          "import re,sys;pat=sys.argv[1];txt=open(sys.argv[2],encoding='utf-8').read();"
                          "print('primary regex match:',bool(re.search(pat,txt)))",
                          r"(bfloat16|bf16)", str(log)], cwd=integr)
    rec.add("quickly_check.primary keyword scan against a synthetic log "
            "(grep is not present on this Windows host; Python re is equivalent here)", rc, out, err)
    rc, out, err = L.run(["python", "-c",
                          "import re,sys;pat=sys.argv[1];txt=open(sys.argv[2],encoding='utf-8').read();"
                          "print('regex match:',bool(re.search(pat,txt)))",
                          r"(bfloat16|bf16).*(not supported|unsupported)", str(log)], cwd=integr)
    rec.add("expected regex matches the log", rc, out, err)

    # ---- 12. record git state ------------------------------------------------
    rc, out, err = L.git(integr, "log", "--oneline", "-6")
    rec.add("integration main log", rc, out)
    rc, out, err = L.git(integr, "show", "--stat", "--oneline", "HEAD~1")
    rec.add("merge commit stat", rc, out)

    path = rec.dump()
    rec.print_summary()
    print(f"\nrecord: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
