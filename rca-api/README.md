# rca-api/

FastAPI service that receives a snapshot of microservice metrics and returns
the predicted root cause of an incident (phase B2, owner: Phước Thọ — TV4).

It reuses the inference code handed over by ML (`ml/src/predict.py`) and the
request/response contract in `schemas.py` (Interface Contract 2, defined by
Đình Tân). See `docs/handover_b1_to_b2.md`.

## Files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app: the 3 endpoints below, loads the model once at startup |
| `schemas.py` | Pydantic request/response models (owned by ML, do not change alone) |
| `requirements.txt` | Runtime dependencies (installed in the Docker image) |
| `requirements-dev.txt` | Runtime + test dependencies (`pytest`, `httpx`) |
| `tests/test_api.py` | API tests, run against the real trained model |
| `Dockerfile` | Image definition; build it from the **repository root** |

Kubernetes manifests: `kubernetes/ml-stack/rca-api/`.

## Endpoints

| Method | Path | Returns |
|---|---|---|
| `GET` | `/health` | `{"status": "ok", "model_version": "1"}` |
| `POST` | `/predict` | Predicted root cause, confidence, top 3 candidates, evidence |
| `GET` | `/metrics` | Prometheus metrics of the API itself |

`POST /predict` takes the 15 metrics defined in `MetricSnapshotRequest`
(`gw_*`, `order_*`, `payment_*`, `db_*`). A request with a missing or
out-of-range field returns `422`.

Metrics exposed on `/metrics` (used by
`monitoring/grafana-dashboards/rca-model-monitoring.json`):
`rca_inference_requests_total`, `rca_inference_duration_seconds`,
`rca_model_errors_total`, `rca_predictions_total{root_cause}`,
`rca_prediction_confidence`.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `MODEL_DIR` | `<repo>/ml/models` (`/models` in the image) | Folder with `rca_random_forest.joblib`, `label_encoder.joblib`, `feature_names.json` |
| `ML_SRC_DIR` | `<repo>/ml/src` (`/app/ml/src` in the image) | Where `predict.py` is imported from |
| `MODEL_VERSION` | `1` | Version string reported in `/health` and in each prediction |

## Where the model comes from

The model files are **not** in git (`ml/models/` is gitignored) and **not**
in the image (`.dockerignore`). Produce them first with `python ml/src/train.py`
(or get them from the ML owner), then provide them at runtime in `MODEL_DIR`.
If the files are missing, the service refuses to start.

Moving the model to S3 / the MLflow registry is planned (phase B2.2).

## Run locally

```bash
# from the repository root, with the model in ml/models/
pip install -r rca-api/requirements-dev.txt
cd rca-api
uvicorn main:app --port 8000        # http://localhost:8000/docs
python -m pytest -v                 # 4 tests
```

## Run with Docker

```bash
# from the repository root
docker build -f rca-api/Dockerfile -t rca-api .
docker run -p 8000:8000 -v "$(pwd)/ml/models:/models:ro" rca-api
```

## Deploy on Kubernetes (manual, for now)

```bash
kubectl create configmap rca-model -n ml-stack \
  --from-file=ml/models/rca_random_forest.joblib \
  --from-file=ml/models/label_encoder.joblib \
  --from-file=ml/models/feature_names.json
# replace REGISTRY in the image name with the ECR registry first
kubectl apply -f kubernetes/ml-stack/rca-api/
```

Not yet wired into the GitOps flow (`kubernetes/base/` + ArgoCD on
`feat/gitops`); that is the next step.
