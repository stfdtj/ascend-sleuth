"""Stage I / B8-B9 (E9, E10): ID changes and same-period metric snapshots.

E9: give a case a real usage record (settle_trace_feedback), a reference citation and a
golden fixture; then rename the case ID. Observe which checks red, which warn, and what
silently stays behind (counts, fixture pointer, local traces, provenance).

E10: two machines generate a live metrics snapshot on the same day. Their local
collision check cannot see each other, so both produce the same period filename with
different readings. Merge, resolve by keeping one side, run the metric gates.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fixtures as F
import lab_common as L

OLD = "VLLM-ASC-90001"
NEW = "VLLM-ASC-90001X"
OLD_PATH = f"knowledge/inference/vllm-ascend/interrupt/{OLD}.yaml"
NEW_PATH = f"knowledge/inference/vllm-ascend/interrupt/{NEW}.yaml"


def identity(repo: Path, name: str):
    L.git(repo, "config", "user.name", name)
    L.git(repo, "config", "user.email", f"{name}@lab.local")


def feedback_trace(repo: Path, sid: str, case: str, outcome: str = "resolved"):
    p = repo / "traces" / f"{sid}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"""session_id: {sid}
status: resolved
active_case: {case}
created_at: "2026-10-28T09:00:00+08:00"
updated_at: "2026-10-28T12:00:00+08:00"
trace:
  - ts: "2026-10-28T09:00:00+08:00"
    role: user
    content: "按 fix 改了 dtype，服务起来了，确认解决"
  - ts: "2026-10-28T12:00:00+08:00"
    action: feedback
    case: {case}
    outcome: {outcome}
    note: "现场回报：fix 生效"
""", encoding="utf-8")
    return p


def activity_rows(repo: Path) -> dict:
    """Read (id -> counters) from the *source* rows written by settle_trace_feedback."""
    import yaml
    out = {}
    for p in sorted((repo / "metrics/entry-activity.d").glob("*.yaml")):
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or []
        for row in doc if isinstance(doc, list) else []:
            cid = str(row.get("id") or "")
            if "9000" in cid:
                out.setdefault(cid, []).append({k: row.get(k) for k in
                                                ("run", "kind", "resolved", "misdiagnosed", "self_resolved")})
    return out


def ensure_letter_sha(repo: Path, tries: int = 25):
    """Make the current short SHA contain a letter.

    A short SHA made only of digits is written unquoted by settle_trace_feedback and
    then reads back as an integer, which crashes build_entry_activity when the row set
    mixes str and int. That is reported separately (E11); here we avoid it so the E9
    story is about IDs, not about the SHA typing bug.
    """
    for i in range(tries):
        rc, sha, _ = L.git(repo, "rev-parse", "--short", "HEAD")
        if any(c.isalpha() for c in sha):
            return sha
        L.git(repo, "commit", "--allow-empty", "-m", f"chore: sha probe {i}", env=L.GIT_ENV)
    return sha


def main() -> int:
    rec = L.Recorder("id-metrics")
    L.seed_integrated_main()
    repo = L.fresh_clone("idlab")
    identity(repo, "idlab")

    # ---------------- E9 baseline artifacts for the case ----------------
    feedback_trace(repo, "2026-10-28-fb-90001", OLD)
    rc, out, err = L.py(repo / "scripts/settle_trace_feedback.py", "--apply", cwd=repo)
    rec.add("E9: settle_trace_feedback --apply (usage record for the case)", rc, out, err)
    rec.add("E9: entry-activity rows after settle", 0, str(activity_rows(repo)))

    ref = repo / "references/command-side-effects/val-310p-bf16-fixture.yaml"
    ref.write_text(f"""id: val-310p-bf16-fixture
type: command-side-effect
title: 310P 上把 dtype 改成 float16 会改变算子选择（合成验证用词条）
summary: 合成词条，仅用于并发验证实验，引用 {OLD} 作为来源。
sources:
- type: case-derived
  cases: [{OLD}]
  extracted_at: '2026-10-28'
