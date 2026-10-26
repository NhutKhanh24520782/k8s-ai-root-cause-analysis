variable "repositories" {
  description = "List of ECR repository names to create."
  type        = list(string)
}

variable "image_retention_count" {
  description = "Number of tagged images to keep per repository (older images are purged)."
  type        = number
  default     = 10
}
