#!/usr/bin/env python3
"""E10: two clones produce a live snapshot for the same period."""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab_v2 as L

HERE = Path(__file__).parent
PY = sys.executable


def main():
    L.reset_origin()
    a, b = L.fresh("e10a"), L.fresh("e10b")
    L.F.write_trace(a, "v2-e10-a", summary="A snapshot", user_msg="310P bf16",
                    cand="case A", active_case=None)
    L.F.write_trace(b, "v2-e10-b", summary="B snapshot", user_msg="HCCL port",
                    cand="case B", active_case=None)
    rec = L.Rec("v2-e10")
    for name, repo in (("A", a), ("B", b)):
        rc, out, err = L.py(repo / "scripts/metrics_snapshot.py", "--json", cwd=repo)
        data = json.loads(out) if rc == 0 and out.strip().startswith("{") else {}
        rec.add(f"{name} snapshot", rc, json.dumps(data, ensure_ascii=False)[:1200], err)
        if data:
            dest = repo / "metrics/timeline.d" / f"{data['period']}.yaml"
            dest.parent.mkdir(parents=True, exist_ok=True)
            # minimal source file with the generated metrics; avoid E12 validator noise here
            import yaml
            dest.write_text(yaml.safe_dump({k: data[k] for k in ("period", "kind", "metrics") if k in data},
                                           allow_unicode=True, sort_keys=False), encoding="utf-8")
    rec.add("same period?", 0, "see rows")
    rec.show()
    print(rec.dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
