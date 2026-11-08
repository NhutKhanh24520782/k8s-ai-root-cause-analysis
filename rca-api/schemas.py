"""
rca-api/schemas.py

Interface Contract 2: API Request and Response Schemas
Defined by: Đình Tân (Machine Learning)
Consumed by: Phước Thọ (RCA API FastAPI implementation)
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class MetricSnapshotRequest(BaseModel):
    """Telemetry snapshot request payload for root cause inference."""
    timestamp: Optional[str] = Field(default=None, description="ISO-8601 UTC timestamp")
    gw_request_rate: float = Field(..., ge=0.0, description="API Gateway request rate (req/s)")
    gw_error_rate: float = Field(..., ge=0.0, le=1.0, description="API Gateway 5xx error ratio")
    gw_p95_latency: float = Field(..., ge=0.0, description="API Gateway 95th percentile latency (ms)")
    order_request_rate: float = Field(..., ge=0.0, description="Order Service request rate (req/s)")
    order_error_rate: float = Field(..., ge=0.0, le=1.0, description="Order Service 5xx error ratio")
    order_p95_latency: float = Field(..., ge=0.0, description="Order Service 95th percentile latency (ms)")
    order_cpu: float = Field(..., ge=0.0, description="Order Service CPU usage")
    order_mem: float = Field(..., ge=0.0, description="Order Service memory working set (MB)")
    payment_request_rate: float = Field(..., ge=0.0, description="Payment Service request rate (req/s)")
    payment_error_rate: float = Field(..., ge=0.0, le=1.0, description="Payment Service 5xx error ratio")
    payment_p95_latency: float = Field(..., ge=0.0, description="Payment Service 95th percentile latency (ms)")
    payment_cpu: float = Field(..., ge=0.0, description="Payment Service CPU usage")
    payment_mem: float = Field(..., ge=0.0, description="Payment Service memory working set (MB)")
    db_query_latency_p95: float = Field(..., ge=0.0, description="Database p95 query latency (ms)")
    db_connection_count: float = Field(..., ge=0.0, description="Active database connection pool count")

    model_config = {
        "json_schema_extra": {
            "example": {
                "timestamp": "2026-10-30T10:00:00Z",
                "gw_request_rate": 12.5,
                "gw_error_rate": 0.03,
                "gw_p95_latency": 150.0,
                "order_request_rate": 12.0,
                "order_error_rate": 0.01,
                "order_p95_latency": 1.2,
                "order_cpu": 0.25,
                "order_mem": 85.0,
                "payment_request_rate": 12.0,
                "payment_error_rate": 0.0,
                "payment_p95_latency": 2.5,
                "payment_cpu": 0.15,
                "payment_mem": 70.0,
                "db_query_latency_p95": 1.1,
                "db_connection_count": 5.0,
            }
        }
    }


class CandidateProbability(BaseModel):
    fault_type: str = Field(..., description="Hypothesized root cause class")
    probability: float = Field(..., ge=0.0, le=1.0, description="Confidence probability (0.0 to 1.0)")


class InferenceEvidence(BaseModel):
    key_metrics: List[str] = Field(..., description="Metrics indicating anomalous behavior")
    model_version: str = Field(default="1", description="Model version or MLflow run identifier")


class RootCausePredictionResponse(BaseModel):
    predicted_root_cause: str = Field(..., description="Primary predicted root cause category")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score of prediction")
    top3_candidates: List[CandidateProbability] = Field(..., description="Top 3 ranked potential causes")
    evidence: InferenceEvidence = Field(..., description="Diagnostic evidence and metadata")

    model_config = {
        "json_schema_extra": {
            "example": {
                "predicted_root_cause": "db_slowness",
                "confidence": 0.87,
                "top3_candidates": [
                    {"fault_type": "db_slowness", "probability": 0.87},
                    {"fault_type": "cpu_stress", "probability": 0.08},
                    {"fault_type": "normal", "probability": 0.05},
                ],
                "evidence": {
                    "key_metrics": ["db_query_latency_p95", "order_p95_latency"],
                    "model_version": "1",
                },
            }
        }
    }


class HealthCheckResponse(BaseModel):
    status: str = Field(default="ok", description="Service health state")
    model_version: str = Field(default="v1", description="Loaded model version")
