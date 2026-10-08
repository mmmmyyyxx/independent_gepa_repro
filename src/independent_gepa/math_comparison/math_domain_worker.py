"""Pinned V2 evaluator. Parent process owns the hard portable deadline."""
import json
import logging
import re
import sys
from .contract import PINS
from .contract import SETTINGS


def ambiguous_parentheses(text):
    # This detects ambiguity, never decides tuple/interval correctness. No
    # coordinate parsing or comparison is implemented in the project wrapper.
    text=re.sub(r'\\(?:left|right|big|Big|bigg|Bigg)\b','',text).strip().strip('$').strip()
    # Boxed formatting does not supply a mathematical type tag.
    while text.startswith('\\boxed{') and text.endswith('}'):
        depth=0;closing=None
        for index,character in enumerate(text[6:],start=6):
            if character=='{': depth+=1
            elif character=='}':
                depth-=1
                if depth==0:
                    closing=index;break
        if closing!=len(text)-1: break
        text=text[7:-1].strip()
    if not (text.startswith('(') and text.endswith(')')):
        return False
    depth=0;commas=0
    for character in text[1:-1]:
        if character in '({[': depth+=1
        elif character in ')}]': depth-=1
        elif character==',' and depth==0: commas+=1
    return depth==0 and commas==1


def initialize():
    import importlib.metadata
    for package,version in PINS.items():
        if importlib.metadata.version(package)!=version:
            raise ValueError('MATH_EVALUATOR_DEPENDENCY_IDENTITY_MISMATCH')
    import math_verify.parser as parser
    import math_verify.grader as grader
    from functools import partial
    from latex2sympy2_extended.latex2sympy2 import ConversionConfig
    # Bind the pinned converter's options explicitly at its public function
    # seam; no dependency file or arithmetic/parser rule is modified.
    parser.latex2sympy=partial(parser.latex2sympy,conversion_config=ConversionConfig(**SETTINGS['conversion_config']))
    parser.timeout=grader.timeout=lambda *args,**kwargs:lambda function:function
    logging.disable(logging.CRITICAL)


def parse_payload(text):
    from math_verify import parse,LatexExtractionConfig
    from latex2sympy2_extended.math_normalization import NormalizationConfig
    config=SETTINGS['latex_extraction']
    value=parse(text if '$' in text or '\\boxed' in text else '$'+text+'$',
        extraction_config=(LatexExtractionConfig(try_extract_without_anchor=config['try_extract_without_anchor'],
            boxed_match_priority=config['boxed_match_priority'],normalization_config=NormalizationConfig(**config['normalization_config'])),),
        fallback_mode=SETTINGS['fallback_mode'],extraction_mode=SETTINGS['extraction_mode'],parsing_timeout=SETTINGS['parsing_timeout'])
    # Native parsing always occurs before ambiguity admission is decided.
    valid=bool(text.strip()) and len(text)<=SETTINGS['maximum_expression_characters'] and bool(value) and not any(isinstance(x,str) for x in value)
    return value,valid and not ambiguous_parentheses(text)


def compatible(left,right):
    from sympy import Tuple,MatrixBase,Set
    from sympy.core.relational import Relational
    from sympy.logic.boolalg import BooleanFunction
    def family(value):
        if isinstance(value,Tuple): return 'tuple'
        if isinstance(value,MatrixBase): return 'matrix'
        if isinstance(value,Set):
            return 'finite_set' if value.is_FiniteSet else 'infinite_set'
        if isinstance(value,(Relational,BooleanFunction)): return 'relation'
        return 'expression'
    # Strict pinned verify still converts some intervals to endpoint sets.
    # Preserve container semantics without implementing numeric equivalence.
    return family(left) in SETTINGS['object_families'] and family(left)==family(right)


def verify_payload(left,right):
    from math_verify import verify
    return any(compatible(g,p) and verify(g,p,strict=SETTINGS['strict'],
        float_rounding=SETTINGS['float_rounding'],numeric_precision=SETTINGS['numeric_precision'],
        timeout_seconds=SETTINGS['verification_timeout']) for g in left for p in right)


def evaluate(expressions):
    parsed=[parse_payload(text) for text in expressions]
    valid=[supported for _,supported in parsed]
    matrix=[[bool(valid[i] and valid[j] and verify_payload(parsed[i][0],parsed[j][0]))
        for j in range(len(parsed))] for i in range(len(parsed))]
    return dict(valid=valid,equivalence=matrix,parsed_types=[[type(x).__name__ for x in values] for values,_ in parsed])


def main():
    import socket
    def blocked(*args,**kwargs): raise RuntimeError('MATH_WORKER_NETWORK_FORBIDDEN')
    socket.socket.connect=socket.socket.connect_ex=socket.create_connection=socket.getaddrinfo=blocked
    try:
        initialize()
        result=evaluate(json.load(sys.stdin)['expressions'])
        json.dump(result,sys.stdout)
        return 0
    except Exception:
        json.dump(dict(error='MATH_EVALUATOR_FAILURE'),sys.stdout)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
