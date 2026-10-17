"""Assemble gain1 PCM16 source samples from an explicit normal-speed cut map.

Task-local preparation only: no decoder, detector, take/filler judgment, hearing,
native-store write, resampling, padding, stretching or automatic approval.
"""
from __future__ import annotations
import argparse,copy,functools,hashlib,json,math,os
from fractions import Fraction
from pathlib import Path
import wave
from source_hash_session import digest as verified_digest, verified_hash_session

SCHEMA='capcut-audio-assembly-plan/v1'

def need(ok,message):
    if not ok:raise ValueError(message)
def read(path):return json.loads(Path(path).read_text('utf-8-sig'))
def sha(path):
    return verified_digest(path)

def _verified_call(function):
    @functools.wraps(function)
    def run(*args,**kwargs):
        with verified_hash_session():return function(*args,**kwargs)
    return run
def hash_value(value):
    need(isinstance(value,str),'sha256-required');value=value.removeprefix('sha256:').lower()
    need(len(value)==64 and all(c in '0123456789abcdef' for c in value),'sha256-required')
    return 'sha256:'+value
def checked(path,*,file=False):
    p=Path(path);need(p.is_absolute(),'absolute-path-required')
    for x in (p,*p.parents):
        need(not x.is_symlink() and not(hasattr(x,'is_junction') and x.is_junction()),'linked-path-refused')
    if file:need(p.is_file(),'input-file-required')
    return p
def integer(value,label,minimum=0):
    need(type(value) is int and value>=minimum,label+'-integer-required');return value
def same_path(a,b):
    return isinstance(a,str) and Path(a).is_absolute() and Path(a).resolve()==Path(b).resolve()
def file_ref(ref):
    need(isinstance(ref,dict),'decoder-evidence-path-hash-required')
    p=checked(ref.get('path',''),file=True)
    need(sha(p)==hash_value(ref.get('sha256')),'decoder-evidence-hash-drift');return p
def round_frame(ticks,rate):
    # Nonnegative exact nearest sample, half up; no float clock arithmetic.
    return (ticks*rate+500_000)//1_000_000
def rational(value):return {'numerator':value.numerator,'denominator':value.denominator}

def decoder_binding(binding,params):
    """Bind a supplied decode record; preserve its original observation limits.

    Accept generic source/audio/sourceSha256/audioSha256/clock/offset/gain
    records or equivalent explicit originalSource*/pcm*/sourceOffsetTicks fields.
    It is evidence consistency, not authentication of a decoder or heard source.
    """
    path=file_ref(binding.get('decoderEvidenceRef'));data=read(path)
    need(isinstance(data,dict),'decoder-evidence-object-required')
    source=data.get('originalSourcePath',data.get('source'))
    pcm=data.get('pcmPath',data.get('audio'))
    sh=data.get('originalSourceSHA256',data.get('sourceSha256'))
    ah=data.get('pcmSHA256',data.get('audioSha256'))
    need(same_path(source,binding['originalSourcePath']) and same_path(pcm,binding['path']),
         'decoder-source-pcm-path-mismatch')
    need(hash_value(sh)==hash_value(binding['originalSourceSHA256'])
         and hash_value(ah)==hash_value(binding['sha256']),'decoder-source-pcm-hash-mismatch')
    need(data.get('clockBasis')=='ORIGINAL_SOURCE','decoder-original-source-clock-required')
    offset=data.get('sourceOffsetTicks')
    if offset is None:
        raw=data.get('offset');need(type(raw) in (int,float) and math.isfinite(raw),'decoder-offset-required')
        offset=Fraction(str(raw))*1_000_000
        need(offset.denominator==1,'decoder-offset-must-be-integer-ticks');offset=offset.numerator
    need(type(offset) is int and offset==binding['sourceOffsetTicks'],'decoder-offset-mismatch')
    gain=data.get('linearGain',data.get('gain'))
    need(type(gain) in (int,float) and gain==1,'decoder-gain1-required')
    clock=data.get('clock',{})
    need(isinstance(clock,dict) and all(type(clock.get(k)) is int for k in ('rate','channels','samples'))
         and clock.get('rate')==params.framerate and clock.get('channels')==params.nchannels
         and clock.get('samples')==params.nframes,'decoder-pcm-format-or-frame-count-mismatch')
    return {'path':str(path),'sha256':sha(path)}

