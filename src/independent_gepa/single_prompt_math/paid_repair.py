"""Strict acknowledgments for historical paid Test-scoring terminal events."""
from .common import digest,read
from .scoring_v7 import validate_policy
from ..protocol import ProtocolViolation


class PaidTerminalRepairs:
    def __init__(self,policy=None):
        self.policy=policy;self.pending={};self.count=0
        if policy is not None:validate_policy(policy)

    def terminal(self,event,context,logical_contexts,resolved):
        key=event['key']
        if (self.policy is None or context is None or key in self.pending or key in resolved
            or (event.get('arm'),key) not in logical_contexts
            or event.get('phase')!='test' or event.get('split')!='test' or event.get('stage')!='scoring'
            or event.get('category')!='MATH_EVALUATOR_UNRESOLVED_COMPUTATION'
            or event.get('repeat')!=context[0] or context[1:3]!=('test','test')):
            raise ProtocolViolation('AUDIT_UNRESOLVED_LOCAL_COMPUTATION')
        self.pending[key]=event

    def reservation(self,key):
        if key in self.pending:raise ProtocolViolation('AUDIT_TERMINAL_REPAIR_RESAMPLED')

    def repaired(self,event,resolved,directory):
        key=event['key'];terminal=self.pending.get(key);value=resolved.get(key)
        if (self.policy is None or terminal is None or value is None
            or event.get('terminal_event_sha256')!=terminal['event_sha256']
            or event.get('policy_sha256')!=digest(self.policy) or event.get('new_model_calls')!=0
            or event.get('observation_sha256')!=digest(value)):
            raise ProtocolViolation('AUDIT_PAID_TERMINAL_REPAIR_BINDING')
        paid=read(directory/'resolved_answers'/f'{key}.json')
        if {k:v for k,v in value.items() if k not in ('correct','valid','answer')}!=paid:
            raise ProtocolViolation('AUDIT_PAID_TERMINAL_REPAIR_CHANGED_ANSWER')
        del self.pending[key];self.count+=1

    def close(self):
        if self.pending:raise ProtocolViolation('AUDIT_UNRESOLVED_LOCAL_COMPUTATION')
