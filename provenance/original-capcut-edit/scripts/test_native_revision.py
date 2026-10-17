"""Synthetic temporary-store regressions; never invoke a real native writer.

External process/application/guard success is mocked only for mutation mechanics.
The unmocked real guard refusal case proves that no stored/mock success is used
by production code. Fixture authority is simulated data, not a human approval.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch, DEFAULT
import wave

import native_timeline as n
import native_revision as r


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='capcut-owned-revision-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        source = self.root / 'synthetic-media.mp4'
        source.write_bytes(b'SYNTHETIC MEDIA HASH FIXTURE; NOT DECODED')
        self.plan = {'schema': n.SCHEMA,
            'project': {'name': 'Owned_EP 1', 'fps': 30,
                'canvas': {'width': 1080, 'height': 1920}},
            'sources': [{'id': 'main', 'path': str(source), 'sha256': n.sha256(source),
                'durationTicks': 20_000_000, 'width': 1080, 'height': 1920}],
            'mainPieces': [{'id': 'm1', 'sourceId': 'main', 'sourceInTicks': 1_000_000,
                'sourceOutTicks': 11_000_000, 'targetInTicks': 0}],
            'captions': [{'id': 'c1', 'text': 'cụm đầu tiên', 'rawWordIds': ['w1', 'w2', 'w3'],
                'startTicks': 0, 'endTicks': 5_000_000, 'style': {}},
                {'id': 'c2', 'text': 'cụm tiếp theo', 'rawWordIds': ['w4', 'w5', 'w6'],
                'startTicks': 5_000_000, 'endTicks': 10_000_000, 'style': {}}],
            'brollPolicy': 'NO_SOURCE_REPEAT', 'broll': []}
        initial = self.root / 'initial'
        self.initial = n.compile_plan(self.plan, initial)
        self.store = self.root / 'synthetic-store'
        self.target = self.store / self.plan['project']['name']
        shutil.copytree(initial / 'files', self.target)
        meta = n.read_json(self.target / 'draft_meta_info.json')
        meta.update(draft_fold_path=str(self.target).replace('\\', '/'),
            draft_root_path=str(self.store).replace('\\', '/'), opaqueUserMetadata={'keep': 97})
        self.old_meta = meta
        (self.target / 'draft_meta_info.json').write_bytes(n.json_bytes(meta))
        (self.target / 'unselected-extra.bin').write_bytes(b'PRESERVE TARGET EXTRA')
        foreign = self.store / 'Foreign project'
        foreign.mkdir()
        self.foreign = foreign / 'foreign.bin'
        self.foreign.write_bytes(b'FOREIGN PROJECT BYTES')
        row = {'draft_id': self.initial['projectId'], 'draft_name': self.initial['name'],
            'draft_fold_path': str(self.target).replace('\\', '/')}
        self.index = self.store / 'root_meta_info.json'
        self.index_bytes = (b'\xef\xbb\xbf{ "opaque":900719925474099312345, "decimal":1.234567890123456789,'
            b' "all_draft_store":[' + n.json_bytes(row).rstrip(b'\n') + b'], "tail":true}\n')
        self.index.write_bytes(self.index_bytes)
        self.baseline_ref = r.capture_baseline(self.store, self.initial['name'], self.root / 'baseline')
        self.baseline = n.read_json(self.baseline_ref['path'])
        self.before = {rel: (self.target / rel).read_bytes() for rel in self.baseline['expectedFiles']}
        revised = copy.deepcopy(self.plan)
        revised['project']['revisionIdentity'] = self.baseline_ref
        revised['captions'][0]['endTicks'] = 4_800_000
        revised['captions'][1]['startTicks'] = 4_800_000
        self.compiled = self.root / 'revision'
        self.manifest = n.compile_plan(revised, self.compiled)
        audio = self.root / 'synthetic-gain1.wav'
        with wave.open(str(audio), 'wb') as out:
            out.setparams((1, 2, 1000, 0, 'NONE', 'not compressed'))
            out.writeframes(b'\x00\x00' * 10_000)
        native = self.compiled / 'files/draft_content.json'
        self.authority_path = self.root / 'authority.json'
        self.authority = {'evidenceClass': 'REAL_OBSERVATION',
            'syntheticFixture': True, 'authority': 'explicit-user-request',
            'userQuote': 'SIMULATED UNIT AUTHORITY; NO HUMAN/PRODUCTION ACCEPTANCE',
            'taskId': 'synthetic-unit', 'claim': 'review-draft-native-update-owned',
            'mode': 'REVIEW_DRAFT', 'operation': r.OPERATION,
            'nativeHash': 'sha256:' + n.sha256(native), 'audioHash': 'sha256:' + n.sha256(audio),
            'destinationPath': str(self.target), 'name': self.initial['name'],
            'projectId': self.initial['projectId'], 'timelineId': self.initial['timelineId'],
            'rootIndexSHA256': self.baseline['rootIndexSHA256'],
            'expectedFiles': self.baseline['expectedFiles']}
        self.guard = {'schema': 'capcut-pre-native-apply/v1', 'mode': 'REVIEW_DRAFT',
            'branch': 'CONTENT_EDIT',
            'native': {'path': str(native), 'sha256': self.authority['nativeHash']},
            'audio': {'path': str(audio), 'sha256': self.authority['audioHash']},
            'reviewDraft': {'schema': 'capcut-review-draft/v1', 'taskId': 'synthetic-unit',
                'destination': {'operation': r.OPERATION, 'overwriteExisting': True,
                    'path': str(self.target), 'name': self.initial['name'],
                    'projectId': self.initial['projectId'], 'timelineId': self.initial['timelineId'],
                    'revisionBaseline': self.baseline_ref}}}
        self.guard_path = self.root / 'guard.json'
        self.request = {'schema': r.REQUEST_SCHEMA, 'operation': r.OPERATION,
            'storePath': str(self.store), 'name': self.initial['name'],
            'projectId': self.initial['projectId'], 'timelineId': self.initial['timelineId'],
            'rootIndexSHA256': self.baseline['rootIndexSHA256'],
            'expectedFiles': self.baseline['expectedFiles']}
        self.refresh_records()
        self.result = {'passed': True, 'errors': [], 'status': 'PROVISIONAL_NOT_ACCEPTED',
            'stage': 'REVIEW_DRAFT', 'finalAcceptance': False,
            'nativeHash': self.authority['nativeHash'], 'syntheticMockOnly': True}
        self.journal = self.root / 'journal'

    def refresh_records(self):
        self.authority_path.write_bytes(n.json_bytes(self.authority))
        authority_ref = {'path': str(self.authority_path), 'sha256': 'sha256:' + n.sha256(self.authority_path)}
        self.guard['reviewDraft']['authorityEvidence'] = authority_ref
        self.guard_path.write_bytes(n.json_bytes(self.guard))
        self.request['authorityEvidence'] = authority_ref
        self.request['guardManifest'] = {'path': str(self.guard_path), 'sha256': 'sha256:' + n.sha256(self.guard_path)}

    def mocks(self):
        return patch.multiple(n, _assert_app=DEFAULT, _assert_editor_closed=DEFAULT, _guard_check=DEFAULT)

    def apply(self):
        return r.apply_revision(self.compiled, self.request, self.journal)

    def assert_before(self):
        self.assertEqual(self.index_bytes, self.index.read_bytes())
        for rel, value in self.before.items():
            self.assertEqual(value, (self.target / rel).read_bytes(), rel)
        self.assertEqual(b'FOREIGN PROJECT BYTES', self.foreign.read_bytes())

    def test_success_same_identity_nine_readbacks_preserved_index_foreign_and_metadata(self):
        with self.mocks() as mocks:
            mocks['_guard_check'].return_value = self.result
            result = self.apply()
            self.assertEqual(1, mocks['_guard_check'].call_count)
            self.assertGreaterEqual(mocks['_assert_editor_closed'].call_count, 3)
        self.assertEqual('OWNED_NATIVE_REVISION_FILE_READBACK_PASS', result['status'])
        self.assertEqual(9, result['filesChecked'])
        self.assertEqual(self.index_bytes, self.index.read_bytes())
        self.assertEqual(b'FOREIGN PROJECT BYTES', self.foreign.read_bytes())
        self.assertEqual(b'PRESERVE TARGET EXTRA', (self.target / 'unselected-extra.bin').read_bytes())
        meta = n.read_json(self.target / 'draft_meta_info.json')
        self.assertEqual(self.old_meta['tm_draft_create'], meta['tm_draft_create'])
        self.assertEqual({'keep': 97}, meta['opaqueUserMetadata'])
        self.assertEqual(self.old_meta['draft_fold_path'], meta['draft_fold_path'])
        self.assertEqual('SEMANTIC_READBACK_PASS', n.validate_compiled(self.compiled)['status'])
        self.assertFalse(result['finalAcceptance'])
        self.assertTrue((self.journal / 'before/draft_content.json').is_file())

    def test_default_compile_fresh_identity_and_revision_cannot_use_create_writer(self):
        self.assertEqual('CREATE_NEW', self.initial['identityMode'])
        self.assertEqual('OWNED_REVISION', self.manifest['identityMode'])
        self.assertEqual(self.initial['projectId'], self.manifest['projectId'])
        self.assertEqual(self.initial['timelineId'], self.manifest['timelineId'])
        other = n.compile_plan(self.plan, self.root / 'other')
        self.assertNotEqual(other['projectId'], self.initial['projectId'])
        with self.assertRaisesRegex(n.PlanError, 'cannot-create-project'):
            n.apply_new_project(self.compiled, {'schema': 'capcut-new-project-apply/v1'}, self.journal)
        self.assert_before()

    def test_identity_name_request_changes_reject(self):
        for key in ('projectId', 'timelineId', 'name'):
            with self.subTest(key=key):
                request = copy.deepcopy(self.request)
                request[key] = 'wrong'
                with self.mocks(), self.assertRaisesRegex(n.PlanError, 'revision-exact-'):
                    r.apply_revision(self.compiled, request, self.journal)
        self.assert_before()

    def test_authority_change_or_teacher_claim_rejects(self):
        for key, value in [('operation', 'CREATE'), ('claim', 'teacher-activation'),
                ('nativeHash', 'sha256:' + '0' * 64), ('userQuote', ''),
                ('expectedFiles', {}), ('rootIndexSHA256', '0' * 64)]:
            with self.subTest(key=key):
                old = self.authority[key]
                self.authority[key] = value
                self.refresh_records()
                with self.mocks(), self.assertRaisesRegex(n.PlanError, 'exact-update-authority'):
                    self.apply()
                self.authority[key] = old
        self.assert_before()

    def test_changed_before_hash_request_rejects(self):
        self.request['expectedFiles'] = {**self.request['expectedFiles'], 'key_value.json': '0' * 64}
        with self.mocks(), self.assertRaisesRegex(n.PlanError, 'before-baseline'):
            self.apply()
        self.assert_before()

    def test_live_target_drift_rejects(self):
        path = self.target / 'key_value.json'
        path.write_bytes(b'{"foreign":1}')
        with self.mocks(), self.assertRaisesRegex(n.PlanError, 'target-drift'):
            self.apply()
        self.assertEqual(b'{"foreign":1}', path.read_bytes())
        self.assertFalse(self.journal.exists())

    def test_live_index_drift_rejects(self):
        self.index.write_bytes(self.index_bytes + b' ')
        with self.mocks(), self.assertRaisesRegex(n.PlanError, 'root-index-drift'):
            self.apply()
        self.assertEqual(self.index_bytes + b' ', self.index.read_bytes())

    def test_old_metadata_root_identity_not_caller_owned_boolean(self):
        meta = copy.deepcopy(self.old_meta)
        meta['draft_id'] = str(__import__('uuid').uuid4()).upper()
        (self.target / 'draft_meta_info.json').write_bytes(n.json_bytes(meta))
        with self.assertRaisesRegex(n.PlanError, 'root-index-project-identity'):
            r.capture_baseline(self.store, self.initial['name'], self.root / 'wrong-baseline')
        self.assertFalse((self.root / 'wrong-baseline').exists())

    def test_open_app_rejects_before_journal_or_write(self):
        with self.mocks() as mocks:
            mocks['_assert_editor_closed'].side_effect = n.PlanError('capcut-must-be-closed')
            with self.assertRaisesRegex(n.PlanError, 'must-be-closed'):
                self.apply()
            mocks['_guard_check'].assert_not_called()
        self.assert_before()
        self.assertFalse(self.journal.exists())

    def test_guard_refusal_retains_terminal_failure_without_native_mutation(self):
        with self.mocks() as mocks:
            mocks['_guard_check'].return_value = {**self.result, 'passed': False, 'errors': ['audio-review-missing']}
            with self.assertRaisesRegex(n.PlanError, 'fresh-guard-refused'):
                self.apply()
        self.assert_before()
        self.assertEqual([], n.read_json(self.journal / 'failure.json')['attemptedFiles'])

    def test_unmocked_guard_refuses_missing_actual_audio_quality_evidence(self):
        with patch.object(n, '_assert_app'), patch.object(n, '_assert_editor_closed'):
            with self.assertRaises((n.PlanError, ValueError, KeyError)):
                self.apply()
        self.assert_before()
        self.assertTrue((self.journal / 'failure.json').is_file())

    def test_owned_guard_branch_checks_real_baseline_not_new_destination(self):
        from check_native_apply import check_review_draft
        errors = []
        draft = n.read_json(self.compiled / 'files/draft_content.json')
        check_review_draft(self.guard, draft,
            {'native': self.authority['nativeHash'], 'audio': self.authority['audioHash']}, errors)
        self.assertTrue(errors)  # Missing actual semantic/audio proof stays blocked.
        self.assertNotIn('review-draft-new-destination-required', errors)
        self.assertNotIn('review-draft-no-existing-project-edit', errors)
        self.assertFalse(any('owned-identity-binding' in e or 'owned-authority-' in e for e in errors), errors)
        self.authority['operation'] = 'CREATE'
        self.refresh_records()
        errors = []
        check_review_draft(self.guard, draft,
            {'native': self.authority['nativeHash'], 'audio': self.authority['audioHash']}, errors)
        self.assertIn('review-draft-owned-authority-operation', errors)

    def test_unexpected_compiled_file_rejects(self):
        (self.compiled / 'files/not-allowed.bin').write_bytes(b'UNEXPECTED')
        with self.mocks(), self.assertRaisesRegex(n.PlanError, 'unexpected-compiled-payload'):
            self.apply()
        self.assert_before()

    def test_unexpected_expected_file_rejects(self):
        self.request['expectedFiles'] = {**self.request['expectedFiles'], '../foreign.bin': '0' * 64}
        with self.mocks(), self.assertRaisesRegex(n.PlanError, 'before-baseline'):
            self.apply()
        self.assert_before()

    def test_hardlinked_target_file_rejects(self):
        path = self.target / 'key_value.json'
        os.link(path, self.root / 'second-hard-link')
        with self.mocks(), self.assertRaisesRegex(n.PlanError, 'hardlinked'):
            self.apply()
        self.assert_before()

    def test_junction_parent_refused_without_creating_real_link(self):
        original = Path.is_junction
        def is_junction(path):
            return path == self.target or original(path)
        with patch.object(Path, 'is_junction', is_junction), self.mocks():
            with self.assertRaisesRegex(n.PlanError, 'linked-path'):
                self.apply()
        self.assert_before()

    def test_target_foreign_change_during_guard_preserved(self):
        path = self.target / 'key_value.json'
        def guard(_):
            path.write_bytes(b'FOREIGN DURING GUARD')
            return self.result
        with self.mocks() as mocks:
            mocks['_guard_check'].side_effect = guard
            with self.assertRaisesRegex(n.PlanError, 'target-changed-before-write'):
                self.apply()
        self.assertEqual(b'FOREIGN DURING GUARD', path.read_bytes())
        self.assertEqual([], n.read_json(self.journal / 'failure.json')['attemptedFiles'])

    def test_shared_index_foreign_change_during_guard_preserved(self):
        def guard(_):
            self.index.write_bytes(self.index_bytes + b' ')
            return self.result
        with self.mocks() as mocks:
            mocks['_guard_check'].side_effect = guard
            with self.assertRaisesRegex(n.PlanError, 'shared-index-changed'):
                self.apply()
        self.assertEqual(self.index_bytes + b' ', self.index.read_bytes())

    def test_compiled_file_drift_during_guard_blocks_before_native_write(self):
        def guard(_):
            (self.compiled / 'files/key_value.json').write_bytes(b'{"foreign":2}')
            return self.result
        with self.mocks() as mocks:
            mocks['_guard_check'].side_effect = guard
            with self.assertRaisesRegex(n.PlanError, 'compiled-drift-after-guard'):
                self.apply()
        self.assert_before()

    def test_effect_then_error_is_reconciled_and_owned_bytes_restored(self):
        original = r.os.replace
        count = 0
        def replace(src, dst):
            nonlocal count
            count += 1
            original(src, dst)
            if count == 1:
                raise OSError('effect-then-error')
        with self.mocks() as mocks, patch.object(r.os, 'replace', side_effect=replace):
            mocks['_guard_check'].return_value = self.result
            with self.assertRaisesRegex(OSError, 'effect-then-error'):
                self.apply()
        self.assert_before()
        failure = n.read_json(self.journal / 'failure.json')
        self.assertTrue(any(x['state'] == 'OWNED_AFTER' for x in failure['reconciliation'].values()))
        self.assertEqual('OWNED_BYTES_RESTORED', failure['rollback'][0]['status'])

    def test_partial_second_write_failure_restores_only_first_owned_write(self):
        original = r.os.replace
        count = 0
        def replace(src, dst):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('second-write-failure')
            return original(src, dst)
        with self.mocks() as mocks, patch.object(r.os, 'replace', side_effect=replace):
            mocks['_guard_check'].return_value = self.result
            with self.assertRaisesRegex(OSError, 'second-write-failure'):
                self.apply()
        self.assert_before()
        self.assertTrue(n.read_json(self.journal / 'failure.json')['rollback'])

    def test_cas_foreign_change_after_stage_is_not_overwritten(self):
        original = n._exclusive_write
        changed = []
        def stage(path, data):
            original(path, data)
            path = Path(path)
            if path.name.endswith('.owned-revision.tmp') and not changed:
                victim = path.parent / path.name[1:].removesuffix('.owned-revision.tmp').rsplit('.', 1)[0]
                victim.write_bytes(b'FOREIGN AFTER STAGING')
                changed.append(victim)
        with self.mocks() as mocks, patch.object(n, '_exclusive_write', side_effect=stage):
            mocks['_guard_check'].return_value = self.result
            with self.assertRaisesRegex(n.PlanError, 'cas-before-replace'):
                self.apply()
        self.assertEqual(b'FOREIGN AFTER STAGING', changed[0].read_bytes())
        failure = n.read_json(self.journal / 'failure.json')
        self.assertTrue(any(x['state'] == 'FOREIGN_OR_UNKNOWN' for x in failure['reconciliation'].values()))

    def test_foreign_change_after_replace_is_not_rolled_back(self):
        original = r.os.replace
        changed = []
        def replace(src, dst):
            original(src, dst)
            if not changed:
                Path(dst).write_bytes(b'FOREIGN AFTER COMMIT')
                changed.append(Path(dst))
        with self.mocks() as mocks, patch.object(r.os, 'replace', side_effect=replace):
            mocks['_guard_check'].return_value = self.result
            with self.assertRaisesRegex(n.PlanError, 'replace-readback'):
                self.apply()
        self.assertEqual(b'FOREIGN AFTER COMMIT', changed[0].read_bytes())
        self.assertEqual([], n.read_json(self.journal / 'failure.json')['rollback'])

    def test_foreign_equal_candidate_before_replace_is_not_claimed_as_our_write(self):
        original = n._exclusive_write
        changed = []
        def stage(path, data):
            original(path, data)
            path = Path(path)
            if path.name.endswith('.owned-revision.tmp') and not changed:
                victim = path.parent / path.name[1:].removesuffix('.owned-revision.tmp').rsplit('.', 1)[0]
                victim.write_bytes(data)
                changed.append((victim, data))
        with self.mocks() as mocks, patch.object(n, '_exclusive_write', side_effect=stage):
            mocks['_guard_check'].return_value = self.result
            with self.assertRaisesRegex(n.PlanError, 'cas-before-replace'):
                self.apply()
        self.assertEqual(changed[0][1], changed[0][0].read_bytes())
        failure = n.read_json(self.journal / 'failure.json')
        self.assertEqual([], failure['attemptedFiles'])
        self.assertEqual([], failure['rollback'])

    def test_app_opening_mid_write_holds_rollback_without_kill(self):
        original = r.os.replace
        replaced = []
        def replace(src, dst):
            original(src, dst)
            replaced.append(Path(dst))
        def closed():
            if replaced:
                raise n.PlanError('capcut-must-be-closed')
        with self.mocks() as mocks, patch.object(r.os, 'replace', side_effect=replace):
            mocks['_guard_check'].return_value = self.result
            mocks['_assert_editor_closed'].side_effect = closed
            with self.assertRaisesRegex(n.PlanError, 'must-be-closed'):
                self.apply()
        failure = n.read_json(self.journal / 'failure.json')
        self.assertTrue(any(x['status'] == 'HELD' for x in failure['rollback']))
        self.assertEqual(self.index_bytes, self.index.read_bytes())

    def test_preflight_has_no_native_or_journal_writes(self):
        with self.mocks() as mocks:
            mocks['_guard_check'].return_value = self.result
            result = r.preflight(self.compiled, self.request)
        self.assertEqual(0, result['nativeWrites'])
        self.assertFalse(result['permissionGranted'])
        self.assert_before()
        self.assertFalse(self.journal.exists())

    def test_review_builder_preserves_explicit_owned_destination_and_authority_fields(self):
        from prepare_review_draft import _destination_contract
        inp = {'destinationPath': str(self.target), 'destinationOperation': r.OPERATION,
            'revisionBaseline': self.baseline_ref}
        decision = {'operation': r.OPERATION, 'revisionBaseline': self.baseline_ref,
            'projectId': self.initial['projectId'], 'timelineId': self.initial['timelineId']}
        producer = n.read_json(self.compiled / 'plan.json')
        destination, fields = _destination_contract(inp, decision, self.manifest, producer)
        self.assertEqual(r.OPERATION, destination['operation'])
        self.assertTrue(destination['overwriteExisting'])
        self.assertEqual(self.baseline_ref, destination['revisionBaseline'])
        self.assertEqual(self.baseline['expectedFiles'], fields['expectedFiles'])
        self.assertEqual(self.baseline['rootIndexSHA256'], fields['rootIndexSHA256'])
        self.assertEqual('review-draft-native-update-owned', fields['claim'])

    def test_review_builder_cannot_silently_default_revision_to_create(self):
        from prepare_review_draft import _destination_contract
        with self.assertRaisesRegex(ValueError, 'review-new-destination-required'):
            _destination_contract({'destinationPath': str(self.target)}, {}, self.manifest,
                n.read_json(self.compiled / 'plan.json'))
        with self.assertRaisesRegex(ValueError, 'revision-compile-cannot-select-create'):
            _destination_contract({'destinationPath': str(self.root / 'new-destination')}, {}, self.manifest,
                n.read_json(self.compiled / 'plan.json'))

    def test_review_builder_requires_original_owned_decision_and_exact_baseline(self):
        from prepare_review_draft import _destination_contract
        inp = {'destinationPath': str(self.target), 'destinationOperation': r.OPERATION,
            'revisionBaseline': self.baseline_ref}
        with self.assertRaisesRegex(ValueError, 'original-decision-binding'):
            _destination_contract(inp, {}, self.manifest, n.read_json(self.compiled / 'plan.json'))
        self.index.write_bytes(self.index_bytes + b' ')
        with self.assertRaisesRegex(n.PlanError, 'root-index-drift'):
            _destination_contract(inp, {}, self.manifest, n.read_json(self.compiled / 'plan.json'))


if __name__ == '__main__':
    unittest.main()
