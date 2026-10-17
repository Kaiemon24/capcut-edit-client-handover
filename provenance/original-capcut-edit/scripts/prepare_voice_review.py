"""Create a separate PCM16 listening copy at exactly 2x amplitude; no hearing/app claims."""
from pathlib import Path
import argparse
import array
import hashlib
import json
import math
import sys
import wave


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def checked_path(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('Explicit absolute path required')
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ValueError('Linked input/output path is not supported')
    return path


def samples(raw):
    values = array.array('h')
    values.frombytes(raw)
    if sys.byteorder != 'little':
        values.byteswap()
    return values


def prepare_review(source, output):
    source, output = checked_path(source), checked_path(output)
    receipt_path = output.with_suffix('.review.json')
    checked_path(receipt_path)
    if output.suffix.lower() != '.wav' or not output.parent.is_dir():
        raise ValueError('New WAV in an existing explicit task directory required')
    if output.exists() or receipt_path.exists():
        raise ValueError('Refuse an existing output or receipt; reconcile it first')
    before_hash = digest(source)
    with wave.open(str(source), 'rb') as reader:
        params = reader.getparams()
        if params.sampwidth != 2 or params.comptype != 'NONE':
            raise ValueError('Decoded uncompressed PCM16 WAV required')
        raw = reader.readframes(params.nframes)
    original = samples(raw)
    if not original or len(original) != params.nframes * params.nchannels:
        raise ValueError('Nonempty complete PCM samples required')
    if min(original) * 2 < -32768 or max(original) * 2 > 32767:
        raise ValueError('2x gain would clip; hold export without clamping or attenuation')
    doubled = array.array('h', (int(value) * 2 for value in original))
    if sys.byteorder != 'little':
        doubled.byteswap()
    expected = doubled.tobytes()
    if digest(source) != before_hash:
        raise ValueError('Source changed before export')
    with output.open('xb') as handle:
        with wave.open(handle, 'wb') as writer:
            writer.setparams(params)
            writer.writeframes(expected)
    with wave.open(str(output), 'rb') as reader:
        output_params = reader.getparams()
        output_raw = reader.readframes(output_params.nframes)
    if output_params != params or output_raw != expected or digest(source) != before_hash:
        raise ValueError('Readback failed; preserve files for reconciliation')
    receipt = {
        'schemaVersion': 'capcut-listening-review/v1',
        'status': 'PREPARED_ONLY',
        'sourcePath': str(source), 'outputPath': str(output),
        'sourceSha256': before_hash, 'outputSha256': digest(output),
        'linearGain': 2.0, 'gainDb': 20 * math.log10(2),
        'sourcePeakAbsolute': max(abs(v) for v in original),
        'outputPeakAbsolute': max(abs(v * 2) for v in original),
        'clippedSampleCount': 0, 'exactDoubledSamples': True,
        'channels': params.nchannels, 'sampleRate': params.framerate,
        'frames': params.nframes, 'durationSeconds': params.nframes / params.framerate,
        'sourceUnchanged': True, 'clockAndDurationUnchanged': True,
        'mainProjectAudioTouched': False,
        'actualListeningAcceptance': 'PENDING', 'nativeAcceptance': 'NOT_TESTED',
    }
    with receipt_path.open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = prepare_review(args.input, args.output)
        print(json.dumps({'status': receipt['status'], 'linearGain': 2.0,
                          'exactDoubledSamples': True, 'durationSeconds': receipt['durationSeconds']}))
        return 0
    except (ValueError, OSError, wave.Error) as error:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
