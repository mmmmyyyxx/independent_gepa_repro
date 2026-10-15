"""Gold-blind answer declarations, independent of presentation and correctness.

V2 remains frozen in math_structured_answer for historical baseline replay.
This policy selects declarations, never a number from arbitrary working.
"""
from dataclasses import asdict
import json
import re

from ..protocol import ProtocolViolation as SearchContractError
from .math_prediction_validity import (
    MATHPrediction, MATHResolvedPrediction, classify_payload, resolve_predictions,
)

IDENTITY = 'MATH_FLEXIBLE_ANSWER_EXTRACTION_V3'
VALIDITY = 'MATH_FLEXIBLE_PREDICTION_VALIDITY_V3'
POLICY = dict(
    identity=IDENTITY,
    declaration_forms=['final_answer_label', 'answer_label', 'markdown_label',
                       'natural_conclusion', 'terminal_balanced_boxed'],
    multiline='balanced_display_boxed_matrix_or_labeled_math_fence',
    selection='last_explicit_label_else_last_terminal_conclusion',
    confirmations='all_labels_and_conclusions_after_selected_label_must_agree_gold_blind',
    scalar_confirmation='single_variable_constant_assignment_rhs_only',
    trailing_prose='permitted_after_explicit_label_without_conflicting_declaration',
    normalization='outer_math_markdown_sentence_period_unicode_radical_minus_pi_v1',
    maximum_declarations=16, unmarked_expression='forbidden',
    maximum_payload_characters=2048, maximum_wrapped_declaration_characters=4096,
    empty_heading='skip_when_followed_by_another_answer_declaration',
    coordinate_assignment='distinct_named_coordinates_same_arity_pinned_tuple_rhs',
    gold_access=False, intermediate_selection=False,
    truncated='invalid_even_with_answer', payload_parser='math_verify_no_fallback_v1',
)
_LABEL = re.compile(r'^(?:final[ _]+answer|answer)\s*(?:\*\*|__)?\s*[:=]\s*(.*)$', re.I)
_CONCLUSION = re.compile(
    r'^(?:(?:therefore|thus|hence|so)[,:]?\s+(?:(?:the\s+)?(?:final\s+)?(?:answer|result)\s+is\s*:?\s+)?'
    r'|(?:the\s+)?(?:final\s+)?answer\s+is\s*:?\s+)(.*)$', re.I)
_ASSIGNMENT = re.compile(r'^([A-Za-z])\s*=\s*(.+)$', re.S)
_ENVIRONMENTS = {'matrix', 'pmatrix', 'bmatrix', 'Bmatrix', 'vmatrix', 'Vmatrix',
                 'smallmatrix', 'array', 'cases', 'aligned', 'align', 'gathered'}
_WORDS = {'sqrt', 'sin', 'cos', 'tan', 'log', 'ln', 'pi', 'oo', 'inf',
          'cm', 'mm', 'kg'}
_CONSTANT_COMMANDS = {'frac', 'dfrac', 'tfrac', 'sqrt', 'pi', 'sin', 'cos',
                      'tan', 'log', 'ln', 'left', 'right', 'cdot', 'times',
                      'div', 'infty', 'text', 'mathrm', 'operatorname'}


def _line(value):
    value = re.sub(r'^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+)', '', value.strip())
    if value.startswith(('**', '__')):
        marker = value[:2]
        value = value[2:]
        if value.endswith(marker + '.'):
            value = value[:-3] + '.'
        elif value.endswith(marker):
            value = value[:-2]
    return value.strip()


def _label(value):
    match = _LABEL.fullmatch(value)
    if not match:
        return None
    payload = match[1]
    # In a bold label only, the closing markup follows the colon. Preserve
    # independently balanced markup around the answer itself.
    if payload.startswith(('**', '__')) and not payload.rstrip().endswith(payload[:2]):
        payload = payload[2:].lstrip()
    return payload


