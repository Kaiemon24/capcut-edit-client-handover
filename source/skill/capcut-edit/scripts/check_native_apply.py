"""Cooperative pre-write consistency guard; never hears, approves or writes a draft.

Run immediately before a filesystem draft apply, in addition to the SDK's editor,
version and unchanged-file guards. A PASS is prerequisite consistency, not native
playback acceptance or authentication of a supplied human review.
"""
import argparse
import hashlib
import json
from pathlib import Path
import wave
from source_hash_session import digest as _verified_digest,fresh_hash_session,SourceHashDrift
from execution_audit import load_ref,scan_audio,cut_inventory,check_caption_plan
from dependency_proof import (validate_native_phase,validate_adoption,dependency_fingerprints,
    validate_audio_review_checkpoint,speech_checkpoint_required,validate_audio_edit_inventory)

SCOPES = ['HEAD', 'INTERNAL', 'TAIL']
BASES = {'HUMAN_LISTENING', 'SUPPORTED_AUDIO_REVIEW'}

def digest(path):
    return _verified_digest(path)

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def integer(value):
    return type(value) is int

def native_broll_inventory(draft, main_track_id, native_phase_evidence=None):
    """Derive every supporting video object; unsupported roles never mean absent."""
    if not isinstance(draft,dict):raise ValueError('broll-native-object-required')
    tracks=draft.get('tracks')
    if not isinstance(tracks,list) or not isinstance(main_track_id,str) or not main_track_id:
        raise ValueError('broll-bound-main-track-required')
    main=[t for t in tracks if isinstance(t,dict) and t.get('id')==main_track_id]
    if len(main)!=1 or main[0].get('type')!='video':raise ValueError('broll-bound-main-track-required')
    nested=('sub_drafts','subdrafts','drafts','children','subdraft','draft','tracks')
    if any(draft.get(k) for k in nested if k!='tracks'):raise ValueError('broll-unsupported-nesting')
    materials=draft.get('materials',{})
    if not isinstance(materials,dict):raise ValueError('broll-native-materials-required')
    videos=materials.get('videos',[])
    if not isinstance(videos,list):raise ValueError('broll-video-material-inventory')
    by_material={}
    for material in videos:
        ident=material.get('id') if isinstance(material,dict) else None
        if not isinstance(ident,str) or not ident or (ident in by_material and by_material[ident]!=material):raise ValueError('broll-conflicting-or-missing-material-id')
        by_material[ident]=material
    if materials.get('drafts') or materials.get('sub_drafts'):raise ValueError('broll-unsupported-nesting')
    speeds={}
    if not isinstance(materials.get('speeds',[]),list):raise ValueError('broll-speed-material-inventory')
    for speed in materials.get('speeds',[]):
        ident=speed.get('id') if isinstance(speed,dict) else None
        if not isinstance(ident,str) or not ident or (ident in speeds and speeds[ident]!=speed):raise ValueError('broll-conflicting-speed-material-id')
        speeds[ident]=speed
    seen_segments=set();seen_tracks=set();result=[];source_hashes={}
    for track in tracks:
        if not isinstance(track,dict) or track.get('type') not in ('video','audio','text','filter','effect','sticker','adjust','mask'):
            raise ValueError('broll-unknown-track-role')
        track_id=track.get('id')
        if track_id is not None:
            if not isinstance(track_id,str) or not track_id or track_id in seen_tracks:raise ValueError('broll-duplicate-or-missing-track-id')
            seen_tracks.add(track_id)
        segments=track.get('segments')
        if not isinstance(segments,list) or any(track.get(k) for k in nested):raise ValueError('broll-unsupported-nesting')
        for segment in segments:
            ident=segment.get('id') if isinstance(segment,dict) else None
            if not isinstance(ident,str) or not ident or ident in seen_segments:raise ValueError('broll-duplicate-or-missing-segment-id')
            seen_segments.add(ident)
            if any(segment.get(k) for k in nested) or segment.get('segments'):raise ValueError('broll-unsupported-nesting')
            if track.get('type')!='video':
                if segment.get('material_id') in by_material:raise ValueError('broll-video-material-on-unknown-role')
                continue
            if track_id==main_track_id:continue
            if not isinstance(track_id,str) or not track_id:raise ValueError('broll-support-track-id-required')
            material=by_material.get(segment.get('material_id'))
            if material is None or material.get('type')!='video' or any(material.get(k) for k in nested) or any(material.get(k) for k in ('is_compound','is_draft','is_nested')):
                raise ValueError('broll-unmapped-or-nested-video-material')
            path=Path(material.get('path',''))
            if not path.is_absolute() or not path.is_file() or path.is_symlink() or path.suffix.lower() not in ('.mp4','.mov','.mkv','.m4v'):
                raise ValueError('broll-native-source-file-required')
            if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in path.parents):raise ValueError('broll-linked-native-source')
            source=segment.get('source_timerange');target=segment.get('target_timerange')
            if not isinstance(source,dict) or not isinstance(target,dict):raise ValueError('broll-source-target-windows-required')
            a,length=source.get('start'),source.get('duration');x,target_length=target.get('start'),target.get('duration')
            if not all(integer(v) for v in (a,length,x,target_length)) or min(a,x)<0 or min(length,target_length)<=0 or x+target_length>draft.get('duration',-1):
                raise ValueError('broll-normal-speed-positive-windows-required')
            if target_length!=length:
                validate_native_phase(native_phase_evidence,ident,material['id'],a,a+length,x,x+target_length,currentFps=draft.get('fps'))
            speed=segment.get('speed');volume=segment.get('volume')
            if type(speed) not in (int,float) or speed!=1 or type(volume) not in (int,float) or volume!=0 or segment.get('reverse') or segment.get('is_reverse'):
                raise ValueError('broll-normal-speed-silent-required')
            refs=segment.get('extra_material_refs',[])
            if not isinstance(refs,list):raise ValueError('broll-unsupported-material-references')
            for ref in refs:
                speed_material=speeds.get(ref)
                if speed_material is not None and (type(speed_material.get('speed')) not in (int,float) or speed_material['speed']!=1 or speed_material.get('curve_speed')):
                    raise ValueError('broll-normal-speed-silent-required')
            resolved=path.resolve()
            if resolved not in source_hashes:source_hashes[resolved]=digest(path)
            result.append({'segmentId':ident,'trackId':track_id,'materialId':material['id'],
                'sourceIdentitySha256':source_hashes[resolved],'sourceInTick':a,'sourceOutTick':a+length,
                'startTick':x,'endTick':x+target_length,'speed':speed,'volume':volume})
    return sorted(result,key=lambda r:(r['startTick'],r['endTick'],r['segmentId']))

