# Build from the repository root, because the image needs code from both
# rca-api/ and ml/src/:
#     docker build -f rca-api/Dockerfile -t rca-api .
#
# The trained model is NOT baked into the image (see the root .dockerignore).
# Provide it at runtime in MODEL_DIR, for example with a volume:
#     docker run -p 8000:8000 -v "<repo>/ml/models:/models:ro" rca-api
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY rca-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# API code
COPY rca-api/main.py rca-api/schemas.py ./

# Inference code handed over by ML (ml/src/predict.py and its helper)
COPY ml/src/predict.py ml/src/feature_engineering.py ./ml/src/

ENV ML_SRC_DIR=/app/ml/src
ENV MODEL_DIR=/models

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
