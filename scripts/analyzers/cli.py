#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内置分析器统一 CLI。

用法：
  python3 scripts/analyzers/cli.py status [--json]
  python3 scripts/analyzers/cli.py list
  python3 scripts/analyzers/cli.py run <name> --inputs <路径...> [--out-dir <目录>] [--session-id <ID>]

开关：SLEUTH_ANALYZERS=on 启用；未设置或 off 时 run 直接拒绝，不启动分析器。
每个分析器也可以直接跑自己的适配器：python3 scripts/analyzers/<name>/run.py --help
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _lib import ENV_NAME, UPSTREAM_COMMIT, analyzer_enabled, enablement_source, force_utf8  # noqa: E402
from registry import ANALYZERS, find  # noqa: E402


def _installed(item: dict) -> bool:
    return (HERE / item["adapter"]).is_file() and (HERE / item["vendor"]).is_dir()


def _status_payload() -> dict:
    return {
        "schema_version": 1,
        "enabled": analyzer_enabled(),
        "source": enablement_source(),
        "upstream_commit": UPSTREAM_COMMIT,
        "python": sys.executable,
        "analyzers": [
            {
                "name": item["name"],
                "installed": _installed(item),
                "adapter": str(HERE / item["adapter"]),
                "vendor": str(HERE / item["vendor"]),
                "inputs": item["inputs"],
                "purpose": item["purpose"],
            }
            for item in ANALYZERS
        ],
    }


def cmd_status(args: argparse.Namespace) -> int:
    payload = _status_payload()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        state = "enabled" if payload["enabled"] else "disabled"
        print(f"analyzers: {state}")
        print(f"source: {payload['source']}")
        print(f"python: {payload['python']}")
        print(f"upstream: {payload['upstream_commit']}")
        for item in payload["analyzers"]:
            mark = "installed" if item["installed"] else "MISSING"
            print(f"  {item['name']:<22} {mark}")
        if not payload["enabled"]:
            print(f"\n启用：设置 {ENV_NAME}=on（A/B 组保持未设置）")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        print(json.dumps(
            [
                {"name": item["name"], "inputs": item["inputs"], "purpose": item["purpose"]}
                for item in ANALYZERS
            ],
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    print("name                     inputs")
    for item in ANALYZERS:
        print(f"{item['name']:<24} {item['inputs']}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    item = find(args.name)
    if item is None:
        print(f"未知分析器：{args.name}；可用：{', '.join(x['name'] for x in ANALYZERS)}", file=sys.stderr)
        return 2
    if not analyzer_enabled():
        print(
            f"分析器未启用（{enablement_source()}）。这是实验开关，不是错误；"
            f"设置 {ENV_NAME}=on 后重跑。本次没有启动任何分析器。",
            file=sys.stderr,
        )
        return 3
    adapter = HERE / item["adapter"]
    if not adapter.is_file():
        print(f"分析器适配器缺失：{adapter}", file=sys.stderr)
        return 4
    cmd = [sys.executable, str(adapter), *args.rest]
    return subprocess.call(cmd)


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(description="ascend-sleuth 内置分析器 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="查看开关与分析器安装状态")
    status.add_argument("--json", action="store_true", help="输出 JSON")
    status.set_defaults(func=cmd_status)

    listing = sub.add_parser("list", help="列出分析器与输入形态")
    listing.add_argument("--json", action="store_true", help="输出 JSON")
    listing.set_defaults(func=cmd_list)

    run = sub.add_parser("run", help="运行一个分析器（参数透传给适配器）")
    run.add_argument("name", help="分析器名")
    run.add_argument("rest", nargs=argparse.REMAINDER, help="--inputs / --out-dir / --session-id / --ab / --purpose / --timeout")
    run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
