"""Independent, deterministic content-risk screening; never a candidate gate."""
import re
import yaml

from .common import digest, read, write
from ..protocol import ProtocolViolation


def load_policy(root, path='configs/gepa_single_prompt_posthoc_v6.yaml'):
    policy = yaml.safe_load((root / path).read_text(encoding='utf-8'))
    expected = {'identity': 'GEPA_POSTHOC_CONTENT_REVIEW_V6',
        'mode': 'observation_only_never_filter_reselect_or_change_score',
        'long_reference_min_characters': 12, 'solution_fragment_min_tokens': 16,
        'solution_fragment_min_characters': 80, 'normalize_math_variants': True,
        'short_reference_requires_explicit_example_context': True,
        'fixed_constant_output_detection': 'explicit_unconditional_output_literal',
        'manual_rubric': ['general_mathematical_technique', 'specific_training_example_or_reference',
                          'instance_identity_lookup', 'ambiguous_needs_review'],
        'scope': 'all_generated_and_selected_candidates', 'review_model_calls': 0}
    if policy != expected or any(type(policy[k]) is not type(v) for k,v in expected.items()):
        raise ProtocolViolation('POSTHOC_POLICY_MISMATCH')
    return policy


def normalize(text):
    text = text.lower().replace('−', '-').replace('∞', r'\infty').replace('∪', r'\cup')
    text = re.sub(r'\\(?:left|right|boxed|text|mathrm)', '', text)
    return re.sub(r'[\s${}]', '', text)


def fragments(text, count, minimum):
    words = re.findall(r'\\[a-zA-Z]+|[a-zA-Z]+|\d+|[^\s]', text.lower())
    return {tuple(words[i:i + count]) for i in range(max(0, len(words) - count + 1))
            if len(' '.join(words[i:i + count])) >= minimum}


def review(candidate, optimize_rows, policy):
    text = '\n'.join(candidate.values())
    normalized = normalize(text)
    context = bool(re.search(r'(?:reference|correct)\s+(?:answer|result)|example\s*\d+|assistant\s+(?:gave|output)', text, re.I))
    grams = fragments(text, policy['solution_fragment_min_tokens'], policy['solution_fragment_min_characters'])
    evidence = []
    for row in optimize_rows:
        ref = normalize(row['reference_final_answer'])
        literal = bool(ref and len(ref) >= policy['long_reference_min_characters'] and ref in normalized)
        short = bool(context and ref and len(ref) < policy['long_reference_min_characters']
            and re.search(r'(?:correct|reference)\s+(?:answer|result)\s*(?:was|is|:)\s*[`$]*' + re.escape(row['reference_final_answer']) + r'(?![\w\d])', text, re.I))
        overlap = grams & fragments(row['content'].get('solution', ''), policy['solution_fragment_min_tokens'], policy['solution_fragment_min_characters'])
        identity = row['stable_example_id'] in text
        if literal or short or overlap or identity:
            evidence.append({'source_id_hash': digest(row['stable_example_id']), 'long_reference_variant': literal,
                'short_reference_in_explicit_example_context': short, 'solution_fragment_matches': len(overlap),
                'instance_identity': identity})
    lookup = bool(re.search(r'(?:if|when).{0,160}(?:problem|input|question|example).{0,160}(?:return|output|answer).{0,80}\d', text, re.I))
    fixed = bool(re.search(r'\b(?:always|only)\s+(?:output|return|respond(?: with)?|answer(?: with)?)\s+[`$]*[-+]?\d',text,re.I))
    return {'candidate_hash': digest(candidate), 'risk_flag': bool(evidence or lookup or fixed),
            'evidence': evidence, 'lookup_pattern_flag': lookup,
            'fixed_constant_output_flag':fixed,
            'classification': 'needs_independent_manual_review' if evidence or lookup or fixed else 'no_automatic_match_not_certified',
            'native_score_changed': False, 'reselected': False, 'semantic_legitimacy_certified': False}


def audit_run(directory, optimize_rows, policy, *, persist=True):
    frozen = read(directory / 'frozen.json')
    cells = []
    for arm in frozen['config']['arms']:
        for repeat in frozen['config']['repeat_ids']:
            folder = directory / arm / f'repeat_{repeat}'
            proposals, selection = read(folder / 'proposals.json'), read(folder / 'selection.json')
            generated = [review(p['candidate'], optimize_rows, policy) for p in proposals]
            final = review(selection['selected'], optimize_rows, policy)
            cells.append({'arm': arm, 'repeat_id': repeat, 'generated': generated, 'selected': final})
    result = {'identity': 'GEPA_INDEPENDENT_POSTHOC_CONTENT_V6', 'policy_sha256': digest(policy),
              'mode': policy['mode'], 'cells': cells, 'model_calls': 0, 'changes_to_native_selection': 0}
    if persist:
        write(directory / 'posthoc_content.json', result)
    return result
