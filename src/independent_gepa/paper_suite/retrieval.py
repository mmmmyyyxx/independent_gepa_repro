"""Offline staging of the author's Wikipedia/BM25 resources outside upstream."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tarfile

from .sources import file_hash
from .data import canonical


def prepare(workspace: Path, *, build_index=False, minimum_free_gib=8.0) -> dict:
    root = workspace / "retrieval"
    root.mkdir(exist_ok=True)
    archive = workspace / "assets/wiki.abstracts.2017.tar.gz"
    inputs = json.loads((workspace / "public_inputs.json").read_text())
    if file_hash(archive) != inputs["files"][archive.name]["sha256"]:
        raise ValueError("WIKIPEDIA_ARCHIVE_HASH_MISMATCH")
    corpus_path = root / "wiki.abstracts.2017.jsonl"
    if not corpus_path.exists():
        # Explicit single-file streaming avoids extractall traversal and never
        # materializes all Wikipedia documents just to unpack the resource.
        with tarfile.open(archive, "r:gz") as tar:
            candidates = [m for m in tar.getmembers() if Path(m.name).name == corpus_path.name and m.isfile()]
            if len(candidates) != 1:
                raise ValueError("UNEXPECTED_WIKIPEDIA_ARCHIVE_MEMBERS")
            with tar.extractfile(candidates[0]) as source, corpus_path.with_suffix(".part").open("xb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
        corpus_path.with_suffix(".part").replace(corpus_path)
    receipt = {"schema": "author_wikipedia_bm25_resources_v1", "archive_sha256": file_hash(archive),
               "corpus_sha256": file_hash(corpus_path), "corpus_bytes": corpus_path.stat().st_size,
               "index_ready": False, "MODEL_API_CALLS": 0}
    if build_index:
        import psutil
        available = psutil.virtual_memory().available
        if available < minimum_free_gib * 1024 ** 3:
            raise RuntimeError("BM25_BUILD_REQUIRES_FREE_MEMORY; no index build started")
        index = root / "bm25s_retriever"
        if index.exists():
            raise ValueError("FRESH_INDEX_DIRECTORY_REQUIRED; existing index preserved")
        import bm25s
        import Stemmer
        import ujson
        corpus = []
        with corpus_path.open(encoding="utf-8") as stream:
            for line in stream:
                row = ujson.loads(line)
                corpus.append(f"{row['title']} | {' '.join(row['text'])}")
        stemmer = Stemmer.Stemmer("english")
        tokens = bm25s.tokenize(corpus, stopwords="en", stemmer=stemmer)
        retriever = bm25s.BM25(k1=0.9, b=0.4)
        retriever.index(tokens)
        retriever.save(str(index))
        receipt.update(index_ready=True, documents=len(corpus),
                       index_files={p.relative_to(index).as_posix(): file_hash(p) for p in index.rglob("*") if p.is_file()})
    receipt_path = root / ("index_receipt.json" if build_index else "corpus_receipt.json")
    if receipt_path.exists():
        old = json.loads(receipt_path.read_text())
        if old != receipt:
            raise ValueError("EXISTING_RETRIEVAL_RECEIPT_MISMATCH")
    else:
        receipt_path.write_bytes(canonical(receipt) + b"\n")
    return receipt
