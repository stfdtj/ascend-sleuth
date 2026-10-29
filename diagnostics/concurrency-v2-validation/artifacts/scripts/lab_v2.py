"""Shared helpers for the V2 validation lab (disposable clones under D:\\working\\asv2)."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(os.environ.get("ASV2_ROOT", r"D:\working\asv2"))
LOG = LAB / "logs"
LOG.mkdir(parents=True, exist_ok=True)
PY = sys.executable
BASE = None  # resolved from origin/main at runtime
OLD = Path(r"D:\working\ascend-sleuth\diagnostics\concurrency-validation\artifacts\scripts")
sys.path.insert(0, str(OLD))
import fixtures as F  # noqa: E402


def env():
    e = dict(os.environ)
    e.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "GIT_TERMINAL_PROMPT": "0"})
    return e


def run(cmd, cwd, timeout=900):
    p = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, env=env())
    return p.returncode, p.stdout or "", p.stderr or ""


def py(script, *args, cwd):
    return run([PY, str(script), *args], cwd=cwd)


def git(repo, *args, env_extra=None):
    e = env()
    if env_extra:
        e.update(env_extra)
    p = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=e)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def rmtree(path: Path):
    def onerror(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if path.exists():
        shutil.rmtree(path, onerror=onerror)


def fresh(name: str) -> Path:
    dest = LAB / name
    rmtree(dest)
    rc, out, err = run(["git", "clone", "-q", "--branch", "main", str(LAB / "origin.git"), str(dest)], cwd=LAB)
    if rc != 0:
        raise RuntimeError(f"clone {name}: {out}\n{err}")
    for k, v in (("user.name", name), ("user.email", f"{name}@v2.local"),
                 ("commit.gpgsign", "false"), ("core.autocrlf", "false")):
        git(dest, "config", k, v)
    return dest


def base_sha() -> str:
    rc, out, _ = git(LAB / "base", "rev-parse", "HEAD")
    return out


def reset_origin():
    rc, out, _ = git(LAB / "origin.git", "update-ref", "refs/heads/main", base_sha())
    for ref in git(LAB / "origin.git", "for-each-ref", "--format=%(refname)", "refs/heads")[1].splitlines():
        if ref.strip() and ref.strip() != "refs/heads/main":
            git(LAB / "origin.git", "update-ref", "-d", ref.strip())


def commit(repo: Path, msg: str):
    git(repo, "add", "-A")
    return git(repo, "commit", "-m", msg,
               env_extra={"GIT_AUTHOR_DATE": "2026-10-29T10:00:00+08:00",
                          "GIT_COMMITTER_DATE": "2026-10-29T10:00:00+08:00"})


def case(cid: str, **over):
    c = dict(F.CASE_X)
    c.update(over)
    c["id"] = cid
    c["session"] = over.get("session", "v2-session-" + cid.lower())
    return c


def write_case(repo: Path, rel: str, c: dict):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(F.case_text(c), encoding="utf-8")


class Rec:
    def __init__(self, name):
        self.name = name
        self.rows = []
        self.notes = []

    def add(self, step, rc, out="", err="", **kw):
        self.rows.append({"step": step, "rc": rc, "out": (out or "")[-3000:],
                          "err": (err or "")[-1500:], **kw})
        return rc

    def note(self, text):
        self.notes.append(text)

    def dump(self):
        p = LOG / f"{self.name}-{datetime.now(timezone.utc).strftime('%H%M%S')}.json"
        p.write_text(json.dumps({"name": self.name, "base": base_sha(), "notes": self.notes,
                                 "rows": self.rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    def show(self):
        for r in self.rows:
            print(f"[{r['rc']:>2}] {r['step']}")
            if r["out"]:
                print("   " + r["out"].replace("\n", "\n   ")[-1200:])
            if r["err"]:
                print(" ! " + r["err"].replace("\n", "\n ! ")[-600:])
