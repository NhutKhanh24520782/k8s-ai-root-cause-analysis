"""
scripts/generate_dashboards_configmap.py
Generates monitoring/dashboards-configmap.yaml embedding JSON dashboards
so that Grafana's sidecar automatically discovers and imports them into Kubernetes.
"""

import json
import os

DASHBOARDS_DIR = os.path.join("monitoring", "grafana-dashboards")
OUTPUT_FILE = os.path.join("monitoring", "dashboards-configmap.yaml")

DASHBOARDS = [
    ("microservices-overview", "microservices-overview.json"),
    ("rca-model-monitoring", "rca-model-monitoring.json"),
]

def main():
    docs = []
    for cm_name, filename in DASHBOARDS:
        filepath = os.path.join(DASHBOARDS_DIR, filename)
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Format as indented yaml multi-line block
        indented_content = "\n".join("    " + line for line in content.splitlines())

        doc = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboard-{cm_name}
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
    app.kubernetes.io/part-of: kube-prometheus-stack
data:
  {filename}: |-
{indented_content}
"""
        docs.append(doc)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# =============================================================================\n")
        f.write("# Auto-generated Grafana Dashboard ConfigMaps for AI-RCA Graduation Project\n")
        f.write("# Applied via: kubectl apply -f monitoring/dashboards-configmap.yaml\n")
        f.write("# =============================================================================\n\n")
        f.write("---\n".join(docs))

    print(f"[OK] Generated {OUTPUT_FILE} successfully.")

if __name__ == "__main__":
    main()

