"""Stage I / B6 (E1): Scenario 1 "shared local deployment" -- two writers, one inbox.

Precondition verified here with repository code: `scripts/shared_dir.py inbox` resolves
the inbox of the *main checkout*, so every worktree of the same clone writes the same
`postmortems/inbox/`. Two agent sessions in two worktrees therefore share the queue.

The writer used here is `Path.write_text` -- the same open/write/close operation the
agent's file-write tool performs for `postmortems/inbox/<id>.case.yaml` /
`<id>.md`. No new protection is introduced (Stage I).

Experiments:
  1. shared-path evidence (clone + worktree resolve to the same inbox);
  2. 10 rounds, two threads write the same draft file simultaneously -> who survives;
  3. 3 rounds, chunked large writes -> mixed/truncated content classification;
  4. a writer killed mid-write -> partial file; what detects it and what does not;
  5. control: simultaneous writes to different ids survive independently;
  6. "half set" (case.yaml present, postmortem.md missing) -> does anything check it?
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fixtures as F
import lab_common as L

BK = threading.Barrier(2)


def write_small(path: Path, marker: str):
    text = F.case_text(dict(F.CASE_A, title=f"同一草稿并发写入实验 {marker}"))
    BK.wait(timeout=10)
    path.write_text(text, encoding="utf-8")


def write_chunked(path: Path, marker: str, total_mb: int = 3, delay=0.001):
    """Deliberately non-atomic writer: the shape a streaming/large-material write has."""
    payload = (marker * 1024)[:1024]
    BK.wait(timeout=10)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(f"# draft marker={marker}\ncases:\n  - id: VLLM-ASC-90099\n    title: \"")
        for _ in range(total_mb * 1024):
            fh.write(payload)
            fh.flush()
            time.sleep(delay)
        fh.write("\"\n")


def classify(path: Path, markers=("ALPHA", "BETA")) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    present = {m: (m in raw) for m in markers}
    mixed = sum(v for v in present.values()) > 1
    try:
        import yaml
        yaml.safe_load(raw)
        parses = True
    except Exception as exc:
        parses = f"{type(exc).__name__}: {exc}"[:120]
    return {"size": len(raw), "markers": present, "mixed": mixed, "parses": parses,
            "head": raw[:80].replace("\n", "\\n")}


def main() -> int:
    rec = L.Recorder("inbox-race")
    L.reset_origin()
    repo = L.fresh_clone("inboxlab")
    L.git(repo, "config", "user.name", "inboxlab")
    L.git(repo, "config", "user.email", "inboxlab@lab.local")

    # 1. shared-path evidence
    wt = L.LAB_ROOT / "inboxlab-wt"
    L.rmtree_force(wt)
    rc, out, err = L.git(repo, "worktree", "add", "-q", str(wt), "-b", "kb/wt-inbox")
    rec.add("create a second worktree of the same clone", rc, out, err, worktree=str(wt))
    paths = {}
    for label, cwd in (("main-checkout", repo), ("worktree", wt)):
        rc, out, err = L.py(cwd / "scripts/shared_dir.py", "inbox", cwd=cwd)
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        paths[label] = lines[-1] if lines else None
        rec.add(f"shared_dir inbox from {label}", rc, "\n".join(lines[-2:] if lines else []), err)
    rec.add("shared inbox identical across worktrees?", 0 if paths["main-checkout"] == paths["worktree"] else 1,
            json.dumps(paths), identical=paths["main-checkout"] == paths["worktree"])
    inbox = Path(paths["main-checkout"])

    # 2. 10 rounds: two simultaneous writers, same file
    rounds = []
    for i in range(10):
        target = inbox / f"VLLM-ASC-90098.case.yaml"
        target.unlink(missing_ok=True)
        t1 = threading.Thread(target=write_small, args=(target, f"ALPHA-{i}"))
        t2 = threading.Thread(target=write_small, args=(target, f"BETA-{i}"))
        t1.start(); t2.start(); t1.join(); t2.join()
        info = classify(target, markers=(f"ALPHA-{i}", f"BETA-{i}"))
        rounds.append(info)
    rec.add("same-file concurrent small writes (10 rounds)", 0,
            json.dumps(rounds, ensure_ascii=False, indent=1),
            rounds=len(rounds),
            both_present=sum(1 for r in rounds if all(r["markers"].values())),
            one_present=sum(1 for r in rounds if sum(r["markers"].values()) == 1),
            valid_yaml=sum(1 for r in rounds if r["parses"] is True))

    # 3. chunked large writes: corruption shape
    big = []
    for i in range(3):
        target = inbox / "VLLM-ASC-90097.case.yaml"
        target.unlink(missing_ok=True)
        t1 = threading.Thread(target=write_chunked, args=(target, "ALPHA"))
        t2 = threading.Thread(target=write_chunked, args=(target, "BETA"))
        t1.start(); t2.start(); t1.join(); t2.join()
        big.append(classify(target))
    rec.add("same-file chunked large writes (3 rounds)", 0,
            json.dumps(big, ensure_ascii=False, indent=1),
            mixed=sum(1 for r in big if r["mixed"]),
            parse_failures=sum(1 for r in big if r["parses"] is not True))

    # 4. writer killed mid-write
    target = inbox / "VLLM-ASC-90096.case.yaml"
    target.unlink(missing_ok=True)
    child = [L.PY, "-c", (
        "import time,sys\n"
        "p=sys.argv[1]\n"
        "with open(p,'w',encoding='utf-8') as f:\n"
        "    f.write('# partial\\ncases:\\n  - id: VLLM-ASC-90096\\n    title: \"')\n"
        "    for _ in range(4000):\n"
        "        f.write('x'*256)\n"
        "        f.flush()\n"
        "        time.sleep(0.002)\n"
    ), str(target)]
    proc = subprocess.Popen(child, cwd=str(repo), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(0.35)
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    killed = classify(target, markers=())
    rec.add("writer killed mid-write: file left behind", 0, json.dumps(killed, ensure_ascii=False),
            parses=killed["parses"] is True, size=killed["size"])
    rc, out, err = L.py(repo / "scripts/verify_case_draft.py", str(target), cwd=repo)
    rec.add("verify_case_draft on the killed-writer file", rc, out, err)

    # 4b. half set: case.yaml complete, postmortem.md missing
    target2 = inbox / "VLLM-ASC-90095.case.yaml"
    target2.write_text(F.case_text(dict(F.CASE_A, id="VLLM-ASC-90095")), encoding="utf-8")
    (inbox / "VLLM-ASC-90095.md").unlink(missing_ok=True)
    rc, out, err = L.py(repo / "scripts/verify_case_draft.py", str(target2), cwd=repo)
    rec.add("half set (case.yaml present, .md missing): verify_case_draft", rc, out, err)
    grep = L.run(["git", "grep", "-n", "-E", "\\.md|\\.case\\.yaml",
                  "--", "scripts/sediment_batch.py", "scripts/verify_case_draft.py",
                  "skills/knowledge-groom/SKILL.md", "postmortems/inbox/README.md"], cwd=repo)
    rec.add("who reads the draft's .md half? (grep for .md in the intake path)", grep[0],
            grep[1], grep[2])

    # 5. control: different ids
    ids = {}
    for i in range(4):
        p = inbox / f"VLLM-ASC-9010{i}.case.yaml"
        p.write_text(F.case_text(dict(F.CASE_A, id=f"VLLM-ASC-9010{i}")), encoding="utf-8")
        ids[i] = p.exists() and "cases:" in p.read_text(encoding="utf-8")
    rec.add("control: different ids written to the same inbox", 0, json.dumps(ids),
            all_present=all(ids.values()))

    path = rec.dump()
    rec.print_summary()
    print(f"\nrecord: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
