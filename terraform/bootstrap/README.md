# terraform/bootstrap/

> **Purpose:** One-time provisioning of the S3 bucket used as Terraform remote state for the main configuration.

---

## Why a separate bootstrap?

The main `terraform/` configuration uses an S3 bucket as its backend. That bucket must exist **before** `terraform init` can run in `terraform/`. This creates a chicken-and-egg dependency:

```
Main Terraform backend  →  needs S3 bucket
S3 bucket               →  cannot be created by the same config that uses it as backend
```

This `bootstrap/` directory is a **standalone Terraform configuration with a local backend**. Its only job is to create and harden that S3 bucket.

---

## Files

| File | Purpose |
|------|---------|
| `main.tf` | Creates the S3 bucket with versioning, encryption, public access block, lifecycle rule, and TLS-enforce policy |
| `variables.tf` | Input variables (project name, region, bucket name) |
| `outputs.tf` | Prints the bucket name and the next-step command after apply |
| `terraform.tfvars.example` | Template — copy to `terraform.tfvars` and fill in `bucket_name` |
| `terraform.tfstate` | **Local** state file created after `terraform apply` — **commit this to Git** |

---

## Usage (one-time, per team)

### Option A — Terraform bootstrap (this directory) ✅ Recommended

```bash
cd terraform/bootstrap/

# 1. Create your tfvars
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set a unique bucket_name (e.g. ai-rca-tfstate-abc123)

# 2. Init and apply
terraform init
terraform plan
terraform apply

# 3. Copy the output bucket name into ../backend.tf
#    (the apply output will remind you of the exact name)

# 4. Commit terraform.tfstate so the team can see bootstrap was done
git add terraform.tfstate
git commit -m "chore(terraform): bootstrap S3 state bucket"
```

### Option B — AWS CLI script (alternative)

**Linux/macOS:**
```bash
cd <repo-root>
chmod +x scripts/bootstrap-state-bucket.sh
./scripts/bootstrap-state-bucket.sh ai-rca-tfstate-<suffix>
```

**Windows (PowerShell):**
```powershell
cd <repo-root>
.\scripts\bootstrap-state-bucket.ps1 -BucketName "ai-rca-tfstate-<suffix>"
```

---

## After bootstrap — update `backend.tf`

Open [../backend.tf](../backend.tf) and replace the placeholder:

```hcl
# Before
bucket = "ai-rca-tfstate-changeme"

# After
bucket = "ai-rca-tfstate-<your-actual-suffix>"
```

Commit the change, then proceed to the main Terraform workflow:

```bash
cd ../
terraform init
terraform plan
terraform apply
```

---

## Important notes

- **Do NOT run `terraform destroy` in this directory** unless you are permanently retiring the project. The state bucket contains all main Terraform state — destroying it makes the main infrastructure unmanageable.
- The `prevent_destroy = true` lifecycle rule on the bucket resource prevents accidental `terraform destroy`. You must remove it from `main.tf` before Terraform will allow destruction.
- `terraform.tfvars` is excluded from Git (via root `.gitignore`). The example file IS committed.
- `terraform.tfstate` (the local state of the bootstrap itself) SHOULD be committed after the first apply. It contains only the bucket's metadata — no secrets.
