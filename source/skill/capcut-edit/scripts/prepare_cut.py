"""Prepare reviewed phrase captions and original-source ranges; no app writes/network."""
from pathlib import Path
import argparse, copy, csv, hashlib, io, json, math, re, unicodedata
from project_naming import resolve_project_identity, selected_profile
from source_hash_session import digest as _verified_digest

def number(value):
    if type(value) not in (int,float) or not math.isfinite(value): raise ValueError('Finite numeric time required')
    return value

def hash_file(path):
    return _verified_digest(path)

def unique(rows, label):
    if not isinstance(rows,list) or not rows: raise ValueError(label+' must be nonempty')
    result={}
    for row in rows:
        if not isinstance(row,dict):raise ValueError(label+' row must be an object')
        key=row.get('id')
        if not isinstance(key,str) or not key or key in result: raise ValueError('Duplicate/missing '+label+' id')
        result[key]=row
    return result

def verified(row):
    return row.get('reviewed') is True and isinstance(row.get('evidenceRef'),str) and bool(row['evidenceRef'].strip())

def srt_time(value):
    ms=round(value*1000); h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'

def exact_text(value):
    if not isinstance(value,str) or not value.strip() or any(c in value for c in '\r\n\x00'):
        raise ValueError('Nonempty one-paragraph text required')
    return ' '.join(value.split())

def caption_policy(plan):
    policy={'maxWordsPerCue':6,'aimWordsPerCue':[5,6],'removeFullStops':True,
            'retainInternalCommas':True,'removeTrailingCommas':True,
            'preserveReviewedColonAndQuestionMark':True,'requireSingleReviewedSentence':True,
            'capitalization':'verified-names-only','gapless':True}
    override=plan.get('captionPolicyOverride')
    if override is not None:
        if not isinstance(override,dict) or override.get('authority')!='explicit-user-request' or not str(override.get('evidenceRef','')).strip():
            raise ValueError('Caption override needs an explicit user request and evidence')
        allowed={'authority','evidenceRef','maxWordsPerCue','removeFullStops','retainInternalCommas','removeTrailingCommas','removeCommasAndFullStops','capitalization','gapless'}
        if set(override)-allowed:raise ValueError('Unknown caption override field')
        for key in allowed-{'authority','evidenceRef','removeCommasAndFullStops'}:
            if key in override:policy[key]=override[key]
        if 'removeCommasAndFullStops' in override:
            legacy=override['removeCommasAndFullStops']
            if type(legacy) is not bool or any(k in override for k in ('removeFullStops','retainInternalCommas')):
                raise ValueError('Legacy punctuation override must be an unambiguous explicit boolean')
            policy['removeFullStops']=legacy;policy['retainInternalCommas']=not legacy
        limit=policy['maxWordsPerCue']
        if limit is not None and (type(limit) is not int or limit<1):raise ValueError('Positive word limit or explicit null required')
        if any(type(policy[key]) is not bool for key in ('removeFullStops','retainInternalCommas','removeTrailingCommas','gapless')):
            raise ValueError('Explicit boolean caption override required')
        if policy['capitalization'] not in ('verified-names-only','source'):raise ValueError('Unknown caption capitalization')
    return policy

def display_words(words, take_id, plan, policy, membership):
    """Apply reviewed display conventions only after raw audio/script fidelity checks."""
    conversions={}
    for row in plan.get('numericConversions',[]):
        if not isinstance(row,dict) or not verified(row):raise ValueError('Numeric conversion needs review evidence')
        key=(row.get('takeId'),row.get('wordId'))
        if key in conversions:raise ValueError('Duplicate numeric conversion')
        text=exact_text(row.get('displayText'))
        if policy['removeFullStops'] and '.' in text:raise ValueError('Reviewed numeric display must have no full stops')
        conversions[key]=row
    tokens=[];owners=[]
    for index,w in enumerate(words):
        text=w['text'];row=conversions.get((take_id,w['id']))
        numeric=bool(re.search(r'(?<=\d)[,.](?=\d)',text))
        if row is not None:
            if row.get('sourceText')!=text or not numeric:raise ValueError('Numeric conversion does not match the source word')
            text=exact_text(row.get('displayText'))
        elif (bool(re.search(r'(?<=\d)\.(?=\d)',text)) and policy['removeFullStops']) or (numeric and not policy['retainInternalCommas'] and ',' in text):
            raise ValueError('Ambiguous numeric punctuation needs a reviewed conversion')
        if policy['removeFullStops']:text=text.replace('.','')
        if not policy['retainInternalCommas']:text=text.replace(',','')
        if not text.strip():raise ValueError('Caption display cannot erase a word')
        if policy['capitalization']=='verified-names-only':text=text.lower()
        pieces=text.split();tokens.extend(pieces);owners.extend([index]*len(pieces))
    names={}
    for row in plan.get('verifiedNames',[]):
        if not isinstance(row,dict) or not verified(row):raise ValueError('Proper name needs review evidence')
        name=exact_text(row.get('text'))
        if policy['removeFullStops']:name=name.replace('.','')
        if not policy['retainInternalCommas']:name=name.replace(',','')
        key=tuple(t.lower().rstrip(',:?') for t in name.split());value=[t.rstrip(',:?') for t in name.split()]
        if not key or (key in names and names[key]!=value):raise ValueError('Conflicting or empty verified name')
        names[key]=value
    if policy['capitalization']=='verified-names-only':
        index=0
        while index<len(tokens):
            matches=[key for key in names if tuple(t.lower().rstrip(',:?') for t in tokens[index:index+len(key)])==key and len({membership[words[owner]['id']] for owner in owners[index:index+len(key)]})==1]
            if matches:
                key=max(matches,key=len)
                tokens[index:index+len(key)]=[name+t[len(t.rstrip(',:?')):] for name,t in zip(names[key],tokens[index:index+len(key)])]
                index+=len(key)
            else:index+=1
    result=['']*len(words)
    for token,owner in zip(tokens,owners):result[owner]+=(' ' if result[owner] else '')+token
    return result

def nga_style_selection(plan, require_recipient=False):
    """Resolve supplied recipient/domain facts; never infer a person from a filename or topic."""
    style=plan.get('style')
    if style is None:style={}
    if not isinstance(style,dict):raise ValueError('Saved style selection must be an object')
    selected=style.get('selectedId')
    if selected is not None and (not isinstance(selected,str) or not selected.strip()):raise ValueError('Saved style ID must be a nonempty string')
    recipient=plan.get('recipient')
    known=isinstance(recipient,dict) and verified(recipient) and recipient.get('kind') in ('PERSON','ORGANIZATION') and isinstance(recipient.get('id'),str) and bool(recipient['id'].strip()) and isinstance(recipient.get('label'),str) and bool(recipient['label'].strip())
    if not known:
        return {'status':'NEEDS_RECIPIENT' if require_recipient or selected=='nga' else 'NOT_SELECTED','applies':False,'question':'Clip này làm cho ai?','evidenceRef':None}
    base={'recipientId':recipient['id'],'recipientEvidenceRef':recipient['evidenceRef'],'selectedId':selected,'applies':False}
    if selected not in (None,'nga'):return dict(base,status='NOT_APPLICABLE',reason='Explicit different saved style preserved')
    if recipient['kind']!='PERSON' or recipient['id']!='mrs-nga':return dict(base,status='NOT_APPLICABLE',reason='Recipient is not confirmed person Mrs Nga')
    domain=plan.get('contentDomain')
    if not isinstance(domain,dict) or not verified(domain) or not isinstance(domain.get('id'),str) or not domain['id'].strip():
        return dict(base,status='NEEDS_DOMAIN',question='Clip cho Mrs Nga này có thuộc nội dung bất động sản không?')
    base.update(domainId=domain['id'],domainEvidenceRef=domain['evidenceRef'])
    if domain['id']!='real-estate':return dict(base,status='NOT_APPLICABLE',reason='Confirmed content domain is not real estate')
    return dict(base,status='APPLIES',applies=True,effectiveStyleId='nga',selectionBasis='confirmed-person-Mrs-Nga-and-real-estate-no-explicit-different-style')

def nga_emoji_display(words, displayed, plan, membership):
    """Exact saved-style display only; keep all raw IDs/times and original display for reversal."""
    binding=nga_style_selection(plan)
    if binding['status'] in ('NEEDS_RECIPIENT','NEEDS_DOMAIN'):raise ValueError('GATE0_STYLE_BINDING_REQUIRED: '+binding['question'])
    if not binding['applies']:return list(displayed),[],binding
    result=[unicodedata.normalize('NFC',text) for text in displayed]
    flat='';owners=[];offsets=[]
    for index,text in enumerate(result):
        if not text:continue
        if flat:flat+=' ';owners.append(None);offsets.append(None)
        for offset,ch in enumerate(text):flat+=ch;owners.append(index);offsets.append(offset)
    patterns=[('bất động sản',r'(?<!\w)bất\s+động\s+sản(?!\w)','🏡'),('sale',r'(?<!\w)sale(?!\w)','👨‍💼👩‍💼'),('deal',r'(?<!\w)deal(?!\w)','🤝📝')]
    matches=[]
    def word_edge(ch):return ch=='_' or ch.isalnum() or unicodedata.category(ch).startswith('M') or unicodedata.category(ch)=='Cf'
    for source,pattern,replacement in patterns:
        for match in re.finditer(pattern,flat,re.IGNORECASE):
            start,end=match.span()
            if (start and word_edge(flat[start-1])) or (end<len(flat) and word_edge(flat[end])):continue
            first,last=owners[start],owners[end-1]
            if first is None or last is None:raise ValueError('Invalid style token ownership')
            raw=words[first:last+1];sid=membership[raw[0]['id']]
            if any(membership[w['id']]!=sid for w in raw):raise ValueError('Style replacement cannot cross a reviewed logical sentence')
            matches.append({'start':start,'end':end,'first':first,'last':last,'localStart':offsets[start],'localEnd':offsets[end-1]+1,'source':source,'replacement':replacement,'matchedDisplayText':match.group(),'sentenceId':sid})
    matches.sort(key=lambda m:m['start'])
    if any(a['end']>b['start'] for a,b in zip(matches,matches[1:])):raise ValueError('Overlapping saved-style matches')
    transforms=[]
    for n,m in enumerate(matches,1):
        first,last=m['first'],m['last'];raw=words[first:last+1];replacement=m['replacement']
        transforms.append({'id':'nga-emoji-'+str(n),'profileId':'nga','operation':'SAVED_MRS_NGA_REAL_ESTATE_EXACT_EMOJI_DISPLAY','startWord':first,'endWord':last+1,'sentenceId':m['sentenceId'],'rawWordIds':[w['id'] for w in raw],'rawText':' '.join(w['text'] for w in raw),'rawWords':[{'id':w['id'],'text':w['text']} for w in raw],'beforeDisplayByWord':list(displayed[first:last+1]),'matchedDisplayText':m['matchedDisplayText'],'matchedWholeTerm':m['source'],'displayReplacement':replacement,'replacementAtomic':True,'replacementCodepoints':len(replacement),'replacementUtf16Units':len(replacement.encode('utf-16-le'))//2,'bindingEvidence':binding})
    for m in reversed(matches):
        first,last=m['first'],m['last']
        result[first]=result[first][:m['localStart']]+m['replacement']+result[last][m['localEnd']:]
        for index in range(first+1,last+1):result[index]=''
    return result,transforms,binding

def enumeration_contract(plan, takes):
    """Bind optional reviewed list order; authorization is display-only, never audio truth."""
    lists=plan.get('reviewedEnumerations',[])
    if not isinstance(lists,list):raise ValueError('Explicit reviewed enumeration inventory required')
    if not lists:return {}
    auth=plan.get('enumerationDisplayAuthorization')
    if not isinstance(auth,dict) or auth.get('authority')!='explicit-user-request' or not str(auth.get('evidenceRef','')).strip() or auth.get('scope')!='reviewed-ordinal-lead-in-to-numbered-caption-prefix':
        raise ValueError('Enumeration display needs exact explicit user authorization; no general word deletion')
    unique(lists,'enumeration');by_take={};item_ids=set()
    for listing in lists:
        if not verified(listing) or listing.get('basis')!='reviewed-spoken-enumeration' or listing.get('complete') is not True:raise ValueError('Complete spoken enumeration review required')
        items=listing.get('items');unique(items,'enumeration item')
        for ordinal,item in enumerate(items,1):
            if not verified(item) or type(item.get('ordinal')) is not int or item['ordinal']!=ordinal or item.get('takeId') not in takes or item.get('leadInOnly') is not True:
                raise ValueError('Reviewed enumeration items must be ordered1..N and bind a known take and lead-in-only assertion')
            if item['id'] in item_ids:raise ValueError('Duplicate enumeration item identity')
            item_ids.add(item['id']);by_take.setdefault(item['takeId'],[]).append(dict(item,listId=listing['id'],listItemCount=len(items),listEvidenceRef=listing['evidenceRef']))
    return by_take

def enumeration_display(words, displayed, items, membership):
    """Replace only reviewed raw lead-ins; every raw ID remains in transform evidence."""
    result=list(displayed);positions={w['id']:i for i,w in enumerate(words)};transforms=[];previous=-1
    vi={1:('nhất','một'),2:('hai',),3:('ba',),4:('tư','bốn'),5:('năm',),6:('sáu',),7:('bảy',),8:('tám',),9:('chín',),10:('mười',)}
    for item in items:
        ids=item.get('leadInWordIds');marker_ids=item.get('markerWordIds')
        if not isinstance(ids,list) or not ids or any(i not in positions for i in ids) or not isinstance(marker_ids,list) or not marker_ids or any(i not in ids for i in marker_ids):raise ValueError('Enumeration raw lead-in and marker word IDs required')
        start=positions[ids[0]];end=start+len(ids);span=words[start:end]
        if [w['id'] for w in span]!=ids or start<previous:raise ValueError('Enumeration lead-ins must be contiguous, ordered and nonoverlapping')
        marker_start=positions[marker_ids[0]];marker_end=marker_start+len(marker_ids)
        if [w['id'] for w in words[marker_start:marker_end]]!=marker_ids or not start<=marker_start<marker_end<=end:raise ValueError('Enumeration marker must be contiguous within its lead-in')
        sid=item.get('sentenceId')
        long=len(' '.join(w['text'] for w in span).split())>4
        content_sid=item.get('firstContentSentenceId',sid) if long else sid
        if end>=len(words) or words[end]['id']!=item.get('firstContentWordId') or any(membership[w['id']]!=sid for w in span) or membership[words[end]['id']]!=content_sid:raise ValueError('Enumeration prefix and first content word must be adjacent within one reviewed sentence, or bind a preserved long lead-in/content sentence')
        if long and (item.get('preserveLongLeadIn') is not True or not str(item.get('preserveEvidenceRef','')).strip()):raise ValueError('Long enumeration lead-in over four raw words must be preserved with explicit review evidence')
        raw=' '.join(w['text'] for w in span)
        if exact_text(item.get('leadInText'))!=raw:raise ValueError('Enumeration lead-in text changes raw words')
        marker_raw=' '.join(w['text'].strip('.,:?').lower() for w in words[marker_start:marker_end])
        marker=marker_raw.removeprefix('và ').removesuffix(' là')
        ordinal=item['ordinal'];meaning=item.get('markerMeaning')
        if meaning=='final-item':
            if marker not in ('cuối cùng','điểm cuối cùng') or ordinal!=item['listItemCount']:raise ValueError('Final enumeration marker must be reviewed as the final list item')
        elif meaning=='ordinal':
            endings=(*vi.get(ordinal,()),str(ordinal));valid={prefix+ending for prefix in ('thứ ','điểm thứ ') for ending in endings}
            if marker not in valid:raise ValueError('Spoken ordinal marker disagrees with reviewed list number')
        else:raise ValueError('Enumeration marker meaning must be ordinal or reviewed final-item')
        normalized=' '.join(w['text'].strip('.,:?').lower() for w in span)
        allowed_lead_ins={before+marker+after for before in ('','và ','điểm ','yếu tố ') for after in ('',' là',' thì',' chính là',' là về')}
        if not long and normalized not in allowed_lead_ins:raise ValueError('Reviewed ordinal lead-in contains content or unsupported wording; no general word deletion')
        prefix=str(ordinal)+'.'
        if not long:
            result[start]=prefix
            for index in range(start+1,end):result[index]=''
        content=result[end];parts=content.split()
        if not parts:raise ValueError('Enumeration first content word cannot disappear')
        first=parts[0];parts[0]=first[:1].upper()+first[1:];result[end]=(prefix+' ' if long else '')+' '.join(parts)
        transform={'id':item['id'],'listId':item['listId'],'ordinal':ordinal,'startWord':end if long else start,'endWord':end+1 if long else end,'firstContentWord':end,'sentenceId':content_sid,'rawWordIds':[words[end]['id']] if long else ids,'markerWordIds':marker_ids,'firstContentWordId':words[end]['id'],'rawLeadIn':raw,'displayPrefix':prefix,'evidenceRef':item['evidenceRef'],'listEvidenceRef':item['listEvidenceRef'],'operation':'PRESERVE_LONG_LEAD_IN_AND_PREFIX_CONTENT' if long else 'AUTHORIZED_REVIEWED_LEAD_IN_TO_PREFIX_ONLY'}
        if long:transform.update(preservedLeadInWordIds=ids,preservedStartWord=start,preservedEndWord=end,preservedSentenceId=sid,preserveEvidenceRef=item['preserveEvidenceRef'],rawLeadInWordCount=len(raw.split()),leadInDisplay=' '.join(result[start:end]))
        transforms.append(transform)
        previous=end+1
    return result,transforms

def sentence_membership(words, sentences):
    """Validate reviewed logical-sentence partition before display punctuation is removed."""
    unique(sentences,'reviewed sentence')
    membership={};cursor=0
    for sentence in sentences:
        if not verified(sentence) or sentence.get('boundaryBasis')!='reviewed-logical-sentence':
            raise ValueError('Sentence boundaries need logical-meaning review evidence, not ASR segments')
        ids=sentence.get('wordIds')
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) for i in ids):
            raise ValueError('Sentence word IDs required')
        span=words[cursor:cursor+len(ids)]
        if [w['id'] for w in span]!=ids:raise ValueError('Sentence ranges must cover raw words contiguously, once')
        if exact_text(sentence.get('text'))!=' '.join(w['text'] for w in span):
            raise ValueError('Sentence text changes raw words')
        for word in span:membership[word['id']]=sentence['id']
        cursor+=len(ids)
    if cursor!=len(words):raise ValueError('Sentence ranges omit raw words')
    return membership

