"""Deterministic source-copy checks, with safe categories and no prompt rewriting.

This is a bounded lexical conformance guard, not a semantic proof of novelty.
Ordinary constants and general mathematical instructions remain permitted.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from fractions import Fraction
import re
import unicodedata
from typing import Any

GUARD_ID = 'math_candidate_conformance_guard_v2'


def _math_text(text: str) -> str:
    text = unicodedata.normalize('NFKC', text).lower().replace('−', '-')
    text = text.replace('\\dfrac', '\\frac').replace('\\tfrac', '\\frac')
    text = text.replace('\\left', '').replace('\\right', '')
    text = re.sub(r'\\(?:,|;|!|quad|qquad|displaystyle)\s*', '', text)
    return re.sub(r'\s+|\$', '', text)


def _rational_forms(reference: str) -> set[str]:
    """Exact terminating decimals and slash/LaTeX spellings of scalar gold."""
    value = _math_text(reference)
    match = re.fullmatch(r'(-?)\\frac\{(-?\d+)\}\{(-?\d+)\}', value)
    try:
        if match:
            rational = Fraction(int(match[2]), int(match[3]))
            if match[1]: rational = -rational
        else:
            rational = Fraction(value)
    except (ValueError, ZeroDivisionError, InvalidOperation):
        return {value}
    forms = {value, str(rational)}
    numerator, denominator = rational.numerator, rational.denominator
    if denominator != 1:
        forms.add(f'\\frac{{{numerator}}}{{{denominator}}}')
        if numerator < 0: forms.add(f'-\\frac{{{-numerator}}}{{{denominator}}}')
    reduced = denominator
    for factor in (2, 5):
        while reduced % factor == 0: reduced //= factor
    if reduced == 1:
        # No rounded approximation: limit representation size for a bounded guard.
        digits = max(len(str(abs(numerator))), len(str(denominator))) + 8
        if digits <= 128:
            from decimal import localcontext
            with localcontext() as context:
                context.prec = digits * 4
                decimal = format(Decimal(numerator) / Decimal(denominator), 'f')
            forms.add(decimal)
            if decimal.startswith('0.'): forms.add(decimal[1:])
            if decimal.startswith('-0.'): forms.add('-' + decimal[2:])
    return forms


def _literal_in(text: str, value: str) -> bool:
    if not value: return False
    # Avoid treating one digit as part of a different number or a word.
    left = r'(?<![\d.])' if not value[0].isalpha() else r'(?<![\w.])'
    right = r'(?!\d|\.\d)' if not value[-1].isalpha() else r'(?!\w|\.\d)'
    return re.search(left + re.escape(value) + right, text) is not None


def candidate_failures(prompt: str, examples: list[dict[str, Any]]) -> list[str]:
    if not isinstance(prompt, str) or not prompt.strip(): return ['EMPTY_PROCEDURE']
    if len(prompt) > 3000: return ['PROCEDURE_LENGTH']
    failures: set[str] = set()
    if re.search(r'(?i)(?:always|regardless).*?(?:answer|output|return)|(?:final[_ ]answer\s*:)\s*(?!<answer>)[0-9]', prompt):
        failures.add('FIXED_ANSWER_INSTRUCTION')
    if re.search(r'(?i)(?:omit|remove|replace|change|ignore).{0,50}(?:FINAL_ANSWER|marker|response format)', prompt):
        failures.add('IMMUTABLE_INTERFACE_MODIFICATION')
    # Reasoning instructions may govern internal work, but the immutable A4
    # shell requests one final line. Explicitly displaying work violates it.
    for match in re.finditer(r'(?i)\b(?:provide|present|show|write|include|output|explain)\b[^\n;.!?]{0,80}\b(?:derivation|proof|reasoning|solution|steps|work)\b',prompt):
        before=prompt[max(0,match.start()-14):match.start()].lower()
        if re.search(r'(?:do not|don.t|never)\s*$',before): continue
        if re.search(r'(?i)\b(?:internally|silently|private|mentally)\b',match.group()): continue
        failures.add('VISIBLE_REASONING_OUTPUT_CONFLICT')
    # References to optimizer-only example numbering or gold metadata cannot
    # become Solver instructions, even when the copied answer is one character.
    if re.search(r'(?i)\b(?:example|sample|case)\s*#?\s*\d+\b|\b(?:gold|reference|training)\s+answer\b|\b(?:training|feedback)\s+(?:example|sample|problem)\b', prompt):
        failures.add('OPTIMIZER_EXAMPLE_OR_ANSWER_METADATA')
    normalized = ' '.join(prompt.split()).lower()
    compact = _math_text(prompt)
    sentences = re.split(r'[\n;!?]|(?<!\d)\.(?!\d)', prompt)
    for row in examples:
        problem = ' '.join(row['problem'].split()).lower()
        if len(problem) >= 80 and any(problem[i:i+80] in normalized for i in range(len(problem)-79)):
            failures.add('SOURCE_PROBLEM_COPY')
        reference = row['reference'].strip()
        if len(reference) >= 16 and reference in prompt:
            failures.add('SOURCE_ANSWER_LITERAL_COPY')
        forms = _rational_forms(reference)
        for form in forms:
            # Fractions and compound expressions are source-specific even when
            # their serialization is shorter than the old sixteen-character cap.
            compound = len(form) >= 5 and bool(re.search(r'\\|[+*/^=]|(?<=\w)-|[(){}]', form))
            if compound and _literal_in(compact, form):
                failures.add('SHORT_SOURCE_MATH_LITERAL_COPY')
            for sentence in sentences:
                answer_context = re.search(r'(?i)\b(?:answer|result|output|solution)\s*(?:is|was|=|:|should\s+be|must\s+be)\s*', sentence)
                worked_context = (re.search(r'(?i)\b(?:e\.g\.|for example|for instance|such as|suppose)\b', sentence)
                                  or re.search(r'\d\s*[-+*/÷]\s*\d.{0,32}=', sentence))
                # Universal constants are allowed outside explicit answer context.
                if (answer_context or (worked_context and form not in {'0','1','-1'})) and _literal_in(_math_text(sentence), form):
                    failures.add('SHORT_SOURCE_RESULT_IN_WORKED_CONTEXT')
    return sorted(failures)


def candidate_valid(prompt: str, examples: list[dict[str, Any]]) -> bool:
    return not candidate_failures(prompt, examples)
