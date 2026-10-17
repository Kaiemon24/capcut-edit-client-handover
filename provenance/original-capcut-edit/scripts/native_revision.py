"""Exact, separately authorized revision of one already owned native project.

Never creates a project, edits the shared index, grants Teacher activation or
substitutes for current audio/native acceptance. Production calls use the real
producer validators, process checks and fresh pre-native guard. Tests mock those
external boundaries only in isolated synthetic stores.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import uuid

import native_timeline as n

OPERATION = 'READDRAFT_UPDATE_OWNED'
BASELINE_SCHEMA = 'capcut-owned-project-baseline/v1'
REQUEST_SCHEMA = 'capcut-owned-project-revision/v1'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _file(path):
    path = n._unlinked(Path(path), exists=True)
    n.require(path.stat().st_nlink == 1, 'revision-hardlinked-file-refused')
    return path


def _directory(path):
    path = n._unlinked(Path(path), exists=False)
    n.require(path.is_dir(), 'revision-existing-directory-required')
    return path


def _paths(tid):
    try:
        uuid.UUID(tid)
    except (ValueError, TypeError, AttributeError):
        raise n.PlanError('revision-timeline-uuid-required')
    return {'draft_content.json', 'template-2.tmp',
        f'Timelines/{tid}/draft_content.json', f'Timelines/{tid}/template-2.tmp',
        'draft_meta_info.json', 'Timelines/project.json', 'timeline_layout.json',
        'draft_virtual_store.json', 'key_value.json'}


def _safe_relative(rel, allowed):
    n.require(isinstance(rel, str) and rel in allowed and '\\' not in rel
        and not PurePosixPath(rel).is_absolute()
        and all(p not in ('', '.', '..') for p in rel.split('/')),
        'revision-payload-relative-path-refused')
    return rel


def _target(store, name):
    store = _directory(store)
    target = _directory(store / n._safe_name(name))
    n.require(target.parent == store, 'revision-target-outside-store')
    return store, target


def _identity(data, index, store, target, name, pid, tid):
    """Bind actual old metadata and index row, never a caller's owned flag."""
    for ident in (pid, tid):
        try:
            uuid.UUID(ident)
        except (ValueError, TypeError, AttributeError):
            raise n.PlanError('revision-project-timeline-uuid-required')
    decode = lambda b: json.loads(b.decode('utf-8-sig'), object_pairs_hook=n._pairs)
    meta = decode(data['draft_meta_info.json'])
    n.require(meta.get('draft_id') == pid and meta.get('draft_name') == name,
        'revision-old-metadata-identity-mismatch')
    norm = lambda p: os.path.normcase(os.path.abspath(p))
    n.require(norm(meta.get('draft_fold_path', '')) == norm(target)
        and norm(meta.get('draft_root_path', '')) == norm(store),
        'revision-old-metadata-path-mismatch')
    for rel in ('draft_content.json', 'template-2.tmp',
                f'Timelines/{tid}/draft_content.json', f'Timelines/{tid}/template-2.tmp'):
        draft = decode(data[rel])
        n.require(draft.get('id') == tid and draft.get('name') == name,
            'revision-old-native-identity-mismatch')
    project = decode(data['Timelines/project.json'])
    n.require(project.get('id') == tid and project.get('main_timeline_id') == tid
        and [r.get('id') for r in project.get('timelines', [])] == [tid],
        'revision-old-active-timeline-mismatch')
    layout = decode(data['timeline_layout.json'])
    n.require(layout.get('dockItems', [{}])[0].get('timelineIds') == [tid],
        'revision-old-layout-timeline-mismatch')
    rows = decode(index).get('all_draft_store')
    n.require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows),
        'revision-root-index-shape')
    matches = [r for r in rows if r.get('draft_id') == pid]
    n.require(len(matches) == 1 and matches[0].get('draft_name') == name
        and norm(matches[0].get('draft_fold_path', '')) == norm(target),
        'revision-root-index-project-identity-mismatch')
    n.require(len([r for r in rows if r.get('draft_name') == name]) == 1
        and len([r for r in rows if norm(r.get('draft_fold_path', '')) == norm(target)]) == 1,
        'revision-root-index-ambiguous-target')
    return meta


