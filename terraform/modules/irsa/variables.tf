variable "name_prefix" {
  description = "Prefix applied to the IAM role name."
  type        = string
}

variable "role_name" {
  description = "Short name for this IRSA role (appended to name_prefix)."
  type        = string
}

variable "oidc_provider_arn" {
  description = "ARN of the EKS OIDC provider."
  type        = string
}

variable "oidc_provider_url" {
  description = "URL of the EKS OIDC provider (without https://)."
  type        = string
}

variable "k8s_namespace" {
  description = "Kubernetes namespace of the service account."
  type        = string
}

variable "k8s_service_account" {
  description = "Name of the Kubernetes service account to bind the IAM role to."
  type        = string
}

variable "policy_arn" {
  description = "ARN of the IAM policy to attach to this role."
  type        = string
}
