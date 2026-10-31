import json

import pytest

from independent_gepa.paper_suite.contract import TASKS
from independent_gepa.paper_suite.data import canonical
from independent_gepa.paper_suite.preparation import phase_plan, safe_deployment_presence, verify_data_files
from independent_gepa.paper_suite.sources import file_hash


def test_launch_plan_has_all_cells_and_never_creates_an_authorization():
    cells = phase_plan()
    assert len(cells) == 16
    assert sum(c["native_search_threshold"] for c in cells if c["phase"] == "search") == 21193
    assert sum(c["max_logical_evaluations"] for c in cells if c["phase"] in {"baseline", "final_test"}) == 2340
    assert [c["phase"] for c in cells] == ["canary"] + ["search"] * 5 + ["baseline"] * 5 + ["final_test"] * 5
    for c in cells:
        assert c["approved_by"] is None and not c["READY_TO_RUN"] and not c["real_api_allowed"]
        assert c["source_sha"] is None and c["scope_id"] is None
        assert c["seed"] == 0 and c["repeat"] == 1
        assert all(type(c[k]) is int and c[k] > 0 for k in
                   ("max_logical_evaluations", "max_physical_attempts", "max_elapsed_seconds"))


@pytest.mark.parametrize("value", [
    {"OPENLUX_API_KEY": "synthetic-secret"}, {"private_endpoint": "https://synthetic.invalid/v1"},
])
def test_public_deployment_inventory_cannot_persist_secret_values(value):
    with pytest.raises(ValueError, match="BOOLEAN_DEPLOYMENT"):
        safe_deployment_presence(value)


def test_offline_deployment_inventory_distinguishes_unknown_from_missing():
    assert safe_deployment_presence(None)["status"].startswith("NOT_CHECKED")
    values = {k: False for k in ("OPENLUX_API_KEY", "OPENLUX_BASE_URL", "LWJ_DASHSCOPE_API_KEY", "LWJ_DASHSCOPE_BASE_URL")}
    assert safe_deployment_presence(values) == values


def test_launch_rechecks_every_data_file_and_refuses_payload_drift(tmp_path):
    receipt = {"splits": {}}
    for task in TASKS:
        receipt["splits"][task.key] = {}
        directory = tmp_path / task.key
        directory.mkdir()
        for split, size in zip(("train", "validation", "test"), task.sizes):
            path = directory / (split + ".jsonl")
            path.write_bytes((canonical({"example": "synthetic"}) + b"\n") * size)
            receipt["splits"][task.key][split] = {"count": size, "file_sha256": file_hash(path)}
    assert verify_data_files(tmp_path, receipt) == {"files": 15, "rows": 2852, "hash_mismatches": 0}
    (tmp_path / "aime2025/test.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="LAUNCH_DATA_FILE_DRIFT"):
        verify_data_files(tmp_path, receipt)
