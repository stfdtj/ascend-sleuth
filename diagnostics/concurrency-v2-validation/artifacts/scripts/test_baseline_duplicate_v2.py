"""S2/S3 baseline: two clones, same problem, different IDs/categories, no V2 gate."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab_v2 as L

HERE = Path(__file__).parent


def main():
    L.reset_origin()
    a, b = L.fresh("base2a"), L.fresh("base2b")
    ca = L.case("VLLM-ASC-97001", title="310P bf16 startup failure", category="interrupt",
                root_cause="310P does not support bfloat16", fix="change dtype to float16")
    cb = L.case("VLLM-ASC-97002", title="310P zero output, dtype bf16", category="precision",
                symptoms=["audio output all zero", "npu-smi 310P", "dtype bfloat16"],
                root_cause="310P does not support bfloat16", fix="change dtype to float16")
    for repo, c, br in ((a, ca, "kb/a"), (b, cb, "kb/b")):
        L.git(repo, "checkout", "-q", "-B", br, "main")
        L.write_case(repo, f"knowledge/inference/vllm-ascend/{c['category']}/{c['id']}.yaml", c)
        L.commit(repo, br)
        L.git(repo, "push", "-q", "origin", br)
    integ = L.fresh("base2-int")
    rec = L.Rec("v2-baseline-duplicate")
    rc, out, err = L.git(integ, "merge", "--no-ff", "-m", "merge A", "origin/kb/a")
    rec.add("merge A", rc, out, err)
    rc, out, err = L.py(integ / "scripts/rebuild_generated.py", "--check", cwd=integ)
    rec.add("rebuild A", rc, out, err)
    L.commit(integ, "rebuild A")
    rc, out, err = L.git(integ, "merge", "--no-ff", "-m", "merge B", "origin/kb/b")
    rec.add("merge B", rc, out, err)
    rc, out, err = L.py(integ / "scripts/rebuild_generated.py", "--check", cwd=integ)
    rec.add("rebuild B", rc, out, err)
    L.commit(integ, "rebuild B")
    for name, args in (("case structure", ["scripts/verify_case_draft.py", "--all"]),
                       ("index", ["scripts/build_index.py", "--check"]),
                       ("references", ["scripts/verify_references.py", "--check"]),
                       ("entry", ["scripts/verify_entry_activity.py"])):
        rc, out, err = L.py(integ / args[0], *args[1:], cwd=integ)
        rec.add("gate " + name, rc, out, err)
    text = (integ / "knowledge/_index.yaml").read_text(encoding="utf-8")
    rec.add("both duplicates present", 0 if "VLLM-ASC-97001" in text and "VLLM-ASC-97002" in text else 1,
            f"97001={'VLLM-ASC-97001' in text} 97002={'VLLM-ASC-97002' in text}")
    rec.show()
    print(rec.dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
