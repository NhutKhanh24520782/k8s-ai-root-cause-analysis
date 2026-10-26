# =============================================================================
# ECR Repositories
# One repository per service image (api-gateway, order-service, etc.)
# =============================================================================

resource "aws_ecr_repository" "this" {
  for_each = toset(var.repositories)

  name                 = each.key
  image_tag_mutability = "MUTABLE" # Allows re-pushing the same tag (e.g., "latest")

  image_scanning_configuration {
    scan_on_push = true # Scan every pushed image for CVEs at no extra cost
  }

  tags = {
    Name = each.key
  }
}

# =============================================================================
# Lifecycle Policy — retain only the N most recent tagged images
# This prevents unbounded storage growth during active development.
# =============================================================================

resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the last ${var.image_retention_count} tagged images."
        selection = {
          tagStatus   = "tagged"
          tagPrefixList = ["v", "sha-"]
          countType   = "imageCountMoreThan"
          countNumber = var.image_retention_count
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Remove untagged images older than 7 days."
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      }
    ]
  })
}
