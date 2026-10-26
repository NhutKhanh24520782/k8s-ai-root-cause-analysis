variable "name_prefix" {
  description = "Prefix applied to every resource name."
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version for the EKS cluster."
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC to deploy the cluster into."
  type        = string
}

variable "private_subnet_ids" {
  description = "IDs of private subnets where worker nodes will run."
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "IDs of public subnets (used for ALB Ingress)."
  type        = list(string)
}

variable "node_instance_type" {
  description = "EC2 instance type for the managed node group."
  type        = string
}

variable "node_desired_count" {
  description = "Desired number of worker nodes."
  type        = number
}

variable "node_min_count" {
  description = "Minimum number of worker nodes."
  type        = number
}

variable "node_max_count" {
  description = "Maximum number of worker nodes."
  type        = number
}
