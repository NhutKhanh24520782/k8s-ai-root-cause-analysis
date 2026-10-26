# terraform/

> **Status:** Configuration files created. Bootstrap the S3 state bucket, then run `terraform init` and `terraform apply`.

---

## Table of Contents

1. [Purpose](#purpose)
2. [Directory Structure](#directory-structure)
3. [Modules](#modules)
4. [Quick Start](#quick-start)
5. [Bootstrap Remote State (one-time)](#bootstrap-remote-state-one-time)
6. [Daily Workflow](#daily-workflow)
7. [Outputs](#outputs)
8. [Cost Control](#cost-control)
9. [Security Notes](#security-notes)

---

## Purpose

Terraform provisions **all AWS infrastructure** for the project:

| Resource | Module |
|----------|--------|
| VPC, subnets, IGW, NAT Gateway, route tables | `modules/vpc` |
| EKS cluster, managed node group, add-ons, OIDC | `modules/eks` |
| ECR repositories (one per service image) | `modules/ecr` |
| IRSA role for the AWS Load Balancer Controller | `modules/irsa` |

Terraform does **not** deploy application workloads (Deployments, Services, Helm charts). Those live in `kubernetes/`.

---

## Directory Structure

```
terraform/
├── versions.tf                  ← required providers (aws ~> 5.80, tls ~> 4.0)
├── backend.tf                   ← S3 remote state config (update bucket name before init)
├── variables.tf                 ← all input variables with defaults
├── main.tf                      ← root config: wires all modules together
├── outputs.tf                   ← cluster name, ECR URLs, kubeconfig command, etc.
├── terraform.tfvars.example     ← copy → terraform.tfvars and fill in values
├── bootstrap/                   ← one-time: creates the S3 state bucket
│   ├── main.tf                  ← S3 bucket (local backend, prevent_destroy)
│   ├── variables.tf
│   ├── outputs.tf               ← prints bucket name + next-step command
│   ├── terraform.tfvars.example
│   └── README.md
├── policies/
│   └── alb-controller-policy.json  ← IAM policy for the AWS LBC (v2.8.0)
└── modules/
    ├── vpc/                     ← VPC, subnets, IGW, NAT, route tables
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── eks/                     ← EKS cluster, node group, OIDC, add-ons
    │   ├── main.tf
    │   ├── variables.tf
    │   ├── outputs.tf
    │   └── versions.tf
    ├── ecr/                     ← ECR repos + lifecycle policies
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    └── irsa/                    ← reusable IRSA role (used for ALB Controller)
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

---

## Modules

### `modules/vpc`
Creates the VPC with:
- 2 public subnets (ALB, NAT Gateway) tagged `kubernetes.io/role/elb=1`
- 2 private subnets (EKS nodes) tagged `kubernetes.io/role/internal-elb=1`
- 1 Internet Gateway
- 1 NAT Gateway (single, cost-optimised for the MVP)
- Public and private route tables

### `modules/eks`
Creates:
- **EKS cluster** (K8s 1.31 by default, private+public endpoint)
- **Cluster IAM role** with `AmazonEKSClusterPolicy`
- **Node IAM role** with `AmazonEKSWorkerNodePolicy`, `AmazonEKS_CNI_Policy`, `AmazonEC2ContainerRegistryReadOnly`, `AmazonEBSCSIDriverPolicy`
- **Managed node group** (AL2023, configurable instance type and count)
- **IAM OIDC provider** (prerequisite for IRSA)
- **EKS add-ons**: CoreDNS, kube-proxy, VPC CNI, EBS CSI Driver

### `modules/ecr`
Creates one ECR repository per service:
- `api-gateway`
- `order-service`
- `payment-service`
- `rca-api`

Each repository has:
- Image scanning on push (CVE detection, free tier)
- Lifecycle policy: retain 10 most-recent tagged images; purge untagged images after 7 days

### `modules/irsa`
Generic, reusable module that creates an IAM role with an OIDC trust policy scoped to a Kubernetes ServiceAccount. Used for the AWS Load Balancer Controller.

---

## Quick Start

### Prerequisites
- AWS CLI v2 configured (`aws configure` or `AWS_PROFILE` set)
- Terraform ≥ 1.10
- Sufficient IAM permissions (Administrator or a scoped DevOps policy)

### Step 1 — Bootstrap the S3 state bucket (one-time, per team)

Choose **one** of the following options. All three produce the same result.

**Option A — Terraform bootstrap** *(recommended — fully declarative)*
```bash
cd terraform/bootstrap/
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars → set a unique bucket_name (e.g. ai-rca-tfstate-abc123)

terraform init
terraform plan
terraform apply

# Commit the local state so teammates know bootstrap is done
git add terraform.tfstate
git commit -m "chore(terraform): bootstrap S3 state bucket"
cd ..
```

**Option B — Bash script** *(Linux/macOS)*
```bash
chmod +x scripts/bootstrap-state-bucket.sh
./scripts/bootstrap-state-bucket.sh ai-rca-tfstate-<suffix>
```

**Option C — PowerShell script** *(Windows)*
```powershell
.\scripts\bootstrap-state-bucket.ps1 -BucketName "ai-rca-tfstate-<suffix>"
```

> See [bootstrap/README.md](./bootstrap/README.md) for full details on each option.

### Step 2 — Update `backend.tf`

Open [backend.tf](./backend.tf) and replace `ai-rca-tfstate-changeme` with the actual bucket name created above. Commit this change.

### Step 3 — Create your tfvars

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars if you need non-default values
```

`terraform.tfvars` is excluded from Git by `.gitignore`.

### Step 4 — Initialise Terraform

```bash
cd terraform/
terraform init
```

### Step 5 — Plan and Apply

```bash
terraform fmt -check   # must pass before any PR
terraform validate
terraform plan
terraform apply
```

### Step 6 — Configure kubectl

After apply, run the kubeconfig command shown in the outputs:

```bash
aws eks update-kubeconfig --region ap-southeast-1 --name ai-rca-dev-cluster
kubectl get nodes      # should show 2 Ready nodes
```

---

## Daily Workflow

```bash
terraform fmt          # format before committing
terraform validate     # syntax check
terraform plan         # review changes
terraform apply        # apply after team review
```

**Destroy when done for the day:**
```bash
terraform destroy      # removes EKS cluster, node group, VPC — NOT the S3 state bucket
```

> [!WARNING]
> `terraform destroy` will remove the EKS cluster and all data on nodes. Always `kubectl drain` if there are important workloads. The S3 state bucket is **not** managed by this Terraform configuration and will NOT be destroyed.

---

## Outputs

After `terraform apply`, the following values are printed:

| Output | Description |
|--------|-------------|
| `vpc_id` | VPC ID |
| `private_subnet_ids` | IDs of private subnets |
| `public_subnet_ids` | IDs of public subnets |
| `cluster_name` | EKS cluster name |
| `cluster_endpoint` | EKS API server HTTPS endpoint |
| `node_group_role_arn` | IAM role ARN for the node group |
| `oidc_provider_arn` | OIDC provider ARN (for IRSA) |
| `ecr_repository_urls` | Map of service → ECR URL |
| `kubeconfig_command` | `aws eks update-kubeconfig ...` command |

Retrieve a specific output at any time:
```bash
terraform output ecr_repository_urls
```

---

## Cost Control

| Resource | ~Cost | Action |
|----------|-------|--------|
| EKS control plane | $0.10/hr | `terraform destroy` when not working |
| 2× t3.medium nodes | $0.08–0.18/hr | Same as above |
| NAT Gateway | $0.045/hr + data | Same as above |
| ALB | $0.008/hr + LCU | Same as above |
| ECR + S3 | Negligible | Leave running |

**Set an AWS Budget alert** at your team's threshold before the first `terraform apply`.

---

## Security Notes

- **Never commit `terraform.tfvars`** — it is in `.gitignore`.
- **Never commit `.tfstate` files** — they may contain sensitive resource IDs.
- The `.terraform.lock.hcl` file **must** be committed after `terraform init` so all team members use identical provider versions.
- All sensitive outputs (certificate authority data) are marked `sensitive = true` and will not appear in plain-text `terraform output`.
- IAM roles use least-privilege policies; do not attach `AdministratorAccess` to node roles.
