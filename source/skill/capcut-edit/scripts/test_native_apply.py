"""Synthetic consistency tests only; no fixture proves heard audio or native use."""
import copy,json,tempfile,unittest,wave
from pathlib import Path
from check_native_apply import check,digest,native_broll_inventory
from execution_audit import prepare

class NativeApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.native=self.root/'native.json'
        self.native.write_text(json.dumps({'duration':1000000,'materials':{'texts':[{'id':'text-a','content':json.dumps({'text':'nhà'})}]},'tracks':[{'id':'main','type':'video','segments':[{'id':'piece-a','material_id':'src','speed':1,'source_timerange':{'start':0,'duration':1000000},'target_timerange':{'start':0,'duration':1000000}}]},{'type':'text','segments':[{'id':'cue-a','material_id':'text-a','target_timerange':{'start':100000,'duration':900000}}]}]}))
        self.audio=self.root/'audio.wav'
        with wave.open(str(self.audio),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*16000)
        self.m={'schema':'capcut-native-apply-evidence/v1','evidenceClass':'REAL_OBSERVATION','branch':'CONTENT_EDIT','native':{'path':str(self.native),'sha256':digest(self.native)},'audio':{'path':str(self.audio),'sha256':digest(self.audio)},'clockBinding':{'status':'REVIEWED'},'pacing':{'scope':'ALL_PAUSES','criterion':{'minimumQuietDurationTicks':200000,'comparison':'STRICTLY_GREATER','auditScopes':['HEAD','INTERNAL','TAIL']},'status':'REVIEWED','auditedScopes':['HEAD','INTERNAL','TAIL'],'intervals':[]},'onsets':[{'segmentId':'cue-a','startTick':100000,'rawWordIds':['w1'],'status':'REVIEWED'}]}
        # This positive fixture simulates a well-formed real review declaration;
        # it tests consistency, never authenticity. Known synthetic declarations
        # are rejected separately by the identical production entry point.
        self.m['clockBinding']['evidence']=self.proof('audio-clock-binding',mainTrackId='main')
        self.m['pacing']['evidence']=self.proof('all-pause-audit',auditedScopes=['HEAD','INTERNAL','TAIL'],intervalIds=[])
        self.m['onsets'][0]['evidence']=self.proof('caption-first-phoneme',segmentId='cue-a',startTick=100000,rawWordIds=['w1'])
        baseline=self.root/'locks.json';baseline.write_text(json.dumps({'protectedSpans':[]}))
        plan={'mainTrackId':'main','words':[{'id':'w1','text':'nhà','sentenceId':'s1','sourceId':'src','sourceStartTick':100000,'sourceEndTick':300000}],
            'cues':[{'segmentId':'cue-a','rawWordIds':['w1'],'nativeText':'nhà'}],
            'protectedSpans':[],'acceptedLockBaseline':{'path':str(baseline),'sha256':digest(baseline)},
            'semanticReview':{'basis':'whole-transcript-semantic-review','coveredWordIds':['w1']}}
        plan['semanticReview']['evidence']=self.proof('caption-policy-review',coveredWordIds=['w1'],cueGroups=plan['cues'],protectedSpans=[])
        self.revise(plan['semanticReview']['evidence'],basis='SUPPORTED_TEXT_REVIEW')
        profile={'windowMs':20,'hopMs':5,'methods':[{'kind':'RMS','thresholdsDbFS':[-50,-45]},{'kind':'PEAK','thresholdsDbFS':[-40,-35]}]}
        audit=prepare(self.native,self.audio,plan,profile)
        audit['calibrationEvidence']=self.proof('pause-detector-calibration',profile=profile)
        audit['pauseDecisions']=[{'id':c['id'],'decision':'RETAINED_PROTECTED','status':'REVIEWED','evidence':self.proof('pause-risk-disposition',candidateId=c['id'],decision='RETAINED_PROTECTED')} for c in audit['pauseScan']['candidates']]
        self.audit_path=self.root/'execution.json';self.audit=audit;self.save_audit()
        from test_dependency_proof import audio_review_fixture
        self.m['taskId']='synthetic-audio-task'
        self.m['audioReviewCheckpoint']=audio_review_fixture(self.root,self.audio)['checkpoint']
    def save_audit(self,rebuild_audio_edit=True):
        self.audit_path.write_text(json.dumps(self.audit));self.m['executionAudit']={'path':str(self.audit_path),'sha256':digest(self.audit_path)}
        if rebuild_audio_edit:
            from test_dependency_proof import audio_edit_fixture
            self.m['audioEditInventory']=audio_edit_fixture(self.root,self.native,self.audio,self.m['executionAudit'])
    def proof(self,claim,**extra):
        p=self.root/(claim+str(len(list(self.root.glob('*.json'))))+'.json')
        p.write_text(json.dumps(dict(evidenceClass='REAL_OBSERVATION',basis='HUMAN_LISTENING',status='PASS',reviewer='simulated-test-reviewer',observation='Simulated declaration, not a listening observation',claim=claim,nativeHash=digest(self.native),audioHash=digest(self.audio),**extra)))
        return {'path':str(p),'sha256':digest(p)}
    def revise(self,ref,**changes):
        p=Path(ref['path']);d=json.loads(p.read_text());d.update(changes);p.write_text(json.dumps(d));ref['sha256']=digest(p)
    def blocked(self): self.assertEqual(check(self.m)['status'],'BLOCKED')
    def test_positive_consistency_path(self):
        result=check(self.m);self.assertEqual(result['errors'],[]);self.assertFalse(result['nativeWriteAuthorized'])
    def test_missing_pacing(self):self.m.pop('pacing');self.blocked()
    def test_speech_native_apply_requires_user_audio_review(self):
        self.m.pop('audioReviewCheckpoint');result=check(self.m)
        self.assertEqual(result['status'],'BLOCKED');self.assertTrue(any('audio-review-checkpoint-blocked' in e for e in result['errors']))
    def test_audio_review_clock_map_must_match_current_structural_projection(self):
        self.revise(self.m['clockBinding']['evidence'],audioProjection={'path':'stale-map','sha256':'sha256:stale'})
        result=check(self.m);self.assertIn('audio-review-current-source-clock-map',result['errors'])
    def test_audio_acceptance_must_bind_current_task(self):
        self.m.pop('taskId');result=check(self.m)
        self.assertTrue(any('audio-review-current-task-required' in e for e in result['errors']))
    def test_all_pauses_requires_actual_quiet_inventory(self):
        self.m.pop('audioEditInventory');result=check(self.m)
        self.assertTrue(any('audio-edit-inventory-blocked' in e for e in result['errors']))
    def test_exact_legacy_scope_override_keeps_its_own_pacing(self):
        self.m.pop('audioEditInventory');self.m['pacing'].update(scope='INTER_SENTENCE_ONLY',
            scopeEvidence=self.proof('pacing-scope-override',scope='INTER_SENTENCE_ONLY'))
        result=check(self.m);self.assertEqual(result['errors'],[],result)
    def test_missing_onset_inventory(self):self.m['onsets']=[];self.blocked()
    def test_pending_onset(self):self.m['onsets'][0]['status']='PENDING';self.blocked()
    def test_asr_cannot_certify_onset(self):self.revise(self.m['onsets'][0]['evidence'],basis='ASR_ESTIMATE');self.blocked()
    def test_energy_cannot_certify_quiet(self):self.revise(self.m['pacing']['evidence'],basis='ENERGY_DETECTOR');self.blocked()
    def test_fixture_manifest_rejected(self):self.m['evidenceClass']='SYNTHETIC_FIXTURE';self.blocked()
    def test_fixture_evidence_rejected(self):self.revise(self.m['onsets'][0]['evidence'],evidenceClass='SYNTHETIC_FIXTURE');self.blocked()
    def test_stale_audio(self):self.m['audio']['sha256']='sha256:old';self.blocked()
    def test_stale_review_revision(self):self.revise(self.m['onsets'][0]['evidence'],nativeHash='sha256:old');self.blocked()
    def test_end_refinement_is_not_start_proof(self):self.revise(self.m['onsets'][0]['evidence'],claim='caption-end-refinement');self.blocked()
    def test_native_early_start_not_matching_review(self):self.m['onsets'][0]['startTick']=0;self.blocked()
    def test_incomplete_outer_pause_audit(self):self.m['pacing']['auditedScopes']=['INTERNAL'];self.blocked()
    def test_held_pause(self):
        self.m['pacing']['intervals']=[{'id':'p1','kind':'INTERNAL','startTick':300000,'endTick':600000,'decision':'HELD'}];self.blocked()
    def test_wrong_threshold(self):self.m['pacing']['criterion']['minimumQuietDurationTicks']=199999;self.blocked()
    def test_float_threshold_rejected(self):self.m['pacing']['criterion']['minimumQuietDurationTicks']=200000.0;self.blocked()
    def test_legacy_scope_requires_actual_override(self):self.m['pacing']['scope']='SENTENCE_AND_INTRA';self.blocked()
    def test_reviewed_legacy_route_retained(self):
        self.m['pacing']['scope']='SENTENCE_AND_INTRA'
        self.m['pacing']['scopeEvidence']=self.proof('pacing-scope-override',scope='SENTENCE_AND_INTRA')
        self.assertEqual(check(self.m)['status'],'PREREQUISITES_CONSISTENT')
    def test_subtitle_scope_requires_evidence(self):self.m['branch']='SUBTITLE_ONLY';self.m['pacing']={'status':'NOT_APPLICABLE_PRESERVE_EXISTING_PACE'};self.blocked()
    def test_review_cannot_borrow_previous_audio_hash(self):self.revise(self.m['pacing']['evidence'],audioHash='sha256:old');self.blocked()
    def test_proof_tampering(self):Path(self.m['onsets'][0]['evidence']['path']).write_text('{}');self.blocked()
    def test_zero_length_cue(self):
        d=json.loads(self.native.read_text());d['tracks'][0]['segments'][0]['target_timerange']['duration']=0;self.native.write_text(json.dumps(d));self.blocked()
    def test_missing_execution_audit(self):self.m.pop('executionAudit');self.blocked()
    def test_deleted_acoustic_conflict_is_not_complete_scan(self):self.audit['pauseScan']['candidates']=[];self.save_audit();self.blocked()
    def test_asr_overlap_is_not_a_quiet_disposition(self):
        self.audit['pauseDecisions'][0]['decision']='OVERLAPS_MODEL_WORD';self.save_audit();self.blocked()
    def test_unreviewed_candidate_blocks(self):self.audit['pauseDecisions'][0]['status']='PENDING';self.save_audit();self.blocked()
    def test_cut_inventory_cannot_be_omitted(self):self.audit['cutInventory']['allCues']=[];self.save_audit();self.blocked()
    def test_semantic_review_cannot_be_empty(self):self.audit['captionPlan']['semanticReview']['coveredWordIds']=[];self.save_audit();self.blocked()
    def test_raw_identity_cannot_be_rebound_in_caption_plan(self):self.audit['captionPlan']['cues'][0]['rawWordIds']=['w2'];self.save_audit();self.blocked()
    def test_empty_profile_cannot_skip_sensitive_scan(self):
        self.audit['pauseProfile']['methods']=[];self.save_audit(rebuild_audio_edit=False)
        result=check(self.m);self.assertEqual(result['status'],'BLOCKED')
        self.assertTrue(any('rms-and-peak-surveys-required' in e for e in result['errors']))
    def add_cut_risk(self,bind_review=True):
        from execution_audit import cut_inventory
        data=json.loads(self.native.read_text());main=data['tracks'][0]['segments']
        main[0]['source_timerange']['duration']=200000;main[0]['target_timerange']['duration']=200000
        main.append({'id':'piece-b','material_id':'src','speed':1,'source_timerange':{'start':200000,'duration':800000},'target_timerange':{'start':200000,'duration':800000}})
        self.native.write_text(json.dumps(data));self.m['native']['sha256']=digest(self.native);self.audit['nativeHash']=digest(self.native)
        for p in self.root.glob('*.json'):
            obj=json.loads(p.read_text())
            if isinstance(obj,dict) and 'nativeHash' in obj:obj['nativeHash']=digest(self.native);p.write_text(json.dumps(obj))
        def refresh(obj):
            if isinstance(obj,dict):
                if 'path' in obj and 'sha256' in obj and Path(obj['path']).is_file():obj['sha256']=digest(obj['path'])
                for value in obj.values():refresh(value)
            elif isinstance(obj,list):
                for value in obj:refresh(value)
        refresh(self.audit);refresh(self.m)
        self.audit['cutInventory']=cut_inventory(data,self.audit['captionPlan'])
        if bind_review:self.revise(self.m['onsets'][0]['evidence'],cutRisk=self.audit['cutInventory']['allCues'][0])
        self.save_audit()
    def test_complete_cut_source_leg_consistency_path(self):
        self.add_cut_risk();self.assertEqual(check(self.m)['errors'],[])
    def test_cut_source_legs_need_actual_bound_review(self):self.add_cut_risk(False);self.blocked()
    def test_matching_cut_count_cannot_hide_missing_source_leg(self):
        self.add_cut_risk();self.audit['cutInventory']['allCues'][0]['firstWordSourceLegs']=[];self.save_audit();self.blocked()