def check_broll_audit(draft, manifest, main_track_id, native_hash, evidence, require):
    """Recompute a provided plan and bind both native inventories before a write."""
    actual=native_broll_inventory(draft,main_track_id,manifest.get('nativePhaseEvidence'))
    if not actual and manifest.get('bRollAudit') is None:return
    audit=load_ref(manifest.get('bRollAudit'))
    require(audit.get('schema')=='capcut-native-broll-audit/v1','broll-audit-schema')
    require(audit.get('nativeHash')==native_hash and audit.get('mainTrackId')==main_track_id,'broll-audit-stale-revision')
    plan_ref=audit.get('plan');plan=load_ref(plan_ref)
    provisional=manifest.get('mode','FINAL_ACCEPTANCE')=='REVIEW_DRAFT'
    require(plan.get('mode','FINAL_ACCEPTANCE')==manifest.get('mode','FINAL_ACCEPTANCE'),'broll-stage-binding')
    if provisional:
        require(plan.get('reviewDraftAuthority')==manifest.get('reviewDraft',{}).get('authorityEvidence'),'broll-review-draft-authority-binding')
    require(plan.get('nativePhaseEvidence')==manifest.get('nativePhaseEvidence'),'broll-native-phase-evidence-binding')
    from prepare_cut import prepare_broll
    outputs=prepare_broll(plan)
    report=json.loads(outputs['broll-report.json']);spec=json.loads(outputs['broll-spec.json'])
    require(report.get('status')=='PREPARED_ONLY' and spec.get('status')=='PREPARED_ONLY'
        and report.get('sourceUsageConflicts')==[] and report.get('providedWholeTimelineUsageMechanicallyConflictFree') is True,'broll-recomputed-plan-held')
    sources={s['id']:s for s in plan['sources']}
    def expected(rows, existing=False):
        result=[];seen=set()
        for row in rows:
            ident=row['id'] if existing else row['placementId']
            if ident in seen:raise ValueError('broll-duplicate-plan-placement')
            seen.add(ident)
            result.append({'segmentId':ident,'sourceIdentitySha256':sources[row['sourceId']]['sha256'],
                'sourceInTick':row['sourceInTick'],'sourceOutTick':row['sourceOutTick'],
                'startTick':row['startTick'],'endTick':row['endTick'],'speed':1,'volume':0})
        return sorted(result,key=lambda r:(r['startTick'],r['endTick'],r['segmentId']))
    def comparable(rows):return [{k:v for k,v in row.items() if k not in ('trackId','materialId')} for row in rows]
    require(comparable(actual)==expected(report['sourceUsageLedger']),'broll-whole-native-placement-mismatch')
    base=load_ref(plan['baseSnapshot'])
    require(base.get('duration')==draft.get('duration')==plan['baseSnapshot'].get('durationTicks'),'broll-base-duration-mismatch')
    base_inventory=native_broll_inventory(base,main_track_id,manifest.get('nativePhaseEvidence'))
    require(comparable(base_inventory)==expected(plan['sourceUsageReview']['existingPlacements'],True),'broll-base-existing-inventory-mismatch')
    def main_track(value):return next(t for t in value['tracks'] if t.get('id')==main_track_id)
    require(main_track(base)==main_track(draft),'broll-main-track-changed')
    main_material_ids=set()
    for segment in main_track(base)['segments']:
        refs=segment.get('extra_material_refs',[])
        if not isinstance(refs,list) or any(not isinstance(i,str) or not i for i in refs):raise ValueError('broll-main-material-reference-required')
        main_material_ids.update(refs);main_material_ids.add(segment.get('material_id'))
    def main_materials(value):
        selected={}
        for kind,rows in value.get('materials',{}).items():
            if not isinstance(rows,list):continue
            for material in rows:
                if not isinstance(material,dict) or material.get('id') not in main_material_ids:continue
                key=(kind,material['id'])
                if key in selected and selected[key]!=material:raise ValueError('broll-conflicting-main-material-id')
                selected[key]=material
        return selected
    require(main_materials(base)==main_materials(draft),'broll-main-source-material-changed')
    def caption_clock(value):
        rows=[{'id':s['id'],'startTick':s['target_timerange']['start'],'endTick':s['target_timerange']['start']+s['target_timerange']['duration']}
            for t in value['tracks'] if t.get('type')=='text' for s in t['segments']]
        return sorted(rows,key=lambda r:(r['startTick'],r['endTick'],r['id']))
    planned_clock=sorted([{'id':r['id'],'startTick':r['startTick'],'endTick':r['endTick']} for r in plan['captionCues']],key=lambda r:(r['startTick'],r['endTick'],r['id']))
    require(caption_clock(base)==caption_clock(draft)==planned_clock,'broll-base-caption-clock-mismatch')
    review=load_ref(audit.get('reviewEvidence'))
    require(isinstance(review.get('inventoryObservation'),str) and bool(review['inventoryObservation'].strip())
        and isinstance(review.get('lineageObservation'),str) and bool(review['lineageObservation'].strip()),'broll-inventory-lineage-observation-required')
    evidence(audit.get('reviewEvidence'),'broll-whole-timeline-preparation' if provisional else 'broll-whole-timeline-review',
        bases={'SUPPORTED_STRUCTURAL_REVIEW'} if provisional else {'HUMAN_VISUAL_REVIEW','SUPPORTED_VISUAL_REVIEW'},
        mainTrackId=main_track_id,planHash=plan_ref['sha256'],actualInventory=actual,
        wholeTimelineInventoryComplete=True,knownSourceLineageReviewed=True)

