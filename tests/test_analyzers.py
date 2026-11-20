#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内置分析器的端到端测试：开关、失败路径、合成输入到报告输出。

所有夹具在临时目录现造，不读主检出的 traces/ 或客户数据，不访问外网。
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "analyzers" / "cli.py"
BASE_ENV = {
    **os.environ,
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
}


def run_cli(args, enabled: bool = True, extra_env: dict | None = None, timeout: int = 300):
    env = dict(BASE_ENV)
    env["SLEUTH_ANALYZERS"] = "on" if enabled else "off"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
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
    def test_status_defaults_off(self):
        proc = run_cli(["status", "--json"], enabled=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["enabled"])
        names = {item["name"] for item in payload["analyzers"]}
        self.assertIn("ibmc_analyzer", names)
        self.assertNotIn("vllm-ascend-tuning", names)
        self.assertEqual(len(names), 7)

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
        adapter = REPO / "analyzers" / "ibmc_analyzer" / "run.py"
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

    def test_zip_slip_is_rejected(self):
        archive = self.tmp / "ibmc" / "evil.zip"
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../escape.txt", "escaped")
        out = self.out("ibmc-zip")
        proc = run_cli(["run", "ibmc_analyzer", "--inputs", json.dumps([str(archive)]), "--out-dir", str(out)])
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(list(self.tmp.rglob("escape.txt")), [], "越界条目不应被写出")


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

    def test_single_is_partial_when_versions_unknown(self):
        a, _ = self._fixture()
        out = self.out("dump-single")
        proc = run_cli(["run", "ascend-dump-analyzer", "--inputs", json.dumps([str(a)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertIn(result["status"], ("ok", "partial"))
        self.assertTrue((out / "compatibility.json").is_file())


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


class ClusterAnalysisTests(AnalyzerTestBase):
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
        generator = REPO / "analyzers" / "vendor" / "cpu-host-performance" / "examples" / "generate_synthetic.py"
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
        self.assertTrue(any("bind_cpu.sh" in item for item in result["artifacts"]))


class ProfCompareTests(AnalyzerTestBase):
    def _xlsx(self) -> Path:
        from openpyxl import Workbook

        path = self.tmp / "prof" / "compare.xlsx"
        path.parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        ws = wb.active
        ws.title = "OverallMetrics"
        ws.append(["Index", "Base Duration(ms)", "Base Ratio", "Base Number",
                   "Comparison Duration(ms)", "Comparison Ratio", "Comparison Number",
                   "Diff Duration(ms)", "Diff Ratio"])
        ws.append(["E2E Time", 1000, 1, 1, 1200, 1, 1, 200, 0.2])
        ws.append(["Computing Time", 600, 0.6, 1, 650, 0.54, 1, 50, 0.083])
        wb.save(path)
        return path

    @unittest.skipUnless(importlib.util.find_spec("openpyxl"), "未安装 openpyxl：跳过 xlsx 解析用例")
    def test_existing_xlsx(self):
        out = self.out("prof")
        proc = run_cli(["run", "prof-compare", "--inputs", json.dumps([str(self._xlsx())]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = read_result(out)
        self.assertIn(result["status"], ("ok", "partial"))
        self.assertTrue((out / "compare_analysis_report.html").is_file())

    def test_missing_xlsx_dependency_is_reported(self):
        if importlib.util.find_spec("openpyxl"):
            self.skipTest("本机已安装 openpyxl，缺依赖分支由 CI 缺依赖环境覆盖")
        path = self.tmp / "prof" / "dummy.xlsx"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not an xlsx")
        out = self.out("prof-missing")
        proc = run_cli(["run", "prof-compare", "--inputs", json.dumps([str(path)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 1)
        result = read_result(out)
        self.assertEqual(result["reason"], "dependency-missing")


class UnsupportedInputTests(AnalyzerTestBase):
    def test_cluster_compare_requires_two_dirs(self):
        one = self.tmp / "clusters" / "only" / "cluster_analysis_output"
        one.mkdir(parents=True, exist_ok=True)
        out = self.out("unsupported")
        proc = run_cli(["run", "cluster-compare", "--inputs", json.dumps([str(one.parent)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(read_result(out)["reason"], "bad-input")

    def test_prof_compare_rejects_single_dir(self):
        one = self.tmp / "prof-dir"
        one.mkdir(parents=True, exist_ok=True)
        out = self.out("prof-single-dir")
        proc = run_cli(["run", "prof-compare", "--inputs", json.dumps([str(one)]), "--out-dir", str(out)])
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(read_result(out)["reason"], "bad-input")


class PluginRemovalTests(AnalyzerTestBase):
    def test_plugin_package_is_gone(self):
        self.assertFalse((REPO / "dsh-plugins" / "dsh-sleuth-analyzers").exists())

    def test_diagnose_uses_builtin_cli(self):
        skill = (REPO / "skills" / "diagnose" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("sleuth_analyze", skill)
        dispatch = (REPO / "skills" / "diagnose" / "references" / "analyzer-dispatch.md").read_text(encoding="utf-8")
        self.assertIn("analyzers/cli.py", dispatch)
        self.assertIn("SLEUTH_ANALYZERS", dispatch)


if __name__ == "__main__":
    unittest.main()
