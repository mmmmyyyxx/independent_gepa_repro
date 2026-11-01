from concurrent.futures import ThreadPoolExecutor
from email.utils import formatdate
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time

import pytest

from independent_gepa.paper_suite.control import Ledger, OperationalHalt, Transport, install_transport
from independent_gepa.paper_suite.execution import PhaseFutures, GRANT_SCHEMA
from independent_gepa.paper_suite.provider_errors import describe, retry_after, private_record, public_details
from independent_gepa.paper_suite.scheduling import Cell, ProcessJob


class Failure(Exception):
    def __init__(self, status=None, *, wire_status=None, body=None, headers=None):
        super().__init__('provider error; details are in the error body')
        self.status_code = status
        self.body = body
        if wire_status is not None:
            self.response = SimpleNamespace(status_code=wire_status, headers=headers or {},
                                            text=json.dumps(body) if body is not None else '')
        else:
            self.headers = headers or {}


def payload():
    return {'model':'openai/gpt-4.1-mini','temperature':1.,'max_tokens':16384,
            'messages':[{'role':'system','content':'synthetic'},{'role':'user','content':'synthetic'}]}


def response():
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=3,completion_tokens=2),
                           choices=[SimpleNamespace(finish_reason='stop')],model='synthetic')


@pytest.mark.parametrize('status', [408,409,429,500,501,502,503,504,520,524,529,599,'429'])
def test_status_not_sdk_class_controls_transient_recovery(status):
    BadRequestError = type('BadRequestError',(Failure,),{})
    info=describe(BadRequestError(status))
    assert info['recoverable'] and info['category']=='http_transient'
    assert info['http_status']==int(status)


@pytest.mark.parametrize('status', [400,401,402,403,404,405,413,422])
def test_real_request_or_access_failure_does_not_blindly_retry(status):
    err=Failure(503,wire_status=status,headers={'Retry-After':'2'},
                body={'error':{'message':'please retry; upstream503','type':'new_api_error'}})
    assert not describe(err)['recoverable']
    assert describe(err)['http_status']==status


def test_wire_status_overrides_sdk_remapping_and_cause_chain_recovers_missing_status():
    assert describe(Failure(400,wire_status=503))['recoverable']
    outer=RuntimeError('SDK wrapper')
    outer.__cause__=Failure('524',headers={'retry-after-ms':'1500'})
    info=describe(outer)
    assert info['http_status']==524 and info['retry_after_seconds']==1.5
    assert info['status_source']=='chain[1].exception'
    outer.__cause__=outer
    assert describe(outer)['category']=='unclassified_error'


def test_wrapped_network_errors_retry_but_certificate_and_unknown_errors_do_not():
    import ssl
    err=RuntimeError('wrapped')
    err.__cause__=ConnectionError('synthetic reset')
    assert describe(err)['recoverable']
    assert not describe(ssl.SSLCertVerificationError('CERTIFICATE_VERIFY_FAILED'))['recoverable']
    assert not describe(ValueError('invalid code'))['recoverable']
    BadRequestError=type('BadRequestError',(Exception,),{})
    info=describe(BadRequestError('unknown provider failure'))
    assert not info['recoverable'] and info['category']=='unclassified_error'


@pytest.mark.parametrize('headers,expected', [
    ({'Retry-After':'3.5'},3.5),({'retry-after-ms':'2500'},2.5),
    ({'Retry-After':'1','x-ms-retry-after-ms':'2200'},2.2),
    ({'Retry-After':formatdate(1020,usegmt=True)},20),
    ({'Retry-After':'NaN'},0),({'Retry-After':'inf'},0),({'Retry-After':'-3'},0),
    ({'Retry-After':'bad-date'},0),
])
def test_retry_after_seconds_date_and_invalid_values(headers,expected):
    assert retry_after(headers,now=1000)==expected


def test_retry_keeps_identical_request_and_honors_retry_after(tmp_path):
    ledger=Ledger(tmp_path/'ledger.jsonl',1,18);calls=[];waits=[];errors=[]
    def fake(**kwargs):
        calls.append(kwargs)
        if len(calls)==1:raise Failure(400,wire_status=503,headers={'Retry-After':'3.5'})
        return response()
    Transport(fake,ledger,sleep=waits.append,persist_error=lambda *args:errors.append(args))(**payload())
    assert calls==[payload()]*2 and sum(waits)==3.5
    assert ledger.physical==2 and ledger.unknown_failed_usage==1
    assert len(errors)==1 and ledger.tokens['solver']=={'prompt':3,'completion':2}
    assert not ledger.abort_event.is_set()


