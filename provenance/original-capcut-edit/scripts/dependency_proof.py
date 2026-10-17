"""Mechanical inheritance of exact dependencies; never fresh hearing or authority.

Phase support is limited to exact inherited native geometry evidenced by a
hash-bound baseline and rational frame count. There is no epsilon tolerance.
"""
import hashlib
import array
import json
from fractions import Fraction
from pathlib import Path
import wave
import sys
from source_hash_session import digest as _verified_digest

CLAIM_SCOPES = {
    'audio-clock-binding': ('audio',),
    'all-pause-audit': ('audio',),
    'pause-disposition': ('audio',),
    'pause-detector-calibration': ('audio',),
    'pause-risk-disposition': ('audio',),
    'subtitle-only-scope': ('audio',),
    'pacing-scope-override': ('audio',),
    'caption-first-phoneme': ('audio', 'captionTiming'),
    'caption-policy-review': ('captionTiming',),
    'caption-style-binding': ('captionStyle',),
    'broll-whole-timeline-review': ('audio', 'captionStyle', 'wholeInventory'),
}

def digest(path):
    return _verified_digest(path)

def read_ref(ref):
    if not isinstance(ref,dict):raise ValueError('hash-bound-reference-required')
    path=Path(ref.get('path',''))
    if not path.is_absolute() or not path.is_file() or path.is_symlink() or digest(path)!=ref.get('sha256'):
        raise ValueError('missing-or-stale-dependency-reference')
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in path.parents):
        raise ValueError('linked-dependency-reference')
    return json.loads(path.read_text(encoding='utf-8-sig'))

def file_ref(path):
    path=Path(path).resolve()
    return {'path':str(path),'sha256':digest(path)}

def stable_hash(value):
    return 'sha256:'+hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()

