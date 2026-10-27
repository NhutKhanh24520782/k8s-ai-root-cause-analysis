# monitoring/

> **Status:** No monitoring configuration files have been created yet.  
> This README documents the planned observability stack and its purpose.

---

## Purpose

This directory will contain the Helm values files and configuration for the observability stack: **Prometheus** for metric collection and **Grafana** for visualisation.

Observability is a prerequisite for the ML training data pipeline. Prometheus scrapes service metrics during controlled incident runs; those metric snapshots are then labeled and used to train the root-cause classifier.

---

## Planned Stack

| Component | Role |
|-----------|------|
| **Prometheus** | Scrapes `/metrics` endpoints from all microservices and Kubernetes node/Pod metrics. Stores time-series data. |
| **Grafana** | Visualises Prometheus metrics through dashboards. Used during development to inspect incident patterns and validate data quality. |
| `kube-prometheus-stack` | Helm chart that bundles Prometheus Operator, Prometheus, Grafana, Alertmanager, and default Kubernetes dashboards. |

**Out of scope for the MVP:** Loki (log aggregation), Tempo or Jaeger (distributed tracing), and OpenTelemetry Collector. These may be added in a later phase.

---

## Required Metrics

The following metrics must be collected during incident runs to produce the ML training dataset:

| Metric | Source |
|--------|--------|
| `http_requests_total` (by status code) | Application `/metrics` endpoint |
| `http_request_duration_seconds` (histogram) | Application `/metrics` endpoint |
| `container_cpu_usage_seconds_total` | `kubelet` / `node-exporter` |
| `container_memory_working_set_bytes` | `kubelet` |
| `kube_pod_container_status_restarts_total` | `kube-state-metrics` |

These are the raw Prometheus metrics. Feature engineering (e.g., rate calculations, windowed aggregations) is performed in the `ml/` pipeline.

---

## Application Instrumentation Requirements

Each microservice must expose a Prometheus-compatible `/metrics` endpoint. Refer to `services/README.md` for the required metric list and the recommended Python client library.

Services must also have appropriate Kubernetes annotations so that the Prometheus Operator's `ServiceMonitor` can discover them automatically:

```yaml
metadata:
  labels:
    # This label selector must match the ServiceMonitor selector
    prometheus-scrape: "true"
```

The exact label and `ServiceMonitor` configuration will be defined when Kubernetes manifests are written.

---

## Planned Installation Approach

Prometheus and Grafana will be installed into the EKS cluster using Helm:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --values monitoring/values-kube-prometheus-stack.yaml
```

A `values-kube-prometheus-stack.yaml` file will be created in this directory to configure:
- Grafana admin credentials (via Kubernetes Secret, not hardcoded in the values file).
- Persistent storage for Prometheus using the EBS CSI Driver.
- `ServiceMonitor` selectors for the microservices.

---

## Verification Steps

Once installed, verify the stack with:

```bash
# Check all Pods in the monitoring namespace are Running
kubectl get pods -n monitoring

# Port-forward Grafana to your local machine
kubectl port-forward svc/kube-prometheus-stack-grafana 3000:80 -n monitoring
# Then open http://localhost:3000 in a browser

# Port-forward Prometheus
kubectl port-forward svc/kube-prometheus-stack-prometheus 9090:9090 -n monitoring
# Then open http://localhost:9090 → Status → Targets
```

All application services should appear as active Prometheus scrape targets.

---

## Planned Subdirectory Structure

The following file will be created when implementation begins. It is **not created now** because no configuration exists yet.

```
monitoring/
└── values-kube-prometheus-stack.yaml
```

Grafana dashboard JSON exports may be stored here as well when they are ready.

---

## Current Implementation Status

No Helm values files or configuration exist yet. Implementation begins in **Phase 6** of the project roadmap (see root `README.md`).

# Kubernetes Monitoring

## 1. Overview

This directory contains the monitoring configuration for the **Kubernetes AI Root Cause Analysis (AI-RCA)** project.

The monitoring stack collects metrics from the application microservices, provides dashboards for observability, and establishes the foundation for analyzing application failures and performance degradation.

### Technology Stack

| Component | Purpose |
|---|---|
| Kubernetes / Amazon EKS | Container orchestration |
| Helm | Monitoring stack deployment |
| kube-prometheus-stack | Prometheus, Grafana, Alertmanager, and supporting components |
| Prometheus | Metrics collection and time-series storage |
| Grafana | Metrics visualization and dashboards |
| ServiceMonitor | Prometheus scrape configuration for Kubernetes Services |
| FastAPI | Application framework used by the microservices |
| prometheus-client | Exposes application metrics |

### Architecture

```text
                         Amazon EKS Cluster
                                  |
              +-------------------+-------------------+
              |                                       |
       monitoring namespace                   microservices namespace
              |                                       |
    +---------+----------+                 +----------+----------+
    |                    |                 |          |          |
 Prometheus           Grafana          API Gateway  Order      Payment
    |                    |              :8000        Service    Service
    |                    |                           :8001      :8002
    |                    |                              |          |
    |                    |                              +----+-----+
    |                    |                                   |
    |                    |                           /metrics endpoints
    |                    |
    +---- ServiceMonitor resources
                 |
          Scrape every 15s
