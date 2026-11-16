from fastapi.testclient import TestClient
import pytest
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["service"] == "ai-rca-api"

def test_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "rca_inference_requests_total" in response.text

def test_predict_endpoint_valid_snapshot():
    sample_request = {
        "timestamp": "2026-11-15T20:00:00Z",
        "gw_request_rate": 5.0,
        "gw_error_rate": 0.85,
        "gw_p95_latency": 150.0,
        "order_request_rate": 4.8,
        "order_error_rate": 0.80,
        "order_p95_latency": 140.0,
        "order_cpu": 0.05,
        "order_mem": 80.0,
        "payment_request_rate": 4.5,
        "payment_error_rate": 1.0,
        "payment_p95_latency": 120.0,
        "payment_cpu": 0.03,
        "payment_mem": 85.0,
        "db_query_latency_p95": 2.5,
        "db_connection_count": 5.0,
        "pod_restart_count": 0.0
    }
    response = client.post("/predict", json=sample_request)
    assert response.status_code in [200, 503]
    if response.status_code == 200:
        data = response.json()
        assert "predicted_root_cause" in data
        assert "confidence" in data
        assert "top3_candidates" in data

