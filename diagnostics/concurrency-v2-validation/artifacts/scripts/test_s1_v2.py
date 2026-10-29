"""S1: shared-inbox baseline (flat same-name writes) vs V2 UUID drafts."""
from __future__ import annotations
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab_v2 as L

HERE = Path(__file__).parent
PY = sys.executable
INBOX = HERE.parent / "proto" / "inbox_v2.py"
BARRIER = threading.Barrier(2)


def write_flat(path: Path, marker: str):
    BARRIER.wait(timeout=10)
    path.write_text(L.F.case_text(L.case("VLLM-ASC-97001", title=f"flat {marker}")),
                    encoding="utf-8")


def main():
    L.reset_origin()
    repo = L.fresh("s1v2")
    inbox = repo / "postmortems/inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    rec = L.Rec("v2-s1")
    rounds = []
    for i in range(10):
        target = inbox / "VLLM-ASC-97001.case.yaml"
        target.unlink(missing_ok=True)
        t1 = threading.Thread(target=write_flat, args=(target, f"A{i}"))
        t2 = threading.Thread(target=write_flat, args=(target, f"B{i}"))
        t1.start(); t2.start(); t1.join(); t2.join()
        text = target.read_text(encoding="utf-8")
        rounds.append({"A": f"A{i}" in text, "B": f"B{i}" in text})
    rec.add("V1 flat same-name 10 rounds", 0, json.dumps(
        {"both": sum(1 for r in rounds if r["A"] and r["B"]),
         "one": sum(1 for r in rounds if r["A"] != r["B"])}))
    # V2: eight simultaneous UUID drafts
    import subprocess
    procs = [subprocess.Popen([PY, str(INBOX), "new", "--root", str(repo)], cwd=str(HERE),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              encoding="utf-8") for _ in range(8)]
    outs = [p.communicate(timeout=60) for p in procs]
    dirs = [p for p in inbox.iterdir() if p.is_dir()]
    rec.add("V2 UUID 8 concurrent creators", 0 if len(dirs) >= 8 else 1,
            json.dumps({"dirs": len(dirs), "unique": len({d.name for d in dirs})}))
    rec.show()
    print(rec.dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