def _read_current(store, target, expected, index_sha, name, pid, tid):
    allowed = _paths(tid)
    n.require(isinstance(expected, dict) and set(expected) == allowed,
        'revision-exact-nine-before-hashes-required')
    index = _file(store / 'root_meta_info.json').read_bytes()
    n.require(_sha(index) == n._hash(index_sha), 'revision-root-index-drift')
    data = {}
    for rel in sorted(allowed):
        _safe_relative(rel, allowed)
        value = _file(target / rel).read_bytes()
        n.require(_sha(value) == n._hash(expected[rel]), 'revision-target-drift: ' + rel)
        data[rel] = value
    meta = _identity(data, index, store, target, name, pid, tid)
    # Re-read after the inventory, preventing a mixed baseline during observation.
    n.require(_file(store / 'root_meta_info.json').read_bytes() == index,
        'revision-root-index-drift-during-read')
    for rel, value in data.items():
        n.require(_file(target / rel).read_bytes() == value, 'revision-target-drift-during-read: ' + rel)
    return data, index, meta


def capture_baseline(store_path, name, output_dir):
    """Read-only native observation; copies exact bytes into a fresh task folder."""
    store, target = _target(store_path, name)
    meta = n.read_json(_file(target / 'draft_meta_info.json'))
    draft = n.read_json(_file(target / 'draft_content.json'))
    pid, tid = meta.get('draft_id'), draft.get('id')
    expected = {rel: _sha(_file(target / rel).read_bytes()) for rel in sorted(_paths(tid))}
    index_sha = _sha(_file(store / 'root_meta_info.json').read_bytes())
    data, index, _ = _read_current(store, target, expected, index_sha, name, pid, tid)
    out = n._unlinked(Path(output_dir).absolute(), exists=False)
    n.require(not out.exists() and not out.is_relative_to(store),
        'revision-fresh-task-baseline-required')
    n.require(not any((p / 'root_meta_info.json').exists() or p.name.casefold() == 'com.lveditor.draft'
        for p in (out, *out.parents)), 'revision-baseline-cannot-be-native-store')
    out.mkdir(parents=True)
    n._exclusive_write(out / 'root_meta_info.before.bin', index)
    refs = {}
    for rel, value in data.items():
        p = out / 'files' / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        n._exclusive_write(p, value)
        refs[rel] = {'path': str(p), 'sha256': 'sha256:' + _sha(value)}
    record = {'schema': BASELINE_SCHEMA, 'evidenceClass': 'REAL_OBSERVATION',
        'basis': 'SUPPORTED_FILE_READBACK_NOT_NATIVE_ACCEPTANCE',
        'storePath': str(store), 'destinationPath': str(target), 'name': name,
        'projectId': pid, 'timelineId': tid, 'expectedFiles': expected,
        'rootIndexSHA256': index_sha,
        'rootIndex': {'path': str(out / 'root_meta_info.before.bin'), 'sha256': 'sha256:' + index_sha},
        'files': refs, 'nativeAcceptance': 'PENDING'}
    # Capture is truthful only while all observed native bytes still match.
    _read_current(store, target, expected, index_sha, name, pid, tid)
    n._exclusive_write(out / 'baseline.json', n.json_bytes(record))
    return {'path': str(out / 'baseline.json'), 'sha256': 'sha256:' + _sha(n.json_bytes(record))}


