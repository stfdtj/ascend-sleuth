"""Score iBMC presence reports via the same CLI used by diagnosis (synthetic inputs)."""

import json
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tests.test_analyzers import read_result, run_cli, write_text

HEADER = "Name|Board|Power|WorkMode|SingleEcc|DoubleEcc|Diversification\n"
CARDS = [f"NPU{i}|Board|150W|Normal|0|0|NA\n" for i in range(1, 9)]
CASES = {
    "empty": ("", "unknown"),
    "timeout": ("collection timed out\n", "unknown"),
    "truncated": (HEADER + "collection interrupted\n", "unknown"),
    "missing": (None, "unknown"),
    "zero": (HEADER, "zero"),
    "one": (HEADER + CARDS[0], "one"),
    "eight": (HEADER + "".join(CARDS), "eight"),
}


def score(folder, content, expected):
    dump = folder / "dump_info"
    write_text(dump / "AppDump/sensor_alarm/current_event.txt", "")
    if content is not None:
        write_text(dump / "AppDump/CpuMem/npu_info", content)
    out = folder / "out"
    proc = run_cli(["run", "ibmc_analyzer", "--inputs", json.dumps([str(dump)]),
                    "--out-dir", str(out)])
    if proc.returncode:
        raise RuntimeError(f"{folder.name}: analyzer exited {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    result = read_result(out)
    return assess(result, expected)


def _has_evidence(item):
    evidence = item.get("evidence")
    return isinstance(evidence, str) and bool(evidence.strip())


def _is_count_claim(item):
    return "疑似丢卡" in item["claim"] or "NPU 数量" in item["claim"]


def assess(result, expected):
    findings = result["findings"]
    count_findings = [item for item in findings if _is_count_claim(item)]
    alerts = [item["claim"] for item in count_findings]
    report_ok = (result.get("status") in ("ok", "partial")
                 and any(_has_evidence(item) for item in findings))
    gaps = [gap for gap in result["missing"] if "NPU 在位未知" in gap]
    suppressed = [item for item in result.get("suppressed", []) if _is_count_claim(item)]
    if expected == "unknown":
        passed = not alerts and bool(gaps and suppressed) and all(_has_evidence(s) for s in suppressed)
    elif expected == "eight":
        passed = not alerts and not gaps and not suppressed
    else:
        count = 0 if expected == "zero" else 1
        passed = (len(alerts) == 1 and re.search(rf"NPU 数量\s+{count}\s*<", alerts[0]) is not None
                  and _has_evidence(count_findings[0]) and not gaps and not suppressed)
    return {"expected": expected, "pass": report_ok and passed, "report_ok": report_ok,
            "alerts": alerts, "unknown": gaps,
            "suppressed": suppressed}


if __name__ == "__main__":
    with TemporaryDirectory(prefix="ibmc-cases-") as temp:
        results = {}
        for name, (content, expected) in CASES.items():
            try:
                results[name] = score(Path(temp) / name, content, expected)
            except (OSError, RuntimeError, ValueError, KeyError, TypeError,
                    subprocess.TimeoutExpired) as exc:
                print(f"{name}: {exc}", file=sys.stderr)
                results[name] = {"expected": expected, "pass": False, "error": str(exc)[-2000:]}
    print(json.dumps(results, ensure_ascii=False))
