# kubernetes/namespaces/

> **Status:** ✅ `namespaces.yaml` implemented — Step A1.3

---

## Purpose

This directory contains the Kubernetes `Namespace` manifests that create the logical isolation boundaries for all workloads in the AI Root Cause Analysis project.

Namespaces allow:
- **Workload isolation** — pods in different namespaces cannot accidentally communicate unless explicitly allowed.
- **RBAC scoping** — `Role` and `RoleBinding` objects are namespace-scoped, enabling fine-grained access control per team/component.
- **Resource quota** — `LimitRange` and `ResourceQuota` can be applied per namespace to prevent any one group of pods from starving others (future phase).

---

## Namespaces Created

| Namespace | Workloads | Purpose |
|-----------|-----------|---------|
| `microservices` | API Gateway, Order Service, Payment Service | Hosts the three core application microservices |
| `monitoring` | Prometheus, Grafana | Hosts the observability stack (deployed via `kube-prometheus-stack` Helm chart) |
| `ml-stack` | MLflow Tracking Server, RCA FastAPI | Hosts the machine-learning inference and experiment-tracking components |

---

## File

| File | Description |
|------|-------------|
| `namespaces.yaml` | Single multi-document YAML defining all three `Namespace` objects |

---

## Apply

```bash
# Apply all three namespaces to the cluster
kubectl apply -f kubernetes/namespaces/namespaces.yaml

# Verify namespaces were created
kubectl get namespaces -l project=ai-rca

# Inspect a specific namespace
kubectl describe namespace microservices
kubectl describe namespace monitoring
kubectl describe namespace ml-stack
```

Expected output after `kubectl get namespaces -l project=ai-rca`:

```
NAME             STATUS   AGE
microservices    Active   Xs
ml-stack         Active   Xs
monitoring       Active   Xs
```

---

## Labels & Annotations

Every namespace carries the following metadata:

| Key | Value | Reason |
|-----|-------|--------|
| `project` | `ai-rca` | Selects all resources belonging to this project |
| `env` | `dev` | Environment tag (change to `staging`/`prod` for later phases) |
| `managed-by` | `kubectl` | Signals that this resource is managed manually (not by Helm or Flux) |
| `annotation: description` | Human-readable purpose | Onboarding clarity for new team members |

---

## RBAC (Future — Step A1.3 continuation)

Namespace-scoped `Role` and `RoleBinding` objects will be added in subsequent steps. Planned bindings:

| Namespace | Role | Bound To |
|-----------|------|----------|
| `microservices` | `deploy-role` | Jenkins service account |
| `monitoring` | `view` (built-in) | Read-only observability access |
| `ml-stack` | `deploy-role` | Jenkins service account |

---

## Prerequisites

- EKS cluster must be running and `kubectl` must be configured with the correct context:

```bash
# Verify cluster connection and node health
kubectl get nodes

# Verify current context
kubectl config current-context
```

Both cluster nodes should show `Ready` status before applying manifests.