def normalize_payload(value):
    value = value.strip()
    # A sentence full stop is distinct from a decimal point or an ellipsis.
    if value.endswith('.') and not value.endswith('..'):
        value = value[:-1].rstrip()
    for left, right in (('**', '**'), ('`', '`'), ('$$', '$$'),
                        ('\\(', '\\)'), ('\\[', '\\]'), ('$', '$')):
        if value.startswith(left) and value.endswith(right) and len(value) > len(left) + len(right):
            value = value[len(left):-len(right)].strip()
    value = value.replace('\u2212', '-').replace('\u03c0', r'\pi')
    # Only a single atom or an explicitly grouped radicand is rewritten.
    value = re.sub(r'\u221a\s*(\([^()]*\)|\{[^{}]*\}|(?:\d+(?:\.\d+)?|[A-Za-z])(?![A-Za-z0-9.]))',
                   lambda m: r'\sqrt{' + (m[1][1:-1] if m[1][0] in '({' else m[1]) + '}', value)
    return value.strip()


def _complete(value):
    """Return whether a supported multiline wrapper is closed, without guessing."""
    stripped = value.strip()
    if stripped.startswith('```'):
        return '\n' in stripped and stripped.endswith('```')
    for left, right in (('$$', '$$'), ('\\[', '\\]'), ('\\(', '\\)')):
        if stripped.startswith(left):
            return len(stripped) > len(left) + len(right) and stripped.rstrip('. ').endswith(right)
    # A boxed expression may have nested braces and span physical lines.
    if r'\boxed' in stripped:
        depth = 0
        opened = False
        for i, char in enumerate(stripped):
            if i and stripped[i-1] == '\\':
                continue
            if char == '{':
                opened = True
                depth += 1
            elif char == '}':
                depth -= 1
        return opened and depth == 0
    env = re.match(r'\\begin\{([A-Za-z]+)\}', stripped)
    return not env or (r'\end{' + env[1] + '}') in stripped


def _unwrap(value):
    value = value.strip()
    if value.startswith('```'):
        lines = value.splitlines()
        if len(lines) < 3 or not re.fullmatch(r'```(?:latex|math|text)?', lines[0], re.I) or lines[-1] != '```':
            return None
        value = '\n'.join(lines[1:-1])
    if value.count('`') % 2 or value.count('$') % 2:
        return None
    value = normalize_payload(value)
    match = re.match(r'\\boxed\s*\{', value)
    if not match:
        if r'\boxed' not in value:
            return value
        assignment = _ASSIGNMENT.fullmatch(value)
        if assignment:
            rhs = _unwrap(assignment[2])
            return assignment[1] + '=' + rhs if rhs is not None else None
        return None
    depth, cursor = 1, match.end()
    while cursor < len(value) and depth:
        if value[cursor-1] != '\\':
            if value[cursor] == '{':
                depth += 1
            elif value[cursor] == '}':
                depth -= 1
        cursor += 1
    if depth or value[cursor:].strip():
        return None
    return normalize_payload(value[match.end():cursor-1])


