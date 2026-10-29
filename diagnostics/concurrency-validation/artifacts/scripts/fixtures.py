"""Synthetic but interface-compatible fixtures for the concurrency validation lab.

All content is invented. It mimics the real case schema (docs/spec/case-schema.md,
examples/sample-case.yaml) and the real trace schema
(skills/diagnose/references/diagnosis-trace.md), so the repository's own scripts
(verify_case_draft.py, build_index.py, verify_references.py, sediment_batch.py) can
consume it without modification.

Why a hand-written template instead of yaml.safe_dump: the E6 experiment needs two
engineers to edit *disjoint lines* of the same case file. A dump-based rewrite would
change every line and turn every experiment into a whole-file Git conflict, which is
not what a human editor does.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml


def q(value: str) -> str:
    """A YAML double-quoted scalar (JSON string syntax is valid YAML)."""
    return json.dumps(value, ensure_ascii=False)


def yaml_list(items) -> str:
    return "[" + ", ".join(q(x) for x in items) + "]"


CASE_A = {
    "id": "VLLM-ASC-90001",
    "title": "310P 平台不支持 bf16：qwen3-tts 启动即失败",
    "category": "interrupt",
    "tags": ["310p", "bf16", "startup", "dtype"],
    "platforms": ["A2-310P"],
    "ranges": ["==0.22.0"],
    "symptoms": [
        "npu-smi info 显示芯片为 310P",
        "启动 qwen3-tts 服务时报 RuntimeError: bfloat16 is not supported on this device",
        "qwen3_tts.yaml 中 dtype 字段为 bfloat16",
    ],
    "cmd": "grep -E 'bfloat16|bf16' {{log_path}}",
    "expected": "regex:(bfloat16|bf16).*(not supported|unsupported)",
    "cheks": [
        ("check", "日志里是否出现 bf16/bfloat16 不被支持的报错"),
        ("command_template", "grep -n 'dtype' qwen3_tts.yaml"),
    ],
    "severity": "service-affecting",
    "fix_type": "config-change",
    "detail": "客户端到端复现；把 dtype 改成 float16 后启动成功",
    "root_cause": "310P 硬件不支持 bfloat16；qwen3_tts.yaml 配的是 bfloat16，启动时算子选择失败",
    "fix": "把 qwen3_tts.yaml 的 dtype 全部改为 float16 后重启服务",
    "session": "2026-10-28-conc-a01",
}

# Same underlying root cause as CASE_A, filed under a different category, with
# different symptom wording, a different discriminator and a different ID.
CASE_B = {
    "id": "VLLM-ASC-90002",
    "title": "qwen3-tts 在 310P 上输出全 0：dtype 落到不支持的 bf16",
    "category": "precision",
    "tags": ["310p", "dtype", "zero-output"],
    "platforms": ["A2-310P"],
    "ranges": ["==0.22.0"],
    "symptoms": [
        "推理返回的音频张量全为 0",
        "npu-smi info 显示芯片为 310P",
        "服务启动日志里 dtype 打印为 bfloat16",
    ],
    "cmd": "grep -c 'dtype=bfloat16' {{log_path}}",
    "expected": "regex:^[1-9]",
    "cheks": [
        ("check", "输出张量是否全 0 且设备为 310P"),
        ("check", "qwen3_tts.yaml 的 dtype 是否仍为 bfloat16"),
    ],
    "severity": "service-affecting",
    "fix_type": "config-change",
    "detail": "同一台机器上改 dtype 为 float16 后输出正常",
    "root_cause": "310P 不支持 bfloat16，qwen3-tts 按 bf16 配置加载，算子回退后输出全 0",
    "fix": "把 qwen3_tts.yaml 的 dtype 改为 float16 并重启",
    "session": "2026-10-28-conc-b01",
}

# Third, deliberately different knowledge unit used for the same-path conflict.
CASE_X = {
    "id": "VLLM-ASC-90003",
    "title": "310P 上 HCCL 端口被占用导致多机启动超时",
    "category": "interrupt",
    "tags": ["310p", "hccl", "port", "timeout"],
    "platforms": ["A2-310P"],
    "ranges": ["==0.22.0"],
    "symptoms": ["多机启动卡在 HCCL init", "日志出现 EADDRINUSE"],
    "cmd": "grep -c 'EADDRINUSE' {{log_path}}",
    "expected": "regex:^[1-9]",
    "cheks": [("check", "是否多机同时启动且端口固定")],
    "severity": "service-affecting",
    "fix_type": "env-var",
    "detail": "改 HCCL_IF_BASE_PORT 后启动成功（工程师 A 的现场）",
    "root_cause": "多机并用固定 HCCL 端口，第二个进程 bind 失败",
    "fix": "export HCCL_IF_BASE_PORT=<不同端口> 后重启",
    "session": "2026-10-28-conc-a02",
}


def case_text(c: dict) -> str:
    """Render one case in a stable, line-editable YAML layout."""
    out = [
        f"# {c['id']} —— synthetic concurrency-validation fixture (invented content)",
        "cases:",
        f"  - id: {c['id']}",
        f"    title: {q(c['title'])}",
        f"    category: {c['category']}",
        f"    tags: {yaml_list(c['tags'])}",
        f"    platforms: {yaml_list(c['platforms'])}",
        "    compat:",
        "      - framework: vllm-ascend",
        f"        ranges: {yaml_list(c['ranges'])}",
        "    investigation_quality: high",
        "    symptoms:",
    ]
    out += [f"      - {q(s)}" for s in c["symptoms"]]
    out += [
        "    quickly_check:",
        "      primary:",
        f"        command_template: {q(c['cmd'])}",
        "        rank_selector: all_failed",
        f"        expected: {q(c['expected'])}",
        "    diagnosis:",
    ]
    for i, (kind, value) in enumerate(c["cheks"], 1):
        out.append(f"      - step: {i}")
        out.append(f"        {kind}: {q(value)}")
    out += [
        f"    severity: {c['severity']}",
        "    fix_side_effects: [requires-restart]",
        f"    fix_type: {c['fix_type']}",
        "    verification:",
        "      source: investigation",
        f"      detail: {q(c['detail'])}",
        f"    root_cause: {q(c['root_cause'])}",
        f"    fix: {q(c['fix'])}",
        f"    source_session: {c['session']}",
        "",
    ]
    return "\n".join(out)


def draft_yaml(case: dict, novelty: str, trace_id: str) -> str:
    """The flat draft format to-postmortem produces today (postmortems/inbox/<id>.case.yaml)."""
    head = "\n".join([
        "# to-postmortem draft (synthetic fixture)",
        f"# pre-triage: {novelty}",
        "# verification: investigation",
        f"# 来源: traces/{trace_id}.yaml",
        "",
    ])
    return head + case_text(case)


POSTMORTEM = """# {cid} — {title}

