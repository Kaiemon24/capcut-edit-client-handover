"""Inert behavior fixtures; no UI, audio submissions, installs or app writes."""
import copy,hashlib,tempfile,unittest
from pathlib import Path
import capability_preflight as c

class CapabilityPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=Path(self.tmp.name)/'observation.txt';p.write_text('inert fixture observation',encoding='utf-8')
        self.proof={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        self.context=dict(sessionId='fixture',toolsetHash='fixture-tools',audioContext='fixture-audio',appVersion='fixture-app',runtimeEpoch='1',targetId='fixture-target')
        self.data={'schemaVersion':'capcut-capability-session/v1','context':self.context.copy(),'outputMode':'EDIT_TIMELINE','requiresSpeech':True,'catalogComplete':True,'providers':[],'observations':[],'deniedCapabilities':[]}
    def provider(self,pid,caps,**kw):
        p=dict(id=pid,capabilities=caps,available=True,initialized=True,scopeAuthorized=True,visibility='non_ui',visibilitySupported=True,visibilityApproved=False);p.update(kw);self.data['providers'].append(p);return p
    def observe(self,pid,cap,status='PASS',**kw):
        o=dict(provider=pid,capability=cap,status=status,proofType=c.PROOF_TYPES[cap],context=self.context.copy(),evidence=self.proof.copy());o.update(kw);self.data['observations'].append(o);return o
    def ready(self):
        for cap in c.CAPABILITIES:
            self.provider(cap,[cap]);self.observe(cap,cap)
    def plan(self):return c.evaluate(self.data)
    def actions(self,kind=None):return [a for a in self.plan()['actions'] if kind is None or a['kind']==kind]
    def test_ready_never_authorizes_mutation_or_accepts_project(self):
        self.ready();r=self.plan();self.assertEqual(r['status'],'CAPABILITY_READY');self.assertFalse(r['nativeMutationAuthorized']);self.assertEqual(r['projectAcceptance'],'NOT_ASSESSED')
    def test_provider_restriction_is_not_universal(self):
        self.provider('cua',['native_frame'],available=False);self.provider('sky',['native_frame'],initialized=False)
        self.assertEqual(self.actions('initialize_provider')[0]['provider'],'sky')
    def test_initialization_is_automatic_deduplicated_plan(self):
        self.provider('local',['media_read','media_decode'],initialized=False)
        self.assertEqual(len(self.actions('initialize_provider')),1)
    def test_unknown_catalog_discovers_before_unavailable_claim(self):
        self.data['catalogComplete']=False;self.assertTrue(self.actions('discover_supported_providers'))
    def test_srt_does_not_require_native_checks(self):
        self.ready();self.data['outputMode']='SRT_ONLY';r=self.plan();self.assertFalse(any(k.startswith('native') for k in r['capabilities']));self.assertTrue(r['transferCapabilityReady'])
    def test_silent_task_does_not_probe_audio_modality(self):
        self.data['requiresSpeech']=False;r=self.plan();self.assertNotIn('auditory_input',r['capabilities'])
    def test_asr_does_not_clear_unsupported_audio(self):
        self.provider('asr',['speech_candidates']);self.observe('asr','speech_candidates');self.provider('audio',['auditory_input']);self.observe('audio','auditory_input','UNSUPPORTED')
        r=self.plan();self.assertEqual(r['capabilities']['auditory_input'],'UNAVAILABLE');self.assertFalse(any(a['capability']=='auditory_input' for a in r['actions']))
    def test_model_output_cannot_be_auditory_proof(self):
        self.provider('asr',['auditory_input']);self.observe('asr','auditory_input',proofType='MODEL_OUTPUT')
        with self.assertRaisesRegex(ValueError,'wrong_proof_type'):self.plan()
    def test_uia_cannot_be_window_pixels(self):
        self.provider('uia',['native_frame']);self.observe('uia','native_frame',proofType='UIA_TEXT')
        with self.assertRaisesRegex(ValueError,'wrong_proof_type'):self.plan()
    def test_pass_requires_existing_evidence(self):
        self.provider('p',['media_read']);self.observe('p','media_read',evidence={'path':str(Path(self.tmp.name)/'absent'),'sha256':'0'*64})
        with self.assertRaisesRegex(ValueError,'evidence_file'):self.plan()
    def test_pass_rejects_changed_evidence(self):
        self.provider('p',['media_read']);self.observe('p','media_read');Path(self.proof['path']).write_text('changed')
        with self.assertRaisesRegex(ValueError,'evidence_drift'):self.plan()
    def test_all_context_changes_invalidate_current_capability(self):
        self.provider('p',['media_read']);self.observe('p','media_read')
        for key in c.CONTEXT_KEYS:
            with self.subTest(key=key):
                self.data['context']=self.context.copy();self.data['context'][key]+='-changed'
                r=self.plan();self.assertTrue(r['staleObservations']);self.assertEqual(r['actions'][0]['kind'],'probe_capability')
    def test_unchanged_negative_does_not_block_new_provider(self):
        self.provider('old',['native_frame']);self.observe('old','native_frame','FAIL',failureKind='native_capture_timeout',attempts=2,usedRecoveries=['refresh_target'])
        self.provider('new',['native_frame'],initialized=False)
        self.assertEqual(self.actions('initialize_provider')[0]['provider'],'new')
    def test_known_capture_gets_one_refresh(self):
        self.provider('p',['native_frame']);self.observe('p','native_frame','FAIL',failureKind='native_capture_timeout')
        a=self.actions('known_recovery');self.assertEqual(len(a),1);self.assertEqual(a[0]['recovery'],'refresh_target')
    def test_exhausted_capture_does_not_loop_or_consult_again(self):
        self.provider('p',['native_frame']);self.observe('p','native_frame','FAIL',failureKind='native_capture_timeout',attempts=2,usedRecoveries=['refresh_target'])
        self.assertFalse(self.actions());self.assertEqual(self.plan()['capabilities']['native_frame'],'UNAVAILABLE')
    def test_recovery_identity_prevents_budget_reset(self):
        self.provider('p',['native_frame']);self.observe('p','native_frame','FAIL',failureKind='native_capture_timeout',usedRecoveries=['refresh_target'])
        self.assertFalse(self.actions('known_recovery'))
    def test_denied_target_not_repackaged_through_another_provider(self):
        self.provider('p',['native_frame']);self.provider('q',['native_frame']);self.data['deniedCapabilities']=['native_frame']
        self.assertFalse(any(a['capability']=='native_frame' for a in self.actions()));self.assertEqual(self.plan()['capabilities']['native_frame'],'DENIED')
    def test_visible_requires_exact_current_approval(self):
        self.provider('p',['native_frame'],initialized=False,visibility='visible',visibilityApproved=False)
        self.assertFalse(self.actions('initialize_provider'));self.assertEqual(self.plan()['capabilities']['native_frame'],'NEEDS_VISIBILITY')
    def test_visible_grant_reused_without_new_permission_action(self):
        self.provider('p',['native_frame'],initialized=False,visibility='visible',visibilityApproved=True)
        self.assertTrue(self.actions('initialize_provider'))
    def test_unsupported_hidden_does_not_steal_focus(self):
        self.provider('p',['native_frame'],initialized=False,visibility='hidden',visibilitySupported=False)
        self.assertFalse(self.actions('initialize_provider'));self.assertEqual(self.plan()['capabilities']['native_frame'],'UNAVAILABLE')
    def test_scope_authority_required_even_without_ui(self):
        self.provider('p',['native_writer'],initialized=False,scopeAuthorized=False)
        self.assertFalse(self.actions('initialize_provider'))
    def test_preparation_continues_when_capture_is_blocked(self):
        for cap in ['media_read','media_decode']:
            self.provider(cap,[cap]);self.observe(cap,cap)
        self.provider('sky',['native_frame']);self.observe('sky','native_frame','UNSUPPORTED')
        self.assertTrue(self.plan()['preparationReady']);self.assertEqual(self.plan()['capabilities']['native_frame'],'UNAVAILABLE')
    def test_new_fault_consults_owner_internally_once(self):
        self.provider('p',['media_decode']);o=self.observe('p','media_decode','FAIL',failureKind='new_fault')
        self.assertEqual(len(self.actions('consult_functional_owner')),1);o['ownerConsulted']=True;self.assertFalse(self.actions('consult_functional_owner'))
    def test_malformed_consultation_flag_does_not_hide_failure(self):
        self.provider('p',['media_decode']);o=self.observe('p','media_decode','FAIL',failureKind='new_fault')
        for bad in ['false',1,[],None]:
            with self.subTest(bad=bad):
                o['ownerConsulted']=bad
                with self.assertRaisesRegex(ValueError,'owner_consulted_boolean'):self.plan()
    def test_uncertain_write_holds_proven_alternate_control(self):
        self.provider('p',['native_writer']);self.observe('p','native_writer','FAIL',failureKind='uncertain_native_write');self.provider('q',['native_control']);self.observe('q','native_control')
        r=self.plan();self.assertEqual(r['capabilities']['native_control'],'RECONCILE_REQUIRED');self.assertFalse(r['transferCapabilityReady']);self.assertTrue(self.actions('reconcile_uncertain_state'))
    def test_uncertain_write_does_not_restore_denied_read_authority(self):
        p=self.provider('p',['native_writer']);self.observe('p','native_writer','FAIL',failureKind='uncertain_native_write');self.data['deniedCapabilities']=['native_writer']
        self.assertFalse(self.actions('reconcile_uncertain_state'));self.assertFalse(self.plan()['transferCapabilityReady'])
        self.data['deniedCapabilities']=[];p['scopeAuthorized']=False;self.assertFalse(self.actions('reconcile_uncertain_state'))
    def test_uncertain_recovery_honors_visibility_and_initializes_first(self):
        p=self.provider('p',['native_writer'],visibility='visible',visibilityApproved=False);self.observe('p','native_writer','FAIL',failureKind='uncertain_native_write')
        self.assertFalse(self.actions());p.update(visibility='hidden',visibilitySupported=False);self.assertFalse(self.actions())
        p.update(visibility='non_ui',initialized=False);a=self.actions();self.assertEqual([x['kind'] for x in a],['initialize_provider']);self.assertFalse(self.plan()['transferCapabilityReady'])
    def test_unavailable_writer_pass_does_not_preempt_valid_control(self):
        self.provider('old',['native_writer'],available=False);self.observe('old','native_writer');self.provider('new',['native_writer']);self.provider('q',['native_control']);self.observe('q','native_control')
        r=self.plan();self.assertEqual(r['capabilities']['native_control'],'CAPABLE');self.assertFalse(any(a['capability']=='native_writer' for a in r['actions']))
    def test_recovery_kind_cannot_cross_capability(self):
        self.provider('p',['speech_candidates']);self.observe('p','speech_candidates','FAIL',failureKind='native_capture_timeout')
        with self.assertRaisesRegex(ValueError,'failure_capability_mismatch'):self.plan()
    def test_srt_ignores_unrelated_native_evidence_drift(self):
        self.ready();self.data['outputMode']='SRT_ONLY'
        next(o for o in self.data['observations'] if o['capability']=='native_frame')['evidence']={'path':'Z:/absent-proof','sha256':'0'*64}
        r=self.plan();self.assertEqual(r['status'],'CAPABILITY_READY');self.assertTrue(r['ignoredObservations'])
    def test_stale_removed_provider_is_not_current_failure(self):
        self.provider('old',['media_read']);o=self.observe('old','media_read');self.data['providers']=[];self.data['context']['toolsetHash']='changed';self.data['catalogComplete']=False
        r=self.plan();self.assertTrue(r['staleObservations']);self.assertTrue(self.actions('discover_supported_providers'))
    def test_uncertain_write_reconciles_before_any_replay(self):
        self.provider('p',['native_writer']);self.observe('p','native_writer','FAIL',failureKind='uncertain_native_write')
        a=self.actions();self.assertEqual(a[0]['kind'],'reconcile_uncertain_state');self.assertFalse(any(x['kind']=='known_recovery' for x in a))
    def test_decoder_recovery_needs_proven_local_decode(self):
        self.provider('asr',['speech_candidates']);self.observe('asr','speech_candidates','FAIL',failureKind='asr_file_decode_mismatch')
        self.assertFalse(self.actions('known_recovery'));self.provider('decode',['media_decode']);self.observe('decode','media_decode');self.assertTrue(self.actions('known_recovery'))
    def test_decoder_recovery_cannot_use_unauthorized_provider(self):
        self.provider('decode',['media_decode'],scopeAuthorized=False);self.observe('decode','media_decode');self.provider('asr',['speech_candidates']);self.observe('asr','speech_candidates','FAIL',failureKind='asr_file_decode_mismatch')
        self.assertFalse(self.actions('known_recovery'))
    def test_incomplete_catalog_still_discovers_after_known_failure(self):
        self.provider('p',['native_frame']);self.observe('p','native_frame','FAIL',failureKind='native_capture_timeout',attempts=2);self.data['catalogComplete']=False
        self.assertTrue(any(a['capability']=='native_frame' for a in self.actions('discover_supported_providers')))
    def test_choose_proven_control_without_probing_writer(self):
        self.provider('control',['native_control']);self.observe('control','native_control');self.provider('writer',['native_writer'])
        r=self.plan();self.assertEqual(r['capabilities']['native_writer'],'NOT_SELECTED');self.assertFalse(any(a['capability']=='native_writer' for a in r['actions']))
    def test_writer_probe_is_not_followed_by_unneeded_control_probe(self):
        self.provider('writer',['native_writer']);self.provider('control',['native_control'])
        r=self.plan();self.assertEqual(r['capabilities']['native_control'],'NOT_SELECTED')
    def test_malformed_and_duplicate_observations_fail(self):
        self.provider('p',['media_read']);self.observe('p','media_read');self.observe('p','media_read')
        with self.assertRaisesRegex(ValueError,'duplicate_current_observation'):self.plan()
    def test_initialization_not_mistaken_for_operational_proof(self):
        self.provider('p',['native_frame']);r=self.plan();self.assertEqual(r['capabilities']['native_frame'],'CHECK_PENDING');self.assertFalse(r['nativeMutationAuthorized'])

if __name__=='__main__':unittest.main()
