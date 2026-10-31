"""Exercise the real phase runner on synthetic data and a socket-blocked fake LM.

The real authorization validator is deliberately replaced by a synthetic-only
fixture. This is runner/persistence evidence, never a real freeze or API grant.
"""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
from unittest.mock import patch
import uuid

from .contract import IDENTITY, TASKS, draft
from .control import request_role
from .data import canonical, digest
from .models import role_route
from .sources import file_hash
from .execution import POLICY_PATH, GRANT_SCHEMA, execution_policy, execution_binding


def verify_lifecycle(workspace: Path, output: Path) -> dict:
    from . import runtime
    import litellm

    output.mkdir(parents=True, exist_ok=False)
    fake_root = output / "synthetic_source"
    (fake_root / "runs").mkdir(parents=True)
    (fake_root / POLICY_PATH).parent.mkdir(parents=True)
    (fake_root / POLICY_PATH).write_bytes(canonical(execution_policy()) + b"\n")
    bundle = output / "synthetic_data"
    fixture_task = replace(next(t for t in TASKS if t.key == "aime2025"),
                           budget=10, sizes=(6, 4, 2))
    for split, size in zip(("train", "validation", "test"), fixture_task.sizes):
        directory = bundle / fixture_task.key
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (split + ".jsonl")).write_bytes(b"".join(
            canonical({"example": {"problem": f"Synthetic lifecycle {split} {i}", "answer": "1"}}) + b"\n"
            for i in range(size)))
    scope = "offline_lifecycle_" + uuid.uuid4().hex
    validations = []
    dispatches = []
    def synthetic_validation(root, observed_workspace, grant):
        if (root != fake_root or observed_workspace != workspace or grant.get("real_api_allowed") is not False
                or grant.get("approved_by") != "synthetic_offline_fixture"
                or not grant["scope_id"].startswith(scope)):
            raise AssertionError("SYNTHETIC_VALIDATION_SCOPE_ESCAPE")
        validations.append(grant["phase"])
        return {"task": fixture_task, "bundle": bundle}

    def completion(**kwargs):
        role = request_role(kwargs["messages"])
        if kwargs["model"] != role_route(role)["model"]:
            raise AssertionError("LIFECYCLE_ROLE_MODEL_DRIFT")
        dispatches.append(role)
        if role == "reflection":
            text = "```\nSYNTHETIC_IMPROVED. Return one.\n```"
        else:
            improved = "SYNTHETIC_IMPROVED" in kwargs["messages"][0]["content"]
            text = ("[[ ## reasoning ## ]]\nSynthetic reasoning.\n[[ ## answer ## ]]\n"
                    + ("1" if improved else "0") + "\n[[ ## completed ## ]]")
        return litellm.ModelResponse(model="synthetic-offline", choices=[{
            "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})

    models = draft()["models"]
    shared = dict(schema=GRANT_SCHEMA, approved_by="synthetic_offline_fixture",
                  READY_TO_RUN=False, real_api_allowed=False, task=fixture_task.key, seed=0, repeat=1,
                  source_sha="0" * 40, config_sha256=digest(draft()), data_receipt_sha256=digest({"synthetic": True}),
                  environment_lock_sha256="0" * 64, cache_namespace=scope,
                  solver_model=models["solver"], reflection_model=models["reflection"],
                  reflection_provider=models["reflection_provider_profile"], provider=models["provider_profile"],
                  deployment_base_url_sha256="1" * 64, reflection_deployment_base_url_sha256="2" * 64,
                  max_logical_evaluations=100, max_physical_attempts=200, max_elapsed_seconds=180)
    shared.update(execution_binding(fake_root, os.cpu_count()))
    receipts = {}
    environment = dict(OPENLUX_API_KEY="synthetic-solver-key", OPENLUX_BASE_URL="https://solver.invalid/v1",
                       LWJ_DASHSCOPE_API_KEY="synthetic-reflection-key", LWJ_DASHSCOPE_BASE_URL="https://reflection.invalid/v1")
    with patch.dict(os.environ, environment), patch.object(runtime, "validate_grant", synthetic_validation), \
            patch.object(litellm, "completion", completion):
        for phase in ("canary", "search", "baseline", "final_test"):
            grant = {**shared, "scope_id": scope + "_" + phase, "phase": phase,
                     "roles": ["solver", "reflection"] if phase in {"canary", "search"} else ["solver"]}
            if phase == "final_test":
                selected = workspace / "execution" / (scope + "_search") / "selected_program.json"
                grant.update(selected_program=selected.relative_to(workspace).as_posix(),
                             selected_program_sha256=file_hash(selected))
            grant_path = output / (phase + ".synthetic.json")
            grant_path.write_bytes(canonical(grant) + b"\n")
            receipts[phase] = runtime.execute(fake_root, workspace, grant_path)
            if receipts[phase]["status"] != "COMPLETE":
                raise AssertionError("LIFECYCLE_PHASE_NOT_COMPLETE:" + phase)
            if not receipts[phase]["phase_futures"]["drained"] or receipts[phase]["phase_futures"]["pending"]:
                raise AssertionError("LIFECYCLE_FUTURES_NOT_DRAINED")
            events = [json.loads(line) for line in (workspace / "execution" / grant["scope_id"] / "ledger.jsonl")
                      .read_text(encoding="utf-8").splitlines()]
            splits = [e["split"] for e in events if e["event"] == "data_split_load"]
            if phase == "search" and splits != ["train", "validation"]:
                raise AssertionError("LIFECYCLE_SEARCH_SPLIT_ACCESS_DRIFT")
            if phase in {"baseline", "final_test"}:
                if splits != ["test"] or receipts[phase]["tokens"]["reflection"] != {"prompt": 0, "completion": 0}:
                    raise AssertionError("LIFECYCLE_FINAL_ROLE_OR_SPLIT_DRIFT")
                profile = json.loads((workspace / "execution" / grant["scope_id"] / "test_profile.private.json").read_text())
                if len(profile["predictions"]) != 2 or len(profile["scores"]) != 2:
                    raise AssertionError("AUTHOR_EVALUATE_TRIPLES_NOT_PERSISTED")
    if (receipts["baseline"]["score"] != 0 or receipts["final_test"]["score"] != 100
            or len(validations) != 8):
        raise AssertionError("LIFECYCLE_SELECTION_OR_REVALIDATION_FAILED")
    return {"phases_complete": list(receipts), "synthetic_baseline_score": 0, "synthetic_selected_score": 100,
            "predictions_persisted_per_test_phase": 2, "pre_post_validation_calls": len(validations),
            "physical_roles": {role: dispatches.count(role) for role in ("solver", "reflection")},
            "search_test_access": False, "model_api_calls": 0,
            "limitation": "synthetic-only grant validator; does not establish real source freeze or authorization"}
