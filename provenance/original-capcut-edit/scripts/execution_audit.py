"""Deterministic risk coverage, never hearing, safe-cut proof or write authority.

All parameters and private words are task inputs. Models may annotate a candidate
but cannot veto it. The native guard recomputes coverage from exact current WAV.
"""
import array
import hashlib
import json
import math
from pathlib import Path
import sys
import wave

def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_ref(ref):
    if not isinstance(ref,dict):raise ValueError('missing-file-reference')
    path=Path(ref.get('path',''))
    if not path.is_absolute() or not path.is_file() or digest(path)!=ref.get('sha256'):
        raise ValueError('missing-or-stale-file-reference')
    return json.loads(path.read_text(encoding='utf-8-sig'))

def runs(mask):
    start=None
    for i,value in enumerate([*mask,False]):
        if value and start is None:start=i
        if not value and start is not None:
            yield start,i
            start=None

def scan_audio(path,profile):
    """Whole file, all channels, explicit multi-threshold RMS and peak survey.

    Twenty-ms windows every five ms, including the final partial window. Peak
    uses all samples; RMS uses channel-max energy, so anti-phase channels cannot
    cancel. Consecutive candidate windows union locally; methods are not fused
    or intersected, and ASR is never an exclusion. No normalization or 2x gain.
    """
    if not isinstance(profile,dict) or profile.get('windowMs')!=20 or profile.get('hopMs')!=5:
        raise ValueError('explicit-20ms-window-5ms-hop-required')
    methods=profile.get('methods',[])
    if not isinstance(methods,list) or {m.get('kind') for m in methods}!={'RMS','PEAK'} or len(methods)!=2:
        raise ValueError('rms-and-peak-surveys-required')
    for method in methods:
        values=method.get('thresholdsDbFS')
        if not isinstance(values,list) or len(values)<2 or len(values)>5 or len(set(values))!=len(values):
            raise ValueError('multiple-explicit-thresholds-required')
        if any(type(v) not in (int,float) or not math.isfinite(v) or not -100<=v<=-1 for v in values):
            raise ValueError('invalid-amplitude-threshold')
    with wave.open(str(path),'rb') as f:
        if f.getsampwidth()!=2 or f.getcomptype()!='NONE':raise ValueError('pcm16-required')
        rate,channels,count=f.getframerate(),f.getnchannels(),f.getnframes()
        pcm=array.array('h');pcm.frombytes(f.readframes(count))
    if sys.byteorder!='little':pcm.byteswap()
    if rate<1000 or channels<1 or count<1:raise ValueError('invalid-audio')
    win=max(1,round(rate*.020));hop=max(1,round(rate*.005));levels={'RMS':[],'PEAK':[]}
    positions=list(range(0,count,hop))
    for a in positions:
        b=min(a+win,count); rms=[];peak=0
        for channel in range(channels):
            values=pcm[a*channels+channel:b*channels:channels]
            peak=max(peak,max((abs(v) for v in values),default=0))
            rms.append(math.sqrt(sum(v*v for v in values)/len(values)))
        levels['RMS'].append(20*math.log10(max(max(rms)/32768,1e-9)))
        levels['PEAK'].append(20*math.log10(max(peak/32768,1e-9)))
    candidates=[]
    for method in sorted(methods,key=lambda x:x['kind']):
        for threshold in sorted(method['thresholdsDbFS']):
            for a,b in runs([v<threshold for v in levels[method['kind']]]):
                start=positions[a];end=min(count,positions[b-1]+win)
                # Compare integer sample duration before tick/frame rounding.
                if (end-start)*1000000<=200000*rate:continue
                ident=f"{method['kind']}:{threshold:g}:{start}:{end}"
                candidates.append({'id':ident,'method':method['kind'],'thresholdDbFS':threshold,
                    'startSample':start,'endSample':end,'startTick':round(start*1000000/rate),
                    'endTick':round(end*1000000/rate),'durationTick':round((end-start)*1000000/rate),
                    'kind':'HEAD' if start==0 else 'TAIL' if end==count else 'INTERNAL'})
    return {'schema':'capcut-pause-risk-scan/v1','audioHash':digest(path),'sampleRate':rate,
        'channels':channels,'samples':count,'analysisGainApplied':1,'profile':profile,
        'criterion':{'minimumQuietDurationTicks':200000,'comparison':'STRICTLY_GREATER'},
        'candidateClass':'MACHINE_RISK_NOT_QUIET','candidates':candidates}

