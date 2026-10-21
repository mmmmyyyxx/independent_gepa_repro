> HISTORICAL / RETIRED: this document describes the former three-policy audit infrastructure. Its online implementations and selectors have been retired. The sole current contract is [cevolve_hendrycks_math_v1](math_scoring_cevolve_hendrycks_v1.md); predecessor source and configs are recoverable only from docs/archive/scoring/pre_hendrycks_20261021/. Historical reports remain unchanged.

# Unified MATH scoring V1: opt-in offline infrastructure

Status: **OFFLINE_IMPLEMENTATION_ONLY; NOT_ACTIVATED**. This document does not
change the current benchmark protocol, member/team measurements, GEPA selection,
held-out access, recovery, or any frozen experiment. No A2 Test execution is allowed.
The user separately authorized implementation in both repositories; neither imports
the other's runtime. Historical V7 sources, policies, caches and results remain intact.

## Interfaces and versions

The canonical implementation is `multi_dataset_diverse_rl.math_scoring`. Its
byte-matched mirror is `independent_gepa.math_scoring`; only the local unchanged
kernel import differs. Both reuse the pinned existing Math-Verify worker functions
for scalar parsing/equivalence instead of implementing another symbolic algebra
engine. Copy provenance and per-module hashes accompany the offline audit.

An explicit `Policy` is required: there is no new production default. Policy
identities and full resource/dependency hashes are in
`configs/math_unified_scoring_v1.json` in each repository.

```python
from multi_dataset_diverse_rl.math_scoring import MathScorer, policy_for

with MathScorer(policy_for("math_semantic_v1")) as scorer:
    result = scorer.score_math("1/2", "Final answer: 0.5")
    # Only result.binary() may project a determined outcome into a score.
    # It raises UnresolvedMathScore on every unresolved state.
    relation = scorer.compare_answers("1/2", "0.5")
```

The GEPA import uses `independent_gepa` instead. `score_math(reference, prediction,
policy)` is also a convenience one-call facade. Batch callers retain a context to
avoid repeated interpreter startup. The `OfflineMathAdapter` is an unregistered
future member/Validation/Test/voting integration seam, not current composition.

`ScoreResult` carries policy ID/hash, extracted and normalized values, prediction
validity, status, nullable correctness, reason, stage, elapsed milliseconds,
anonymous reference/input identities and cache/kernel accounting. Raw values are
private. Truth-coercing a result is forbidden; an evaluator failure is never score0.

| Status | correct | Meaning |
|---|---|---|
| CORRECT | true | Confirmed by the named policy, not necessarily mathematical equivalence under an exact-string policy |
| INCORRECT | false | Determined mismatch under the named policy |
| INVALID_OUTPUT | false | Explicit declaration/finish protocol violated |
| UNSUPPORTED | null | Unsupported type, ambiguity, expression or finite complexity limit |
| EVALUATOR_TIMEOUT | null | Fixed wall budget expired; saved response retained |
| INFRASTRUCTURE_FAILURE | null | Worker, dependency, memory or protocol fault |
| REFERENCE_INVALID | null | Reference violates the applicable data/admission contract |

Finite-domain or computational limits do not silently become output errors. No
operation removes unresolved cases from a formal denominator or requests a new
Solver realization. Any future integration must define a frozen incomplete-run
policy rather than applying `correct or False`.

## Three distinct scoring policies

### paper_extracted_exact_v1

Gold-blind declaration extraction, presentation-only normalization and exact
string comparison. It imports neither SymPy nor Math-Verify. Display delimiters,
balanced outer boxes, spacing commands, `left/right` sizing and `dfrac/tfrac`
display variants can normalize. Signs, case, variable names, brackets, tuple/set
distinctions, endpoints and element order are retained. Alphanumeric whitespace
separators are preserved; `1 2` is not silently joined into `12`.