## 背景与现象

{body}

## 定位过程

1. 采集 npu-smi 与启动日志；
2. 在日志中确认 `{needle}`；
3. 改配置后复现消失。

## 根因

{root_cause}

## 修复

{fix}

## 证据缺口

- 只有单机复现，没有第二台同款机器交叉验证。
"""


def postmortem_text(case: dict, needle: str, body: str) -> str:
    return POSTMORTEM.format(
        cid=case["id"], title=case["title"], body=body,
        needle=needle, root_cause=case["root_cause"], fix=case["fix"],
    ).lstrip("\n")


TRACE = """session_id: {sid}
status: {status}
active_case: {active_case}
created_at: "2026-10-28T09:00:00+08:00"
updated_at: "2026-10-28T11:30:00+08:00"
workload_type: inference
workload_type_source: material
report_file: traces/evidence/{sid}/report.md
summary: "{summary}"
last_action: report
feedback: {feedback}
sediment_candidates:
  - kind: case
    summary: "{cand}"
    status: proposed
trace:
  - ts: "2026-10-28T09:00:00+08:00"
    role: user
    content: "{user_msg}"
  - ts: "2026-10-28T09:05:00+08:00"
    role: agent
    output: "已按 triage 路由到 interrupt；用 quickly_check 排除了 3 条候选"
    reason: "错误签名是启动失败，属于 interrupt；命中候选的 expected 都不匹配"
"""


def trace_text(sid: str, summary: str, user_msg: str, cand: str,
               active_case: str | None = None, feedback_outcome: str | None = None) -> str:
    if feedback_outcome:
        fb = "{case: %s, outcome: %s, confirmed_at: \"2026-10-28T11:00:00+08:00\"}" % (
            active_case or "null", feedback_outcome)
    else:
        fb = "{}"
    return TRACE.format(
        sid=sid,
        status="resolved",
        active_case=active_case if active_case else "null",
        summary=summary.replace('"', "'"),
        feedback=fb,
        cand=cand.replace('"', "'"),
        user_msg=user_msg.replace('"', "'"),
    )


def write_trace(repo: Path, sid: str, **kw) -> Path:
    p = repo / "traces" / f"{sid}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(trace_text(sid, **kw), encoding="utf-8")
    return p


def write_draft(inbox: Path, case: dict, novelty: str, trace_id: str,
                needle: str, body: str) -> tuple[Path, Path]:
    inbox.mkdir(parents=True, exist_ok=True)
    case_path = inbox / f"{case['id']}.case.yaml"
    md_path = inbox / f"{case['id']}.md"
    case_path.write_text(draft_yaml(case, novelty, trace_id), encoding="utf-8")
    md_path.write_text(postmortem_text(case, needle, body), encoding="utf-8")
    return case_path, md_path


def promote(draft_case_path: Path, repo: Path, ns: str, category: str) -> Path:
    """groom 升格：把草稿的 cases: 段落写进 knowledge/<ns>/<category>/<id>.yaml。"""
    doc = yaml.safe_load(draft_case_path.read_text(encoding="utf-8"))
    cid = doc["cases"][0]["id"]
    dest = repo / "knowledge" / ns / category / f"{cid}.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = draft_case_path.read_text(encoding="utf-8")
    # strip the draft header (kept behaviour of groom: the queue's header does not
    # become part of the knowledge file)
    body = body[body.index("cases:"):]
    dest.write_text(f"# {cid} —— promoted from synthetic draft\n" + body, encoding="utf-8")
    return dest