def native_cues(draft):
    result={}
    texts={m['id']:json.loads(m['content'])['text'] for m in draft.get('materials',{}).get('texts',[])}
    for track in draft.get('tracks',[]):
        if track.get('type')!='text':continue
        for cue in track.get('segments',[]):
            if cue['id'] in result:raise ValueError('duplicate-native-cue')
            result[cue['id']]={'startTick':cue['target_timerange']['start'],
                'endTick':cue['target_timerange']['start']+cue['target_timerange']['duration'],
                'text':texts[cue['material_id']]}
    return result

def cut_inventory(draft,plan):
    """Inventory every cue/cut and first-word source leg, including non-risk rows."""
    track=next((t for t in draft.get('tracks',[]) if t.get('id')==plan.get('mainTrackId') and t.get('type')=='video'),None)
    if track is None:raise ValueError('main-track-not-bound')
    pieces=sorted(track['segments'],key=lambda s:s['target_timerange']['start'])
    cuts=[{'leftPieceId':a['id'],'rightPieceId':b['id'],'tick':b['target_timerange']['start']} for a,b in zip(pieces,pieces[1:])]
    native=native_cues(draft);words={w['id']:w for w in plan['words']};rows=[]
    def legs(word):
        a,b=word['sourceStartTick'],word['sourceEndTick'];result=[]
        if type(a) is not int or type(b) is not int or not 0<=a<b:raise ValueError('word-source-bounds')
        for piece in pieces:
            if piece['material_id']!=word['sourceId']:continue
            src,dst=piece['source_timerange'],piece['target_timerange']
            if piece.get('speed',1)!=1 or abs(src['duration']-dst['duration'])>1:raise ValueError('unsupported-piece-clock')
            lo,hi=max(a,src['start']),min(b,src['start']+src['duration'])
            if lo<hi:result.append({'pieceId':piece['id'],'sourceStartTick':lo,'sourceEndTick':hi,
                'outputStartTick':dst['start']+lo-src['start'],'outputEndTick':dst['start']+hi-src['start']})
        return result
    for cue in plan['cues']:
        current=native[cue['segmentId']];ids=cue['rawWordIds'];first=legs(words[ids[0]])
        following=[leg for ident in ids[1:] for leg in legs(words[ident])]
        touch=[cut for cut in cuts if current['startTick']<=cut['tick']<=current['endTick']]
        isolated=bool(first and following and {x['pieceId'] for x in first}.isdisjoint({x['pieceId'] for x in following}))
        reasons=[]
        if touch:reasons.append('CUT_INSIDE_OR_TOUCHING_CUE')
        if len(first)!=1:reasons.append('FIRST_WORD_MULTIPLE_OR_MISSING_SOURCE_LEGS')
        if isolated:reasons.append('FIRST_WORD_ISOLATED_FROM_REMAINING_WORDS')
        rows.append({'segmentId':cue['segmentId'],'startTick':current['startTick'],'rawWordIds':ids,
            'firstWordSourceLegs':first,'cuts':touch,'riskReasons':reasons})
    return {'allCuts':cuts,'allCues':rows}

