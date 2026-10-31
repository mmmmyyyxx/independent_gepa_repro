"""Independent zero-model checks of the completed native-format resource."""
from pathlib import Path
import argparse, gc, hashlib, importlib, json, sys, time
import bm25s
import Stemmer
import numpy as np
import psutil
import ujson
from bm25s.scoring import _select_idf_scorer, _select_tfc_scorer, _get_counts_from_token_ids


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main(workspace, output):
    started = time.monotonic()
    root = workspace / 'retrieval'
    receipt = json.loads((root / 'index_receipt.json').read_text())
    meta = json.loads((root / 'disk_build_v1/tokens.complete.json').read_text())
    index = root / 'bm25s_retriever'
    assert receipt['index_ready'] and receipt['documents'] == meta['documents']
    files = {}
    for name, expected in receipt['index_files'].items():
        path = index / name
        assert sha(path) == expected
        files[name] = {'sha256': expected, 'bytes': path.stat().st_size}
    params = json.loads((index / 'params.index.json').read_text())
    assert params['k1'] == .9 and params['b'] == .4
    assert params['method'] == 'lucene' and params['idf_method'] == 'lucene'
    queries = ['Alan Turing', 'Pacific Ocean', 'United Nations 1945', 'quantum mechanics',
               'Sao Paulo', 'solar system', 'mathematical logic', 'ancient Roman history']
    stemmer = Stemmer.Stemmer('english')
    references = {}
    # This is the exact default, non-mmap loader used by the frozen runtime.
    engine = bm25s.BM25.load(str(index))
    assert engine.scores['num_docs'] == meta['documents']
    assert engine.scores['data'].dtype == np.dtype('float32')
    assert engine.scores['indices'].dtype == np.dtype('int32')
    assert engine.scores['indptr'].dtype == np.dtype('int32')
    ptr = engine.scores['indptr']
    assert ptr[0] == 0 and ptr[-1] == meta['postings'] and (np.diff(ptr) > 0).all()
    for start in range(0, meta['postings'], 1000000):
        scores = engine.scores['data'][start:start+1000000]
        ids = engine.scores['indices'][start:start+1000000]
        assert np.isfinite(scores).all() and (scores >= 0).all()
        assert (ids >= 0).all() and (ids < meta['documents']).all()
    for number, query in enumerate(queries):
        tokens = bm25s.tokenize(query, stopwords='en', stemmer=stemmer, show_progress=False)
        for k in (7, 10):
            result, scores = engine.retrieve(tokens, k=k, n_threads=1, show_progress=False)
            assert result.shape == scores.shape == (1, k)
            references[number, k] = (result.copy(), scores.copy())
    del ptr, engine, scores, ids
    gc.collect()
    engine = bm25s.BM25.load(str(index), mmap=True)
    for number, query in enumerate(queries):
        tokens = bm25s.tokenize(query, stopwords='en', stemmer=stemmer, show_progress=False)
        for k in (7, 10):
            result, scores = engine.retrieve(tokens, k=k, n_threads=1, show_progress=False)
            a, b = references[number, k]
            assert np.array_equal(result, a) and np.array_equal(scores, b)
    print(json.dumps({'stage':'native_loaders_pass','documents':meta['documents']}), flush=True)
    # Preserve exact author corpus rendering and order; this is also the actual
    # list allocation required by the frozen runtime, not a disk-backed stand-in.
    corpus = []
    corpus_hash = hashlib.sha256()
    selected_ids = set(np.linspace(0, meta['documents'] - 1, 128, dtype=int).tolist())
    samples = {}
    with (root / 'wiki.abstracts.2017.jsonl').open('rb') as stream:
        for doc, line in enumerate(stream):
            corpus_hash.update(line)
            row = ujson.loads(line)
            text = f"{row['title']} | {' '.join(row['text'])}"
            corpus.append(text)
            if doc in selected_ids:
                samples[doc] = text
    assert len(corpus) == meta['documents'] and corpus_hash.hexdigest() == receipt['corpus_sha256']
    # Re-tokenize distributed documents, rederive DF from final CSC, and recompute
    # native weights independently of build-stage IDs, DF or saved score buffers.
    checked = 0
    ptr = engine.scores['indptr']
    idf_fn = _select_idf_scorer('lucene')
    tfc_fn = _select_tfc_scorer('lucene')
    avg = np.float64(meta['tokens']) / np.float64(meta['documents'])
    for doc, text in samples.items():
        words = bm25s.tokenize([text], stopwords='en', stemmer=stemmer,
                              return_ids=False, show_progress=False)[0]
        token_ids = [engine.vocab_dict[word] for word in words]
        terms, freq = _get_counts_from_token_ids(token_ids, dtype='float32', int_dtype='int32')
        idfs = np.array([idf_fn(int(ptr[t+1] - ptr[t]), N=meta['documents']) for t in terms], dtype='float32')
        # Native BM25S stores these float64 intermediates into its float32 CSC
        # buffer. Compare the same storage representation, without a tolerance.
        expected = np.asarray(idfs * tfc_fn(tf_array=freq, l_d=len(words), l_avg=avg,
                                          k1=.9, b=.4, delta=.5), dtype='float32')
        for term, weight in zip(terms, expected):
            lo, hi = int(ptr[term]), int(ptr[term+1])
            pos = lo + int(np.searchsorted(engine.scores['indices'][lo:hi], doc))
            assert pos < hi and engine.scores['indices'][pos] == doc
            assert engine.scores['data'][pos].tobytes() == weight.tobytes()
            checked += 1
    print(json.dumps({'stage':'full_corpus_and_sample_weights_pass','weight_checks':checked}), flush=True)
    sys.path[:0] = [str(workspace / 'upstream/gepa-artifact'), str(workspace / 'upstream/dspy-study')]
    hover = importlib.import_module('gepa_artifact.benchmarks.hover.hover_program')
    hotpot = importlib.import_module('gepa_artifact.benchmarks.hotpotQA.hotpot_program')
    assert hotpot.search is hover.search
    hover.retriever = engine
    hover.corpus = corpus
    hover.stemmer = stemmer
    hover.initialized = True
    programs = [hotpot.HotpotMultiHop(), hover.HoverMultiHop()]
    calls = 0
    for program in programs:
        retrievers = [program.retrieve_k]
        if hasattr(program, 'retrieve_10'):
            retrievers.append(program.retrieve_10)
        for retrieve in retrievers:
            assert retrieve.func is hover.search
            k = retrieve.keywords['k']
            for number, query in enumerate(queries):
                doc_ids, _ = references[number, k]
                expected = list(dict.fromkeys(corpus[int(doc)] for doc in doc_ids[0]))[:k]
                # Exercise the real decorated callable, including its real cache.
                actual = retrieve(query).passages
                assert actual == expected and retrieve(query).passages == expected
                calls += 2
    result = {'schema':'gepa_paper_full_bm25_verification_v1', 'status':'PASS',
              'documents':len(corpus), 'tokens':meta['tokens'], 'vocabulary':meta['vocabulary'],
              'postings':meta['postings'], 'corpus_sha256':corpus_hash.hexdigest(),
              'index_receipt_sha256':sha(root / 'index_receipt.json'), 'files':files,
              'parameters':params, 'native_loader_modes':[False,True],
              'native_loader_query_k_cases':len(references), 'loader_score_or_rank_mismatches':0,
              'full_posting_finite_and_bounds_checks':meta['postings'],
              'distributed_documents_retokenized':len(samples), 'native_weights_bitwise_checked':checked,
              'native_weight_mismatches':0, 'author_search_shared_between_tasks':True,
              'author_program_retrieval_calls_including_cache_repeats':calls,
              'author_program_retrieval_mismatches':0, 'exact_full_corpus_list_loaded':True,
              'process_rss_bytes':psutil.Process().memory_info().rss,
              'elapsed_seconds':round(time.monotonic()-started,2),
              'model_api_calls':0, 'model_tokens':0, 'sealed_test_inference':False}
    output.write_text(json.dumps(result, separators=(',',':')) + '\n')
    print(json.dumps({'verification':'PASS','retrieval_calls':calls,'model_api_calls':0}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    main(args.workspace, args.output)
