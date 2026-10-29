"""E11/E12 re-test on the current commit, plus prototype fixes in a disposable clone."""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab_v2 as L

HERE = Path(__file__).parent
PY = sys.executable


def patch(path: Path, old: str, new: str):
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"patch target missing in {path}: {old[:60]}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main():
    L.reset_origin()
    repo = L.fresh("d2")
    rec = L.Rec("v2-defects")
    # E11: numeric-looking SHA in source rows
    rows = (repo / "metrics/entry-activity.d/2026-W44.yaml")
    rows.parent.mkdir(parents=True, exist_ok=True)
    rows.write_text("""- {run: 2026-10-29-1200, deployment: d2, checkout: 8577483, kb_rev: 8577483, sessions: 1, kind: case, id: VLLM-ASC-93001, selected: 0, loaded: 0, resolved: 1, misdiagnosed: 0, self_resolved: 0, excluded: 0}
- {run: 2026-10-29-1300, deployment: d2, checkout: 55c20dc, kb_rev: 55c20dc, sessions: 1, kind: case, id: VLLM-ASC-93002, selected: 0, loaded: 0, resolved: 1, misdiagnosed: 0, self_resolved: 0, excluded: 0}
""", encoding="utf-8")
    rc, out, err = L.py(repo / "scripts/build_entry_activity.py", cwd=repo)
    rec.add("E11 current build_entry_activity", rc, out, err)
    patch(repo / "scripts/entry_activity.py",
          '"checkouts": sorted(checkouts),', '"checkouts": sorted(str(x) for x in checkouts),')
    rc, out, err = L.py(repo / "scripts/build_entry_activity.py", cwd=repo)
    rec.add("E11 after coerce-to-str fix", rc, out, err)

    # E12: snapshot output vs live whitelist/strength registry
    L.F.write_trace(repo, "2026-10-29-snap", summary="E12 snapshot trace",
                    user_msg="310P bf16 startup failure", cand="case candidate",
                    active_case="VLLM-ASC-93001")
    rc, out, err = L.py(repo / "scripts/metrics_snapshot.py", "--emit-yaml", cwd=repo)
    rec.add("E12 snapshot emit", rc, out[:300], err)
    import yaml
    doc = yaml.safe_load(out) if rc == 0 else {}
    period = doc.get("period")
    if period:
        dest = repo / "metrics/timeline.d" / f"{period}.yaml"
        dest.write_text(out, encoding="utf-8")
        L.py(repo / "scripts/build_timeline.py", cwd=repo)
        rc, out2, err2 = L.py(repo / "scripts/verify_metrics.py", "--check", cwd=repo)
        rec.add("E12 verify_metrics current", rc, out2, err2)
        patch(repo / "scripts/verify_metrics.py",
              '"trace_record_violations_total",', '"trace_record_violations_total",\n    "external_record_violations_total",')
        patch(repo / "metrics/gates.yaml", "  reference_total: 确定性",
              "  reference_total: 确定性\n"
              "  external_record_violations_total: 确定性\n"
              "  considered_candidates_events: 确定性\n"
              "  parallel_group_events: 确定性\n"
              "  stop_reason_unrecorded: 确定性\n"
              "  trace_record_violations_total: 确定性\n"
              "  triage_miss_classes: 确定性")
        rc, out3, err3 = L.py(repo / "scripts/verify_metrics.py", "--check", cwd=repo)
        rec.add("E12 after whitelist/strength fix", rc, out3, err3)
    rec.show()
    print(rec.dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
