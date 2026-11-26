"""Agentless-style bounded repair for the iBMC adapter, using Sleuth candidates."""

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ..candidate import CandidateError, apply_to_root, diff_workspace, rollback_workspace, validate_candidate
from ..contracts import Patch
from ..regions import REGIONS

REGION = "tooling.ibmc_analyzer"
SOURCE, = REGIONS[REGION].paths
PROBE = "scripts/evolve/evaluations/ibmc_presence.py"
ISSUE = (
    "iBMC 的 npu_info 为空、含采集超时文字或表头后只有错误信息时，采集无法证明 NPU 数量，"
    "报告却给出疑似丢卡。请在 missing 沿用“NPU 在位未知”并说明证据缺口，保留被过滤告警的依据。"
    "有完整表头且没有数据行时，按本分析器已有约定保留零卡告警。保留真实少卡和正常八卡的原有结果。"
)


class AgentlessOptimizer:
    id = "agentless"
    version = "sleuth-ibmc-v1"
    scope = "tooling"
    execution = "subagent"

    def propose(self, target, observations, current, budget):
        if target != self.scope:
            raise ValueError("agentless requires tooling")
        return Patch(
            target_kind=target, target_component=REGION, summary=ISSUE,
            algorithm=self.id, algorithm_version=self.version,
            payload={"file": SOURCE, "format": "SEARCH/REPLACE",
                     "entry": "experiment agentless prepare"},
            budget=dict(budget or {}),
        )


def candidate_from_response(response, source, revision):
    """Map disjoint whole-line edits on the original file to one Sleuth candidate."""
    lines = source.splitlines(keepends=True)
    pattern = re.compile(
        r"^```(?:python)?\n### " + re.escape(SOURCE)
        + r"\n<<<<<<< SEARCH\n(.*?)^=======\n(.*?)^>>>>>>> REPLACE\n```[ \t]*$",
        re.MULTILINE | re.DOTALL,
    )
    edits = []
    pos = 0
    for match in pattern.finditer(response):
        if response[pos:match.start()].strip():
            raise ValueError("expected only fenced SEARCH/REPLACE edits for " + SOURCE)
        old, new = match.groups()
        if any(marker in (old + new).splitlines() for marker in
               ("<<<<<<< SEARCH", "=======", ">>>>>>> REPLACE", "```")):
            raise ValueError("unexpected nested edit marker")
        if not old or source.count(old) != 1:
            raise ValueError("SEARCH must match one unique, non-empty block of source lines")
        offset = source.index(old)
        if offset and source[offset - 1] != "\n":
            raise ValueError("SEARCH must begin at the start of a line")
        start = source.count("\n", 0, offset)
        edits.append((start, start + len(old.splitlines()), new))
        pos = match.end()
    if not edits or response[pos:].strip():
        raise ValueError("expected only fenced SEARCH/REPLACE edits for " + SOURCE)
    edits.sort()
    start, end = edits[0][0], edits[-1][1]
    changed = []
    cursor = start
    for left, right, replacement in edits:
        if left < cursor:
            raise ValueError("SEARCH blocks overlap")
        changed.extend(lines[cursor:left])
        changed.append(replacement)
        cursor = right
    return validate_candidate({
        "candidate_id": "ibmc-" + hashlib.sha256(response.encode()).hexdigest()[:16],
        "target_kind": "tooling",
        "region": REGION, "target_component": REGION, "file": SOURCE,
        "action": "modify", "base_rev": revision, "old_text": "".join(lines[start:end]),
        "new_text": "".join(changed), "checks": ["diff_check"],
    })


