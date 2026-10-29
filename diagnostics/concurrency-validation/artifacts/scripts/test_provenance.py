"""Provenance + ID migration + observability feasibility (plan §5-§6).

Tests the proposed provenance sidecar against the questions it is supposed to answer:
  1. where did the final case come from (material level)?
  2. which draft contributed each *field* (sub-field attribution)?
  3. what was discarded, and where is it recoverable?
  4. is the evidence independent, or is the same event counted twice?
  5. is a merged/renamed/archived case still traceable?
  6. do the monthly metrics have a data source at all?

The provenance file is written by hand exactly as the plan's example; no product code
implements it (there is no verify_provenance.py, and no CI job reads it).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fixtures as F
import lab_common as L

import yaml

PY = sys.executable
OLD = "VLLM-ASC-90001"
NEW = "VLLM-ASC-90001R"
OLD_PATH = f"knowledge/inference/vllm-ascend/interrupt/{OLD}.yaml"
NEW_PATH = f"knowledge/inference/vllm-ascend/interrupt/{NEW}.yaml"


def feedback_trace(repo: Path, sid: str, case: str, outcome: str = "resolved"):
    p = repo / "traces" / f"{sid}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"""session_id: {sid}
status: resolved
active_case: {case}
trace:
  - ts: "2026-10-28T09:00:00+08:00"
    role: user
    content: "现场回报：fix 生效"
  - ts: "2026-10-28T12:00:00+08:00"
    action: feedback
    case: {case}
    outcome: {outcome}
