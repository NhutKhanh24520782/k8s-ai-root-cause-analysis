output "cluster_name" {
  description = "Name of the EKS cluster."
  value       = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  description = "HTTPS endpoint of the EKS API server."
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64-encoded CA data for the cluster."
  value       = aws_eks_cluster.this.certificate_authority[0].data
  sensitive   = true
}

output "node_group_role_arn" {
  description = "IAM role ARN attached to the managed node group."
  value       = aws_iam_role.node.arn
}

output "oidc_provider_arn" {
  description = "ARN of the IAM OIDC provider (needed by IRSA module)."
  value       = aws_iam_openid_connect_provider.this.arn
}

output "oidc_provider_url" {
  description = "URL of the IAM OIDC provider (without https://)."
  value       = replace(aws_iam_openid_connect_provider.this.url, "https://", "")
}
