"""Synthetic mechanical tests only; none certifies heard speech/native playback."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import wave
from dependency_proof import (file_ref,make_adoption,validate_adoption,
    dependency_fingerprints,validate_native_phase)
from check_native_apply import native_broll_inventory

def audio_review_fixture(root,audio,task='synthetic-audio-task',clock_map=None):
    """Simulated consistency declarations only; never real user acceptance."""
    from prepare_voice_review import prepare_review
    root=Path(root);number=len(list(root.glob('audio-fixture-*')));prefix='audio-fixture-'+str(number)
    def put(suffix,obj):
        path=root/(prefix+suffix);path.write_text(json.dumps(obj),encoding='utf-8');return file_ref(path)
    gain2=root/(prefix+'-gain2.wav');prepare_review(Path(audio),gain2)
    receipt=file_ref(gain2.with_suffix('.review.json'));gain1=file_ref(audio);listen=file_ref(gain2)
    if clock_map is None:clock_map=put('-clock.json',{'evidenceClass':'REAL_OBSERVATION','status':'PASS_STRUCTURAL_NOT_HEARD','audioHash':gain1['sha256'],'gain':1})
    feedback=put('-feedback.json',{'schema':'capcut-audio-feedback-inventory/v1','taskId':task,'audioHash':gain1['sha256'],
        'coverage':'ALL_CURRENT_TASK_AUDIO_FEEDBACK','latestFeedbackIds':[],'items':[],'unresolvedFeedbackIds':[]})
    reply=put('-reply.json',{'evidenceClass':'REAL_OBSERVATION','source':'DIRECT_USER_MESSAGE','reviewKind':'AUDIO_CONTENT',
        'sourceRef':'synthetic consistency fixture, not a real provider/message id',
        'message':'Synthetic acceptance declaration; no human actually listened'})
    acceptance=put('-acceptance.json',{'schema':'capcut-user-audio-review/v1','evidenceClass':'REAL_OBSERVATION',
        'basis':'USER_AUDIO_REVIEW','status':'ACCEPTED','claim':'audio-content-review-acceptance','taskId':task,
        'audioHash':gain1['sha256'],'listeningCopyHash':listen['sha256'],'clockMapHash':clock_map['sha256'],
        'feedbackInventoryHash':feedback['sha256'],'userReply':reply,
        'userQuote':'Synthetic acceptance declaration; no human actually listened'})
    inputs={'listeningGain2':listen,'gainReceipt':receipt,'feedbackInventory':feedback,'acceptanceEvidence':acceptance}
    checkpoint=put('-checkpoint.json',{'schema':'capcut-audio-review-checkpoint/v1','taskId':task,'status':'ACCEPTED_BY_USER',
        'audioGain1':gain1,'clockMap':clock_map,**inputs})
    return {'checkpoint':checkpoint,'input':inputs}

def source_word_fixture(root,words):
    """Tiny complete synthetic transcript and reversible stable IDs."""
    root=Path(root);prefix='source-word-fixture-'+str(len(list(root.glob('source-word-fixture-*'))))
    def put(suffix,value):
        p=root/(prefix+suffix);p.write_text(json.dumps(value));return file_ref(p)
    complete=[];raw=[]
    for index,word in enumerate(words):
        row={'word':word['text'],'start':word['sourceStartTick']/1e6,'end':word['sourceEndTick']/1e6,'probability':0.5}
        complete.append({'id':index,'words':[row]})
        raw.append({'id':word['id'],'segmentId':index,'rawText':row['word'],
            'sourceStartSeconds':row['start'],'sourceEndSeconds':row['end'],'probability':row['probability']})
    transcript=put('-transcript.json',{'sourceAudioSha256':'synthetic source-audio hash, no actual media','segments':complete})
    record=put('-raw.json',{'asrSha256':transcript['sha256'],'sourceAudioSha256':'synthetic source-audio hash, no actual media','words':raw})
    return {'rawSourceWords':record,'rawTranscript':transcript}

def audio_edit_fixture(root,native,audio,execution,final=True):
    """Simulated classification consistency only; never actual audio proof."""
    from dependency_proof import make_audio_edit_inventory,read_ref
    root=Path(root);prefix='edit-fixture-'+str(len(list(root.glob('edit-fixture-*'))))
    def put(suffix,obj):
        p=root/(prefix+suffix);p.write_text(json.dumps(obj),encoding='utf-8');return file_ref(p)
    audit=read_ref(execution);raw=source_word_fixture(root,audit['captionPlan']['words'])
    obs=put('-observations.json',{'schema':'capcut-source-edit-observations/v1','evidenceClass':'REAL_OBSERVATION','removals':[]})
    policy={'maxActualRetainedQuietTicks':200000,**raw,'sourceEditObservations':obs,'removedContentRawWordIds':[]}
    source_map={w['sourceId']:w['sourceId'] for w in audit['captionPlan']['words']}
    record=make_audio_edit_inventory(file_ref(native),file_ref(audio),execution,policy,source_map)
    if final:
        for row in record['candidates']:
            row.update(status='REVIEWED',observedKind='SPEECH_OR_NOT_QUIET')
            row['evidence']=put('-'+str(len(list(root.glob(prefix+'*'))))+'-review.json',{
                'evidenceClass':'REAL_OBSERVATION','status':'PASS','basis':'HUMAN_LISTENING','claim':'actual-quiet-span-review',
                'reviewer':'synthetic reviewer','observation':'Synthetic declaration only, no actual listening',
                'nativeHash':file_ref(native)['sha256'],'audioHash':file_ref(audio)['sha256'],
                'candidateId':row['id'],'observedKind':row['observedKind'],'observedQuietIntervals':[]})
    return put('-inventory.json',record)

class AudioReviewCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.audio=self.root/'final.wav'
        with wave.open(str(self.audio),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\xe8\x03'*16000)
        self.ref=audio_review_fixture(self.root,self.audio,'audio-task')['checkpoint']
    def put(self,ref,obj):
        p=Path(ref['path']);p.write_text(json.dumps(obj));return file_ref(p)
    def record(self):return json.loads(Path(self.ref['path']).read_text())
    def validate(self):
        from dependency_proof import validate_audio_review_checkpoint
        return validate_audio_review_checkpoint(self.ref,file_ref(self.audio),'audio-task')
    def test_exact_real_review_contract_consistency_and_unchanged_reuse(self):
        self.assertEqual(self.validate()['status'],'USER_AUDIO_REVIEW_ACCEPTED')
        self.assertEqual(self.validate()['status'],'USER_AUDIO_REVIEW_ACCEPTED')
        self.assertTrue(self.validate()['doesNotCertifyCaptionOnsetsOrNativePlayback'])
    def test_missing_acceptance_is_blocked(self):
        r=self.record();r['status']='PENDING_USER_AUDIO_REVIEW';self.ref=self.put(self.ref,r)
        with self.assertRaisesRegex(ValueError,'pending-or-rejected'):self.validate()
    def test_recut_audio_hash_invalidates_acceptance(self):
        with wave.open(str(self.audio),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\xe8\x03'*15999)
        with self.assertRaisesRegex(ValueError,'audio-drift'):self.validate()
    def test_latest_feedback_pending_blocks_even_consistent_updated_hashes(self):
        r=self.record();fb=json.loads(Path(r['feedbackInventory']['path']).read_text())
        fb.update(latestFeedbackIds=['latest'],items=[{'id':'latest','status':'PENDING','observation':'Synthetic current defect unresolved'}],unresolvedFeedbackIds=['latest'])
        r['feedbackInventory']=self.put(r['feedbackInventory'],fb);self.ref=self.put(self.ref,r)
        with self.assertRaisesRegex(ValueError,'feedback-unresolved'):self.validate()
    def test_teacher_approval_cannot_replace_audio_reply(self):
        r=self.record();accept=json.loads(Path(r['acceptanceEvidence']['path']).read_text())
        reply=json.loads(Path(accept['userReply']['path']).read_text());reply['reviewKind']='TEACHER_APPROVAL'
        accept['userReply']=self.put(accept['userReply'],reply);r['acceptanceEvidence']=self.put(r['acceptanceEvidence'],accept);self.ref=self.put(self.ref,r)
        with self.assertRaisesRegex(ValueError,'not-teacher-approval'):self.validate()
    def test_acceptance_basis_must_be_user_audio_review(self):
        r=self.record();accept=json.loads(Path(r['acceptanceEvidence']['path']).read_text());accept['basis']='TEACHER_APPROVAL'
        r['acceptanceEvidence']=self.put(r['acceptanceEvidence'],accept);self.ref=self.put(self.ref,r)
        with self.assertRaisesRegex(ValueError,'real-current-user-acceptance'):self.validate()
    def test_wrong_listening_copy_hash_blocks(self):
        r=self.record();r['listeningGain2']['sha256']='sha256:old';self.ref=self.put(self.ref,r)
        with self.assertRaisesRegex(ValueError,'copy-drift'):self.validate()
    def test_false_gain_receipt_cannot_override_actual_samples(self):
        r=self.record();copy_path=Path(r['listeningGain2']['path'])
        with wave.open(str(copy_path),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\xe9\x03'*16000)
        r['listeningGain2']=file_ref(copy_path);receipt=json.loads(Path(r['gainReceipt']['path']).read_text());receipt['outputSha256']=r['listeningGain2']['sha256']
        r['gainReceipt']=self.put(r['gainReceipt'],receipt);self.ref=self.put(self.ref,r)
        with self.assertRaisesRegex(ValueError,'not-exact-safe-gain-two'):self.validate()
    def test_receipt_sample_clock_must_match_actual_wav(self):
        r=self.record();receipt=json.loads(Path(r['gainReceipt']['path']).read_text());receipt['frames']+=1
        r['gainReceipt']=self.put(r['gainReceipt'],receipt);self.ref=self.put(self.ref,r)
        with self.assertRaisesRegex(ValueError,'receipt-sample-clock'):self.validate()
    def test_synthetic_audio_acceptance_class_is_rejected(self):
        r=self.record();accept=json.loads(Path(r['acceptanceEvidence']['path']).read_text());accept['evidenceClass']='SYNTHETIC_TEST'
        r['acceptanceEvidence']=self.put(r['acceptanceEvidence'],accept);self.ref=self.put(self.ref,r)
        with self.assertRaisesRegex(ValueError,'real-current-user-acceptance'):self.validate()
    def test_explicit_silent_source_classification_only_and_subtitle_scope(self):
        from dependency_proof import speech_checkpoint_required
        n='sha256:n';a='sha256:a';path=self.root/'silent.json'
        proof={'evidenceClass':'REAL_OBSERVATION','basis':'USER_SOURCE_CLASSIFICATION','status':'PASS','claim':'silent-content-scope',
            'nativeHash':n,'audioHash':a,'userQuote':'Synthetic explicit silent source classification'}
        path.write_text(json.dumps(proof));m={'branch':'CONTENT_EDIT','speechScope':{'mode':'SILENT_NO_SPEECH','evidence':file_ref(path)}}
        self.assertFalse(speech_checkpoint_required(m,n,a));self.assertFalse(speech_checkpoint_required({'branch':'SUBTITLE_ONLY'},n,a))
        m['speechScope'].pop('evidence')
        with self.assertRaises(ValueError):speech_checkpoint_required(m,n,a)

class AudioEditInventoryTests(unittest.TestCase):
    def setUp(self):
        from test_native_apply import NativeApplyTests
        self.f=NativeApplyTests('test_positive_consistency_path');self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root;self.ref=self.f.m['audioEditInventory']
    def record(self):return json.loads(Path(self.ref['path']).read_text())
    def put(self,ref,obj):
        p=Path(ref['path']);p.write_text(json.dumps(obj));return file_ref(p)
    def validate(self,mode='FINAL_ACCEPTANCE'):
        from dependency_proof import validate_audio_edit_inventory
        return validate_audio_edit_inventory(self.ref,file_ref(self.f.native),file_ref(self.f.audio),self.f.m['executionAudit'],mode,'synthetic-audio-task')
    def classify(self,kind,spans,basis='HUMAN_LISTENING'):
        r=self.record();row=r['candidates'][0];row.update(status='REVIEWED',observedKind=kind,observedQuietIntervals=spans)
        proof=json.loads(Path(row['evidence']['path']).read_text());proof.update(basis=basis,observedKind=kind,observedQuietIntervals=spans)
        row['evidence']=self.put(row['evidence'],proof);self.ref=self.put(self.ref,r)
    def test_explicit_observed_speech_can_clear_machine_candidate(self):
        self.assertEqual(self.validate()['status'],'ACTUAL_QUIET_REVIEW_CONSISTENT')
    def test_pending_is_provisional_only(self):
        r=self.record();r['candidates'][0].update(status='PENDING',observedKind='UNKNOWN',observedQuietIntervals=[])
        self.ref=self.put(self.ref,r);self.assertTrue(self.validate('REVIEW_DRAFT')['pendingCandidateIds'])
        with self.assertRaisesRegex(ValueError,'final-quiet-review'):self.validate()
    def test_omitting_machine_candidate_is_blocked(self):
        r=self.record();r['candidates'].pop();self.ref=self.put(self.ref,r)
        with self.assertRaisesRegex(ValueError,'all-candidate-coverage'):self.validate('REVIEW_DRAFT')
    def test_true_quiet_exact_cap_is_permitted(self):
        self.classify('TRUE_QUIET',[{'startTick':0,'endTick':200000}]);self.assertEqual(self.validate()['heldTrueQuietIntervals'],[])
    def test_true_quiet_over_cap_is_held(self):
        self.classify('TRUE_QUIET',[{'startTick':0,'endTick':200001}])
        with self.assertRaisesRegex(ValueError,'final-quiet-review'):self.validate()
        self.assertEqual(self.validate('REVIEW_DRAFT')['heldTrueQuietIntervals'][0]['endTick'],200001)
    def test_split_adjacent_quiet_spans_cannot_evade_cap(self):
        self.classify('TRUE_QUIET',[{'startTick':0,'endTick':150000},{'startTick':150000,'endTick':300000}])
        with self.assertRaisesRegex(ValueError,'final-quiet-review'):self.validate()
    def exception(self,kind='QUIET_LIMIT_EXCEPTION'):
        r=self.record();row=r['candidates'][0];quote='Synthetic exact exception declaration, not a real user decision'
        reply=self.f.proof('synthetic-quiet-reply',source='DIRECT_USER_MESSAGE',reviewKind=kind,sourceRef='synthetic fixture',message=quote)
        proof=self.f.proof('synthetic-quiet-exception',schema='capcut-quiet-limit-exception/v1',
            taskId='synthetic-audio-task',candidateId=row['id'],startTick=0,endTick=200001,
            maxActualRetainedQuietTicks=200000,userQuote=quote,userReply=reply)
        data=json.loads(Path(proof['path']).read_text());data.update(status='ACCEPTED',basis='USER_EXPLICIT_QUIET_EXCEPTION')
        row['exceptionEvidence']=self.put(proof,data);self.ref=self.put(self.ref,r)
    def test_exact_separate_user_exception_can_clear_one_over_cap_span(self):
        self.classify('TRUE_QUIET',[{'startTick':0,'endTick':200001}]);self.exception()
        self.assertEqual(self.validate()['heldTrueQuietIntervals'],[])
    def test_teacher_decision_cannot_supply_quiet_exception(self):
        self.classify('TRUE_QUIET',[{'startTick':0,'endTick':200001}]);self.exception('TEACHER_APPROVAL')
        with self.assertRaisesRegex(ValueError,'direct-quiet-exception'):self.validate()
    def test_generic_protection_is_not_actual_speech_classification(self):
        self.classify('SPEECH_OR_NOT_QUIET',[],basis='GENERIC_PROTECTION')
        with self.assertRaisesRegex(ValueError,'not-generic-protection'):self.validate()
    def test_original_raw_interval_with_empty_asr_ids_stays_reversible(self):
        from dependency_proof import make_audio_edit_inventory
        policy=self.source_policy();obs=json.loads(Path(policy['sourceEditObservations']['path']).read_text())
        new=make_audio_edit_inventory(file_ref(self.f.native),file_ref(self.f.audio),self.f.m['executionAudit'],policy,{'src':'src'})
        row=new['sourceRemovals'][0];self.assertEqual(row['reversal']['originalRawWordIds'],[])
        self.assertEqual(row['originalObservation'],obs['removals'][0]);self.assertTrue(row['currentRetainedIntersections'])
        self.assertEqual(row['phoneAndMeaningReview'],'PENDING_AUDIO_CONTINUITY')
    def source_policy(self):
        source=self.root/'context-source.bin';source.write_bytes(b'synthetic source identity, not actual media')
        native=json.loads(self.f.native.read_text());native['materials']['videos']=[{'id':'src','path':str(source)}]
        self.f.native.write_text(json.dumps(native));self.f.m['native']=file_ref(self.f.native)
        self.f.audit['nativeHash']=file_ref(self.f.native)['sha256'];self.f.save_audit();self.ref=self.f.m['audioEditInventory']
        probe=self.f.proof('synthetic-source-identity',sources=[{'path':str(source),'sha256':file_ref(source)['sha256'],'durationTicks':1000000}])
        r=self.record();obs_ref=r['sourceEditObservations'];obs={'evidenceClass':'REAL_OBSERVATION',
            'sourceIdentity':probe,'originalSourceSHA256':file_ref(source)['sha256'],'removals':[{
            'id':'unmapped-filler','originalSourceInterval':{'sourceId':'src','startTick':400000,'endTick':600000},
            'oldTargetIntervals':[{'sourceStartTick':400000,'sourceEndTick':600000,'oldTargetStartTick':400000,'oldTargetEndTick':600000}],
            'rawWordIds':[],'contextualReason':'Synthetic contextual hesitation trial; meaningful or quoted words must stay'}]}
        r['sourceEditObservations']=self.put(obs_ref,obs)
        return {k:r[k] for k in ('maxActualRetainedQuietTicks','rawSourceWords','rawTranscript','sourceEditObservations','removedContentRawWordIds')}
    def test_missing_material_mapping_cannot_fake_removed_source_interval(self):
        from dependency_proof import make_audio_edit_inventory
        policy=self.source_policy()
        with self.assertRaisesRegex(ValueError,'not-current-main-material'):
            make_audio_edit_inventory(file_ref(self.f.native),file_ref(self.f.audio),self.f.m['executionAudit'],policy,{'src':'MISSING_NATIVE_MATERIAL'})
    def test_source_probe_must_identify_actual_native_source(self):
        from dependency_proof import make_audio_edit_inventory
        policy=self.source_policy();obs=json.loads(Path(policy['sourceEditObservations']['path']).read_text());obs['originalSourceSHA256']='sha256:wrong'
        policy['sourceEditObservations']=self.put(policy['sourceEditObservations'],obs)
        with self.assertRaisesRegex(ValueError,'source-identity-or-bounds'):
            make_audio_edit_inventory(file_ref(self.f.native),file_ref(self.f.audio),self.f.m['executionAudit'],policy,{'src':'src'})
    def filler_context(self,policy,attachment):
        obs=json.loads(Path(policy['sourceEditObservations']['path']).read_text());row=obs['removals'][0]
        context=self.f.proof('filler-attachment-review',sourceHash=obs['originalSourceSHA256'],
            originalSourceInterval=row['originalSourceInterval'],detectionStatus='DETECTED',attachment=attachment)
        row['fillerContext']={'detectionStatus':'DETECTED','attachment':attachment,'evidence':context}
        policy['sourceEditObservations']=self.put(policy['sourceEditObservations'],obs);return policy
    def test_detected_isolated_filler_cannot_remain_even_in_draft(self):
        from dependency_proof import make_audio_edit_inventory
        policy=self.filler_context(self.source_policy(),'ISOLATED_BETWEEN_PAUSES')
        with self.assertRaisesRegex(ValueError,'unresolved-isolated-detected-filler'):
            make_audio_edit_inventory(file_ref(self.f.native),file_ref(self.f.audio),self.f.m['executionAudit'],policy,{'src':'src'})
    def test_attached_filler_may_be_held_with_actual_reason_and_separate_audio_gate(self):
        from dependency_proof import make_audio_edit_inventory
        policy=self.filler_context(self.source_policy(),'ATTACHED_TO_CONTENT');baseline=self.record()
        record=make_audio_edit_inventory(file_ref(self.f.native),file_ref(self.f.audio),self.f.m['executionAudit'],policy,{'src':'src'})
        record['candidates']=baseline['candidates'];row=record['sourceRemovalReviews'][0]
        row.update(status='HELD_FOR_PHONETIC_SAFETY',contextualRole='HESITATION_OR_FILLER',
            decision='RETAIN_ATTACHED_FOR_PHONETIC_SAFETY',reason='Synthetic listening declaration: tighter cut risks adjacent consonant')
        row['evidence']=self.f.proof('source-removal-context-review',removalId=row['id'],
            originalSourceInterval=record['sourceRemovals'][0]['originalObservation']['originalSourceInterval'],
            contextualRole=row['contextualRole'],decision=row['decision'],rawWordIds=[],reason=row['reason'])
        self.ref=self.put(self.ref,record);result=self.validate()
        self.assertEqual(len(result['attachedFillerSafetyHolds']),1)
        self.assertTrue(result['attachedFillerSafetyHolds'][0]['requiresSeparateCurrentUserAudioAcceptance'])
    def test_unknown_or_reasonless_filler_cannot_be_a_blanket_safety_hold(self):
        from dependency_proof import make_audio_edit_inventory
        policy=self.source_policy();baseline=self.record()
        record=make_audio_edit_inventory(file_ref(self.f.native),file_ref(self.f.audio),self.f.m['executionAudit'],policy,{'src':'src'})
        record['candidates']=baseline['candidates'];record['sourceRemovalReviews'][0].update(status='HELD_FOR_PHONETIC_SAFETY',
            contextualRole='HESITATION_OR_FILLER',decision='RETAIN_ATTACHED_FOR_PHONETIC_SAFETY')
        self.ref=self.put(self.ref,record)
        with self.assertRaisesRegex(ValueError,'contextual-filler-or-meaningful'):self.validate()
    def test_missing_explicit_removed_content_ids_is_blocked(self):
        r=self.record();r.pop('removedContentRawWordIds');self.ref=self.put(self.ref,r)
        with self.assertRaisesRegex(ValueError,'explicit-removed-content'):self.validate('REVIEW_DRAFT')
    def test_current_wav_drift_invalidates_inventory(self):
        with wave.open(str(self.f.audio),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*15999)
        with self.assertRaisesRegex(ValueError,'current-binding'):self.validate('REVIEW_DRAFT')
    def test_one_supplied_review_document_keeps_unreviewed_candidates_pending(self):
        from dependency_proof import apply_audio_edit_review
        record=self.record();first=copy.deepcopy(record['candidates'][0]);first.pop('evidence')
        review=self.f.proof('audio-edit-review',schema='capcut-audio-edit-review/v1',
            sourceEditObservations=record['sourceEditObservations'],candidateReviews=[first],sourceRemovalReviews=[])
        for row in record['candidates']:row.update(status='PENDING',observedKind='UNKNOWN',observedQuietIntervals=[],evidence=None)
        self.ref=self.put(self.ref,apply_audio_edit_review(record,review))
        result=self.validate('REVIEW_DRAFT');self.assertEqual(len(result['pendingCandidateIds']),3)
        with self.assertRaisesRegex(ValueError,'final-quiet-review'):self.validate()
    def test_synthetic_review_document_cannot_supply_actual_classifications(self):
        from dependency_proof import apply_audio_edit_review
        record=self.record();review=self.f.proof('audio-edit-review',schema='capcut-audio-edit-review/v1',
            sourceEditObservations=record['sourceEditObservations'],candidateReviews=[],sourceRemovalReviews=[])
        obj=json.loads(Path(review['path']).read_text());obj['evidenceClass']='SYNTHETIC_TEST';review=self.put(review,obj)
        with self.assertRaisesRegex(ValueError,'supplied-actual-review'):apply_audio_edit_review(record,review)
    def test_review_row_cannot_override_stale_common_audio_identity(self):
        record=self.record();row=copy.deepcopy(record['candidates'][0]);row.pop('evidence')
        row.update(audioHash=file_ref(self.f.audio)['sha256'],nativeHash=file_ref(self.f.native)['sha256'],evidenceClass='REAL_OBSERVATION')
        proof=self.f.proof('audio-edit-review',schema='capcut-audio-edit-review/v1',
            sourceEditObservations=record['sourceEditObservations'],candidateReviews=[row],sourceRemovalReviews=[])
        obj=json.loads(Path(proof['path']).read_text());obj['audioHash']='sha256:stale';proof=self.put(proof,obj)
        record['candidates'][0]['evidence']=proof;self.ref=self.put(self.ref,record)
        with self.assertRaisesRegex(ValueError,'actual-listening-basis'):self.validate('REVIEW_DRAFT')

class RawSourceCompletenessTests(unittest.TestCase):
    def setUp(self):
        from test_native_apply import NativeApplyTests
        self.f=NativeApplyTests('test_positive_consistency_path');self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root
        self.transcript={'sourceAudioSha256':'synthetic original audio hash','segments':[{'id':1,'words':[
            {'word':' a','start':0.1,'end':0.2,'probability':0.5},
            {'word':' b','start':0.3,'end':0.4,'probability':0.6}]}]}
        self.tr=self.put('original-asr.json',self.transcript)
        self.raw={'asrSha256':self.tr['sha256'],'sourceAudioSha256':self.transcript['sourceAudioSha256'],'words':[
            {'id':'W00001','segmentId':1,'rawText':' a','sourceStartSeconds':0.1,'sourceEndSeconds':0.2,'probability':0.5},
            {'id':'W00002','segmentId':1,'rawText':' b','sourceStartSeconds':0.3,'sourceEndSeconds':0.4,'probability':0.6}]}
        self.policy={'maxActualRetainedQuietTicks':200000,'rawSourceWords':self.put('raw.json',self.raw),'rawTranscript':self.tr,
            'sourceEditObservations':self.put('source-edits.json',{'evidenceClass':'REAL_OBSERVATION','removals':[],
                'originalRawASRSha256':self.tr['sha256']}),'removedContentRawWordIds':[]}
    def put(self,name,value):
        p=self.root/name;p.write_text(json.dumps(value));return file_ref(p)
    def make(self):
        from dependency_proof import make_audio_edit_inventory
        return make_audio_edit_inventory(file_ref(self.f.native),file_ref(self.f.audio),self.f.m['executionAudit'],self.policy,{'src':'src'})
    def test_full_original_word_record_is_kept(self):self.assertEqual(len(self.make()['candidates']),4)
    def test_selected_adapter_cannot_claim_full_original_asr_hash(self):
        self.raw['words'].pop();self.policy['rawSourceWords']=self.put('raw.json',self.raw)
        with self.assertRaisesRegex(ValueError,'full-original-transcript-word-coverage'):self.make()
    def test_duplicate_stable_raw_ids_are_rejected(self):
        self.raw['words'][1]['id']='W00001';self.policy['rawSourceWords']=self.put('raw.json',self.raw)
        with self.assertRaisesRegex(ValueError,'raw-ids-missing-or-duplicate'):self.make()
    def test_changed_original_word_clock_cannot_be_hidden_in_wrapper(self):
        self.raw['words'][1]['sourceEndSeconds']=0.5;self.policy['rawSourceWords']=self.put('raw.json',self.raw)
        with self.assertRaisesRegex(ValueError,'full-original-transcript-word-coverage'):self.make()
    def test_original_transcript_reference_is_required(self):
        self.policy.pop('rawTranscript')
        with self.assertRaisesRegex(ValueError,'hash-bound-reference-required'):self.make()
    def test_omitting_both_asr_claims_cannot_omit_original_anchor(self):
        self.raw.pop('asrSha256');self.policy['rawSourceWords']=self.put('raw.json',self.raw)
        obj=json.loads(Path(self.policy['sourceEditObservations']['path']).read_text());obj.pop('originalRawASRSha256')
        self.policy['sourceEditObservations']=self.put('source-edits.json',obj);self.policy.pop('rawTranscript')
        with self.assertRaisesRegex(ValueError,'hash-bound-reference-required'):self.make()

class DependencyProofTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source=self.root/'source.mp4';self.source.write_bytes(b'synthetic source, not media proof')
        self.audio=self.root/'audio.wav'
        with wave.open(str(self.audio),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*16000)
        self.d={'duration':1000000,'fps':30,'materials':{'videos':[{'id':'src','type':'video','path':str(self.source)},
            {'id':'unused','type':'video','path':str(self.source)}],
            'texts':[{'id':'txt','content':json.dumps({'text':'nhà','styles':[{'size':20}]})}]},
            'tracks':[{'id':'main','type':'video','segments':[{'id':'clip','material_id':'src','speed':1,'volume':1,
                'source_timerange':{'start':0,'duration':1000000},'target_timerange':{'start':0,'duration':1000000}}]},
            {'id':'captions','type':'text','segments':[{'id':'cue','material_id':'txt','target_timerange':{'start':0,'duration':1000000}}]}]}
        self.old=self.put('old.json',self.d);self.new=self.put('new.json',self.d)
    def put(self,name,obj):
        p=self.root/name;p.write_text(json.dumps(obj),encoding='utf-8');return file_ref(p)
    def proof(self,claim):
        source_dependencies={} if claim in ('caption-policy-review','caption-style-binding') else {str(self.source):file_ref(self.source)['sha256']}
        basis='SUPPORTED_TEXT_REVIEW' if claim in ('caption-policy-review','caption-style-binding') else 'HUMAN_VISUAL_REVIEW' if claim=='broll-whole-timeline-review' else 'HUMAN_LISTENING'
        return self.put('observation.json',{'evidenceClass':'REAL_OBSERVATION','status':'PASS',
            'basis':basis,'reviewer':'simulated-test-reviewer',
            'observation':'Synthetic declaration only; no listening observation',
            'claim':claim,'nativeHash':self.old['sha256'],'audioHash':file_ref(self.audio)['sha256'],
            'sourceDependencies':source_dependencies})
    def adopt(self,claim):
        proof=self.proof(claim)
        return make_adoption(proof,self.old,self.new,file_ref(self.audio),file_ref(self.audio),'main')
    def change(self,fn):
        updated=copy.deepcopy(self.d);fn(updated);self.new=self.put('new.json',updated)
    def test_app_removal_of_unused_material_is_equivalent(self):
        self.change(lambda d:d['materials']['videos'].pop())
        for claim in ('audio-clock-binding','caption-first-phoneme','caption-policy-review','caption-style-binding','broll-whole-timeline-review'):
            record=self.adopt(claim);self.assertEqual(record['status'],'DEPENDENCIES_EQUIVALENT')
            ref=self.put('adoption.json',record)
            self.assertFalse(validate_adoption(ref,record['oldEvidence'],self.new,file_ref(self.audio))['newHearingClaimed'])
    def test_active_caption_clock_reopens_onset(self):
        self.change(lambda d:d['tracks'][1]['segments'][0]['target_timerange'].update(start=1,duration=999999))
        self.assertEqual(self.adopt('caption-first-phoneme')['status'],'DEPENDENCIES_CHANGED')
    def test_active_caption_text_reopens_text_review(self):
        self.change(lambda d:d['materials']['texts'][0].update(content=json.dumps({'text':'khác'})))
        self.assertEqual(self.adopt('caption-policy-review')['status'],'DEPENDENCIES_CHANGED')
    def test_source_clock_change_reopens_audio(self):
        self.change(lambda d:d['tracks'][0]['segments'][0]['source_timerange'].update(start=1))
        self.assertEqual(self.adopt('audio-clock-binding')['status'],'DEPENDENCIES_CHANGED')
    def test_speed_change_reopens_audio(self):
        self.change(lambda d:d['tracks'][0]['segments'][0].update(speed=2))
        self.assertEqual(self.adopt('caption-first-phoneme')['status'],'DEPENDENCIES_CHANGED')
    def test_main_gain_change_reopens_audio(self):
        self.change(lambda d:d['tracks'][0]['segments'][0].update(volume=2))
        self.assertEqual(self.adopt('all-pause-audit')['status'],'DEPENDENCIES_CHANGED')
    def test_style_change_reopens_style_but_not_hearing(self):
        self.change(lambda d:d['materials']['texts'][0].update(content=json.dumps({'text':'nhà','styles':[{'size':21}]})))
        self.assertEqual(self.adopt('caption-style-binding')['status'],'DEPENDENCIES_CHANGED')
        self.assertEqual(self.adopt('broll-whole-timeline-review')['status'],'DEPENDENCIES_CHANGED')
        self.assertEqual(self.adopt('caption-first-phoneme')['status'],'DEPENDENCIES_EQUIVALENT')
    def test_whole_inventory_change_reopens_visual_review(self):
        self.change(lambda d:d['tracks'].append({'id':'overlay','type':'effect','segments':[]}))
        self.assertEqual(self.adopt('broll-whole-timeline-review')['status'],'DEPENDENCIES_CHANGED')
    def supporting_layer(self,volume):
        def add(d):
            clip=copy.deepcopy(d['tracks'][0]['segments'][0]);clip.update(id='supporting',volume=volume)
            d['tracks'].append({'id':'support-track','type':'video','segments':[clip]})
        self.change(add)
    def test_silent_supporting_layer_preserves_audio_but_reopens_inventory(self):
        self.supporting_layer(0)
        self.assertEqual(self.adopt('caption-first-phoneme')['status'],'DEPENDENCIES_EQUIVALENT')
        self.assertEqual(self.adopt('broll-whole-timeline-review')['status'],'DEPENDENCIES_CHANGED')
    def test_unmuted_supporting_layer_changes_audio_dependency(self):
        self.supporting_layer(1)
        self.assertEqual(self.adopt('caption-first-phoneme')['status'],'DEPENDENCIES_CHANGED')
    def test_same_path_source_overwrite_cannot_rebind_old_observation(self):
        ref=self.proof('audio-clock-binding');self.source.write_bytes(b'changed source at same path')
        with self.assertRaisesRegex(ValueError,'original-source-dependencies'):
            make_adoption(ref,self.old,self.new,file_ref(self.audio),file_ref(self.audio),'main')
    def test_adoption_tampering_or_other_target_rejected(self):
        record=self.adopt('caption-first-phoneme');record['before']['audio']='sha256:invented'
        with self.assertRaises(ValueError):validate_adoption(self.put('adoption.json',record),record['oldEvidence'],self.new,file_ref(self.audio))
    def test_synthetic_evidence_cannot_be_adopted_as_real(self):
        ref=self.proof('caption-first-phoneme');obj=json.loads(Path(ref['path']).read_text());obj['evidenceClass']='SYNTHETIC_FIXTURE';ref=self.put('observation.json',obj)
        with self.assertRaises(ValueError):make_adoption(ref,self.old,self.new,file_ref(self.audio),file_ref(self.audio),'main')
    def test_historic_source_hash_cannot_be_inferred_from_current_path(self):
        ref=self.proof('audio-clock-binding');obj=json.loads(Path(ref['path']).read_text());obj.pop('sourceDependencies')
        ref=self.put('observation.json',obj)
        with self.assertRaises(ValueError):make_adoption(ref,self.old,self.new,file_ref(self.audio),file_ref(self.audio),'main')

class ExactInheritedPhaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source=self.root/'source.mp4';self.source.write_bytes(b'synthetic source')
        self.segment={'id':'inherited','material_id':'broll','speed':1,'volume':0,
            'source_timerange':{'start':0,'duration':6533333},'target_timerange':{'start':0,'duration':6533334}}
        self.d={'fps':30,'duration':7000000,'materials':{'videos':[{'id':'broll','type':'video','path':str(self.source)}]},
            'tracks':[{'id':'main','type':'video','segments':[]},{'id':'support','type':'video','segments':[self.segment]}]}
        self.baseline=self.put('baseline.json',self.d)
        self.record={'schema':'capcut-native-phase/v1','baseline':self.baseline,'rationalFps':{'numerator':30,'denominator':1},
            'inheritedRanges':[{'segmentId':'inherited','materialId':'broll','sourceInTick':0,'sourceOutTick':6533333,
                'startTick':0,'endTick':6533334,'frameCount':196}]}
        self.ref=self.put('phase.json',self.record)
    def put(self,name,obj):
        p=self.root/name;p.write_text(json.dumps(obj),encoding='utf-8');return file_ref(p)
    def test_exact_inherited_geometry_uses_actual_target_end(self):
        row=native_broll_inventory(self.d,'main',self.ref)[0]
        self.assertEqual(row['sourceOutTick'],6533333);self.assertEqual(row['endTick'],6533334)
    def test_unbound_one_tick_is_not_a_tolerance(self):
        with self.assertRaises(ValueError):native_broll_inventory(self.d,'main')
    def test_changed_one_tick_phase_is_rejected(self):
        self.segment['target_timerange']['duration']-=2
        with self.assertRaises(ValueError):native_broll_inventory(self.d,'main',self.ref)
    def test_invented_current_row_cannot_replace_baseline_geometry(self):
        self.record['inheritedRanges'][0]['sourceOutTick']-=1;self.ref=self.put('phase.json',self.record)
        with self.assertRaises(ValueError):validate_native_phase(self.ref,'inherited','broll',0,6533332,0,6533334,currentFps=30)
    def test_wrong_rational_frame_count_is_rejected(self):
        self.record['inheritedRanges'][0]['frameCount']=195;self.ref=self.put('phase.json',self.record)
        with self.assertRaises(ValueError):native_broll_inventory(self.d,'main',self.ref)
    def test_current_fps_change_cannot_borrow_old_rational_phase(self):
        self.d['fps']=60
        with self.assertRaises(ValueError):native_broll_inventory(self.d,'main',self.ref)
    def test_larger_inherited_phase_fails_rational_quantization(self):
        self.segment['source_timerange']['duration']=6533332;self.baseline=self.put('baseline.json',self.d)
        self.record['baseline']=self.baseline;self.record['inheritedRanges'][0]['sourceOutTick']=6533332;self.ref=self.put('phase.json',self.record)
        with self.assertRaises(ValueError):native_broll_inventory(self.d,'main',self.ref)

class BrollPreparationRegressionTests(unittest.TestCase):
    def setUp(self):
        from test_native_apply import NativeBrollAuditTests
        self.f=NativeBrollAuditTests('test_complete_native_broll_inventory_is_consistent_only')
        self.f.setUp();self.addCleanup(self.f.doCleanups)
    def test_explicit_provisional_checkpoint_does_not_need_fake_acceptance(self):
        from prepare_cut import prepare_broll
        f=self.f;path=f.root/'authority.json'
        path.write_text(json.dumps({'evidenceClass':'REAL_OBSERVATION','authority':'explicit-user-request',
            'claim':'review-draft-native-apply','mode':'REVIEW_DRAFT','userQuote':'Synthetic explicit review draft choice'}))
        f.plan.update(mode='REVIEW_DRAFT',contentCaptionCheckpoint='PROVISIONAL_PREPARED',
            baseCheckpointEvidenceBasis='STRUCTURAL_PREPARATION',reviewDraftAuthority=file_ref(path))
        report=json.loads(prepare_broll(f.plan)['broll-report.json'])
        self.assertEqual(report['baseCheckpoint'],'PROVISIONAL_PREPARED')
        self.assertEqual(report['nativeAcceptance'],'PENDING')
        f.plan.pop('mode')
        with self.assertRaises(ValueError):prepare_broll(f.plan)
    def test_preparation_preserves_actual_inherited_source_duration(self):
        from prepare_cut import prepare_broll
        f=self.f;draft=copy.deepcopy(f.d);draft['fps']=30
        segment=draft['tracks'][-1]['segments'][0]
        segment['source_timerange']['duration']=6533333;segment['target_timerange']['duration']=6533334
        base=f.root/'phase-baseline.json';base.write_text(json.dumps(draft))
        phase={'schema':'capcut-native-phase/v1','baseline':file_ref(base),'rationalFps':{'numerator':30,'denominator':1},
            'inheritedRanges':[{'segmentId':'new','materialId':'matA','sourceInTick':0,'sourceOutTick':6533333,
                'startTick':0,'endTick':6533334,'frameCount':196}]}
        p=f.root/'phase.json';p.write_text(json.dumps(phase));f.plan['nativePhaseEvidence']=file_ref(p)
        f.plan['sources'][0]['nativeMaterialId']='matA'
        frozen=json.loads(f.base.read_text());frozen['fps']=30;f.base.write_text(json.dumps(frozen))
        f.plan['baseSnapshot']['sha256']=file_ref(f.base)['sha256'];f.plan['sourceUsageReview']['baseSnapshotSha256']=file_ref(f.base)['sha256'];f.review_placements()
        f.plan['captionCues'][0]['endTick']=6533334;f.plan['captionCues'][1]['startTick']=6533334
        f.plan['placements'][0].update(endTick=6533334,sourceOutTick=6533333)
        outputs=prepare_broll(f.plan);spec=json.loads(outputs['broll-spec.json']);report=json.loads(outputs['broll-report.json'])
        self.assertEqual(spec['track']['items'][0]['durationTicks'],6533334)
        self.assertEqual(spec['track']['items'][0]['sourceDurationTicks'],6533333)
        self.assertEqual(report['placements'][0]['sourceOutTick'],6533333)
        f.plan.pop('nativePhaseEvidence')
        with self.assertRaises(ValueError):prepare_broll(f.plan)

if __name__=='__main__':unittest.main()