""", encoding="utf-8")


def provenance_text(case_id: str, *, material_ref: str, dropped_where: str) -> str:
    return yaml.safe_dump({
        "case_id": case_id,
        "decided_at": "2026-10-28",
        "owner": "owner-a",
        "decision": "merged",
        "materials": [
            {"draft_id": "2026-10-28-diag-001", "deployment": "clone-a",
             "fields_kept": ["symptoms", "fix", "compat"],
             "fields_dropped": {"diagnosis": "与已有步骤重复"}},
            {"draft_id": "2026-10-28-diag-002", "deployment": "clone-b",
             "fields_kept": ["symptoms", "verification"],
             "fields_dropped": {}},
        ],
        "verification": [
            {"event": "feedback:2026-10-28-conc-a01", "independent": False,
             "note": "与 material 2 同一次现场回报"},
        ],
        # deliberately points at a path that does not exist (recovery test)
        "dropped_destinations": [
            {"draft_id": "2026-10-28-diag-002", "where": "archived", "ref": dropped_where},
        ],
        "recover_from": material_ref,
    }, allow_unicode=True, sort_keys=False)


def main() -> int:
    rec = L.Recorder("provenance")
    L.seed_integrated_main()
    repo = L.fresh_clone("prov")
    L.git(repo, "config", "user.name", "prov")
    L.git(repo, "config", "user.email", "prov@lab.local")

    # ---- 1. write a provenance sidecar for a merge of 90001 + 90002 -------------
    prov_dir = repo / "postmortems" / "2026-Q4"
    prov_dir.mkdir(parents=True, exist_ok=True)
    prov = prov_dir / f"{OLD}.provenance.yaml"
    prov.write_text(provenance_text(OLD, material_ref="postmortems/2026-Q4/some-draft",
                                    dropped_where="postmortems/2026-Q4/never-existed"), encoding="utf-8")
    rc, out, err = L.py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
    rec.add("provenance sidecar added: rebuild_generated --check", rc, out, err)
    for name, args in (("verify_references --check", ["scripts/verify_references.py", "--check"]),
                       ("verify_entry_activity", ["scripts/verify_entry_activity.py"]),
                       ("verify_case_draft --all", ["scripts/verify_case_draft.py", "--all"])):
        rc, out, err = L.py(repo / args[0], *args[1:], cwd=repo)
        rec.add(f"with provenance sidecar: {name}", rc, out, err)
    grep = subprocess.run(["git", "grep", "-n", "-E", "provenance\\.yaml|verify_provenance",
                           "--", "scripts", ".github/workflows", "docs/guide"],
                          cwd=repo, capture_output=True, text=True, encoding="utf-8")
    rec.add("does any script / CI read the proposed provenance sidecar?", grep.returncode,
            grep.stdout, grep.stderr)

    # ---- 2. field-level attribution ---------------------------------------------
    merged = (repo / OLD_PATH).read_text(encoding="utf-8")
    merged = merged.replace("310P 硬件不支持 bfloat16；qwen3_tts.yaml 配的是 bfloat16，启动时算子选择失败",
                            "310P 硬件不支持 bfloat16；qwen3_tts.yaml 配的是 bfloat16，"
                            "启动时算子选择失败；输出全 0 是同一次现场的另一面")
    merged = merged.replace("- \"npu-smi info 显示芯片为 310P\"",
                            "- \"npu-smi info 显示芯片为 310P\"\n"
                            "      - \"推理返回音频张量全为 0（来自 draft-002）\"")
    (repo / OLD_PATH).write_text(merged, encoding="utf-8")
    rc, out, err = L.py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
    rec.add("after the merged edit: rebuild_generated --check", rc, out, err)
    prov_loaded = yaml.safe_load(prov.read_text(encoding="utf-8"))
    kept = {}
    for m in prov_loaded["materials"]:
        for f in m["fields_kept"]:
            kept.setdefault(f, []).append(m["draft_id"])
    rec.add("field → contributing drafts from provenance", 0,
            json.dumps(kept, ensure_ascii=False),
            ambiguous_fields=[f for f, ms in kept.items() if len(ms) > 1])

    # ---- 3. rename the case: does provenance follow? ----------------------------
    L.git(repo, "mv", OLD_PATH, NEW_PATH)
    p = repo / NEW_PATH
    p.write_text(p.read_text(encoding="utf-8").replace(OLD, NEW), encoding="utf-8")
    rc, out, err = L.py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
    rec.add("rename case, rebuild", rc, out, err)
    rec.add("provenance filename after the rename", 0,
            json.dumps({"provenance_file": prov.name, "case_file": Path(NEW_PATH).name,
                        "still_references_old_id": OLD in prov.read_text(encoding="utf-8"),
                        "orphan": not (repo / prov_dir / f"{NEW}.provenance.yaml").exists()}))
    for name, args in (("verify_references --check", ["scripts/verify_references.py", "--check"]),
                       ("verify_case_draft --all", ["scripts/verify_case_draft.py", "--all"])):
        rc, out, err = L.py(repo / args[0], *args[1:], cwd=repo)
        rec.add(f"after rename: {name}", rc, out, err)

    # ---- 4. counts after merging: delete vs archive -----------------------------
    feedback_trace(repo, "2026-10-28-fb-1", NEW)
    feedback_trace(repo, "2026-10-28-fb-2", "VLLM-ASC-90002")
    rc, out, err = L.py(repo / "scripts/settle_trace_feedback.py", "--apply", cwd=repo)
    rec.add("settle two usage rows (NEW and 90002)", rc, out, err)
    rc, out, err = L.py(repo / "scripts/build_entry_activity.py", cwd=repo)
    rec.add("rebuild the generated entry-activity artifact", rc, out, err)
    rows = []
    for pth in sorted((repo / "metrics/entry-activity.d").glob("*.yaml")):
        doc = yaml.safe_load(pth.read_text(encoding="utf-8")) or []
        rows += [r for r in doc if isinstance(r, dict) and str(r.get("id", "")).startswith("VLLM-ASC-9")]
    rec.add("usage rows before merge", 0, json.dumps([{k: r.get(k) for k in ("id", "resolved")}
                                                      for r in rows], ensure_ascii=False))
    # archive the duplicate instead of deleting it
    arch = repo / "knowledge/_archive/precision/VLLM-ASC-90002.yaml"
    arch.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(repo / "knowledge/inference/vllm-ascend/precision/VLLM-ASC-90002.yaml"), arch)
    rc, out, err = L.py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
    rec.add("merge 90002 into 90001 by archiving the duplicate, rebuild", rc, out, err)
    if rc != 0:
        rc, out, err = L.py(repo / "scripts/build_index.py", cwd=repo)
        rec.add("recover: build_index.py", rc, out, err)
        rc, out, err = L.py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
        rec.add("recover: rebuild_generated --check", rc, out, err)
    rc, out, err = L.py(repo / "scripts/verify_entry_activity.py", cwd=repo)
    rec.add("verify_entry_activity after archiving the duplicate", rc, out, err)
    rc, out, err = L.py(repo / "scripts/score_entries.py", cwd=repo)
    rec.add("score_entries after archive (counts do not transfer)", rc, out, err)
    act = {}
    for pth in sorted((repo / "metrics/entry-activity").glob("*.yaml")):
        doc = yaml.safe_load(pth.read_text(encoding="utf-8")) or {}
        act.update(doc.get("cases") or {})
    rec.add("generated entry-activity keys after archive", 0,
            json.dumps({k: v for k, v in act.items() if "VLLM-ASC-9" in k},
                       ensure_ascii=False)[:800])

    # ---- 5. same evidence counted twice -----------------------------------------
    other = repo / "knowledge/inference/vllm-ascend/precision/VLLM-ASC-90005.yaml"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text(F.case_text(dict(F.CASE_B, id="VLLM-ASC-90005",
                                      session="2026-10-28-fb-1")), encoding="utf-8")
    feedback_trace(repo, "2026-10-28-fb-3", "VLLM-ASC-90005")
    rc, out, err = L.py(repo / "scripts/settle_trace_feedback.py", "--apply", cwd=repo)
    rec.add("two cases claiming the same incident, each with its own feedback event", rc, out, err)
    rows2 = []
    for pth in sorted((repo / "metrics/entry-activity.d").glob("*.yaml")):
        doc = yaml.safe_load(pth.read_text(encoding="utf-8")) or []
        rows2 += [r for r in doc if isinstance(r, dict) and str(r.get("id", "")).startswith("VLLM-ASC-9")]
    rec.add("usage rows after the second case", 0, json.dumps(
        [{"id": r.get("id"), "resolved": r.get("resolved"), "self_resolved": r.get("self_resolved")}
         for r in rows2], ensure_ascii=False))
    rec.add("provenance independence is a human assertion, not a check", 0,
            json.dumps({"independent_field": prov_loaded["verification"][0]["independent"],
                        "checked_by": "nothing"}))

    # ---- 6. observability data availability ------------------------------------
    lib = []
    for pth in (repo / "knowledge").rglob("*.yaml"):
        if "_index" in pth.parts:
            continue
        try:
            doc = yaml.safe_load(pth.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        lib += [c for c in doc.get("cases") or [] if isinstance(c, dict)]
    have_session = sum(1 for c in lib if c.get("source_session"))
    metrics = {
        "duplicate_candidate_precision": {
            "needs": ["candidate list", "reviewer decision per pair"],
            "have": ["candidate list (prototype) / nowhere in the repo",
                     "no decision field in PR templates or metrics"],
            "computable": False},
        "duplicate_candidate_recall": {
            "needs": ["labelled duplicate/non-duplicate set"],
            "have": ["eval/golden is retrieval regression (28 fixtures), not duplicate labels"],
            "computable": False},
        "merge_rework_rate": {
            "needs": ["record of each merge and any later split/rewrite"],
            "have": ["git history only; no machine-readable merge event"],
            "computable": False},
        "post_merge_misdiagnosis": {
            "needs": ["entry-activity counts mapped across the merge"],
            "have": [f"counts per case id; {have_session}/{len(lib)} cases carry source_session; "
                     "merging does not transfer counts"],
            "computable": False},
        "duplicate_verification_evidence_rate": {
            "needs": ["per-case verification-event ids", "case->event mapping"],
            "have": [f"{have_session}/{len(lib)} cases carry source_session; "
                     "validation_record has counts, not event ids"],
            "computable": False},
        "reviewer_decision_auditable": {
            "needs": ["structured decision record"],
            "have": ["PR body free text; verify_pr_body checks headings only"],
            "computable": False},
    }
    rec.add("monthly observability: data availability", 0,
            json.dumps(metrics, ensure_ascii=False, indent=2))
    rec.print_summary()
    print(f"\nrecord: {rec.dump()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
