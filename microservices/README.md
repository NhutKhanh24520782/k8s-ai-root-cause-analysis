# services/

> **Status:** No microservice source code has been implemented yet.  
> This README documents what will be built and why.

---

## Purpose

This directory will contain the source code for the microservices that form the sample application used to generate incident data and demonstrate root-cause analysis.

The application is intentionally minimal. Its primary function within this project is to produce realistic, observable workloads on Kubernetes so that Prometheus can collect the metrics needed for ML training and RCA prediction.

---

## Planned Microservices

| Service | Responsibility |
|---------|---------------|
| **API Gateway** | Single entry point for external traffic. Routes requests to Order Service and Payment Service. Exposes `/metrics` for Prometheus. |
| **Order Service** | Simulates order creation and retrieval. Introduces realistic database interaction patterns (and simulated slowness during incidents). Exposes `/metrics`. |
| **Payment Service** | Simulates payment processing. Can be configured to return errors during payment-failure incident runs. Exposes `/metrics`. |

**PostgreSQL** is a data dependency for Order Service (and optionally Payment Service). It is not a microservice that this team maintains; it will be deployed as a Kubernetes StatefulSet or managed through a Helm chart.

---

## Service Communication

```
Internet → ALB (Ingress) → API Gateway → Order Service
                                       → Payment Service
```

- All internal communication uses Kubernetes DNS (`http://<service-name>.<namespace>.svc.cluster.local`).
- Services use HTTP (not gRPC) in the MVP to keep implementation complexity low.
- There is no service mesh in the MVP.

---

## Required Application Metrics

Each service must expose a Prometheus-compatible `/metrics` endpoint. The following metric types are required for the ML training dataset:

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Total HTTP requests, labelled by status code and handler |
| `http_request_duration_seconds` | Histogram | Request latency distribution |
| `http_requests_in_flight` | Gauge | Currently active requests |

Standard Kubernetes node and Pod metrics (CPU, memory, Pod restarts) will be collected automatically by `kube-prometheus-stack`; services do not need to expose these themselves.

When implementing, use the [Prometheus Python client](https://github.com/prometheus/client_python) (for Python services) or the appropriate client library for the chosen language.

---

## Docker Image Conventions

When Dockerfiles are added:

- Each service will have its own `Dockerfile` inside its subdirectory.
- Base images must be official, minimal images (e.g., `python:3.11-slim`).
- Images will be tagged with the Git short SHA and pushed to Amazon ECR.
- Multi-stage builds should be used to exclude development dependencies from the runtime image.

---

## Planned Subdirectory Structure

The following structure will be created when implementation begins. It is **not created now** because no source files exist yet.

```
services/
├── api-gateway/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── order-service/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
└── payment-service/
    ├── Dockerfile
    ├── main.py
    └── requirements.txt
```

---

## Current Implementation Status

No source code, Dockerfiles, or configuration files exist in this directory yet. Implementation begins in **Phase 4** of the project roadmap (see root `README.md`).
