"""Resolve task-bound names; naming and lookup intent never authorize app writes."""
from pathlib import Path
import copy, json, re, string


def safe_name(value):
    """Filesystem-safe display name, including unchanged historical names."""
    if not isinstance(value, str) or not value.strip() or value in ('.', '..'):
        raise ValueError('Nonempty project display name required')
    if value != value.strip() or any(c in value for c in '/\\:<>"|?*') or any(ord(c) < 32 or ord(c) == 127 for c in value) or value.endswith((' ', '.')):
        raise ValueError('Unsafe project display name')
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', value, re.I):
        raise ValueError('Reserved project display name')
    return value


def validate_new_project_name(value):
    """A new name has prefix and final episode number/title, never run state.

    Explicit user prefixes/titles are retained. Shape validation proves neither
    the episode/style nor project existence, ownership or user authority.
    """
    safe_name(value)
    parts = value.split('_')
    if len(parts) < 2 or any(not p or p != p.strip() for p in parts):
        raise ValueError('New project name needs nonempty underscore-separated prefix and episode')
    tail = parts[-1]
    tokens = [t.casefold() for t in re.findall(r'\w+', tail)]
    while tokens and re.fullmatch(r'(?:v|r)?[0-9]+', tokens[-1]):
        tokens.pop()
    if tokens and re.fullmatch(r'(?:draft|review|fb|feedback|trial|test|final|preview|wip)(?:v?[0-9]+)?', tokens[-1]):
        raise ValueError('New project name cannot end in workflow status; provide the episode number or title')
    if re.fullmatch(r'[0-9]+', tail) or re.fullmatch(r'(?i)EP(?:\s*[+-]?[0-9]+)?', tail):
        match = re.fullmatch(r'(?i)EP\s*([0-9]+)', tail)
        if match is None or int(match.group(1)) <= 0:
            raise ValueError('Final numeric episode must be EP followed by a positive number')
    return value


