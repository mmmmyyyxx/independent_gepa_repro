"""Five isolated GEPA searches and direct final-team composition."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

import yaml

from ._vendor import import_vendor_gepa
from .adapter import IndependentGEPAAdapter
from .artifacts import sanitize_member_results, stable_config_hash, write_private_json
from .budget import BudgetLedger
from .bundle import ValidatedBundle, prompt_hash, validate_bundle, write_canonical_json
from .evaluator import MemberEvaluator
from .parser import StrictAnswerParser
from .protocol import ProtocolViolation, SplitAccessController, SplitName
from .provider import OpenAICompatibleProvider, ProviderAccounting
from .versions import CHECKPOINT_VERSION, METHOD_ID


@dataclass(frozen=True)
class GEPASettings:
    candidate_selection_strategy: str
    frontier_type: str
    skip_perfect_score: bool
    reflection_minibatch_size: int
    perfect_score: float
    use_merge: bool
    max_merge_invocations: int
    merge_val_overlap_floor: int
    cache_evaluation: bool
    display_progress_bar: bool

    @staticmethod
    def from_mapping(raw: Mapping[str, Any]) -> "GEPASettings":
        settings = GEPASettings(
            candidate_selection_strategy=str(raw["candidate_selection_strategy"]),
            frontier_type=str(raw["frontier_type"]),
            skip_perfect_score=bool(raw["skip_perfect_score"]),
            reflection_minibatch_size=int(raw["reflection_minibatch_size"]),
            perfect_score=float(raw["perfect_score"]),
            use_merge=bool(raw["use_merge"]),
            max_merge_invocations=int(raw["max_merge_invocations"]),
            merge_val_overlap_floor=int(raw["merge_val_overlap_floor"]),
            cache_evaluation=bool(raw["cache_evaluation"]),
            display_progress_bar=bool(raw["display_progress_bar"]),
        )
        if settings.candidate_selection_strategy != "pareto" or settings.frontier_type != "instance":
            raise ProtocolViolation("protocol requires Pareto selection with instance frontier")
        if settings.cache_evaluation:
            raise ProtocolViolation("upstream evaluation cache must be off so logical cache hits remain countable")
        if settings.reflection_minibatch_size <= 0:
            raise ProtocolViolation("reflection_minibatch_size must be positive")
        return settings


@dataclass(frozen=True)
class RunConfig:
    method_id: str
    stage: str
    real_api_allowed: bool
    members: int
    task_model: str
    reflection_model: str
    member_ids: tuple[int, ...]
    optimization_example_limit: int | None
    canary_member_budget: int | None
    gepa: GEPASettings
    raw: Mapping[str, Any]

    @staticmethod
    def load(path: Path) -> "RunConfig":
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ProtocolViolation(f"invalid run config: {exc}") from exc
        if not isinstance(raw, dict):
            raise ProtocolViolation("run config must be a mapping")
        provider_raw = raw.get("provider")
        if not isinstance(provider_raw, dict):
            raise ProtocolViolation("run config requires a provider mapping")
        required_provider_fields = {
            "api_key_env",
            "base_url_env",
            "temperature",
            "max_tokens",
            "timeout_seconds",
            "max_retries",
            "enable_thinking",
        }
        if not required_provider_fields.issubset(provider_raw):
            raise ProtocolViolation("run config provider mapping is incomplete")
        if provider_raw["enable_thinking"] is not False:
            raise ProtocolViolation("run config must disable thinking")
        if (
            int(provider_raw["max_tokens"]) <= 0
            or float(provider_raw["timeout_seconds"]) <= 0
            or int(provider_raw["max_retries"]) < 0
        ):
            raise ProtocolViolation("run config provider settings are invalid")
        stage = str(raw.get("stage", ""))
        members = int(raw.get("members", 0))
        raw_member_ids = raw.get("member_ids", list(range(members)))
        if not isinstance(raw_member_ids, list):
            raise ProtocolViolation("member_ids must be a list")
        config = RunConfig(
            method_id=str(raw.get("method_id", "")),
            stage=stage,
            real_api_allowed=bool(raw.get("real_api_allowed", False)),
            members=members,
            task_model=str(raw.get("task_model", "")),
            reflection_model=str(raw.get("reflection_model", "")),
            member_ids=tuple(int(item) for item in raw_member_ids),
            optimization_example_limit=(
                int(raw["optimization_example_limit"])
                if raw.get("optimization_example_limit") is not None
                else None
            ),
            canary_member_budget=(
                int(raw["logical_evaluation_budget"])
                if stage == "canary" and raw.get("logical_evaluation_budget") is not None
                else None
            ),
            gepa=GEPASettings.from_mapping(raw.get("gepa", {})),
            raw=raw,
        )
        if config.method_id != METHOD_ID:
            raise ProtocolViolation("run config method identity mismatch")
        if config.stage not in {"canary", "pilot", "formal", "offline_fake"}:
            raise ProtocolViolation("unsupported run stage")
        if config.stage in {"pilot", "formal", "offline_fake"} and config.members != 5:
            raise ProtocolViolation("five members are required outside the member-zero canary")
        if config.stage == "canary":
            if config.members != 1 or config.member_ids != (0,):
                raise ProtocolViolation("canary must run member 0 only")
            if config.optimization_example_limit != 5:
                raise ProtocolViolation("canary must use exactly five optimization examples")
            if config.canary_member_budget is None or config.canary_member_budget < 5:
                raise ProtocolViolation("canary member logical budget must cover its five seed examples")
        elif config.member_ids != (0, 1, 2, 3, 4):
            raise ProtocolViolation("five-member stages require stable member ordering 0..4")
        return config


@dataclass(frozen=True)
class MemberOptimizationResult:
    member_id: int
    gepa_seed: int
    best_prompt: str
    candidate_count: int
    logical_evaluations: int
    completed: bool = True


class MemberExecutor(Protocol):
    def optimize(
        self,
        *,
        member_id: int,
        seed_prompt: str,
        optimization_examples: Sequence[Any],
        adapter: IndependentGEPAAdapter,
        provider: OpenAICompatibleProvider,
        settings: GEPASettings,
        run_dir: Path,
        gepa_seed: int,
        member_budget: int,
    ) -> MemberOptimizationResult: ...


class RealGEPAExecutor:
    """Thin adapter around the fixed v0.1.1 public API."""

    def optimize(
        self,
        *,
        member_id: int,
        seed_prompt: str,
        optimization_examples: Sequence[Any],
        adapter: IndependentGEPAAdapter,
        provider: OpenAICompatibleProvider,
        settings: GEPASettings,
        run_dir: Path,
        gepa_seed: int,
        member_budget: int,
    ) -> MemberOptimizationResult:
        gepa = import_vendor_gepa()
        ledger = adapter.evaluator.budget
        consumed_before = ledger.consumed_by_member[member_id]
        validation_size = len(optimization_examples)
        reflection_iteration_cost = 2 * settings.reflection_minibatch_size + validation_size
        merge_iteration_cost = 5 + validation_size if settings.use_merge else 0
        reserve_cost = max(reflection_iteration_cost, merge_iteration_cost)

        class RemainingLogicalBudgetStopper:
            def __call__(self, _gepa_state: Any) -> bool:
                return ledger.remaining(member_id) < reserve_cost

        result = gepa.optimize(
            seed_candidate={"system_prompt": seed_prompt},
            trainset=list(optimization_examples),
            valset=list(optimization_examples),
            adapter=adapter,
            reflection_lm=provider.reflection_callable(),
            candidate_selection_strategy=settings.candidate_selection_strategy,
            frontier_type=settings.frontier_type,
            skip_perfect_score=settings.skip_perfect_score,
            reflection_minibatch_size=settings.reflection_minibatch_size,
            perfect_score=settings.perfect_score,
            module_selector="round_robin",
            use_merge=settings.use_merge,
            max_merge_invocations=settings.max_merge_invocations,
            merge_val_overlap_floor=settings.merge_val_overlap_floor,
            max_metric_calls=member_budget,
            stop_callbacks=RemainingLogicalBudgetStopper(),
            run_dir=str(run_dir),
            display_progress_bar=settings.display_progress_bar,
            cache_evaluation=False,
            seed=gepa_seed,
            raise_on_exception=True,
        )
        best = result.best_candidate
        if not isinstance(best, dict) or set(best) != {"system_prompt"}:
            raise ProtocolViolation("GEPA returned a candidate outside the one-component contract")
        return MemberOptimizationResult(
            member_id=member_id,
            gepa_seed=gepa_seed,
            best_prompt=best["system_prompt"],
            candidate_count=result.num_candidates,
            logical_evaluations=ledger.consumed_by_member[member_id] - consumed_before,
        )


ProviderFactory = Callable[[int, Path, ProviderAccounting], OpenAICompatibleProvider]


class IndependentRunner:
    def __init__(
        self,
        *,
        bundle: ValidatedBundle,
        config: RunConfig,
        output_root: Path,
        provider_factory: ProviderFactory,
        executor: MemberExecutor,
    ):
        if config.task_model != bundle.model_contract["task_model"]:
            raise ProtocolViolation("config and bundle task model mismatch")
        if config.reflection_model != bundle.model_contract["reflection_model"]:
            raise ProtocolViolation("config and bundle reflection model mismatch")
        self.bundle = bundle
        self.config = config
        self.output_root = output_root.resolve()
        self.provider_factory = provider_factory
        self.executor = executor
        self.access = SplitAccessController(formal=config.stage == "formal")

    def _checkpoint_identity(self, member_id: int, initial_prompt: str, member_budget: int) -> dict[str, Any]:
        return {
            "checkpoint_version": CHECKPOINT_VERSION,
            "method_id": METHOD_ID,
            "bundle_hash": self.bundle.overall_hash,
            "experiment_seed": self.bundle.experiment_seed,
            "member_id": member_id,
            "gepa_seed": self.bundle.experiment_seed * 1000 + member_id,
            "initial_prompt_hash": prompt_hash(initial_prompt),
            "member_budget": member_budget,
            "config_hash": stable_config_hash(self.config.raw),
        }

    @staticmethod
    def _prepare_checkpoint(run_dir: Path, expected: Mapping[str, Any]) -> None:
        metadata = run_dir / "checkpoint_identity.json"
        upstream = run_dir / "gepa_state.bin"
        if upstream.exists() and not metadata.exists():
            raise ProtocolViolation("upstream checkpoint exists without independent identity metadata")
        if metadata.exists():
            try:
                actual = json.loads(metadata.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProtocolViolation(f"invalid checkpoint identity: {exc}") from exc
            if actual != dict(expected):
                raise ProtocolViolation("checkpoint identity mismatch")
        else:
            run_dir.mkdir(parents=True, exist_ok=True)
            write_canonical_json(metadata, dict(expected))

    def _load_completed_result(
        self, run_dir: Path, *, member_id: int, gepa_seed: int
    ) -> MemberOptimizationResult | None:
        path = run_dir / "member_result_private.json"
        if not path.exists():
            return None
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProtocolViolation(f"invalid completed member result: {exc}") from exc
        required_identity = {
            "bundle_hash": self.bundle.overall_hash,
            "member_id": member_id,
            "gepa_seed": gepa_seed,
            "completed": True,
        }
        if not isinstance(row, dict) or any(row.get(key) != value for key, value in required_identity.items()):
            raise ProtocolViolation("completed member result identity mismatch")
        best_prompt = row.get("best_prompt")
        candidate_count = row.get("candidate_count")
        if not isinstance(best_prompt, str) or not best_prompt or not isinstance(candidate_count, int):
            raise ProtocolViolation("completed member result is incomplete")
        return MemberOptimizationResult(
            member_id=member_id,
            gepa_seed=gepa_seed,
            best_prompt=best_prompt,
            candidate_count=candidate_count,
            logical_evaluations=0,
            completed=True,
        )

    def run(self) -> tuple[tuple[str, ...], dict[str, Any]]:
        started = time.monotonic()
        self.access.access_for_optimization(SplitName.OPTIMIZATION)
        optimization_examples = self.bundle.splits[SplitName.OPTIMIZATION.value]
        if self.config.optimization_example_limit is not None:
            optimization_examples = optimization_examples[: self.config.optimization_example_limit]
        total_budget = (
            self.config.canary_member_budget * 5
            if self.config.canary_member_budget is not None
            else self.bundle.total_budget
        )
        budget = BudgetLedger(
            total_budget,
            member_count=5,
            state_paths={
                member_id: self.output_root / f"member_{member_id}" / "logical_budget_ledger.json"
                for member_id in range(5)
            },
        )
        accounting = ProviderAccounting()
        prompts: list[str] = []
        rows: list[dict[str, Any]] = []
        object_ids: set[int] = set()
        runtime_objects: list[object] = []
        run_dirs: set[Path] = set()
        for member_id in self.config.member_ids:
            initial_prompt = self.bundle.prompts[member_id]
            run_dir = self.output_root / f"member_{member_id}"
            if run_dir in run_dirs:
                raise ProtocolViolation("member run-directory collision")
            run_dirs.add(run_dir)
            checkpoint = self._checkpoint_identity(member_id, initial_prompt, budget.member_budget)
            self._prepare_checkpoint(run_dir, checkpoint)
            consumed_before = budget.consumed_by_member[member_id]
            result = self._load_completed_result(
                run_dir,
                member_id=member_id,
                gepa_seed=self.bundle.experiment_seed * 1000 + member_id,
            )
            if result is None:
                provider = self.provider_factory(member_id, run_dir, accounting)
                evaluator = MemberEvaluator(
                    member_id=member_id,
                    provider=provider,
                    parser=StrictAnswerParser(self.bundle.parser_contract),
                    budget=budget,
                )
                adapter = IndependentGEPAAdapter(member_id, evaluator)
                for obj in (provider, evaluator, adapter):
                    if id(obj) in object_ids:
                        raise ProtocolViolation("cross-member runtime object reuse")
                    object_ids.add(id(obj))
                    runtime_objects.append(obj)
                result = self.executor.optimize(
                    member_id=member_id,
                    seed_prompt=initial_prompt,
                    optimization_examples=optimization_examples,
                    adapter=adapter,
                    provider=provider,
                    settings=self.config.gepa,
                    run_dir=run_dir,
                    gepa_seed=self.bundle.experiment_seed * 1000 + member_id,
                    member_budget=budget.member_budget,
                )
            if result.member_id != member_id or result.gepa_seed != checkpoint["gepa_seed"]:
                raise ProtocolViolation("member executor returned mismatched identity")
            consumed_during_run = budget.consumed_by_member[member_id] - consumed_before
            if result.logical_evaluations != consumed_during_run:
                raise ProtocolViolation(
                    f"member {member_id} logical accounting mismatch: "
                    f"executor={result.logical_evaluations}, ledger={consumed_during_run}"
                )
            if not result.best_prompt:
                raise ProtocolViolation("member executor returned an invalid best prompt")
            prompts.append(result.best_prompt)
            row = asdict(result)
            row.pop("best_prompt")
            row["logical_evaluations"] = budget.consumed_by_member[member_id]
            row["initial_prompt_hash"] = checkpoint["initial_prompt_hash"]
            rows.append(row)
            write_private_json(
                run_dir / "member_result_private.json",
                {
                    **row,
                    "best_prompt": result.best_prompt,
                    "bundle_hash": self.bundle.overall_hash,
                },
            )
        hashes = tuple(prompt_hash(prompt) for prompt in prompts)
        final_team_frozen = len(prompts) == 5
        if final_team_frozen:
            self.access.freeze(hashes)
            write_private_json(
                self.output_root / "final_team_private.json",
                {
                    "bundle_hash": self.bundle.overall_hash,
                    "experiment_seed": self.bundle.experiment_seed,
                    "frozen": True,
                    "prompts": prompts,
                    "prompt_hashes": list(hashes),
                },
            )
        else:
            write_private_json(
                self.output_root / "canary_member_private.json",
                {
                    "bundle_hash": self.bundle.overall_hash,
                    "experiment_seed": self.bundle.experiment_seed,
                    "frozen_final_team": False,
                    "member_id": self.config.member_ids[0],
                    "prompt": prompts[0],
                    "prompt_hash": hashes[0],
                },
            )
        summary = sanitize_member_results(
            bundle_hash=self.bundle.overall_hash,
            experiment_seed=self.bundle.experiment_seed,
            prompts=prompts,
            member_rows=rows,
            budget=budget.snapshot(),
            provider_accounting=accounting.snapshot(),
            wall_clock_seconds=time.monotonic() - started,
        )
        summary["stage"] = self.config.stage
        summary["final_team_frozen"] = final_team_frozen
        return tuple(prompts), summary


def load_validated_inputs(bundle_path: Path, config_path: Path) -> tuple[ValidatedBundle, RunConfig]:
    config = RunConfig.load(config_path)
    bundle = validate_bundle(bundle_path, require_formal=config.stage in {"formal", "pilot", "offline_fake"})
    StrictAnswerParser(bundle.parser_contract).assert_golden_parity()
    required_seed_evaluations = (
        config.optimization_example_limit
        if config.optimization_example_limit is not None
        else len(bundle.splits[SplitName.OPTIMIZATION.value])
    )
    available_member_budget = (
        config.canary_member_budget
        if config.canary_member_budget is not None
        else bundle.total_budget // 5
    )
    if available_member_budget < required_seed_evaluations:
        raise ProtocolViolation("member budget cannot cover the mandatory seed-candidate evaluation")
    return bundle, config