def preserved_enumeration_cues(plan,current):
    """Validate only the explicit long-lead-in exception; no global count waiver."""
    rows=plan.get('preservedEnumerationLeadIns',[])
    if not isinstance(rows,list):return set(),['long-enumeration-exception-inventory']
    allowed=set();errors=[];words=plan.get('words',[]);ids=[w['id'] for w in words];byword={w['id']:w for w in words}
    cues=sorted(plan.get('cues',[]),key=lambda c:current.get(c.get('segmentId'),{}).get('startTick',-1))
    vi={1:('nhất','một'),2:('hai',),3:('ba',),4:('tư','bốn'),5:('năm',),6:('sáu',),7:('bảy',),8:('tám',),9:('chín',),10:('mười',)}
    for item in rows:
        try:
            ident=item['segmentId'];group=item['rawWordIds'];ordinal=item['ordinal']
            cue=next(c for c in cues if c.get('segmentId')==ident);n=cues.index(cue);following=cues[n+1]
            if ident in allowed or type(ordinal) is not int or ordinal<1:raise ValueError('identity')
            if not isinstance(group,list) or not group or group!=cue.get('rawWordIds') or any(i not in byword for i in group):raise ValueError('word binding')
            pos=ids.index(group[0])
            if ids[pos:pos+len(group)]!=group:raise ValueError('contiguity')
            raw=' '.join(byword[i]['text'].strip() for i in group)
            if item.get('rawLeadIn')!=raw:raise ValueError('raw text')
            if len(raw.split())<=4:raise ValueError('not over four raw whitespace words')
            text=cue.get('nativeText','')
            tokens=lambda t:[x.strip('.,:?').casefold() for x in t.split()]
            if tokens(raw)!=tokens(text):raise ValueError('preserve every raw word')
            marker=item['markerWordIds'];mpos=group.index(marker[0])
            if not marker or group[mpos:mpos+len(marker)]!=marker:raise ValueError('marker binding')
            value=' '.join(tokens(' '.join(byword[i]['text'] for i in marker)))
            valid={p+v for p in ('thứ ','điểm thứ ') for v in (*vi.get(ordinal,()),str(ordinal))}
            if item.get('markerMeaning')=='final-item':
                if value not in ('cuối cùng','điểm cuối cùng') or item.get('listItemCount')!=ordinal:raise ValueError('final marker')
            elif value not in valid:raise ValueError('ordinal')
            if following['segmentId']!=item['contentSegmentId'] or not following.get('rawWordIds') or following['rawWordIds'][0]!=item['firstContentWordId'] or ids[pos+len(group)]!=item['firstContentWordId']:raise ValueError('content binding')
            content=following.get('nativeText','')
            prefix=str(ordinal)+'. '
            if not content.startswith(prefix) or not content[len(prefix):] or content[len(prefix):][0]!=content[len(prefix):][0].upper():raise ValueError('content prefix/case')
            decision=load_ref(item.get('decision'))
            if decision.get('authority')!='explicit-user-request' or decision.get('scope')!='preserve-long-enumeration-leadin-and-prefix-main-content' or not decision.get('userQuote'):raise ValueError('exact decision')
            if item.get('preserved') is not True:raise ValueError('not preserved')
            allowed.add(ident)
        except (ValueError,KeyError,IndexError,TypeError,StopIteration,OSError):
            errors.append('invalid-preserved-long-enumeration')
    return allowed,sorted(set(errors))


