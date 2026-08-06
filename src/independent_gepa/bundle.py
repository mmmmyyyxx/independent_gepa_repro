"""Canonical frozen comparison-bundle export and validation."""

from __future__ import annotations

import hashlib
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .protocol import Example, ProtocolViolation, SplitName
from .versions import BUNDLE_VERSION

MEMBER_COUNT = 5
FORMAL_SPLIT_SIZES = {
    SplitName.OPTIMIZATION.value: 75,
    SplitName.DEVELOPMENT.value: 50,
    SplitName.TEST.value: 125,
}
REQUIRED_FILES = (
    "manifest.json",
    "model_contract.json",
    "parser_contract.json",
    "budget_reference.json",
    "hashes.json",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_json_bytes(value: Any) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prompt_hash(prompt: str) -> str:
    return sha256_bytes(prompt.encode("utf-8"))


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolViolation(f"cannot read valid JSON from {path}: {exc}") from exc


def write_canonical_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise ProtocolViolation(f"blank JSONL line at {path}:{line_number}")
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ProtocolViolation(f"JSONL row must be an object at {path}:{line_number}")
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolViolation(f"cannot read valid JSONL from {path}: {exc}") from exc
    return rows


def write_canonical_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(canonical_json(dict(row)) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8", newline="\n")


def _identity_payload(manifest: Mapping[str, Any], files: Mapping[str, str]) -> dict[str, Any]:
    stable_manifest = {key: value for key, value in manifest.items() if key != "overall_bundle_hash"}
    return {"manifest": stable_manifest, "files": dict(sorted(files.items()))}


def compute_overall_hash(manifest: Mapping[str, Any], files: Mapping[str, str]) -> str:
    return sha256_bytes(canonical_json_bytes(_identity_payload(manifest, files)))


@dataclass(frozen=True)
class ValidatedBundle:
    root: Path
    manifest: Mapping[str, Any]
    model_contract: Mapping[str, Any]
    parser_contract: Mapping[str, Any]
    budget_reference: Mapping[str, Any]
    prompts: tuple[str, ...]
    splits: Mapping[str, tuple[Example, ...]]
    overall_hash: str

    @property
    def experiment_seed(self) -> int:
        return int(self.manifest["experiment_seed"])

    @property
    def total_budget(self) -> int:
        return int(self.budget_reference["logical_task_example_evaluations"])


def validate_bundle(root: Path, *, require_formal: bool = True) -> ValidatedBundle:
    root = root.resolve()
    if not root.is_dir():
        raise ProtocolViolation(f"bundle directory does not exist: {root}")
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            raise ProtocolViolation(f"bundle is missing {relative}")
    manifest = read_json(root / "manifest.json")
    model_contract = read_json(root / "model_contract.json")
    parser_contract = read_json(root / "parser_contract.json")
    budget_reference = read_json(root / "budget_reference.json")
    hashes = read_json(root / "hashes.json")
    if not all(isinstance(item, dict) for item in (manifest, model_contract, parser_contract, budget_reference, hashes)):
        raise ProtocolViolation("bundle JSON contracts must be objects")
    if manifest.get("bundle_version") != BUNDLE_VERSION:
        raise ProtocolViolation(f"unsupported bundle_version: {manifest.get('bundle_version')!r}")
    if manifest.get("task") != "disambiguation_qa":
        raise ProtocolViolation("formal comparison task must be disambiguation_qa")
    if int(manifest.get("member_count", -1)) != MEMBER_COUNT:
        raise ProtocolViolation("bundle must define exactly five members")
    if not isinstance(manifest.get("experiment_seed"), int):
        raise ProtocolViolation("experiment_seed must be an integer")
    if require_formal and int(manifest["experiment_seed"]) not in {44, 45, 46}:
        raise ProtocolViolation("formal experiment seed must be one of 44, 45, or 46")

    declared_files = hashes.get("files")
    if not isinstance(declared_files, dict) or not declared_files:
        raise ProtocolViolation("hashes.json must contain a non-empty files mapping")
    expected_paths = {
        "model_contract.json",
        "parser_contract.json",
        "budget_reference.json",
        *(f"initialization/agent_{index}.txt" for index in range(MEMBER_COUNT)),
        *(f"splits/{name}.jsonl" for name in FORMAL_SPLIT_SIZES),
    }
    if set(declared_files) != expected_paths:
        missing = sorted(expected_paths - set(declared_files))
        extra = sorted(set(declared_files) - expected_paths)
        raise ProtocolViolation(f"bundle file-hash set mismatch; missing={missing}, extra={extra}")
    for relative, expected_hash in sorted(declared_files.items()):
        path = root / relative
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise ProtocolViolation(f"file hash mismatch: {relative}")
    declared_example_ids = hashes.get("example_ids")
    declared_example_id_hashes = hashes.get("example_id_hashes")
    if not isinstance(declared_example_ids, dict) or not isinstance(declared_example_id_hashes, dict):
        raise ProtocolViolation("hashes.json must contain example_ids and example_id_hashes")

    prompts: list[str] = []
    prompt_hashes: list[str] = []
    member_mapping = manifest.get("members")
    if not isinstance(member_mapping, list) or len(member_mapping) != MEMBER_COUNT:
        raise ProtocolViolation("manifest members must define five stable member mappings")
    for index, row in enumerate(member_mapping):
        expected_path = f"initialization/agent_{index}.txt"
        if not isinstance(row, dict) or row.get("member_id") != index or row.get("prompt_file") != expected_path:
            raise ProtocolViolation(f"unstable member mapping at member {index}")
        prompt = (root / expected_path).read_text(encoding="utf-8")
        digest = prompt_hash(prompt)
        if row.get("prompt_hash") != digest:
            raise ProtocolViolation(f"prompt hash mismatch for member {index}")
        prompts.append(prompt)
        prompt_hashes.append(digest)

    splits: dict[str, tuple[Example, ...]] = {}
    all_ids: set[str] = set()
    split_sizes = manifest.get("split_sizes")
    split_hashes = manifest.get("split_hashes")
    split_example_id_hashes = manifest.get("split_example_id_hashes")
    if (
        not isinstance(split_sizes, dict)
        or not isinstance(split_hashes, dict)
        or not isinstance(split_example_id_hashes, dict)
    ):
        raise ProtocolViolation(
            "manifest split_sizes, split_hashes, and split_example_id_hashes must be objects"
        )
    for name, formal_size in FORMAL_SPLIT_SIZES.items():
        relative = f"splits/{name}.jsonl"
        raw_rows = read_jsonl(root / relative)
        expected_size = formal_size if require_formal else int(split_sizes.get(name, -1))
        if len(raw_rows) != expected_size or int(split_sizes.get(name, -1)) != expected_size:
            raise ProtocolViolation(f"unexpected {name} split size: {len(raw_rows)}")
        examples = tuple(Example.from_mapping(row) for row in raw_rows)
        ids = [example.example_id for example in examples]
        if len(ids) != len(set(ids)):
            raise ProtocolViolation(f"duplicate example_id within {name}")
        overlap = all_ids.intersection(ids)
        if overlap:
            raise ProtocolViolation(f"split overlap detected for IDs: {sorted(overlap)[:5]}")
        all_ids.update(ids)
        if split_hashes.get(name) != declared_files[relative]:
            raise ProtocolViolation(f"manifest split hash mismatch for {name}")
        ids_hash = sha256_bytes(canonical_json_bytes(ids))
        if declared_example_ids.get(name) != ids:
            raise ProtocolViolation(f"declared example IDs mismatch for {name}")
        if declared_example_id_hashes.get(name) != ids_hash:
            raise ProtocolViolation(f"example ID hash mismatch for {name}")
        if split_example_id_hashes.get(name) != ids_hash:
            raise ProtocolViolation(f"manifest example ID hash mismatch for {name}")
        splits[name] = examples

    if model_contract.get("task_model") != manifest.get("task_model"):
        raise ProtocolViolation("task model identity mismatch")
    if model_contract.get("reflection_model") != manifest.get("reflection_model"):
        raise ProtocolViolation("reflection model identity mismatch")
    if model_contract.get("enable_thinking") is not False or manifest.get("enable_thinking") is not False:
        raise ProtocolViolation("enable_thinking must be false")
    numeric_model_fields = ("temperature", "max_tokens", "timeout_seconds", "max_retries")
    if any(field not in model_contract for field in numeric_model_fields):
        raise ProtocolViolation("model contract lacks explicit sampling, token, timeout, or retry settings")
    if (
        int(model_contract["max_tokens"]) <= 0
        or float(model_contract["timeout_seconds"]) <= 0
        or int(model_contract["max_retries"]) < 0
    ):
        raise ProtocolViolation("model contract contains invalid provider settings")
    if require_formal:
        expected_model = "qwen3.7-flash-2026-07-15"
        if model_contract.get("task_model") != expected_model or model_contract.get("reflection_model") != expected_model:
            raise ProtocolViolation("formal model snapshot mismatch")
    if manifest.get("voting_rule") != "plurality" or manifest.get("tie_rule") != "abstain":
        raise ProtocolViolation("bundle must use plurality with tie-as-abstain")
    if parser_contract.get("version") != manifest.get("parser_version"):
        raise ProtocolViolation("parser contract version mismatch")
    logical_budget = budget_reference.get("logical_task_example_evaluations")
    if not isinstance(logical_budget, int) or logical_budget < MEMBER_COUNT:
        raise ProtocolViolation("logical task-example budget must be a positive integer")
    if budget_reference.get("allocation_rule") != "equal_floor_per_member":
        raise ProtocolViolation("unsupported budget allocation rule")

    overall = compute_overall_hash(manifest, declared_files)
    if hashes.get("overall_bundle_hash") != overall or manifest.get("overall_bundle_hash") != overall:
        raise ProtocolViolation("overall bundle hash mismatch")
    return ValidatedBundle(
        root=root,
        manifest=manifest,
        model_contract=model_contract,
        parser_contract=parser_contract,
        budget_reference=budget_reference,
        prompts=tuple(prompts),
        splits=splits,
        overall_hash=overall,
    )


def export_bundle_from_spec(source_root: Path, spec_path: Path, output: Path) -> str:
    """Export a bundle from an explicit data-only source specification.

    The exporter reads files only; it never imports the source repository.
    """

    source_root = source_root.resolve()
    spec_path = spec_path.resolve()
    output = output.resolve()
    if not source_root.is_dir() or not spec_path.is_file():
        raise ProtocolViolation("source root or export spec is missing")
    if output == source_root or source_root in output.parents:
        raise ProtocolViolation("bundle output must not be inside the read-only source root")
    if output.exists() and any(output.iterdir()):
        raise ProtocolViolation("output bundle directory must be absent or empty")
    spec = read_json(spec_path)
    if not isinstance(spec, dict):
        raise ProtocolViolation("export spec must be a JSON object")

    def source_path(relative: str) -> Path:
        resolved = (source_root / relative).resolve()
        if source_root not in resolved.parents:
            raise ProtocolViolation(f"source path escapes source root: {relative}")
        if not resolved.is_file():
            raise ProtocolViolation(f"source file is missing: {relative}")
        return resolved

    output.mkdir(parents=True, exist_ok=True)
    prompts_spec = spec.get("initial_prompts")
    split_spec = spec.get("splits")
    if not isinstance(prompts_spec, list) or len(prompts_spec) != MEMBER_COUNT or not isinstance(split_spec, dict):
        raise ProtocolViolation("export spec requires five initial_prompts and three splits")
    for index, relative in enumerate(prompts_spec):
        prompt = source_path(str(relative)).read_text(encoding="utf-8")
        target = output / "initialization" / f"agent_{index}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(prompt, encoding="utf-8", newline="\n")
    def source_rows(split_entry: Any) -> list[dict[str, Any]]:
        if isinstance(split_entry, str):
            return read_jsonl(source_path(split_entry))
        if not isinstance(split_entry, dict):
            raise ProtocolViolation("split export entry must be a path or mapping")
        path = source_path(str(split_entry["path"]))
        if split_entry.get("format") != "csv":
            raise ProtocolViolation("mapped split entries currently require format=csv")
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                source_records = list(csv.DictReader(handle))
        except OSError as exc:
            raise ProtocolViolation(f"cannot read source CSV: {exc}") from exc
        id_field = str(split_entry["id_field"])
        question_field = str(split_entry["question_field"])
        gold_field = str(split_entry["gold_field"])
        layout = split_entry.get("question_options_format")
        rows: list[dict[str, Any]] = []
        for source_record in source_records:
            question = str(source_record[question_field])
            if layout == "bbh_embedded_options":
                marker = "\nOptions:\n"
                if marker not in question:
                    raise ProtocolViolation("BBH question lacks the explicit Options block")
                stem, option_block = question.rsplit(marker, 1)
                parsed_choices: list[tuple[str, str]] = []
                for line in option_block.splitlines():
                    match = re.fullmatch(r"\(([A-Z])\)\s+(.+)", line.strip())
                    if match is None:
                        raise ProtocolViolation("invalid BBH option line")
                    parsed_choices.append((match.group(1), match.group(2)))
                expected_labels = [chr(ord("A") + index) for index in range(len(parsed_choices))]
                if [label for label, _ in parsed_choices] != expected_labels:
                    raise ProtocolViolation("BBH options must be contiguous and stably ordered")
                choices = [choice for _, choice in parsed_choices]
                question = stem
            else:
                choices_field = split_entry.get("choices_field")
                if not isinstance(choices_field, str):
                    raise ProtocolViolation("CSV split requires choices_field or bbh_embedded_options")
                try:
                    decoded_choices = json.loads(str(source_record[choices_field]))
                except json.JSONDecodeError as exc:
                    raise ProtocolViolation("CSV choices_field must contain a JSON list") from exc
                if not isinstance(decoded_choices, list):
                    raise ProtocolViolation("CSV choices_field must contain a JSON list")
                choices = [str(item) for item in decoded_choices]
            raw_gold = str(source_record[gold_field]).strip()
            gold_match = re.fullmatch(r"\(?([A-Za-z])\)?", raw_gold)
            if gold_match is None:
                raise ProtocolViolation(f"cannot normalize option-letter gold answer: {raw_gold!r}")
            rows.append(
                {
                    "example_id": str(source_record[id_field]),
                    "question": question,
                    "choices": choices,
                    "gold_answer": gold_match.group(1).upper(),
                }
            )
        return rows

    for name in FORMAL_SPLIT_SIZES:
        rows = source_rows(split_spec[name])
        write_canonical_jsonl(output / "splits" / f"{name}.jsonl", rows)
    for contract_name in ("model_contract", "parser_contract", "budget_reference"):
        value = read_json(source_path(str(spec[contract_name])))
        write_canonical_json(output / f"{contract_name}.json", value)

    file_hashes: dict[str, str] = {}
    for relative in sorted(
        {
            "model_contract.json",
            "parser_contract.json",
            "budget_reference.json",
            *(f"initialization/agent_{index}.txt" for index in range(MEMBER_COUNT)),
            *(f"splits/{name}.jsonl" for name in FORMAL_SPLIT_SIZES),
        }
    ):
        file_hashes[relative] = sha256_file(output / relative)
    members = [
        {
            "member_id": index,
            "prompt_file": f"initialization/agent_{index}.txt",
            "prompt_hash": prompt_hash((output / "initialization" / f"agent_{index}.txt").read_text(encoding="utf-8")),
        }
        for index in range(MEMBER_COUNT)
    ]
    model_contract = read_json(output / "model_contract.json")
    example_ids = {
        name: [str(row["example_id"]) for row in read_jsonl(output / "splits" / f"{name}.jsonl")]
        for name in FORMAL_SPLIT_SIZES
    }
    example_id_hashes = {
        name: sha256_bytes(canonical_json_bytes(ids)) for name, ids in example_ids.items()
    }
    manifest = {
        "bundle_version": BUNDLE_VERSION,
        "task": spec["task"],
        "experiment_seed": int(spec["experiment_seed"]),
        "member_count": MEMBER_COUNT,
        "members": members,
        "split_sizes": {
            name: len(read_jsonl(output / "splits" / f"{name}.jsonl")) for name in FORMAL_SPLIT_SIZES
        },
        "split_hashes": {name: file_hashes[f"splits/{name}.jsonl"] for name in FORMAL_SPLIT_SIZES},
        "split_example_id_hashes": example_id_hashes,
        "task_model": model_contract["task_model"],
        "reflection_model": model_contract["reflection_model"],
        "enable_thinking": model_contract["enable_thinking"],
        "parser_version": read_json(output / "parser_contract.json")["version"],
        "voting_rule": "plurality",
        "tie_rule": "abstain",
        "source_identity": spec["source_identity"],
        "reference_results": spec["reference_results"],
        "budget_identity": spec["budget_identity"],
    }
    overall = compute_overall_hash(manifest, file_hashes)
    manifest["overall_bundle_hash"] = overall
    write_canonical_json(output / "manifest.json", manifest)
    write_canonical_json(
        output / "hashes.json",
        {
            "files": file_hashes,
            "example_ids": example_ids,
            "example_id_hashes": example_id_hashes,
            "overall_bundle_hash": overall,
        },
    )
    validate_bundle(output, require_formal=True)
    return overall
