# =============================================================================
# Root variables
# =============================================================================

# --- Project identity ---

variable "project_name" {
  description = "Short name for the project; used in resource names and tags."
  type        = string
  default     = "ai-rca"
}

variable "environment" {
  description = "Deployment environment (dev | staging | prod)."
  type        = string
  default     = "dev"
}

# --- AWS ---

variable "aws_region" {
  description = "AWS region to deploy all resources into."
  type        = string
  default     = "ap-southeast-1"
}

# --- VPC ---

variable "vpc_cidr" {
  description = "IPv4 CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for the two public subnets (one per AZ)."
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for the two private subnets (one per AZ)."
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.20.0/24"]
}

# --- EKS ---

variable "kubernetes_version" {
  description = "Kubernetes version for the EKS cluster."
  type        = string
  default     = "1.31"
}

variable "node_instance_type" {
  description = "EC2 instance type for the EKS managed node group."
  type        = string
  default     = "t3.medium"
}

variable "node_desired_count" {
  description = "Desired number of worker nodes."
  type        = number
  default     = 2
}

variable "node_min_count" {
  description = "Minimum number of worker nodes."
  type        = number
  default     = 1
}

variable "node_max_count" {
  description = "Maximum number of worker nodes."
  type        = number
  default     = 3
}

# --- ECR ---

variable "ecr_image_retention_count" {
  description = "Number of images to keep per ECR repository (lifecycle policy)."
  type        = number
  default     = 10
}
