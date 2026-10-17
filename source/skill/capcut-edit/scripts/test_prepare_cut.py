"""Synthetic timing/speaker safety tests; never live CapCut acceptance."""
from pathlib import Path
import copy, hashlib, json, tempfile, unittest
from prepare_cut import prepare, prepare_broll, prepare_intake, prepare_pacing, pacing_input, srt_time, nga_style_selection, nga_emoji_display

class TimingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.addCleanup(self.temp.cleanup)
        source=Path(self.temp.name)/'fixture.mp4';source.write_bytes(b'synthetic media placeholder; not a video')
        def words(start,text):
            return [{'id':f'w{i+1}','start':start+i*.5,'end':start+i*.5+.4,'text':w,'role':'main','reviewed':True,'evidenceRef':'synthetic-fixture'} for i,w in enumerate(text.split())]
        def take(id,unit,start,role='main',usable=True):
            w=words(start+.1,'Nga nói đúng.')
            return {'id':id,'unitId':unit,'sourceId':'s','in':start,'out':start+3,'role':role,'complete':usable,'usable':usable,'reviewed':True,'evidenceRef':'synthetic-fixture','reason':'Synthetic excluded attempt','timingBasis':'fresh-audio-review','words':w,'protectedSpanReview':{'reviewed':True,'evidenceRef':'synthetic-whole-transcript-review','basis':'whole-transcript-semantic-review','wordIds':[x['id'] for x in w]},'reviewedProtectedSpans':[],'reviewedSentences':[{'id':'s1','wordIds':[x['id'] for x in w],'text':'Nga nói đúng.','reviewed':True,'boundaryBasis':'reviewed-logical-sentence','evidenceRef':'synthetic-fixture'}],'phrases':[{'id':'p1','sentenceId':'s1','wordIds':[x['id'] for x in w],'start':w[0]['start'],'end':w[-1]['end'],'text':'Nga nói đúng.','role':'main','reviewed':True,'evidenceRef':'synthetic-fixture'}]}
        self.plan={'schemaVersion':'capcut-cut-plan/v2','name':'Test cut','canvas':{'width':1080,'height':1920,'fps':30},'sources':[{'id':'s','path':str(source),'sha256':'sha256:'+hashlib.sha256(source.read_bytes()).hexdigest(),'duration':100,'recordingOrder':0}],'units':[{'id':'u1','scriptText':'Nga nói đúng.'},{'id':'u2','scriptText':'Nga nói đúng.'}],'takes':[take('first','u1',10),take('last-good','u1',20),take('prompt','u1',30,'prompter'),take('failed-final','u1',40,usable=False),take('second','u2',60)]}
        self.plan['script']={'mode':'EXACT_CONTENT','evidenceRef':'synthetic-explicit-verbatim-script'}
        self.plan['verifiedNames']=[{'text':'Nga','reviewed':True,'evidenceRef':'synthetic-fixture'}]
    def test_last_usable_not_prompt_or_final_error(self):
        out=prepare(self.plan);report=json.loads(out['selection-report.json'])
        self.assertEqual([r['takeId'] for r in report['units']],['last-good','second'])
        self.assertEqual(report['duration'],6)
        spec=json.loads(out['compile-spec.json'])
        self.assertEqual([i['sourceStart'] for i in spec['tracks'][0]['items']],[20,60])
        self.assertEqual([i['start'] for i in spec['tracks'][0]['items']],[0,3])
        self.assertEqual(spec['operations'][0]['path'],'captions.srt')
        self.assertIn('00:00:00,100 --> 00:00:03,100',out['captions.srt'])
        self.assertIn('00:00:03,100 --> 00:00:04,500',out['captions.srt'])
        self.assertEqual(report['status'],'PREPARED_ONLY')
        self.assertEqual(report['visualSingleLine'],'PENDING')
        self.assertEqual(report['captionMode'],'REVIEWED_SHORT_PHRASE')
    def rejected(self,change):
        p=copy.deepcopy(self.plan);change(p)
        with self.assertRaises((ValueError,TypeError)):prepare(p)
    def test_missing_unit(self):self.rejected(lambda p:p['units'].append({'id':'missing','scriptText':'Thiếu.'}))
    def test_unknown_words(self):self.rejected(lambda p:p['takes'][1]['words'][0].update(role='unknown'))
    def test_prompt_inside_winner(self):self.rejected(lambda p:p['takes'][1]['words'][0].update(role='prompter'))
    def test_cut_word(self):self.rejected(lambda p:p['takes'][1]['words'][0].update(start=19.9))
    def test_overlap_words(self):self.rejected(lambda p:p['takes'][1]['words'][1].update(start=20.2))
    def test_hash_drift(self):self.rejected(lambda p:p['sources'][0].update(sha256='sha256:'+'0'*64))
    def test_unreviewed(self):self.rejected(lambda p:p['takes'][1].update(reviewed=False))
    def test_no_review_proof(self):self.rejected(lambda p:p['takes'][1].update(evidenceRef=''))
    def test_duplicate_ids(self):self.rejected(lambda p:p['takes'].append(copy.deepcopy(p['takes'][0])))
    def test_nan(self):self.rejected(lambda p:p['takes'][1].update(out=float('nan')))
    def test_outside_source(self):self.rejected(lambda p:p['takes'][1].update(out=101))
    def test_empty_words(self):self.rejected(lambda p:p['takes'][1].update(words=[]))
    def test_bad_folder_name(self):self.rejected(lambda p:p.update(name='../escape'))
    def test_reserved_name(self):self.rejected(lambda p:p.update(name='NUL.mp4'))
    def test_control_character_name(self):self.rejected(lambda p:p.update(name='bad\nname'))
    def test_invalid_canvas_type(self):self.rejected(lambda p:p.update(canvas=[]))
    def test_repeated_source_speech(self):
        self.rejected(lambda p:p['takes'][-1].update(**{'in':20,'out':23}))
    def test_chronology_across_files(self):
        p=copy.deepcopy(self.plan);s=copy.deepcopy(p['sources'][0]);s.update(id='s2',recordingOrder=1);p['sources'].append(s)
        t=copy.deepcopy(p['takes'][0]);t.update(id='later-file',sourceId='s2');p['takes'].append(t)
        self.assertEqual(json.loads(prepare(p)['selection-report.json'])['units'][0]['takeId'],'later-file')
    def test_fractional_clock_and_unicode(self):
        p=copy.deepcopy(self.plan);p['takes'][1].update(out=22.7345)
        result=prepare(p)
        self.assertIn('Nga nói đúng',result['captions.srt']);self.assertIn('00:00:02,834',result['captions.srt'])
        self.assertEqual(srt_time(3600.001),'01:00:00,001')
    def test_missing_reviewed_phrases(self):self.rejected(lambda p:p['takes'][1].pop('phrases'))
    def test_stale_timing_basis(self):self.rejected(lambda p:p['takes'][1].update(timingBasis='old-capcut-transcript'))
    def test_exact_script_mismatch(self):self.rejected(lambda p:p['units'][0].update(scriptText='Nga nói sai.'))
    def test_phrase_rewrites_word(self):self.rejected(lambda p:p['takes'][1]['phrases'][0].update(text='Nga nói sai.'))
    def test_phrase_omits_word(self):self.rejected(lambda p:p['takes'][1]['phrases'][0].update(wordIds=['w1','w2'],text='Nga nói'))
    def test_phrase_reorders_words(self):self.rejected(lambda p:p['takes'][1]['phrases'][0].update(wordIds=['w2','w1','w3']))
    def test_phrase_excludes_word_boundary(self):self.rejected(lambda p:p['takes'][1]['phrases'][0].update(start=20.2))
    def test_unreviewed_phrase(self):self.rejected(lambda p:p['takes'][1]['phrases'][0].update(reviewed=False))
    def test_duplicate_word_ids(self):self.rejected(lambda p:p['takes'][1]['words'][1].update(id='w1'))
    def test_word_by_word_rejected(self):
        p=copy.deepcopy(self.plan);t=p['takes'][1]
        t['phrases']=[{'id':f'p{i}','sentenceId':'s1','wordIds':[w['id']],'text':w['text'],'start':w['start'],'end':w['end'],'role':'main','reviewed':True,'evidenceRef':'synthetic-fixture'} for i,w in enumerate(t['words'])]
        with self.assertRaisesRegex(ValueError,'Word-by-word'):prepare(p)
    def test_long_phrase_needs_explicit_future_user_override(self):
        p=copy.deepcopy(self.plan);text='Một cụm lời nói được kiểm tra từ âm thanh và giữ nguyên thành câu dài có nhiều dấu tiếng Việt.'
        p['units'][0]['scriptText']=text;t=p['takes'][1];t['out']=35
        t['words']=[{'id':f'w{i}','text':w,'start':20.1+i*.5,'end':20.5+i*.5,'role':'main','reviewed':True,'evidenceRef':'synthetic-fixture'} for i,w in enumerate(text.split())]
        t['reviewedSentences']=[{'id':'s1','wordIds':[w['id'] for w in t['words']],'text':text,'reviewed':True,'boundaryBasis':'reviewed-logical-sentence','evidenceRef':'synthetic-fixture'}]
        t['protectedSpanReview']={'reviewed':True,'evidenceRef':'synthetic-whole-transcript-review','basis':'whole-transcript-semantic-review','wordIds':[w['id'] for w in t['words']]}
        t['reviewedProtectedSpans']=[]
        t['phrases']=[{'id':'long','text':text,'sentenceId':'s1','wordIds':[w['id'] for w in t['words']],'start':t['words'][0]['start'],'end':t['words'][-1]['end'],'role':'main','reviewed':True,'evidenceRef':'synthetic-fixture'}]
        with self.assertRaisesRegex(ValueError,'word limit'):prepare(p)
        p['captionPolicyOverride']={'authority':'explicit-user-request','evidenceRef':'synthetic-later-user-request','maxWordsPerCue':None,'removeCommasAndFullStops':False,'capitalization':'source','gapless':False}
        out=prepare(p)
        self.assertGreater(len(text),42)
        self.assertIn(text,out['captions.srt'])
        self.assertEqual(json.loads(out['selection-report.json'])['visualSingleLine'],'PENDING')
    def test_meaningful_two_phrase_mapping(self):
        p=copy.deepcopy(self.plan);t=p['takes'][1];w=t['words']
        t['phrases']=[{'id':'p1','sentenceId':'s1','wordIds':['w1','w2'],'text':'Nga nói','start':w[0]['start'],'end':w[1]['end'],'role':'main','reviewed':True,'evidenceRef':'synthetic-fixture'},{'id':'p2','sentenceId':'s1','wordIds':['w3'],'text':'đúng.','start':w[2]['start'],'end':w[2]['end'],'role':'main','reviewed':True,'evidenceRef':'synthetic-fixture'}]
        out=prepare(p)['captions.srt']
        self.assertIn('00:00:00,100 --> 00:00:01,100\nNga nói',out)
        self.assertIn('00:00:01,100 --> 00:00:03,100\nđúng',out)
    def set_text(self,p,text):
        p['units'][0]['scriptText']=text;t=p['takes'][1];t['out']=35
        t['words']=[{'id':f'w{i}','text':w,'start':20.1+i*.5,'end':20.5+i*.5,'role':'main','reviewed':True,'evidenceRef':'synthetic-fixture'} for i,w in enumerate(text.split())]
        t['reviewedSentences']=[{'id':'s1','wordIds':[w['id'] for w in t['words']],'text':text,'reviewed':True,'boundaryBasis':'reviewed-logical-sentence','evidenceRef':'synthetic-fixture'}]
        t['protectedSpanReview']={'reviewed':True,'evidenceRef':'synthetic-whole-transcript-review','basis':'whole-transcript-semantic-review','wordIds':[w['id'] for w in t['words']]}
        t['reviewedProtectedSpans']=[]
        t['phrases']=[{'id':'p','text':text,'sentenceId':'s1','wordIds':[w['id'] for w in t['words']],'start':t['words'][0]['start'],'end':t['words'][-1]['end'],'role':'main','reviewed':True,'evidenceRef':'synthetic-fixture'}]
    def test_six_words_pass_seven_reject(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Một Hai Ba Bốn Năm Sáu.')
        self.assertIn('một hai ba bốn năm sáu',prepare(p)['captions.srt'])
        self.set_text(p,'Một Hai Ba Bốn Năm Sáu Bảy.')
        with self.assertRaisesRegex(ValueError,'word limit'):prepare(p)
    def test_display_conventions_preserve_raw_script_and_input(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Ở TP.HCM, Nga Là Realtor.')
        p['verifiedNames'].append({'text':'TP.HCM','reviewed':True,'evidenceRef':'synthetic-fixture'})
        before=copy.deepcopy(p);out=prepare(p);cue=json.loads(out['selection-report.json'])['captionCues'][0]
        self.assertEqual(cue['text'],'ở TPHCM, Nga là realtor')
        self.assertEqual(cue['rawText'],'Ở TP.HCM, Nga Là Realtor.')
        self.assertEqual(p,before)
    def test_case_name_crosses_reviewed_cue_boundary(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Tại Palm City Nga Nói Đúng.')
        p['verifiedNames'].append({'text':'Palm City','reviewed':True,'evidenceRef':'synthetic-fixture'})
        t=p['takes'][1];w=t['words'];t['phrases']=[]
        for i,span in enumerate((w[:2],w[2:])):
            t['phrases'].append({'id':str(i),'text':' '.join(x['text'] for x in span),'sentenceId':'s1','wordIds':[x['id'] for x in span],'start':span[0]['start'],'end':span[-1]['end'],'role':'main','reviewed':True,'evidenceRef':'synthetic-fixture'})
        cues=json.loads(prepare(p)['selection-report.json'])['captionCues']
        self.assertEqual([c['text'] for c in cues[:2]],['tại Palm','City Nga nói đúng'])
        self.assertEqual(cues[0]['end'],cues[1]['start'])
    def test_unverified_name_rejected(self):self.rejected(lambda p:p['verifiedNames'][0].update(reviewed=False))
    def test_plain_number_and_trailing_period(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Có 1000 Người.')
        self.assertIn('có 1000 người',prepare(p)['captions.srt'])
    def test_ambiguous_numeric_punctuation_rejected(self):
        for text in ('Có 1.000 Người.','Có 1.5 Người.'):
            p=copy.deepcopy(self.plan);self.set_text(p,text)
            with self.assertRaisesRegex(ValueError,'numeric punctuation'):prepare(p)
    def test_reviewed_numeric_meaning_conversion(self):
        for raw,display in (('1.000','1000'),('1,5','một phẩy năm')):
            p=copy.deepcopy(self.plan);self.set_text(p,f'Có {raw} Người.')
            p['numericConversions']=[{'takeId':'last-good','wordId':'w1','sourceText':raw,'displayText':display,'reviewed':True,'evidenceRef':'synthetic-reviewed-numeric-meaning'}]
            out=prepare(p);self.assertIn(f'có {display} người',out['captions.srt'])
            self.assertEqual(json.loads(out['selection-report.json'])['captionCues'][0]['rawText'],f'Có {raw} Người.')
            p['numericConversions'][0]['reviewed']=False
            with self.assertRaisesRegex(ValueError,'review evidence'):prepare(p)
    def test_conversion_display_word_count_is_checked(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Một Hai Ba Bốn 1,5 Năm.')
        p['numericConversions']=[{'takeId':'last-good','wordId':'w4','sourceText':'1,5','displayText':'một phẩy năm','reviewed':True,'evidenceRef':'synthetic-reviewed-numeric-meaning'}]
        with self.assertRaisesRegex(ValueError,'word limit'):prepare(p)
    def test_numeric_conversion_cannot_rewrite_another_word(self):
        p=copy.deepcopy(self.plan);p['numericConversions']=[{'takeId':'last-good','wordId':'w1','sourceText':'Nga','displayText':'1000','reviewed':True,'evidenceRef':'synthetic-fixture'}]
        with self.assertRaisesRegex(ValueError,'source word'):prepare(p)
    def test_default_gapless_keeps_first_and_last_reviewed_bounds(self):
        p=copy.deepcopy(self.plan);p['takes'][1].update(out=22.7345)
        cues=json.loads(prepare(p)['selection-report.json'])['captionCues']
        self.assertEqual(cues[0]['start'],.1);self.assertEqual(cues[-1]['end'],4.2345)
        self.assertEqual(cues[0]['end'],cues[1]['start'])
    def test_style_name_does_not_authorize_override(self):
        self.rejected(lambda p:p.update(captionPolicyOverride={'authority':'style-preset','evidenceRef':'Nga','maxWordsPerCue':None}))
    def test_override_cannot_change_audio_or_native_requirement(self):
        self.rejected(lambda p:p.update(captionPolicyOverride={'authority':'explicit-user-request','evidenceRef':'synthetic-fixture','requireNativeProof':False}))
    def test_invalid_row_type(self):self.rejected(lambda p:p['takes'][1]['words'].append('bad'))
    def test_v1_needs_review_not_automatic_conversion(self):self.rejected(lambda p:p.update(schemaVersion='capcut-cut-plan/v1'))


    def test_missing_sentence_partition_rejected(self):self.rejected(lambda p:p['takes'][1].pop('reviewedSentences'))
    def test_unreviewed_sentence_rejected(self):self.rejected(lambda p:p['takes'][1]['reviewedSentences'][0].update(reviewed=False))
    def test_asr_segment_is_not_logical_sentence(self):self.rejected(lambda p:p['takes'][1]['reviewedSentences'][0].update(boundaryBasis='asr-segment'))
    def test_sentence_without_evidence_rejected(self):self.rejected(lambda p:p['takes'][1]['reviewedSentences'][0].update(evidenceRef=''))
    def test_duplicate_sentence_identity_rejected(self):self.rejected(lambda p:p['takes'][1]['reviewedSentences'].append(copy.deepcopy(p['takes'][1]['reviewedSentences'][0])))
    def test_sentence_omits_raw_word_rejected(self):self.rejected(lambda p:p['takes'][1]['reviewedSentences'][0].update(wordIds=['w1','w2'],text='Nga nói'))
    def test_sentence_reorders_raw_words_rejected(self):self.rejected(lambda p:p['takes'][1]['reviewedSentences'][0].update(wordIds=['w2','w1','w3']))
    def test_sentence_changes_raw_text_rejected(self):self.rejected(lambda p:p['takes'][1]['reviewedSentences'][0].update(text='Nga nói đúng'))
    def test_missing_cue_sentence_identity_rejected(self):self.rejected(lambda p:p['takes'][1]['phrases'][0].pop('sentenceId'))
    def test_unknown_cue_sentence_identity_rejected(self):self.rejected(lambda p:p['takes'][1]['phrases'][0].update(sentenceId='unknown'))
    def define_sentences(self,t,ranges):
        t['reviewedSentences']=[]
        for i,span in enumerate(ranges):
            t['reviewedSentences'].append({'id':f's{i+1}','wordIds':[w['id'] for w in span],'text':' '.join(w['text'] for w in span),'reviewed':True,'boundaryBasis':'reviewed-logical-sentence','evidenceRef':'synthetic-reviewed-meaning'})
    def define_cues(self,t,groups):
        t['phrases']=[]
        for i,(sentence_id,span) in enumerate(groups):
            t['phrases'].append({'id':f'p{i}','sentenceId':sentence_id,'wordIds':[w['id'] for w in span],'text':' '.join(w['text'] for w in span),'start':span[0]['start'],'end':span[-1]['end'],'role':'main','reviewed':True,'evidenceRef':'synthetic-reviewed-cue'})
    def transition_plan(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Giải thích đơn giản là như vậy. Trong bất động sản')
        t=p['takes'][1];w=t['words'];self.define_sentences(t,[w[:7],w[7:]])
        self.define_cues(t,[('s1',w[:4]),('s1',w[4:7]),('s2',w[7:])])
        return p
    def test_production_sentence_transition_keeps_four_plus_three(self):
        p=self.transition_plan();before=copy.deepcopy(p)
        report=json.loads(prepare(p)['selection-report.json']);cues=report['captionCues'][:3]
        self.assertEqual([c['text'] for c in cues],['giải thích đơn giản','là như vậy','trong bất động sản'])
        self.assertEqual([c['sentenceId'] for c in cues],['s1','s1','s2'])
        self.assertEqual([wid for c in cues for wid in c['wordIds']],[w['id'] for w in p['takes'][1]['words']])
        self.assertEqual(cues[0]['end'],cues[1]['start']);self.assertEqual(cues[1]['end'],cues[2]['start'])
        self.assertEqual(cues[0]['start'],.1);self.assertEqual(p,before)
    def test_six_word_cross_sentence_cue_rejected_before_punctuation(self):
        p=self.transition_plan();t=p['takes'][1];w=t['words']
        self.define_cues(t,[('s1',w[:5]),('s1',w[5:])])
        self.assertEqual(len(w[5:]),6)
        with self.assertRaisesRegex(ValueError,'one reviewed logical sentence'):prepare(p)
    def test_sentence_overlap_rejected(self):
        p=self.transition_plan();t=p['takes'][1];w=t['words'];self.define_sentences(t,[w[:7],w[6:]])
        with self.assertRaisesRegex(ValueError,'contiguously'):prepare(p)
    def test_short_real_sentences_are_not_word_by_word_fragmentation(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Có? Không.')
        t=p['takes'][1];w=t['words'];self.define_sentences(t,[w[:1],w[1:]])
        self.define_cues(t,[('s1',w[:1]),('s2',w[1:])])
        self.assertEqual([c['text'] for c in json.loads(prepare(p)['selection-report.json'])['captionCues'][:2]],['có?','không'])
    def test_internal_comma_colon_question_retained_no_punctuation_invented(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Vì Sao: Có, 1000 Người?')
        cue=json.loads(prepare(p)['selection-report.json'])['captionCues'][0]
        self.assertEqual(cue['text'],'vì sao: có, 1000 người?')
        self.assertFalse(any(c in cue['text'] for c in '.!;'))
    def test_cue_trailing_comma_removed_without_removing_internal_comma(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Một, Hai, Ba Bốn.')
        t=p['takes'][1];w=t['words'];self.define_cues(t,[('s1',w[:2]),('s1',w[2:])])
        self.assertEqual([c['text'] for c in json.loads(prepare(p)['selection-report.json'])['captionCues'][:2]],['một, hai','ba bốn'])
    def test_reviewed_name_keeps_case_with_internal_comma_and_question(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Ở TP.HCM, Nga Là Realtor?')
        p['verifiedNames'].append({'text':'TP.HCM','reviewed':True,'evidenceRef':'synthetic-name-review'})
        self.assertEqual(json.loads(prepare(p)['selection-report.json'])['captionCues'][0]['text'],'ở TPHCM, Nga là realtor?')
    def test_numeric_comma_preserves_exact_value_and_unit(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Có 1,5 m2.')
        self.assertIn('có 1,5 m2',prepare(p)['captions.srt'])
    def test_reviewed_numeric_dot_conversion_preserves_unit(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Có 1.500 m2.')
        p['numericConversions']=[{'takeId':'last-good','wordId':'w1','sourceText':'1.500','displayText':'1500','reviewed':True,'evidenceRef':'synthetic-reviewed-number-and-unit'}]
        self.assertIn('có 1500 m2',prepare(p)['captions.srt'])
    def test_numeric_display_with_dot_still_rejected(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Có 1.500 m2.')
        p['numericConversions']=[{'takeId':'last-good','wordId':'w1','sourceText':'1.500','displayText':'1.500','reviewed':True,'evidenceRef':'synthetic-reviewed-number'}]
        with self.assertRaisesRegex(ValueError,'no full stops'):prepare(p)
    def test_names_do_not_match_across_real_sentence_boundary(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Palm. City Nga')
        p['verifiedNames'].append({'text':'Palm City','reviewed':True,'evidenceRef':'synthetic-name-review'})
        t=p['takes'][1];w=t['words'];self.define_sentences(t,[w[:1],w[1:]])
        self.define_cues(t,[('s1',w[:1]),('s2',w[1:])])
        self.assertEqual([c['text'] for c in json.loads(prepare(p)['selection-report.json'])['captionCues'][:2]],['palm','city Nga'])
    def test_override_cannot_disable_sentence_boundary_proof(self):
        self.rejected(lambda p:p.update(captionPolicyOverride={'authority':'explicit-user-request','evidenceRef':'synthetic-request','requireSingleReviewedSentence':False}))
    def test_explicit_new_punctuation_override_is_bounded(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Một, Hai Ba.')
        p['captionPolicyOverride']={'authority':'explicit-user-request','evidenceRef':'synthetic-request','retainInternalCommas':False}
        self.assertIn('một hai ba',prepare(p)['captions.srt'])
    def test_conflicting_legacy_and_new_punctuation_override_rejected(self):
        self.rejected(lambda p:p.update(captionPolicyOverride={'authority':'explicit-user-request','evidenceRef':'synthetic-request','removeCommasAndFullStops':True,'retainInternalCommas':True}))


    def protect(self,t,groups,kind='noun-phrase'):
        t['reviewedProtectedSpans']=[{'id':f'protected-{i}','sentenceId':'s1','wordIds':[w['id'] for w in group],'text':' '.join(w['text'] for w in group),'kind':kind,'reviewed':True,'evidenceRef':'synthetic-semantic-review'} for i,group in enumerate(groups)]
    def test_protected_noun_formula_whole_cue(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Đây là công thức bỏ túi.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[2:]])
        self.define_cues(t,[('s1',w[:2]),('s1',w[2:])])
        cue=json.loads(prepare(p)['selection-report.json'])['captionCues'][1]
        self.assertEqual(cue['text'],'công thức bỏ túi');self.assertEqual(cue['protectedSpanIds'],['protected-0'])
    def test_protected_noun_formula_rejects_split_even_below_six(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Đây là công thức bỏ túi.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[2:]]);self.define_cues(t,[('s1',w[:4]),('s1',w[4:])])
        with self.assertRaisesRegex(ValueError,'splits a reviewed protected'):prepare(p)
    def test_protected_sales_audience_three_words(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Cho những bạn sale biết.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[1:4]]);self.define_cues(t,[('s1',w[:3]),('s1',w[3:])])
        with self.assertRaisesRegex(ValueError,'splits a reviewed protected'):prepare(p)
        self.define_cues(t,[('s1',w)]);self.assertIn('cho những bạn sale biết',prepare(p)['captions.srt'])
    def test_whole_review_missing_rejected(self):self.rejected(lambda p:p['takes'][1].pop('protectedSpanReview'))
    def test_whole_review_partial_or_reordered_rejected(self):
        for ids in (['w1','w2'],['w2','w1','w3']):
            self.rejected(lambda p:p['takes'][1]['protectedSpanReview'].update(wordIds=ids))
    def test_whole_review_inference_only_or_unreviewed_rejected(self):
        self.rejected(lambda p:p['takes'][1]['protectedSpanReview'].update(basis='automatic-grammar-inference'))
        self.rejected(lambda p:p['takes'][1]['protectedSpanReview'].update(reviewed=False))
    def test_explicit_empty_inventory_requires_whole_review(self):
        self.assertEqual(json.loads(prepare(self.plan)['selection-report.json'])['status'],'PREPARED_ONLY')
        self.rejected(lambda p:p['takes'][1].pop('reviewedProtectedSpans'))
    def test_protected_span_raw_text_mismatch_rejected(self):
        p=copy.deepcopy(self.plan);t=p['takes'][1];self.protect(t,[t['words']]);t['reviewedProtectedSpans'][0]['text']='Nga nói sai.'
        with self.assertRaisesRegex(ValueError,'changes raw'):prepare(p)
    def test_protected_span_noncontiguous_or_reordered_rejected(self):
        for ids in (['w1','w3'],['w2','w1']):
            p=copy.deepcopy(self.plan);t=p['takes'][1];self.protect(t,[t['words']]);t['reviewedProtectedSpans'][0]['wordIds']=ids
            with self.assertRaisesRegex(ValueError,'contiguous and ordered'):prepare(p)
    def test_protected_span_unknown_word_or_duplicate_id_rejected(self):
        p=copy.deepcopy(self.plan);t=p['takes'][1];self.protect(t,[t['words']]);t['reviewedProtectedSpans'][0]['wordIds']=['unknown']
        with self.assertRaisesRegex(ValueError,'raw word IDs'):prepare(p)
        self.protect(t,[t['words']]);t['reviewedProtectedSpans'].append(copy.deepcopy(t['reviewedProtectedSpans'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate/missing'):prepare(p)
    def test_protected_span_review_kind_and_evidence_required(self):
        for change in ({'reviewed':False},{'kind':'automatic-NLP'},{'evidenceRef':''}):
            p=copy.deepcopy(self.plan);t=p['takes'][1];self.protect(t,[t['words']]);t['reviewedProtectedSpans'][0].update(change)
            with self.assertRaisesRegex(ValueError,'typed semantic review'):prepare(p)
    def test_protected_span_cross_sentence_rejected(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Có? Không biết.')
        t=p['takes'][1];w=t['words'];self.define_sentences(t,[w[:1],w[1:]]);self.define_cues(t,[('s1',w[:1]),('s2',w[1:])]);self.protect(t,[w])
        with self.assertRaisesRegex(ValueError,'one reviewed logical sentence'):prepare(p)
    def test_protected_exact_six_passes_whole(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Một cụm sáu từ được giữ.')
        t=p['takes'][1];self.protect(t,[t['words']]);self.assertIn('một cụm sáu từ được giữ',prepare(p)['captions.srt'])
    def test_protected_over_six_explicit_conflict(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Một cụm bảy từ phải được giữ.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w]);self.define_cues(t,[('s1',w[:4]),('s1',w[4:])])
        with self.assertRaisesRegex(ValueError,'semantic-unit conflict'):prepare(p)
    def test_compatible_nested_and_overlap_union_pass(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Một cụm sáu từ được giữ.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[:4],w[2:],w[2:4]])
        self.assertEqual(len(json.loads(prepare(p)['selection-report.json'])['captionCues'][0]['protectedSpanIds']),3)
    def test_overlap_union_over_six_rejected(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Một cụm bảy từ phải được giữ.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[:5],w[3:]]);self.define_cues(t,[('s1',w[:4]),('s1',w[4:])])
        with self.assertRaisesRegex(ValueError,'overlapping union exceeds'):prepare(p)
    def test_protected_name_and_english_term_with_comma(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Tại Palm City, sale vẫn biết.')
        p['verifiedNames'].append({'text':'Palm City','reviewed':True,'evidenceRef':'synthetic-name-review'})
        t=p['takes'][1];w=t['words'];self.protect(t,[w[1:3]],'proper-name');self.define_cues(t,[('s1',w[:2]),('s1',w[2:])])
        with self.assertRaisesRegex(ValueError,'splits a reviewed protected'):prepare(p)
        self.define_cues(t,[('s1',w)]);self.assertIn('tại Palm City, sale vẫn biết',prepare(p)['captions.srt'])
        self.protect(t,[w[1:3]],'term');self.assertIn('Palm City',prepare(p)['captions.srt'])
    def test_protected_numeric_conversion_preserves_raw_span_and_unit(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Có 1.500 m2 tại đây.')
        p['numericConversions']=[{'takeId':'last-good','wordId':'w1','sourceText':'1.500','displayText':'1500','reviewed':True,'evidenceRef':'synthetic-number-review'}]
        t=p['takes'][1];w=t['words'];self.protect(t,[w[1:3]],'number-unit');self.define_cues(t,[('s1',w[:2]),('s1',w[2:])])
        with self.assertRaisesRegex(ValueError,'splits a reviewed protected'):prepare(p)
        self.define_cues(t,[('s1',w)]);self.assertIn('có 1500 m2 tại đây',prepare(p)['captions.srt'])
    def test_numeric_expansion_over_six_protected_conflict(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Có 1.5 triệu đồng một tháng.')
        p['numericConversions']=[{'takeId':'last-good','wordId':'w1','sourceText':'1.5','displayText':'một phẩy năm','reviewed':True,'evidenceRef':'synthetic-long-number-review'}]
        t=p['takes'][1];self.protect(t,[t['words'][1:]],'number-unit')
        with self.assertRaisesRegex(ValueError,'semantic-unit conflict'):prepare(p)
    def test_protected_edges_allow_short_neighbor_cues_and_preserve_clock(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Này công thức bỏ túi đây.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[1:5]]);self.define_cues(t,[('s1',w[:1]),('s1',w[1:5]),('s1',w[5:])])
        out=prepare(p);cues=json.loads(out['selection-report.json'])['captionCues']
        self.assertEqual([c['text'] for c in cues[:3]],['này','công thức bỏ túi','đây'])
        self.assertEqual(cues[0]['start'],.1);self.assertEqual(cues[0]['end'],cues[1]['start']);self.assertEqual(cues[1]['end'],cues[2]['start'])
        self.assertEqual(json.loads(out['compile-spec.json'])['tracks'][0]['items'][0]['sourceStart'],20)
    def test_override_cannot_disable_protected_guard(self):
        self.rejected(lambda p:p.update(captionPolicyOverride={'authority':'explicit-user-request','evidenceRef':'synthetic-request','requireProtectedSpans':False}))
    def test_comparison_adjective_phrase_whole_not_forced_packing(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Vị trí quan trọng bằng giá trị.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[2:5]],'adjective-phrase')
        self.define_cues(t,[('s1',w[:4]),('s1',w[4:])])
        with self.assertRaisesRegex(ValueError,'splits a reviewed protected'):prepare(p)
        self.define_cues(t,[('s1',w[:2]),('s1',w[2:5]),('s1',w[5:])])
        cues=json.loads(prepare(p)['selection-report.json'])['captionCues']
        self.assertEqual([r['text'] for r in cues[:3]],['vị trí','quan trọng bằng','giá trị'])
    def test_verb_phrase_whole_and_exact_six_words(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Giúp tăng giá trị sử dụng.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w],'verb-phrase')
        self.define_cues(t,[('s1',w[:3]),('s1',w[3:])])
        with self.assertRaisesRegex(ValueError,'splits a reviewed protected'):prepare(p)
        self.define_cues(t,[('s1',w)]);self.assertIn('giúp tăng giá trị sử dụng',prepare(p)['captions.srt'])
    def test_short_number_unit_leftover_keeps_own_cue(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Hai miếng đất cách nhau 10 km.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[5:]],'number-unit');self.define_cues(t,[('s1',w[:5]),('s1',w[5:])])
        cues=json.loads(prepare(p)['selection-report.json'])['captionCues']
        self.assertEqual([r['text'] for r in cues[:2]],['hai miếng đất cách nhau','10 km'])
        self.assertEqual(cues[0]['end'],cues[1]['start'])
    def test_short_noun_leftover_keeps_own_cue(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Yếu tố tiếp theo khoảng cách.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[4:]],'noun-phrase');self.define_cues(t,[('s1',w[:4]),('s1',w[4:])])
        self.assertEqual([r['text'] for r in json.loads(prepare(p)['selection-report.json'])['captionCues'][:2]],['yếu tố tiếp theo','khoảng cách'])
    def test_overlimit_verb_phrase_remains_explicit_conflict(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Giúp tăng toàn bộ giá trị sử dụng.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w],'verb-phrase');self.define_cues(t,[('s1',w[:4]),('s1',w[4:])])
        with self.assertRaisesRegex(ValueError,'semantic-unit conflict'):prepare(p)
    def test_user_modal_copula_and_full_reporting_phrase_preserved(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Nga nghĩ sẽ là một công thức bỏ túi.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[:4],w[2:4]],'verb-phrase');self.define_cues(t,[('s1',w[:3]),('s1',w[3:])])
        with self.assertRaisesRegex(ValueError,'splits a reviewed protected'):prepare(p)
        self.define_cues(t,[('s1',w[:4]),('s1',w[4:])]);c=json.loads(prepare(p)['selection-report.json'])['captionCues']
        self.assertEqual([x['text'] for x in c[:2]],['Nga nghĩ sẽ là','một công thức bỏ túi']);self.assertEqual(c[0]['end'],c[1]['start'])
    def test_context_reviewed_modal_verb_unit_not_bare_stopword_ban(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Nga có thể chọn vị trí.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[1:4]],'verb-phrase');self.define_cues(t,[('s1',w[:2]),('s1',w[2:])])
        with self.assertRaisesRegex(ValueError,'splits a reviewed protected'):prepare(p)
        self.define_cues(t,[('s1',w[:4]),('s1',w[4:])]);self.assertEqual([x['text'] for x in json.loads(prepare(p)['selection-report.json'])['captionCues'][:2]],['Nga có thể chọn','vị trí'])
    def test_context_negation_modal_stem_and_recipient_units(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Nga không thể giúp chủ sở hữu.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[1:4]],'verb-phrase');first=t['reviewedProtectedSpans'];self.protect(t,[w[4:]],'noun-phrase');t['reviewedProtectedSpans'][0]['id']='recipient';t['reviewedProtectedSpans']=first+t['reviewedProtectedSpans']
        self.define_cues(t,[('s1',w[:3]),('s1',w[3:])])
        with self.assertRaisesRegex(ValueError,'splits a reviewed protected'):prepare(p)
        self.define_cues(t,[('s1',w[:4]),('s1',w[4:])]);self.assertEqual([x['text'] for x in json.loads(prepare(p)['selection-report.json'])['captionCues'][:2]],['Nga không thể giúp','chủ sở hữu'])
    def test_degree_comparative_collocation_keeps_negation(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Nhỏ hơn mà không kém quan trọng.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[:2],w[3:]],'adjective-phrase');self.define_cues(t,[('s1',w[:5]),('s1',w[5:])])
        with self.assertRaisesRegex(ValueError,'splits a reviewed protected'):prepare(p)
        self.define_cues(t,[('s1',w[:3]),('s1',w[3:])]);self.assertEqual([x['text'] for x in json.loads(prepare(p)['selection-report.json'])['captionCues'][:2]],['nhỏ hơn mà','không kém quan trọng'])
    def test_context_preposition_beneficiary_not_established_english_term_claim(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Dành cho những bạn sale tại đây.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[:5]],'verb-phrase');self.define_cues(t,[('s1',w[:2]),('s1',w[2:])])
        with self.assertRaisesRegex(ValueError,'splits a reviewed protected'):prepare(p)
        self.define_cues(t,[('s1',w[:5]),('s1',w[5:])]);self.assertEqual([x['text'] for x in json.loads(prepare(p)['selection-report.json'])['captionCues'][:2]],['dành cho những bạn sale','tại đây'])
    def test_regroup_rechecks_retained_user_lock_and_new_noun_lock(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Nga nghĩ sẽ là một công thức bỏ túi.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[:4]],'verb-phrase');old=copy.deepcopy(t['reviewedProtectedSpans']);self.protect(t,[w[4:]],'noun-phrase');t['reviewedProtectedSpans'][0]['id']='new-noun';t['reviewedProtectedSpans']=old+t['reviewedProtectedSpans'];locks=copy.deepcopy(t['reviewedProtectedSpans'])
        self.define_cues(t,[('s1',w[:4]),('s1',w[4:])]);prepare(p)
        self.define_cues(t,[('s1',w[:3]),('s1',w[3:])])
        with self.assertRaisesRegex(ValueError,'splits a reviewed protected'):prepare(p)
        self.assertEqual(t['reviewedProtectedSpans'],locks);self.define_cues(t,[('s1',w[:4]),('s1',w[4:])]);prepare(p)
    def test_reviewed_coordination_hinge_is_soft_composition_not_atomic_nine(self):
        p=copy.deepcopy(self.plan);self.set_text(p,'Quy hoạch và tốc độ phát triển khu vực.')
        t=p['takes'][1];w=t['words'];self.protect(t,[w[:2],w[3:]],'noun-phrase');self.define_cues(t,[('s1',w[:3]),('s1',w[3:])])
        self.assertEqual([x['text'] for x in json.loads(prepare(p)['selection-report.json'])['captionCues'][:2]],['quy hoạch và','tốc độ phát triển khu vực'])
        self.protect(t,[w],'noun-phrase')
        with self.assertRaisesRegex(ValueError,'semantic-unit conflict'):prepare(p)

    def enumeration_plan(self):
        p=copy.deepcopy(self.plan)
        chunks=['Thứ nhất là về Khả năng kết nối.','Thứ hai là về Những tiện ích ngoại khu.','Thứ ba là về Chất lượng khu vực.','Cuối cùng là về Nhu cầu thực tế.']
        self.set_text(p,' '.join(chunks));t=p['takes'][1];t['out']=50;w=t['words'];cursor=0;groups=[];items=[];contents=[]
        for i,chunk in enumerate(chunks,1):
            span=w[cursor:cursor+len(chunk.split())];lead=span[:4];content=span[len(lead):]
            groups.append(span);contents.append(content)
            items.append({'id':f'item{i}','ordinal':i,'takeId':t['id'],'sentenceId':f's{i}','leadInWordIds':[x['id'] for x in lead],'markerWordIds':[x['id'] for x in lead[:-1]],'leadInText':' '.join(x['text'] for x in lead),'firstContentWordId':content[0]['id'],'markerMeaning':'final-item' if i==4 else 'ordinal','leadInOnly':True,'reviewed':True,'evidenceRef':'synthetic-explicit-reviewed-list-item'})
            cursor+=len(span)
        self.define_sentences(t,groups);self.define_cues(t,[(f's{i}',span) for i,span in enumerate(groups,1)])
        self.protect(t,contents)
        for i,s in enumerate(t['reviewedProtectedSpans'],1):s['sentenceId']=f's{i}'
        p['enumerationDisplayAuthorization']={'authority':'explicit-user-request','evidenceRef':'synthetic-user-numbered-display','scope':'reviewed-ordinal-lead-in-to-numbered-caption-prefix'}
        p['reviewedEnumerations']=[{'id':'list','reviewed':True,'basis':'reviewed-spoken-enumeration','complete':True,'evidenceRef':'synthetic-whole-list-review','items':items}]
        return p
    def enum_rejected(self,change,pattern):
        p=self.enumeration_plan();change(p)
        with self.assertRaisesRegex(ValueError,pattern):prepare(p)
    def test_reviewed_production_four_headings_all_sixteen_short_lead_ids_traced(self):
        p=self.enumeration_plan();before=copy.deepcopy(p);out=prepare(p);report=json.loads(out['selection-report.json']);c=report['captionCues'][:4]
        self.assertEqual([x['text'] for x in c],['1. Khả năng kết nối','2. Những tiện ích ngoại khu','3. Chất lượng khu vực','4. Nhu cầu thực tế'])
        transforms=[e for x in c for e in x['enumerationTransforms']]
        self.assertEqual([len(e['rawWordIds']) for e in transforms],[4,4,4,4]);self.assertEqual(sum(len(e['rawWordIds']) for e in transforms),16)
        self.assertEqual([i for x in c for i in x['wordIds']],[w['id'] for w in p['takes'][1]['words']]);self.assertEqual(p,before)
        self.assertEqual([len(x['text'].split()) for x in c],[5,6,5,5]);self.assertTrue(all(a['end']==b['start'] for a,b in zip(report['captionCues'],report['captionCues'][1:])))
        self.assertEqual(json.loads(out['compile-spec.json'])['tracks'][0]['items'][0]['sourceStart'],20)
    def test_numbered_prefix_needs_authorization_not_style_or_audio_file(self):
        self.enum_rejected(lambda p:p.pop('enumerationDisplayAuthorization'),'explicit user authorization')
        self.enum_rejected(lambda p:p['enumerationDisplayAuthorization'].update(authority='style-preset'),'explicit user authorization')
    def test_reviewed_list_complete_evidence_and_order_required(self):
        self.enum_rejected(lambda p:p['reviewedEnumerations'][0].update(complete=False),'Complete spoken enumeration')
        self.enum_rejected(lambda p:p['reviewedEnumerations'][0]['items'][1].update(ordinal=3),'ordered1..N')
    def test_marker_must_match_reviewed_ordinal_and_final_position(self):
        self.enum_rejected(lambda p:p['reviewedEnumerations'][0]['items'][0].update(markerMeaning='final-item'),'Final enumeration')
        self.enum_rejected(lambda p:p['reviewedEnumerations'][0]['items'][3].update(markerMeaning='ordinal'),'Spoken ordinal')
    def test_marker_ids_noncontiguous_and_lead_raw_mismatch_rejected(self):
        self.enum_rejected(lambda p:p['reviewedEnumerations'][0]['items'][0].update(markerWordIds=['w0','w2']),'marker must be contiguous')
        self.enum_rejected(lambda p:p['reviewedEnumerations'][0]['items'][0].update(leadInText='Thứ nhất về'),'changes raw words')
    def test_missing_item_review_and_duplicate_item_identity_rejected(self):
        self.enum_rejected(lambda p:p['reviewedEnumerations'][0]['items'][0].update(reviewed=False),'Reviewed enumeration items')
        self.enum_rejected(lambda p:p['reviewedEnumerations'][0]['items'][1].update(id='item1'),'Duplicate')
    def test_lead_in_cannot_swallow_content_or_negation(self):
        def consume(p):
            item=p['reviewedEnumerations'][0]['items'][0];w=p['takes'][1]['words'];item.update(leadInWordIds=[x['id'] for x in w[:5]],leadInText=' '.join(x['text'] for x in w[:5]),firstContentWordId=w[5]['id'])
        self.enum_rejected(consume,'contains content or unsupported|Long enumeration')
        def negate(p):
            t=p['takes'][1];t['words'][2]['text']='không';p['units'][0]['scriptText']=' '.join(x['text'] for x in t['words']);t['reviewedSentences'][0]['text']=t['phrases'][0]['text']=' '.join(x['text'] for x in t['words'][:8]);p['reviewedEnumerations'][0]['items'][0]['leadInText']='Thứ nhất không về'
        self.enum_rejected(negate,'Spoken ordinal|unsupported')
    def test_prefix_and_content_cannot_cross_sentence_or_cue_boundary(self):
        self.enum_rejected(lambda p:p['reviewedEnumerations'][0]['items'][0].update(sentenceId='s2'),'within one reviewed sentence')
        def split(p):
            t=p['takes'][1];first=t['phrases'][0];w=t['words'];new=copy.deepcopy(first);first.update(wordIds=[x['id'] for x in w[:4]],text=' '.join(x['text'] for x in w[:4]),end=w[3]['end']);new.update(id='first-content',wordIds=[x['id'] for x in w[4:8]],text=' '.join(x['text'] for x in w[4:8]),start=w[4]['start']);t['phrases'].insert(1,new)
        self.enum_rejected(split,'prefix from its first content')
    def test_unselected_take_enumeration_not_silently_omitted(self):
        p=self.enumeration_plan();p['reviewedEnumerations'][0]['items'][0]['takeId']='first'
        p['captionPolicyOverride']={'authority':'explicit-user-request','evidenceRef':'synthetic-isolate-unselected-item-guard','maxWordsPerCue':None}
        with self.assertRaisesRegex(ValueError,'refer only to selected takes'):prepare(p)
    def test_partial_protected_lead_in_conflict_not_erased(self):
        def protect(p):
            t=p['takes'][1];span=t['words'][1:3];t['reviewedProtectedSpans'].append({'id':'partial-lead','sentenceId':'s1','wordIds':[x['id'] for x in span],'text':' '.join(x['text'] for x in span),'kind':'term','reviewed':True,'evidenceRef':'synthetic-conflicting-semantic-review'})
        self.enum_rejected(protect,'partly overlaps')
    def test_period_exception_does_not_capitalize_each_ordinary_cue(self):
        p=self.enumeration_plan();report=json.loads(prepare(p)['selection-report.json'])
        self.assertEqual(report['captionCues'][-1]['text'],'Nga nói đúng');self.assertNotIn('.',report['captionCues'][-1]['text'])
        self.assertEqual(report['captionCues'][0]['text'],'1. Khả năng kết nối')

    def long_enumeration_plan(self,lead='vì vậy phải nhớ kỹ nguyên tắc an toàn thứ nhất',separate=False):
        p=copy.deepcopy(self.plan);self.set_text(p,lead+' Nội dung quan trọng.');t=p['takes'][1];t['out']=50;w=t['words'];n=len(lead.split());a,b=w[:n],w[n:]
        self.define_sentences(t,[a,b] if separate else [w]);self.define_cues(t,[('s1',a),('s2' if separate else 's1',b)]);self.protect(t,[])
        item={'id':'long1','ordinal':1,'takeId':t['id'],'sentenceId':'s1','leadInWordIds':[x['id'] for x in a],'markerWordIds':[x['id'] for x in a[-2:]],'leadInText':' '.join(x['text'] for x in a),'firstContentWordId':b[0]['id'],'markerMeaning':'ordinal','leadInOnly':True,'reviewed':True,'evidenceRef':'synthetic-list-review','preserveLongLeadIn':True,'preserveEvidenceRef':'synthetic-explicit-long-preservation'}
        if separate:item['firstContentSentenceId']='s2'
        p['enumerationDisplayAuthorization']={'authority':'explicit-user-request','evidenceRef':'synthetic-user-display-rule','scope':'reviewed-ordinal-lead-in-to-numbered-caption-prefix'}
        p['reviewedEnumerations']=[{'id':'list','reviewed':True,'basis':'reviewed-spoken-enumeration','complete':True,'evidenceRef':'synthetic-complete-list','items':[item]}]
        return p
    def test_long_lead_preserved_over_six_and_number_only_main_content(self):
        p=self.long_enumeration_plan();before=copy.deepcopy(p);r=json.loads(prepare(p)['selection-report.json']);c=r['captionCues']
        self.assertEqual(c[0]['text'],'vì vậy phải nhớ kỹ nguyên tắc an toàn thứ nhất');self.assertGreater(len(c[0]['text'].split()),6)
        self.assertEqual(c[1]['text'],'1. Nội dung quan trọng');self.assertEqual(c[0]['enumerationTransforms'],[])
        e=c[1]['enumerationTransforms'][0];self.assertEqual(e['operation'],'PRESERVE_LONG_LEAD_IN_AND_PREFIX_CONTENT');self.assertEqual(e['preservedLeadInWordIds'],c[0]['wordIds']);self.assertEqual(e['rawWordIds'],[c[1]['wordIds'][0]])
        self.assertEqual(p,before);self.assertEqual(r['visualSingleLine'],'PENDING')
    def test_five_raw_words_preserve_not_marker_count(self):
        p=self.long_enumeration_plan('nhớ nguyên tắc thứ nhất');r=json.loads(prepare(p)['selection-report.json'])
        self.assertEqual(r['captionCues'][0]['text'],'nhớ nguyên tắc thứ nhất');self.assertEqual(r['captionCues'][1]['text'],'1. Nội dung quan trọng')
    def test_four_raw_words_still_use_short_conversion(self):
        r=json.loads(prepare(self.enumeration_plan())['selection-report.json']);self.assertEqual(r['captionCues'][0]['text'],'1. Khả năng kết nối')
    def test_long_lead_needs_explicit_preservation_metadata(self):
        p=self.long_enumeration_plan();p['reviewedEnumerations'][0]['items'][0].pop('preserveEvidenceRef')
        with self.assertRaisesRegex(ValueError,'Long enumeration'):prepare(p)
    def test_long_intro_and_content_can_be_two_reviewed_sentences(self):
        r=json.loads(prepare(self.long_enumeration_plan(separate=True))['selection-report.json'])
        self.assertEqual(r['captionCues'][0]['sentenceId'],'s1');self.assertEqual(r['captionCues'][1]['sentenceId'],'s2')
    def test_long_intro_missing_content_sentence_binding_rejected(self):
        p=self.long_enumeration_plan(separate=True);p['reviewedEnumerations'][0]['items'][0].pop('firstContentSentenceId')
        with self.assertRaisesRegex(ValueError,'within one reviewed sentence'):prepare(p)
    def test_long_lead_must_not_be_split_or_merge_into_content(self):
        for split in (True,False):
            p=self.long_enumeration_plan();t=p['takes'][1];w=t['words'];n=len(p['reviewedEnumerations'][0]['items'][0]['leadInWordIds'])
            self.define_cues(t,[('s1',w[:5]),('s1',w[5:n]),('s1',w[n:])] if split else [('s1',w)])
            with self.assertRaisesRegex(ValueError,'Preserved long enumeration'):prepare(p)
    def test_main_prefix_uses_content_clock_not_old_ordinal(self):
        p=self.long_enumeration_plan();t=p['takes'][1];n=len(p['reviewedEnumerations'][0]['items'][0]['leadInWordIds']);c=json.loads(prepare(p)['selection-report.json'])['captionCues']
        self.assertEqual(c[1]['start'],round(t['words'][n]['start']-t['in'],6));self.assertEqual(c[0]['end'],c[1]['start'])
    def test_other_long_cues_still_rejected(self):
        p=self.long_enumeration_plan();t=p['takes'][-1];w=t['words']
        # The protected existing ceiling is still exercised by the original suite;
        # a manually broadened main-content cue cannot inherit the intro exception.
        item=p['reviewedEnumerations'][0]['items'][0];item['leadInWordIds']=item['leadInWordIds'][:-1]
        with self.assertRaises(ValueError):prepare(p)
    def test_screenshot_third_ordinal_keeps_long_intro(self):
        from prepare_cut import enumeration_display
        lead='vì vậy phải nhớ kỹ nguyên tắc an toàn thứ 3';tokens=(lead+' nếu phải').split()
        w=[{'id':str(i),'text':v} for i,v in enumerate(tokens)];n=len(lead.split())
        item={'id':'third','listId':'list','listItemCount':3,'ordinal':3,'sentenceId':'s1','leadInWordIds':[str(i) for i in range(n)],'markerWordIds':[str(n-2),str(n-1)],'leadInText':lead,'firstContentWordId':str(n),'markerMeaning':'ordinal','preserveLongLeadIn':True,'preserveEvidenceRef':'synthetic-user-image-example','evidenceRef':'synthetic-reviewed-item','listEvidenceRef':'synthetic-list'}
        display,changes=enumeration_display(w,tokens,[item],{x['id']:'s1' for x in w})
        self.assertEqual(' '.join(display[:n]),lead);self.assertEqual(' '.join(display[n:]),'3. Nếu phải');self.assertEqual(changes[0]['preservedLeadInWordIds'],[str(i) for i in range(n)])

    def test_long_threshold_counts_raw_whitespace_not_record_ids(self):
        from prepare_cut import enumeration_display
        text=['và','thứ nhất','là','về','nội','dung'];w=[{'id':str(i),'text':v} for i,v in enumerate(text)]
        item={'id':'compound','listId':'list','listItemCount':1,'ordinal':1,'sentenceId':'s1','leadInWordIds':['0','1','2','3'],'markerWordIds':['1'],'leadInText':'và thứ nhất là về','firstContentWordId':'4','markerMeaning':'ordinal','preserveLongLeadIn':True,'preserveEvidenceRef':'synthetic-exact-user-rule','evidenceRef':'synthetic-item','listEvidenceRef':'synthetic-list'}
        display,transforms=enumeration_display(w,text,[item],{x['id']:'s1' for x in w})
        self.assertEqual(' '.join(display[:4]),'và thứ nhất là về');self.assertEqual(' '.join(display[4:]),'1. Nội dung');self.assertEqual(transforms[0]['rawLeadInWordCount'],5)
    def test_early_long_content_phrase_start_inside_gap_is_rejected(self):
        p=self.long_enumeration_plan();t=p['takes'][1];item=p['reviewedEnumerations'][0]['items'][0];n=len(item['leadInWordIds'])
        for w in t['words'][n:]:w['start']+=1;w['end']+=1
        t['phrases'][1]['start']+=.75;t['phrases'][1]['end']+=1
        with self.assertRaisesRegex(ValueError,'must start at its first raw word'):prepare(p)
    def test_exact_long_content_phrase_start_after_gap_remains_valid(self):
        p=self.long_enumeration_plan();t=p['takes'][1];n=len(p['reviewedEnumerations'][0]['items'][0]['leadInWordIds'])
        for w in t['words'][n:]:w['start']+=1;w['end']+=1
        t['phrases'][1]['start']+=1;t['phrases'][1]['end']+=1
        c=json.loads(prepare(p)['selection-report.json'])['captionCues'];self.assertEqual(c[1]['start'],round(t['words'][n]['start']-t['in'],6));self.assertEqual(c[0]['end'],c[1]['start'])

class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.addCleanup(self.temp.cleanup);audio=Path(self.temp.name)/'audio.wav';audio.write_bytes(b'synthetic audio identity; no hearing proof')
        self.brief={'schemaVersion':'capcut-brief/v1','workScope':'SUB_ONLY','output':{'mode':'EDIT_TIMELINE','modeEvidence':'synthetic-known-timeline-request'},'requiresTranscription':True,'transcriptionRequirementEvidenceRef':'synthetic-asr-needed','appStatus':'READY','audioInput':{'status':'AVAILABLE','path':str(audio),'sha256':'sha256:'+hashlib.sha256(audio.read_bytes()).hexdigest(),'durationSeconds':12.81,'clockBasis':'EDITED_TIMELINE','exportRange':{'startSeconds':0,'endSeconds':12.81},'intendedExportRange':{'startSeconds':0,'endSeconds':12.81},'startOffsetSeconds':0,'timingEvidenceRef':'synthetic-export-clock-evidence','preservesPausesCutsAndSpeed':True,'currentTimelineIdentityRef':'synthetic-current-timeline'}}
        self.brief['projectIdentity']={'name':'Synthetic existing timeline','evidenceRef':'synthetic-task-target'}
        self.brief['recipient']={'kind':'PERSON','id':'other-person','label':'Other person','reviewed':True,'evidenceRef':'synthetic-known-recipient-baseline'}
    def report(self):return json.loads(prepare_intake(self.brief)['caption-intake-report.json'])
    def test_known_timeline_target_and_edited_audio_reused_no_extra_question(self):
        before=copy.deepcopy(self.brief);r=self.report();self.assertTrue(r['readyForAuthorizedPreparation']);self.assertIsNone(r['nextQuestion']);self.assertEqual(self.brief,before);self.assertEqual(r['audioTruth'],'PENDING')
    def test_missing_mode_not_inferred_from_receiving_audio(self):
        self.brief['output']['mode']=None;r=self.report();self.assertEqual(r['inputDependencies'],['OUTPUT_MODE']);self.assertIsNotNone(r['nextQuestion'])
    def test_missing_audio_requests_source_without_native_downgrade(self):
        self.brief['audioInput']['status']='PENDING';r=self.report();self.assertIn('AUDIO_SOURCE',r['inputDependencies']);self.assertEqual(r['outputMode'],'EDIT_TIMELINE')
    def test_app_failure_preserves_timeline_and_pending_file_acceptance(self):
        self.brief['appStatus']='BLOCKED';r=self.report();self.assertEqual(r['outputMode'],'EDIT_TIMELINE');self.assertEqual(r['nativeAcceptance'],'BLOCKED');self.assertEqual(r['fileAcceptance'],'PENDING')
    def test_explicit_srt_only_audio_file_clock_no_native_claim_or_script_requirement(self):
        self.brief['output'].update(mode='SRT_ONLY',modeEvidence='synthetic-explicit-file-request');self.brief['audioInput']['clockBasis']='AUDIO_FILE';r=self.report();self.assertTrue(r['readyForAuthorizedPreparation']);self.assertEqual(r['nativeAcceptance'],'NOT_APPLICABLE');self.assertEqual(r['fileAcceptance'],'PENDING')
    def test_original_source_for_timeline_needs_reviewed_cut_map(self):
        a=self.brief['audioInput'];a['clockBasis']='ORIGINAL_SOURCE';r=self.report();self.assertIn('REVIEWED_SOURCE_TO_TIMELINE_MAP',r['inputDependencies'])
        a['reviewedEditMap']={'reviewed':True,'evidenceRef':'synthetic-reviewed-edit-map','sourceSha256':a['sha256'],'targetTimelineIdentityRef':'synthetic-current-timeline'};self.assertTrue(self.report()['readyForAuthorizedPreparation'])
    def test_duration_filename_not_clock_proof(self):
        self.brief['audioInput']['timingEvidenceRef']=None;self.assertIn('AUDIO_CLOCK',self.report()['inputDependencies'])
    def test_partial_export_and_changed_pause_cut_speed_rejected(self):
        self.brief['audioInput']['exportRange']['endSeconds']=10
        with self.assertRaisesRegex(ValueError,'whole reviewed intended'):self.report()
        self.brief['audioInput']['exportRange']['endSeconds']=12.81;self.brief['audioInput']['preservesPausesCutsAndSpeed']=False
        with self.assertRaisesRegex(ValueError,'whole interval'):self.report()
    def test_verified_nonzero_export_offset_preserved(self):
        a=self.brief['audioInput'];a['exportRange']=a['intendedExportRange']={'startSeconds':5,'endSeconds':17.81};a['startOffsetSeconds']=5;self.assertTrue(self.report()['readyForAuthorizedPreparation'])
        a['startOffsetSeconds']=0
        with self.assertRaisesRegex(ValueError,'start offset disagree'):self.report()
    def test_audio_identity_drift_rejected(self):
        self.brief['audioInput']['sha256']='sha256:'+'0'*64
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.report()
    def test_available_aligned_transcript_does_not_require_another_export(self):
        self.brief.update(requiresTranscription=False,transcriptionRequirementEvidenceRef='synthetic-aligned-transcript-audio-source');self.brief.pop('audioInput');self.assertTrue(self.report()['readyForAuthorizedPreparation'])


class PacingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.addCleanup(self.temp.cleanup);self.source=Path(self.temp.name)/'source.mp4';self.source.write_bytes(b'synthetic source identity; no actual audio/video proof')
        self.plan=self.fixture()
    def fixture(self,num=30,den=1,bounds=((0,12),(21,33),(60,72),(78,90))):
        def us(f):return f*1000000*den//num
        words=[{'id':i,'text':text,'role':'main','reviewed':True,'evidenceRef':'synthetic-word-boundary-review','sourcePieces':[{'clipId':'base','sourceStartTick':us(a),'sourceEndTick':us(b)}]} for (i,text),(a,b) in zip([('a','Nga'),('b','nói'),('c','giá'),('d','trị')],bounds)]
        ids=[w['id'] for w in words]
        sentences=[{'id':'s1','wordIds':ids[:2],'text':'Nga nói','reviewed':True,'boundaryBasis':'reviewed-logical-sentence','evidenceRef':'synthetic-sentence-review'},{'id':'s2','wordIds':ids[2:],'text':'giá trị','reviewed':True,'boundaryBasis':'reviewed-logical-sentence','evidenceRef':'synthetic-sentence-review'}]
        p={'schemaVersion':'capcut-pacing-plan/v1','workScope':'CONTENT_EDIT','outputMode':'EDIT_TIMELINE','authorization':{'authority':'explicit-user-request','evidenceRef':'synthetic-user-frame15-5-request'},'nativeClock':{'tickRate':1000000,'clockBasis':'ACTUAL_TIMELINE','fpsNumerator':num,'fpsDenominator':den,'reviewed':True,'evidenceRef':'synthetic-timeline-fps-readback'},'sources':[{'id':'s','path':str(self.source),'sha256':'sha256:'+hashlib.sha256(self.source.read_bytes()).hexdigest(),'actualDurationTicks':10000000,'durationEvidenceRef':'synthetic-duration-probe'}],'clips':[{'id':'base','sourceId':'s','sourceInTick':0,'sourceOutTick':us(120),'startFrame':0,'endFrame':120,'speed':1,'volume':3}],'words':words,'reviewedSentences':sentences,'captionCues':[{'id':'c1','sentenceId':'s1','wordIds':ids[:2],'text':'Nga nói','reviewedDisplayByWord':['Nga','nói'],'reviewed':True,'evidenceRef':'synthetic-reviewed-caption'},{'id':'c2','sentenceId':'s2','wordIds':ids[2:],'text':'giá trị','reviewedDisplayByWord':['giá','trị'],'reviewed':True,'evidenceRef':'synthetic-reviewed-caption'}],'reviewedProtectedSpans':[{'id':'one','sentenceId':'s1','wordIds':ids[:2],'text':'Nga nói','kind':'verb-phrase','reviewed':True,'evidenceRef':'synthetic-protected-review'},{'id':'two','sentenceId':'s2','wordIds':ids[2:],'text':'giá trị','kind':'noun-phrase','reviewed':True,'evidenceRef':'synthetic-protected-review'}],'protectedSpanReview':{'reviewed':True,'basis':'whole-transcript-semantic-review','wordIds':ids,'evidenceRef':'synthetic-whole-review'},'knownSpeechOrPrompterIntervals':[],'reviewedPauses':[],'reviewedCaptionOuterBounds':{'firstOnsetFrame':0,'lastEndFrame':bounds[-1][1],'reviewed':True,'evidenceRef':'synthetic-reviewed-existing-caption-outer'}}
        for n,(left,right) in enumerate(zip(words,words[1:])):
            a,b=bounds[n][1],bounds[n+1][0];row={'previousWordId':left['id'],'nextWordId':right['id'],'kind':'sentence-boundary' if n==1 else 'intra-sentence-breath','oldStartFrame':a,'oldEndFrame':b,'oldStartTick':us(a),'oldEndTick':us(b),'reviewed':True,'reviewBasis':'audio-speech-boundary-review','noSpeechOrPrompter':True,'joinEvidenceRef':'synthetic-source-join-review','evidenceRef':'synthetic-quiet-review'}
            if n==1:row['previousSourceQuietTail']={'sourceId':'s','startTick':us(a),'availableEndTick':5000000,'reviewed':True,'evidenceRef':'synthetic-prior-source-quiet-review'}
            p['reviewedPauses'].append(row)
        self.select_scope(p,'SENTENCE_AND_INTRA')
        return p
    def select_scope(self,p,scope):
        p.update(pacingScope=scope,pacingScopeOverride={'pacingScope':scope,'authority':'explicit-user-request','evidenceRef':'synthetic-explicit-legacy-selection'})
    def all_plan(self):
        p=copy.deepcopy(self.plan);p.pop('pacingScope');p.pop('pacingScopeOverride')
        # Isolate internal-pause tests: final synthetic word reaches the native end, so no unreviewed outer quiet is hidden.
        p['words'][-1]['sourcePieces'][-1]['sourceEndTick']=p['clips'][-1]['sourceOutTick']
        p['reviewedCaptionOuterBounds']['lastEndFrame']=p['clips'][-1]['endFrame']
        for row in p['reviewedPauses']:
            a,b=row['oldStartFrame']+1,row['oldEndFrame']-1
            us=lambda f:f*1000000*p['nativeClock']['fpsDenominator']//p['nativeClock']['fpsNumerator']
            row['safeRemoval']={'startFrame':a,'endFrame':b,'startTick':us(a),'endTick':us(b),'leftPhoneticHandleTicks':us(a)-row['oldStartTick'],'rightPhoneticHandleTicks':row['oldEndTick']-us(b),'reviewed':True,'reviewBasis':'audio-speech-boundary-review','evidenceRef':'synthetic-safe-quiet-phonetic-review'}
        return p
    def report(self,p=None):return json.loads(prepare_pacing(p or self.plan)['pacing-report.json'])
    def bind_nga(self,p):
        p.update(recipient={'kind':'PERSON','id':'mrs-nga','label':'Mrs Nga','reviewed':True,'evidenceRef':'synthetic-person-binding'},contentDomain={'id':'real-estate','reviewed':True,'evidenceRef':'synthetic-domain-binding'},style={'selectedId':'nga'})
    def test_wrapper_preserves_nga_context_and_does_not_mutate_input(self):
        wrapper={'pacingPlan':self.all_plan()};self.bind_nga(wrapper);before=copy.deepcopy(wrapper);r=self.report(pacing_input(wrapper))
        self.assertEqual(r['pacingScope'],'ALL_PAUSES');self.assertEqual(r['intraSentenceEditCount'],1);self.assertEqual(wrapper,before)
    def test_matching_duplicated_context_is_accepted(self):
        p=self.all_plan();self.bind_nga(p);wrapper={'pacingPlan':p,**{k:copy.deepcopy(p[k]) for k in ('recipient','contentDomain','style')}}
        self.assertEqual(self.report(pacing_input(wrapper))['pacingScope'],'ALL_PAUSES')
    def test_each_conflicting_outer_child_context_is_rejected(self):
        for field in ('recipient','contentDomain','style','pacingScope','pacingScopeOverride','reviewedFinalCaptionOnsets'):
            with self.subTest(field=field):
                p=copy.deepcopy(self.plan);p[field]='child';wrapper={'pacingPlan':p,field:'outer'}
                with self.assertRaisesRegex(ValueError,'Conflicting outer/child'):pacing_input(wrapper)
    def test_wrapper_duplicate_json_types_are_not_coerced(self):
        for inner,outer in ((True,1),(1,True),(1,1.0),(False,0),([True],[1])):
            with self.subTest(inner=inner,outer=outer):
                wrapper={'pacingPlan':{'recipient':{'reviewed':inner}},'recipient':{'reviewed':outer}}
                with self.assertRaisesRegex(ValueError,'Conflicting outer/child'):pacing_input(wrapper)
        wrapper={'pacingPlan':{'recipient':{'reviewed':True,'id':'mrs-nga'}},'recipient':{'id':'mrs-nga','reviewed':True}}
        self.assertEqual(pacing_input(wrapper)['recipient'],wrapper['recipient'])
    def test_wrapper_general_authority_cannot_replace_pacing_authority(self):
        p=copy.deepcopy(self.plan);p.pop('authorization');wrapper={'pacingPlan':p,'authorization':self.plan['authorization']}
        with self.assertRaisesRegex(ValueError,'Explicit pacing authority'):prepare_pacing(pacing_input(wrapper))
    def test_wrapper_nondefault_override_evidence_is_preserved(self):
        wrapper={'pacingPlan':copy.deepcopy(self.plan),'pacingScope':'SENTENCE_AND_INTRA','pacingScopeOverride':{'pacingScope':'SENTENCE_AND_INTRA','authority':'explicit-user-request','evidenceRef':'synthetic-wrapper-specific-override'}};self.bind_nga(wrapper)
        wrapper['pacingPlan'].pop('pacingScopeOverride')
        r=self.report(pacing_input(wrapper));self.assertEqual(r['intraSentenceEditCount'],2);self.assertEqual(r['pacingScopeOverride'],wrapper['pacingScopeOverride'])
    def test_wrapper_nondefault_does_not_borrow_generic_authority(self):
        wrapper={'pacingPlan':copy.deepcopy(self.plan),'pacingScope':'SENTENCE_AND_INTRA'};self.bind_nga(wrapper)
        wrapper['pacingPlan'].pop('pacingScopeOverride')
        with self.assertRaisesRegex(ValueError,'nondefault pacingScope'):prepare_pacing(pacing_input(wrapper))
    def test_wrapper_final_onset_tuple_is_never_discarded(self):
        for value in ([],None,[{'id':'c1','startTick':0}]):
            wrapper={'pacingPlan':copy.deepcopy(self.plan),'reviewedFinalCaptionOnsets':value}
            with self.assertRaisesRegex(ValueError,'cannot overwrite'):prepare_pacing(pacing_input(wrapper))
    def test_wrapper_preserves_explicit_different_style(self):
        wrapper={'pacingPlan':copy.deepcopy(self.plan)};self.bind_nga(wrapper);wrapper['style']['selectedId']='another-style'
        self.assertEqual(self.report(pacing_input(wrapper))['pacingScope'],'SENTENCE_AND_INTRA')
    def test_wrapper_missing_recipient_or_domain_still_holds(self):
        wrapper={'pacingPlan':copy.deepcopy(self.plan),'style':{'selectedId':'nga'}}
        with self.assertRaisesRegex(ValueError,'GATE0_STYLE_BINDING_REQUIRED'):prepare_pacing(pacing_input(wrapper))
    def test_standalone_and_child_only_inputs_keep_existing_behavior(self):
        self.assertEqual(pacing_input(self.plan),self.plan);p=copy.deepcopy(self.plan);self.bind_nga(p);self.select_scope(p,'INTER_SENTENCE_ONLY')
        self.assertEqual(self.report(pacing_input({'pacingPlan':p}))['pacingScope'],'INTER_SENTENCE_ONLY')
    def test_malformed_wrapper_or_unknown_scope_rejected(self):
        for value in (None,[],True):
            with self.assertRaisesRegex(ValueError,'requires an object'):pacing_input({'pacingPlan':value})
        wrapper={'pacingPlan':copy.deepcopy(self.plan),'pacingScope':'UNSUPPORTED_PAUSE_MODE'}
        wrapper['pacingPlan'].pop('pacingScope')
        with self.assertRaisesRegex(ValueError,'Known pacingScope'):prepare_pacing(pacing_input(wrapper))
    def test_actual_cli_wrapper_dispatch_honors_confirmed_nga(self):
        import subprocess,sys
        wrapper={'pacingPlan':self.all_plan()};self.bind_nga(wrapper);root=Path(self.temp.name);plan=root/'wrapper.json';plan.write_text(json.dumps(wrapper),encoding='utf-8');out=root/'output'
        run=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('prepare_cut.py')),'--mode','pacing','--plan',str(plan),'--out-dir',str(out)],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr);r=json.loads((out/'pacing-report.json').read_text('utf-8'));self.assertEqual(r['pacingScope'],'ALL_PAUSES');self.assertEqual(r['intraSentenceEditCount'],1)
    def test_inter_sentence_only_preserves_both_intra_gaps_and_source_words(self):
        p=copy.deepcopy(self.plan);self.select_scope(p,'INTER_SENTENCE_ONLY');before=copy.deepcopy(p);r=self.report(p)
        self.assertEqual([q['afterFrames'] for q in r['pauses']],[9,15,6]);self.assertEqual(r['afterDurationFrames'],108);self.assertEqual(r['intraSentenceEditCount'],0)
        self.assertEqual(r['intraSentenceBreathCapFrames'],None);self.assertEqual(r['intraAuditoryGapMaximumTicks'],None);self.assertTrue(r['intraSentencePausesPreserved'])
        self.assertEqual([q['kind'] for q in r['quietEdits']],['sentence-boundary']);self.assertEqual(p,before)
        for old,new in zip(p['words'],r['words']):self.assertEqual(new['sourcePieces'][0]['sourceStartTick'],old['sourcePieces'][0]['sourceStartTick']);self.assertEqual(new['sourcePieces'][0]['sourceEndTick'],old['sourcePieces'][0]['sourceEndTick'])
    def test_preserved_intra_needs_no_cut_review_but_sentence_still_does(self):
        p=copy.deepcopy(self.plan);self.select_scope(p,'INTER_SENTENCE_ONLY');p['reviewedPauses']=[p['reviewedPauses'][1]]
        self.assertEqual(self.report(p)['status'],'PREPARED_ONLY');p['reviewedPauses']=[]
        with self.assertRaisesRegex(ValueError,'reviewed source quiet'):prepare_pacing(p)
    def test_applicable_nga_defaults_all_pauses_without_scope_field(self):
        p=self.all_plan();self.bind_nga(p);r=self.report(p)
        self.assertEqual(r['pacingScope'],'ALL_PAUSES');self.assertEqual([q['afterFrames'] for q in r['pauses']],[2,2,6]);self.assertTrue(r['pacingStyleBinding']['applies'])
    def test_explicit_generic_legacy_keeps_existing_five_frame_behavior(self):
        r=self.report();self.assertEqual(r['pacingScope'],'SENTENCE_AND_INTRA');self.assertEqual(r['intraSentenceEditCount'],2);self.assertEqual(r['intraSentenceBreathCapFrames'],5)
    def test_other_recipient_or_style_keeps_explicit_generic_legacy(self):
        for change in ('recipient','style','domain'):
            p=copy.deepcopy(self.plan);self.bind_nga(p)
            if change=='recipient':p['recipient']['id']='other-person'
            elif change=='style':p['style']['selectedId']='another-style'
            else:p['contentDomain']['id']='another-domain'
            r=self.report(p);self.assertEqual(r['pacingScope'],'SENTENCE_AND_INTRA');self.assertFalse(r['pacingStyleBinding']['applies'])
    def test_nga_nondefault_needs_more_than_generic_content_authority(self):
        p=copy.deepcopy(self.plan);self.bind_nga(p);p['pacingScope']='SENTENCE_AND_INTRA';p.pop('pacingScopeOverride')
        with self.assertRaisesRegex(ValueError,'nondefault pacingScope'):prepare_pacing(p)
    def test_nga_explicit_scoped_override_retains_legacy_behavior(self):
        p=copy.deepcopy(self.plan);self.bind_nga(p);p.update(pacingScope='SENTENCE_AND_INTRA',pacingScopeOverride={'pacingScope':'SENTENCE_AND_INTRA','authority':'explicit-user-request','evidenceRef':'synthetic-scoped-nga-override'})
        r=self.report(p);self.assertEqual([q['afterFrames'] for q in r['pauses']],[5,15,5]);self.assertEqual(r['pacingScopeOverride'],p['pacingScopeOverride'])
    def test_unknown_scope_does_not_mean_zero_pause_trial(self):
        for scope in ('ALL_PAUSES_UNSAFE','ZERO_PAUSE','',None,5):
            self.rejected(lambda p:p.update(pacingScope=scope),'Known pacingScope')
    def test_override_must_be_explicit_scoped_nonempty_and_matching(self):
        for override in ({'pacingScope':'INTER_SENTENCE_ONLY','authority':'explicit-user-request','evidenceRef':'synthetic'}, {'pacingScope':'SENTENCE_AND_INTRA','authority':'model-choice','evidenceRef':'synthetic'}, {'pacingScope':'SENTENCE_AND_INTRA','authority':'explicit-user-request','evidenceRef':' '}, 'yes'):
            self.rejected(lambda p:p.update(pacingScope='SENTENCE_AND_INTRA',pacingScopeOverride=override),'Scoped explicit pacingScopeOverride')
    def test_selected_nga_requires_recipient_and_confirmed_domain(self):
        self.rejected(lambda p:p.update(style={'selectedId':'nga'}),'GATE0_STYLE_BINDING_REQUIRED')
        p=copy.deepcopy(self.plan);self.bind_nga(p);p.pop('contentDomain')
        with self.assertRaisesRegex(ValueError,'GATE0_STYLE_BINDING_REQUIRED'):prepare_pacing(p)
    def test_inter_scope_does_not_weaken_supplied_review_or_known_speech_checks(self):
        self.rejected(lambda p:(self.select_scope(p,'INTER_SENTENCE_ONLY'),p['reviewedPauses'][0].update(reviewed=False)),'Quiet-only')
        self.rejected(lambda p:(self.select_scope(p,'INTER_SENTENCE_ONLY'),p['knownSpeechOrPrompterIntervals'].append({'sourceId':'s','startTick':1500000,'endTick':1700000,'role':'prompter','reviewed':True,'evidenceRef':'synthetic-prompter'})),'intersects retained speech')
    def test_inter_scope_fps_and_fractional_word_ticks_remain_exact(self):
        p=self.fixture(30000,1001);self.select_scope(p,'INTER_SENTENCE_ONLY');r=self.report(p)
        self.assertEqual(r['afterDurationTicks'],108*1000000*1001//30000)
        self.assertEqual(r['pauses'][0]['afterAuditoryGapTicks'],r['pauses'][0]['beforeAuditoryGapTicks']);self.assertEqual(r['pauses'][2]['afterAuditoryGapTicks'],r['pauses'][2]['beforeAuditoryGapTicks'])
    def test_generated_caption_starts_are_provisional_and_end_fill_never_moves_them(self):
        r=self.report();self.assertEqual(r['captionOnsetStatus'],'FRAME_ESTIMATES_PENDING_FINAL_AUDIO_REVIEW');self.assertEqual(r['finalCaptionAnchorAcceptance'],'PENDING');self.assertTrue(r['captionStartsUnchangedByEndFill'])
        self.assertEqual(r['captionCues'][0]['endTick'],r['captionCues'][1]['startTick']);self.assertEqual(r['captionCues'][1]['startFrame'],r['words'][2]['startFrame']);self.assertEqual(r['nativeAudioAcceptance'],'PENDING')
    def test_existing_reviewed_final_onsets_cannot_be_silently_overwritten(self):
        self.rejected(lambda p:p.update(reviewedFinalCaptionOnsets=[{'id':'c1','startTick':0}]),'cannot overwrite')
    def rejected(self,change,pattern):
        p=copy.deepcopy(self.plan);change(p)
        with self.assertRaisesRegex(ValueError,pattern):prepare_pacing(p)
    def test_exact_frame15_and_cap5_at24_30_60_without_seconds_default(self):
        for fps in (24,30,60):
            r=self.report(self.fixture(fps));self.assertEqual([x['afterFrames'] for x in r['pauses']],[5,15,5]);self.assertEqual((r['afterDurationFrames'],r['sentenceTailFrames'],r['intraSentenceBreathCapFrames']),(103,15,5));self.assertEqual(r['fpsNumerator'],fps)
            self.assertEqual(r['pauses'][1]['afterTicks'],15*1000000//fps)
    def test_rational_actual_timeline_fps_and_phase_preserved(self):
        r=self.report(self.fixture(30000,1001));self.assertEqual((r['fpsNumerator'],r['fpsDenominator']),(30000,1001));self.assertEqual(r['afterDurationTicks'],103*1000000*1001//30000)
    def test_five_frames_can_be166667_microseconds_not_false_floor_cap(self):
        r=self.report(self.fixture(bounds=((0,13),(22,34),(60,72),(78,90))));self.assertEqual(r['pauses'][0]['afterFrames'],5);self.assertEqual(r['pauses'][0]['afterTicks'],166667)
    def test_shorter_and_exact_five_frame_breaths_unchanged(self):
        for count in (4,5):
            p=self.fixture(bounds=((0,12),(12+count,33),(60,72),(76,90)));r=self.report(p);self.assertEqual((r['pauses'][0]['afterFrames'],r['pauses'][0]['changed']),(count,False));self.assertEqual((r['pauses'][2]['afterFrames'],r['pauses'][2]['changed']),(4,False))
    def test_source_fps_is_not_timeline_clock_or_reason_to_change_fps(self):
        self.plan['sources'][0]['fps']=120;self.assertEqual(self.report()['fpsNumerator'],30)
        self.rejected(lambda p:p['nativeClock'].update(clockBasis='SOURCE_FPS'),'actual timeline FPS')
    def test_invalid_missing_or_submicrosecond_frame_clock_rejected(self):
        self.rejected(lambda p:p['nativeClock'].update(fpsDenominator=0),'FPS ratio')
        self.rejected(lambda p:p['nativeClock'].pop('evidenceRef'),'actual timeline FPS')
        self.rejected(lambda p:p['nativeClock'].update(fpsNumerator=200000000),'zero-length')
    def test_last_sentence_no_forced_tail_or_fake_padding(self):
        r=self.report();self.assertFalse(r['lastSentenceForcedTail']);self.assertEqual(r['afterDurationTicks']-r['words'][-1]['endTick'],1000000)
    def test_raw_word_pieces_and_atomic_caption_survive_quiet_picture_cut(self):
        before=copy.deepcopy(self.plan);out=prepare_pacing(self.plan);r=json.loads(out['pacing-report.json']);s=json.loads(out['pacing-spec.json']);self.assertEqual([w['id'] for w in r['words']],['a','b','c','d']);self.assertEqual([c['text'] for c in r['captionCues']],['Nga nói','giá trị']);self.assertEqual(r['captionCues'][0]['endTick'],r['captionCues'][1]['startTick']);self.assertGreater(len(s['track']['items']),1)
        self.assertTrue(all(i['speed']==1 and i['volume']==3 for i in s['track']['items']));self.assertEqual(self.plan,before);self.assertEqual(r['nativeAudioAcceptance'],'PENDING')
        for old,new in zip(self.plan['words'],r['words']):self.assertEqual(new['sourcePieces'][0]['sourceStartTick'],old['sourcePieces'][0]['sourceStartTick']);self.assertEqual(new['projectedSourcePieces'][0]['newEndTick']-new['projectedSourcePieces'][0]['newStartTick'],old['sourcePieces'][0]['sourceEndTick']-old['sourcePieces'][0]['sourceStartTick'])
    def test_unavailable15_frame_prior_source_tail_rejects_no_freeze_speed_or_pad(self):self.rejected(lambda p:p['reviewedPauses'][1]['previousSourceQuietTail'].update(availableEndTick=1599999),'available15-frame')
    def test_known_prompter_in_tail_rejected(self):self.rejected(lambda p:p['knownSpeechOrPrompterIntervals'].append({'sourceId':'s','startTick':1500000,'endTick':1700000,'role':'prompter','reviewed':True,'evidenceRef':'synthetic-prompter-review'}),'intersects retained speech or known prompter')
    def test_known_speech_in_removed_breath_is_not_quiet(self):self.rejected(lambda p:p['knownSpeechOrPrompterIntervals'].append({'sourceId':'s','startTick':600000,'endTick':650000,'role':'main','reviewed':True,'evidenceRef':'synthetic-extra-speech-review'}),'removal intersects known source speech')
    def test_amplitude_only_unknown_unreviewed_quiet_not_eligibility(self):
        self.rejected(lambda p:p['reviewedPauses'][0].update(reviewBasis='amplitude-only'),'amplitude-only');self.rejected(lambda p:p['reviewedPauses'][0].update(reviewed=False),'Quiet-only');self.rejected(lambda p:p['reviewedPauses'][0].update(noSpeechOrPrompter=None),'Quiet-only')
    def test_missing_join_or_tail_review_rejected(self):
        self.rejected(lambda p:p['reviewedPauses'][0].update(joinEvidenceRef=None),'join review');self.rejected(lambda p:p['reviewedPauses'][1]['previousSourceQuietTail'].pop('evidenceRef'),'available15-frame')
    def test_stale_pause_frame_or_tick_cannot_trim_a_raw_word(self):
        self.rejected(lambda p:p['reviewedPauses'][0].update(oldStartFrame=6),'exact adjacent frames');self.rejected(lambda p:p['reviewedPauses'][0].update(oldStartTick=200000),'exact adjacent frames')
    def test_every_sentence_transition_and_long_breath_requires_review(self):
        self.rejected(lambda p:p['reviewedPauses'].pop(0),'Affected sentence or long');self.rejected(lambda p:p['reviewedPauses'].pop(1),'Affected sentence or long')
    def test_subtitle_only_srt_only_never_change_pace(self):
        self.rejected(lambda p:p.update(workScope='SUB_ONLY'),'CND content editing only');self.rejected(lambda p:p.update(outputMode='SRT_ONLY'),'CND content editing only')
    def test_speed_edited_or_mismatched_frame_map_not_silently_rescaled(self):
        self.rejected(lambda p:p['clips'][0].update(speed=2),'no implicit speed change');self.rejected(lambda p:p['clips'][0].update(sourceOutTick=3999999),'reviewed exact mapping')
    def test_source_identity_and_actual_bounds_required(self):
        self.rejected(lambda p:p['sources'][0].update(sha256='sha256:'+'0'*64),'identity mismatch');self.rejected(lambda p:p['reviewedPauses'][1]['previousSourceQuietTail'].update(availableEndTick=10000001),'available15-frame')
    def test_sentence_not_inferred_from_asr_or_caption_punctuation(self):self.rejected(lambda p:p['reviewedSentences'][0].update(boundaryBasis='asr-segment'),'logical-meaning review')
    def test_picture_cut_never_creates_caption_boundary_inside_lock(self):
        def split(p):
            original=p['captionCues'][0];a=copy.deepcopy(original);b=copy.deepcopy(original);a.update(id='split-a',wordIds=['a'],text='Nga',reviewedDisplayByWord=['Nga']);b.update(id='split-b',wordIds=['b'],text='nói',reviewedDisplayByWord=['nói']);p['captionCues']=[a,b,p['captionCues'][1]]
        self.rejected(split,'retained old/new protected unit')
    def test_zero_baseline_sentence_gap_inserts_tail_on_correct_side(self):
        p=self.fixture(bounds=((0,12),(21,33),(33,45),(51,63)));p['clips']=[dict(p['clips'][0],endFrame=33,sourceOutTick=1100000),dict(p['clips'][0],id='next',startFrame=33,sourceInTick=2000000,sourceOutTick=4900000)]
        for w in p['words'][2:]:
            part=w['sourcePieces'][0];part.update(clipId='next',sourceStartTick=part['sourceStartTick']+900000,sourceEndTick=part['sourceEndTick']+900000)
        r=self.report(p);self.assertEqual(r['words'][2]['startFrame']-r['words'][1]['endFrame'],15);self.assertEqual(r['words'][2]['startTick']-r['words'][1]['endTick'],500000)
    def test_extra_nonadjacent_pause_pair_rejected(self):
        def extra(p):r=copy.deepcopy(p['reviewedPauses'][0]);r.update(previousWordId='a',nextWordId='d');p['reviewedPauses'].append(r)
        self.rejected(extra,'unknown/nonadjacent pairs')
    def test_raw_positive_audio_words_may_share_one_picture_frame(self):
        p=copy.deepcopy(self.plan);p['words'][0]['sourcePieces'][0].update(sourceEndTick=10000);p['words'][1]['sourcePieces'][0].update(sourceStartTick=10000,sourceEndTick=20000);p['reviewedPauses'].pop(0);row=p['reviewedPauses'][0];row.update(oldStartFrame=1,oldStartTick=33333);row['previousSourceQuietTail']['startTick']=33333
        r=self.report(p);self.assertEqual([w['startFrame'] for w in r['words'][:2]],[0,0]);self.assertEqual([w['endTick']-w['startTick'] for w in r['words'][:2]],[10000,10000])
    def test_non_aligned_audio_ticks_preserved_and_inverse_floor_clock_correct(self):
        p=copy.deepcopy(self.plan);p['words'][0]['sourcePieces'][0].update(sourceStartTick=33333,sourceEndTick=400001);p['reviewedPauses'][0].update(oldStartFrame=13,oldStartTick=433333)
        r=self.report(p);self.assertEqual(r['words'][0]['startFrame'],1);self.assertEqual((r['words'][0]['startTick'],r['words'][0]['endTick']),(33333,400001));self.assertEqual(r['pauses'][0]['afterFrames'],4);self.assertLessEqual(r['pauses'][0]['afterAuditoryGapTicks'],166667)
    def test_no_quiet_frame_between_raw_speech_blocks_sentence_edit(self):
        p=copy.deepcopy(self.plan);p['words'][1]['sourcePieces'][0]['sourceEndTick']=1990000;p['words'][2]['sourcePieces'][0]['sourceStartTick']=1991000
        with self.assertRaisesRegex(ValueError,'No whole-frame quiet'):prepare_pacing(p)
    def test_two_caption_onsets_in_same_frame_reject_zero_length_without_dropping_words(self):
        p=copy.deepcopy(self.plan);p['words'][0]['sourcePieces'][0].update(sourceEndTick=10000);p['words'][1]['sourcePieces'][0].update(sourceStartTick=10000,sourceEndTick=20000);p['reviewedPauses'].pop(0);p['reviewedPauses'][0].update(oldStartFrame=1,oldStartTick=33333);p['reviewedPauses'][0]['previousSourceQuietTail']['startTick']=33333;p['reviewedProtectedSpans']=[]
        p['captionCues']=[dict(p['captionCues'][0],id='one',wordIds=['a'],text='Nga',reviewedDisplayByWord=['Nga']),dict(p['captionCues'][0],id='two',wordIds=['b'],text='nói',reviewedDisplayByWord=['nói']),p['captionCues'][1]]
        with self.assertRaisesRegex(ValueError,'Zero-length rounded caption'):prepare_pacing(p)


    def test_reviewed_first_onset_and_last_end_preserved_on_new_piecewise_clock(self):
        p=copy.deepcopy(self.plan);p['reviewedCaptionOuterBounds'].update(firstOnsetFrame=0,lastEndFrame=100);r=self.report(p);self.assertEqual(r['captionCues'][0]['startFrame'],0);self.assertEqual(r['captionCues'][-1]['endFrame'],83);self.assertNotEqual(r['captionCues'][-1]['endFrame'],r['afterDurationFrames'])
    def test_missing_unreviewed_or_invalid_outer_caption_bounds_block(self):
        self.rejected(lambda p:p.pop('reviewedCaptionOuterBounds'),'original first caption');self.rejected(lambda p:p['reviewedCaptionOuterBounds'].update(lastEndFrame=89),'outer caption bounds')

    def test_interior_word_uses_retained_item_constant_offset_not_local_frame_phase(self):
        p=self.fixture(bounds=((0,12),(31,32),(60,72),(78,90)));b=p['words'][1];e=copy.deepcopy(b);e.update(id='e',text='rõ');e['sourcePieces'][0].update(sourceStartTick=1066666,sourceEndTick=1333333);p['words'].insert(2,e);p['reviewedSentences'][0].update(wordIds=['a','b','e'],text='Nga nói rõ');p['captionCues'][0].update(wordIds=['a','b','e'],text='Nga nói rõ',reviewedDisplayByWord=['Nga','nói','rõ']);p['protectedSpanReview']['wordIds']=['a','b','e','c','d'];p['reviewedPauses'][1].update(previousWordId='e',oldStartFrame=40,oldStartTick=1333333);p['reviewedPauses'][1]['previousSourceQuietTail']['startTick']=1333333
        r=self.report(p);word=next(w for w in r['words'] if w['id']=='e');self.assertEqual((word['startTick'],word['endTick']),(599999,866666));self.assertEqual(word['endTick']-word['startTick'],266667)
        for word in r['words']:
            for part in word['projectedSourcePieces']:
                m=next(m for m in r['piecewiseSourceToOutput'] if m['baseClipId']==part['clipId'] and m['oldStartTick']<=part['oldStartTick']<part['oldEndTick']<=m['oldEndTick']);self.assertEqual(part['newStartTick'],m['newStartTick']+part['oldStartTick']-m['oldStartTick']);self.assertEqual(part['newEndTick']-part['newStartTick'],part['sourceEndTick']-part['sourceStartTick'])
    def test_word_split_across_existing_base_maps_preserves_all_original_pieces(self):
        p=copy.deepcopy(self.plan);p['clips']=[dict(p['clips'][0],endFrame=6,sourceOutTick=200000),dict(p['clips'][0],id='rest',startFrame=6,sourceInTick=200000)];p['words'][0]['sourcePieces']=[{'clipId':'base','sourceStartTick':0,'sourceEndTick':200000},{'clipId':'rest','sourceStartTick':200000,'sourceEndTick':400000}]
        for w in p['words'][1:]:w['sourcePieces'][0]['clipId']='rest'
        r=self.report(p);word=r['words'][0];self.assertEqual(len(word['projectedSourcePieces']),2);self.assertEqual(sum(x['newEndTick']-x['newStartTick'] for x in word['projectedSourcePieces']),400000);self.assertEqual((word['startTick'],word['endTick']),(0,400000))

    def enable_shortfall(self,p):p['sentenceShortfallPolicy']={'action':'KEEP_REVIEWED_REAL_QUIET_AND_REPORT','authority':'explicit-user-request','evidenceRef':'synthetic-direct-user-retain-real-shortfall'}
    def test_reviewed_short_source_quiet_kept_and_per_sentence_shortfall_reported(self):
        p=copy.deepcopy(self.plan);self.enable_shortfall(p);p['reviewedPauses'][1]['previousSourceQuietTail']['availableEndTick']=1400000;r=self.report(p);row=r['pauses'][1];self.assertEqual(row['afterFrames'],9);self.assertTrue(row['shortfall']);self.assertEqual((row['retainedRealSourceQuietTicks'],row['afterAuditoryGapTicks']),(300000,300000));self.assertEqual(r['status'],'PREPARED_ONLY');self.assertEqual(row['sentenceId'],'s1')
    def test_shortfall_missing_explicit_decision_or_unreviewed_quiet_cannot_pass(self):
        self.rejected(lambda p:p['reviewedPauses'][1]['previousSourceQuietTail'].update(availableEndTick=1400000),'explicit reviewed real-quiet shortfall')
        p=copy.deepcopy(self.plan);self.enable_shortfall(p);p['reviewedPauses'][1]['previousSourceQuietTail'].update(availableEndTick=1400000,reviewed=False)
        with self.assertRaisesRegex(ValueError,'reviewed available15-frame'):prepare_pacing(p)
    def test_shortfall_rejects_inferred_or_unbound_policy(self):
        self.rejected(lambda p:p.update(sentenceShortfallPolicy={'action':'KEEP_REVIEWED_REAL_QUIET_AND_REPORT','authority':'model-suggestion','evidenceRef':'ASR-silence'}),'Scoped explicit');self.rejected(lambda p:p.update(sentenceShortfallPolicy={'action':'KEEP_REVIEWED_REAL_QUIET_AND_REPORT','authority':'explicit-user-request'}),'decision evidence')
    def test_fractional_shortfall_keeps_affected_baseline_and_prepares_other_quiet_cuts(self):
        p=copy.deepcopy(self.plan);self.enable_shortfall(p);p['reviewedPauses'][1]['previousSourceQuietTail']['availableEndTick']=1450001;r=self.report(p);self.assertEqual(r['status'],'PARTIAL_PREPARED_REVIEW_REQUIRED');self.assertEqual(r['pauses'][1]['decision'],'AFFECTED_JOIN_HELD_REVIEW_REQUIRED');self.assertNotIn('retainedRealSourceQuietTicks',r['pauses'][1]);self.assertEqual(r['pauses'][1]['reviewedShortSourceQuietTicks'],350001);self.assertTrue(r['pauses'][0]['changed']);self.assertEqual([w['id'] for w in r['words']],['a','b','c','d'])
    def test_200ms_raw_gap_with_only_five_quiet_frames_removes_one_safely(self):
        p=self.fixture(bounds=((0,329),(334,360),(420,432),(438,450)));p['clips'][0].update(endFrame=600,sourceOutTick=20000000);p['sources'][0]['actualDurationTicks']=30000000;p['words'][0]['sourcePieces'][0]['sourceEndTick']=10940000;p['words'][1]['sourcePieces'][0]['sourceStartTick']=11140000;p['reviewedPauses'][1]['previousSourceQuietTail']['availableEndTick']=12500000
        r=self.report(p);row=r['pauses'][0];self.assertEqual((row['beforeAuditoryGapTicks'],row['beforeWholeQuietFrames'],row['beforeLeftSubframeTicks'],row['beforeRightSubframeTicks']),(200000,5,26666,6667));self.assertTrue(row['changed']);self.assertEqual(row['afterFrames'],4);self.assertLessEqual(row['afterAuditoryGapTicks'],166667);self.assertEqual(r['words'][0]['sourcePieces'][0]['sourceEndTick'],10940000)
    def test_sentence_fractional_edges_not_falsely_labelled_exact15_auditory_gap(self):
        p=copy.deepcopy(self.plan);p['words'][1]['sourcePieces'][0]['sourceEndTick']=1100001;p['reviewedPauses'][1].update(oldStartFrame=34,oldStartTick=1133333);p['reviewedPauses'][1]['previousSourceQuietTail']['startTick']=1133333;r=self.report(p);row=r['pauses'][1];self.assertEqual(r['status'],'PARTIAL_PREPARED_REVIEW_REQUIRED');self.assertEqual(row['decision'],'AFFECTED_JOIN_HELD_REVIEW_REQUIRED');self.assertNotEqual(row['afterAuditoryGapTicks'],500000);self.assertEqual(row['beforeAuditoryGapTicks'],899999)

    def test_short_raw_gap_unchanged_with_fractional_speech_edge_margins(self):
        p=copy.deepcopy(self.plan);p['words'][0]['sourcePieces'][0]['sourceEndTick']=400001;p['words'][1]['sourcePieces'][0]['sourceStartTick']=525001;p['reviewedPauses'][0].update(oldStartFrame=13,oldStartTick=433333,oldEndFrame=15,oldEndTick=500000);r=self.report(p);row=r['pauses'][0];self.assertEqual(row['beforeAuditoryGapTicks'],125000);self.assertEqual(row['afterAuditoryGapTicks'],125000);self.assertFalse(row['changed']);self.assertEqual(row['beforeWholeQuietFrames'],2)

class BrollTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.addCleanup(self.temp.cleanup);root=Path(self.temp.name)
        base=root/'base.json';base.write_bytes(b'synthetic native snapshot; not app proof');source=root/'support.mp4';source.write_bytes(b'synthetic footage; not decoded video')
        def sha(p):return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
        captions=[{'id':f'c{i}','startTick':i*2000000,'endTick':(i+1)*2000000} for i in range(10)]
        self.plan={'schemaVersion':'capcut-broll-plan/v1','tickRate':1000000,'baseSnapshot':{'path':str(base),'sha256':sha(base),'durationTicks':20000000},'contentCaptionCheckpoint':'PASS','baseCheckpointEvidenceRef':'synthetic-user-base-review','baseCheckpointEvidenceBasis':'USER_REPORTED','captionCues':captions,'existingArollCuts':[0,9000000,16000000],'cadenceReview':{'reviewed':True,'evidenceRef':'synthetic-cadence-review','reason':'Meaning-led sparse plan'},'sources':[{'id':'b','path':str(source),'sha256':sha(source),'actualDurationTicks':30000000,'actualDurationEvidenceRef':'synthetic-actual-source-probe','sourceOrigin':'CAMERA','voiceClassification':'HAS_VOICE','classificationReview':{'reviewed':True,'evidenceRef':'synthetic-source-classification','evidenceBasis':'USER_REPORTED'},'permitted':True,'rightsEvidenceRef':'synthetic-permission'}],'placements':[self.placement('one','c1','c2',2000000,6000000)]}
        self.plan['sourceUsageReview']={'reviewed':True,'evidenceRef':'synthetic-whole-current-timeline-inventory','evidenceBasis':'USER_REPORTED','scope':'WHOLE_CURRENT_TIMELINE','baseSnapshotSha256':sha(base),'existingPlacements':[]}
        self.review_plan(self.plan)
    def review_plan(self,p):
        for item in p['placements']:
            rows=[]
            for s in p['sources']:
                edge=s['sourceOrigin']=='CAMERA' and s.get('voiceClassification')=='NO_VOICE'
                rows.append({'sourceId':s['id'],'status':'ELIGIBLE','evidenceRef':'synthetic-exhaustive-suitable-source-window-review','windows':[{'sourceInTick':5000000 if edge else 0,'sourceOutTick':s['actualDurationTicks']-4000000 if edge else s['actualDurationTicks']}],'reason':'Synthetic suitable window; not semantic or native proof'})
            item['eligibleSourceReview']={'reviewed':True,'evidenceRef':'synthetic-every-source-reviewed-for-this-placement','evidenceBasis':'USER_REPORTED','scope':'ALL_SUPPLIED_SOURCES','exhaustive':True,'baseSnapshotSha256':p['baseSnapshot']['sha256'],'sources':rows}
    def placement(self,id,first,last,start,end,source_in=0):
        return {'id':id,'sourceId':'b','sourceInTick':source_in,'startCaptionId':first,'lastCaptionId':last,'startTick':start,'endTick':end,'meaningReview':{'reviewed':True,'evidenceRef':'synthetic-meaning-review','relevance':'Context of the spoken question','addedInformation':'Visible environment illustrates context','startSelectionReason':'Caption onset chosen for meaning; existing cut is only a preference'},'paddedToTenSeconds':False,'muteSourceAudio':True,'preserveMainVideo':True}
    def rejected(self,change,pattern):
        p=copy.deepcopy(self.plan);change(p)
        with self.assertRaisesRegex(ValueError,pattern):prepare_broll(p)
    def test_exact_caption_start_without_maincut_intersection(self):
        original=copy.deepcopy(self.plan);out=prepare_broll(self.plan);spec=json.loads(out['broll-spec.json']);report=json.loads(out['broll-report.json'])
        self.assertEqual(spec['track']['items'][0]['startTicks'],2000000);self.assertEqual(report['placements'][0]['nearestExistingArollCutTick'],0)
        self.assertEqual(spec['mainVideoOperations'],[]);self.assertEqual(spec['mainAudioOperations'],[]);self.assertEqual(spec['captionOperations'],[]);self.assertEqual(self.plan,original)
    def test_nearby_cut_never_snaps_start(self):
        self.plan['existingArollCuts']=[0,1900000,10000000];r=json.loads(prepare_broll(self.plan)['broll-report.json'])['placements'][0]
        self.assertEqual((r['startTick'],r['nearestExistingArollCutTick'],r['cutDistanceTicks']),(2000000,1900000,100000))
    def test_wrong_start_or_end_anchor_rejected(self):
        self.rejected(lambda p:p['placements'][0].update(startTick=1900000),'exactly at caption')
        self.rejected(lambda p:p['placements'][0].update(endTick=5900000),'last caption end')
    def test_internal_caption_boundary_does_not_split_overlay(self):
        spec=json.loads(prepare_broll(self.plan)['broll-spec.json']);self.assertEqual(len(spec['track']['items']),1);self.assertEqual(spec['track']['items'][0]['durationTicks'],4000000)
    def test_hard_three_second_minimum_and_exact_three(self):
        self.plan['captionCues'][2]['endTick']=5000000;self.plan['captionCues'][3]['startTick']=5000000;self.plan['placements'][0]['endTick']=5000000
        self.assertEqual(json.loads(prepare_broll(self.plan)['broll-spec.json'])['track']['items'][0]['durationTicks'],3000000)
        self.plan['placements'][0].update(lastCaptionId='c1',endTick=4000000)
        with self.assertRaisesRegex(ValueError,'minimum three'):prepare_broll(self.plan)
    def test_over_ten_needs_meaning_reason_but_is_not_hard_max(self):
        self.plan['placements']=[self.placement('long','c0','c5',0,12000000)]
        self.review_plan(self.plan)
        with self.assertRaisesRegex(ValueError,'Over ten'):prepare_broll(self.plan)
        self.plan['placements'][0]['meaningReview']['overTenSecondsReason']='The reviewed visual demonstration needs all twelve seconds'
        self.assertEqual(json.loads(prepare_broll(self.plan)['broll-spec.json'])['track']['items'][0]['durationTicks'],12000000)
    def test_no_forced_ten_second_padding(self):self.rejected(lambda p:p['placements'][0].update(paddedToTenSeconds=True),'force-fill')
    def test_multiple_excerpts_same_source_and_soft_cadence(self):
        self.plan['placements'].append(self.placement('two','c8','c9',16000000,20000000,10000000))
        self.review_plan(self.plan)
        r=json.loads(prepare_broll(self.plan)['broll-report.json']);self.assertEqual(r['observedStartGapsTicks'],[14000000]);self.assertEqual(len(r['placements']),2)
        self.assertEqual([r['sourceId'] for r in r['placements']],['b','b'])
        self.assertEqual(r['status'],'PARTIAL_PREPARED_REVIEW_REQUIRED');self.assertIn('SOURCE_IDENTITY_ALREADY_USED_NO_REPEAT',r['sourceUsageConflicts'][0]['reasons'])
    def test_silent_separate_editable_track(self):
        item=json.loads(prepare_broll(self.plan)['broll-spec.json'])['track']['items'][0];self.assertEqual(item['volume'],0);self.assertTrue(item['separatelyEditable'])
        self.rejected(lambda p:p['placements'][0].update(muteSourceAudio=False),'Silent separate')
    def test_main_preservation_is_required(self):self.rejected(lambda p:p['placements'][0].update(preserveMainVideo=False),'preserve main')
    def test_unreviewed_meaning_or_missing_added_information_rejected(self):
        self.rejected(lambda p:p['placements'][0]['meaningReview'].update(reviewed=False),'meaningful relevance')
        self.rejected(lambda p:p['placements'][0]['meaningReview'].update(addedInformation=None),'added information')
    def test_cadence_whole_plan_review_required(self):self.rejected(lambda p:p['cadenceReview'].update(reason=None),'whole-plan cadence')
    def test_source_bounds_permission_and_identity(self):
        self.rejected(lambda p:p['placements'][0].update(sourceInTick=29000000),'source handles')
        self.rejected(lambda p:p['sources'][0].update(rightsEvidenceRef=None),'permission evidence')
        self.rejected(lambda p:p['sources'][0].update(sha256='sha256:'+'0'*64),'source identity')
    def test_frozen_baseline_identity(self):self.rejected(lambda p:p['baseSnapshot'].update(sha256='sha256:'+'0'*64),'base identity')
    def test_integer_native_clock_no_float_rounding(self):self.rejected(lambda p:p['placements'][0].update(startTick=2000000.0),'integer native')
    def test_base_checkpoint_evidence_and_actual_basis_required(self):
        for state in ('PENDING','BLOCKED','FAIL'):
            self.rejected(lambda p:p.update(contentCaptionCheckpoint=state),'passed base checkpoint')
        self.rejected(lambda p:p.update(baseCheckpointEvidenceRef=None),'passed base checkpoint')
        self.rejected(lambda p:p.update(baseCheckpointEvidenceBasis='ASSUMED'),'passed base checkpoint')
        r=json.loads(prepare_broll(self.plan)['broll-report.json']);self.assertEqual(r['baseCheckpointEvidenceBasis'],'USER_REPORTED');self.assertEqual(r['nativeAcceptance'],'PENDING')
    def test_unknown_reversed_or_overlapping_anchors_rejected(self):
        self.rejected(lambda p:p['placements'][0].update(startCaptionId='unknown'),'Known ordered')
        self.rejected(lambda p:p['placements'][0].update(startCaptionId='c3'),'Known ordered')
        self.rejected(lambda p:p['placements'].append(self.placement('two','c2','c3',4000000,8000000)),'Nonoverlapping')
    def camera_without_voice(self):
        self.plan['sources'][0]['voiceClassification']='NO_VOICE'
        self.plan['placements'][0]['sourceInTick']=5000000
        self.review_plan(self.plan)
    def test_camera_no_voice_head_boundary_exact_and_below(self):
        self.camera_without_voice()
        r=json.loads(prepare_broll(self.plan)['broll-report.json'])['placements'][0]
        self.assertTrue(r['sourceEdgeExclusionApplied']);self.assertEqual(r['sourceUsableWindowTicks'],[5000000,26000000])
        self.rejected(lambda p:p['placements'][0].update(sourceInTick=4999999),'exclude first five')
    def test_camera_no_voice_tail_exact_and_one_tick_over(self):
        self.camera_without_voice();self.plan['sources'][0]['actualDurationTicks']=13000000
        self.review_plan(self.plan)
        self.assertEqual(json.loads(prepare_broll(self.plan)['broll-report.json'])['placements'][0]['sourceOutTick'],9000000)
        self.rejected(lambda p:p['placements'][0].update(sourceInTick=5000001),'last four source')
    def test_camera_no_voice_twelve_second_source_allows_exact_three(self):
        self.camera_without_voice();self.plan['sources'][0]['actualDurationTicks']=12000000
        self.review_plan(self.plan)
        self.plan['captionCues'][2]['endTick']=5000000;self.plan['captionCues'][3]['startTick']=5000000;self.plan['placements'][0]['endTick']=5000000
        r=json.loads(prepare_broll(self.plan)['broll-report.json'])['placements'][0]
        self.assertEqual((r['sourceInTick'],r['sourceOutTick']), (5000000,8000000))
    def test_camera_no_voice_short_source_cannot_supply_three_seconds(self):
        self.camera_without_voice()
        for duration in (9000000,11999999):
            self.rejected(lambda p:p['sources'][0].update(actualDurationTicks=duration),'at least twelve')
    def test_camera_with_voice_has_no_mandated_edge_exclusion(self):
        self.plan['sources'][0]['actualDurationTicks']=4000000
        self.review_plan(self.plan)
        r=json.loads(prepare_broll(self.plan)['broll-report.json'])['placements'][0]
        self.assertFalse(r['sourceEdgeExclusionApplied']);self.assertEqual((r['sourceInTick'],r['sourceOutTick']),(0,4000000))
    def test_ai_without_voice_has_no_camera_edge_exclusion(self):
        self.plan['sources'][0].update(sourceOrigin='AI',voiceClassification='NO_VOICE',actualDurationTicks=4000000)
        self.review_plan(self.plan)
        r=json.loads(prepare_broll(self.plan)['broll-report.json'])['placements'][0]
        self.assertFalse(r['sourceEdgeExclusionApplied']);self.assertEqual(r['sourceUsableWindowTicks'],[0,4000000])
    def test_reviewed_ai_unknown_or_irrelevant_voice_needs_no_extra_interview(self):
        self.plan['sources'][0].update(sourceOrigin='AI',actualDurationTicks=3000000)
        self.review_plan(self.plan)
        self.plan['captionCues'][2]['endTick']=5000000;self.plan['captionCues'][3]['startTick']=5000000;self.plan['placements'][0]['endTick']=5000000
        for voice in ('UNKNOWN','NOT_APPLICABLE'):
            self.plan['sources'][0]['voiceClassification']=voice
            r=json.loads(prepare_broll(self.plan)['broll-report.json'])['placements'][0]
            self.assertEqual((r['sourceInTick'],r['sourceOutTick']),(0,3000000));self.assertFalse(r['sourceEdgeExclusionApplied'])
    def test_unknown_origin_cannot_claim_camera_no_voice_class(self):
        self.plan['sources'][0].update(sourceOrigin='UNKNOWN',voiceClassification='NO_VOICE')
        with self.assertRaisesRegex(ValueError,'GATE0_SOURCE_CLASSIFICATION_REQUIRED'):prepare_broll(self.plan)
    def test_unknown_or_missing_class_requires_gate0_interview(self):
        for key in ('sourceOrigin','voiceClassification'):
            self.rejected(lambda p:p['sources'][0].update({key:'UNKNOWN'}),'GATE0_SOURCE_CLASSIFICATION_REQUIRED')
            self.rejected(lambda p:p['sources'][0].pop(key),'GATE0_SOURCE_CLASSIFICATION_REQUIRED')
    def test_missing_or_assumed_classification_evidence_rejected(self):
        self.rejected(lambda p:p['sources'][0].pop('classificationReview'),'GATE0_SOURCE_CLASSIFICATION_REQUIRED')
        self.rejected(lambda p:p['sources'][0]['classificationReview'].update(reviewed=False),'GATE0_SOURCE_CLASSIFICATION_REQUIRED')
        self.rejected(lambda p:p['sources'][0]['classificationReview'].update(evidenceBasis='ASSUMED_FROM_AUDIO_STREAM'),'GATE0_SOURCE_CLASSIFICATION_REQUIRED')
    def test_muting_stream_or_silence_never_resolves_unknown_voice(self):
        self.plan['sources'][0].update(voiceClassification='UNKNOWN',hasAudioStream=False,asrText='',looksCameraShot=True)
        with self.assertRaisesRegex(ValueError,'GATE0_SOURCE_CLASSIFICATION_REQUIRED'):prepare_broll(self.plan)
    def test_each_repeated_camera_no_voice_excerpt_uses_trimmed_source_window(self):
        self.camera_without_voice();self.plan['placements'].append(self.placement('two','c8','c9',16000000,20000000,10000000))
        self.review_plan(self.plan)
        r=json.loads(prepare_broll(self.plan)['broll-report.json']);self.assertEqual(len(r['placements']),2)
        self.rejected(lambda p:p['placements'][1].update(sourceInTick=4999999),'exclude first five')
    def test_actual_duration_not_native_rounded_duration_for_tail(self):
        self.camera_without_voice();self.plan['sources'][0].update(actualDurationTicks=13500000,durationTicks=14000000)
        self.review_plan(self.plan)
        self.plan['placements'][0]['sourceInTick']=5500000
        self.assertEqual(json.loads(prepare_broll(self.plan)['broll-report.json'])['placements'][0]['sourceOutTick'],9500000)
        self.rejected(lambda p:p['placements'][0].update(sourceInTick=5500001),'last four source')
    def test_actual_duration_and_probe_evidence_required(self):
        self.rejected(lambda p:p['sources'][0].pop('actualDurationTicks'),'integer native')
        self.rejected(lambda p:p['sources'][0].update(actualDurationEvidenceRef=None),'actual source duration')
    def test_actual_duration_bounds_apply_to_ai_and_voiced_camera_too(self):
        self.plan['sources'][0].update(sourceOrigin='AI',actualDurationTicks=3500000,durationTicks=4000000)
        with self.assertRaisesRegex(ValueError,'actual source handles'):prepare_broll(self.plan)

class BrollOwnedRevisionAuthorityTests(unittest.TestCase):
    """Synthetic temporary stores prove bindings, never native/user acceptance."""
    placement=BrollTests.placement
    review_plan=BrollTests.review_plan

    def setUp(self):
        import shutil
        import native_timeline as native
        import native_revision as revision
        BrollTests.setUp(self)
        self.root=Path(self.temp.name).resolve()
        self.base=Path(self.plan['baseSnapshot']['path'])
        source=self.plan['sources'][0]
        initial=self.root/'synthetic-compiled'
        manifest=native.compile_plan({'schema':native.SCHEMA,
            'project':{'name':'OwnedBroll_EP 1','fps':30,'canvas':{'width':1080,'height':1920}},
            'sources':[{'id':'main','path':source['path'],'sha256':source['sha256'],
                'durationTicks':30000000,'width':1080,'height':1920}],
            'mainPieces':[{'id':'m1','sourceId':'main','sourceInTicks':0,'sourceOutTicks':20000000,'targetInTicks':0}],
            'captions':[{'id':'c1','text':'cụm có nghĩa','rawWordIds':['w1','w2','w3'],
                'startTicks':0,'endTicks':20000000,'style':{}}],
            'brollPolicy':'NO_SOURCE_REPEAT','broll':[]},initial)
        self.store=self.root/'synthetic-store';self.target=self.store/manifest['name']
        shutil.copytree(initial/'files',self.target)
        meta=native.read_json(self.target/'draft_meta_info.json')
        meta.update(draft_fold_path=str(self.target).replace('\\','/'),draft_root_path=str(self.store).replace('\\','/'))
        (self.target/'draft_meta_info.json').write_bytes(native.json_bytes(meta))
        self.index=self.store/'root_meta_info.json'
        self.index.write_bytes(native.json_bytes({'all_draft_store':[{'draft_id':manifest['projectId'],
            'draft_name':manifest['name'],'draft_fold_path':str(self.target).replace('\\','/')}]}))
        self.baseline_ref=revision.capture_baseline(self.store,manifest['name'],self.root/'baseline')
        self.baseline=native.read_json(self.baseline_ref['path'])
        self.base.write_bytes((initial/'files/draft_content.json').read_bytes())
        base_hash=self.sha(self.base);self.plan['baseSnapshot']['sha256']=base_hash
        self.plan['sourceUsageReview']['baseSnapshotSha256']=base_hash;self.review_plan(self.plan)
        self.decision={'schema':'capcut-review-draft-decision/v1','evidenceClass':'REAL_OBSERVATION',
            'authority':'explicit-user-request','mode':'REVIEW_DRAFT','taskId':'synthetic-owned-broll',
            'userQuote':'SIMULATED UNIT AUTHORITY; NO HUMAN OR PRODUCTION ACCEPTANCE',
            'operation':revision.OPERATION,'revisionBaseline':self.baseline_ref,
            'destinationPath':str(self.target),'projectName':manifest['name'],
            'projectId':manifest['projectId'],'timelineId':manifest['timelineId']}
        self.authority={'evidenceClass':'REAL_OBSERVATION','authority':'explicit-user-request',
            'claim':'review-draft-native-update-owned','mode':'REVIEW_DRAFT',
            'taskId':self.decision['taskId'],'userQuote':self.decision['userQuote'],
            'operation':revision.OPERATION,'destinationPath':str(self.target),'name':manifest['name'],
            'projectId':manifest['projectId'],'timelineId':manifest['timelineId'],
            'rootIndexSHA256':self.baseline['rootIndexSHA256'],'expectedFiles':copy.deepcopy(self.baseline['expectedFiles'])}
        self.plan.update(mode='REVIEW_DRAFT',contentCaptionCheckpoint='PROVISIONAL_PREPARED',
            baseCheckpointEvidenceBasis='STRUCTURAL_PREPARATION')
        self.refresh()

    def sha(self,path):return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
    def refresh(self):
        decision_path=self.root/'synthetic-decision.json'
        decision_path.write_text(json.dumps(self.decision),encoding='utf-8')
        self.authority['originalDecision']={'path':str(decision_path),'sha256':self.sha(decision_path)}
        authority_path=self.root/'synthetic-authority.json'
        authority_path.write_text(json.dumps(self.authority),encoding='utf-8')
        self.plan['reviewDraftAuthority']={'path':str(authority_path),'sha256':self.sha(authority_path)}

    def reject(self,pattern):
        self.refresh()
        with self.assertRaisesRegex(ValueError,pattern):prepare_broll(self.plan)

    def test_exact_owned_revision_broll_prepares_without_mutating_store(self):
        before={p:p.read_bytes() for p in self.store.rglob('*') if p.is_file()}
        result=json.loads(prepare_broll(self.plan)['broll-report.json'])
        self.assertEqual(result['status'],'PREPARED_ONLY')
        self.assertEqual(result['nativeAcceptance'],'PENDING')
        self.assertEqual({p:p.read_bytes() for p in before},before)

    def test_existing_create_authority_branch_remains_unchanged(self):
        self.authority={'evidenceClass':'REAL_OBSERVATION','authority':'explicit-user-request',
            'claim':'review-draft-native-apply','mode':'REVIEW_DRAFT','userQuote':'SIMULATED CREATE UNIT'}
        self.refresh();self.assertEqual(json.loads(prepare_broll(self.plan)['broll-report.json'])['status'],'PREPARED_ONLY')

    def test_owned_claim_requires_exact_operation(self):
        self.authority['operation']='CREATE_SEPARATE_NEW_PROJECT';self.reject('owned original decision')
    def test_original_decision_requires_owned_operation(self):
        self.decision['operation']='CREATE_SEPARATE_NEW_PROJECT';self.reject('owned original decision')
    def test_missing_baseline_is_refused(self):
        self.decision.pop('revisionBaseline');self.reject('ref|reference|hash')
    def test_original_quote_drift_is_refused(self):
        self.decision['userQuote']='OTHER SIMULATED SCOPE';self.reject('owned original decision')
    def test_wrapper_foreign_target_is_refused(self):
        self.authority['destinationPath']=str(self.store/'Foreign');self.reject('owned exact target')
    def test_original_foreign_target_is_refused(self):
        self.decision['destinationPath']=str(self.store/'Foreign');self.reject('owned exact target')
    def test_project_id_drift_is_refused(self):
        self.authority['projectId']='00000000-0000-0000-0000-000000000000';self.reject('owned exact target')
    def test_timeline_id_drift_is_refused(self):
        self.decision['timelineId']='00000000-0000-0000-0000-000000000000';self.reject('owned exact target')
    def test_expected_nine_hash_drift_is_refused(self):
        self.authority['expectedFiles']['draft_content.json']='0'*64;self.reject('owned exact target')
    def test_wrapper_index_drift_is_refused(self):
        self.authority['rootIndexSHA256']='0'*64;self.reject('owned exact target')
    def test_actual_target_drift_is_refused(self):
        (self.target/'key_value.json').write_bytes(b'{}');self.reject('revision-target-drift')
    def test_actual_shared_index_drift_is_refused(self):
        self.index.write_bytes(self.index.read_bytes()+b' ');self.reject('revision-root-index-drift')
    def test_foreign_base_project_is_refused(self):
        data=json.loads(self.base.read_text(encoding='utf-8'));data['id']='00000000-0000-0000-0000-000000000000'
        self.base.write_text(json.dumps(data),encoding='utf-8');self.plan['baseSnapshot']['sha256']=self.sha(self.base)
        self.reject('owned base project identity')


class NgaEmojiTests(unittest.TestCase):
    def setUp(self):TimingTests.setUp(self)
    def set_text(self,p,text):TimingTests.set_text(self,p,text)
    def binding(self):
        return {'recipient':{'kind':'PERSON','id':'mrs-nga','label':'Mrs Nga','reviewed':True,'evidenceRef':'synthetic-explicit-person-answer'},'contentDomain':{'id':'real-estate','reviewed':True,'evidenceRef':'synthetic-explicit-domain-answer'},'style':{'selectedId':None}}
    def text_plan(self,text,groups=None):
        p=copy.deepcopy(self.plan);t=copy.deepcopy(p['takes'][1]);tokens=text.split()
        words=[{'id':'e'+str(i),'text':x,'start':20.1+i*.2,'end':20.25+i*.2,'role':'main','reviewed':True,'evidenceRef':'synthetic-word'} for i,x in enumerate(tokens)]
        ids=[w['id'] for w in words];t.update(words=words,out=20.4+len(words)*.2,reviewedSentences=[{'id':'s1','wordIds':ids,'text':' '.join(tokens),'boundaryBasis':'reviewed-logical-sentence','reviewed':True,'evidenceRef':'synthetic-sentence'}],reviewedProtectedSpans=[],protectedSpanReview={'reviewed':True,'basis':'whole-transcript-semantic-review','wordIds':ids,'evidenceRef':'synthetic-whole-review'})
        t['phrases']=[];at=0
        for i,n in enumerate(groups or [len(words)]):
            span=words[at:at+n];t['phrases'].append({'id':'ep'+str(i),'sentenceId':'s1','wordIds':[w['id'] for w in span],'text':' '.join(w['text'] for w in span),'start':span[0]['start'],'end':span[-1]['end'],'role':'main','reviewed':True,'evidenceRef':'synthetic-cue'});at+=n
        self.assertEqual(at,len(words));p['takes']=[t];p['units']=[{'id':'u1','scriptText':' '.join(tokens)}];p.update(self.binding());return p
    def report(self,p):return json.loads(prepare(p)['selection-report.json'])
    def direct(self,text):
        tokens=text.split();w=[{'id':str(i),'text':t} for i,t in enumerate(tokens)]
        return nga_emoji_display(w,tokens,self.binding(),{x['id']:'s' for x in w})
    def protect(self,p,a,b):
        t=p['takes'][0];w=t['words'][a:b];t['reviewedProtectedSpans'].append({'id':'lock','sentenceId':'s1','wordIds':[x['id'] for x in w],'text':' '.join(x['text'] for x in w),'kind':'noun-phrase','reviewed':True,'evidenceRef':'synthetic-retained-lock'})
    def test_exact_all_three_terms_raw_ids_reversible(self):
        p=self.text_plan('bất động sản sale deal');before=copy.deepcopy(p);r=self.report(p);c=r['captionCues'][0]
        self.assertEqual(c['text'],'🏡 👨‍💼👩‍💼 🤝📝');tr=c['styleDisplayTransforms'];self.assertEqual([x['matchedWholeTerm'] for x in tr],['bất động sản','sale','deal'])
        self.assertEqual([x for z in tr for x in z['rawWordIds']],c['wordIds']);self.assertEqual(' '.join(z['rawText'] for z in tr),c['rawText']);self.assertEqual(p,before)
    def test_uppercase_variants_replace_without_global_case_change(self):self.assertEqual(self.report(self.text_plan('BẤT ĐỘNG SẢN SALE DEAL'))['captionCues'][0]['text'],'🏡 👨‍💼👩‍💼 🤝📝')
    def test_nfd_unicode_and_whitespace_display_only(self):
        import unicodedata
        p=self.text_plan(unicodedata.normalize('NFD','bất động sản')+'\u00a0SALE');before=copy.deepcopy(p);self.assertEqual(self.report(p)['captionCues'][0]['text'],'🏡 👨‍💼👩‍💼');self.assertEqual(p,before)
    def test_whole_unicode_tokens_not_sales_dealer_or_neighbor_letters(self):
        out,tr,_=self.direct('sales dealer presale sale deal sale_name sale2 saleé dealx αsale sale\u0301')
        self.assertEqual(' '.join(out),'sales dealer presale 👨‍💼👩‍💼 🤝📝 sale_name sale2 saleé dealx αsale salé');self.assertEqual(len(tr),2)
    def test_uncomposed_combining_and_join_format_not_plain_whole_terms(self):
        text='sale\u0338 deal\u0338 bất động sản\u0338 sale\u200dX deal\u200bX';out,tr,_=self.direct(text)
        self.assertEqual(' '.join(out),text);self.assertEqual(tr,[])
    def test_internal_comma_colon_question_preserved(self):self.assertEqual(self.report(self.text_plan('bất động sản, sale: deal?'))['captionCues'][0]['text'],'🏡, 👨‍💼👩‍💼: 🤝📝?')
    def test_trailing_comma_and_ordinary_period_policy_still_applies(self):self.assertEqual(self.report(self.text_plan('bất động sản. sale,'))['captionCues'][0]['text'],'🏡 👨‍💼👩‍💼')
    def test_all_repeated_matches_in_order(self):
        r=self.report(self.text_plan('bất động sản bất động sản sale sale deal deal'))['captionCues'][0]
        self.assertEqual(r['text'],'🏡 🏡 👨‍💼👩‍💼 👨‍💼👩‍💼 🤝📝 🤝📝');self.assertEqual(len(r['styleDisplayTransforms']),6);self.assertEqual(len(r['wordIds']),10)
    def test_style_replacement_cannot_cross_cue_boundary(self):
        with self.assertRaisesRegex(ValueError,'atomic saved-style'):self.report(self.text_plan('bất động sản tốt',[1,3]))
    def test_prior_user_lock_still_rejects_split(self):
        p=self.text_plan('những bạn sale tốt',[2,2]);self.protect(p,0,3)
        with self.assertRaisesRegex(ValueError,'protected semantic span'):self.report(p)
    def test_prior_lock_preserved_with_emoji_inside(self):
        p=self.text_plan('những bạn sale tốt');self.protect(p,0,3);r=self.report(p)
        self.assertEqual(r['captionCues'][0]['text'],'những bạn 👨‍💼👩‍💼 tốt');self.assertEqual(r['units'][0]['reviewedProtectedSpans'][0]['wordIds'],['e0','e1','e2'])
    def test_authorized_replacement_counts_after_display_six_pass(self):
        p=self.text_plan('bất động sản a b c d e');self.protect(p,0,8);self.assertEqual(len(self.report(p)['captionCues'][0]['text'].split()),6)
    def test_over_six_after_display_remains_conflict(self):
        p=self.text_plan('bất động sản a b c d e f');self.protect(p,0,9)
        with self.assertRaisesRegex(ValueError,'semantic-unit conflict'):self.report(p)
    def test_no_other_raw_word_erased_or_timing_rewritten(self):
        p=self.text_plan('Nga thích bất động sản sale');before=copy.deepcopy(p);r=self.report(p);c=r['captionCues'][0]
        self.assertEqual(c['rawText'],'Nga thích bất động sản sale');self.assertEqual(c['wordIds'],[x['id'] for x in p['takes'][0]['words']]);self.assertEqual(c['start'],.1);self.assertEqual(c['end'],1.25);self.assertEqual(p,before)
    def test_exact_zwj_pairs_and_utf16_units(self):
        _,tr,_=self.direct('sale deal bất động sản');self.assertEqual([(x['replacementCodepoints'],x['replacementUtf16Units']) for x in tr],[(6,10),(2,4),(1,2)]);self.assertEqual(tr[0]['displayReplacement'],'👨\u200d💼👩\u200d💼');self.assertTrue(all(x['replacementAtomic'] for x in tr))
    def test_existing_emoji_display_idempotent(self):
        out,tr,_=self.direct('🏡 👨‍💼👩‍💼 🤝📝');self.assertEqual(' '.join(out),'🏡 👨‍💼👩‍💼 🤝📝');self.assertEqual(tr,[])
    def test_full_prepare_replay_idempotent_and_input_unchanged(self):
        p=self.text_plan('bất động sản sale deal');before=copy.deepcopy(p);self.assertEqual(prepare(p),prepare(p));self.assertEqual(p,before)
    def test_other_person_does_not_apply(self):
        p=self.text_plan('bất động sản sale deal');p['recipient'].update(id='other-person',label='Other person');self.assertEqual(self.report(p)['captionCues'][0]['text'],'bất động sản sale deal')
    def test_other_domain_does_not_apply(self):
        p=self.text_plan('bất động sản sale deal');p['contentDomain']['id']='health';self.assertFalse(self.report(p)['savedStyleSelection']['applies'])
    def test_explicit_different_style_preserved(self):
        p=self.text_plan('bất động sản sale deal');p['style']['selectedId']='other-style';self.assertEqual(self.report(p)['captionCues'][0]['styleDisplayTransforms'],[])
    def test_bare_nga_label_not_person_identity(self):
        p=self.text_plan('bất động sản sale deal');p['recipient'].update(id='nga',label='Nga');self.assertFalse(self.report(p)['savedStyleSelection']['applies'])
    def test_country_or_organization_not_mrs_nga_person(self):
        p=self.text_plan('bất động sản sale deal');p['recipient']['kind']='ORGANIZATION';self.assertFalse(self.report(p)['savedStyleSelection']['applies'])
    def test_selected_nga_without_recipient_requires_gate0(self):
        p=self.text_plan('bất động sản');p.pop('recipient');p['style']['selectedId']='nga'
        with self.assertRaisesRegex(ValueError,'Clip này làm cho ai'):self.report(p)
    def test_confirmed_mrs_nga_unknown_domain_requires_gate0(self):
        p=self.text_plan('bất động sản');p.pop('contentDomain')
        with self.assertRaisesRegex(ValueError,'GATE0_STYLE_BINDING_REQUIRED'):self.report(p)
    def test_style_cannot_cross_real_sentence_after_punctuation_removed(self):
        w=[{'id':'a','text':'bất'},{'id':'b','text':'động'},{'id':'c','text':'sản'}]
        with self.assertRaisesRegex(ValueError,'logical sentence'):nga_emoji_display(w,['bất','động','sản'],self.binding(),{'a':'s1','b':'s2','c':'s2'})
    def test_punctuation_adjacent_whole_tokens_without_ascii_boundary(self):
        out,tr,_=self.direct('(SALE), DEAL?');self.assertEqual(' '.join(out),'(👨‍💼👩‍💼), 🤝📝?');self.assertEqual(len(tr),2)
    def test_matching_multiple_punctuation_delimited_terms_in_one_raw_word(self):
        out,tr,_=self.direct('sale/deal');self.assertEqual(out,['👨‍💼👩‍💼/🤝📝']);self.assertEqual(len(tr),2);self.assertEqual(tr[0]['rawWords'],[{'id':'0','text':'sale/deal'}])
    def test_ordinal_first_content_transform_keeps_prefix_and_raw_trace(self):
        p=self.text_plan('Thứ nhất là về sale tốt');t=p['takes'][0]
        p['enumerationDisplayAuthorization']={'authority':'explicit-user-request','evidenceRef':'synthetic-numbered-style-request','scope':'reviewed-ordinal-lead-in-to-numbered-caption-prefix'}
        p['reviewedEnumerations']=[{'id':'list','reviewed':True,'basis':'reviewed-spoken-enumeration','complete':True,'evidenceRef':'synthetic-complete-one-item-list','items':[{'id':'item','ordinal':1,'takeId':t['id'],'sentenceId':'s1','leadInWordIds':['e0','e1','e2','e3'],'markerWordIds':['e0','e1','e2'],'leadInText':'Thứ nhất là về','firstContentWordId':'e4','markerMeaning':'ordinal','leadInOnly':True,'reviewed':True,'evidenceRef':'synthetic-list-item'}]}]
        r=self.report(p)
        self.assertEqual(r['captionCues'][0]['text'],'1. 👨‍💼👩‍💼 tốt');self.assertEqual(r['captionCues'][0]['enumerationTransforms'][0]['rawWordIds'],['e0','e1','e2','e3'])
    def intake(self,binding):
        brief={'schemaVersion':'capcut-brief/v1','workScope':'SUB_ONLY','output':{'mode':'EDIT_TIMELINE','modeEvidence':'synthetic-known-mode'},'requiresTranscription':False,'transcriptionRequirementEvidenceRef':'synthetic-aligned-source','projectIdentity':{'name':'Synthetic existing target','evidenceRef':'synthetic-known-project'}};brief.update(binding);return json.loads(prepare_intake(brief)['caption-intake-report.json'])
    def test_intake_unknown_recipient_asks_exact_question_once(self):
        r=self.intake({});self.assertEqual(r['inputDependencies'],['RECIPIENT']);self.assertEqual(r['nextQuestion'],'Clip này làm cho ai?');self.assertFalse(r['readyForAuthorizedPreparation'])
    def test_intake_known_recipient_domain_reused_no_question(self):
        r=self.intake(self.binding());self.assertTrue(r['readyForAuthorizedPreparation']);self.assertIsNone(r['nextQuestion']);self.assertEqual(r['savedStyleSelection']['effectiveStyleId'],'nga')
    def test_intake_unknown_domain_only_after_known_mrs_nga(self):
        b=self.binding();b.pop('contentDomain');r=self.intake(b);self.assertEqual(r['inputDependencies'],['CONTENT_DOMAIN'])
    def test_intake_unreviewed_or_missing_evidence_is_unknown(self):
        b=self.binding();b['recipient']['evidenceRef']='';self.assertEqual(self.intake(b)['inputDependencies'],['RECIPIENT']);b=self.binding();b['recipient']['reviewed']=False;self.assertEqual(self.intake(b)['nextQuestion'],'Clip này làm cho ai?')
    def test_intake_other_recipient_needs_no_nga_domain(self):
        b=self.binding();b['recipient']['id']='other-person';b.pop('contentDomain');self.assertTrue(self.intake(b)['readyForAuthorizedPreparation'])
    def test_invalid_style_shape_not_silently_ignored(self):
        for invalid in ('nga',[],False,0,''):
            with self.subTest(style=invalid):
                p=self.text_plan('sale');p['style']=invalid
                with self.assertRaisesRegex(ValueError,'object'):self.report(p)


class AllPauseTests(unittest.TestCase):
    """New default is quiet-interior review, never a legacy15/5 alias."""
    setUp=PacingTests.setUp
    fixture=PacingTests.fixture
    select_scope=PacingTests.select_scope
    all_plan=PacingTests.all_plan
    report=PacingTests.report
    bind_nga=PacingTests.bind_nga
    def test_global_omitted_default_removes_safe_interiors_within_and_between(self):
        p=self.all_plan();before=copy.deepcopy(p);r=self.report(p)
        self.assertEqual((r['pacingScope'],r['pacingScopeDefault']),('ALL_PAUSES','ALL_PAUSES'))
        self.assertEqual([x['afterFrames'] for x in r['pauses']],[2,2,6]);self.assertEqual(r['afterDurationFrames'],88)
        self.assertEqual((r['sentenceTailFrames'],r['intraSentenceBreathCapFrames'],r['intraAuditoryGapMaximumTicks']),(None,None,None))
        self.assertEqual(r['intraSentenceEditCount'],1);self.assertEqual(p,before)
    def test_default_identical_for_every_recipient_and_selected_style(self):
        for binding in ('generic','nga','other-style','other-domain','other-recipient'):
            p=self.all_plan()
            if binding!='generic':self.bind_nga(p)
            if binding=='other-style':p['style']['selectedId']='another-style'
            if binding=='other-domain':p['contentDomain']['id']='another-domain'
            if binding=='other-recipient':p['recipient']['id']='another-person'
            r=self.report(p);self.assertEqual(r['pacingScope'],'ALL_PAUSES');self.assertEqual(r['afterDurationFrames'],88)
    def test_explicit_all_scope_has_same_safe_policy(self):
        p=self.all_plan();p['pacingScope']='ALL_PAUSES';self.assertEqual(self.report(p)['afterDurationFrames'],88)
    def test_keyword_or_style_does_not_supply_cut_authority(self):
        p=self.all_plan();p.pop('authorization');p.update(style={'selectedId':'all-pauses'},instructions='ALL_PAUSES requested')
        with self.assertRaisesRegex(ValueError,'Explicit pacing authority'):prepare_pacing(p)
    def test_both_legacy_modes_require_scoped_authority_for_generic_and_nga(self):
        for scope in ('INTER_SENTENCE_ONLY','SENTENCE_AND_INTRA'):
            for nga in (False,True):
                p=self.all_plan();p['pacingScope']=scope
                if nga:self.bind_nga(p)
                with self.assertRaisesRegex(ValueError,'nondefault pacingScope'):prepare_pacing(p)
                self.select_scope(p,scope);r=self.report(p);self.assertEqual(r['pacingScope'],scope)
    def test_missing_pause_review_holds_join_without_blocking_independent_safe_cuts(self):
        p=self.all_plan();p['reviewedPauses'].pop(0);r=self.report(p)
        self.assertEqual(r['status'],'PARTIAL_PREPARED_REVIEW_REQUIRED');self.assertEqual(len(r['quietEdits']),1)
        self.assertEqual(r['pauses'][0]['decision'],'AFFECTED_JOIN_HELD_REVIEW_REQUIRED');self.assertEqual(r['pauses'][0]['beforeAuditoryGapTicks'],r['pauses'][0]['afterAuditoryGapTicks'])
    def test_no_safe_interior_is_never_silently_legacy_trimmed(self):
        p=self.all_plan()
        for row in p['reviewedPauses']:row.pop('safeRemoval')
        r=self.report(p);self.assertEqual(r['afterDurationFrames'],120);self.assertEqual(r['quietEdits'],[]);self.assertEqual(len(r['nativeRepresentationConflicts']),2)
    def test_shape_example_is_not_review_authority(self):
        p=self.all_plan();p['reviewedPauseExampleShapeOnly']=p['reviewedPauses'][0];p['reviewedPauses']=[]
        r=self.report(p);self.assertEqual(r['quietEdits'],[]);self.assertEqual(r['status'],'PARTIAL_PREPARED_REVIEW_REQUIRED')
    def test_unreviewed_energy_or_asr_only_interior_is_held(self):
        for change in ('safe-unreviewed','safe-asr','outer-energy','join-missing','unknown-voice'):
            p=self.all_plan();row=p['reviewedPauses'][0]
            if change=='safe-unreviewed':row['safeRemoval']['reviewed']=False
            elif change=='safe-asr':row['safeRemoval']['reviewBasis']='asr-word-gap'
            elif change=='outer-energy':row['reviewBasis']='amplitude-only'
            elif change=='join-missing':row.pop('joinEvidenceRef')
            else:row['noSpeechOrPrompter']=None
            r=self.report(p);self.assertEqual(r['pauses'][0]['decision'],'AFFECTED_JOIN_HELD_REVIEW_REQUIRED');self.assertEqual(len(r['quietEdits']),1)
    def test_cut_cannot_touch_or_cross_raw_word_edges(self):
        for edge in ('left','right','cross'):
            p=self.all_plan();row=p['reviewedPauses'][0];safe=row['safeRemoval']
            if edge=='left':safe.update(startFrame=row['oldStartFrame'],startTick=row['oldStartTick'],leftPhoneticHandleTicks=0)
            elif edge=='right':safe.update(endFrame=row['oldEndFrame'],endTick=row['oldEndTick'],rightPhoneticHandleTicks=0)
            else:safe.update(startFrame=row['oldStartFrame']-1,startTick=row['oldStartTick']-33334)
            with self.assertRaisesRegex(ValueError,'phonetic handles|raw word gap'):prepare_pacing(p)
    def test_handle_and_tick_claims_must_match_exact_clock(self):
        for field in ('leftPhoneticHandleTicks','rightPhoneticHandleTicks','startTick','endTick'):
            p=self.all_plan();p['reviewedPauses'][0]['safeRemoval'][field]+=1
            with self.assertRaisesRegex(ValueError,'matching native ticks|phonetic handles'):prepare_pacing(p)
    def test_known_soft_speech_or_prompter_blocks_actual_quiet_removal(self):
        for role in ('main','prompter','other'):
            p=self.all_plan();p['knownSpeechOrPrompterIntervals']=[{'sourceId':'s','startTick':600000,'endTick':620000,'role':role,'reviewed':True,'evidenceRef':'synthetic-low-amplitude-guard'}]
            with self.assertRaisesRegex(ValueError,'removal intersects known source speech'):prepare_pacing(p)
    def test_all_cut_preserves_word_audio_durations_volume_and_original_ids(self):
        p=self.all_plan();r=self.report(p);spec=json.loads(prepare_pacing(p)['pacing-spec.json'])
        self.assertFalse(spec['applyEligible']);self.assertEqual(r['nativeAudioAcceptance'],'PENDING')
        for old,new in zip(p['words'],r['words']):
            self.assertEqual(new['sourcePieces'][0]['sourceStartTick'],old['sourcePieces'][0]['sourceStartTick'])
            self.assertEqual(new['sourcePieces'][0]['sourceEndTick'],old['sourcePieces'][0]['sourceEndTick'])
            self.assertEqual(sum(x['newEndTick']-x['newStartTick'] for x in new['projectedSourcePieces']),sum(x['sourceEndTick']-x['sourceStartTick'] for x in old['sourcePieces']))
        self.assertTrue(all(item['speed']==1 and item['volume']==3 for item in spec['track']['items']))
    def test_variable_reviewed_handles_do_not_force_zero_or_fixed15_5(self):
        p=self.all_plan();row=p['reviewedPauses'][1];safe=row['safeRemoval'];safe.update(startFrame=39,startTick=1300000,leftPhoneticHandleTicks=200000,endFrame=51,endTick=1700000,rightPhoneticHandleTicks=300000)
        r=self.report(p);self.assertLessEqual(abs(r['pauses'][1]['afterAuditoryGapTicks']-500000),1);self.assertEqual(r['pauses'][1]['decision'],'REVIEWED_SAFE_QUIET_INTERIOR_REMOVED')
        self.assertIsNone(r['sentenceTailFrames']);self.assertEqual(r['quietEdits'][1]['insert'],None)
    def test_final_caption_tuple_cannot_be_mistaken_for_pacing_estimate(self):
        p=self.all_plan();p['reviewedFinalCaptionOnsets']=[{'id':'c1','startTick':0}]
        with self.assertRaisesRegex(ValueError,'cannot overwrite'):prepare_pacing(p)
    def test_end_fill_uses_estimated_next_start_without_advancing_it(self):
        r=self.report(self.all_plan());self.assertEqual(r['captionCues'][0]['endTick'],r['captionCues'][1]['startTick']);self.assertEqual(r['captionCues'][1]['startFrame'],r['words'][2]['startFrame'])
        self.assertEqual(r['captionOnsetStatus'],'FRAME_ESTIMATES_PENDING_FINAL_AUDIO_REVIEW');self.assertEqual(r['finalCaptionAnchorAcceptance'],'PENDING')
    def test_srt_only_or_sub_only_cannot_enter_default_recut(self):
        for field,value in (('outputMode','SRT_ONLY'),('workScope','SUB_ONLY')):
            p=self.all_plan();p[field]=value
            with self.assertRaisesRegex(ValueError,'CND content editing only'):prepare_pacing(p)
    def test_all_wrapper_keeps_six_typed_context_fields(self):
        p=self.all_plan();wrapper={'pacingPlan':p,'pacingScope':'ALL_PAUSES'};self.bind_nga(wrapper);r=self.report(pacing_input(wrapper))
        self.assertTrue(r['pacingStyleBinding']['applies']);self.assertEqual(r['afterDurationFrames'],88)
        wrapper['reviewedFinalCaptionOnsets']=None
        with self.assertRaisesRegex(ValueError,'cannot overwrite'):prepare_pacing(pacing_input(wrapper))
    def test_all_safe_interiors_use_actual_24_30_60_and_rational_clock(self):
        for num,den in ((24,1),(30,1),(60,1),(30000,1001)):
            self.plan=self.fixture(num,den);r=self.report(self.all_plan());removed=sum(n-2 for n in (9,27,6) if n*1000000*den//num>200000);expected=120-removed
            self.assertEqual(r['afterDurationFrames'],expected)
            self.assertEqual(r['afterDurationTicks'],expected*1000000*den//num)
            self.assertEqual((r['fpsNumerator'],r['fpsDenominator']),(num,den))
    def test_short_gap_with_no_whole_safe_frame_keeps_all_speech(self):
        p=self.all_plan();p['words'][0]['sourcePieces'][0]['sourceEndTick']=699999;p['reviewedPauses'].pop(0);r=self.report(p)
        self.assertEqual(r['pauses'][0]['decision'],'AT_OR_BELOW_200MS_UNCHANGED');self.assertEqual(r['pauses'][0]['afterAuditoryGapTicks'],1)


class FullBrollCoverageTests(unittest.TestCase):
    setUp=BrollTests.setUp
    placement=BrollTests.placement
    review_plan=BrollTests.review_plan
    def full(self):
        p=copy.deepcopy(self.plan);p['captionCues'][0]['startTick']=1000000;p['captionCues'][-1]['endTick']=19000000
        p.update(coverageMode='FULL_TIMELINE',sourcePresentationRole='VOICEOVER_READING',coverageReview={'reviewed':True,'evidenceRef':'synthetic-user-full-coverage-request','evidenceBasis':'USER_REPORTED','baseSnapshotSha256':p['baseSnapshot']['sha256'],'durationTicks':20000000,'firstCaptionId':'c0','lastCaptionId':'c9'})
        p['placements']=[self.placement('one','c0','c2',0,6000000),self.placement('two','c3','c5',6000000,12000000,6000000),self.placement('three','c6','c9',12000000,20000000,12000000)]
        # These older coverage geometry cases explicitly select retained conditional mode.
        p['sourceReuseMode']='REVIEWED_CONDITIONAL_REUSE'
        p['sourceReuseOverride']={'reviewed':True,'evidenceRef':'synthetic-explicit-conditional-coverage','evidenceBasis':'USER_REPORTED','authority':'explicit-user-request','mode':'REVIEWED_CONDITIONAL_REUSE','baseSnapshotSha256':p['baseSnapshot']['sha256'],'userQuote':'Synthetic fixture: allow multiple distinct windows for coverage geometry tests'}
        self.review_plan(p)
        return p
    def report(self,p):return json.loads(prepare_broll(p)['broll-report.json'])
    def test_full_bound_edges_cover_silent_outer_regions_and_preserve_base(self):
        p=self.full();old=copy.deepcopy(p);r=self.report(p);spec=json.loads(prepare_broll(p)['broll-spec.json'])
        self.assertTrue(r['fullTimelineCoveragePrepared']);self.assertEqual(r['coverageMode'],'FULL_TIMELINE');self.assertEqual(p,old)
        self.assertEqual([x['timelineStartEdgeExceptionApplied'] for x in r['placements']],[True,False,False]);self.assertEqual([x['timelineEndEdgeExceptionApplied'] for x in r['placements']],[False,False,True])
        self.assertEqual((spec['mainVideoOperations'],spec['mainAudioOperations'],spec['captionOperations']),([],[],[]));self.assertEqual(r['nativeAcceptance'],'PENDING')
    def test_full_reports_no_exception_when_outer_caption_edges_already_match(self):
        p=self.full();p['captionCues'][0]['startTick']=0;p['captionCues'][-1]['endTick']=20000000
        r=self.report(p);self.assertFalse(any(x['timelineStartEdgeExceptionApplied'] or x['timelineEndEdgeExceptionApplied'] for x in r['placements']))
    def test_sparse_default_retains_existing_uncovered_timeline(self):
        r=self.report(self.plan);self.assertEqual(r['coverageMode'],'SPARSE');self.assertFalse(r['fullTimelineCoveragePrepared']);self.assertEqual(len(r['placements']),1)
    def test_presentation_keyword_alone_never_selects_full_or_waives_edges(self):
        p=copy.deepcopy(self.plan);p['sourcePresentationRole']='VOICEOVER_READING';p['fullTimelineOuterPictureExceptions']={'firstStartAtZeroBeforeCaption':True}
        self.assertEqual(self.report(p)['coverageMode'],'SPARSE');p['placements'][0]['startTick']=0
        with self.assertRaisesRegex(ValueError,'exactly at caption'):prepare_broll(p)
    def test_full_requires_reviewed_role_and_truthful_evidence(self):
        for field,value in (('sourcePresentationRole','talking-head'),('coverageReview',None),('coverageReview',{'reviewed':False,'evidenceRef':'label-only'})):
            p=self.full();p[field]=value
            with self.assertRaisesRegex(ValueError,'reviewed voiceover-reading'):prepare_broll(p)
    def test_full_review_binds_current_base_duration_and_caption_ids(self):
        for field,value in (('baseSnapshotSha256','sha256:'+'0'*64),('durationTicks',19999999),('firstCaptionId','c1'),('lastCaptionId','c8')):
            p=self.full();p['coverageReview'][field]=value
            with self.assertRaisesRegex(ValueError,'exact current base'):prepare_broll(p)
    def test_full_missing_start_middle_or_end_is_rejected(self):
        for change in ('start','middle','end'):
            p=self.full()
            if change=='start':p['placements'][0].update(startTick=1000000)
            elif change=='middle':p['placements'][1].update(startTick=8000000,startCaptionId='c4')
            else:p['placements'][-1].update(endTick=19000000)
            with self.assertRaisesRegex(ValueError,'contiguous|exact bound timeline end'):prepare_broll(p)
    def test_edge_exception_never_applies_to_interior_or_wrong_cue(self):
        for change in ('interior','first-id','last-id'):
            p=self.full()
            if change=='interior':p['placements'][1]['startTick']=6000001
            elif change=='first-id':p['placements'][0]['startCaptionId']='c1'
            else:p['placements'][-1]['lastCaptionId']='c8'
            with self.assertRaisesRegex(ValueError,'exactly at caption'):prepare_broll(p)
    def test_full_outer_exception_does_not_waive_three_second_minimum(self):
        p=self.full();p['placements'][0].update(endTick=2000000,lastCaptionId='c0')
        with self.assertRaisesRegex(ValueError,'minimum three'):prepare_broll(p)
    def test_full_still_mutes_preserves_main_and_checks_source_handles(self):
        for field,value in (('muteSourceAudio',False),('preserveMainVideo',False),('sourceInTick',29000000)):
            p=self.full();p['placements'][0][field]=value
            with self.assertRaisesRegex(ValueError,'preserve main|actual source handles'):prepare_broll(p)
    def test_full_camera_no_voice_first5_last4_still_apply_every_excerpt(self):
        p=self.full();p['sources'][0]['voiceClassification']='NO_VOICE'
        with self.assertRaisesRegex(ValueError,'first five'):prepare_broll(p)
        for item in p['placements']:item['sourceInTick']+=5000000
        self.review_plan(p)
        r=self.report(p);self.assertTrue(all(item['sourceEdgeExclusionApplied'] for item in r['placements']))
        p['placements'][-1]['sourceInTick']=19000000
        with self.assertRaisesRegex(ValueError,'last four'):prepare_broll(p)
    def test_unknown_full_source_classification_still_requires_interview(self):
        p=self.full();p['sources'][0]['sourceOrigin']='UNKNOWN'
        with self.assertRaisesRegex(ValueError,'GATE0_SOURCE_CLASSIFICATION_REQUIRED'):prepare_broll(p)
    def test_full_keeps_actual_base_checkpoint_required(self):
        p=self.full();p['contentCaptionCheckpoint']='PENDING'
        with self.assertRaisesRegex(ValueError,'passed base checkpoint'):prepare_broll(p)
    def test_sparse_cannot_use_full_outer_exception_or_unknown_mode(self):
        p=self.full();p['coverageMode']='SPARSE'
        with self.assertRaisesRegex(ValueError,'exactly at caption'):prepare_broll(p)
        p['coverageMode']='full'
        with self.assertRaisesRegex(ValueError,'Known B-roll coverageMode'):prepare_broll(p)


class BrollReuseTests(unittest.TestCase):
    setUp=BrollTests.setUp
    placement=BrollTests.placement
    review_plan=BrollTests.review_plan
    def long(self):
        p=copy.deepcopy(self.plan);p['baseSnapshot']['durationTicks']=600000000
        p['captionCues']=[{'id':f'c{i}','startTick':i*2000000,'endTick':(i+1)*2000000} for i in range(300)]
        p['existingArollCuts']=[0,200000000,400000000]
        p['placements']=[self.placement('new','c92','c93',184000000,188000000)]
        p['sourceUsageReview']['existingPlacements']=[self.usage('prior',0,4000000,0,4000000)]
        p['sourceReuseMode']='REVIEWED_CONDITIONAL_REUSE'
        p['sourceReuseOverride']={'reviewed':True,'evidenceRef':'synthetic-explicit-conditional-reuse','evidenceBasis':'USER_REPORTED','authority':'explicit-user-request','mode':'REVIEWED_CONDITIONAL_REUSE','baseSnapshotSha256':p['baseSnapshot']['sha256'],'userQuote':'Synthetic fixture: allow the legacy conditional source reuse policy'}
        self.review_plan(p);return p
    def usage(self,id,a,b,x,y,source='b'):

        return {'id':id,'sourceId':source,'sourceInTick':a,'sourceOutTick':b,'startTick':x,'endTick':y}
    def eligible(self,p,windows,status='ELIGIBLE',source='b',placement=0):
        r=next(x for x in p['placements'][placement]['eligibleSourceReview']['sources'] if x['sourceId']==source)
        r.update(status=status,windows=[{'sourceInTick':a,'sourceOutTick':b} for a,b in windows],reason='Synthetic reviewed eligibility or exclusion; not semantic proof')
    def report(self,p):return json.loads(prepare_broll(p)['broll-report.json'])
    def reasons(self,p,id='new'):
        return next(x for x in self.report(p)['sourceUsageLedger'] if x['placementId']==id)['conflictReasons']
    def exhausted(self):
        p=self.long();self.eligible(p,[(0,4000000)]);return p
    def add_source(self,p,id,alias=False):
        s=copy.deepcopy(p['sources'][0]);path=Path(self.temp.name)/(id+'.mp4');path.write_bytes(Path(s['path']).read_bytes() if alias else ('different synthetic footage '+id).encode())
        s.update(id=id,path=str(path),sha256='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest());p['sources'].append(s);self.review_plan(p)
    def test_exact_180_seconds_end_to_start_allows_exhausted_reviewed_reuse(self):
        p=self.exhausted();old=copy.deepcopy(p);r=self.report(p);row=r['placements'][0]['sourceUsage']
        self.assertEqual(r['status'],'PREPARED_ONLY');self.assertEqual(row['cooldownTicks'],180000000);self.assertTrue(row['exhaustionMechanicallySupported']);self.assertEqual(p,old)
        self.assertEqual(r['nativeAcceptance'],'PENDING');self.assertFalse(r['sourceReusePolicy']['suppliedInventoryCompletenessAuthenticated'])
    def test_one_microsecond_below_180_seconds_is_held_without_overlay(self):
        p=self.exhausted();p['sourceUsageReview']['existingPlacements'][0].update(sourceOutTick=4000001,endTick=4000001)
        self.assertIn('SOURCE_REUSE_COOLDOWN_BELOW_180_SECONDS',self.reasons(p));self.assertEqual(json.loads(prepare_broll(p)['broll-spec.json'])['track']['items'],[])
    def test_start_to_start_180_seconds_does_not_satisfy_end_to_start_rule(self):
        p=self.exhausted();p['placements'][0].update(startCaptionId='c90',lastCaptionId='c91',startTick=180000000,endTick=184000000)
        self.assertIn('SOURCE_REUSE_COOLDOWN_BELOW_180_SECONDS',self.reasons(p))
    def test_wall_clock_wait_or_source_recording_clock_is_not_cooldown(self):
        p=self.exhausted();p['placements'][0].update(startCaptionId='c10',lastCaptionId='c11',startTick=20000000,endTick=24000000,wallClockWaitTicks=999999999,recordingTime=999999999)
        self.assertIn('SOURCE_REUSE_COOLDOWN_BELOW_180_SECONDS',self.reasons(p))
    def test_partial_source_overlap_counts_as_reuse(self):
        p=self.exhausted();p['placements'][0]['sourceInTick']=2000000;self.eligible(p,[(0,6000000)])
        row=self.report(p)['placements'][0]['sourceUsage'];self.assertTrue(row['sourceOverlapReuse']);self.assertEqual(row['overlappingPriorPlacementIds'],['prior']);self.assertEqual(row['status'],'PREPARED_ONLY')
    def test_equal_touching_source_intervals_are_not_reuse(self):
        p=self.long();p['placements'][0].update(sourceInTick=4000000,startCaptionId='c3',lastCaptionId='c4',startTick=6000000,endTick=10000000)
        row=self.report(p)['placements'][0]['sourceUsage'];self.assertFalse(row['sourceOverlapReuse']);self.assertIsNone(row['cooldownTicks']);self.assertEqual(row['status'],'PREPARED_ONLY')
    def test_one_tick_source_overlap_is_still_reuse(self):
        p=self.long();p['placements'][0].update(sourceInTick=3999999,startCaptionId='c3',lastCaptionId='c4',startTick=6000000,endTick=10000000)
        self.assertIn('SOURCE_REUSE_COOLDOWN_BELOW_180_SECONDS',self.reasons(p))
    def test_same_sha_alias_path_and_id_do_not_reset_usage(self):
        p=self.long();self.add_source(p,'alias',True);p['placements'][0].update(sourceId='alias',startCaptionId='c3',lastCaptionId='c4',startTick=6000000,endTick=10000000)
        for sid in ('b','alias'):self.eligible(p,[(0,4000000)],source=sid)
        r=self.report(p);self.assertIn('SOURCE_REUSE_COOLDOWN_BELOW_180_SECONDS',self.reasons(p));self.assertEqual(len({x['sourceIdentitySha256'] for x in r['sourceUsageLedger']}),1)
    def test_crop_transform_labels_cannot_reset_same_sha_source_lineage(self):
        p=self.exhausted();p['placements'][0].update(startCaptionId='c3',lastCaptionId='c4',startTick=6000000,endTick=10000000,crop={'scale':2},transformedSourceId='new-camera-angle')
        self.assertIn('SOURCE_REUSE_COOLDOWN_BELOW_180_SECONDS',self.reasons(p))
    def test_known_rendered_derivative_new_sha_cannot_be_declared_fresh(self):
        p=self.long();self.add_source(p,'rendered-crop');p['sources'][1]['derivedFromSourceId']='b';p['placements'][0]['sourceId']='rendered-crop'
        with self.assertRaisesRegex(ValueError,'different-SHA derivative lineage is HELD'):prepare_broll(p)
    def test_known_byte_identical_derivative_alias_still_shares_usage(self):
        p=self.long();self.add_source(p,'alias',True);p['sources'][1]['derivedFromSourceId']='b';p['placements'][0].update(sourceId='alias',startCaptionId='c3',lastCaptionId='c4',startTick=6000000,endTick=10000000)
        for sid in ('b','alias'):self.eligible(p,[(0,4000000)],source=sid)
        self.assertIn('SOURCE_REUSE_COOLDOWN_BELOW_180_SECONDS',self.reasons(p))
    def test_same_sha_alias_conflicting_duration_or_class_is_invalid(self):
        for field,value in (('actualDurationTicks',31000000),('sourceOrigin','AI')):
            p=self.long();self.add_source(p,'alias',True);p['sources'][1][field]=value
            with self.assertRaisesRegex(ValueError,'Same-SHA source aliases'):prepare_broll(p)
    def test_alias_eligibility_cannot_hide_an_unused_window(self):
        p=self.long();self.add_source(p,'alias',True);self.eligible(p,[(0,4000000)]);self.eligible(p,[],status='IRRELEVANT',source='alias')
        self.assertIn('SAME_SHA_ALIAS_ELIGIBILITY_CONFLICT',self.reasons(p))
    def test_maximum_end_of_all_overlapping_prior_occurrences_is_used(self):
        p=self.long();first=self.usage('first',0,4000000,0,4000000);second=self.usage('second',2000000,6000000,200000000,204000000)
        p['placements'][0].update(startCaptionId='c192',lastCaptionId='c193',startTick=384000000,endTick=388000000,sourceInTick=3000000)
        self.eligible(p,[(0,7000000)]);second['eligibleSourceReview']=copy.deepcopy(p['placements'][0]['eligibleSourceReview']);second['eligibleSourceReview']['sources'][0]['windows'][0]['sourceOutTick']=6000000
        p['sourceUsageReview']['existingPlacements']=[second,first]
        row=self.report(p)['placements'][0]['sourceUsage'];self.assertEqual(row['cooldownTicks'],180000000);self.assertEqual(set(row['overlappingPriorPlacementIds']),{'first','second'});self.assertEqual(row['status'],'PREPARED_ONLY')
    def test_later_nonoverlapping_source_use_does_not_reset_overlap_cooldown(self):
        p=self.exhausted();p['sourceUsageReview']['existingPlacements'].append(self.usage('other-window',10000000,14000000,160000000,164000000))
        self.eligible(p,[(0,4000000),(10000000,14000000)])
        row=self.report(p)['placements'][0]['sourceUsage'];self.assertEqual(row['cooldownTicks'],180000000);self.assertEqual(row['overlappingPriorPlacementIds'],['prior'])
    def test_any_unused_contiguous_three_seconds_rejects_exhaustion(self):
        p=self.long();self.eligible(p,[(0,7000000)])
        self.assertIn('UNUSED_ELIGIBLE_THREE_SECOND_WINDOW_AVAILABLE',self.reasons(p))
    def test_unused_window_one_tick_below_three_seconds_does_not_block_exhaustion(self):
        p=self.long();self.eligible(p,[(0,6999999)])
        row=self.report(p)['placements'][0]['sourceUsage'];self.assertTrue(row['exhaustionMechanicallySupported']);self.assertEqual(row['eligibleUnusedWindows'],[])
    def test_adjacent_reviewed_windows_merge_before_minimum_check(self):
        p=self.long();self.eligible(p,[(0,4000000),(4000000,5500000),(5500000,7000000)])
        self.assertIn('UNUSED_ELIGIBLE_THREE_SECOND_WINDOW_AVAILABLE',self.reasons(p))
    def test_used_intervals_are_union_subtracted_not_total_duration_subtracted(self):
        p=self.long();second=self.usage('second',2000000,6000000,200000000,204000000);p['placements'][0].update(startCaptionId='c200',lastCaptionId='c201',startTick=400000000,endTick=404000000)
        self.eligible(p,[(0,9000000)]);second['eligibleSourceReview']=copy.deepcopy(p['placements'][0]['eligibleSourceReview']);second['eligibleSourceReview']['sources'][0]['windows'][0]['sourceOutTick']=6000000;p['sourceUsageReview']['existingPlacements'].append(second)
        self.assertIn('UNUSED_ELIGIBLE_THREE_SECOND_WINDOW_AVAILABLE',self.reasons(p))
    def test_boolean_exhausted_alone_never_authorizes_reuse(self):
        p=self.long();p['placements'][0]['eligibleSourceReview']={'exhausted':True,'reviewed':True,'evidenceRef':'keyword-only'}
        self.assertIn('EXHAUSTIVE_ELIGIBLE_SOURCE_WINDOW_REVIEW_REQUIRED',self.reasons(p))
    def test_future_reservations_do_not_subtract_unused_eligible_material(self):
        p=self.long();p['placements'][0]['eligibleSourceReview']['futureReservedWindows']=[{'sourceId':'b','sourceInTick':4000000,'sourceOutTick':30000000}]
        self.assertIn('UNUSED_ELIGIBLE_THREE_SECOND_WINDOW_AVAILABLE',self.reasons(p))
    def test_unused_source_is_preferred_to_nonoverlapping_excerpt_of_seen_source(self):
        p=self.long();self.add_source(p,'fresh');p['placements'][0]['sourceInTick']=10000000
        self.assertIn('WHOLLY_FRESH_ELIGIBLE_SOURCE_PREFERRED',self.reasons(p))
    def test_reviewed_irrelevant_fresh_source_does_not_force_bad_imagery(self):
        p=self.long();self.add_source(p,'fresh');p['placements'][0]['sourceInTick']=10000000;self.eligible(p,[],status='IRRELEVANT',source='fresh')
        self.assertEqual(self.report(p)['placements'][0]['sourceUsage']['status'],'PREPARED_ONLY')
    def test_reviewed_unavailable_source_is_explicitly_excluded(self):
        p=self.long();self.add_source(p,'fresh');self.eligible(p,[(0,4000000)]);self.eligible(p,[],status='UNAVAILABLE',source='fresh')
        self.assertTrue(self.report(p)['placements'][0]['sourceUsage']['exhaustionMechanicallySupported'])
    def test_unknown_eligibility_holds_slot_without_guessing_exhaustion(self):
        p=self.long();self.add_source(p,'fresh');self.eligible(p,[(0,4000000)]);self.eligible(p,[],status='UNKNOWN',source='fresh')
        self.assertIn('UNKNOWN_SOURCE_ELIGIBILITY_HELD',self.reasons(p));self.assertEqual(json.loads(prepare_broll(p)['broll-spec.json'])['track']['items'],[])
    def test_every_supplied_source_needs_eligible_window_or_exclusion_row(self):
        p=self.long();self.add_source(p,'fresh');p['placements'][0]['eligibleSourceReview']['sources'].pop()
        self.assertIn('EXHAUSTIVE_REVIEW_MUST_COVER_EVERY_SUPPLIED_SOURCE',self.reasons(p))
    def test_duplicate_or_unknown_eligible_source_row_is_invalid(self):
        for change in ('duplicate','unknown'):
            p=self.exhausted();row=copy.deepcopy(p['placements'][0]['eligibleSourceReview']['sources'][0])
            if change=='unknown':row['sourceId']='not-supplied'
            p['placements'][0]['eligibleSourceReview']['sources'].append(row)
            with self.assertRaisesRegex(ValueError,'each known supplied source exactly once'):prepare_broll(p)
    def test_missing_exclusion_evidence_or_reason_holds_slot(self):
        for field in ('evidenceRef','reason'):
            p=self.long();self.add_source(p,'fresh');self.eligible(p,[],status='IRRELEVANT',source='fresh');p['placements'][0]['eligibleSourceReview']['sources'][1][field]=None
            self.assertIn('ELIGIBILITY_OR_EXCLUSION_EVIDENCE_REQUIRED',self.reasons(p))
    def test_unreviewed_or_stale_exhaustion_review_is_held(self):
        for field,value in (('reviewed',False),('exhaustive',False),('evidenceBasis','ASSUMED'),('baseSnapshotSha256','sha256:'+'0'*64)):
            p=self.exhausted();p['placements'][0]['eligibleSourceReview'][field]=value
            self.assertIn('EXHAUSTIVE_ELIGIBLE_SOURCE_WINDOW_REVIEW_REQUIRED',self.reasons(p))
    def test_selected_excerpt_must_be_inside_reviewed_eligible_window(self):
        p=self.exhausted();self.eligible(p,[(10000000,14000000)])
        self.assertIn('SELECTED_EXCERPT_NOT_IN_REVIEWED_ELIGIBLE_WINDOW',self.reasons(p))
    def test_eligible_windows_cannot_waive_camera_head_or_tail(self):
        p=self.long();p['sources'][0]['voiceClassification']='NO_VOICE';p['sourceUsageReview']['existingPlacements']=[];p['placements'][0]['sourceInTick']=5000000
        with self.assertRaisesRegex(ValueError,'conditional five/four'):prepare_broll(p)
    def test_eligible_windows_cannot_exceed_actual_source_duration(self):
        p=self.exhausted();self.eligible(p,[(0,30000001)])
        with self.assertRaisesRegex(ValueError,'actual source bounds'):prepare_broll(p)
    def test_reviewed_full_current_baseline_inventory_is_required_even_first_use(self):
        for field,value in (('reviewed',False),('scope','NEW_PLACEMENTS_ONLY'),('baseSnapshotSha256','sha256:'+'0'*64),('existingPlacements',None)):
            p=copy.deepcopy(self.plan);p['sourceUsageReview'][field]=value
            with self.assertRaisesRegex(ValueError,'Whole current timeline sourceUsageReview'):prepare_broll(p)
        p=copy.deepcopy(self.plan);p.pop('sourceUsageReview')
        with self.assertRaisesRegex(ValueError,'Whole current timeline sourceUsageReview'):prepare_broll(p)
    def test_exact_same_existing_id_and_bounds_is_counted_once(self):
        p=copy.deepcopy(self.plan);p['sourceUsageReview']['existingPlacements']=[self.usage('one',0,4000000,2000000,6000000)]
        r=self.report(p);self.assertEqual(len(r['sourceUsageLedger']),1);self.assertTrue(r['sourceUsageLedger'][0]['existingInBase']);self.assertFalse(r['sourceUsageLedger'][0]['sourceOverlapReuse'])
    def test_existing_same_id_changed_bounds_is_not_silently_rebased(self):
        p=copy.deepcopy(self.plan);p['sourceUsageReview']['existingPlacements']=[self.usage('one',1000000,5000000,2000000,6000000)]
        with self.assertRaisesRegex(ValueError,'Existing placement ID/ranges changed'):prepare_broll(p)
    def reconcile(self,old_ids,new_ids):
        return {'existingPlacementIds':old_ids,'plannedPlacementIds':new_ids,'reviewed':True,'evidenceRef':'synthetic-reviewed-reanchor-after-content-recut','evidenceBasis':'USER_REPORTED','reason':'Proposed caption reanchor/repartition only; no native mutation authority'}
    def test_reviewed_after_recut_reanchor_does_not_count_old_and_new_twice(self):
        p=FullBrollCoverageTests.full(self);p['sourceUsageReview']['existingPlacements']=[self.usage('one',0,6000000,1000000,7000000),self.usage('two',6000000,12000000,7000000,13000000),self.usage('three',12000000,19000000,13000000,20000000)]
        p['sourceUsageReview']['reconciliations']=[self.reconcile(['one','two','three'],['one','two','three'])]
        r=self.report(p);spec=json.loads(prepare_broll(p)['broll-spec.json']);self.assertEqual(len(r['sourceUsageLedger']),3);self.assertTrue(r['fullTimelineCoveragePrepared']);self.assertFalse(any(x['sourceOverlapReuse'] for x in r['sourceUsageLedger']));self.assertEqual(spec['nativeReplacementOperations'],[])
        self.assertEqual(spec['reviewedProposedPlacementReconciliations'],p['sourceUsageReview']['reconciliations'])
    def test_reviewed_many_to_one_repartition_is_prepared_without_delete_operations(self):
        p=copy.deepcopy(self.plan);p['sourceUsageReview']['existingPlacements']=[self.usage('old-a',0,3000000,0,3000000),self.usage('old-b',3000000,6000000,3000000,6000000)];p['sourceUsageReview']['reconciliations']=[self.reconcile(['old-a','old-b'],['one'])]
        r=self.report(p);self.assertEqual(len(r['sourceUsageLedger']),1);self.assertEqual(r['placements'][0]['sourceUsage']['reconciledExistingPlacementIds'],['old-a','old-b']);self.assertEqual(r['status'],'PREPARED_ONLY')
    def test_reconciliation_needs_explicit_review_and_actual_evidence(self):
        for field,value in (('reviewed',False),('evidenceRef',None),('evidenceBasis','ASSUMED'),('reason','')):
            p=copy.deepcopy(self.plan);p['sourceUsageReview']['existingPlacements']=[self.usage('one',1000000,5000000,2000000,6000000)];r=self.reconcile(['one'],['one']);r[field]=value;p['sourceUsageReview']['reconciliations']=[r]
            with self.assertRaisesRegex(ValueError,'Explicit reviewed base-bound'):prepare_broll(p)
    def test_reconciliation_rejects_unknown_duplicate_or_ambiguous_group_ids(self):
        for rows in ([self.reconcile(['missing'],['one'])],[self.reconcile(['one'],['missing'])],[self.reconcile(['one','one'],['one'])],[self.reconcile(['one'],['one']),self.reconcile(['one'],['one'])]):
            p=copy.deepcopy(self.plan);p['sourceUsageReview']['existingPlacements']=[self.usage('one',1000000,5000000,2000000,6000000)];p['sourceUsageReview']['reconciliations']=rows
            with self.assertRaisesRegex(ValueError,'known, unique and disjoint'):prepare_broll(p)
    def test_reconciliation_cannot_be_delete_only_or_hide_stale_outer_geometry(self):
        p=copy.deepcopy(self.plan);p['sourceUsageReview']['existingPlacements']=[self.usage('one',0,4000000,19000000,23000000)];p['sourceUsageReview']['reconciliations']=[self.reconcile(['one'],['one'])]
        with self.assertRaisesRegex(ValueError,'positive source/target bounds'):prepare_broll(p)
        p['sourceUsageReview']['existingPlacements'][0].update(startTick=2000000,endTick=6000000);p['sourceUsageReview']['reconciliations'][0]['plannedPlacementIds']=[]
        with self.assertRaisesRegex(ValueError,'nonempty old/planned IDs'):prepare_broll(p)
    def test_new_earlier_usage_is_checked_against_unchanged_later_clip(self):
        p=self.long();p['sourceUsageReview']['existingPlacements']=[self.usage('later',0,4000000,184000000,188000000)];p['placements']=[self.placement('new','c0','c2',0,6000000)];self.review_plan(p)
        r=self.report(p);row=next(x for x in r['sourceUsageLedger'] if x['placementId']=='later');self.assertIn('SOURCE_REUSE_COOLDOWN_BELOW_180_SECONDS',row['conflictReasons']);self.assertTrue(row['influencedByNewPriorPlacement']);self.assertEqual(r['status'],'PARTIAL_PREPARED_REVIEW_REQUIRED');self.assertEqual(json.loads(prepare_broll(p)['broll-spec.json'])['track']['items'],[])
    def test_existing_baseline_violation_is_held_not_retroactively_certified(self):
        p=self.long();p['sourceUsageReview']['existingPlacements'].append(self.usage('old-violation',0,4000000,20000000,24000000))
        r=self.report(p);self.assertFalse(r['providedWholeTimelineUsageMechanicallyConflictFree']);self.assertEqual(next(x for x in r['sourceUsageLedger'] if x['placementId']=='prior')['status'],'BASELINE_RECORDED_NOT_RETRO_CERTIFIED')
    def test_combined_usage_cannot_hide_overlapping_existing_target_clip(self):
        p=copy.deepcopy(self.plan);p['sourceUsageReview']['existingPlacements']=[self.usage('hidden',10000000,14000000,4000000,8000000)]
        with self.assertRaisesRegex(ValueError,'Combined whole-timeline B-roll usage overlaps'):prepare_broll(p)
    def test_existing_inventory_requires_unique_known_ids_and_normal_speed_bounds(self):
        for row in (self.usage('bad',0,4000000,0,5000000),self.usage('bad',0,4000000,0,4000000,source='unknown')):
            p=self.long();p['sourceUsageReview']['existingPlacements'].append(row)
            with self.assertRaises(ValueError):prepare_broll(p)
    def test_recut_invalidates_inventory_review_even_when_captions_are_retimed(self):
        p=self.exhausted();path=Path(p['baseSnapshot']['path']);path.write_bytes(b'new synthetic native cut');p['baseSnapshot']['sha256']='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'current base hash'):prepare_broll(p)
    def test_generated_ledger_is_chronological_and_does_not_mutate_input(self):
        p=self.long();p['sourceUsageReview']['existingPlacements'].append(self.usage('earlier-unused-window',10000000,14000000,160000000,164000000));old=copy.deepcopy(p);r=self.report(p)
        self.assertEqual([u['placementId'] for u in r['sourceUsageLedger']],['prior','earlier-unused-window','new']);self.assertEqual(p,old);self.assertEqual(r['sourceReusePolicy']['cooldownTicks'],180000000)
    def test_full_coverage_unknown_reuse_cannot_claim_covered_prepared_output(self):
        p=FullBrollCoverageTests.full(self);p['placements'][1]['sourceInTick']=0
        r=self.report(p);self.assertFalse(r['fullTimelineCoveragePrepared']);self.assertEqual(r['status'],'PARTIAL_PREPARED_REVIEW_REQUIRED');self.assertEqual(r['wholeTimelineReuseNativeAcceptance'],'PENDING')
    def test_cli_reports_held_arithmetic_instead_of_prepared_only_success_claim(self):
        import subprocess,sys
        p=self.long();root=Path(self.temp.name);path=root/'reuse.json';path.write_text(json.dumps({'bRollPlan':p}),encoding='utf-8');out=root/'reuse-out'
        q=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('prepare_cut.py')),'--mode','broll','--plan',str(path),'--out-dir',str(out)],capture_output=True,text=True)
        self.assertEqual(q.returncode,0,q.stdout+q.stderr);self.assertEqual(json.loads(q.stdout)['status'],'PARTIAL_PREPARED_REVIEW_REQUIRED');self.assertEqual(json.loads((out/'broll-spec.json').read_text())['track']['items'],[])


class ScriptModeTests(unittest.TestCase):
    setUp=TimingTests.setUp
    def reference(self):
        p=copy.deepcopy(self.plan);p['script']={'mode':'REFERENCE_ONLY','evidenceRef':'synthetic-user-image-is-reference'}
        for unit in p['units']:unit.update(spokenText=unit['scriptText'],scriptText='Mua nhà đứng tên vợ?',reviewed=True,evidenceRef='synthetic-reviewed-actual-spoken-unit')
        return p
    def test_reference_uses_actual_spoken_units_without_false_exact_reference_claim(self):
        p=self.reference();old=copy.deepcopy(p);r=json.loads(prepare(p)['selection-report.json'])
        self.assertEqual(r['scriptMode'],'REFERENCE_ONLY');self.assertFalse(r['referenceScriptCoverageClaimed']);self.assertEqual([x['takeId'] for x in r['units']],['last-good','second']);self.assertEqual(p,old)
    def test_missing_script_role_defaults_to_reviewed_actual_speech(self):
        p=self.reference();p.pop('script');old=copy.deepcopy(p)
        r=json.loads(prepare(p)['selection-report.json'])
        self.assertEqual(r['scriptMode'],'REFERENCE_ONLY')
        self.assertEqual(r['scriptModeEvidenceRef'],'capcut-default-script-reference-only')
        self.assertFalse(r['referenceScriptCoverageClaimed']);self.assertEqual(p,old)
    def test_default_reference_still_requires_reviewed_actual_words(self):
        p=self.reference();p.pop('script');p['units'][0]['reviewed']=False
        with self.assertRaisesRegex(ValueError,'actual spoken-content review'):prepare(p)
        p=self.reference();p.pop('script');p['units'][0]['spokenText']='Nga nói sai.'
        with self.assertRaisesRegex(ValueError,'differ from reviewed spoken unit'):prepare(p)
    def test_explicit_exact_preserves_raw_script_contract(self):
        p=copy.deepcopy(self.plan);p['script']={'mode':'EXACT_CONTENT','evidenceRef':'synthetic-user-exact-script'}
        self.assertTrue(json.loads(prepare(p)['selection-report.json'])['referenceScriptCoverageClaimed'])
        p['units'][0]['scriptText']='Sai lời'
        with self.assertRaisesRegex(ValueError,'differ from exact script'):prepare(p)
    def test_reference_spoken_units_cannot_drop_rewrite_or_be_unreviewed(self):
        for field,value in (('spokenText','Nga nói'),('reviewed',False),('evidenceRef','')):
            p=self.reference();p['units'][0][field]=value
            with self.assertRaisesRegex(ValueError,'review evidence|reviewed spoken unit'):prepare(p)
    def test_reference_missing_spoken_text_is_not_inferred_from_reference(self):
        p=self.reference();p['units'][0].pop('spokenText')
        with self.assertRaisesRegex(ValueError,'actual spoken unit text'):prepare(p)
    def test_unknown_or_unbound_script_mode_is_rejected(self):
        for value in ({'mode':'REFERENCE_ONLY'}, {'mode':'REFERENCE_ONLY','evidenceRef':' '}, {'mode':'GUESS','evidenceRef':'synthetic'}, 'REFERENCE_ONLY'):
            p=copy.deepcopy(self.plan);p['script']=value
            with self.assertRaisesRegex(ValueError,'script mode'):prepare(p)
    def test_reference_keyword_alone_cannot_relax_exact_script_contract(self):
        p=copy.deepcopy(self.plan);p['instructions']='REFERENCE_ONLY';p['units'][0]['scriptText']='Sai lời'
        with self.assertRaisesRegex(ValueError,'differ from exact script'):prepare(p)


class QuietThresholdBoundaryTests(unittest.TestCase):
    """Strict raw200ms detection, separate outer review, no heard/native claim."""
    setUp=PacingTests.setUp
    fixture=PacingTests.fixture
    select_scope=PacingTests.select_scope
    all_plan=PacingTests.all_plan
    report=PacingTests.report
    def outer_plan(self,head=400000,tail=400000,num=30,den=1):
        self.plan=self.fixture(num,den);p=self.all_plan()
        us=lambda f:f*1000000*den//num
        floor=lambda t:((t+1)*num+1000000*den-1)//(1000000*den)-1
        ceil=lambda t:floor(t) if us(floor(t))==t else floor(t)+1
        endframe=ceil(6000000);end=us(endframe)
        p['clips'][0].update(endFrame=endframe,sourceOutTick=end)
        for w in p['words']:
            z=w['sourcePieces'][0];z['sourceStartTick']+=head;z['sourceEndTick']+=head
        p['words'][-1]['sourcePieces'][0]['sourceEndTick']=end-tail
        p['reviewedCaptionOuterBounds'].update(firstOnsetFrame=floor(head),lastEndFrame=ceil(end-tail))
        for row,left,right in zip(p['reviewedPauses'],p['words'],p['words'][1:]):
            leftend=left['sourcePieces'][-1]['sourceEndTick'];rightstart=right['sourcePieces'][0]['sourceStartTick'];a,b=ceil(leftend),floor(rightstart)
            row.update(oldStartFrame=a,oldEndFrame=b,oldStartTick=us(a),oldEndTick=us(b))
            row['safeRemoval'].update(startFrame=a+1,endFrame=b-1,startTick=us(a+1),endTick=us(b-1),leftPhoneticHandleTicks=us(a+1)-leftend,rightPhoneticHandleTicks=rightstart-us(b-1))
        p['pauseCriterion']={'minimumQuietDurationTicks':200000,'comparison':'STRICTLY_GREATER','auditScopes':['HEAD','INTERNAL','TAIL']}
        p['reviewedBoundaryPauses']=[]
        for kind,word,rawa,rawb in [('head-quiet',p['words'][0],0,head),('tail-quiet',p['words'][-1],end-tail,end)]:
            a,b=ceil(rawa),floor(rawb);x,y=(a,b-1) if kind=='head-quiet' else (a+1,b)
            p['reviewedBoundaryPauses'].append({'kind':kind,'clipId':'base','sourceId':'s','nearestWordId':word['id'],'oldStartFrame':a,'oldEndFrame':b,'oldStartTick':us(a),'oldEndTick':us(b),'sourceStartTick':us(a),'sourceEndTick':us(b),'reviewed':True,'reviewBasis':'audio-speech-boundary-review','noSpeechOrPrompter':True,'joinEvidenceRef':'synthetic-outer-source-join','evidenceRef':'synthetic-outer-audio-review','safeRemoval':{'startFrame':x,'endFrame':y,'startTick':us(x),'endTick':us(y),'leftPhoneticHandleTicks':us(x)-rawa,'rightPhoneticHandleTicks':rawb-us(y),'reviewed':True,'reviewBasis':'audio-speech-boundary-review','evidenceRef':'synthetic-reviewed-outer-handles'}})
        return p
    def test_full_head_internal_tail_inventory_and_positive_speech_handles(self):
        p=self.outer_plan();before=copy.deepcopy(p);r=self.report(p)
        self.assertEqual(r['status'],'PREPARED_ONLY');self.assertEqual(p,before)
        self.assertEqual([q['pauseRegion'] for q in r['boundaryPauses']],['HEAD','TAIL'])
        self.assertTrue(all(q['changed'] for q in r['boundaryPauses']));self.assertTrue(r['allEligibleQuietPrepared'])
        self.assertEqual(len(r['quietEdits']),4);self.assertEqual(r['boundaryPauses'][0]['retainedLeftPhoneticHandleTicks'],0);self.assertEqual(r['boundaryPauses'][1]['retainedRightPhoneticHandleTicks'],0)
        self.assertGreater(r['boundaryPauses'][0]['afterAuditoryGapTicks'],0);self.assertGreater(r['boundaryPauses'][1]['afterAuditoryGapTicks'],0)
    def test_exact200ms_and_below_head_stay_unchanged_even_with_review(self):
        for gap in (199999,200000):
            p=self.outer_plan(head=gap);r=self.report(p);q=r['boundaryPauses'][0]
            self.assertEqual(q['decision'],'AT_OR_BELOW_200MS_UNCHANGED');self.assertFalse(q['changed']);self.assertFalse(q['overDetectionThreshold']);self.assertEqual(q['beforeAuditoryGapTicks'],q['afterAuditoryGapTicks'])
    def test_exact200ms_and_below_tail_stay_unchanged_even_with_review(self):
        for gap in (199999,200000):
            q=self.report(self.outer_plan(tail=gap))['boundaryPauses'][1]
            self.assertFalse(q['changed']);self.assertEqual(q['decision'],'AT_OR_BELOW_200MS_UNCHANGED');self.assertEqual(q['rawQuietDurationTicks'],gap)
    def test_one_microsecond_over_threshold_head_is_eligible_before_frame_containment(self):
        q=self.report(self.outer_plan(head=200001))['boundaryPauses'][0]
        self.assertTrue(q['changed']);self.assertEqual(q['rawQuietDurationTicks'],200001);self.assertEqual(q['beforeWholeQuietFrames'],6);self.assertLess(q['afterAuditoryGapTicks'],200000)
    def test_one_microsecond_over_threshold_tail_is_eligible_before_frame_containment(self):
        q=self.report(self.outer_plan(tail=200001))['boundaryPauses'][1]
        self.assertTrue(q['changed']);self.assertEqual(q['rawQuietDurationTicks'],200001);self.assertLess(q['beforeTicks'],q['rawQuietDurationTicks'])
    def test_internal_exact200ms_is_not_cut_or_legacy_capped(self):
        r=self.report(self.all_plan());q=r['pauses'][-1]
        self.assertEqual(q['beforeAuditoryGapTicks'],200000);self.assertEqual(q['afterAuditoryGapTicks'],200000);self.assertFalse(q['changed'])
    def test_internal200001_with_fractional_margin_is_cut(self):
        p=self.all_plan();p['words'][-1]['sourcePieces'][0]['sourceStartTick']+=1;p['reviewedPauses'][-1]['safeRemoval']['rightPhoneticHandleTicks']+=1
        q=self.report(p)['pauses'][-1];self.assertTrue(q['changed']);self.assertEqual(q['rawQuietDurationTicks'],200001)
    def test_raw200001_with_only_five_contained_frames_is_still_eligible(self):
        p=self.all_plan();p['words'][0]['sourcePieces'][0]['sourceEndTick']=410001;p['words'][1]['sourcePieces'][0]['sourceStartTick']=610002;q=p['reviewedPauses'][0]
        q.update(oldStartFrame=13,oldEndFrame=18,oldStartTick=433333,oldEndTick=600000);q['safeRemoval'].update(startFrame=14,endFrame=17,startTick=466666,endTick=566666,leftPhoneticHandleTicks=56665,rightPhoneticHandleTicks=43336)
        r=self.report(p)['pauses'][0];self.assertTrue(r['changed']);self.assertEqual(r['rawQuietDurationTicks'],200001);self.assertEqual(r['beforeWholeQuietFrames'],5);self.assertEqual(r['afterAuditoryGapTicks'],100001)
    def test_criterion_is_detection_not200ms_retention_or_zero_target(self):
        r=self.report(self.outer_plan());self.assertEqual(r['pauseCriterion']['comparison'],'STRICTLY_GREATER')
        for q in r['boundaryPauses']:self.assertTrue(0<q['afterAuditoryGapTicks']<200000)
        self.assertIsNone(r['sentenceTailFrames']);self.assertIsNone(r['intraSentenceBreathCapFrames'])
    def test_missing_head_review_holds_only_head_with_specific_diagnosis(self):
        p=self.outer_plan();p['reviewedBoundaryPauses'].pop(0);r=self.report(p)
        self.assertEqual(r['status'],'PARTIAL_PREPARED_REVIEW_REQUIRED');self.assertFalse(r['allEligibleQuietPrepared']);self.assertFalse(r['boundaryPauses'][0]['changed']);self.assertTrue(r['boundaryPauses'][1]['changed'])
        self.assertTrue(any(q.get('status')=='BOUNDARY_QUIET_REVIEW_REQUIRED' for q in r['nativeRepresentationConflicts']))
    def test_missing_tail_review_is_not_hidden_by_clean_internal_cuts(self):
        p=self.outer_plan();p['reviewedBoundaryPauses'].pop();r=self.report(p)
        self.assertFalse(r['boundaryPauses'][1]['changed']);self.assertEqual(r['status'],'PARTIAL_PREPARED_REVIEW_REQUIRED');self.assertTrue(any(q['changed'] for q in r['pauses']))
    def test_energy_asr_unknown_or_missing_join_never_authenticates_outer_quiet(self):
        for change in ('energy','asr','unknown','join','safe'):
            p=self.outer_plan();q=p['reviewedBoundaryPauses'][0]
            if change=='energy':q['reviewBasis']='amplitude-only'
            elif change=='asr':q['safeRemoval']['reviewBasis']='asr-word-gap'
            elif change=='unknown':q['noSpeechOrPrompter']=None
            elif change=='join':q.pop('joinEvidenceRef')
            else:q['safeRemoval']['reviewed']=False
            r=self.report(p);self.assertFalse(r['boundaryPauses'][0]['changed']);self.assertEqual(r['status'],'PARTIAL_PREPARED_REVIEW_REQUIRED')
    def test_boundary_nearest_word_and_no_fake_pair_are_required(self):
        for field,value in [('nearestWordId','b'),('previousWordId','a'),('nextWordId','a')]:
            p=self.outer_plan();p['reviewedBoundaryPauses'][0][field]=value
            with self.assertRaisesRegex(ValueError,'nearest|fake'):prepare_pacing(p)
    def test_boundary_exact_native_and_source_translation_required(self):
        for field,value in [('sourceStartTick',1),('sourceEndTick',399999),('oldStartTick',1),('oldEndFrame',13),('clipId','wrong'),('sourceId','wrong')]:
            p=self.outer_plan();p['reviewedBoundaryPauses'][0][field]=value
            with self.assertRaisesRegex(ValueError,'Boundary quiet'):prepare_pacing(p)
    def test_duplicate_or_invalid_boundary_kind_rejected(self):
        p=self.outer_plan();p['reviewedBoundaryPauses'].append(copy.deepcopy(p['reviewedBoundaryPauses'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate boundary'):prepare_pacing(p)
        for value in (None,{},[{'kind':'sentence-boundary'}]):
            p=self.outer_plan();p['reviewedBoundaryPauses']=value
            with self.assertRaisesRegex(ValueError,'Boundary|boundary'):prepare_pacing(p)
    def test_head_cannot_remove_speech_facing_handle(self):
        p=self.outer_plan();q=p['reviewedBoundaryPauses'][0];q['safeRemoval'].update(endFrame=12,endTick=400000,rightPhoneticHandleTicks=0)
        with self.assertRaisesRegex(ValueError,'positive against speech'):prepare_pacing(p)
    def test_tail_cannot_remove_speech_facing_handle(self):
        p=self.outer_plan();q=p['reviewedBoundaryPauses'][1];q['safeRemoval'].update(startFrame=168,startTick=5600000,leftPhoneticHandleTicks=0)
        with self.assertRaisesRegex(ValueError,'positive against speech'):prepare_pacing(p)
    def test_boundary_safe_removal_cannot_extend_or_falsify_margin(self):
        for field,value in [('startFrame',13),('endFrame',13),('endTick',366665),('rightPhoneticHandleTicks',1)]:
            p=self.outer_plan();p['reviewedBoundaryPauses'][0]['safeRemoval'][field]=value
            with self.assertRaisesRegex(ValueError,'Boundary safe|phonetic handle'):prepare_pacing(p)
    def test_known_soft_speech_or_prompter_blocks_head_and_tail_cut(self):
        for start,end in [(10000,20000),(5800000,5810000)]:
            p=self.outer_plan();p['knownSpeechOrPrompterIntervals']=[{'sourceId':'s','startTick':start,'endTick':end,'role':'prompter','reviewed':True,'evidenceRef':'synthetic-quiet-is-not-soft-speech'}]
            with self.assertRaisesRegex(ValueError,'removal intersects known source speech'):prepare_pacing(p)
    def test_all_raw_word_source_pieces_order_volume_and_duration_survive_outer_cuts(self):
        p=self.outer_plan();r=self.report(p);spec=json.loads(prepare_pacing(p)['pacing-spec.json'])
        self.assertEqual([w['id'] for w in r['words']],[w['id'] for w in p['words']]);self.assertFalse(spec['applyEligible'])
        for a,b in zip(p['words'],r['words']):self.assertEqual(sum(x['sourceEndTick']-x['sourceStartTick'] for x in a['sourcePieces']),sum(x['newEndTick']-x['newStartTick'] for x in b['projectedSourcePieces']))
        self.assertTrue(all(i['volume']==3 and i['speed']==1 and 0<=i['sourceInTick']<i['sourceOutTick']<=6000000 for i in spec['track']['items']))
    def test_caption_clock_is_fresh_provisional_then_END_only_and_old_locks_retained(self):
        p=self.outer_plan();r=self.report(p)
        self.assertEqual([q['wordIds'] for q in r['captionCues']],[q['wordIds'] for q in p['captionCues']]);self.assertEqual(r['captionCues'][0]['endTick'],r['captionCues'][1]['startTick'])
        self.assertEqual(r['captionOnsetStatus'],'FRAME_ESTIMATES_PENDING_FINAL_AUDIO_REVIEW');self.assertEqual(r['finalCaptionAnchorAcceptance'],'PENDING');self.assertTrue(r['captionStartsUnchangedByEndFill'])
    def test_reviewed_caption_outer_bound_inside_cut_holds_that_boundary(self):
        p=self.outer_plan();p['reviewedCaptionOuterBounds']['firstOnsetFrame']=5;r=self.report(p)
        self.assertFalse(r['boundaryPauses'][0]['changed']);self.assertTrue(r['boundaryPauses'][1]['changed']);self.assertTrue(any(q['status']=='REVIEWED_CAPTION_OUTER_BOUNDARY_CONFLICT' for q in r['nativeRepresentationConflicts']))
    def test_zero_outer_quiet_needs_no_fake_review(self):
        p=self.outer_plan(head=0,tail=0);p['reviewedBoundaryPauses']=[];r=self.report(p)
        self.assertEqual(r['status'],'PREPARED_ONLY');self.assertTrue(all(q['rawQuietDurationTicks']==0 and not q['changed'] for q in r['boundaryPauses']))
    def test_source_identity_bounds_and_actual_duration_still_hold(self):
        p=self.outer_plan();p['sources'][0]['actualDurationTicks']=5900000
        with self.assertRaisesRegex(ValueError,'bounded normal-speed'):prepare_pacing(p)
        p=self.outer_plan();p['sources'][0]['sha256']='sha256:'+'0'*64
        with self.assertRaisesRegex(ValueError,'source identity'):prepare_pacing(p)
    def test_boundary_inventory_cannot_be_used_to_recut_legacy_scope(self):
        p=self.outer_plan();self.select_scope(p,'INTER_SENTENCE_ONLY')
        with self.assertRaisesRegex(ValueError,'HEAD/TAIL removal'):prepare_pacing(p)
    def test_head_quiet_crossing_baseline_pieces_is_held_without_inventing_source_join(self):
        p=self.outer_plan();p['clips']=[dict(p['clips'][0],id='head-part',endFrame=6,sourceOutTick=200000),dict(p['clips'][0],id='speech-part',startFrame=6,sourceInTick=200000)]
        for w in p['words']:w['sourcePieces'][0]['clipId']='speech-part'
        p['reviewedBoundaryPauses'].pop(0);p['reviewedBoundaryPauses'][0]['clipId']='speech-part';r=self.report(p)
        self.assertEqual(r['status'],'PARTIAL_PREPARED_REVIEW_REQUIRED');self.assertFalse(r['boundaryPauses'][0]['changed']);self.assertTrue(r['boundaryPauses'][1]['changed']);self.assertTrue(any(q['status']=='BOUNDARY_MULTI_PIECE_REVIEW_REQUIRED' for q in r['nativeRepresentationConflicts']))
    def test_criterion_types_threshold_comparison_and_scopes_fail_closed(self):
        for field,value in [('minimumQuietDurationTicks',True),('minimumQuietDurationTicks',200000.0),('minimumQuietDurationTicks',0),('minimumQuietDurationTicks',200001),('comparison','GREATER_OR_EQUAL'),('auditScopes',['INTERNAL']),('auditScopes',['TAIL','HEAD','INTERNAL'])]:
            p=self.outer_plan();p['pauseCriterion'][field]=value
            with self.assertRaisesRegex(ValueError,'Exact pauseCriterion'):prepare_pacing(p)
    def test_wrapper_retains_criterion_and_rejects_typed_conflicting_duplicate(self):
        p=self.outer_plan();criterion=p.pop('pauseCriterion');wrapper={'pacingPlan':p,'pauseCriterion':criterion};before=copy.deepcopy(wrapper)
        q=pacing_input(wrapper);self.assertEqual(q['pauseCriterion'],criterion);self.assertEqual(wrapper,before);self.assertEqual(self.report(q)['status'],'PREPARED_ONLY')
        wrapper['pacingPlan']['pauseCriterion']=dict(criterion,minimumQuietDurationTicks=200000.0)
        with self.assertRaisesRegex(ValueError,'Conflicting outer/child'):pacing_input(wrapper)
    def test_boundary_frames_use_actual_24_30_60_and_rational_FPS(self):
        for num,den in ((24,1),(30,1),(60,1),(30000,1001)):
            r=self.report(self.outer_plan(num=num,den=den));self.assertEqual(r['status'],'PREPARED_ONLY');self.assertTrue(all(q['changed'] for q in r['boundaryPauses']));self.assertEqual((r['fpsNumerator'],r['fpsDenominator']),(num,den))
    def test_actual_cli_binds_criterion_and_both_outer_edits_without_native_authority(self):
        import subprocess,sys
        p=self.outer_plan();root=Path(self.temp.name);path=root/'threshold.json';path.write_text(json.dumps({'pacingPlan':p}),encoding='utf-8');out=root/'threshold-output'
        q=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('prepare_cut.py')),'--mode','pacing','--plan',str(path),'--out-dir',str(out)],capture_output=True,text=True)
        self.assertEqual(q.returncode,0,q.stdout+q.stderr);r=json.loads((out/'pacing-report.json').read_text(encoding='utf-8'));self.assertEqual(r['pauseCriterion']['minimumQuietDurationTicks'],200000);self.assertEqual(len(r['boundaryPauses']),2);self.assertEqual(r['nativeAudioAcceptance'],'PENDING')




class BrollNoRepeatDefaultTests(unittest.TestCase):
    setUp=BrollTests.setUp
    placement=BrollTests.placement
    review_plan=BrollTests.review_plan
    long=BrollReuseTests.long
    usage=BrollReuseTests.usage
    eligible=BrollReuseTests.eligible
    report=BrollReuseTests.report
    reasons=BrollReuseTests.reasons
    exhausted=BrollReuseTests.exhausted
    add_source=BrollReuseTests.add_source
    # Reuse fixture helpers only. Tests explicitly remove the legacy override
    # to exercise the new default.
    def default(self,p):
        p.pop('sourceReuseMode',None);p.pop('sourceReuseOverride',None);return p
    def test_ep5_captured_repeat_clock_shape_is_held(self):
        # Captured target/source numbers, synthetic files/review declarations only.
        p=self.default(self.long());p['placements'][0].update(startCaptionId='c0',lastCaptionId='c1',startTick=132566666,endTick=144666666,sourceInTick=0)
        p['placements'][0]['meaningReview']['overTenSecondsReason']='Synthetic long example for captured repeat-clock regression'
        p['captionCues']=[{'id':'c0','startTick':132566666,'endTick':138566666},{'id':'c1','startTick':138566666,'endTick':144666666}]
        p['sourceUsageReview']['existingPlacements']=[self.usage('first',5000000,9400000,0,4400000)];self.review_plan(p)
        row=self.report(p)['placements'][0]['sourceUsage']
        self.assertEqual(row['cooldownTicks'],128166666);self.assertIn('SOURCE_IDENTITY_ALREADY_USED_NO_REPEAT',row['conflictReasons']);self.assertIn('SOURCE_REUSE_COOLDOWN_BELOW_180_SECONDS',row['conflictReasons'])
    def test_default_blocks_disjoint_windows_same_original(self):
        p=self.default(self.long());p['placements'][0]['sourceInTick']=10000000;self.review_plan(p)
        r=self.report(p);self.assertIn('SOURCE_IDENTITY_ALREADY_USED_NO_REPEAT',self.reasons(p));self.assertEqual(r['sourceReusePolicy']['mode'],'NO_SOURCE_REPEAT')
        self.assertEqual(__import__('json').loads(prepare_broll(p)['broll-spec.json'])['track']['items'],[])
    def test_default_touching_source_windows_do_not_reset_identity(self):
        p=self.default(self.long());p['placements'][0]['sourceInTick']=4000000;self.review_plan(p)
        self.assertIn('SOURCE_IDENTITY_ALREADY_USED_NO_REPEAT',self.reasons(p))
    def test_default_180_seconds_and_exhaustion_are_not_permission(self):
        p=self.default(self.exhausted());r=self.report(p)
        self.assertIn('SOURCE_IDENTITY_ALREADY_USED_NO_REPEAT',self.reasons(p));self.assertFalse(r['placements'][0]['sourceUsage']['exhaustionMechanicallySupported'])
    def test_default_new_path_or_source_id_same_bytes_is_not_fresh(self):
        p=self.default(self.long());self.add_source(p,'renamed-alias',alias=True);p['placements'][0].update(sourceId='renamed-alias',sourceInTick=10000000);self.review_plan(p)
        self.assertIn('SOURCE_IDENTITY_ALREADY_USED_NO_REPEAT',self.reasons(p))
    def test_default_wholly_fresh_suitable_source_passes(self):
        p=self.default(self.long());self.add_source(p,'fresh');p['placements'][0]['sourceId']='fresh';self.review_plan(p)
        r=self.report(p);self.assertEqual(r['status'],'PREPARED_ONLY');self.assertEqual(r['sourceReusePolicy']['preference'],['WHOLLY_FRESH_SUITABLE_SOURCE','HOLD_MISSING_SUITABLE_FRESH_MATERIAL'])
    def test_conditional_mode_needs_exact_current_user_override(self):
        for field,value in [('reviewed',False),('evidenceBasis','AGENT_VERIFIED'),('authority','style-name'),('mode','NO_SOURCE_REPEAT'),('baseSnapshotSha256','sha256:stale'),('userQuote',''),('evidenceRef','')]:
            p=self.exhausted();p['sourceReuseOverride'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'explicit user override'):prepare_broll(p)
        p=self.exhausted();p.pop('sourceReuseOverride')
        with self.assertRaisesRegex(ValueError,'explicit user override'):prepare_broll(p)
    def test_unknown_reuse_mode_cannot_restore_legacy_default(self):
        p=self.long();p['sourceReuseMode']='ALLOW'
        with self.assertRaisesRegex(ValueError,'Known sourceReuseMode'):prepare_broll(p)
    def test_full_coverage_shortage_is_held_without_repeated_filler(self):
        p=self.default(FullBrollCoverageTests.full(self));r=self.report(p)
        self.assertFalse(r['fullTimelineCoveragePrepared']);self.assertEqual(r['status'],'PARTIAL_PREPARED_REVIEW_REQUIRED')
        self.assertEqual(len(__import__('json').loads(prepare_broll(p)['broll-spec.json'])['track']['items']),1)

if __name__=='__main__':unittest.main()
