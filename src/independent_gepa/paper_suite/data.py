"""Read-only membership preparation; invoke author split code without model APIs."""
from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import random
from types import SimpleNamespace
from typing import Callable, List, Type

from .contract import TASKS
from .sources import file_hash, syntax_node


class DataExample(dict):
    """Only the storage/with_inputs operations used by author dataset loaders."""
    def with_inputs(self, *names):
        self.input_keys = names
        return self


def canonical(value) -> bytes:
    def encode_metadata(obj):
        if isinstance(obj, (date, datetime)):
            return {"__paper_metadata_type__": type(obj).__name__, "iso": obj.isoformat()}
        raise TypeError(f"UNSUPPORTED_PAPER_METADATA_TYPE:{type(obj).__name__}")
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False, default=encode_metadata).encode("utf-8")


def decode_metadata(obj):
    if set(obj) == {"__paper_metadata_type__", "iso"}:
        classes = {"date": date, "datetime": datetime}
        return classes[obj["__paper_metadata_type__"]].fromisoformat(obj["iso"])
    return obj


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _class(path, name, namespace):
    node = syntax_node(path, name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


def load_asset_rows(assets: Path) -> dict:
    import pyarrow.parquet as pq
    def parquet(name):
        return pq.read_table(assets / name).to_pylist()
    # Author's Hotpot loader only wraps rows before splitting/sampling. Select
    # those original positions first, then hydrate the selected rows by rowgroup.
    # This avoids expanding all 90k contexts on a shared Windows research host.
    hotpot_count = sum(pq.ParquetFile(assets / f"hotpot_{i}.parquet").metadata.num_rows for i in range(2))
    hotpot = [{"_paper_parquet_index": i} for i in range(hotpot_count)]
    hover = json.loads((assets / "hover_train.json").read_text(encoding="utf-8"))
    # The pinned HuggingFace hover.py declares this exact ClassLabel ordering.
    # Reproduce HF encoding, rather than leaving raw release label strings.
    labels = {"NOT_SUPPORTED": 0, "SUPPORTED": 1}
    hover = [{**x, "label": labels[x["label"]],
              "supporting_facts": [{"key": s[0], "value": s[1]}
                                    for s in x["supporting_facts"]]} for x in hover]
    return {"_assets": assets, "hotpot_qa": {"train": hotpot}, "hover": {"train": hover},
            "AI-MO/aimo-validation-aime": {"train": parquet("aime_train_0.parquet")},
            "MathArena/aime_2025": {"train": parquet("aime_test_0.parquet")},
            "livebench/math": {"test": parquet("livebench.parquet")}}


def author_splits(artifact: Path, rows: dict, *, example_class=DataExample) -> dict:
    """Execute pinned class bodies, including Benchmark.trim_dataset(seed=1).

    Only IFBench's redundant NLTK download is suppressed during membership
    preparation. It contributes no dataset values. Runtime NLP resources have
    a separate readiness gate. All data/split statements are original source.
    """
    base = artifact / "gepa_artifact/benchmarks"
    ns = dict(ABC=ABC, abstractmethod=abstractmethod, dspy=SimpleNamespace(Example=example_class),
              random=random, Callable=Callable, List=List, Type=Type,
              dataset_size={"full": None, "lite": 500, "tiny": 200, "test": 50})
    benchmark = _class(base / "benchmark.py", "Benchmark", ns)
    def dataset(name, *args, **kwargs):
        return rows[name]
    modules = {"hotpotqa": "hotpotQA/hotpot_data.py", "hover": "hover/hover_data.py",
               "aime2025": "AIME/AIME_data.py", "livebench_math": "livebench_math/livebenchmath_data.py"}
    result = {}
    for task in TASKS:
        if task.key == "ifbench":
            train = [example_class(**json.loads(s)).with_inputs("prompt") for s in
                     (base / "IFBench/data/IFBench_train.jsonl").read_text(encoding="utf-8").splitlines()]
            test = [example_class(**json.loads(s)).with_inputs("prompt") for s in
                    (base / "IFBench/data/IFBench_test.jsonl").read_text(encoding="utf-8").splitlines()]
            # The exact loader assignments, followed by the inherited trim.
            class IFPrepared(benchmark):
                def init_dataset(self):
                    self.train_set = train[300:600]
                    self.val_set = train[:300]
                    self.test_set = test
                    self.dataset = self.train_set + self.val_set + self.test_set
            obj = IFPrepared()
        else:
            path = base / modules[task.key]
            context = dict(ns, Benchmark=benchmark, load_dataset=dataset,
                           tqdm=SimpleNamespace(tqdm=lambda x: x),
                           count_unique_docs=lambda x: len({s["key"] for s in x["supporting_facts"]}))
            obj = _class(path, task.benchmark, context)()
        splits = dict(train=[dict(x) for x in obj.train_set],
                      validation=[dict(x) for x in obj.val_set], test=[dict(x) for x in obj.test_set])
        if task.key == "hotpotqa" and "_assets" in rows:
            import pyarrow.parquet as pq
            selected = {x["_paper_parquet_index"] for group in splits.values() for x in group}
            hydrated = {}
            offset = 0
            for index in range(2):
                pf = pq.ParquetFile(rows["_assets"] / f"hotpot_{index}.parquet")
                for group in range(pf.num_row_groups):
                    size = pf.metadata.row_group(group).num_rows
                    wanted = sorted(i for i in selected if offset <= i < offset + size)
                    if wanted:
                        table = pf.read_row_group(group)
                        for i in wanted:
                            hydrated[i] = table.slice(i - offset, 1).to_pylist()[0]
                    offset += size
            splits = {s: [hydrated[x["_paper_parquet_index"]] for x in group]
                      for s, group in splits.items()}
        counts = tuple(len(splits[k]) for k in ("train", "validation", "test"))
        if counts != task.sizes:
            raise ValueError(f"AUTHOR_SPLIT_COUNT_MISMATCH:{task.key}:{counts}")
        result[task.key] = splits
    if len(rows["livebench/math"]["test"]) != 368:
        raise ValueError("LIVEBENCH_PAPER_SNAPSHOT_MUST_HAVE_368_ROWS")
    if len(rows["AI-MO/aimo-validation-aime"]["train"]) != 90:
        raise ValueError("AIME_PRIOR_YEAR_POOL_MUST_HAVE_90_ROWS")
    return result


def item_identity(task: str, row: dict) -> str:
    key = {"hotpotqa": "question", "hover": "claim", "ifbench": "prompt",
           "aime2025": "problem", "livebench_math": "question"}[task]
    return digest(row[key])


def write_bundle(artifact: Path, assets: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("FRESH_DATA_BUNDLE_DIRECTORY_REQUIRED")
    splits = author_splits(artifact, load_asset_rows(assets))
    summary = {}
    overlaps = {}
    duplicates = {}
    for task, task_splits in splits.items():
        ids = {s: [item_identity(task, x) for x in rows] for s, rows in task_splits.items()}
        overlaps[task] = {f"{left}:{right}": len(set(ids[left]) & set(ids[right])) for left, right in
                          [("train", "validation"), ("train", "test"), ("validation", "test")]}
        duplicates[task] = {s: len(v) - len(set(v)) for s, v in ids.items()}
        if task == "aime2025":
            from collections import Counter
            if set(Counter(ids["test"]).values()) != {5} or len(set(ids["test"])) != 30:
                raise ValueError("AIME_TEST_REPEAT_CONTRACT_MISMATCH")
        # Reproducing a published loader never authorizes silently deduplicating
        # its output. Preserve author membership, disclose overlap and HOLD any
        # formal grant until that concrete limitation is reviewed.
        summary[task] = {}
        for split, rows in task_splits.items():
            path = output / task / (split + ".jsonl")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as f:
                for i, row in enumerate(rows):
                    f.write(canonical({"id": f"{task}:{split}:{i}", "content_id": ids[split][i],
                                       "example": row}) + b"\n")
            summary[task][split] = {"count": len(rows), "unique_content": len(set(ids[split])),
                                   "file_sha256": file_hash(path), "ordered_membership_sha256": digest(ids[split])}
    receipt = {"schema": "gepa_paper_data_bundle_v1", "splits": summary,
               "assets": {p.name: {"sha256": file_hash(p), "bytes": p.stat().st_size}
                          for p in assets.iterdir() if p.is_file() and not p.name.endswith(".part")},
               "cross_split_content_overlap": overlaps, "within_split_duplicate_content": duplicates,
               "strict_content_disjointness": not any(n for task in overlaps.values() for n in task.values()),
               "READY_TO_RUN": False, "model_api_calls": 0}
    (output / "receipt.json").write_bytes(canonical(receipt) + b"\n")
    return receipt
