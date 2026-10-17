"""Compile explicit reviewed/provisional plans into editable CapCut 9.5.5 files.

Preparation writes only a fresh caller-selected task directory. Native apply is a
separate opt-in operation that creates one new project and inserts one index row.
Neither operation hears audio, judges content, proves glyph fit or native playback.
Only Python's standard library and sibling owned guard/template files are used.
"""
from __future__ import annotations

import argparse
import copy
import csv
import functools
from fractions import Fraction
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from source_hash_session import digest as verified_digest, verified_hash_session

SCHEMA = 'capcut-timeline-plan/v1'
MANIFEST_SCHEMA = 'capcut-native-compiled/v1'
APP_VERSION = '9.5.5'
TEMPLATE = Path(__file__).resolve().parent.parent / 'templates/native-template.json'
DEPENDENCIES = ('speeds', 'placeholder_infos', 'canvases',
                'sound_channel_mappings', 'material_colors', 'vocal_separations')


class PlanError(ValueError):
    """The explicit input cannot be represented safely by this producer."""


def require(condition, message):
    if not condition:
        raise PlanError(message)


def _pairs(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, 'duplicate-json-key: ' + k)
        result[k] = v
    return result


def read_json(path):
    return json.loads(Path(path).read_text('utf-8-sig'), object_pairs_hook=_pairs,
                      parse_constant=lambda v: (_ for _ in ()).throw(PlanError('nonfinite-json-number')))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                       allow_nan=False) + '\n').encode('utf-8')


def sha256(path):
    return verified_digest(path).removeprefix('sha256:')


def _verified_call(function):
    @functools.wraps(function)
    def run(*args, **kwargs):
        with verified_hash_session():
            return function(*args, **kwargs)
    return run


def _hash(value):
    require(isinstance(value, str), 'sha256-string-required')
    value = value.removeprefix('sha256:').lower()
    require(bool(re.fullmatch('[0-9a-f]{64}', value)), 'sha256-required')
    return value


def _int(value, label, minimum=0):
    require(type(value) is int and value >= minimum, label + '-integer-required')
    return value


def _number(value, label, minimum=0, maximum=10):
    require(type(value) in (int, float) and math.isfinite(value)
            and minimum <= value <= maximum, label + '-number-out-of-range')
    return value


def _id(value, label='id'):
    require(isinstance(value, str) and bool(value.strip()) and '\x00' not in value,
            label + '-nonempty-string-required')
    return value


def _new_id():
    return str(uuid.uuid4()).upper()


def _unlinked(path, *, exists=True):
    path = Path(path)
    require(path.is_absolute(), 'absolute-path-required')
    for p in [path, *path.parents]:
        require(not p.is_symlink() and not (hasattr(p, 'is_junction') and p.is_junction()),
                'linked-path-refused')
    if exists:
        require(path.is_file(), 'source-file-required')
    return path


def _ref(ref):
    require(isinstance(ref, dict), 'bound-file-reference-required')
    p = _unlinked(ref.get('path', ''))
    require(sha256(p) == _hash(ref.get('sha256')), 'bound-file-hash-mismatch')
    return p


def _safe_name(name):
    _id(name, 'project-name')
    require(name == name.strip() and name not in ('.', '..')
            and not any(c in name for c in '<>:"/\\|?*\x00')
            and not name.endswith(('.', ' '))
            and not re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name),
            'project-name-invalid')
    return name


def _phase(plan, row, source, segment_id, material_id, a, b, x, y):
    if b - a == y - x:
        return
    require(row.get('nativeSegmentId') == segment_id
            and source.get('nativeMaterialId') == material_id,
            'native-phase-preserved-object-ids-required')
    require('nativePhaseEvidence' in plan, 'native-phase-evidence-required')
    # The shared owner validates exact inherited clocks, baseline and rational
    # frame geometry. A one-microsecond tolerance alone is intentionally absent.
    from dependency_proof import validate_native_phase
    validate_native_phase(plan['nativePhaseEvidence'], segment_id, material_id,
                          a, b, x, y, currentFps=plan['project']['fps'])


