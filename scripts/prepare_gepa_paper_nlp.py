"""Download/cache public NLP resources only; no inference or model API calls."""
import argparse
import json
from pathlib import Path
import urllib.request

from _bootstrap import ROOT
from independent_gepa.paper_suite.sources import file_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT / "runs/gepa_paper_suite_20261031")
    parser.add_argument("--direct", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if not workspace.is_relative_to((ROOT / "runs").resolve()):
        raise ValueError("NLP_RESOURCES_MUST_REMAIN_IN_IGNORED_RUNS")
    if args.direct:
        urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
    import nltk
    import spacy
    spacy.load("en_core_web_sm")
    root = workspace / "nlp/nltk_data"
    root.mkdir(parents=True, exist_ok=True)
    for name in ("punkt_tab", "punkt", "averaged_perceptron_tagger_eng", "stopwords"):
        if not nltk.download(name, download_dir=str(root), quiet=True, raise_on_error=True):
            raise RuntimeError("NLP_RESOURCE_PREPARATION_FAILED")
    files = {p.relative_to(root).as_posix(): file_hash(p) for p in root.rglob("*") if p.is_file()}
    target = workspace / "nlp/receipt.json"
    receipt = {"files": files, "MODEL_API_CALLS": 0}
    if target.exists() and json.loads(target.read_text()) != receipt:
        raise ValueError("NLP_RESOURCE_RECEIPT_MISMATCH")
    target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"NLP_RESOURCE_FILES": len(files), "MODEL_API_CALLS": 0}))


if __name__ == "__main__":
    main()