def selected_profile(style_id):
    if style_id is None:
        return None
    if not isinstance(style_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', style_id):
        raise ValueError('Safe selected style ID required')
    path = Path(__file__).resolve().parents[1] / 'styles' / (style_id + '.json')
    if not path.exists():
        return None
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ValueError('Linked style profile refused')
    profile = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(profile, dict) or profile.get('id') != style_id:
        raise ValueError('Selected profile identity mismatch')
    return profile


def _positive(value, label):
    if type(value) is int and value > 0:
        return str(value)
    if isinstance(value, str) and re.fullmatch(r'[0-9]+', value) and int(value) > 0:
        return value
    raise ValueError('Positive integer ' + label + ' required')


def _part(value, label):
    safe_name(value)
    if '_' in value:
        raise ValueError(label + ' must be one name part')
    return value


def _legacy_template_prefix(policy):
    """Read an old plain template without evaluating expressions or requiring batch."""
    template, definitions = policy.get('template'), policy.get('parameters')
    if not isinstance(template, str) or not template or not isinstance(definitions, list) or not definitions:
        raise ValueError('Template and parameter definitions required')
    ids = []
    for item in definitions:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', item['id']):
            raise ValueError('Safe parameter ID required')
        if item['id'] in ids or item.get('type') not in ('POSITIVE_INTEGER', 'TEXT') or not isinstance(item.get('label'), str) or not item['label'].strip():
            raise ValueError('Unique typed labeled parameters required')
        ids.append(item['id'])
    fields = []
    for _, field, spec, conversion in string.Formatter().parse(template):
        if field is not None:
            if field not in ids or spec or conversion:
                raise ValueError('Template fields must be plain declared parameter IDs')
            fields.append(field)
    if set(fields) != set(ids):
        raise ValueError('Every naming parameter must occur in template')
    prefix = template.split('_')[0]
    return prefix if '_' in template and not any(c in prefix for c in '{}') else None


def resolve_project_identity(brief, profile=None, style_id=None):
    """Reuse proven answers; ask a missing episode, or absent style label.

    An explicit name without intent retains old lookup-before-app behavior.
    CREATE is strict here and independently strict in the native producer.
    Lookup intent does not qualify a revision for compilation.
    """
    mode = brief.get('output', {}).get('mode')
    base = {'status': 'PENDING_OUTPUT_MODE', 'name': None, 'nextQuestion': None,
            'missingParameters': [], 'nativeExistence': 'UNKNOWN', 'applyEligible': False,
            'creationAction': 'PENDING_TASK_SCOPE_AND_COMPATIBLE_TOOL', 'intent': None,
            'renamedExistingProject': False}
    if mode != 'EDIT_TIMELINE':
        return dict(base, status='NOT_APPLICABLE' if mode == 'SRT_ONLY' else 'PENDING_OUTPUT_MODE')
    identity = brief.get('projectIdentity') or {}
    if not isinstance(identity, dict):
        raise ValueError('Project identity must be an object')
    name = identity.get('name')
    intent = identity.get('intent')
    if intent is None:
        intent = 'LOOKUP_EXISTING' if name not in (None, '') else 'CREATE'
    if not isinstance(intent, str) or intent not in ('CREATE', 'LOOKUP_EXISTING', 'LOOKUP', 'EXISTING'):
        raise ValueError('Known project identity intent required')
    base['intent'] = intent
    if intent != 'CREATE':
        base['creationAction'] = 'LOOKUP_ONLY_NO_CREATE_OR_REVISION_AUTHORITY'
    revision = identity.get('revisionIdentity')
    if revision is not None:
        from native_revision import load_baseline
        baseline = load_baseline(revision)
        if name not in (None, '', baseline['name']):
            raise ValueError('Existing revision name must match its bound baseline')
        return dict(base, status='EXPLICIT_NAME_BOUND', name=baseline['name'],
                    intent='EXISTING', revisionIdentity=copy.deepcopy(revision),
                    creationAction='BOUND_REVISION_REQUIRES_SEPARATE_CURRENT_GUARD')
    if name not in (None, ''):
        safe_name(name)
        evidence = identity.get('evidenceRef')
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError('Project-name evidence required')
        if intent == 'CREATE':
            try:
                validate_new_project_name(name)
            except ValueError as error:
                return dict(base, status='NEEDS_PROJECT_NAME', rejectedName=name,
                            namingIssue=str(error), missingParameters=['name'],
                            nextQuestion='Tên dự án mới cần các phần cách nhau bằng _, phần cuối là EP hoặc tên tập, không phải trạng thái. Bạn muốn dùng tên nào?')
        return dict(base, status='EXPLICIT_NAME_BOUND', name=name, evidenceRef=evidence)
    if intent != 'CREATE':
        return dict(base, status='NEEDS_PROJECT_NAME', missingParameters=['name'],
                    nextQuestion='Tên chính xác của dự án CapCut hiện có là gì?')
    if profile is not None and (not isinstance(profile, dict) or profile.get('id') != style_id):
        raise ValueError('Naming profile must belong to selected style')
    policy = (profile.get('projectNaming') or {}) if isinstance(profile, dict) else {}
    if not isinstance(policy, dict) or policy.get('mode') not in (None, 'EXACT_NAME', 'TEMPLATE', 'STYLE_EPISODE'):
        raise ValueError('Known project-naming mode required')
    if policy.get('styleId', style_id) != style_id:
        raise ValueError('Naming policy must belong to selected style')
    if policy.get('separator', '_') != '_' or policy.get('episodePrefix', 'EP ') != 'EP ':
        raise ValueError('Supported naming separator and episode prefix required')
    legacy_prefix = _legacy_template_prefix(policy) if policy.get('mode') == 'TEMPLATE' else None
    prefix = policy.get('defaultPrefix')
    if not prefix and profile:
        prefix = next((profile.get(k) for k in ('displayName', 'name', 'title') if profile.get(k)), None)
    # Compatibility for owned TEMPLATE profiles during instruction staging.
    if not prefix:
        prefix = legacy_prefix
    if not prefix:
        return dict(base, status='NEEDS_PROJECT_NAME', missingParameters=['styleDisplayName'],
                    nextQuestion='Bạn muốn dùng tên phong cách dựng nào làm phần đầu tên dự án?')
    prefix = _part(prefix, 'Style display name')
    params = identity.get('namingParameters') or {}
    proofs = identity.get('parameterEvidenceRefs') or {}
    if not isinstance(params, dict) or not isinstance(proofs, dict):
        raise ValueError('Parameter values and evidence must be objects')
    def answer(key):
        direct = key in identity and identity[key] not in (None, '')
        value = identity[key] if direct else params.get(key)
        proof = proofs.get(key) or (identity.get('evidenceRef') if direct else None)
        return value, proof if isinstance(proof, str) and proof.strip() else None
    episode, evidence = answer('episode')
    label, label_evidence = answer('episodeLabel')
    if episode in (None, '') or not evidence:
        episode, evidence = label, label_evidence
    if episode in (None, '') or not evidence:
        return dict(base, status='NEEDS_NAMING_PARAMETERS', missingParameters=['episode'],
                    nextQuestion='Clip này là EP số mấy hoặc có tên tập là gì?')
    if type(episode) is int or isinstance(episode, str) and re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]+)?', episode):
        tail = 'EP ' + _positive(episode, 'episode')
    else:
        tail = _part(episode, 'Episode title')
    values = {'episode': copy.deepcopy(episode)}
    used_proofs = {'episode': evidence}
    context, context_evidence = answer('context')
    batch, batch_evidence = answer('shootBatch')
    if context not in (None, '') and context_evidence:
        context = _part(context, 'Context')
        values['context'] = context; used_proofs['context'] = context_evidence
    elif batch not in (None, '') and batch_evidence:
        batch = _positive(batch, 'shoot batch')
        if policy.get('contextTemplate', 'Dot{shootBatch}') != 'Dot{shootBatch}':
            raise ValueError('Supported optional shoot-batch context template required')
        context = 'Dot' + batch
        values['shootBatch'] = batch; used_proofs['shootBatch'] = batch_evidence
    else:
        context = None
    result = '_'.join([prefix, *([context] if context else []), tail])
    try:
        validate_new_project_name(result)
    except ValueError as error:
        return dict(base, status='NEEDS_PROJECT_NAME', rejectedName=result, namingIssue=str(error),
                    missingParameters=['episode'], nextQuestion='Tên hoặc số EP là gì? Không dùng trạng thái công việc làm tên tập.')
    return dict(base, status='PROPOSED_NAME_PENDING_APP_MATCH', name=result,
                namingParameters=values, evidenceRefs=used_proofs, nextQuestion=None)
