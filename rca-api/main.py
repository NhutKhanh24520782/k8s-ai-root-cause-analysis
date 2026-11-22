"""
rca-api/main.py
Endpoints:
    GET  /health   -> is the service up, and which model version is loaded
    POST /predict  -> metrics snapshot in, predicted root cause out
    GET  /metrics  -> Prometheus metrics about the API itself

Run locally (from the rca-api/ directory, after training a model):
    uvicorn main:app --port 8000
"""

import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from schemas import (
    HealthCheckResponse,
    MetricSnapshotRequest,
    RootCausePredictionResponse,
)

# Where the inference code and the trained model live. The defaults work when
# running from a clone of the repo; the Docker image overrides them with env vars.
REPO_ROOT = Path(__file__).resolve().parent.parent
ML_SRC_DIR = os.getenv("ML_SRC_DIR", str(REPO_ROOT / "ml" / "src"))
MODEL_DIR = os.getenv("MODEL_DIR", str(REPO_ROOT / "ml" / "models"))
MODEL_VERSION = os.getenv("MODEL_VERSION", "1")

# Reuse the inference module handed over by ML (ml/src/predict.py).
sys.path.insert(0, ML_SRC_DIR)
from predict import RCAPredictor  # noqa: E402

# Metric names match the queries in
# monitoring/grafana-dashboards/rca-model-monitoring.json
INFERENCE_REQUESTS = Counter(
    "rca_inference_requests_total",
    "Total number of /predict requests received",
)
INFERENCE_DURATION = Histogram(
    "rca_inference_duration_seconds",
    "Time spent running model inference, in seconds",
)
MODEL_ERRORS = Counter(
    "rca_model_errors_total",
    "Total number of /predict requests that failed inside the model",
)
PREDICTIONS = Counter(
    "rca_predictions_total",
    "Total number of predictions, by predicted root cause",
    ["root_cause"],
)
PREDICTION_CONFIDENCE = Gauge(
    "rca_prediction_confidence",
    "Confidence of the most recent prediction (0.0 to 1.0)",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the model once at startup and keep it in memory. If the model files
    # are missing the service refuses to start, which is what we want.
    app.state.predictor = RCAPredictor(model_dir=MODEL_DIR)
    yield


app = FastAPI(title="RCA API", lifespan=lifespan)


@app.get("/health", response_model=HealthCheckResponse)
def health():
    return HealthCheckResponse(status="ok", model_version=MODEL_VERSION)


@app.post("/predict", response_model=RootCausePredictionResponse)
def predict(snapshot: MetricSnapshotRequest, request: Request):
    INFERENCE_REQUESTS.inc()
    started = time.perf_counter()

    try:
        result = request.app.state.predictor.predict(snapshot.model_dump())
    except Exception as exc:
        MODEL_ERRORS.inc()
        raise HTTPException(status_code=500, detail="Model inference failed") from exc
    finally:
        INFERENCE_DURATION.observe(time.perf_counter() - started)

    result["evidence"]["model_version"] = MODEL_VERSION
    PREDICTIONS.labels(root_cause=result["predicted_root_cause"]).inc()
    PREDICTION_CONFIDENCE.set(result["confidence"])
    return result


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