This metric intentionally does not equate `1/2` and `0.5` or prove algebraic
identities. Reference validation here is a bounded structural input contract, not
an independent mathematical proof of a dataset label. It is a candidate primary
metric for a new paper-comparison experiment, requiring review and fresh freeze.

### maspo_compat_v1

Isolated compatibility reference to the two pure functions in
[MASPO utils.py at90e8c6f](https://github.com/wangzx1219/MASPO/blob/90e8c6fcc08c1e8f9a61740b296d4fab9e09e2d2/utils.py).
Their ASTs are preserved and compared with the downloaded fixed official source.
The upstream final no-judge MATH path compares normalized extracted output with
normalized gold; choice-task substring matching is not part of MATH scoring.
Its optimizer's LLM comparisons are a separate mechanism, not this accuracy metric.

Compatibility deliberately keeps last answer-tag selection, first limited-nesting
box selection, last-line30-character fallback, bracket conversion, case folding,
and sorting of bare integer lists. For example, it can accept different interval
closures or `x` versus `X`. It is not mathematical evidence or approved for voting.
Its original extraction is the explicit reference-only exception to the shared
extractor; `ScoreResult` separately retains the unified extraction and its validity.
This exception is necessary for actual compatibility and is not hidden as a shared
production extraction rule. Original MASPO has no provider finish-reason check;
this reference preserves that fact within bounded admitted inputs.

### math_semantic_v1

The common extractor, explicit mathematical type checks, safe direct/closed
rational equality, then the unchanged pinned Math-Verify scalar kernel. Dependencies
are Math-Verify0.6.0, SymPy1.14.0, latex2sympy2_extended1.0.9, ANTLR4 runtime4.13.2,
mpmath1.3.0. No package is upgraded. Unsupported symbolic inputs remain unresolved.
The native adapter reuses the unchanged legacy presentation normalizer for Unicode
radical atoms/groups, minus and pi before native parsing. Policy A retains its
separate exact surface rules. Reused kernel functions, settings and presentation
normalization ASTs also enter the policy hash.
The AST identity omits only the empty type-parameter field added in Python3.12;
equivalent legacy functions share the same policy hash under the repositories'
Python3.11 and3.13 runtimes. Cross-runtime identity and saved-response decisions
are checked independently. Cached scoring results record zero new symbolic calls.

The project extension adds bounded typed containers and exact finite-rational
checks. Sets ignore order/duplicates; tuples and matrices retain order. Closed/
half-open interval endpoint inclusivity is retained. Relations cannot equal scalar
expressions. Numeric near-equality is not silently rounded into exact equality;
non-identical general floating expressions are left unsupported if not certified
by the bounded rational path. No new per-example power proof is introduced.

Two-component parentheses are ambiguous between ordered pairs and open intervals.
They return UNSUPPORTED unless the caller supplies explicit frozen type metadata,
for example `type_hints={"reference":"tuple","prediction":"tuple"}`. Hints must
agree with syntax and are part of cache identity; they may not be inferred by
matching the prediction to gold. Nested ambiguous forms without type evidence are
also unsupported. Three-component tuples and explicit finite sets/matrices do not
need that hint. Supporting broader typed annotations is a separate future policy.

Correctness calls always compare gold first, prediction second. Voting uses a
separate `compare_answers` API, checks type compatibility and both native directions,
returns nullable equivalence, and leaves asymmetric results unsupported. A scoring
boolean cannot silently become a voting equivalence relation.

## Shared final-answer extraction

The deterministic extractor takes no gold or scoring mode. It recognizes explicit
answer tags, balanced nested boxes including terminal inline boxes, answer/final
answer labels, explicit conclusions and supported multiline display forms.
Intermediate boxes are not selected as final declarations. Conflicting declared
payload strings are rejected using presentation-only canonicalization, without
symbolic or reference-guided winner selection. Mathematically equivalent but
different competing strings may therefore be conservatively rejected; this is a
documented output protocol choice, not a mathematical incorrectness assertion.
Earlier natural conclusions are working when an explicit label/tag exists; only
subsequent confirmations enter its final region. Without a label/tag, the last
deterministic conclusion/terminal box is used. All explicit competing labels/tags
remain subject to conflict checking regardless of their position.
An unlabelled conclusion must end the final region; subsequent unmarked reasoning
cannot cause fallback to an earlier working answer. A terminal balanced box has
its own boundary even when it occurs inside a natural-language conclusion.

Truncation, missing declarations, unclosed tags/boxes and malformed final boundaries
retain explicit reasons. Resource-limit cases remain unresolved. New extraction
is not retroactively applied to old scores, recovery positions or search decisions.

## Finite execution and caching

All calls run in supervised persistent local workers. Default limits are65,536
raw characters,2,048 expression characters,32 nesting/declarations/container items,
512 lexical/parsed nodes,256 integer digits, absolute literal exponent10,000,
8 seconds per request,10 seconds worker startup and1,024MiB process memory. The
literal rational-exponent limit is a resource guard, not an inequality certificate.
Startup and scoring deadlines are separately bounded; cleanup has bounded waits.

Windows uses a Job Object with process-memory and kill-on-close limits. The actual
worker PID is attached and awaited as well as a possible venv launcher PID. POSIX
workers set RLIMIT_AS before handling inputs. Socket calls are blocked before
math imports; credential-like environment values are removed. Windows does not
depend on signal.alarm. The pinned library's broken internal timeout wrapper is
disabled only in the supervised child, with no dependency-source edits.

A timeout kills/reaps the worker and its reader; a later input can start a new
bounded worker. There is one computational attempt per call, no infinite retries,
no model generation and no hidden timeout enlargement. Every typed unknown remains
visible. A bounded per-policy LRU binds operation, full policy/hash/dependency
identity, raw reference/prediction, finish reason and explicit type hints. Scoring
and voting cache identities are distinct. Policy hashes bind the
scoring/extraction/normalization/supervision component
bytes; a live scorer refuses a source change instead of reusing its old cache.
Cached result semantics are stable;
wall-time failure occurrence can still depend on machine load and is not a
mathematical false verdict.

## Paper comparison and limits

[C-EVOLVE, ICLR2026 Appendix B.2](https://proceedings.iclr.cc/paper_files/paper/2026/file/3f1351a10a3f904e6f3845a94275a909-Paper-Conference.pdf)
describes final-answer extraction followed by exact string matching. Its detailed
official extraction/normalization code was not located: provenance is
`paper_description_only`, not an exact author-code reproduction. Policy A is a
transparent project realization of that broad description. Policy B is the
separately pinned MASPO code-compatibility reference. Policy C's typed/rational
admission and supervised bounded execution are project extensions around fixed
[Math-Verify](https://github.com/huggingface/Math-Verify), not either paper's metric.

## Audit and migration

The [offline report](../reports/math_unified_scoring_v1_20261021/README.md) separates
all3,492 paid raw responses, their3,491 previously resolved three-way comparisons,
and2,700 historical terminal observations. The last is a subset of response
identities, not an additional disjoint accuracy denominator. A2's partial350 raw
responses never become a completed Test300 cell. Original replay outcomes and
counterfactual new-policy outcomes remain separate, with unresolved counts and
fixed-denominator bounds. No favorable score determines policy choice.

Before activation, the owner must choose the primary/secondary metric, final
declaration/conflict contract, dataset type annotations, unresolved-run behavior,
resource settings, semantic versus surface voting, and any compatibility reporting.
Then freeze new source SHA, policy/dependency hashes, data/memberships, cache and
scoring/voting read points with a fresh experiment identity and API authorization.
Old checkpoints, historical labels and consumed execution grants cannot be reused
as if the metric had stayed unchanged. Historical Test exposure remains disclosed.
The recommendation is to review A as a paper-comparison primary and C as a
mathematical secondary, reporting both transparently; B remains a reference only.
This recommendation does not activate any policy or authorize A2 Test continuation.