def protected_spans(words, spans, review, displayed, policy, membership, enumerations=()):
    """Check supplied whole-transcript review and raw protected spans; no NLP/audio proof."""
    if not isinstance(review,dict) or not verified(review) or review.get('basis')!='whole-transcript-semantic-review' or review.get('wordIds')!=[w['id'] for w in words]:
        raise ValueError('Whole-transcript semantic review must cover every selected raw word in order')
    if not isinstance(spans,list):raise ValueError('Explicit reviewed protected-span inventory required')
    if spans:unique(spans,'protected span')
    positions={w['id']:i for i,w in enumerate(words)};result=[];seen=set()
    for span in spans:
        if not verified(span) or span.get('kind') not in ('noun-phrase','adjective-phrase','verb-phrase','proper-name','term','number-unit'):
            raise ValueError('Protected span needs a typed semantic review and evidence')
        ids=span.get('wordIds')
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in positions for i in ids):
            raise ValueError('Protected span raw word IDs required')
        start=positions[ids[0]];end=start+len(ids);raw=words[start:end]
        if [w['id'] for w in raw]!=ids:raise ValueError('Protected span must be contiguous and ordered')
        sid=span.get('sentenceId')
        if not isinstance(sid,str) or not sid or any(membership[w['id']]!=sid for w in raw):
            raise ValueError('Protected span must stay within one reviewed logical sentence')
        if exact_text(span.get('text'))!=' '.join(w['text'] for w in raw):raise ValueError('Protected span text changes raw words')
        key=(start,end,span['kind'])
        if key in seen:raise ValueError('Duplicate protected span assertion')
        seen.add(key)
        result.append({'id':span['id'],'startWord':start,'endWord':end,'sentenceId':sid,'wordIds':ids,'rawText':span['text'],'displayText':' '.join(displayed[start:end]),'kind':span['kind'],'evidenceRef':span['evidenceRef']})
    unions=[]
    for span in sorted(result,key=lambda r:(r['startWord'],r['endWord'])):
        if unions and span['startWord']<unions[-1][1]:unions[-1][1]=max(unions[-1][1],span['endWord'])
        else:unions.append([span['startWord'],span['endWord']])
    limit=policy['maxWordsPerCue']
    if limit is not None:
        for start,end in unions:
            if len(' '.join(displayed[start:end]).split())>limit and not any(e.get('preservedStartWord')<=start and end<=e.get('preservedEndWord') for e in enumerations if e.get('operation')=='PRESERVE_LONG_LEAD_IN_AND_PREFIX_CONTENT'):
                raise ValueError('Protected semantic-unit conflict: overlapping union exceeds displayed word limit; reviewed resolution required without silent shortening or splitting')
    return result

def captions(words, phrases, take_start, take_end, displayed, policy, membership, protected, enumerations=(), style_transforms=()):
    """Validate reviewed short cue groups; never invent grouping or word timings."""
    unique(words,'word');unique(phrases,'phrase')
    cursor=0;previous=take_start;result=[];lengths=[]
    for phrase in phrases:
        if phrase.get('role')!='main' or not verified(phrase):raise ValueError('Phrase needs main-speaker review evidence')
        ids=phrase.get('wordIds')
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) for i in ids):
            raise ValueError('Phrase word IDs required')
        span=words[cursor:cursor+len(ids)]
        if [w['id'] for w in span]!=ids:raise ValueError('Phrase words must cover speech contiguously, once')
        boundary=cursor+len(ids)
        if any(s['startWord']<cursor<s['endWord'] or s['startWord']<boundary<s['endWord'] for s in protected):
            raise ValueError('Caption boundary splits a reviewed protected semantic span')
        preserved=[e for e in enumerations if e.get('operation')=='PRESERVE_LONG_LEAD_IN_AND_PREFIX_CONTENT']
        for e in preserved:
            a,b=e['preservedStartWord'],e['preservedEndWord']
            if a<cursor<b or a<boundary<b or cursor<=a<boundary and (cursor!=a or boundary!=b):raise ValueError('Preserved long enumeration lead-in must remain one exact cue')
            if cursor<e['firstContentWord']<boundary:raise ValueError('Numbered main content must begin a new cue after preserved lead-in')
        if any(e['startWord']<cursor<=e['firstContentWord'] or e['startWord']<boundary<=e['firstContentWord'] for e in enumerations):
            raise ValueError('Caption boundary splits the reviewed ordinal prefix from its first content word')
        if any(e['startWord']<cursor<e['endWord'] or e['startWord']<boundary<e['endWord'] for e in style_transforms):
            raise ValueError('Caption boundary splits an atomic saved-style emoji replacement')
        sentence_id=phrase.get('sentenceId')
        if not isinstance(sentence_id,str) or not sentence_id or any(membership[w['id']]!=sentence_id for w in span):
            raise ValueError('Caption must stay within one reviewed logical sentence')
        text=exact_text(phrase.get('text'))
        if text!=' '.join(w['text'] for w in span):raise ValueError('Phrase text changes audible words')
        start,end=number(phrase.get('start')),number(phrase.get('end'))
        if not take_start<=start<end<=take_end or start<previous:
            raise ValueError('Phrase crosses trim or overlaps previous phrase')
        if start>span[0]['start'] or end<span[-1]['end']:
            raise ValueError('Phrase excludes part of its words')
        if any(cursor==e['firstContentWord'] for e in preserved) and start!=span[0]['start']:raise ValueError('Long-enumeration main content cue must start at its first raw word; final audio review still required')
        display=' '.join(part for part in displayed[cursor:cursor+len(ids)] if part)
        if policy['removeTrailingCommas']:display=display.rstrip(',').rstrip()
        limit=policy['maxWordsPerCue']
        if limit is not None and len(display.split())>limit and not any(cursor==e['preservedStartWord'] and boundary==e['preservedEndWord'] for e in preserved):raise ValueError('Caption exceeds the displayed word limit; review shorter cue groups')
        result.append({'start':start,'end':end,'text':display,'rawText':text,'wordIds':ids,'sentenceId':sentence_id,'protectedSpanIds':[s['id'] for s in protected if cursor<=s['startWord'] and s['endWord']<=boundary],'enumerationTransforms':[e for e in enumerations if cursor<=e['startWord'] and e['firstContentWord']<boundary],'styleDisplayTransforms':[e for e in style_transforms if cursor<=e['startWord'] and e['endWord']<=boundary]});lengths.append((sentence_id,len(ids)))
        cursor+=len(ids);previous=end
    if cursor!=len(words):raise ValueError('Phrase captions omit spoken words')
    for sentence_id in set(membership.values()):
        groups=[n for sid,n in lengths if sid==sentence_id]
        if len(groups)>1 and all(n==1 for n in groups):raise ValueError('Word-by-word caption fragmentation prohibited')
    return result

def prepare_intake(brief):
    """Check consequential input dependencies only; no export, ASR or acceptance proof."""
    if not isinstance(brief,dict) or brief.get('schemaVersion')!='capcut-brief/v1':raise ValueError('Task-owned caption brief v1 required')
    output=brief.get('output',{})
    if not isinstance(output,dict):raise ValueError('Output binding object required')
    mode=output.get('mode')
    if mode not in (None,'EDIT_TIMELINE','SRT_ONLY'):raise ValueError('Unknown output mode; no implicit fallback')
    report={'status':'PREPARED_ONLY','outputMode':mode,'inputDependencies':[],'nextQuestion':None,'audioTruth':'PENDING','nativeAcceptance':'PENDING' if mode=='EDIT_TIMELINE' else 'NOT_APPLICABLE' if mode=='SRT_ONLY' else 'PENDING','fileAcceptance':'PENDING','limitations':['This report checks supplied metadata and identity, not actual audio hearing, export provenance, word alignment, SRT acceptance or native playback/persistence.','Audio-file receipt and app failure never authorize changing a known output mode.']}
    def missing(kind,question):
        report['inputDependencies'].append(kind)
        if report['nextQuestion'] is None:report['nextQuestion']=question
    style_binding=nga_style_selection(brief,require_recipient=True)
    report['savedStyleSelection']=style_binding
    if style_binding['status']=='NEEDS_RECIPIENT':missing('RECIPIENT','Clip này làm cho ai?')
    elif style_binding['status']=='NEEDS_DOMAIN':missing('CONTENT_DOMAIN',style_binding['question'])
    if mode is None:missing('OUTPUT_MODE','Edit/add captions in the named CapCut timeline, or create an SRT file only? Reuse any known answer.')
    elif not isinstance(output.get('modeEvidence'),str) or not output['modeEvidence'].strip():raise ValueError('Bound output mode needs user-request evidence')
    scope=brief.get('workScope')
    if scope not in ('CONTENT_EDIT','SUB_ONLY'):missing('WORK_SCOPE','Which already authorized scope needs captions: content editing or captions on the existing edited clip?')
    needs_asr=brief.get('requiresTranscription')
    if type(needs_asr) is not bool or not isinstance(brief.get('transcriptionRequirementEvidenceRef'),str) or not brief['transcriptionRequirementEvidenceRef'].strip():missing('TRANSCRIPTION_NEED','Bind whether transcription is needed and the available aligned transcript/audio evidence.')
    if needs_asr is True:
        audio=brief.get('audioInput')
        if not isinstance(audio,dict) or audio.get('status')!='AVAILABLE':
            missing('AUDIO_SOURCE','Provide sufficient audio from the exact edited timeline including pauses, joins and speed changes, or an authorized usable audio source with its clock evidence.')
        else:
            path=Path(audio.get('path',''))
            if not path.is_absolute() or not path.is_file() or path.is_symlink():raise ValueError('Available audio must bind an existing absolute regular source')
            for parent in path.parents:
                if parent.is_symlink() or (hasattr(parent,'is_junction') and parent.is_junction()):raise ValueError('Linked audio source')
            if not re.fullmatch(r'sha256:[0-9a-f]{64}',audio.get('sha256','')) or hash_file(path)!=audio['sha256']:raise ValueError('Audio identity/hash mismatch')
            duration=number(audio.get('durationSeconds'))
            if duration<=0:raise ValueError('Positive supplied audio duration required')
            report['audioIdentity']={'path':str(path),'sha256':audio['sha256'],'durationSeconds':duration}
            clock=audio.get('clockBasis')
            if clock not in ('EDITED_TIMELINE','ORIGINAL_SOURCE','AUDIO_FILE','UNKNOWN'):raise ValueError('Unknown audio clock basis')
            proof=isinstance(audio.get('timingEvidenceRef'),str) and bool(audio['timingEvidenceRef'].strip())
            if clock=='UNKNOWN' or not proof:missing('AUDIO_CLOCK','Confirm the supplied audio clock/range and any start offset; duration or filename alone is insufficient.')
            elif clock=='EDITED_TIMELINE':
                actual=audio.get('exportRange');intended=audio.get('intendedExportRange')
                if not isinstance(actual,dict) or not isinstance(intended,dict) or actual!=intended:raise ValueError('Edited export must cover the whole reviewed intended interval')
                start,end=number(actual.get('startSeconds')),number(actual.get('endSeconds'))
                if not 0<=start<end or abs((end-start)-duration)>.001 or number(audio.get('startOffsetSeconds'))!=start:raise ValueError('Edited export duration/range/start offset disagree')
                if audio.get('preservesPausesCutsAndSpeed') is not True or not isinstance(audio.get('currentTimelineIdentityRef'),str) or not audio['currentTimelineIdentityRef'].strip():raise ValueError('Edited audio needs current timeline identity and whole interval including pauses/cuts/speed')
            elif mode=='EDIT_TIMELINE':
                edit_map=audio.get('reviewedEditMap')
                if not isinstance(edit_map,dict) or not verified(edit_map) or edit_map.get('sourceSha256')!=audio['sha256'] or not isinstance(edit_map.get('targetTimelineIdentityRef'),str) or not edit_map['targetTimelineIdentityRef'].strip():missing('REVIEWED_SOURCE_TO_TIMELINE_MAP','Bind the reviewed source-to-edited-timeline map before assigning caption timestamps.')
            report['audioClockBasis']=clock
    if mode=='EDIT_TIMELINE':
        effective_style=style_binding.get('effectiveStyleId') or style_binding.get('selectedId')
        known_identity=brief.get('projectIdentity')
        known_name=isinstance(known_identity,dict) and known_identity.get('name') is not None and known_identity.get('name')!=''
        profile=None if known_name else selected_profile(effective_style)
        identity=resolve_project_identity(brief,profile,effective_style)
        report['projectIdentity']=identity
        if identity['nextQuestion'] is not None:missing('PROJECT_IDENTITY',identity['nextQuestion'])
    if mode=='EDIT_TIMELINE' and brief.get('appStatus')=='BLOCKED':report['nativeAcceptance']='BLOCKED'
    report['readyForAuthorizedPreparation']=not report['inputDependencies']
    return {'caption-intake-report.json':json.dumps(report,ensure_ascii=False,indent=2)+'\n'}

