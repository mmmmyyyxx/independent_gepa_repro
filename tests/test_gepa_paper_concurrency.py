from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from independent_gepa.paper_suite.control import Ledger, OperationalHalt
from independent_gepa.paper_suite.execution import PhaseFutures, execution_policy, POLICY_PATH, GRANT_SCHEMA
from independent_gepa.paper_suite.scheduling import Cell, _run_queue, admissible, validate_stage
from independent_gepa.paper_suite.runtime import validate_grant, validate_phase_dependencies, MODEL_BINDINGS
from independent_gepa.paper_suite.execution import EXECUTION_BINDINGS
from independent_gepa.paper_suite.contract import TASKS
from independent_gepa.paper_suite.data import canonical
from independent_gepa.paper_suite.sources import file_hash


def test_losing_future_is_drained_before_receipt_and_transport_restore(tmp_path):
    ledger = Ledger(tmp_path/'ledger.jsonl', 10, 10)
    native = SimpleNamespace(ThreadPoolExecutor=ThreadPoolExecutor)
    phase = PhaseFutures(ledger)
    phase.install(native)
    release = threading.Event()
    observed = []
    def delayed():
        assert release.wait(2)
        ledger.reserve_physical('solver', 'late')
        observed.append('late-paid-body')
    pool = native.ThreadPoolExecutor(max_workers=2)
    future = pool.submit(delayed)
    assert pool.submit(lambda: 'winning-draw').result(1) == 'winning-draw'
    pool.shutdown(wait=False)
    with pytest.raises(OperationalHalt, match='UNDRAINED'):
        phase.restore()
    timer = threading.Timer(.03, release.set)
    timer.start()
    phase.drain()
    timer.join()
    phase.restore()
    assert future.done() and ledger.physical == 1 and observed == ['late-paid-body']
    assert phase.summary()['pending'] == 0 and phase.summary()['completed'] == 2
    assert native.ThreadPoolExecutor is ThreadPoolExecutor


def test_late_fatal_failure_cannot_be_hidden_by_an_earlier_winner(tmp_path):
    phase = PhaseFutures(Ledger(tmp_path/'ledger.jsonl', 10, 10))
    native = SimpleNamespace(ThreadPoolExecutor=ThreadPoolExecutor)
    phase.install(native)
    release = threading.Event()
    def fail():
        assert release.wait(2)
        raise OperationalHalt('SYNTHETIC_LATE_PROVIDER_401')
    pool = native.ThreadPoolExecutor(max_workers=2)
    pool.submit(fail)
    assert pool.submit(lambda: 'winner').result(1) == 'winner'
    release.set()
    with pytest.raises(OperationalHalt, match='LATE_PROVIDER_401'):
        phase.drain()
    phase.restore()
    assert phase.summary()['drained'] and phase.summary()['late_error_category'] == 'OperationalHalt'


def test_deadline_cancels_queued_work_and_reaps_running_work(tmp_path):
    ledger = Ledger(tmp_path/'ledger.jsonl', 10, 10)
    ledger.wall_deadline = time.monotonic() - 1
    phase = PhaseFutures(ledger)
    native = SimpleNamespace(ThreadPoolExecutor=ThreadPoolExecutor)
    phase.install(native)
    release = threading.Event()
    started = threading.Event()
    def active():
        started.set()
        assert release.wait(2)
    pool = native.ThreadPoolExecutor(max_workers=1)
    pool.submit(active)
    assert started.wait(1)
    queued = pool.submit(lambda: pytest.fail('cancelled queued work must not run'))
    timer = threading.Timer(.04, release.set)
    timer.start()
    with pytest.raises(OperationalHalt, match='WALL_TIME'):
        phase.drain()
    timer.join()
    phase.restore()
    assert queued.cancelled() and phase.summary()['drained']


def cells(phase='search'):
    return [Cell(t.key, Path(t.key+'.json'), {'scope_id':t.key, 'phase':phase, 'max_elapsed_seconds':100}) for t in TASKS]


class FakeJob:
    def __init__(self, cell, clock, duration, code=0):
        self.cell, self.clock, self.duration, self.code = cell, clock, duration, code
        self.started = clock[0]
        self.stopped = self.closed = False
    def poll(self):
        return self.code if self.clock[0] - self.started >= self.duration else None
    def private_bytes(self):
        return 0
    def stop(self):
        self.stopped = True
    def close(self):
        self.closed = True


