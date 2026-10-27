# =============================================================================
# Bootstrap — S3 Remote State Bucket
# =============================================================================
# This is a STANDALONE Terraform configuration with a LOCAL backend.
# Its only job is to create the S3 bucket that the MAIN Terraform configuration
# uses as its remote backend.
#
# Run order:
#   1. cd terraform/bootstrap/
#   2. cp terraform.tfvars.example terraform.tfvars   (fill in bucket_name)
#   3. terraform init
#   4. terraform apply
#   5. Copy the output `state_bucket_name` into terraform/backend.tf
#   6. cd ../  →  terraform init  →  terraform apply
#
# IMPORTANT:
#   - Do NOT run `terraform destroy` here unless you are retiring the project.
#   - The main `terraform destroy` does NOT touch this bucket.
# =============================================================================

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  # Intentionally LOCAL backend — this config must not depend on the bucket
  # it is creating. State is stored in terraform/bootstrap/terraform.tfstate.
  # Commit this file to Git after the first apply so the team can see it.
  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform-bootstrap"
    }
  }
}

# =============================================================================
# S3 State Bucket
# =============================================================================

resource "aws_s3_bucket" "tfstate" {
  bucket = var.bucket_name

  # Prevent accidental deletion of the state bucket.
  # Remove this before running `terraform destroy` if you truly want to delete it.
  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Name    = var.bucket_name
    Purpose = "terraform-remote-state"
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

# Enable versioning — allows rollback if state becomes corrupted
resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Encrypt all objects at rest using SSE-S3 (AES-256)
resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Lifecycle rule: expire old state versions after 90 days to control storage cost
resource "aws_s3_bucket_lifecycle_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  # Must wait for versioning to be enabled before applying lifecycle rules
  depends_on = [aws_s3_bucket_versioning.tfstate]

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Bucket policy: deny any request that is NOT using TLS
resource "aws_s3_bucket_policy" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  # Wait for public access block to be applied first
  depends_on = [aws_s3_bucket_public_access_block.tfstate]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyNonTLS"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.tfstate.arn,
          "${aws_s3_bucket.tfstate.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}
