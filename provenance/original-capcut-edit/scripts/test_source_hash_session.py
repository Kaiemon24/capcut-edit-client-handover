"""Synthetic actual-file reads and drift checks; no native writes or media QA."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

from source_hash_session import (digest, fresh_hash_session, verified_hash_session,
                                 SourceHashDrift)

_READ_CAPTURE = None


def _audit(event, args):
    if event == 'open' and _READ_CAPTURE is not None:
        path, mode, _ = args
        if isinstance(path, (str, bytes, os.PathLike)):
            name = os.path.normcase(os.path.abspath(os.fsdecode(path)))
            if name in _READ_CAPTURE['paths'] and mode and 'r' in mode:
                _READ_CAPTURE['reads'].append(name)
                action = _READ_CAPTURE.pop('onRead', None)
                if action is not None:action()


sys.addaudithook(_audit)


class SourceHashSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'source.bin'
        self.path.write_bytes(b'actual synthetic source bytes'*1024)
        self.expected = 'sha256:'+hashlib.sha256(self.path.read_bytes()).hexdigest()

    def capture(self):
        global _READ_CAPTURE
        _READ_CAPTURE = {'paths':{os.path.normcase(str(self.path.absolute()))}, 'reads':[]}
        self.addCleanup(self.reset_capture)
        return _READ_CAPTURE['reads']

    def reset_capture(self):
        global _READ_CAPTURE
        _READ_CAPTURE = None

    def test_same_invocation_opens_actual_file_once_then_new_call_reads_fresh(self):
        reads = self.capture()
        with fresh_hash_session():
            self.assertEqual(digest(self.path), self.expected)
            self.assertEqual(digest(self.path), self.expected)
            with verified_hash_session():
                self.assertEqual(digest(self.path), self.expected)
        self.assertEqual(len(reads), 1)
        with fresh_hash_session():
            self.assertEqual(digest(self.path), self.expected)
        self.assertEqual(len(reads), 2)

    def test_standalone_digest_never_keeps_a_cache(self):
        reads = self.capture()
        self.assertEqual(digest(self.path), self.expected)
        self.assertEqual(digest(self.path), self.expected)
        self.assertEqual(len(reads), 2)

    def test_mutation_during_call_is_failure_not_replaced_snapshot(self):
        with self.assertRaises(SourceHashDrift):
            with fresh_hash_session():
                digest(self.path)
                self.path.write_bytes(b'changed')
                digest(self.path)
        self.assertNotEqual(digest(self.path), self.expected)

    def test_exit_detects_mutation_without_second_digest(self):
        with self.assertRaisesRegex(SourceHashDrift, 'at-call-exit'):
            with fresh_hash_session():
                digest(self.path)
                self.path.write_bytes(b'drift detected at close')

    def test_change_between_path_snapshot_and_open_is_refused(self):
        self.capture()
        _READ_CAPTURE['onRead'] = lambda:self.path.write_bytes(b'changed at read boundary')
        with self.assertRaisesRegex(SourceHashDrift, 'changed-before-read'):
            digest(self.path)

    def test_atomic_replacement_with_same_size_and_mtime_is_identity_drift(self):
        original = self.path.stat()
        with self.assertRaises(SourceHashDrift):
            with fresh_hash_session():
                digest(self.path)
                replacement = self.path.with_suffix('.replacement')
                replacement.write_bytes(b'x'*original.st_size)
                os.utime(replacement, ns=(original.st_atime_ns, original.st_mtime_ns))
                os.replace(replacement, self.path)
                digest(self.path)

    def test_fresh_nested_guard_reads_again_and_restores_outer_context(self):
        reads = self.capture()
        with fresh_hash_session():
            digest(self.path)
            with fresh_hash_session():
                digest(self.path)
                digest(self.path)
            digest(self.path)
        self.assertEqual(len(reads), 2)

    def test_error_clears_context_and_preserves_original_error(self):
        reads = self.capture()
        with self.assertRaisesRegex(RuntimeError, 'original error'):
            with fresh_hash_session():
                digest(self.path)
                raise RuntimeError('original error')
        digest(self.path)
        self.assertEqual(len(reads), 2)

    def test_failed_read_does_not_poison_later_invocation(self):
        absent = self.path.with_name('absent.bin')
        with self.assertRaises(FileNotFoundError):
            with fresh_hash_session():
                digest(absent)
        self.assertEqual(digest(self.path), self.expected)

    def test_closed_session_cannot_supply_verified_hash(self):
        with fresh_hash_session() as session:
            digest(self.path)
        with self.assertRaises(SourceHashDrift):
            session.digest(self.path)

    def test_concurrent_threads_have_separate_read_sessions(self):
        reads = self.capture(); barrier = threading.Barrier(2); results=[]; failures=[]
        def run():
            try:
                with fresh_hash_session():
                    barrier.wait(timeout=5)
                    results.append(digest(self.path))
                    results.append(digest(self.path))
            except BaseException as exc:
                failures.append(repr(exc))
        workers=[threading.Thread(target=run) for _ in range(2)]
        for worker in workers:worker.start()
        for worker in workers:worker.join(timeout=10)
        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertEqual(failures, [])
        self.assertEqual(results, [self.expected]*4)
        self.assertEqual(len(reads), 2)


if __name__ == '__main__':unittest.main()