def prepare(plan):
    if not isinstance(plan,dict) or plan.get('schemaVersion')!='capcut-cut-plan/v2':raise ValueError('Reviewed phrase v2 plan required')
    policy=caption_policy(plan)
    name=plan.get('name','')
    if not isinstance(name,str) or not name.strip() or any(c in name for c in '/\\:<>"|?*') or any(ord(c)<32 or ord(c)==127 for c in name) or name.endswith((' ','.')) or name in ('.','..'):
        raise ValueError('Safe project name required')
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)',name,re.I):raise ValueError('Reserved project name')
    canvas=plan.get('canvas',{})
    if not isinstance(canvas,dict) or any(type(canvas.get(k)) is not int or canvas[k]<=0 for k in ('width','height')) or number(canvas.get('fps',0))<=0:raise ValueError('Canvas required')
    sources=unique(plan.get('sources'),'source');units=unique(plan.get('units'),'unit');takes=unique(plan.get('takes'),'take')
    orders=set()
    for source in sources.values():
        path=Path(source.get('path',''))
        if not path.is_absolute() or not path.is_file() or path.is_symlink() or path.suffix.lower() not in ('.mp4','.mov','.mkv','.m4v'):
            raise ValueError('Existing absolute regular media required')
        for parent in path.parents:
            if parent.is_symlink() or (hasattr(parent,'is_junction') and parent.is_junction()):raise ValueError('Linked source path')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',source.get('sha256','')) or hash_file(path)!=source['sha256']:raise ValueError('Source hash mismatch')
        if number(source.get('duration',0))<=0:raise ValueError('Source duration required')
        order=source.get('recordingOrder')
        if type(order) is not int or order<0 or order in orders:raise ValueError('Unique recording chronology required')
        orders.add(order)
    script=plan.get('script',{'mode':'REFERENCE_ONLY','evidenceRef':'capcut-default-script-reference-only'})
    if not isinstance(script,dict) or script.get('mode') not in ('EXACT_CONTENT','REFERENCE_ONLY'):raise ValueError('Known script mode EXACT_CONTENT or REFERENCE_ONLY required')
    if 'script' in plan and not (isinstance(script.get('evidenceRef'),str) and script['evidenceRef'].strip()):raise ValueError('Explicit script mode needs scoped evidence')
    script_mode=script['mode']
    unit_text_field='scriptText' if script_mode=='EXACT_CONTENT' else 'spokenText'
    for unit in units.values():
        if not isinstance(unit.get(unit_text_field),str) or not unit[unit_text_field].strip():raise ValueError('Script meaning required' if script_mode=='EXACT_CONTENT' else 'Reviewed actual spoken unit text required')
        if script_mode=='REFERENCE_ONLY' and not verified(unit):raise ValueError('Reference-only units need actual spoken-content review evidence')
    for take in takes.values():
        if take.get('unitId') not in units or take.get('sourceId') not in sources:raise ValueError('Unknown take reference')
        if not verified(take):raise ValueError('Every take needs review evidence')
        start,end=number(take.get('in')),number(take.get('out'))
        if not 0<=start<end<=sources[take['sourceId']]['duration']:raise ValueError('Source interval out of bounds')
        if type(take.get('complete')) is not bool or type(take.get('usable')) is not bool:raise ValueError('Explicit take assessment required')
        if take.get('role') not in ('main','prompter','other','unknown'):raise ValueError('Known speaker role required')
        if not(take['complete'] and take['usable'] and take['role']=='main') and not str(take.get('reason','')).strip():raise ValueError('Rejected take reason required')
    for row in plan.get('numericConversions',[]):
        if not isinstance(row,dict) or row.get('takeId') not in takes:raise ValueError('Unknown numeric conversion take')
        words=takes[row['takeId']].get('words',[])
        matches=[w for w in words if isinstance(w,dict) and w.get('id')==row.get('wordId')]
        if len(matches)!=1 or matches[0].get('text')!=row.get('sourceText'):raise ValueError('Numeric conversion must match one source word')
    enumeration_by_take=enumeration_contract(plan,takes);encountered_enumerations=[]
    selected=[];mapped=[];cursor=0.0;report=[];used={}
    for unit_id in units:
        candidates=[t for t in takes.values() if t['unitId']==unit_id]
        good=[t for t in candidates if t['role']=='main' and t['complete'] and t['usable']]
        if not good:raise ValueError('Missing usable main-speaker unit: '+unit_id)
        def chronology(t):return (sources[t['sourceId']]['recordingOrder'],t['in'],t['out'])
        winner=max(good,key=chronology)
        if sum(chronology(t)==chronology(winner) for t in good)>1:raise ValueError('Ambiguous take chronology')
        for old_start,old_end in used.get(winner['sourceId'],[]):
            if winner['in']<old_end and old_start<winner['out']:raise ValueError('Reused/overlapping source speech across units')
        used.setdefault(winner['sourceId'],[]).append((winner['in'],winner['out']))
        words=winner.get('words')
        if not isinstance(words,list) or not words:raise ValueError('Reviewed caption intervals required')
        if winner.get('timingBasis')!='fresh-audio-review':raise ValueError('Fresh source-audio timing review required')
        unique(words,'word')
        previous=winner['in'];out_words=[]
        for w in words:
            if w.get('role')!='main' or not verified(w):raise ValueError('Prompt/unknown/unreviewed speech inside selected take')
            start,end=number(w.get('start')),number(w.get('end'))
            if not winner['in']<=start<end<=winner['out'] or start<previous:raise ValueError('Word crosses trim or overlaps previous word')
            text=exact_text(w.get('text'))
            out_words.append({'id':w['id'],'start':start,'end':end,'text':text});previous=end
        if ' '.join(w['text'] for w in out_words)!=exact_text(units[unit_id][unit_text_field]):
            raise ValueError('Selected audible words differ from exact script' if script_mode=='EXACT_CONTENT' else 'Selected audible words differ from reviewed spoken unit')
        membership=sentence_membership(out_words,winner.get('reviewedSentences'))
        displayed=display_words(out_words,winner['id'],plan,policy,membership)
        displayed,enumerations=enumeration_display(out_words,displayed,enumeration_by_take.get(winner['id'],[]),membership)
        displayed,style_transforms,style_binding=nga_emoji_display(out_words,displayed,plan,membership)
        protected=protected_spans(out_words,winner.get('reviewedProtectedSpans'),winner.get('protectedSpanReview'),displayed,policy,membership,enumerations)
        for e in enumerations:
            if e.get('operation')!='PRESERVE_LONG_LEAD_IN_AND_PREFIX_CONTENT' and any(s['startWord']<e['endWord'] and e['startWord']<s['endWord'] and not(s['startWord']<=e['startWord'] and e['endWord']<=s['endWord']) for s in protected):
                raise ValueError('Protected span partly overlaps an authorized enumeration lead-in; explicit semantic review conflict')
        for cue in captions(out_words,winner.get('phrases'),winner['in'],winner['out'],displayed,policy,membership,protected,enumerations,style_transforms):
            mapped.append({'start':round(cursor+cue['start']-winner['in'],6),'end':round(cursor+cue['end']-winner['in'],6),'text':cue['text'],'rawText':cue['rawText'],'takeId':winner['id'],'wordIds':cue['wordIds'],'sentenceId':cue['sentenceId'],'protectedSpanIds':cue['protectedSpanIds'],'enumerationTransforms':cue['enumerationTransforms'],'styleDisplayTransforms':cue['styleDisplayTransforms']})
            encountered_enumerations.extend(cue['enumerationTransforms'])
        duration=winner['out']-winner['in']
        selected.append({'ref':unit_id,'path':sources[winner['sourceId']]['path'],'start':round(cursor,6),'duration':round(duration,6),'sourceStart':winner['in'],'speed':1,'volume':1})
        report.append({'protectedSpanReview':winner['protectedSpanReview'],'reviewedProtectedSpans':protected,'reviewedEnumerationTransforms':enumerations,'styleDisplayTransforms':style_transforms,'savedStyleSelection':style_binding,'unitId':unit_id,'takeId':winner['id'],'sourceId':winner['sourceId'],'sourceIn':winner['in'],'sourceOut':winner['out'],'editedIn':round(cursor,6),'editedOut':round(cursor+duration,6),'selectedProof':winner['evidenceRef'],'rejected':[{'takeId':t['id'],'reason':t.get('reason','Earlier usable take superseded')} for t in candidates if t['id']!=winner['id']]})
        cursor+=duration
    expected_items={item['id'] for items in enumeration_by_take.values() for item in items}
    if {item['id'] for item in encountered_enumerations}!=expected_items or len(encountered_enumerations)!=len(expected_items):raise ValueError('Enumeration items must refer only to selected takes and map every reviewed lead-in exactly once')
    for listing in plan.get('reviewedEnumerations',[]):
        actual=[item['ordinal'] for item in encountered_enumerations if item['listId']==listing['id']]
        if actual!=list(range(1,len(listing['items'])+1)):raise ValueError('Enumeration list order must match retained native timeline order')
    if policy['gapless']:
        for cue,following in zip(mapped,mapped[1:]):cue['end']=following['start']
    cues=[]
    for i,cue in enumerate(mapped,1):
        if round(cue['end']*1000)<=round(cue['start']*1000):raise ValueError('Caption too short for SRT milliseconds')
        cues.append(f"{i}\n{srt_time(cue['start'])} --> {srt_time(cue['end'])}\n{cue['text']}\n")
    spec={'name':name,**canvas,'tracks':[{'type':'video','name':'Main speech','items':selected}],'operations':[{'op':'captions','path':'captions.srt','trackName':'Captions'}]}
    output=io.StringIO(newline='');fields=['unitId','takeId','sourceId','sourceIn','sourceOut','editedIn','editedOut']
    writer=csv.DictWriter(output,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(report)
    return {'compile-spec.json':json.dumps(spec,ensure_ascii=False,indent=2)+'\n','captions.srt':'\n'.join(cues),'source-to-timeline.csv':output.getvalue(),'selection-report.json':json.dumps({'status':'PREPARED_ONLY','duration':round(cursor,6),'units':report,'scriptMode':script_mode,'scriptModeEvidenceRef':script.get('evidenceRef'),'referenceScriptCoverageClaimed':script_mode=='EXACT_CONTENT','captionMode':'REVIEWED_SHORT_PHRASE','captionPolicy':policy,'captionPolicyOverrideEvidence':plan.get('captionPolicyOverride'),'savedStyleSelection':nga_style_selection(plan),'captionCues':mapped,'visualSingleLine':'PENDING','styleCalibration':'PENDING','limitations':['Reviewer assertions, whole-transcript semantic coverage and supplied durations are not authenticated by this helper; no automatic grammar/audio proof is performed.','Raw exact text coverage is checked before caption display conventions; authorized reviewed enumeration prefixes retain every consumed raw ID reversibly without changing source audio. Actual source audio must still support the assertions.','Exact Mrs Nga real-estate emoji display retains reversible raw IDs and unchanged cue timing; glyph/ZWJ shaping, UTF16 native style ranges and one-line rendering remain pending.','Proper-name spelling and numeric conversions require reviewed task data; the helper cannot verify that evidence.','Gapless cue holds may span a cut; inspect them against the native project clock.','No font-width, rendered-line, native playback, CapCut write or app compatibility proof performed.']},ensure_ascii=False,indent=2)+'\n'}

def broll_source_usage(plan,sources,placements):
    """Check supplied whole-timeline usage; assertions are not native/semantic proof."""
    def tick(v):
        if type(v) is not int or v<0:raise ValueError('Nonnegative integer source-usage tick required')
        return v
    def reviewed(r):return isinstance(r,dict) and verified(r) and r.get('evidenceBasis') in ('USER_REPORTED','AGENT_VERIFIED')
    def merged(rows):
        out=[]
        for a,b in sorted(rows):
            if out and a<=out[-1][1]:out[-1][1]=max(b,out[-1][1])
            else:out.append([a,b])
        return out
    def subtract(windows,used):
        out=[]
        for a,b in merged(windows):
            cursor=a
            for x,y in merged(used):
                if y<=cursor:continue
                if x>=b:break
                if cursor<x:out.append([cursor,min(x,b)])
                cursor=max(cursor,y)
                if cursor>=b:break
            if cursor<b:out.append([cursor,b])
        return out
    review=plan.get('sourceUsageReview');base=plan['baseSnapshot']
    if not reviewed(review) or review.get('scope')!='WHOLE_CURRENT_TIMELINE' or review.get('baseSnapshotSha256')!=base['sha256'] or not isinstance(review.get('existingPlacements'),list):
        raise ValueError('Whole current timeline sourceUsageReview with reviewed completeness, current base hash and existingPlacements required')
    mode=plan.get('sourceReuseMode','NO_SOURCE_REPEAT')
    if mode not in ('NO_SOURCE_REPEAT','REVIEWED_CONDITIONAL_REUSE'):raise ValueError('Known sourceReuseMode required; default is NO_SOURCE_REPEAT')
    if mode!='NO_SOURCE_REPEAT':
        override=plan.get('sourceReuseOverride')
        if not reviewed(override) or override.get('evidenceBasis')!='USER_REPORTED' or override.get('authority')!='explicit-user-request' or override.get('mode')!=mode or override.get('baseSnapshotSha256')!=base['sha256'] or not isinstance(override.get('userQuote'),str) or not override['userQuote'].strip():
            raise ValueError('Conditional source reuse requires exact current-base explicit user override; exhaustion or duration alone is not permission')
    identities={};usable={}
    for s in sources.values():
        original=s.get('derivedFromSourceId')
        if original is not None:
            if not isinstance(original,str) or original not in sources or original==s['id']:raise ValueError('Known derivative lineage must name another supplied verified original source')
            if s['sha256']!=sources[original]['sha256']:raise ValueError('Known different-SHA derivative lineage is HELD: use verified original source/window with native transform; unsupported clock mapping cannot create fresh footage')
        identity=s['sha256'];edge=s['sourceOrigin']=='CAMERA' and s.get('voiceClassification')=='NO_VOICE'
        signature=(s['actualDurationTicks'],s['sourceOrigin'],s.get('voiceClassification','NOT_APPLICABLE'))
        if identity in identities and identities[identity]!=signature:raise ValueError('Same-SHA source aliases need identical actual duration/origin/voice facts')
        identities[identity]=signature;usable[identity]=(5000000,s['actualDurationTicks']-4000000) if edge else (0,s['actualDurationTicks'])
    combined={};conflicts=[]
    def usage(row,existing):
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id'] or row.get('sourceId') not in sources:raise ValueError('Known source and unique source-usage placement ID required')
        a,b=tick(row.get('sourceInTick')),tick(row.get('sourceOutTick'));x,y=tick(row.get('startTick')),tick(row.get('endTick'))
        if not a<b or not 0<=x<y<=base['durationTicks']:raise ValueError('Source-usage inventory requires exact normal-speed positive source/target bounds')
        if b-a!=y-x:
            from dependency_proof import validate_native_phase
            current_native=json.loads(Path(base['path']).read_text(encoding='utf-8-sig'))
            validate_native_phase(plan.get('nativePhaseEvidence'),row['id'],sources[row['sourceId']].get('nativeMaterialId'),a,b,x,y,currentFps=current_native.get('fps'))
        s=sources[row['sourceId']];identity=s['sha256'];lo,hi=usable[identity]
        reasons=[]
        if b-a<3000000:reasons.append('BASELINE_BELOW_THREE_SECOND_MINIMUM')
        if a<lo or b>hi:reasons.append('BASELINE_SOURCE_HANDLE_OR_EDGE_EXCLUSION_CONFLICT')
        return {'placementId':row['id'],'sourceId':s['id'],'sourceIdentitySha256':identity,'sourceInTick':a,'sourceOutTick':b,'startTick':x,'endTick':y,'existingInBase':existing,'planned':not existing,'eligibleSourceReview':row.get('eligibleSourceReview'),'conflictReasons':reasons}
    for row in review['existingPlacements']:
        u=usage(row,True)
        if u['placementId'] in combined:raise ValueError('Duplicate existing source-usage placement ID')
        combined[u['placementId']]=u
    reconciliations=review.get('reconciliations',[]);replaced=set();replacement_for={};planned_ids={p['placementId'] for p in placements}
    if not isinstance(reconciliations,list):raise ValueError('Reviewed placement reconciliations must be a list')
    for r in reconciliations:
        old_ids=r.get('existingPlacementIds') if isinstance(r,dict) else None;new_ids=r.get('plannedPlacementIds') if isinstance(r,dict) else None
        if not reviewed(r) or not isinstance(r.get('reason'),str) or not r['reason'].strip() or not isinstance(old_ids,list) or not old_ids or not isinstance(new_ids,list) or not new_ids or any(not isinstance(i,str) for i in old_ids+new_ids):raise ValueError('Explicit reviewed base-bound placement reconciliation with nonempty old/planned IDs and reason required')
        if len(set(old_ids))!=len(old_ids) or len(set(new_ids))!=len(new_ids) or not set(old_ids)<=set(combined) or not set(new_ids)<=planned_ids or replaced.intersection(old_ids) or set(replacement_for).intersection(new_ids):raise ValueError('Reconciliation IDs must be known, unique and disjoint across groups')
        replaced.update(old_ids)
        for key in new_ids:replacement_for[key]=list(old_ids)
    for key in replaced:del combined[key]
    for p in placements:
        raw=dict(p,id=p['placementId']);u=usage(raw,False);u['eligibleSourceReview']=plan['placements'][next(i for i,r in enumerate(plan['placements']) if r['id']==p['placementId'])].get('eligibleSourceReview')
        u['reconciledExistingPlacementIds']=replacement_for.get(u['placementId'],[])
        old=combined.get(u['placementId'])
        if old:
            keys=('sourceIdentitySha256','sourceInTick','sourceOutTick','startTick','endTick')
            if any(old[k]!=u[k] for k in keys):raise ValueError('Existing placement ID/ranges changed: obtain a fresh reviewed base; no silent replacement')
            u['existingInBase']=True
        combined[u['placementId']]=u
    ledger=sorted(combined.values(),key=lambda u:(u['startTick'],u['endTick'],u['placementId']))
    if any(a['endTick']>b['startTick'] for a,b in zip(ledger,ledger[1:])):raise ValueError('Combined whole-timeline B-roll usage overlaps; unchanged clips cannot be omitted')
    prior=[];per_placement={}
    for u in ledger:
        identity=u['sourceIdentitySha256'];same=[p for p in prior if p['sourceIdentitySha256']==identity]
        overlaps=[p for p in same if p['sourceInTick']<u['sourceOutTick'] and u['sourceInTick']<p['sourceOutTick']]
        if same and mode=='NO_SOURCE_REPEAT':u['conflictReasons'].append('SOURCE_IDENTITY_ALREADY_USED_NO_REPEAT')
        u.update(sourceOverlapReuse=bool(overlaps),overlappingPriorPlacementIds=[p['placementId'] for p in overlaps],cooldownTicks=None,latestOverlappingPriorEndTick=None,eligibleUnusedWindows=[],exhaustionMechanicallySupported=False)
        if overlaps:
            latest=max(p['endTick'] for p in overlaps);u.update(cooldownTicks=u['startTick']-latest,latestOverlappingPriorEndTick=latest)
            if u['cooldownTicks']<180000000:u['conflictReasons'].append('SOURCE_REUSE_COOLDOWN_BELOW_180_SECONDS')
        e=u.pop('eligibleSourceReview');needs_review=u['planned'] or bool(same)
        if needs_review:
            if not reviewed(e) or e.get('scope')!='ALL_SUPPLIED_SOURCES' or e.get('exhaustive') is not True or e.get('baseSnapshotSha256')!=base['sha256'] or not isinstance(e.get('sources'),list):
                u['conflictReasons'].append('EXHAUSTIVE_ELIGIBLE_SOURCE_WINDOW_REVIEW_REQUIRED')
            else:
                rows={};eligible={};unknown=False;signatures={}
                for r in e['sources']:
                    if not isinstance(r,dict) or r.get('sourceId') not in sources or r['sourceId'] in rows:raise ValueError('Eligible-source review needs each known supplied source exactly once')
                    rows[r['sourceId']]=r;status=r.get('status');windows=r.get('windows');sid=sources[r['sourceId']]['sha256'];lo,hi=usable[sid]
                    if status not in ('ELIGIBLE','IRRELEVANT','UNAVAILABLE','UNKNOWN') or not isinstance(windows,list):raise ValueError('Known eligible-source status and structured windows required')
                    if not isinstance(r.get('evidenceRef'),str) or not r['evidenceRef'].strip() or (status!='ELIGIBLE' and (windows or not isinstance(r.get('reason'),str) or not r['reason'].strip())):
                        u['conflictReasons'].append('ELIGIBILITY_OR_EXCLUSION_EVIDENCE_REQUIRED')
                    ranges=[]
                    for w in windows:
                        if not isinstance(w,dict):raise ValueError('Eligible source window object required')
                        a,b=tick(w.get('sourceInTick')),tick(w.get('sourceOutTick'))
                        if not lo<=a<b<=hi:raise ValueError('Eligible source windows must obey actual source bounds and conditional five/four-second exclusions')
                        ranges.append([a,b])
                    if status=='ELIGIBLE' and not ranges:u['conflictReasons'].append('ELIGIBLE_SOURCE_REQUIRES_REVIEWED_WINDOWS')
                    canonical=merged(ranges);sig=(status,tuple(map(tuple,canonical)))
                    if sid in signatures and signatures[sid]!=sig:u['conflictReasons'].append('SAME_SHA_ALIAS_ELIGIBILITY_CONFLICT')
                    signatures[sid]=sig
                    if status=='UNKNOWN':unknown=True
                    if status=='ELIGIBLE':eligible[sid]=canonical
                if set(rows)!=set(sources):u['conflictReasons'].append('EXHAUSTIVE_REVIEW_MUST_COVER_EVERY_SUPPLIED_SOURCE')
                if unknown:u['conflictReasons'].append('UNKNOWN_SOURCE_ELIGIBILITY_HELD')
                selected=eligible.get(identity,[])
                if not any(a<=u['sourceInTick'] and u['sourceOutTick']<=b for a,b in selected):u['conflictReasons'].append('SELECTED_EXCERPT_NOT_IN_REVIEWED_ELIGIBLE_WINDOW')
                available=[];fresh=[]
                for sid,windows in sorted(eligible.items()):
                    used=[[p['sourceInTick'],p['sourceOutTick']] for p in prior if p['sourceIdentitySha256']==sid]
                    unused=[w for w in subtract(windows,used) if w[1]-w[0]>=3000000]
                    if unused:
                        available.append({'sourceIdentitySha256':sid,'windows':unused,'whollyFreshSource':not used})
                        if not used:fresh.append(sid)
                u['eligibleUnusedWindows']=available;u['eligibilityEvidenceRef']=e['evidenceRef'];u['eligibilityEvidenceBasis']=e['evidenceBasis']
                if overlaps and available:u['conflictReasons'].append('UNUSED_ELIGIBLE_THREE_SECOND_WINDOW_AVAILABLE')
                elif not overlaps and same and fresh:u['conflictReasons'].append('WHOLLY_FRESH_ELIGIBLE_SOURCE_PREFERRED')
                if overlaps and not available and not unknown and set(rows)==set(sources) and not u['conflictReasons']:u['exhaustionMechanicallySupported']=True
        u['conflictReasons']=list(dict.fromkeys(u['conflictReasons']))
        u['influencedByNewPriorPlacement']=any(p['planned'] and not p['existingInBase'] for p in same)
        u['status']='HELD_REVIEW_REQUIRED' if u['conflictReasons'] else 'PREPARED_ONLY' if u['planned'] else 'BASELINE_RECORDED_NOT_RETRO_CERTIFIED'
        if u['conflictReasons']:conflicts.append({'placementId':u['placementId'],'existingInBase':u['existingInBase'],'planned':u['planned'],'reasons':u['conflictReasons']})
        if u['planned']:per_placement[u['placementId']]=u
        prior.append(u)
    # An additive proposal cannot emit a new earlier use that leaves a later
    # unchanged occurrence held. Keep the contributing new use held as well.
    for held in ledger:
        if held['planned'] or not held['conflictReasons']:continue
        for u in ledger:
            if not u['planned'] or u['existingInBase'] or u['endTick']>held['startTick'] or u['sourceIdentitySha256']!=held['sourceIdentitySha256']:continue
            u.setdefault('heldLaterExistingPlacementIds',[]).append(held['placementId'])
            reason='NEW_USAGE_CONTRIBUTES_TO_HELD_LATER_EXISTING_PLACEMENT'
            if reason not in u['conflictReasons']:u['conflictReasons'].append(reason)
            u['status']='HELD_REVIEW_REQUIRED'
    conflicts=[{'placementId':u['placementId'],'existingInBase':u['existingInBase'],'planned':u['planned'],'reasons':u['conflictReasons']} for u in ledger if u['conflictReasons']]
    policy={'mode':mode,'defaultMode':'NO_SOURCE_REPEAT','repeatDefinition':'ANY_SECOND_PLACEMENT_OF_ORIGINAL_SOURCE_IDENTITY_EVEN_DISJOINT_WINDOWS','conditionalModeRequires':'EXPLICIT_CURRENT_BASE_USER_OVERRIDE','sameSourceIdentity':'VERIFIED_ACTUAL_FILE_SHA256_ALIASES_GROUPED','reuseDefinition':'POSITIVE_HALF_OPEN_SOURCE_INTERVAL_OVERLAP','cooldownTicks':180000000,'cooldownClock':'NEW_TARGET_START_MINUS_MAX_PRIOR_OVERLAPPING_TARGET_END','exhaustion':'REVIEWED_EXHAUSTIVE_ELIGIBLE_WINDOWS_MINUS_ALL_PRIOR_USED_SOURCE_INTERVALS','minimumUnusedContiguousWindowTicks':3000000,'preference':(['WHOLLY_FRESH_SUITABLE_SOURCE','HOLD_MISSING_SUITABLE_FRESH_MATERIAL'] if mode=='NO_SOURCE_REPEAT' else ['WHOLLY_FRESH_SUITABLE_SOURCE','UNUSED_WINDOW_OF_SEEN_SOURCE','COOLDOWN_AND_EXHAUSTION_REVIEWED_OVERLAP_REUSE']),'cooldownAndExhaustionPermissionAppliesOnlyTo':'REVIEWED_CONDITIONAL_REUSE','futureReservationsExcludeMaterial':False,'suppliedInventoryCompletenessAuthenticated':False,'nativeSemanticAcceptance':'PENDING'}
    return policy,ledger,conflicts,per_placement


def prepare_broll(plan):
    """Prepare silent caption-anchored overlays; never mutate or authenticate the native base."""
    if not isinstance(plan,dict) or plan.get('schemaVersion')!='capcut-broll-plan/v1':raise ValueError('Reviewed B-roll v1 plan required')
    def tick(value):
        if type(value) is not int or value<0:raise ValueError('Nonnegative integer native microsecond tick required')
        return value
    def nonempty(value):return isinstance(value,str) and bool(value.strip())
    if plan.get('tickRate')!=1000000:raise ValueError('Native microsecond timebase required')
    base=plan.get('baseSnapshot')
    if not isinstance(base,dict):raise ValueError('Frozen base snapshot required')
    path=Path(base.get('path',''))
    if not path.is_absolute() or not path.is_file() or path.is_symlink() or hash_file(path)!=base.get('sha256'):raise ValueError('Frozen base identity mismatch')
    for parent in path.parents:
        if parent.is_symlink() or (hasattr(parent,'is_junction') and parent.is_junction()):raise ValueError('Linked base snapshot')
    duration=tick(base.get('durationTicks'));checkpoint=plan.get('contentCaptionCheckpoint')
    provisional=plan.get('mode')=='REVIEW_DRAFT'
    if provisional:
        from dependency_proof import read_ref
        authority=read_ref(plan.get('reviewDraftAuthority'))
        owned=authority.get('claim')=='review-draft-native-update-owned'
        if authority.get('evidenceClass')!='REAL_OBSERVATION' or authority.get('authority')!='explicit-user-request' or (not owned and authority.get('claim')!='review-draft-native-apply') or authority.get('mode')!='REVIEW_DRAFT' or not authority.get('userQuote'):
            raise ValueError('Provisional B-roll requires exact explicit review-draft authority')
        if owned:
            # This preparer grants no write permission. The existing-owned route
            # must independently bind the original decision and current nine-file
            # baseline; accepting the wrapper claim alone would widen CREATE.
            from native_revision import OPERATION,load_baseline
            decision=read_ref(authority.get('originalDecision'))
            if (decision.get('schema')!='capcut-review-draft-decision/v1'
                or decision.get('evidenceClass')!='REAL_OBSERVATION'
                or decision.get('authority')!='explicit-user-request'
                or decision.get('mode')!='REVIEW_DRAFT'
                or decision.get('operation')!=OPERATION
                or authority.get('operation')!=OPERATION
                or decision.get('userQuote')!=authority['userQuote']
                or not nonempty(authority.get('taskId'))
                or decision.get('taskId')!=authority['taskId']):
                raise ValueError('Provisional B-roll owned original decision binding required')
            baseline=load_baseline(decision.get('revisionBaseline'),current=True)
            if baseline.get('evidenceClass')!='REAL_OBSERVATION':
                raise ValueError('Provisional B-roll owned observed baseline required')
            expected={'destinationPath':baseline['destinationPath'],'name':baseline['name'],
                'projectId':baseline['projectId'],'timelineId':baseline['timelineId'],
                'rootIndexSHA256':baseline['rootIndexSHA256'],'expectedFiles':baseline['expectedFiles']}
            if (any(authority.get(k)!=v for k,v in expected.items())
                or any(decision.get(k)!=baseline[k] for k in ('destinationPath','projectId','timelineId'))
                or decision.get('projectName')!=baseline['name']):
                raise ValueError('Provisional B-roll owned exact target/index/nine-file binding required')
            current_base=json.loads(path.read_text(encoding='utf-8-sig'))
            if current_base.get('id')!=baseline['timelineId'] or current_base.get('name')!=baseline['name']:
                raise ValueError('Provisional B-roll owned base project identity mismatch')
    allowed_checkpoint='PROVISIONAL_PREPARED' if provisional else 'PASS'
    allowed_basis=('STRUCTURAL_PREPARATION',) if provisional else ('USER_REPORTED','AGENT_VERIFIED')
    if checkpoint!=allowed_checkpoint or not nonempty(plan.get('baseCheckpointEvidenceRef')) or plan.get('baseCheckpointEvidenceBasis') not in allowed_basis:
        raise ValueError('B-roll requires passed base checkpoint with explicit evidence and truthful basis')
    captions=unique(plan.get('captionCues'),'base caption');previous=0;order={};caption_rows=[]
    for index,cue in enumerate(captions.values()):
        start,end=tick(cue.get('startTick')),tick(cue.get('endTick'))
        if not previous<=start<end<=duration:raise ValueError('Base caption bounds/order invalid')
        order[cue['id']]=index;caption_rows.append(cue);previous=end
    cuts=plan.get('existingArollCuts')
    if not isinstance(cuts,list) or not cuts or any(type(t) is not int or not 0<=t<=duration for t in cuts) or cuts!=sorted(set(cuts)):raise ValueError('Existing A-roll cut inventory required without creating new cuts')
    cadence=plan.get('cadenceReview')
    if not isinstance(cadence,dict) or not verified(cadence) or not nonempty(cadence.get('reason')):raise ValueError('Meaning-led whole-plan cadence review required')
    coverage_mode=plan.get('coverageMode','SPARSE')
    if coverage_mode not in ('SPARSE','FULL_TIMELINE'):raise ValueError('Known B-roll coverageMode SPARSE or FULL_TIMELINE required')
    coverage_review=plan.get('coverageReview')
    if coverage_mode=='FULL_TIMELINE':
        if plan.get('sourcePresentationRole')!='VOICEOVER_READING' or not isinstance(coverage_review,dict) or not verified(coverage_review) or coverage_review.get('evidenceBasis') not in ('USER_REPORTED','AGENT_VERIFIED'):raise ValueError('Full timeline coverage needs reviewed voiceover-reading role and explicit evidence')
        if coverage_review.get('baseSnapshotSha256')!=base['sha256'] or type(coverage_review.get('durationTicks')) is not int or coverage_review['durationTicks']!=duration or coverage_review.get('firstCaptionId')!=caption_rows[0]['id'] or coverage_review.get('lastCaptionId')!=caption_rows[-1]['id']:raise ValueError('Full coverage review must bind exact current base hash/duration/outer caption IDs')
    sources=unique(plan.get('sources'),'B-roll source')
    for source in sources.values():
        source_path=Path(source.get('path',''))
        if not source_path.is_absolute() or not source_path.is_file() or source_path.is_symlink() or source_path.suffix.lower() not in ('.mp4','.mov','.mkv','.m4v') or hash_file(source_path)!=source.get('sha256'):raise ValueError('Existing permitted B-roll source identity required')
        for parent in source_path.parents:
            if parent.is_symlink() or (hasattr(parent,'is_junction') and parent.is_junction()):raise ValueError('Linked B-roll source')
        if tick(source.get('actualDurationTicks'))<=0 or not nonempty(source.get('actualDurationEvidenceRef')) or source.get('permitted') is not True or not nonempty(source.get('rightsEvidenceRef')):raise ValueError('B-roll actual source duration and permission evidence required')
        classification=source.get('classificationReview')
        if source.get('sourceOrigin') not in ('CAMERA','AI') or not isinstance(classification,dict) or not verified(classification) or classification.get('evidenceBasis') not in ('USER_REPORTED','AGENT_VERIFIED'):
            raise ValueError('GATE0_SOURCE_CLASSIFICATION_REQUIRED: ask about unresolved source origin with evidence; never infer from appearance or filenames')
        if source['sourceOrigin']=='CAMERA' and source.get('voiceClassification') not in ('HAS_VOICE','NO_VOICE'):
            raise ValueError('GATE0_SOURCE_CLASSIFICATION_REQUIRED: ask about camera-source voice with evidence; never infer from audio streams, muting or ASR silence')
        if source['sourceOrigin']=='AI' and source.get('voiceClassification','NOT_APPLICABLE') not in ('HAS_VOICE','NO_VOICE','UNKNOWN','NOT_APPLICABLE'):
            raise ValueError('AI voice field must record known, UNKNOWN or NOT_APPLICABLE; it is irrelevant to the camera edge rule and requires no voice interview')
        if source['sourceOrigin']=='CAMERA' and source['voiceClassification']=='NO_VOICE' and source['actualDurationTicks']<12000000:
            raise ValueError('Camera no-voice source needs at least twelve seconds for five-second head/four-second tail exclusions and a three-second excerpt')
    placements=unique(plan.get('placements'),'B-roll placement');items=[];reports=[];previous=0
    for placement_index,placement in enumerate(placements.values()):
        source=sources.get(placement.get('sourceId'));first=placement.get('startCaptionId');last=placement.get('lastCaptionId')
        if source is None or first not in captions or last not in captions or order[first]>order[last]:raise ValueError('Known ordered caption anchors and source required')
        start,end=tick(placement.get('startTick')),tick(placement.get('endTick'));length=end-start
        start_exception=coverage_mode=='FULL_TIMELINE' and placement_index==0 and start==0 and first==caption_rows[0]['id'] and start!=captions[first]['startTick']
        end_exception=coverage_mode=='FULL_TIMELINE' and placement_index==len(placements)-1 and end==duration and last==caption_rows[-1]['id'] and end!=captions[last]['endTick']
        if (start!=captions[first]['startTick'] and not start_exception) or (end!=captions[last]['endTick'] and not end_exception):raise ValueError('B-roll must start exactly at caption onset and end at last caption end, except bound full-timeline outer edges')
        if not 0<=start<end<=duration:raise ValueError('B-roll placement exceeds bound native timeline')
        if coverage_mode=='FULL_TIMELINE' and start!=previous:raise ValueError('Full timeline coverage must be contiguous from zero without gaps')
        if start<previous or length<3000000:raise ValueError('Nonoverlapping B-roll with hard minimum three seconds required')
        review=placement.get('meaningReview')
        if not isinstance(review,dict) or not verified(review) or any(not nonempty(review.get(k)) for k in ('relevance','addedInformation','startSelectionReason')):raise ValueError('Reviewed meaningful relevance, added information and start selection reason required')
        if placement.get('paddedToTenSeconds') is not False:raise ValueError('Do not force-fill ten seconds')
        if length>10000000 and not nonempty(review.get('overTenSecondsReason')):raise ValueError('Over ten seconds needs an explicit reviewed meaning reason')
        if placement.get('muteSourceAudio') is not True or placement.get('preserveMainVideo') is not True:raise ValueError('Silent separate B-roll must preserve main video and speech')
        source_in=tick(placement.get('sourceInTick'))
        source_out=tick(placement['sourceOutTick']) if 'sourceOutTick' in placement else source_in+length
        if source_out-source_in!=length:
            from dependency_proof import validate_native_phase
            current_native=json.loads(path.read_text(encoding='utf-8-sig'))
            validate_native_phase(plan.get('nativePhaseEvidence'),placement['id'],source.get('nativeMaterialId'),source_in,source_out,start,end,currentFps=current_native.get('fps'))
        if source_out>source['actualDurationTicks']:raise ValueError('B-roll excerpt exceeds actual source handles')
        edge_exclusion=source['sourceOrigin']=='CAMERA' and source.get('voiceClassification')=='NO_VOICE'
        if edge_exclusion and (source_in<5000000 or source_out>source['actualDurationTicks']-4000000):raise ValueError('Camera no-voice excerpt must exclude first five and last four source seconds')
        nearest=min(cuts,key=lambda cut:(abs(cut-start),cut))
        item={'ref':placement['id'],'path':source['path'],'sourceStartTicks':source_in,'startTicks':start,'durationTicks':length,'speed':1,'volume':0,'separatelyEditable':True}
        if source_out-source_in!=length:item['sourceDurationTicks']=source_out-source_in
        items.append(item)
        reports.append({'placementId':placement['id'],'sourceId':source['id'],'sourceInTick':source_in,'sourceOutTick':source_out,'actualSourceDurationTicks':source['actualDurationTicks'],'actualDurationEvidenceRef':source['actualDurationEvidenceRef'],'sourceOrigin':source['sourceOrigin'],'voiceClassification':source.get('voiceClassification','NOT_APPLICABLE'),'classificationReview':source['classificationReview'],'sourceEdgeExclusionApplied':edge_exclusion,'sourceUsableWindowTicks':[5000000,source['actualDurationTicks']-4000000] if edge_exclusion else [0,source['actualDurationTicks']],'startTick':start,'endTick':end,'startCaptionId':first,'lastCaptionId':last,'nearestExistingArollCutTick':nearest,'cutDistanceTicks':abs(nearest-start),'cutPreference':'Selection only; exact caption onset except bound full-timeline first edge; no main split','timelineStartEdgeExceptionApplied':start_exception,'timelineEndEdgeExceptionApplied':end_exception,'meaningReview':review})
        previous=end
    if coverage_mode=='FULL_TIMELINE' and previous!=duration:raise ValueError('Full timeline coverage must reach exact bound timeline end')
    policy,usage_ledger,usage_conflicts,placement_usage=broll_source_usage(plan,sources,reports)
    for r in reports:r['sourceUsage']=placement_usage[r['placementId']]
    items=[item for item in items if placement_usage[item['ref']]['status']!='HELD_REVIEW_REQUIRED']
    status='PARTIAL_PREPARED_REVIEW_REQUIRED' if usage_conflicts else 'PREPARED_ONLY'
    spec={'status':status,'applyEligible':False,'coverageMode':coverage_mode,'tickRate':1000000,'baseSnapshot':base,'preserveBase':True,'preserveUnreconciledExistingBroll':True,'reviewedProposedPlacementReconciliations':plan['sourceUsageReview'].get('reconciliations',[]),'nativeReplacementOperations':[],'track':{'type':'video','name':'B-roll','items':items},'mainVideoOperations':[],'captionOperations':[],'mainAudioOperations':[]}
    report={'status':'PREPARED_ONLY','coverageMode':coverage_mode,'coverageReview':coverage_review,'sourcePresentationRole':plan.get('sourcePresentationRole'),'fullTimelineCoveragePrepared':coverage_mode=='FULL_TIMELINE','baseCheckpoint':checkpoint,'baseCheckpointEvidenceRef':plan['baseCheckpointEvidenceRef'],'baseCheckpointEvidenceBasis':plan['baseCheckpointEvidenceBasis'],'baseCheckpointNotCertifiedByHelper':True,'placements':reports,'cadenceSoftTargetSeconds':[5,10],'cadenceReview':cadence,'observedStartGapsTicks':[b['startTick']-a['startTick'] for a,b in zip(reports,reports[1:])],'internalCaptionBoundaries':'UNCONSTRAINED','nativeAcceptance':'PENDING','limitations':['Supplied actual source duration, origin/voice classification, permission, meaning and checkpoint assertions are not authenticated.','USER_REPORTED evidence is not the helper or agent personally hearing/playing or proving source origin.','Unknown origin or camera voice requires the Gate0 interview; a reviewed AI origin is already exempt even when its voice is UNKNOWN/NOT_APPLICABLE. Muting, an audio stream, ASR silence or visual appearance never supplies classification.','Camera no-voice exclusions apply on each excerpt source clock, not the main timeline or AI/voiced-camera sources.','No automatic cadence quota, ten-second fill, A-roll split or caption/speech change.','Native playback, crop/rotation, caption fit, editable tracks and persistence remain required.']}
    report.update(status=status,sourceReusePolicy=policy,sourceUsageReview=plan['sourceUsageReview'],sourceUsageLedger=usage_ledger,sourceUsageConflicts=usage_conflicts,providedWholeTimelineUsageMechanicallyConflictFree=not usage_conflicts,wholeTimelineReuseNativeAcceptance='PENDING',fullTimelineCoveragePrepared=coverage_mode=='FULL_TIMELINE' and not usage_conflicts)
    report['limitations'].append('Whole-current-timeline completeness, exhaustive eligible windows, relevance and exclusions are supplied review assertions, not authenticated native/semantic proof. Default NO_SOURCE_REPEAT holds every second same-identity placement including disjoint windows and touching windows. Only an explicit current-base user override selects REVIEWED_CONDITIONAL_REUSE; its positive half-open overlap still needs180seconds from maximum prior END to new START and evidenced exhaustion. Prior used intervals are union-subtracted; any remaining eligible contiguous3seconds blocks reuse even if reserved for a future slot. Existing violations stay HELD and are not retroactively certified; affected planned overlays are omitted, never silently replaced by A-roll or generated imagery. Recut/reorder/source changes invalidate the bound review. Native final inventory and meaning remain pending.')
    return {'broll-spec.json':json.dumps(spec,ensure_ascii=False,indent=2)+'\n','broll-report.json':json.dumps(report,ensure_ascii=False,indent=2)+'\n'}

def prepare_pacing(plan):
    """Prepare reviewed frame-based quiet-only CND maps; never native/hearing proof."""
    from fractions import Fraction
    if not isinstance(plan,dict) or plan.get('schemaVersion')!='capcut-pacing-plan/v1':raise ValueError('Reviewed pacing plan v1 required')
    if plan.get('workScope')!='CONTENT_EDIT' or plan.get('outputMode')!='EDIT_TIMELINE':raise ValueError('Pacing is CND content editing only; subtitle/SRT/edited-audio preservation must not alter pace')
    def tick(v):
        if type(v) is not int or v<0:raise ValueError('Nonnegative integer frame or microsecond tick required')
        return v
    def nonempty(v):return isinstance(v,str) and bool(v.strip())
    auth=plan.get('authorization')
    if not isinstance(auth,dict) or auth.get('authority')!='explicit-user-request' or not nonempty(auth.get('evidenceRef')):raise ValueError('Explicit pacing authority evidence required')
    style_binding=nga_style_selection(plan)
    if style_binding['status'] in ('NEEDS_RECIPIENT','NEEDS_DOMAIN'):raise ValueError('GATE0_STYLE_BINDING_REQUIRED: '+style_binding['question'])
    default_scope='ALL_PAUSES'
    scope=plan.get('pacingScope',default_scope)
    if scope not in ('ALL_PAUSES','INTER_SENTENCE_ONLY','SENTENCE_AND_INTRA'):raise ValueError('Known pacingScope ALL_PAUSES, INTER_SENTENCE_ONLY or SENTENCE_AND_INTRA required')
    override=plan.get('pacingScopeOverride')
    if override is not None and (not isinstance(override,dict) or override.get('pacingScope')!=scope or override.get('authority')!='explicit-user-request' or not nonempty(override.get('evidenceRef'))):raise ValueError('Scoped explicit pacingScopeOverride evidence must match selected pacingScope')
    if scope!=default_scope and override is None:raise ValueError('Legacy nondefault pacingScope needs scoped explicit pacingScopeOverride evidence')
    criterion=plan.get('pauseCriterion',{'minimumQuietDurationTicks':200000,'comparison':'STRICTLY_GREATER','auditScopes':['HEAD','INTERNAL','TAIL']})
    if not isinstance(criterion,dict) or type(criterion.get('minimumQuietDurationTicks')) is not int or criterion['minimumQuietDurationTicks']!=200000 or criterion.get('comparison')!='STRICTLY_GREATER' or criterion.get('auditScopes')!=['HEAD','INTERNAL','TAIL']:
        raise ValueError('Exact pauseCriterion requires strict greater-than200000 microseconds and HEAD/INTERNAL/TAIL audits; it is not a retained-gap target')
    if 'reviewedFinalCaptionOnsets' in plan:raise ValueError('Reviewed final caption onsets must remain frozen in the separate final edited-audio anchor stage; pacing cannot overwrite them')
    native=plan.get('nativeClock')
    if not isinstance(native,dict) or native.get('tickRate')!=1000000 or native.get('clockBasis')!='ACTUAL_TIMELINE' or not verified(native):raise ValueError('Reviewed actual timeline FPS required, never source FPS')
    num,den=native.get('fpsNumerator'),native.get('fpsDenominator')
    if num is not None or den is not None:
        if type(num) is not int or type(den) is not int or num<=0 or den<=0:raise ValueError('Positive exact timeline FPS ratio required')
        rate=Fraction(num,den)
    else:
        fps=number(native.get('fps'))
        if fps<=0:raise ValueError('Positive actual timeline FPS required')
        rate=Fraction(str(fps))
    def frame_us(frame):return tick(frame)*1000000*rate.denominator//rate.numerator
    def duration(a,b):
        value=frame_us(b)-frame_us(a)
        if b<=a or value<=0:raise ValueError('Frame conversion cannot create a zero-length interval')
        return value
    def floor_frame(us):
        # Inverse of the floor-valued native clock, including33333us at30fps.
        return ((tick(us)+1)*rate.numerator+1000000*rate.denominator-1)//(1000000*rate.denominator)-1
    def ceil_frame(us):
        f=floor_frame(us)
        return f if frame_us(f)==us else f+1
    sources=unique(plan.get('sources'),'pacing source')
    for s in sources.values():
        p=Path(s.get('path',''))
        if not p.is_absolute() or not p.is_file() or p.is_symlink() or hash_file(p)!=s.get('sha256'):raise ValueError('Pacing source identity mismatch')
        for parent in p.parents:
            if parent.is_symlink() or (hasattr(parent,'is_junction') and parent.is_junction()):raise ValueError('Linked pacing source')
        if tick(s.get('actualDurationTicks'))<=0 or not nonempty(s.get('durationEvidenceRef')):raise ValueError('Actual source duration evidence required')
    known=plan.get('knownSpeechOrPrompterIntervals')
    if not isinstance(known,list):raise ValueError('Explicit known source speech/prompter inventory required')
    for k in known:
        if not isinstance(k,dict) or k.get('sourceId') not in sources or not verified(k) or k.get('role') not in ('main','prompter','other') or not 0<=tick(k.get('startTick'))<tick(k.get('endTick'))<=sources[k['sourceId']]['actualDurationTicks']:raise ValueError('Malformed known speech/prompter interval')
    base=[];cursor=0
    for c in unique(plan.get('clips'),'pacing baseline clip').values():
        a,b=tick(c.get('startFrame')),tick(c.get('endFrame'));src=sources.get(c.get('sourceId'));source_a,source_b=tick(c.get('sourceInTick')),tick(c.get('sourceOutTick'))
        if src is None or a!=cursor or not 0<=source_a<source_b<=src['actualDurationTicks'] or c.get('speed')!=1 or type(c.get('speed')) is bool:raise ValueError('Contiguous bounded normal-speed native baseline map required; no implicit speed change')
        if source_b-source_a!=duration(a,b):raise ValueError('Baseline source/native frame durations need reviewed exact mapping, not guessed rescaling')
        volume=number(c.get('volume'))
        if volume<0:raise ValueError('Preserved baseline volume required')
        base.append(dict(c,oldStartTick=frame_us(a),oldEndTick=frame_us(b)));cursor=b
    if not base:raise ValueError('Nonempty reviewed baseline required')
    clips={c['id']:c for c in base};wordrows=[];previous=0
    for w in unique(plan.get('words'),'pacing word').values():
        if not verified(w) or w.get('role')!='main':raise ValueError('Reviewed ordered main-word native boundaries required')
        parts=w.get('sourcePieces')
        if not isinstance(parts,list) or not parts:raise ValueError('Every raw word needs all original source pieces')
        pieces=[]
        for part in parts:
            if not isinstance(part,dict):raise ValueError('Source word piece must be an object')
            c=clips.get(part.get('clipId'));x,y=tick(part.get('sourceStartTick')),tick(part.get('sourceEndTick'))
            if c is None or not c['sourceInTick']<=x<y<=c['sourceOutTick']:raise ValueError('Raw word piece outside baseline source handle')
            pieces.append({'clipId':c['id'],'sourceId':c['sourceId'],'sourceStartTick':x,'sourceEndTick':y,'oldStartTick':c['oldStartTick']+x-c['sourceInTick'],'oldEndTick':c['oldStartTick']+y-c['sourceInTick']})
        start,end=pieces[0]['oldStartTick'],pieces[-1]['oldEndTick']
        if start<previous or any(x['oldEndTick']>y['oldStartTick'] for x,y in zip(pieces,pieces[1:])):raise ValueError('Raw word source/native tick mapping is stale, reordered or overlapping')
        a,b=floor_frame(start),ceil_frame(end)
        if any(k in w and tick(w[k])!=v for k,v in (('startFrame',a),('endFrame',b))):raise ValueError('Optional word frame bounds disagree with exact raw source ticks')
        # Words can share a picture frame; raw positive audio ticks remain authoritative.
        wordrows.append({'id':w['id'],'text':exact_text(w.get('text')),'start':start,'end':end,'startFrame':a,'endFrame':b,'pieces':pieces});previous=end
    if not wordrows:raise ValueError('Nonempty reviewed raw words required')
    membership=sentence_membership(wordrows,plan.get('reviewedSentences'));positions={w['id']:i for i,w in enumerate(wordrows)};coverage=[];displayed=['']*len(wordrows);grouped=[]
    for c in unique(plan.get('captionCues'),'paced caption').values():
        ids=c.get('wordIds')
        if not isinstance(ids,list) or not ids or ids!=[w['id'] for w in wordrows[len(coverage):len(coverage)+len(ids)]] or not verified(c) or any(membership[i]!=c.get('sentenceId') for i in ids):raise ValueError('Caption raw coverage/order/logical sentence must be preserved')
        text=exact_text(c.get('text'));display=c.get('reviewedDisplayByWord')
        if len(text.split())>6 or not isinstance(display,list) or len(display)!=len(ids) or any(not isinstance(t,str) for t in display) or ' '.join(t for t in display if t)!=text:raise ValueError('Exact reviewed caption display and six-word ceiling required')
        for i,t in zip(ids,display):displayed[positions[i]]=t
        coverage.extend(ids);grouped.append(dict(c,text=text))
    if coverage!=[w['id'] for w in wordrows]:raise ValueError('Paced captions omit raw words')
    protected=protected_spans(wordrows,plan.get('reviewedProtectedSpans'),plan.get('protectedSpanReview'),displayed,caption_policy({}),membership);at=0
    for c in grouped:
        end=at+len(c['wordIds'])
        if any(s['startWord']<at<s['endWord'] or s['startWord']<end<s['endWord'] for s in protected):raise ValueError('Pacing cannot split retained old/new protected unit')
        at=end
    rows=plan.get('reviewedPauses')
    if not isinstance(rows,list):raise ValueError('Reviewed quiet-pause inventory required')
    pairs={}
    for r in rows:
        if not isinstance(r,dict):raise ValueError('Pause review must be an object')
        if scope!='ALL_PAUSES' and (not verified(r) or r.get('reviewBasis')!='audio-speech-boundary-review' or r.get('noSpeechOrPrompter') is not True or not nonempty(r.get('joinEvidenceRef'))):raise ValueError('Quiet-only audio/source/join review required; amplitude-only or unknown is insufficient')
        pair=(r.get('previousWordId'),r.get('nextWordId'))
        if pair in pairs:raise ValueError('Duplicate pause pair')
        pairs[pair]=r
    boundary_rows=plan.get('reviewedBoundaryPauses',[])
    if not isinstance(boundary_rows,list):raise ValueError('Boundary pause inventory must be a list')
    boundary_reviews={}
    for r in boundary_rows:
        if scope!='ALL_PAUSES':raise ValueError('HEAD/TAIL removal review belongs only to ALL_PAUSES, never a legacy-scope recut')
        if not isinstance(r,dict) or r.get('kind') not in ('head-quiet','tail-quiet') or 'previousWordId' in r or 'nextWordId' in r:raise ValueError('Boundary quiet requires head-quiet/tail-quiet and nearestWordId, never a fake adjacent-word pair')
        if r['kind'] in boundary_reviews:raise ValueError('Duplicate boundary quiet review')
        boundary_reviews[r['kind']]=r
    shortfall=plan.get('sentenceShortfallPolicy')
    if shortfall is not None and (not isinstance(shortfall,dict) or shortfall.get('action')!='KEEP_REVIEWED_REAL_QUIET_AND_REPORT' or shortfall.get('authority')!='explicit-user-request' or not nonempty(shortfall.get('evidenceRef'))):raise ValueError('Scoped explicit real-quiet shortfall decision evidence required')
    cap_ticks=(5*1000000*rate.denominator+rate.numerator-1)//rate.numerator
    edits=[];used=set();reports=[];conflicts=[];delta_frames=0;retained_origin=0
    def projected_left_end(w):
        c=clips[w['pieces'][-1]['clipId']];first=max(retained_origin,c['startFrame'])
        return frame_us(first+delta_frames)+w['end']-frame_us(first)
    for left,right in zip(wordrows,wordrows[1:]):
        a,b=ceil_frame(left['end']),floor_frame(right['start']);gap=max(0,b-a);sentence=membership[left['id']]!=membership[right['id']];pair=(left['id'],right['id']);r=pairs.get(pair);raw_gap=right['start']-left['end']
        if r is not None:
            used.add(pair)
            if b<a:raise ValueError('No whole-frame quiet interval at this reviewed pair; cannot cut speech to force pacing')
            if tick(r.get('oldStartFrame'))!=a or tick(r.get('oldEndFrame'))!=b or tick(r.get('oldStartTick'))!=frame_us(a) or tick(r.get('oldEndTick'))!=frame_us(b) or r.get('kind')!=('sentence-boundary' if sentence else 'intra-sentence-breath'):raise ValueError('Pause review must bind exact adjacent frames/ticks and logical kind')
        if scope=='ALL_PAUSES':
            row={'previousWordId':left['id'],'nextWordId':right['id'],'sentenceId':membership[left['id']],'kind':'sentence-boundary' if sentence else 'intra-sentence-breath','pauseRegion':'INTERNAL','beforeFrames':gap,'afterFrames':gap,'changed':False,'decision':'NO_SAFE_WHOLE_FRAME_QUIET','rawQuietDurationTicks':raw_gap,'overDetectionThreshold':raw_gap>200000,'thresholdEligibilityBasis':'SUPPLIED_RAW_BOUNDARIES_NOT_AUTHENTICATED_HEARING'}
            if raw_gap<=200000:
                row['decision']='AT_OR_BELOW_200MS_UNCHANGED';reports.append(row);continue
            if gap<=0:
                conflicts.append({'previousWordId':left['id'],'nextWordId':right['id'],'status':'NO_SAFE_WHOLE_FRAME_QUIET','reason':'Qualifying candidate gap has no complete quiet frame; retain baseline until reviewed representation'})
                reports.append(row);continue
            safe=r.get('safeRemoval') if r is not None else None
            reviewed=r is not None and verified(r) and r.get('reviewBasis')=='audio-speech-boundary-review' and r.get('noSpeechOrPrompter') is True and nonempty(r.get('joinEvidenceRef')) and isinstance(safe,dict) and verified(safe) and safe.get('reviewBasis')=='audio-speech-boundary-review'
            if not reviewed:
                conflicts.append({'previousWordId':left['id'],'nextWordId':right['id'],'status':'QUIET_INTERIOR_REVIEW_REQUIRED','reason':'Retain this baseline gap: missing audio-reviewed safe interior/phonetic handles; ASR or amplitude alone is insufficient'})
                row['decision']='AFFECTED_JOIN_HELD_REVIEW_REQUIRED';reports.append(row);continue
            x,y=tick(safe.get('startFrame')),tick(safe.get('endFrame'))
            if not a<=x<y<=b or tick(safe.get('startTick'))!=frame_us(x) or tick(safe.get('endTick'))!=frame_us(y):raise ValueError('Safe removal must be a positive whole-frame interior inside exact raw word gap, with matching native ticks')
            left_handle,right_handle=frame_us(x)-left['end'],right['start']-frame_us(y)
            if left_handle<=0 or right_handle<=0 or tick(safe.get('leftPhoneticHandleTicks'))!=left_handle or tick(safe.get('rightPhoneticHandleTicks'))!=right_handle:raise ValueError('Positive reviewed phonetic handles must exactly bind actual raw speech edges to quiet cut')
            edits.append({'startFrame':x,'endFrame':y,'insert':None,'insertFrames':0,'kind':row['kind'],'safeRemovalReview':safe,'joinEvidenceRef':r['joinEvidenceRef']})
            delta_frames-=y-x;retained_origin=y
            row.update(afterFrames=gap-(y-x),changed=True,decision='REVIEWED_SAFE_QUIET_INTERIOR_REMOVED',evidenceRef=r['evidenceRef'],safeRemoval=safe,retainedLeftPhoneticHandleTicks=left_handle,retainedRightPhoneticHandleTicks=right_handle)
            reports.append(row);continue
        if not sentence and scope=='INTER_SENTENCE_ONLY':
            reports.append({'previousWordId':left['id'],'nextWordId':right['id'],'kind':'intra-sentence','beforeFrames':gap,'afterFrames':gap,'changed':False,'decision':'INTRA_SENTENCE_PRESERVED_BY_SCOPE'});continue
        if not sentence and raw_gap<=cap_ticks:
            reports.append({'previousWordId':left['id'],'nextWordId':right['id'],'kind':'intra-sentence','beforeFrames':gap,'afterFrames':gap,'changed':False,'decision':'SHORT_RAW_GAP_UNCHANGED'});continue
        if r is None:raise ValueError('Affected sentence or long breathing pause needs reviewed source quiet')
        if b<a:raise ValueError('No whole-frame quiet interval; reviewed frame/source conflict, no speech cut')
        new_start=a+delta_frames;left_end=projected_left_end(left);right_residual=right['start']-frame_us(b)
        row={'previousWordId':left['id'],'nextWordId':right['id'],'sentenceId':membership[left['id']],'kind':r['kind'],'beforeFrames':gap,'evidenceRef':r['evidenceRef']}
        if sentence:
            last=left['pieces'][-1];c=clips[last['clipId']];tail=r.get('previousSourceQuietTail');tail_start=last['sourceEndTick']+frame_us(a)-left['end'];requested=duration(new_start,new_start+15)
            if not isinstance(tail,dict) or not verified(tail) or tail.get('sourceId')!=last['sourceId'] or tick(tail.get('startTick'))!=tail_start or not last['sourceEndTick']<=tick(tail.get('availableEndTick'))<=sources[last['sourceId']]['actualDurationTicks']:raise ValueError('Prior original source needs reviewed available15-frame quiet tail or scoped reviewed shortfall; no padding/freeze/speed change')
            available=tail['availableEndTick']-tail_start;after=15;y=tail_start+requested;short=available<requested
            row.update(requestedSentenceFrames=15,availableRealSourceQuietTicks=tail['availableEndTick']-last['sourceEndTick'],shortfall=short)
            if short:
                if shortfall is None:raise ValueError('Source lacks available15-frame tail; explicit reviewed real-quiet shortfall decision required')
                after=0
                while after<14 and duration(new_start,new_start+after+1)<=available+1:after+=1
                y=tail['availableEndTick'];row['shortfallDecisionEvidenceRef']=shortfall['evidenceRef'];row['reviewedShortSourceQuietTicks']=y-last['sourceEndTick']
            expected_ticks=0 if after==0 else duration(new_start,new_start+after)
            actual_gap=frame_us(new_start+after)+right_residual-left_end
            target_low=15*1000000*rate.denominator//rate.numerator;target_high=(15*1000000*rate.denominator+rate.numerator-1)//rate.numerator
            representable=available>=0 and abs(expected_ticks-(y-tail_start))<=1 and (short or target_low<=actual_gap<=target_high)
            if not representable:
                conflict={'previousWordId':left['id'],'nextWordId':right['id'],'sentenceId':membership[left['id']],'status':'NATIVE_REPRESENTATION_REVIEW_REQUIRED','reason':'Cannot retain exact real source quiet and target auditory gap on whole-frame map without changing speech/padding; leave this baseline join unchanged','availableRealSourceQuietTicks':row['availableRealSourceQuietTicks']};conflicts.append(conflict);row.update(afterFrames=gap,changed=False,decision='AFFECTED_JOIN_HELD_REVIEW_REQUIRED');reports.append(row);continue
            row['retainedRealSourceQuietTicks']=y-last['sourceEndTick']
            x=tail_start
            if any(p['sourceId']==last['sourceId'] and p['sourceStartTick']<y and x<p['sourceEndTick'] for w in wordrows for p in w['pieces']) or any(k['sourceId']==last['sourceId'] and k['startTick']<y and x<k['endTick'] for k in known):raise ValueError('Sentence tail intersects retained speech or known prompter')
            insert=None if y==x else {'sourceId':last['sourceId'],'sourceInTick':x,'sourceOutTick':y,'speed':1,'volume':c['volume']};edits.append({'startFrame':a,'endFrame':b,'insert':insert,'insertFrames':after,'kind':'sentence-boundary'});delta_frames+=after-gap;retained_origin=b;row.update(afterFrames=after,changed=gap!=after,decision='KEEP_REVIEWED_REAL_QUIET_REPORT_SHORTFALL' if short else 'REVIEWED15_FRAME_TARGET')
        else:
            after=gap
            while after>0 and frame_us(new_start+after)+right_residual-left_end>cap_ticks:after-=1
            if frame_us(new_start+after)+right_residual-left_end>cap_ticks or after==gap:
                conflicts.append({'previousWordId':left['id'],'nextWordId':right['id'],'status':'NATIVE_REPRESENTATION_REVIEW_REQUIRED','reason':'No safe complete quiet-frame removal meets raw auditory five-frame cap; retain baseline until reviewed mapping'});row.update(afterFrames=gap,changed=False,decision='AFFECTED_JOIN_HELD_REVIEW_REQUIRED');reports.append(row);continue
            edits.append({'startFrame':a+after,'endFrame':b,'insert':None,'insertFrames':0,'kind':'intra-sentence-breath'});delta_frames-=gap-after;retained_origin=b;row.update(afterFrames=after,changed=True,decision='RAW_AUDITORY_GAP_CAPPED_BY_SAFE_QUIET_FRAMES')
        reports.append(row)
    if used!=set(pairs):raise ValueError('Pause inventory contains unknown/nonadjacent pairs')
    boundary_reports=[]
    if scope=='ALL_PAUSES':
        for kind,w,c,raw_start,raw_end in [('head-quiet',wordrows[0],base[0],0,wordrows[0]['start']),('tail-quiet',wordrows[-1],base[-1],wordrows[-1]['end'],frame_us(cursor))]:
            a,b=ceil_frame(raw_start),floor_frame(raw_end);raw_gap=raw_end-raw_start;r=boundary_reviews.get(kind)
            row={'kind':kind,'pauseRegion':'HEAD' if kind=='head-quiet' else 'TAIL','nearestWordId':w['id'],'beforeFrames':max(0,b-a),'afterFrames':max(0,b-a),'rawQuietDurationTicks':raw_gap,'overDetectionThreshold':raw_gap>200000,'changed':False,'thresholdEligibilityBasis':'SUPPLIED_RAW_BOUNDARIES_NOT_AUTHENTICATED_HEARING'}
            if r is not None:
                if r.get('nearestWordId')!=w['id'] or r.get('clipId')!=c['id'] or r.get('sourceId')!=c['sourceId'] or tick(r.get('oldStartFrame'))!=a or tick(r.get('oldEndFrame'))!=b or tick(r.get('oldStartTick'))!=frame_us(a) or tick(r.get('oldEndTick'))!=frame_us(b):raise ValueError('Boundary quiet review must bind actual outer edge, nearest first/last word and exact native frame/ticks')
                source_a=c['sourceInTick']+frame_us(a)-c['oldStartTick'];source_b=c['sourceInTick']+frame_us(b)-c['oldStartTick']
                if tick(r.get('sourceStartTick'))!=source_a or tick(r.get('sourceEndTick'))!=source_b:raise ValueError('Boundary quiet source clock must exactly match the bound baseline translation')
            if raw_gap<=200000:
                row['decision']='AT_OR_BELOW_200MS_UNCHANGED';boundary_reports.append(row);continue
            # A single row never invents a continuous source interval across existing clips.
            near=w['pieces'][0 if kind=='head-quiet' else -1]
            if near['clipId']!=c['id'] or a<c['startFrame'] or b>c['endFrame']:
                conflicts.append({'kind':kind,'nearestWordId':w['id'],'status':'BOUNDARY_MULTI_PIECE_REVIEW_REQUIRED','reason':'Outer candidate quiet crosses baseline source pieces; this single-source row cannot authenticate its full window'})
                row['decision']='AFFECTED_BOUNDARY_HELD_REVIEW_REQUIRED';boundary_reports.append(row);continue
            safe=r.get('safeRemoval') if r is not None else None
            reviewed=r is not None and verified(r) and r.get('reviewBasis')=='audio-speech-boundary-review' and r.get('noSpeechOrPrompter') is True and nonempty(r.get('joinEvidenceRef')) and isinstance(safe,dict) and verified(safe) and safe.get('reviewBasis')=='audio-speech-boundary-review'
            if not reviewed or b<=a:
                conflicts.append({'kind':kind,'nearestWordId':w['id'],'status':'BOUNDARY_QUIET_REVIEW_REQUIRED','reason':'Qualifying outer candidate quiet lacks audio-reviewed safe source interior/phonetic handle or complete frame; keep baseline, ASR/energy alone is insufficient'})
                row['decision']='AFFECTED_BOUNDARY_HELD_REVIEW_REQUIRED';boundary_reports.append(row);continue
            x,y=tick(safe.get('startFrame')),tick(safe.get('endFrame'))
            if not a<=x<y<=b or tick(safe.get('startTick'))!=frame_us(x) or tick(safe.get('endTick'))!=frame_us(y):raise ValueError('Boundary safe removal must stay inside its complete quiet-frame window with exact ticks')
            left_handle,right_handle=frame_us(x)-raw_start,raw_end-frame_us(y)
            if left_handle<0 or right_handle<0 or (kind=='head-quiet' and right_handle<=0) or (kind=='tail-quiet' and left_handle<=0) or tick(safe.get('leftPhoneticHandleTicks'))!=left_handle or tick(safe.get('rightPhoneticHandleTicks'))!=right_handle:raise ValueError('Boundary phonetic handle must be positive against speech; zero is allowed only at the exposed outer edge, with exact margins')
            outer_bound=plan.get('reviewedCaptionOuterBounds',{}).get('firstOnsetFrame' if kind=='head-quiet' else 'lastEndFrame')
            if type(outer_bound) is int and x<outer_bound<y:
                conflicts.append({'kind':kind,'nearestWordId':w['id'],'status':'REVIEWED_CAPTION_OUTER_BOUNDARY_CONFLICT','reason':'Reviewed old outer caption bound lies inside proposed removed quiet; keep boundary until an evidenced final-clock anchor stage resolves it'})
                row['decision']='AFFECTED_BOUNDARY_HELD_REVIEW_REQUIRED';boundary_reports.append(row);continue
            edits.append({'startFrame':x,'endFrame':y,'insert':None,'insertFrames':0,'kind':kind,'safeRemovalReview':safe,'joinEvidenceRef':r['joinEvidenceRef']})
            row.update(afterFrames=(b-a)-(y-x),changed=True,decision='REVIEWED_SAFE_BOUNDARY_QUIET_REMOVED',safeRemoval=safe,evidenceRef=r['evidenceRef'],retainedLeftPhoneticHandleTicks=left_handle,retainedRightPhoneticHandleTicks=right_handle)
            boundary_reports.append(row)
    edits.sort(key=lambda e:(e['startFrame'],e['endFrame']))
    if any(x['endFrame']>y['startFrame'] for x,y in zip(edits,edits[1:])):raise ValueError('Reviewed quiet removals overlap')
    for e in edits:
        for c in base:
            a,b=max(e['startFrame'],c['startFrame']),min(e['endFrame'],c['endFrame'])
            if a>=b:continue
            x=c['sourceInTick']+frame_us(a)-c['oldStartTick'];y=c['sourceInTick']+frame_us(b)-c['oldStartTick']
            if any(k['sourceId']==c['sourceId'] and k['startTick']<y and x<k['endTick'] for k in known):raise ValueError('Quiet removal intersects known source speech/prompter')
    items=[];maps=[];out_frame=0
    def retain(a,b):
        nonlocal out_frame
        for c in base:
            first,last=max(a,c['startFrame']),min(b,c['endFrame'])
            if first>=last:continue
            new_end=out_frame+last-first;source_a=c['sourceInTick']+frame_us(first)-c['oldStartTick'];source_b=c['sourceInTick']+frame_us(last)-c['oldStartTick'];target_ticks=duration(out_frame,new_end)
            items.append({'sourceId':c['sourceId'],'path':sources[c['sourceId']]['path'],'sourceInTick':source_a,'sourceOutTick':source_b,'startFrame':out_frame,'endFrame':new_end,'startTick':frame_us(out_frame),'durationTicks':target_ticks,'sourceTargetPhaseDifferenceTicks':target_ticks-(source_b-source_a),'speed':1,'volume':c['volume']});maps.append({'oldStartFrame':first,'oldEndFrame':last,'newStartFrame':out_frame,'newEndFrame':new_end,'baseClipId':c['id'],'oldStartTick':frame_us(first),'oldEndTick':frame_us(last),'newStartTick':frame_us(out_frame),'newEndTick':frame_us(new_end),'sourceTargetPhaseDifferenceTicks':target_ticks-(source_b-source_a),'kind':'retained-base'});out_frame=new_end
    old_cursor=0
    for e in edits:
        retain(old_cursor,e['startFrame']);e['newStartFrame']=out_frame
        if e['insert']:
            end=out_frame+e['insertFrames'];items.append(dict(e['insert'],path=sources[e['insert']['sourceId']]['path'],startFrame=out_frame,endFrame=end,startTick=frame_us(out_frame),durationTicks=duration(out_frame,end),sourceTargetPhaseDifferenceTicks=duration(out_frame,end)-(e['insert']['sourceOutTick']-e['insert']['sourceInTick'])));out_frame=end
        e['newEndFrame']=out_frame;old_cursor=e['endFrame']
    retain(old_cursor,cursor)
    def remap(frame,is_start=True):
        shift=0
        for e in edits:
            if frame<e['startFrame']:break
            if frame==e['startFrame']:return e['newEndFrame'] if is_start and e['startFrame']==e['endFrame'] else e['newStartFrame']
            if frame<e['endFrame']:raise ValueError('Spoken boundary lies inside removed quiet frames')
            shift+=(e['newEndFrame']-e['newStartFrame'])-(e['endFrame']-e['startFrame'])
        return frame+shift
    remapped=[]
    for w in wordrows:
        for p in w['pieces']:
            if any(frame_us(e['startFrame'])<p['oldEndTick'] and p['oldStartTick']<frame_us(e['endFrame']) for e in edits):raise ValueError('Pacing edit intersects original raw word source piece')
        # Project each original audio piece by translation, never scale or quantize its duration.
        projected=[]
        for p in w['pieces']:
            covered=0
            for m in maps:
                first,last=max(p['oldStartTick'],m['oldStartTick']),min(p['oldEndTick'],m['oldEndTick'])
                if m['baseClipId']!=p['clipId'] or first>=last:continue
                # Every event in one retained original interval uses ONE constant offset.
                x=m['newStartTick']+first-m['oldStartTick'];y=x+last-first
                projected.append(dict(p,sourceStartTick=p['sourceStartTick']+first-p['oldStartTick'],sourceEndTick=p['sourceStartTick']+last-p['oldStartTick'],oldStartTick=first,oldEndTick=last,newStartTick=x,newEndTick=y,sourceTargetPhaseDifferenceTicks=m['sourceTargetPhaseDifferenceTicks'],endRelativeToNativeItemEndTicks=y-m['newEndTick']))
                covered+=last-first
            if covered!=p['oldEndTick']-p['oldStartTick']:raise ValueError('Word piece is not covered exactly once by retained original intervals')
        x,y=projected[0]['newStartTick'],projected[-1]['newEndTick']
        a,b=floor_frame(x),ceil_frame(y)
        remapped.append({'id':w['id'],'text':w['text'],'sentenceId':membership[w['id']],'sourcePieces':w['pieces'],'projectedSourcePieces':projected,'startFrame':a,'endFrame':b,'startTick':x,'endTick':y})
    outer=plan.get('reviewedCaptionOuterBounds')
    if not isinstance(outer,dict) or not verified(outer):raise ValueError('Reviewed original first caption onset and last end required')
    first_frame,last_frame=tick(outer.get('firstOnsetFrame')),tick(outer.get('lastEndFrame'))
    if not first_frame<=wordrows[0]['startFrame'] or not wordrows[-1]['endFrame']<=last_frame<=cursor:raise ValueError('Reviewed outer caption bounds must include retained speech within baseline')
    lookup={w['id']:w for w in remapped};new_cues=[]
    for c in grouped:
        a,b=lookup[c['wordIds'][0]]['startFrame'],lookup[c['wordIds'][-1]]['endFrame'];new_cues.append({'id':c['id'],'sentenceId':c['sentenceId'],'wordIds':c['wordIds'],'text':c['text'],'startFrame':a,'endFrame':b,'startTick':frame_us(a),'endTick':frame_us(b)})
    new_cues[0].update(startFrame=remap(first_frame,True),startTick=frame_us(remap(first_frame,True)))
    new_cues[-1].update(endFrame=remap(last_frame,False),endTick=frame_us(remap(last_frame,False)))
    for a,b in zip(new_cues,new_cues[1:]):a.update(endFrame=b['startFrame'],endTick=b['startTick'])
    if any(c['startFrame']>=c['endFrame'] or c['startTick']>=c['endTick'] for c in new_cues):raise ValueError('Zero-length rounded caption prohibited')
    srt='\n'.join(f"{i}\n{srt_time(c['startTick']/1e6)} --> {srt_time(c['endTick']/1e6)}\n{c['text']}\n" for i,c in enumerate(new_cues,1))
    old_lookup={w['id']:w for w in wordrows}
    for row in reports:
        l,r=old_lookup[row['previousWordId']],old_lookup[row['nextWordId']];nl,nr=lookup[l['id']],lookup[r['id']]
        oa,ob=ceil_frame(l['end']),floor_frame(r['start']);na,nb=ceil_frame(nl['endTick']),floor_frame(nr['startTick'])
        row.update(beforeAuditoryGapTicks=r['start']-l['end'],afterAuditoryGapTicks=nr['startTick']-nl['endTick'],beforeWholeQuietFrames=max(0,ob-oa),afterWholeQuietFrames=max(0,nb-na),beforeTicks=max(0,frame_us(ob)-frame_us(oa)),afterTicks=max(0,frame_us(nb)-frame_us(na)),beforeLeftSubframeTicks=frame_us(oa)-l['end'],beforeRightSubframeTicks=r['start']-frame_us(ob),afterLeftSubframeTicks=frame_us(na)-nl['endTick'],afterRightSubframeTicks=nr['startTick']-frame_us(nb),auditoryEvidenceBasis='SUPPLIED_REVIEW_ASSERTIONS_NOT_AUTHENTICATED')
        if scope=='SENTENCE_AND_INTRA' and row['kind']!='sentence-boundary' and row['afterAuditoryGapTicks']>cap_ticks:
            conflicts.append({'previousWordId':row['previousWordId'],'nextWordId':row['nextWordId'],'status':'POST_PROJECTED_AUDITORY_CAP_REVIEW_REQUIRED','reason':'Projected full word gap exceeds five-frame cap; no native application before reviewed mapping'})
            row['decision']='PREPARED_JOIN_TARGET_REVIEW_REQUIRED'
    for row in boundary_reports:
        head=row['kind']=='head-quiet';w=wordrows[0 if head else -1];nw=lookup[w['id']]
        old_a,old_b=(0,w['start']) if head else (w['end'],frame_us(cursor))
        new_a,new_b=(0,nw['startTick']) if head else (nw['endTick'],frame_us(out_frame))
        oa,ob=ceil_frame(old_a),floor_frame(old_b);na,nb=ceil_frame(new_a),floor_frame(new_b)
        row.update(beforeAuditoryGapTicks=old_b-old_a,afterAuditoryGapTicks=new_b-new_a,beforeWholeQuietFrames=max(0,ob-oa),afterWholeQuietFrames=max(0,nb-na),beforeTicks=max(0,frame_us(ob)-frame_us(oa)),afterTicks=max(0,frame_us(nb)-frame_us(na)),beforeLeftSubframeTicks=frame_us(oa)-old_a,beforeRightSubframeTicks=old_b-frame_us(ob),afterLeftSubframeTicks=frame_us(na)-new_a,afterRightSubframeTicks=new_b-frame_us(nb),auditoryEvidenceBasis='SUPPLIED_REVIEW_ASSERTIONS_NOT_AUTHENTICATED')
    for row in reports:
        if row['kind']=='sentence-boundary' and row['decision']=='REVIEWED15_FRAME_TARGET':
            low=15*1000000*rate.denominator//rate.numerator;high=(15*1000000*rate.denominator+rate.numerator-1)//rate.numerator
            if not low<=row['afterAuditoryGapTicks']<=high:
                conflicts.append({'previousWordId':row['previousWordId'],'nextWordId':row['nextWordId'],'status':'POST_PROJECTED_AUDITORY_TARGET_REVIEW_REQUIRED','reason':'Prepared projected word gap does not represent15frames; no native application before reviewed mapping'})
                row['decision']='PREPARED_JOIN_TARGET_REVIEW_REQUIRED'
    prepared_status='PARTIAL_PREPARED_REVIEW_REQUIRED' if conflicts else 'PREPARED_ONLY'
    report={'status':prepared_status,'nativeRepresentationConflicts':conflicts,'intraAuditoryGapMaximumTicks':cap_ticks,'sentenceShortfallPolicy':shortfall,'units':'FRAMES_ACTUAL_TIMELINE_FPS','fpsNumerator':rate.numerator,'fpsDenominator':rate.denominator,'sentenceTailFrames':15,'intraSentenceBreathCapFrames':5,'lastSentenceForcedTail':False,'reviewedCaptionOuterBounds':outer,'afterFirstCaptionOnsetFrame':new_cues[0]['startFrame'],'afterLastCaptionEndFrame':new_cues[-1]['endFrame'],'beforeDurationFrames':cursor,'afterDurationFrames':out_frame,'beforeDurationTicks':frame_us(cursor),'afterDurationTicks':frame_us(out_frame),'nativeClock':native,'pauses':reports,'quietEdits':edits,'piecewiseSourceToOutput':maps,'words':remapped,'captionCues':new_cues,'reviewedProtectedSpans':protected,'sourceWordOrderAndPiecesPreserved':True,'captionTextAndGroupingPreserved':True,'nativeAudioAcceptance':'PENDING','BrollReanchorAndNewBaseCheckpoint':'PENDING_REQUIRED','limitations':['Source/grammar/speech-free/tail/join/native-FPS review assertions are not authenticated; amplitude-only evidence is insufficient.','Frame endpoints use floor(frame*1000000/FPS); equal frame spans can differ by one microsecond with phase. Intra-sentence cap judges full projected raw word gap against ceil(5*1000000/FPS), not the count of contained quiet frames; sentence target also checks projected auditory gap against nativefloor/ceil15frame ticks. Raw positive word/audio ticks can share frames; only reviewed whole-frame quiet bounds are cut.','Normal-speed baseline maps only; source/native frame mapping must be reviewed, never silently rescaled.','Phase normalization is reported; source/audio boundaries, actual15/<=5frames, words/joins, native captions/editability/persistence need fresh readback.','No source FPS assumption, FPS/speed change, padded/frozen tail, final-sentence forced tail or app/source mutation. Reviewed shortfall needs explicit decision, retains exact real source quiet and reports eachsentence. Unknown review is not shortfall. Fraction/native representation conflicts hold affected joins with partial prepared status, never source/word normalization.']}
    spec={'status':prepared_status,'applyEligible':False,'heldJoinsRequireReview':conflicts,'fpsNumerator':rate.numerator,'fpsDenominator':rate.denominator,'tickRate':1000000,'track':{'type':'video','name':'Paced main speech','items':items},'preserveSourceFiles':True,'captionTextOperations':[]}
    report.update(pacingScope=scope,pacingScopeDefault=default_scope,pacingStyleBinding=style_binding,pacingScopeOverride=override,intraSentencePausesPreserved=scope=='INTER_SENTENCE_ONLY',intraSentenceEditCount=sum(e['kind']=='intra-sentence-breath' for e in edits),captionOnsetStatus='FRAME_ESTIMATES_PENDING_FINAL_AUDIO_REVIEW',finalCaptionAnchorAcceptance='PENDING',captionStartsUnchangedByEndFill=True)
    if scope=='INTER_SENTENCE_ONLY':report.update(intraAuditoryGapMaximumTicks=None,intraSentenceBreathCapFrames=None)
    if scope=='ALL_PAUSES':
        report.update(intraAuditoryGapMaximumTicks=None,intraSentenceBreathCapFrames=None,sentenceTailFrames=None,sentenceShortfallPolicy=None,pauseCriterion=copy.deepcopy(criterion),boundaryPauses=boundary_reports,allPausePolicy='REAL_QUIET_STRICTLY_OVER_200MS_SAFE_INTERIORS_NO_FORCED_GAP',phoneticHandlesPreserved=True,allEligibleQuietPrepared=not conflicts)
        report['limitations']=[item for item in report['limitations'] if not any(term in item for term in ('sentence target','actual15/<=5frames','Reviewed shortfall'))]
        report['limitations'].append('ALL_PAUSES audits HEAD/INTERNAL/TAIL candidates strictly over200000 microseconds before frame containment. At/below remains unchanged. This is a detection threshold, never a retained200ms or zero-gap target. Speech-facing phonetic margins stay positive; only exposed outer edges may have zero margin. Missing/uncertain review holds the affected window with a specific diagnosis. Raw boundary, quiet and review assertions remain unauthenticated; native hearing, final edited-audio caption anchors, B-roll reanchor and persistence are pending.')
    report['limitations'].append('Pacing scope preserves every intra-sentence gap in INTER_SENTENCE_ONLY. Mechanically floored caption starts are provisional frame estimates, not authenticated audible onsets. Freeze a separately reviewed final edited-audio onset tuple before an end-only hold; never advance later starts to fill quiet.')
    spec.update(pacingScope=scope,captionOnsetStatus=report['captionOnsetStatus'],finalCaptionAnchorAcceptance='PENDING')
    return {'pacing-spec.json':json.dumps(spec,ensure_ascii=False,indent=2)+'\n','pacing-report.json':json.dumps(report,ensure_ascii=False,indent=2)+'\n','paced-captions.srt':srt}



def pacing_input(data):
    """Preserve declared wrapper routing facts, never inherit general cut authority."""
    if not isinstance(data,dict):raise ValueError('Plan object required')
    if 'pacingPlan' not in data:return data
    child=data['pacingPlan']
    if not isinstance(child,dict):raise ValueError('Pacing wrapper requires an object pacingPlan')
    result=copy.deepcopy(child)
    fields=('recipient','contentDomain','style','pacingScope','pacingScopeOverride','reviewedFinalCaptionOnsets','pauseCriterion')
    for field in fields:
        if field not in data:continue
        if field in child and json.dumps(child[field],sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)!=json.dumps(data[field],sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False):raise ValueError('Conflicting outer/child pacing context: '+field)
        result[field]=copy.deepcopy(data[field])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',required=True,type=Path);parser.add_argument('--out-dir',required=True,type=Path);parser.add_argument('--mode',choices=('content','broll','intake','pacing'),default='content');args=parser.parse_args()
    try:
        if not args.out_dir.is_absolute() or args.out_dir.exists():raise ValueError('New absolute task-owned output directory required')
        for p in (args.out_dir,*args.out_dir.parents):
            if p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()):raise ValueError('Linked output directory')
        data=json.loads(args.plan.read_text(encoding='utf-8-sig'))
        if not isinstance(data,dict):raise ValueError('Plan object required')
        artifacts=prepare_broll(data.get('bRollPlan',data)) if args.mode=='broll' else prepare_intake(data) if args.mode=='intake' else prepare_pacing(pacing_input(data)) if args.mode=='pacing' else prepare(data)
        args.out_dir.mkdir(parents=True,exist_ok=False)
        for name,text in artifacts.items():(args.out_dir/name).write_text(text,encoding='utf-8',newline='\n')
        result_status=json.loads(artifacts['broll-spec.json'])['status'] if args.mode=='broll' else 'PREPARED_ONLY'
        print(json.dumps({'status':result_status,'output':str(args.out_dir),'files':list(artifacts)},ensure_ascii=False));return 0
    except (ValueError,KeyError,TypeError,OSError) as e:
        print(json.dumps({'status':'BLOCKED','reason':str(e)},ensure_ascii=False));return 2

if __name__=='__main__':raise SystemExit(main())
