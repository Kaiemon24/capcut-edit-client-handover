"""Synthetic task-local preparation fixtures; no real audio or native acceptance."""
import copy,json,tempfile,unittest,wave
from pathlib import Path
from dependency_proof import file_ref
from prepare_review_draft import prepare,_rebind_identical_audio_acceptance

class ReviewPreparationTests(unittest.TestCase):
    def setUp(self):
        from test_native_timeline import ProducerTests
        self.f=ProducerTests('test_editable_objects_original_handles_and_sidecars');self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root;p=self.f.plan
        p['mainPieces']=[{'id':'main','sourceId':'s0','sourceInTicks':0,'sourceOutTicks':12000000,'targetInTicks':0}]
        texts=['nhà','đường','phố','đẹp']
        p['captions']=[{'id':'c'+str(i),'text':text,'rawWordIds':['w'+str(i)],'startTicks':i*3000000,
            'endTicks':(i+1)*3000000,'style':{}} for i,text in enumerate(texts)]
        for i,b in enumerate(p['broll']):b['targetInTicks']=i*3000000
        self.f.compile();self.compiled=self.f.output;m=self.f.manifest;ph='sha256:'+m['planSHA256']
        self.audio=self.root/'final.wav'
        with wave.open(str(self.audio),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*(12*16000))
        self.style=self.put('style.json',{'id':'synthetic-style'})
        self.decision={'schema':'capcut-review-draft-decision/v1','evidenceClass':'REAL_OBSERVATION','authority':'explicit-user-request',
            'mode':'REVIEW_DRAFT','taskId':'synthetic-task','destinationPath':str(self.root/'new-project'),
            'projectName':m['name'],'sourceIds':[s['id'] for s in p['sources']],
            'userQuote':'Synthetic explicit selection of separate provisional review project'}
        self.semantic={'schema':'capcut-caption-preparation-review/v1','evidenceClass':'REAL_OBSERVATION',
            'status':'PASS','basis':'SUPPORTED_TEXT_REVIEW','reviewer':'simulated-test-reviewer',
            'observation':'Synthetic text review fixture, never hearing','planHash':ph,
            'words':[{'id':'w'+str(i),'text':text,'sentenceId':'sentence'+str(i),'sourceId':'s0',
                'sourceStartTick':i*3000000+100000,'sourceEndTick':i*3000000+600000} for i,text in enumerate(texts)],
            'cues':[{'id':c['id'],'rawWordIds':c['rawWordIds'],'nativeText':c['text']} for c in p['captions']],
            'protectedSpans':[],'acceptedLockBaseline':self.put('locks.json',{'protectedSpans':[]}),
            'styleProfile':self.style,'styleObservation':'Synthetic planned native fields bind selected style, native pixels pending'}
        probe={'status':'FRESH_FULL_HASH_AND_FFPROBE_PASS_NOT_HEARD','sources':[{'path':s['path'],'sha256':s['sha256'],
            'durationTicks':s['durationTicks'],'unchangedStatBeforeAfter':True,'probeCommand':['synthetic probe never executed']} for s in p['sources']]}
        projection={'evidenceClass':'REAL_OBSERVATION','status':'PASS_STRUCTURAL_NOT_HEARD','planHash':ph,
            'audioHash':file_ref(self.audio)['sha256'],'mainPieces':p['mainPieces'],'gain':1,
            'reviewer':'simulated-test-reviewer','observation':'Synthetic source-clock projection; no hearing claim'}
        srcs=[{'sourceId':s['id'],'permitted':True,'rightsEvidenceRef':'synthetic explicit scope','sourceOrigin':'CAMERA',
            'voiceClassification':'NO_VOICE','classificationReview':{'reviewed':True,'evidenceRef':'synthetic classification',
                'evidenceBasis':'USER_REPORTED'}} for s in p['sources'][1:]]
        eligible=[{'sourceId':s['id'],'status':'ELIGIBLE','windows':[{'sourceInTick':5000000,'sourceOutTick':26000000}],
            'reason':'Synthetic imagery role','evidenceRef':'synthetic exhaustive eligibility'} for s in p['sources'][1:]]
        broll={'schema':'capcut-broll-preparation-review/v1','evidenceClass':'REAL_OBSERVATION','status':'PASS',
            'planHash':ph,'reviewer':'simulated-test-reviewer','observation':'Synthetic three distinct source plan',
            'evidenceBasis':'USER_REPORTED','sources':srcs,'placements':[{'id':b['id'],'startCaptionId':'c'+str(i),
                'lastCaptionId':'c'+str(i),'meaningReview':{'reviewed':True,'evidenceRef':'synthetic meaning',
                    'relevance':'Synthetic supplied role','addedInformation':'Synthetic supporting detail',
                    'startSelectionReason':'Existing caption onset'},'eligibleSources':copy.deepcopy(eligible)} for i,b in enumerate(p['broll'])]}
        self.input={'schema':'capcut-review-draft-input/v1','taskId':'synthetic-task','destinationPath':self.decision['destinationPath'],
            'decision':self.put('decision.json',self.decision),'styleProfile':self.style,'sourceProbe':self.put('probe.json',probe),
            'captionReview':self.put('semantic.json',self.semantic),'audioProjection':self.put('projection.json',projection),
            'pauseProfile':{'windowMs':20,'hopMs':5,'methods':[{'kind':'RMS','thresholdsDbFS':[-50,-45]},
                {'kind':'PEAK','thresholdsDbFS':[-40,-35]}]},'pacingIntervals':[],
            'contentReview':{'status':'PROVISIONAL_MODEL_ONLY','wordTimingBasis':'MODEL_ONLY',
                'takeGroups':[{'id':'take','status':'PENDING','observation':'Synthetic ASR-only choice'}],
                'uncertainties':[{'id':'all','kind':'AUDIO_TRUTH','observation':'No fixture can prove speech'}]},
            'brollReview':self.put('broll-review.json',broll)}
        from test_dependency_proof import audio_review_fixture
        self.input['audioReview']=audio_review_fixture(self.root,self.audio,'synthetic-task',self.input['audioProjection'])['input']
        from test_dependency_proof import source_word_fixture
        self.input['audioEditPolicy']={'maxActualRetainedQuietTicks':200000,
            **source_word_fixture(self.root,self.semantic['words']),
            'sourceEditObservations':self.put('source-edits.json',{'evidenceClass':'REAL_OBSERVATION','removals':[]}),
            'removedContentRawWordIds':[]}
    def put(self,name,obj):
        p=self.root/name;p.write_text(json.dumps(obj),encoding='utf-8');return file_ref(p)
    def run_prepare(self):return prepare(self.compiled,self.audio,self.input,self.root/'prepared')
    def test_builds_all_pending_evidence_without_manual_native_ids_or_hearing(self):
        result=self.run_prepare();self.assertEqual(result['status'],'PROVISIONAL_NOT_ACCEPTED',
            json.loads(Path(result['guardResult']['path']).read_text()))
        manifest=json.loads(Path(result['manifest']['path']).read_text());guard=json.loads(Path(result['guardResult']['path']).read_text())
        self.assertEqual(len(manifest['onsets']),4);self.assertTrue(all(r['status']=='PENDING' for r in manifest['onsets']))
        self.assertEqual(len(guard['pendingQuality']['pauseCandidates']),4)
        self.assertFalse(result['finalAcceptance']);self.assertEqual(result['nativeStoreWrites'],0)
        self.assertEqual(len(json.loads((self.root/'prepared/broll-report.json').read_text())['placements']),3)
    def test_text_review_cannot_be_generated_from_model_flag(self):
        self.semantic['status']='MODEL_ONLY';self.input['captionReview']=self.put('semantic.json',self.semantic)
        with self.assertRaisesRegex(ValueError,'actual-text-review'):self.run_prepare()
    def test_missing_user_decision_is_not_invented(self):
        self.input.pop('decision')
        with self.assertRaises(ValueError):self.run_prepare()
    def test_synthetic_fixture_decision_is_not_real_authority(self):
        self.decision['evidenceClass']='SYNTHETIC_FIXTURE';self.input['decision']=self.put('decision.json',self.decision)
        with self.assertRaisesRegex(ValueError,'explicit-decision'):self.run_prepare()
    def test_changed_cue_review_is_blocked(self):
        self.semantic['cues'][0]['nativeText']='khác';self.input['captionReview']=self.put('semantic.json',self.semantic)
        with self.assertRaisesRegex(ValueError,'caption-mismatch'):self.run_prepare()
    def test_audio_projection_must_bind_exact_final_wav(self):
        ref=self.input['audioProjection'];obj=json.loads(Path(ref['path']).read_text());obj['audioHash']='sha256:old'
        self.input['audioProjection']=self.put('projection.json',obj)
        with self.assertRaisesRegex(ValueError,'audio-projection'):self.run_prepare()
    def test_existing_output_is_preserved(self):
        out=self.root/'prepared';out.mkdir();(out/'keep.txt').write_text('keep')
        with self.assertRaisesRegex(ValueError,'already-exists'):self.run_prepare()
        self.assertEqual((out/'keep.txt').read_text(),'keep')
    def test_explicit_model_overlap_scope_is_carried_without_new_hearing(self):
        self.decision.update(allowModelWordIntervalOverlap=True,
            scopeInterpretation='Synthetic separate draft scope; no heard approval',
            provisionalCutScope={'mainPieces':1,'candidateDurationSeconds':12,'detectorQuietRemovals':0,'speechFacingHandlesMs':100})
        self.input['decision']=self.put('decision.json',self.decision);result=self.run_prepare()
        self.assertEqual(result['status'],'PROVISIONAL_NOT_ACCEPTED')
        manifest=json.loads(Path(result['manifest']['path']).read_text())
        authority=json.loads(Path(manifest['reviewDraft']['authorityEvidence']['path']).read_text())
        self.assertTrue(authority['allowModelWordIntervalOverlap']);self.assertEqual(authority['originalDecision'],self.input['decision'])
        self.assertEqual(authority['provisionalCutScope'],self.decision['provisionalCutScope'])
    def test_missing_user_audio_acceptance_builds_preparation_but_blocks_apply(self):
        self.input.pop('audioReview');result=self.run_prepare()
        self.assertEqual(result['status'],'BLOCKED');self.assertFalse(result['passed'])
        self.assertTrue((self.root/'prepared/review-manifest.json').is_file())
        checkpoint=json.loads((self.root/'prepared/audio-review-checkpoint.json').read_text())
        self.assertEqual(checkpoint['status'],'PENDING_USER_AUDIO_REVIEW')

    def test_layout_clock_metadata_rebinds_without_new_user_decision(self):
        old_ref=self.input['audioReview']['acceptanceEvidence']
        old_bytes=Path(old_ref['path']).read_bytes()
        projection=json.loads(Path(self.input['audioProjection']['path']).read_text())
        projection['captionLayoutRevision']='Synthetic metadata only; audio unchanged'
        self.input['audioProjection']=self.put('projection-current.json',projection)
        result=self.run_prepare();self.assertEqual(result['status'],'PROVISIONAL_NOT_ACCEPTED')
        checkpoint=json.loads((self.root/'prepared/audio-review-checkpoint.json').read_text())
        binding=json.loads(Path(checkpoint['acceptanceEvidence']['path']).read_text())
        self.assertEqual(binding['priorAcceptanceEvidence'],old_ref)
        self.assertEqual(binding['clockMapHash'],self.input['audioProjection']['sha256'])
        self.assertFalse(binding['newUserDecision'])
        self.assertEqual(Path(old_ref['path']).read_bytes(),old_bytes)


