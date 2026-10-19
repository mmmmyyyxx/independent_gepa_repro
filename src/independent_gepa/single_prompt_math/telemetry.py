"""Observation-only native callbacks and availability-aware budget/token curves."""
from collections import Counter

from gepa.gepa_utils import remove_dominated_programs

from .common import Abort, write
from .search import History, fail_closed


def frontier(scores):
    return {q: {i for i, row in enumerate(scores) if row[q] == max(r[q] for r in scores)} for q in sorted(scores[0])}


def metadata_counts(rows, ids):
    counts = Counter()
    for index in ids:
        content = rows[index].get('content', {})
        # Existing canonical fields only; no model inference or fabricated taxonomy.
        counts[(content.get('type'), content.get('level'))] += 1
    return [{'type': kind, 'level': level, 'count': n,
             'provenance': 'existing_canonical_content' if kind is not None or level is not None else 'unavailable'}
            for (kind, level), n in sorted(counts.items(), key=lambda x: str(x[0]))]


def native_value_at(events, budget):
    available = [r for r in events if r['native_metric_calls'] <= budget and r['best_score'] is not None]
    return available[-1]['best_score'] if available else None


def token_value_at(events, tokens):
    # At equal cost use the first observed prefix at that coordinate, never a
    # future zero-increment event backfilled into an earlier checkpoint.
    available = None
    for row in events:
        cost = row['search_tokens']
        if cost > tokens:
            break
        available = row['best_score']
        if cost == tokens:
            break
    return available