def validate_native_phase(ref, segmentId, materialId, sourceInTick, sourceOutTick, startTick, endTick, currentFps=None):
    """Return exact inherited phase; reject any new/unbound/changed geometry."""
    record=read_ref(ref)
    if record.get('schema')!='capcut-native-phase/v1':raise ValueError('native-phase-schema')
    fps=record.get('rationalFps',{})
    n,d=fps.get('numerator'),fps.get('denominator')
    if type(n) is not int or type(d) is not int or min(n,d)<=0:raise ValueError('native-phase-rational-fps')
    current=(Fraction(currentFps['numerator'],currentFps['denominator']) if isinstance(currentFps,dict)
             else Fraction(str(currentFps)))
    if current!=Fraction(n,d):raise ValueError('native-phase-current-fps-mismatch')
    baseline=read_ref(record.get('baseline'))
    if Fraction(str(baseline.get('fps'))) != Fraction(n,d):raise ValueError('native-phase-baseline-fps')
    rows=record.get('inheritedRanges')
    if not isinstance(rows,list) or len({r.get('segmentId') for r in rows})!=len(rows):raise ValueError('native-phase-inventory')
    rows=[r for r in rows if r.get('segmentId')==segmentId]
    if len(rows)!=1:raise ValueError('native-phase-unbound-segment')
    row=rows[0];expected={'segmentId':segmentId,'materialId':materialId,'sourceInTick':sourceInTick,
        'sourceOutTick':sourceOutTick,'startTick':startTick,'endTick':endTick}
    if any(row.get(k)!=v for k,v in expected.items()):raise ValueError('native-phase-changed-geometry')
    matches=[s for t in baseline.get('tracks',[]) for s in t.get('segments',[]) if s.get('id')==segmentId]
    if len(matches)!=1:raise ValueError('native-phase-baseline-segment')
    old=matches[0];src=old.get('source_timerange',{});dst=old.get('target_timerange',{})
    actual={'segmentId':old.get('id'),'materialId':old.get('material_id'),
        'sourceInTick':src.get('start'),'sourceOutTick':src.get('start',0)+src.get('duration',0),
        'startTick':dst.get('start'),'endTick':dst.get('start',0)+dst.get('duration',0)}
    if actual!=expected or old.get('speed')!=1 or old.get('reverse') or old.get('is_reverse'):
        raise ValueError('native-phase-not-exact-inherited-normal-speed')
    frames=row.get('frameCount')
    if type(frames) is not int or frames<=0:raise ValueError('native-phase-frame-count')
    duration=Fraction(frames*1000000*d,n);lo=duration.numerator//duration.denominator
    hi=-(-duration.numerator//duration.denominator)
    if sourceOutTick-sourceInTick not in (lo,hi) or endTick-startTick not in (lo,hi):
        raise ValueError('native-phase-not-rational-frame-quantization')
    return {'sourceMinusTargetTick':(sourceOutTick-sourceInTick)-(endTick-startTick),
        'frameCount':frames,'rationalFps':fps,'baseline':record['baseline'],
        'basis':'EXACT_INHERITED_NATIVE_GEOMETRY_NOT_TOLERANCE'}

def _materials(native,tracks,cache):
    catalog={}
    for kind,rows in native.get('materials',{}).items():
        if not isinstance(rows,list):continue
        for row in rows:
            if not isinstance(row,dict) or not row.get('id'):continue
            key=(kind,row['id'])
            if key in catalog and catalog[key]!=row:raise ValueError('conflicting-material-id')
            catalog[key]=row
    wanted={s.get('material_id') for t in tracks for s in t.get('segments',[])}
    for t in tracks:
        for s in t.get('segments',[]):wanted.update(s.get('extra_material_refs',[]))
    chosen={};changed=True
    while changed:
        changed=False
        for key,row in catalog.items():
            if key[1] not in wanted or key in chosen:continue
            chosen[key]=row;changed=True
            # Preserve indirect known material references without including
            # unrelated unused records pruned by an application save.
            def strings(value):
                if isinstance(value,str):yield value
                elif isinstance(value,dict):
                    for value in value.values():yield from strings(value)
                elif isinstance(value,list):
                    for value in value:yield from strings(value)
            wanted.update(strings(row))
    result=[]
    for (kind,ident),row in sorted(chosen.items()):
        item={'collection':kind,'id':ident,'object':row}
        path=row.get('path')
        if isinstance(path,str) and path:
            p=Path(path)
            if p.is_absolute() and p.is_file():
                if path not in cache:cache[path]=digest(p)
                item['sourceFileHash']=cache[path]
            elif kind in ('videos','audios'):raise ValueError('dependency-source-file-missing')
        def paths(value):
            if isinstance(value,dict):
                for key,v in value.items():
                    if isinstance(v,str) and (key=='path' or key.endswith('_path')):yield v
                    yield from paths(v)
            elif isinstance(value,list):
                for v in value:yield from paths(v)
        objects=[row]
        if isinstance(row.get('content'),str):
            try:objects.append(json.loads(row['content']))
            except ValueError:pass
        files={}
        for obj in objects:
            for candidate in paths(obj):
                p=Path(candidate)
                if p.is_absolute() and p.is_file():
                    if candidate not in cache:cache[candidate]=digest(p)
                    files[candidate]=cache[candidate]
        item['fileDependencies']=files
        result.append(item)
    return result

def audio_data_identity(path):
    h=hashlib.sha256()
    with wave.open(str(path),'rb') as f:
        if f.getcomptype()!='NONE':raise ValueError('uncompressed-audio-required')
        metadata={'channels':f.getnchannels(),'sampleWidth':f.getsampwidth(),
            'sampleRate':f.getframerate(),'frames':f.getnframes()}
        for block in iter(lambda:f.readframes(65536),b''):h.update(block)
    return {**metadata,'pcmSha256':'sha256:'+h.hexdigest()}

def dependency_fingerprints(native,audio,main_track_id,cache=None,scopes=None):
    cache={} if cache is None else cache
    tracks=native.get('tracks',[])
    main=[t for t in tracks if t.get('id')==main_track_id and t.get('type')=='video']
    if len(main)!=1:raise ValueError('dependency-main-track-required')
    audio_tracks=main+[t for t in tracks if t.get('type')=='audio']
    # A muted supporting layer cannot affect hearing. An unmuted supporting
    # video is an audio dependency even if a later guard rejects its mute scope.
    for t in tracks:
        if t.get('type')=='video' and t.get('id')!=main_track_id:
            audible=[s for s in t.get('segments',[]) if s.get('volume')!=0]
            if audible:audio_tracks.append({**t,'segments':audible})
    text_tracks=[t for t in tracks if t.get('type')=='text']
    text_by_id={m['id']:m for m in native.get('materials',{}).get('texts',[])}
    timing=[]
    for t in text_tracks:
        for s in t.get('segments',[]):
            text=json.loads(text_by_id[s['material_id']]['content'])['text']
            timing.append({'id':s['id'],'materialId':s['material_id'],
                           'target':s['target_timerange'],'text':text})
    common={'duration':native.get('duration'),'fps':native.get('fps')}
    wanted=set(scopes or ('audio','captionTiming','captionStyle','wholeInventory'));values={}
    if 'audio' in wanted:values['audio']={**common,'pcm':audio_data_identity(audio),'tracks':audio_tracks,
                 'materials':_materials(native,audio_tracks,cache)}
    if 'captionTiming' in wanted:values['captionTiming']=sorted(timing,key=lambda s:(s['target']['start'],s['id']))
    if 'captionStyle' in wanted:values['captionStyle']={'tracks':text_tracks,'materials':_materials(native,text_tracks,cache)}
    if 'wholeInventory' in wanted:values['wholeInventory']={**common,'tracks':tracks,'materials':_materials(native,tracks,cache),
            'canvas':{k:native.get(k) for k in ('canvas_config','config','color_space')}}
    fingerprints={k:stable_hash(v) for k,v in values.items()}
    fingerprints['_sourceBindings']={}
    for key,value in values.items():
        rows=value.get('materials',[]) if isinstance(value,dict) else []
        fingerprints['_sourceBindings'][key]={path:sha for row in rows for path,sha in row.get('fileDependencies',{}).items()}
    return fingerprints

def make_adoption(oldEvidence,oldNative,newNative,oldAudio,newAudio,mainTrackId,cache=None):
    """Prepare a mechanical receipt; it does not mutate the old observation."""
    proof=read_ref(oldEvidence);old=read_ref(oldNative);new=read_ref(newNative)
    if proof.get('evidenceClass')!='REAL_OBSERVATION' or proof.get('status')!='PASS':
        raise ValueError('adoption-needs-original-real-passed-observation')
    claim=proof.get('claim')
    if claim not in CLAIM_SCOPES:raise ValueError('unsupported-adoption-claim')
    bases=({'HUMAN_TEXT_REVIEW','SUPPORTED_TEXT_REVIEW'} if claim in ('caption-policy-review','caption-style-binding')
        else {'HUMAN_VISUAL_REVIEW','SUPPORTED_VISUAL_REVIEW'} if claim=='broll-whole-timeline-review'
        else {'HUMAN_LISTENING','SUPPORTED_AUDIO_REVIEW'})
    if proof.get('basis') not in bases or not proof.get('reviewer') or not proof.get('observation'):
        raise ValueError('adoption-original-observation-basis')
    for ref in (oldAudio,newAudio):
        if not isinstance(ref,dict) or digest(ref['path'])!=ref.get('sha256'):raise ValueError('adoption-audio-reference')
    if proof.get('nativeHash')!=oldNative['sha256'] or proof.get('audioHash')!=oldAudio['sha256']:
        raise ValueError('adoption-old-observation-identity')
    scopes=CLAIM_SCOPES[claim]
    cache={} if cache is None else cache
    before=dependency_fingerprints(old,oldAudio['path'],mainTrackId,cache,scopes=scopes)
    after=dependency_fingerprints(new,newAudio['path'],mainTrackId,cache,scopes=scopes)
    original_sources={path:sha for scope in scopes for path,sha in before['_sourceBindings'][scope].items()}
    # A path in old native JSON does not prove its historic file bytes. A
    # source-bound old claim must have recorded its source hashes originally;
    # never manufacture them now and relabel the result old hearing/vision.
    if proof.get('sourceDependencies',{})!=original_sources:raise ValueError('adoption-original-source-dependencies-missing-or-changed')
    equivalent=all(before[k]==after[k] for k in scopes)
    return {'schema':'capcut-evidence-adoption/v1','status':'DEPENDENCIES_EQUIVALENT' if equivalent else 'DEPENDENCIES_CHANGED',
        'basis':'MECHANICAL_DEPENDENCY_COMPARISON_NOT_NEW_OBSERVATION','claim':claim,
        'oldEvidence':oldEvidence,'oldNative':oldNative,'newNative':newNative,
        'oldAudio':oldAudio,'newAudio':newAudio,'mainTrackId':mainTrackId,
        'scopes':list(scopes),'before':{k:before[k] for k in scopes},'after':{k:after[k] for k in scopes},
        'originalReviewer':proof.get('reviewer'),'originalObservation':proof.get('observation'),
        'newHearingClaimed':False}

def validate_adoption(adoptionRef,evidenceRef,nativeRef,audioRef,cache=None):
    supplied=read_ref(adoptionRef)
    old_ref={k:evidenceRef[k] for k in ('path','sha256')}
    if supplied.get('oldEvidence')!=old_ref or supplied.get('newNative')!=nativeRef or supplied.get('newAudio')!=audioRef:
        raise ValueError('adoption-current-target-or-original-proof-mismatch')
    actual=make_adoption(supplied['oldEvidence'],supplied['oldNative'],supplied['newNative'],
        supplied['oldAudio'],supplied['newAudio'],supplied['mainTrackId'],cache=cache)
    if supplied!=actual or actual['status']!='DEPENDENCIES_EQUIVALENT':raise ValueError('adoption-dependencies-changed-or-stale')
    return actual

def validate_audio_review_checkpoint(checkpoint_ref,audio_ref,task_id=None):
    """Check a real supplied user acceptance; never create that acceptance."""
    record=read_ref(checkpoint_ref)
    if record.get('schema')!='capcut-audio-review-checkpoint/v1':raise ValueError('audio-review-checkpoint-schema')
    if not isinstance(record.get('taskId'),str) or not record['taskId'].strip():raise ValueError('audio-review-task-required')
    if record.get('status')!='ACCEPTED_BY_USER':raise ValueError('audio-review-user-acceptance-pending-or-rejected')
    if task_id is not None and record.get('taskId')!=task_id:raise ValueError('audio-review-task-binding')
    def binary_ref(ref):
        if not isinstance(ref,dict):raise ValueError('audio-review-binary-reference')
        path=Path(ref.get('path',''))
        if not path.is_absolute() or not path.is_file() or path.is_symlink() or any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in path.parents) or digest(path)!=ref.get('sha256'):
            raise ValueError('audio-review-binary-reference-drift-or-linked')
    binary_ref(audio_ref)
    if record.get('audioGain1')!=audio_ref:
        raise ValueError('audio-review-current-audio-drift')
    listening=record.get('listeningGain2',{})
    if not isinstance(listening,dict) or digest(listening['path'])!=listening.get('sha256'):
        raise ValueError('audio-review-listening-copy-drift')
    binary_ref(listening)
    receipt=read_ref(record.get('gainReceipt'))
    expected={'schemaVersion':'capcut-listening-review/v1','sourcePath':audio_ref['path'],'outputPath':listening['path'],
        'sourceSha256':audio_ref['sha256'],'outputSha256':listening['sha256'],'linearGain':2.0,
        'clippedSampleCount':0,'exactDoubledSamples':True,'sourceUnchanged':True,
        'clockAndDurationUnchanged':True,'mainProjectAudioTouched':False}
    if any(receipt.get(k)!=v for k,v in expected.items()):raise ValueError('audio-review-gain-receipt-binding')
    with wave.open(audio_ref['path'],'rb') as source,wave.open(listening['path'],'rb') as copy:
        if source.getparams()!=copy.getparams() or source.getsampwidth()!=2 or source.getcomptype()!='NONE' or source.getnframes()<1:
            raise ValueError('audio-review-exact-pcm-clock-required')
        if any(receipt.get(k)!=v for k,v in {'frames':source.getnframes(),'channels':source.getnchannels(),'sampleRate':source.getframerate()}.items()):
            raise ValueError('audio-review-receipt-sample-clock')
        while True:
            raw=source.readframes(65536);doubled=copy.readframes(65536)
            if not raw:
                if doubled:raise ValueError('audio-review-copy-has-extra-samples')
                break
            a=array.array('h');a.frombytes(raw);b=array.array('h');b.frombytes(doubled)
            if sys.byteorder!='little':a.byteswap();b.byteswap()
            if len(a)!=len(b) or any(not -32768<=value*2<=32767 or value*2!=other for value,other in zip(a,b)):
                raise ValueError('audio-review-copy-not-exact-safe-gain-two')
    clock=read_ref(record.get('clockMap'))
    if clock.get('evidenceClass')!='REAL_OBSERVATION' or clock.get('audioHash')!=audio_ref['sha256'] or clock.get('gain')!=1 or clock.get('status')!='PASS_STRUCTURAL_NOT_HEARD':
        raise ValueError('audio-review-exact-clock-map')
    feedback_ref=record.get('feedbackInventory');feedback=read_ref(feedback_ref)
    if feedback.get('schema')!='capcut-audio-feedback-inventory/v1' or feedback.get('taskId')!=record.get('taskId') or feedback.get('audioHash')!=audio_ref['sha256']:
        raise ValueError('audio-review-feedback-binding')
    ids=feedback.get('latestFeedbackIds');rows=feedback.get('items')
    if not isinstance(ids,list) or len(ids)!=len(set(ids)) or not isinstance(rows,list) or len(rows)!=len(ids) or {r.get('id') for r in rows}!=set(ids):
        raise ValueError('audio-review-feedback-inventory-incomplete')
    if feedback.get('coverage')!='ALL_CURRENT_TASK_AUDIO_FEEDBACK' or feedback.get('unresolvedFeedbackIds')!=[] or any(r.get('status')!='RESOLVED' or not r.get('observation') for r in rows):
        raise ValueError('audio-review-latest-feedback-unresolved')
    acceptance=read_ref(record.get('acceptanceEvidence'))
    expected={'schema':'capcut-user-audio-review/v1','evidenceClass':'REAL_OBSERVATION','basis':'USER_AUDIO_REVIEW',
        'status':'ACCEPTED','claim':'audio-content-review-acceptance','taskId':record.get('taskId'),
        'audioHash':audio_ref['sha256'],'listeningCopyHash':listening['sha256'],
        'clockMapHash':record['clockMap']['sha256'],'feedbackInventoryHash':feedback_ref['sha256']}
    if any(acceptance.get(k)!=v for k,v in expected.items()) or not isinstance(acceptance.get('userQuote'),str) or not acceptance['userQuote'].strip():
        raise ValueError('audio-review-real-current-user-acceptance-required')
    reply=read_ref(acceptance.get('userReply'))
    if reply.get('evidenceClass')!='REAL_OBSERVATION' or reply.get('source')!='DIRECT_USER_MESSAGE' or reply.get('reviewKind')!='AUDIO_CONTENT' or not isinstance(reply.get('sourceRef'),str) or not reply['sourceRef'].strip() or reply.get('message')!=acceptance['userQuote']:
        raise ValueError('audio-review-direct-audio-reply-required-not-teacher-approval')
    return {'status':'USER_AUDIO_REVIEW_ACCEPTED','taskId':record.get('taskId'),
        'audioHash':audio_ref['sha256'],'listeningCopyHash':listening['sha256'],
        'clockMap':record['clockMap'],
        'feedbackInventoryHash':feedback_ref['sha256'],'acceptanceEvidence':record['acceptanceEvidence'],
        'doesNotCertifyCaptionOnsetsOrNativePlayback':True}