def load_baseline(ref, *, current=False):
    record_path = _file(n._ref(ref))
    record = n.read_json(record_path)
    n.require(record.get('schema') == BASELINE_SCHEMA, 'revision-baseline-schema')
    store, target = Path(record['storePath']), Path(record['destinationPath'])
    n.require(store.is_absolute() and target == store / n._safe_name(record['name']),
        'revision-baseline-target-binding')
    allowed = _paths(record['timelineId'])
    n.require(set(record.get('files', {})) == allowed
        and set(record.get('expectedFiles', {})) == allowed, 'revision-baseline-nine-files')
    snapshot_paths = [record_path, Path(record['rootIndex']['path']),
        *[Path(r['path']) for r in record['files'].values()]]
    n.require(all(p.is_absolute() and not p.is_relative_to(store) for p in snapshot_paths),
        'revision-baseline-snapshots-must-be-task-local')
    data = {rel: _file(n._ref(record['files'][rel])).read_bytes() for rel in sorted(allowed)}
    n.require(all(_sha(data[rel]) == n._hash(record['expectedFiles'][rel]) for rel in allowed),
        'revision-baseline-before-hash-mismatch')
    index = _file(n._ref(record.get('rootIndex'))).read_bytes()
    n.require(_sha(index) == n._hash(record['rootIndexSHA256']), 'revision-baseline-index-hash')
    _identity(data, index, store, target, record['name'], record['projectId'], record['timelineId'])
    if current:
        _target(store, record['name'])
        _read_current(store, target, record['expectedFiles'], record['rootIndexSHA256'],
            record['name'], record['projectId'], record['timelineId'])
    return record


def compile_identity(ref, name):
    baseline = load_baseline(ref, current=True)
    n.require(baseline['name'] == name, 'revision-compile-name-mismatch')
    return baseline['projectId'], baseline['timelineId']


