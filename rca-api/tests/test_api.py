"""
rca-api/tests/test_api.py

Contract tests for the RCA API: they check that each endpoint answers in the
agreed shape, not how accurate the model is.

They need a trained model in ml/models/ (run ml/src/train.py first).

Run from the repository root:
    pytest rca-api/tests/test_api.py
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Make rca-api/main.py importable when pytest is started from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from main import app  # noqa: E402

KNOWN_ROOT_CAUSES = {
    "normal",
    "cpu_stress",
    "payment_failure",
    "db_slowness",
    "memory_leak",
    "network_latency",
}

HEALTHY_SNAPSHOT = {
    "timestamp": "2026-11-15T10:00:00Z",
    "gw_request_rate": 5.0,
    "gw_error_rate": 0.0,
    "gw_p95_latency": 8.0,
    "order_request_rate": 4.9,
    "order_error_rate": 0.0,
    "order_p95_latency": 5.0,
    "order_cpu": 0.005,
    "order_mem": 78.0,
    "payment_request_rate": 4.75,
    "payment_error_rate": 0.0,
    "payment_p95_latency": 4.5,
    "payment_cpu": 0.004,
    "payment_mem": 82.0,
    "db_query_latency_p95": 1.8,
    "db_connection_count": 4.0,
}


@pytest.fixture(scope="module")
def client():
    # Entering the context runs the app startup, which loads the model.
    with TestClient(app) as test_client:
        yield test_client


def metric_value(client, name: str) -> float:
    """Read one un-labelled metric from the /metrics text output."""
    for line in client.get("/metrics").text.splitlines():
        if line.startswith(name + " "):
            return float(line.split()[1])
    raise AssertionError(f"metric {name} not found in /metrics")


def test_health_reports_ok_and_model_version(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model_version"]


def test_predict_returns_a_known_root_cause(client):
    response = client.post("/predict", json=HEALTHY_SNAPSHOT)

    assert response.status_code == 200
    body = response.json()
    assert body["predicted_root_cause"] in KNOWN_ROOT_CAUSES
    assert 0.0 <= body["confidence"] <= 1.0
    assert len(body["top3_candidates"]) == 3
    assert body["top3_candidates"][0]["fault_type"] == body["predicted_root_cause"]
    assert body["evidence"]["key_metrics"]


def test_predict_rejects_incomplete_snapshot(client):
    response = client.post("/predict", json={"gw_request_rate": 5.0})

    assert response.status_code == 422


def test_metrics_count_each_prediction(client):
    before = metric_value(client, "rca_inference_requests_total")

    client.post("/predict", json=HEALTHY_SNAPSHOT)

    assert metric_value(client, "rca_inference_requests_total") == before + 1