def check_caption_plan(draft,plan,baseline):
    errors=[]
    def need(ok,code):
        if not ok:errors.append(code)
    current=native_cues(draft);words=plan.get('words',[]);ids=[w['id'] for w in words]
    preserved,exception_errors=preserved_enumeration_cues(plan,current);errors.extend(exception_errors)
    need(bool(ids) and len(ids)==len(set(ids)),'raw-word-inventory')
    byword={w['id']:w for w in words};cues=plan.get('cues',[])
    ordered=sorted(cues,key=lambda c:current.get(c.get('segmentId'),{}).get('startTick',-1))
    need([i for c in ordered for i in c.get('rawWordIds',[])]==ids,'raw-word-once-in-order')
    need(len(cues)==len(current) and {c.get('segmentId') for c in cues}==set(current),'semantic-cue-coverage')
    owner={}
    for cue in cues:
        ident=cue.get('segmentId');group=cue.get('rawWordIds',[]);text=cue.get('nativeText')
        need(text==current.get(ident,{}).get('text'),'native-caption-text-binding')
        need(isinstance(text,str) and 0<len(text.split()) and (len(text.split())<=6 or ident in preserved) and '\n' not in text and '\r' not in text,'caption-one-line-six-word-policy')
        need(bool(group) and all(i in byword for i in group),'cue-raw-binding')
        if group and all(i in byword for i in group):
            need(len({byword[i].get('sentenceId') for i in group})==1 and bool(byword[group[0]].get('sentenceId')),'logical-sentence-boundary')
        for i in group:owner[i]=ident
    need(plan.get('semanticReview',{}).get('basis')=='whole-transcript-semantic-review' and plan.get('semanticReview',{}).get('coveredWordIds')==ids,'whole-transcript-semantic-coverage')
    locks=plan.get('protectedSpans');need(isinstance(locks,list),'protected-span-inventory')
    locks=locks if isinstance(locks,list) else [];bylock={s.get('id'):s for s in locks}
    need(len(bylock)==len(locks),'duplicate-protected-span')
    for span in locks:
        group=span.get('wordIds',[])
        valid=bool(group) and all(i in byword for i in group)
        need(valid,'protected-span-word-binding')
        if not valid:continue
        positions=[ids.index(i) for i in group]
        need(positions==list(range(positions[0],positions[0]+len(group))),'protected-span-contiguity')
        need(len({byword[i].get('sentenceId') for i in group})==1,'protected-span-sentence')
        need(' '.join(byword[i]['text'].strip() for i in group)==span.get('rawText'),'protected-span-raw-text')
        need(len({owner.get(i) for i in group})==1 and owner.get(group[0]) is not None,'split-protected-span')
    # A baseline is task data tied to the actual prior locks, not a source of authority.
    # Explicitly superseded locks need their separate exact user decision record.
    superseded={s['lockId']:s for s in plan.get('supersededLocks',[])}
    for previous in baseline.get('protectedSpans',[]):
        if bylock.get(previous['id'])==previous:continue
        item=superseded.get(previous['id'])
        if not item:errors.append('prior-lock-dropped-or-redefined');continue
        decision=load_ref(item.get('decision'))
        need(decision.get('authority')=='explicit-user-request' and decision.get('lockId')==previous['id'] and bool(decision.get('scope')) and bool(decision.get('userQuote')),'prior-lock-supersession-evidence')
    return sorted(set(errors))

def prepare(native_path,audio_path,plan,profile,branch='CONTENT_EDIT'):
    draft=json.loads(Path(native_path).read_text(encoding='utf-8-sig'))
    return {'schema':'capcut-execution-audit/v1','status':'PREPARED_ONLY_REVIEW_REQUIRED',
        'nativeHash':digest(native_path),'audioHash':digest(audio_path),'captionPlan':plan,
        'cutInventory':cut_inventory(draft,plan),'pauseProfile':profile,
        'pauseScan':scan_audio(audio_path,profile) if branch=='CONTENT_EDIT' else 'NOT_APPLICABLE_PRESERVE_EXISTING_PACE',
        'pauseDecisions':[],'calibrationEvidence':None,'nativeWriteAuthorized':False}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('native','audio','plan','profile','output'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--branch',choices=['CONTENT_EDIT','SUBTITLE_ONLY'],default='CONTENT_EDIT')
    args=parser.parse_args()
    if args.output.exists():parser.error('Output already exists; preserve prior evidence.')
    result=prepare(args.native,args.audio,json.loads(args.plan.read_text(encoding='utf-8-sig')),
        json.loads(args.profile.read_text(encoding='utf-8-sig')),args.branch)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'nativeWriteAuthorized':False}))
