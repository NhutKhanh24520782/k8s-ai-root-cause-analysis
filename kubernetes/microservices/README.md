# Microservices

This directory contains the Kubernetes manifests for the application microservices deployed into the EKS cluster.

## Purpose

The `microservices/` folder groups the runtime resources for the project’s service layer. It is responsible for defining how each application component is deployed inside Kubernetes, including:

- Deployment configuration
- Cluster-internal Service exposure
- Pod replicas and container image references
- Application-level networking within the namespace

This folder is separate from the infrastructure layer in `terraform/` and from the database manifests in `kubernetes/postgres/`.

## Structure

```text
kubernetes/microservices/
├── README.md
├── api-gateway/
│   ├── deployment.yaml
│   └── service.yaml
├── order-service/
│   ├── deployment.yaml
│   └── service.yaml
└── payment-service/
    ├── deployment.yaml
    └── service.yaml
```

## Included components

### API Gateway
The `api-gateway` directory contains the Kubernetes manifest for the public entry point of the application. It exposes the API layer to the cluster and routes requests to downstream services.

### Order Service
The `order-service` directory contains the deployment and service resources for the order-processing service. This component handles order-related business logic and communicates with the database layer.

### Payment Service
The `payment-service` directory contains the deployment and service resources for the payment-processing service. It handles payment-related logic and participates in the application workflow.

## Role in the project

This folder represents the application workload layer of the project. While Terraform provisions the AWS EKS infrastructure, the files under this directory define what runs inside the cluster.

The manifests here are used to:

- deploy service containers,
- expose them through Kubernetes Services,
- enable internal communication between application components,
- support the end-to-end microservice architecture used for incident simulation and RCA analysis.

## Notes

- These manifests are Kubernetes application configs, not AWS infrastructure definitions.
- The service assets are organized by workload, making it easier to manage, update, and debug each microservice independently.
- Environment-specific values such as container image URIs are typically injected at deployment time rather than hardcoded in Git-managed manifests.
