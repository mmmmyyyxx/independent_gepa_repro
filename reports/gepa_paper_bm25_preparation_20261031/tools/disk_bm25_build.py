"""Native BM25S tokenizer/scorers with disk-backed corpus IDs and CSC storage.

No model libraries or benchmark examples are used. Term IDs may be permuted;
document order, stem strings, corpus-wide statistics and float32 scores are not.
"""
from pathlib import Path
from array import array
import argparse,gc,hashlib,json,os,time

import bm25s
import Stemmer
import numpy as np
import psutil
import ujson
from bm25s.scoring import _build_idf_array, _select_idf_scorer, _select_tfc_scorer, _get_counts_from_token_ids


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def atomic(path,value):
    path=Path(path);temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    temp.replace(path)


def progress(path,stage,**kwargs):
    value=dict(stage=stage,**kwargs,process_rss_bytes=psutil.Process().memory_info().rss,
               available_ram_bytes=psutil.virtual_memory().available,model_api_calls=0)
    atomic(path,value)
    print(json.dumps({k:v for k,v in value.items() if k!='private'}),flush=True)


def format_row(row):return f"{row['title']} | {' '.join(row['text'])}"


def stage_tokens(corpus,scratch,batch_size=2048):
    scratch.mkdir(parents=True,exist_ok=False)
    stemmer=Stemmer.Stemmer('english');vocab={};df=array('I')
    n=total=nnz=0;started=time.monotonic();h=hashlib.sha256()
    with Path(corpus).open('rb') as source,(scratch/'ids.i32').open('xb') as ids_file,(scratch/'offsets.u64').open('xb') as offsets:
        array('Q',[0]).tofile(offsets)
        while True:
            batch=[]
            for _ in range(batch_size):
                line=source.readline()
                if not line:break
                h.update(line);batch.append(format_row(ujson.loads(line)))
            if not batch:break
            # This is the original public tokenizer, not the alternate Tokenizer
            # class (which treats empty/stopword-only documents differently).
            tokenized=bm25s.tokenize(batch,stopwords='en',stemmer=stemmer,return_ids=False,show_progress=False)
            flat=array('I');ends=array('Q')
            for words in tokenized:
                ids=[]
                for word in words:
                    token=vocab.get(word)
                    if token is None:
                        token=len(vocab);vocab[word]=token;df.append(0)
                    ids.append(token)
                for token in set(ids):df[token]+=1
                nnz+=len(set(ids));flat.extend(ids);total+=len(ids);ends.append(total);n+=1
            flat.tofile(ids_file);ends.tofile(offsets)
            if n%65536<batch_size:
                ids_file.flush();offsets.flush()
                progress(scratch/'status.json','tokenizing',documents=n,tokens=total,vocabulary=len(vocab),
                         postings=nnz,elapsed_seconds=round(time.monotonic()-started,2))
        ids_file.flush();os.fsync(ids_file.fileno());offsets.flush();os.fsync(offsets.fileno())
    with (scratch/'vocab.build.json').open('x',encoding='utf-8') as f:
        json.dump(vocab,f,ensure_ascii=False,separators=(',',':'))
    with (scratch/'df.u32').open('xb') as f:df.tofile(f)
    meta=dict(documents=n,tokens=total,vocabulary=len(vocab),postings=nnz,corpus_sha256=h.hexdigest())
    atomic(scratch/'tokens.complete.json',meta)
    progress(scratch/'status.json','tokens_complete',**meta)
    return meta,vocab


class Frequencies:
    def __init__(self,counts):self.counts=counts
    def __len__(self):return len(self.counts)
    def items(self):return ((i,int(v)) for i,v in enumerate(self.counts))


