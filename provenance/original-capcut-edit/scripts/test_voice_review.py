"""Real sample arithmetic and refusal tests; no listening or native appearance proof."""
from pathlib import Path
import array
import hashlib
import json
import tempfile
import unittest
import wave
from prepare_voice_review import prepare_review, samples


class ReviewGainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def source(self, values, channels=1, width=2):
        path = self.root / 'source.wav'
        with wave.open(str(path), 'wb') as f:
            f.setnchannels(channels)
            f.setframerate(16000)
            f.setsampwidth(width)
            f.writeframes(array.array('h', values).tobytes() if width == 2 else bytes(values))
        return path

    def test_exact_gain_clock_source_and_receipt(self):
        src = self.source([-16000, -13, 0, 24, 16383])
        before = src.read_bytes(); output = self.root / 'review.wav'
        receipt = prepare_review(src, output)
        with wave.open(str(output), 'rb') as f:
            self.assertEqual(list(samples(f.readframes(f.getnframes()))), [-32000, -26, 0, 48, 32766])
            self.assertEqual((f.getframerate(), f.getnframes()), (16000, 5))
        self.assertEqual(src.read_bytes(), before)
        self.assertEqual(receipt['linearGain'], 2.0)
        self.assertEqual(receipt['actualListeningAcceptance'], 'PENDING')
        self.assertFalse(receipt['mainProjectAudioTouched'])
        self.assertEqual(json.loads(output.with_suffix('.review.json').read_text())['outputSha256'],
                         'sha256:' + hashlib.sha256(output.read_bytes()).hexdigest())

    def test_stereo_channels_and_sample_order_preserved(self):
        receipt = prepare_review(self.source([-2, 5, 9, -8], channels=2), self.root / 'stereo.wav')
        self.assertEqual((receipt['channels'], receipt['frames']), (2, 2))

    def test_positive_negative_clipping_both_refuse_before_writes(self):
        for value in [16384, -16385]:
            src = self.source([value]);output = self.root / 'held.wav'
            with self.assertRaisesRegex(ValueError, 'clip'):
                prepare_review(src, output)
            self.assertFalse(output.exists());self.assertFalse(output.with_suffix('.review.json').exists())

    def test_existing_output_never_overwritten(self):
        src = self.source([10]);output = self.root / 'existing.wav';output.write_bytes(b'foreign')
        with self.assertRaisesRegex(ValueError, 'existing'):
            prepare_review(src, output)
        self.assertEqual(output.read_bytes(), b'foreign')

    def test_wrong_sample_width_has_no_output(self):
        src = self.source([127, 128], width=1);output = self.root / 'held.wav'
        with self.assertRaisesRegex(ValueError, 'PCM16'):
            prepare_review(src, output)
        self.assertFalse(output.exists())

    def test_relative_destination_refused(self):
        with self.assertRaisesRegex(ValueError, 'absolute'):
            prepare_review(self.source([10]), Path('review.wav'))


if __name__ == '__main__':
    unittest.main()
