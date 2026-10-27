# PostgreSQL

This directory contains the PostgreSQL resources used by the application stack in Kubernetes.

## Purpose

The `postgres/` folder stores the database manifests for the project, including:

- database services,
- StatefulSet definitions,
- storage-related Kubernetes configuration,
- database deployment objects for each application domain.

The project separates database resources into per-application subfolders so each service has its own isolated PostgreSQL deployment and service definition.

## Structure

```text
kubernetes/postgres/
├── order_db/
│   ├── service.yaml
│   └── statefulset.yaml
├── payment_db/
│   ├── service.yaml
│   └── statefulset.yaml
└── README.md
```

## Included resources

- `order_db/`: PostgreSQL resources for the order database
- `payment_db/`: PostgreSQL resources for the payment database
- Each subfolder contains the Kubernetes `Service` and `StatefulSet` needed to expose and run the database instance

## Notes

- These manifests are part of the application runtime configuration inside the cluster.
- They are distinct from AWS infrastructure files in the `terraform/` folder.
- The database credentials are managed separately as Kubernetes Secrets, not embedded directly in Git-tracked manifests.

---

This folder is dedicated to PostgreSQL deployment assets for the microservices environment.
