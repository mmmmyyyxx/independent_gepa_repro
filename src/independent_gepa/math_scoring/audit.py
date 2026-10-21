"""Read-only regrading of explicitly authorized offline saved observations."""
import argparse,json,hashlib
from collections import Counter
from pathlib import Path
from . import score_math_response,CONTRACT_ID,contract_sha256

def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()
def file_hash(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return [json.loads(x) for x in p.read_bytes().splitlines() if x.strip()]
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=True,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
def run(corpus,previous_v7,previous_v1,historical,out):
    if out.exists():raise ValueError('FRESH_PRIVATE_AUDIT_OUTPUT_REQUIRED')
    samples=rows(corpus);old_v7={x['audit_id']:x for x in rows(previous_v7)};old_v1={x['audit_id']:x for x in rows(previous_v1)}
    assert len(samples)==3492 and len({r['audit_id'] for r in samples})==3492
    assert set(old_v7)==set(old_v1)=={r['audit_id'] for r in samples}
    terminal=json.loads(historical.read_bytes());assert len(terminal)==2700
    results=[];transitions={};old_counts={};reasons=Counter();unknown=Counter();unknown_reasons=Counter();terminal_candidates={}
    for sample in samples:
        identity=sample['audit_id'];new=score_math_response(sample['raw'],sample['gold']).to_dict();reasons[new['reason']]+=1
        olds={'V7':{k:old_v7[identity].get(k) for k in ('correct','valid','status','invalid_reason')}}
        olds.update({k:{f:v.get(f) for f in ('correct','prediction_valid','status','reason')} for k,v in old_v1[identity]['policies'].items()})
        changes={}
        for policy,old in olds.items():
            old_counts.setdefault(policy,Counter())[str(old['correct'])]+=1
            label=str(old['correct'])+'->'+str(new['correct']);transitions.setdefault(policy,Counter())[label]+=1
            if old['correct'] is None:changes[policy]='previously_unresolved_now_'+new['reason']
            elif old['correct']!=new['correct']:changes[policy]=new['reason']
        if old_v1[identity]['policies']['math_semantic_v1']['correct'] is None:
            unknown[str(new['correct'])]+=1;unknown_reasons[new['reason']]+=1
        record=dict(sample_id=identity,cell=sample['cell'],example_id=sample['example_id'],
            raw_response_hash=file_hash_bytes(sample['raw']),ground_truth_hash=file_hash_bytes(sample['gold']),
            old_policy_results=olds,new_result=new,change_reason=changes)
        results.append(record)
        key=sample['cell']+':'+sample['example_id'];prior=terminal.get(key)
        if prior is not None and digest(sample['raw'])==prior['raw_sha256']:
            terminal_candidates.setdefault(key,[]).append(record)
    assert len(terminal_candidates)==2700
    terminal_selected=[]
    for key,candidates in terminal_candidates.items():
        assert len({r['new_result']['correct'] for r in candidates})==1
        record=sorted(candidates,key=lambda r:r['sample_id'])[0]
        terminal_selected.append(dict(terminal_key=key,old_correct=terminal[key]['correct'],sample_id=record['sample_id'],new_correct=record['new_result']['correct'],new_reason=record['new_result']['reason']))
    subset=Counter(str(r['old_correct'])+'->'+str(r['new_correct']) for r in terminal_selected)
    out.mkdir(parents=True)
    target=out/'results.private.jsonl';target.write_text(''.join(json.dumps(x,ensure_ascii=True,sort_keys=True)+'\n' for x in results),encoding='utf-8',newline='\n')
    write(out/'terminal2700.private.json',terminal_selected)
    report=dict(contract=CONTRACT_ID,contract_sha256=contract_sha256(),count=3492,
        correct=sum(r['new_result']['correct'] for r in results),incorrect=sum(not r['new_result']['correct'] for r in results),
        unresolved=0,reasons=dict(reasons),old_counts={k:dict(v) for k,v in old_counts.items()},transitions={k:dict(v) for k,v in transitions.items()},
        former_semantic_unresolved44=dict(count=sum(unknown.values()),outcomes=dict(unknown),reasons=dict(unknown_reasons)),
        terminal2700=dict(count=2700,old_correct=sum(r['old_correct'] for r in terminal_selected),new_correct=sum(r['new_correct'] for r in terminal_selected),transitions=dict(subset)),
        sources={name:file_hash(p) for name,p in dict(corpus=corpus,v7=previous_v7,v1=previous_v1,terminal=historical).items()},
        output_sha256=file_hash(target),model_api_calls=0,historical_writes=0)
    assert report['former_semantic_unresolved44']['count']==44
    write(out/'summary.json',report);return report
def file_hash_bytes(x):return hashlib.sha256(x.encode('utf-8')).hexdigest() if isinstance(x,str) else digest(x)
def main():
    p=argparse.ArgumentParser();[p.add_argument('--'+n,required=True,type=Path) for n in ('corpus','previous-v7','previous-v1','historical','out')]
    a=p.parse_args();r=run(a.corpus,a.previous_v7,a.previous_v1,a.historical,a.out);print(json.dumps(r,sort_keys=True))
if __name__=='__main__':main()