class MechanismHistory(History):
    def __init__(self, adapter, directory, validation_rows, budget, milestones):
        super().__init__(adapter, directory)
        self.validation_rows = validation_rows
        self.budget = budget
        self.milestones = milestones
        self.score_rows = []
        self.averages = []
        self.events = []
        self.frequencies = Counter()
        self.nonbest = 0
        self.newbests = 0

    def checkpoint(self, event):
        cost = self.adapter.runtime.token_snapshot(self.adapter.repeat)
        mapping = frontier(self.score_rows) if self.score_rows else {}
        raw_size = len(set().union(*mapping.values())) if mapping else 0
        filtered = remove_dominated_programs(mapping, self.averages) if mapping else {}
        size = len(set().union(*filtered.values())) if filtered else 0
        self.events.append({'sequence': len(self.events), 'event': event,
            'iteration':self.iterations[-1]['iteration'] if self.iterations else 0,
            'accounting_tip_sha256':self.adapter.runtime.last_hash,
            'native_metric_calls': self.budget.used,
            'search_tokens': cost['standalone_attributed']['accounted_tokens'],
            'actual_dispatch_search_tokens': cost['actual_dispatch']['accounted_tokens'],
            'best_score': max(self.averages) if self.averages else None,
            'frontier_candidates': raw_size, 'sampling_frontier_candidates': size,
            'nonbest_parent_selections': self.nonbest, 'new_best_discoveries': self.newbests})

    @fail_closed
    def on_valset_evaluated(self, event):
        index = event['candidate_idx']
        scores = dict(event['scores_by_val_id'])
        if index != len(self.score_rows) or len(scores) != len(self.validation_rows):
            raise Abort('INCOMPLETE_NATIVE_VALIDATION_TELEMETRY')
        if set(scores.values()) - {0.0, 1.0}:
            raise Abort('NONBINARY_NATIVE_SCORE_TELEMETRY')
        avg = sum(scores.values()) / len(scores)
        if abs(avg - event['average_score']) > 1e-12:
            raise Abort('NATIVE_SCORE_TELEMETRY_AGGREGATE')
        if self.averages and avg > max(self.averages):
            self.newbests += 1
        self.score_rows.append(scores)
        self.averages.append(avg)
        self.checkpoint('archive_available')

    @fail_closed
    def on_iteration_start(self, event):
        super().on_iteration_start(event)
        self.iterations[-1]['budget_before'] = self.budget.used
        self.iterations[-1]['search_tokens_before'] = self.adapter.runtime.token_snapshot(self.adapter.repeat)['standalone_attributed']['accounted_tokens']

    @fail_closed
    def on_candidate_selected(self, event):
        super().on_candidate_selected(event)
        parent = event['candidate_idx']
        best = self.averages.index(max(self.averages))
        p, b = self.score_rows[parent], self.score_rows[best]
        below = self.averages[parent] < self.averages[best]
        self.nonbest += below
        self.frequencies[parent] += 1
        unique = [q for q in p if p[q] == 1 and b[q] == 0]
        self.iterations[-1].update(aggregate_best_index=best, aggregate_best_score=self.averages[best],
            strictly_below_aggregate_best=below, different_from_first_argmax=parent != best,
            tied_alternative_best=parent != best and not below,
            shared_correct=sum(p[q] == b[q] == 1 for q in p), parent_only_correct=len(unique),
            best_only_correct=sum(p[q] == 0 and b[q] == 1 for q in p),
            parent_only_metadata=metadata_counts(self.validation_rows, unique),
            parent_selection_frequency=self.frequencies[parent])
        self.checkpoint('parent_selected')
        self.iterations[-1]['frontier_candidates'] = self.events[-1]['frontier_candidates']
        self.iterations[-1]['sampling_frontier_candidates'] = self.events[-1]['sampling_frontier_candidates']

    @fail_closed
    def on_evaluation_skipped(self, event):
        self.iterations[-1]['native_skip_reason'] = event['reason']

    @fail_closed
    def on_candidate_accepted(self, event):
        super().on_candidate_accepted(event)
        row = self.iterations[-1]
        child = event['new_candidate_idx']
        best = row['aggregate_best_index']
        parent = row['parent_native_index']
        c, p, b = self.score_rows[child], self.score_rows[parent], self.score_rows[best]
        row.update(child_native_index=child, full_validation=True, local_gate_passed=True,
            child_is_new_aggregate_best=self.averages[child] > row['aggregate_best_score'],
            gained_vs_parent=sum(c[q] == 1 and p[q] == 0 for q in c),
            lost_vs_parent=sum(c[q] == 0 and p[q] == 1 for q in c),
            gained_vs_best=sum(c[q] == 1 and b[q] == 0 for q in c),
            lost_vs_best=sum(c[q] == 0 and b[q] == 1 for q in c),
            net_vs_parent=round((self.averages[child] - self.averages[parent]) * len(c)),
            net_vs_best=round((self.averages[child] - self.averages[best]) * len(c)))

    @fail_closed
    def on_candidate_rejected(self, event):
        super().on_candidate_rejected(event)
        self.iterations[-1].update(local_gate_passed=False, full_validation=False)

    @fail_closed
    def on_iteration_end(self, event):
        if event['state'].total_num_evals != self.budget.used:
            raise Abort('NATIVE_BUDGET_END_MISMATCH')
        row = self.iterations[-1]
        row['generated'] = self.pending is not None
        self.checkpoint('iteration_complete')
        row.update(budget_after=self.budget.used, search_tokens_after=self.events[-1]['search_tokens'],
                   mutation_native_evaluations=self.budget.used - row['budget_before'],
                   mutation_search_tokens=self.events[-1]['search_tokens'] - row['search_tokens_before'])
        super().on_iteration_end(event)

    @fail_closed
    def save(self):
        super().save()
        write(self.directory / 'native_budget.json', self.budget.summary())
        write(self.directory / 'mechanism_events.json', self.events)

    def finish(self):
        self.checkpoint('search_complete_including_diagnostics')
        self.save()
        write(self.directory / 'budget_curves.json', {
            'availability_policy': 'complete_archive_only; no partial Full or future backfill',
            'native_checkpoints': [{'budget': b, 'best_score': native_value_at(self.events, b),
                'actual_terminal_spend': self.budget.used, 'terminal_before_checkpoint': self.budget.used < b}
                for b in self.milestones],
            'events': self.events,
            'token_axis': 'standalone attributed search input+output+conservative unknown/retry bounds',
            'comparison_label': 'Matched solver-evaluation budget, not exactly matched total compute.'})
