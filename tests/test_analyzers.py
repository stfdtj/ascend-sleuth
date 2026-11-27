#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内置分析器的端到端测试：开关、失败路径、合成输入到报告输出。

所有夹具在临时目录现造，不读主检出的 traces/ 或客户数据，不访问外网。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "scripts" / "analyzers" / "cli.py"
BASE_ENV = {
    **os.environ,
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
}


def run_cli(args, enabled: bool | None = True, extra_env: dict | None = None,
            timeout: int = 300, cli: Path = CLI):
    env = dict(BASE_ENV)
    if enabled is None:
        env.pop("SLEUTH_ANALYZERS", None)
    else:
        env["SLEUTH_ANALYZERS"] = "on" if enabled else "off"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(cli), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def read_result(out_dir: Path) -> dict:
    return json.loads((out_dir / "result.json").read_text(encoding="utf-8"))


class AnalyzerTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="sleuth-analyzers-"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def out(self, name: str) -> Path:
        return self.tmp / "out" / name


class GateTests(AnalyzerTestBase):
    def test_status_reports_environment_override(self):
        proc = run_cli(["status", "--json"], enabled=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["enabled"])
        names = {item["name"] for item in payload["analyzers"]}
        self.assertIn("ibmc_analyzer", names)
        self.assertIn("prof-compare", names)
        self.assertNotIn("vllm-ascend-tuning", names)
        self.assertEqual(len(names), 7)

    def test_analyzer_can_be_enabled_and_disabled_without_environment_variable(self):
        checkout = self.tmp / "isolated-checkout"
        for relative in (
            "_fs.py", "exec_log_path.py", "analyzers/cli.py", "analyzers/_lib.py",
            "analyzers/registry.py", "analyzers/issue-analyzer/run.py",
            "analyzers/issue-analyzer/scripts/log_analyzer.py",
        ):
            target = checkout / "scripts" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / "scripts" / relative, target)
        cli = checkout / "scripts" / "analyzers" / "cli.py"
        preference = checkout / ".local" / "analyzers.enabled"
        log = checkout / "host-0.log"
        write_text(log, "2026-08-28 10:00:02 ERROR collective timeout rank 5\n")
        out = self.out("locally-enabled")
        analysis = ["run", "issue-analyzer", "--inputs", str(log), "--out-dir", str(out)]

        status = run_cli(["status"], enabled=None, cli=cli)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("analyzers: disabled", status.stdout)
        self.assertRegex(status.stdout, r"issue-analyzer\s+installed")
        self.assertIn("scripts/analyzers/cli.py enable", status.stdout)
        self.assertFalse(preference.exists())
        refused = run_cli(analysis, enabled=None, cli=cli)
        self.assertEqual(refused.returncode, 3, refused.stderr)
        self.assertFalse(out.exists())

        enabled = run_cli(["enable"], enabled=None, cli=cli)
        self.assertEqual(enabled.returncode, 0, enabled.stderr)
        self.assertEqual(preference.read_text(encoding="utf-8").strip(), "on")
        status = run_cli(["status", "--json"], enabled=None, cli=cli)
        payload = json.loads(status.stdout)
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["source"], str(preference))
        analyzed = run_cli(analysis, enabled=None, cli=cli)
        self.assertEqual(analyzed.returncode, 0, analyzed.stdout + analyzed.stderr)
        self.assertIn("collective timeout", read_result(out)["findings"][0]["claim"])
        invocation = json.loads((out / "invocation.json").read_text(encoding="utf-8"))
        self.assertEqual(invocation["enabled_by"], str(preference))

        overridden = run_cli(["status", "--json"], enabled=False, cli=cli)
        self.assertFalse(json.loads(overridden.stdout)["enabled"])
        self.assertEqual(preference.read_text(encoding="utf-8").strip(), "on")
        disabled = run_cli(["disable"], enabled=None, cli=cli)
        self.assertEqual(disabled.returncode, 0, disabled.stderr)
        self.assertEqual(preference.read_text(encoding="utf-8").strip(), "off")
        status = run_cli(["status", "--json"], enabled=None, cli=cli)
        self.assertFalse(json.loads(status.stdout)["enabled"])

    def test_disabled_run_does_not_create_output(self):
        out = self.out("must-not-exist")
        proc = run_cli(
            ["run", "ibmc_analyzer", "--inputs", json.dumps([str(self.tmp)]), "--out-dir", str(out)],
            enabled=False,
        )
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(out.exists(), "禁用时不应创建输出目录，更不应启动分析器")
        self.assertIn("SLEUTH_ANALYZERS", proc.stderr)

    def test_disabled_adapter_also_refuses(self):
        out = self.out("adapter-must-not-exist")
        adapter = REPO / "scripts" / "analyzers" / "ibmc_analyzer" / "run.py"
        env = dict(BASE_ENV)
        env["SLEUTH_ANALYZERS"] = "off"
        proc = subprocess.run(
            [sys.executable, str(adapter), "--inputs", json.dumps([str(self.tmp)]), "--out-dir", str(out)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(out.exists())

    def test_no_input_prompts_for_required_data(self):
        out = self.out("no-input")
        proc = run_cli(["run", "ibmc_analyzer", "--inputs", "", "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 1)
        result = read_result(out)
        self.assertEqual(result["reason"], "no-input")
        self.assertTrue(result["data_needed"])
        self.assertIn("dump_info", result["data_needed"][0])
        self.assertIn("需要的数据", proc.stdout)

    def test_bad_input_is_blocked_with_result(self):
        out = self.out("bad-input")
        missing = self.tmp / "does-not-exist.log"
        proc = run_cli(["run", "issue-analyzer", "--inputs", json.dumps([str(missing)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 1)
        result = read_result(out)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "bad-input")
        self.assertTrue((out / "result.json").is_file())
        self.assertTrue(result["data_needed"])
        self.assertIn("日志", result["data_needed"][0])
        self.assertEqual(list((out).glob("logs/*")), [], "坏路径不应启动上游脚本")


class IbmcTests(AnalyzerTestBase):
    def _fixture(self) -> Path:
        root = self.tmp / "ibmc" / "dump_info"
        write_text(root / "AppDump" / "sensor_alarm" / "current_event.txt", "")
        write_text(root / "AppDump" / "BMC" / "psu_info.txt", "PSU1 present Vin=220V Vout=12V\n")
        return root

    def test_synthetic_dump_info(self):
        out = self.out("ibmc")
        proc = run_cli(["run", "ibmc_analyzer", "--inputs", json.dumps([str(self._fixture())]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertIn(result["status"], ("ok", "partial"))
        self.assertTrue(result["data_needed"] or result["missing"])
        self.assertTrue(any(path.endswith("_bmc.json") for path in result["artifacts"]))
        self.assertTrue((out / "result.json").is_file())
        self.assertTrue(list(out.glob("*.html")))
        self.assertIn("RESULT_JSON=", proc.stdout)

    def test_partial_gap_stays_in_missing_not_data_needed(self):
        """可选缺口不能写进 data_needed：那会让 agent 去要本次不需要的材料。"""
        out = self.out("ibmc-partial")
        proc = run_cli(["run", "ibmc_analyzer", "--inputs", json.dumps([str(self._fixture())]), "--out-dir", str(out)])
        result = read_result(out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["missing"], "缺采集时间等可选缺口应留在 missing")
        self.assertEqual(result["data_needed"], [], "partial 不应向用户索要材料")

    def test_cli_status_survives_cp1252_console(self):
        """Windows 默认代码页下打印中文不能崩：输出统一转 UTF-8。"""
        proc = run_cli(["status"], extra_env={"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("analyzers:", proc.stdout)

    def test_npu_info_missing_is_unknown_not_zero(self):
        """缺 npu_info 时在位情况是未知：不能生成「疑似丢卡」，但原始判定要留痕。"""
        out = self.out("ibmc-npu-missing")
        proc = run_cli(["run", "ibmc_analyzer", "--inputs", json.dumps([str(self._fixture())]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        claims = " ".join(item["claim"] for item in result["findings"])
        self.assertNotIn("疑似丢卡", claims, "缺文件不能推出丢卡")
        self.assertNotIn("NPU 数量 0", claims)
        self.assertTrue(
            any("NPU 在位未知" in item for item in result["missing"]),
            "缺文件要作为未知项如实报出",
        )
        self.assertTrue(result.get("suppressed"), "被移除的判定要能追溯")
        self.assertEqual(result["suppressed"][0]["reason"], "npu-info-missing")
        raw = "".join(
            Path(item).read_text(encoding="utf-8-sig", errors="replace")
            for item in result["artifacts"]
            if item.endswith("_bmc.json")
        )
        self.assertIn("疑似丢卡", raw, "原始 JSON 必须保留上游判定，供追溯")

    def test_npu_info_present_with_zero_cards_keeps_finding(self):
        """文件在、卡数真是 0：这是有效异常，不能被过滤。"""
        root = self._fixture()
        write_text(
            root / "AppDump" / "CpuMem" / "npu_info",
            "Name|Board|Power|WorkMode|SingleEcc|DoubleEcc|Diversification\n",
        )
        out = self.out("ibmc-npu-zero")
        proc = run_cli(["run", "ibmc_analyzer", "--inputs", json.dumps([str(root)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        claims = " ".join(item["claim"] for item in result["findings"])
        self.assertIn("NPU 数量 0", claims, "真实 0 卡必须保留为异常")
        self.assertFalse(result.get("suppressed"), "有文件就不该走缺证据的抑制分支")

    def test_npu_info_with_eight_cards_reports_no_npu_issue(self):
        """正常 8 卡不应出现任何在位异常，也不应被记为缺失。"""
        root = self._fixture()
        rows = ["Name|Board|Power|WorkMode|SingleEcc|DoubleEcc|Diversification|FW|SW"]
        rows += [f"NPU{i}|Board|150W|Normal|0|0|NA|1.0|1.0" for i in range(1, 9)]
        write_text(root / "AppDump" / "CpuMem" / "npu_info", "\n".join(rows) + "\n")
        out = self.out("ibmc-npu-ok")
        proc = run_cli(["run", "ibmc_analyzer", "--inputs", json.dumps([str(root)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        claims = " ".join(item["claim"] for item in result["findings"])
        self.assertNotIn("NPU 数量", claims)
        self.assertFalse(any("NPU 在位未知" in item for item in result["missing"]))
        self.assertFalse(result.get("suppressed"))

    def test_p2_items_go_to_observations_with_raw_values(self):
        """P2 不进 findings，但要作为观察项露出原始读数与等级。"""
        out = self.out("ibmc-p2")
        root = REPO / "tests" / "fixtures" / "analyzers" / "bmc-dump-02-ecc" / "dump_info"
        proc = run_cli(["run", "ibmc_analyzer", "--inputs", json.dumps([str(root)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        claims = " ".join(item["claim"] for item in result["findings"])
        self.assertNotIn("逻辑盘", claims, "P2 不能混进 findings")
        observations = result.get("observations") or []
        self.assertTrue(observations, "P2 要以观察项形式交给 agent")
        self.assertTrue(any(item.get("level") == "P2" for item in observations))
        self.assertTrue(all(item.get("evidence") for item in observations), "观察项要带证据位置")

    def test_sensor_observation_keeps_raw_value_and_marks_threshold_unverified(self):
        """温度读数按原样露出，阈值不给确定性结论。"""
        out = self.out("ibmc-temp")
        root = REPO / "tests" / "fixtures" / "analyzers" / "bmc-dump-04-temp" / "dump_info"
        proc = run_cli(["run", "ibmc_analyzer", "--inputs", json.dumps([str(root)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        observations = result.get("observations") or []
        text = " ".join(f"{item.get('topic')} {item.get('detail')}" for item in observations)
        self.assertIn("99", text, "原始读数要保留")
        self.assertIn("阈值归属未核", text, "未经验证的阈值不能写成结论")
        self.assertNotIn("超过", text, "不能替 agent 判超限")
        self.assertNotIn("95", text, "未核的阈值数值不该出现在观察项里")
        claims = " ".join(item["claim"] for item in result["findings"])
        self.assertNotIn("传感器", claims)

    def test_ecc_with_bom_is_reconciled_not_silently_zero(self):
        """真实输入带 BOM 时上游读不出 ECC：适配层要复读补上，不能静默报 0。"""
        root = self._fixture()
        ecc = root / "AppDump" / "CpuMem" / "npu_ecc_info.json"
        ecc.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"EccInfo": [{"Name": "NPU1", "SingleBitEcc": {"Count": 0}, "MultiBitEcc": {"Count": 5}}]}
        )
        ecc.write_text(payload, encoding="utf-8-sig")  # 带 BOM 写出，模拟真实采集
        out = self.out("ibmc-ecc-bom")
        proc = run_cli(["run", "ibmc_analyzer", "--inputs", json.dumps([str(root)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        claims = " ".join(item["claim"] for item in result["findings"])
        self.assertIn("适配层复读", claims, "BOM 导致的漏读要补上")
        self.assertIn("多bit=5", claims)
        self.assertTrue(result.get("reconciled"), "补读要留痕")

    def test_ecc_unparsable_is_reported_as_missing(self):
        """文件在但解析不了：写进 missing，不写成 0。"""
        root = self._fixture()
        ecc = root / "AppDump" / "CpuMem" / "npu_ecc_info.json"
        ecc.parent.mkdir(parents=True, exist_ok=True)
        ecc.write_text("{not-json", encoding="utf-8")
        out = self.out("ibmc-ecc-bad")
        proc = run_cli(["run", "ibmc_analyzer", "--inputs", json.dumps([str(root)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertTrue(any("npu_ecc_info.json 存在但解析失败" in item for item in result["missing"]))
        claims = " ".join(item["claim"] for item in result["findings"])
        self.assertNotIn("多bit=", claims)

    def test_zip_slip_is_rejected(self):
        archive = self.tmp / "ibmc" / "evil.zip"
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../escape.txt", "escaped")
        out = self.out("ibmc-zip")
        proc = run_cli(["run", "ibmc_analyzer", "--inputs", json.dumps([str(archive)]), "--out-dir", str(out)])
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(list(self.tmp.rglob("escape.txt")), [], "越界条目不应被写出")


class IbmcPilotFixtureTests(AnalyzerTestBase):
    """试点用的合成包（tests/fixtures/analyzers/bmc-dump-01）要保持可跑。"""

    def _fixture(self) -> Path:
        return REPO / "tests" / "fixtures" / "analyzers" / "bmc-dump-01" / "dump_info"

    def test_pilot_fixture_end_to_end(self):
        out = self.out("ibmc-pilot")
        proc = run_cli(["run", "ibmc_analyzer", "--inputs", json.dumps([str(self._fixture())]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertIn(result["status"], ("ok", "partial"))
        claims = " ".join(item["claim"] for item in result["findings"])
        self.assertIn("Power Supply input lost", claims, "当前告警要出现在发现里")
        self.assertIn("PSU1 Vin=0", claims, "电源输入为 0 要单独成为一条发现")
        self.assertTrue(result["missing"], "合成包缺 npu_info 等文件，必须如实报缺")
        self.assertTrue((out / "result.json").is_file())


class IssueTests(AnalyzerTestBase):
    def test_synthetic_logs(self):
        logs = self.tmp / "issue" / "plog"
        write_text(logs / "device-0.log", "[2026-08-28 10:00:02.200] [ERROR] HCCL execute failed\n")
        write_text(logs / "host-0.log", "2026-08-28 10:00:02 ERROR collective timeout rank 5\n")
        out = self.out("issue")
        proc = run_cli(["run", "issue-analyzer", "--inputs", json.dumps([str(logs.parent)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["findings"])
        hits = json.loads((out / "logs" / "hits.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(hits["total_hits"], 2)

    def test_log_archive_requires_unpacking(self):
        raw = self.tmp / "archived-logs" / "host-0.log"
        write_text(raw, "2026-08-28 10:00:02 ERROR collective timeout rank 5\n")
        archive = raw.with_name("plog_window.tar.gz")
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(raw, arcname=raw.name)
        out = self.out("issue-archive")
        proc = run_cli(["run", "issue-analyzer", "--inputs", str(archive), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any("先解包" in item for item in result["data_needed"]))
        self.assertIn(archive.name, result["detail"])
        self.assertFalse((out / "logs" / "hits.json").exists())


class DumpTests(AnalyzerTestBase):
    def _fixture(self):
        base = self.tmp / "dump"
        a = base / "a.json"
        b = base / "b.json"
        write_json(a, {"ascend": {"driver": {"version": "23.0.3"}}, "system": {"hostname": "a"}})
        write_json(b, {"ascend": {"driver": {"version": "23.0.4"}}, "system": {"hostname": "b"}})
        return a, b

    def test_compare(self):
        a, b = self._fixture()
        out = self.out("dump-compare")
        proc = run_cli(["run", "ascend-dump-analyzer", "--inputs", json.dumps([str(a), str(b)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(any(item.endswith("diff.json") for item in result["artifacts"]))
        diff = json.loads((out / "diff.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(diff["status"], "success")
        self.assertGreaterEqual(diff["summary"]["diff_count"], 2)

    def test_single_snapshot_uses_compatibility_not_diff(self):
        a, _ = self._fixture()
        out = self.out("dump-single")
        proc = run_cli(["run", "ascend-dump-analyzer", "--inputs", str(a), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(any(path.endswith("compatibility.json") for path in result["artifacts"]))
        self.assertFalse((out / "diff.json").exists(), "单份快照不走比对路径")

    def test_compare_preserves_partial_results(self):
        a, b = self._fixture()
        shutil.copyfile(a, b)
        damaged = a.parent / "damaged.json"
        write_text(damaged, "{invalid}")
        out = self.out("dump-partial")
        inputs = json.dumps([str(a), str(b), str(damaged)])
        proc = run_cli(["run", "ascend-dump-analyzer", "--inputs", inputs, "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertEqual(result["status"], "partial")
        self.assertIn("2 份已比对的快照未发现差异", result["findings"][0]["claim"])
        self.assertTrue(any(damaged.name in item for item in result["missing"]))
        self.assertEqual(result["data_needed"], [])
        self.assertIn(str(out / "diff.json"), result["artifacts"])


class DumpSingleTests(AnalyzerTestBase):
    """单份环境快照：看版本配套，不要求第二份。"""

    def _snapshot(self, name: str, toolkit: str = "9.2.0") -> Path:
        path = self.tmp / "dump-single" / name
        write_json(
            path,
            {
                "_meta": {"schema_version": "1.2", "status": "success"},
                "system": {"os_release": "Kylin V10", "machine": "aarch64", "release": "5.10.0"},
                "runtime": {
                    "python_version": "3.10.1",
                    "packages": {
                        "pip_list_raw": ["torch==2.7.1", "torch_npu==2.7.1.post11"]
                    },
                },
                "ascend": {
                    "toolkit": {"version": toolkit, "collection_status": "success"},
                    "driver": {"version": "24.1.0"},
                },
                "npu": {
                    "devices": [
                        {
                            "device_id": 0,
                            "name": "910B",
                            "chip_type": "Ascend910B",
                            "compatibility": "OK",
                        }
                    ]
                },
            },
        )
        return path

    def test_compatibility_facts(self):
        snapshot = self._snapshot("ok.json")
        out = self.out("dump-single-ok")
        proc = run_cli(
            ["run", "ascend-dump-analyzer", "--inputs", str(snapshot), "--out-dir", str(out)]
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertEqual(result["status"], "ok")
        claims = " ".join(item["claim"] for item in result["findings"])
        self.assertIn("torch_npu = 2.7.1.post11", claims)
        self.assertIn("软件配套匹配", claims)
        self.assertTrue(any(path.endswith("compatibility.json") for path in result["artifacts"]))
        self.assertFalse((out / "diff.json").exists(), "单份不应走比对路径")

    def test_incomplete_snapshot_keeps_workload_and_collection_evidence(self):
        path = self._snapshot("collection-gap.json")
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        del snapshot["npu"]
        snapshot["_meta"].update(
            status="partial",
            timestamp="2026-08-28 10:00:02",
            collection={
                "npu": {"status": "failed", "errors": ["npu-smi unavailable"]},
                "ping": {"status": "skipped", "reason": "probes disabled"},
            },
        )
        loaded = "/opt/cann/8.3.RC1/lib/libascendcl.so"
        snapshot["workload"] = {"targets": {"worker-0": {
            "pid": 42,
            "start_time_ticks": 1234,
            "libraries": {"source": "proc_maps", "paths": [loaded]},
        }}}
        write_json(path, snapshot)
        out = self.out("dump-collection-gap")
        proc = run_cli(["run", "ascend-dump-analyzer", "--inputs", str(path), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(any("npu-smi unavailable" in item for item in result["missing"]))
        self.assertTrue(any("业务进程配套未核对" in item for item in result["missing"]))
        self.assertFalse(any("ping" in item for item in result["missing"]))
        data = json.loads((out / "compatibility.json").read_text(encoding="utf-8"))
        self.assertEqual(data["software"]["status"], "matched")
        evidence = data["snapshot_evidence"]
        self.assertEqual(evidence["software_scope"], "collector_environment")
        self.assertEqual(evidence["collection"], snapshot["_meta"]["collection"])
        self.assertEqual(evidence["targets"]["worker-0"]["libraries"]["paths"], [loaded])

    def test_deviation_keeps_raw_version(self):
        snapshot = self._snapshot("deviation.json", toolkit="8.3.RC1")
        out = self.out("dump-single-deviation")
        proc = run_cli(
            ["run", "ascend-dump-analyzer", "--inputs", str(snapshot), "--out-dir", str(out)]
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        claims = " ".join(item["claim"] for item in result["findings"])
        self.assertIn("软件配套偏离", claims)
        self.assertIn("8.3.RC1", claims, "报原值，不报小写归一后的值")
        self.assertIn("9.2.0", claims)
        self.assertFalse(result["data_needed"], "单份成功时不该向用户要第二份")

    def test_compare_also_checks_each_snapshot(self):
        a = self._snapshot("compare-a.json", toolkit="9.2.0")
        b = self._snapshot("compare-b.json", toolkit="8.3.RC1")
        out = self.out("dump-compare-compat")
        proc = run_cli(
            [
                "run",
                "ascend-dump-analyzer",
                "--inputs",
                f"{a}\n{b}",
                "--out-dir",
                str(out),
            ]
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        claims = " ".join(item["claim"] for item in result["findings"])
        self.assertIn("配套偏离（compare-b.json", claims)
        self.assertIn("8.3.RC1", claims, "配套事实也要保留原始版本串")
        self.assertTrue(
            any(path.endswith("compatibility-02-compare-b.json") for path in result["artifacts"]),
            "每份快照的兼容性结果要作为产物留痕",
        )

    def test_invalid_json_is_blocked_not_crashed(self):
        path = self.tmp / "dump-single" / "bad.json"
        write_text(path, "{not-json")
        out = self.out("dump-single-bad")
        proc = run_cli(
            ["run", "ascend-dump-analyzer", "--inputs", str(path), "--out-dir", str(out)]
        )
        self.assertEqual(proc.returncode, 1)
        result = read_result(out)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "bad-input")
        self.assertIn("JSON", result["detail"])


class ProfCompareTests(AnalyzerTestBase):
    """两份单卡 NPU 文本导出：Host/Device 热点对比，不依赖第三方包。"""

    HEADER = (
        "Type,Accelerator Core,Name,Duration(us),Start Time(us),Stream ID,Device_id,"
        "Input Shapes,Output Shapes,Input Data Types,Output Data Types"
    )

    def _export(self, name: str, duration: int) -> Path:
        root = self.tmp / "prof" / name
        output = root / "ASCEND_PROFILER_OUTPUT"
        rows = [self.HEADER]
        for offset in (0, 2000):
            rows.append(
                f'MatMul,AI_CORE,aclnnMatmul,{duration},{100000 + offset},1,0,'
                f'"1024;1024","1024;1024","DT_BF16;DT_BF16","DT_BF16"'
            )
        rows.append(
            f'Vector,AI_VECTOR,aclnnAdd,{duration // 2},{105000},2,0,'
            f'"1024","1024","DT_BF16","DT_BF16"'
        )
        write_text(output / "kernel_details.csv", "\n".join(rows) + "\n")
        return root

    def test_two_single_card_exports(self):
        a = self._export("A", 1000)
        b = self._export("B", 1200)
        out = self.out("prof-compare")
        proc = run_cli(
            [
                "run",
                "prof-compare",
                "--inputs",
                f"{a}\n{b}",
                "--out-dir",
                str(out),
            ]
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertIn(result["status"], ("ok", "partial"))
        claims = " ".join(item["claim"] for item in result["findings"])
        self.assertIn("Device MatMul/AI_CORE", claims)
        self.assertIn("慢", claims)
        self.assertIn("0.400", claims)
        self.assertTrue((out / "prof_compare.json").is_file())
        self.assertTrue((out / "prof_compare.md").is_file())

    def test_mixed_pair_requires_gpu_baseline(self):
        npu = self._export("mixed", 1000)
        gpu = npu.parent / "rank.pt.trace.json"
        write_json(gpu, {"traceEvents": [
            {"name": "aten::matmul", "cat": "cpu_op", "ph": "X", "pid": 12,
             "tid": 12, "dur": 150, "ts": 100000},
            {"name": "MatMul", "cat": "kernel", "ph": "X", "pid": 0,
             "tid": 1, "dur": 600, "ts": 100200, "args": {"device": 0}},
        ]})
        out = self.out("mixed-gpu-first")
        proc = run_cli(["run", "prof-compare", "--inputs", f"{gpu}\n{npu}", "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        detail = json.loads((out / "prof_compare.json").read_text(encoding="utf-8"))
        matmul = next(row for row in detail["device"] if row["op"] == "MatMul")
        self.assertAlmostEqual(matmul["diff"]["delta_ms"], 1.4)
        self.assertEqual(detail["identity"]["base"]["device_type"], "GPU")
        self.assertEqual(detail["identity"]["compare"]["device_type"], "NPU")

        out = self.out("mixed-npu-first")
        proc = run_cli(["run", "prof-compare", "--inputs", f"{npu}\n{gpu}", "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertEqual(result["reason"], "bad-input")
        self.assertTrue(any("GPU trace 基准" in item for item in result["data_needed"]))
        self.assertIn("按顺序", result["detail"])
        self.assertFalse((out / "prof_compare.json").exists())

    def test_requires_two_sides(self):
        a = self._export("A", 1000)
        out = self.out("prof-compare-single")
        proc = run_cli(
            ["run", "prof-compare", "--inputs", str(a), "--out-dir", str(out)]
        )
        self.assertEqual(proc.returncode, 1)
        result = read_result(out)
        self.assertEqual(result["reason"], "bad-input")
        self.assertIn("两份", result["data_needed"][0])


class ClusterCompareTests(AnalyzerTestBase):
    HEADER = (
        "Step,Type,Index,Computing,Communication(Not Overlapped),Overlapped,Communication,"
        "Free,Stage,Bubble,Communication(Not Overlapped and Exclude Receive),Preparing"
    )

    def _cluster(self, name: str, stage: int) -> Path:
        root = self.tmp / "clusters" / name / "cluster_analysis_output"
        write_text(
            root / "cluster_step_trace_time.csv",
            "\n".join(
                [
                    self.HEADER,
                    f"1,rank,0,100000,20000,5000,25000,30000,{stage},0,20000,5000",
                    f"1,rank,1,110000,21000,5000,26000,31000,{stage + 1000},0,21000,6000",
                ]
            ),
        )
        write_json(root / "communication_group.json", {"collective": [[0, 1]], "p2p": [], "comm_group_parallel_info": []})
        return root.parent

    def test_compare(self):
        a = self._cluster("A", 155000)
        b = self._cluster("B", 215000)
        out = self.out("cluster-compare")
        proc = run_cli(["run", "cluster-compare", "--inputs", json.dumps([str(a), str(b)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertIn(result["status"], ("ok", "partial"))
        self.assertTrue((out / "cluster_compare_report.html").is_file())
        self.assertTrue((out / "cluster_compare_report.md").is_file())
        self.assertTrue(result["findings"])

    def test_nonoverlapping_steps_keep_shape_comparison(self):
        a = self._cluster("shape-A", 155000)
        b = self._cluster("shape-B", 215000)
        csv = b / "cluster_analysis_output" / "cluster_step_trace_time.csv"
        text = csv.read_text(encoding="utf-8").replace("\n1,rank,", "\n11,rank,")
        write_text(csv, text)
        out = self.out("shape-compare")
        proc = run_cli(["run", "cluster-compare", "--inputs", f"{a}\n{b}", "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertEqual(result["status"], "partial")
        self.assertIn("按采集顺序配对", result["summary"])
        self.assertTrue(any("仅用于形态比较" in gap for gap in result["missing"]))
        self.assertEqual(result["findings"][0]["kind"], "candidate")
        self.assertIn(str(out / "cluster_compare_report.html"), result["artifacts"])


class ClusterAnalysisTests(AnalyzerTestBase):
    def test_two_cards_keep_json_comparison_after_upstream_update(self):
        root = self.tmp / "multi-card"
        for rank in (0, 1):
            card = root / f"rank{rank}_ascend_pt"
            write_json(card / f"profiler_info_{rank}.json", {"rank_id": rank})
            write_text(
                card / "ASCEND_PROFILER_OUTPUT" / "step_trace_time.csv",
                "Step,Computing,Communication(Not Overlapped),Overlapped,Communication,Free,Stage,Bubble\n"
                f"1,100000,{20000 + rank * 10000},5000,{25000 + rank * 10000},30000,{155000 + rank * 10000},0\n",
            )
        out = self.out("multi-card")
        proc = run_cli(["run", "cluster-analysis", "--inputs", str(root), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        state = json.loads((out / "workflow_status.json").read_text(encoding="utf-8"))
        self.assertNotEqual(state["stages"]["compare_fallback"]["status"], "failed")
        self.assertTrue((out / "compare" / "compare_analysis_result.json").is_file())
        self.assertTrue((out / "performance_report.html").is_file())

    def test_single_card(self):
        card = self.tmp / "ca" / "card0_ascend_pt" / "ASCEND_PROFILER_OUTPUT"
        write_text(
            card / "step_trace_time.csv",
            "Step,Computing,Communication(Not Overlapped),Overlapped,Communication,Free,Stage,Bubble\n"
            "1,100000,20000,5000,25000,30000,155000,0\n"
            "2,110000,21000,5000,26000,31000,167000,0\n",
        )
        write_json(self.tmp / "ca" / "card0_ascend_pt" / "profiler_info_0.json", {"rank_id": 0})
        out = self.out("cluster-analysis")
        proc = run_cli(
            ["run", "cluster-analysis", "--inputs", json.dumps([str(self.tmp / "ca")]), "--out-dir", str(out)],
            timeout=300,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertIn(result["status"], ("ok", "partial"))
        self.assertTrue((out / "performance_report.html").is_file())
        self.assertFalse((self.tmp / "ca" / "cluster_analysis_output").exists(), "单卡分析不应写输入目录")


class CpuHostTests(AnalyzerTestBase):
    def test_synthetic_trace(self):
        generated = self.tmp / "cpu" / "case"
        generator = REPO / "tests" / "fixtures" / "analyzers" / "generate_cpu_trace.py"
        proc = subprocess.run(
            [sys.executable, str(generator), "--output", str(generated)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=BASE_ENV,
            timeout=180,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        trace = generated / "synthetic_256_capture.tar.gz"
        self.assertTrue(trace.is_file())
        out = self.out("cpu")
        proc = run_cli(["run", "cpu-host-performance", "--inputs", json.dumps([str(trace)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertEqual(result["status"], "ok")
        self.assertTrue((out / "hostbound_report.html").is_file())
        self.assertTrue(any("cpu_binder_simple.py" in item for item in result["artifacts"]))
        self.assertTrue(any("bind_design.json" in item for item in result["artifacts"]))


class UnsupportedInputTests(AnalyzerTestBase):
    def test_cluster_compare_requires_two_dirs(self):
        one = self.tmp / "clusters" / "only" / "cluster_analysis_output"
        one.mkdir(parents=True, exist_ok=True)
        out = self.out("unsupported")
        proc = run_cli(["run", "cluster-compare", "--inputs", json.dumps([str(one.parent)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(read_result(out)["reason"], "bad-input")


class PluginRemovalTests(AnalyzerTestBase):
    def test_plugin_package_is_gone(self):
        self.assertFalse((REPO / "dsh-plugins" / "dsh-sleuth-analyzers").exists())

    def test_diagnose_uses_builtin_cli(self):
        skill = (REPO / "skills" / "diagnose" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("sleuth_analyze", skill)
        self.assertIn("scripts/analyzers/cli.py", skill, "诊断骨架要给出入口")
        dispatch = (REPO / "skills" / "diagnose" / "references" / "analyzer-dispatch.md").read_text(encoding="utf-8")
        self.assertIn("scripts/analyzers/cli.py", dispatch)
        self.assertIn("SLEUTH_ANALYZERS", dispatch)


class CallChainTests(AnalyzerTestBase):
    """Agent 的调用链路：发现（list）→ 选择（dispatch 表）→ 调用（CLI）三处必须对得上。"""

    def _registry(self) -> set:
        proc = run_cli(["list", "--json"], enabled=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return {item["name"] for item in json.loads(proc.stdout)}

    def test_dispatch_table_and_registry_agree(self):
        dispatch = (REPO / "skills" / "diagnose" / "references" / "analyzer-dispatch.md").read_text(encoding="utf-8")
        named = set(re.findall(r"^\|\s*[^|]+\|\s*`([a-z0-9][a-z0-9_-]+)`\s*\|", dispatch, re.MULTILINE))
        registry = self._registry()
        self.assertTrue(named, "选择表里没有解析出任何分析器名")
        self.assertEqual(named - registry, set(), "选择表提到了不存在的分析器")
        self.assertEqual(registry - named, set(), "有分析器没进选择表，Agent 选不到它")

    def test_list_json_gives_inputs_and_purpose(self):
        proc = run_cli(["list", "--json"], enabled=False)
        items = {item["name"]: item for item in json.loads(proc.stdout)}
        self.assertIn("ibmc_analyzer", items)
        self.assertIn("dump_info", items["ibmc_analyzer"]["inputs"])
        self.assertTrue(items["ibmc_analyzer"]["purpose"])

    def test_status_reports_source_and_installed(self):
        proc = run_cli(["status", "--json"], enabled=False)
        payload = json.loads(proc.stdout)
        self.assertIn("source", payload)
        self.assertTrue(any(item["name"] == "ibmc_analyzer" and item["installed"] for item in payload["analyzers"]))



if __name__ == "__main__":
    unittest.main()
