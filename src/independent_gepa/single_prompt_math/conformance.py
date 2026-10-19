"""Independent V6 budget, telemetry, cost-prefix and native RNG reconciliation."""
import random
from types import SimpleNamespace

from gepa.core.data_loader import ensure_loader
from gepa.strategies.batch_sampler import EpochShuffledBatchSampler
from gepa.strategies.candidate_selector import CurrentBestCandidateSelector, ParetoCandidateSelector

from .common import read
from .telemetry import frontier, native_value_at, metadata_counts
from gepa.gepa_utils import remove_dominated_programs
from .tokens import TokenLedger
from ..protocol import ProtocolViolation


def require(condition, category):
    if not condition:
        raise ProtocolViolation(category)


def reconcile_v6(directory, config, splits):
    from pathlib import Path
    from . import posthoc
    policy=posthoc.load_policy(Path(__file__).resolve().parents[3],config['posthoc_policy'])
    require(read(directory/'posthoc_content.json')==posthoc.audit_run(directory,splits['optimize'],policy,persist=False),
            'AUDIT_INDEPENDENT_POSTHOC_CONTENT')
    cells = {}
    watches = {}
    for arm in config['arms']:
        for repeat in config['repeat_ids']:
            folder = directory / arm / f'repeat_{repeat}'
            events = read(folder / 'mechanism_events.json')
            cells[(arm, repeat)] = (folder, events)
            for event in events:
                watches.setdefault(event['accounting_tip_sha256'], set()).add((arm, repeat))
    tokens = TokenLedger.replay(directory, watches)
    for (arm, repeat), (folder, events) in cells.items():
        native = read(folder / 'native_result.json')
        selected = read(folder / 'selection.json')
        budget = read(folder / 'native_budget.json')
        iterations = read(folder / 'iterations.json')
        curves = read(folder / 'budget_curves.json')
        require(budget['limit'] == config['native_logical_budget'] and 0 <= budget['used'] <= budget['limit'], 'AUDIT_NATIVE_BUDGET_LIMIT')
        require(budget['remaining'] == budget['limit'] - budget['used'] and budget['utilization'] == budget['used']/budget['limit'], 'AUDIT_NATIVE_BUDGET_ARITHMETIC')
        require(budget['used'] == native['total_metric_calls'] == selected['native_metric_calls'], 'AUDIT_NATIVE_BUDGET_COUNTERS')
        require(selected['native_budget'] == {k:v for k,v in budget.items() if k != 'batches'}, 'AUDIT_SELECTION_BUDGET')
        previous = 0
        for batch in budget['batches']:
            require(batch['before'] == previous and batch['after'] == previous + batch['size'] <= budget['limit'], 'AUDIT_NATIVE_BATCH_ADMISSION')
            previous = batch['after']
        require(previous == budget['used'], 'AUDIT_NATIVE_BATCH_SUM')
        require(budget['complete_iteration_reserve'] == len(splits['validation']) + 2*config['reflection_minibatch_size'], 'AUDIT_COMPLETE_ITERATION_RESERVE')
        if budget['stop_reason'] in ('budget_exhausted', 'insufficient_complete_iteration_budget'):
            require(budget['remaining'] < budget['complete_iteration_reserve'], 'AUDIT_BUDGET_STOP_REASON')
        elif budget['stop_reason'] == 'proposal_safety_limit':
            require(len(iterations) >= config['max_native_proposals'], 'AUDIT_PROPOSAL_SAFETY_STOP')
        else:
            raise ProtocolViolation('AUDIT_UNKNOWN_NATIVE_STOP')
        require(len(iterations) <= config['max_native_proposals'], 'AUDIT_NATIVE_SAFETY_LIMIT')
        require(selected['tokens'] == tokens.view('search', arm, repeat), 'AUDIT_CELL_TOKEN_ACCOUNTING')
        if 'test' in splits and (folder/'test_result.json').exists():
            measured=read(folder/'test_accounting.json')
            require(measured['arm']==arm and measured['repeat_id']==repeat and measured['wall_seconds']>=0
                and measured['tokens']==tokens.view('test',arm,repeat),'AUDIT_TEST_TOKEN_ACCOUNTING')
        scores = [{int(k):v for k,v in r.items()} for r in native['val_subscores']]
        availability = [len(splits['validation'])] + [n + len(splits['validation']) for n in native['discovery_eval_counts'][1:]]
        archive_events = [e for e in events if e['event'] == 'archive_available']
        require(len(archive_events) == len(scores), 'AUDIT_ARCHIVE_AVAILABILITY_COUNT')
        require([e['native_metric_calls'] for e in archive_events] == availability, 'AUDIT_FULL_COMPLETION_COORDINATES')
        previous_budget = previous_cost = -1
        for event in events:
            actual = tokens.watched.get(event['accounting_tip_sha256'], {}).get((arm, repeat))
            require(actual is not None and event['search_tokens'] == actual['standalone_attributed']['accounted_tokens']
                    and event['actual_dispatch_search_tokens'] == actual['actual_dispatch']['accounted_tokens'], 'AUDIT_COST_PREFIX_FUTURE_LEAK')
            used = event['native_metric_calls']
            require(previous_budget <= used <= budget['used'] and event['search_tokens'] >= previous_cost, 'AUDIT_NONMONOTONE_CURVE')
            available = [v for v,n in zip(native['val_aggregate_scores'],availability) if n <= used]
            require(event['best_score'] == (max(available) if available else None), 'AUDIT_CURVE_FUTURE_WINNER')
            active=scores[:len(available)]
            mapping=frontier(active) if active else {}
            filtered=remove_dominated_programs(mapping,available) if mapping else {}
            expected_front=len(set().union(*mapping.values())) if mapping else 0
            expected_sampling=len(set().union(*filtered.values())) if filtered else 0
            discoveries=sum(available[i]>max(available[:i]) for i in range(1,len(available)))
            nonbest=sum(r['strictly_below_aggregate_best'] for r in iterations if r['iteration']<=event['iteration'])
            require(event['frontier_candidates']==expected_front and event['sampling_frontier_candidates']==expected_sampling
                and event['new_best_discoveries']==discoveries and event['nonbest_parent_selections']==nonbest,
                'AUDIT_MECHANISM_PREFIX_COUNTS')
            previous_budget, previous_cost = used, event['search_tokens']
        require(curves['events'] == events, 'AUDIT_CURVE_EVENT_IDENTITY')
        expected = [{'budget':b,'best_score':native_value_at(events,b),'actual_terminal_spend':budget['used'],
                     'terminal_before_checkpoint':budget['used']<b} for b in config['budget_milestones']]
        require(curves['native_checkpoints'] == expected, 'AUDIT_BUDGET_MILESTONE')
        rng = random.Random(config['seed'])
        selector = ParetoCandidateSelector(rng) if config['selectors'][arm] == 'pareto' else CurrentBestCandidateSelector()
        sampler = EpochShuffledBatchSampler(config['reflection_minibatch_size'], rng)
        loader = ensure_loader(splits['optimize'])
        frequencies = {}
        previous_budget=len(splits['validation'])
        proposals=read(folder/'proposals.json')
        for row in iterations:
            averages = row['pool_validation_scores_before']
            parent = row['parent_native_index']
            best = averages.index(max(averages))
            subset = scores[:len(averages)]
            front = frontier(subset)
            state = SimpleNamespace(program_full_scores_val_set=averages,program_candidates=native['candidates'][:len(averages)],
                per_program_tracked_scores=averages,get_pareto_front_mapping=lambda:front,i=row['iteration']-1)
            require(selector.select_candidate_idx(state) == parent and sampler.next_minibatch_ids(loader,state) == row['minibatch_ids'], 'AUDIT_NATIVE_RNG_TRACE')
            frequencies[parent] = frequencies.get(parent,0)+1
            p,b = subset[parent],subset[best]
            unique = [q for q in p if p[q] == 1 and b[q] == 0]
            require(row['aggregate_best_index'] == best and row['strictly_below_aggregate_best'] == (averages[parent]<max(averages))
                    and row['parent_only_correct'] == len(unique) and row['shared_correct'] == sum(p[q] == b[q] == 1 for q in p)
                    and row['best_only_correct'] == sum(p[q] == 0 and b[q] == 1 for q in p)
                    and row['parent_only_metadata'] == metadata_counts(splits['validation'],unique)
                    and row['parent_selection_frequency'] == frequencies[parent], 'AUDIT_PARENT_COMPLEMENTARITY')
            proposal=next((p for p in proposals if p['iteration']==row['iteration']),None)
            amount=config['reflection_minibatch_size']*(1+int(proposal is not None)) + len(splits['validation'])*int(row.get('full_validation',False))
            require(row['generated']==(proposal is not None) and row['budget_before']==previous_budget
                and row['budget_after']==previous_budget+amount and row['mutation_native_evaluations']==amount
                and row['mutation_search_tokens']==row['search_tokens_after']-row['search_tokens_before']>=0,
                'AUDIT_MUTATION_COST_AND_FUNNEL')
            previous_budget=row['budget_after']
            if row.get('full_validation'):
                child = row['child_native_index']
                c = scores[child]
                expected = {'gained_vs_parent':sum(c[q]==1 and p[q]==0 for q in c),'lost_vs_parent':sum(c[q]==0 and p[q]==1 for q in c),
                    'gained_vs_best':sum(c[q]==1 and b[q]==0 for q in c),'lost_vs_best':sum(c[q]==0 and b[q]==1 for q in c),
                    'child_is_new_aggregate_best':native['val_aggregate_scores'][child] > max(averages)}
                expected.update(net_vs_parent=round(sum(c.values())-sum(p.values())),net_vs_best=round(sum(c.values())-sum(b.values())))
                require(all(row[k] == v for k,v in expected.items()), 'AUDIT_DESCENDANT_CONVERSION')
    return tokens
