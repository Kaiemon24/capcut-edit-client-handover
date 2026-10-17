"""Isolated producer/writer regressions; no real CapCut store is touched."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import native_timeline as n


class ProducerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.sources=[]
        for i in range(4):
            p=self.root/f'media{i}.mp4'; p.write_bytes((str(i)*89).encode())
            self.sources.append({'id':f's{i}','path':str(p),'sha256':n.sha256(p),
                'durationTicks':30_000_000,'width':2160,'height':3840,
                'origin':'CAMERA','voice':'NO_VOICE'})
        self.plan={'schema':n.SCHEMA,'project':{'name':'Portable_EP 1','fps':30,
            'canvas':{'width':1080,'height':1920}},'sources':self.sources,
            'mainPieces':[{'id':'m1','sourceId':'s0','sourceInTicks':2_000_000,
                'sourceOutTicks':7_000_000,'targetInTicks':0},
                {'id':'m2','sourceId':'s0','sourceInTicks':9_000_000,
                 'sourceOutTicks':14_000_000,'targetInTicks':5_000_000}],
            'captions':[{'id':'c1','text':'nhà 🏡 👨‍💼👩‍💼','rawWordIds':['w1','w2','w3'],
                'startTicks':0,'endTicks':5_000_000,'style':{}},
                {'id':'c2','text':'cụm tiếp theo','rawWordIds':['w4','w5','w6'],
                 'startTicks':5_000_000,'endTicks':10_000_000,'style':{}}],
            'brollPolicy':'NO_SOURCE_REPEAT','broll':[
                {'id':'b1','sourceId':'s1','sourceInTicks':5_000_000,
                 'sourceOutTicks':8_000_000,'targetInTicks':0,'mute':True},
                {'id':'b2','sourceId':'s2','sourceInTicks':6_000_000,
                 'sourceOutTicks':9_000_000,'targetInTicks':4_000_000,'mute':True},
                {'id':'b3','sourceId':'s3','sourceInTicks':8_000_000,
                 'sourceOutTicks':11_000_000,'targetInTicks':7_000_000,'mute':True}]}

    def compile(self):
        self.output=self.root/'compiled'; self.manifest=n.compile_plan(self.plan,self.output)
        return n.read_json(self.output/'files/draft_content.json')

    def test_editable_objects_original_handles_and_sidecars(self):
        draft=self.compile(); self.assertEqual([2,3,2],[len(t['segments']) for t in draft['tracks']])
        self.assertEqual(2_000_000,draft['tracks'][0]['segments'][0]['source_timerange']['start'])
        self.assertEqual(30_000_000,draft['materials']['videos'][0]['duration'])
        self.assertEqual(9,len(self.manifest['files']))
        self.assertEqual('SEMANTIC_READBACK_PASS',n.validate_compiled(self.output)['status'])
        for s in draft['tracks'][1]['segments']: self.assertEqual(0,s['volume'])
        self.assertLess(sum(s['target_timerange']['duration'] for s in draft['tracks'][1]['segments']),draft['duration'])

    def test_new_name_emitted_exactly_into_native_metadata_and_manifest(self):
        for i,name in enumerate(('MrsNga_Dot5_EP 1','OtherStyle_EP 7','Custom_Bán nhà cho người quen')):
            with self.subTest(name=name):
                plan=copy.deepcopy(self.plan);plan['project']['name']=name
                output=self.root/('named-'+str(i));manifest=n.compile_plan(plan,output)
                self.assertEqual(name,manifest['name'])
                self.assertEqual(name,n.read_json(output/'files/draft_content.json')['name'])
                self.assertEqual(name,n.read_json(output/'files/draft_meta_info.json')['draft_name'])

    def test_create_contract_cannot_be_bypassed_by_lookup_or_owned_flags(self):
        for name in ('Legacy project','MrsNga__EP 7','MrsNga_EP 7_REVIEW DRAFT',
                     'MrsNga_EP 7_fb2','MrsNga_EP 0'):
            with self.subTest(name=name):
                plan=copy.deepcopy(self.plan);plan['project'].update(name=name,intent='LOOKUP_EXISTING',owned=True)
                with self.assertRaisesRegex(n.PlanError,'new-project-name-invalid'):
                    n.compile_plan(plan,self.root/'never-created')
                self.assertFalse((self.root/'never-created').exists())
        plan=copy.deepcopy(self.plan);plan['project'].update(name='Old REVIEW DRAFT',revisionIdentity={'owned':True})
        with self.assertRaises(n.PlanError):n.validate_plan(plan)

    def test_bound_legacy_revision_preserves_exact_name_and_ids(self):
        import native_revision as revision
        from project_naming import resolve_project_identity
        self.compile();legacy='Old project REVIEW DRAFT';store=self.root/'fake-store';target=store/legacy
        shutil.copytree(self.output/'files',target)
        tid=self.manifest['timelineId'];pid=self.manifest['projectId']
        for rel in ('draft_content.json','template-2.tmp',f'Timelines/{tid}/draft_content.json',f'Timelines/{tid}/template-2.tmp'):
            value=n.read_json(target/rel);value['name']=legacy;(target/rel).write_bytes(n.json_bytes(value))
        meta=n.read_json(target/'draft_meta_info.json')
        meta.update(draft_name=legacy,draft_fold_path=str(target),draft_root_path=str(store))
        (target/'draft_meta_info.json').write_bytes(n.json_bytes(meta))
        (store/'root_meta_info.json').write_bytes(n.json_bytes({'all_draft_store':[
            {'draft_id':pid,'draft_name':legacy,'draft_fold_path':str(target)}]}))
        baseline=revision.capture_baseline(store,legacy,self.root/'legacy-baseline')
        plan=copy.deepcopy(self.plan);plan['project'].update(name=legacy,revisionIdentity=baseline)
        manifest=n.compile_plan(plan,self.root/'legacy-revision')
        self.assertEqual((legacy,pid,tid,'OWNED_REVISION'),tuple(manifest[k] for k in ('name','projectId','timelineId','identityMode')))
        result=resolve_project_identity({'output':{'mode':'EDIT_TIMELINE'},'projectIdentity':{'revisionIdentity':baseline}})
        self.assertEqual(legacy,result['name']);self.assertFalse(result['renamedExistingProject'])
        changed=copy.deepcopy(plan);changed['project']['name']='New_EP 7'
        with self.assertRaisesRegex(n.PlanError,'revision-compile-name-mismatch'):n.validate_plan(changed)
        changed=copy.deepcopy(plan);changed['project']['revisionIdentity']['sha256']='0'*64
        with self.assertRaisesRegex(n.PlanError,'hash-mismatch'):n.validate_plan(changed)

    def test_utf16_zwj_and_one_row_style(self):
        draft=self.compile(); content=json.loads(draft['materials']['texts'][0]['content'])
        self.assertEqual([0,len(content['text'].encode('utf-16-le'))//2],content['styles'][0]['range'])
        self.assertGreater(content['styles'][0]['range'][1],len(content['text']))
        draft['materials']['texts'][0]['content']=json.dumps({**content,'styles':[
            {**content['styles'][0],'range':[0,len(content['text'])]}]})
        with self.assertRaisesRegex(n.PlanError,'utf16'): n.inspect_native(draft,self.plan,self.manifest)

    def test_material_reordering_and_unreferenced_cleanup_preserve_semantics(self):
        draft=self.compile()
        for rows in draft['materials'].values(): rows.reverse()
        draft['tracks'].reverse()
        self.assertEqual('SEMANTIC_READBACK_PASS',n.inspect_native(draft,self.plan,self.manifest)['status'])
        draft['tracks'][0]['segments'][0]['target_timerange']['start']+=1
        with self.assertRaisesRegex(n.PlanError,'clock'): n.inspect_native(draft,self.plan,self.manifest)

    def test_source_drift_rejected_before_output(self):
        Path(self.sources[0]['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(n.PlanError,'source-hash'): n.compile_plan(self.plan,self.root/'never-created')
        self.assertFalse((self.root/'never-created').exists())

    def test_saved_dependency_and_video_transform_changes_are_detected(self):
        original=self.compile(); draft=copy.deepcopy(original)
        draft['materials']['canvases'][0]['color']='#FF0000'
        with self.assertRaisesRegex(n.PlanError,'resolved-dependency'): n.inspect_native(draft,self.plan,self.manifest)
        draft=copy.deepcopy(original); draft['tracks'][0]['segments'][0]['clip']['rotation']=90
        with self.assertRaisesRegex(n.PlanError,'visibility'): n.inspect_native(draft,self.plan,self.manifest)

    def test_preparation_cannot_write_under_native_store(self):
        store=self.root/'store'; store.mkdir(); (store/'root_meta_info.json').write_text('{}')
        with self.assertRaisesRegex(n.PlanError,'cannot-be-native-store'): n.compile_plan(self.plan,store/'new-project')
        self.assertFalse((store/'new-project').exists())

    def test_output_collision_does_not_change_existing(self):
        self.compile(); before=(self.output/'compiled-manifest.json').read_bytes()
        with self.assertRaisesRegex(n.PlanError,'must-not-exist'): n.compile_plan(self.plan,self.output)
        self.assertEqual(before,(self.output/'compiled-manifest.json').read_bytes())

    def test_malformed_cases(self):
        cases=[('float-clocks',lambda p:p['mainPieces'][0].update(sourceInTicks=2.0)),
            ('source-bounds',lambda p:p['mainPieces'][0].update(sourceOutTicks=31_000_000)),
            ('main-gap',lambda p:p['mainPieces'][1].update(targetInTicks=5_000_001)),
            ('duplicate-id',lambda p:p['captions'][0].update(id='m1')),
            ('repeat-source',lambda p:p['broll'][1].update(sourceId='s1')),
            ('unmuted',lambda p:p['broll'][0].update(mute=False)),
            ('edge',lambda p:p['broll'][0].update(sourceInTicks=4_999_999)),
            ('two-row',lambda p:p['captions'][0].update(text='two\nrows')),
            ('raw-id',lambda p:p['captions'][1].update(rawWordIds=['w1'])),
            ('unknown-style',lambda p:p['captions'][0].update(style={'font_path':'private'})),
            ('invalid-style',lambda p:p['captions'][0].update(style={'opacity':float('nan')})),
            ('bad-name',lambda p:p['project'].update(name='../foreign'))]
        for label, mutate in cases:
            with self.subTest(label=label):
                p=copy.deepcopy(self.plan); mutate(p)
                with self.assertRaises(n.PlanError): n.validate_plan(p)

    def test_larger_or_unbound_source_target_phase_rejected(self):
        p=copy.deepcopy(self.plan); p['mainPieces'][0]['targetOutTicks']=4_999_999
        with self.assertRaisesRegex(n.PlanError,'phase'): n.validate_plan(p)
        p['mainPieces'][0]['targetOutTicks']=4_000_000
        with self.assertRaisesRegex(n.PlanError,'phase'): n.validate_plan(p)

    def test_bound_inherited_phase_preserves_exact_source_and_actual_target_end(self):
        p=copy.deepcopy(self.plan); p['sources'][0]['nativeMaterialId']='inherited-material'
        p['mainPieces']=[{'id':'m1','sourceId':'s0','sourceInTicks':10,'sourceOutTicks':33344,
            'targetInTicks':0,'targetOutTicks':33333,'nativeSegmentId':'inherited-segment'}]
        p['broll']=[]; p['captions'][0].update(startTicks=0,endTicks=33333); p['captions']=p['captions'][:1]
        baseline=self.root/'baseline.json'; baseline.write_bytes(n.json_bytes({'fps':30,'tracks':[
            {'segments':[{'id':'inherited-segment','material_id':'inherited-material','speed':1,'reverse':False,
                'source_timerange':{'start':10,'duration':33334},'target_timerange':{'start':0,'duration':33333}}]}]}))
        phase=self.root/'phase.json'; phase.write_bytes(n.json_bytes({'schema':'capcut-native-phase/v1',
            'baseline':{'path':str(baseline),'sha256':'sha256:'+n.sha256(baseline)},
            'rationalFps':{'numerator':30,'denominator':1},'inheritedRanges':[{
                'segmentId':'inherited-segment','materialId':'inherited-material','sourceInTick':10,
                'sourceOutTick':33344,'startTick':0,'endTick':33333,'frameCount':1}]}))
        p['nativePhaseEvidence']={'path':str(phase),'sha256':'sha256:'+n.sha256(phase)}
        out=self.root/'phase-output'; m=n.compile_plan(p,out); draft=n.read_json(out/'files/draft_content.json')
        self.assertEqual(33333,m['durationTicks']); self.assertEqual(33334,draft['tracks'][0]['segments'][0]['source_timerange']['duration'])
        changed=copy.deepcopy(p); changed['project']['fps']=60
        with self.assertRaisesRegex(ValueError,'phase-current-fps'): n.validate_plan(changed)
        p['mainPieces'][0]['sourceOutTicks']+=1
        with self.assertRaisesRegex(ValueError,'phase-changed-geometry'): n.validate_plan(p)

    def test_fresh_ids_and_no_template_private_values(self):
        self.compile(); one=self.manifest['projectId']; other=n.compile_plan(self.plan,self.root/'second')
        self.assertNotEqual(one,other['projectId'])
        t=n.read_json(n.TEMPLATE); encoded=json.dumps(t)
        self.assertNotRegex(encoded,r'[A-Za-z]:[/\\]')
        self.assertNotRegex(encoded,r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}')
        self.assertNotIn('MrsNga',encoded); self.assertNotIn('toan_',encoded)

    def test_duplicate_json_keys_rejected(self):
        p=self.root/'bad.json'; p.write_text('{"id":1,"id":2}')
        with self.assertRaisesRegex(n.PlanError,'duplicate-json-key'): n.read_json(p)


class SavedNormalizationTests(unittest.TestCase):
    setUp=ProducerTests.setUp
    compile=ProducerTests.compile
    def frame_fixture(self, fps=30, *, floor_plan=False):
        self.plan['project']['fps']=fps
        self.plan['project']['rationalFps']={'numerator':fps,'denominator':1}
        end=(133333 if floor_plan else 133334) if fps==30 else 160000
        middle=(66666 if floor_plan else 66667) if fps==30 else 80000
        self.plan['mainPieces']=[{'id':'m1','sourceId':'s0','sourceInTicks':0,
            'sourceOutTicks':end,'targetInTicks':0}]
        self.plan['broll']=[]
        self.plan['captions'][0].update(startTicks=0,endTicks=middle)
        self.plan['captions'][1].update(startTicks=middle,endTicks=end)
        return self.compile()

    def test_30fps_floor_and_ceil_of_same_events_both_directions(self):
        for floor_plan in (False,True):
            with self.subTest(floor_plan=floor_plan):
                if hasattr(self,'output'):
                    self.output.rename(self.root/'previous-compiled')
                draft=self.frame_fixture(floor_plan=floor_plan)
                middle,end=(66667,133334) if floor_plan else (66666,133333)
                draft['duration']=end
                segment=draft['tracks'][0]['segments'][0]
                segment['source_timerange']['duration']=end
                segment['target_timerange']['duration']=end
                caps=draft['tracks'][2]['segments']
                caps[0]['target_timerange']['duration']=middle
                caps[1]['target_timerange']={'start':middle,'duration':end-middle}
                result=n.inspect_native(draft,self.plan,self.manifest)
                self.assertEqual('SEMANTIC_READBACK_PASS',result['status'])
                self.assertTrue(result['saveNormalization']['clockEndpoints'])

    def test_25fps_exact_frame_events_have_no_microsecond_tolerance(self):
        draft=self.frame_fixture(25)
        self.assertEqual([],n.inspect_native(draft,self.plan,self.manifest)['saveNormalization']['clockEndpoints'])
        for delta in (-1,1,40000):
            with self.subTest(delta=delta):
                changed=copy.deepcopy(draft);changed['duration']+=delta
                with self.assertRaisesRegex(n.PlanError,'duration-mismatch'):
                    n.inspect_native(changed,self.plan,self.manifest)

    def test_arbitrary_tick_and_whole_frame_drift_rejected(self):
        draft=self.frame_fixture()
        for start,end in ((66668,133334),(10001,133334),(100000,133334)):
            with self.subTest(start=start,end=end):
                changed=copy.deepcopy(draft)
                changed['tracks'][2]['segments'][1]['target_timerange']={'start':start,'duration':end-start}
                with self.assertRaisesRegex(n.PlanError,'caption-clock'):
                    n.inspect_native(changed,self.plan,self.manifest)

    def test_source_start_and_unpaired_source_end_changes_rejected(self):
        draft=self.frame_fixture()
        for source_range in ({'start':1,'duration':133333},{'start':0,'duration':133333}):
            with self.subTest(source_range=source_range):
                changed=copy.deepcopy(draft);changed['tracks'][0]['segments'][0]['source_timerange']=source_range
                with self.assertRaisesRegex(n.PlanError,'source-target-clocks'):
                    n.inspect_native(changed,self.plan,self.manifest)

    def test_clock_json_types_and_extra_fields_remain_strict(self):
        draft=self.frame_fixture()
        for update in ({'start':False},{'duration':133334.0},{'extra':0}):
            with self.subTest(update=update):
                changed=copy.deepcopy(draft);changed['tracks'][0]['segments'][0]['target_timerange'].update(update)
                with self.assertRaisesRegex(n.PlanError,'source-target-clocks'):
                    n.inspect_native(changed,self.plan,self.manifest)

    def test_identical_same_category_material_aliases_only(self):
        draft=self.compile();row=copy.deepcopy(draft['materials']['videos'][0])
        draft['materials']['videos'].extend([copy.deepcopy(row),copy.deepcopy(row)])
        result=n.inspect_native(draft,self.plan,self.manifest)
        self.assertEqual(2,len(result['saveNormalization']['identicalMaterialAliases']))
        for key,value in (('path','foreign.mp4'),('width',2160.0),('extra',False)):
            with self.subTest(key=key):
                changed=copy.deepcopy(draft);changed['materials']['videos'][-1][key]=value
                with self.assertRaisesRegex(n.PlanError,'duplicate-material'):
                    n.inspect_native(changed,self.plan,self.manifest)
        draft['materials']['canvases'].append(row)
        with self.assertRaisesRegex(n.PlanError,'duplicate-material'):
            n.inspect_native(draft,self.plan,self.manifest)

    def test_registration_duration_observed_upward_native_frame_only(self):
        cases=((30,61561500,61566666),(30,61561500,61566667),(30,94094000,94100000),
               (30,107607500,107633333),(25,30000001,30040000))
        for index,(fps,original,saved) in enumerate(cases):
            with self.subTest(fps=fps,original=original):
                self.plan['project']['fps']=fps;self.plan['sources'][0]['durationTicks']=original
                output=self.root/f'registration-{index}';manifest=n.compile_plan(self.plan,output)
                draft=n.read_json(output/'files/draft_content.json');draft['materials']['videos'][0]['duration']=saved
                result=n.inspect_native(draft,self.plan,manifest)
                changes=result['saveNormalization']['registrationDurations']
                self.assertEqual(1,len(changes));self.assertEqual(original,changes[0]['originalDurationTick'])
                for bad in (saved+2,saved+40000,original+1):
                    if bad==original:continue
                    changed=copy.deepcopy(draft);changed['materials']['videos'][0]['duration']=bad
                    with self.assertRaisesRegex(n.PlanError,'source-registration'):
                        n.inspect_native(changed,self.plan,manifest)

    def test_registration_metadata_does_not_expand_original_excerpt_bounds(self):
        draft=self.compile();p=copy.deepcopy(self.plan)
        p['mainPieces']=[{'id':'m1','sourceId':'s0','sourceInTicks':0,
            'sourceOutTicks':30_000_001,'targetInTicks':0}]
        p['captions']=[];p['broll']=[]
        draft['materials']['videos'][0]['duration']=30_033_333
        with self.assertRaisesRegex(n.PlanError,'source-target-bounds'):
            n.inspect_native(draft,p,self.manifest)

    def test_saved_source_rounding_cannot_expand_original_bounds(self):
        self.plan['sources'][0]['durationTicks']=133333
        draft=self.frame_fixture(floor_plan=True)
        draft['duration']=133334
        segment=draft['tracks'][0]['segments'][0]
        segment['source_timerange']['duration']=133334
        segment['target_timerange']['duration']=133334
        with self.assertRaisesRegex(n.PlanError,'source-target-clocks'):
            n.inspect_native(draft,self.plan,self.manifest)


class WriterTests(unittest.TestCase):
    setUp=ProducerTests.setUp
    compile=ProducerTests.compile
    def writer_setup(self):
        self.compile(); self.store=self.root/'fake-store'; self.store.mkdir()
        self.index=self.store/'root_meta_info.json'
        self.original=(b'\xef\xbb\xbf{ "opaque":900719925474099312345, "number":-9007199254740999,'
            b' "decimal":1.234567890123456789,"all_draft_store" : [\n'
            b' {"draft_name":"old","draft_id":900719925474099312345,"typed":"900719925474099312345"}\n],"tail":true}\n')
        self.index.write_bytes(self.original)
        native=self.output/'files/draft_content.json'
        self.destination=self.store/self.manifest['name']
        authority=self.root/'authority.json'; authority.write_bytes(n.json_bytes({
            'evidenceClass':'REAL_OBSERVATION','authority':'explicit-user-request','userQuote':'synthetic test only',
            'claim':'review-draft-native-apply','mode':'REVIEW_DRAFT',
            'nativeHash':'sha256:'+n.sha256(native),'destinationPath':str(self.destination),
            'projectId':self.manifest['projectId'],'timelineId':self.manifest['timelineId']}))
        authority_ref={'path':str(authority),'sha256':'sha256:'+n.sha256(authority)}
        self.guard={'mode':'REVIEW_DRAFT','native':{'path':str(native),'sha256':'sha256:'+n.sha256(native)},
            'reviewDraft':{'authorityEvidence':authority_ref,'destination':{'path':str(self.destination),'projectId':self.manifest['projectId'],
                'timelineId':self.manifest['timelineId'],'operation':'CREATE_SEPARATE_NEW_PROJECT','overwriteExisting':False}}}
        guard_path=self.root/'guard.json'; guard_path.write_bytes(n.json_bytes(self.guard))
        self.request={'schema':'capcut-new-project-apply/v1','storePath':str(self.store),
            'rootIndexSHA256':n.sha256(self.index),'name':self.manifest['name'],
            'projectId':self.manifest['projectId'],'timelineId':self.manifest['timelineId'],
            'authorityEvidence':authority_ref,
            'guardManifest':{'path':str(guard_path),'sha256':n.sha256(guard_path)}}
        self.result={'passed':True,'status':'PROVISIONAL_NOT_ACCEPTED','stage':'REVIEW_DRAFT',
            'finalAcceptance':False,'errors':[],'nativeHash':self.guard['native']['sha256']}

    def apply(self):
        return n.apply_new_project(self.output,self.request,self.root/'journal')

    def mocks(self):
        return patch.multiple(n,_assert_app=unittest.mock.DEFAULT,
            _assert_editor_closed=unittest.mock.DEFAULT,_guard_check=unittest.mock.DEFAULT)

    def test_writer_precision_headers_old_rows_and_readback(self):
        self.writer_setup()
        with self.mocks() as mocks:
            mocks['_guard_check'].return_value=self.result
            result=self.apply(); self.assertEqual(1,mocks['_guard_check'].call_count)
            self.assertGreaterEqual(mocks['_assert_editor_closed'].call_count,3)
        self.assertTrue(result['oldRootBytesPreserved']); self.assertFalse(result['finalAcceptance'])
        after=self.index.read_bytes(); doc=json.loads(after.decode('utf-8-sig'))
        self.assertEqual(900719925474099312345,doc['opaque'])
        self.assertIs(type(doc['all_draft_store'][1]['draft_id']),int)
        ins=result['insertion']; at=ins['insertionOffset']; count=ins['insertedByteCount']
        self.assertEqual(self.original,after[:at]+after[at+count:])
        self.assertEqual(self.manifest['projectId'],doc['all_draft_store'][0]['draft_id'])
        self.assertTrue((self.destination/'Timelines/project.json').is_file())

    def test_guard_refusal_never_creates_store_files(self):
        self.writer_setup()
        with self.mocks() as mocks:
            mocks['_guard_check'].return_value={'status':'BLOCKED','errors':['pending']}
            with self.assertRaisesRegex(n.PlanError,'guard-refused'): self.apply()
        self.assertFalse(self.destination.exists()); self.assertEqual(self.original,self.index.read_bytes())

    def test_arbitrary_authority_reference_is_refused(self):
        self.writer_setup(); p=self.root/'authority.json'; p.write_text('{"explicit":true}')
        self.request['authorityEvidence']['sha256']='sha256:'+n.sha256(p)
        with self.mocks() as mocks:
            with self.assertRaisesRegex(n.PlanError,'exact-native-create-authority'): self.apply()
            mocks['_guard_check'].assert_not_called()
        self.assertFalse(self.destination.exists()); self.assertEqual(self.original,self.index.read_bytes())

    def test_name_collision_blocks_before_guard(self):
        self.writer_setup(); self.destination.mkdir()
        with self.mocks() as mocks:
            with self.assertRaisesRegex(n.PlanError,'collision'): self.apply()
            mocks['_guard_check'].assert_not_called()
        self.assertEqual(self.original,self.index.read_bytes())

    def test_baseline_drift_blocks_before_guard(self):
        self.writer_setup(); self.index.write_bytes(self.original+b' ')
        with self.mocks() as mocks:
            with self.assertRaisesRegex(n.PlanError,'baseline-drift'): self.apply()
            mocks['_guard_check'].assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_guard_side_effect_drift_is_not_overwritten(self):
        self.writer_setup(); foreign=self.original+b'\n'
        def drift(_): self.index.write_bytes(foreign); return self.result
        with self.mocks() as mocks:
            mocks['_guard_check'].side_effect=drift
            with self.assertRaisesRegex(n.PlanError,'drift-after-guard'): self.apply()
        self.assertEqual(foreign,self.index.read_bytes()); self.assertFalse(self.destination.exists())

    def test_editor_open_blocks_before_guard(self):
        self.writer_setup()
        with self.mocks() as mocks:
            mocks['_assert_editor_closed'].side_effect=n.PlanError('capcut-must-be-closed')
            with self.assertRaisesRegex(n.PlanError,'closed'): self.apply()
            mocks['_guard_check'].assert_not_called()
        self.assertEqual(self.original,self.index.read_bytes()); self.assertFalse(self.destination.exists())

    def test_index_write_failure_retains_owned_folder_and_old_index(self):
        self.writer_setup()
        with self.mocks() as mocks, patch.object(n.os,'replace',side_effect=OSError('synthetic-write-fault')):
            mocks['_guard_check'].return_value=self.result
            with self.assertRaisesRegex(OSError,'synthetic'): self.apply()
        self.assertEqual(self.original,self.index.read_bytes()); self.assertTrue(self.destination.is_dir())
        self.assertTrue((self.root/'journal/failure.json').is_file())

    def test_uncertain_replace_is_reconciled_from_actual_bytes(self):
        self.writer_setup(); actual_replace=os.replace; calls=0
        def effect_then_raise(source,dest):
            nonlocal calls
            calls+=1; actual_replace(source,dest)
            if calls==1: raise OSError('reported-after-write')
        with self.mocks() as mocks, patch.object(n.os,'replace',side_effect=effect_then_raise):
            mocks['_guard_check'].return_value=self.result
            with self.assertRaisesRegex(OSError,'reported-after-write'): self.apply()
        self.assertEqual(self.original,self.index.read_bytes())
        self.assertTrue(n.read_json(self.root/'journal/failure.json')['indexRestored'])

    def test_guard_wrong_destination_blocks_before_mutation(self):
        self.writer_setup(); self.guard['reviewDraft']['destination']['projectId']='foreign'
        p=self.root/'guard.json'; p.write_bytes(n.json_bytes(self.guard)); self.request['guardManifest']['sha256']=n.sha256(p)
        with self.mocks() as mocks:
            with self.assertRaisesRegex(n.PlanError,'destination-mismatch'): self.apply()
            mocks['_guard_check'].assert_not_called()
        self.assertEqual(self.original,self.index.read_bytes())


if __name__=='__main__': unittest.main()