def test_retry_exhaustion_is_bounded_and_stops_later_paid_dispatch(tmp_path):
    ledger=Ledger(tmp_path/'ledger.jsonl',10,20);calls=[]
    def fail(**kwargs):calls.append(1);raise Failure(503)
    transport=Transport(fail,ledger,retries=2,sleep=lambda _:None)
    with pytest.raises(OperationalHalt,match='RETRY_EXHAUSTED'):transport(**payload())
    with pytest.raises(OperationalHalt,match='CANCELLED'):transport(**payload())
    assert len(calls)==ledger.physical==3 and ledger.unknown_failed_usage==3


def test_private_error_details_persist_before_halt_and_redact_credentials(tmp_path,monkeypatch):
    key='sk-secret_fixture_123456';endpoint='https://secret-host.invalid/v1'
    monkeypatch.setenv('SYNTHETIC_API_KEY',key)
    body={'error':{'code':'invalid_parameter','type':'new_api_error','param':'max_tokens',
                   'message':f'invalid max_tokens; Bearer {key}; endpoint {endpoint}',
                   'api_key':key,'nested':{'Authorization':'Bearer '+key}}}
    error=Failure(400,wire_status=400,body=body,headers={'X-Request-ID':'private-correlation'})
    def fake(**kwargs):raise error
    ledger=Ledger(tmp_path/'ledger.jsonl',1,18);module=SimpleNamespace(completion=fake)
    install_transport(module,ledger,tmp_path/'paid_responses')
    with pytest.raises(OperationalHalt,match='PROVIDER_FAILURE'):
        module.completion(**payload(),api_key=key,api_base=endpoint)
    evidence=list((tmp_path/'provider_errors').glob('*.json'))
    assert len(evidence)==1
    record=json.loads(evidence[0].read_text());content=evidence[0].read_text()
    assert key not in content and endpoint not in content and 'secret-host' not in content
    assert record['details']['http_status']==400
    assert record['details']['error_code']=='invalid_parameter'
    assert 'max_tokens' in record['details']['body']['error']['message']
    events=[json.loads(x) for x in ledger.path.read_text().splitlines()]
    failure=next(e for e in events if e['event']=='transport_failure')
    assert failure['http_status']==400 and failure['recovery_category']=='http_request_or_access_error'
    assert 'message' not in failure and 'body' not in failure and 'private-correlation' not in json.dumps(failure)
    assert failure['evidence_sha256']==hashlib.sha256(evidence[0].read_bytes()).hexdigest()
    assert ledger.abort_event.is_set()


def test_evidence_write_failure_blocks_new_dispatch_and_preserves_unknown_usage(tmp_path):
    ledger=Ledger(tmp_path/'ledger.jsonl',1,10);calls=[]
    def fake(**kwargs):calls.append(1);raise Failure(503)
    def persist(*args):raise OSError('synthetic disk failure')
    transport=Transport(fake,ledger,persist_error=persist)
    with pytest.raises(OperationalHalt,match='EVIDENCE_PERSISTENCE_FAILED'):transport(**payload())
    with pytest.raises(OperationalHalt,match='CANCELLED'):transport(**payload())
    assert len(calls)==ledger.physical==ledger.unknown_failed_usage==1


def test_retry_after_exceeding_phase_deadline_stops_without_sleep_or_resend(tmp_path):
    ledger=Ledger(tmp_path/'ledger.jsonl',1,18);ledger.wall_deadline=time.monotonic()+2
    waits=[]
    def fake(**kwargs):raise Failure(429,headers={'Retry-After':'30'})
    with pytest.raises(OperationalHalt,match='DELAY_EXCEEDS_PHASE_DEADLINE'):
        Transport(fake,ledger,sleep=waits.append)(**payload())
    assert waits==[] and ledger.physical==1


