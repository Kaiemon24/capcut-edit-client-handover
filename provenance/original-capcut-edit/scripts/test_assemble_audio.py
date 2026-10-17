"""Synthetic PCM assembly proof; no fixture establishes speech or native quality."""
import array,copy,json,sys,tempfile,unittest,wave
from pathlib import Path
from assemble_audio import assemble_audio,sha

class AssembleAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.original=self.root/'original.mp4';self.original.write_bytes(b'synthetic original identity only')
        self.pcm=self.root/'decoded.wav';values=array.array('h',range(64))
        if sys.byteorder!='little':values.byteswap()
        self.raw=values.tobytes()
        with wave.open(str(self.pcm),'wb') as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(8000);f.writeframes(self.raw)
        self.proof=self.root/'decode.json'
        self.decode={'source':str(self.original),'sourceSha256':sha(self.original),'audio':str(self.pcm),
            'audioSha256':sha(self.pcm),'clockBasis':'ORIGINAL_SOURCE','offset':0,'gain':1,
            'clock':{'rate':8000,'channels':2,'samples':32},'hearing':'NOT_PERFORMED'}
        self.proof.write_text(json.dumps(self.decode),'utf-8')
        self.binding={'sourceId':'source','path':str(self.pcm),'sha256':sha(self.pcm),
            'originalSourcePath':str(self.original),'originalSourceSHA256':sha(self.original),
            'sourceOffsetTicks':0,'decoderEvidenceRef':{'path':str(self.proof),'sha256':sha(self.proof)}}
        self.plan={'schema':'capcut-audio-assembly-plan/v1','pcmBindings':[self.binding],
            'mainPieces':[{'id':'one','sourceId':'source','sourceInTicks':1000,'sourceOutTicks':2000,'targetInTicks':0},
                {'id':'two','sourceId':'source','sourceInTicks':2500,'sourceOutTicks':3500,'targetInTicks':1000}]}
        self.output=self.root/'edited.wav'
    def update_proof(self):
        self.proof.write_text(json.dumps(self.decode),'utf-8');self.binding['decoderEvidenceRef']['sha256']=sha(self.proof)
    def run_audio(self,plan=None):return assemble_audio(plan or self.plan,self.output)
    def test_exact_original_stereo_samples_and_clocks(self):
        original_hash=sha(self.original);pcm_hash=sha(self.pcm);r=self.run_audio()
        with wave.open(str(self.output),'rb') as f:
            self.assertEqual((2,2,8000,16),(f.getnchannels(),f.getsampwidth(),f.getframerate(),f.getnframes()))
            self.assertEqual(self.raw[8*4:16*4]+self.raw[20*4:28*4],f.readframes(16))
        self.assertEqual([8,8],[x['frames'] for x in r['sourceSampleProjection']])
        self.assertEqual(original_hash,sha(self.original));self.assertEqual(pcm_hash,sha(self.pcm))
        self.assertEqual('PENDING',r['userAudioAcceptance']);self.assertFalse(r['resampled']);self.assertEqual(1,r['linearGain'])
    def test_reported_sample_quantization_without_stretch(self):
        p=copy.deepcopy(self.plan);p['mainPieces']=p['mainPieces'][:1]
        p['mainPieces'][0].update(sourceInTicks=1,sourceOutTicks=1001)
        r=self.run_audio(p);row=r['sourceSampleProjection'][0]
        self.assertEqual({'numerator':-1,'denominator':1},row['sourceInQuantizationErrorTicks'])
        self.assertEqual(8,r['frames']);self.assertFalse(r['stretched']);self.assertEqual(p['mainPieces'],r['mainPieces'])
    def test_unrepresentable_sample_map_is_rejected_before_output(self):
        p=copy.deepcopy(self.plan);p['mainPieces']=p['mainPieces'][:1]
        p['mainPieces'][0].update(sourceInTicks=62,sourceOutTicks=188)
        with self.assertRaisesRegex(ValueError,'unrepresentable'):self.run_audio(p)
        self.assertFalse(self.output.exists())
    def test_no_existing_output_or_receipt_overwrite(self):
        self.output.with_suffix('.assembly.json').write_text('preserve')
        with self.assertRaisesRegex(ValueError,'already-exists'):self.run_audio()
        self.assertFalse(self.output.exists())
    def test_input_hash_and_decoder_binding_drift(self):
        self.original.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'hash-drift'):self.run_audio()
        self.assertFalse(self.output.exists())
    def test_decoder_clock_or_gain_claim_mismatch(self):
        for field,value in [('gain',2),('offset',.001),('clockBasis','OUTPUT')]:
            with self.subTest(field=field):
                prior=self.decode[field];self.decode[field]=value;self.update_proof()
                with self.assertRaises(ValueError):self.run_audio()
                self.decode[field]=prior;self.update_proof()
        self.assertFalse(self.output.exists())
    def test_invalid_bounds_overlap_gap_speed_gain_and_duplicate_ids(self):
        changes=[lambda p:p['mainPieces'][0].update(sourceOutTicks=4001),
            lambda p:p['mainPieces'][1].update(targetInTicks=999),
            lambda p:p['mainPieces'][1].update(targetInTicks=1001),
            lambda p:p['mainPieces'][0].update(speed=2),lambda p:p['mainPieces'][0].update(volume=2),
            lambda p:p['mainPieces'][1].update(id='one'),
            lambda p:p['mainPieces'][1].update(sourceInTicks=1500,sourceOutTicks=2500),
            lambda p:p['mainPieces'][0].update(sourceInTicks=1.0)]
        for change in changes:
            with self.subTest(change=change):
                p=copy.deepcopy(self.plan);change(p)
                with self.assertRaises(ValueError):self.run_audio(p)
                self.assertFalse(self.output.exists())
    def test_no_audio_gate_or_caption_inputs_needed_to_prepare(self):
        self.assertNotIn('captions',self.plan);self.assertNotIn('audioReviewCheckpoint',self.plan)
        self.assertEqual('PREPARED_ONLY_NOT_HEARD',self.run_audio()['status'])
    def test_dictionary_bindings_and_exact_2x_supplier_chain(self):
        from prepare_voice_review import prepare_review
        p=copy.deepcopy(self.plan);p['pcmBindings']={'source':{k:v for k,v in self.binding.items() if k!='sourceId'}}
        self.run_audio(p);review=self.root/'listen.wav';r=prepare_review(self.output,review)
        self.assertTrue(r['exactDoubledSamples']);self.assertEqual(16,r['frames'])
    def test_native_and_instruction_output_roots_are_refused(self):
        for parts in [('COM.LVEDITOR.DRAFT',),('.CODEX','SKILLS')]:
            p=self.root.joinpath(*parts);p.mkdir(parents=True)
            with self.subTest(parts=parts):
                with self.assertRaisesRegex(ValueError,'cannot-be'):assemble_audio(self.plan,p/'out.wav')
                self.assertFalse((p/'out.wav').exists())
    def test_mixed_pcm_formats_require_explicit_supported_route(self):
        other=self.root/'mono.wav'
        with wave.open(str(other),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*32)
        binding=copy.deepcopy(self.binding);binding.update(sourceId='other',path=str(other),sha256=sha(other))
        p=copy.deepcopy(self.plan);p['pcmBindings'].append(binding);p['mainPieces'][1]['sourceId']='other'
        with self.assertRaisesRegex(ValueError,'mixed-pcm-formats'):self.run_audio(p)

if __name__=='__main__':unittest.main()