def validate_plan(plan, *, verify_sources=True):
    require(isinstance(plan, dict) and plan.get('schema') == SCHEMA, 'timeline-plan-schema')
    project = plan.get('project', {})
    _safe_name(project.get('name'))
    if project.get('revisionIdentity') is None:
        from project_naming import validate_new_project_name
        try:
            validate_new_project_name(project['name'])
        except ValueError as error:
            raise PlanError('new-project-name-invalid: ' + str(error)) from error
    else:
        from native_revision import load_baseline
        baseline = load_baseline(project['revisionIdentity'])
        require(project['name'] == baseline['name'], 'revision-compile-name-mismatch')
    fps = project.get('fps')
    _number(fps, 'fps', 1, 240)
    if 'rationalFps' in project:
        f = project['rationalFps']
        require(isinstance(f, dict), 'rational-fps-object-required')
        require(abs(_int(f.get('numerator'), 'fps-numerator', 1) /
                    _int(f.get('denominator'), 'fps-denominator', 1) - fps) < 1e-10,
                'rational-fps-mismatch')
    canvas = project.get('canvas', {})
    _int(canvas.get('width'), 'canvas-width', 1)
    _int(canvas.get('height'), 'canvas-height', 1)
    sources = plan.get('sources')
    require(isinstance(sources, list) and sources, 'sources-required')
    by_source = {}; paths = set(); ids = set()
    for source in sources:
        require(isinstance(source, dict), 'source-object-required')
        sid = _id(source.get('id'), 'source-id')
        require(sid not in by_source, 'duplicate-source-id')
        p = _unlinked(source.get('path', ''))
        require(p.resolve() not in paths, 'duplicate-source-path-use-one-source-id')
        paths.add(p.resolve())
        _int(source.get('durationTicks'), 'full-source-duration', 1)
        _int(source.get('width'), 'source-width', 1)
        _int(source.get('height'), 'source-height', 1)
        if 'displayWidth' in source or 'displayHeight' in source:
            require(source.get('displayWidth')==source['width'] and source.get('displayHeight')==source['height'],
                    'native-source-dimensions-must-be-display-dimensions')
        h = _hash(source.get('sha256'))
        if verify_sources:
            require(sha256(p) == h, 'source-hash-mismatch: ' + sid)
        by_source[sid] = source
    main = plan.get('mainPieces'); captions = plan.get('captions'); broll = plan.get('broll', [])
    require(isinstance(main, list) and main, 'main-pieces-required')
    require(isinstance(captions, list), 'caption-array-required')
    require(isinstance(broll, list), 'broll-array-required')
    cursor = 0; bounds = {}; source_usage = set()
    for role, rows in [('main', main), ('broll', broll)]:
        previous_end = 0
        for row in rows:
            require(isinstance(row, dict), role + '-object-required')
            rid = _id(row.get('id'))
            require(rid not in ids, 'duplicate-logical-object-id')
            ids.add(rid)
            sid = row.get('sourceId')
            require(sid in by_source, 'unknown-source-id')
            source = by_source[sid]
            a = _int(row.get('sourceInTicks'), 'source-in')
            b = _int(row.get('sourceOutTicks'), 'source-out', 1)
            x = _int(row.get('targetInTicks'), 'target-in')
            y = _int(row.get('targetOutTicks', x + b - a), 'target-out', 1)
            require(a < b <= source['durationTicks'] and x < y, 'source-target-bounds')
            require(row.get('speed', 1) == 1 and type(row.get('speed', 1)) in (int, float)
                    and row.get('reverse', False) is False, 'normal-forward-speed-required')
            require(x >= previous_end, role + '-overlap-or-order')
            previous_end = y
            if role == 'main':
                require(x == cursor, 'main-target-gap')
                cursor = y
                _number(row.get('volume', 1.0), 'main-volume')
            else:
                require(row.get('mute') is True, 'broll-mute-required')
                require(y <= cursor, 'broll-outside-main-duration')
                identity = _hash(source['sha256'])
                require(identity not in source_usage, 'broll-source-repeat')
                source_usage.add(identity)
                if source.get('origin') in ('CAMERA', 'CAMERA_SHOT') and source.get('voice') in ('NO_VOICE', 'WITHOUT_VOICE'):
                    require(a >= 5_000_000 and b <= source['durationTicks'] - 4_000_000,
                            'camera-no-voice-source-edge-exclusion')
            _phase(plan, row, source, row.get('nativeSegmentId'),
                   source.get('nativeMaterialId'), a, b, x, y)
            bounds[rid] = (a, b, x, y)
    require(plan.get('brollPolicy', 'NO_SOURCE_REPEAT') == 'NO_SOURCE_REPEAT',
            'producer-only-supports-no-source-repeat')
    prior_end = 0; raw_ids = set()
    for cue in captions:
        require(isinstance(cue, dict), 'caption-object-required')
        rid = _id(cue.get('id'))
        require(rid not in ids, 'duplicate-logical-object-id'); ids.add(rid)
        text = cue.get('text')
        require(isinstance(text, str) and text.strip() and not any(c in text for c in '\r\n\x00'),
                'caption-one-row-nonempty-text-required')
        a = _int(cue.get('startTicks'), 'caption-start')
        b = _int(cue.get('endTicks'), 'caption-end', 1)
        require(prior_end <= a < b <= cursor, 'caption-overlap-or-bounds')
        prior_end = b
        words = cue.get('rawWordIds')
        require(isinstance(words, list) and words and all(type(w) in (str, int) for w in words)
                and len(set(words)) == len(words), 'caption-raw-ids-required')
        require(not raw_ids.intersection(words), 'caption-raw-id-reused'); raw_ids.update(words)
        _validate_style(cue.get('style', {}))
    return {'durationTicks': cursor, 'sources': by_source, 'bounds': bounds}


def _validate_style(style):
    require(isinstance(style, dict), 'caption-style-object-required')
    allowed = {'fontPath', 'fontSHA256', 'fontName', 'fontTitle', 'fontSize',
               'color', 'positionX', 'positionY', 'scaleX', 'scaleY', 'rotation',
               'opacity', 'lineMaxWidth', 'alignment', 'boldWidth', 'shadow'}
    require(set(style) <= allowed, 'unsupported-caption-style-field')
    require(('fontPath' in style) == ('fontSHA256' in style), 'font-path-and-hash-pair-required')
    if 'fontPath' in style:
        _ref({'path': style['fontPath'], 'sha256': style['fontSHA256']})
    for name in ('fontName', 'fontTitle'):
        if name in style: _id(style[name], name)
    for name, low, high in [('fontSize', .1, 200), ('positionX', -5, 5),
        ('positionY', -5, 5), ('scaleX', .01, 10), ('scaleY', .01, 10),
        ('rotation', -360, 360), ('opacity', 0, 1), ('lineMaxWidth', .01, 5), ('boldWidth', 0, 10)]:
        if name in style: _number(style[name], name, low, high)
    if 'color' in style:
        require(isinstance(style['color'], str) and bool(re.fullmatch('#[0-9a-fA-F]{6}', style['color'])), 'caption-color')
    if 'alignment' in style: require(type(style['alignment']) is int and style['alignment'] in (0, 1, 2), 'caption-alignment')
    if 'shadow' in style: require(type(style['shadow']) is bool, 'caption-shadow')