class NativeBrollAuditTests(unittest.TestCase):
    """Temporary synthetic JSON/WAV/source bytes test consistency, never media truth."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.native=self.root/'native.json';self.base=self.root/'base.json';self.audio=self.root/'audio.wav'
        with wave.open(str(self.audio),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*192000)
        self.sources=[]
        for ident in ('A','B'):
            source=self.root/(ident+'.mp4');source.write_bytes(('synthetic source '+ident).encode())
            self.sources.append({'id':ident,'path':str(source),'sha256':digest(source),'actualDurationTicks':12000000,
                'actualDurationEvidenceRef':'synthetic-probe','permitted':True,'rightsEvidenceRef':'synthetic-rights',
                'sourceOrigin':'AI','voiceClassification':'NOT_APPLICABLE',
                'classificationReview':{'reviewed':True,'evidenceRef':'synthetic-classification','evidenceBasis':'AGENT_VERIFIED'}})
        captions=[{'id':'c'+str(i),'startTick':i*4000000,'endTick':(i+1)*4000000} for i in range(3)]
        texts=[{'id':'t'+str(i),'content':json.dumps({'text':'house'})} for i in range(3)]
        materials=[{'id':'mat'+s['id'],'type':'video','path':s['path']} for s in self.sources]
        self.d={'duration':12000000,'materials':{'texts':texts,'videos':materials},'tracks':[
            {'id':'main','type':'video','segments':[{'id':'main-piece','material_id':'src','speed':1,'volume':1,
                'source_timerange':{'start':0,'duration':12000000},'target_timerange':{'start':0,'duration':12000000}}]},
            {'id':'captions','type':'text','segments':[{'id':c['id'],'material_id':'t'+str(i),
                'target_timerange':{'start':c['startTick'],'duration':c['endTick']-c['startTick']}} for i,c in enumerate(captions)]}]}
        self.base.write_text(json.dumps(self.d));self.d['tracks'].append({'id':'support','type':'video','segments':[self.segment('new','A',0,0)]})
        self.native.write_text(json.dumps(self.d))
        self.plan={'schemaVersion':'capcut-broll-plan/v1','tickRate':1000000,'coverageMode':'SPARSE',
            'baseSnapshot':{'path':str(self.base),'sha256':digest(self.base),'durationTicks':12000000},
            'contentCaptionCheckpoint':'PASS','baseCheckpointEvidenceRef':'synthetic-base-checkpoint','baseCheckpointEvidenceBasis':'USER_REPORTED',
            'captionCues':captions,'existingArollCuts':[0,12000000],
            'cadenceReview':{'reviewed':True,'evidenceRef':'synthetic-cadence','reason':'Synthetic relevant source, not a quota'},
            'sources':copy.deepcopy(self.sources),'sourceUsageReview':{'reviewed':True,'evidenceRef':'synthetic-complete-inventory',
                'evidenceBasis':'AGENT_VERIFIED','scope':'WHOLE_CURRENT_TIMELINE','baseSnapshotSha256':digest(self.base),'existingPlacements':[]},
            'placements':[self.placement('new','A',0,0)]}
        self.review_placements();self.bind()
    def segment(self,ident,source,a,x):
        return {'id':ident,'material_id':'mat'+source,'speed':1,'volume':0,
            'source_timerange':{'start':a,'duration':4000000},'target_timerange':{'start':x,'duration':4000000}}
    def placement(self,ident,source,a,x):
        return {'id':ident,'sourceId':source,'sourceInTick':a,'startCaptionId':'c'+str(x//4000000),
            'lastCaptionId':'c'+str(x//4000000),'startTick':x,'endTick':x+4000000,
            'meaningReview':{'reviewed':True,'evidenceRef':'synthetic-meaning','relevance':'Synthetic reviewed imagery',
                'addedInformation':'Synthetic detail','startSelectionReason':'Existing caption boundary'},
            'paddedToTenSeconds':False,'muteSourceAudio':True,'preserveMainVideo':True}
    def review_placements(self):
        for p in self.plan['placements']:
            p['eligibleSourceReview']={'reviewed':True,'evidenceRef':'synthetic-eligibility','evidenceBasis':'AGENT_VERIFIED',
                'scope':'ALL_SUPPLIED_SOURCES','exhaustive':True,'baseSnapshotSha256':self.plan['baseSnapshot']['sha256'],
                'sources':[{'sourceId':s['id'],'status':'ELIGIBLE','evidenceRef':'synthetic-eligible-source',
                    'windows':[{'sourceInTick':0,'sourceOutTick':12000000}],'reason':'Synthetic exhaustive windows'} for s in self.plan['sources']]}
    def proof(self,claim,basis='HUMAN_LISTENING',**fields):
        p=self.root/(claim+'.json');p.write_text(json.dumps(dict(evidenceClass='REAL_OBSERVATION',basis=basis,status='PASS',
            reviewer='simulated-reviewer',observation='Synthetic consistency declaration; no actual playback or visual review',
            nativeHash=digest(self.native),audioHash=digest(self.audio),claim=claim,**fields)))
        return {'path':str(p),'sha256':digest(p)}
    def ref(self,name,data):
        p=self.root/name;p.write_text(json.dumps(data));return {'path':str(p),'sha256':digest(p)}
    def bind(self):
        """Bind current synthetic identities so each negative test reaches its own gate."""
        self.native.write_text(json.dumps(self.d))
        words=[{'id':'w'+str(i),'text':'house','sentenceId':'s'+str(i),'sourceId':'src',
            'sourceStartTick':i*4000000,'sourceEndTick':i*4000000+1000000} for i in range(3)]
        cues=[{'segmentId':'c'+str(i),'rawWordIds':['w'+str(i)],'nativeText':'house'} for i in range(3)]
        cp={'mainTrackId':'main','words':words,'cues':cues,'protectedSpans':[],
            'acceptedLockBaseline':self.ref('locks.json',{'protectedSpans':[]}),
            'semanticReview':{'basis':'whole-transcript-semantic-review','coveredWordIds':[w['id'] for w in words]}}
        cp['semanticReview']['evidence']=self.proof('caption-policy-review',basis='SUPPORTED_TEXT_REVIEW',
            coveredWordIds=[w['id'] for w in words],cueGroups=cues,protectedSpans=[])
        audit=prepare(self.native,self.audio,cp,{},branch='SUBTITLE_ONLY')
        self.m={'schema':'capcut-native-apply-evidence/v1','evidenceClass':'REAL_OBSERVATION','branch':'SUBTITLE_ONLY',
            'native':{'path':str(self.native),'sha256':digest(self.native)},'audio':{'path':str(self.audio),'sha256':digest(self.audio)},
            'clockBinding':{'status':'REVIEWED','evidence':self.proof('audio-clock-binding',mainTrackId='main')},
            'pacing':{'status':'NOT_APPLICABLE_PRESERVE_EXISTING_PACE','evidence':self.proof('subtitle-only-scope')},
            'onsets':[],'executionAudit':self.ref('execution.json',audit)}
        for i in range(3):
            onset={'segmentId':'c'+str(i),'startTick':i*4000000,'rawWordIds':['w'+str(i)],'status':'REVIEWED'}
            onset['evidence']=self.proof('caption-first-phoneme-'+str(i),**{})
            path=Path(onset['evidence']['path']);record=json.loads(path.read_text());record.update(claim='caption-first-phoneme',
                segmentId=onset['segmentId'],startTick=onset['startTick'],rawWordIds=onset['rawWordIds']);path.write_text(json.dumps(record));onset['evidence']['sha256']=digest(path)
            self.m['onsets'].append(onset)
        self.plan_ref=self.ref('broll-plan.json',self.plan)
        try:inventory=native_broll_inventory(self.d,'main')
        except (ValueError,TypeError):inventory=[]
        review=self.proof('broll-whole-timeline-review',basis='HUMAN_VISUAL_REVIEW',mainTrackId='main',planHash=self.plan_ref['sha256'],
            actualInventory=inventory,wholeTimelineInventoryComplete=True,knownSourceLineageReviewed=True,
            inventoryObservation='Synthetic complete inventory declaration',lineageObservation='Synthetic known original identities declaration')
        self.broll={'schema':'capcut-native-broll-audit/v1','nativeHash':digest(self.native),'mainTrackId':'main',
            'plan':self.plan_ref,'reviewEvidence':review}
        self.m['bRollAudit']=self.ref('broll-audit.json',self.broll)
    def rejected(self,reason):
        result=check(self.m);self.assertEqual(result['status'],'BLOCKED',result)
        self.assertTrue(any(reason in e for e in result['errors']),result)
    def test_complete_native_broll_inventory_is_consistent_only(self):
        result=check(self.m);self.assertEqual(result['errors'],[]);self.assertFalse(result['nativeWriteAuthorized'])
    def test_nonmain_video_requires_audit_despite_duplicate_repeated_source(self):
        self.d['tracks'][-1]['segments'].append(self.segment('repeat','A',0,4000000));self.bind();self.m.pop('bRollAudit')
        self.rejected('missing-file-reference')
    def test_false_empty_or_missing_audit_never_exempts_actual_objects(self):
        for ref in (None,False,{}):
            self.m['bRollAudit']=ref;self.rejected('file-reference')
    def test_derived_zero_support_objects_is_the_only_no_audit_exemption(self):
        self.d['tracks'].pop();self.bind();self.m.pop('bRollAudit');self.assertEqual(check(self.m)['errors'],[])
    def test_extra_native_overlay_not_in_full_combined_ledger_blocks(self):
        self.d['tracks'][-1]['segments'].append(self.segment('undeclared','B',0,4000000));self.bind()
        self.rejected('broll-whole-native-placement-mismatch')
    def test_native_source_window_mismatch_blocks(self):
        self.d['tracks'][-1]['segments'][0]['source_timerange']['start']=1000000;self.bind()
        self.rejected('broll-whole-native-placement-mismatch')
    def test_native_target_window_mismatch_blocks(self):
        self.d['tracks'][-1]['segments'][0]['target_timerange']['start']=4000000;self.bind()
        self.rejected('broll-whole-native-placement-mismatch')
    def test_stale_audit_native_hash_blocks(self):
        self.broll['nativeHash']='sha256:old';self.m['bRollAudit']=self.ref('broll-audit.json',self.broll)
        self.rejected('broll-audit-stale-revision')
    def test_stale_plan_hash_blocks(self):
        Path(self.plan_ref['path']).write_text('{}');self.rejected('missing-or-stale-file-reference')
    def test_changed_actual_source_bytes_cannot_borrow_declared_source_hash(self):
        Path(self.sources[0]['path']).write_bytes(b'changed bytes');self.rejected('source identity')
    def test_held_recomputation_cannot_be_hidden_by_claimed_audit(self):
        self.plan['placements'][0]['eligibleSourceReview']['sources'][0].update(status='UNKNOWN',windows=[],reason='Unreviewed source')
        self.bind();self.rejected('broll-recomputed-plan-held')
    def test_duplicate_native_segment_id_blocks(self):
        self.d['tracks'][-1]['segments'].append(self.segment('new','B',0,4000000));self.bind();self.rejected('duplicate-or-missing-segment')
    def test_exact_identical_material_duplicates_are_safe_native_representation(self):
        self.d['materials']['videos'].extend(copy.deepcopy(self.d['materials']['videos']));self.bind()
        self.assertEqual(check(self.m)['errors'],[])
    def test_exact_identical_material_duplicates_do_not_break_zero_overlay_exemption(self):
        self.d['materials']['videos'].extend(copy.deepcopy(self.d['materials']['videos']));self.d['tracks'].pop();self.bind();self.m.pop('bRollAudit')
        self.assertEqual(check(self.m)['errors'],[])
    def test_conflicting_same_id_materials_are_held(self):
        material=copy.deepcopy(self.d['materials']['videos'][0]);material['path']=self.sources[1]['path']
        self.d['materials']['videos'].append(material);self.bind();self.rejected('conflicting-or-missing-material')
    def test_current_file_hash_is_cached_only_within_one_inventory_call(self):
        from unittest.mock import patch
        self.d['tracks'][-1]['segments'].append(self.segment('second','A',4000000,4000000))
        with patch('check_native_apply.digest',wraps=digest) as hashed:
            native_broll_inventory(self.d,'main');self.assertEqual(hashed.call_count,1)
            native_broll_inventory(self.d,'main');self.assertEqual(hashed.call_count,2)
    def test_unmapped_native_video_material_blocks(self):
        self.d['tracks'][-1]['segments'][0]['material_id']='unmapped';self.bind();self.rejected('unmapped-or-nested')
    def test_unsupported_nested_video_never_disappears_from_inventory(self):
        self.d['tracks'][-1]['segments'][0]['tracks']=[{'type':'video'}];self.bind();self.rejected('unsupported-nesting')
    def test_missing_source_window_blocks(self):
        self.d['tracks'][-1]['segments'][0].pop('source_timerange');self.bind();self.rejected('source-target-windows')
    def test_unknown_track_role_is_held_even_if_audit_claims_no_broll(self):
        self.d['tracks'][-1]['type']='unknown';self.bind();self.m.pop('bRollAudit');self.rejected('unknown-track-role')
    def test_known_nonmain_video_cannot_hide_on_audio_track(self):
        self.d['tracks'][-1]['type']='audio';self.bind();self.rejected('video-material-on-unknown-role')
    def test_nonunit_speed_or_nonsilent_overlay_blocks(self):
        for key,value in (('speed',2),('volume',1)):
            original=self.d['tracks'][-1]['segments'][0][key];self.d['tracks'][-1]['segments'][0][key]=value;self.bind()
            self.rejected('normal-speed-silent');self.d['tracks'][-1]['segments'][0][key]=original
    def test_hash_alias_is_not_a_new_source_identity(self):
        alias=self.root/'alias.mp4';alias.write_bytes(Path(self.sources[0]['path']).read_bytes())
        self.d['materials']['videos'].append({'id':'alias-material','type':'video','path':str(alias)})
        segment=self.segment('alias-use','A',4000000,4000000);segment['material_id']='alias-material';self.d['tracks'][-1]['segments'].append(segment)
        self.plan['placements'].append(self.placement('alias-use','A',4000000,4000000));self.review_placements();self.bind()
        self.rejected('broll-recomputed-plan-held')
    def test_default_rejects_same_source_disjoint_window_even_without_fresh_alternative(self):
        self.d['tracks'][-1]['segments'].append(self.segment('second','A',4000000,4000000))
        self.plan['placements'].append(self.placement('second','A',4000000,4000000));self.review_placements()
        for p in self.plan['placements']:
            p['eligibleSourceReview']['sources'][1].update(status='IRRELEVANT',windows=[],reason='Synthetic reviewed different visual role')
        self.bind();self.rejected('broll-recomputed-plan-held')
    def test_explicit_base_bound_conditional_mode_retains_disjoint_window_behavior(self):
        self.d['tracks'][-1]['segments'].append(self.segment('second','A',4000000,4000000))
        self.plan['placements'].append(self.placement('second','A',4000000,4000000));self.review_placements()
        for p in self.plan['placements']:
            p['eligibleSourceReview']['sources'][1].update(status='IRRELEVANT',windows=[],reason='Synthetic reviewed different visual role')
        self.plan.update(sourceReuseMode='REVIEWED_CONDITIONAL_REUSE',sourceReuseOverride={'reviewed':True,'evidenceRef':'synthetic-explicit-choice',
            'evidenceBasis':'USER_REPORTED','authority':'explicit-user-request','mode':'REVIEWED_CONDITIONAL_REUSE',
            'baseSnapshotSha256':self.plan['baseSnapshot']['sha256'],'userQuote':'Synthetic explicit request to allow distinct source windows'})
        self.bind();self.assertEqual(check(self.m)['errors'],[])
    def add_unchanged_baseline(self):
        base=json.loads(self.base.read_text());old=self.segment('old','A',0,0)
        base['tracks'].append({'id':'old-support','type':'video','segments':[old]});self.base.write_text(json.dumps(base))
        self.plan['baseSnapshot']['sha256']=digest(self.base);self.plan['sourceUsageReview']['baseSnapshotSha256']=digest(self.base)
        self.plan['sourceUsageReview']['existingPlacements']=[{'id':'old','sourceId':'A','sourceInTick':0,'sourceOutTick':4000000,'startTick':0,'endTick':4000000}]
        self.plan['placements']=[self.placement('new','B',0,4000000)];self.review_placements()
        self.d=copy.deepcopy(base);self.d['tracks'].append({'id':'new-support','type':'video','segments':[self.segment('new','B',0,4000000)]});self.bind()
    def test_full_inventory_includes_unchanged_native_baseline(self):
        self.add_unchanged_baseline();self.assertEqual(check(self.m)['errors'],[])
    def test_omitting_unchanged_object_from_existing_inventory_blocks(self):
        self.add_unchanged_baseline();self.plan['sourceUsageReview']['existingPlacements']=[];self.bind()
        self.rejected('broll-base-existing-inventory-mismatch')
    def test_base_existing_inventory_cannot_be_invented_from_proposed_draft(self):
        self.plan['sourceUsageReview']['existingPlacements']=[{'id':'new','sourceId':'A','sourceInTick':0,'sourceOutTick':4000000,'startTick':0,'endTick':4000000}]
        self.bind();self.rejected('broll-base-existing-inventory-mismatch')
    def test_base_duration_or_caption_clock_mismatch_blocks(self):
        self.plan['captionCues'][1]['startTick']+=1;self.bind();self.rejected('broll-base-caption-clock-mismatch')
    def test_main_track_changes_cannot_borrow_old_base_checkpoint(self):
        self.d['tracks'][0]['segments'][0]['volume']=2;self.bind();self.rejected('broll-main-track-changed')
    def test_main_extra_speed_material_cannot_change_behind_unchanged_segment(self):
        base=json.loads(self.base.read_text());base['tracks'][0]['segments'][0]['extra_material_refs']=['main-speed']
        base['materials']['speeds']=[{'id':'main-speed','speed':1,'curve_speed':None}];self.base.write_text(json.dumps(base))
        self.plan['baseSnapshot']['sha256']=digest(self.base);self.plan['sourceUsageReview']['baseSnapshotSha256']=digest(self.base);self.review_placements()
        self.d['tracks'][0]=copy.deepcopy(base['tracks'][0]);self.d['materials']['speeds']=[{'id':'main-speed','speed':2,'curve_speed':None}]
        self.bind();self.rejected('broll-main-source-material-changed')
    def test_extra_support_speed_curve_cannot_hide_behind_segment_speed_one(self):
        self.d['materials']['speeds']=[{'id':'curve','speed':1,'curve_speed':{'points':[1,2]}}]
        self.d['tracks'][-1]['segments'][0]['extra_material_refs']=['curve'];self.bind();self.rejected('normal-speed-silent')
    def test_visual_review_cannot_be_audio_or_hash_only_evidence(self):
        path=Path(self.broll['reviewEvidence']['path']);record=json.loads(path.read_text());record.update(basis='HUMAN_LISTENING',lineageObservation='')
        path.write_text(json.dumps(record));self.broll['reviewEvidence']['sha256']=digest(path);self.m['bRollAudit']=self.ref('broll-audit.json',self.broll)
        self.rejected('broll-inventory-lineage-observation-required')
    def test_review_must_bind_current_actual_inventory_and_plan_hash(self):
        path=Path(self.broll['reviewEvidence']['path']);record=json.loads(path.read_text());record.update(actualInventory=[],planHash='sha256:old')
        path.write_text(json.dumps(record));self.broll['reviewEvidence']['sha256']=digest(path);self.m['bRollAudit']=self.ref('broll-audit.json',self.broll)
        self.rejected('broll-whole-timeline-review-actualInventory')

class ReviewDraftTests(unittest.TestCase):
    """Inert provisional fixtures; no assertion is actual hearing/native use."""
    def setUp(self):
        self.fixture=NativeApplyTests('test_positive_consistency_path');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture;self.root=f.root;self.native=f.native;self.audio=f.audio
        data=json.loads(self.native.read_text());data.update(id='timeline-id',fps=30)
        data['tracks'][0]['segments'][0]['volume']=1
        source=self.root/'main.mp4';source.write_bytes(b'synthetic source fixture, not actual media')
        data['materials']['videos']=[{'id':'src','type':'video','path':str(source)}]
        self.native.write_text(json.dumps(data));self.data=data
        self.m=copy.deepcopy(f.m);self.m.update(mode='REVIEW_DRAFT',native={'path':str(self.native),'sha256':digest(self.native)})
        f.native=self.native
        cp=copy.deepcopy(f.audit['captionPlan'])
        cp['semanticReview']['evidence']=f.proof('caption-policy-review',coveredWordIds=['w1'],cueGroups=cp['cues'],protectedSpans=[])
        f.revise(cp['semanticReview']['evidence'],basis='SUPPORTED_TEXT_REVIEW')
        audit=prepare(self.native,self.audio,cp,f.audit['pauseProfile'])
        audit['pauseDecisions']=[{'id':c['id'],'status':'PENDING','decision':'UNREVIEWED'} for c in audit['pauseScan']['candidates']]
        self.audit=audit;self.save_audit()
        self.m['pacing'].update(status='PENDING');self.m['pacing'].pop('evidence',None)
        self.m['onsets']=[{'segmentId':'cue-a','startTick':100000,'rawWordIds':['w1'],'status':'PENDING'}]
        clock=f.proof('audio-clock-binding',mainTrackId='main',mainSourcePieces=data['tracks'][0]['segments'])
        f.revise(clock,basis='SUPPORTED_STRUCTURAL_REVIEW')
        self.m['clockBinding']={'status':'PREPARED_EXACT_SOURCE_MAP','evidence':clock}
        dest={'path':str(self.root/'new-separate-project'),'projectId':'metadata-project-id',
            'timelineId':'timeline-id','operation':'CREATE_SEPARATE_NEW_PROJECT','overwriteExisting':False}
        authority=self.ref('authority.json',{'evidenceClass':'REAL_OBSERVATION','authority':'explicit-user-request',
            'claim':'review-draft-native-apply','mode':'REVIEW_DRAFT','taskId':'test-task',
            'nativeHash':digest(self.native),'audioHash':digest(self.audio),'destinationPath':dest['path'],
            'projectId':dest['projectId'],'timelineId':dest['timelineId'],
            'userQuote':'Synthetic explicit choice of a separate provisional review project'})
        probe=self.ref('source-probe.json',{'status':'PASS_IDENTITY_NOT_HEARD','sources':[{'path':str(source),
            'sha256':digest(source),'durationTicks':1000000,'unchangedStatBeforeAfter':True,
            'probeCommand':['synthetic ffprobe fixture, never executed']}]})
        source_scope=self.ref('source-scope.json',{'schema':'capcut-review-draft-source-scope/v1',
            'evidenceClass':'REAL_OBSERVATION','authority':'explicit-user-request','taskId':'test-task',
            'nativeHash':digest(self.native),'audioHash':digest(self.audio),'userQuote':'Synthetic permitted source choice',
            'sources':[{'materialId':'src','path':str(source),'sha256':digest(source),'actualDurationTicks':1000000,
                'actualDurationEvidenceRef':probe}]})
        profile=self.ref('style-profile.json',{'id':'synthetic-style'})
        from dependency_proof import dependency_fingerprints
        style=f.proof('caption-style-binding',taskId='test-task',styleProfile=profile,
            captionStyleFingerprint=dependency_fingerprints(data,self.audio,'main')['captionStyle'])
        f.revise(style,basis='SUPPORTED_TEXT_REVIEW')
        self.m['reviewDraft']={'schema':'capcut-review-draft/v1','taskId':'test-task','destination':dest,
            'authorityEvidence':authority,'sourceScope':source_scope,'styleEvidence':style,
            'contentReview':{'status':'PROVISIONAL_MODEL_ONLY','wordTimingBasis':'MODEL_ONLY',
                'takeGroups':[{'id':'take1','status':'PENDING','observation':'Synthetic model-only take choice'}],
                'uncertainties':[{'id':'words','kind':'CONTENT_AND_SPEAKER','observation':'Synthetic words have no hearing evidence'}]}}
        from test_dependency_proof import audio_review_fixture
        self.m['audioReviewCheckpoint']=audio_review_fixture(self.root,self.audio,'test-task')['checkpoint']
    def ref(self,name,data):
        path=self.root/name;path.write_text(json.dumps(data));return {'path':str(path),'sha256':digest(path)}
    def save_audit(self):
        self.m['executionAudit']=self.ref('review-execution.json',self.audit)
        from test_dependency_proof import audio_edit_fixture
        self.m['audioEditInventory']=audio_edit_fixture(self.root,self.native,self.audio,self.m['executionAudit'],final=False)
    def result(self):return check(self.m)
    def assert_blocked(self):self.assertEqual(self.result()['status'],'BLOCKED',self.result())
    def test_explicit_new_project_can_be_provisional_with_all_pending_inventory(self):
        result=self.result();self.assertEqual(result['errors'],[],result)
        self.assertEqual(result['status'],'PROVISIONAL_NOT_ACCEPTED');self.assertTrue(result['passed'])
        self.assertTrue(result['reviewDraftEligible']);self.assertFalse(result['finalAcceptance'])
        self.assertEqual(len(result['pendingQuality']['onsets']),1)
        self.assertEqual(len(result['pendingQuality']['pauseCandidates']),4)
        self.assertEqual(result['pendingQuality']['pauseCalibration'],'PENDING_UNCALIBRATED_MACHINE_RISK_ONLY')
        self.assertEqual(result['wordSourceCoverageScope'],'SUPPLIED_PROPOSED_CAPTION_WORDS_ONLY_NOT_AUDIBLE_COMPLETENESS')
    def test_cli_returns_success_for_eligible_provisional_draft(self):
        import subprocess,sys
        path=self.root/'cli-manifest.json';path.write_text(json.dumps(self.m))
        script=Path(__file__).with_name('check_native_apply.py')
        result=subprocess.run([sys.executable,'-B',str(script),'--manifest',str(path)],capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'],'PROVISIONAL_NOT_ACCEPTED')
    def test_omitting_mode_never_silently_waives_final_gate(self):self.m.pop('mode');self.assert_blocked()
    def test_missing_exact_authority_is_blocked(self):self.m['reviewDraft'].pop('authorityEvidence');self.assert_blocked()
    def test_separate_review_draft_also_requires_prior_user_audio_review(self):
        self.m.pop('audioReviewCheckpoint');result=self.result()
        self.assertEqual(result['status'],'BLOCKED');self.assertFalse(result['reviewDraftEligible'])
    def test_synthetic_authority_is_blocked(self):
        ref=self.m['reviewDraft']['authorityEvidence'];data=json.loads(Path(ref['path']).read_text());data['evidenceClass']='SYNTHETIC_FIXTURE'
        self.m['reviewDraft']['authorityEvidence']=self.ref('authority.json',data);self.assert_blocked()
    def test_existing_project_destination_is_blocked(self):Path(self.m['reviewDraft']['destination']['path']).mkdir();self.assert_blocked()
    def test_old_project_edit_operation_is_blocked(self):self.m['reviewDraft']['destination']['operation']='UPDATE_EXISTING_PROJECT';self.assert_blocked()
    def test_project_and_timeline_ids_can_differ_but_timeline_must_match(self):
        self.assertEqual(self.result()['errors'],[]);self.m['reviewDraft']['destination']['timelineId']='another';self.assert_blocked()
    def test_pending_onset_cannot_be_omitted(self):self.m['onsets']=[];self.assert_blocked()
    def test_pending_pause_candidate_cannot_be_omitted(self):self.audit['pauseDecisions']=[];self.save_audit();self.assert_blocked()
    def test_model_only_content_requires_uncertainty_inventory(self):self.m['reviewDraft']['contentReview']['uncertainties']=[];self.assert_blocked()
    def test_reviewed_label_cannot_supply_hearing(self):self.m['onsets'][0]['status']='REVIEWED';self.assert_blocked()
    def test_synthetic_style_evidence_is_blocked(self):
        ref=self.m['reviewDraft']['styleEvidence'];data=json.loads(Path(ref['path']).read_text());data['evidenceClass']='SYNTHETIC_FIXTURE'
        self.m['reviewDraft']['styleEvidence']=self.ref('changed-style.json',data);self.assert_blocked()
    def test_source_bounds_change_is_blocked(self):
        ref=self.m['reviewDraft']['sourceScope'];data=json.loads(Path(ref['path']).read_text());data['sources'][0]['actualDurationTicks']=999999
        self.m['reviewDraft']['sourceScope']=self.ref('source-scope.json',data);self.assert_blocked()
    def model_overlap(self,allow=False,fully_removed=False,duplicate=False):
        f=self.fixture;data=copy.deepcopy(self.data);main=data['tracks'][0]['segments'];first=copy.deepcopy(main[0]);second=copy.deepcopy(main[0])
        first['source_timerange']={'start':0,'duration':150000};first['target_timerange']={'start':0,'duration':150000}
        second.update(id='piece-b',source_timerange={'start':100000 if duplicate else 200000,'duration':800000},target_timerange={'start':150000,'duration':800000})
        data['tracks'][0]['segments']=[first,second];data['duration']=950000
        data['tracks'][1]['segments'][0]['target_timerange']['duration']=850000
        self.native.write_text(json.dumps(data));self.data=data
        with wave.open(str(self.audio),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*15200)
        self.m['native']={'path':str(self.native),'sha256':digest(self.native)};self.m['audio']={'path':str(self.audio),'sha256':digest(self.audio)}
        for key in ('authorityEvidence','sourceScope'):
            ref=self.m['reviewDraft'][key];obj=json.loads(Path(ref['path']).read_text());obj.update(nativeHash=digest(self.native),audioHash=digest(self.audio))
            if key=='authorityEvidence':
                obj['allowModelWordIntervalOverlap']=allow
                obj['scopeInterpretation']='Synthetic separate model-only draft; all cut intersections remain pending'
                obj['provisionalCutScope']={'mainPieces':2,'candidateDurationSeconds':.95,'detectorQuietRemovals':0,'speechFacingHandlesMs':100}
            self.m['reviewDraft'][key]=self.ref(key+'.json',obj)
        plan=copy.deepcopy(self.audit['captionPlan'])
        if fully_removed:plan['words'][0].update(sourceStartTick=160000,sourceEndTick=190000)
        plan['semanticReview']['evidence']=f.proof('caption-policy-review',coveredWordIds=['w1'],cueGroups=plan['cues'],protectedSpans=[])
        f.revise(plan['semanticReview']['evidence'],basis='SUPPORTED_TEXT_REVIEW')
        self.audit=prepare(self.native,self.audio,plan,self.audit['pauseProfile'])
        self.audit['pauseDecisions']=[{'id':c['id'],'status':'PENDING','decision':'UNREVIEWED'} for c in self.audit['pauseScan']['candidates']];self.save_audit()
        clock=f.proof('audio-clock-binding',mainTrackId='main',mainSourcePieces=data['tracks'][0]['segments']);f.revise(clock,basis='SUPPORTED_STRUCTURAL_REVIEW');self.m['clockBinding']['evidence']=clock
        old_style=json.loads(Path(self.m['reviewDraft']['styleEvidence']['path']).read_text())
        from dependency_proof import dependency_fingerprints
        style=f.proof('caption-style-binding',taskId='test-task',styleProfile=old_style['styleProfile'],
            captionStyleFingerprint=dependency_fingerprints(data,self.audio,'main',scopes=('captionStyle',))['captionStyle'])
        f.revise(style,basis='SUPPORTED_TEXT_REVIEW');self.m['reviewDraft']['styleEvidence']=style
        from test_dependency_proof import audio_review_fixture
        self.m['audioReviewCheckpoint']=audio_review_fixture(self.root,self.audio,'test-task')['checkpoint']
    def test_explicit_model_overlap_is_pending_with_exact_original_and_removed_ranges(self):
        self.model_overlap(allow=True);result=self.result();self.assertEqual(result['errors'],[],result)
        word=result['pendingQuality']['wordSourceCoverage'][0]
        self.assertEqual((word['originalSourceStartTick'],word['originalSourceEndTick']),(100000,300000))
        self.assertEqual(word['removedSourceIntervals'],[{'startTick':150000,'endTick':200000}])
        self.assertEqual(word['status'],'PENDING_AUDIO_CONTINUITY');self.assertEqual(len(word['retainedSourceLegs']),2)
    def test_model_overlap_without_explicit_flag_is_blocked(self):self.model_overlap();self.assert_blocked()
    def test_fully_removed_model_word_is_blocked_even_with_flag(self):self.model_overlap(allow=True,fully_removed=True);self.assert_blocked()
    def test_duplicated_retained_word_source_leg_is_blocked(self):self.model_overlap(allow=True,duplicate=True);self.assert_blocked()
    def test_review_overlap_flag_never_waives_final_mode(self):self.model_overlap(allow=True);self.m['mode']='FINAL_ACCEPTANCE';self.assert_blocked()

class AdoptedFinalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture=NativeApplyTests('test_positive_consistency_path');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.f=self.fixture;self.m=self.f.m
    def test_guard_accepts_exact_dependency_adoption_after_unused_record_pruning(self):
        from dependency_proof import make_adoption,file_ref
        f=self.f;old=f.root/'old-native.json';old.write_bytes(f.native.read_bytes())
        data=json.loads(f.native.read_text());data.setdefault('materials',{})['videos']=[{'id':'unused','type':'video','path':'unused source never referenced'}]
        f.native.write_text(json.dumps(data));self.m['native']=file_ref(f.native)
        self.assertEqual(check(self.m)['status'],'BLOCKED')
        def adopt(ref):
            original={k:ref[k] for k in ('path','sha256')}
            record=make_adoption(original,file_ref(old),file_ref(f.native),file_ref(f.audio),file_ref(f.audio),'main')
            path=f.root/('adoption-'+str(len(list(f.root.glob('adoption-*'))))+'.json')
            path.write_text(json.dumps(record));ref['adoption']=file_ref(path)
        adopt(self.m['clockBinding']['evidence']);adopt(self.m['pacing']['evidence'])
        for row in self.m['onsets']:adopt(row['evidence'])
        adopt(f.audit['captionPlan']['semanticReview']['evidence']);adopt(f.audit['calibrationEvidence'])
        for row in f.audit['pauseDecisions']:adopt(row['evidence'])
        f.audit['nativeHash']=digest(f.native);f.save_audit()
        result=check(self.m);self.assertEqual(result['errors'],[],result)
        self.assertEqual(result['status'],'PREREQUISITES_CONSISTENT')
        self.assertNotIn('newHearingClaimed',result)

if __name__=='__main__':unittest.main()
