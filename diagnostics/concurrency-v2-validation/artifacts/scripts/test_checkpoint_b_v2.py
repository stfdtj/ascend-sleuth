"""Checkpoint B V2: D1-D11 generation/display, tier counts, UUID-reader integration."""
from __future__ import annotations
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab_v2 as L
import yaml

HERE = Path(__file__).parent
PROTO = HERE.parent / "proto"
B = PROTO / "find_duplicates_v2.py"
INBOX = PROTO / "inbox_v2.py"
OLD = Path(r"D:\working\asv\b-lab")
PY = sys.executable


def run_b(root, *args):
    rc, out, err = L.run([PY, str(B), "--root", str(root), "--json", *args], cwd=HERE)
    return rc, (json.loads(out) if rc == 0 else None), err


def main():
    L.reset_origin()
    repo = L.fresh("b2")
    # seed the two synthetic library cases used by the labelled D1-D11 set
    for src in (OLD / "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-90001.yaml",
                OLD / "knowledge/inference/vllm-ascend/precision/VLLM-ASC-90002.yaml"):
        rel = src.relative_to(OLD / "knowledge")
        dest = repo / "knowledge" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    L.commit(repo, "seed synthetic library cases")
    # copy the already-labelled drafts into V2 UUID directories, then finish
    inbox = repo / "postmortems/inbox"
    created = []
    for d in sorted((OLD / "postmortems/inbox").iterdir()):
        if not d.is_dir() or d.name.endswith("099"):
            continue
        rc, out, err = L.run([PY, str(INBOX), "new", "--root", str(repo)], cwd=HERE)
        assert rc == 0, (out, err)
        target = Path(out.strip().splitlines()[-1])
        for name in ("case.yaml", "postmortem.md", "sources.yaml"):
            src = d / name
            if src.exists():
                shutil.copy2(src, target / name)
        src = yaml.safe_load((target / "sources.yaml").read_text(encoding="utf-8")) or {}
        src["draft_id"] = target.name
        case_doc = yaml.safe_load((target / "case.yaml").read_text(encoding="utf-8")) or {}
        cid = (case_doc.get("cases") or [{}])[0].get("id", "")
        if cid != "VLLM-ASC-91009":
            sid = "v2-session-" + cid.lower()
            src.setdefault("source", {})["session"] = sid
            src["sessions"] = [sid]
            src["verification"] = [{"kind": "feedback", "ref": sid}]
            case_text = (target / "case.yaml").read_text(encoding="utf-8")
            import re
            case_text = re.sub(r"^\s*source_session:.*$", f"    source_session: {sid}",
                               case_text, flags=re.M)
            (target / "case.yaml").write_text(case_text, encoding="utf-8")
        else:
            src.setdefault("source", {})["session"] = None
            src["sessions"] = []
            src["verification"] = [{"kind": "feedback", "ref": "2026-10-28-conc-a01"}]
        (target / "sources.yaml").write_text(yaml.safe_dump(src, allow_unicode=True, sort_keys=False),
                                             encoding="utf-8")
        rc, out, err = L.run([PY, str(INBOX), "finish", str(target)], cwd=HERE)
        created.append((target.name, rc))
    rec = L.Rec("v2-b")
    rec.add("V2 drafts created", 0 if all(rc == 0 for _, rc in created) else 1,
            json.dumps(created, ensure_ascii=False))
    rc, data, err = run_b(repo)
    rec.add("B JSON", rc, json.dumps(data.get("counts") if data else {}, ensure_ascii=False), err)
    pairs = data["pairs"] if data else []
    by = {}
    for p in pairs:
        by.setdefault(frozenset((p.get("draft_case"), p["case"])), p)
    targets = {
        "D1": ("VLLM-ASC-91001", "VLLM-ASC-90001"),
        "D2": ("VLLM-ASC-91002", "VLLM-ASC-90001"),
        "D3": ("VLLM-ASC-91003", "VLLM-ASC-90001"),
        "D4/D5": ("VLLM-ASC-91004", "VLLM-ASC-91005"),
        "D6": ("VLLM-ASC-91006", "VLLM-ASC-90001"),
        "D7": ("VLLM-ASC-91007", "VLLM-ASC-90001"),
        "D8": ("VLLM-ASC-91008", "VLLM-ASC-90001"),
        "D9": ("VLLM-ASC-91009", "VLLM-ASC-90001"),
        "D10": ("VLLM-ASC-91010", "VLLM-ASC-90001"),
        "D11": ("VLLM-ASC-91011", "VLLM-ASC-90001"),
    }
    results = {}
    for name, (a, b) in targets.items():
        p = by.get(frozenset((a, b)))
        results[name] = {"displayed": bool(p), "tier": p["tier"] if p else None,
                         "score": p["score"] if p else None}
    rec.add("D1-D11", 0, json.dumps(results, ensure_ascii=False, indent=2))
    # overflow behavior: cap high to 2 -> hidden_high > 0
    rc2, data2, err2 = run_b(repo, "--high-cap", "2")
    rec.add("high overflow", rc2, json.dumps(data2.get("counts") if data2 else {}, ensure_ascii=False), err2)
    # incomplete draft must not be consumed: add an unfinished UUID dir with a case
    rc, out, err = L.run([PY, str(INBOX), "new", "--root", str(repo)], cwd=HERE)
    stray = Path(out.strip().splitlines()[-1])
    (stray / "case.yaml").write_text((repo / "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-90001.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    rc3, data3, err3 = run_b(repo)
    rec.add("incomplete draft excluded", 0 if data3 and data3["counts"]["drafts"] == 11 else 1,
            json.dumps(data3["counts"] if data3 else {}, ensure_ascii=False), err3)
    rec.show()
    print(rec.dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
