variable "project_name" {
  description = "Short project name; used in resource tags."
  type        = string
  default     = "ai-rca"
}

variable "aws_region" {
  description = "AWS region to create the state bucket in. Must match the main Terraform region."
  type        = string
  default     = "ap-southeast-1"
}

variable "bucket_name" {
  description = <<-EOT
    Globally unique name for the S3 Terraform state bucket.
    Convention: ai-rca-tfstate-<random-suffix>
    Example:    ai-rca-tfstate-abc123

    Rules:
    - 3–63 characters, lowercase letters, numbers, hyphens only
    - Must not start or end with a hyphen
    - Must be globally unique across ALL AWS accounts
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name must be 3–63 lowercase alphanumeric characters or hyphens, and cannot start/end with a hyphen."
  }
}
