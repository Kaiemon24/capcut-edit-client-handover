"""Plan scoped capability checks from current observations; never drives tools.

The calling agent discovers/initializes supported tools and records real results.
This cooperative helper validates identity, provenance types and bounded actions;
it cannot authenticate a reviewer, grant permissions, hear or certify a project.
"""
from pathlib import Path
import argparse,hashlib,json

CAPABILITIES={'media_read','media_decode','speech_candidates','auditory_input','native_frame','native_control','native_writer'}
PROOF_TYPES={'media_read':'FILE_READBACK','media_decode':'DECODED_MEDIA','speech_candidates':'MODEL_OUTPUT','auditory_input':'AUDITORY_INPUT','native_frame':'WINDOW_PIXELS','native_control':'TARGET_CONTROL','native_writer':'COMPATIBILITY_READBACK'}
CONTEXT_KEYS={'sessionId','toolsetHash','audioContext','appVersion','runtimeEpoch','targetId'}
RECOVERY={'native_capture_timeout':'refresh_target','launch_no_window':'reconcile_launch','asr_file_decode_mismatch':'decode_pcm_ndarray','console_encoding':'utf8_output'}
FAILURE_CAPABILITIES={'native_capture_timeout':{'native_frame'},'launch_no_window':{'native_control','native_frame'},'asr_file_decode_mismatch':{'speech_candidates'},'console_encoding':{'media_read','media_decode','speech_candidates'},'uncertain_native_write':{'native_writer'}}

def need(ok,why):
    if not ok:raise ValueError('capability_preflight:'+why)

def evidence_ok(ref):
    need(isinstance(ref,dict),'evidence_object')
    path=Path(ref.get('path',''));h=ref.get('sha256','').removeprefix('sha256:')
    need(path.is_absolute() and path.is_file(),'evidence_file')
    need(not path.is_symlink() and len(h)==64 and all(c in '0123456789abcdef' for c in h),'evidence_identity')
    need(hashlib.sha256(path.read_bytes()).hexdigest()==h,'evidence_drift')