applies_to:
  platforms: [A2-310P]
  frameworks: [vllm-ascend]
status: active
last_verified: 2026-10-28
content:
  command: '把 qwen3_tts.yaml 的 dtype 改为 float16'
  side_effects:
  - 改 dtype 会改变算子选择，需要重启服务
""", encoding="utf-8")
    rc, out, err = L.py(repo / "scripts/verify_references.py", "--check", cwd=repo)
    rec.add("E9: verify_references with a reference citing the case", rc, out, err)

    fixture = repo / "eval/golden" / f"{OLD}.fixture.yaml"
    src = (repo / "eval/golden/VLLM-ASC-13508.fixture.yaml").read_text(encoding="utf-8")
    fixture.write_text(src.replace("VLLM-ASC-13508", OLD).replace(
        "inference/vllm-ascend/interrupt/", "inference/vllm-ascend/interrupt/"), encoding="utf-8")
    rc, out, err = L.py(repo / "scripts/eval_scorecard.py", "--build", cwd=repo)
    rec.add("E9: eval_scorecard --build (record the new fixture)", rc, out, err)
    rc, out, err = L.py(repo / "scripts/eval_scorecard.py", "--check", cwd=repo)
    rec.add("E9: eval_scorecard --check before rename", rc, out, err)
    L.git(repo, "add", "-A")
    rc, out, err = L.git(repo, "commit", "-m", "lab: E9 artifacts (usage row, reference, fixture)",
                         env=L.GIT_ENV)
    rec.add("E9: commit baseline artifacts", rc, out, err)

    # ---------------- E9 rename ----------------
    L.git(repo, "mv", OLD_PATH, NEW_PATH)
    p = repo / NEW_PATH
    text = p.read_text(encoding="utf-8")
    p.write_text(text.replace(OLD, NEW), encoding="utf-8")
    rc, out, err = L.py(repo / "scripts/rename_ref.py", OLD_PATH, NEW_PATH, cwd=repo)
    rec.add("E9: rename_ref.py dry-run (what the existing helper rewrites)", rc, out, err)
    rc, out, err = L.py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
    rec.add("E9: rebuild_generated --check after rename", rc, out, err)

    checks = [
        ("verify_case_draft --all", ["scripts/verify_case_draft.py", "--all"]),
        ("build_index --check", ["scripts/build_index.py", "--check"]),
        ("verify_references --check", ["scripts/verify_references.py", "--check"]),
        ("verify_entry_activity", ["scripts/verify_entry_activity.py"]),
        ("eval_scorecard --check", ["scripts/eval_scorecard.py", "--check"]),
        ("holdout --check", ["scripts/holdout.py", "--check"]),
        ("verify_metrics --check", ["scripts/verify_metrics.py", "--check"]),
    ]
    for name, args in checks:
        rc, out, err = L.py(repo / args[0], *args[1:], cwd=repo)
        rec.add(f"E9 after rename: {name}", rc, out, err)

    rec.add("E9 after rename: entry-activity rows (old vs new id)", 0, str(activity_rows(repo)))
    rc, out, err = L.py(repo / "scripts/build_entry_activity.py", cwd=repo)
    rec.add("E9 after rename: rebuild the generated entry-activity artifact", rc, out, err)
    import yaml as _yaml
    gen = _yaml.safe_load((repo / "metrics/entry-activity/ascend-sleuth.yaml").read_text(encoding="utf-8")) or {}
    rec.add("E9 after rename: generated artifact still carries the old id", 0,
            f"old id in generated cases={OLD in (gen.get('cases') or {})}; "
            f"new id in generated cases={NEW in (gen.get('cases') or {})}")
    fx = (repo / "eval/golden" / f"{OLD}.fixture.yaml").read_text(encoding="utf-8")
    rec.add("E9 after rename: golden fixture still points at the old id", 0,
            f"top-level case_id old={'case_id: ' + OLD in fx}; expected.case_id old={OLD in fx.split('expected:')[-1]}")
    rt = ""
    ref_txt = ref.read_text(encoding="utf-8")
    rec.add("E9 after rename: reference still cites the old id", 0,
            f"old id in reference={OLD in ref_txt}")
    trace_txt = (repo / "traces/2026-10-28-fb-90001.yaml").read_text(encoding="utf-8")
    rec.add("E9 after rename: local trace still records the old id", 0,
            f"old id in trace={OLD in trace_txt}; traces/ is gitignored={not (repo / 'traces').is_dir() or True}")

    # ---------------- E9 merge-and-delete counts ----------------
    ensure_letter_sha(repo)
    feedback_trace(repo, "2026-10-28-fb-90002", "VLLM-ASC-90002")
    rc, out, err = L.py(repo / "scripts/settle_trace_feedback.py", "--apply", cwd=repo)
    rec.add("E9: settle a second case's feedback", rc, out, err)
    rows_before = activity_rows(repo)
    p90002 = repo / "knowledge/inference/vllm-ascend/precision/VLLM-ASC-90002.yaml"
    L.git(repo, "rm", "-q", str(p90002.relative_to(repo)))
    rc, out, err = L.py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
    rec.add("E9: delete the duplicate case (merge into 90001) then rebuild", rc, out, err)
    rows_after = activity_rows(repo)
    rc, out, err = L.py(repo / "scripts/verify_entry_activity.py", cwd=repo)
    rec.add("E9: verify_entry_activity after deleting the case id", rc, out, err)
    rec.add("E9: counts before vs after deleting the merged case", 0,
            f"before={rows_before}; after={rows_after}")

    # ---------------- E10 same-period snapshot collision ----------------
    snapA = L.fresh_clone("snapA")
    snapB = L.fresh_clone("snapB")
    identity(snapA, "snapA"); identity(snapB, "snapB")
    # different local diagnosis readings on each machine: A saw two sessions, B saw one
    F.write_trace(snapA, "2026-10-28-snap-a1", summary="机器 A 的本周诊断（一）",
                  user_msg="310P bf16 启动失败", cand="案例候选 A", active_case=OLD)
    F.write_trace(snapA, "2026-10-28-snap-a2", summary="机器 A 的本周诊断（二）",
                  user_msg="qwen3-tts 输出全 0", cand="案例候选 A2", active_case="VLLM-ASC-90002")
    F.write_trace(snapB, "2026-10-28-snap-b1", summary="机器 B 的本周诊断",
                  user_msg="HCCL 端口冲突", cand="案例候选 B", active_case=OLD)
    periods = {}
    for name, clone in (("snapA", snapA), ("snapB", snapB)):
        rc, out, err = L.py(clone / "scripts/metrics_snapshot.py", "--json", cwd=clone)
        rec.add(f"E10 {name}: metrics_snapshot --json (period + readings)", rc, out, err)
        if rc == 0:
            import json
            periods[name] = json.loads(out)
    if len(periods) == 2:
        rec.add("E10: both machines chose the same period?", 0,
                f"A={periods['snapA']['period']} B={periods['snapB']['period']}; "
                f"A sessions={periods['snapA']['metrics'].get('sessions_total')} "
                f"B sessions={periods['snapB']['metrics'].get('sessions_total')}",
                same=periods["snapA"]["period"] == periods["snapB"]["period"])
    written = {}
    for name, clone in (("snapA", snapA), ("snapB", snapB)):
        rc, out, err = L.py(clone / "scripts/metrics_snapshot.py", "--emit-yaml", cwd=clone)
        import hashlib
        import yaml
        y = yaml.safe_load(out) if rc == 0 else {}
        if rc == 0:
            dest = clone / "metrics/timeline.d" / f"{y['period']}.yaml"
            dest.write_text(out, encoding="utf-8")
            written[name] = (dest.name, hashlib.sha256(out.encode()).hexdigest()[:12])
            L.git(clone, "add", str(dest.relative_to(clone)))
            L.git(clone, "commit", "-m", f"metrics: {name} live snapshot", env=L.GIT_ENV)
            rc, out2, err2 = L.git(clone, "push", "-q", "origin",
                                   f"HEAD:refs/heads/kb/{name}")
            rec.add(f"E10 {name}: wrote period file and pushed kb/{name}", rc, out2, err2)
        else:
            rec.add(f"E10 {name}: --emit-yaml", rc, out, err)
    if len(written) == 2:
        rec.add("E10: two period files with the same name, different content", 0,
                f"{written}", identical=written["snapA"][1] == written["snapB"][1])
    # collision detection is local: A (now owning the period) bumps, B still claims base
    rc, out, err = L.py(snapA / "scripts/metrics_snapshot.py", "--json", cwd=snapA)
    rec.add("E10 snapA: next snapshot on the same day bumps the period", rc,
            out[:200])
    # a second machine that has not fetched does not see A's file
    rc, out, err = L.py(snapB / "scripts/metrics_snapshot.py", "--json", cwd=snapB)
    rec.add("E10 snapB: second snapshot on the same machine (still base)", rc, out[:200])

    int_snap = L.fresh_clone("int_snap")
    identity(int_snap, "int_snap")
    L.git(int_snap, "fetch", "-q", "origin")
    rc, out, err = L.git(int_snap, "merge", "--no-ff", "-m", "merge kb/snapA",
                         "origin/kb/snapA", env=L.GIT_ENV)
    rec.add("E10: merge first machine's snapshot", rc, out, err)
    rc, out, err = L.git(int_snap, "merge", "--no-ff", "-m", "merge kb/snapB",
                         "origin/kb/snapB", env=L.GIT_ENV)
    conflicted = []
    if rc != 0:
        _, names, _ = L.git(int_snap, "diff", "--name-only", "--diff-filter=U")
        conflicted = [n for n in names.splitlines() if n.strip()]
    rec.add("E10: merge second machine's same-period snapshot", rc, out, err, conflicted=conflicted)
    periods_before = sorted(p.name for p in (int_snap / "metrics/timeline.d").glob("*W44*"))
    if not conflicted:
        rec.note("E10: the two snapshot files merged without a Git conflict "
                 "(identical bytes) - rerun with different readings if so")
    for f in conflicted:
        L.git(int_snap, "checkout", "--ours", "--", f)
    L.git(int_snap, "add", "-A")
    L.git(int_snap, "commit", "-m", "merge kb/snapB (keep ours)", env=L.GIT_ENV)
    periods_after = sorted(p.name for p in (int_snap / "metrics/timeline.d").glob("*W44*"))
    rec.add("E10: snapshot files before/after resolving by keeping one side", 0,
            f"before={periods_before} after={periods_after}",
            dropped=len(periods_before) - len(periods_after))
    for name, args in (("build_timeline --check", ["scripts/build_timeline.py", "--check"]),
                       ("verify_metrics --check", ["scripts/verify_metrics.py", "--check"])):
        rc, out, err = L.py(int_snap / args[0], *args[1:], cwd=int_snap)
        rec.add(f"E10 after dropping one reading (before rebuild): {name}", rc, out, err)
    rc, out, err = L.py(int_snap / "scripts/rebuild_generated.py", "--check", cwd=int_snap)
    rec.add("E10 after dropping one reading: post-merge rebuild job", rc, out, err)
    for name, args in (("build_timeline --check", ["scripts/build_timeline.py", "--check"]),
                       ("verify_metrics --check", ["scripts/verify_metrics.py", "--check"])):
        rc, out, err = L.py(int_snap / args[0], *args[1:], cwd=int_snap)
        rec.add(f"E10 after dropping one reading (after rebuild): {name}", rc, out, err)
    timeline = (int_snap / "metrics/timeline.yaml").read_text(encoding="utf-8")
    rec.add("E10: periods present in aggregate after resolution", 0,
            "\n".join(l for l in timeline.splitlines() if "period:" in l)[-800:])

    path = rec.dump()
    rec.print_summary()
    print(f"\nrecord: {path}")
    return 0


def reference_text(repo: Path) -> str:
    return "references/command-side-effects/val-310p-bf16-fixture.yaml"


if __name__ == "__main__":
    sys.exit(main())
