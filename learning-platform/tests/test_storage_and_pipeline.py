import tempfile
import unittest
from pathlib import Path

from sleuth_learning import storage
from sleuth_learning.errors import AuthorizationError, NotFoundError, ValidationBlockedError
from sleuth_learning.extraction import evidence_linker, trace_adapter
from sleuth_learning.extraction import validation as validation_mod
from sleuth_learning.fixtures import fixtures_root
from sleuth_learning.generation import assemble as assemble_mod
from sleuth_learning.generation import replay as replay_mod

from helpers import prepare_and_ingest, prepare_and_ingest_from_path


def _generate(ctx, mode="replay"):
    extracted = trace_adapter.extract(ctx["package_dir"], ctx["manifest"])
    evidence_linker.link_evidence(extracted)
    evidence_linker.verify_quotes(extracted, ctx["package_dir"], ctx["manifest"])
    view = replay_mod.generate_replay_view(extracted)
    case_id = storage.case_id_for_session(extracted.session_id)
    case = assemble_mod.assemble_case(extracted, ctx["manifest"], mode, [view], case_id=case_id)
    findings = validation_mod.validate_artifact(
        case, package_dir=ctx["package_dir"], manifest=ctx["manifest"],
        source_event_count=extracted.source_event_count)
    key = storage.job_key(ctx["manifest"]["snapshot_hash"], mode, case.generator.version,
                          case.generator.model_id, case.generator.prompt_hash)
    result = storage.save_case_revision(ctx["data_dir"], case, findings, manifest=ctx["manifest"],
                                        key=key)
    return result, case, findings


class IdempotentIngestTests(unittest.TestCase):
    def test_duplicate_ingestion_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            ctx1 = prepare_and_ingest("complete", tmp)
            # re-ingest the exact same package directory a second time
            result2 = storage.ingest_package(ctx1["package_dir"], ctx1["data_dir"])
            self.assertTrue(result2["duplicate"])
            self.assertEqual(result2["snapshot_id"], ctx1["snapshot_id"])
            snaps = storage.list_snapshots(ctx1["data_dir"])
            self.assertEqual(len(snaps), 1)

    def test_duplicate_generation_job_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            ctx = prepare_and_ingest("complete", Path(td))
            r1, _, _ = _generate(ctx)
            r2, _, _ = _generate(ctx)
            self.assertTrue(r2["duplicate"])
            self.assertEqual(r1["revision"], r2["revision"])


class RegenerationTests(unittest.TestCase):
    def test_source_change_creates_new_revision_and_keeps_old_published(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = fixtures_root() / "sample_traces" / "complete.yaml"
            edited = tmp / "edited-source"
            edited.mkdir()
            text = src.read_text(encoding="utf-8").replace(
                "HCCL buffer undersize confirmed and fixed.",
                "HCCL buffer undersize confirmed and fixed (corrected write-up).")
            edited_trace = edited / "complete.yaml"
            edited_trace.write_text(text, encoding="utf-8")
            # evidence/ referenced by the trace is relative to the allow-root;
            # reuse the real fixtures root as allow-root for both ingests so the
            # referenced log file still resolves.
            root = fixtures_root()

            ctx_v1 = prepare_and_ingest_from_path(src, root, tmp, "v1")
            result_v1, case_v1, findings_v1 = _generate(ctx_v1)
            storage.publish(ctx_v1["data_dir"], result_v1["case_id"], result_v1["revision"],
                            authorized=True)

            ctx_v2 = prepare_and_ingest_from_path(edited_trace, root, tmp, "v2")
            self.assertEqual(ctx_v2["data_dir"], ctx_v1["data_dir"])  # same data dir, different snapshot
            self.assertNotEqual(ctx_v2["manifest"]["snapshot_hash"], ctx_v1["manifest"]["snapshot_hash"])
            result_v2, case_v2, _ = _generate(ctx_v2)

            self.assertEqual(result_v2["case_id"], result_v1["case_id"])  # same case (same session_id)
            self.assertEqual(result_v2["revision"], result_v1["revision"] + 1)

            head = storage.load_head(ctx_v1["data_dir"], result_v1["case_id"])
            self.assertEqual(head["published_revision"], result_v1["revision"])
            self.assertEqual(head["latest_revision"], result_v2["revision"])

            published = storage.get_published_case(ctx_v1["data_dir"], result_v1["case_id"])
            self.assertNotIn("corrected write-up", published.title + str(published.diagnosis.basis))


class PublicationAuthorizationTests(unittest.TestCase):
    def test_publish_without_authorization_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            ctx = prepare_and_ingest("complete", Path(td))
            result, _, _ = _generate(ctx)
            with self.assertRaises(AuthorizationError):
                storage.publish(ctx["data_dir"], result["case_id"], result["revision"],
                                authorized=False)

    def test_publish_blocked_by_error_findings(self):
        with tempfile.TemporaryDirectory() as td:
            ctx = prepare_and_ingest("complete", Path(td))
            extracted = trace_adapter.extract(ctx["package_dir"], ctx["manifest"])
            evidence_linker.link_evidence(extracted)
            extracted.steps.pop(0)  # break coverage on purpose
            view = replay_mod.generate_replay_view(extracted)
            case_id = storage.case_id_for_session(extracted.session_id)
            case = assemble_mod.assemble_case(extracted, ctx["manifest"], "replay", [view],
                                              case_id=case_id)
            findings = validation_mod.validate_artifact(
                case, package_dir=ctx["package_dir"], manifest=ctx["manifest"],
                source_event_count=extracted.source_event_count)
            self.assertTrue(validation_mod.has_blocking_errors(findings))
            key = storage.job_key(ctx["manifest"]["snapshot_hash"], "replay", "1", None, None)
            result = storage.save_case_revision(ctx["data_dir"], case, findings,
                                                manifest=ctx["manifest"], key=key)
            with self.assertRaises(ValidationBlockedError):
                storage.publish(ctx["data_dir"], result["case_id"], result["revision"],
                                authorized=True)

    def test_non_synthetic_publish_needs_an_extra_flag(self):
        with tempfile.TemporaryDirectory() as td:
            ctx = prepare_and_ingest("complete", Path(td), synthetic=False)
            result, _, _ = _generate(ctx)
            with self.assertRaises(AuthorizationError):
                storage.publish(ctx["data_dir"], result["case_id"], result["revision"],
                                authorized=True, allow_non_synthetic=False)
            head = storage.publish(ctx["data_dir"], result["case_id"], result["revision"],
                                   authorized=True, allow_non_synthetic=True)
            self.assertEqual(head["publication_status"], "published")


class WithdrawTests(unittest.TestCase):
    def test_withdraw_hides_published_content(self):
        with tempfile.TemporaryDirectory() as td:
            ctx = prepare_and_ingest("complete", Path(td))
            result, _, _ = _generate(ctx)
            storage.publish(ctx["data_dir"], result["case_id"], result["revision"], authorized=True)
            storage.get_published_case(ctx["data_dir"], result["case_id"])  # does not raise

            storage.withdraw(ctx["data_dir"], result["case_id"], reason="correction needed")
            with self.assertRaises(NotFoundError):
                storage.get_published_case(ctx["data_dir"], result["case_id"])


if __name__ == "__main__":
    unittest.main()
