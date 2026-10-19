"""Unmodified upstream GEPA search with registered, observable component boundaries."""
from __future__ import annotations

from copy import deepcopy
from functools import wraps
from pathlib import Path

from gepa import optimize
from gepa.core.adapter import EvaluationBatch

from ..protocol import ProtocolViolation
from .common import Abort,digest,write,progress
from .feedback import worked_reference
from .prompt import SystemPrompt


def candidate_hash(candidate):
    try:return SystemPrompt.from_dict(candidate).prompt_hash
    except ProtocolViolation:return digest(candidate)


def fail_closed(function):
    @wraps(function)
    def checked(*args,**kwargs):
        try:return function(*args,**kwargs)
        except Abort:raise
        except BaseException as exc:raise Abort('NATIVE_BOUNDARY_FAILURE:'+function.__name__+':'+type(exc).__name__) from exc
    return checked


class History:
    def __init__(self,adapter,directory):
        self.adapter=adapter;self.directory=directory;self.iterations=[];self.proposals=[]
        self.parent=None;self.pending=None

    @fail_closed
    def save(self):
        write(self.directory/'proposals.json',self.proposals)
        write(self.directory/'iterations.json',self.iterations)
        write(self.directory/'candidate_decisions.json',self.adapter.decisions)

    @fail_closed
    def on_iteration_start(self,event):
        self.pending=None;self.adapter.pending=None
        self.iterations.append({'iteration':event['iteration'],'proposal_accepted':None,
            'pool_validation_scores_before':list(event['state'].program_full_scores_val_set)})

    @fail_closed
    def on_candidate_selected(self,event):
        self.iterations[-1].update(parent_native_index=event['candidate_idx'],
            parent_hash=candidate_hash(event['candidate']),parent_validation_score=event['score'])

    @fail_closed
    def on_proposal_start(self,event):
        self.parent=deepcopy(event['parent_candidate'])

    @fail_closed
    def on_minibatch_sampled(self,event):
        self.iterations[-1]['minibatch_ids']=list(event['minibatch_ids'])

    @fail_closed
    def on_proposal_end(self,event):
        child={**self.parent,**event['new_instructions']};sha=candidate_hash(child)
        prompt=SystemPrompt.from_dict(child)
        row={'generation':len(self.proposals)+1,'iteration':self.iterations[-1]['iteration'],
            'candidate_hash':sha,'candidate':child,'parent_hash':candidate_hash(self.parent),
            'native_parseable':True,'semantic_guard_evaluated':False,'guard_policy':'native_only',
            'reflection_source_ids':[e['example_id'] for e in self.adapter.reflection_examples],
            'native_accepted':False,'local_positive':None}
        self.proposals.append(row);self.pending=row
        self.adapter.pending=row
        self.adapter.decisions[sha]=deepcopy(row)
        self.adapter.runtime.register_prompt(prompt,self.adapter.repeat)
        self.adapter.runtime.event('CANDIDATE_REGISTERED',arm=self.adapter.runtime.arm,repeat=self.adapter.repeat,candidate_hash=sha,
            generation=row['generation'],registration_sha256=digest(row))
        self.save()

    @fail_closed
    def on_candidate_accepted(self,event):
        if self.pending:
            self.pending['native_accepted']=True;self.pending['local_positive']=True
            self.pending['native_candidate_index']=event['new_candidate_idx'];self.save()

    @fail_closed
    def on_candidate_rejected(self,event):
        if self.pending:
            self.pending['local_positive']=event['new_score']>event['old_score']
            self.pending['native_rejection_reason']=event['reason'];self.save()

    @fail_closed
    def on_iteration_end(self,event):
        self.iterations[-1]['proposal_accepted']=event['proposal_accepted'];self.save()
        progress(f'GEPA repeat={self.adapter.repeat} iteration={event["iteration"]} generated={len(self.proposals)} accepted={event["proposal_accepted"]}')


