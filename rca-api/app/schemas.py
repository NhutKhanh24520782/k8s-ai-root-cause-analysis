from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MetricSnapshotRequest(BaseModel):
    """Real-time observability metric snapshot from Prometheus / telemetry."""

    timestamp: Optional[str] = Field(None, description="ISO timestamp of metric collection")
    gw_request_rate: float = Field(..., ge=0.0, description="API Gateway requests/sec")
    gw_error_rate: float = Field(..., ge=0.0, le=1.0, description="API Gateway 5xx error rate [0.0 - 1.0]")
    gw_p95_latency: float = Field(..., ge=0.0, description="API Gateway p95 latency in ms")

    order_request_rate: float = Field(..., ge=0.0, description="Order Service requests/sec")
    order_error_rate: float = Field(..., ge=0.0, le=1.0, description="Order Service error rate [0.0 - 1.0]")
    order_p95_latency: float = Field(..., ge=0.0, description="Order Service p95 latency in ms")
    order_cpu: float = Field(..., ge=0.0, description="Order Service CPU utilization [0.0 - 1.0+]")
    order_mem: float = Field(..., ge=0.0, description="Order Service Memory in MB")

    payment_request_rate: float = Field(..., ge=0.0, description="Payment Service requests/sec")
    payment_error_rate: float = Field(..., ge=0.0, le=1.0, description="Payment Service error rate [0.0 - 1.0]")
    payment_p95_latency: float = Field(..., ge=0.0, description="Payment Service p95 latency in ms")
    payment_cpu: float = Field(..., ge=0.0, description="Payment Service CPU utilization [0.0 - 1.0+]")
    payment_mem: float = Field(..., ge=0.0, description="Payment Service Memory in MB")

    db_query_latency_p95: float = Field(..., ge=0.0, description="PostgreSQL query p95 latency in ms")
    db_connection_count: float = Field(..., ge=0.0, description="Active database connection count")

    model_config = {
        "json_schema_extra": {
            "example": {
                "timestamp": "2026-11-11T16:00:00Z",
                "gw_request_rate": 5.2,
                "gw_error_rate": 0.0,
                "gw_p95_latency": 12.5,
                "order_request_rate": 5.1,
                "order_error_rate": 0.0,
                "order_p95_latency": 10.2,
                "order_cpu": 0.05,
                "order_mem": 78.4,
                "payment_request_rate": 4.9,
                "payment_error_rate": 0.0,
                "payment_p95_latency": 8.1,
                "payment_cpu": 0.04,
                "payment_mem": 82.0,
                "db_query_latency_p95": 1.9,
                "db_connection_count": 5.0,
            }
        }
    }


class CandidateProbability(BaseModel):
    fault_type: str
    probability: float


class EvidenceDetails(BaseModel):
    key_metrics: List[str]
    model_version: str


class PredictionResponse(BaseModel):
    predicted_root_cause: str
    confidence: float
    top3_candidates: List[CandidateProbability]
    evidence: EvidenceDetails
    low_confidence_warning: bool = False


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    model_loaded: bool
    model_path: str
