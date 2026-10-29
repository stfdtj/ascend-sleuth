"""V2 provenance checker tests: integrity, recoverability, event uniqueness, lineage."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import lab_v2 as L

HERE = Path(__file__).parent
CHECK = HERE.parent / "proto" / "provenance_check.py"
PY = sys.executable


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(root):
    rc, out, err = L.run([PY, str(CHECK), "--root", str(root), "--json"], cwd=HERE)
    return rc, (json.loads(out) if out.strip() else None), err


def manifest(case_id, *, material_path=None, material_committed=True,
             dropped=None, evidence=None, fields=None, lineage=None):
    files = []
    if material_path:
        files.append({"path": material_path,
                      "sha256": sha(root / material_path) if (root / material_path).is_file() else "0" * 64,
                      "committed": material_committed})
    return {
        "case_id": case_id, "decided_at": "2026-10-29", "owner": "v2-test",
        "decision": "merged", "lineage": lineage or {},
        "materials": [{
            "draft_id": "draft-1", "deployment_id": "dep-1", "session": "s1",
            "files": files,
            "fields": fields or {"fix": ["draft-1"], "symptoms": ["draft-1"]},
            "dropped": dropped or [],
        }],
        "evidence": evidence or [{"event_id": "feedback:s1:1", "kind": "feedback",
                                  "independent": True, "note": ""}],
        "counts": {"usage": "historical", "incident_key": "incident-1"},
    }


def write(root, doc, name=None):
    p = root / "postmortems/provenance" / (name or f"{doc['case_id']}.yaml")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return p


def main():
    global root
    L.reset_origin()
    root = L.fresh("p2")
    L.write_case(root, "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-93001.yaml", L.case("VLLM-ASC-93001"))
    L.write_case(root, "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-93002.yaml", L.case("VLLM-ASC-93002"))
    mat = root / "postmortems/materials/VLLM-ASC-93001/draft-1/case.yaml"
    mat.parent.mkdir(parents=True, exist_ok=True)
    mat.write_text(L.F.case_text(L.case("VLLM-ASC-93001")), encoding="utf-8")
    rec = L.Rec("v2-provenance")
    doc = manifest("VLLM-ASC-93001", material_path="postmortems/materials/VLLM-ASC-93001/draft-1/case.yaml")
    p = write(root, doc)
    rc, data, err = run(root)
    rec.add("valid committed manifest", rc, json.dumps(data, ensure_ascii=False), err)
    mat.write_text(mat.read_text(encoding="utf-8") + "\n# edit\n", encoding="utf-8")
    rc, data, err = run(root)
    rec.add("altered committed material", rc, json.dumps(data, ensure_ascii=False), err)
    mat.write_text(L.F.case_text(L.case("VLLM-ASC-93001")), encoding="utf-8")
    # local-only absent material
    local = manifest("VLLM-ASC-93001", material_path="postmortems/materials/nonexistent.yaml",
                     material_committed=False)
    write(root, local)
    rc, data, err = run(root)
    rec.add("local-only missing material", rc, json.dumps(data, ensure_ascii=False), err)
    # dropped verified vs declared
    d1 = manifest("VLLM-ASC-93001", material_path="postmortems/materials/VLLM-ASC-93001/draft-1/case.yaml",
                  dropped=[{"field": "diagnosis", "reason": "dup", "destination": "missing.yaml",
                            "recoverability": "verified"}])
    write(root, d1)
    rc, data, err = run(root)
    rec.add("dropped verified missing", rc, json.dumps(data, ensure_ascii=False), err)
    d1["materials"][0]["dropped"][0] = {"field": "diagnosis", "reason": "dup", "destination": None,
                                        "recoverability": "declared"}
    write(root, d1)
    rc, data, err = run(root)
    rec.add("dropped declared", rc, json.dumps(data, ensure_ascii=False), err)
    # multi-source field without merged
    bad = manifest("VLLM-ASC-93001", material_path="postmortems/materials/VLLM-ASC-93001/draft-1/case.yaml",
                   fields={"symptoms": ["draft-1", "draft-2"]})
    write(root, bad)
    rc, data, err = run(root)
    rec.add("multi-source without merged", rc, json.dumps(data, ensure_ascii=False), err)
    # event independence duplicate across two cases
    write(root, manifest("VLLM-ASC-93001", material_path="postmortems/materials/VLLM-ASC-93001/draft-1/case.yaml"))
    m2 = manifest("VLLM-ASC-93002")
    m2["evidence"][0]["independent"] = False
    write(root, m2)
    rc, data, err = run(root)
    rec.add("same event independently claimed", rc, json.dumps(data, ensure_ascii=False), err)
    # lineage target missing / valid redirect
    write(root, manifest("VLLM-ASC-93001", material_path="postmortems/materials/VLLM-ASC-93001/draft-1/case.yaml",
                         lineage={"merged_into": "VLLM-ASC-93002"}))
    rc, data, err = run(root)
    rec.add("valid merged_into", rc, json.dumps(data, ensure_ascii=False), err)
    m2["evidence"][0]["independent"] = True
    write(root, m2)
    rc, data, err = run(root)
    rec.add("same event independently claimed", rc, json.dumps(data, ensure_ascii=False), err)
    m2["evidence"][0]["independent"] = False
    write(root, m2)
    (root / "postmortems/redirects.yaml").write_text(yaml.safe_dump(
        [{"old_id": "VLLM-ASC-99999", "new_id": "VLLM-ASC-93001", "reason": "rename"}],
        allow_unicode=True, sort_keys=False), encoding="utf-8")
    rc, data, err = run(root)
    rec.add("redirect old->new", rc, json.dumps(data, ensure_ascii=False), err)
    rec.show()
    print(rec.dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