class Adapter:
    propose_new_texts=None
    def __init__(self,runtime,repeat,initial,optimize_rows,validation_rows,budget=None):
        self.runtime=runtime;self.repeat=repeat;self.reflection_examples=[];self.pending=None
        self.members={r['stable_example_id']:(split,r) for split,rows in
            (('optimize',optimize_rows),('validation',validation_rows)) for r in rows}
        self.decisions={candidate_hash(initial):{'native_parseable':True,'origin':'frozen_initial'}}
        self.native_metric_calls=0;self.reflection_calls=0
        self.budget=budget

    def evaluate(self,batch,candidate,capture_traces=False):
        try:
            sha=candidate_hash(candidate);decision=self.decisions.get(sha)
            if self.pending and sha==self.pending['candidate_hash'] and not capture_traces:decision=self.pending
            if decision is None:raise Abort('NATIVE_CANDIDATE_WITHOUT_REGISTRATION_RECORD')
            split=None
            for row in batch:
                member=self.members.get(row['stable_example_id'])
                if member is None or member[1]!=row:raise Abort('NATIVE_DATA_MEMBERSHIP_MISMATCH')
                if split is not None and split!=member[0]:raise Abort('MIXED_NATIVE_SPLIT_BATCH')
                split=member[0]
            if capture_traces and split!='optimize':raise Abort('VALIDATION_REFLECTION_FEEDBACK_FORBIDDEN')
            if self.budget is None:raise Abort('NATIVE_BUDGET_BINDING_REQUIRED')
            self.budget.admit(len(batch),'parent_trace' if capture_traces else split)
            self.native_metric_calls+=len(batch)
            prompt=SystemPrompt.from_dict(candidate)
            outputs=self.runtime.evaluate(prompt,batch,self.repeat,split)
            traces=[{'row':row,'observation':output} for row,output in zip(batch,outputs,strict=True)] if capture_traces else None
            return EvaluationBatch(outputs=outputs,scores=[float(o['correct']) for o in outputs],trajectories=traces)
        except Abort:raise
        except BaseException as exc:raise Abort('NATIVE_EVALUATION_OPERATIONAL_FAILURE:'+type(exc).__name__+':'+str(exc)) from exc

    @fail_closed
    def make_reflective_dataset(self,candidate,eval_batch,components_to_update):
        self.reflection_examples=[]
        for trace in eval_batch.trajectories:
            row=trace['row'];obs=trace['observation'];ident=row['stable_example_id']
            if self.members[ident][0]!='optimize':raise Abort('HELDOUT_REFLECTION_SOURCE')
            self.reflection_examples.append({'example_id':ident,'problem':row['content']['problem'],
                'reference':row['reference_final_answer'],'reference_solution':row['content']['solution'],
                'solver_response':obs['prediction']['text'] or ''})
        result={}
        for component in components_to_update:
            records=[]
            for trace,error in zip(eval_batch.trajectories,self.reflection_examples,strict=True):
                obs=trace['observation']
                records.append({'Inputs':{'problem':error['problem'],'current_system_blocks':deepcopy(candidate)},
                    'Generated Outputs':error['solver_response'],
                    'Feedback':{'correct':obs['correct'],'prediction_valid':obs['valid'],
                        'invalid_reason':obs['prediction']['invalid_reason'],'reference_final_answer':error['reference'],
                        'worked_reference':worked_reference(error['reference_solution']),
                        'editable_component':component}})
            result[component]=records
        return result


