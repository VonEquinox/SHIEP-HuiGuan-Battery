"""Real package binding, numeric jobs and Agent context on disposable assets."""
import pytest

from app.db import now, one, tx
from test_platform import seed
from test_v2_workflow import work_job


@pytest.mark.parametrize(
    "package_id,input_source,protocol,query_time,physical",
    [
        ("M1_matr_lifetime_masked_seed0", "committed_development_bundle", "4.8C(80%)-4.8C", 50, True),
        ("M1_multisource_seed0", "label_free_package_development_examples", "unknown", 11, False),
    ],
)
def test_package_owned_inputs_reach_real_numeric_job_and_agent(
    admin, monkeypatch, package_id, input_source, protocol, query_time, physical
):
    monkeypatch.delenv("BATTERY_LLM_API_KEY", raising=False)
    existing = seed(admin)
    response = admin.post("/api/assets", json={"code": "package-lab-cell", "name": "研究包回放验证电芯",
                                               "kind": "cell", "parent_id": existing["parent_id"]})
    assert response.status_code == 201, response.text
    asset = response.json()
    catalog = admin.get("/api/v2/model-packages").json()
    package = next(item for item in catalog["items"] if item["package_id"] == package_id)
    assert package["binding_input_source"] == input_source
    row = next(item for item in package["feature_rows"] if item["source_id"] == "matr"
               and item["split"] == "dev" and item["protocol_id"] == protocol and item["query_time"] == query_time)
    response = admin.post(f"/api/v2/assets/{asset['id']}/v2-binding",
                          json={"version": asset["version"], "installation_id": asset["installation_id"],
                                "package_id": package_id, "row_index": row["row_index"]},
                          headers={"Idempotency-Key": "package-live-binding"})
    assert response.status_code == 200, response.text
    assert response.json()["binding"]["physical_cell_id"] == row["physical_cell_id"]
    response = admin.post("/api/v2/model-runs", json={"kind": "v2_inference", "asset_id": asset["id"]},
                          headers={"Idempotency-Key": "package-live-job"})
    assert response.status_code == 202, response.text
    job = work_job(response.json()["job_id"])
    assert job["status"] == "succeeded", job["error"]
    profile = admin.get(f"/api/v2/assets/{asset['id']}/prediction-profile").json()
    assert profile["query"]["physical_cell_id"] == row["physical_cell_id"]
    assert profile["query"]["source_id"] == "matr"
    assert profile["provenance"] == "experimental_replay_on_simulated_asset"
    assert profile["production_connected"] is False
    assert set(profile["query"]).isdisjoint({"survival_censor_type", "survival_label_observed_at",
                                            "survival_label_available_at", "target_observed_at", "target_available_at", "split"})
    heads = {head["head"]: head for head in profile["heads"]}
    assert heads["soh"]["support"] == "supported" and heads["soh"]["value"] is not None
    if physical:
        assert profile["query"]["source_time"]["time_basis"] == "verified_physical_cycle"
        assert profile["query"]["source_time"]["query_cycle"] == 50
        assert heads["rul"]["support"] == "supported"
        assert heads["efficiency"]["support"] == heads["fault"]["support"] == "unsupported"
        assert heads["rul"]["distribution"]["kind"] == "discrete_survival"
        assert heads["rul"]["calibration_version"] is None
        assert heads["soh"]["calibrated_interval"]["status"] == "insufficient_calibration_objects"
    else:
        assert profile["query"]["source_time"]["time_basis"] == "source_record_ordinal"
    response = admin.post("/api/v2/agent/runs", json={"asset_id": asset["id"],
                           "installation_id": asset["installation_id"], "visible_cutoff": now()},
                          headers={"Idempotency-Key": "package-live-agent"})
    assert response.status_code == 202, response.text
    job = work_job(response.json()["job_id"])
    assert job["status"] == "succeeded", job["error"]
    with tx() as connection:
        assert one(connection, "SELECT count(*) n FROM orders")["n"] == 0
        assert one(connection, "SELECT count(*) n FROM bindings WHERE asset_id=:a", {"a": asset["id"]})["n"] == 0
