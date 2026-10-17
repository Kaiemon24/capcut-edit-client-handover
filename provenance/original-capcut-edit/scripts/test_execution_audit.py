"""Synthetic coverage/semantic fixtures; never actual hearing or native playback."""
import copy,json,tempfile,unittest,wave
from pathlib import Path
from execution_audit import scan_audio,cut_inventory,check_caption_plan,digest,load_ref

PROFILE={'windowMs':20,'hopMs':5,'methods':[{'kind':'RMS','thresholdsDbFS':[-50,-45]},{'kind':'PEAK','thresholdsDbFS':[-40,-35]}]}

class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def wav(self,count=16000,channels=1,pcm=None):
        p=self.root/'test.wav'
        with wave.open(str(p),'wb') as f:f.setnchannels(channels);f.setsampwidth(2);f.setframerate(16000);f.writeframes(pcm or b'\0\0'*count*channels)
        return p
    def test_strictly_200ms_stays_below_selection(self):
        self.assertEqual(scan_audio(self.wav(3200),PROFILE)['candidates'],[])
    def test_one_sample_over_200ms_is_selected_before_rounding(self):
        self.assertEqual(len(scan_audio(self.wav(3201),PROFILE)['candidates']),4)
    def test_no_asr_mask_input_can_veto_candidates(self):
        self.assertEqual(len(scan_audio(self.wav(),PROFILE)['candidates']),4)
    def test_noise_sensitivity_is_separate_from_duration(self):
        import array
        samples=array.array('h',[500]*16000)
        profile={'windowMs':20,'hopMs':5,'methods':[{'kind':'RMS','thresholdsDbFS':[-40,-35]},{'kind':'PEAK','thresholdsDbFS':[-40,-35]}]}
        result=scan_audio(self.wav(pcm=samples.tobytes()),profile)
        self.assertEqual({x['thresholdDbFS'] for x in result['candidates']},{-35})
        self.assertEqual(result['criterion']['minimumQuietDurationTicks'],200000)
    def test_loud_signal_is_not_selected_by_these_thresholds(self):
        import array
        self.assertFalse(scan_audio(self.wav(pcm=array.array('h',[20000]*16000).tobytes()),PROFILE)['candidates'])
    def test_antiphase_stereo_cannot_cancel_to_quiet(self):
        import array
        self.assertFalse(scan_audio(self.wav(channels=2,pcm=array.array('h',[20000,-20000]*16000).tobytes()),PROFILE)['candidates'])
    def test_missing_sensitivity_survey_rejected(self):
        p=copy.deepcopy(PROFILE);p['methods'][0]['thresholdsDbFS']=[-45]
        with self.assertRaises(ValueError):scan_audio(self.wav(),p)
    def test_duplicate_methods_rejected(self):
        p=copy.deepcopy(PROFILE);p['methods'][1]['kind']='RMS'
        with self.assertRaises(ValueError):scan_audio(self.wav(),p)
    def test_no_normalization_or_review_flag_is_emitted(self):
        r=scan_audio(self.wav(),PROFILE);self.assertEqual(r['analysisGainApplied'],1);self.assertEqual(r['candidateClass'],'MACHINE_RISK_NOT_QUIET');self.assertNotIn('reviewed',r)
    def test_all_head_internal_tail_runs_are_accounted(self):
        import array
        pcm=array.array('h',[0]*4800+[20000]*1600+[0]*4800+[20000]*1600+[0]*4800)
        result=scan_audio(self.wav(pcm=pcm.tobytes()),PROFILE)
        self.assertEqual({c['kind'] for c in result['candidates']},{'HEAD','INTERNAL','TAIL'})

