"""Synthetic naming/intake tests; no native app, heard audio or write authority."""
import copy, json, unittest
from pathlib import Path
from project_naming import resolve_project_identity, selected_profile, safe_name, validate_new_project_name
from prepare_cut import prepare_intake


class NamingTests(unittest.TestCase):
    def setUp(self):
        self.profile = {'id':'nga','displayName':'MrsNga','projectNaming':{
            'mode':'STYLE_EPISODE','styleId':'nga','defaultPrefix':'MrsNga',
            'separator':'_','episodePrefix':'EP ','contextTemplate':'Dot{shootBatch}'}}
        self.brief = {'output':{'mode':'EDIT_TIMELINE'},'style':{'selectedId':'nga'},
                      'projectIdentity':{'namingParameters':{},'parameterEvidenceRefs':{}}}
    def result(self, brief=None, profile=None):
        return resolve_project_identity(brief or self.brief, self.profile if profile is None else profile, 'nga')
    def bind(self, **values):
        self.brief['projectIdentity']['namingParameters'].update(values)
        self.brief['projectIdentity']['parameterEvidenceRefs'].update({k:'synthetic-user-answer' for k in values})
    def test_explicit_new_name_preserves_prefix_and_spacing(self):
        self.brief['projectIdentity'].update(intent='CREATE',name='Custom Brand_Dot5_EP 7',evidenceRef='synthetic-user')
        before=copy.deepcopy(self.brief);r=self.result()
        self.assertEqual(r['name'],'Custom Brand_Dot5_EP 7');self.assertIsNone(r['nextQuestion'])
        self.assertEqual(self.brief,before);self.assertFalse(r['applyEligible'])
    def test_explicit_new_title_without_profile(self):
        self.brief['projectIdentity'].update(intent='CREATE',name='OtherStyle_Bán nhà cho người quen',evidenceRef='synthetic')
        self.assertEqual(resolve_project_identity(self.brief,None,None)['name'],'OtherStyle_Bán nhà cho người quen')
    def test_legacy_lookup_explicit_or_default_preserves_exact_name(self):
        for intent in (None,'LOOKUP_EXISTING','LOOKUP','EXISTING'):
            with self.subTest(intent=intent):
                b=copy.deepcopy(self.brief);b['projectIdentity'].update(name='Old project REVIEW DRAFT',evidenceRef='synthetic')
                if intent:b['projectIdentity']['intent']=intent
                r=self.result(b);self.assertEqual(r['name'],'Old project REVIEW DRAFT')
                self.assertEqual(r['intent'],intent or 'LOOKUP_EXISTING')
                self.assertEqual(r['creationAction'],'LOOKUP_ONLY_NO_CREATE_OR_REVISION_AUTHORITY')
                self.assertFalse(r['applyEligible']);self.assertEqual(r['nativeExistence'],'UNKNOWN')
    def test_invalid_new_name_returns_targeted_question_without_silent_strip(self):
        for name in ('MrsNga_EP 7_REVIEW DRAFT','MrsNga_EP 7_fb2','MrsNga__EP 7','OnlyOnePart'):
            with self.subTest(name=name):
                self.brief['projectIdentity'].update(intent='CREATE',name=name,evidenceRef='synthetic')
                before=copy.deepcopy(self.brief);r=self.result()
                self.assertEqual(r['status'],'NEEDS_PROJECT_NAME');self.assertIsNone(r['name'])
                self.assertEqual(r['rejectedName'],name);self.assertTrue(r['nextQuestion'])
                self.assertEqual(self.brief,before)
    def test_name_requires_evidence(self):
        self.brief['projectIdentity']['name']='Brand_EP 1'
        with self.assertRaisesRegex(ValueError,'evidence'):self.result()
    def test_missing_episode_is_only_question_optional_batch_not_requested(self):
        r=self.result();self.assertEqual(r['missingParameters'],['episode'])
        self.assertIn('EP',r['nextQuestion']);self.assertNotIn('đợt',r['nextQuestion'])
    def test_known_batch_asks_episode_only(self):
        self.bind(shootBatch=5);r=self.result()
        self.assertEqual(r['missingParameters'],['episode']);self.assertNotIn('đợt',r['nextQuestion'])
    def test_known_episode_needs_no_context_interview(self):
        self.bind(episode=7);r=self.result()
        self.assertEqual(r['name'],'MrsNga_EP 7');self.assertIsNone(r['nextQuestion'])
    def test_explicit_null_intent_without_name_infers_create(self):
        self.bind(episode=7);self.brief['projectIdentity']['intent']=None
        before=copy.deepcopy(self.brief);r=self.result()
        self.assertEqual(r['intent'],'CREATE');self.assertEqual(r['name'],'MrsNga_EP 7')
        self.assertFalse(r['applyEligible']);self.assertEqual(before,self.brief)
    def test_explicit_null_intent_with_name_infers_legacy_lookup(self):
        self.brief['projectIdentity'].update(intent=None,name='Legacy REVIEW DRAFT',evidenceRef='synthetic')
        r=self.result();self.assertEqual(r['intent'],'LOOKUP_EXISTING')
        self.assertEqual(r['name'],'Legacy REVIEW DRAFT');self.assertFalse(r['applyEligible'])
        self.assertEqual(r['creationAction'],'LOOKUP_ONLY_NO_CREATE_OR_REVISION_AUTHORITY')
    def test_explicit_invalid_intent_types_and_values_still_reject(self):
        for intent in ('','create','FORCE_CREATE',False,0,1,[],{},['CREATE']):
            with self.subTest(intent=intent):
                self.brief['projectIdentity']['intent']=intent
                with self.assertRaisesRegex(ValueError,'Known project identity intent'):
                    self.result()
    def test_known_batch_and_episode(self):
        self.bind(shootBatch=5,episode=1);r=self.result()
        self.assertEqual(r['name'],'MrsNga_Dot5_EP 1');self.assertIsNone(r['nextQuestion'])
        self.assertFalse(r['renamedExistingProject']);self.assertFalse(r['applyEligible'])
    def test_different_batches_do_not_collide(self):
        self.bind(shootBatch=5,episode=1);a=self.result()['name']
        self.bind(shootBatch=6);self.assertNotEqual(a,self.result()['name'])
    def test_unknown_batch_not_invented_from_folder(self):
        self.bind(episode=7);self.brief['source']={'path':'D:/FolderDot99/clip.MP4'}
        self.assertEqual(self.result()['name'],'MrsNga_EP 7')
    def test_number_without_evidence_is_still_missing(self):
        self.brief['projectIdentity']['namingParameters']['episode']=7
        self.assertEqual(self.result()['missingParameters'],['episode'])
    def test_direct_episode_and_context_use_proven_answers(self):
        self.brief['projectIdentity'].update(episode=7,context='Dot5',parameterEvidenceRefs={'episode':'old-answer','context':'old-answer'})
        self.assertEqual(self.result()['name'],'MrsNga_Dot5_EP 7')
    def test_direct_title_or_legacy_episode_label(self):
        self.brief['projectIdentity'].update(episode='Bán nhà cho người quen',evidenceRef='synthetic-user')
        self.assertEqual(self.result()['name'],'MrsNga_Bán nhà cho người quen')
        self.brief['projectIdentity'].pop('episode');self.bind(episodeLabel='Tập mở đầu')
        self.assertEqual(self.result()['name'],'MrsNga_Tập mở đầu')
    def test_context_alias_wins_over_batch(self):
        self.bind(context='Season 2',shootBatch=5,episode=7)
        self.assertEqual(self.result()['name'],'MrsNga_Season 2_EP 7')
    def test_malformed_positive_numbers_refused(self):
        for bad in (0,-1,True,1.2,'0','-1','1.0'):
            with self.subTest(bad=bad):
                self.bind(shootBatch=bad,episode=7)
                with self.assertRaises(ValueError):self.result()
    def test_numeric_padding_is_preserved(self):
        self.bind(shootBatch='05',episode='07');self.assertEqual(self.result()['name'],'MrsNga_Dot05_EP 07')
    def test_empty_direct_field_does_not_hide_prior_proven_answer(self):
        self.bind(episode=7);self.brief['projectIdentity']['episode']=None
        self.assertEqual(self.result()['name'],'MrsNga_EP 7')
    def test_bad_episode_type_does_not_become_title(self):
        for bad in (0,-1,True,1.2,[],{},'-1','1.0'):
            with self.subTest(bad=bad):
                self.bind(episode=bad)
                with self.assertRaises(ValueError):self.result()
    def test_srt_and_unknown_mode_do_not_ask_project(self):
        for mode in ('SRT_ONLY',None):
            self.brief['output']['mode']=mode;r=self.result()
            self.assertIsNone(r['nextQuestion']);self.assertIsNone(r['intent'])
    def test_unknown_style_asks_style_label_not_nga_or_batch(self):
        self.bind(episode=7);r=resolve_project_identity(self.brief,None,'other')
        self.assertEqual(r['missingParameters'],['styleDisplayName']);self.assertIsNone(r['name'])
        self.assertNotIn('Nga',r['nextQuestion'])
    def test_other_style_and_style_label_fallback(self):
        for key in ('displayName','name','title'):
            with self.subTest(key=key):
                p={'id':'other',key:'Kai Green'};self.bind(episode=2)
                self.assertEqual(resolve_project_identity(self.brief,p,'other')['name'],'Kai Green_EP 2')
        self.assertIsNone(resolve_project_identity(self.brief,{'id':'other'},'other')['name'])
    def test_profile_mismatch_and_unsupported_policy_refused(self):
        with self.assertRaises(ValueError):resolve_project_identity(self.brief,self.profile,'other')
        for field,value in (('styleId','other'),('mode','EXPRESSION'),('separator','-'),('episodePrefix','Part')):
            p=copy.deepcopy(self.profile);p['projectNaming'][field]=value
            with self.assertRaises(ValueError):self.result(profile=p)
    def test_no_expression_evaluation_in_optional_context(self):
        self.bind(shootBatch=5,episode=7);p=copy.deepcopy(self.profile)
        p['projectNaming']['contextTemplate']='{shootBatch.__class__}'
        with self.assertRaises(ValueError):self.result(profile=p)
    def test_legacy_template_readable_but_batch_not_required(self):
        p={'id':'nga','projectNaming':{'mode':'TEMPLATE','styleId':'nga',
            'template':'MrsNga_Dot{shootBatch}_EP{episode}','parameters':[
                {'id':'shootBatch','label':'đợt quay','type':'POSITIVE_INTEGER'},
                {'id':'episode','label':'EP','type':'POSITIVE_INTEGER'}]}}
        self.bind(episode=7);self.assertEqual(self.result(profile=p)['name'],'MrsNga_EP 7')
        for field in ('{shootBatch.__class__}','{shootBatch[0]}','{shootBatch!r}','{shootBatch:02d}','{undeclared}'):
            p['projectNaming']['template']='MrsNga_'+field+'_{episode}'
            with self.assertRaises(ValueError):self.result(profile=p)
    def test_new_name_shape_status_and_numeric_rejections(self):
        for name in ('Brand__EP 7','_EP 7','Brand_EP 7_','Brand_ EP 7','Brand _EP 7',
                     'Brand_7','Brand_EP','Brand_EP 0','Brand_EP -1','Brand_review',
                     'Brand_Review Draft','Brand_EP 7 feedback-v2','Brand_FB02',
                     'Brand_trial 1','Brand_test-v1','Brand_draft2','Brand_FINAL',
                     'Brand_preview v2','Brand_WiP','Brand_EP7_review!',
                     'Brand_EP7_feedback,','Brand_EP 7 draft v2!','Brand_FB…'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):validate_new_project_name(name)
    def test_valid_names_are_returned_byte_for_byte(self):
        for name in ('MrsNga_Dot5_EP 1','MrsNga_EP 7','OtherStyle_EP007',
                     'Personal_Tập mở đầu','Khách hàng_Nhà cho người quen',
                     'Client_Review dự án X','Client_Previewing the house'):
            self.assertEqual(name,validate_new_project_name(name))
    def test_unsafe_names_never_normalized_or_written(self):
        for name in ('../x','bad/name','NUL','name.','name ',' name','bad\nname'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):safe_name(name)
    def test_loader_identity_and_traversal(self):
        self.assertEqual('nga',selected_profile('nga')['id'])
        self.bind(episode=7)
        self.assertEqual('MrsNga_EP 7',resolve_project_identity(self.brief,selected_profile('nga'),'nga')['name'])
        with self.assertRaises(ValueError):selected_profile('../other')
        self.assertIsNone(selected_profile('nonexistent_synthetic_style'))
    def test_lookup_missing_name_does_not_propose_new_one(self):
        self.brief['projectIdentity']['intent']='LOOKUP_EXISTING';self.bind(episode=7)
        self.assertEqual(self.result()['status'],'NEEDS_PROJECT_NAME');self.assertIsNone(self.result()['name'])
    def test_fake_revision_or_name_intent_is_not_authority(self):
        self.brief['projectIdentity']['revisionIdentity']={'owned':True}
        with self.assertRaises(ValueError):self.result()
        self.brief['projectIdentity']={'intent':'FORCE_CREATE'}
        with self.assertRaises(ValueError):self.result()


