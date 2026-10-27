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

# Deploy database and microservices

## Activate environment

```bash
export KUBECONFIG=~/.kube/config_NT548 # change the path to where you want to store
export AWS_PROFILE=NT548
export ECR_REGISTRY=274118253913.dkr.ecr.ap-southeast-1.amazonaws.com
export AWS_REGION=ap-southeast-1
export NAME_SPACE=microservices

aws eks update-kubeconfig --region ap-southeast-1 --name ai-rca-dev-cluster --kubeconfig $KUBECONFIG
```

Go to kubernetes/example and copy to kubernetes/credential
```bash
cp -r kubernetes/example kubernetes/credentials
```

## Secret

### Create secret

```bash
kubectl get storageclass --kubeconfig $KUBECONFIG

kubectl create secret generic order-db-secret \
  --kubeconfig $KUBECONFIG \
  --namespace $NAME_SPACE \
  --from-literal=POSTGRES_HOST=order-db \
  --from-literal=POSTGRES_PORT=5432 \
  --from-literal=POSTGRES_DB=orders_db \
  --from-literal=POSTGRES_USER=order_user \
  --from-literal=POSTGRES_PASSWORD="$(sed -n 's/^ORDER_DB_PASSWORD=//p' kubernetes/credentials)" \
  --dry-run=client -o yaml | \
  kubectl apply -f - --kubeconfig $KUBECONFIG

kubectl create secret generic payment-db-secret \
  --kubeconfig $KUBECONFIG \
  --namespace $NAME_SPACE \
  --from-literal=POSTGRES_HOST=payment-db \
  --from-literal=POSTGRES_PORT=5432 \
  --from-literal=POSTGRES_DB=payment_db \
  --from-literal=POSTGRES_USER=payment_user \
  --from-literal=POSTGRES_PASSWORD="$(sed -n 's/^PAYMENT_DB_PASSWORD=//p' kubernetes/credentials)" \
  --dry-run=client -o yaml | \
  kubectl apply -f - --kubeconfig $KUBECONFIG
```

### Check secrets

```bash
kubectl get secrets -n $NAME_SPACE --kubeconfig $KUBECONFIG

kubectl get secret order-db-secret \
  -n $NAME_SPACE \
  --kubeconfig $KUBECONFIG

kubectl describe secret order-db-secret \
  -n $NAME_SPACE \
  --kubeconfig $KUBECONFIG

kubectl get secret payment-db-secret \
  -n $NAME_SPACE \
  --kubeconfig $KUBECONFIG

kubectl describe secret payment-db-secret \
  -n $NAME_SPACE \
  --kubeconfig $KUBECONFIG
```

## Postgres

### Deploy PostgreSQL

```bash
kubectl apply -f kubernetes/postgres/order_db/service.yaml --kubeconfig $KUBECONFIG
kubectl apply -f kubernetes/postgres/order_db/statefulset.yaml --kubeconfig $KUBECONFIG

kubectl apply -f kubernetes/postgres/payment_db/service.yaml --kubeconfig $KUBECONFIG
kubectl apply -f kubernetes/postgres/payment_db/statefulset.yaml --kubeconfig $KUBECONFIG
```

### Check Postgres

```bash
kubectl get statefulset,pod,pvc,svc -n $NAME_SPACE --kubeconfig $KUBECONFIG
```

### Check database log

```bash
kubectl logs order-db-0 -n $NAME_SPACE --kubeconfig $KUBECONFIG
kubectl logs payment-db-0 -n $NAME_SPACE --kubeconfig $KUBECONFIG
```

### If pods do not ready

```bash
kubectl describe pod order-db-0 -n $NAME_SPACE --kubeconfig $KUBECONFIG
kubectl describe pod payment-db-0 -n $NAME_SPACE --kubeconfig $KUBECONFIG
kubectl get events -n $NAME_SPACE --sort-by=.lastTimestamp --kubeconfig $KUBECONFIG
```

```bash
kubectl get statefulset order-db payment-db -n $NAME_SPACE --kubeconfig $KUBECONFIG \
  -o jsonpath='{range .items[*]}{.metadata.name}{": "}{.spec.volumeClaimTemplates[0].spec.storageClassName}{"\n"}{end}'
```

## Microservices

### Deploy

```bash
export ECR_REGISTRY="$(sed -n 's/^ECR_REGISTRY=//p' kubernetes/credentials)"

envsubst '${ECR_REGISTRY}' < kubernetes/microservices/order-service/deployment.yaml |
  kubectl apply -f - --kubeconfig $KUBECONFIG

envsubst '${ECR_REGISTRY}' < kubernetes/microservices/payment-service/deployment.yaml |
  kubectl apply -f - --kubeconfig $KUBECONFIG

envsubst '${ECR_REGISTRY}' < kubernetes/microservices/api-gateway/deployment.yaml |
  kubectl apply -f - --kubeconfig $KUBECONFIG
```

### Check for errors

```bash
kubectl logs deployment/order-service \
  -n $NAMESPACE \
  --kubeconfig $KUBECONFIG \
  --tail=50

kubectl logs deployment/payment-service \
  -n $NAMESPACE \
  --kubeconfig $KUBECONFIG \
  --tail=50
```

### Check all pods

```bash
kubectl get statefulset,pod,pvc,svc -n $NAMESPACE --kubeconfig $KUBECONFIG

kubectl describe deployment order-service \
  -n $NAMESPACE \
  --kubeconfig $KUBECONFIG

kubectl describe deployment payment-service \
  -n $NAMESPACE \
  --kubeconfig $KUBECONFIG
```

### Apply services

```bash
kubectl apply -f kubernetes/microservices/api-gateway/service.yaml --kubeconfig $KUBECONFIG
kubectl apply -f kubernetes/microservices/order-service/service.yaml --kubeconfig $KUBECONFIG
kubectl apply -f kubernetes/microservices/payment-service/service.yaml --kubeconfig $KUBECONFIG
```

## Delete

### Delete secret

```bash
kubectl delete secret order-db-secret \
  -n $NAMESPACE \
  --kubeconfig $KUBECONFIG

kubectl delete secret payment-db-secret \
  -n $NAMESPACE \
  --kubeconfig $KUBECONFIG
```

### Delete service pod

```bash
kubectl delete deployment payment-service \
  -n $NAMESPACE \
  --kubeconfig $KUBECONFIG

kubectl delete deployment order-service \
  -n $NAMESPACE \
  --kubeconfig $KUBECONFIG
```

### Delete namespace

```bash
kubectl delete namespace $NAMESPACE
```
