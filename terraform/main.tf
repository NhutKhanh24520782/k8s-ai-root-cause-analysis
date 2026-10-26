# =============================================================================
# Local values — computed from variables, not repeated in every resource block
# =============================================================================

locals {
  # Consistent name prefix for all resources
  name_prefix = "${var.project_name}-${var.environment}"

  # Two AZs in the target region
  azs = ["${var.aws_region}a", "${var.aws_region}b"]

  # ECR repositories required by the project
  ecr_repos = [
    "api-gateway",
    "order-service",
    "payment-service",
    "rca-api",
  ]
}

# =============================================================================
# Data sources
# =============================================================================

# Retrieve the caller's AWS account ID at plan time (used in IAM ARNs)
data "aws_caller_identity" "current" {}

# EKS-optimised AL2023 AMI (used implicitly by the managed node group)
data "aws_eks_cluster_auth" "this" {
  name = module.eks.cluster_name
}

# =============================================================================
# VPC
# =============================================================================

module "vpc" {
  source = "./modules/vpc"

  name_prefix          = local.name_prefix
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  azs                  = local.azs
}

# =============================================================================
# EKS cluster + node group
# =============================================================================

module "eks" {
  source = "./modules/eks"

  name_prefix        = local.name_prefix
  kubernetes_version = var.kubernetes_version

  # Networking
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  public_subnet_ids  = module.vpc.public_subnet_ids

  # Node group sizing
  node_instance_type = var.node_instance_type
  node_desired_count = var.node_desired_count
  node_min_count     = var.node_min_count
  node_max_count     = var.node_max_count
}

# =============================================================================
# ECR repositories (one per service image)
# =============================================================================

module "ecr" {
  source = "./modules/ecr"

  repositories          = local.ecr_repos
  image_retention_count = var.ecr_image_retention_count
}

# =============================================================================
# IAM — IRSA for the AWS Load Balancer Controller
# =============================================================================

module "irsa_alb_controller" {
  source = "./modules/irsa"

  name_prefix         = local.name_prefix
  role_name           = "alb-controller"
  oidc_provider_arn   = module.eks.oidc_provider_arn
  oidc_provider_url   = module.eks.oidc_provider_url
  k8s_namespace       = "kube-system"
  k8s_service_account = "aws-load-balancer-controller"
  policy_arn          = aws_iam_policy.alb_controller.arn
}

# Inline policy document — permits the ALB controller to manage load balancers.
# Sourced from the official AWS docs for the LBC.
resource "aws_iam_policy" "alb_controller" {
  name        = "${local.name_prefix}-alb-controller-policy"
  description = "Permissions for the AWS Load Balancer Controller running in EKS."
  policy      = file("${path.module}/policies/alb-controller-policy.json")
}
