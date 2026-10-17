"""Render one explicit original into a task-local derived picture/PCM master.

No ASR, semantic selection, audio filtering, native-project writer or acceptance
is provided. Inputs remain original; extending the derivative cannot recover
discarded footage. FFmpeg/FFprobe are explicit existing external dependencies.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import wave

from source_hash_session import digest, fresh_hash_session


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _integer(value, name, minimum=0):
    _need(type(value) is int and value >= minimum, name)
    return value


def _rate(value, name):
    _need(not isinstance(value, (bool, float)), name)
    try:
        result = Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError):
        raise ValueError(name) from None
    _need(result > 0, name)
    return result


def _sha(value):
    _need(isinstance(value, str), 'sha256-required')
    value = value.removeprefix('sha256:')
    _need(len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'sha256-required')
    return 'sha256:' + value


def _file(value):
    path = Path(value).absolute()
    _need(path.is_file() and not path.is_symlink(), 'regular-unlinked-input-required')
    return path.resolve(strict=True)


def _fresh_output(value):
    path = Path(value).absolute()
    _need(not path.exists(), 'fresh-output-directory-required')
    for parent in [path] + list(path.parents):
        _need(not parent.is_symlink() and not (hasattr(parent, 'is_junction') and parent.is_junction()),
              'linked-output-refused')
    parts = tuple(p.casefold() for p in path.parts)
    _need('com.lveditor.draft' not in parts, 'native-store-output-refused')
    _need(not any(parts[i:i+2] == ('.codex', 'skills') for i in range(len(parts)-1)),
          'instruction-store-output-refused')
    return path.resolve()


def _put(path, value):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def _ref(path, stage):
    started = time.perf_counter()
    hashed = digest(path)
    stat = path.stat()
    return {'path': str(path), 'sha256': hashed, 'bytes': stat.st_size,
            'statIdentity': [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns],
            'verification': stage, 'elapsedSeconds': time.perf_counter() - started}


def _json_call(argv):
    started = time.perf_counter()
    result = subprocess.run(argv, capture_output=True, check=False)
    _need(result.returncode == 0, 'probe-failed:' + result.stderr.decode('utf-8', 'replace')[-1000:])
    return json.loads(result.stdout), {'argv': argv, 'exitCode': result.returncode,
                                      'elapsedSeconds': time.perf_counter() - started}


def _sample(tick):
    return (tick * 48000 + 500000) // 1000000


def _frame_field(row, generic, legacy, rate):
    if generic in row:
        if legacy in row:
            _need(rate == 30 and row[generic] == row[legacy], 'conflicting-frame-alias')
        return _integer(row[generic], generic)
    _need(rate == 30 and legacy in row, 'explicit-normalized-source-frame-required')
    return _integer(row[legacy], legacy)


def _plan_geometry(plan, rate):
    _need(isinstance(plan, dict) and plan.get('schema') == 'capcut-audio-assembly-plan/v1', 'master-plan-schema')
    bindings = plan.get('pcmBindings')
    _need(isinstance(bindings, list) and len(bindings) == 1, 'one-original-source-binding-required')
    binding = bindings[0]
    _need(isinstance(binding, dict), 'original-source-binding-object-required')
    _need(isinstance(binding.get('sourceId'), str) and bool(binding['sourceId'].strip()), 'source-id-required')
    source = _file(binding.get('originalSourcePath', ''))
    expected_source = _sha(binding.get('originalSourceSHA256'))
    pieces = plan.get('mainPieces')
    _need(isinstance(pieces, list) and bool(pieces), 'nonempty-main-pieces-required')
    seen = set()
    cursor = 0
    previous_source_end = 0
    rows = []
    for piece in pieces:
        _need(isinstance(piece, dict), 'main-piece-object-required')
        ident = piece.get('id')
        _need(isinstance(ident, str) and ident.strip() and ident not in seen, 'unique-piece-id-required')
        seen.add(ident)
        _need(piece.get('sourceId') == binding['sourceId'], 'piece-source-binding')
        _need(type(piece.get('volume')) in (int, float) and piece['volume'] == 1,
              'unchanged-gain-required')
        _need(type(piece.get('speed', 1)) in (int, float) and piece.get('speed', 1) == 1,
              'normal-speed-required')
        a = _frame_field(piece, 'sourceFrameIn', 'sourceFrameIn30', rate)
        z = _frame_field(piece, 'sourceFrameOut', 'sourceFrameOut30', rate)
        _need(a < z, 'nonempty-frame-window-required')
        _need(a >= previous_source_end, 'overlapping-or-reordered-source-windows-unsupported')
        previous_source_end = z
        source_a = _integer(piece.get('sourceInTicks'), 'source-in-ticks')
        source_z = _integer(piece.get('sourceOutTicks'), 'source-out-ticks', 1)
        target_a = _integer(piece.get('targetInTicks'), 'target-in-ticks')
        _need(source_a < source_z, 'bounded-source-ticks-required')
        frame_a, frame_z = Fraction(a * 48000, rate), Fraction(z * 48000, rate)
        output_a = Fraction(cursor * 48000, rate)
        output_z = Fraction((cursor + z - a) * 48000, rate)
        _need(all(v.denominator == 1 for v in (frame_a, frame_z, output_a, output_z)),
              'frame-sample-map-unrepresentable-no-resampling')
        _need((_sample(source_a), _sample(source_z)) == (int(frame_a), int(frame_z)),
              'source-frame-sample-mismatch')
        _need(_sample(target_a) == output_a, 'noncontiguous-target-sample-map')
        if 'targetOutTicks' in piece:
            _need(_sample(_integer(piece['targetOutTicks'], 'target-out-ticks', 1)) == output_z,
                  'target-out-sample-mismatch')
        rows.append({'pieceId': ident, 'originalSourceId': binding['sourceId'],
                     'originalSourceInTicks': source_a, 'originalSourceOutTicks': source_z,
                     'originalPlanTargetInTicks': target_a,
                     'normalizedSourceFrameIn': a, 'normalizedSourceFrameOut': z,
                     'derivedFrameIn': cursor, 'derivedFrameOut': cursor + z - a,
                     'originalSourceSampleIn': int(frame_a), 'originalSourceSampleOut': int(frame_z),
                     'acceptedAudioSampleIn': int(output_a), 'acceptedAudioSampleOut': int(output_z),
                     'sourceInTickQuantizationSamples': str(Fraction(source_a * 48000, 1000000) - frame_a),
                     'sourceOutTickQuantizationSamples': str(Fraction(source_z * 48000, 1000000) - frame_z),
                     'targetInTickQuantizationSamples': str(Fraction(target_a * 48000, 1000000) - output_a)})
        cursor += z - a
    return source, expected_source, rows, cursor


def _source_geometry(probe, source_rate, rate, rows):
    pictures = [s for s in probe.get('streams', []) if s.get('codec_type') == 'video'
                and s.get('disposition', {}).get('attached_pic', 0) != 1]
    _need(len(pictures) == 1, 'one-picture-stream-required')
    video = pictures[0]
    _need(_rate(video.get('avg_frame_rate'), 'source-probe-fps') == source_rate
          and _rate(video.get('r_frame_rate'), 'source-probe-fixed-fps') == source_rate,
          'declared-source-fps-mismatch-or-vfr-unsupported')
    _need(Fraction(video.get('start_time', '1')) == 0, 'nonzero-source-start-clock-unsupported')
    _need(video.get('sample_aspect_ratio') in ('1:1', '1/1'), 'anamorphic-source-unsupported')
    width = _integer(video.get('width'), 'source-width', 1)
    height = _integer(video.get('height'), 'source-height', 1)
    rotations = [s['rotation'] for s in video.get('side_data_list', []) if 'rotation' in s]
    _need(len(rotations) <= 1, 'ambiguous-source-rotation')
    rotation = rotations[0] if rotations else 0
    _need(type(rotation) in (int, float) and rotation in (-270, -180, -90, 0, 90, 180, 270),
          'unsupported-source-rotation')
    duration = Fraction(_integer(video.get('duration_ts'), 'source-duration-ts', 1)) * Fraction(video['time_base'])
    _need(all(Fraction(row['normalizedSourceFrameOut'], rate) <= duration for row in rows),
          'source-window-out-of-bounds')
    return video, {'visibleWidth': width, 'visibleHeight': height, 'rotationDegrees': rotation,
                   'displayWidth': height if rotation % 180 else width,
                   'displayHeight': width if rotation % 180 else height,
                   'durationRational': str(duration), 'sourceFPS': str(source_rate)}


def _render(plan_path, audio, accepted_hash, out, ffmpeg, ffprobe, rate, source_rate, canvas, threads):
    started = time.perf_counter()
    pre_plan = _ref(plan_path, 'FRESH_FULL_READ')
    plan = json.loads(plan_path.read_text(encoding='utf-8-sig'))
    source, expected_source, rows, frames = _plan_geometry(plan, rate)
    _need(not source.samefile(audio), 'source-and-accepted-audio-alias')
    with wave.open(str(audio), 'rb') as stream:
        _need((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype())
              == (2, 2, 48000, 'NONE'), 'pcm16-stereo-48000-required-no-resample')
        samples = stream.getnframes()
    _need(Fraction(frames * 48000, rate) == samples, 'accepted-pcm-length-does-not-match-plan')
    tracked = {'originalSource': source, 'acceptedAudio': audio, 'plan': plan_path,
               'ffmpeg': ffmpeg, 'ffprobe': ffprobe, 'producer': Path(__file__).resolve()}
    before = {'originalSource': _ref(source, 'FRESH_FULL_READ'),
              'acceptedAudio': _ref(audio, 'FRESH_FULL_READ'), 'plan': pre_plan}
    _need(before['originalSource']['sha256'] == expected_source, 'original-source-hash-mismatch')
    _need(before['acceptedAudio']['sha256'] == accepted_hash, 'accepted-audio-hash-mismatch')
    before.update({name: _ref(tracked[name], 'FRESH_FULL_READ') for name in ('ffmpeg', 'ffprobe', 'producer')})
    probe, source_probe_call = _json_call([str(ffprobe), '-v', 'error', '-show_streams', '-of', 'json', str(source)])
    video, geometry = _source_geometry(probe, source_rate, rate, rows)
    versions = {}
    for name, tool in [('ffmpeg', ffmpeg), ('ffprobe', ffprobe)]:
        command = [str(tool), '-version']
        result = subprocess.run(command, capture_output=True, check=False)
        _need(result.returncode == 0, 'tool-version-call-failed')
        versions[name] = {'argv': command, 'text': result.stdout.decode('utf-8', 'replace').splitlines()}
    out.mkdir(parents=True)
    _put(out / 'plan.json', plan)
    _put(out / 'source-probe.json', probe)
    labels = ''.join(f'[s{i}]' for i in range(len(rows)))
    width, height = canvas
    fps_text = f'{rate.numerator}/{rate.denominator}'
    graph = (f"[0:{video['index']}]fps=fps={fps_text}:start_time=0:round=near,"
             f'scale=w={width}:h={height}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,'
             f'pad=w={width}:h={height}:x=(ow-iw)/2:y=(oh-ih)/2,setsar=1,split={len(rows)}{labels};\n')
    for i, row in enumerate(rows):
        graph += (f"[s{i}]trim=start_frame={row['normalizedSourceFrameIn']}:end_frame={row['normalizedSourceFrameOut']},"
                  f'setpts=N*{rate.denominator}/({rate.numerator}*TB)[v{i}];\n')
    graph += ''.join(f'[v{i}]' for i in range(len(rows))) + f'concat=n={len(rows)}:v=1:a=0[vout]\n'
    filter_path = out / 'picture-filter.ffgraph'
    filter_path.write_text(graph, encoding='utf-8')
    movie = out / 'aroll-master.mov'
    command = [str(ffmpeg), '-hide_banner', '-nostdin', '-n', '-loglevel', 'warning', '-threads', str(threads),
               '-autorotate', '-i', str(source), '-i', str(audio), '-filter_complex_threads', str(threads),
               '-filter_complex_script', str(filter_path), '-map', '[vout]', '-map', '1:a:0',
               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-pix_fmt', 'yuv420p',
               '-threads:v', str(threads), '-r', fps_text, '-fps_mode', 'cfr', '-c:a', 'copy',
               '-map_metadata', '-1', '-metadata:s:v:0', 'rotate=0',
               '-video_track_timescale', str(rate.numerator), '-movie_timescale', str(rate.numerator),
               '-movflags', '+faststart',
               '-progress', str(out / 'render-progress.txt'), str(movie)]
    _put(out / 'render-request.json', {'schema': 'capcut-aroll-master-request/v1', 'before': before,
         'acceptedAudioHash': accepted_hash, 'toolVersions': versions, 'sourceGeometry': geometry,
         'fps': fps_text, 'canvas': {'width': width, 'height': height, 'fitMode': 'contain'},
         'originalSourceCutCrosswalk': rows, 'sourceProbeCall': source_probe_call, 'renderArgv': command,
         'audioMethod': 'a:copy; no resample, normalization, gain, fade, pad or stretch',
         'derivedNotOriginal': True, 'nativeWrites': 0})
    render_start = time.perf_counter()
    with (out / 'render-stdout.log').open('xb') as stdout, (out / 'render-stderr.log').open('xb') as stderr:
        result = subprocess.run(command, stdout=stdout, stderr=stderr, check=False)
    render_seconds = time.perf_counter() - render_start
    _put(out / 'render-command-result.json', {'argv': command, 'exitCode': result.returncode,
                                             'elapsedSeconds': render_seconds})
    _need(result.returncode == 0, 'render-failed-preserve-output-and-logs-no-overwrite')
    output_probe, output_probe_call = _json_call([str(ffprobe), '-v', 'error', '-count_frames',
                                                 '-show_streams', '-of', 'json', str(movie)])
    _put(out / 'derived-probe.json', output_probe)
    streams = output_probe['streams']
    pictures = [s for s in streams if s.get('codec_type') == 'video']
    sounds = [s for s in streams if s.get('codec_type') == 'audio']
    _need(len(pictures) == len(sounds) == 1, 'output-stream-count-mismatch')
    picture, sound = pictures[0], sounds[0]
    _need((picture['codec_name'], picture['width'], picture['height'], int(picture['nb_read_frames']))
          == ('h264', width, height, frames) and Fraction(picture['avg_frame_rate']) == rate,
          'output-picture-geometry-or-frame-count-mismatch')
    _need(all(s.get('rotation', 0) == 0 for s in picture.get('side_data_list', [])), 'output-rotation-not-cleared')
    _need((sound['codec_name'], sound['sample_rate'], sound['channels'], sound['bits_per_sample'])
          == ('pcm_s16le', '48000', 2, 16), 'output-audio-format-mismatch')
    _need(Fraction(picture['duration_ts']) * Fraction(picture['time_base']) == Fraction(frames, rate)
          and Fraction(sound['duration_ts']) * Fraction(sound['time_base']) == Fraction(samples, 48000),
          'output-exact-rational-duration-mismatch')
    decode_command = [str(ffmpeg), '-hide_banner', '-v', 'error', '-nostdin', '-threads', str(threads),
                      '-i', str(movie), '-map', '0:a:0', '-vn', '-c:a', 'pcm_s16le', '-f', 's16le', 'pipe:1']
    decode_start = time.perf_counter()
    decoded = subprocess.run(decode_command, capture_output=True, check=False)
    _need(decoded.returncode == 0, 'output-audio-decode-failed')
    with wave.open(str(audio), 'rb') as stream:
        expected = stream.readframes(stream.getnframes())
    _need(decoded.stdout == expected, 'decoded-pcm-not-sample-exact')
    pcm_proof = {'argv': decode_command, 'exitCode': 0, 'everyPCMByteEqual': True, 'sampleFrames': samples,
                 'dataSHA256': 'sha256:' + hashlib.sha256(decoded.stdout).hexdigest(),
                 'elapsedSeconds': time.perf_counter() - decode_start}
    _put(out / 'decoded-audio-readback.json', pcm_proof)
    sample_frames = sorted({0, frames // 2, frames - 1})
    sample_command = [str(ffmpeg), '-hide_banner', '-v', 'error', '-nostdin', '-n', '-threads', str(threads),
                      '-i', str(movie), '-map', '0:v:0', '-vf',
                      "select='" + '+'.join(f'eq(n,{n})' for n in sample_frames) + "'", '-fps_mode', 'vfr',
                      '-frames:v', str(len(sample_frames)), '-threads:v', str(threads), str(out / 'sample-%02d.png')]
    sample_start = time.perf_counter()
    sample_result = subprocess.run(sample_command, capture_output=True, check=False)
    sample_seconds = time.perf_counter() - sample_start
    _need(sample_result.returncode == 0, 'sample-picture-export-failed')
    images = [{'frame': n, 'image': _ref(out / f'sample-{i:02d}.png', 'FRESH_FULL_READ'),
               'visualAcceptance': 'PENDING_ACTUAL_PIXEL_REVIEW'} for i, n in enumerate(sample_frames, 1)]
    after = {name: _ref(path, 'SAME_INVOCATION_VERIFIED_REUSE') for name, path in tracked.items()}
    _need(all(before[name]['sha256'] == after[name]['sha256'] and before[name]['statIdentity'] == after[name]['statIdentity']
              for name in tracked), 'input-or-tool-drift')
    return {'schema': 'capcut-aroll-master-receipt/v1', 'status': 'PASS_MEDIA_MECHANICS_NOT_NATIVE_ACCEPTANCE',
            'derivedMaster': _ref(movie, 'FRESH_FULL_READ'), 'sourceBefore': before, 'sourceAfter': after,
            'allInputsUnchanged': True, 'hashSession': 'NEW_CALL_SCOPED_FULL_FIRST_READ_POST_STAT_AND_EXIT_CHECK',
            'video': {'frames': frames, 'fps': fps_text, 'width': width, 'height': height,
                      'codedWidth': picture.get('coded_width'), 'codedHeight': picture.get('coded_height'),
                      'rotationDegrees': 0, 'durationRationalSeconds': str(Fraction(frames, rate))},
            'audio': pcm_proof, 'originalSourceCutCrosswalk': rows, 'outputProbeCall': output_probe_call,
            'sampleExport': {'argv': sample_command, 'exitCode': 0, 'elapsedSeconds': sample_seconds, 'images': images},
            'renderSeconds': render_seconds, 'totalSeconds': time.perf_counter() - started,
            'derivedNotOriginal': True, 'nativeWrites': 0, 'hearingOrCaptionAcceptance': False,
            'limits': ['Original source history and discarded handles remain outside this derivative.',
                       'Sample images require actual visual inspection; native import/edit/save-reopen remains separate.',
                       'Caller-supplied accepted audio identity is not independently authenticated user acceptance.',
                       'Cooperative file snapshot cannot authenticate malicious metadata restoration.']}


def render_master(plan_path, audio_path, accepted_audio_sha256, output_dir, ffmpeg_path, ffprobe_path,
                  *, fps, source_fps, canvas, threads=4, fit_mode='contain'):
    """Render fresh task output. Explicit frame/sample maps only, PCM16 stereo48k.

    fps is the normalized picture clock; source_fps must match the actual fixed
    original video. Audio is never resampled to make an unrepresentable map fit.
    """
    rate, source_rate = _rate(fps, 'explicit-fps-required'), _rate(source_fps, 'explicit-source-fps-required')
    _need(rate.numerator <= 2147483647, 'normalized-fps-exceeds-supported-mov-timescale')
    _need(fit_mode == 'contain', 'only-contain-fit-supported')
    _need(type(threads) is int and threads in (4, 8), 'threads-must-be-4-or-8')
    _need(isinstance(canvas, (list, tuple)) and len(canvas) == 2, 'explicit-canvas-required')
    width, height = (_integer(v, 'positive-even-canvas-required', 2) for v in canvas)
    _need(width % 2 == height % 2 == 0, 'positive-even-canvas-required')
    out = _fresh_output(output_dir)
    plan_path, audio, ffmpeg, ffprobe = map(_file, (plan_path, audio_path, ffmpeg_path, ffprobe_path))
    accepted_hash = _sha(accepted_audio_sha256)
    with fresh_hash_session():
        receipt = _render(plan_path, audio, accepted_hash, out, ffmpeg, ffprobe,
                          rate, source_rate, (width, height), threads)
    # Closing the fresh session must pass before emitting a successful receipt.
    _put(out / 'render-receipt.json', receipt)
    return receipt


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('plan', 'audio', 'output-dir', 'ffmpeg', 'ffprobe'):
        parser.add_argument('--' + field, required=True, type=Path)
    for field in ('audio-sha256', 'fps', 'source-fps'):
        parser.add_argument('--' + field, required=True)
    parser.add_argument('--canvas-width', required=True, type=int)
    parser.add_argument('--canvas-height', required=True, type=int)
    parser.add_argument('--threads', type=int, choices=(4, 8), default=4)
    args = parser.parse_args()
    result = render_master(args.plan, args.audio, args.audio_sha256, args.output_dir,
                           args.ffmpeg, args.ffprobe, fps=args.fps, source_fps=args.source_fps,
                           canvas=(args.canvas_width, args.canvas_height), threads=args.threads)
    print(json.dumps({'status': result['status'], 'derivedMaster': result['derivedMaster'],
                      'receipt': str(args.output_dir / 'render-receipt.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
