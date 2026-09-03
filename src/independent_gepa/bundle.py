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
from .versions import (
    BUNDLE_VERSION,
    EVALUATOR_MODEL,
    OPTIMIZER_MODEL,
    PARSER_CONTRACT_VERSION,
    REFLECTION_MODEL,
    SOLVER_MODEL,
    TASK_REQUEST_TEMPLATE_VERSION,
)

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
    "reference_results.json",
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
    reference_results: Mapping[str, Any]
    prompts: tuple[str, ...]
    splits: Mapping[str, tuple[Example, ...]]
    overall_hash: str

    @property
    def experiment_seed(self) -> int:
        return int(self.manifest["experiment_seed"])

    @property
    def logical_evaluation_cap(self) -> int:
        row = self.budget_reference.get("formal")
        if not isinstance(row, Mapping) or row.get("status") != "frozen":
            raise ProtocolViolation("formal token/calibration budget is not frozen")
        value = row.get("gepa_logical_eval_cap_total")
        if not isinstance(value, int) or value < MEMBER_COUNT:
            raise ProtocolViolation("formal GEPA logical-evaluation cap is invalid")
        return value

    def token_budget(self) -> Mapping[str, int | float | str]:
        row = self.budget_reference.get("formal")
        if not isinstance(row, Mapping) or row.get("status") != "frozen":
            raise ProtocolViolation("formal token/calibration budget is not frozen")
        return row


def _validate_model_contract(
    model_contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    require_formal: bool,
) -> None:
    schema_version = model_contract.get("schema_version")
    if schema_version not in {"model_contract_v2", "model_contract_v3"}:
        raise ProtocolViolation("unsupported model contract schema")
    task = model_contract.get("shared_task_model")
    reference = model_contract.get("reference_optimizer")
    reflection = model_contract.get("independent_gepa_reflection_model")
    evaluator = model_contract.get("independent_gepa_evaluator_model")
    optimizer = model_contract.get("independent_gepa_optimizer_model")
    required_roles = (task, reference, reflection)
    if schema_version == "model_contract_v3":
        required_roles += (evaluator, optimizer)
    if not all(isinstance(item, Mapping) for item in required_roles):
        raise ProtocolViolation("model contract must separate task, reference, and GEPA roles")
    if task.get("model") != manifest.get("task_model"):
        raise ProtocolViolation("task model identity mismatch")
    if reflection.get("model") != manifest.get("reflection_model"):
        raise ProtocolViolation("reflection model identity mismatch")
    if schema_version == "model_contract_v3":
        if evaluator.get("model") != manifest.get("evaluator_model"):
            raise ProtocolViolation("evaluator model identity mismatch")
        if optimizer.get("model") != manifest.get("optimizer_model"):
            raise ProtocolViolation("optimizer model identity mismatch")
        if len({evaluator.get("model"), optimizer.get("model"), reflection.get("model")}) != 1:
            raise ProtocolViolation("evaluator, optimizer, and reflection model identities diverge")
        if any(row.get("enable_thinking") is not False for row in (evaluator, optimizer)):
            raise ProtocolViolation("evaluator and optimizer thinking must be disabled")
    if task.get("enable_thinking") is not False or reflection.get("enable_thinking") is not False:
        raise ProtocolViolation("task and reflection thinking must be disabled")
    for name, row in (("shared task", task), ("GEPA reflection", reflection)):
        required = ("temperature", "max_tokens", "timeout_seconds", "max_retries")
        if any(field not in row for field in required):
            raise ProtocolViolation(f"{name} model contract is incomplete")
        if (
            int(row["max_tokens"]) <= 0
            or float(row["timeout_seconds"]) <= 0
            or int(row["max_retries"]) < 0
        ):
            raise ProtocolViolation(f"{name} model contract contains invalid settings")
    if task.get("parser_version") != manifest.get("parser_version"):
        raise ProtocolViolation("task model parser identity mismatch")
    if task.get("request_template_version") != TASK_REQUEST_TEMPLATE_VERSION:
        raise ProtocolViolation("task request-template identity mismatch")
    if task.get("question_rendering_version") != "bbh_options_marker_v1":
        raise ProtocolViolation("task question-rendering identity mismatch")
    roles = reference.get("roles")
    if reference.get("model") != "qwen3-14b" or not isinstance(roles, Mapping):
        raise ProtocolViolation("reference optimizer metadata is incomplete")
    if set(roles) != {"teacher", "critic", "student"}:
        raise ProtocolViolation("reference optimizer roles must be teacher, critic, and student")
    for role, row in roles.items():
        if not isinstance(row, Mapping) or not isinstance(row.get("temperature"), (int, float)):
            raise ProtocolViolation(f"reference optimizer role is incomplete: {role}")
    if require_formal:
        if schema_version == "model_contract_v2":
            if task.get("model") != "qwen3-14b" or reflection.get("model") != "qwen3-14b":
                raise ProtocolViolation("legacy formal model snapshot mismatch")
        elif (
            task.get("model") != SOLVER_MODEL
            or evaluator.get("model") != EVALUATOR_MODEL
            or optimizer.get("model") != OPTIMIZER_MODEL
            or reflection.get("model") != REFLECTION_MODEL
        ):
            raise ProtocolViolation("formal split-role model snapshot mismatch")