class IntakeNamingTests(unittest.TestCase):
    def brief(self):
        return {'schemaVersion':'capcut-brief/v1','workScope':'SUB_ONLY','output':{'mode':'EDIT_TIMELINE','modeEvidence':'synthetic-user-timeline'},'requiresTranscription':False,'transcriptionRequirementEvidenceRef':'synthetic-aligned-transcript','recipient':{'kind':'PERSON','id':'other','label':'Other','reviewed':True,'evidenceRef':'synthetic-user'}}
    def test_missing_name_is_real_dependency(self):
        r=json.loads(prepare_intake(self.brief())['caption-intake-report.json'])
        self.assertIn('PROJECT_IDENTITY',r['inputDependencies']);self.assertFalse(r['readyForAuthorizedPreparation'])
    def test_actual_candidate_template_null_intent_is_supported(self):
        path=Path(__file__).resolve().parents[1]/'templates/brief.json'
        b=json.loads(path.read_text('utf-8-sig'))
        self.assertIsNone(b['projectIdentity']['intent'])
        self.assertEqual('PENDING_OUTPUT_MODE',resolve_project_identity(b)['status'])
        b['output']['mode']='EDIT_TIMELINE'
        before=copy.deepcopy(b);r=resolve_project_identity(b,selected_profile('nga'),'nga')
        self.assertEqual('CREATE',r['intent']);self.assertEqual(['episode'],r['missingParameters'])
        self.assertEqual(before,b)
        b['projectIdentity'].update(name='Existing legacy REVIEW DRAFT',evidenceRef='synthetic')
        r=resolve_project_identity(b,None,None)
        self.assertEqual('LOOKUP_EXISTING',r['intent']);self.assertEqual('Existing legacy REVIEW DRAFT',r['name'])
    def test_legacy_explicit_name_reused_for_lookup_but_not_native_proof(self):
        b=self.brief();b['projectIdentity']={'name':'Explicit legacy name','evidenceRef':'synthetic-user'}
        r=json.loads(prepare_intake(b)['caption-intake-report.json'])
        self.assertNotIn('PROJECT_IDENTITY',r['inputDependencies'])
        self.assertEqual(r['projectIdentity']['intent'],'LOOKUP_EXISTING')
        self.assertEqual(r['projectIdentity']['nativeExistence'],'UNKNOWN')
    def test_explicit_create_bad_suffix_is_dependency_even_when_profile_skipped(self):
        b=self.brief();b['projectIdentity']={'intent':'CREATE','name':'Custom_EP 7_REVIEW DRAFT','evidenceRef':'synthetic'}
        r=json.loads(prepare_intake(b)['caption-intake-report.json'])
        self.assertIn('PROJECT_IDENTITY',r['inputDependencies'])
        self.assertEqual(r['projectIdentity']['rejectedName'],'Custom_EP 7_REVIEW DRAFT')
    def test_explicit_create_valid_custom_prefix_no_profile_needed(self):
        b=self.brief();b['projectIdentity']={'intent':'CREATE','name':'Custom_EP 7','evidenceRef':'synthetic'}
        r=json.loads(prepare_intake(b)['caption-intake-report.json'])
        self.assertNotIn('PROJECT_IDENTITY',r['inputDependencies'])
    def test_srt_has_no_project_dependency(self):
        b=self.brief();b['output']['mode']='SRT_ONLY'
        r=json.loads(prepare_intake(b)['caption-intake-report.json'])
        self.assertNotIn('PROJECT_IDENTITY',r['inputDependencies'])


if __name__ == '__main__':
    unittest.main()