def _style(text_material, segment, cue):
    style = cue.get('style', {}); text = cue['text']
    m = text_material; content = m['content']; content['text'] = text
    m['font_path'] = style.get('fontPath', '')
    for native, name in [('font_name','fontName'), ('font_title','fontTitle'),
        ('font_size','fontSize'), ('text_color','color'), ('line_max_width','lineMaxWidth'),
        ('alignment','alignment'), ('bold_width','boldWidth'), ('has_shadow','shadow')]:
        if name in style: m[native] = style[name]
    m['global_alpha'] = m['text_alpha'] = style.get('opacity', 1.0)
    rgb = [int(m['text_color'][i:i+2],16)/255 for i in (1,3,5)]
    for span in content['styles']:
        span['range'] = [0, len(text.encode('utf-16-le')) // 2]
        span['size'] = m['font_size']; span['font']['path'] = m['font_path']
        span['fill']['alpha'] = m['text_alpha']
        span['fill']['content']['solid'].update(color=rgb, alpha=m['text_alpha'])
    segment['clip']['transform'] = {'x':style.get('positionX',0.0),'y':style.get('positionY',-.56)}
    segment['clip']['scale'] = {'x':style.get('scaleX',1.0),'y':style.get('scaleY',1.0)}
    segment['clip']['rotation'] = style.get('rotation',0.0)
    segment['clip']['alpha'] = style.get('opacity',1.0)
    m['content'] = json.dumps(content,ensure_ascii=False,separators=(',',':'))


@_verified_call
def compile_plan(plan, output_dir):
    """Produce a fresh task-local project; return its bound manifest dictionary."""
    started = time.perf_counter()
    plan = read_json(plan) if isinstance(plan, (str, Path)) else copy.deepcopy(plan)
    checked = validate_plan(plan)
    outdir = _unlinked(Path(output_dir).absolute(), exists=False)
    require(not outdir.exists(), 'compile-output-must-not-exist')
    require(not any((p/'root_meta_info.json').exists() or p.name.casefold()=='com.lveditor.draft'
                    for p in [outdir,*outdir.parents]), 'compile-task-output-cannot-be-native-store')
    t = read_json(TEMPLATE)
    require(t.get('schema') == 'capcut-native-template/v1' and t.get('appVersion') == APP_VERSION,
            'native-template-incompatible')
    out = copy.deepcopy(t['native']); now = time.time_ns() // 1000
    revision_ref = plan['project'].get('revisionIdentity')
    if revision_ref is not None:
        from native_revision import compile_identity
        pid, tid = compile_identity(revision_ref, plan['project']['name'])
    else:
        pid, tid = _new_id(), _new_id()
    duration = checked['durationTicks']
    out.update(id=tid,name=plan['project']['name'],duration=duration,create_time=now,update_time=now,
               fps=plan['project']['fps'],path='')
    canvas = plan['project']['canvas']; out['canvas_config'].update(canvas)
    from fractions import Fraction
    ratio = Fraction(canvas['width'],canvas['height'])
    out['canvas_config']['ratio'] = str(ratio.numerator)+':'+str(ratio.denominator)
    videos = {}; registrations = []; source_map = []
    native_ids = {pid,tid}
    def identity(explicit=None):
        ident = explicit if explicit is not None else _new_id()
        _id(ident, 'native-id'); require(ident not in native_ids, 'duplicate-native-id'); native_ids.add(ident)
        return ident
    for source in plan['sources']:
        m = copy.deepcopy(t['videoMaterial']); local = identity()
        mid = identity(source.get('nativeMaterialId'))
        m.update(id=mid,local_material_id=local,path=source['path'],duration=source['durationTicks'],
                 material_name=Path(source['path']).name,width=source['width'],height=source['height'])
        out['materials']['videos'].append(m); videos[source['id']] = m
        reg = copy.deepcopy(t['mediaRegistration'])
        reg.update(id=local,duration=source['durationTicks'],extra_info=Path(source['path']).name,
                   file_Path=source['path'].replace('\\','/'),width=source['width'],height=source['height'],
                   roughcut_time_range={'start':0,'duration':source['durationTicks']})
        registrations.append(reg)
        source_map.append({'sourceId':source['id'],'materialId':mid,'localMaterialId':local,
                           'path':source['path'],'sha256':_hash(source['sha256']),
                           'durationTicks':source['durationTicks'],'sizeBytes':Path(source['path']).stat().st_size})
    track_ids = {}; object_map = []
    for i, (role, label) in enumerate([('main','Main source'),('broll','Supporting picture'),('captions','Captions')]):
        track = copy.deepcopy(t['tracks'][i]); track.update(id=identity(),name=label,segments=[],is_default_name=False)
        out['tracks'].append(track); track_ids[role] = track['id']
    for ti, role, rows, key in [(0,'main',plan['mainPieces'],'videoSegment'),
                                (1,'broll',plan.get('broll',[]),'overlaySegment')]:
        for row in rows:
            a,b,x,y = checked['bounds'][row['id']]
            s = copy.deepcopy(t[key]); sid = identity(row.get('nativeSegmentId'))
            volume = row.get('volume',1.0) if role == 'main' else 0.0
            s.update(id=sid,raw_segment_id=sid,material_id=videos[row['sourceId']]['id'],
                source_timerange={'start':a,'duration':b-a},target_timerange={'start':x,'duration':y-x},
                volume=volume,last_nonzero_volume=volume if volume else 1.0,
                speed=1.0,reverse=False,extra_material_refs=[],desc='')
            for dep in DEPENDENCIES:
                d = copy.deepcopy(t['dependencies'][dep]); d['id'] = identity()
                out['materials'][dep].append(d); s['extra_material_refs'].append(d['id'])
            out['tracks'][ti]['segments'].append(s)
            object_map.append({'id':row['id'],'role':role,'segmentId':sid,
                               'trackId':track_ids[role],'materialId':s['material_id'],'sourceId':row['sourceId']})
    for cue in plan['captions']:
        m = copy.deepcopy(t['textMaterial']); m['id'] = identity()
        s = copy.deepcopy(t['textSegment']); sid = identity(cue.get('nativeSegmentId'))
        s.update(id=sid,raw_segment_id=sid,material_id=m['id'],
                 target_timerange={'start':cue['startTicks'],'duration':cue['endTicks']-cue['startTicks']})
        _style(m,s,cue); out['materials']['texts'].append(m); out['tracks'][2]['segments'].append(s)
        object_map.append({'id':cue['id'],'role':'captions','segmentId':sid,
                           'trackId':track_ids['captions'],'materialId':m['id'],'rawWordIds':cue['rawWordIds']})
    files = outdir/'files'; meta = copy.deepcopy(t['metadata'])
    meta.update(draft_id=pid,draft_name=out['name'],draft_fold_path=str(files).replace('\\','/'),
        draft_root_path=str(outdir).replace('\\','/'),draft_cover='',tm_draft_create=now,tm_draft_modified=now,
        tm_draft_removed=0,tm_duration=duration,draft_materials=[{'type':0,'value':registrations}],
        draft_timeline_materials_size_=sum(s['sizeBytes'] for s in source_map))
    pj = copy.deepcopy(t['project']); pj.update(id=tid,main_timeline_id=tid,create_time=now,update_time=now,
        timelines=[{'id':tid,'name':'Timeline 01','is_marked_delete':False,'create_time':now,'update_time':now}])
    content = json_bytes(out)
    payloads = {rel:content for rel in ('draft_content.json','template-2.tmp',
        f'Timelines/{tid}/draft_content.json',f'Timelines/{tid}/template-2.tmp')}
    payloads.update({'draft_meta_info.json':json_bytes(meta),'Timelines/project.json':json_bytes(pj),
        'timeline_layout.json':json_bytes({'dockItems':[{'dockIndex':0,'ratio':1,'timelineIds':[tid],
            'timelineNames':['Timeline 01']}],'layoutOrientation':1}),
        'draft_virtual_store.json':json_bytes({'draft_materials':[],
            'draft_virtual_store':[{'type':i,'value':[]} for i in range(3)]}),
        'key_value.json':json_bytes({})})
    # Validate before creating any output; material/default inheritance is tested
    # semantically, rather than inferred from successful JSON serialization.
    manifest = {'schema':MANIFEST_SCHEMA,'status':'PREPARED_ONLY','appVersion':APP_VERSION,
        'name':out['name'],'projectId':pid,'timelineId':tid,'durationTicks':duration,
        'identityMode':'OWNED_REVISION' if revision_ref is not None else 'CREATE_NEW',
        'trackIds':track_ids,'sources':source_map,'objects':object_map,
        'templateSHA256':sha256(TEMPLATE),'planSHA256':hashlib.sha256(json_bytes(plan)).hexdigest(),
        'files':{rel:hashlib.sha256(data).hexdigest() for rel,data in payloads.items()},
        'nativeAcceptance':'PENDING','captionOneLineGlyphFit':'PENDING',
        'audioContentAndOnsets':'PENDING','compileSeconds':time.perf_counter()-started}
    inspect_native(out, plan, manifest, verify_sources=False)
    outdir.mkdir(); files.mkdir()
    for rel, data in payloads.items():
        path = files/rel; path.parent.mkdir(parents=True,exist_ok=True); _exclusive_write(path,data)
    _exclusive_write(outdir/'plan.json',json_bytes(plan))
    _exclusive_write(outdir/'compiled-manifest.json',json_bytes(manifest))
    report = validate_compiled(outdir, verify_sources=False)
    _exclusive_write(outdir/'semantic-readback.json',json_bytes(report))
    return manifest


def _load_native(value):
    if isinstance(value, dict): return copy.deepcopy(value)
    path = Path(value)
    return read_json(path/'draft_content.json' if path.is_dir() else path)


def _frame_event(expected, actual, project):
    """Return the shared rational frame index, never a time tolerance."""
    if type(expected) is not int or type(actual) is not int or min(expected, actual) < 0:
        return None
    rate = project.get('rationalFps')
    fps = (Fraction(rate['numerator'], rate['denominator']) if rate is not None
           else Fraction(str(project['fps'])))
    unit = 1_000_000 * fps.denominator
    near = expected * fps.numerator // unit
    for frame in (near, near + 1):
        floor, remainder = divmod(frame * unit, fps.numerator)
        endpoints = {floor, floor + bool(remainder)}
        if expected in endpoints and actual in endpoints:
            return frame
    return None


def _saved_tick(expected, actual, project, changes, **identity):
    if type(actual) is not int or actual < 0:
        return False
    if actual == expected:
        return True
    frame = _frame_event(expected, actual, project)
    if frame is None:
        return False
    changes.append({**identity, 'expectedTick':expected, 'actualTick':actual,
                    'frameIndex':frame})
    return True


def _saved_range(actual, start, end, project, changes, *, segment_id, range_name,
                 allow_start=True):
    if (not isinstance(actual, dict) or set(actual) != {'start', 'duration'}
            or type(actual.get('start')) is not int or type(actual.get('duration')) is not int
            or actual['start'] < 0 or actual['duration'] <= 0):
        return False
    identity = {'segmentId':segment_id, 'range':range_name}
    return ((actual['start'] == start if not allow_start else
             _saved_tick(start, actual['start'], project, changes, endpoint='start', **identity))
            and _saved_tick(end, actual['start'] + actual['duration'], project, changes,
                            endpoint='end', **identity))


def _saved_registration_duration(original, actual, project, changes, material_id):
    if type(actual) is not int or actual <= 0:
        return False
    if actual == original:
        return True
    rate = project.get('rationalFps')
    fps = (Fraction(rate['numerator'], rate['denominator']) if rate is not None
           else Fraction(str(project['fps'])))
    unit = 1_000_000 * fps.denominator
    frame = (original * fps.numerator + unit - 1) // unit
    floor, remainder = divmod(frame * unit, fps.numerator)
    if actual not in {floor, floor + bool(remainder)}:
        return False
    entry = {'materialId':material_id, 'originalDurationTick':original,
             'savedDurationTick':actual, 'ceilingFrameIndex':frame}
    if entry not in changes:
        changes.append(entry)
    return True


@_verified_call
def inspect_native(native, plan, manifest, *, verify_sources=True):
    """Verify objects by IDs with bounded observed save normalization.

    This is saved-file evidence only. It cannot certify native UI or heard audio.
    """
    draft = _load_native(native)
    plan = read_json(plan) if isinstance(plan,(str,Path)) else plan
    manifest = read_json(manifest) if isinstance(manifest,(str,Path)) else manifest
    checked = validate_plan(plan,verify_sources=verify_sources)
    clock_changes = []; duplicate_materials = []; registration_changes = []
    require(draft.get('id') == manifest['timelineId']
            and _saved_tick(checked['durationTicks'], draft.get('duration'), plan['project'],
                            clock_changes, range='timeline', endpoint='end'),
            'native-timeline-id-or-duration-mismatch')
    require(draft.get('fps') == plan['project']['fps'], 'native-fps-mismatch')
    require(all(draft.get('canvas_config',{}).get(k)==v for k,v in plan['project']['canvas'].items()),
            'native-canvas-mismatch')
    materials = {}; kinds = {}
    for kind, rows in draft.get('materials',{}).items():
        require(isinstance(rows,list), 'native-material-array-required')
        for m in rows:
            mid = _id(m.get('id'),'native-material-id')
            if mid in materials:
                require(kinds[mid] == kind
                        and json.dumps(m, sort_keys=True, ensure_ascii=False, allow_nan=False)
                        == json.dumps(materials[mid], sort_keys=True, ensure_ascii=False, allow_nan=False),
                        'native-duplicate-material-id')
                duplicate_materials.append({'materialId':mid, 'category':kind})
                continue
            materials[mid] = m; kinds[mid] = kind
    actual = {}; tracks = {}; native_ids = set(materials)
    for track in draft.get('tracks',[]):
        tid = _id(track.get('id'),'native-track-id')
        require(tid not in tracks and tid not in native_ids,'native-duplicate-track-id'); tracks[tid] = track
        native_ids.add(tid)
        for seg in track.get('segments',[]):
            sid = _id(seg.get('id'),'native-segment-id')
            require(sid not in actual and sid not in native_ids,'native-duplicate-segment-id')
            actual[sid] = (tid,seg)
            native_ids.add(sid)
    require(set(actual)=={r['segmentId'] for r in manifest['objects']}, 'native-active-object-inventory-mismatch')
    require(set(tracks)==set(manifest['trackIds'].values()), 'native-track-inventory-mismatch')
    source_specs = checked['sources']; sources = {r['sourceId']:r for r in manifest['sources']}
    rows = {r['id']:r for r in plan['mainPieces']+plan.get('broll',[])+plan['captions']}
    template = read_json(TEMPLATE)
    for obj in manifest['objects']:
        tid,seg = actual[obj['segmentId']]; row=rows[obj['id']]
        require(tid==obj['trackId'] and seg.get('material_id')==obj['materialId'], 'native-object-reference-mismatch')
        role = obj['role']; material = materials.get(obj['materialId'])
        require(material is not None, 'native-object-material-missing')
        require(seg.get('speed')==1 and not seg.get('reverse') and not seg.get('is_loop'), 'native-normal-speed-required')
        if role in ('main','broll'):
            require(tracks[tid].get('type')=='video' and kinds[obj['materialId']]=='videos', 'native-video-role')
            spec=source_specs[obj['sourceId']]; registered=sources[obj['sourceId']]
            a,b,x,y=checked['bounds'][row['id']]
            source_range = seg.get('source_timerange'); target_range = seg.get('target_timerange')
            require(_saved_range(target_range, x, y, plan['project'], clock_changes,
                                 segment_id=seg['id'], range_name='target'),
                    'native-source-target-clocks-mismatch')
            # Observed source normalization changes only the end, with the same
            # normal-speed duration change in the target. Source starts stay exact.
            source_exact = source_range == {'start':a,'duration':b-a}
            require(isinstance(source_range, dict)
                    and (source_exact or (b-a == y-x
                         and source_range.get('duration') == target_range['duration']))
                    and _saved_range(source_range, a, b, plan['project'], clock_changes,
                                     segment_id=seg['id'], range_name='source', allow_start=False)
                    and source_range['start'] + source_range['duration'] <= spec['durationTicks'],
                    'native-source-target-clocks-mismatch')
            volume = row.get('volume',1.0) if role=='main' else 0
            segment_template=template['videoSegment' if role=='main' else 'overlaySegment']
            require(seg.get('volume')==volume and seg.get('visible') is True
                    and seg.get('clip')==segment_template['clip']
                    and all(seg.get(k)==segment_template.get(k) for k in ('render_index','track_render_index')),
                    'native-volume-or-visibility-mismatch')
            require(material.get('path')==spec['path']
                and _saved_registration_duration(spec['durationTicks'], material.get('duration'),
                                                  plan['project'], registration_changes, obj['materialId'])
                and material.get('width')==spec['width'] and material.get('height')==spec['height']
                and material.get('local_material_id')==registered['localMaterialId'], 'native-full-source-registration-mismatch')
            refs=seg.get('extra_material_refs')
            require(isinstance(refs,list) and len(refs)==len(DEPENDENCIES) and len(set(refs))==len(refs)
                and {kinds.get(r) for r in refs}==set(DEPENDENCIES),'native-video-dependencies-mismatch')
            speed = next(materials[r] for r in refs if kinds[r]=='speeds')
            require(speed.get('speed')==1 and not speed.get('curve_speed'), 'native-speed-dependency-mismatch')
            for ref in refs:
                dependency=materials[ref]
                expected=copy.deepcopy(template['dependencies'][kinds[ref]]); expected['id']=ref
                require(dependency==expected,'native-resolved-dependency-setting-mismatch')
        else:
            require(tracks[tid].get('type')=='text' and kinds[obj['materialId']]=='texts', 'native-caption-role')
            require(_saved_range(seg.get('target_timerange'), row['startTicks'], row['endTicks'],
                                 plan['project'], clock_changes, segment_id=seg['id'], range_name='target'),
                    'native-caption-clock-mismatch')
            expected_m=copy.deepcopy(template['textMaterial']); expected_s=copy.deepcopy(template['textSegment'])
            _style(expected_m,expected_s,row)
            require(json.loads(material.get('content','{}'))==json.loads(expected_m['content']), 'native-caption-text-or-utf16-style-mismatch')
            fields=('font_path','font_name','font_title','font_size','text_color','text_alpha','global_alpha',
                    'line_max_width','alignment','bold_width','has_shadow','line_feed','typesetting')
            require(all(material.get(k)==expected_m.get(k) for k in fields)
                    and seg.get('clip')==expected_s['clip'], 'native-caption-appearance-mismatch')
    return {'status':'SEMANTIC_READBACK_PASS','scope':'FILE_SEMANTICS_ONLY',
            'counts':{role:sum(r['role']==role for r in manifest['objects']) for role in ('main','broll','captions')},
            'durationTicks':draft['duration'],'nativePlayback':'PENDING','captionFitAndGlyphs':'PENDING',
            'audioContentAndOnsets':'PENDING','saveCloseReopen':'PENDING',
            'saveNormalization':{'clockEndpoints':clock_changes,
                                 'identicalMaterialAliases':duplicate_materials,
                                 'registrationDurations':registration_changes}}


@_verified_call
def validate_compiled(output_dir, *, verify_sources=True):
    root=Path(output_dir); manifest=read_json(root/'compiled-manifest.json'); plan=read_json(root/'plan.json')
    require(manifest.get('schema')==MANIFEST_SCHEMA,'compiled-manifest-schema')
    revision_ref=plan.get('project',{}).get('revisionIdentity')
    require(manifest.get('identityMode','CREATE_NEW') == ('OWNED_REVISION' if revision_ref is not None else 'CREATE_NEW'),
            'compiled-identity-mode-mismatch')
    if revision_ref is not None:
        from native_revision import load_baseline
        baseline=load_baseline(revision_ref)
        require(all(manifest.get(k)==baseline.get(k) for k in ('projectId','timelineId','name')),
                'compiled-revision-identity-mismatch')
    require(hashlib.sha256(json_bytes(plan)).hexdigest()==manifest['planSHA256'],'compiled-plan-drift')
    require(sha256(TEMPLATE)==manifest['templateSHA256'],'compiled-template-drift')
    expected={'draft_content.json','template-2.tmp',f"Timelines/{manifest['timelineId']}/draft_content.json",
        f"Timelines/{manifest['timelineId']}/template-2.tmp",'draft_meta_info.json',
        'Timelines/project.json','timeline_layout.json','draft_virtual_store.json','key_value.json'}
    require(set(manifest['files'])==expected,'compiled-file-inventory-mismatch')
    for rel,h in manifest['files'].items():
        require(sha256(_unlinked((root/'files'/rel).absolute()))==h,'compiled-file-drift: '+rel)
    mirrors=[manifest['files'][r] for r in expected if r.endswith('draft_content.json') or r.endswith('template-2.tmp')]
    require(len(set(mirrors))==1,'compiled-timeline-mirror-mismatch')
    pj=read_json(root/'files/Timelines/project.json'); tid=manifest['timelineId']
    require(pj.get('id')==tid and pj.get('main_timeline_id')==tid
        and [r['id'] for r in pj.get('timelines',[])]==[tid],'compiled-active-timeline-mismatch')
    layout=read_json(root/'files/timeline_layout.json')
    require(layout.get('dockItems',[{}])[0].get('timelineIds')==[tid], 'compiled-layout-timeline-mismatch')
    meta=read_json(root/'files/draft_meta_info.json')
    require(meta.get('draft_id')==manifest['projectId'] and meta.get('draft_name')==manifest['name']
        and meta.get('tm_duration')==manifest['durationTicks'],'compiled-metadata-mismatch')
    registrations=meta.get('draft_materials',[{}])[0].get('value',[])
    require(len(registrations)==len(manifest['sources']),'compiled-source-registration-count')
    for spec in manifest['sources']:
        regs=[r for r in registrations if r.get('id')==spec['localMaterialId']]
        require(len(regs)==1 and regs[0].get('duration')==spec['durationTicks']
            and regs[0].get('roughcut_time_range')=={'start':0,'duration':spec['durationTicks']}
            and regs[0].get('file_Path')==spec['path'].replace('\\','/'),'compiled-source-registration-mismatch')
    return inspect_native(root/'files',plan,manifest,verify_sources=verify_sources)


def _exclusive_write(path, data):
    with Path(path).open('xb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    require(Path(path).read_bytes()==data, 'file-readback-mismatch')


def inserted_index(raw, entry):
    """Prepend one row while retaining *all* original UTF-8 bytes verbatim."""
    bom=b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
    text=raw[len(bom):].decode('utf-8'); decoder=json.JSONDecoder(object_pairs_hook=_pairs)
    parsed=json.loads(text,object_pairs_hook=_pairs)
    require(isinstance(parsed,dict) and isinstance(parsed.get('all_draft_store'),list),'index-shape-unsupported')
    def ws(i):
        while i<len(text) and text[i].isspace(): i+=1
        return i
    i=ws(0); require(text[i]=='{','index-root-object'); i+=1; at=None
    while True:
        i=ws(i)
        if text[i]=='}': break
        key,end=decoder.raw_decode(text,i); i=ws(end); require(text[i]==':','index-colon'); i=ws(i+1)
        _,end=decoder.raw_decode(text,i)
        if key=='all_draft_store':
            require(text[i]=='[','index-array'); at=len(bom)+len(text[:i+1].encode('utf-8')); break
        i=ws(end); require(text[i]==',','index-separator'); i+=1
    require(at is not None,'index-store-array-missing')
    addition=json_bytes(entry).rstrip(b'\n')+(b',' if parsed['all_draft_store'] else b'')
    after=raw[:at]+addition+raw[at:]
    require(after[:at]==raw[:at] and after[at+len(addition):]==raw[at:],'index-original-bytes-not-preserved')
    check=json.loads(after.decode('utf-8-sig'),object_pairs_hook=_pairs)
    require(check['all_draft_store']==[entry]+parsed['all_draft_store'],'index-insertion-readback')
    return after, {'insertionOffset':at,'insertedByteCount':len(addition),
        'oldEntryCount':len(parsed['all_draft_store']),'newEntryCount':len(parsed['all_draft_store'])+1,
        'allOriginalBytesPreserved':True}


def _assert_editor_closed():
    require(os.name=='nt','native-apply-requires-windows-process-check')
    # Observe the actual process table. A caller-supplied closed flag is ignored.
    result=subprocess.run(['tasklist.exe','/FO','CSV','/NH'],capture_output=True,check=True,
                          text=True,encoding='utf-8',errors='replace')
    rows=list(csv.reader(io.StringIO(result.stdout)))
    require(bool(rows),'process-inventory-unavailable')
    require(not any(row and row[0].casefold() in ('capcut.exe','capcutlauncher.exe') for row in rows),
            'capcut-must-be-closed')


def _assert_app(request):
    executable=_unlinked(request.get('appExecutable',''))
    require(sha256(executable)==_hash(request.get('appExecutableSHA256')),'app-executable-drift')
    require(os.name=='nt','native-apply-requires-windows-version-check')
    # Pass path as argv via environment; never interpolate shell command text.
    env=dict(os.environ); env['CAPCUT_OWNED_VERSION_TARGET']=str(executable)
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
        '(Get-Item -LiteralPath $env:CAPCUT_OWNED_VERSION_TARGET).VersionInfo.ProductVersion'],
        capture_output=True,check=True,text=True,env=env)
    version=result.stdout.strip()
    require(version==APP_VERSION or version.startswith(APP_VERSION+'.'),'app-version-incompatible')


