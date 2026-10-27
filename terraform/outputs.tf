# =============================================================================
# Outputs — values consumed by other tools (kubectl, Helm, CI/CD scripts)
# =============================================================================

# --- VPC ---

output "vpc_id" {
  description = "ID of the project VPC."
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "IDs of the two private subnets (EKS nodes run here)."
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "IDs of the two public subnets (ALB, NAT Gateway)."
  value       = module.vpc.public_subnet_ids
}

# --- EKS ---

output "cluster_name" {
  description = "Name of the EKS cluster."
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "HTTPS endpoint of the EKS API server."
  value       = module.eks.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64-encoded certificate authority data for the cluster."
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "node_group_role_arn" {
  description = "IAM role ARN of the EKS managed node group."
  value       = module.eks.node_group_role_arn
}

output "oidc_provider_arn" {
  description = "ARN of the IAM OIDC provider for IRSA."
  value       = module.eks.oidc_provider_arn
}

# --- ECR ---

output "ecr_repository_urls" {
  description = "Map of service name → ECR repository URL."
  value       = module.ecr.repository_urls
}

# --- Convenience: kubeconfig update command ---

output "kubeconfig_command" {
  description = "Run this command to update ~/.kube/config for kubectl access."
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}
