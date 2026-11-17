"""Local agent handoff tests use only repository-shaped synthetic Traces."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from helpers import prepare_and_ingest
from sleuth_learning import cli, storage
from sleuth_learning.errors import SchemaError, AuthorizationError
from sleuth_learning.extraction import trace_adapter, evidence_linker
from sleuth_learning.generation import handoff


class TeachingHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ctx = prepare_and_ingest('complete', self.root)
        self.extracted = trace_adapter.extract(self.ctx['package_dir'], self.ctx['manifest'])
        evidence_linker.link_evidence(self.extracted)
        evidence_linker.verify_quotes(self.extracted, self.ctx['package_dir'], self.ctx['manifest'])
        self.bundle = handoff.build_requests(self.extracted, self.ctx['manifest'])
        example = Path(__file__).resolve().parents[1] / 'examples/agent-teaching-response.json'
        self.response = json.loads(example.read_text(encoding='utf-8'))
        # The same synthetic source can be collected under a different origin.
        self.response.update(snapshot_hash=self.bundle['snapshot_hash'], request_hash=self.bundle['request_hash'])
        self.path = self.root / 'teaching.json'

    def write_response(self):
        self.path.write_text(json.dumps(self.response), encoding='utf-8')
        return self.path

    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = cli.main(list(args))
        self.assertEqual(result, 0, out.getvalue())
        return json.loads(out.getvalue())

    def test_requests_exclude_later_steps_summary_and_outcome(self):
        first = self.bundle['requests'][0]
        self.assertEqual(first['prior'], [])
        self.assertNotIn('summary', first)
        self.assertNotIn('diagnosis', first)
        self.assertNotIn('HCCL_BUFFSIZE', json.dumps(first))
        self.assertFalse(any('/trace/7/' in (p.get('json_pointer') or '') for p in first['allowed_citations']))
        self.assertIn('HCCL_BUFFSIZE', json.dumps(self.bundle['requests'][-1]['current']))

    def test_trial_has_distinct_views_and_keeps_source_immutable(self):
        before = [s.to_dict() for s in self.extracted.steps]
        views, author, digest = handoff.import_teaching(self.write_response(), self.bundle)
        self.assertEqual([len(v.cards) for v in views], [8, 8])
        self.assertTrue(all(a.explanation != e.explanation for a, e in zip(views[0].cards, views[1].cards)))
        self.assertTrue(all(c.origin == 'reconstructed' for v in views for c in v.cards))
        self.assertEqual(before, [s.to_dict() for s in self.extracted.steps])

    def test_rejects_stale_response_and_future_or_invalid_citations(self):
        original = copy.deepcopy(self.response)
        for edit in ('hash', 'future', 'nonexistent', 'empty'):
            self.response = copy.deepcopy(original)
            if edit == 'hash':
                self.response['request_hash'] = 'wrong'
            elif edit == 'empty':
                self.response['cards'][0]['citations'] = []
            else:
                self.response['cards'][0]['citations'] = [{
                    'file_id': 'trace', 'json_pointer': '/trace/7/content' if edit == 'future' else '/trace/0/not-real', 'lines': None}]
            with self.subTest(edit=edit), self.assertRaises(SchemaError):
                handoff.import_teaching(self.write_response(), self.bundle)

    def test_rejects_source_fields_duplicate_cards_and_command_blocks(self):
        original = copy.deepcopy(self.response)
        for edit in ('source', 'duplicate', 'code', 'badtype'):
            self.response = copy.deepcopy(original)
            if edit == 'source':
                self.response['cards'][0]['commands'] = ['invented']
            elif edit == 'duplicate':
                self.response['cards'][1] = copy.deepcopy(self.response['cards'][0])
            elif edit == 'badtype':
                self.response['cards'][0]['style'] = []
            else:
                self.response['cards'][0]['explanation'] = '```sh\ninvented\n```'
            with self.subTest(edit=edit), self.assertRaises(SchemaError):
                handoff.import_teaching(self.write_response(), self.bundle)

    def test_budget_retains_source_steps_and_reports_omissions(self):
        before = len(self.extracted.steps)
        self.extracted.steps[0].output = 'x' * 20000
        bundle = handoff.build_requests(self.extracted, self.ctx['manifest'])
        self.assertEqual(bundle['requests'], [])
        self.assertEqual(len(bundle['omitted']), before)
        self.assertEqual(len(self.extracted.steps), before)

    def test_export_does_not_overwrite_existing_response_template(self):
        out = self.root / 'requests'
        handoff.export_requests(self.bundle, out)
        template = out / 'response-template.json'
        template.write_text('keep my work', encoding='utf-8')
        handoff.export_requests(self.bundle, out)
        self.assertEqual(template.read_text(encoding='utf-8'), 'keep my work')

    def test_cli_handoff_dedup_and_teaching_edit_creates_revision(self):
        base = ['--data-dir', str(self.ctx['data_dir']), '--snapshot', self.ctx['snapshot_id']]
        exported = self.run_cli('teaching-request', *base, '--out', str(self.root / 'requests'), '--json')
        self.assertEqual(exported['requests'], 8)
        args = ['generate', *base, '--mode', 'agent', '--teaching-file', str(self.write_response()), '--json']
        first = self.run_cli(*args)
        repeated = self.run_cli(*args)
        self.assertTrue(repeated['duplicate'])
        self.assertEqual(first['effective_mode'], 'agent')
        self.assertEqual(len(first['findings']), 16)
        self.assertTrue(all(f['code'] == 'teaching-review' for f in first['findings']))
        case = storage.get_case(self.ctx['data_dir'], first['case_id'])
        self.assertEqual(len(case.views), 3)
        self.assertEqual(case.generator.dependency_hashes[0], self.bundle['request_hash'])
        self.response['cards'][0]['question'] = 'What observation would narrow this symptom?'
        self.write_response()
        changed = self.run_cli(*args)
        self.assertEqual(changed['revision'], 2)
        self.assertFalse(changed['duplicate'])
        reader = self.root / 'reader.html'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['render', '--data-dir', str(self.ctx['data_dir']), '--case', first['case_id'], '--out', str(reader)]), 0)
        self.assertIn('Agent-authored reconstruction', reader.read_text(encoding='utf-8'))

    def test_partial_response_marks_other_perspective_unavailable(self):
        self.response['cards'] = self.response['cards'][:1]
        views, _, _ = handoff.import_teaching(self.write_response(), self.bundle)
        self.assertEqual(views[0].state, 'available')
        self.assertEqual(views[1].state, 'unavailable')

    def test_changed_export_refuses_stale_directory_before_writing(self):
        out = self.root / 'requests'
        handoff.export_requests(self.bundle, out)
        before = {p.name: p.read_bytes() for p in out.iterdir()}
        self.extracted.steps = self.extracted.steps[:1]
        changed = handoff.build_requests(self.extracted, self.ctx['manifest'])
        with self.assertRaises(SchemaError):
            handoff.export_requests(changed, out)
        self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})
        handoff.export_requests(changed, self.root / 'fresh')
        self.assertFalse((self.root / 'fresh' / 's-7.json').exists())

    def test_publication_uses_selected_revisions_synthetic_status(self):
        real = prepare_and_ingest('complete', self.root, synthetic=False)
        first = self.run_cli('generate', '--data-dir', str(real['data_dir']), '--snapshot', real['snapshot_id'], '--mode', 'replay', '--json')
        second = self.run_cli('generate', '--data-dir', str(self.ctx['data_dir']), '--snapshot', self.ctx['snapshot_id'], '--mode', 'replay', '--json')
        self.assertEqual(first['case_id'], second['case_id'])
        with self.assertRaises(AuthorizationError):
            storage.publish(real['data_dir'], first['case_id'], first['revision'], authorized=True)
        storage.publish(real['data_dir'], first['case_id'], second['revision'], authorized=True)
        old = storage.get_case(real['data_dir'], first['case_id'], first['revision'])
        self.assertFalse(storage.case_is_synthetic(real['data_dir'], old))
