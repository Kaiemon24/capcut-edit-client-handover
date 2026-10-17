"""Build task-local pending review evidence from supplied reviewed inputs.

No decoder, hearing, native-store writer, approval or quality acceptance is
provided. Original human decisions and text/meaning reviews remain hash-bound;
generated wrappers perform identity conversion and structural checks only.
"""
import argparse
import copy
import json
from pathlib import Path

from dependency_proof import (file_ref,read_ref,dependency_fingerprints,make_audio_edit_inventory,
    apply_audio_edit_review,validate_audio_review_checkpoint)
from execution_audit import prepare as execution_prepare
from prepare_cut import prepare_broll
from check_native_apply import check,native_broll_inventory
from source_hash_session import fresh_hash_session

def _read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def _need(ok,message):
    if not ok:raise ValueError(message)

def _rebind_identical_audio_acceptance(checkpoint,put):
    """Bind an existing audio decision to new layout metadata, never new hearing.

    The unchanged owner validator must reject only the old acceptance binding;
    every non-clock acceptance field and direct audio reply must still match.
    The normal fresh guard independently proves the new native/audio mapping.
    """
    prior_ref=checkpoint.get('acceptanceEvidence')
    if prior_ref is None:return checkpoint
    acceptance=read_ref(prior_ref)
    old_clock=acceptance.get('clockMapHash');new_clock=checkpoint['clockMap']['sha256']
    if old_clock==new_clock:return checkpoint
    if (not isinstance(old_clock,str) or not old_clock.startswith('sha256:') or len(old_clock)!=71
        or any(char not in '0123456789abcdef' for char in old_clock[7:])):
        return checkpoint
    prior_checkpoint=put('audio-review-prior-clock-checkpoint.json',checkpoint)
    try:
        validate_audio_review_checkpoint(prior_checkpoint,checkpoint['audioGain1'],checkpoint['taskId'])
    except ValueError as error:
        if str(error)!='audio-review-real-current-user-acceptance-required':return checkpoint
    else:return checkpoint
    expected={'schema':'capcut-user-audio-review/v1','evidenceClass':'REAL_OBSERVATION',
        'basis':'USER_AUDIO_REVIEW','status':'ACCEPTED','claim':'audio-content-review-acceptance',
        'taskId':checkpoint['taskId'],'audioHash':checkpoint['audioGain1']['sha256'],
        'listeningCopyHash':checkpoint['listeningGain2']['sha256'],
        'feedbackInventoryHash':checkpoint['feedbackInventory']['sha256']}
    if any(acceptance.get(key)!=value for key,value in expected.items()):return checkpoint
    quote=acceptance.get('userQuote')
    if not isinstance(quote,str) or not quote.strip():return checkpoint
    reply=read_ref(acceptance.get('userReply'))
    if (reply.get('evidenceClass')!='REAL_OBSERVATION' or reply.get('source')!='DIRECT_USER_MESSAGE'
        or reply.get('reviewKind')!='AUDIO_CONTENT' or not isinstance(reply.get('sourceRef'),str)
        or not reply['sourceRef'].strip() or reply.get('message')!=quote):return checkpoint
    rebound={**copy.deepcopy(acceptance),'clockMapHash':new_clock,
        'priorAcceptanceEvidence':copy.deepcopy(prior_ref),'oldClockHash':old_clock,
        'currentClockMap':copy.deepcopy(checkpoint['clockMap']),
        'newUserDecision':False,'bindingBasis':'IDENTICAL_ACCEPTED_AUDIO'}
    result=copy.deepcopy(checkpoint)
    result['acceptanceEvidence']=put('audio-acceptance-clock-binding.json',rebound)
    result['bindingBasis']='IDENTICAL_ACCEPTED_AUDIO'
    result['newUserDecision']=False
    return result

