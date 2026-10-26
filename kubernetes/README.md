# kubernetes/

> **Status:** 🚧 In progress — Step A1.3 (Namespace & RBAC) ✅ complete.  
> Deployment and Service manifests will follow in Phase 5.

---

## Purpose

This directory will contain the Kubernetes application manifests that deploy the microservices, monitoring stack components, and the RCA API onto the Amazon EKS cluster provisioned by Terraform.

Kubernetes manifests are **application workload configuration** and are separate from AWS infrastructure (which lives in `terraform/`). Terraform creates the EKS cluster; this directory defines what runs inside it.

---

## Planned Kubernetes Resources

For each microservice and the RCA API, the following resource types will be created:

| Resource | Purpose |
|----------|---------|
| `Namespace` | Isolate workloads (e.g., `rca-system`, `monitoring`) |
| `Deployment` | Declare desired Pod replicas, image, resource limits |
| `Service` | Stable DNS name and cluster-internal load balancing |
| `ConfigMap` | Non-sensitive runtime configuration (environment variables, config files) |
| `Secret` | Sensitive values (database passwords, API tokens) — see the secrets note below |
| `Ingress` | Route external HTTP traffic through the AWS Load Balancer Controller |
| `HorizontalPodAutoscaler` | (Optional) Auto-scale Pods based on CPU/memory during load tests |

The Prometheus and Grafana manifests will be managed by Helm (`kube-prometheus-stack`); their configuration files live in `monitoring/`.

---

## Secrets Handling

**Never commit plaintext secrets to Git.**

The planned approach for managing secrets in the MVP:

1. Use Kubernetes `Secret` objects for values that Pods must access at runtime.
2. Populate secrets via `kubectl create secret` or a secure CI/CD step — not by committing YAML files containing real values.
3. `.gitignore` is configured to exclude `*.env` and `*.tfvars` files.
4. Consider AWS Secrets Manager integration in a later phase if the team has capacity.

---

## Inspection Commands

The following commands will be useful once manifests are applied:

```bash
# List all Pods in the rca-system namespace
kubectl get pods -n rca-system

# Describe a specific Pod (useful for debugging startup failures)
kubectl describe pod <pod-name> -n rca-system

# Tail logs from a running container
kubectl logs -f deployment/<deployment-name> -n rca-system

# Check rollout status
kubectl rollout status deployment/<deployment-name> -n rca-system

# Inspect a Service
kubectl get svc -n rca-system

# Get Ingress address (ALB DNS name)
kubectl get ingress -n rca-system
```

---

## Subdirectory Structure

```
kubernetes/
├── namespaces/                  ← ✅ Step A1.3 — Namespace definitions
│   ├── namespaces.yaml          ← microservices, monitoring, ml-stack
│   └── README.md
├── api-gateway/                 ← ⏳ Phase 5 — Deployment, Service, Ingress
├── order-service/               ← ⏳ Phase 5 — Deployment, Service
├── payment-service/             ← ⏳ Phase 5 — Deployment, Service
└── rca-api/                     ← ⏳ Phase 10 — FastAPI prediction service
```

Each subdirectory will contain the Deployment, Service, ConfigMap, and (where needed) Ingress manifests for that workload.

---

## Current Implementation Status

| Step | Resource | Status |
|------|----------|--------|
| A1.3 | `Namespace` — microservices, monitoring, ml-stack | ✅ Complete |
| Phase 5 | Deployments, Services, ConfigMaps, Ingress | ⏳ Not started |
| Phase 6 | kube-prometheus-stack (Helm) | ⏳ Not started |
| Phase 10 | RCA FastAPI Deployment | ⏳ Not started |

Apply namespaces:

```bash
kubectl apply -f kubernetes/namespaces/namespaces.yaml
kubectl get namespaces -l project=ai-rca
```
