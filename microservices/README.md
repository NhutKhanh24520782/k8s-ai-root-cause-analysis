# Microservices

This directory contains the application services used to generate realistic workload, observability signals, and failure scenarios for the Kubernetes root-cause analysis project.

The services are intentionally lightweight and designed to be easy to deploy and monitor. They simulate real microservice behavior, expose metrics for Prometheus, and interact with PostgreSQL so the platform can generate training data for RCA and ML-based diagnosis.

---

## Purpose

The microservices in this project exist to:

- generate HTTP traffic against Kubernetes workloads,
- produce structured logs and metrics for Prometheus/Grafana,
- simulate service-to-service communication,
- model failure patterns such as latency spikes and payment errors,
- provide a realistic environment for incident analysis and root-cause prediction.

This directory is not intended to be a production-grade distributed system. It is a small benchmark-style application used for research and learning.

---

## Service Architecture

```text
Internet
  ↓
ALB / Ingress
  ↓
API Gateway
  ├── Order Service ──> PostgreSQL (order)
  └── Payment Service ──> PostgreSQL (payment)
```

### Services

| Service | Responsibility |
|---------|----------------|
| API Gateway | Entry point for external traffic. Routes requests to the downstream services and exposes `/metrics`. |
| Order Service | Handles order creation and retrieval. Connects to PostgreSQL and exposes metrics. |
| Payment Service | Simulates payment processing and can fail under controlled conditions for fault injection scenarios. |
| PostgreSQL | Persistent database dependency for the application. Used by the order flow and optionally by payment-related logic. |

---

## Communication Model

- Services communicate over HTTP using Kubernetes service DNS.
- Internal requests should use names such as:
  - `http://order-service.<namespace>.svc.cluster.local`
  - `http://payment-service.<namespace>.svc.cluster.local`
  - `http://api-gateway.<namespace>.svc.cluster.local`
- The system uses a simple Kubernetes service model and does not require a service mesh.
- Prometheus scrapes metrics by exposing a `/metrics` endpoint in each service.

---

## Required Metrics

Each service should expose Prometheus-compatible metrics, especially:

| Metric | Type | Purpose |
|--------|------|---------|
| `http_requests_total` | Counter | Number of requests, labelled by path and status code |
| `http_request_duration_seconds` | Histogram | Request latency distribution |
| `http_requests_in_flight` | Gauge | Number of requests currently being processed |

These metrics are essential for RCA training data and Grafana dashboards.

---

## Directory Structure

```text
microservices/
├── api-gateway/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── order-service/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── payment-service/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── docker-compose.yml
├── docker-compose.ecr.yml
├── README.md
└── test_script.sh
```

---

## Local Development

Use Docker Compose for local development and testing before pushing images to ECR.

### Start the stack locally

```bash
docker compose up --build
```

### Stop the stack

```bash
docker compose down
```

### Check service health

```bash
docker compose ps
```

### View logs

```bash
docker compose logs -f
```

---

## Docker and ECR Workflow

### Set up environment
```bash
export ECR_REGISTRY=274118253913.dkr.ecr.ap-southeast-1.amazonaws.com
export AWS_REGION=ap-southeast-1
```
Before pushing images to AWS ECR, authenticate Docker with the target registry.

### Login to ECR

```bash
aws ecr get-login-password --region "$AWS_REGION" |
  docker login \
    --username AWS \
    --password-stdin "$ECR_REGISTRY"
```

### Validate compose configuration

```bash
docker compose -f microservices/docker-compose.ecr.yml config
```

### Build images

```bash
docker compose -f microservices/docker-compose.ecr.yml build order-service payment-service api-gateway
```

### Push images to ECR

```bash
docker compose -f microservices/docker-compose.ecr.yml push order-service payment-service api-gateway
```

---

## Notes for Deployment

- Use a dedicated ECR repository per service or a naming strategy consistent with the project.
- Keep the runtime image lightweight, preferably using Python slim images.
- Tag images with the Git SHA or a stable environment tag before pushing.
- In Kubernetes, inject environment variables and database credentials through ConfigMaps and Secrets rather than hardcoding them into the image.

---

## Current Status

This directory is the service layer for the application. The project is in active deployment and observability setup, and the microservices are expected to be containerized and deployed into the EKS cluster as part of the Kubernetes rollout.

The repository currently includes the service structure, Docker Compose definitions, and the image build/publish commands needed for deployment to ECR and Kubernetes.

---

## Useful Commands Summary

```bash
# Local run

export ECR_REGISTRY=274118253913.dkr.ecr.ap-southeast-1.amazonaws.com
export AWS_REGION=ap-southeast-1

docker compose up --build

docker compose logs -f

docker compose down

# ECR login
aws ecr get-login-password --region "$AWS_REGION" |
  docker login \
    --username AWS \
    --password-stdin "$ECR_REGISTRY"

# Build and push

docker compose -f microservices/docker-compose.ecr.yml build order-service payment-service api-gateway
docker compose -f microservices/docker-compose.ecr.yml push order-service payment-service api-gateway
```
