"""Typed infrastructure recovery; never consume a search RNG or model semantic draw."""
from __future__ import annotations

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import errno
import math
import time
from typing import Callable,TypeVar

from ..protocol import ProtocolViolation
from .common import Abort,progress

T=TypeVar('T')


class ReflectionUnavailable(Exception):
    """A bounded exhausted generation uses the native no-proposal path."""


class TransientProviderPayload(Exception):
    def __init__(self,category,evidence):
        super().__init__(category);self.category=category;self.provider_evidence=evidence


@dataclass(frozen=True)
class RetryDecision:
    retryable: bool
    category: str
    http_status: int|None=None
    retry_after_seconds: float|None=None


def retry_after(headers,now=None):
    now=time.time() if now is None else now
    for name,scale in (('retry-after-ms',0.001),('retry-after',1.0)):
        value=headers.get(name)
        if value is None:continue
        try:seconds=float(value)*scale
        except (ValueError,TypeError):
            if name!='retry-after':continue
            try:seconds=parsedate_to_datetime(value).timestamp()-now
            except (ValueError,TypeError,OverflowError):continue
        if math.isfinite(seconds) and seconds>=0:return seconds
    return None


def transport_failure(exc,config):
    from openai import APIConnectionError,APITimeoutError,APIStatusError
    if isinstance(exc,APITimeoutError):return RetryDecision(True,'REQUEST_TIMEOUT')
    if isinstance(exc,APIConnectionError):return RetryDecision(True,'CONNECTION_FAILURE')
    if isinstance(exc,TransientProviderPayload):return RetryDecision(True,'PROVIDER_'+exc.category)
    if isinstance(exc,APIStatusError):
        status=exc.status_code;lower,upper=config['http_retry_status_range']
        transient=status in config['http_retry_status_codes'] or lower<=status<=upper
        return RetryDecision(transient,'HTTP_'+str(status),status,retry_after(exc.response.headers))
    return RetryDecision(False,type(exc).__name__)


def retry_delay(config,index,decision=None):
    schedule=config['network_backoff_seconds'];seconds=schedule[min(index,len(schedule)-1)]
    if decision is not None and config['retry_after_policy']=='max_backoff_and_valid_seconds_ms_http_date':
        seconds=max(seconds,decision.retry_after_seconds or 0)
    return seconds


def temporary_worker_resource_error(exc):
    return isinstance(exc,OSError) and (exc.errno in (errno.EAGAIN,errno.ENOMEM,errno.EINTR)
        or getattr(exc,'winerror',None) in (8,14,1450,1455))


def temporary_worker_exit(code):
    return code in (-1073741801,3221225495,-1073741670,3221225626)


def retry_local_worker(operation: Callable[[],T],config,initial_deadline,*,check=lambda:None,
                       wait=None,on_retry=lambda **event:None) -> T:
    from .math_domain_v2 import worker_deadline
    retries=0;deadline=initial_deadline;timeouts_at_ceiling=0
    if wait is None:
        def wait(seconds):
            end=time.monotonic()+seconds;heartbeat=time.monotonic()+config['recovery_wait_heartbeat_seconds']
            while time.monotonic()<end:
                check();time.sleep(min(1,max(0,end-time.monotonic())))
                if time.monotonic()>=heartbeat:
                    progress('LOCAL_RECOVERY_WAIT remaining_seconds='+str(round(max(0,end-time.monotonic()))))
                    heartbeat=time.monotonic()+config['recovery_wait_heartbeat_seconds']
            check()
    while True:
        check()
        try:
            with worker_deadline(deadline):return operation()
        except ProtocolViolation as exc:
            category=str(exc)
            if category not in config['local_worker_retry_categories']:raise
            if category=='MATH_EVALUATOR_TIMEOUT' and deadline>=config['local_worker_retry_max_deadline_seconds']:
                timeouts_at_ceiling+=1
                limit=config.get('local_timeout_attempts_at_ceiling')
                if limit is not None and timeouts_at_ceiling>=limit:
                    raise ProtocolViolation('MATH_EVALUATOR_UNRESOLVED_COMPUTATION') from exc
            delay=retry_delay(config,retries)
            next_deadline=min(deadline*config['local_worker_retry_deadline_multiplier'],config['local_worker_retry_max_deadline_seconds'])
            on_retry(category=category,retry_index=retries+1,delay_seconds=delay,
                     worker_deadline_seconds=deadline,next_worker_deadline_seconds=next_deadline)
            wait(delay);retries+=1;deadline=next_deadline