def _records(text):
    if not isinstance(text, str):
        return [], 'MISSING_EXPLICIT_FINAL_ANSWER'
    lines = list(re.finditer(r'[^\r\n]+', text))
    records, skip = [], -1
    for index, line in enumerate(lines):
        if index <= skip:
            continue
        content = _line(line.group())
        label = _label(content)
        conclusion = _CONCLUSION.fullmatch(content)
        terminal_box = normalize_payload(content).startswith(r'\boxed')
        display = content.startswith(('\\[', '$$'))
        if not (label is not None or conclusion or terminal_box or display):
            continue
        kind = 'label' if label is not None else 'conclusion' if conclusion else 'box'
        value = label if label is not None else conclusion[1] if conclusion else content
        if label is not None and not value.strip():
            following = index + 1
            while following < len(lines) and not _line(lines[following].group()):
                following += 1
            if following < len(lines):
                next_line = _line(lines[following].group())
                if _label(next_line) is not None or _CONCLUSION.fullmatch(next_line):
                    # A section heading followed by a complete declaration is
                    # not itself an empty competing answer.
                    continue
        if kind == 'conclusion' and not _expression_only(value) and not re.search(r'\d|=|\\[A-Za-z]', value):
            # "Therefore, this completes the proof" is explanatory prose,
            # not a competing mathematical declaration.
            continue
        end_index = index
        while (not value.strip() or not _complete(value)) and end_index + 1 < len(lines):
            end_index += 1
            value += '\n' + lines[end_index].group().strip()
            if len(value) > POLICY['maximum_wrapped_declaration_characters']:
                break
        skip = end_index
        payload = _unwrap(value) if _complete(value) else None
        if display and kind == 'box' and not normalize_payload(value).startswith(r'\boxed'):
            # An unmarked display expression is still working, not a declaration.
            continue
        tail = text[lines[end_index].end():].strip()
        if kind != 'label' and tail and not any(_LABEL.fullmatch(_line(m.group())) for m in lines[end_index+1:]):
            # Natural conclusions can be followed by prose, but an ordinary
            # intermediate box is not a final answer.
            if kind == 'box' and tail not in {'.', '```'}:
                continue
        records.append(dict(payload=payload, start=line.start(), end=lines[end_index].end(), kind=kind))
    labels = [r for r in records if r['kind'] == 'label']
    if labels:
        primary = labels[-1]
        # Earlier boxes and natural conclusions belong to working, not to the
        # final declaration's consistency checks.
        records = [r for r in records if r['kind'] == 'label' or r['start'] > primary['start']]
    elif records:
        primary = records[-1]
        records = [primary]
    else:
        return [], 'MISSING_EXPLICIT_FINAL_ANSWER'
    # Bound competing answer claims after excluding ordinary earlier working.
    if len(records) > POLICY['maximum_declarations']:
        return [], 'AMBIGUOUS_FINAL_PAYLOAD'
    for record in records:
        record['primary'] = record is primary
    return records, None


def boundaries(text):
    """Projection seam: primary starts the answer region, even before a confirmation."""
    records, reason = _records(text)
    if reason and reason != 'MISSING_EXPLICIT_FINAL_ANSWER':
        return None
    if any(r['payload'] is None for r in records):
        return None
    return [(r['payload'], r['start'], r['end'], r['primary']) for r in records]


def _expression_only(payload):
    # The pinned math parser can extract a prefix. Reject prose alternatives
    # before it sees them; matrix environment names are syntax, not prose.
    if '\u221a' in payload:
        return False
    value = re.sub(r'\\(?:begin|end)\{([A-Za-z]+)\}',
                   lambda m: '' if m[1] in _ENVIRONMENTS else m[0], payload)
    value = re.sub(r'\\[A-Za-z]+', '', value)
    return not any(w.casefold() not in _WORDS for w in re.findall(r'[A-Za-z]{2,}', value))


def _constant_rhs(payload):
    match = _ASSIGNMENT.fullmatch(payload)
    if not match or '=' in match[2]:
        return None
    rhs = match[2]
    # Single-letter variables remaining after removing TeX commands mean this
    # is an equation, not a scalar confirmation.
    bare = re.sub(r'\\([A-Za-z]+)',
                  lambda m: '' if m[1] in _CONSTANT_COMMANDS else m[0], rhs)
    if any(char.isalpha() for char in bare) or classify_payload(rhs) is not None:
        return None
    return rhs


def _coordinate_rhs(payload):
    """A named coordinate tuple is a presentation of its ordered tuple values."""
    match = re.fullmatch(r'(?:\\left\s*)?\(\s*([A-Za-z](?:\s*,\s*[A-Za-z]){2,15})\s*(?:\\right\s*)?\)\s*=\s*(.+)', payload, re.S)
    if not match:
        return None
    names = [v.strip() for v in match[1].split(',')]
    if len(set(names)) != len(names):
        return None
    rhs = match[2].strip()
    plain = rhs.replace(r'\left', '').replace(r'\right', '').strip()
    if not plain.startswith('(') or not plain.endswith(')'):
        return None
    stack, entries = [], 1
    for char in plain[1:-1]:
        if char in '([{':
            stack.append(char)
        elif char in ')]}':
            if not stack or '([{'.index(stack.pop()) != ')]}'.index(char):
                return None
        elif char == ',' and not stack:
            entries += 1
    if stack or entries != len(names) or not _expression_only(rhs):
        return None
    from .math_domain_v2 import domain_matrix
    result = domain_matrix((rhs,))
    return rhs if result['valid'][0] and result['parsed_types'][0] == ['Tuple'] else None