@_verified_call
def assemble_audio(plan,output):
    """Return a projection receipt; write one fresh WAV plus .assembly.json.

    mainPieces uses sourceId/sourceInTicks/sourceOutTicks/targetInTicks and
    optional targetOutTicks. pcmBindings is a list (or source-ID dictionary) of
    path/hash, originalSourcePath/hash, sourceOffsetTicks and decoderEvidenceRef.
    Every input must share the exact PCM16 sample rate/channel layout. Requested
    microsecond endpoints are quantized to nearest actual sample, with every
    error reported. Unequal resulting source/target sample counts are rejected.
    """
    code_hash=sha(Path(__file__))
    plan=read(plan) if isinstance(plan,(str,Path)) else copy.deepcopy(plan)
    need(isinstance(plan,dict) and plan.get('schema')==SCHEMA,'audio-assembly-plan-schema')
    output=checked(output);receipt_path=checked(output.with_suffix('.assembly.json'))
    need(output.suffix.lower()=='.wav' and output.parent.is_dir(),'new-wav-in-existing-task-directory-required')
    need(not output.exists() and not receipt_path.exists(),'output-or-receipt-already-exists')
    parts=[x.casefold() for x in output.parts]
    need('com.lveditor.draft' not in parts and not any((p/'root_meta_info.json').exists() for p in output.parents),
         'audio-output-cannot-be-native-store')
    need(not any(parts[i:i+2]==['.codex','skills'] for i in range(len(parts)-1)),
         'audio-output-cannot-be-instruction-store')
    pieces=plan.get('mainPieces');bindings=plan.get('pcmBindings')
    need(isinstance(pieces,list) and bool(pieces),'audio-main-pieces-required')
    if isinstance(bindings,dict):bindings=[dict(value,sourceId=sid) for sid,value in bindings.items()]
    need(isinstance(bindings,list) and bool(bindings),'pcm-bindings-required')
    by_source={};input_hashes={};formats={};common=None
    for row in bindings:
        need(isinstance(row,dict) and isinstance(row.get('sourceId'),str) and row['sourceId'],'pcm-source-id-required')
        sid=row['sourceId'];need(sid not in by_source,'duplicate-pcm-source-id')
        pcm=checked(row.get('path',''),file=True);original=checked(row.get('originalSourcePath',''),file=True)
        integer(row.get('sourceOffsetTicks'),'source-offset')
        ph,oh=sha(pcm),sha(original)
        need(ph==hash_value(row.get('sha256')) and oh==hash_value(row.get('originalSourceSHA256')),'pcm-or-original-source-hash-drift')
        need(output.resolve() not in (pcm.resolve(),original.resolve()),'output-cannot-replace-source')
        with wave.open(str(pcm),'rb') as f:params=f.getparams()
        need(params.sampwidth==2 and params.comptype=='NONE' and params.nframes>0,'nonempty-uncompressed-pcm16-required')
        fmt=(params.nchannels,params.sampwidth,params.framerate)
        need(common is None or fmt==common,'mixed-pcm-formats-no-resampling-allowed');common=fmt
        provenance=decoder_binding(row,params)
        by_source[sid]={**row,'path':str(pcm),'originalSourcePath':str(original),'decoderEvidenceRef':provenance}
        formats[sid]=params;input_hashes[str(pcm)]=ph;input_hashes[str(original)]=oh
        input_hashes[provenance['path']]=provenance['sha256']
    need(set(by_source)=={p.get('sourceId') for p in pieces},'pcm-binding-coverage-exact-required')
    channels,width,rate=common;cursor=0;requested_cursor=0;seen=set();rows=[];chunks=[];used={}
    for piece in pieces:
        need(isinstance(piece,dict) and isinstance(piece.get('id'),str) and piece['id'],'audio-piece-id-required')
        ident=piece['id'];need(ident not in seen,'duplicate-audio-piece-id');seen.add(ident)
        sid=piece.get('sourceId');need(sid in by_source,'unknown-pcm-source-id')
        a=integer(piece.get('sourceInTicks'),'source-in');b=integer(piece.get('sourceOutTicks'),'source-out',1)
        x=integer(piece.get('targetInTicks'),'target-in');y=integer(piece.get('targetOutTicks',x+b-a),'target-out',1)
        need(a<b and x<y and x==requested_cursor,'positive-contiguous-target-clock-required')
        need(type(piece.get('speed',1)) in (int,float) and piece.get('speed',1)==1
             and piece.get('reverse',False) is False and piece.get('is_loop',False) is False,
             'normal-forward-nonloop-audio-required')
        need(type(piece.get('volume',1)) in (int,float) and piece.get('volume',1)==1,'project-gain1-required')
        binding=by_source[sid];offset=binding['sourceOffsetTicks'];params=formats[sid]
        need(a>=offset and (b-offset)*rate<=params.nframes*1_000_000,'source-outside-decoded-clock')
        first,last=round_frame(a-offset,rate),round_frame(b-offset,rate)
        ta,tb=round_frame(x,rate),round_frame(y,rate)
        need(0<=first<last<=params.nframes,'source-sample-bounds')
        need(ta==cursor and tb-ta==last-first,'unrepresentable-source-target-sample-map')
        # Detect accidental duplicate source samples across aliases as well as
        # same-ID overlaps. Intentional repeats require a different reviewed route.
        source_key=hash_value(binding['originalSourceSHA256'])
        absolute_first=Fraction(offset,1_000_000)+Fraction(first,rate)
        absolute_last=Fraction(offset,1_000_000)+Fraction(last,rate)
        need(not any(max(absolute_first,lo)<min(absolute_last,hi) for lo,hi in used.get(source_key,[])),
             'overlapping-original-source-samples')
        used.setdefault(source_key,[]).append((absolute_first,absolute_last))
        with wave.open(binding['path'],'rb') as f:
            f.setpos(first);raw=f.readframes(last-first)
        need(len(raw)==(last-first)*channels*width,'truncated-pcm-source')
        chunks.append(raw)
        rows.append({'id':ident,'sourceId':sid,'sourceInTicks':a,'sourceOutTicks':b,
            'targetInTicks':x,'targetOutTicks':y,'sourceInFrame':first,'sourceOutFrame':last,
            'targetInFrame':ta,'targetOutFrame':tb,'frames':last-first,
            'sourceInQuantizationErrorTicks':rational(Fraction(first*1_000_000,rate)-(a-offset)),
            'sourceOutQuantizationErrorTicks':rational(Fraction(last*1_000_000,rate)-(b-offset)),
            'targetInQuantizationErrorTicks':rational(Fraction(ta*1_000_000,rate)-x),
            'targetOutQuantizationErrorTicks':rational(Fraction(tb*1_000_000,rate)-y),
            'sourceSamplesSHA256':'sha256:'+hashlib.sha256(raw).hexdigest()})
        cursor=tb;requested_cursor=y
    for path,expected in input_hashes.items():need(sha(path)==expected,'input-changed-before-audio-write')
    expected_hash=hashlib.sha256()
    for raw in chunks:expected_hash.update(raw)
    with output.open('xb') as handle:
        with wave.open(handle,'wb') as f:
            f.setnchannels(channels);f.setsampwidth(width);f.setframerate(rate);f.setnframes(cursor)
            for raw in chunks:f.writeframesraw(raw)
        handle.flush();os.fsync(handle.fileno())
    actual_hash=hashlib.sha256();frames_read=0
    with wave.open(str(output),'rb') as f:
        need((f.getnchannels(),f.getsampwidth(),f.getframerate(),f.getnframes(),f.getcomptype())
             ==(channels,width,rate,cursor,'NONE'),'output-pcm-format-or-length-mismatch')
        while True:
            raw=f.readframes(65536)
            if not raw:break
            actual_hash.update(raw);frames_read+=len(raw)//(channels*width)
    need(frames_read==cursor and actual_hash.digest()==expected_hash.digest(),'gain1-output-sample-readback-failed')
    for path,expected in input_hashes.items():need(sha(path)==expected,'input-changed-during-audio-write')
    need(sha(Path(__file__))==code_hash,'assembler-code-changed-during-run')
    receipt={'schema':'capcut-audio-assembly/v1','status':'PREPARED_ONLY_NOT_HEARD','assemblerSHA256':code_hash,
        'outputPath':str(output),'outputSHA256':sha(output),'pcmSamplesSHA256':'sha256:'+actual_hash.hexdigest(),
        'linearGain':1,'sampleRate':rate,'channels':channels,'sampleWidth':width,'frames':cursor,
        'durationSeconds':cursor/rate,'durationTicksExact':rational(Fraction(cursor*1_000_000,rate)),
        'requestedTimelineEndTicks':requested_cursor,'mainPieces':copy.deepcopy(pieces),
        'sourceSampleProjection':rows,'pcmBindings':list(by_source.values()),'inputHashes':input_hashes,
        'quantization':'NEAREST_SAMPLE_HALF_UP_EXACT_RATIONAL_ERRORS_RECORDED',
        'sourceSamplesCopiedExactly':True,'sourceFilesUnchanged':True,'speed':1,
        'resampled':False,'padded':False,'stretched':False,'normalized':False,
        'nativeStoreWrites':0,'userAudioAcceptance':'PENDING','heardContentOrFillerJudgment':'NOT_PERFORMED',
        'limits':'Provenance hashes bind supplied decoder records, not authentication of decoding or original hearing. Caption/onset, actual user audio acceptance and native proof remain separate.'}
    with receipt_path.open('x',encoding='utf-8') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
    need(read(receipt_path)==receipt,'audio-assembly-receipt-readback-failed')
    return receipt

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    try:
        r=assemble_audio(a.plan,a.output)
        print(json.dumps({'status':r['status'],'outputPath':r['outputPath'],'outputSHA256':r['outputSHA256'],
            'frames':r['frames'],'sampleRate':r['sampleRate'],'durationSeconds':r['durationSeconds'],'linearGain':1}));return 0
    except (OSError,ValueError,TypeError,KeyError,wave.Error) as exc:
        print(json.dumps({'status':'BLOCKED','error':str(exc)}));return 2
if __name__=='__main__':raise SystemExit(main())
