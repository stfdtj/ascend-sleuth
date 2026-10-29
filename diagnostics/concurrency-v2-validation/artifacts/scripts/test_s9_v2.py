"""S9: stale generated index detection (heartbeat prototype)."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab_v2 as L

HERE = Path(__file__).parent
PY = sys.executable
CHECK = HERE.parent / "proto" / "check_main_freshness.py"


def main():
    L.reset_origin()
    repo = L.fresh("s9")
    rec = L.Rec("v2-s9")
    L.write_case(repo, "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-98001.yaml",
                 L.case("VLLM-ASC-98001"))
    rc, out, err = L.py(CHECK, "--root", str(repo), cwd=HERE)
    rec.add("heartbeat before rebuild", rc, out, err)
    rc, out, err = L.py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
    rec.add("rebuild", rc, out, err)
    rc, out, err = L.py(CHECK, "--root", str(repo), cwd=HERE)
    rec.add("heartbeat after rebuild", rc, out, err)
    rec.show()
    print(rec.dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
