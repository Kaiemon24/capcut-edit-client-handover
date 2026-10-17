"""Cooperative, call-scoped full-file verification; no persistent hash cache.

The first read hashes the actual complete file and checks path/handle identity
before and after. Reuse inside the same session requires unchanged file identity,
size, mtime_ns and ctime_ns. Every path is checked again on session exit. This is
a cooperative snapshot, not authentication against malicious metadata restoration.
The native guard must create its own fresh session immediately before a write.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import os
from pathlib import Path
import stat

_CURRENT = ContextVar('capcut_source_hash_session', default=None)
_BLOCK_BYTES = 1024 * 1024


class SourceHashDrift(ValueError):
    """A source changed after this invocation's verification began."""


def _path(path):
    result = Path(os.path.abspath(os.fspath(path)))
    if result.is_symlink():
        raise SourceHashDrift('source-hash-linked-file-refused')
    return result


def _identity(value):
    if not stat.S_ISREG(value.st_mode):
        raise SourceHashDrift('source-hash-regular-file-required')
    return (value.st_dev, value.st_ino, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _snapshot(path):
    return _identity(path.stat())


def _read_verified(path):
    before = _snapshot(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        opened = _identity(os.fstat(stream.fileno()))
        # Windows Python may report creation time through stat().st_ctime_ns
        # and change time through fstat().st_ctime_ns. Compare each API's ctime
        # against its own snapshot; shared identity/size/mtime must still match.
        if opened[:-1] != before[:-1]:
            raise SourceHashDrift('source-hash-identity-changed-before-read')
        for block in iter(lambda: stream.read(_BLOCK_BYTES), b''):
            h.update(block)
        if _identity(os.fstat(stream.fileno())) != opened:
            raise SourceHashDrift('source-hash-file-changed-during-read')
    if _snapshot(path) != before:
        raise SourceHashDrift('source-hash-path-changed-during-read')
    return before, 'sha256:' + h.hexdigest()


class _Session:
    def __init__(self):
        self._files = {}
        self._failed = False
        self._closed = False

    def digest(self, path):
        if self._closed or self._failed:
            raise SourceHashDrift('source-hash-session-closed-or-failed')
        path = _path(path)
        key = os.path.normcase(str(path))
        try:
            if key in self._files:
                original, expected, hashed = self._files[key]
                if _snapshot(original) != expected:
                    raise SourceHashDrift('source-hash-file-drift-within-call')
                return hashed
            identity, hashed = _read_verified(path)
            self._files[key] = (path, identity, hashed)
            return hashed
        except (OSError, ValueError):
            self._failed = True
            raise

    def close(self):
        try:
            if self._failed:
                raise SourceHashDrift('source-hash-session-had-verification-failure')
            for path, expected, _ in self._files.values():
                if _snapshot(path) != expected:
                    raise SourceHashDrift('source-hash-file-drift-at-call-exit')
        finally:
            self._closed = True
            self._files.clear()


@contextmanager
def fresh_hash_session():
    """Always create a NEW isolated verification context; restore outer on exit."""
    session = _Session()
    token = _CURRENT.set(session)
    failed = False
    try:
        yield session
    except BaseException:
        failed = True
        raise
    finally:
        try:
            # Preserve the original error while still checking/clearing on exit.
            if failed:
                try:
                    session.close()
                except (OSError, ValueError):
                    pass
            else:
                session.close()
        finally:
            _CURRENT.reset(token)


@contextmanager
def verified_hash_session():
    """Join a preparation context, or create a fresh one for a standalone call.

    Do not use this entry for the native apply guard: its independent check must
    use fresh_hash_session even when called by an already verified preparation.
    """
    current = _CURRENT.get()
    if current is not None:
        yield current
    else:
        with fresh_hash_session() as session:
            yield session


def digest(path):
    """Return sha256:hex from current context, or one new complete verification."""
    current = _CURRENT.get()
    if current is not None:
        return current.digest(path)
    with fresh_hash_session() as session:
        return session.digest(path)


hash_file = digest