class IdenticalAudioAcceptanceBindingTests(unittest.TestCase):
    """Synthetic acceptance consistency only, never an actual listening result."""
    def setUp(self):
        from test_dependency_proof import audio_review_fixture
        from dependency_proof import validate_audio_review_checkpoint
        self.validate=validate_audio_review_checkpoint
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.sequence=0
        self.audio=self.root/'source.wav'
        with wave.open(str(self.audio),'wb') as source:
            source.setnchannels(1);source.setsampwidth(2);source.setframerate(16000)
            source.writeframes(b'\x01\x00'*400)
        fixture=audio_review_fixture(self.root,self.audio,'binding-fixture')
        self.checkpoint=json.loads(Path(fixture['checkpoint']['path']).read_text())
        self.old_ref=self.checkpoint['acceptanceEvidence']
        self.old_bytes=Path(self.old_ref['path']).read_bytes()
        current=json.loads(Path(self.checkpoint['clockMap']['path']).read_text())
        current['layoutRevision']='Different caption/native metadata, same PCM'
        self.checkpoint['clockMap']=self.put('new-clock.json',current)
    def put(self,name,obj):
        self.sequence+=1;p=self.root/(str(self.sequence)+'-'+name)
        p.write_text(json.dumps(obj),encoding='utf-8');return file_ref(p)
    def rewrite(self,field,changes):
        value=json.loads(Path(self.checkpoint[field]['path']).read_text())
        value.update(changes);self.checkpoint[field]=self.put(field+'.json',value)
    def assert_not_rebound(self):
        result=_rebind_identical_audio_acceptance(self.checkpoint,self.put)
        self.assertEqual(result['acceptanceEvidence'],self.checkpoint['acceptanceEvidence'])
        self.assertFalse(list(self.root.glob('*audio-acceptance-clock-binding.json')))
        with self.assertRaises(ValueError):
            self.validate(self.put('rejected-checkpoint.json',result),self.checkpoint['audioGain1'],'binding-fixture')
    def test_identical_audio_rebound_passes_unchanged_owner_with_linked_history(self):
        old=json.loads(self.old_bytes)
        result=_rebind_identical_audio_acceptance(self.checkpoint,self.put)
        binding=json.loads(Path(result['acceptanceEvidence']['path']).read_text())
        self.assertEqual(binding['oldClockHash'],old['clockMapHash'])
        self.assertEqual(binding['clockMapHash'],self.checkpoint['clockMap']['sha256'])
        self.assertEqual(binding['priorAcceptanceEvidence'],self.old_ref)
        self.assertEqual(binding['userReply'],old['userReply'])
        self.assertEqual(binding['userQuote'],old['userQuote'])
        self.assertEqual(binding['bindingBasis'],'IDENTICAL_ACCEPTED_AUDIO')
        self.assertIs(binding['newUserDecision'],False)
        self.assertEqual(Path(self.old_ref['path']).read_bytes(),self.old_bytes)
        accepted=self.validate(self.put('current-checkpoint.json',result),self.checkpoint['audioGain1'],'binding-fixture')
        self.assertEqual(accepted['status'],'USER_AUDIO_REVIEW_ACCEPTED')
    def test_unchanged_clock_preserves_acceptance_ref(self):
        old=json.loads(self.old_bytes)
        # Restore the original hash-bound projection from the fixture checkpoint.
        clock=next(p for p in self.root.glob('audio-fixture-*-clock.json') if file_ref(p)['sha256']==old['clockMapHash'])
        self.checkpoint['clockMap']=file_ref(clock)
        result=_rebind_identical_audio_acceptance(self.checkpoint,self.put)
        self.assertEqual(result,self.checkpoint)
    def test_changed_audio_does_not_inherit_old_acceptance(self):
        with wave.open(str(self.audio),'wb') as source:
            source.setnchannels(1);source.setsampwidth(2);source.setframerate(16000)
            source.writeframes(b'\x02\x00'*400)
        self.checkpoint['audioGain1']=file_ref(self.audio);self.assert_not_rebound()
    def test_changed_listening_copy_does_not_inherit_old_acceptance(self):
        listening=Path(self.checkpoint['listeningGain2']['path'])
        with wave.open(str(listening),'wb') as source:
            source.setnchannels(1);source.setsampwidth(2);source.setframerate(16000)
            source.writeframes(b'\x03\x00'*400)
        self.checkpoint['listeningGain2']=file_ref(listening);self.assert_not_rebound()
    def test_changed_resolved_feedback_requires_current_acceptance(self):
        self.rewrite('feedbackInventory',{'latestFeedbackIds':['new-item'],
            'items':[{'id':'new-item','status':'RESOLVED','observation':'New scoped feedback'}]})
        self.assert_not_rebound()
    def test_unresolved_feedback_never_rebound(self):
        self.rewrite('feedbackInventory',{'unresolvedFeedbackIds':['new-item']})
        self.assert_not_rebound()
    def test_wrong_task_acceptance_never_rebound(self):
        self.rewrite('acceptanceEvidence',{'taskId':'different-task'});self.assert_not_rebound()
    def test_teacher_reply_is_not_audio_acceptance(self):
        acceptance=json.loads(self.old_bytes);reply=json.loads(Path(acceptance['userReply']['path']).read_text())
        reply['reviewKind']='TEACHER_APPROVAL';self.rewrite('acceptanceEvidence',{'userReply':self.put('teacher-reply.json',reply)})
        self.assert_not_rebound()
    def test_quote_mismatch_never_rebound(self):
        self.rewrite('acceptanceEvidence',{'userQuote':'Different quotation'});self.assert_not_rebound()
    def test_invalid_current_clock_stays_blocked(self):
        self.rewrite('clockMap',{'gain':2});self.assert_not_rebound()
    def test_unsafe_gain_receipt_stays_blocked(self):
        self.rewrite('gainReceipt',{'clippedSampleCount':1});self.assert_not_rebound()
    def test_missing_prior_clock_binding_stays_blocked(self):
        self.rewrite('acceptanceEvidence',{'clockMapHash':None});self.assert_not_rebound()

if __name__=='__main__':unittest.main()
