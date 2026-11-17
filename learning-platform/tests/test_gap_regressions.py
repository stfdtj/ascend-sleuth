"""Synthetic regressions derived from production Trace contracts.

Sources inspected before fixture construction: trace_begin.build_header,
_trace_content.to_jsonable, _trace_state.derive, verify_evidence, public
examples, tests/test_trace_content.py and diagnosis-trace.md. No customer data.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sleuth_learning import storage, render
from sleuth_learning.collector.discovery import read_candidate
from sleuth_learning.collector.snapshot import plan_sources, capture_stable
from sleuth_learning.collector.package import project_and_seal
from sleuth_learning.errors import SchemaError
from sleuth_learning.extraction import trace_adapter, evidence_linker, validation
from sleuth_learning.generation.assemble import assemble_case
from sleuth_learning.generation.replay import generate_replay_view
from sleuth_learning.hashing import content_hash
from sleuth_learning.model import LearningCase, Link

# role/content/output/reason and quotes match diagnosis-trace.md. Dates are
# deliberately unquoted, as supported by _trace_content.to_jsonable.
TRACE = '''session_id: synthetic-shared
status: resolved
created_at: 2026-11-10T10:00:00+08:00
side: training
side_source: user
active_case: synthetic-only
trace:
  - role: user
    step: 1
    content: node-a rank0 and node-b rank7 observations
    evidence:
      files: [rank0.log, rank7.log, missing.log, huge.log, /private/secret.log]
      quotes:
        - {file: rank7.log, line: 1, quote: 'rank7 timeout <script>alert(1)</script>'}
  - role: agent
    step: 2
    action: source_analysis
    output: Inspect the recorded rank7 timeout
    reason: The user supplied a rank7 timeout; other causes remain unknown.
    tool_calls: ['grep -n timeout rank7.log']
  - role: agent
    action: future_action
    output: Unknown action preserved
  - null
'''

class GapRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.trace = self.root / 'case.yaml'
        self.trace.write_text(TRACE, encoding='utf-8')
        (self.root / 'rank0.log').write_text('rank0 ready\n', encoding='utf-8')
        (self.root / 'rank7.log').write_text('rank7 timeout <script>alert(1)</script>\n', encoding='utf-8')
        with (self.root / 'huge.log').open('wb') as f:
            f.truncate(10 * 1024 * 1024 + 1)

    def collect(self, name='p', origin=None, lineage=None):
        doc = read_candidate(self.trace)
        plan = plan_sources(doc, self.trace, self.root)
        captured = capture_stable(plan, self.root / 'stage', settle_seconds=0)
        package = self.root / name
        manifest = project_and_seal(captured, plan, package,
            session_id=str(doc.get('session_id') or ''), origin_id=origin, lineage_id=lineage)
        return package, manifest

    def pipeline(self, package, manifest):
        storage.ingest_package(package, self.root / 'store')
        extracted = trace_adapter.extract(package, manifest)
        evidence_linker.link_evidence(extracted)
        evidence_linker.verify_quotes(extracted, package, manifest)
        case = assemble_case(extracted, manifest, 'replay', [generate_replay_view(extracted)])
        findings = validation.validate_artifact(case, package_dir=package, manifest=manifest,
            source_event_count=extracted.source_event_count)
        self.assertFalse(validation.has_blocking_errors(findings), findings)
        result = storage.save_case_revision(self.root / 'store', case, findings,
            manifest=manifest, key=storage.job_key(manifest['snapshot_hash'], 'replay', '2', None, None))
        return case, result

    def test_identity_and_revisions_end_to_end(self):
        p, m = self.collect()
        case, first = self.pipeline(p, m)
        p2, m2 = self.collect('p2')
        _, repeated = self.pipeline(p2, m2)
        self.assertEqual(m['snapshot_hash'], m2['snapshot_hash'])
        self.assertTrue(repeated['duplicate'])
        self.trace.write_text(TRACE + 'summary: updated\n', encoding='utf-8')
        p3, m3 = self.collect('p3')
        changed, result = self.pipeline(p3, m3)
        self.assertEqual(case.id, changed.id)
        self.assertEqual(result['revision'], 2)
        self.assertNotEqual(m['snapshot_hash'], m3['snapshot_hash'])
        _, independent = self.collect('p4', origin='independent')
        self.assertNotEqual(case.id, storage.case_id_for_source(independent))

    def test_missing_session_ids_are_stable_and_distinct(self):
        self.trace.write_text(TRACE.replace('session_id: synthetic-shared\n', ''), encoding='utf-8')
        _, a = self.collect()
        _, repeated = self.collect('p2')
        self.assertEqual(storage.case_id_for_source(a), storage.case_id_for_source(repeated))
        other = self.root / 'other.yaml'
        other.write_text(self.trace.read_text(encoding='utf-8'), encoding='utf-8')
        self.trace = other
        _, b = self.collect('p3')
        self.assertNotEqual(storage.case_id_for_source(a), storage.case_id_for_source(b))

    def test_separate_process_determinism(self):
        manifests = []
        for name in ('one', 'two'):
            proc = subprocess.run([sys.executable, '-m', 'sleuth_learning.cli', 'prepare',
                '--trace', str(self.trace), '--allow-root', str(self.root), '--out', str(self.root / name),
                '--settle-seconds', '0', '--json'], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            manifests.append(json.loads(proc.stdout))
        self.assertEqual(manifests[0]['snapshot_hash'], manifests[1]['snapshot_hash'])

    def test_provenance_commands_missing_and_oversized(self):
        p, m = self.collect()
        case, _ = self.pipeline(p, m)
        self.assertEqual(len(case.steps), 4)
        self.assertEqual(case.steps[1].commands[0].text, 'grep -n timeout rank7.log')
        self.assertEqual(case.steps[1].commands[0].execution, 'recorded-tool-call')
        self.assertEqual(case.steps[1].evidence_links, [])
        self.assertEqual(case.steps[1].commands[0].output_evidence_ids, [])
        quote = next(e for e in case.evidence if 'quote' in e.id)
        self.assertEqual(quote.integrity, 'quote-matched')
        self.assertEqual(quote.lineage['source_ref'], 'rank7.log')
        self.assertEqual(quote.lineage['trace_pointer'], '/trace/0/evidence/quotes/0')
        states = {e.lineage.get('availability') for e in case.evidence}
        self.assertTrue({'available', 'missing', 'omitted', 'inaccessible'} <= states)
        self.assertEqual(case.applicability.assessment, 'unknown')
        self.assertEqual(case.source_context['side'], 'training')
        self.assertIsNone(case.steps[2].reason)

    def test_reader_encoding_and_template_tokens(self):
        p, m = self.collect()
        case, _ = self.pipeline(p, m)
        case.title = '<!--<script></script><img src=x>__HEAD_JSON__'
        html = render.render_html(case, {})
        self.assertNotIn('<img src=x>', html)
        embedded = html.split('<script id="case-data" type="application/json">')[1].split('</script>')[0]
        self.assertEqual(json.loads(embedded)['title'], case.title)
        self.assertNotIn('/private/secret.log', html)
        self.assertIn('No command recorded.', html)
        self.assertIn('evidenceRow(evidence)', html)
        self.assertIn('recorded-tool-call', html)

    def test_no_commands_and_malformed_events(self):
        self.trace.write_text('trace: [null, 3, {action: [odd], evidence: {files: 3, quotes: 3, sources: x}}]\n', encoding='utf-8')
        p, m = self.collect()
        case, _ = self.pipeline(p, m)
        self.assertEqual(len(case.steps), 3)
        self.assertTrue(all(not s.commands for s in case.steps))

    def test_quote_never_borrows_another_events_file(self):
        self.trace.write_text('''session_id: quotes
trace:
- {role: user, evidence: {files: [rank0.log]}}
- {role: user, evidence: {quotes: [{file: rank0.log, line: 1, quote: rank0 ready}]}}
''', encoding='utf-8')
        p, m = self.collect()
        case, _ = self.pipeline(p, m)
        self.assertIsNone(case.evidence[-1].file_id)
        self.assertEqual(case.evidence[-1].integrity, 'unavailable')

    def test_legacy_package_and_case_remain_readable(self):
        p, m = self.collect()
        m['content']['projection_policy'] = 'selected-evidence-v1'
        for f in m['content']['files']:
            f.pop('source_ref', None)
        m['snapshot_hash'] = content_hash(m['content'])
        (p / 'manifest.json').write_text(json.dumps(m), encoding='utf-8')
        case, _ = self.pipeline(p, m)
        self.assertEqual(case.id, storage.case_id_for_session('synthetic-shared'))
        old = case.to_dict()
        old.pop('source_context')
        self.assertEqual(LearningCase.from_dict(old).source_context, {})
        self.assertEqual(case.evidence[-1].integrity, 'quote-matched')

    def test_manifest_tampering_and_blob_traversal_rejected(self):
        p, m = self.collect()
        for bad in ('sha256:../../outside', 'sha256:' + '0' * 64):
            altered = copy.deepcopy(m)
            altered['content']['files'][0]['blob_hash'] = bad
            (p / 'manifest.json').write_text(json.dumps(altered), encoding='utf-8')
            with self.assertRaises(SchemaError):
                storage.ingest_package(p, self.root / 'store')

    def test_validator_rejects_dangling_evidence_link(self):
        p, m = self.collect()
        case, _ = self.pipeline(p, m)
        case.steps[0].evidence_links.append(Link('absent', 'explicit'))
        findings = validation.validate_artifact(case, package_dir=p, manifest=m, source_event_count=4)
        self.assertTrue(validation.has_blocking_errors(findings))

    def test_malformed_yaml_cli_returns_error(self):
        self.trace.write_text('!!python/object:bad {}', encoding='utf-8')
        proc = subprocess.run([sys.executable, '-m', 'sleuth_learning.cli', 'prepare', '--trace',
            str(self.trace), '--allow-root', str(self.root), '--dry-run', '--json'],
            capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn('Traceback', proc.stderr)

    def test_explicit_origin_and_lineage_survive_relocation(self):
        _, a = self.collect('p', origin='source-a', lineage='case-a')
        other = self.root / 'moved.yaml'
        other.write_text(self.trace.read_text(encoding='utf-8'), encoding='utf-8')
        self.trace = other
        _, b = self.collect('p2', origin='source-a', lineage='case-a')
        self.assertEqual(a['snapshot_hash'], b['snapshot_hash'])

    def test_out_of_order_recorded_times_are_not_sorted_or_linked(self):
        self.trace.write_text("trace: [{role: user, at: '2026-11-10T12:00:00Z', rank: 7, node: b}, {role: agent, at: '2026-11-10T11:00:00Z', rank: 0, node: a}]\n", encoding='utf-8')
        p, m = self.collect()
        case, _ = self.pipeline(p, m)
        self.assertEqual([s.recorded_context['rank'] for s in case.steps], [7, 0])
        self.assertTrue(all(s.known_at is None and s.observed_at is None for s in case.steps))
        self.assertTrue(all(not s.evidence_links for s in case.steps))

    def test_production_header_writer_and_historical_aliases(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
        from trace_begin import build_header
        header = build_header(slug='2026-11-16-synthetic', harness_session='',
            created_at='2026-11-16T10:00:00+08:00', kb_rev='synthetic')
        self.trace.write_text(header, encoding='utf-8')
        p, m = self.collect()
        case, _ = self.pipeline(p, m)
        self.assertEqual(case.diagnosis.teaching_class, 'incomplete')
        self.assertEqual(case.steps, [])
        self.assertIn('workload_type', case.source_context)
        self.assertNotIn('side', case.source_context)

    def test_scalar_file_reference_and_incomplete_quote(self):
        self.trace.write_text("trace: [{role: user, evidence: {files: rank0.log}}, {role: user, evidence: {files: 3, quotes: [{file: rank0.log}]}}]\n", encoding='utf-8')
        p, m = self.collect()
        case, _ = self.pipeline(p, m)
        self.assertEqual(case.evidence[0].lineage['trace_pointer'], '/trace/0/evidence/files')
        self.assertEqual(case.evidence[1].integrity, 'unavailable')

    def test_modern_timeline_coverage_limit_is_visible(self):
        self.trace.write_text(TRACE + "incident_timeline: [{id: inc-1, at: '2026-11-10', what: synthetic outage, source: user}]\n", encoding='utf-8')
        p, m = self.collect()
        case, _ = self.pipeline(p, m)
        self.assertEqual(case.source_context['not_projected'], ['/incident_timeline'])
        self.assertIn('Files referenced only there were not collected.', render.render_html(case, {}))