```

Prometheus discovers the application endpoints through `ServiceMonitor` resources. Each monitored service exposes a `/metrics` endpoint.

Grafana queries Prometheus to visualize application health, request traffic, latency, and other available metrics.

---

## 2. Directory Structure

```text
monitoring/
├── README.md
├── helm-values/
│   └── kube-prometheus-stack-values.yaml
├── grafana-dashboards/
│   ├── microservices-overview.json
│   └── rca-model-monitoring.json
└── servicemonitors.yaml
```

File responsibilities:

| File | Description |
|---|---|
| `helm-values/kube-prometheus-stack-values.yaml` | Helm configuration for the monitoring stack |
| `servicemonitors.yaml` | ServiceMonitor definitions, if maintained separately from Helm values |
| `grafana-dashboards/microservices-overview.json` | Dashboard for microservice monitoring |
| `grafana-dashboards/rca-model-monitoring.json` | Dashboard for AI-RCA model metrics |

**Configuration note:** The project currently configures the three ServiceMonitors through `prometheus.additionalServiceMonitors` in the Helm values file. If this approach is retained, `servicemonitors.yaml` is optional and should not contain conflicting duplicate definitions.

---

## 3. Prerequisites

Before deploying the monitoring stack, ensure the following requirements are met:

- An accessible Amazon EKS cluster.
- `kubectl` configured for the target cluster.
- Helm installed.
- The `microservices` namespace exists.
- The three application Services are deployed and expose their metrics endpoints.

The commands below use the project's kubeconfig:

```bash
export KUBECONFIG="$HOME/.kube/config_NT548"
```

Verify the cluster connection:

```bash
kubectl cluster-info
kubectl get nodes
```

Verify the namespaces:

```bash
kubectl get namespaces
```

The relevant namespaces are:

- `monitoring`: monitoring infrastructure.
- `microservices`: application microservices.

Check the application Services:

```bash
kubectl get svc -n microservices
```

Expected services:

| Service | Port | Metrics endpoint |
|---|---:|---|
| `api-gateway` | 8000 | `/metrics` |
| `order-service` | 8001 | `/metrics` |
| `payment-service` | 8002 | `/metrics` |

The ServiceMonitor configuration uses the named Service port `http`, so each Service must define that port name correctly.

---

## 4. Deploy the Monitoring Stack

### 4.1 Create the Monitoring Namespace

```bash
kubectl create namespace monitoring \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 4.2 Add the Helm Repository

```bash
helm repo add prometheus-community \
  https://prometheus-community.github.io/helm-charts

helm repo update
```

### 4.3 Install or Upgrade kube-prometheus-stack

Deploy the monitoring stack using the project's Helm values:

```bash
helm upgrade --install kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  --version 92.14.0 \
  --namespace monitoring \
  --values monitoring/helm-values/kube-prometheus-stack-values.yaml
```

The command uses the chart version specified for this project. Remove or change the version only when intentionally upgrading the chart.

Verify the Helm release:

```bash
helm list -n monitoring
```

Check the deployed resources:

```bash
kubectl get pods -n monitoring
kubectl get svc -n monitoring
kubectl get servicemonitors -n monitoring
```

Wait for the monitoring pods to become ready:

```bash
kubectl wait \
  --for=condition=Ready pod \
  --all \
  -n monitoring \
  --timeout=300s
```

If a pod does not become ready, inspect its status and logs before proceeding.

---

## 5. Prometheus Configuration

### 5.1 Service Discovery

Prometheus uses `ServiceMonitor` resources to discover the application endpoints.

The configuration targets the following services:

| ServiceMonitor | Target Service | Namespace | Scrape Path | Interval |
|---|---|---|---|---|
| `api-gateway` | `api-gateway` | `microservices` | `/metrics` | 15s |
| `order-service` | `order-service` | `microservices` | `/metrics` | 15s |
| `payment-service` | `payment-service` | `microservices` | `/metrics` | 15s |

The ServiceMonitor configuration must satisfy these requirements:

- The ServiceMonitor resources are created in `monitoring`.
- Their `release` label matches the Helm release selector: `kube-prometheus-stack`.
- The namespace selector includes `microservices`.
- Each selector matches the corresponding Service's `app` label.
- Each endpoint uses the named Service port `http`.
- The scrape path is `/metrics`.
- The scrape interval is `15s`.
- The scrape timeout is `10s`.

### 5.2 Verify ServiceMonitor Resources

```bash
kubectl get servicemonitors -n monitoring
```

Inspect a specific ServiceMonitor:

```bash
kubectl get servicemonitor api-gateway \
  -n monitoring -o yaml
```

Repeat for `order-service` and `payment-service` as necessary.

Check the Service labels and named ports:

```bash
kubectl get svc api-gateway order-service payment-service \
  -n microservices --show-labels
```

Inspect a Service's port configuration:

```bash
kubectl get svc api-gateway \
  -n microservices -o yaml
```

### 5.3 Access Prometheus

Start port forwarding:

```bash
kubectl port-forward \
  -n monitoring \
  svc/kube-prometheus-stack-kube-prometheus \
  9090:9090
```

Open Prometheus in a browser:

```text
http://localhost:9090
```

To check whether the application targets are being scraped, execute this PromQL query:

```promql
up{namespace="microservices"}
```

To focus on the three application jobs:

```promql
up{
  job=~"api-gateway|order-service|payment-service"
}
```

A value of `1` indicates that Prometheus can scrape the target successfully. A value of `0` indicates that the target is known but currently cannot be scraped.

You can also inspect **Status → Targets** in the Prometheus interface to see target health and scrape errors.

---

## 6. Application Metrics

Each microservice should expose the following endpoints:

| Endpoint | Purpose |
|---|---|
| `/health` | Basic application health check |
| `/metrics` | Prometheus metrics endpoint |

The application must return metrics in the Prometheus exposition format.

### 6.1 HTTP Metrics

The main HTTP metrics used by the project are:

| Metric | Type | Purpose |
|---|---|---|
| `http_requests_total` | Counter | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | HTTP request duration |
| `http_requests_in_flight` | Gauge | Number of requests currently being processed |

The available labels depend on the application instrumentation. For example, the request counter may include `method`, `endpoint`, and `status_code`.

### 6.2 Verify Application Metrics

Check the API Gateway:

```bash
kubectl port-forward \
  -n microservices \
  svc/api-gateway 8000:8000
```

In another terminal:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/metrics
```

Check the Order Service:

```bash
kubectl port-forward \
  -n microservices \
  svc/order-service 8001:8001
```

```bash
curl -fsS http://localhost:8001/health
curl -fsS http://localhost:8001/metrics
```

Check the Payment Service:

```bash
kubectl port-forward \
  -n microservices \
  svc/payment-service 8002:8002
```

```bash
curl -fsS http://localhost:8002/health
curl -fsS http://localhost:8002/metrics
```

Run each port-forward command in a separate terminal, or stop the previous port-forward before reusing a local port.

---

## 7. Grafana

Grafana provides dashboards for inspecting application behavior and monitoring metrics collected by Prometheus.

### 7.1 Access Grafana

Start port forwarding:

```bash
kubectl port-forward \
  -n monitoring \
  svc/kube-prometheus-stack-grafana \
  3000:80
```

Open:

```text
http://localhost:3000
```

The default username configured for this deployment is:

```text
admin
```

Retrieve the password from the Grafana Secret:

```bash
kubectl get secret kube-prometheus-stack-grafana \
  -n monitoring \
  -o jsonpath='{.data.admin-password}' \
  --kubeconfig "$HOME/.kube/config_NT548" \
  | base64 --decode

echo
```

If the Secret name differs or the command returns an error, list the available Grafana Secrets:

```bash
kubectl get secrets -n monitoring \
  --kubeconfig "$HOME/.kube/config_NT548" \
  | grep -i grafana