def score_tokens(scratch,output,meta,vocab):
    n=meta['documents'];v=meta['vocabulary'];nnz=meta['postings']
    if max(n,v,nnz)>=np.iinfo(np.int32).max:raise ValueError('INT32_NATIVE_FORMAT_LIMIT')
    rows=np.memmap(scratch/'offsets.u64',dtype='<u8',mode='r',shape=(n+1,))
    ids=np.memmap(scratch/'ids.i32',dtype='<u4',mode='r',shape=(meta['tokens'],))
    df=np.memmap(scratch/'df.u32',dtype='<u4',mode='r',shape=(v,))
    idf=_build_idf_array(Frequencies(df),n,_select_idf_scorer('lucene'),dtype='float32')
    avg=np.float64(meta['tokens'])/np.float64(n)
    ptr=np.lib.format.open_memmap(scratch/'indptr.npy',mode='w+',dtype='int32',shape=(v+1,))
    ptr[0]=0;np.cumsum(df,dtype=np.int64,out=ptr[1:])
    if int(ptr[-1])!=nnz:raise ValueError('DOCUMENT_FREQUENCY_SUM_MISMATCH')
    data=np.lib.format.open_memmap(scratch/'data.npy',mode='w+',dtype='float32',shape=(nnz,))
    indices=np.lib.format.open_memmap(scratch/'indices.npy',mode='w+',dtype='int32',shape=(nnz,))
    cursor=np.array(ptr[:-1],dtype='int32',copy=True)
    tfc=_select_tfc_scorer('lucene');started=time.monotonic()
    for doc in range(n):
        tokens=ids[int(rows[doc]):int(rows[doc+1])].tolist()
        terms,frequencies=_get_counts_from_token_ids(tokens,dtype='float32',int_dtype='int32')
        weights=idf[terms]*tfc(tf_array=frequencies,l_d=len(tokens),l_avg=avg,k1=0.9,b=0.4,delta=0.5)
        positions=cursor[terms]
        data[positions]=weights;indices[positions]=doc;cursor[terms]+=1
        if (doc+1)%100000==0:
            progress(scratch/'status.json','scoring',documents=doc+1,total_documents=n,
                     elapsed_seconds=round(time.monotonic()-started,2))
    if not np.array_equal(cursor,ptr[1:]):raise ValueError('CSC_COLUMN_FILL_MISMATCH')
    data.flush();indices.flush();ptr.flush()
    for start in range(0,nnz,1000000):
        if not np.isfinite(data[start:start+1000000]).all():raise ValueError('NONFINITE_NATIVE_SCORE')
    retriever=bm25s.BM25(k1=0.9,b=0.4)
    retriever.scores={'data':data,'indices':indices,'indptr':ptr,'num_docs':n}
    if '' not in vocab:vocab['']=max(vocab.values())+1
    retriever.vocab_dict=vocab;retriever.nonoccurrence_array=None
    retriever.save(str(output))
    progress(scratch/'status.json','index_saved',documents=n,postings=nnz,vocabulary=v)
    return retriever


def compare(native,actual,texts):
    if set(native.vocab_dict)!=set(actual.vocab_dict):raise AssertionError('VOCABULARY_DRIFT')
    postings=0
    for word,index in native.vocab_dict.items():
        if index+1>=len(native.scores['indptr']):continue # native empty sentinel
        actual_index=actual.vocab_dict[word]
        a=slice(int(native.scores['indptr'][index]),int(native.scores['indptr'][index+1]))
        b=slice(int(actual.scores['indptr'][actual_index]),int(actual.scores['indptr'][actual_index+1]))
        if not np.array_equal(native.scores['indices'][a],actual.scores['indices'][b]):raise AssertionError('POSTING_DOCUMENT_DRIFT')
        if not np.array_equal(native.scores['data'][a],actual.scores['data'][b]):raise AssertionError('BITWISE_TERM_SCORE_DRIFT')
        postings+=a.stop-a.start
    stemmer=Stemmer.Stemmer('english');checked=0
    for text in texts:
        q=bm25s.tokenize(text,stopwords='en',stemmer=stemmer,show_progress=False)
        for k in (7,10):
            errors=[];answers=[]
            for engine in (native,actual):
                try:answers.append(engine.retrieve(q,k=k,n_threads=1,show_progress=False));errors.append(None)
                except Exception as exc:answers.append(None);errors.append(type(exc).__name__)
            if errors[0]!=errors[1]:raise AssertionError('QUERY_EXCEPTION_SEMANTICS_DRIFT')
            if not errors[0] and (not np.array_equal(answers[0][0],answers[1][0]) or not np.array_equal(answers[0][1],answers[1][1])):
                raise AssertionError('NATIVE_RANKING_OR_SCORE_DRIFT')
            checked+=1
    return {'postings_bitwise_checked':postings,'query_k_cases':checked,'mismatches':0}


