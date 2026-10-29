"""E11 reproduction: an all-digit short SHA is stored as an integer and crashes the
entry-activity generator.

Cause: `scripts/settle_trace_feedback.py:286-287` writes `checkout` / `kb_rev` as
ordinary YAML scalars. `scripts/entry_activity.py:414,495` then puts them in a set and
calls `sorted()`. If one row's SHA is all digits (a legal short SHA) and another row's
SHA contains a hex letter, the set holds {int, str} and `sorted()` raises TypeError.
`build_entry_activity.py` is part of the post-merge rebuild job, so the whole generated
artifact plane stays stale after such a merge.

The reproduction is deterministic: it writes the two row shapes by hand, exactly as
settle would write them.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab_common as L

ROWS = """# synthetic entry-activity rows for E11
- {{run: 2026-10-28-1200, deployment: e11, checkout: {a}, kb_rev: {a}, sessions: 1, kind: case, id: VLLM-ASC-90001, selected: 0, loaded: 0, resolved: 1, misdiagnosed: 0, self_resolved: 0, excluded: 0}}
- {{run: 2026-10-28-1300, deployment: e11, checkout: {b}, kb_rev: {b}, sessions: 1, kind: case, id: VLLM-ASC-90002, selected: 0, loaded: 0, resolved: 1, misdiagnosed: 0, self_resolved: 0, excluded: 0}}
"""


def main() -> int:
    rec = L.Recorder("e11-sha-type")
    L.seed_integrated_main()
    repo = L.fresh_clone("e11")
    L.git(repo, "config", "user.name", "e11")
    L.git(repo, "config", "user.email", "e11@lab.local")
    src = repo / "metrics/entry-activity.d/2026-W44.yaml"

    # (1) mixed types: 8577483 is all digits -> YAML int; 55c20dc -> str
    src.write_text(ROWS.format(a="8577483", b="55c20dc"), encoding="utf-8")
    rc, out, err = L.py(repo / "scripts/build_entry_activity.py", cwd=repo)
    rec.add("build_entry_activity with mixed int/str checkout values", rc, out, err)
    rc, out, err = L.py(repo / "scripts/verify_entry_activity.py", cwd=repo)
    rec.add("verify_entry_activity on the same source rows", rc, out, err)

    # (2) the same rows with the numeric-looking SHA quoted -> success
    src.write_text(ROWS.format(a="'8577483'", b="'55c20dc'"), encoding="utf-8")
    rc, out, err = L.py(repo / "scripts/build_entry_activity.py", cwd=repo)
    rec.add("build_entry_activity after quoting the numeric-looking SHA", rc, out, err)

    # (3) confirm the writer path emits unquoted scalars (code-level evidence)
    settle = (repo / "scripts/settle_trace_feedback.py").read_text(encoding="utf-8").splitlines()
    line = next((f"{i}: {l.strip()}" for i, l in enumerate(settle, 1)
                 if '"checkout": ea.checkout_rev(root)' in l), "not found")
    rec.add("settle_trace_feedback row construction (writes checkout/kb_rev unquoted)", 0, line)

    rec.print_summary()
    print(f"\nrecord: {rec.dump()}")
    return 0 if all(r["rc"] == 0 for r in rec.rows if r["step"].startswith("build_entry_activity after")) else 1


if __name__ == "__main__":
    sys.exit(main())
