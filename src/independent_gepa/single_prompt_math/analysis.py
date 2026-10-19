"""Preregistered paired analysis with shared-item correlation retained."""
import random
import statistics

from .telemetry import token_value_at
from ..protocol import ProtocolViolation


def paired(profiles, bootstrap_draws=2000):
    deltas = []
    per_repeat = []
    reference_ids = None
    for repeat in (1, 2, 3):
        strict, pareto = profiles[('strict_validation', repeat)], profiles[('native_pareto', repeat)]
        ids = [r['example_id'] for r in strict]
        if ids != [r['example_id'] for r in pareto] or (reference_ids is not None and ids != reference_ids):
            raise ProtocolViolation('PAIRED_TEST_MEMBERSHIP_ORDER')
        reference_ids = ids
        values = [int(p['correct']) - int(s['correct']) for s, p in zip(strict, pareto, strict=True)]
        deltas.append(values)
        per_repeat.append({'repeat_id': repeat, 'strict_correct': sum(r['correct'] for r in strict),
            'pareto_correct': sum(r['correct'] for r in pareto), 'difference': sum(values) / len(values),
            'corrected': values.count(1), 'regressed': values.count(-1), 'unchanged': values.count(0)})
    rng = random.Random(42)
    n = len(reference_ids)
    samples = []
    for _ in range(bootstrap_draws):
        repeats = [rng.randrange(3) for _ in range(3)]
        items = [rng.randrange(n) for _ in range(n)]
        samples.append(sum(deltas[r][i] for r in repeats for i in items) / (3 * n))
    samples.sort()
    effects = [r['difference'] for r in per_repeat]
    return {'identity': 'PAIRED_REPEAT_AND_ITEM_ANALYSIS_V6', 'per_repeat': per_repeat,
        'mean_difference': statistics.mean(effects), 'sample_standard_deviation': statistics.stdev(effects),
        'wins': sum(d > 0 for d in effects), 'ties': effects.count(0), 'losses': sum(d < 0 for d in effects),
        'descriptive_95_interval': [samples[int(.025 * len(samples))], samples[min(len(samples)-1, int(.975 * len(samples)))]],
        'interval_method': 'paired two-way repeat/item bootstrap; same item resample shared across sampled repeats',
        'bootstrap_seed': 42, 'bootstrap_draws': bootstrap_draws,
        'interpretation': 'Three fixed-optimizer-seed stochastic repeats; sparse repeat uncertainty. Descriptive interval, no stable superiority or significance declaration.'}


def align_tokens(curves):
    maximum = min(rows[-1]['search_tokens'] for rows in curves.values())
    grid = [maximum * k // 10 for k in range(1, 11)]
    return {'axis': 'standalone_attributed_total_search_accounted_tokens', 'common_support_max': maximum,
            'fixed_grid_rule': 'deciles of minimum terminal cost across all six cells; no result-based weighting',
            'cells': {name: [{'tokens': t, 'available_best_score': token_value_at(rows, t)} for t in grid]
                      for name, rows in curves.items()},
            'label': 'Matched solver-evaluation budget, not exactly matched total compute.'}
