output "repository_urls" {
  description = "Map of repository name → repository URL (used for docker push / Kubernetes image references)."
  value       = { for name, repo in aws_ecr_repository.this : name => repo.repository_url }
}

output "repository_arns" {
  description = "Map of repository name → repository ARN."
  value       = { for name, repo in aws_ecr_repository.this : name => repo.arn }
}
