output "state_bucket_name" {
  description = "Name of the S3 state bucket. Copy this value into terraform/backend.tf."
  value       = aws_s3_bucket.tfstate.bucket
}

output "state_bucket_arn" {
  description = "ARN of the S3 state bucket."
  value       = aws_s3_bucket.tfstate.arn
}

output "state_bucket_region" {
  description = "AWS region where the state bucket was created."
  value       = aws_s3_bucket.tfstate.region
}

output "next_step" {
  description = "What to do after this apply completes."
  value       = <<-EOT

    ✅ Bootstrap complete.

    Next steps:
    1. Open  terraform/backend.tf
    2. Replace 'ai-rca-tfstate-changeme' with: ${aws_s3_bucket.tfstate.bucket}
    3. Run:
         cd ..
         terraform init
         terraform plan
         terraform apply
  EOT
}
