"""Child process used by test_inbox_put.py to create genuinely overlapping operations.

Modes:
  new       wait for <go> file, then run inbox_put.new (exclusive mkdir loop)
  naive     wait for <go>, then "check whether seq exists -> sleep -> mkdir(exist_ok)"
  crash_mkdir   mkdir a draft dir, then exit
  crash_files   mkdir, write a half case.yaml, exit
  crash_done    mkdir + three valid files + a truncated DONE, exit
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import inbox_put  # noqa: E402


def wait_for(go: Path, timeout: float = 30.0):
    t0 = time.time()
    while not go.exists():
        if time.time() - t0 > timeout:
            raise SystemExit("go file never appeared")
        time.sleep(0.002)


def write_valid(target: Path, draft_id: str):
    target.mkdir(parents=True, exist_ok=True)
    (target / "sources.yaml").write_text(f"draft_id: {draft_id}\n", encoding="utf-8")
    (target / "case.yaml").write_text("cases:\n  - id: VLLM-ASC-90001\n    title: x\n", encoding="utf-8")
    (target / "postmortem.md").write_text("# x\n", encoding="utf-8")


def main() -> int:
    mode, root, go = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    index = sys.argv[4] if len(sys.argv) > 4 else "0"
    inbox = root / "postmortems" / "inbox"

    if mode == "new":
        wait_for(go)
        return inbox_put.main(["new", "--root", str(root), "--source", "diag"])
    if mode == "naive":
        wait_for(go)
        inbox.mkdir(parents=True, exist_ok=True)
        date = "2026-10-28"
        seq = 1
        while (inbox / f"{date}-diag-{seq:03d}").exists():
            seq += 1
        time.sleep(0.05)                    # the window the plan calls "check-then-act"
        target = inbox / f"{date}-diag-{seq:03d}"
        target.mkdir(parents=True, exist_ok=True)
        (target / "case.yaml").write_text(
            f'cases:\n  - id: VLLM-ASC-90001\n    title: "writer {index}"\n', encoding="utf-8")
        return 0
    if mode == "crash_mkdir":
        inbox.mkdir(parents=True, exist_ok=True)
        target = inbox / "2026-10-28-diag-001"
        os.mkdir(target)
        os._exit(7)
    if mode == "crash_files":
        inbox.mkdir(parents=True, exist_ok=True)
        target = inbox / "2026-10-28-diag-002"
        target.mkdir(parents=True, exist_ok=True)
        (target / "case.yaml").write_text("cases:\n  - id: VLLM-ASC-90001\n    title: \"half", encoding="utf-8")
        os._exit(7)
    if mode == "crash_done":
        target = inbox / "2026-10-28-diag-003"
        write_valid(target, target.name)
        # truncated DONE: valid YAML, no `files` map
        (target / "DONE").write_text("completed_at: 2026-10-28T10:00:00+08:00\n", encoding="utf-8")
        os._exit(7)
    raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    sys.exit(main())
