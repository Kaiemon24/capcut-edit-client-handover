"""Validate a hash-bound derived A-roll and compose its original sample history.

This verifies media/clock/PCM relationships, not phonemes, semantics, consent or
native appearance. Original ASR/removal clocks are never renamed as master clocks.
"""
import hashlib
import json
import wave
from fractions import Fraction
from pathlib import Path
from source_hash_session import digest


def _need(ok, message):
    if not ok:
        raise ValueError('source-derivation-' + message)


def _ref(ref):
    _need(isinstance(ref, dict), 'reference')
    p = Path(ref.get('path', ''))
    _need(p.is_absolute() and p.is_file() and not p.is_symlink(), 'file')
    _need(not any(x.is_symlink() or (hasattr(x, 'is_junction') and x.is_junction()) for x in p.parents), 'linked-file')
    _need(digest(p) == ref.get('sha256'), 'hash-drift')
    return p


def _json(ref):
    return json.loads(_ref(ref).read_text(encoding='utf-8-sig'))


def _int(value):
    return type(value) is int


def _sample(tick, rate):
    return (tick * rate + 500000) // 1000000


def _tick(sample, rate):
    return sample * 1000000 // rate


def _pcm(ref):
    p = _ref(ref)
    with wave.open(str(p), 'rb') as f:
        _need(f.getsampwidth() == 2 and f.getcomptype() == 'NONE', 'pcm16')
        return (f.getframerate(), f.getnchannels(), f.getnframes()), f.readframes(f.getnframes())


def _render_row(actual, generic):
    _need(isinstance(actual, dict), 'render-crosswalk-row')
    if not generic:
        return actual
    return {**actual,
        'normalizedSourceFrameIn30': actual.get('normalizedSourceFrameIn'),
        'normalizedSourceFrameOut30': actual.get('normalizedSourceFrameOut'),
        'derivedFrameIn30': actual.get('derivedFrameIn'), 'derivedFrameOut30': actual.get('derivedFrameOut'),
        'originalAudioSourceSampleIn': actual.get('originalSourceSampleIn'),
        'originalAudioSourceSampleOut': actual.get('originalSourceSampleOut')}


def _master_copy(master, *, verify_files=False):
    """Optional same-byte relocation; preserve the original render identity.

    This record verifies a copy, never a new render or native relink outcome.
    Both original and copy must remain available for actual verification.
    """
    ref = master.get('copyProvenance')
    if ref is None:
        return None
    record = _json(ref)
    _need(record.get('schema') == 'capcut-task-byte-identical-media-copy/v1'
          and record.get('status') == 'BYTE_IDENTICAL_COPY_VERIFIED_NATIVE_RELINK_PENDING'
          and record.get('sourceDeletedOrModified') is False, 'copy-provenance-schema')
    old, new, rendered = record.get('original', {}), record.get('copy', {}), master.get('file', {})
    _need(isinstance(old, dict) and isinstance(new, dict) and isinstance(rendered, dict), 'copy-provenance-files')
    _need(all(old.get(k) == rendered.get(k) for k in ('path', 'sha256'))
          and new.get('sha256') == old.get('sha256'), 'copy-provenance-identity')
    paths = [Path(row.get('path', '')) for row in (old, new)]
    _need(all(p.is_absolute() for p in paths) and paths[0] != paths[1], 'copy-distinct-absolute-paths')
    _need(_int(old.get('size')) and old['size'] > 0 and _int(new.get('size'))
          and old['size'] == new['size'], 'copy-provenance-size')
    if verify_files:
        actual = [_ref({'path': row['path'], 'sha256': row['sha256']}) for row in (old, new)]
        _need(all(p.stat().st_size == row['size'] for p, row in zip(actual, (old, new))), 'copy-actual-size')
    return {'copyProvenance': ref, 'renderedMaster': {k: old[k] for k in ('path', 'sha256', 'size')},
            'currentMaster': {k: new[k] for k in ('path', 'sha256', 'size')},
            'status': 'BYTE_IDENTICAL_COPY_STRUCTURAL_NATIVE_RELINK_NOT_CERTIFIED'}


