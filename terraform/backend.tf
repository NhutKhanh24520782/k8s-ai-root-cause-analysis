# =============================================================================
# Remote State Backend (S3)
# =============================================================================
# Bootstrap the S3 bucket BEFORE running `terraform init`.
# See: scripts/bootstrap-state-bucket.sh
#
# To init without committing real values, use -backend-config flags:
#   terraform init \
#     -backend-config="bucket=ai-rca-tfstate-<suffix>" \
#     -backend-config="key=ai-root-cause-analysis/dev/terraform.tfstate" \
#     -backend-config="region=ap-southeast-1" \
#     -backend-config="encrypt=true" \
#     -backend-config="use_lockfile=true"
# =============================================================================

terraform {
  backend "s3" {
    # Replace with your actual bucket name after running the bootstrap script.
    # This value is NOT a secret and can be committed.
    bucket = "ai-rca-tfstate-changeme"

    key    = "ai-root-cause-analysis/dev/terraform.tfstate"
    region = "ap-southeast-1"

    encrypt = true

    # NOTE: `use_lockfile = true` (native S3 locking) requires Terraform >= 1.10.
    # The team is currently on 1.9.x — state locking is disabled.
    # To re-enable: upgrade Terraform to >= 1.10 and add `use_lockfile = true`.
    # For now, coordinate with the team to avoid concurrent `terraform apply` runs.
  }
}