def speech_checkpoint_required(manifest,native_hash,audio_hash):
    """CONTENT_EDIT speech is default; only an explicit user silent scope exempts."""
    if manifest.get('branch')!='CONTENT_EDIT':return False
    scope=manifest.get('speechScope',{})
    if not scope or scope.get('mode','SPEECH')=='SPEECH':return True
    if scope.get('mode')!='SILENT_NO_SPEECH':raise ValueError('speech-scope-mode')
    proof=read_ref(scope.get('evidence'))
    if proof.get('evidenceClass')!='REAL_OBSERVATION' or proof.get('basis')!='USER_SOURCE_CLASSIFICATION' or proof.get('status')!='PASS' or proof.get('claim')!='silent-content-scope' or proof.get('nativeHash')!=native_hash or proof.get('audioHash')!=audio_hash or not proof.get('userQuote'):
        raise ValueError('silent-scope-explicit-current-user-classification-required')
    return False


def make_audio_edit_inventory(native_ref,audio_ref,execution_ref,policy,source_map=None,producer_plan=None):
    """Materialize risks and reversible source ranges, never heard classifications."""
    from execution_audit import scan_audio
    native=read_ref(native_ref);audit=read_ref(execution_ref)
    if audit.get('nativeHash')!=native_ref.get('sha256') or audit.get('audioHash')!=audio_ref.get('sha256'):
        raise ValueError('audio-edit-execution-plan-current-binding')
    if not isinstance(policy,dict) or type(policy.get('maxActualRetainedQuietTicks')) is not int or policy['maxActualRetainedQuietTicks']!=200000:
        raise ValueError('audio-edit-explicit-all-pauses-limit-required')
    raw=read_ref(policy.get('rawSourceWords'));observations=read_ref(policy.get('sourceEditObservations'))
    if observations.get('evidenceClass')!='REAL_OBSERVATION':raise ValueError('audio-edit-original-observations-required')
    original_hash=observations.get('originalRawASRSha256')
    transcript_ref=policy.get('rawTranscript');transcript=read_ref(transcript_ref)
    bound_raw_hash=raw.get('asrSha256',transcript_ref['sha256']) if isinstance(raw,dict) else transcript_ref['sha256']
    if original_hash is not None and 'sha256:'+original_hash.removeprefix('sha256:')!='sha256:'+bound_raw_hash.removeprefix('sha256:'):
        raise ValueError('audio-edit-immutable-raw-source-drift')
    removed_ids=policy.get('removedContentRawWordIds')
    if not isinstance(removed_ids,list) or len(set(removed_ids))!=len(removed_ids):raise ValueError('audio-edit-explicit-removed-content-ids-required')
    raw_rows=raw.get('words',[]) if isinstance(raw,dict) else raw if isinstance(raw,list) else []
    raw_ids={w.get('id') for w in raw_rows if isinstance(w,dict)}
    if len(raw_ids)!=len(raw_rows) or any(not isinstance(ident,str) or not ident for ident in raw_ids):
        raise ValueError('audio-edit-immutable-raw-ids-missing-or-duplicate')
    if transcript_ref['sha256']!='sha256:'+bound_raw_hash.removeprefix('sha256:'):
        raise ValueError('audio-edit-original-transcript-hash-binding')
    complete=[]
    for segment in transcript.get('segments',[]):
        for word in segment.get('words',[]):
            complete.append({'segmentId':segment['id'],'rawText':word['word'],
                'sourceStartSeconds':word['start'],'sourceEndSeconds':word['end'],'probability':word.get('probability')})
    actual=[{key:word.get(key) for key in ('segmentId','rawText','sourceStartSeconds','sourceEndSeconds','probability')} for word in raw_rows]
    if not complete or actual!=complete or not raw.get('sourceAudioSha256') or raw.get('sourceAudioSha256')!=transcript.get('sourceAudioSha256'):
        raise ValueError('audio-edit-full-original-transcript-word-coverage')
    if not set(removed_ids)<=raw_ids or set(removed_ids)&{w['id'] for w in audit['captionPlan']['words']}:
        raise ValueError('audio-edit-removed-content-id-not-raw-or-still-captioned')
    source_map={} if source_map is None else source_map
    logical={k:v.get('materialId',v.get('nativeMaterialId')) if isinstance(v,dict) else v for k,v in source_map.items()}
    derivation=None
    if policy.get('sourceDerivation') is not None:
        from source_derivation import validate_source_derivation
        derivation=validate_source_derivation(policy['sourceDerivation'],native_ref,audio_ref,execution_ref,source_map,policy)
    original=observations.get('fourRemovals',observations.get('removals'))
    if not isinstance(original,list):raise ValueError('audio-edit-original-removal-inventory-required')
    source_identity=None
    if observations.get('sourceIdentity') is not None:
        identity_ref=dict(observations['sourceIdentity']);identity_ref['sha256']='sha256:'+identity_ref['sha256'].removeprefix('sha256:')
        source_identity=read_ref(identity_ref)
    native_sources={m['id']:m for m in native.get('materials',{}).get('videos',[])}
    pieces=[s for t in native.get('tracks',[]) if t.get('id')==audit['captionPlan']['mainTrackId'] for s in t.get('segments',[])]
    rows=[];seen=set()
    for row in original:
        ident=row.get('id');interval=row.get('originalSourceInterval',{})
        sid=interval.get('sourceId');lo=interval.get('startTick');hi=interval.get('endTick')
        derived_original=derivation is not None and sid==derivation['originalSourceId']
        if not ident or ident in seen or type(lo) is not int or type(hi) is not int or not 0<=lo<hi or (sid not in logical and not derived_original):
            raise ValueError('audio-edit-original-removal-bounds-or-source')
        seen.add(ident)
        if not derived_original and (logical[sid] not in {piece.get('material_id') for piece in pieces} or logical[sid] not in native_sources):
            raise ValueError('audio-edit-removal-source-map-not-current-main-material')
        if not isinstance(row.get('rawWordIds'),list) or not isinstance(row.get('oldTargetIntervals'),list) or not row.get('contextualReason'):
            raise ValueError('audio-edit-original-context-and-raw-ids-required')
        if len(set(row['rawWordIds']))!=len(row['rawWordIds']) or not set(row['rawWordIds'])<=raw_ids:
            raise ValueError('audio-edit-original-raw-ids-not-in-immutable-source')
        if not isinstance(observations.get('originalSourceSHA256'),str) or source_identity is None:
            raise ValueError('audio-edit-original-source-probe-and-hash-required')
        if observations.get('originalSourceSHA256') is not None:
            material={'path':derivation['originalSourcePath']} if derived_original else native_sources.get(logical[sid],{})
            matches=[] if source_identity is None else [s for s in source_identity.get('sources',[]) if s.get('path')==material.get('path')
                and str(s.get('sha256','')).removeprefix('sha256:')==observations['originalSourceSHA256'].removeprefix('sha256:')]
            if len(matches)!=1 or hi>matches[0].get('durationTicks',matches[0].get('actualDurationTicks',0)):
                raise ValueError('audio-edit-original-source-identity-or-bounds')
            if derived_original and (observations['originalSourceSHA256'].removeprefix('sha256:')!=derivation['originalSourceSHA256'].removeprefix('sha256:')
                or hi>derivation['originalSourceDurationTicks']):
                raise ValueError('audio-edit-derived-original-source-identity-or-bounds')
        retained=[]
        if derived_original:
            for piece in derivation['originalPieces']:
                a=max(lo,piece['sourceStartTick']);b=min(hi,piece['sourceEndTick'])
                if a<b:retained.append({'pieceId':piece['nativePieceId'],'originalPieceId':piece['originalPieceId'],
                    'sourceStartTick':a,'sourceEndTick':b,
                    'targetStartTick':piece['targetStartTick']+a-piece['sourceStartTick'],
                    'targetEndTick':piece['targetStartTick']+b-piece['sourceStartTick'],
                    'basis':'COMPOSED_ORIGINAL_SAMPLE_MAP_NOT_CURRENT_MASTER_CLOCK'})
        else:
            for piece in pieces:
                if piece.get('material_id')!=logical[sid]:continue
                src=piece['source_timerange'];dst=piece['target_timerange'];a=max(lo,src['start']);b=min(hi,src['start']+src['duration'])
                if a<b:retained.append({'pieceId':piece['id'],'sourceStartTick':a,'sourceEndTick':b,
                    'targetStartTick':dst['start']+a-src['start'],'targetEndTick':dst['start']+b-src['start']})
        ordered=sorted(retained,key=lambda r:r['sourceStartTick'])
        if any(a['sourceEndTick']>b['sourceStartTick'] for a,b in zip(ordered,ordered[1:])):
            raise ValueError('audio-edit-duplicated-original-source-removal-leg')
        context=row.get('fillerContext',{})
        if context.get('detectionStatus')=='DETECTED':
            if context.get('attachment') not in ('ISOLATED_BETWEEN_PAUSES','ATTACHED_TO_CONTENT','UNKNOWN'):
                raise ValueError('audio-edit-filler-attachment-kind')
            proof=read_ref(context.get('evidence'))
            expected={'evidenceClass':'REAL_OBSERVATION','status':'PASS','claim':'filler-attachment-review',
                'sourceHash':'sha256:'+observations['originalSourceSHA256'].removeprefix('sha256:'),
                'originalSourceInterval':interval,'detectionStatus':'DETECTED','attachment':context['attachment']}
            if any(proof.get(k)!=v for k,v in expected.items()) or proof.get('basis') not in ('HUMAN_LISTENING','SUPPORTED_AUDIO_REVIEW','USER_REPORTED') or not proof.get('reviewer') or not proof.get('observation'):
                raise ValueError('audio-edit-actual-filler-attachment-evidence-required')
            if context['attachment']=='ISOLATED_BETWEEN_PAUSES' and retained:
                raise ValueError('audio-edit-unresolved-isolated-detected-filler')
        rows.append({'id':ident,'originalObservation':row,'currentRetainedIntersections':retained,
            'removalStatus':'REMOVED_IN_CURRENT_MAP' if not retained else 'PARTLY_OR_FULLY_RETAINED_PENDING',
            'reversal':{'sourceId':sid,'sourceStartTick':lo,'sourceEndTick':hi,'originalRawWordIds':row['rawWordIds']},
            'phoneAndMeaningReview':'PENDING_AUDIO_CONTINUITY'})
    if not set(removed_ids)<={ident for row in original for ident in row['rawWordIds']}:
        raise ValueError('audio-edit-content-removal-missing-reversible-original-range')
    scan=scan_audio(audio_ref['path'],audit['pauseProfile'])
    result={'schema':'capcut-audio-edit-inventory/v1','evidenceClass':'REAL_OBSERVATION',
        'status':'PENDING_AUDIO_REVIEW','scope':'ALL_PAUSES','native':native_ref,'audio':audio_ref,
        'executionAudit':execution_ref,'producerPlan':producer_plan,'rawSourceWords':policy['rawSourceWords'],
        'rawTranscript':policy.get('rawTranscript'),
        'sourceEditObservations':policy['sourceEditObservations'],'sourceMap':logical,
        'removedContentRawWordIds':removed_ids,'maxActualRetainedQuietTicks':policy['maxActualRetainedQuietTicks'],
        'sourceRemovals':rows,'pauseScan':scan,
        'sourceRemovalReviews':[{'id':r['id'],'status':'PENDING','contextualRole':'UNKNOWN','decision':'PENDING_AUDIO_CONTINUITY','evidence':None} for r in rows],
        'candidates':[{'id':r['id'],'status':'PENDING','observedKind':'UNKNOWN',
            'observedQuietIntervals':[],'evidence':None,'exceptionEvidence':None} for r in scan['candidates']],
        'bindingBasis':'MECHANICAL_INVENTORY_NOT_HEARING_OR_CONTENT_DELETION_AUTHORITY'}
    if derivation is not None:
        result.update(sourceDerivation=policy['sourceDerivation'],sourceDerivationReadback=derivation)
    return result