def _setup(compiled_dir, request):
    root = n._unlinked(Path(compiled_dir).absolute(), exists=False)
    request = n.read_json(request) if isinstance(request, (str, Path)) else copy.deepcopy(request)
    n.require(request.get('schema') == REQUEST_SCHEMA and request.get('operation') == OPERATION,
        'revision-request-schema-or-operation')
    n.validate_compiled(root)
    manifest, plan = n.read_json(root / 'compiled-manifest.json'), n.read_json(root / 'plan.json')
    n.require(manifest.get('identityMode') == 'OWNED_REVISION', 'revision-bound-compile-required')
    baseline_ref = plan['project'].get('revisionIdentity')
    baseline = load_baseline(baseline_ref, current=True)
    for key in ('name', 'projectId', 'timelineId'):
        n.require(request.get(key) == manifest.get(key) == baseline.get(key), 'revision-exact-' + key)
    store, target = _target(request.get('storePath', ''), request['name'])
    n.require(str(store) == baseline['storePath'] and str(target) == baseline['destinationPath'],
        'revision-exact-target-path')
    n.require(request.get('expectedFiles') == baseline['expectedFiles']
        and n._hash(request.get('rootIndexSHA256')) == n._hash(baseline['rootIndexSHA256']),
        'revision-request-before-baseline-mismatch')
    before, index, meta = _read_current(store, target, request['expectedFiles'],
        request['rootIndexSHA256'], request['name'], request['projectId'], request['timelineId'])
    allowed = _paths(manifest['timelineId'])
    actual = {p.relative_to(root / 'files').as_posix() for p in (root / 'files').rglob('*') if p.is_file()}
    n.require(actual == allowed and set(manifest['files']) == allowed,
        'revision-unexpected-compiled-payload')
    payload = {rel: _file(root / 'files' / rel).read_bytes() for rel in sorted(allowed)}
    compiled_meta = n.read_json(root / 'files/draft_meta_info.json')
    revised_meta = copy.deepcopy(meta)
    for key in ('tm_duration', 'tm_draft_modified', 'draft_materials', 'draft_timeline_materials_size_'):
        n.require(key in compiled_meta, 'revision-compiled-metadata-field-missing')
        revised_meta[key] = compiled_meta[key]
    payload['draft_meta_info.json'] = n.json_bytes(revised_meta)
    guard = n.read_json(n._ref(request.get('guardManifest')))
    native_ref = guard.get('native', {})
    n.require(Path(native_ref.get('path', '')).absolute() == root / 'files/draft_content.json'
        and n._hash(native_ref.get('sha256')) == manifest['files']['draft_content.json'],
        'revision-guard-exact-compiled-native')
    n.require(guard.get('mode') == 'REVIEW_DRAFT', 'revision-explicit-review-mode-required')
    authority = n.read_json(n._ref(request.get('authorityEvidence')))
    expected_authority = {'claim': 'review-draft-native-update-owned', 'mode': 'REVIEW_DRAFT',
        'operation': OPERATION, 'nativeHash': native_ref['sha256'],
        'audioHash': guard.get('audio', {}).get('sha256'), 'destinationPath': str(target),
        'name': request['name'], 'projectId': request['projectId'], 'timelineId': request['timelineId'],
        'rootIndexSHA256': request['rootIndexSHA256'], 'expectedFiles': request['expectedFiles']}
    n.require(authority.get('evidenceClass') == 'REAL_OBSERVATION'
        and authority.get('authority') == 'explicit-user-request'
        and isinstance(authority.get('userQuote'), str) and bool(authority['userQuote'].strip())
        and all(authority.get(k) == v for k, v in expected_authority.items()),
        'revision-exact-update-authority-required')
    destination = guard.get('reviewDraft', {}).get('destination', {})
    n.require(request['authorityEvidence'] == guard.get('reviewDraft', {}).get('authorityEvidence')
        and destination.get('operation') == OPERATION
        and destination.get('path') == str(target)
        and destination.get('projectId') == request['projectId']
        and destination.get('timelineId') == request['timelineId']
        and destination.get('name') == request['name']
        and destination.get('overwriteExisting') is True
        and destination.get('revisionBaseline') == baseline_ref,
        'revision-guard-destination-binding')
    n._assert_app(request)
    n._assert_editor_closed()
    return {'root': root, 'request': request, 'manifest': manifest, 'plan': plan,
        'store': store, 'target': target, 'before': before, 'index': index,
        'payload': payload, 'guard': guard, 'baselineRef': baseline_ref}


def _guard(state):
    result = n._guard_check(state['guard'])  # Real public checker starts a fresh hash session.
    n.require(result.get('passed') is True and result.get('errors') == []
        and result.get('status') == 'PROVISIONAL_NOT_ACCEPTED'
        and result.get('stage') == 'REVIEW_DRAFT' and result.get('finalAcceptance') is False
        and result.get('nativeHash') == state['guard']['native']['sha256'],
        'revision-fresh-guard-refused')
    return result


def _unchanged(state, current):
    _directory(state['target'])
    n.require(_file(state['store'] / 'root_meta_info.json').read_bytes() == state['index'],
        'revision-shared-index-changed')
    for rel, value in current.items():
        n.require(_file(state['target'] / rel).read_bytes() == value,
            'revision-target-changed-before-write: ' + rel)


def preflight(compiled_dir, request):
    state = _setup(compiled_dir, request)
    result = _guard(state)
    _unchanged(state, state['before'])
    return {'status': 'OWNED_REVISION_PREFLIGHT_PASS', 'operation': OPERATION,
        'destination': str(state['target']), 'guardStatus': result['status'],
        'nativeHash': result['nativeHash'], 'finalAcceptance': False,
        'permissionGranted': False, 'nativeWrites': 0}


