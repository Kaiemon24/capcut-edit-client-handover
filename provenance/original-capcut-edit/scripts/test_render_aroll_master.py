"""Tiny real FFmpeg roundtrip plus malformed source/frame/PCM refusals."""
import copy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

import render_aroll_master as render


def sha(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


class RenderMasterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
        if not ffmpeg or not ffprobe:
            raise unittest.SkipTest('Existing FFmpeg/FFprobe unavailable; no installation authorized')
        cls.ffmpeg, cls.ffprobe = Path(ffmpeg), Path(ffprobe)
        retained = os.environ.get('CAPCUT_RENDER_MASTER_TEST_DIR')
        if retained:
            cls.root = Path(retained)
            if cls.root.exists():
                raise ValueError('Fresh test evidence directory required')
            cls.root.mkdir(parents=True)
            cls.temp = None
        else:
            cls.temp = tempfile.TemporaryDirectory()
            cls.root = Path(cls.temp.name)
        cls.source_pcm = cls.root / 'original.wav'
        import wave
        cls.pcm = b''.join(struct.pack('<hh', (n * 71) % 10000 - 5000,
                                       (n * 113) % 14000 - 7000) for n in range(48000))
        with wave.open(str(cls.source_pcm), 'wb') as stream:
            stream.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            stream.writeframes(cls.pcm)
        base = cls.root / 'landscape-unrotated.mov'
        command = [str(cls.ffmpeg), '-hide_banner', '-v', 'error', '-nostdin', '-n', '-f', 'lavfi',
                   '-i', 'testsrc2=size=96x64:rate=30:duration=1', '-i', str(cls.source_pcm),
                   '-map', '0:v:0', '-map', '1:a:0', '-vf', 'setsar=1', '-c:v', 'libx264',
                   '-threads:v', '1', '-preset', 'ultrafast', '-crf', '18', '-c:a', 'copy', str(base)]
        subprocess.run(command, capture_output=True, check=True)
        cls.source = cls.root / 'original-rotated.mov'
        rotate = [str(cls.ffmpeg), '-hide_banner', '-v', 'error', '-nostdin', '-n',
                  '-display_rotation:v:0', '-90', '-noautorotate', '-i', str(base),
                  '-map', '0', '-c', 'copy', str(cls.source)]
        subprocess.run(rotate, capture_output=True, check=True)
        cls.audio = cls.root / 'accepted.wav'
        cls.edited_pcm = cls.pcm[2*1600*4:5*1600*4] + cls.pcm[10*1600*4:14*1600*4]
        with wave.open(str(cls.audio), 'wb') as stream:
            stream.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            stream.writeframes(cls.edited_pcm)
        cls.plan = {'schema': 'capcut-audio-assembly-plan/v1',
                    'pcmBindings': [{'sourceId': 'original', 'originalSourcePath': str(cls.source),
                                     'originalSourceSHA256': sha(cls.source)}],
                    'mainPieces': [
                        {'id': 'piece-a', 'sourceId': 'original', 'volume': 1,
                         'sourceFrameIn': 2, 'sourceFrameOut': 5,
                         'sourceInTicks': 2*1000000//30, 'sourceOutTicks': 5*1000000//30, 'targetInTicks': 0},
                        {'id': 'piece-b', 'sourceId': 'original', 'volume': 1,
                         'sourceFrameIn': 10, 'sourceFrameOut': 14,
                         'sourceInTicks': 10*1000000//30, 'sourceOutTicks': 14*1000000//30,
                         'targetInTicks': 3*1000000//30}]}
        (cls.root / 'fixture-commands.json').write_text(json.dumps({'generate': command, 'rotationRemux': rotate}, indent=2))

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, 'temp', None):
            cls.temp.cleanup()

    def setUp(self):
        self.case = self.root / self._testMethodName
        self.case.mkdir()
        self.plan_path = self.case / 'plan.json'

    def run_plan(self, plan=None, **changes):
        self.plan_path.write_text(json.dumps(self.plan if plan is None else plan), encoding='utf-8')
        args = dict(plan_path=self.plan_path, audio_path=self.audio, accepted_audio_sha256=sha(self.audio),
                    output_dir=self.case / 'out', ffmpeg_path=self.ffmpeg, ffprobe_path=self.ffprobe,
                    fps='30/1', source_fps='30/1', canvas=(64, 96), threads=4)
        args.update(changes)
        return render.render_master(**args)

    def refused(self, plan=None, match=None, **changes):
        source_before, audio_before = sha(self.source), sha(self.audio)
        with self.assertRaisesRegex(ValueError, match or '.'):
            self.run_plan(plan, **changes)
        self.assertFalse((self.case / 'out').exists())
        self.assertEqual((source_before, audio_before), (sha(self.source), sha(self.audio)))

    def test_actual_rotated_source_frame_pcm_roundtrip(self):
        result = self.run_plan()
        self.assertEqual(result['video']['frames'], 7)
        self.assertEqual((result['video']['width'], result['video']['height']), (64, 96))
        self.assertEqual(result['video']['rotationDegrees'], 0)
        self.assertEqual(result['audio']['sampleFrames'], 11200)
        self.assertTrue(result['audio']['everyPCMByteEqual'])
        self.assertEqual(result['audio']['dataSHA256'], 'sha256:' + hashlib.sha256(self.edited_pcm).hexdigest())
        self.assertEqual(len(result['originalSourceCutCrosswalk']), 2)
        self.assertEqual(len(result['sampleExport']['images']), 3)
        request = json.loads((self.case / 'out/render-request.json').read_text(encoding='utf-8'))
        self.assertEqual(request['sourceGeometry']['rotationDegrees'], -90)
        self.assertEqual((request['sourceGeometry']['displayWidth'], request['sourceGeometry']['displayHeight']), (64, 96))
        self.assertTrue(result['allInputsUnchanged'])
        self.assertFalse(result['hearingOrCaptionAcceptance'])
        self.assertEqual(result['nativeWrites'], 0)
        # Independent explicit transpose is a pixel reference for automatic
        # rotation and the first/last selected source frame, not just dimensions.
        pixel_checks = []
        for derived_frame, source_frame in [(0, 2), (6, 13)]:
            reference = [str(self.ffmpeg), '-hide_banner', '-v', 'error', '-nostdin', '-noautorotate',
                         '-i', str(self.source), '-vf', f'transpose=clock,select=eq(n\\,{source_frame})',
                         '-frames:v', '1', '-pix_fmt', 'rgb24', '-threads:v', '1', '-f', 'rawvideo', 'pipe:1']
            actual = [str(self.ffmpeg), '-hide_banner', '-v', 'error', '-nostdin',
                      '-i', result['derivedMaster']['path'], '-vf', f'select=eq(n\\,{derived_frame})',
                      '-frames:v', '1', '-pix_fmt', 'rgb24', '-threads:v', '1', '-f', 'rawvideo', 'pipe:1']
            expected_pixels = subprocess.run(reference, capture_output=True, check=True).stdout
            actual_pixels = subprocess.run(actual, capture_output=True, check=True).stdout
            self.assertEqual(len(actual_pixels), 64*96*3)
            self.assertEqual(len(actual_pixels), len(expected_pixels))
            error = sum(abs(a-b) for a, b in zip(expected_pixels, actual_pixels)) / len(actual_pixels)
            self.assertLess(error, 8, 'Rotation/frame reference differs beyond lossy H264 tolerance')
            pixel_checks.append({'derivedFrame': derived_frame, 'sourceFrame': source_frame,
                                 'explicitTransposeReferenceArgv': reference, 'actualArgv': actual,
                                 'meanAbsoluteRGBError': error, 'maximumAllowedMeanError': 8})
        (self.case / 'pixel-reference-checks.json').write_text(json.dumps(pixel_checks, indent=2))

    def test_wrong_schema(self):
        plan = copy.deepcopy(self.plan); plan['schema'] = 'unknown'
        self.refused(plan, 'master-plan-schema')

    def test_actual_cli_roundtrip(self):
        self.plan_path.write_text(json.dumps(self.plan), encoding='utf-8')
        command = [sys.executable, '-B', str(Path(render.__file__)), '--plan', str(self.plan_path),
                   '--audio', str(self.audio), '--audio-sha256', sha(self.audio),
                   '--output-dir', str(self.case / 'out'), '--ffmpeg', str(self.ffmpeg), '--ffprobe', str(self.ffprobe),
                   '--fps', '30/1', '--source-fps', '30/1', '--canvas-width', '64', '--canvas-height', '96']
        result = subprocess.run(command, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
        value = json.loads(result.stdout)
        self.assertEqual(value['status'], 'PASS_MEDIA_MECHANICS_NOT_NATIVE_ACCEPTANCE')
        receipt = json.loads((self.case / 'out/render-receipt.json').read_text(encoding='utf-8'))
        self.assertTrue(receipt['audio']['everyPCMByteEqual'])

    def test_actual_25fps_normalization_has_exact_movie_clock(self):
        import wave
        plan = copy.deepcopy(self.plan)
        cursor = 0
        pcm = b''
        for item in plan['mainPieces']:
            a, z = item['sourceFrameIn'], item['sourceFrameOut']
            item.update(sourceInTicks=a*1000000//25, sourceOutTicks=z*1000000//25,
                        targetInTicks=cursor*1000000//25)
            pcm += self.pcm[a*1920*4:z*1920*4]
            cursor += z-a
        audio = self.case / 'accepted25.wav'
        with wave.open(str(audio), 'wb') as stream:
            stream.setparams((2, 2, 48000, 0, 'NONE', 'not compressed')); stream.writeframes(pcm)
        result = self.run_plan(plan, fps='25/1', audio_path=audio, accepted_audio_sha256=sha(audio))
        self.assertEqual(result['video']['durationRationalSeconds'], '7/25')
        self.assertEqual(result['audio']['sampleFrames'], 13440)
        self.assertTrue(result['audio']['everyPCMByteEqual'])

    def test_empty_pieces(self):
        plan = copy.deepcopy(self.plan); plan['mainPieces'] = []
        self.refused(plan, 'nonempty-main')

    def test_malformed_binding_and_piece_objects(self):
        for field in ['pcmBindings', 'mainPieces']:
            with self.subTest(field=field):
                plan = copy.deepcopy(self.plan); plan[field] = [None]
                self.refused(plan, 'object-required')

    def test_legacy_30fps_frame_aliases_keep_exact_clock(self):
        plan = copy.deepcopy(self.plan)
        for piece in plan['mainPieces']:
            piece['sourceFrameIn30'] = piece.pop('sourceFrameIn')
            piece['sourceFrameOut30'] = piece.pop('sourceFrameOut')
        a = render._plan_geometry(self.plan, Fraction(30))
        b = render._plan_geometry(plan, Fraction(30))
        self.assertEqual(a, b)

    def test_multiple_original_bindings(self):
        plan = copy.deepcopy(self.plan); plan['pcmBindings'] *= 2
        self.refused(plan, 'one-original-source')

    def test_duplicate_piece_ids(self):
        plan = copy.deepcopy(self.plan); plan['mainPieces'][1]['id'] = 'piece-a'
        self.refused(plan, 'unique-piece-id')

    def test_source_frame_tick_alias_mismatch(self):
        plan = copy.deepcopy(self.plan); plan['mainPieces'][0]['sourceFrameIn30'] = 3
        self.refused(plan, 'conflicting-frame-alias')

    def test_source_frame_sample_mismatch(self):
        plan = copy.deepcopy(self.plan); plan['mainPieces'][0]['sourceInTicks'] += 1000
        self.refused(plan, 'source-frame-sample')

    def test_target_gap_or_overlap(self):
        plan = copy.deepcopy(self.plan); plan['mainPieces'][1]['targetInTicks'] += 1000
        self.refused(plan, 'noncontiguous-target')

    def test_source_window_out_of_actual_duration(self):
        plan = copy.deepcopy(self.plan)
        for item, a, z in zip(plan['mainPieces'], [32, 40], [35, 44]):
            item.update(sourceFrameIn=a, sourceFrameOut=z, sourceInTicks=a*1000000//30, sourceOutTicks=z*1000000//30)
        self.refused(plan, 'source-window-out-of-bounds')

    def test_source_windows_overlap(self):
        plan = copy.deepcopy(self.plan); p = plan['mainPieces'][1]
        p.update(sourceFrameIn=4, sourceFrameOut=8, sourceInTicks=4*1000000//30, sourceOutTicks=8*1000000//30)
        self.refused(plan, 'overlapping-or-reordered')

    def test_speed_or_gain_changes(self):
        for field, value in [('speed', 2), ('volume', 0), ('volume', True)]:
            with self.subTest(field=field, value=value):
                plan = copy.deepcopy(self.plan); plan['mainPieces'][0][field] = value
                self.refused(plan)

    def test_unrepresentable_frame_sample_clock(self):
        self.refused(match='unrepresentable', fps=Fraction(30000, 1001))

    def test_wrong_original_hash(self):
        plan = copy.deepcopy(self.plan); plan['pcmBindings'][0]['originalSourceSHA256'] = '0'*64
        self.refused(plan, 'original-source-hash')

    def test_wrong_accepted_hash(self):
        self.refused(match='accepted-audio-hash', accepted_audio_sha256='0'*64)

    def test_declared_source_fps_mismatch(self):
        self.refused(match='declared-source-fps', source_fps='25/1')

    def test_shape_and_mode_refusals(self):
        for settings in [dict(canvas=(63, 96)), dict(canvas=(0, 96)), dict(canvas=(64,)),
                         dict(fit_mode='crop'), dict(fps=0), dict(fps=True), dict(threads=True)]:
            with self.subTest(settings=settings):
                self.refused(**settings)

    def test_audio_source_alias_refused(self):
        self.refused(match='audio-alias', audio_path=self.source, accepted_audio_sha256=sha(self.source))

    def test_wrong_pcm_format_or_length(self):
        import wave
        mono = self.case / 'mono.wav'
        with wave.open(str(mono), 'wb') as stream:
            stream.setparams((1, 2, 48000, 0, 'NONE', 'not compressed')); stream.writeframes(b'\x00'*22400)
        self.refused(match='pcm16-stereo', audio_path=mono, accepted_audio_sha256=sha(mono))
        self.refused(match='pcm-length', audio_path=self.source_pcm, accepted_audio_sha256=sha(self.source_pcm))

    def test_output_collision_preserves_foreign_file(self):
        out = self.case / 'out'; out.mkdir(); marker = out / 'foreign'; marker.write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError, 'fresh-output'):
            self.run_plan()
        self.assertEqual(marker.read_bytes(), b'preserve')

    def test_native_and_instruction_output_casefold_denials(self):
        for relative in ['Com.LvEditor.Draft/new', '.Codex/Skills/new']:
            with self.subTest(relative=relative):
                self.refused(match='store-output', output_dir=self.case / relative)


if __name__ == '__main__':
    unittest.main()
