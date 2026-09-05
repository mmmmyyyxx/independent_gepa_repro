"""Isolated single-prompt GEPA capacity-probe protocol.

This module intentionally does not reuse the matched five-member runner.  Its
bundle has three train/optimizer-validation folds plus an external validation
set, and deliberately has no test-example loader.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._vendor import import_vendor_gepa
from .adapter import IndependentGEPAAdapter
from .audit import require_clean_public_artifacts
from .budget import BudgetLedger
from .bundle import (canonical_json_bytes, prompt_hash, read_json, read_jsonl,
                     sha256_file, write_canonical_json, write_canonical_jsonl)
from .evaluator import MemberEvaluator
from .model_profile import split_role_model_contract
from .parser import StrictAnswerParser
from .protocol import Example, ProtocolViolation
from .provider import ExactRequestCache, OpenAICompatibleProvider, ProviderAccounting
from .versions import GEPA_COMMIT, REFLECTION_MODEL, SOLVER_MODEL

CAPACITY_SCHEMA = "gepa_single_prompt_capacity_probe_v1"
SEEDS = (75, 76, 77)
P0_HASH = "549bc93c03f703faf5aa1bd56b557135fb6e65d0cf6c055b8fad6a15e7c87a63"


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _question_hash(question: str) -> str:
    return hashlib.sha256(question.replace("\r\n", "\n").replace("\r", "\n").encode()).hexdigest()


def _rows_from_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        source = list(csv.DictReader(handle))
    rows: list[dict[str, Any]] = []
    for row in source:
        source_question = str(row["question"])
        raw = source_question.replace("\r\n", "\n").replace("\r", "\n")
        marker = "\nOptions:\n"
        if marker not in raw:
            raise ProtocolViolation("capacity source BBH row lacks Options block")
        question, options = raw.rsplit(marker, 1)
        choices: list[str] = []
        for index, line in enumerate(options.splitlines()):
            expected = f"({chr(ord('A') + index)}) "
            if not line.startswith(expected):
                raise ProtocolViolation("capacity source options are not canonical")
            choices.append(line[len(expected):])
        answer = re.fullmatch(r"\(?([A-Za-z])\)?", str(row["answer"]).strip())
        if answer is None: raise ProtocolViolation("capacity source gold is not an option letter")
        rows.append({"example_id": str(row["sample_id"]), "question": question,
                     "choices": choices, "gold_answer": answer.group(1).upper(),
                     "option_labels": [chr(ord("A") + i) for i in range(len(choices))],
                     "_source_question_hash": hashlib.sha256(source_question.encode("utf-8")).hexdigest()})
    return rows


def export_capacity_bundle(*, source_root: Path, prompt_carrier: Path,
                           d0_manifest: Path, output: Path) -> str:
    """Freeze the anti-overfitting artifact without importing its Python code.

    `output` intentionally receives no Test50 rows: test identity is proved in
    its manifest, but no capacity runtime object can read test content.
    """
    source_root, output = source_root.resolve(), output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ProtocolViolation("capacity bundle output must be empty")
    frozen = source_root / "experiments" / "anti_overfitting_split_v1"
    split_manifest = read_json(frozen / "split_manifest.json")
    assignment = read_json(frozen / "fold_assignment.json")
    hashes = read_json(frozen / "dataset_hashes.json")
    d0 = read_json(d0_manifest)
    p0 = prompt_carrier.read_text(encoding="utf-8")
    p0_hash = prompt_hash(p0)
    snapshot = d0.get("initialization_snapshot", {})
    d0_hashes = snapshot.get("initial_prompt_hashes") if isinstance(snapshot, Mapping) else None
    if p0_hash != P0_HASH or not isinstance(d0_hashes, list) or set(d0_hashes) != {P0_HASH}:
        raise ProtocolViolation("cannot prove prompt carrier is D0 P0")
    csv_root = source_root / "strict_splits_bbh_seed42" / "disambiguation_qa"
    source_files = {name: csv_root / f"{name}.csv" for name in ("opt", "val", "test")}
    expected = {"opt": hashes["source_files"]["opt.csv"],
                "val": hashes["source_files"]["val.csv"],
                "test": hashes["source_files"]["test.csv"]}
    if any(sha256_file(source_files[key]) != expected[key] for key in source_files):
        raise ProtocolViolation("capacity source CSV hash mismatch")
    all_rows = [row for key in ("opt", "val", "test") for row in _rows_from_csv(source_files[key])]
    by_qhash = {str(row.pop("_source_question_hash")): row for row in all_rows}
    if len(by_qhash) != 250:
        raise ProtocolViolation("capacity source inventory is not 250 unique questions")
    groups = split_manifest["question_hashes"]
    fold_hashes = assignment["folds"]
    required = {"fold_a": fold_hashes["fold_a"], "fold_b": fold_hashes["fold_b"],
                "fold_c": fold_hashes["fold_c"], "external_validation": groups["validation"]}
    all_declared = set(groups["train_dev"]) | set(groups["validation"]) | set(groups["test"])
    if all_declared != set(by_qhash) or sum(map(len, groups.values())) != 250:
        raise ProtocolViolation("frozen split identities do not partition source inventory")
    output.mkdir(parents=True, exist_ok=True)
    write_canonical_json(output / "model_contract.json", split_role_model_contract())
    # Parser contract is byte-identical to the current qwen3-8b frozen bundle.
    carrier_contract = prompt_carrier.parents[1] / "parser_contract.json"
    if not carrier_contract.is_file():
        raise ProtocolViolation("P0 carrier parser contract is missing")
    write_canonical_json(output / "parser_contract.json", read_json(carrier_contract))
    (output / "initialization").mkdir(exist_ok=True)
    (output / "initialization" / "p0.txt").write_text(p0, encoding="utf-8", newline="\n")
    file_hashes: dict[str, str] = {"initialization/p0.txt": sha256_file(output / "initialization" / "p0.txt")}
    ids: dict[str, list[str]] = {}
    for name, qhashes in required.items():
        rows = [by_qhash[item] for item in qhashes]
        if len(rows) != 50:
            raise ProtocolViolation(f"frozen {name} is not 50 rows")
        write_canonical_jsonl(output / "splits" / f"{name}.jsonl", rows)
        relative = f"splits/{name}.jsonl"
        file_hashes[relative] = sha256_file(output / relative)
        ids[name] = [row["example_id"] for row in rows]
    # Test is an identity-only denial record, never copied as rows.
    test_ids = [by_qhash[item]["example_id"] for item in groups["test"]]
    manifest = {
        "schema_version": CAPACITY_SCHEMA, "task": "disambiguation_qa", "member_count": 1,
        "seeds": list(SEEDS), "p0_hash": p0_hash, "gepa_commit": GEPA_COMMIT,
        "models": {"task": SOLVER_MODEL, "reflection": REFLECTION_MODEL, "enable_thinking": False},
        "split_sizes": {key: 50 for key in required} | {"test_identity_only": 50},
        "split_file_hashes": {key: file_hashes[f"splits/{key}.jsonl"] for key in required},
        "example_ids": ids, "example_id_hashes": {key: _hash(value) for key, value in ids.items()},
        "test_identity": {"count": 50, "example_ids_hash": _hash(test_ids),
                          "question_hashes_hash": _hash(groups["test"]), "source_sha256": expected["test"]},
        "fold_assignment": {str(item["seed"]): {"optimize": item["optimize"], "optimizer_val": item["shadow"]}
                            for item in assignment["trajectory_groups"]},
        "source_provenance": {"split_manifest_sha256": sha256_file(frozen / "split_manifest.json"),
            "fold_assignment_sha256": sha256_file(frozen / "fold_assignment.json"),
            "dataset_hashes_sha256": sha256_file(frozen / "dataset_hashes.json"),
            "source_csv_sha256": expected, "d0_manifest_sha256": sha256_file(d0_manifest),
            "prompt_carrier_sha256": sha256_file(prompt_carrier),
            "prompt_identity": "D0_P0_hash_verified"},
        "test_access": "denied_no_test_rows_in_bundle",
    }
    manifest["bundle_hash"] = _hash({"manifest": manifest, "files": file_hashes})
    write_canonical_json(output / "manifest.json", manifest)
    validate_capacity_bundle(output)
    return str(manifest["bundle_hash"])


@dataclass(frozen=True)
class CapacityBundle:
    root: Path; manifest: Mapping[str, Any]; p0: str
    folds: Mapping[str, tuple[Example, ...]]; external_validation: tuple[Example, ...]
    @property
    def test_examples(self) -> tuple[Example, ...]:
        raise ProtocolViolation("Test50 is intentionally unavailable to capacity probe")
    def split_for_seed(self, seed: int) -> tuple[tuple[Example, ...], tuple[Example, ...]]:
        if seed not in SEEDS: raise ProtocolViolation("unregistered capacity seed")
        mapping = self.manifest["fold_assignment"][str(seed)]
        left, right = str(mapping["optimize"]).split("+")
        return self.folds[left] + self.folds[right], self.folds[str(mapping["optimizer_val"])]


def validate_capacity_bundle(root: Path) -> CapacityBundle:
    root = root.resolve(); manifest = read_json(root / "manifest.json")
    if manifest.get("schema_version") != CAPACITY_SCHEMA or manifest.get("gepa_commit") != GEPA_COMMIT:
        raise ProtocolViolation("capacity bundle schema/GEPA identity mismatch")
    p0 = (root / "initialization" / "p0.txt").read_text(encoding="utf-8")
    if prompt_hash(p0) != P0_HASH or manifest.get("p0_hash") != P0_HASH: raise ProtocolViolation("P0 mismatch")
    if manifest.get("models") != {"task": SOLVER_MODEL, "reflection": REFLECTION_MODEL, "enable_thinking": False}:
        raise ProtocolViolation("capacity model contract mismatch")
    folds: dict[str, tuple[Example, ...]] = {}; seen: set[str] = set()
    for name in ("fold_a", "fold_b", "fold_c", "external_validation"):
        path = root / "splits" / f"{name}.jsonl"; rows = read_jsonl(path); examples = tuple(Example.from_mapping(row) for row in rows)
        if len(examples) != 50 or sha256_file(path) != manifest["split_file_hashes"][name]: raise ProtocolViolation("capacity split hash/size mismatch")
        actual = [row.example_id for row in examples]
        if actual != manifest["example_ids"][name] or _hash(actual) != manifest["example_id_hashes"][name] or seen.intersection(actual):
            raise ProtocolViolation("capacity split identity/disjointness mismatch")
        seen.update(actual); folds[name] = examples
    if len(seen) != 200 or (root / "splits" / "test.jsonl").exists(): raise ProtocolViolation("test access contract violated")
    for seed in SEEDS:
        optimize, val = CapacityBundle(root, manifest, p0, folds, folds["external_validation"]).split_for_seed(seed)
        if len(optimize) != 100 or len(val) != 50 or {x.example_id for x in optimize}.intersection(x.example_id for x in val):
            raise ProtocolViolation("capacity fold construction mismatch")
    return CapacityBundle(root, manifest, p0, folds, folds["external_validation"])


@dataclass(frozen=True)
class CapacitySettings:
    reflection_minibatch_size: int = 3; no_improvement_patience: int = 10; max_candidate_proposals: int = 50
    max_merge_invocations: int = 5; merge_val_overlap_floor: int = 5; emergency_logical_safety: int = 1_000_000
    def validate(self) -> None:
        if (self.reflection_minibatch_size, self.no_improvement_patience, self.max_candidate_proposals,
            self.max_merge_invocations, self.merge_val_overlap_floor) != (3, 10, 50, 5, 5):
            raise ProtocolViolation("capacity GEPA stop/search contract changed")


def derive_capacity_gepa_seed(seed: int) -> int:
    if seed not in SEEDS: raise ProtocolViolation("unregistered capacity seed")
    return seed * 1000


class _RecordedStops:
    def __init__(self, patience: int, cap: int):
        import_vendor_gepa(); from gepa.utils import MaxCandidateProposalsStopper, NoImprovementStopper  # type: ignore
        self.no_improvement = NoImprovementStopper(max_iterations_without_improvement=patience)
        self.candidate_cap = MaxCandidateProposalsStopper(max_proposals=cap)
        self.reason: str | None = None
        self.checks = 0
    def __call__(self, state: Any) -> bool:
        self.checks += 1
        natural, cap = self.no_improvement(state), self.candidate_cap(state)
        if natural: self.reason = "no_improvement_patience_10"
        elif cap: self.reason = "max_candidate_proposals_50"
        return natural or cap


def _frontier_indices(result: Any) -> list[int]:
    return sorted({index for candidates in result.per_val_instance_best_candidates.values() for index in candidates})


def run_capacity_seed(*, bundle: CapacityBundle, seed: int, settings: CapacitySettings,
                      private_root: Path, public_root: Path, provider: OpenAICompatibleProvider) -> dict[str, Any]:
    """Run exactly one fold. External validation starts only after GEPA returns."""
    settings.validate(); optimize, optimizer_val = bundle.split_for_seed(seed)
    private = private_root / f"seed_{seed}"; public = public_root / f"seed_{seed}"; private.mkdir(parents=True, exist_ok=True); public.mkdir(parents=True, exist_ok=True)
    identity = _hash({"bundle": bundle.manifest["bundle_hash"], "seed": seed, "p0": bundle.manifest["p0_hash"],
                      "gepa": GEPA_COMMIT, "settings": settings.__dict__})
    identity_path = private / "run_identity.json"
    if identity_path.exists() and read_json(identity_path).get("identity") != identity: raise ProtocolViolation("capacity resume identity mismatch")
    write_canonical_json(identity_path, {"identity": identity, "seed": seed})
    # Accounting remains exhaustive but its very high emergency guard is not a normal stopper.
    ledger = BudgetLedger(total_budget=settings.emergency_logical_safety, member_count=1,
                          state_paths={0: private / "logical_ledger.json"})
    parser = StrictAnswerParser(read_json(bundle.root / "parser_contract.json")); parser.assert_golden_parity()
    evaluator = MemberEvaluator(member_id=0, provider=provider, parser=parser, budget=ledger, concurrency=1)
    adapter = IndependentGEPAAdapter(0, evaluator); stops = _RecordedStops(settings.no_improvement_patience, settings.max_candidate_proposals)
    gepa = import_vendor_gepa()
    result = gepa.optimize(seed_candidate={"system_prompt": bundle.p0}, trainset=list(optimize), valset=list(optimizer_val), adapter=adapter,
        reflection_lm=provider.reflection_callable(), candidate_selection_strategy="pareto", frontier_type="instance",
        skip_perfect_score=False, reflection_minibatch_size=3, module_selector="round_robin", use_merge=True,
        max_merge_invocations=5, merge_val_overlap_floor=5, cache_evaluation=False, max_metric_calls=None,
        stop_callbacks=stops, run_dir=str(private / "gepa"), display_progress_bar=False, seed=derive_capacity_gepa_seed(seed), raise_on_exception=True, track_best_outputs=True)
    if not isinstance(result.best_candidate, dict) or set(result.best_candidate) != {"system_prompt"}: raise ProtocolViolation("capacity result breaks one-prompt contract")
    if stops.reason is None: raise ProtocolViolation("GEPA ended without the registered capacity stopper")
    frontier = _frontier_indices(result); best_index = result.best_idx
    # Private state retains raw candidates/subscores; it is never copied into public reports.
    write_canonical_json(private / "candidate_state.json", {"result": result.to_dict(), "frontier_indices": frontier, "stop_reason": stops.reason})
    gepa_logical = int(ledger.snapshot()["consumed_total"])
    candidate_indices = sorted(set(frontier) | {0, best_index})
    external_scores: dict[int, float] = {}; external_details: dict[int, list[dict[str, Any]]] = {}
    for index in candidate_indices:
        evaluations = evaluator.evaluate(result.candidates[index]["system_prompt"], bundle.external_validation)
        external_scores[index] = sum(item.score for item in evaluations) / len(evaluations)
        external_details[index] = [{"example_id": item.example_id, "parsed": item.parsed_option, "correct": item.correct, "valid": item.valid} for item in evaluations]
    write_canonical_json(private / "external_validation_replay.json", external_details)
    selected = external_scores[best_index]; initial = external_scores[0]; oracle = max(external_scores.values())
    candidate_rows = [{"candidate_id": i, "candidate_hash": prompt_hash(result.candidates[i]["system_prompt"]), "optimizer_val_accuracy": result.val_aggregate_scores[i], "frontier_member": i in frontier, "selected": i == best_index, "parent_candidate_ids": [x for x in result.parents[i] if x is not None], "origin": "seed" if i == 0 else ("merge" if len([x for x in result.parents[i] if x is not None]) > 1 else "reflection")} for i in range(result.num_candidates)]
    write_canonical_json(public / "candidate_summary.json", candidate_rows)
    write_canonical_json(public / "frontier.json", {"candidate_ids": frontier, "size": len(frontier)})
    write_canonical_json(public / "validation_replay.json", {"candidate_external_accuracy": {str(k): v for k, v in external_scores.items()}})
    accounting = provider.accounting.snapshot()
    report = {"seed": seed, "gepa_seed": derive_capacity_gepa_seed(seed), "p0_hash": bundle.manifest["p0_hash"],
       "selected_candidate_id": best_index, "selected_candidate_hash": prompt_hash(result.best_candidate["system_prompt"]),
       "p0_optimizer_val_accuracy": result.val_aggregate_scores[0], "best_optimizer_val_accuracy": result.val_aggregate_scores[best_index],
       "selected_external_validation_accuracy": selected, "p0_external_validation_accuracy": initial,
       "generalizable_optimization_capacity": selected-initial, "generalization_gap": result.val_aggregate_scores[best_index]-selected,
       "frontier_oracle_external_validation_accuracy": oracle, "search_space_complementarity_gap": oracle-selected,
       "candidate_count": result.num_candidates, "frontier_size": len(frontier), "reflection_calls": accounting["roles"]["reflection"]["logical_calls"],
       "gepa_logical_task_example_evaluations": gepa_logical, "external_validation_logical_task_example_evaluations": len(candidate_indices) * len(bundle.external_validation),
       "logical_task_example_evaluations": ledger.snapshot()["consumed_total"], "proposal_iterations": stops.checks - 1,
       "candidate_proposals_since_last_best": result.num_candidates - 1 - max(i for i, score in enumerate(result.val_aggregate_scores) if score == max(result.val_aggregate_scores)), "api_accounting": accounting,
       "termination_reason": stops.reason, "saturation_status": "SATURATED" if stops.reason.startswith("no_improvement") else "NOT_SATURATED_CAP_HIT",
       "test_access": "denied", "optimizer_val_size": len(optimizer_val), "optimize_size": len(optimize)}
    write_canonical_json(public / "result.json", report); require_clean_public_artifacts([public]); return report
