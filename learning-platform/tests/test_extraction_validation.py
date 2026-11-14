import tempfile
import unittest
from pathlib import Path

from sleuth_learning.extraction import evidence_linker, trace_adapter
from sleuth_learning.extraction import validation as validation_mod
from sleuth_learning.generation import assemble as assemble_mod
from sleuth_learning.generation import replay as replay_mod

from helpers import prepare_and_ingest


def _extract(trace_name, tmp_root, platform_registry=None):
    ctx = prepare_and_ingest(trace_name, tmp_root)
    extracted = trace_adapter.extract(ctx["package_dir"], ctx["manifest"],
                                      platform_registry=platform_registry)
    evidence_linker.link_evidence(extracted)
    evidence_linker.verify_quotes(extracted, ctx["package_dir"], ctx["manifest"])
    return extracted, ctx


class TraceAdapterTests(unittest.TestCase):
    def test_complete_trace_full_coverage_and_quote_matched(self):
        with tempfile.TemporaryDirectory() as td:
            extracted, ctx = _extract("complete", Path(td))
            self.assertEqual(len(extracted.steps), extracted.source_event_count)
            indices = sorted(s.source_index for s in extracted.steps)
            self.assertEqual(indices, list(range(extracted.source_event_count)))
            self.assertEqual(extracted.diagnosis.teaching_class, "success-reported")

            quote_ev = [e for e in extracted.evidence if e.id == "e-0-quote-0"]
            self.assertEqual(len(quote_ev), 1)
            self.assertEqual(quote_ev[0].integrity, "quote-matched")

    def test_missing_evidence_recorded_on_step(self):
        with tempfile.TemporaryDirectory() as td:
            extracted, _ = _extract("missing_evidence", Path(td))
            step0 = extracted.steps[0]
            self.assertTrue(any("CANN" in m for m in step0.missing))

    def test_incomplete_trace_teaching_class(self):
        with tempfile.TemporaryDirectory() as td:
            extracted, _ = _extract("incomplete", Path(td))
            self.assertEqual(extracted.diagnosis.teaching_class, "incomplete")

    def test_invalid_evidence_ref_marked_unavailable_not_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            extracted, _ = _extract("invalid_evidence_ref", Path(td))
            # coverage must still include this step even though its evidence is unresolved
            step0 = extracted.steps[0]
            self.assertEqual(step0.source_index, 0)
            file_evs = [e for e in extracted.evidence if e.id.startswith("e-0-file-")]
            self.assertTrue(all(e.file_id is None and e.integrity == "unavailable" for e in file_evs))
            self.assertTrue(len(step0.missing) >= 1)

    def test_failed_diagnosis_teaching_class(self):
        with tempfile.TemporaryDirectory() as td:
            extracted, _ = _extract("failed_diagnosis", Path(td))
            self.assertEqual(extracted.diagnosis.teaching_class, "failure")

    def test_conflicting_reference_requires_review_finding(self):
        registry = {"MSLLM-EP-HANG-001": ["A5-950"]}
        with tempfile.TemporaryDirectory() as td:
            extracted, ctx = _extract("conflicting_reference", Path(td), platform_registry=registry)
            self.assertEqual(extracted.applicability.assessment, "conflicting")

            view = replay_mod.generate_replay_view(extracted)
            case = assemble_mod.assemble_case(extracted, ctx["manifest"], "replay", [view])
            findings = validation_mod.validate_artifact(
                case, package_dir=ctx["package_dir"], manifest=ctx["manifest"],
                source_event_count=extracted.source_event_count)
            review = [f for f in findings if f.code == "applicability"]
            self.assertEqual(len(review), 1)
            self.assertEqual(review[0].severity, "review")
            # a review finding must not block -- only error severity blocks publish
            self.assertFalse(validation_mod.has_blocking_errors(review))


class ValidationTests(unittest.TestCase):
    def test_complete_case_has_no_blocking_errors(self):
        with tempfile.TemporaryDirectory() as td:
            extracted, ctx = _extract("complete", Path(td))
            view = replay_mod.generate_replay_view(extracted)
            case = assemble_mod.assemble_case(extracted, ctx["manifest"], "replay", [view])
            findings = validation_mod.validate_artifact(
                case, package_dir=ctx["package_dir"], manifest=ctx["manifest"],
                source_event_count=extracted.source_event_count)
            self.assertFalse(validation_mod.has_blocking_errors(findings))

    def test_mismatched_quote_is_a_blocking_finding(self):
        with tempfile.TemporaryDirectory() as td:
            extracted, ctx = _extract("complete", Path(td))
            # corrupt one evidence record's quote after the fact
            ev = next(e for e in extracted.evidence if e.id == "e-0-quote-0")
            ev.integrity = "mismatch"
            view = replay_mod.generate_replay_view(extracted)
            case = assemble_mod.assemble_case(extracted, ctx["manifest"], "replay", [view])
            findings = validation_mod.validate_artifact(
                case, package_dir=ctx["package_dir"], manifest=ctx["manifest"],
                source_event_count=extracted.source_event_count)
            self.assertTrue(validation_mod.has_blocking_errors(findings))
            self.assertTrue(any(f.code == "quote" for f in findings))

    def test_coverage_catches_a_dropped_step(self):
        with tempfile.TemporaryDirectory() as td:
            extracted, ctx = _extract("complete", Path(td))
            extracted.steps.pop(0)
            view = replay_mod.generate_replay_view(extracted)
            case = assemble_mod.assemble_case(extracted, ctx["manifest"], "replay", [view])
            findings = validation_mod.validate_artifact(
                case, package_dir=ctx["package_dir"], manifest=ctx["manifest"],
                source_event_count=extracted.source_event_count)
            self.assertTrue(any(f.code == "coverage" for f in findings))
            self.assertTrue(validation_mod.has_blocking_errors(findings))


if __name__ == "__main__":
    unittest.main()
