"""Tiny synthetic media relationships; never hearing or real user approval."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave
import source_derivation
from dependency_proof import file_ref, make_audio_edit_inventory, validate_audio_edit_inventory
from source_derivation import validate_source_derivation


class DerivationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.original = self.root / 'original.mp4'
        self.original.write_bytes(b'SYNTHETIC original container identity')
        self.master = self.root / 'master.mov'
        self.master.write_bytes(b'SYNTHETIC rendered container identity')
        self.opcm = self.root / 'original.wav'
        self.bpcm = self.root / 'B.wav'
        self.cpcm = self.root / 'C.wav'
        # Every source frame has different samples, preventing accidental alias
        # equality from hiding a wrong frame/source crosswalk.
        self.pcm = b''.join(struct.pack('<hh', i + 1, -i - 1) * 1600 for i in range(10))
        self.bdata = self.pcm[1600*4:6400*4] + self.pcm[9600*4:16000*4]
        self.wav(self.opcm, self.pcm)
        self.wav(self.bpcm, self.bdata)
        self.wav(self.cpcm, self.bdata[1600*4:])
        self.probe = self.put('original-probe.json', {'sources': [{'id':'original', 'path':str(self.original),
            'sha256':file_ref(self.original)['sha256'], 'durationTicks':333334,
            'unchangedStatBeforeAfter':True,'probeCommand':['synthetic-supported-probe',str(self.original)]}]})
        self.decoder = self.put('decoder.json', {'source':str(self.original),'sourceSha256':file_ref(self.original)['sha256'],
            'audio':str(self.opcm),'audioSha256':file_ref(self.opcm)['sha256'],'clockBasis':'ORIGINAL_SOURCE',
            'offset':0,'gain':1,'clock':{'rate':48000,'channels':2,'samples':16000}})
        self.transcript = self.put('transcript.json', {'sourceAudioSha256':file_ref(self.opcm)['sha256'],
            'segments':[{'id':1,'words':[{'word':'word','start':.07,'end':.08,'probability':.5}]}]})
        self.raw = self.put('raw.json', {'asrSha256':self.transcript['sha256'],'sourceAudioSha256':file_ref(self.opcm)['sha256'],
            'words':[{'id':'W1','segmentId':1,'rawText':'word','sourceStartSeconds':.07,'sourceEndSeconds':.08,'probability':.5}]})
        self.obs = self.put('observations.json', {'evidenceClass':'REAL_OBSERVATION',
            'originalRawASRSha256':self.transcript['sha256'],'originalSourceSHA256':file_ref(self.original)['sha256'],
            'sourceIdentity':self.probe,'fourRemovals':[
                {'id':'removed','originalSourceInterval':{'sourceId':'original','startTick':140000,'endTick':190000},
                 'rawWordIds':[],'oldTargetIntervals':[],'contextualReason':'Synthetic historical gap'},
                {'id':'retained','originalSourceInterval':{'sourceId':'original','startTick':70000,'endTick':80000},
                 'rawWordIds':['W1'],'oldTargetIntervals':[],'contextualReason':'Synthetic retained context'}]})
        self.policy={'maxActualRetainedQuietTicks':200000,'rawSourceWords':self.raw,'rawTranscript':self.transcript,
                     'sourceEditObservations':self.obs,'removedContentRawWordIds':[]}
        self.bscope=self.accept('B-scope.json',self.bpcm)
        self.cscope=self.accept('C-scope.json',self.cpcm,self.bscope)
        self.rows=[{'pieceId':'old1','originalFrameIn':1,'originalFrameOut':4,'masterFrameIn':0,'masterFrameOut':3},
                   {'pieceId':'old2','originalFrameIn':6,'originalFrameOut':10,'masterFrameIn':3,'masterFrameOut':7}]
        actual=[]
        for row in self.rows:
            actual.append({'pieceId':row['pieceId'],'originalSourceId':'original',
                'normalizedSourceFrameIn30':row['originalFrameIn'],'normalizedSourceFrameOut30':row['originalFrameOut'],
                'derivedFrameIn30':row['masterFrameIn'],'derivedFrameOut30':row['masterFrameOut'],
                'acceptedAudioSampleIn':row['masterFrameIn']*1600,'acceptedAudioSampleOut':row['masterFrameOut']*1600,
                'originalAudioSourceSampleIn':row['originalFrameIn']*1600,'originalAudioSourceSampleOut':row['originalFrameOut']*1600,
                'normalSpeed':True})
        self.render=self.put('render.json', {'schema':'ep7-derived-master-render-receipt/v1',
            'status':'PASS_MEDIA_MECHANICS_PENDING_VISUAL_NATIVE','derivedNotOriginal':True,'allInputsUnchanged':True,
            'derivedMaster':{'path':str(self.master),'sha256':file_ref(self.master)['sha256']},
            'probeCommand':{'exitCode':0,'argv':['synthetic-probe',str(self.master)]},'originalSourceCutCrosswalk':actual})
        self.mprobe=self.put('master-probe.json', {'streams':[
            {'codec_type':'video','nb_read_frames':7,'avg_frame_rate':'30/1','duration_ts':7,'time_base':'1/30'},
            {'codec_type':'audio','codec_name':'pcm_s16le','sample_rate':48000,'channels':2,'duration_ts':11200,'time_base':'1/48000'}]})
        dh='sha256:'+hashlib.sha256(self.bdata).hexdigest()
        self.decoded=self.put('decoded.json', {'exitCode':0,'sampleExact':True,'sampleFrames':11200,'rate':48000,
            'channels':2,'decodedPCMDataSHA256':dh,'acceptedBPCMDataSHA256':dh,'argv':['synthetic-decoder',str(self.master)]})
        self.native={'materials':{'videos':[{'id':'master-material','path':str(self.master)}]},'tracks':[
            {'id':'main','type':'video','segments':[
                {'id':'N1','material_id':'master-material','source_timerange':{'start':33333,'duration':100000},
                 'target_timerange':{'start':0,'duration':100000},'speed':1,'volume':1},
                {'id':'N2','material_id':'master-material','source_timerange':{'start':133333,'duration':100000},
                 'target_timerange':{'start':100000,'duration':100000},'speed':1,'volume':1}]}]}
        self.nref=self.put('native.json',self.native)
        self.execution={'nativeHash':self.nref['sha256'],'audioHash':file_ref(self.cpcm)['sha256'],
            'captionPlan':{'mainTrackId':'main','words':[{'id':'W1'}]},
            'pauseProfile':{'windowMs':20,'hopMs':5,'methods':[{'kind':'RMS','thresholdsDbFS':[-48,-45]},
                                                          {'kind':'PEAK','thresholdsDbFS':[-36,-35]}]}}
        self.eref=self.put('execution.json',self.execution)
        self.source_map={'master':{'materialId':'master-material'}}
        self.record={'schema':'capcut-source-derivation/v1','evidenceClass':'REAL_OBSERVATION','status':'PASS_STRUCTURAL_NOT_HEARD',
            **{k:self.policy[k] for k in ('rawSourceWords','rawTranscript','sourceEditObservations')},
            'originalSource':{'id':'original','file':file_ref(self.original),'probe':self.probe,'pcm':file_ref(self.opcm),'decoderEvidence':self.decoder},
            'master':{'sourceId':'master','file':file_ref(self.master),'frameCount':7,'probe':self.mprobe,'renderReceipt':self.render,
                'decodedPCMProof':self.decoded,'acceptedPCM':file_ref(self.bpcm),'acceptanceEvidence':self.bscope},
            'frameRate':{'numerator':30,'denominator':1},'crosswalk':copy.deepcopy(self.rows),
            'currentAudio':{'file':file_ref(self.cpcm),'acceptanceEvidence':self.cscope,'masterSampleStart':1600,'masterSampleEnd':11200}}

    def wav(self,path,data):
        with wave.open(str(path),'wb') as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(48000);f.writeframes(data)

    def put(self,name,obj):
        p=self.root/name;p.write_text(json.dumps(obj),encoding='utf-8');return file_ref(p)

    def accept(self,name,audio,prior=None):
        reply=self.put(name+'-reply.json',{'evidenceClass':'REAL_OBSERVATION','source':'DIRECT_USER_MESSAGE',
            'sourceRef':'synthetic-not-a-real-human-call','message':'Synthetic declaration only'})
        return self.put(name,{'schema':'capcut-current-audio-scope-observation/v1','evidenceClass':'REAL_OBSERVATION',
            'basis':'USER_AUDIO_REVIEW','status':'ACCEPTED','audioGain1':file_ref(audio),'userReply':reply,
            'unresolvedCurrentAudioFeedback':[],'priorAcceptedScope':prior})

    def validate(self):
        return validate_source_derivation(self.put('derivation.json',self.record),self.nref,file_ref(self.cpcm),self.eref,self.source_map,self.policy)

    def test_positive_exact_composed_original_sample_map(self):
        r=self.validate()
        self.assertEqual(r['currentSamples'],9600)
        self.assertEqual(sum(p['sourceEndSample']-p['sourceStartSample'] for p in r['originalPieces']),9600)
        self.assertEqual(r['originalPieces'][0]['sourceStartSample'],3200)
        self.assertEqual(r['status'],'PASS_STRUCTURAL_NOT_HEARD')

    def test_dependency_integration_keeps_original_clock_and_pending_reviews(self):
        self.policy['sourceDerivation']=self.put('derivation.json',self.record)
        r=make_audio_edit_inventory(self.nref,file_ref(self.cpcm),self.eref,self.policy,self.source_map)
        self.assertEqual(r['sourceRemovals'][0]['currentRetainedIntersections'],[])
        self.assertEqual(len(r['sourceRemovals'][1]['currentRetainedIntersections']),1)
        self.assertEqual(set(r['sourceMap']),{'master'})
        inv=self.put('inventory.json',r)
        result=validate_audio_edit_inventory(inv,self.nref,file_ref(self.cpcm),self.eref,'REVIEW_DRAFT')
        self.assertEqual(len(result['pendingSourceRemovalIds']),2)
        with self.assertRaisesRegex(ValueError,'final-quiet-review-held-or-pending'):
            validate_audio_edit_inventory(inv,self.nref,file_ref(self.cpcm),self.eref,'FINAL_ACCEPTANCE')
        r['sourceDerivationReadback']['currentSamples']+=1
        with self.assertRaisesRegex(ValueError,'recomputed-sourceDerivationReadback'):
            validate_audio_edit_inventory(self.put('tampered.json',r),self.nref,file_ref(self.cpcm),self.eref,'REVIEW_DRAFT')

    def test_stale_master_hash(self):
        self.master.write_bytes(b'drift')
        with self.assertRaisesRegex(ValueError,'hash-drift'):self.validate()

    def test_crosswalk_gap(self):
        self.record['crosswalk'][1]['masterFrameIn']=4
        with self.assertRaisesRegex(ValueError,'crosswalk-gap-or-duration'):self.validate()

    def test_crosswalk_duplicate_original_range(self):
        self.record['crosswalk'][1].update(originalFrameIn=2,originalFrameOut=6)
        with self.assertRaisesRegex(ValueError,'original-overlap-or-bounds'):self.validate()

    def test_wrong_current_pcm_even_with_updated_file_and_acceptance_hash(self):
        self.wav(self.cpcm,b'\x00'*9600*4)
        self.record['currentAudio']['file']=file_ref(self.cpcm)
        with self.assertRaisesRegex(ValueError,'current-pcm-difference'):self.validate()

    def test_wrong_original_to_master_pcm(self):
        data=bytearray(self.pcm);data[3200*4]=1;self.wav(self.opcm,data)
        self.record['originalSource']['pcm']=file_ref(self.opcm)
        decoder=json.loads(Path(self.decoder['path']).read_text());decoder['audioSha256']=file_ref(self.opcm)['sha256']
        self.record['originalSource']['decoderEvidence']=self.put('decoder.json',decoder)
        transcript=json.loads(Path(self.transcript['path']).read_text());transcript['sourceAudioSha256']=file_ref(self.opcm)['sha256']
        self.transcript=self.put('transcript.json',transcript)
        raw=json.loads(Path(self.raw['path']).read_text());raw.update(sourceAudioSha256=file_ref(self.opcm)['sha256'],asrSha256=self.transcript['sha256'])
        self.raw=self.put('raw.json',raw)
        self.policy.update(rawSourceWords=self.raw,rawTranscript=self.transcript)
        self.record.update(rawSourceWords=self.raw,rawTranscript=self.transcript)
        with self.assertRaisesRegex(ValueError,'original-to-master-pcm'):self.validate()

    def test_history_audio_identity_cannot_be_claim_only(self):
        raw=json.loads(Path(self.raw['path']).read_text());raw['sourceAudioSha256']='sha256:'+'0'*64
        self.raw=self.put('raw.json',raw);self.policy['rawSourceWords']=self.raw;self.record['rawSourceWords']=self.raw
        with self.assertRaisesRegex(ValueError,'raw-history-original-audio-binding'):self.validate()

    def test_missing_original_history(self):
        self.record['rawSourceWords']=self.put('selected-only.json',{'words':[]})
        with self.assertRaisesRegex(ValueError,'original-history-reference'):self.validate()

    def test_missing_derivation_never_treats_master_as_original(self):
        with self.assertRaisesRegex(ValueError,'original-removal-bounds-or-source'):
            make_audio_edit_inventory(self.nref,file_ref(self.cpcm),self.eref,self.policy,self.source_map)

    def test_original_derived_frame_proof_mismatch(self):
        self.record['crosswalk'][1]['pieceId']='different'
        with self.assertRaisesRegex(ValueError,'render-crosswalk-row-drift'):self.validate()

    def test_current_window_gap_is_blocked(self):
        self.native['tracks'][0]['segments'][1]['source_timerange']['start']+=1000
        self.nref=self.put('native.json',self.native);self.execution['nativeHash']=self.nref['sha256'];self.eref=self.put('execution.json',self.execution)
        with self.assertRaisesRegex(ValueError,'current-window-gap-duplicate-or-sample-phase'):self.validate()

    def test_speed_change_is_blocked(self):
        self.native['tracks'][0]['segments'][0]['speed']=.5
        self.nref=self.put('native.json',self.native);self.execution['nativeHash']=self.nref['sha256'];self.eref=self.put('execution.json',self.execution)
        with self.assertRaisesRegex(ValueError,'current-normal-source-window'):self.validate()

    def test_wrong_probe_frame_count(self):
        self.record['master']['frameCount']=8
        with self.assertRaisesRegex(ValueError,'frame-count'):self.validate()

    def test_acceptance_missing_direct_reply(self):
        scope=json.loads(Path(self.cscope['path']).read_text());scope['userReply']=self.put('bad-reply.json',{'source':'MODEL'})
        self.record['currentAudio']['acceptanceEvidence']=self.put('C-scope.json',scope)
        with self.assertRaisesRegex(ValueError,'direct-audio-reply'):self.validate()

    def generic_fixture(self):
        legacy=json.loads(Path(self.render['path']).read_text())
        pcm=json.loads(Path(self.decoded['path']).read_text())
        decoded={'argv':pcm['argv'],'exitCode':0,'everyPCMByteEqual':True,'sampleFrames':pcm['sampleFrames'],
                 'dataSHA256':pcm['decodedPCMDataSHA256']}
        self.record['master']['decodedPCMProof']=self.put('generic-decoded.json',decoded)
        rows=[]
        for old in legacy['originalSourceCutCrosswalk']:
            row=copy.deepcopy(old)
            for a,b in [('normalizedSourceFrameIn30','normalizedSourceFrameIn'),('normalizedSourceFrameOut30','normalizedSourceFrameOut'),
                        ('derivedFrameIn30','derivedFrameIn'),('derivedFrameOut30','derivedFrameOut'),
                        ('originalAudioSourceSampleIn','originalSourceSampleIn'),('originalAudioSourceSampleOut','originalSourceSampleOut')]:
                row[b]=row.pop(a)
            row.pop('normalSpeed');rows.append(row)
        before={k:{**file_ref(p),'statIdentity':list((p.stat().st_dev,p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns,p.stat().st_ctime_ns))}
                for k,p in [('originalSource',self.original),('acceptedAudio',self.bpcm)]}
        generic={'schema':'capcut-aroll-master-receipt/v1','status':'PASS_MEDIA_MECHANICS_NOT_NATIVE_ACCEPTANCE',
            'derivedNotOriginal':True,'allInputsUnchanged':True,'derivedMaster':legacy['derivedMaster'],
            'sourceBefore':before,'sourceAfter':copy.deepcopy(before),'audio':decoded,
            'originalSourceCutCrosswalk':rows,'outputProbeCall':legacy['probeCommand']}
        self.record['master']['renderReceipt']=self.put('generic-render.json',generic)
        return generic

    def test_packaged_schema_frame_sample_equivalence(self):
        self.generic_fixture()
        self.assertEqual(self.validate()['currentSamples'],9600)

    def test_generic_aliases_do_not_leak_to_legacy_receipt(self):
        row=self.generic_fixture();row.pop('schema')
        self.record['master']['renderReceipt']=self.put('generic-render.json',row)
        with self.assertRaisesRegex(ValueError,'unsupported-render-receipt-schema'):self.validate()

    def test_generic_wrong_decode_hash_is_blocked(self):
        row=self.generic_fixture();row['audio']['dataSHA256']='sha256:'+'0'*64
        self.record['master']['decodedPCMProof']=self.put('generic-decoded.json',row['audio'])
        self.record['master']['renderReceipt']=self.put('generic-render.json',row)
        with self.assertRaisesRegex(ValueError,'generic-master-decoded-pcm-proof'):self.validate()

    def test_generic_input_stat_drift_is_blocked(self):
        row=self.generic_fixture();row['sourceAfter']['originalSource']['statIdentity'][2]+=1
        self.record['master']['renderReceipt']=self.put('generic-render.json',row)
        with self.assertRaisesRegex(ValueError,'generic-render-input-drift'):self.validate()

    def assert_protocol_fails_before_original_hash(self, expected):
        derivation_ref=self.put('derivation.json',self.record)
        actual_digest=source_derivation.digest
        def bounded_digest(path):
            if Path(path)==self.original:
                self.fail('Protocol error attempted expensive original-source hash')
            return actual_digest(path)
        with patch('source_derivation.digest',side_effect=bounded_digest):
            with self.assertRaisesRegex(ValueError,expected):
                validate_source_derivation(derivation_ref,self.nref,file_ref(self.cpcm),self.eref,self.source_map,self.policy)

    def test_unknown_receipt_rejected_before_original_hash(self):
        r=json.loads(Path(self.render['path']).read_text());r['schema']='unsupported/v99'
        self.record['master']['renderReceipt']=self.put('unknown-render.json',r)
        self.assert_protocol_fails_before_original_hash('unsupported-render-receipt-schema')

    def test_probe_header_rejected_before_original_hash(self):
        probe=json.loads(Path(self.mprobe['path']).read_text());probe['streams'][0]['nb_read_frames']=8
        self.record['master']['probe']=self.put('bad-probe.json',probe)
        self.assert_protocol_fails_before_original_hash('frame-count')

    def test_crosswalk_protocol_rejected_before_original_hash(self):
        self.record['crosswalk'][1]['masterFrameIn']+=1
        self.assert_protocol_fails_before_original_hash('crosswalk-gap-or-duration')

    def test_exact_observed_legacy_schema_is_supported(self):
        self.assertEqual(json.loads(Path(self.render['path']).read_text())['schema'],'ep7-derived-master-render-receipt/v1')
        self.assertEqual(self.validate()['currentSamples'],9600)

    def copied_master_fixture(self):
        dest=self.root/'short-master.mov';dest.write_bytes(self.master.read_bytes())
        receipt={'schema':'capcut-task-byte-identical-media-copy/v1',
            'status':'BYTE_IDENTICAL_COPY_VERIFIED_NATIVE_RELINK_PENDING','sourceDeletedOrModified':False,
            'original':{**file_ref(self.master),'size':self.master.stat().st_size},
            'copy':{**file_ref(dest),'size':dest.stat().st_size}}
        self.record['master']['copyProvenance']=self.put('copy-provenance.json',receipt)
        self.native['materials']['videos'][0]['path']=str(dest)
        self.nref=self.put('native.json',self.native);self.execution['nativeHash']=self.nref['sha256'];self.eref=self.put('execution.json',self.execution)
        return dest,receipt

    def test_same_byte_copied_master_preserves_render_and_audio_history(self):
        dest,receipt=self.copied_master_fixture();result=self.validate()
        copied=result['masterCopyReadback']
        self.assertEqual(copied['renderedMaster']['path'],str(self.master))
        self.assertEqual(copied['currentMaster']['path'],str(dest))
        self.assertEqual(copied['currentMaster']['sha256'],file_ref(self.master)['sha256'])
        self.assertEqual(result['currentSamples'],9600)
        self.assertIn('NOT_CERTIFIED',copied['status'])

    def test_copy_receipt_cannot_point_to_unrelated_original(self):
        dest,r=self.copied_master_fixture();r['original']['path']=str(self.original)
        self.record['master']['copyProvenance']=self.put('bad-copy.json',r)
        self.assert_protocol_fails_before_original_hash('copy-provenance-identity')

    def test_copy_identity_hash_must_equal_rendered_master(self):
        dest,r=self.copied_master_fixture();r['copy']['sha256']='sha256:'+'0'*64
        self.record['master']['copyProvenance']=self.put('bad-copy.json',r)
        self.assert_protocol_fails_before_original_hash('copy-provenance-identity')

    def test_actual_copy_bytes_drift_is_rejected(self):
        dest,r=self.copied_master_fixture();dest.write_bytes(b'drifted actual bytes')
        with self.assertRaisesRegex(ValueError,'hash-drift'):self.validate()

    def test_equal_but_false_reported_sizes_are_rejected(self):
        dest,r=self.copied_master_fixture();r['original']['size']+=1;r['copy']['size']+=1
        self.record['master']['copyProvenance']=self.put('bad-copy.json',r)
        with self.assertRaisesRegex(ValueError,'copy-actual-size'):self.validate()

    def test_copied_master_path_requires_explicit_copy_provenance(self):
        self.copied_master_fixture();self.record['master'].pop('copyProvenance')
        with self.assertRaisesRegex(ValueError,'current-master-material'):self.validate()

    def test_native_material_must_use_exact_verified_copy(self):
        dest,r=self.copied_master_fixture();self.native['materials']['videos'][0]['path']=str(self.root/'other.mov')
        self.nref=self.put('native.json',self.native);self.execution['nativeHash']=self.nref['sha256'];self.eref=self.put('execution.json',self.execution)
        with self.assertRaisesRegex(ValueError,'current-master-material'):self.validate()

    def test_original_rendered_master_must_remain_present(self):
        self.copied_master_fixture();self.master.unlink()
        with self.assertRaisesRegex(ValueError,'file'):self.validate()

    def test_copy_symlink_is_refused_without_creating_any_link(self):
        dest,r=self.copied_master_fixture();original=Path.is_symlink
        with patch.object(Path,'is_symlink',lambda p: p==dest or original(p)):
            with self.assertRaisesRegex(ValueError,'file'):self.validate()

    def test_copy_parent_junction_is_refused_without_creating_any_link(self):
        dest,r=self.copied_master_fixture();dest2=self.root/'copy-dir'/'short-master.mov';dest2.parent.mkdir();dest2.write_bytes(dest.read_bytes())
        r['copy']={**file_ref(dest2),'size':dest2.stat().st_size}
        self.record['master']['copyProvenance']=self.put('copy2.json',r)
        original=Path.is_junction
        with patch.object(Path,'is_junction',lambda p: p==dest2.parent or original(p)):
            with self.assertRaisesRegex(ValueError,'linked-file'):self.validate()


if __name__=='__main__':unittest.main()
