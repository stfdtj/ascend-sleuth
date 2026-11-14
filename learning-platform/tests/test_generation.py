import tempfile
import unittest
from pathlib import Path

from sleuth_learning.cli import _build_views
from sleuth_learning.extraction import evidence_linker, trace_adapter
from sleuth_learning.generation.providers import MockModelProvider, SYNTHETIC_PREFIX

from helpers import prepare_and_ingest


def _extracted(trace_name, tmp_root):
    ctx = prepare_and_ingest(trace_name, tmp_root)
    extracted = trace_adapter.extract(ctx["package_dir"], ctx["manifest"])
    evidence_linker.link_evidence(extracted)
    return extracted, ctx


class ReplayBaselineTests(unittest.TestCase):
    def test_replay_works_with_no_model_and_is_always_included(self):
        with tempfile.TemporaryDirectory() as td:
            extracted, _ = _extracted("complete", Path(td))
            views, mode, provider = _build_views(extracted, "replay", "none")
            self.assertEqual(mode, "replay")
            self.assertIsNone(provider)
            self.assertEqual(len(views), 1)
            self.assertEqual(views[0].style, "replay")
            self.assertEqual(views[0].state, "available")


class ModelDowngradeTests(unittest.TestCase):
    def test_agent_mode_without_model_downgrades_to_replay_and_marks_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            extracted, _ = _extracted("complete", Path(td))
            views, mode, provider = _build_views(extracted, "agent", "none")
            self.assertEqual(mode, "replay")  # never silently claims "agent"
            self.assertIsNone(provider)
            agent_view = next(v for v in views if v.style == "agent")
            self.assertEqual(agent_view.state, "unavailable")
            self.assertIn("no model", agent_view.reason)

    def test_agent_mode_with_mock_is_recorded_as_mock_not_agent(self):
        with tempfile.TemporaryDirectory() as td:
            extracted, _ = _extracted("complete", Path(td))
            views, mode, provider = _build_views(extracted, "agent", "mock")
            self.assertEqual(mode, "mock")  # honest: never claims a real agent-model generation
            self.assertIsNotNone(provider)
            agent_view = next(v for v in views if v.style == "agent")
            self.assertEqual(agent_view.state, "available")
            explained = [c for c in agent_view.cards if c.explanation]
            self.assertTrue(all(c.explanation.startswith(SYNTHETIC_PREFIX) for c in explained))

    def test_mock_mode_produces_both_agent_and_engineer_views(self):
        with tempfile.TemporaryDirectory() as td:
            extracted, _ = _extracted("complete", Path(td))
            views, mode, provider = _build_views(extracted, "mock", "none")
            self.assertEqual(mode, "mock")
            styles = {v.style for v in views}
            self.assertEqual(styles, {"replay", "agent", "engineer"})


class MockProviderGroundingTests(unittest.TestCase):
    def test_mock_never_invents_citations_beyond_what_it_was_given(self):
        provider = MockModelProvider()
        result = provider.generate({"style": "agent", "step": {"id": "s-0", "role": "agent",
                                                                "action": "hit", "reason": "x"},
                                    "allowed_citation_pointers": []})
        self.assertEqual(result["cards"][0]["citations"], [])

    def test_mock_echoes_only_recorded_reason_text(self):
        provider = MockModelProvider()
        result = provider.generate({
            "style": "agent",
            "step": {"id": "s-5", "role": "agent", "action": "hit",
                    "reason": "log timeout signature plus platform compatibility"},
            "allowed_citation_pointers": [],
        })
        card = result["cards"][0]
        self.assertIn("log timeout signature plus platform compatibility", card["explanation"])
        self.assertTrue(card["explanation"].startswith(SYNTHETIC_PREFIX))


if __name__ == "__main__":
    unittest.main()