def run_repeat(runtime,config,initial,optimize_rows,validation_rows,directory: Path,repeat: int):
    import time
    from .budget import NativeBudget
    from .telemetry import MechanismHistory
    started=time.monotonic()
    directory.mkdir(parents=True)
    initial={k:initial[k] for k in config['mutable_components']}
    budget=NativeBudget(config['native_logical_budget'],len(validation_rows),config['reflection_minibatch_size'],config['max_native_proposals'])
    root_prompt=SystemPrompt.from_dict(initial)
    runtime.register_prompt(root_prompt,repeat)
    before=runtime.evaluate(root_prompt,optimize_rows,repeat,'optimize','initial_diagnostic')
    write(directory/'initial_optimize.json',before)
    adapter=Adapter(runtime,repeat,initial,optimize_rows,validation_rows,budget)
    history=MechanismHistory(adapter,directory,validation_rows,budget,config['budget_milestones'])
    # Keep upstream logging containing private prompts exclusively in the ignored run directory.
    class PrivateLogger:
        @fail_closed
        def log(self,message):
            with (directory/'native.log').open('a',encoding='utf-8') as stream:stream.write(str(message)+'\n')
    result=optimize(seed_candidate=deepcopy(initial),trainset=optimize_rows,valset=validation_rows,adapter=adapter,
        reflection_lm=lambda prompt:runtime.reflect(prompt,repeat),
        candidate_selection_strategy=config['selectors'][runtime.arm],frontier_type=config['frontier_type'],
        reflection_minibatch_size=config['reflection_minibatch_size'],
        module_selector=config['module_selector'],
        skip_perfect_score=config['skip_perfect_score'],use_merge=config['use_merge'],
        cache_evaluation=config['cache_evaluation'],val_evaluation_policy=config['val_evaluation_policy'],
        stop_callbacks=budget,seed=config['seed'],
        run_dir=str(directory/'native'),logger=PrivateLogger(),callbacks=[history],
        display_progress_bar=False,raise_on_exception=True)
    selected=result.best_candidate;sha=candidate_hash(selected)
    if sha not in adapter.decisions:raise Abort('NATIVE_SELECTED_WITHOUT_REGISTRATION')
    write(directory/'native_result.json',result.to_dict())
    write(directory/'search_result.json',{**result.to_dict(),'engine':'unmodified_native_gepa_v0.1.1'})
    history.save()
    after=runtime.evaluate(SystemPrompt.from_dict(selected),optimize_rows,repeat,'optimize','selected_diagnostic')
    history.finish()
    write(directory/'selected_optimize.json',after)
    old=[x['correct'] for x in before];new=[x['correct'] for x in after]
    record={'arm':runtime.arm,'repeat_id':repeat,'seed':42,'selected':selected,'selected_hash':sha,
        'native_best_index':result.best_idx,'validation_correct':round(result.val_aggregate_scores[result.best_idx]*len(validation_rows)),
        'initial_validation_correct':round(result.val_aggregate_scores[0]*len(validation_rows)),
        'native_iterations':len(history.iterations),'generated':len(history.proposals),
        'native_parseable':len(history.proposals),'semantic_guard_evaluated':False,'candidate_guard_policy':'native_only',
        'native_accepted':sum(p['native_accepted'] for p in history.proposals),
        'full_validation_evaluated':len(result.candidates)-1,
        'validation_improving_over_parent':sum(result.val_aggregate_scores[i]>result.val_aggregate_scores[result.parents[i][0]] for i in range(1,len(result.candidates))),
        'unique_generated':len({p['candidate_hash'] for p in history.proposals}),
        'native_metric_calls':adapter.native_metric_calls,'guard_zero_metrics':0,
        'upstream_total_metric_calls':result.total_metric_calls,'initial_optimize_correct':sum(old),
        'selected_optimize_correct':sum(new),'old_correct_retained':sum(a and b for a,b in zip(old,new,strict=True)),
        'old_correct_lost':sum(a and not b for a,b in zip(old,new,strict=True)),
        'newly_correct':sum(not a and b for a,b in zip(old,new,strict=True)),
        'native_budget':{k:v for k,v in budget.summary().items() if k!='batches'},
        'wall_seconds':time.monotonic()-started,'tokens':runtime.token_snapshot(repeat),
        'selector':config['selectors'][runtime.arm],'selection':'unmodified_native_result_best_candidate'}
    write(directory/'selection.json',record)
    return record