def _destination_contract(inp,decision,compiled_manifest,producer):
    """Preserve CREATE default or bind the explicit existing-owned revision."""
    from native_revision import OPERATION,load_baseline
    destination=Path(inp.get('destinationPath',''))
    operation=inp.get('destinationOperation','CREATE_SEPARATE_NEW_PROJECT')
    _need(destination.is_absolute(),'review-absolute-destination-required')
    if operation=='CREATE_SEPARATE_NEW_PROJECT':
        _need(not destination.exists(),'review-new-destination-required')
        _need(compiled_manifest.get('identityMode','CREATE_NEW')=='CREATE_NEW'
            and producer.get('project',{}).get('revisionIdentity') is None,
            'review-revision-compile-cannot-select-create')
        return {'path':str(destination),'projectId':compiled_manifest['projectId'],
            'timelineId':compiled_manifest['timelineId'],'operation':operation,
            'overwriteExisting':False},{}
    _need(operation==OPERATION,'review-destination-operation-unsupported')
    ref=inp.get('revisionBaseline');baseline=load_baseline(ref,current=True)
    _need(compiled_manifest.get('identityMode')=='OWNED_REVISION'
        and producer.get('project',{}).get('revisionIdentity')==ref,
        'review-owned-compiled-baseline-binding')
    _need(str(destination)==baseline['destinationPath']
        and all(compiled_manifest.get(k)==baseline.get(k) for k in ('name','projectId','timelineId')),
        'review-owned-existing-identity-binding')
    _need(decision.get('operation')==OPERATION and decision.get('revisionBaseline')==ref
        and all(decision.get(k)==baseline[k] for k in ('projectId','timelineId')),
        'review-owned-original-decision-binding')
    fields={'claim':'review-draft-native-update-owned','operation':OPERATION,
        'name':baseline['name'],'rootIndexSHA256':baseline['rootIndexSHA256'],
        'expectedFiles':copy.deepcopy(baseline['expectedFiles'])}
    return {'path':str(destination),'name':baseline['name'],'projectId':baseline['projectId'],
        'timelineId':baseline['timelineId'],'operation':OPERATION,
        'overwriteExisting':True,'revisionBaseline':copy.deepcopy(ref)},fields