def parity(workspace,output):
    corpus=workspace/'retrieval/wiki.abstracts.2017.jsonl';output.mkdir(parents=True,exist_ok=False)
    rows=[]
    with corpus.open('rb') as source:
        for _ in range(2048):rows.append(ujson.loads(source.readline()))
    rows += [{'title':'Synthetic','text':[x]} for x in ['', 'the and of','Cats cats running runs','Café São Paulo 日本語',
                                                    'tie alpha beta','tie alpha beta','123 123 1945','a I x','line\nwords']] * 3
    fixture=output/'corpus.private.jsonl'
    with fixture.open('xb') as f:
        for row in rows:f.write((json.dumps(row,ensure_ascii=False)+'\n').encode())
    native=bm25s.BM25(k1=0.9,b=0.4)
    native.index(bm25s.tokenize([format_row(x) for x in rows],stopwords='en',stemmer=Stemmer.Stemmer('english'),show_progress=False),show_progress=False)
    queries=['Alan Turing','Pacific Ocean','Cats running runs','São Paulo','1945 United Nations','tie alpha beta',
             'the and of','zzzznotinvocabularyyyyy','123 123','日本語']+[row['title'] for row in rows[::101]]
    reports=[]
    for batch_size in (1,127,2048):
        scratch=output/('scratch_'+str(batch_size));index=output/('index_'+str(batch_size))
        meta,vocab=stage_tokens(fixture,scratch,batch_size)
        score_tokens(scratch,index,meta,vocab)
        for mmap in (False,True):
            actual=bm25s.BM25.load(str(index),mmap=mmap)
            report=compare(native,actual,queries);report.update(batch_size=batch_size,mmap=mmap)
            reports.append(report)
    result={'native_bm25s_version':bm25s.__version__,'documents':len(rows),'cases':reports,
            'tokenizer':'unchanged native tokenize; en stopwords; PyStemmer english',
            'scoring':'unchanged native float32 IDF/TFC/count helpers; column IDs may be permuted',
            'model_api_calls':0}
    atomic(output/'parity.json',result);print(json.dumps({'parity':'PASS','cases':len(reports),'model_api_calls':0}),flush=True)


def build(workspace,parity_receipt):
    root=workspace/'retrieval';scratch=root/'disk_build_v1';output=root/'bm25s_retriever.building_v1';final=root/'bm25s_retriever'
    if final.exists() or output.exists():raise ValueError('FRESH_INDEX_TARGET_REQUIRED')
    proof=json.loads(parity_receipt.read_text());assert all(x['mismatches']==0 for x in proof['cases'])
    original=json.loads((root/'corpus_receipt.json').read_text())
    if sha(workspace/'assets/wiki.abstracts.2017.tar.gz')!=original['archive_sha256']:raise ValueError('ARCHIVE_DRIFT')
    if scratch.exists():
        meta=json.loads((scratch/'tokens.complete.json').read_text())
        vocab=json.loads((scratch/'vocab.build.json').read_text())
    else:meta,vocab=stage_tokens(root/'wiki.abstracts.2017.jsonl',scratch)
    if meta['corpus_sha256']!=original['corpus_sha256']:raise ValueError('CORPUS_DRIFT')
    score_tokens(scratch,output,meta,vocab)
    # Standard library format; only publish a finished immutable directory.
    files={p.name:sha(p) for p in output.iterdir() if p.is_file()}
    if set(files)!={'data.csc.index.npy','indices.csc.index.npy','indptr.csc.index.npy','params.index.json','vocab.index.json'}:
        raise ValueError('UNEXPECTED_NATIVE_INDEX_FORMAT')
    output.rename(final)
    receipt={**original,'index_ready':True,'documents':meta['documents'],'index_files':files,
             'builder':'native-bm25s-disk-backed-csc-v1','builder_sha256':sha(__file__),
             'parity_receipt_sha256':sha(parity_receipt),'native_bm25s_version':bm25s.__version__,
             'corpus_order_preserved':True,'score_dtype':'float32','index_dtype':'int32','postings':meta['postings'],
             'model_api_calls':0,'MODEL_API_CALLS':0}
    atomic(root/'index_receipt.json',receipt)
    progress(scratch/'status.json','complete',documents=meta['documents'],postings=meta['postings'],index_files=len(files))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['parity','build']);p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--output',type=Path);p.add_argument('--parity-receipt',type=Path);a=p.parse_args()
    if a.mode=='parity':parity(a.workspace,a.output)
    else:build(a.workspace,a.parity_receipt)
