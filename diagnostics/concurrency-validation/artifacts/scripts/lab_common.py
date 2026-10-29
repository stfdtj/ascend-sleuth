"""Shared helpers for the concurrency validation lab (Stage I baseline).

Everything here writes only into the disposable lab root (D:\\working\\asv by default)
or into a clone passed by the caller. The report directory lives in the repository,
but no tracked repository file is touched by these scripts.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB_ROOT = Path(os.environ.get("ASV_ROOT", r"D:\working\asv"))
LOG_DIR = LAB_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
PY = sys.executable
GIT_ENV = {
    "GIT_AUTHOR_DATE": "2026-10-28T10:00:00+08:00",
    "GIT_COMMITTER_DATE": "2026-10-28T10:00:00+08:00",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


def env_for(extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env.update({
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "GIT_TERMINAL_PROMPT": "0",
    })
    if extra:
        env.update(extra)
    return env


def run(cmd, cwd: Path, timeout: int = 900, extra_env: dict | None = None):
    """Run a command, capture stdout/stderr as UTF-8, never raise on non-zero."""
    p = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env_for(extra_env),
    )
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def py(script: str | Path, *args, cwd: Path, timeout: int = 900):
    return run([PY, str(script), *args], cwd=cwd, timeout=timeout)


def git(repo: Path, *args, check: bool = False, env: dict | None = None):
    rc, out, err = run(["git", *args], cwd=repo, extra_env=env)
    if check and rc != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}: rc={rc}\n{out}\n{err}")
    return rc, out.strip(), err.strip()


def git_ok(repo: Path, *args, env: dict | None = None):
    return git(repo, *args, check=True, env=env)


def stamp(tag: str, text: str) -> Path:
    """Persist a command transcript under artifacts/logs/ and return its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"{tag}.log"
    path.write_text(text, encoding="utf-8")
    return path


class Recorder:
    """Collect structured evidence rows; dump one JSON per experiment run."""

    def __init__(self, name: str):
        self.name = name
        self.rows: list[dict] = []
        self.notes: list[str] = []

    def add(self, step: str, rc: int, stdout: str = "", stderr: str = "", **kw):
        self.rows.append({
            "step": step,
            "rc": rc,
            "stdout_tail": tail(stdout),
            "stderr_tail": tail(stderr),
            **kw,
        })
        return rc

    def note(self, text: str):
        self.notes.append(text)

    def dump(self) -> Path:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"{self.name}-{datetime.now(timezone.utc).strftime('%H%M%S')}.json"
        path.write_text(json.dumps({
            "experiment": self.name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "lab_root": str(LAB_ROOT),
            "notes": self.notes,
            "rows": self.rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def print_summary(self):
        for r in self.rows:
            print(f"[{r['rc']:>2}] {r['step']}")
            if r["stdout_tail"]:
                for line in r["stdout_tail"].splitlines():
                    print(f"      {line}")
            if r["stderr_tail"]:
                for line in r["stderr_tail"].splitlines():
                    print(f"   !  {line}")


def tail(text: str, n: int = 12) -> str:
    lines = [l for l in (text or "").splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def rmtree_force(path: Path):
    """rmtree that survives Windows read-only git objects."""
    import shutil
    import stat

    def onerror(func, p, exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            raise

    if path.exists():
        shutil.rmtree(path, onerror=onerror)


#: Baseline commit of the real fork this validation was run against (2026-10-28).
BASE_COMMIT = os.environ.get(
    "ASV_BASE", "28adab0d1db1f00989b5416dfeaf8206df71ca4a")


def reset_origin(base: str | None = None):
    """Reset the lab bare remote to the baseline commit and drop experiment branches.

    Every scenario starts from the same tree, so an earlier scenario's pushes must
    not leak into the next one. Only the lab bare repo is touched.
    """
    base = base or BASE_COMMIT
    origin = LAB_ROOT / "origin.git"
    rc, out, err = run(["git", "update-ref", "refs/heads/main", base], cwd=origin)
    if rc != 0:
        raise RuntimeError(f"reset origin main failed: {out}\n{err}")
    rc, out, err = run(["git", "for-each-ref", "--format=%(refname)", "refs/heads"], cwd=origin)
    for ref in out.splitlines():
        if ref.strip() and ref.strip() != "refs/heads/main":
            run(["git", "update-ref", "-d", ref.strip()], cwd=origin)
    return base


def seed_integrated_main(cases=None) -> Path:
    """Reset the lab remote and publish a main that already contains the two synthetic
    duplicate cases (VLLM-ASC-90001 / 90002). Later scenarios start from that tree so
    they exercise a populated, realistic main without replaying the whole merge story.
    """
    import fixtures as F  # local import: fixtures imports nothing from this module

    reset_origin()
    repo = fresh_clone("seed")
    git(repo, "config", "user.name", "seed")
    git(repo, "config", "user.email", "seed@lab.local")
    for case, ns, cat in ((F.CASE_A, "inference/vllm-ascend", "interrupt"),
                          (F.CASE_B, "inference/vllm-ascend", "precision")):
        dest = repo / "knowledge" / ns / cat / f"{case['id']}.yaml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f"# {case['id']} —— synthetic fixture (invented content)\n"
                        + F.case_text(case)[F.case_text(case).index("cases:"):],
                        encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "seed: synthetic duplicate cases", env=GIT_ENV)
    rc, out, err = py(repo / "scripts/rebuild_generated.py", "--check", cwd=repo)
    if rc != 0:
        raise RuntimeError(f"seed rebuild failed: {out}\n{err}")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "chore: rebuild generated views", env=GIT_ENV)
    git(repo, "push", "origin", "main")
    return repo


def fresh_clone(name: str, source: Path | None = None, branch: str = "main") -> Path:
    """Clone the lab origin (or a local repo) into LAB_ROOT/name, removing an old copy."""
    dest = LAB_ROOT / name
    rmtree_force(dest)
    src = source or (LAB_ROOT / "origin.git")
    rc, out, err = run(["git", "clone", "-q", "--branch", branch, str(src), str(dest)], cwd=LAB_ROOT)
    if rc != 0:
        raise RuntimeError(f"clone failed: {out}\n{err}")
    for k, v in (("user.name", name), ("user.email", f"{name}@lab.local"),
                 ("commit.gpgsign", "false"), ("core.autocrlf", "false")):
        git_ok(dest, "config", k, v)
    return dest
