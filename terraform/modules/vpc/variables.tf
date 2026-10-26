variable "name_prefix" {
  description = "Prefix applied to every resource name."
  type        = string
}

variable "vpc_cidr" {
  description = "IPv4 CIDR block for the VPC."
  type        = string
}

variable "public_subnet_cidrs" {
  description = "List of CIDR blocks for public subnets (one per AZ)."
  type        = list(string)
}

variable "private_subnet_cidrs" {
  description = "List of CIDR blocks for private subnets (one per AZ)."
  type        = list(string)
}

variable "azs" {
  description = "List of Availability Zone names to use (must match subnet count)."
  type        = list(string)
}