def check_review_draft(manifest,draft,bound,errors,audio_review=None,audio_edit_review=None):
    """Explicit new-project or exact owned revision; uncertain quality stays visible."""
    def need(ok,message):
        if not ok:errors.append(message)
    pending={'onsets':[],'pauseCandidates':[],'originalPauseIntervals':[],
             'content':[],'nativePlayback':'PENDING','nativePersistence':'PENDING'}
    def evidence(ref,claim,bases=None,**expected):
        try:data=load_ref(ref)
        except (OSError,ValueError,TypeError,KeyError) as exc:
            errors.append(claim+'-evidence-invalid: '+str(exc));return
        need(data.get('evidenceClass')=='REAL_OBSERVATION',claim+'-synthetic-evidence')
        need(data.get('status')=='PASS',claim+'-review-pending')
        need(data.get('basis') in (bases or BASES),claim+'-basis')
        need(bool(data.get('reviewer')) and bool(data.get('observation')),claim+'-observation-missing')
        need(data.get('claim')==claim,claim+'-claim')
        need(data.get('nativeHash')==bound['native'] and data.get('audioHash')==bound['audio'],claim+'-stale-revision')
        for key,value in expected.items():need(data.get(key)==value,claim+'-'+key)
    try:
        review=manifest.get('reviewDraft',{})
        need(review.get('schema')=='capcut-review-draft/v1','review-draft-schema')
        task=review.get('taskId');need(isinstance(task,str) and bool(task.strip()),'review-draft-task-id')
        destination=review.get('destination',{});path=Path(destination.get('path',''))
        owned=destination.get('operation')=='READDRAFT_UPDATE_OWNED'
        baseline=None
        if owned:
            from native_revision import load_baseline
            baseline=load_baseline(destination.get('revisionBaseline'),current=True)
            need(path.is_absolute() and path.is_dir()
                and str(path)==baseline['destinationPath'],'review-draft-owned-destination-required')
            need(destination.get('overwriteExisting') is True
                and destination.get('name')==baseline['name']
                and destination.get('projectId')==baseline['projectId']
                and destination.get('timelineId')==baseline['timelineId']
                and draft.get('name')==baseline['name'],'review-draft-owned-identity-binding')
        else:
            need(path.is_absolute() and not path.exists() and bool(path.name),'review-draft-new-destination-required')
        need(not any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (path,*path.parents)),'review-draft-linked-destination')
        if not owned:
            need(destination.get('operation')=='CREATE_SEPARATE_NEW_PROJECT' and destination.get('overwriteExisting') is False,'review-draft-no-existing-project-edit')
        need(isinstance(destination.get('projectId'),str) and bool(destination['projectId']),'review-draft-project-id')
        need(destination.get('timelineId')==draft.get('id') and bool(draft.get('id')),'review-draft-timeline-id')
        if review.get('projectMeta') is not None:
            meta=load_ref(review['projectMeta']);need(meta.get('draft_id')==destination.get('projectId'),'review-draft-project-metadata-id')
        authority=load_ref(review.get('authorityEvidence'))
        need(authority.get('evidenceClass')=='REAL_OBSERVATION' and authority.get('authority')=='explicit-user-request'
            and authority.get('claim')==('review-draft-native-update-owned' if owned else 'review-draft-native-apply') and authority.get('mode')=='REVIEW_DRAFT'
            and isinstance(authority.get('userQuote'),str) and bool(authority['userQuote'].strip()),'review-draft-exact-explicit-authority')
        for key,value in {'taskId':task,'nativeHash':bound['native'],'audioHash':bound['audio'],
                          'destinationPath':str(path),'projectId':destination.get('projectId'),
                          'timelineId':destination.get('timelineId')}.items():need(authority.get(key)==value,'review-draft-authority-'+key)
        if owned:
            for key,value in {'operation':'READDRAFT_UPDATE_OWNED','name':baseline['name'],
                'rootIndexSHA256':baseline['rootIndexSHA256'],
                'expectedFiles':baseline['expectedFiles']}.items():
                need(authority.get(key)==value,'review-draft-owned-authority-'+key)
        audit=load_ref(manifest.get('executionAudit'))
        need(audit.get('schema')=='capcut-execution-audit/v1','execution-audit-schema')
        need(audit.get('nativeHash')==bound['native'] and audit.get('audioHash')==bound['audio'],'execution-audit-stale-revision')
        plan=audit['captionPlan'];main_id=plan['mainTrackId'];baseline=load_ref(plan.get('acceptedLockBaseline'))
        errors.extend(check_caption_plan(draft,plan,baseline))
        evidence(plan.get('semanticReview',{}).get('evidence'),'caption-policy-review',
            bases={'HUMAN_TEXT_REVIEW','SUPPORTED_TEXT_REVIEW'},coveredWordIds=[w['id'] for w in plan['words']],
            cueGroups=plan['cues'],protectedSpans=plan['protectedSpans'])
        main=[t for t in draft['tracks'] if t.get('id')==main_id and t.get('type')=='video']
        need(len(main)==1,'review-draft-main-track')
        pieces=sorted(main[0]['segments'],key=lambda s:s['target_timerange']['start'])
        cursor=0
        for piece in pieces:
            src,dst=piece['source_timerange'],piece['target_timerange']
            need(type(piece.get('speed')) in (int,float) and piece.get('speed')==1 and not piece.get('reverse') and not piece.get('is_reverse'),'review-draft-normal-speed')
            need(type(piece.get('volume')) in (int,float) and piece.get('volume')==1,'review-draft-original-main-gain')
            need(all(integer(x) for x in (src['start'],src['duration'],dst['start'],dst['duration']))
                and src['start']>=0 and min(src['duration'],dst['duration'])>0,'review-draft-positive-source-clock')
            need(dst['start']==cursor,'review-draft-main-contiguous')
            cursor=dst['start']+dst['duration']
            if src['duration']!=dst['duration']:
                validate_native_phase(manifest.get('nativePhaseEvidence'),piece['id'],piece['material_id'],
                    src['start'],src['start']+src['duration'],dst['start'],cursor,currentFps=draft.get('fps'))
        need(cursor==draft['duration'],'review-draft-main-duration')
        if authority.get('allowModelWordIntervalOverlap') is True:
            scope=authority.get('provisionalCutScope',{})
            need(type(scope.get('mainPieces')) is int and scope['mainPieces']==len(pieces),'review-draft-overlap-piece-scope')
            need(type(scope.get('candidateDurationSeconds')) in (int,float)
                and round(scope['candidateDurationSeconds']*1000000)==draft['duration'],'review-draft-overlap-duration-scope')
            need(isinstance(authority.get('scopeInterpretation'),str) and bool(authority['scopeInterpretation'].strip()),'review-draft-overlap-scope-description')
            pending['provisionalScope']={'scopeInterpretation':authority.get('scopeInterpretation'),
                'provisionalCutScope':scope,'originalDecision':authority.get('originalDecision'),
                'scopeControlsStatus':'DECLARED_PREPARED_NOT_PHONETICALLY_VERIFIED'}
        scope=load_ref(review.get('sourceScope'))
        need(scope.get('schema')=='capcut-review-draft-source-scope/v1' and scope.get('evidenceClass')=='REAL_OBSERVATION'
            and scope.get('authority')=='explicit-user-request' and bool(scope.get('userQuote')),'review-draft-source-authority')
        for key,value in {'taskId':task,'nativeHash':bound['native'],'audioHash':bound['audio']}.items():need(scope.get(key)==value,'review-draft-source-'+key)
        sources=scope.get('sources',[]);need(isinstance(sources,list) and bool(sources),'review-draft-source-inventory')
        by_source={s['materialId']:s for s in sources}
        need(len(by_source)==len(sources),'review-draft-duplicate-source')
        media={}
        for kind in ('videos','audios'):
            for material in draft.get('materials',{}).get(kind,[]):
                if material['id'] in media and media[material['id']]!=material:raise ValueError('conflicting source material')
                media[material['id']]=material
        used={s['material_id'] for t in draft['tracks'] for s in t.get('segments',[]) if s.get('material_id') in media}
        need(used==set(by_source),'review-draft-source-scope-coverage')
        source_hashes={}
        for ident,row in by_source.items():
            material=media.get(ident,{});p=Path(row.get('path',''))
            need(p.is_absolute() and p.is_file() and not p.is_symlink() and material.get('path')==str(p),'review-draft-source-path')
            need(not any(q.is_symlink() or (hasattr(q,'is_junction') and q.is_junction()) for q in p.parents),'review-draft-linked-source')
            if p.is_absolute() and p.is_file():
                if str(p) not in source_hashes:source_hashes[str(p)]=digest(p)
                need(row.get('sha256')==source_hashes[str(p)],'review-draft-source-hash')
            need(integer(row.get('actualDurationTicks')) and row['actualDurationTicks']>0 and bool(row.get('actualDurationEvidenceRef')),'review-draft-source-actual-duration')
            probe=load_ref(row.get('actualDurationEvidenceRef'))
            need(probe.get('status') in ('PASS_IDENTITY_NOT_HEARD','FRESH_FULL_HASH_AND_FFPROBE_PASS_NOT_HEARD','PASS') and isinstance(probe.get('sources'),list),'review-draft-source-probe-status')
            observations=[s for s in probe.get('sources',[]) if s.get('path')==str(p) and ('sha256:'+str(s.get('sha256','')).removeprefix('sha256:'))==row.get('sha256')]
            need(len(observations)==1,'review-draft-source-probe-identity')
            if len(observations)==1:
                observed=observations[0]
                need(observed.get('actualDurationTicks',observed.get('durationTicks'))==row.get('actualDurationTicks')
                    and observed.get('unchangedStatBeforeAfter') is True and bool(observed.get('probeCommand')),'review-draft-source-probe-duration')
        for track in draft['tracks']:
            for segment in track.get('segments',[]):
                if segment.get('material_id') in by_source:
                    src=segment['source_timerange'];row=by_source[segment['material_id']]
                    need(0<=src['start']<src['start']+src['duration']<=row['actualDurationTicks'],'review-draft-source-bounds')
        pending['wordSourceCoverage']=[]
        for word in plan['words']:
            lo,hi=word['sourceStartTick'],word['sourceEndTick']
            need(word['sourceId'] in by_source and integer(lo) and integer(hi) and 0<=lo<hi,'review-draft-word-source')
            legs=[]
            for piece in pieces:
                if piece['material_id']!=word['sourceId']:continue
                src,dst=piece['source_timerange'],piece['target_timerange']
                a,b=max(lo,src['start']),min(hi,src['start']+src['duration'])
                if a<b:legs.append({'pieceId':piece['id'],'sourceStartTick':a,'sourceEndTick':b,
                    'outputStartTick':dst['start']+a-src['start'],'outputEndTick':dst['start']+b-src['start']})
            source_order=sorted(legs,key=lambda r:(r['sourceStartTick'],r['sourceEndTick'],r['pieceId']))
            duplicate=any(a['sourceEndTick']>b['sourceStartTick'] for a,b in zip(source_order,source_order[1:]))
            need(bool(legs) and not duplicate,'review-draft-word-source-empty-or-duplicated')
            removed=[];position=lo
            for leg in source_order:
                if position<leg['sourceStartTick']:removed.append({'startTick':position,'endTick':leg['sourceStartTick']})
                position=max(position,leg['sourceEndTick'])
            if position<hi:removed.append({'startTick':position,'endTick':hi})
            if removed:
                content_scope=review.get('contentReview',{})
                need(authority.get('allowModelWordIntervalOverlap') is True
                    and content_scope.get('status')=='PROVISIONAL_MODEL_ONLY'
                    and content_scope.get('wordTimingBasis')=='MODEL_ONLY','review-draft-word-overlap-explicit-model-authority-required')
            pending['wordSourceCoverage'].append({'wordId':word['id'],'sourceId':word['sourceId'],
                'originalSourceStartTick':lo,'originalSourceEndTick':hi,'retainedSourceLegs':legs,
                'removedSourceIntervals':removed,'duplicatedSourceLegs':duplicate,
                'status':'PENDING_AUDIO_CONTINUITY' if removed else 'FULL_INTERVAL_RETAINED_MODEL_TIMING_PENDING'})
        need(manifest.get('clockBinding',{}).get('status')=='PREPARED_EXACT_SOURCE_MAP','review-draft-clock-status')
        evidence(manifest.get('clockBinding',{}).get('evidence'),'audio-clock-binding',bases={'SUPPORTED_STRUCTURAL_REVIEW'},mainTrackId=main_id,mainSourcePieces=pieces)
        style=load_ref(review.get('styleEvidence'));load_ref(style.get('styleProfile'))
        fingerprint=dependency_fingerprints(draft,manifest['audio']['path'],main_id,scopes=('captionStyle',))['captionStyle']
        evidence(review.get('styleEvidence'),'caption-style-binding',bases={'HUMAN_TEXT_REVIEW','SUPPORTED_TEXT_REVIEW'},taskId=task,captionStyleFingerprint=fingerprint)
        content=review.get('contentReview',{})
        need(content.get('status') in ('PROVISIONAL_MODEL_ONLY','REVIEWED') and content.get('wordTimingBasis') in ('MODEL_ONLY','REVIEWED'),'review-draft-content-status')
        groups=content.get('takeGroups');unknowns=content.get('uncertainties')
        need(isinstance(groups,list) and bool(groups) and all(isinstance(g,dict) and bool(g.get('id')) and g.get('status') in ('PENDING','REVIEWED') and bool(g.get('observation')) for g in groups),'review-draft-take-inventory')
        need(isinstance(unknowns,list) and all(isinstance(u,dict) and bool(u.get('id')) and bool(u.get('kind')) and bool(u.get('observation')) for u in unknowns),'review-draft-uncertainty-inventory')
        if content.get('status')=='PROVISIONAL_MODEL_ONLY':need(bool(unknowns) and any(g.get('status')=='PENDING' for g in groups),'review-draft-model-uncertainties-required')
        if content.get('status')=='REVIEWED':
            evidence(content.get('evidence'),'content-coverage-review',coveredWordIds=[w['id'] for w in plan['words']],takeGroupIds=[g['id'] for g in groups])
        if content.get('wordTimingBasis')=='REVIEWED':
            evidence(content.get('timingEvidence'),'word-timing-review',coveredWordIds=[w['id'] for w in plan['words']])
        for group in groups:
            if group.get('status')=='REVIEWED':evidence(group.get('evidence'),'content-take-review',takeGroupId=group['id'])
        pending['content']={'takeGroups':groups,'uncertainties':unknowns,'wordTimingBasis':content.get('wordTimingBasis')}
        derived=cut_inventory(draft,plan);need(audit.get('cutInventory')==derived,'cut-and-source-leg-coverage')
        pending['sourceCuts']=[{**cut,'status':'PENDING_AUDIO_CONTINUITY'} for cut in derived['allCuts']]
        cues={c['segmentId']:c for c in plan['cues']};native_cues={s['id']:s for t in draft['tracks'] if t.get('type')=='text' for s in t['segments']}
        onsets=manifest.get('onsets',[]);need(isinstance(onsets,list),'review-draft-onset-inventory')
        need(len(onsets)==len(native_cues) and {r.get('segmentId') for r in onsets}==set(native_cues),'onset-coverage')
        for row in onsets:
            ident=row['segmentId'];need(row.get('rawWordIds')==cues.get(ident,{}).get('rawWordIds'),'onset-semantic-raw-binding')
            need(row.get('startTick')==native_cues.get(ident,{}).get('target_timerange',{}).get('start'),'native-onset-mismatch')
            need(row.get('status') in ('PENDING','REVIEWED'),'review-draft-onset-status')
            if row.get('status')=='REVIEWED':
                evidence(row.get('evidence'),'caption-first-phoneme',segmentId=ident,startTick=row['startTick'],rawWordIds=row['rawWordIds'])
                risk=next(r for r in derived['allCues'] if r['segmentId']==ident)
                if risk['riskReasons']:evidence(row.get('evidence'),'caption-first-phoneme',cutRisk=risk)
            else:pending['onsets'].append({'segmentId':ident,'startTick':row['startTick'],'rawWordIds':row['rawWordIds'],'cutRisk':next(r for r in derived['allCues'] if r['segmentId']==ident)})
        ordered=sorted(native_cues.values(),key=lambda s:s['target_timerange']['start'])
        for index,cue in enumerate(ordered):
            timerange=cue['target_timerange'];need(integer(timerange['start']) and integer(timerange['duration'])
                and 0<=timerange['start']<timerange['start']+timerange['duration']<=draft['duration'],'cue-bounds')
            if index+1<len(ordered):need(timerange['start']+timerange['duration']==ordered[index+1]['target_timerange']['start'],'end-only-hold-mismatch')
        pacing=manifest.get('pacing',{})
        if manifest['branch']=='CONTENT_EDIT':
            need(pacing.get('scope')=='ALL_PAUSES','review-draft-all-pauses-scope')
            need(pacing.get('auditedScopes')==SCOPES and isinstance(pacing.get('intervals'),list),'review-draft-original-pause-inventory')
            need(pacing.get('criterion')=={'minimumQuietDurationTicks':200000,'comparison':'STRICTLY_GREATER','auditScopes':SCOPES},'pacing-criterion')
            need(pacing.get('status') in ('PENDING','REVIEWED'),'review-draft-pacing-status')
            need(len({i.get('id') for i in pacing.get('intervals',[])})==len(pacing.get('intervals',[])),'pause-duplicate-or-missing-id')
            for interval in pacing.get('intervals',[]):
                need(bool(interval.get('id')) and interval.get('kind') in SCOPES and integer(interval.get('startTick')) and integer(interval.get('endTick')) and 0<=interval['startTick']<interval['endTick'],'review-draft-original-pause-row')
                if interval.get('decision') in ('PENDING','HELD'):
                    pending['originalPauseIntervals'].append(interval)
                else:
                    need(interval.get('decision') in ('REMOVED_SAFE_QUIET','RETAINED_PROTECTED','AT_OR_BELOW_THRESHOLD'),'pause-unresolved')
                    need((interval['endTick']-interval['startTick']<=200000)==(interval.get('decision')=='AT_OR_BELOW_THRESHOLD'),'pause-strict-threshold')
                    evidence(interval.get('evidence'),'pause-disposition',intervalId=interval.get('id'),decision=interval.get('decision'))
            if pacing.get('status')=='REVIEWED':evidence(pacing.get('evidence'),'all-pause-audit',auditedScopes=SCOPES,intervalIds=sorted(i['id'] for i in pacing['intervals']))
            scan=scan_audio(manifest['audio']['path'],audit['pauseProfile'])
            need(audit.get('pauseScan')==scan,'pause-candidate-coverage')
            decisions=audit.get('pauseDecisions',[])
            need(len(decisions)==len(scan['candidates']) and {r.get('id') for r in decisions}=={r['id'] for r in scan['candidates']},'pause-risk-disposition-coverage')
            for row in decisions:
                need(row.get('status') in ('PENDING','REVIEWED'),'review-draft-pause-status')
                if row.get('status')=='PENDING':
                    need(row.get('decision') in ('PENDING','UNREVIEWED'),'review-draft-pause-pending-label')
                    pending['pauseCandidates'].append(next(c for c in scan['candidates'] if c['id']==row['id']))
                else:
                    need(row.get('decision') in ('RETAINED_PROTECTED','RETAINED_NOT_QUIET'),'pause-risk-unresolved')
                    evidence(row.get('evidence'),'pause-risk-disposition',candidateId=row['id'],decision=row.get('decision'))
            if audit.get('calibrationEvidence') is not None:evidence(audit['calibrationEvidence'],'pause-detector-calibration',profile=audit['pauseProfile'])
            else:pending['pauseCalibration']='PENDING_UNCALIBRATED_MACHINE_RISK_ONLY'
        else:
            need(pacing.get('status')=='NOT_APPLICABLE_PRESERVE_EXISTING_PACE' and audit.get('pauseScan')=='NOT_APPLICABLE_PRESERVE_EXISTING_PACE','subtitle-risk-scan-scope')
        check_broll_audit(draft,manifest,main_id,bound['native'],evidence,need)
    except (OSError,ValueError,TypeError,KeyError,IndexError,StopIteration,wave.Error) as exc:
        errors.append('review-draft-invalid: '+str(exc))
    return {'status':'PROVISIONAL_NOT_ACCEPTED' if not errors else 'BLOCKED','passed':not errors,
        'stage':'REVIEW_DRAFT','finalAcceptance':False,'reviewDraftEligible':not errors,
        'errors':sorted(set(errors)),'nativeHash':bound['native'],'audioHash':bound['audio'],
        'pendingQuality':pending,'nativeWriteAuthorized':False,
        'wordSourceCoverageScope':'SUPPLIED_PROPOSED_CAPTION_WORDS_ONLY_NOT_AUDIBLE_COMPLETENESS',
        'audioReview':audio_review or {'status':'PENDING_USER_AUDIO_REVIEW'},'audioEditReview':audio_edit_review,
        'limits':'New separate project preparation only. No heard-content, phonetic timing, pause quality, native appearance/playback or persistence acceptance. Writer must independently enforce exact task authority, new destination, closed editor, version, source/store scope, backup, precision and immediate byte readback.'}

