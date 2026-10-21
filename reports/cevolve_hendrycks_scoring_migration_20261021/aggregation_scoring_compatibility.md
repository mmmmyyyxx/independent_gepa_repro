# Aggregation versus correctness compatibility

Status: **DIFFERENT_RELATIONS_DISCLOSED; AGGREGATION_UNCHANGED**.

The sole correctness contract is `cevolve_hendrycks_math_v1`. Every selected
answer is graded by its pinned boxed extraction and finite string normalization.
Math-Verify is not a second correctness judge or a fallback scorer.

The existing team aggregator remains gold-blind equal-weight equivalence
plurality with tie-abstention. Its equivalence classes use the preserved pinned
mathematical relation. It does not use the new scorer's finite normalization as
its grouping relation. Thus symbolic computation may still occur during team
aggregation, although single-Prompt correctness no longer invokes it.

## Observable consequence and offline control

A synthetic group can contain x+x and 2x in the same mathematical vote class.
With reference 2x, the new finite-normalization score accepts 2x and rejects x+x.
The existing aggregator chooses the first representative of its winning class;
swapping these two members can therefore change selected-answer correctness.
Both repositories' Hendrycks integration tests exercise this order sensitivity.
It is not a claim about any historical model answer or a rewritten old grade.

| Aspect | Current retained team policy | C-EVOLVE paper description |
|---|---|---|
| Grouping | Pinned mathematical equivalence | Most frequent extracted answer; complete implementation not supplied |
| Decision | Plurality, ties abstain | Strict majority; otherwise random choice among candidates |
| Correctness of chosen answer | Sole Hendrycks scorer | Extracted-answer accuracy |
| Random fallback added by this migration | No | Described in Appendix B.2 |

The two relations are not interchangeable. An equivalence class need not have
uniform correctness under the new finite string contract. No automatic switch
to string-based grouping, strict-majority consensus, random fallback, member
reordering or gold-aware representative selection is made. These would require
a separate scientific protocol, identities, tests and any subsequent API grant.

## Validity and execution boundaries

The new prediction-validity flag means successful boxed extraction, not symbolic
parseability. A syntactically extracted payload outside the old voting domain
can therefore reach the unchanged relation-consistency/abstention or resource-error
paths. The finite correctness scorer accepts a broader syntactic domain than the
vote comparator. No mathematical validation is reintroduced as a correctness gate.
Existing bounded invalid-output recovery and request accounting remain project
adaptations; a logical evaluation is not necessarily a single raw generation.

## Current source routes

- multi_agent_diversity: `search/scientific_aggregation.py` uses the benchmark's
  gold-blind `equivalent`; `benchmarks/math_domain_v2.py` supplies that relation.
  Member and final correctness use its `score_member_output`, which delegates to
  `math_scoring/score.py`.
- independent_gepa_repro: `math_comparison/benchmark.py` retains team vote
  equivalence and routes selected-output correctness to `math_scoring/score.py`.
- Single-Prompt GEPA and Gradient-Pattern runs do not use a team vote.

The migration therefore completes correctness unification, not a complete
reproduction of C-EVOLVE consensus. Historical scores and voting results stay
immutable. The relevant public source is [C-EVOLVE Appendix B.2](https://arxiv.org/html/2509.23331v1).
Model API calls for this compatibility review: **0**.
