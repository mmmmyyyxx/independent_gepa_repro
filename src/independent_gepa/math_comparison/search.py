"""Native GEPA optimization and an outcome-independent post-search selection."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .._vendor import import_vendor_gepa
from ..protocol import ProtocolViolation
from .contract import digest, write
from .runtime import Runtime, append
from .candidate_guard import candidate_valid, candidate_failures, GUARD_ID
from .candidate_review import CandidateReview, POLICY

gepa=import_vendor_gepa()
from gepa.core.adapter import EvaluationBatch
from gepa.core.callbacks import GEPACallback
from gepa.strategies.instruction_proposal import InstructionProposalSignature

INITIAL='Solve the problem.'
MUTABLE_KEY='system_prompt'  # Native component name; actual Solver boundary is the A4 user message.
REFLECTION_TEMPLATE=InstructionProposalSignature.default_prompt_template+"""

Task boundary: optimize only reusable mathematical reasoning instructions.
The mutable component is the reasoning procedure inserted in the user message;
its native component name does not grant control over the system message.
The immutable Solver interface requires exactly one visible line:
FINAL_ANSWER: <answer>
No visible reasoning, derivation, solution process, headings or extra lines
are allowed, including when a problem asks for a solution. Reason internally.
Do not weaken that rule or add exceptions. Do not change the interface,
final-answer marker, or parser. Do not prescribe fixed answers,
copy training problems, worked examples, their numeric results or solutions,
or include example-specific facts. Infer reusable reasoning rules instead.
"""

def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode('utf-8')).hexdigest()

class PrivateLogger:
    def __init__(self,path: Path): self.path=path
    def log(self,message: str): append(self.path,{'message':message})

class History(GEPACallback):
    def __init__(self, private: Path, adapter: 'MathAdapter'):
        self.private=private; self.adapter=adapter; self.proposals: list[dict[str,Any]]=[]
        self.events: list[dict[str,Any]]=[]; self.parent=0; self.iteration=0
    def record(self,kind: str,**data):
        row={'kind':kind,'search_metrics_used':self.adapter.metrics_used,**data}
        self.events.append(row); append(self.private/'history.jsonl',row)
    def on_iteration_start(self,event): self.iteration=event['iteration']
    def on_candidate_selected(self,event):
        self.parent=event['candidate_idx']
        self.record('parent_selected',iteration=event['iteration'],parent_idx=self.parent,
                    parent_hash=prompt_hash(event['candidate'][MUTABLE_KEY]),score=event['score'])
    def on_minibatch_sampled(self,event): self.record('minibatch',ids=event['minibatch_ids'],iteration=event['iteration'])
    def on_proposal_end(self,event):
        prompt=event['new_instructions'][MUTABLE_KEY]
        generation=len(self.proposals)+1
        row={'generation':len(self.proposals)+1,'iteration':event['iteration'],'parent_idx':self.parent,
             'prompt_hash':prompt_hash(prompt),'prompt':prompt,'contract_valid':False,
             'candidate_guard':GUARD_ID,'contract_failures':[],
             'reflection_source_ids_at_generation':list(self.adapter.reflection_source_ids),
             'automatic_guard_passed':candidate_valid(prompt,self.adapter.examples),'owner_review_status':'PENDING'}
        self.proposals.append(row)
        write(self.private/'proposals.json',self.proposals)
        checked=self.adapter.check_candidate(prompt,generation)
        row.update(checked)
        write(self.private/'proposals.json',self.proposals)
        self.record('proposal',**{k:v for k,v in row.items() if k!='prompt'})
    def on_candidate_accepted(self,event):
        self.proposals[-1]['native_local_positive']=True
        write(self.private/'proposals.json',self.proposals)
        self.record('accepted',generation=len(self.proposals),candidate_idx=event['new_candidate_idx'],
                    parent_ids=list(event['parent_ids']),local_sum=event['new_score'])
    def on_candidate_rejected(self,event):
        self.proposals[-1]['native_local_positive']=event['new_score']>event['old_score']
        write(self.private/'proposals.json',self.proposals)
        self.record('rejected',generation=len(self.proposals),old_sum=event['old_score'],new_sum=event['new_score'])
    def on_pareto_front_updated(self,event):
        self.record('frontier_update',front=event['new_front'],displaced=event['displaced_candidates'])
    def on_evaluation_end(self,event):
        self.record('metric_batch',scores=event['scores'],candidate_idx=event['candidate_idx'],
                    capture_traces=event['has_trajectories'])

class MathAdapter:
    propose_new_texts=None
    def __init__(self,runtime: Runtime,examples: list[dict[str,Any]],window: int,member: int,private: Path,
                 *,review: CandidateReview|None=None):
        self.runtime=runtime; self.examples=examples; self.window=window; self.member=member
        self.private=private; self.metrics_used=0; self.evaluated: set[str]=set()
        self.allowed={digest(row) for row in examples}
        self.review=review;self.reflection_source_ids: list[str]=[];self.generation=0
        self.decisions: dict[str,dict[str,Any]]={}
    def check_candidate(self,prompt: str,generation: int|None=None) -> dict[str,Any]:
        if generation is not None:self.generation=generation
        failures=candidate_failures(prompt,self.examples);automatic=not failures
        status='IMMUTABLE_INITIAL' if prompt==INITIAL else 'NOT_REQUIRED_OFFLINE_HISTORICAL'
        receipt_hash=None
        if automatic and prompt!=INITIAL and self.review is not None:
            receipt=self.review.check(prompt,prompt_hash(prompt),self.generation,self.reflection_source_ids)
            status=receipt['status'];receipt_hash=receipt['receipt_sha256']
            if prompt_hash(prompt) not in self.decisions and hasattr(self.runtime,'event'):
                self.runtime.event({'kind':'CANDIDATE_REVIEW_DECISION','window':self.window,'member':self.member,
                    'prompt_hash':prompt_hash(prompt),'status':status,'receipt_sha256':receipt_hash,
                    'request_sha256':receipt['request_sha256'],'reviewer_identity':receipt['reviewer_identity']})
            if status=='REJECT':failures=['OWNER_CONFORMANCE_'+c for c in receipt['categories']]
        elif failures:status='LEXICAL_REJECTED'
        value={'contract_valid':not failures,'contract_failures':failures,
               'automatic_guard_passed':automatic,'owner_review_status':status,'owner_receipt_sha256':receipt_hash}
        self.decisions[prompt_hash(prompt)]=value
        return value
    def evaluate(self,batch,candidate,capture_traces=False):
        if set(candidate)!={MUTABLE_KEY}: raise ProtocolViolation('ONE_MUTABLE_COMPONENT_REQUIRED')
        if any(digest(row) not in self.allowed for row in batch): raise ProtocolViolation('NON_OPTIMIZE_SEARCH_ACCESS')
        if self.metrics_used+len(batch)>36: raise ProtocolViolation('SEARCH_METRIC_CEILING')
        prompt=candidate[MUTABLE_KEY];checked=self.check_candidate(prompt);admissible=checked['contract_valid']
        observations=[]; self.metrics_used+=len(batch)
        if admissible:
            observations=[self.runtime.solve(prompt,row,self.window,self.member,'search') for row in batch]
            self.evaluated.add(prompt_hash(prompt))
        else:
            observations=[{'correct':False,'prediction_valid':False,'text':'',
                           'answer':'','invalid_reason':'CANDIDATE_CONTRACT_REJECTED'} for _ in batch]
        append(self.private/'evaluations.jsonl',{'prompt_hash':prompt_hash(prompt),
            'ids':[r['example_id'] for r in batch],'scores':[int(o['correct']) for o in observations],
            'contract_valid':admissible,'candidate_guard':GUARD_ID,
            **checked,
            'capture_traces':capture_traces,'metrics_used':self.metrics_used})
        return EvaluationBatch(outputs=observations,scores=[float(o['correct']) for o in observations],
            trajectories=list(zip(batch,observations,strict=True)) if capture_traces else None,
            objective_scores=None)
    def make_reflective_dataset(self,candidate,eval_batch,components_to_update):
        if components_to_update!=[MUTABLE_KEY] or eval_batch.trajectories is None:
            raise ProtocolViolation('REFLECTION_COMPONENT_MISMATCH')
        self.reflection_source_ids=[row['example_id'] for row,_ in eval_batch.trajectories]
        return {MUTABLE_KEY:[{'Problem':row['problem'],'Current Member Response':out['text'],
            'Parsed Answer':out['answer'],'Gold Answer':row['reference'],'Correct':out['correct'],
            'Valid':out['prediction_valid'],'Failure Reason':out['invalid_reason']}
            for row,out in eval_batch.trajectories]}

def select_candidates(result,history: History,adapter: MathAdapter,limit: int) -> list[dict[str,Any]]:
    """Native best, leading native frontier, then deterministic hash-order extras."""
    selected=[]; seen=set()
    def add(prompt,rule,native_index=None,generation=None,parent_idx=None):
        identity=prompt_hash(prompt)
        if len(selected)>=limit or identity in seen or identity==prompt_hash(INITIAL): return
        if identity not in adapter.evaluated or not adapter.check_candidate(prompt)['contract_valid']: return
        seen.add(identity); selected.append({'prompt':prompt,'prompt_hash':identity,'selection_rule':rule,
            'native_index':native_index,'generation':generation,'parent_idx':parent_idx})
    add(result.best_candidate[MUTABLE_KEY],'native_best',result.best_idx)
    frontier=sorted({i for indices in result.per_val_instance_best_candidates.values() for i in indices},
                    key=lambda i:(-result.val_aggregate_scores[i],i))
    for index in frontier:
        add(result.candidates[index][MUTABLE_KEY],'native_pareto',index)
    for row in sorted(history.proposals,key=lambda r:(r['prompt_hash'],r['generation'])):
        add(row['prompt'],'hash_order_evaluated_proposal',generation=row['generation'],parent_idx=row['parent_idx'])
    by_hash={row['prompt_hash']:row for row in history.proposals}
    for row in selected:
        generated=by_hash.get(row['prompt_hash'])
        if generated:
            row['generation']=generated['generation']; row['parent_idx']=generated['parent_idx']
        parent_idx=row['parent_idx']
        row['parent_prompt_hash']=prompt_hash(result.candidates[parent_idx][MUTABLE_KEY]) if parent_idx is not None else None
    return selected

def run_window(runtime: Runtime,examples: list[dict[str,Any]],config: dict[str,Any],window: int,member: int,private: Path):
    private.mkdir(parents=True)
    logical_before=runtime.logical['search']
    review=(CandidateReview(private,runtime.identity,window,member,examples,runtime.shell,
                            config['owner_review_timeout_seconds'],config.get('reviewer_identity','offline_fixture'))
            if config.get('candidate_review_policy')==POLICY else None)
    adapter=MathAdapter(runtime,examples,window,member,private,review=review);history=History(private,adapter)
    if review is not None:
        runtime.candidate_checks[(window,member)]=adapter.check_candidate
    valset=sorted(examples,key=lambda row:digest({'seed':81,'window':window,'id':row['example_id']}))[:6]
    def stopper(state):
        # An entire reflective step reserves 3 parent + 3 child + at most 6 native val metrics.
        return len(history.proposals)>=6 or 36-adapter.metrics_used<12
    result=gepa.optimize(seed_candidate={MUTABLE_KEY:INITIAL},trainset=examples,valset=valset,adapter=adapter,
        reflection_lm=lambda prompt:runtime.reflect(prompt,window),reflection_prompt_template=REFLECTION_TEMPLATE,
        candidate_selection_strategy='pareto',frontier_type='instance',module_selector='round_robin',
        skip_perfect_score=False,perfect_score=1.0,reflection_minibatch_size=3,use_merge=False,
        cache_evaluation=False,stop_callbacks=stopper,max_metric_calls=None,callbacks=[history],
        run_dir=str(private/'native_gepa'),logger=PrivateLogger(private/'native_log.jsonl'),
        display_progress_bar=False,seed=81000+window,raise_on_exception=True,track_best_outputs=True)
    write(private/'native_result.json',result.to_dict())
    selected=select_candidates(result,history,adapter,config['full_candidates_per_window'])
    native_best=result.best_candidate[MUTABLE_KEY]
    # P0 remains independently measured even if native GEPA selects no changed prompt.
    selection={'window':window,'member':member,'gepa_seed':81000+window,
        'native_validation_ids':[r['example_id'] for r in valset],
        'native_best_hash':prompt_hash(native_best),'native_best_idx':result.best_idx,
        'native_best_score':result.val_aggregate_scores[result.best_idx],
        'native_initial_score':result.val_aggregate_scores[0],
        'native_archive_count':len(result.candidates),
        'native_frontier_indices':sorted({i for indices in result.per_val_instance_best_candidates.values() for i in indices}),
        'native_archive':[{'index':i,'prompt_hash':prompt_hash(c[MUTABLE_KEY]),'parents':result.parents[i],
            'score':result.val_aggregate_scores[i],'correctness':result.val_subscores[i],
            'discovery_eval_count':result.discovery_eval_counts[i]} for i,c in enumerate(result.candidates)],
        'proposal_count':len(history.proposals),'unique_proposal_count':len({r['prompt_hash'] for r in history.proposals}),
        'contract_rejections':sum(not r['contract_valid'] for r in history.proposals),
        'search_metric_count':adapter.metrics_used,'native_metric_count':result.total_metric_calls,
        'actual_solver_logical_evaluations':runtime.logical['search']-logical_before,
        'guard_rejection_metric_scores':adapter.metrics_used-(runtime.logical['search']-logical_before),
        'candidate_guard':GUARD_ID,
        'proposal_audit':[{k:v for k,v in row.items() if k!='prompt'} for row in history.proposals],
        'stop_reason':'pre_registered_metric_step_reserve_or_proposal_cap',
        'selected':selected,'selected_hashes':[r['prompt_hash'] for r in selected]}
    import json
    eval_rows=[json.loads(line) for line in (private/'evaluations.jsonl').read_text(encoding='utf-8').splitlines()]
    for row in selected:
        row['discovery_search_metric']=next(e['metrics_used'] for e in eval_rows if e['prompt_hash']==row['prompt_hash'])
    write(private/'selection.json',selection)
    return selection