def _atomic_replace(state, rel, expected, value, temporary_paths, on_replace=None):
    """Single-file CAS with fresh closed-editor checks; no shared-index writes."""
    path = _file(state['target'] / rel)
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.owned-revision.tmp')
    n._unlinked(temp, exists=False)
    temporary_paths.append(str(temp))
    n._assert_editor_closed()
    n.require(_file(state['store'] / 'root_meta_info.json').read_bytes() == state['index'],
        'revision-shared-index-changed')
    n.require(_file(path).read_bytes() == expected, 'revision-cas-before-stage: ' + rel)
    n._exclusive_write(temp, value)
    n._assert_editor_closed()
    # The byte CAS is immediately before replace, after staging and process check.
    n.require(_file(state['store'] / 'root_meta_info.json').read_bytes() == state['index'],
        'revision-shared-index-changed')
    n.require(_file(temp).read_bytes() == value, 'revision-staged-bytes-drift')
    n.require(_file(path).read_bytes() == expected, 'revision-cas-before-replace: ' + rel)
    if on_replace is not None:
        on_replace()  # Record intent only after the CAS, immediately before replace.
    os.replace(temp, path)
    n.require(_file(path).read_bytes() == value, 'revision-replace-readback: ' + rel)


def apply_revision(compiled_dir, request, journal_dir):
    state = _setup(compiled_dir, request)
    journal = n._unlinked(Path(journal_dir).absolute(), exists=False)
    n.require(not journal.exists() and not journal.is_relative_to(state['store']),
        'revision-fresh-task-journal-required')
    n.require(not any((p / 'root_meta_info.json').exists() or p.name.casefold() == 'com.lveditor.draft'
        for p in (journal, *journal.parents)), 'revision-journal-cannot-be-native-store')
    journal.mkdir(parents=True)
    attempted, temps, current = [], [], dict(state['before'])
    try:
        n._exclusive_write(journal / 'root_meta_info.before.bin', state['index'])
        for rel, value in state['before'].items():
            path = journal / 'before' / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            n._exclusive_write(path, value)
        n._exclusive_write(journal / 'scope.json', n.json_bytes({
            'schema': 'capcut-owned-revision-journal/v1', 'operation': OPERATION,
            'destination': str(state['target']), 'projectId': state['manifest']['projectId'],
            'timelineId': state['manifest']['timelineId'], 'name': state['manifest']['name'],
            'rootIndexSHA256': _sha(state['index']),
            'beforeFiles': {k: _sha(v) for k, v in state['before'].items()},
            'afterFiles': {k: _sha(v) for k, v in state['payload'].items()},
            'compiledManifest': {'path': str(state['root'] / 'compiled-manifest.json'),
                'sha256': 'sha256:' + _sha((state['root'] / 'compiled-manifest.json').read_bytes())},
            'baseline': state['baselineRef'], 'rootIndexWrites': 0,
            'foreignProjectWrites': 0, 'nativeAcceptance': 'PENDING'}))
        _unchanged(state, current)
        result = _guard(state)
        n._exclusive_write(journal / 'guard-result.json', n.json_bytes(result))
        # Guard binds the exact compiled files, not merely a stored success flag.
        for rel, digest in state['manifest']['files'].items():
            n.require(_sha(_file(state['root'] / 'files' / rel).read_bytes()) == digest,
                'revision-compiled-drift-after-guard: ' + rel)
        n._assert_app(state['request'])
        _unchanged(state, current)
        for rel, value in state['payload'].items():
            _unchanged(state, current)
            if value == current[rel]:
                continue
            _atomic_replace(state, rel, current[rel], value, temps,
                on_replace=lambda rel=rel: attempted.append(rel))
            current[rel] = value
        _unchanged(state, state['payload'])
        semantic = n.inspect_native(state['target'], state['plan'], state['manifest'], verify_sources=False)
        report = {'status': 'OWNED_NATIVE_REVISION_FILE_READBACK_PASS', 'operation': OPERATION,
            'destination': str(state['target']), 'filesChecked': len(state['payload']),
            'afterFiles': {k: _sha(v) for k, v in state['payload'].items()},
            'rootIndexBytesPreserved': True, 'rootIndexWrites': 0, 'foreignProjectWrites': 0,
            'guardStatus': result['status'], 'semanticInspect': semantic,
            'finalAcceptance': False, 'nativePlaybackEditSaveReopen': 'PENDING'}
        n._exclusive_write(journal / 'final-readback.json', n.json_bytes(report))
        return report
    except BaseException as exc:
        reconciliation, rollback = {}, []
        for rel, before in state['before'].items():
            try:
                actual = _file(state['target'] / rel).read_bytes()
                kind = ('BEFORE' if actual == before else 'OWNED_AFTER' if
                    rel in attempted and actual == state['payload'][rel] else 'FOREIGN_OR_UNKNOWN')
                reconciliation[rel] = {'state': kind, 'sha256': _sha(actual)}
            except BaseException as error:
                reconciliation[rel] = {'state': 'UNREADABLE_OR_LINKED', 'error': str(error)}
        # Reverse only attempted files still holding our exact after bytes.
        # Foreign changes, an open app or changed shared index hold recovery.
        for rel in reversed(attempted):
            if reconciliation[rel]['state'] != 'OWNED_AFTER':
                continue
            item = {'path': rel, 'status': 'HELD'}
            try:
                backup = _file(journal / 'before' / rel).read_bytes()
                n.require(backup == state['before'][rel], 'revision-backup-drift')
                _atomic_replace(state, rel, state['payload'][rel], backup, temps)
                item['status'] = 'OWNED_BYTES_RESTORED'
            except BaseException as error:
                item['reason'] = type(error).__name__ + ': ' + str(error)
                try:
                    if _file(state['target'] / rel).read_bytes() == state['before'][rel]:
                        item['status'] = 'OWNED_BYTES_RESTORED_EFFECT_THEN_ERROR'
                except BaseException:
                    pass
            rollback.append(item)
        after_recovery = {}
        for rel, before in state['before'].items():
            try:
                actual = _file(state['target'] / rel).read_bytes()
                after_recovery[rel] = {'sha256': _sha(actual), 'matchesBefore': actual == before}
            except BaseException as error:
                after_recovery[rel] = {'matchesBefore': False, 'error': str(error)}
        try:
            root_unchanged = _file(state['store'] / 'root_meta_info.json').read_bytes() == state['index']
        except BaseException:
            root_unchanged = False
        failure = {'status': 'FAILED_OWNED_REVISION_RECONCILED',
            'error': type(exc).__name__ + ': ' + str(exc), 'attemptedFiles': attempted,
            'reconciliation': reconciliation, 'rollback': rollback,
            'afterRecovery': after_recovery, 'rootIndexBytesUnchanged': root_unchanged,
            'restoredBeforeState': root_unchanged and all(v['matchesBefore'] for v in after_recovery.values()),
            'temporaryPathsRetainedIfPresent': [p for p in temps if Path(p).exists()],
            'rootIndexWrites': 0, 'foreignProjectWrites': 0,
            'foreignBytesNeverOverwritten': True, 'nativeAcceptance': 'PENDING'}
        try:
            n._exclusive_write(journal / 'failure.json', n.json_bytes(failure))
        except BaseException:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    capture = sub.add_parser('capture-baseline', help='Read-only native observation to a fresh task folder')
    capture.add_argument('--store', required=True)
    capture.add_argument('--name', required=True)
    capture.add_argument('--output', required=True)
    for name in ('preflight', 'apply'):
        command = sub.add_parser(name)
        command.add_argument('--compiled', required=True)
        command.add_argument('--request', required=True)
        if name == 'apply':
            command.add_argument('--journal', required=True)
    args = parser.parse_args(argv)
    if args.command == 'capture-baseline':
        result = capture_baseline(args.store, args.name, args.output)
    elif args.command == 'preflight':
        result = preflight(args.compiled, args.request)
    else:
        result = apply_revision(args.compiled, args.request, args.journal)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
