"""Sanitized comparison evidence, with validity and efficacy separated."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..audit import audit_public_paths
from ..protocol import ProtocolViolation
from .contract import read,write,file_hash

def build_report(public: Path,bundle: Path,selections: list[dict[str,Any]],rows: list[dict[str,Any]],
                 baselines: list[dict[str,Any]],accounting: dict[str,Any],identity: str,source: str) -> None:
    public.mkdir(parents=True,exist_ok=True)
    a4=read(bundle/'audit_only/a4_summary.json')
    a4_local=read(bundle/'audit_only/a4_local_budget.json')['logical_local_metrics']
    safe_windows=[{k:v for k,v in s.items() if k not in {'selected','native_validation_ids'}} for s in selections]
    best=max(rows,key=lambda r:(r['candidate_member_correct'],-r['original_correct_lost']),default=None)
    admissible=sum(r['v22_admissible'] for r in rows)
    positive=sorted((r for r in rows if r['NET_POSITIVE']),key=lambda r:(r['window'],r['generation'] or 0))
    first_positive=(sum(s['search_metric_count'] for s in selections if s['window']<positive[0]['window'])
                    +positive[0]['discovery_search_metric']) if positive else None
    summary={'experiment_id':'math_a4_matched_gepa_seed81_20261008','execution_status':'EXECUTION_COMPLETE',
        'integrity':'VALID','identity':identity,'source_sha':source,'full_candidates':len(rows),
        'completed_windows':len(selections),'proposal_generations':sum(s['proposal_count'] for s in selections),
        'search_metric_evaluations':sum(s['search_metric_count'] for s in selections),
        'actual_solver_logical_evaluations':sum(s.get('actual_solver_logical_evaluations',s['search_metric_count']) for s in selections),
        'guard_rejection_metric_scores':sum(s.get('guard_rejection_metric_scores',0) for s in selections),
        'best_member_correct':best['candidate_member_correct'] if best else None,
        'pure_repairs':sum(r['PURE_REPAIR'] for r in rows),'net_positive':sum(r['NET_POSITIVE'] for r in rows),
        'v22_admissible':admissible,'team_vote_gain':max((r['team_vote_delta'] for r in rows),default=0),
        'oracle_gain':max((r['oracle_delta'] for r in rows),default=0),
        'local_improving_windows':sum(s['native_best_score']>s['native_initial_score'] for s in selections),
        'duplicate_generations':sum(s['proposal_count']-s['unique_proposal_count'] for s in selections),
        'first_observed_net_positive_discovery_search_metric':first_positive,
        'shadow_calls':0,'validation_calls':0,'test_calls':0,'team_commits':0,
        'budget_normalization':{'primary':'36_logical_search_metrics_and_6_generation_caps_per_window',
            'gepa_native_validation_size':6,'gepa_train_size':60,
            'GEPA_step_reserve':12,'merge_enabled':False,'full_audit_per_window_cap':4},
        'classification':{'useful_observed_candidate':'SUPPORTED' if admissible else 'NOT SUPPORTED',
            'automatic_preservation_safe_repair':'SUPPORTED' if any(r['PURE_REPAIR'] for r in rows) else 'NOT SUPPORTED',
            'search_component_causal_advantage':'INCONCLUSIVE','promotion_bottleneck':'INCONCLUSIVE',
            'generalization':'INCONCLUSIVE'},'accounting':accounting}
    write(public/'summary.json',summary); write(public/'candidate_metrics.json',rows)
    write(public/'search_windows.json',safe_windows); write(public/'realization_diagnostics.json',baselines)
    table='\n'.join(f'| {r["candidate_id"]} | {r["member"]} | {r["candidate_member_correct"]}/60 | '
        f'{r["original_correct_retained"]} | {r["original_correct_lost"]} | {r["newly_correct"]} | '
        f'{r["net_competence_gain"]:+d} | {r["team_vote_after"]}/60 | {r["oracle_after"]}/60 | '
        f'{"YES" if r["v22_admissible"] else "NO"} |' for r in rows)
    next_experiment=('A separately authorized GEPA Layer1 plus A4 Layer2 hybrid, starting from a fresh frozen attempt.'
        if admissible else 'A matched feedback-format ablation with larger nonadaptive local evaluation support; keep the Solver and Full60 audit fixed.')
    report=f'''# Independent GEPA versus A4: MATH Optimize60

The seven frozen search windows completed. {len(rows)} changed candidates received independent Full60 evaluation;
{admissible} were compatible with the measured Optimize V2.2 transition gate.
This is development-set evidence. Shadow safety and actual deployment were not tested.

## A. Reproduction fidelity

The untouched official GEPA v0.1.1 checkout is pinned to b4dbb55b7601dac448cdb836d5a401ca7d9eb920.
Native reflection, epoch-shuffled minibatches, strict minibatch survival, instance Pareto parent selection,
candidate archive, frontier and best-candidate selection were used. Merge was disabled as a supported native option.
The adapter provides only current-member Optimize feedback. The native mutation template has a declared task-boundary
suffix forbidding example copying and output-interface changes. The result is an independent GEPA reproduction
under this matched task contract; it is not a replication of GEPA paper benchmark numbers.

The MATH workers copy A4's pinned evaluator without algorithm edits; only local imports change.
No sibling optimizer modules are imported. The comparison reads only its frozen bundle during execution.

## B. Frozen protocol

Seed81; targets [0,1,3,2,4,0,1]; GEPA seeds 81000 through 81006. Every window resets to the minimal initial prompt.
Optimize60 identity: {read(bundle/'manifest.json')['optimize_membership_hash']}.
Solver qwen3-8b: thinking false, temperature0.2, top_p0.8, top_k20, min_p0,
presence/frequency penalties0, max_tokens3600. Reflection qwen3.7-flash: thinking false,
temperature0.7, top_p0.8, top_k20, presence penalty1.5, frequency penalty0, max_completion_tokens1800.
The A4 immutable system/user format, directed gold-first MATH equivalence V2, four-draw first-valid recovery,
timeout120, SDK retries0 and frozen transport retry policy are preserved.

Native trainset is Optimize60; native valset is six outcome-independent hash-selected Optimize examples per window.
Each window has caps of36 native metric scores and6 proposal generations, reserving12 metrics before each step.
Contract-rejected zero scores count against native metrics but do not dispatch Solver evaluations.
The reserve can leave unused metrics. This is a bounded pilot, not saturation.
Native best and leading Pareto candidates are selected first, followed by hash-ordered distinct Solver-evaluated
proposals, including native-rejected proposals; at most4 changed candidates per window.
All selections were sealed before any independent Full60 audit. Those audits never return to GEPA.
Exact resolved outputs may be reused within one window/member/attempt across stages; other windows and historical
attempts cannot share realizations. Historical A4 peers are explicitly frozen audit-only measurements.
They never enter optimization. Full60 P0 is freshly measured per window to diagnose realization drift.

Source {source}; execution identity {identity}. Token ceiling3,000,000; physical attempt ceiling9,000.
Fresh single-use authorization comes from this task, not A4's closed scope or remaining authorization.
Shadow, Validation, Test and atomic team commits all have zero calls/actions.

## C. Search results and accounting

Generated {summary['proposal_generations']} proposals; {summary['search_metric_evaluations']} native metric scores;
{summary['actual_solver_logical_evaluations']} actual logical Solver evaluations and
{summary['guard_rejection_metric_scores']} guard-rejection zero scores.
Native local improvement occurred in {summary['local_improving_windows']}/7 windows;
duplicate generations: {summary['duplicate_generations']}. First observed net-positive discovery among
the audited pool occurred by cumulative search metric {first_positive if first_positive is not None else 'not observed'}.
This does not locate the first useful unmeasured proposal.
Physical attempts {accounting['physical_attempts']}; charged tokens {accounting['charged_tokens']}.
The role ledger, journal hash-chain, request/response receipts and independent reconciliation passed.
Search windows, local trajectories, archive scores and retained specialists are reported in search_windows.json.
Rejected candidates are represented in independent audits only through the preregistered selection rule.
Duplicate generations and contract rejections are counted per window. Private histories retain complete feedback,
local candidate score batches, parent choices and native checkpoints.

## D. Independent Full60 quality

| Candidate | Target | Correct | Retained | Lost | New | Net | Vote | Oracle | V2.2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
{table}

Retained/lost/new above refer to the original A4 22-correct realization. Candidate metrics separately include
fresh-parent retention and changes. Fresh-parent realization differences must be considered before causal attribution.
The V2.2 safety binding treats terminal invalid predictions through incorrectness; there is no extra invalid-count veto.
V2.2 compatibility is a measured Optimize diagnostic, not an unmeasured Shadow-pass or deployability claim.
The zero-API structural preflight found {accounting['structural_vote_preflight']['historical_all_invalid_examples']}
historical all-invalid examples. With unanimous per-example initial correctness, single-member Vote gain is
bounded by that count: one correct vote cannot beat or break a tie against any remaining valid wrong peer.
Candidate metrics distinguish new correctness on historical terminal-invalid examples from other repairs.

## E. Direct comparison

| Metric | A4 seven completed opportunities | Independent GEPA |
|---|---:|---:|
| Proposal generations | 42 | {summary['proposal_generations']} |
| Logical local budget cap | 252 | 252 |
| Actual logical local Solver evaluations, including roots | {a4_local} | {summary['actual_solver_logical_evaluations']} |
| Changed Full60 candidates measured | 2 | {len(rows)} |
| Best observed Full member correct | 19/60 | {str(summary['best_member_correct'])+'/60' if best else 'none'} |
| Best observed net competence gain | -3 | {max((r['net_competence_gain'] for r in rows),default=0):+d} |
| Above22 Full candidates | 0/2 | {sum(r['candidate_member_correct']>22 for r in rows)}/{len(rows)} |
| Optimize V2.2 compatible | 0/2 | {admissible}/{len(rows)} |
| Largest replacement Vote gain | 0 | {summary['team_vote_gain']} |
| Largest replacement Oracle gain | +2 | {summary['oracle_gain']:+d} |
| Charged tokens | 480,991 initialization plus seven; 543,976 whole interrupted attempt | {accounting['charged_tokens']} |
| GEPA search-only charged tokens | not separated from A4 setup/progressive evaluation | {accounting['search_accounting']['charged_tokens']} |

A4's other40 proposals have no Full result;19/60 is not the best score over all42 proposals.
Independent Full audits add measurement cost; they are not search feedback. Physical and logical counts differ
because cache hits and invalid-output recovery are governed separately.
A4's actual local support was four examples per window; seven root evaluations plus evaluated children
reconstruct {a4_local} logical metrics from frozen lineages. Both methods had the same252 cap, but actual
usage differs. GEPA's native train60/val6 support and parent remeasurement also differ from A4's focused panel.
A4 TeamProbe promotion was not replayed: its outcome for these candidates remains NOT_MEASURED.

## F. Scientific conclusion

ESTABLISHED: the frozen independent search and candidate-level Full audits executed with reconciled accounting.
Useful observed candidate discovery: {summary['classification']['useful_observed_candidate']}.
Automatic preservation-safe repair: {summary['classification']['automatic_preservation_safe_repair']}.
Component causality, A4 promotion error and generalization: INCONCLUSIVE.
These are seven bounded windows on an already-used development set and one hosted-model realization per lane;
they neither prove global search failure nor isolate reflection versus Pareto versus feedback mechanisms.

## G. Next experiment

{next_experiment}
No further experiment or hybrid arm is automatically authorized.
'''
    (public/'README.md').write_text(report,encoding='utf-8',newline='\n')
    findings=audit_public_paths([public])
    if findings: raise ProtocolViolation('PUBLIC_ARTIFACT_SANITIZATION_FAILURE')
    write(public/'sanitization.json',{'status':'PASS','sensitive_content':'omitted'})
    write(public/'sha256_manifest.json',{p.name:file_hash(p) for p in sorted(public.iterdir()) if p.is_file()})