def _run(root, argv, *, timeout=300):
    return subprocess.run(argv, cwd=root, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _checked(root, argv):
    result = _run(root, argv)
    if result.returncode:
        raise ValueError(f"{argv[0]} exited {result.returncode}: {result.stderr[-2400:]}")
    return result.stdout


def _save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _presence_groups(samples):
    """Report independent denominators for unknown evidence, true faults, and healthy inputs."""
    groups = {}
    categories = {"unknown": "insufficient_evidence", "zero": "confirmed_fault",
                  "one": "confirmed_fault", "eight": "healthy"}
    for sample in samples.values():
        group = groups.setdefault(categories[sample["expected"]], {"passed": 0, "total": 0})
        group["total"] += 1
        group["passed"] += int(sample["pass"])
    return groups


def _measure(workspace, output):
    # Experiments resume at their pinned commit, including runs prepared before the move.
    probe_path = workspace / PROBE
    if not probe_path.is_file():
        probe_path = workspace / "eval/analyzers/ibmc_presence.py"
    probe = _run(workspace, [sys.executable, "-X", "utf8", str(probe_path)])
    (output / "probe.log").write_text(probe.stderr, encoding="utf-8")
    if probe.returncode:
        raise ValueError(f"analyzer probe failed (exit {probe.returncode}), see {output / 'probe.log'}")
    samples = json.loads(probe.stdout)
    regression = _run(workspace, [sys.executable, "-X", "utf8", "-m", "unittest",
                                  "-v", "tests.test_analyzers"])
    (output / "regression.log").write_text(regression.stdout + regression.stderr, encoding="utf-8")
    return {"samples": samples, "by_group": _presence_groups(samples),
            "passed": sum(s["pass"] for s in samples.values()),
            "total": len(samples), "probe_ok": all("error" not in s for s in samples.values()),
            "regression_ok": regression.returncode == 0}


def _prompt(source):
    return (
        ISSUE + "\n\n请先定位负责在位判定和证据缺口的代码。仅输出一个或多个以下格式的代码块，"
        "每个代码块写同一个文件路径。SEARCH 从原文件逐行复制且只命中一次，多个块不得重叠。"
        "仅根据题目与下方源码生成回复，保留缩进，勿读取外部文件或运行命令。\n\n"
        f"```python\n### {SOURCE}\n<<<<<<< SEARCH\n原代码\n=======\n替换代码\n>>>>>>> REPLACE\n```\n\n"
        f"文件 {SOURCE}\n\n```python\n{source}```\n"
    )


def run_trial(root, run_dir, response=None, *, attempt=None):
    root, run_dir = Path(root).resolve(), Path(run_dir).resolve()
    if response is None:
        revision = _checked(root, ["git", "rev-parse", "HEAD"]).strip()
        source = _checked(root, ["git", "show", f"{revision}:{SOURCE}"])
        run_dir.mkdir(parents=True, exist_ok=False)
        output = run_dir
        (output / "request.md").write_text(_prompt(source), encoding="utf-8")
    else:
        baseline = json.loads((run_dir / "baseline.json").read_text(encoding="utf-8"))
        revision = baseline["base_rev"]
        if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
            raise ValueError("invalid base_rev in baseline.json")
        source = _checked(root, ["git", "show", f"{revision}:{SOURCE}"])
        response_text = Path(response).read_text(encoding="utf-8-sig")
        output = attempt or Path(tempfile.mkdtemp(prefix="attempt-", dir=run_dir))
        (output / "response.md").write_text(response_text, encoding="utf-8")
        try:
            candidate = candidate_from_response(response_text, source, revision)
        except ValueError as exc:
            _save(output / "result.json", {"decision": "invalid", "error": str(exc)})
            print(f"invalid: {exc}\nresult: {output / 'result.json'}")
            return 2
        _save(output / "candidate.json", candidate)

    with tempfile.TemporaryDirectory(prefix="sleuth-rsi-") as temp:
        workspace = Path(temp) / "repo"
        _checked(root, ["git", "worktree", "add", "--detach", str(workspace), revision])
        try:
            if response is not None:
                try:
                    apply_to_root(workspace, candidate)
                except CandidateError as exc:
                    _save(output / "result.json", {"decision": "invalid", "error": str(exc)})
                    print(f"invalid: {exc}\nresult: {output / 'result.json'}")
                    return 2
                (output / "candidate.diff").write_text(diff_workspace(workspace), encoding="utf-8")
            result = _measure(workspace, output)
        finally:
            rollback_workspace(root, workspace)
    result["base_rev"] = revision
    if response is None:
        _save(output / "baseline.json", result)
        print(f"baseline {result['passed']}/{result['total']}, regression_ok={result['regression_ok']}")
        print(f"request: {output / 'request.md'}")
        return 0 if result["regression_ok"] and result["probe_ok"] else 2
    if baseline["samples"].keys() != result["samples"].keys():
        raise ValueError("sample IDs differ between baseline and candidate")
    eligible = (baseline["regression_ok"] and baseline["probe_ok"] and result["regression_ok"]
                and result["passed"] == result["total"] and result["passed"] > baseline["passed"])
    result["decision"] = "pass" if eligible else "reject"
    result["baseline_passed"] = baseline["passed"]
    _save(output / "result.json", result)
    print(f"{result['decision']}: {baseline['passed']} -> {result['passed']}/{result['total']}, "
          f"regression_ok={result['regression_ok']}")
    print(f"result: {output / 'result.json'}")
    return 0 if eligible else 1


def run_model_trials(root, run_dir, command, attempts):
    """Send source and last attempt feedback to a stdin/stdout model command."""
    if attempts < 1 or not command:
        raise ValueError("run requires --attempts >= 1 and --model-command COMMAND [ARGS ...]")
    run_dir = Path(run_dir).resolve()
    if run_trial(root, run_dir):
        return 2
    request = (run_dir / "request.md").read_text(encoding="utf-8")
    feedback = ""
    for number in range(1, attempts + 1):
        attempt = run_dir / f"attempt-{number:03d}"
        attempt.mkdir()
        print(f"attempt {number}/{attempts}: {attempt}", flush=True)
        prompt = request + feedback
        (attempt / "prompt.md").write_text(prompt, encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="sleuth-model-") as model_dir:
            with (attempt / "model.log").open("w", encoding="utf-8") as log:
                model = subprocess.run(command, cwd=model_dir, input=prompt, stdout=subprocess.PIPE,
                                       stderr=log, text=True, encoding="utf-8", timeout=600)
        if model.returncode:
            raise ValueError(f"model exited {model.returncode}: {attempt / 'model.log'}")
        response = attempt / "response.md"
        response.write_text(model.stdout, encoding="utf-8")
        status = run_trial(root, run_dir, response, attempt=attempt)
        if status == 0:
            return 0
        report = (attempt / "result.json").read_text(encoding="utf-8")
        regression = attempt / "regression.log"
        tail = regression.read_text(encoding="utf-8")[-2000:] if regression.exists() else ""
        feedback = ("\n上次回复和本地验证结果如下。请针对上面的原始源码重新给出完整修改。\n"
                    + model.stdout + "\n" + report + "\n" + tail)
    print("attempt budget exhausted")
    return 1