def _guard_check(manifest):
    from check_native_apply import check
    return check(manifest)


def apply_new_project(compiled_dir, request, journal_dir):
    """Separately authorized CREATE only. No force/overwrite/update mode exists.

    Request: capcut-new-project-apply/v1, storePath, rootIndexSHA256,
    name/projectId/timelineId, appExecutable/appExecutableSHA256,
    authorityEvidence bound ref, guardManifest bound ref. A real successful guard
    is required again immediately before any native-store mutation.
    """
    root=Path(compiled_dir).absolute(); request=read_json(request) if isinstance(request,(str,Path)) else copy.deepcopy(request)
    require(request.get('schema')=='capcut-new-project-apply/v1','new-project-request-schema')
    validate_compiled(root)
    manifest=read_json(root/'compiled-manifest.json')
    require(manifest.get('identityMode','CREATE_NEW')=='CREATE_NEW','revision-compile-cannot-create-project')
    require(request.get('name')==manifest['name'] and request.get('projectId')==manifest['projectId']
        and request.get('timelineId')==manifest['timelineId'],'apply-exact-project-binding-required')
    authority=read_json(_ref(request.get('authorityEvidence')))
    store=_unlinked(request.get('storePath',''),exists=False)
    require(store.is_dir(),'existing-capcut-store-required')
    index=store/'root_meta_info.json'; _unlinked(index)
    destination=store/_safe_name(request['name'])
    require(not destination.exists(),'new-project-name-collision')
    original=index.read_bytes(); before=_hash(request.get('rootIndexSHA256'))
    require(hashlib.sha256(original).hexdigest()==before,'root-index-baseline-drift')
    parsed=json.loads(original.decode('utf-8-sig'),object_pairs_hook=_pairs)
    rows=parsed.get('all_draft_store'); require(isinstance(rows,list),'index-shape-unsupported')
    for row in rows:
        require(isinstance(row,dict),'index-row-object-required')
        require(row.get('draft_name')!=manifest['name'] and row.get('draft_id')!=manifest['projectId']
            and row.get('draft_fold_path','').replace('\\','/').casefold()!=str(destination).replace('\\','/').casefold(),
            'new-project-index-collision')
    meta=read_json(root/'files/draft_meta_info.json')
    meta.update(draft_fold_path=str(destination).replace('\\','/'),draft_root_path=str(store).replace('\\','/'))
    payload={rel:(json_bytes(meta) if rel=='draft_meta_info.json' else (root/'files'/rel).read_bytes())
             for rel in manifest['files']}
    after,insertion=inserted_index(original,meta)
    guard_manifest=read_json(_ref(request.get('guardManifest')))
    native_ref=guard_manifest.get('native',{})
    require(_hash(native_ref.get('sha256'))==manifest['files']['draft_content.json']
        and Path(native_ref.get('path','')).resolve()==(root/'files/draft_content.json').resolve(),
        'guard-must-bind-exact-compiled-native')
    mode=guard_manifest.get('mode','FINAL_ACCEPTANCE')
    require(mode in ('REVIEW_DRAFT','FINAL_ACCEPTANCE'),'native-apply-mode-unsupported')
    require(authority.get('evidenceClass')=='REAL_OBSERVATION'
        and authority.get('authority')=='explicit-user-request'
        and isinstance(authority.get('userQuote'),str) and bool(authority['userQuote'].strip())
        and authority.get('nativeHash')==native_ref['sha256']
        and authority.get('destinationPath')==str(destination)
        and authority.get('projectId')==manifest['projectId']
        and authority.get('timelineId')==manifest['timelineId'], 'exact-native-create-authority-required')
    if mode=='REVIEW_DRAFT':
        require(request['authorityEvidence']==guard_manifest.get('reviewDraft',{}).get('authorityEvidence')
            and authority.get('claim')=='review-draft-native-apply'
            and authority.get('mode')=='REVIEW_DRAFT','review-draft-authority-binding')
        target=guard_manifest.get('reviewDraft',{}).get('destination',{})
        require(target.get('projectId')==manifest['projectId'] and target.get('timelineId')==manifest['timelineId']
            and target.get('operation')=='CREATE_SEPARATE_NEW_PROJECT' and target.get('overwriteExisting') is False
            and Path(target.get('path','')).resolve()==destination.resolve(),'review-draft-destination-mismatch')
    else:
        require(authority.get('claim')=='native-project-create','native-create-authority-claim')
    journal=_unlinked(Path(journal_dir).absolute(),exists=False)
    require(not journal.exists() and not journal.is_relative_to(store),'fresh-task-local-journal-required')
    journal.mkdir(parents=True)
    _exclusive_write(journal/'root_meta_info.before.bin',original)
    _exclusive_write(journal/'root_meta_info.candidate.bin',after)
    _exclusive_write(journal/'scope.json',json_bytes({'schema':'capcut-new-project-journal/v1',
        'destination':str(destination),'projectId':manifest['projectId'],'timelineId':manifest['timelineId'],
        'beforeIndexSHA256':before,'candidateIndexSHA256':hashlib.sha256(after).hexdigest(),
        'insertion':insertion,'payload':{k:hashlib.sha256(v).hexdigest() for k,v in payload.items()},
        'nativeAcceptance':'PENDING'}))
    _assert_app(request); _assert_editor_closed()
    require(index.read_bytes()==original and not destination.exists(),'store-drift-before-guard')
    # Last content prerequisite immediately before mutation; this call is never
    # replaced by a stored result or a caller-supplied boolean.
    guard_result=_guard_check(guard_manifest)
    accepted=guard_result.get('status')=='PREREQUISITES_CONSISTENT' or (
        mode=='REVIEW_DRAFT' and guard_result.get('status')=='PROVISIONAL_NOT_ACCEPTED'
        and guard_result.get('stage')=='REVIEW_DRAFT' and guard_result.get('finalAcceptance') is False)
    require(accepted and guard_result.get('passed') is True and not guard_result.get('errors')
            and guard_result.get('nativeHash')==native_ref['sha256'],
            'native-apply-guard-refused')
    _exclusive_write(journal/'guard-result.json',json_bytes(guard_result))
    _assert_editor_closed()
    require(index.read_bytes()==original and not destination.exists(),'store-drift-after-guard')
    index_written=False; temporary=index.with_name('root_meta_info.'+uuid.uuid4().hex+'.owned.tmp')
    try:
        destination.mkdir()
        for rel,data in payload.items():
            path=destination/rel; path.parent.mkdir(parents=True,exist_ok=True); _exclusive_write(path,data)
        _assert_editor_closed()
        require(index.read_bytes()==original,'store-drift-during-project-copy')
        _exclusive_write(temporary,after)
        _assert_editor_closed(); require(index.read_bytes()==original,'store-drift-before-index-write')
        os.replace(temporary,index); index_written=True
        require(index.read_bytes()==after,'root-index-after-readback-mismatch')
        for rel,data in payload.items(): require((destination/rel).read_bytes()==data,'native-child-readback-mismatch')
        # Exact insertion inverse proves each old row/header/numeric token stayed
        # byte-for-byte unchanged, even for >2**53 numeric and decimal values.
        at=insertion['insertionOffset']; size=insertion['insertedByteCount']
        require(index.read_bytes()[:at]+index.read_bytes()[at+size:]==original,'old-index-bytes-changed')
        report={'status':'NEW_NATIVE_PROJECT_REGISTERED_FILE_READBACK_PASS',
            'destination':str(destination),'insertion':insertion,'oldRootBytesPreserved':True,
            'guardStatus':guard_result['status'],'finalAcceptance':False,
            'nativePlaybackEditSaveReopen':'PENDING','captionFitAndGlyphs':'PENDING'}
        _exclusive_write(journal/'final-readback.json',json_bytes(report)); return report
    except BaseException as exc:
        restored=False; recovery='NO_SHARED_WRITE_OR_FOREIGN_CHANGE_HELD'
        try:
            # A replace can take effect then raise. Reconcile the actual bytes,
            # never a success flag, before any retry or conditional rollback.
            if index.read_bytes()==after:
                _assert_editor_closed()
                restore=index.with_name('root_meta_info.'+uuid.uuid4().hex+'.restore.tmp')
                _exclusive_write(restore,original)
                require(index.read_bytes()==after,'foreign-index-change-during-recovery')
                _assert_editor_closed(); os.replace(restore,index)
                restored=index.read_bytes()==original; recovery='OWNED_INDEX_RESTORED' if restored else 'RESTORE_READBACK_FAILED'
        except BaseException as recovery_error:
            recovery='RECOVERY_HELD: '+type(recovery_error).__name__+': '+str(recovery_error)
        failure={'status':'FAILED_APPLY_RECONCILIATION_REQUIRED','error':type(exc).__name__+': '+str(exc),
            'indexRestored':restored,'recovery':recovery,'ownedFolderRetained':str(destination),
            'temporaryRetained':str(temporary) if temporary.exists() else None,'foreignBytesNeverOverwritten':True,
            'nativeAcceptance':'PENDING'}
        try: _exclusive_write(journal/'failure.json',json_bytes(failure))
        except BaseException: pass
        raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    c=sub.add_parser('compile'); c.add_argument('--plan',required=True); c.add_argument('--output',required=True)
    v=sub.add_parser('validate'); v.add_argument('--compiled',required=True)
    s=sub.add_parser('inspect'); s.add_argument('--native',required=True); s.add_argument('--compiled',required=True)
    a=sub.add_parser('apply-new'); a.add_argument('--compiled',required=True); a.add_argument('--request',required=True); a.add_argument('--journal',required=True)
    args=parser.parse_args(argv)
    if args.command=='compile': result=compile_plan(args.plan,args.output)
    elif args.command=='validate': result=validate_compiled(args.compiled)
    elif args.command=='inspect':
        root=Path(args.compiled); result=inspect_native(args.native,root/'plan.json',root/'compiled-manifest.json')
    else: result=apply_new_project(args.compiled,args.request,args.journal)
    print(json.dumps(result,ensure_ascii=True,indent=2)); return 0


if __name__=='__main__':
    raise SystemExit(main())
