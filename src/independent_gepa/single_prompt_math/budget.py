"""Atomic native logical admission and outcome-blind complete-iteration stopping."""
from threading import RLock

from .common import Abort


class NativeBudget:
    def __init__(self, limit: int, validation_size: int, minibatch_size: int, safety_proposals: int):
        if any(type(x) is not int or x <= 0 for x in (limit, validation_size, minibatch_size, safety_proposals)):
            raise Abort('INVALID_NATIVE_BUDGET')
        if limit < validation_size:
            raise Abort('NATIVE_BUDGET_CANNOT_FIT_INITIAL_VALIDATION')
        self.limit = limit
        self.reserve = validation_size + 2 * minibatch_size
        self.safety_proposals = safety_proposals
        self.used = 0
        self.reason = None
        self.batches = []
        self.lock = RLock()

    def admit(self, size: int, stage: str) -> None:
        with self.lock:
            if type(size) is not int or size < 0 or self.used + size > self.limit:
                # No partial batch, fabricated score, or mid-iteration ordinary rejection.
                raise Abort('NATIVE_BATCH_BUDGET_INVARIANT')
            self.batches.append({'before': self.used, 'size': size, 'after': self.used + size, 'stage': stage})
            self.used += size

    def __call__(self, state) -> bool:
        with self.lock:
            if state.total_num_evals != self.used:
                raise Abort('NATIVE_EXTERNAL_BUDGET_DIVERGENCE')
            if self.limit - self.used < self.reserve:
                self.reason = 'budget_exhausted' if self.used == self.limit else 'insufficient_complete_iteration_budget'
                return True
            if state.i >= self.safety_proposals - 1:
                self.reason = 'proposal_safety_limit'
                return True
            return False

    def summary(self) -> dict:
        return {'limit': self.limit, 'used': self.used, 'remaining': self.limit - self.used,
                'utilization': self.used / self.limit, 'complete_iteration_reserve': self.reserve,
                'stop_reason': self.reason, 'batches': list(self.batches)}