def _check(manifest):
    errors = []
    def require(value, message):
        if not value: errors.append(message)
    require(manifest.get('schema') == 'capcut-native-apply-evidence/v1', 'schema')
    require(manifest.get('evidenceClass') == 'REAL_OBSERVATION', 'synthetic-or-unclassified-manifest')
    require(manifest.get('branch') in ('CONTENT_EDIT', 'SUBTITLE_ONLY'), 'branch')
    mode=manifest.get('mode','FINAL_ACCEPTANCE')
    require(mode in ('FINAL_ACCEPTANCE','REVIEW_DRAFT'),'native-apply-mode')
    bound = {}
    for key in ('native', 'audio'):
        item = manifest.get(key, {})
        p = Path(item.get('path', ''))
        require(p.is_absolute() and p.is_file(), key + '-file')
        if not p.is_absolute() or not p.is_file(): continue
        actual = digest(p)
        require(item.get('sha256') == actual, key + '-hash-drift')
        bound[key] = actual
    if len(bound) != 2:
        return {'status':'BLOCKED', 'errors':errors, 'nativeWriteAuthorized':False}
    draft = read(manifest['native']['path'])
    duration = draft.get('duration')
    require(integer(duration) and duration > 0, 'native-duration')
    with wave.open(manifest['audio']['path'], 'rb') as wav:
        audio_ticks = round(wav.getnframes() * 1e6 / wav.getframerate())
        tolerance = 1e6 / wav.getframerate()
    require(integer(duration) and abs(duration-audio_ticks) <= tolerance, 'edited-audio-duration-clock')
    audio_review={'status':'NOT_REQUIRED_FOR_THIS_EXPLICIT_SCOPE'}
    try:
        if speech_checkpoint_required(manifest,bound['native'],bound['audio']):
            task=manifest.get('reviewDraft',{}).get('taskId',manifest.get('taskId'))
            if not isinstance(task,str) or not task.strip():raise ValueError('audio-review-current-task-required')
            audio_review=validate_audio_review_checkpoint(manifest.get('audioReviewCheckpoint'),manifest['audio'],task)
            clock_ref=manifest.get('clockBinding',{}).get('evidence')
            clock_evidence=load_ref(clock_ref)
            if clock_evidence.get('audioProjection') is not None:
                require(audio_review['clockMap']==clock_evidence['audioProjection'],'audio-review-current-source-clock-map')
    except (OSError,ValueError,TypeError,KeyError,wave.Error) as exc:
        errors.append('audio-review-checkpoint-blocked: '+str(exc))
        audio_review={'status':'PENDING_OR_INVALID_USER_AUDIO_REVIEW'}
    audio_edit_review=None
    if manifest.get('branch')=='CONTENT_EDIT' and manifest.get('pacing',{}).get('scope')=='ALL_PAUSES':
        try:
            task=manifest.get('reviewDraft',{}).get('taskId',manifest.get('taskId'))
            audio_edit_review=validate_audio_edit_inventory(manifest.get('audioEditInventory'),manifest['native'],
                manifest['audio'],manifest.get('executionAudit'),mode,task)
        except (OSError,ValueError,TypeError,KeyError,wave.Error) as exc:
            errors.append('audio-edit-inventory-blocked: '+str(exc))
    if mode=='REVIEW_DRAFT':
        return check_review_draft(manifest,draft,bound,errors,audio_review,audio_edit_review)
    # Identity binding is checked, but a reviewer must prove that this audio was
    # extracted from these exact clips/channels, joins, gain, offsets and speed.
    require(manifest.get('clockBinding', {}).get('status') == 'REVIEWED', 'clock-binding-pending')

    adoption_cache={}
    def evidence(ref, claim, bases=None, **expected):
        if not isinstance(ref, dict):
            errors.append(claim+'-evidence-missing'); return
        p=Path(ref.get('path',''))
        if not p.is_absolute() or not p.is_file():
            errors.append(claim+'-evidence-file'); return
        require(ref.get('sha256') == digest(p), claim+'-evidence-hash')
        data=read(p)
        require(data.get('evidenceClass') == 'REAL_OBSERVATION', claim+'-synthetic-evidence')
        require(data.get('basis') in (bases or BASES), claim+'-not-listening-proof')
        require(data.get('status') == 'PASS', claim+'-review-pending')
        require(bool(data.get('reviewer')) and bool(data.get('observation')), claim+'-observation-missing')
        require(data.get('claim') == claim, claim+'-claim')
        identities_match=data.get('nativeHash') == bound['native'] and data.get('audioHash') == bound['audio']
        if not identities_match and ref.get('adoption') is not None:
            try:
                validate_adoption(ref['adoption'],ref,manifest['native'],manifest['audio'],cache=adoption_cache)
                identities_match=True
            except (OSError,ValueError,TypeError,KeyError,wave.Error) as exc:
                errors.append(claim+'-adoption-invalid: '+str(exc))
        require(identities_match,claim+'-stale-revision')
        for name,value in expected.items():
            require(data.get(name) == value, claim+'-'+name)

    evidence(manifest.get('clockBinding',{}).get('evidence'), 'audio-clock-binding')
    pacing=manifest.get('pacing',{})
    if manifest.get('branch') == 'CONTENT_EDIT':
        scope=pacing.get('scope')
        require(scope in ('ALL_PAUSES','INTER_SENTENCE_ONLY','SENTENCE_AND_INTRA'), 'pacing-scope')
        if scope == 'ALL_PAUSES':
            criterion=pacing.get('criterion',{})
            require(criterion == {'minimumQuietDurationTicks':200000,'comparison':'STRICTLY_GREATER','auditScopes':SCOPES} and integer(criterion.get('minimumQuietDurationTicks')), 'pacing-criterion')
        else:
            evidence(pacing.get('scopeEvidence'),'pacing-scope-override',scope=scope)
        require(pacing.get('status') == 'REVIEWED' and pacing.get('auditedScopes') == SCOPES, 'pacing-review-incomplete')
        evidence(pacing.get('evidence'),'all-pause-audit',auditedScopes=SCOPES)
        rows=pacing.get('intervals')
        require(isinstance(rows,list), 'pause-inventory-missing')
        seen=set()
        for row in rows if isinstance(rows,list) else []:
            ident=row.get('id'); require(bool(ident) and ident not in seen,'pause-duplicate-or-missing-id');seen.add(ident)
            a,b=row.get('startTick'),row.get('endTick')
            valid=integer(a) and integer(b) and 0<=a<b
            require(valid,'pause-bounds')
            require(row.get('kind') in SCOPES,'pause-kind')
            decision=row.get('decision')
            allowed=('REMOVED_SAFE_QUIET','RETAINED_PROTECTED','AT_OR_BELOW_THRESHOLD') if scope=='ALL_PAUSES' else ('REMOVED_SAFE_QUIET','RETAINED_PROTECTED','RETAINED_REVIEWED_LEGACY')
            require(decision in allowed, 'pause-unresolved')
            if valid and scope=='ALL_PAUSES':
                require((b-a<=200000) == (decision=='AT_OR_BELOW_THRESHOLD'),'pause-strict-threshold')
            evidence(row.get('evidence'),'pause-disposition',intervalId=ident,decision=decision)
        evidence(pacing.get('evidence'),'all-pause-audit',intervalIds=sorted(seen))
    else:
        require(pacing.get('status') == 'NOT_APPLICABLE_PRESERVE_EXISTING_PACE','subtitle-pace-must-stay')
        evidence(pacing.get('evidence'),'subtitle-only-scope')

    current={}
    for track in draft.get('tracks',[]):
        if track.get('type') != 'text': continue
        for segment in track.get('segments',[]):
            ident=segment.get('id'); require(ident not in current,'native-duplicate-cue')
            current[ident]=segment.get('target_timerange',{})
    rows=manifest.get('onsets',[])
    require(isinstance(rows,list) and bool(rows),'onset-inventory-missing')
    found={}
    for row in rows if isinstance(rows,list) else []:
        ident=row.get('segmentId');require(ident not in found,'duplicate-onset');found[ident]=row
        require(row.get('status')=='REVIEWED','onset-pending')
        require(bool(row.get('rawWordIds')) and isinstance(row.get('rawWordIds'),list),'raw-word-binding')
        start=row.get('startTick');require(integer(start) and start>=0,'onset-ticks')
        require(current.get(ident,{}).get('start')==start,'native-onset-mismatch')
        evidence(row.get('evidence'),'caption-first-phoneme',segmentId=ident,startTick=start,rawWordIds=row.get('rawWordIds'))
    require(set(found)==set(current),'onset-coverage')
    ordered=sorted(current.values(),key=lambda x:x.get('start',-1))
    for i,row in enumerate(ordered):
        start,length=row.get('start'),row.get('duration')
        good=integer(start) and integer(length) and start>=0 and length>0
        require(good,'cue-bounds')
        if good and i+1<len(ordered):require(start+length==ordered[i+1].get('start'),'end-only-hold-mismatch')
    # Execution coverage is independently recomputed. Omitted acoustic conflicts,
    # cut/source legs or a split user lock cannot pass via an empty claimed list.
    try:
        audit=load_ref(manifest.get('executionAudit'))
        require(audit.get('schema')=='capcut-execution-audit/v1','execution-audit-schema')
        require(audit.get('nativeHash')==bound['native'] and audit.get('audioHash')==bound['audio'],'execution-audit-stale-revision')
        plan=audit['captionPlan'];baseline=load_ref(plan.get('acceptedLockBaseline'))
        check_broll_audit(draft,manifest,plan.get('mainTrackId'),bound['native'],evidence,require)
        errors.extend(check_caption_plan(draft,plan,baseline))
        groups={c['segmentId']:c['rawWordIds'] for c in plan['cues']}
        require(all(groups.get(k)==v.get('rawWordIds') for k,v in found.items()),'onset-semantic-raw-binding')
        evidence(plan.get('semanticReview',{}).get('evidence'),'caption-policy-review',
            bases={'HUMAN_TEXT_REVIEW','SUPPORTED_TEXT_REVIEW'},coveredWordIds=[w['id'] for w in plan['words']],
            cueGroups=plan['cues'],protectedSpans=plan['protectedSpans'])
        derived=cut_inventory(draft,plan)
        require(audit.get('cutInventory')==derived,'cut-and-source-leg-coverage')
        evidence(manifest.get('clockBinding',{}).get('evidence'),'audio-clock-binding',mainTrackId=plan['mainTrackId'])
        for row in derived['allCues']:
            if row['riskReasons']:
                onset=found.get(row['segmentId'],{})
                evidence(onset.get('evidence'),'caption-first-phoneme',cutRisk=row)
        if manifest.get('branch')=='CONTENT_EDIT':
            profile=audit['pauseProfile']
            scan=scan_audio(manifest['audio']['path'],profile)
            require(audit.get('pauseScan')==scan,'pause-candidate-coverage')
            evidence(audit.get('calibrationEvidence'),'pause-detector-calibration',profile=profile)
            decisions=audit.get('pauseDecisions',[])
            require(isinstance(decisions,list),'pause-risk-decisions')
            decisions=decisions if isinstance(decisions,list) else []
            require(len(decisions)==len(scan['candidates']) and {r.get('id') for r in decisions}=={r['id'] for r in scan['candidates']},'pause-risk-disposition-coverage')
            for row in decisions:
                allowed={'RETAINED_PROTECTED','RETAINED_NOT_QUIET'}
                if pacing.get('scope')!='ALL_PAUSES':allowed.add('RETAINED_REVIEWED_LEGACY')
                require(row.get('decision') in allowed and row.get('status')=='REVIEWED','pause-risk-unresolved')
                evidence(row.get('evidence'),'pause-risk-disposition',candidateId=row.get('id'),decision=row.get('decision'))
        else:
            require(audit.get('pauseScan')=='NOT_APPLICABLE_PRESERVE_EXISTING_PACE','subtitle-risk-scan-scope')
    except (OSError,ValueError,TypeError,KeyError,IndexError,wave.Error) as exc:
        errors.append('execution-audit-invalid: '+str(exc))
    return {'status':'PREREQUISITES_CONSISTENT' if not errors else 'BLOCKED','passed':not errors,'stage':'FINAL_ACCEPTANCE','finalAcceptance':False,'reviewDraftEligible':False,'errors':sorted(set(errors)),'nativeHash':bound['native'],'audioHash':bound['audio'],'cueCount':len(current),'audioReview':audio_review,'audioEditReview':audio_edit_review,'nativeWriteAuthorized':False,'limits':'Cooperative supplied-evidence consistency only. Does not authenticate listening, safe phonemes, scope/permission, closed editor, version, actual saved target, native playback or persistence. Re-run on exact current bytes immediately before a separately authorized guarded write.'}

def check(manifest):
    """Each invocation independently verifies a fresh cooperative snapshot."""
    try:
        with fresh_hash_session():return _check(manifest)
    except SourceHashDrift as exc:
        return {'status':'BLOCKED','passed':False,'errors':['source-hash-drift: '+str(exc)],'nativeWriteAuthorized':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True,type=Path)
    args=parser.parse_args()
    try: result=check(read(args.manifest))
    except (OSError,ValueError,TypeError,KeyError,wave.Error) as exc:
        result={'status':'BLOCKED','errors':['invalid-or-unreadable-input: '+str(exc)],'nativeWriteAuthorized':False}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result.get('passed') is True else 1

if __name__=='__main__': raise SystemExit(main())
