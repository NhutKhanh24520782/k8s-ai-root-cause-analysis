import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app.config import settings
from app.predictor import ServicePredictor
from app.schemas import HealthResponse, MetricSnapshotRequest, PredictionResponse

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rca-api")

# =============================================================================
# Prometheus Metrics (aligned with monitoring/grafana-dashboards/rca-model-monitoring.json)
# =============================================================================
INFERENCE_REQUESTS = Counter(
    "rca_inference_requests_total",
    "Total number of RCA inference requests received",
    ["service"],
)

INFERENCE_LATENCY = Histogram(
    "rca_inference_duration_seconds",
    "Time spent executing RCA model inference in seconds",
    ["service"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0, 2.5],
)

MODEL_ERRORS = Counter(
    "rca_model_errors_total",
    "Total count of model execution or inference errors",
    ["service"],
)

PREDICTIONS_TOTAL = Counter(
    "rca_predictions_total",
    "Total count of predictions made per root cause category",
    ["root_cause", "service"],
)

PREDICTION_CONFIDENCE = Gauge(
    "rca_prediction_confidence",
    "Latest model prediction confidence score [0.0 - 1.0]",
    ["service"],
)

# Global model predictor instance
predictor: ServicePredictor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global predictor
    logger.info("Starting up %s v%s...", settings.APP_NAME, settings.APP_VERSION)
    predictor = ServicePredictor()
    yield
    logger.info("Shutting down %s...", settings.APP_NAME)


app = FastAPI(
    title="AI Root Cause Analysis (RCA) API",
    description="Serves ML-powered root cause diagnoses for Kubernetes microservice incidents.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Enable CORS for frontend / developer dashboard queries
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["Monitoring"])
async def health_check():
    """Health & Readiness probe endpoint for Kubernetes."""
    is_ready = predictor is not None and predictor.is_loaded
    return HealthResponse(
        status="healthy" if is_ready else "degraded",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        model_loaded=is_ready,
        model_path=settings.MODEL_DIR,
    )


@app.get("/metrics", tags=["Monitoring"])
def metrics():
    """Exposes Prometheus metrics for scraping."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict", response_model=PredictionResponse, tags=["Inference"])
async def predict_root_cause(snapshot: MetricSnapshotRequest):
    """Diagnoses likely root cause from an observability metrics snapshot."""
    INFERENCE_REQUESTS.labels(service="rca-api").inc()
    start_time = time.perf_counter()

    if predictor is None or not predictor.is_loaded:
        MODEL_ERRORS.labels(service="rca-api").inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RCA Model is not available. Ensure models are trained and present in model directory.",
        )

    try:
        raw_dict = snapshot.model_dump()
        result = predictor.predict(raw_dict)

        root_cause = result["predicted_root_cause"]
        confidence = result["confidence"]

        # Record metrics for Grafana dashboard
        PREDICTIONS_TOTAL.labels(root_cause=root_cause, service="rca-api").inc()
        PREDICTION_CONFIDENCE.labels(service="rca-api").set(confidence)

        duration = time.perf_counter() - start_time
        INFERENCE_LATENCY.labels(service="rca-api").observe(duration)

        return PredictionResponse(**result)

    except Exception as exc:
        MODEL_ERRORS.labels(service="rca-api").inc()
        logger.exception("Inference failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference error: {str(exc)}",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