def validate_audio_edit_inventory(inventory_ref,native_ref,audio_ref,execution_ref,mode,task_id=None):
    """Recompute ALL_PAUSES coverage; pending review is provisional only."""
    record=read_ref(inventory_ref)
    if record.get('schema')!='capcut-audio-edit-inventory/v1' or record.get('evidenceClass')!='REAL_OBSERVATION' or record.get('scope')!='ALL_PAUSES':
        raise ValueError('audio-edit-inventory-schema')
    if record.get('native')!=native_ref or record.get('audio')!=audio_ref or record.get('executionAudit')!=execution_ref:
        raise ValueError('audio-edit-inventory-current-binding')
    policy={k:record.get(k) for k in ('maxActualRetainedQuietTicks','rawSourceWords','rawTranscript','sourceEditObservations','removedContentRawWordIds','sourceDerivation')}
    actual=make_audio_edit_inventory(native_ref,audio_ref,execution_ref,policy,record.get('sourceMap'),record.get('producerPlan'))
    for key in ('pauseScan','sourceRemovals','sourceMap'):
        if record.get(key)!=actual[key]:raise ValueError('audio-edit-recomputed-'+key)
    if record.get('sourceDerivationReadback')!=actual.get('sourceDerivationReadback'):
        raise ValueError('audio-edit-recomputed-sourceDerivationReadback')
    if record.get('producerPlan') is not None:read_ref(record['producerPlan'])
    scan={r['id']:r for r in actual['pauseScan']['candidates']};rows=record.get('candidates')
    if not isinstance(rows,list) or len(rows)!=len(scan) or {r.get('id') for r in rows}!=set(scan):raise ValueError('audio-edit-all-candidate-coverage')
    pending=[];held=[];quiet_spans=[];approved_spans=set()
    def actual_proof(ref,collection,ident,expected):
        proof=read_ref(ref)
        if proof.get('schema')=='capcut-audio-edit-review/v1':
            if proof.get('sourceEditObservations')!=record['sourceEditObservations'] or proof.get('claim')!='audio-edit-review' or proof.get('status') not in ('PASS','PARTIAL'):
                raise ValueError('audio-edit-consolidated-review-scope')
            matches=[r for r in proof.get(collection,[]) if r.get('id')==ident]
            if len(matches)!=1:raise ValueError('audio-edit-consolidated-review-row')
            item=matches[0]
            if item.get('status') not in ('REVIEWED','HELD_FOR_PHONETIC_SAFETY'):
                raise ValueError('audio-edit-consolidated-review-not-actual')
            scoped_fields=set(expected)-{'evidenceClass','status','claim','nativeHash','audioHash'}
            scoped_fields.add('reason')
            proof={**proof,**{k:item[k] for k in scoped_fields if k in item},'status':'PASS','claim':expected['claim'],
                'candidateId' if collection=='candidateReviews' else 'removalId':ident}
        if any(proof.get(k)!=v for k,v in expected.items()) or proof.get('basis') not in ('HUMAN_LISTENING','SUPPORTED_AUDIO_REVIEW') or not proof.get('reviewer') or not proof.get('observation'):
            raise ValueError('audio-edit-actual-listening-basis-required-not-generic-protection')
        return proof
    removals={r['id']:r for r in actual['sourceRemovals']};reviews=record.get('sourceRemovalReviews')
    if not isinstance(reviews,list) or len(reviews)!=len(removals) or {r.get('id') for r in reviews}!=set(removals):
        raise ValueError('audio-edit-source-context-review-coverage')
    pending_removals=[];attached_holds=[]
    for row in reviews:
        original=removals[row['id']];interval=original['originalObservation']['originalSourceInterval']
        if row.get('status')=='PENDING' and row.get('contextualRole')=='UNKNOWN' and row.get('decision')=='PENDING_AUDIO_CONTINUITY':
            pending_removals.append(row['id']);continue
        retained=sum(r['sourceEndTick']-r['sourceStartTick'] for r in original['currentRetainedIntersections'])
        context=original['originalObservation'].get('fillerContext',{})
        attached=row.get('status')=='HELD_FOR_PHONETIC_SAFETY' and row.get('contextualRole')=='HESITATION_OR_FILLER' and row.get('decision')=='RETAIN_ATTACHED_FOR_PHONETIC_SAFETY' and retained>0 and bool(row.get('reason')) and context.get('attachment')=='ATTACHED_TO_CONTENT' and context.get('detectionStatus')=='DETECTED'
        valid=attached or (row.get('contextualRole')=='HESITATION_OR_FILLER' and row.get('decision')=='REMOVE_CONTEXTUAL_FILLER' and retained==0) or (
            row.get('contextualRole')=='MEANINGFUL_OR_QUOTED' and row.get('decision')=='KEEP_MEANINGFUL_OR_QUOTED' and retained==interval['endTick']-interval['startTick'])
        if row.get('status') not in ('REVIEWED','HELD_FOR_PHONETIC_SAFETY') or not valid or (row.get('status')=='HELD_FOR_PHONETIC_SAFETY' and not attached):raise ValueError('audio-edit-contextual-filler-or-meaningful-preservation')
        expected={'evidenceClass':'REAL_OBSERVATION','status':'PASS','claim':'source-removal-context-review',
            'nativeHash':native_ref['sha256'],'audioHash':audio_ref['sha256'],'removalId':row['id'],
            'originalSourceInterval':interval,'contextualRole':row['contextualRole'],'decision':row['decision'],
            'rawWordIds':original['originalObservation']['rawWordIds']}
        proof=actual_proof(row.get('evidence'),'sourceRemovalReviews',row['id'],expected)
        if attached:
            if proof.get('reason')!=row['reason']:raise ValueError('audio-edit-attached-filler-safety-reason-binding')
            attached_holds.append({'id':row['id'],'originalSourceInterval':interval,'reason':row['reason'],
                'status':'HELD_FOR_PHONETIC_SAFETY','requiresSeparateCurrentUserAudioAcceptance':True})
    for row in rows:
        ident=row['id'];candidate=scan[ident];kind=row.get('observedKind');spans=row.get('observedQuietIntervals')
        if row.get('status')=='PENDING' and kind=='UNKNOWN' and spans==[]:
            pending.append(ident);continue
        if row.get('status')!='REVIEWED' or kind not in ('TRUE_QUIET','SPEECH_OR_NOT_QUIET') or not isinstance(spans,list) or (kind=='TRUE_QUIET' and not spans):
            raise ValueError('audio-edit-actual-quiet-classification-required')
        expected={'evidenceClass':'REAL_OBSERVATION','status':'PASS','claim':'actual-quiet-span-review',
            'nativeHash':native_ref['sha256'],'audioHash':audio_ref['sha256'],'candidateId':ident,
            'observedKind':kind,'observedQuietIntervals':spans}
        actual_proof(row.get('evidence'),'candidateReviews',ident,expected)
        last=candidate['startTick']
        for span in spans:
            a,b=span.get('startTick'),span.get('endTick')
            if type(a) is not int or type(b) is not int or not candidate['startTick']<=a<b<=candidate['endTick'] or a<last:
                raise ValueError('audio-edit-observed-quiet-bounds')
            last=b
            quiet_spans.append((a,b,ident))
            if b-a>record['maxActualRetainedQuietTicks']:
                exception=row.get('exceptionEvidence')
                if exception is None:continue
                supplied=read_ref(exception)
                expected={'schema':'capcut-quiet-limit-exception/v1','evidenceClass':'REAL_OBSERVATION',
                    'status':'ACCEPTED','basis':'USER_EXPLICIT_QUIET_EXCEPTION','taskId':task_id,
                    'audioHash':audio_ref['sha256'],'candidateId':ident,'startTick':a,'endTick':b,
                    'maxActualRetainedQuietTicks':record['maxActualRetainedQuietTicks']}
                if any(supplied.get(k)!=v for k,v in expected.items()) or not isinstance(supplied.get('userQuote'),str) or not supplied['userQuote'].strip():
                    raise ValueError('audio-edit-exact-new-user-quiet-exception-required')
                reply=read_ref(supplied.get('userReply'))
                if reply.get('evidenceClass')!='REAL_OBSERVATION' or reply.get('source')!='DIRECT_USER_MESSAGE' or reply.get('reviewKind')!='QUIET_LIMIT_EXCEPTION' or not reply.get('sourceRef') or reply.get('message')!=supplied['userQuote']:
                    raise ValueError('audio-edit-direct-quiet-exception-reply-required')
                approved_spans.add((a,b))
    merged=[]
    for a,b,ident in sorted(quiet_spans):
        if merged and a<=merged[-1][1]:
            merged[-1][1]=max(b,merged[-1][1]);merged[-1][2].add(ident)
        else:merged.append([a,b,{ident}])
    for a,b,ids in merged:
        if b-a>record['maxActualRetainedQuietTicks'] and (a,b) not in approved_spans:
            held.append({'candidateIds':sorted(ids),'startTick':a,'endTick':b,'reason':'TRUE_QUIET_OVER_EXPLICIT_LIMIT'})
    if mode=='FINAL_ACCEPTANCE' and (pending or held or pending_removals):raise ValueError('audio-edit-final-quiet-review-held-or-pending')
    return {'status':'PENDING_OR_HELD_QUIET_REVIEW' if pending or held or pending_removals else 'ACTUAL_QUIET_REVIEW_CONSISTENT',
        'pendingCandidateIds':pending,'heldTrueQuietIntervals':held,'sourceRemovals':actual['sourceRemovals'],
        'pendingSourceRemovalIds':pending_removals,
        'attachedFillerSafetyHolds':attached_holds,
        'removedContentRawWordIds':record['removedContentRawWordIds'],'maxActualRetainedQuietTicks':record['maxActualRetainedQuietTicks'],
        'doesNotPromoteOnsetsOrModelSourceBoundaries':True}


