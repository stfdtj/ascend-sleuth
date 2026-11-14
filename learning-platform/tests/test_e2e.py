"""The acceptance test: a synthetic trace goes through the whole pipeline --
collect -> import -> generate (deterministic, Mode C, no LLM/model) ->
validate -> store -> open in the reader -- entirely through the CLI, with no
company access, no network, and no real model. This must pass with nothing
more than `pip install -e ./learning-platform` done first.
"""

import tempfile
import unittest
from pathlib import Path

from sleuth_learning import storage
from sleuth_learning.cli import main as cli_main


class AcceptanceTests(unittest.TestCase):
    def test_full_pipeline_cli_end_to_end_no_model(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "demo"
            self.assertEqual(cli_main(["demo-init", "--out", str(root)]), 0)
            self.assertTrue((root / "traces" / "complete.yaml").is_file())

            package_dir = root / "packages" / "complete"
            rc = cli_main(["prepare", "--trace", str(root / "traces" / "complete.yaml"),
                          "--allow-root", str(root), "--out", str(package_dir)])
            self.assertEqual(rc, 0)
            self.assertTrue((package_dir / "manifest.json").is_file())

            self.assertEqual(cli_main(["inspect", "--package", str(package_dir)]), 0)

            data_dir = root / "data"
            self.assertEqual(cli_main(["ingest", "--package", str(package_dir),
                                       "--data-dir", str(data_dir)]), 0)
            snaps = storage.list_snapshots(data_dir)
            self.assertEqual(len(snaps), 1)
            snapshot_id = snaps[0]["snapshot_id"]

            # Mode C: deterministic replay, no model, no LLM involved at all.
            rc = cli_main(["generate", "--data-dir", str(data_dir), "--snapshot", snapshot_id,
                          "--mode", "replay"])
            self.assertEqual(rc, 0)
            cases = storage.list_cases(data_dir)
            self.assertEqual(len(cases), 1)
            case_id = cases[0]["case_id"]
            self.assertEqual(cases[0]["generation_status"], "generated")

            self.assertEqual(cli_main(["validate", "--data-dir", str(data_dir),
                                       "--case", case_id]), 0)

            case = storage.get_case(data_dir, case_id)
            self.assertEqual(case.generator.mode, "replay")
            self.assertIsNone(case.generator.model_id)
            self.assertEqual(len(case.steps), 8)  # complete.yaml has 8 trace[] events
            self.assertEqual(case.diagnosis.teaching_class, "success-reported")

            out_html = root / "reader.html"
            rc = cli_main(["render", "--data-dir", str(data_dir), "--case", case_id,
                          "--out", str(out_html)])
            self.assertEqual(rc, 0)
            html = out_html.read_text(encoding="utf-8")
            self.assertIn("case-data", html)
            self.assertIn("HCCL", html)
            # the embedded JSON must not let a literal </script> break out of its tag
            self.assertNotIn("</script>\n", html.split('id="case-data"')[1].split("</script>")[0])

    def test_demo_run_one_shot_command(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "demo"
            self.assertEqual(cli_main(["demo-init", "--out", str(root)]), 0)
            rc = cli_main(["demo-run", "--root", str(root)])
            self.assertEqual(rc, 0)
            self.assertTrue((root / "demo-case.html").is_file())
            cases = storage.list_cases(root / "data")
            self.assertEqual(cases[0]["publication_status"], "published")


if __name__ == "__main__":
    unittest.main()