def _small_contract(record):
    """Hash small evidence and reject protocol/clock errors before source reads.

    All eligible paths still perform the independent actual file/PCM checks below.
    This preflight authenticates no hearing or user-message semantics.
    """
    original, master = record.get('originalSource', {}), record.get('master', {})
    _need(isinstance(original, dict) and isinstance(master, dict), 'source-records')
    rendered = _json(master.get('renderReceipt'))
    schema = rendered.get('schema')
    _need(schema in ('capcut-aroll-master-receipt/v1', 'ep7-derived-master-render-receipt/v1'),
          'unsupported-render-receipt-schema')
    generic = schema == 'capcut-aroll-master-receipt/v1'
    _master_copy(master)
    _need(rendered.get('status') == ('PASS_MEDIA_MECHANICS_NOT_NATIVE_ACCEPTANCE' if generic
          else 'PASS_MEDIA_MECHANICS_PENDING_VISUAL_NATIVE'), 'render-status')
    probe, decoded, decoder, original_probe = (_json(ref) for ref in
        (master.get('probe'), master.get('decodedPCMProof'), original.get('decoderEvidence'), original.get('probe')))
    fps = record.get('frameRate', {})
    n, den = fps.get('numerator'), fps.get('denominator')
    _need(_int(n) and _int(den) and min(n, den) > 0 and Fraction(n, den) == 30, 'render-crosswalk-supported-frame-rate')
    clock = decoder.get('clock', {})
    rate, channels, source_samples = (clock.get(k) for k in ('rate', 'channels', 'samples'))
    _need(all(_int(v) and v > 0 for v in (rate, channels, source_samples)) and rate * den % n == 0, 'decoder-clock-header')
    source_file, source_pcm = original.get('file', {}), original.get('pcm', {})
    original_rows = [s for s in original_probe.get('sources', []) if s.get('path') == source_file.get('path')
        and str(s.get('sha256', '')).removeprefix('sha256:') == str(source_file.get('sha256', '')).removeprefix('sha256:')]
    _need(len(original_rows) == 1 and original_rows[0].get('unchangedStatBeforeAfter') is True
          and bool(original_rows[0].get('probeCommand')), 'original-probe')
    source_duration = original_rows[0].get('actualDurationTicks', original_rows[0].get('durationTicks'))
    _need(_int(source_duration) and source_duration > 0, 'original-duration')
    _need(decoder.get('source') == source_file.get('path') and decoder.get('audio') == source_pcm.get('path')
          and str(decoder.get('sourceSha256', '')).removeprefix('sha256:') == str(source_file.get('sha256', '')).removeprefix('sha256:')
          and str(decoder.get('audioSha256', '')).removeprefix('sha256:') == str(source_pcm.get('sha256', '')).removeprefix('sha256:')
          and decoder.get('clockBasis') == 'ORIGINAL_SOURCE' and type(decoder.get('offset')) in (int, float)
          and decoder.get('offset') == 0 and decoder.get('gain') == 1, 'original-decoder-binding')
    for key in ('rawSourceWords', 'rawTranscript'):
        _need(str(_json(record[key]).get('sourceAudioSha256', '')).removeprefix('sha256:')
              == str(source_pcm.get('sha256', '')).removeprefix('sha256:'), 'raw-history-original-audio-binding')
    per_frame = rate * den // n
    frames = master.get('frameCount')
    _need(_int(frames) and frames > 0, 'frame-count')
    pictures = [s for s in probe.get('streams', []) if s.get('codec_type') == 'video']
    sounds = [s for s in probe.get('streams', []) if s.get('codec_type') == 'audio']
    _need(len(pictures) == len(sounds) == 1, 'master-streams')
    _need(int(pictures[0].get('nb_read_frames', pictures[0].get('nb_frames', -1))) == frames, 'frame-count')
    _need(Fraction(pictures[0]['avg_frame_rate']) == Fraction(n, den)
          and Fraction(pictures[0]['duration_ts']) * Fraction(pictures[0]['time_base']) == Fraction(frames * den, n), 'video-clock')
    _need(int(sounds[0].get('sample_rate', 0)) == rate and sounds[0].get('channels') == channels
          and sounds[0].get('codec_name') == 'pcm_s16le'
          and Fraction(sounds[0]['duration_ts']) * Fraction(sounds[0]['time_base']) == Fraction(frames * per_frame, rate), 'master-audio-clock')
    path = master.get('file', {}).get('path')
    call = rendered.get('outputProbeCall' if generic else 'probeCommand', {})
    _need(rendered.get('derivedNotOriginal') is True and rendered.get('allInputsUnchanged') is True
          and call.get('exitCode') == 0 and path in call.get('argv', []), 'actual-render-binding')
    _need(decoded.get('exitCode') == 0 and decoded.get('sampleFrames') == frames * per_frame
          and path in decoded.get('argv', []), 'master-decoded-pcm-proof')
    if generic:
        _need(rendered.get('audio') == decoded and decoded.get('everyPCMByteEqual') is True
              and isinstance(decoded.get('dataSHA256'), str), 'generic-render-and-decode-binding')
        before, after = rendered.get('sourceBefore', {}), rendered.get('sourceAfter', {})
        _need(bool(before) and set(before) == set(after)
              and all(isinstance(before[k].get('statIdentity'), list) and len(before[k]['statIdentity']) == 5
                      and all(_int(v) for v in before[k]['statIdentity']) for k in before)
              and all(all(before[k].get(f) == after[k].get(f) for f in ('path', 'sha256', 'statIdentity')) for k in before),
              'generic-render-input-drift')
        for key, expected in (('originalSource', source_file), ('acceptedAudio', master['acceptedPCM'])):
            _need(all(before.get(key, {}).get(f) == expected[f] for f in ('path', 'sha256')), 'generic-render-input-binding')
    else:
        _need(decoded.get('sampleExact') is True and decoded.get('rate') == rate and decoded.get('channels') == channels,
              'master-decoded-pcm-proof')
    rows, actual_rows = record.get('crosswalk'), rendered.get('originalSourceCutCrosswalk')
    _need(isinstance(rows, list) and bool(rows) and isinstance(actual_rows, list) and len(rows) == len(actual_rows), 'render-crosswalk-coverage')
    cursor, previous, seen = 0, 0, set()
    for row, actual in zip(rows, actual_rows):
        actual = _render_row(actual, generic)
        _need(isinstance(row, dict), 'crosswalk-row')
        ident = row.get('pieceId');vals = [row.get(k) for k in ('originalFrameIn', 'originalFrameOut', 'masterFrameIn', 'masterFrameOut')]
        _need(isinstance(ident, str) and bool(ident) and ident not in seen and all(_int(v) for v in vals), 'crosswalk-row')
        seen.add(ident);oi, oo, mi, mo = vals
        _need(0 <= oi < oo and 0 <= mi < mo and mi == cursor and oo - oi == mo - mi, 'crosswalk-gap-or-duration')
        _need(oi >= previous and oo * per_frame <= source_samples
              and Fraction(oo * den * 1000000, n) <= source_duration, 'original-overlap-or-bounds')
        expected = {'pieceId':ident, 'originalSourceId':original.get('id'),
            'normalizedSourceFrameIn30':oi, 'normalizedSourceFrameOut30':oo, 'derivedFrameIn30':mi, 'derivedFrameOut30':mo,
            'acceptedAudioSampleIn':mi*per_frame, 'acceptedAudioSampleOut':mo*per_frame,
            'originalAudioSourceSampleIn':oi*per_frame, 'originalAudioSourceSampleOut':oo*per_frame}
        _need(all(actual.get(k) == v for k, v in expected.items()) and (generic or actual.get('normalSpeed') is True), 'render-crosswalk-row-drift')
        cursor, previous = mo, oo
    _need(cursor == frames, 'master-crosswalk-coverage')
    return rendered