class CaptionTests(unittest.TestCase):
    def setUp(self):
        self.d={'materials':{'texts':[{'id':'t1','content':json.dumps({'text':'có nhà ở mặt tiền'})},{'id':'t2','content':json.dumps({'text':'trung tâm'})}]},
            'tracks':[{'id':'main','type':'video','segments':[{'id':'p1','material_id':'src','speed':1,'source_timerange':{'start':0,'duration':400000},'target_timerange':{'start':0,'duration':400000}},
                {'id':'p2','material_id':'src','speed':1,'source_timerange':{'start':600000,'duration':1400000},'target_timerange':{'start':400000,'duration':1400000}}]},
                {'type':'text','segments':[{'id':'c1','material_id':'t1','target_timerange':{'start':0,'duration':1000000}},{'id':'c2','material_id':'t2','target_timerange':{'start':1000000,'duration':800000}}]}]}
        text='có nhà ở mặt tiền trung tâm'.split()
        words=[{'id':f'w{i}','text':t,'sentenceId':'s1','sourceId':'src','sourceStartTick':i*250000,'sourceEndTick':(i+1)*250000} for i,t in enumerate(text)]
        self.lock={'id':'noun','wordIds':['w1','w2','w3','w4'],'rawText':'nhà ở mặt tiền','kind':'noun-phrase'}
        self.p={'mainTrackId':'main','words':words,'cues':[{'segmentId':'c1','rawWordIds':[f'w{i}' for i in range(5)],'nativeText':'có nhà ở mặt tiền'},
            {'segmentId':'c2','rawWordIds':['w5','w6'],'nativeText':'trung tâm'}],
            'semanticReview':{'basis':'whole-transcript-semantic-review','coveredWordIds':[w['id'] for w in words]},'protectedSpans':[self.lock]}
        self.b={'protectedSpans':[copy.deepcopy(self.lock)]}
    def test_valid_noun_kept_with_short_remainder(self):self.assertEqual(check_caption_plan(self.d,self.p,self.b),[])
    def test_reported_noun_split_is_rejected(self):
        self.p['cues'][0]['rawWordIds']=['w0','w1'];self.p['cues'][1]['rawWordIds']=['w2','w3','w4','w5','w6']
        self.assertIn('split-protected-span',check_caption_plan(self.d,self.p,self.b))
    def test_dropping_prior_lock_cannot_make_split_pass(self):
        self.p['protectedSpans']=[];self.assertIn('prior-lock-dropped-or-redefined',check_caption_plan(self.d,self.p,self.b))
    def test_redefining_prior_lock_cannot_make_split_pass(self):
        self.p['protectedSpans'][0]=dict(self.lock,wordIds=['w1','w2'],rawText='nhà ở')
        self.assertIn('prior-lock-dropped-or-redefined',check_caption_plan(self.d,self.p,self.b))
    def test_raw_word_drop_is_rejected(self):
        self.p['cues'][1]['rawWordIds']=['w5'];self.assertIn('raw-word-once-in-order',check_caption_plan(self.d,self.p,self.b))
    def test_cross_sentence_cue_rejected(self):
        self.p['words'][4]['sentenceId']='s2';self.assertIn('logical-sentence-boundary',check_caption_plan(self.d,self.p,self.b))
    def test_over_six_display_words_rejected(self):
        self.p['cues'][0]['nativeText']='một hai ba bốn năm sáu bảy'
        self.assertIn('caption-one-line-six-word-policy',check_caption_plan(self.d,self.p,self.b))
    def test_partial_semantic_review_rejected(self):
        self.p['semanticReview']['coveredWordIds']=[];self.assertIn('whole-transcript-semantic-coverage',check_caption_plan(self.d,self.p,self.b))
    def test_cut_inventory_covers_each_current_cue_and_cut(self):
        r=cut_inventory(self.d,self.p);self.assertEqual(len(r['allCues']),2);self.assertEqual(len(r['allCuts']),1)
    def test_first_word_source_legs_straddle_cut(self):
        self.p['words'][0].update(sourceStartTick=300000,sourceEndTick=700000)
        r=cut_inventory(self.d,self.p)['allCues'][0]
        self.assertEqual(len(r['firstWordSourceLegs']),2)
        self.assertIn('FIRST_WORD_MULTIPLE_OR_MISSING_SOURCE_LEGS',r['riskReasons'])
    def test_first_word_isolated_in_prior_piece_is_not_omitted(self):
        self.p['words'][0].update(sourceStartTick=100000,sourceEndTick=200000)
        for w in self.p['words'][1:5]:w.update(sourceStartTick=700000,sourceEndTick=800000)
        self.assertIn('FIRST_WORD_ISOLATED_FROM_REMAINING_WORDS',cut_inventory(self.d,self.p)['allCues'][0]['riskReasons'])
    def test_wrong_main_track_blocks(self):
        self.p['mainTrackId']='overlay'
        with self.assertRaises(ValueError):cut_inventory(self.d,self.p)
    def test_nested_locks_can_share_a_cue(self):
        self.p['protectedSpans'].append({'id':'nested','wordIds':['w3','w4'],'rawText':'mặt tiền','kind':'noun-phrase'})
        self.assertEqual(check_caption_plan(self.d,self.p,self.b),[])

class LongEnumerationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.lead='vì vậy phải nhớ kỹ nguyên tắc an toàn thứ 3'
        a=self.lead.split();b='nếu phải'.split();self.words=[{'id':str(i),'text':v,'sentenceId':'lead' if i<len(a) else 'content'} for i,v in enumerate(a+b)]
        self.cues=[{'segmentId':'lead','rawWordIds':[str(i) for i in range(len(a))],'nativeText':self.lead},{'segmentId':'content','rawWordIds':[str(i) for i in range(len(a),len(a)+len(b))],'nativeText':'3. Nếu phải'}]
        self.d={'materials':{'texts':[{'id':'a','content':json.dumps({'text':self.lead})},{'id':'b','content':json.dumps({'text':'3. Nếu phải'})}]},'tracks':[{'type':'text','segments':[{'id':'lead','material_id':'a','target_timerange':{'start':0,'duration':1000000}},{'id':'content','material_id':'b','target_timerange':{'start':1000000,'duration':1000000}}]}]}
        decision=self.root/'decision.json';decision.write_text(json.dumps({'authority':'explicit-user-request','scope':'preserve-long-enumeration-leadin-and-prefix-main-content','userQuote':'synthetic user instruction fixture'}),encoding='utf-8')
        self.item={'segmentId':'lead','rawWordIds':self.cues[0]['rawWordIds'],'ordinal':3,'rawLeadIn':self.lead,'markerWordIds':[str(len(a)-2),str(len(a)-1)],'contentSegmentId':'content','firstContentWordId':str(len(a)),'preserved':True,'decision':{'path':str(decision),'sha256':digest(decision)}}
        self.p={'words':self.words,'cues':self.cues,'semanticReview':{'basis':'whole-transcript-semantic-review','coveredWordIds':[w['id'] for w in self.words]},'protectedSpans':[],'preservedEnumerationLeadIns':[self.item]};self.base={'protectedSpans':[]}
    def check(self):return check_caption_plan(self.d,self.p,self.base)
    def test_exact_long_lead_is_only_scoped_word_limit_exception(self):self.assertEqual(self.check(),[])
    def test_without_exception_long_cue_remains_blocked(self):
        self.p.pop('preservedEnumerationLeadIns');self.assertIn('caption-one-line-six-word-policy',self.check())
    def test_stale_user_decision_blocks(self):
        self.item['decision']['sha256']='sha256:'+'0'*64;self.assertIn('invalid-preserved-long-enumeration',self.check())
    def test_unbound_first_content_word_blocks(self):
        self.item['firstContentWordId']='0';self.assertIn('invalid-preserved-long-enumeration',self.check())
    def test_changed_ordinal_or_missing_capital_blocks(self):
        for text in ('2. Nếu phải','3. nếu phải','Nếu phải'):
            self.cues[1]['nativeText']=text
            self.assertIn('invalid-preserved-long-enumeration',self.check())
    def test_preserved_lead_word_cannot_disappear(self):
        self.cues[0]['nativeText']=self.lead.replace('an toàn ','')
        self.assertIn('invalid-preserved-long-enumeration',self.check())
    def test_duplicate_or_global_exception_not_accepted(self):
        self.p['preservedEnumerationLeadIns'].append(copy.deepcopy(self.item))
        self.assertIn('invalid-preserved-long-enumeration',self.check())
    def test_ordinary_overlong_content_does_not_inherit_exception(self):
        self.cues[1]['nativeText']='3. Nếu phải đi xem thực tế nhà';self.d['materials']['texts'][1]['content']=json.dumps({'text':self.cues[1]['nativeText']})
        self.assertIn('caption-one-line-six-word-policy',self.check())

    def test_compound_raw_record_count_uses_actual_whitespace_words(self):
        words=['và','thứ nhất','là','về','nội','dung']
        self.p['words']=[{'id':str(i),'text':v,'sentenceId':'lead' if i<4 else 'content'} for i,v in enumerate(words)]
        self.cues[0].update(rawWordIds=['0','1','2','3'],nativeText='và thứ nhất là về');self.cues[1].update(rawWordIds=['4','5'],nativeText='1. Nội dung')
        self.d['materials']['texts'][0]['content']=json.dumps({'text':self.cues[0]['nativeText']});self.d['materials']['texts'][1]['content']=json.dumps({'text':self.cues[1]['nativeText']})
        self.p['semanticReview']['coveredWordIds']=[str(i) for i in range(6)]
        self.item.update(rawWordIds=['0','1','2','3'],ordinal=1,rawLeadIn='và thứ nhất là về',markerWordIds=['1'],firstContentWordId='4')
        self.assertEqual(self.check(),[])

if __name__=='__main__':unittest.main()