def evaluate(data):
    need(data.get('schemaVersion')=='capcut-capability-session/v1','schema')
    context=data.get('context',{})
    need(set(context)==CONTEXT_KEYS and all(isinstance(v,str) and v.strip() for v in context.values()),'context')
    mode=data.get('outputMode');need(mode in {'EDIT_TIMELINE','SRT_ONLY'},'output_mode')
    need(type(data.get('requiresSpeech')) is bool and type(data.get('catalogComplete')) is bool,'flags')
    relevant={'media_read','media_decode'}
    if data['requiresSpeech']:relevant|={'speech_candidates','auditory_input'}
    if mode=='EDIT_TIMELINE':relevant|={'native_frame','native_control','native_writer'}
    providers=data.get('providers',[]);need(isinstance(providers,list),'providers')
    ids=[]
    for p in providers:
        need(isinstance(p,dict) and isinstance(p.get('id'),str) and p['id'],'provider_id');ids.append(p['id'])
        need(isinstance(p.get('capabilities'),list) and p['capabilities'] and set(p['capabilities'])<=CAPABILITIES,'provider_capabilities')
        need(all(type(p.get(k)) is bool for k in ('available','initialized','scopeAuthorized')),'provider_flags')
        need(p.get('visibility') in {'non_ui','headless','hidden','visible'},'visibility')
        need(type(p.get('visibilitySupported')) is bool and type(p.get('visibilityApproved')) is bool,'visibility_flags')
    need(len(ids)==len(set(ids)),'duplicate_provider')
    denied=data.get('deniedCapabilities',[]);need(isinstance(denied,list) and set(denied)<=CAPABILITIES,'denied_scope')
    obs=data.get('observations',[]);need(isinstance(obs,list),'observations')
    observations={};stale=[];ignored=[]
    for o in obs:
        need(isinstance(o,dict) and o.get('capability') in CAPABILITIES,'observation_target')
        if o['capability'] not in relevant:
            ignored.append({'provider':o.get('provider'),'capability':o['capability']});continue
        need(isinstance(o.get('context'),dict) and set(o['context'])==CONTEXT_KEYS,'observation_context')
        if o.get('context')!=context:
            stale.append({'provider':o.get('provider'),'capability':o['capability']});continue
        need(o.get('provider') in ids,'observation_target')
        need(o['capability'] in next(p['capabilities'] for p in providers if p['id']==o['provider']),'observation_provider_scope')
        need(o.get('status') in {'PASS','FAIL','UNSUPPORTED'},'observation_status')
        key=(o['provider'],o['capability']);need(key not in observations,'duplicate_current_observation')
        evidence_ok(o.get('evidence'))
        if o['status']=='PASS':need(o.get('proofType')==PROOF_TYPES[o['capability']],'wrong_proof_type')
        attempts=o.get('attempts',1);need(type(attempts) is int and 1<=attempts<=20,'attempts')
        used=o.get('usedRecoveries',[]);need(isinstance(used,list) and all(isinstance(x,str) for x in used),'recoveries')
        need(type(o.get('ownerConsulted',False)) is bool,'owner_consulted_boolean')
        allowed=FAILURE_CAPABILITIES.get(o.get('failureKind'))
        need(allowed is None or o['capability'] in allowed,'failure_capability_mismatch')
        observations[key]=o
    def setup_permitted(p):
        return p['available'] and p['scopeAuthorized'] and (p['visibility']=='non_ui' or (p['visibilitySupported'] and (p['visibility']!='visible' or p['visibilityApproved'])))
    def permitted(p):return setup_permitted(p) and p['initialized']
    uncertain=[o for o in observations.values() if o['status']=='FAIL' and o.get('failureKind')=='uncertain_native_write']
    wanted=['media_read','media_decode']
    if data['requiresSpeech']:wanted+=['speech_candidates','auditory_input']
    if mode=='EDIT_TIMELINE':
        transfer_caps=['native_writer','native_control']
        transfer_caps.sort(key=lambda c:0 if any(o['status']=='PASS' and permitted(next(x for x in providers if x['id']==p)) for (p,k),o in observations.items() if k==c) else 1)
        wanted+=['native_frame',*transfer_caps]
    optional={'speech_candidates','native_control','native_writer'}
    actions=[];states={};seen=set()
    def action(kind,cap,pid=None,**extra):
        # One provider init/discovery is enough for its multiple capabilities.
        key=(kind,pid if kind=='initialize_provider' else (cap,pid))
        if key not in seen:
            seen.add(key);actions.append({'kind':kind,'capability':cap,'provider':pid,**extra})
    for cap in wanted:
        if cap in denied:
            states[cap]='DENIED';continue
        if cap.startswith('native_') and uncertain:
            states[cap]='RECONCILE_REQUIRED'
            for o in uncertain:
                p=next(p for p in providers if p['id']==o['provider'])
                if 'native_writer' not in denied and setup_permitted(p):
                    action('reconcile_uncertain_state' if p['initialized'] else 'initialize_provider','native_writer',o['provider'])
            continue
        if cap in {'native_control','native_writer'} and any(states.get(k) in {'CAPABLE','CHECK_PENDING'} for k in {'native_control','native_writer'}-{cap}):
            states[cap]='NOT_SELECTED';continue
        eligible=[p for p in providers if cap in p['capabilities'] and p['available']]
        # Prefer an already proven candidate; a different provider's restriction
        # never disables this one. A real denied target remains global above.
        eligible.sort(key=lambda p:0 if observations.get((p['id'],cap),{}).get('status')=='PASS' else 2 if (p['id'],cap) in observations else 1)
        results=[]
        for p in eligible:
            pid=p['id'];o=observations.get((pid,cap))
            if not p['scopeAuthorized']:
                results.append('NEEDS_AUTHORITY');continue
            if p['visibility']!='non_ui':
                if not p['visibilitySupported']:
                    results.append('UNAVAILABLE');continue
                if p['visibility']=='visible' and not p['visibilityApproved']:
                    results.append('NEEDS_VISIBILITY');continue
            if not p['initialized']:
                action('initialize_provider',cap,pid);results.append('CHECK_PENDING');break
            if o is None:
                action('probe_capability',cap,pid);results.append('CHECK_PENDING');break
            if o['status']=='PASS':results=['CAPABLE'];break
            if o['status']=='UNSUPPORTED':results.append('UNAVAILABLE');continue
            if o.get('failureKind')=='uncertain_native_write':
                action('reconcile_uncertain_state',cap,pid);results.append('CHECK_PENDING');break
            recovery=RECOVERY.get(o.get('failureKind'))
            if recovery and o.get('attempts',1)<2 and recovery not in o.get('usedRecoveries',[]):
                # Decoder recovery requires a current proven local decoding path.
                decode_ready=states.get('media_decode')=='CAPABLE'
                if recovery!='decode_pcm_ndarray' or decode_ready:
                    action('known_recovery',cap,pid,recovery=recovery);results.append('CHECK_PENDING');break
            if not recovery and not o.get('ownerConsulted',False):action('consult_functional_owner',cap,pid,reason='New fault outside bounded known activation paths; consult internally without a new continuation menu')
            results.append('UNAVAILABLE')
        if not any(v in {'CAPABLE','CHECK_PENDING'} for v in results) and not data['catalogComplete']:
            action('discover_supported_providers',cap);results.append('CHECK_PENDING')
        states[cap]='CAPABLE' if 'CAPABLE' in results else 'CHECK_PENDING' if 'CHECK_PENDING' in results else 'NEEDS_AUTHORITY' if 'NEEDS_AUTHORITY' in results else 'NEEDS_VISIBILITY' if 'NEEDS_VISIBILITY' in results else 'UNAVAILABLE'
    # Control and a compatible filesystem writer are alternative transfer paths.
    transfer=mode=='SRT_ONLY' or any(states.get(k)=='CAPABLE' for k in ('native_control','native_writer'))
    blockers=[{'capability':c,'state':s} for c,s in states.items() if c not in optional and s!='CAPABLE']
    if not transfer:blockers.append({'capability':'native_transfer','state':'NO_PROVEN_TRANSFER_ROUTE'})
    prep=all(states.get(k)=='CAPABLE' for k in ('media_read','media_decode'))
    return {'schemaVersion':'capcut-capability-plan/v1','context':context,'outputMode':mode,'capabilities':states,'actions':actions,'blockers':blockers,'staleObservations':stale,'ignoredObservations':ignored,'preparationReady':prep,'transferCapabilityReady':transfer,'status':'CHECKS_PENDING' if actions else 'CAPABILITY_PARTIAL' if blockers else 'CAPABILITY_READY','nativeMutationAuthorized':False,'projectAcceptance':'NOT_ASSESSED','limits':'Cooperative observations and hashes only. Caller must perform supported actions under existing authority. ASR, UIA, initialization or a capability PASS never proves actual words/onsets, native playback or save/reopen.'}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--input',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    result=evaluate(json.loads(args.input.read_text(encoding='utf-8-sig')))
    with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'status':result['status'],'actions':len(result['actions']),'blockers':len(result['blockers']),'nativeMutationAuthorized':False}))
if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps({'status':'INVALID','error':str(exc)}));raise SystemExit(2)
