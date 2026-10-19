"""Rebuildable token accounting; no monetary estimates or price weights.

Physical usage is charged to the dispatcher. For a fair standalone cache model,
each arm also receives one attribution of each unique resolved Solver observation
it uses, including its observed semantic draws and conservative retry bounds.
Repeat/phase isolation is already part of the observation key. Repeated cache
hits within one arm do not incur another attributed charge. Reflection is fresh.
"""
from collections import Counter
from copy import deepcopy

from .common import digest, read
from ..protocol import ProtocolViolation

FIELDS = ('input_tokens', 'output_tokens', 'failed_input_bound', 'failed_output_bound',
          'unknown_input_bound', 'unknown_output_bound', 'successes', 'failures', 'physical_attempts')


def total(value):
    return sum(value.get(k, 0) for k in FIELDS[:6])


class TokenLedger:
    def __init__(self, directory):
        self.directory = directory
        self.reserved = {}
        self.actual = {}
        self.attributed = {}
        self.observations = {}
        self.contexts = {}
        self.assigned = set()
        self.resolved = set()
        self.completed = set()

    @staticmethod
    def add(table, context, usage):
        component=context.get('kind_of_evaluation','native_reflection' if context['role']=='reflection' else 'unclassified_direct')
        key = (context['phase'], context['arm'], context['repeat'], context['role'],component)
        table.setdefault(key, Counter()).update(usage)

    def assign(self, key, arm, repeat):
        ident = (arm, repeat, key)
        if ident in self.assigned:
            return
        if key not in self.resolved:
            raise ProtocolViolation('TOKEN_ATTRIBUTION_BEFORE_RESOLUTION')
        self.assigned.add(ident)
        context = self.contexts[key][(arm, repeat)]
        self.add(self.attributed, {**context, 'role': 'solver'}, self.observations.get(key, {}))

    def consume(self, event):
        kind = event['kind']
        if kind == 'LOGICAL_SOLVER':
            key = event['key']
            self.contexts.setdefault(key, {})[(event['arm'], event['repeat'])] = event
        elif kind == 'RESERVE':
            self.reserved[event['number']] = event
        elif kind in ('RESPONSE_CHARGE', 'FAILURE_CHARGE'):
            reservation = self.reserved.get(event['number'])
            if reservation is None:
                raise ProtocolViolation('TOKEN_CHARGE_WITHOUT_RESERVATION')
            number = event['number']
            if number in self.completed:
                raise ProtocolViolation('DUPLICATE_TOKEN_CHARGE')
            self.completed.add(number)
            request = read(self.directory / 'requests' / f'{number:06d}.json')['request']
            output_bound = request.get('max_tokens', request.get('max_completion_tokens')) + (10 if reservation['role'] == 'reflection' else 0)
            input_bound = reservation['bound'] - output_bound
            usage = Counter(physical_attempts=1)
            if kind == 'FAILURE_CHARGE':
                usage.update(failures=1, failed_input_bound=input_bound, failed_output_bound=output_bound)
            else:
                response = read(self.directory / 'responses' / f'{number:06d}.json')['response']
                usage['successes'] = 1
                if event['usage_reliable']:
                    usage.update(input_tokens=response['input_tokens'], output_tokens=response['output_tokens'])
                else:
                    usage.update(unknown_input_bound=input_bound, unknown_output_bound=output_bound)
            if total(usage) != event['amount']:
                raise ProtocolViolation('TOKEN_CHARGE_AMOUNT_MISMATCH')
            logical_context=self.contexts.get(reservation.get('logical_key'),{}).get((reservation['arm'],reservation['repeat']),{})
            self.add(self.actual, {**reservation,**({'kind_of_evaluation':logical_context['kind_of_evaluation']} if logical_context else {})}, usage)
            if reservation['role'] == 'reflection':
                self.add(self.attributed, reservation, usage)
            else:
                key = reservation['logical_key']
                self.observations.setdefault(key, Counter()).update(usage)
        elif kind == 'SOLVER_RESOLVED':
            key = event['key']
            self.resolved.add(key)
            for arm, repeat in self.contexts.get(key, {}):
                self.assign(key, arm, repeat)
        elif kind == 'CACHE_HIT':
            self.assign(event['key'], event['arm'], event['repeat'])

    def view(self, phase=None, arm=None, repeat=None):
        result = {}
        for name, table in (('actual_dispatch', self.actual), ('standalone_attributed', self.attributed)):
            roles = {r: Counter() for r in ('solver', 'reflection')}
            components={}
            for (p, a, n, role,component), usage in table.items():
                if (phase is None or p == phase) and (arm is None or a == arm) and (repeat is None or n == repeat):
                    roles[role].update(usage)
                    components.setdefault(component,{r:Counter() for r in ('solver','reflection')})[role].update(usage)
            normalized = {r: {k: values[k] for k in FIELDS} for r, values in roles.items()}
            result[name] = {'roles': normalized, 'accounted_tokens': sum(total(v) for v in normalized.values())}
            result[name]['components']={c:{'roles':{r:{k:v[k] for k in FIELDS} for r,v in values.items()},
                'accounted_tokens':sum(total(v) for v in values.values())} for c,values in sorted(components.items())}
        result['unresolved_physical_reservations']=sum(n not in self.completed for n,c in self.reserved.items()
            if (phase is None or c['phase']==phase) and (arm is None or c['arm']==arm) and (repeat is None or c['repeat']==repeat))
        return deepcopy(result)

    @classmethod
    def replay(cls, directory, watches=None):
        import json
        ledger = cls(directory)
        ledger.watched = {}
        previous = '0' * 64
        with (directory / 'accounting.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                event = json.loads(line)
                value = dict(event)
                sha = value.pop('event_sha256')
                if digest(value) != sha or value['previous_event_sha256'] != previous:
                    raise ProtocolViolation('TOKEN_LEDGER_HASH_CHAIN')
                ledger.consume(value)
                previous = sha
                if watches and sha in watches:
                    ledger.watched[sha] = {(arm, repeat): ledger.view('search', arm, repeat)
                                          for arm, repeat in watches[sha]}
        return ledger