def _validate_initial_metrics(manifest: Mapping[str, Any]) -> None:
    metrics = manifest.get("initial_metrics")
    if not isinstance(metrics, Mapping) or set(metrics) != set(FORMAL_SPLIT_SIZES):
        raise ProtocolViolation("manifest must define initial_metrics for all three splits")
    for split, size in FORMAL_SPLIT_SIZES.items():
        row = metrics.get(split)
        if not isinstance(row, Mapping) or row.get("status") not in {"available", "not_evaluated"}:
            raise ProtocolViolation(f"invalid initial metric status for {split}")
        if row["status"] == "not_evaluated":
            if set(row) != {"status"}:
                raise ProtocolViolation(f"not_evaluated metrics must not contain invented values: {split}")
            continue
        member_correct = row.get("member_correct")
        team_correct = row.get("team_correct")
        if (
            not isinstance(member_correct, list)
            or len(member_correct) != MEMBER_COUNT
            or any(not isinstance(value, int) or value < 0 or value > size for value in member_correct)
            or not isinstance(team_correct, int)
            or team_correct < 0
            or team_correct > size
        ):
            raise ProtocolViolation(f"invalid available initial metrics for {split}")


def _validate_budget_reference(
    budget_reference: Mapping[str, Any],
    *,
    stage: str | None,
) -> None:
    if budget_reference.get("schema_version") != "budget_reference_v3":
        raise ProtocolViolation("unsupported budget reference schema")
    if budget_reference.get("primary_unit") != "total_model_tokens":
        raise ProtocolViolation("primary matched budget must be total model tokens")
    if budget_reference.get("allocation_rule") != "equal_floor_per_member":
        raise ProtocolViolation("unsupported budget allocation rule")
    formal = budget_reference.get("formal")
    if not isinstance(formal, Mapping) or formal.get("status") not in {"frozen", "calibration_pending"}:
        raise ProtocolViolation("formal budget status is invalid")
    if formal["status"] == "frozen":
        required_ints = (
            "reference_training_tokens",
            "reference_provider_calls",
            "gepa_logical_eval_cap_total",
            "expected_token_budget",
            "hard_token_limit",
            "stop_reserve_tokens_per_member",
        )
        if any(not isinstance(formal.get(key), int) or int(formal[key]) <= 0 for key in required_ints):
            raise ProtocolViolation("frozen formal budget is incomplete")
        if formal.get("reference_arm") != "V17_S4":
            raise ProtocolViolation("formal reference arm must be V17_S4")
        tolerance = formal.get("hard_overshoot_tolerance")
        if not isinstance(tolerance, (int, float)) or not 0 <= float(tolerance) <= 0.05:
            raise ProtocolViolation("hard token overshoot tolerance must be at most five percent")
        if int(formal["expected_token_budget"]) != int(formal["reference_training_tokens"]):
            raise ProtocolViolation("expected token budget must equal V17 S4 realized training tokens")
        if int(formal["hard_token_limit"]) > int(formal["reference_training_tokens"] * 1.05):
            raise ProtocolViolation("hard token limit exceeds five-percent tolerance")
    if stage == "formal" and formal.get("status") != "frozen":
        raise ProtocolViolation("formal token/calibration budget is not frozen")


