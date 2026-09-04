"""Frozen model routing for experiments after the V17 qwen3-14b run."""

from __future__ import annotations

from typing import Any

from .versions import (
    EVALUATOR_MODEL,
    OPTIMIZER_MODEL,
    REFLECTION_MODEL,
    SOLVER_MODEL,
    TASK_REQUEST_TEMPLATE_VERSION,
)

MODEL_PROFILE_ID = "qwen3_14b_solver_qwen3_7_flash_control_v1"


def split_role_model_contract() -> dict[str, Any]:
    transport = {
        "temperature": 0.0,
        "max_tokens": 1800,
        "timeout_seconds": 120.0,
        "max_retries": 3,
        "enable_thinking": False,
    }
    return {
        "schema_version": "model_contract_v3",
        "model_profile_id": MODEL_PROFILE_ID,
        "pricing_per_million_tokens": {
            "task": {"prompt": 1.0, "completion": 4.0},
            "reflection": {"prompt": 0.2, "completion": 0.8},
        },
        "pricing_contract": {
            "currency": "CNY",
            "region_class": "china_beijing_or_us_virginia",
            "thinking": False,
            "sources": [
                "https://help.aliyun.com/zh/model-studio/qwen3-14b",
                "https://help.aliyun.com/zh/model-studio/qwen3-7-flash",
            ],
            "verified_date": "2026-09-04",
            "discounts_and_free_quota_excluded": True,
        },
        "shared_task_model": {
            "model": SOLVER_MODEL,
            **transport,
            "parser_version": "task_parser_v1",
            "output_contract_version": "task_output_contract_v1",
            "request_template_version": TASK_REQUEST_TEMPLATE_VERSION,
            "question_rendering_version": "bbh_options_marker_v1",
        },
        "independent_gepa_evaluator_model": {
            "model": EVALUATOR_MODEL,
            "enable_thinking": False,
            "usage": "feedback_control_role_only; correctness_is_strict_parser_plus_gold",
        },
        "independent_gepa_optimizer_model": {
            "model": OPTIMIZER_MODEL,
            **transport,
        },
        "independent_gepa_reflection_model": {
            "model": REFLECTION_MODEL,
            **transport,
        },
        "reference_optimizer": {
            "model": "qwen3-14b",
            "roles": {
                "teacher": {"temperature": 0.4},
                "critic": {"temperature": 0.0},
                "student": {"temperature": 0.5},
            },
            "usage": "historical_reference_metadata_only; never called by Independent-GEPA",
        },
    }