def _prepare(compiled,audio,review_input,newout):
    """Return prepared paths/status; newout must not exist and is task-local."""
    from native_timeline import validate_compiled
    compiled=Path(compiled).resolve();audio=Path(audio).resolve();out=Path(newout).absolute()
    _need(not out.exists(),'review-output-already-exists')
    _need(not out.is_symlink() and not any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in out.parents),'review-output-linked')
    parts=tuple(p.casefold() for p in out.parts)
    _need('com.lveditor.draft' not in parts,'review-output-cannot-be-native-store')
    _need(not any(parts[i:i+2]==('.codex','skills') for i in range(len(parts)-1)),
        'review-output-cannot-be-instruction-store')
    inp=_read(review_input) if isinstance(review_input,(str,Path)) else copy.deepcopy(review_input)
    _need(inp.get('schema')=='capcut-review-draft-input/v1','review-input-schema')
    validate_compiled(compiled)
    compiled_manifest=_read(compiled/'compiled-manifest.json');producer=_read(compiled/'plan.json')
    native_path=compiled/'files/draft_content.json';native=_read(native_path)
    native_ref=file_ref(native_path);audio_ref=file_ref(audio);plan_hash='sha256:'+compiled_manifest['planSHA256']
    task=inp.get('taskId');destination=Path(inp.get('destinationPath',''))
    _need(isinstance(task,str) and bool(task.strip()),'review-task-id')
    decision=read_ref(inp.get('decision'))
    _need(decision.get('schema')=='capcut-review-draft-decision/v1' and decision.get('evidenceClass')=='REAL_OBSERVATION'
        and decision.get('authority')=='explicit-user-request' and decision.get('mode')=='REVIEW_DRAFT'
        and isinstance(decision.get('userQuote'),str) and bool(decision['userQuote'].strip()),'review-original-explicit-decision-required')
    for key,value in {'taskId':task,'destinationPath':str(destination),'projectName':compiled_manifest['name']}.items():
        _need(decision.get(key)==value,'review-decision-'+key)
    destination_record,authority_fields=_destination_contract(inp,decision,compiled_manifest,producer)
    _need(set(decision.get('sourceIds',[]))=={s['sourceId'] for s in compiled_manifest['sources']},'review-decision-source-scope')
    semantic=read_ref(inp.get('captionReview'))
    _need(semantic.get('schema')=='capcut-caption-preparation-review/v1' and semantic.get('evidenceClass')=='REAL_OBSERVATION'
        and semantic.get('status')=='PASS' and semantic.get('basis') in ('SUPPORTED_TEXT_REVIEW','HUMAN_TEXT_REVIEW')
        and bool(semantic.get('reviewer')) and bool(semantic.get('observation')) and semantic.get('planHash')==plan_hash,
        'review-actual-text-review-required')
    _need(semantic.get('styleProfile')==inp.get('styleProfile') and bool(semantic.get('styleObservation')),'review-style-review-binding')
    read_ref(inp.get('styleProfile'));read_ref(semantic.get('acceptedLockBaseline'))
    projection=read_ref(inp.get('audioProjection'))
    _need(projection.get('evidenceClass')=='REAL_OBSERVATION' and projection.get('status')=='PASS_STRUCTURAL_NOT_HEARD'
        and projection.get('planHash')==plan_hash and projection.get('audioHash')==audio_ref['sha256']
        and projection.get('mainPieces')==producer['mainPieces'] and projection.get('gain')==1
        and bool(projection.get('reviewer')) and bool(projection.get('observation')),'review-audio-projection-binding')
    probe=read_ref(inp.get('sourceProbe'))
    _need(probe.get('status') in ('PASS_IDENTITY_NOT_HEARD','FRESH_FULL_HASH_AND_FFPROBE_PASS_NOT_HEARD','PASS') and isinstance(probe.get('sources'),list),'review-current-source-probe-required')
    source_map={s['sourceId']:{**s,'sha256':'sha256:'+s['sha256'].removeprefix('sha256:')} for s in compiled_manifest['sources']}
    object_map={o['id']:o for o in compiled_manifest['objects']}
    expected_cues={c['id']:c for c in producer['captions']}
    reviewed_cues=semantic.get('cues',[])
    _need(len(reviewed_cues)==len(expected_cues) and {c.get('id') for c in reviewed_cues}==set(expected_cues),'review-text-cue-coverage')
    words=[]
    for word in semantic['words']:
        item=copy.deepcopy(word);_need(item.get('sourceId') in source_map,'review-word-source-id')
        item['sourceId']=source_map[item['sourceId']]['materialId'];words.append(item)
    cues=[]
    for row in reviewed_cues:
        cue=expected_cues[row['id']]
        _need(row.get('rawWordIds')==cue['rawWordIds'] and row.get('nativeText')==cue['text'],'review-reviewed-caption-mismatch')
        cues.append({'segmentId':object_map[row['id']]['segmentId'],'rawWordIds':row['rawWordIds'],'nativeText':row['nativeText']})
    caption_plan={'mainTrackId':compiled_manifest['trackIds']['main'],'words':words,'cues':cues,
        'protectedSpans':copy.deepcopy(semantic['protectedSpans']),
        'acceptedLockBaseline':semantic['acceptedLockBaseline'],
        'semanticReview':{'basis':'whole-transcript-semantic-review','coveredWordIds':[w['id'] for w in words]}}
    for field in ('supersededLocks','preservedEnumerationLeadIns'):
        if field in semantic:caption_plan[field]=copy.deepcopy(semantic[field])
    for row in caption_plan.get('preservedEnumerationLeadIns',[]):
        for field in ('segmentId','contentSegmentId'):
            _need(row[field] in object_map,'review-enumeration-logical-id')
            row[field]=object_map[row[field]]['segmentId']
    main_id=caption_plan['mainTrackId'];main=next(t for t in native['tracks'] if t['id']==main_id)
    bound={'nativeHash':native_ref['sha256'],'audioHash':audio_ref['sha256']}
    # Subsequent output is task-local preparation, never native-store mutation.
    out.mkdir(parents=True)
    def put(name,data):
        path=out/name
        with path.open('x',encoding='utf-8') as f:f.write(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        return file_ref(path)
    def proof(name,claim,basis,reviewer,observation,**fields):
        return put(name,{'evidenceClass':'REAL_OBSERVATION','status':'PASS','basis':basis,
            'reviewer':reviewer,'observation':observation,'claim':claim,**bound,**fields})
    authority_record={'evidenceClass':'REAL_OBSERVATION','authority':'explicit-user-request',
        'claim':'review-draft-native-apply','mode':'REVIEW_DRAFT','taskId':task,**bound,
        'destinationPath':str(destination),'projectId':compiled_manifest['projectId'],'timelineId':compiled_manifest['timelineId'],
        'userQuote':decision['userQuote'],'originalDecision':inp['decision'],
        'allowModelWordIntervalOverlap':decision.get('allowModelWordIntervalOverlap') is True,
        'bindingBasis':'MECHANICAL_BINDING_OF_EXISTING_EXPLICIT_TASK_DECISION'}
    for field in ('scopeInterpretation','provisionalCutScope','nativeApplyPrerequisites'):
        if field in decision:authority_record[field]=copy.deepcopy(decision[field])
    authority_record.update(authority_fields)
    authority=put('review-authority.json',authority_record)
    scope_sources=[]
    for source in source_map.values():
        matches=[s for s in probe['sources'] if s.get('path')==source['path'] and ('sha256:'+str(s.get('sha256','')).removeprefix('sha256:'))==source['sha256']]
        _need(len(matches)==1,'review-probe-source-identity')
        observed=matches[0];actual=observed.get('actualDurationTicks',observed.get('durationTicks'))
        _need(actual==source['durationTicks'],'review-probe-native-source-duration')
        scope_sources.append({'sourceId':source['sourceId'],'materialId':source['materialId'],'path':source['path'],
            'sha256':source['sha256'],'actualDurationTicks':actual,'actualDurationEvidenceRef':inp['sourceProbe']})
    scope=put('source-scope.json',{'schema':'capcut-review-draft-source-scope/v1','evidenceClass':'REAL_OBSERVATION',
        'authority':'explicit-user-request','taskId':task,**bound,'userQuote':decision['userQuote'],
        'originalDecision':inp['decision'],'sources':scope_sources})
    caption_plan['semanticReview']['evidence']=proof('caption-policy-binding.json','caption-policy-review',semantic['basis'],
        semantic['reviewer'],semantic['observation'],originalTextReview=inp['captionReview'],
        coveredWordIds=[w['id'] for w in words],cueGroups=cues,protectedSpans=caption_plan['protectedSpans'])
    clock=proof('prepared-audio-clock.json','audio-clock-binding','SUPPORTED_STRUCTURAL_REVIEW',projection['reviewer'],
        projection['observation'],mainTrackId=main_id,mainSourcePieces=main['segments'],audioProjection=inp['audioProjection'],
        doesNotClaimHearing=True)
    fingerprints=dependency_fingerprints(native,audio,main_id,scopes=('captionStyle',))
    style=proof('style-binding.json','caption-style-binding',semantic['basis'],semantic['reviewer'],semantic['styleObservation'],
        taskId=task,styleProfile=inp['styleProfile'],captionStyleFingerprint=fingerprints['captionStyle'],
        originalTextReview=inp['captionReview'],nativeFitAndGlyphs='PENDING')
    audit=execution_prepare(native_path,audio,caption_plan,inp['pauseProfile'])
    audit['pauseDecisions']=[{'id':row['id'],'status':'PENDING','decision':'UNREVIEWED'} for row in audit['pauseScan']['candidates']]
    execution=put('execution-audit.json',audit)
    manifest={'schema':'capcut-native-apply-evidence/v1','evidenceClass':'REAL_OBSERVATION','mode':'REVIEW_DRAFT',
        'branch':'CONTENT_EDIT','native':native_ref,'audio':audio_ref,'executionAudit':execution,
        'clockBinding':{'status':'PREPARED_EXACT_SOURCE_MAP','evidence':clock},
        'pacing':{'scope':'ALL_PAUSES','status':'PENDING','auditedScopes':['HEAD','INTERNAL','TAIL'],
            'criterion':{'minimumQuietDurationTicks':200000,'comparison':'STRICTLY_GREATER','auditScopes':['HEAD','INTERNAL','TAIL']},
            'intervals':copy.deepcopy(inp.get('pacingIntervals',[]))},
        'onsets':[{'segmentId':c['segmentId'],'startTick':next(s['target_timerange']['start'] for t in native['tracks'] for s in t['segments'] if s['id']==c['segmentId']),
            'rawWordIds':c['rawWordIds'],'status':'PENDING'} for c in cues],
        'reviewDraft':{'schema':'capcut-review-draft/v1','taskId':task,'authorityEvidence':authority,'sourceScope':scope,
            'styleEvidence':style,'projectMeta':file_ref(compiled/'files/draft_meta_info.json'),
            'destination':destination_record,'contentReview':copy.deepcopy(inp['contentReview'])}}
    supplied_audio=inp.get('audioReview',{})
    checkpoint={'schema':'capcut-audio-review-checkpoint/v1','taskId':task,
        'status':'ACCEPTED_BY_USER' if supplied_audio.get('acceptanceEvidence') is not None else 'PENDING_USER_AUDIO_REVIEW',
        'audioGain1':audio_ref,'clockMap':inp['audioProjection'],
        'bindingBasis':'SUPPLIED_USER_REVIEW_MECHANICAL_BINDING_NOT_NEW_HEARING'}
    for field in ('listeningGain2','gainReceipt','feedbackInventory','acceptanceEvidence'):
        checkpoint[field]=copy.deepcopy(supplied_audio.get(field))
    checkpoint=_rebind_identical_audio_acceptance(checkpoint,put)
    manifest['audioReviewCheckpoint']=put('audio-review-checkpoint.json',checkpoint)
    if inp.get('audioEditPolicy') is not None:
        edit_inventory=make_audio_edit_inventory(native_ref,audio_ref,execution,inp['audioEditPolicy'],source_map,file_ref(compiled/'plan.json'))
        if inp.get('audioEditReview') is not None:edit_inventory=apply_audio_edit_review(edit_inventory,inp['audioEditReview'])
        manifest['audioEditInventory']=put('audio-edit-inventory.json',edit_inventory)
    if producer.get('nativePhaseEvidence') is not None:manifest['nativePhaseEvidence']=producer['nativePhaseEvidence']
    if producer.get('broll'):
        reviewed=read_ref(inp.get('brollReview'))
        _need(reviewed.get('schema')=='capcut-broll-preparation-review/v1' and reviewed.get('evidenceClass')=='REAL_OBSERVATION'
            and reviewed.get('status')=='PASS' and reviewed.get('planHash')==plan_hash
            and bool(reviewed.get('reviewer')) and bool(reviewed.get('observation')),'review-broll-meaning-review-required')
        source_reviews={s['sourceId']:s for s in reviewed['sources']}
        placement_reviews={p['id']:p for p in reviewed['placements']}
        _need(set(placement_reviews)=={p['id'] for p in producer['broll']},'review-broll-placement-coverage')
        used_sources={p['sourceId'] for p in producer['broll']}
        _need(set(source_reviews)==used_sources,'review-broll-source-coverage')
        base=copy.deepcopy(native)
        for track in base['tracks']:
            if track.get('type')=='video' and track['id']!=main_id:track['segments']=[]
        base_ref=put('broll-base.json',base);base_ref['durationTicks']=native['duration']
        bplan={'schemaVersion':'capcut-broll-plan/v1','tickRate':1000000,'mode':'REVIEW_DRAFT','reviewDraftAuthority':authority,
            'coverageMode':'SPARSE','sourceReuseMode':'NO_SOURCE_REPEAT','baseSnapshot':base_ref,
            'contentCaptionCheckpoint':'PROVISIONAL_PREPARED','baseCheckpointEvidenceRef':clock['path'],
            'baseCheckpointEvidenceBasis':'STRUCTURAL_PREPARATION',
            'captionCues':[{'id':object_map[c['id']]['segmentId'],'startTick':c['startTicks'],'endTick':c['endTicks']} for c in producer['captions']],
            'existingArollCuts':sorted({0,native['duration'],*(p['target_timerange']['start'] for p in main['segments'])}),
            'cadenceReview':{'reviewed':True,'evidenceRef':inp['brollReview']['path'],'reason':reviewed['observation']},
            'sources':[],'sourceUsageReview':{'reviewed':True,'evidenceRef':inp['brollReview']['path'],
                'evidenceBasis':reviewed['evidenceBasis'],'scope':'WHOLE_CURRENT_TIMELINE','baseSnapshotSha256':base_ref['sha256'],'existingPlacements':[]},'placements':[]}
        if manifest.get('nativePhaseEvidence') is not None:bplan['nativePhaseEvidence']=manifest['nativePhaseEvidence']
        for sid in sorted(used_sources):
            s=source_map[sid];review=source_reviews[sid]
            bplan['sources'].append({'id':sid,'nativeMaterialId':s['materialId'],'path':s['path'],'sha256':s['sha256'],
                'actualDurationTicks':s['durationTicks'],'actualDurationEvidenceRef':inp['sourceProbe']['path'],
                **{k:copy.deepcopy(review[k]) for k in ('permitted','rightsEvidenceRef','sourceOrigin','voiceClassification','classificationReview')}})
        for row in producer['broll']:
            review=placement_reviews[row['id']];obj=object_map[row['id']]
            end=row.get('targetOutTicks',row['targetInTicks']+row['sourceOutTicks']-row['sourceInTicks'])
            bplan['placements'].append({'id':obj['segmentId'],'sourceId':row['sourceId'],'sourceInTick':row['sourceInTicks'],
                'sourceOutTick':row['sourceOutTicks'],'startTick':row['targetInTicks'],'endTick':end,
                'startCaptionId':object_map[review['startCaptionId']]['segmentId'],'lastCaptionId':object_map[review['lastCaptionId']]['segmentId'],
                'meaningReview':copy.deepcopy(review['meaningReview']),'paddedToTenSeconds':False,'muteSourceAudio':True,'preserveMainVideo':True,
                'eligibleSourceReview':{'reviewed':True,'evidenceRef':inp['brollReview']['path'],'evidenceBasis':reviewed['evidenceBasis'],
                    'scope':'ALL_SUPPLIED_SOURCES','exhaustive':True,'baseSnapshotSha256':base_ref['sha256'],
                    'sources':copy.deepcopy(review['eligibleSources'])}})
        outputs=prepare_broll(bplan)
        for name,body in outputs.items():put(name,json.loads(body))
        bplan_ref=put('broll-plan.json',bplan)
        actual=native_broll_inventory(native,main_id,manifest.get('nativePhaseEvidence'))
        visual=proof('broll-preparation-binding.json','broll-whole-timeline-preparation','SUPPORTED_STRUCTURAL_REVIEW',
            reviewed['reviewer'],reviewed['observation'],mainTrackId=main_id,planHash=bplan_ref['sha256'],actualInventory=actual,
            wholeTimelineInventoryComplete=True,knownSourceLineageReviewed=True,
            inventoryObservation='All compiled supporting-video objects match the complete provided plan',
            lineageObservation='Original supplied file identities remain bound to source scope and provided lineage review',
            originalMeaningReview=inp['brollReview'],nativeAppearance='PENDING')
        manifest['bRollAudit']=put('broll-audit.json',{'schema':'capcut-native-broll-audit/v1','nativeHash':native_ref['sha256'],
            'mainTrackId':main_id,'plan':bplan_ref,'reviewEvidence':visual})
    manifest_ref=put('review-manifest.json',manifest)
    result=check(manifest);result_ref=put('guard-result.json',result)
    result_record={'schema':'capcut-review-draft-preparation/v1','status':result['status'],'manifest':manifest_ref,
        'guardResult':result_ref,'compiled':str(compiled),'audio':audio_ref,'input':copy.deepcopy(inp),
        'nativeStoreWrites':0,'heardAudio':False,'finalAcceptance':False}
    receipt=put('preparation-receipt.json',result_record)
    return {'status':result['status'],'passed':result.get('passed',False),'manifest':manifest_ref,'guardResult':result_ref,
        'receipt':receipt,'finalAcceptance':False,'nativeStoreWrites':0}

def prepare(compiled,audio,review_input,newout):
    # Preparation may reuse its own verified sources; check() always nests a
    # distinct fresh verification, so a writer never consumes preparation cache.
    with fresh_hash_session():return _prepare(compiled,audio,review_input,newout)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('compiled','audio','input','output'):p.add_argument('--'+arg,required=True,type=Path)
    args=p.parse_args();result=prepare(args.compiled,args.audio,args.input,args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