def _equivalent(a, b):
    if a == b:
        return True
    from .math_domain_v2 import domain_matrix
    relation = domain_matrix((a, b))
    return all(relation['valid']) and relation['equivalence'][0][1] and relation['equivalence'][1][0]


def extract_answer(text):
    records, reason = _records(text)
    if reason:
        return '', reason
    if any(r['payload'] is None for r in records):
        return '', 'MALFORMED_FINAL_BOUNDARY'
    if any(not r['payload'] for r in records):
        return '', 'EMPTY_FINAL_PAYLOAD'
    if any(len(r['payload']) > POLICY['maximum_payload_characters'] for r in records):
        return '', 'PAYLOAD_UNSUPPORTED'
    for record in records:
        record['payload'] = _coordinate_rhs(record['payload']) or record['payload']
    if any(not _expression_only(r['payload']) for r in records):
        return '', 'AMBIGUOUS_FINAL_PAYLOAD'
    primary = next(r for r in records if r['primary'])
    final = primary['payload']
    if primary['kind'] == 'conclusion':
        final = _constant_rhs(final) or final
    for record in records:
        other = record['payload']
        if _equivalent(final, other):
            continue
        if record['kind'] == 'conclusion':
            other = _constant_rhs(other) or other
        if not _equivalent(final, other):
            if classify_payload(final) is not None or classify_payload(other) is not None:
                return '', 'PAYLOAD_PARSE_FAILURE'
            return '', 'CONFLICTING_FINAL_ANSWERS'
    return final, None


def classify_prediction(text, finish_reason='stop'):
    if text is not None and not isinstance(text, str):
        raise SearchContractError('MATH_PREDICTION_SERIALIZATION_INVALID')
    # Avoid doing mathematical work on a known incomplete provider response.
    if finish_reason != 'stop':
        reason = 'OUTPUT_TRUNCATED' if finish_reason in {'length', 'max_tokens', 'max_output_tokens'} else 'OTHER_PREDICTION_CONTRACT_FAILURE'
        return MATHPrediction(text, finish_reason, '', False, reason)
    expression, reason = extract_answer(text)
    if reason is None:
        reason = classify_payload(expression)
    return MATHPrediction(text, finish_reason, expression if reason is None else '', reason is None, reason)


def prediction_from_persisted(value):
    data = asdict(value) if isinstance(value, (MATHPrediction, MATHResolvedPrediction)) else value
    if not isinstance(data, dict):
        raise SearchContractError('MATH_STRUCTURED_PREDICTION_STATE_INVALID')
    if set(data) == set(MATHResolvedPrediction.__dataclass_fields__):
        attempts = tuple(prediction_from_persisted(p) for p in data['original_predictions'])
        expected = resolve_predictions(attempts, data['transport_retry_attempts'])
    elif set(data) == set(MATHPrediction.__dataclass_fields__):
        expected = classify_prediction(data['text'], data['finish_reason'])
    else:
        raise SearchContractError('MATH_STRUCTURED_PREDICTION_STATE_INVALID')
    if json.dumps(data, sort_keys=True) != json.dumps(asdict(expected), sort_keys=True) or type(data['prediction_valid']) is not bool:
        raise SearchContractError('MATH_STRUCTURED_PREDICTION_STATE_CORRUPTION')
    if isinstance(expected, MATHResolvedPrediction) and (
        any(type(data[k]) is not bool for k in ('recovered_invalid', 'terminal_invalid'))
        or any(type(data[k]) is not int for k in ('semantic_attempt_count', 'raw_invalid_count', 'transport_retry_attempts'))
    ):
        raise SearchContractError('MATH_STRUCTURED_PREDICTION_STATE_CORRUPTION')
    return expected


def validity_contract():
    return dict(identity=VALIDITY, reference_failure='hard_contract_failure',
        prediction_failure='invalid_incorrect_continue', truncated_even_with_marker='invalid_incorrect',
        invalid_response_retries=3, fallback_extraction=False,
        invalid_vote='excluded_from_equivalence_classes', denominator='all_frozen_examples',
        invalidity_telemetry='observation_only', answer_extraction=POLICY)
