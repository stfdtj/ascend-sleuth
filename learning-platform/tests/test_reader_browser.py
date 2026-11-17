"""Optional browser integration: pip install playwright; installed Edge required."""
import importlib.util
from pathlib import Path
import unittest
import test_gap_regressions
from sleuth_learning.render import render_html

@unittest.skipUnless(importlib.util.find_spec('playwright'), 'install playwright for browser tests')
class ReaderBrowserTests(unittest.TestCase):
    def test_recorded_process_in_real_browser(self):
        from playwright.sync_api import sync_playwright
        fixture = test_gap_regressions.GapRegressionTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        package, manifest = fixture.collect()
        case, _ = fixture.pipeline(package, manifest)
        html = fixture.root / 'reader.html'
        html.write_text(render_html(case, {'synthetic': True}), encoding='utf-8')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(html.as_uri())
            steps = page.locator('.view-pane.active .step')
            self.assertEqual(steps.count(), 4)
            self.assertIn('grep -n timeout rank7.log', steps.nth(1).inner_text())
            self.assertEqual(steps.nth(1).locator('.evidence').count(), 0)
            self.assertIn('rank7.log', steps.nth(0).inner_text())
            self.assertIn('line 1', steps.nth(0).inner_text())
            self.assertIn('too-large', steps.nth(0).inner_text())
            self.assertIn('No command recorded.', steps.nth(2).inner_text())
            self.assertIn('Diagnostic reasoning not recorded.', steps.nth(2).inner_text())
            self.assertIn('<script>alert(1)</script>', steps.nth(0).inner_text())
            self.assertEqual(page.locator('img').count(), 0)
            self.assertEqual(errors, [])
            browser.close()

    def test_agent_trial_tabs_show_different_teaching(self):
        from playwright.sync_api import sync_playwright
        example = Path(__file__).resolve().parents[1] / 'examples/agent-reader.html'
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            try:
                page = browser.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(example.as_uri())
                tabs = page.locator('.tab')
                self.assertEqual(tabs.count(), 3)
                tabs.nth(1).click()
                agent_text = page.locator('.view-pane.active').inner_text()
                self.assertIn('Agent-authored reconstruction', agent_text)
                self.assertIn('Establish the observed failure', agent_text)
                self.assertEqual(page.locator('.view-pane.active .step').count(), 8)
                tabs.nth(2).click()
                engineer_text = page.locator('.view-pane.active').inner_text()
                self.assertIn('Separate an observation from a causal explanation', engineer_text)
                self.assertNotEqual(agent_text, engineer_text)
                self.assertEqual(page.locator('.view-pane.active .step').count(), 8)
                self.assertEqual(errors, [])
            finally:
                browser.close()