```

Use the actual Secret name returned by the cluster. Do not commit passwords or other credentials to the repository.

### 7.2 Configure the Prometheus Data Source

The kube-prometheus-stack chart normally provisions a Prometheus data source for Grafana.

If the data source is not available, configure one using the in-cluster Prometheus service URL:

```text
http://kube-prometheus-stack-kube-prometheus.monitoring.svc:9090
```

Verify the actual Prometheus Service name with:

```bash
kubectl get svc -n monitoring
```

### 7.3 Import Dashboards

The project includes two dashboard definitions:

1. `grafana-dashboards/microservices-overview.json`
2. `grafana-dashboards/rca-model-monitoring.json`

To import a dashboard:

1. Open Grafana.
2. Navigate to **Dashboards**.
3. Select **New → Import**.
4. Upload the corresponding JSON file.
5. Select the Prometheus data source when prompted.
6. Import the dashboard.

The JSON files are dashboard definitions; storing them in the repository does not automatically import them into Grafana. Automatic provisioning requires an additional provisioning configuration.

### 7.4 Microservices Overview Dashboard

The overview dashboard is intended to display:

- Application target availability.
- HTTP request traffic.
- HTTP request latency.
- Requests currently in flight.
- Other instrumented application metrics.

Example PromQL expressions:

**Target availability**

```promql
up{namespace="microservices"}
```

**HTTP request rate**

```promql
sum by (job) (
  rate(http_requests_total[5m])
)
```

**HTTP 5xx error rate**

```promql
sum by (job) (
  rate(http_requests_total{status_code=~"5.."}[5m])
)
```

The error-rate query assumes the counter uses a `status_code` label. Adjust it if the application uses a different label name.

**HTTP request latency (p95)**

```promql
histogram_quantile(
  0.95,
  sum by (job, le) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
```

This latency query assumes the histogram exposes the `_bucket` series and uses the standard `le` bucket label.

**Requests in flight**

```promql
sum by (job) (
  http_requests_in_flight
)
```

Confirm that the metric names and labels match the actual `/metrics` output before using these queries in production dashboards.

### 7.5 AI-RCA Model Monitoring Dashboard

The RCA dashboard is designed to visualize model-related metrics such as:

- Inference request volume.
- Inference latency.
- Model errors.
- Prediction distribution.
- Prediction confidence.

Metrics with names such as `rca_inference_requests_total`, `rca_model_errors_total`, and `rca_prediction_confidence` are proposed metrics for this dashboard. They will not return data until the AI-RCA application exports metrics with matching names and labels.

---

## 8. Retention and Resource Configuration

The current Helm values define the following monitoring settings:

| Setting | Value |
|---|---|
| Prometheus scrape interval | 15 seconds |
| Prometheus evaluation interval | 15 seconds |
| Prometheus retention | 7 days |
| Scrape timeout | 10 seconds |
| Grafana | Enabled |
| Alertmanager | Enabled |
| kube-state-metrics | Enabled |
| node-exporter | Enabled |

Prometheus resource requests and limits are configured in the Helm values file. Review the current file before changing resource allocations.

The actual storage capacity and persistence behavior depend on the Prometheus volume configuration and the available Kubernetes StorageClass. Verify these settings before relying on historical metrics across pod restarts.

---

## 9. Troubleshooting

### 9.1 ServiceMonitor Exists but Target Is Missing

Check the ServiceMonitor resources:

```bash
kubectl get servicemonitors -n monitoring
```

Check their labels and selectors:

```bash
kubectl get servicemonitors -n monitoring --show-labels
```

Verify the Helm release label:

```text
release: kube-prometheus-stack
```

Then verify that:

- The ServiceMonitor selects the correct Service.
- The namespace selector includes `microservices`.
- The Service has the expected `app` label.
- The Service exposes a port named `http`.
- The endpoint path is `/metrics`.
- The Prometheus custom resource selects the ServiceMonitor's labels and namespace.

Inspect the Prometheus configuration and target errors through the Prometheus UI.

### 9.2 Target Is DOWN

Check the application pods:

```bash
kubectl get pods -n microservices
```

Check the Services and endpoints:

```bash
kubectl get svc -n microservices
kubectl get endpoints -n microservices
```

For clusters using EndpointSlice resources:

```bash
kubectl get endpointslices -n microservices
```

Inspect application logs:

```bash
kubectl logs deployment/api-gateway -n microservices
kubectl logs deployment/order-service -n microservices
kubectl logs deployment/payment-service -n microservices
```

Check whether the metrics endpoint is accessible and whether the application binds to the expected container port.

Also inspect NetworkPolicies if network traffic between Prometheus and the application pods may be restricted.

### 9.3 Metrics Are Missing in Grafana

1. Check whether the relevant target is UP in Prometheus.
2. Execute the metric query directly in Prometheus.
3. Verify that the application exports the metric.
4. Confirm that the dashboard uses the correct Prometheus data source.
5. Check that the dashboard query uses the actual metric names and labels.
6. Adjust the time range if the data is outside the selected interval.

A dashboard panel can exist without displaying data when the corresponding metric has not been implemented or no matching time series has been collected.

### 9.4 Monitoring Pods Are Not Ready

Inspect the pods:

```bash
kubectl get pods -n monitoring
```

Inspect events:

```bash
kubectl get events -n monitoring \
  --sort-by='.lastTimestamp'
```

Inspect a specific pod:

```bash
kubectl describe pod <pod-name> -n monitoring
```

Review logs for the affected component:

```bash
kubectl logs <pod-name> -n monitoring
```

Common causes include insufficient resources, storage provisioning problems, scheduling constraints, and invalid configuration.

### 9.5 Grafana Password Secret Is Missing

List the available Secrets:

```bash
kubectl get secrets -n monitoring \
  --kubeconfig "$HOME/.kube/config_NT548"
```

Filter for Grafana-related names:

```bash
kubectl get secrets -n monitoring \
  --kubeconfig "$HOME/.kube/config_NT548" \
  | grep -i grafana
```

Inspect the Helm values and release status:

```bash
helm get values kube-prometheus-stack \
  -n monitoring --all
```

```bash
helm status kube-prometheus-stack -n monitoring
```

Do not assume that a particular Secret name or label selector exists without checking the deployed release.

---

## 10. Useful Commands

### Kubernetes Resources

```bash
kubectl get pods -n monitoring
kubectl get svc -n monitoring
kubectl get servicemonitors -n monitoring
kubectl get pods -n microservices
kubectl get svc -n microservices
```

### Helm Release

```bash
helm list -n monitoring
helm status kube-prometheus-stack -n monitoring
helm get values kube-prometheus-stack -n monitoring
```

### Port Forwarding

Prometheus:

```bash
kubectl port-forward \
  -n monitoring \
  svc/kube-prometheus-stack-kube-prometheus \
  9090:9090
```

Grafana:

```bash
kubectl port-forward \
  -n monitoring \
  svc/kube-prometheus-stack-grafana \
  3000:80
```

### Reapply the Monitoring Stack

```bash
helm upgrade --install kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  --version 92.14.0 \
  --namespace monitoring \
  --values monitoring/helm-values/kube-prometheus-stack-values.yaml
```

### Inspect Application Metrics

```bash
curl -fsS http://localhost:8000/metrics
curl -fsS http://localhost:8001/metrics
curl -fsS http://localhost:8002/metrics
```

These local `curl` commands assume the corresponding port-forward sessions are running.

---

## 11. Security Considerations

- Do not commit Grafana passwords, Kubernetes credentials, or other secrets to Git.
- Use Kubernetes Secrets or an appropriate external secret-management solution for sensitive configuration.
- Restrict access to Grafana and Prometheus according to the intended environment.
- Avoid exposing monitoring endpoints publicly unless required and protected.
- Use Kubernetes RBAC to restrict access to monitoring resources.
- Review resource requests, limits, and persistent storage settings before scaling the monitoring stack.
- Treat dashboards as visualization configuration; implement and validate the underlying metrics separately.

---

## 12. References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Prometheus Operator](https://prometheus-operator.dev/)
- [kube-prometheus-stack Helm Chart](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack)
- [Grafana Documentation](https://grafana.com/docs/grafana/latest/)
- [Prometheus Python Client](https://github.com/prometheus/client_python)

---

## 13. Summary

The monitoring stack provides a common observability layer for the AI-RCA microservices deployed on Kubernetes.

Prometheus collects metrics from the API Gateway, Order Service, and Payment Service through ServiceMonitor resources. Grafana visualizes the collected metrics through dashboards, while the AI-RCA dashboard provides a foundation for monitoring model behavior once the corresponding application metrics have been instrumented.

The deployment should be considered operational when the monitoring components are ready, the three application targets are UP in Prometheus, and the expected application metrics are queryable.
```