def test_fatal_request_stops_queue_but_paid_inflight_response_is_still_recorded(tmp_path):
    ledger=Ledger(tmp_path/'ledger.jsonl',100,100)
    registry=PhaseFutures(ledger);native=SimpleNamespace(ThreadPoolExecutor=ThreadPoolExecutor)
    registry.install(native);barrier=threading.Barrier(2);release=threading.Event();calls=[]
    def paid(**kwargs):
        name=kwargs['synthetic_case'];calls.append(name)
        assert name!='queued'
        barrier.wait(2)
        if name=='fatal':raise Failure(400)
        assert release.wait(2)
        return response()
    transport=Transport(paid,ledger)
    pool=native.ThreadPoolExecutor(max_workers=2)
    pool.submit(transport,**payload(),synthetic_case='inflight')
    pool.submit(transport,**payload(),synthetic_case='fatal')
    # Submit before releasing the fatal worker if it already finished; either
    # outcome must prevent a third physical request.
    try:pool.submit(transport,**payload(),synthetic_case='queued')
    except OperationalHalt:pass
    timer=threading.Timer(.05,release.set);timer.start()
    try:
        with pytest.raises(OperationalHalt,match='PROVIDER_FAILURE'):registry.drain()
    finally:timer.join();registry.restore()
    assert sorted(calls)==['fatal','inflight'] and ledger.physical==2
    assert ledger.tokens['solver']=={'prompt':3,'completion':2}
    assert registry.summary()['drained'] and registry.summary()['pending']==0


def test_process_dispatch_rejects_outside_workspace_before_launch(tmp_path,monkeypatch):
    import independent_gepa.paper_suite.scheduling as scheduling
    calls=[];monkeypatch.setattr(scheduling.subprocess,'Popen',lambda *a,**k:calls.append(a))
    with pytest.raises(ValueError,match='DISPATCH_OUTPUT_MUST_BE_IN_WORKSPACE'):
        ProcessJob(Cell('synthetic',tmp_path/'grant',{}),tmp_path,tmp_path/'workspace',tmp_path/'outside')
    assert calls==[]


def test_recovery_amendment_preserves_scientific_settings_and_old_scopes_are_rejected(tmp_path):
    from independent_gepa.paper_suite.contract import draft,IDENTITY
    from independent_gepa.paper_suite.runtime import validate_grant
    root=Path(__file__).resolve().parents[1]
    old=json.loads((root/'configs/gepa_paper_five_tasks_openlux_qwen37_alias_windows_v3.json').read_text())
    new=json.loads(json.dumps(draft()))
    for field in ('schema_version','operational_adapter'):new[field]=old[field]
    assert new==old
    for name in ('data','program','source','environment','nlp'):
        assert (root/'experiments/protocols'/IDENTITY/(name+'_inventory.json')).read_bytes()==(root/'experiments/protocols/gepa_paper_five_tasks_openlux_qwen37_alias_windows_v3'/(name+'_inventory.json')).read_bytes()
    with pytest.raises(ValueError,match='FRESH_EXACT'):
        validate_grant(tmp_path,tmp_path,{'schema':'gepa_paper_five_tasks_openlux_qwen37_alias_windows_v3_authorization_v2','approved_by':'user','READY_TO_RUN':True,'real_api_allowed':True})


def test_dns_reset_and_windows_network_errors_are_operational_retries():
    import errno,socket,ssl
    for error in (socket.gaierror(-2,'synthetic DNS'),OSError(errno.ENETUNREACH,'synthetic network'),ssl.SSLEOFError('unexpected EOF')):
        assert describe(error)['recoverable']
    assert not describe(OSError(errno.EACCES,'local permission error'))['recoverable']


def test_300_queued_examples_do_not_all_dispatch_after_first_fatal_error(tmp_path):
    ledger=Ledger(tmp_path/'ledger.jsonl',1000,1000)
    phase=PhaseFutures(ledger);native=SimpleNamespace(ThreadPoolExecutor=ThreadPoolExecutor);phase.install(native)
    gate=threading.Event();release=threading.Event();first_two=threading.Barrier(3);paid=[]
    def network(**kwargs):
        item=kwargs['synthetic_case'];paid.append(item);first_two.wait(3);assert gate.wait(3)
        if item==0:raise Failure(400)
        assert release.wait(3);return response()
    transport=Transport(network,ledger)
    def program(index):ledger.reserve_logical();return transport(**payload(),synthetic_case=index)
    pool=native.ThreadPoolExecutor(max_workers=2)
    futures=[pool.submit(program,i) for i in range(300)]
    first_two.wait(3);gate.set()
    timer=threading.Timer(.05,release.set);timer.start()
    try:
        with pytest.raises(OperationalHalt,match='PROVIDER_FAILURE'):phase.drain()
    finally:timer.join();phase.restore()
    assert ledger.physical==2 and ledger.logical==2
    assert phase.summary()['completed']==300 and phase.summary()['pending']==0
    assert ledger.tokens['solver']=={'prompt':3,'completion':2}
    assert any(f.cancelled() for f in futures)
