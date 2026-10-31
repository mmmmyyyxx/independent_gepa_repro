"""Fetch public reproduction inputs only; never imports or calls an LLM client."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

from _bootstrap import ROOT
from independent_gepa.paper_suite.contract import ARTIFACT_COMMIT, DSPY_COMMIT, LIVEBENCH_REVISION
from independent_gepa.paper_suite.sources import verify_checkout, file_hash

SOURCES = {
    "gepa-artifact": ("https://github.com/gepa-ai/gepa-artifact.git", ARTIFACT_COMMIT, "main"),
    "dspy-study": ("https://github.com/gepa-ai/dspy.git", DSPY_COMMIT, "gepa_study"),
}
ASSETS = {
    "hotpot_0.parquet": "https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/1908d6afbbead072334abe2965f91bd2709910ab/fullwiki/train-00000-of-00002.parquet?download=true",
    "hotpot_1.parquet": "https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/1908d6afbbead072334abe2965f91bd2709910ab/fullwiki/train-00001-of-00002.parquet?download=true",
    "aime_train_0.parquet": "https://huggingface.co/datasets/project-numina/aimo-validation-aime/resolve/13f9e12f613e720c2a2b2f345dd04b998a29494d/data/train-00000-of-00001.parquet?download=true",
    "aime_test_0.parquet": "https://huggingface.co/datasets/MathArena/aime_2025/resolve/c94da77eb22bbd6439e62a323bec18493a421302/data/train-00000-of-00001.parquet?download=true",
    "livebench.parquet": f"https://huggingface.co/datasets/livebench/math/resolve/{LIVEBENCH_REVISION}/data/test-00000-of-00001.parquet?download=true",
}


def download(opener, url: str, path: Path) -> dict:
    """Stage complete downloads; never treat a partial file as an asset."""
    if path.exists():
        return {"sha256": file_hash(path), "bytes": path.stat().st_size, "reused": True}
    for attempt in range(4):
        try:
            with opener.open(url, timeout=120) as response, path.with_suffix(path.suffix + ".part").open("wb") as out:
                expected = response.headers.get("Content-Length")
                count = 0
                h = hashlib.sha256()
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    out.write(block)
                    h.update(block)
                    count += len(block)
                if expected is not None and count != int(expected):
                    raise OSError("PUBLIC_DOWNLOAD_TRUNCATED")
            path.with_suffix(path.suffix + ".part").replace(path)
            return {"sha256": h.hexdigest(), "bytes": count, "reused": False}
        except urllib.error.HTTPError as exc:
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == 3:
                raise
        except (OSError, TimeoutError):
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT / "runs/gepa_paper_suite_20261031")
    parser.add_argument("--direct", action="store_true", help="ignore broken system proxies for public downloads")
    args = parser.parse_args()
    root = args.workspace.resolve()
    if not root.is_relative_to((ROOT / "runs").resolve()):
        raise ValueError("PUBLIC_INPUTS_MUST_REMAIN_IN_IGNORED_RUNS")
    (root / "upstream").mkdir(parents=True, exist_ok=True)
    (root / "assets").mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not any(marker in k.upper() for marker in
           ["API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTHORIZATION"])}
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    if args.direct:
        env = {k: v for k, v in env.items() if "PROXY" not in k.upper()}
    options = ["-c", "http.proxy="] if args.direct else []
    for name, (url, commit, branch) in SOURCES.items():
        path = root / "upstream" / name
        if not path.exists():
            subprocess.run(["git", *options, "clone", "--branch", branch, "--no-checkout", url, str(path)],
                           env=env, check=True)
            subprocess.run(["git", "-C", str(path), "checkout", "--detach", commit], env=env, check=True)
        verify_checkout(path, commit)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if args.direct else urllib.request.build_opener()
    # Resolve external content repositories before fetching, then preserve those
    # exact identities. Never use a moving main URL as frozen dataset identity.
    metadata = {}
    for name, url in {"hover": "https://api.github.com/repos/hover-nlp/hover/commits/main",
                      "wiki": "https://huggingface.co/api/models/dspy/cache"}.items():
        with opener.open(url, timeout=60) as response:
            metadata[name] = json.load(response)
    hover_sha, wiki_sha = metadata["hover"]["sha"], metadata["wiki"]["sha"]
    assets = {**ASSETS,
              "hover_train.json": f"https://raw.githubusercontent.com/hover-nlp/hover/{hover_sha}/data/hover/hover_train_release_v1.1.json",
              "wiki.abstracts.2017.tar.gz": f"https://huggingface.co/dspy/cache/resolve/{wiki_sha}/wiki.abstracts.2017.tar.gz?download=true"}
    receipt = {"schema": "gepa_paper_public_inputs_v1", "MODEL_API_CALLS": 0,
               "hover_revision": hover_sha, "wiki_revision": wiki_sha, "files": {}}
    for name, url in assets.items():
        receipt["files"][name] = {"url": url, **download(opener, url, root / "assets" / name)}
        print(json.dumps({"asset": name, "bytes": receipt["files"][name]["bytes"]}), flush=True)
    receipt_path = root / "public_inputs.json"
    if receipt_path.exists():
        raise ValueError("EXISTING_INPUT_RECEIPT_MUST_NOT_BE_OVERWRITTEN")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