def validate_source_derivation(derivation_ref, native_ref, audio_ref, execution_ref, source_map, policy):
    """Return actual composed original-source pieces for historical intersections.

    Only one original A-roll and one derived master are supported. The current
    normal-speed native map must be a contiguous exact sample slice of the master.
    """
    record = _json(derivation_ref)
    _need(record.get('schema') == 'capcut-source-derivation/v1'
          and record.get('evidenceClass') == 'REAL_OBSERVATION'
          and record.get('status') == 'PASS_STRUCTURAL_NOT_HEARD', 'schema')
    for key in ('rawSourceWords', 'rawTranscript', 'sourceEditObservations'):
        _need(record.get(key) == policy.get(key), 'original-history-reference')
        _json(record[key])
    original, master = record.get('originalSource', {}), record.get('master', {})
    rendered = _small_contract(record)
    oid, mid = original.get('id'), master.get('sourceId')
    _need(isinstance(oid, str) and oid and isinstance(mid, str) and mid and oid != mid, 'source-identities')
    original_path, master_path = _ref(original.get('file')), _ref(master.get('file'))
    copy_readback = _master_copy(master, verify_files=True)
    current_master_path = Path(copy_readback['currentMaster']['path']) if copy_readback else master_path
    _need(original_path != master_path, 'master-is-original')
    original_probe = _json(original.get('probe'))
    originals = [s for s in original_probe.get('sources', []) if s.get('path') == str(original_path)
                 and str(s.get('sha256', '')).removeprefix('sha256:') == original['file']['sha256'].removeprefix('sha256:')]
    _need(len(originals) == 1 and originals[0].get('unchangedStatBeforeAfter') is True
          and originals[0].get('probeCommand'), 'original-probe')
    duration = originals[0].get('actualDurationTicks', originals[0].get('durationTicks'))
    _need(_int(duration) and duration > 0, 'original-duration')
    fmt, original_data = _pcm(original.get('pcm'))
    rate, channels, original_samples = fmt
    _need(rate > 0 and channels > 0, 'pcm-format')
    for key in ('rawSourceWords', 'rawTranscript'):
        history = _json(record[key])
        _need(str(history.get('sourceAudioSha256', '')).removeprefix('sha256:')
              == original['pcm']['sha256'].removeprefix('sha256:'), 'raw-history-original-audio-binding')
    decoder = _json(original.get('decoderEvidence'))
    _need(str(decoder.get('sourceSha256', '')).removeprefix('sha256:') == original['file']['sha256'].removeprefix('sha256:')
          and str(decoder.get('audioSha256', '')).removeprefix('sha256:') == original['pcm']['sha256'].removeprefix('sha256:')
          and decoder.get('clockBasis') == 'ORIGINAL_SOURCE' and type(decoder.get('offset')) in (int, float)
          and decoder['offset'] == 0 and decoder.get('gain') == 1
          and decoder.get('source') == str(original_path) and decoder.get('audio') == str(_ref(original['pcm']))
          and decoder.get('clock', {}).get('rate') == rate and decoder.get('clock', {}).get('channels') == channels
          and decoder.get('clock', {}).get('samples') == original_samples, 'original-decoder-binding')
    fps = record.get('frameRate', {})
    n, den = fps.get('numerator'), fps.get('denominator')
    _need(_int(n) and _int(den) and min(n, den) > 0 and rate * den % n == 0, 'integral-frame-samples')
    # The supported render receipt currently labels its frame windows explicitly
    # as 30 fps. Do not reinterpret those fields at another rate.
    _need(Fraction(n, den) == 30, 'render-crosswalk-supported-frame-rate')
    samples_per_frame = rate * den // n
    probe, pcm_proof = (_json(master.get(k)) for k in ('probe', 'decodedPCMProof'))
    generic = rendered.get('schema') == 'capcut-aroll-master-receipt/v1'
    if generic:
        _need(rendered.get('status') == 'PASS_MEDIA_MECHANICS_NOT_NATIVE_ACCEPTANCE'
              and rendered.get('audio') == pcm_proof, 'generic-render-and-decode-binding')
        before, after = rendered.get('sourceBefore', {}), rendered.get('sourceAfter', {})
        _need(bool(before) and set(before) == set(after)
              and all(isinstance(before[k].get('statIdentity'), list) and len(before[k]['statIdentity']) == 5
                      and all(_int(v) for v in before[k]['statIdentity']) for k in before)
              and all(all(before[k].get(f) == after[k].get(f) for f in ('path', 'sha256', 'statIdentity')) for k in before),
              'generic-render-input-drift')
        for key, expected in (('originalSource', original['file']), ('acceptedAudio', master['acceptedPCM'])):
            _need(all(before.get(key, {}).get(f) == expected[f] for f in ('path', 'sha256')), 'generic-render-input-binding')
        probe_call = rendered.get('outputProbeCall', {})
    else:
        _need(rendered.get('schema') == 'ep7-derived-master-render-receipt/v1'
              and rendered.get('status') == 'PASS_MEDIA_MECHANICS_PENDING_VISUAL_NATIVE', 'legacy-render-status')
        probe_call = rendered.get('probeCommand', {})
    streams = probe.get('streams', [])
    video = [s for s in streams if s.get('codec_type') == 'video']
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    _need(len(video) == len(audio) == 1, 'master-streams')
    frames = master.get('frameCount')
    _need(_int(frames) and frames > 0 and int(video[0].get('nb_read_frames', video[0].get('nb_frames', -1))) == frames, 'frame-count')
    _need(Fraction(video[0]['avg_frame_rate']) == Fraction(n, den)
          and Fraction(video[0]['duration_ts']) * Fraction(video[0]['time_base']) == Fraction(frames * den, n), 'video-clock')
    total = frames * samples_per_frame
    _need(int(audio[0].get('sample_rate', 0)) == rate and audio[0].get('channels') == channels
          and audio[0].get('codec_name') == 'pcm_s16le'
          and Fraction(audio[0]['duration_ts']) * Fraction(audio[0]['time_base']) == Fraction(total, rate), 'master-audio-clock')
    _need(rendered.get('derivedNotOriginal') is True and rendered.get('allInputsUnchanged') is True
          and rendered.get('derivedMaster', {}).get('path') == str(master_path)
          and rendered.get('derivedMaster', {}).get('sha256') == master['file']['sha256']
          and probe_call.get('exitCode') == 0
          and str(master_path) in probe_call.get('argv', []), 'actual-render-binding')
    bfmt, bdata = _pcm(master.get('acceptedPCM'))
    _need(bfmt == (rate, channels, total), 'accepted-master-pcm-format')
    bscope = _json(master.get('acceptanceEvidence'))
    _acceptance(bscope, master['acceptedPCM'])
    data_hash = 'sha256:' + hashlib.sha256(bdata).hexdigest()
    if generic:
        _need(pcm_proof.get('exitCode') == 0 and pcm_proof.get('everyPCMByteEqual') is True
              and pcm_proof.get('sampleFrames') == total and pcm_proof.get('dataSHA256') == data_hash
              and str(master_path) in pcm_proof.get('argv', []), 'generic-master-decoded-pcm-proof')
    else:
        _need(pcm_proof.get('exitCode') == 0 and pcm_proof.get('sampleExact') is True
              and pcm_proof.get('sampleFrames') == total and pcm_proof.get('rate') == rate
              and pcm_proof.get('channels') == channels
              and pcm_proof.get('decodedPCMDataSHA256') == data_hash
              and pcm_proof.get('acceptedBPCMDataSHA256') == data_hash
              and str(master_path) in pcm_proof.get('argv', []), 'master-decoded-pcm-proof')
    rows = record.get('crosswalk')
    _need(isinstance(rows, list) and bool(rows), 'crosswalk')
    rendered_rows = rendered.get('originalSourceCutCrosswalk', [])
    _need(len(rendered_rows) == len(rows), 'render-crosswalk-coverage')
    cursor, previous_original_end, seen = 0, 0, set()
    validated = []
    bytes_per_frame = channels * 2
    for row, actual in zip(rows, rendered_rows):
        actual = _render_row(actual, generic)
        ident = row.get('pieceId')
        vals = [row.get(k) for k in ('originalFrameIn', 'originalFrameOut', 'masterFrameIn', 'masterFrameOut')]
        _need(ident and ident not in seen and all(_int(v) for v in vals), 'crosswalk-row')
        seen.add(ident)
        oi, oo, mi, mo = vals
        _need(0 <= oi < oo and 0 <= mi < mo and mi == cursor and oo - oi == mo - mi, 'crosswalk-gap-or-duration')
        os, oe, ms, me = [v * samples_per_frame for v in (oi, oo, mi, mo)]
        _need(os >= previous_original_end and oe <= original_samples and me <= total
              and Fraction(oo * den * 1000000, n) <= duration, 'original-overlap-or-bounds')
        _need(actual.get('pieceId') == ident and actual.get('originalSourceId') == oid
              and actual.get('normalizedSourceFrameIn30') == oi and actual.get('normalizedSourceFrameOut30') == oo
              and actual.get('derivedFrameIn30') == mi and actual.get('derivedFrameOut30') == mo
              and actual.get('acceptedAudioSampleIn') == ms and actual.get('acceptedAudioSampleOut') == me
              and actual.get('originalAudioSourceSampleIn') == os and actual.get('originalAudioSourceSampleOut') == oe
              and (generic or actual.get('normalSpeed') is True),
              'render-crosswalk-row-drift')
        _need(original_data[os * bytes_per_frame:oe * bytes_per_frame] == bdata[ms * bytes_per_frame:me * bytes_per_frame], 'original-to-master-pcm')
        validated.append({'pieceId': ident, 'sourceId': oid, 'originalSampleStart': os, 'originalSampleEnd': oe,
                          'masterSampleStart': ms, 'masterSampleEnd': me})
        cursor, previous_original_end = mo, oe
    _need(cursor == frames, 'master-crosswalk-coverage')
    current_audio = record.get('currentAudio', {})
    _need(current_audio.get('file') == audio_ref, 'current-audio-binding')
    cfmt, cdata = _pcm(audio_ref)
    ca, cb = current_audio.get('masterSampleStart'), current_audio.get('masterSampleEnd')
    _need(_int(ca) and _int(cb) and 0 <= ca < cb <= total and cfmt == (rate, channels, cb - ca), 'current-slice-bounds')
    _need(cdata == bdata[ca * bytes_per_frame:cb * bytes_per_frame], 'current-pcm-difference')
    cscope = _json(current_audio.get('acceptanceEvidence'))
    _acceptance(cscope, audio_ref)
    _need(cscope.get('priorAcceptedScope') == master['acceptanceEvidence'], 'current-acceptance-history')
    native, execution = _json(native_ref), _json(execution_ref)
    _need(execution.get('nativeHash') == native_ref['sha256'] and execution.get('audioHash') == audio_ref['sha256'], 'current-native-audio-binding')
    source = source_map.get(mid, {})
    material_id = source.get('materialId') if isinstance(source, dict) else source
    matches = [m for m in native.get('materials', {}).get('videos', []) if m.get('id') == material_id]
    _need(matches and all(m.get('path') == str(current_master_path) for m in matches), 'current-master-material')
    main_id = execution.get('captionPlan', {}).get('mainTrackId')
    tracks = [t for t in native.get('tracks', []) if t.get('id') == main_id and t.get('type') == 'video']
    _need(len(tracks) == 1, 'current-main-track')
    pieces = sorted(tracks[0].get('segments', []), key=lambda p: p.get('target_timerange', {}).get('start', -1))
    _need(pieces, 'current-main-empty')
    master_cursor, output_cursor, composed = ca, 0, []
    for piece in pieces:
        src, dst = piece.get('source_timerange', {}), piece.get('target_timerange', {})
        ticks = [src.get('start'), src.get('duration'), dst.get('start'), dst.get('duration')]
        _need(all(_int(v) for v in ticks) and min(src['duration'], dst['duration']) > 0
              and src['start'] >= 0 and dst['start'] >= 0 and src['duration'] == dst['duration']
              and piece.get('material_id') == material_id and piece.get('speed') == 1
              and piece.get('volume') == 1 and not piece.get('reverse') and not piece.get('is_reverse'), 'current-normal-source-window')
        a, b = _sample(src['start'], rate), _sample(src['start'] + src['duration'], rate)
        ta, tb = _sample(dst['start'], rate), _sample(dst['start'] + dst['duration'], rate)
        _need(a == master_cursor and ta == output_cursor and b - a == tb - ta and a < b <= cb, 'current-window-gap-duplicate-or-sample-phase')
        for row in validated:
            lo, hi = max(a, row['masterSampleStart']), min(b, row['masterSampleEnd'])
            if lo >= hi:
                continue
            os = row['originalSampleStart'] + lo - row['masterSampleStart']
            oe = os + hi - lo
            target = ta + lo - a
            composed.append({'nativePieceId': piece['id'], 'originalPieceId': row['pieceId'], 'sourceId': oid,
                             'sourceStartSample': os, 'sourceEndSample': oe,
                             'targetStartSample': target, 'targetEndSample': target + hi - lo,
                             'sourceStartTick': _tick(os, rate), 'sourceEndTick': _tick(oe, rate),
                             'targetStartTick': _tick(target, rate), 'targetEndTick': _tick(target + hi - lo, rate)})
        master_cursor, output_cursor = b, tb
    _need(master_cursor == cb and output_cursor == cfmt[2], 'current-main-coverage')
    _need(sum(p['sourceEndSample'] - p['sourceStartSample'] for p in composed) == cfmt[2], 'composed-original-coverage')
    result = {'schema': 'capcut-source-derivation-readback/v1', 'status': 'PASS_STRUCTURAL_NOT_HEARD',
            'sourceDerivation': derivation_ref, 'originalSourceId': oid, 'masterSourceId': mid,
            'originalSourcePath': str(original_path), 'originalSourceSHA256': original['file']['sha256'],
            'originalSourceDurationTicks': duration, 'masterMaterialId': material_id,
            'sampleRate': rate, 'channels': channels, 'currentSamples': cfmt[2],
            'masterSampleStart': ca, 'masterSampleEnd': cb, 'originalPieces': composed,
            'originalSourceProbe': original['probe'], 'originalPCM': original['pcm'],
            'currentNative': native_ref, 'currentAudio': audio_ref,
            'basis': 'EXACT_SAMPLE_COMPOSITION_WITH_HASH_BOUND_RENDER_AND_DECODE_PROOF',
            'doesNotCertify': ['Independent ASR', 'Heard phonemes/onsets', 'Every audible word', 'Native rendering or save-reopen']}
    if copy_readback:
        result['masterCopyReadback'] = copy_readback
    return result


def _acceptance(scope, audio_ref):
    _need(scope.get('schema') == 'capcut-current-audio-scope-observation/v1'
          and scope.get('evidenceClass') == 'REAL_OBSERVATION'
          and scope.get('basis') == 'USER_AUDIO_REVIEW' and scope.get('status') == 'ACCEPTED'
          and scope.get('audioGain1') == audio_ref
          and scope.get('unresolvedCurrentAudioFeedback') == [], 'accepted-audio-scope')
    reply = _json(scope.get('userReply'))
    _need(reply.get('evidenceClass') == 'REAL_OBSERVATION'
          and reply.get('source') == 'DIRECT_USER_MESSAGE'
          and isinstance(reply.get('message'), str) and bool(reply['message'].strip())
          and bool(reply.get('sourceRef')), 'direct-audio-reply')
