# ═══════════════════════════════════════════════════════════════════════════
# ECR Repositories for FinOps AI container images
# ═══════════════════════════════════════════════════════════════════════════

locals {
  repositories = toset(["backend", "frontend"])
}

resource "aws_ecr_repository" "repos" {
  for_each             = local.repositories
  name                 = "${var.project}-${var.env}/${each.key}"
  image_tag_mutability = "MUTABLE"
  force_delete         = var.env != "prod"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(var.tags, { Name = "${var.project}-${var.env}-${each.key}" })
}

resource "aws_ecr_lifecycle_policy" "cleanup" {
  for_each   = local.repositories
  repository = aws_ecr_repository.repos[each.key].name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