def apply_audio_edit_review(inventory,review_ref):
    """Bind one supplied real review document; all omitted risks stay pending."""
    import copy
    record=copy.deepcopy(inventory);review=read_ref(review_ref)
    expected={'schema':'capcut-audio-edit-review/v1','evidenceClass':'REAL_OBSERVATION','claim':'audio-edit-review',
        'nativeHash':record['native']['sha256'],'audioHash':record['audio']['sha256'],
        'sourceEditObservations':record['sourceEditObservations']}
    if any(review.get(k)!=v for k,v in expected.items()) or review.get('status') not in ('PASS','PARTIAL') or review.get('basis') not in ('HUMAN_LISTENING','SUPPORTED_AUDIO_REVIEW') or not review.get('reviewer') or not review.get('observation'):
        raise ValueError('audio-edit-supplied-actual-review-required')
    for source,target,fields in [('candidateReviews','candidates',('status','observedKind','observedQuietIntervals','exceptionEvidence')),
        ('sourceRemovalReviews','sourceRemovalReviews',('status','contextualRole','decision','reason'))]:
        supplied=review.get(source,[]);rows={r['id']:r for r in record[target]}
        if not isinstance(supplied,list) or len({r.get('id') for r in supplied})!=len(supplied) or any(r.get('id') not in rows for r in supplied):
            raise ValueError('audio-edit-supplied-review-row-coverage')
        for row in supplied:
            for field in fields:
                if field in row:rows[row['id']][field]=copy.deepcopy(row[field])
            rows[row['id']]['evidence']=review_ref
    record['suppliedActualReview']=review_ref
    return record
