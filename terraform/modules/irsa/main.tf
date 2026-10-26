# =============================================================================
# IRSA — IAM Role for Service Account
# Creates an IAM role that a Kubernetes ServiceAccount can assume via OIDC.
# =============================================================================

resource "aws_iam_role" "this" {
  name = "${var.name_prefix}-irsa-${var.role_name}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = var.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${var.oidc_provider_url}:sub" = "system:serviceaccount:${var.k8s_namespace}:${var.k8s_service_account}"
          "${var.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "this" {
  role       = aws_iam_role.this.name
  policy_arn = var.policy_arn
}