def validate_bundle(
    root: Path,
    *,
    require_formal: bool = True,
    stage: str | None = None,
) -> ValidatedBundle:
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
    reference_results = read_json(root / "reference_results.json")
    hashes = read_json(root / "hashes.json")
    if not all(
        isinstance(item, dict)
        for item in (
            manifest,
            model_contract,
            parser_contract,
            budget_reference,
            reference_results,
            hashes,
        )
    ):
        raise ProtocolViolation("bundle JSON contracts must be objects")
    if manifest.get("bundle_version") != BUNDLE_VERSION:
        raise ProtocolViolation(f"unsupported bundle_version: {manifest.get('bundle_version')!r}")
    if manifest.get("task") != "disambiguation_qa":
        raise ProtocolViolation("formal comparison task must be disambiguation_qa")
    if manifest.get("enable_thinking") is not False:
        raise ProtocolViolation("bundle enable_thinking must be false")
    if int(manifest.get("member_count", -1)) != MEMBER_COUNT:
        raise ProtocolViolation("bundle must define exactly five members")
    if not isinstance(manifest.get("experiment_seed"), int):
        raise ProtocolViolation("experiment_seed must be an integer")
    if require_formal and int(manifest["experiment_seed"]) not in {56, 57, 58}:
        raise ProtocolViolation("formal experiment seed must be one of 56, 57, or 58")

    declared_files = hashes.get("files")
    if not isinstance(declared_files, dict) or not declared_files:
        raise ProtocolViolation("hashes.json must contain a non-empty files mapping")
    expected_paths = {
        "model_contract.json",
        "parser_contract.json",
        "budget_reference.json",
        "reference_results.json",
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
    if len(set(prompt_hashes)) != 1 or manifest.get("initialization_mode") != "shared_identical":
        raise ProtocolViolation("V17 baseline requires five byte-identical initial prompts")

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
        for row in raw_rows:
            if "option_labels" not in row:
                raise ProtocolViolation(
                    f"{name} example {row.get('example_id', '<unknown>')} "
                    "must freeze option_labels"
                )
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

    _validate_model_contract(model_contract, manifest, require_formal=require_formal)
    if manifest.get("voting_rule") != "plurality" or manifest.get("tie_rule") != "abstain":
        raise ProtocolViolation("bundle must use plurality with tie-as-abstain")
    if parser_contract.get("schema_version") != PARSER_CONTRACT_VERSION:
        raise ProtocolViolation("parser contract schema mismatch")
    if parser_contract.get("source_parser_version") != manifest.get("parser_version"):
        raise ProtocolViolation("parser contract version mismatch")
    provenance = manifest.get("split_source_provenance")
    if not isinstance(provenance, Mapping) or set(provenance) != set(FORMAL_SPLIT_SIZES):
        raise ProtocolViolation("manifest lacks split source provenance")
    for name, row in provenance.items():
        if (
            not isinstance(row, Mapping)
            or not isinstance(row.get("source_path"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("source_sha256", "")))
        ):
            raise ProtocolViolation(f"invalid split source provenance for {name}")
    _validate_initial_metrics(manifest)
    _validate_budget_reference(budget_reference, stage=stage)
    if reference_results.get("schema_version") != "v17_reference_results_v1":
        raise ProtocolViolation("unsupported V17 reference-results schema")
    if reference_results.get("experiment_seed") != manifest.get("experiment_seed"):
        raise ProtocolViolation("reference-results seed mismatch")
    arms = reference_results.get("arms")
    if not isinstance(arms, Mapping) or set(arms) != {"S0", "S1", "S4"}:
        raise ProtocolViolation("reference results must freeze S0, S1, and S4")
    for arm, row in arms.items():
        if not isinstance(row, Mapping):
            raise ProtocolViolation(f"invalid reference result for {arm}")
        for split in ("validation", "test"):
            metrics = row.get(split)
            if (
                not isinstance(metrics, Mapping)
                or not isinstance(metrics.get("vote_accuracy"), (int, float))
                or not isinstance(metrics.get("oracle_accuracy"), (int, float))
            ):
                raise ProtocolViolation(f"reference result lacks {split} metrics for {arm}")

    overall = compute_overall_hash(manifest, declared_files)
    if hashes.get("overall_bundle_hash") != overall or manifest.get("overall_bundle_hash") != overall:
        raise ProtocolViolation("overall bundle hash mismatch")
    return ValidatedBundle(
        root=root,
        manifest=manifest,
        model_contract=model_contract,
        parser_contract=parser_contract,
        budget_reference=budget_reference,
        reference_results=reference_results,
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
    prompt_sources: list[dict[str, Any]] = []
    for index, entry in enumerate(prompts_spec):
        if isinstance(entry, str):
            path = source_path(entry)
            prompt = path.read_text(encoding="utf-8")
            source = {"source_path": entry, "source_sha256": sha256_file(path), "format": "text"}
        elif isinstance(entry, dict) and entry.get("format") == "json_array":
            relative = str(entry["path"])
            path = source_path(relative)
            values = read_json(path)
            prompt_index = int(entry["index"])
            if not isinstance(values, list) or not 0 <= prompt_index < len(values):
                raise ProtocolViolation("prompt JSON array source is invalid")
            prompt = str(values[prompt_index])
            source = {
                "source_path": relative,
                "source_sha256": sha256_file(path),
                "format": "json_array",
                "index": prompt_index,
            }
        else:
            raise ProtocolViolation("initial prompt source must be text or a JSON-array entry")
        target = output / "initialization" / f"agent_{index}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(prompt, encoding="utf-8", newline="\n")
        prompt_sources.append(source)

    def source_rows(split_entry: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if isinstance(split_entry, str):
            path = source_path(split_entry)
            rows = read_jsonl(path)
            for row in rows:
                choices = row.get("choices")
                if isinstance(choices, list):
                    row["option_labels"] = [
                        chr(ord("A") + index) for index in range(len(choices))
                    ]
            return rows, {
                "source_path": split_entry,
                "source_sha256": sha256_file(path),
                "format": "jsonl",
                "field_newline_normalization": "none",
            }
        if not isinstance(split_entry, dict):
            raise ProtocolViolation("split export entry must be a path or mapping")
        relative = str(split_entry["path"])
        path = source_path(relative)
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
            normalized_question = question.replace("\r\n", "\n").replace("\r", "\n")
            if layout == "bbh_embedded_options":
                marker = "\nOptions:\n"
                if marker not in normalized_question:
                    raise ProtocolViolation("BBH question lacks the explicit Options block")
                stem, option_block = normalized_question.rsplit(marker, 1)
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
                option_labels = [label for label, _ in parsed_choices]
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
                option_labels = [chr(ord("A") + index) for index in range(len(choices))]
                question = normalized_question
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
                    "option_labels": option_labels,
                }
            )
        return rows, {
            "source_path": relative,
            "source_sha256": sha256_file(path),
            "format": "csv",
            "field_newline_normalization": "crlf_cr_to_lf",
        }

    split_source_provenance: dict[str, dict[str, Any]] = {}
    for name in FORMAL_SPLIT_SIZES:
        rows, split_source_provenance[name] = source_rows(split_spec[name])
        write_canonical_jsonl(output / "splits" / f"{name}.jsonl", rows)

    def contract_value(entry: Any) -> Any:
        if isinstance(entry, str):
            return read_json(source_path(entry))
        if isinstance(entry, dict) and isinstance(entry.get("inline"), dict):
            return entry["inline"]
        raise ProtocolViolation("contract source must be a source path or inline object")

    for contract_name in (
        "model_contract",
        "parser_contract",
        "budget_reference",
        "reference_results",
    ):
        value = contract_value(spec[contract_name])
        write_canonical_json(output / f"{contract_name}.json", value)

    file_hashes: dict[str, str] = {}
    for relative in sorted(
        {
            "model_contract.json",
            "parser_contract.json",
            "budget_reference.json",
            "reference_results.json",
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
            "source": prompt_sources[index],
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
        "task_model": model_contract["shared_task_model"]["model"],
        "reflection_model": model_contract["independent_gepa_reflection_model"]["model"],
        "enable_thinking": False,
        "parser_version": read_json(output / "parser_contract.json")["source_parser_version"],
        "voting_rule": "plurality",
        "tie_rule": "abstain",
        "initialization_mode": "shared_identical",
        "source_identity": spec["source_identity"],
        "initial_metrics": spec["initial_metrics"],
        "split_source_provenance": split_source_provenance,
        "budget_identity": spec["budget_identity"],
    }
    if model_contract.get("schema_version") == "model_contract_v3":
        manifest["evaluator_model"] = model_contract["independent_gepa_evaluator_model"][
            "model"
        ]
        manifest["optimizer_model"] = model_contract["independent_gepa_optimizer_model"][
            "model"
        ]
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
    validate_bundle(output, require_formal=True, stage=None)
    return overall