def test_scheduler_uses_two_process_lanes_and_livebench_is_exclusive():
    settings = execution_policy()['scheduler']
    clock = [0]
    events, jobs = [], []
    def start(cell):
        job = FakeJob(cell, clock, 8 if cell.task in settings['retrieval_tasks'] else 2)
        jobs.append(job)
        return job
    def sleep(amount):
        clock[0] += amount
    result = _run_queue(cells(), settings, 100, start=start,
        verify=lambda c:{'receipt_sha256':'synthetic', 'score':0}, available=lambda:20*1024**3,
        event=lambda kind,**kw:events.append((kind,kw)), clock=lambda:clock[0], sleep=sleep)
    assert len(result) == 5 and all(job.closed and not job.stopped for job in jobs)
    active = set()
    for kind, value in events:
        if kind == 'cell_started':active.add(value['task'])
        if kind == 'cell_complete':active.remove(value['task'])
        assert len(active) <= 2
        assert len(active & {'hotpotqa','hover'}) <= 1
        if 'livebench_math' in active:assert len(active) == 1
    assert [job.cell.task for job in jobs] == ['hover','ifbench','aime2025','hotpotqa','livebench_math']
    # Zero scores cannot alter scheduling or cause efficacy-based stopping.
    assert all(x['score'] == 0 for x in result)


def test_memory_reservations_cover_unmaterialized_child_allocations():
    settings = execution_policy()['scheduler'];pool=cells();clock=[0]
    heavy=next(c for c in pool if c.task=='hover');light=next(c for c in pool if c.task=='ifbench')
    active={'hover':FakeJob(heavy,clock,10)}
    assert not admissible(light,active,settings,6*1024**3)
    assert admissible(light,active,settings,7*1024**3)
    assert not admissible(heavy,{},settings,5*1024**3)


def test_failed_child_stops_other_process_and_never_starts_pending_tasks():
    settings=execution_policy()['scheduler'];clock=[0];jobs=[]
    def start(cell):
        job=FakeJob(cell,clock,1 if cell.task=='ifbench' else 50,code=1 if cell.task=='ifbench' else 0)
        jobs.append(job);return job
    def sleep(amount):clock[0]+=amount
    with pytest.raises(OperationalHalt,match='CHILD_PHASE_FAILED'):
        _run_queue(cells(),settings,100,start=start,verify=lambda c:{},available=lambda:20*1024**3,
                   event=lambda *a,**kw:None,clock=lambda:clock[0],sleep=sleep)
    assert len(jobs)==2 and all(job.stopped and job.closed for job in jobs)


def test_resource_wait_expires_without_launching_any_child():
    settings={**execution_policy()['scheduler'],'idle_resource_wait_seconds':3};clock=[0]
    def sleep(amount):clock[0]+=amount
    with pytest.raises(OperationalHalt,match='RESOURCE_WAIT'):
        _run_queue(cells(),settings,100,start=lambda c:pytest.fail('no memory'),verify=lambda c:{},
                   available=lambda:0,event=lambda *a,**kw:None,clock=lambda:clock[0],sleep=sleep)


def test_unauthorized_schedule_and_previous_phase_grant_fail_before_clients(tmp_path):
    with pytest.raises(ValueError,match='STAGE_SCHEDULE_AUTHORIZATION'):
        validate_stage(tmp_path,tmp_path,{'READY_TO_RUN':False})
    with pytest.raises(ValueError,match='FRESH_EXACT'):
        validate_grant(tmp_path,tmp_path,{'schema':GRANT_SCHEMA.replace('_v2','_v1'),
            'approved_by':'user','READY_TO_RUN':True,'real_api_allowed':True})


def test_global_test_barrier_requires_all_searches_and_frozen_programs(tmp_path):
    grant={'phase':'baseline','task':TASKS[0].key,'cache_namespace':'same_task_cache',
           'source_sha':'synthetic','config_sha256':'synthetic','data_receipt_sha256':'synthetic',
           **{key:'synthetic' for key in MODEL_BINDINGS+EXECUTION_BINDINGS}}
    with pytest.raises(ValueError,match='FIVE_TASK_PHASE_BARRIER'):
        validate_phase_dependencies(tmp_path,grant)
    bindings={}
    for task in TASKS:
        folder=tmp_path/task.key;folder.mkdir()
        selected=folder/'selected_program.json';selected.write_bytes(b'synthetic')
        receipt={**grant,'status':'COMPLETE','task':task.key,'phase':'search',
                 'selected_program_sha256':file_hash(selected),'phase_futures':{'drained':True,'pending':0}}
        path=folder/'receipt.json';path.write_bytes(canonical(receipt)+b'\n')
        bindings[task.key]={'path':path.relative_to(tmp_path).as_posix(),'sha256':file_hash(path)}
    grant['search_receipts']=bindings
    validate_phase_dependencies(tmp_path,grant)
    grant['cache_namespace']='different_namespace'
    with pytest.raises(ValueError,match='CACHE_NAMESPACE_MUST_MATCH'):
        validate_phase_dependencies(tmp_path,grant)
    grant['cache_namespace']='same_task_cache'
    (tmp_path/TASKS[0].key/'selected_program.json').write_bytes(b'changed')
    with pytest.raises(ValueError,match='SELECTED_PROGRAMS_MUST_BE_FROZEN'):
        validate_phase_dependencies(tmp_path,grant)


def test_execution_policy_file_matches_supported_implementation():
    root=Path(__file__).resolve().parents[1]
    assert json.loads((root/POLICY_PATH).read_text(encoding='utf-8'))==execution_policy()
