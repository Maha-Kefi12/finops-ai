# ═══════════════════════════════════════════════════════════════════════════
# IAM Roles for EKS Cluster + Node Groups + IRSA
# ═══════════════════════════════════════════════════════════════════════════

# ── EKS Cluster Role ───────────────────────────────────────────────────
resource "aws_iam_role" "eks_cluster" {
  name = "${var.project}-${var.env}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "eks.amazonaws.com"
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster.name
}

resource "aws_iam_role_policy_attachment" "eks_vpc_resource_controller" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
  role       = aws_iam_role.eks_cluster.name
}

# ── EKS Node Group Role ───────────────────────────────────────────────
resource "aws_iam_role" "eks_node" {
  name = "${var.project}-${var.env}-eks-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "eks_worker_node" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_node.name
}

resource "aws_iam_role_policy_attachment" "eks_cni" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_node.name
}

resource "aws_iam_role_policy_attachment" "ecr_read" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_node.name
}

resource "aws_iam_role_policy_attachment" "ssm_managed" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  role       = aws_iam_role.eks_node.name
}

# ── OIDC Provider (for IRSA — pod-level AWS permissions) ───────────────
resource "aws_iam_openid_connect_provider" "eks" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint]
  url             = var.cluster_oidc_issuer

  tags = var.tags
}

data "tls_certificate" "eks" {
  url = var.cluster_oidc_issuer
}

locals {
  oidc_provider_arn = aws_iam_openid_connect_provider.eks.arn
  oidc_provider_id  = replace(var.cluster_oidc_issuer, "https://", "")
}

# ── EBS CSI Driver Role (IRSA) ────────────────────────────────────────
resource "aws_iam_role" "ebs_csi" {
  name = "${var.project}-${var.env}-ebs-csi-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Effect = "Allow"
      Principal = {
        Federated = local.oidc_provider_arn
      }
      Condition = {
        StringEquals = {
          "${local.oidc_provider_id}:sub" = "system:serviceaccount:kube-system:ebs-csi-controller-sa"
          "${local.oidc_provider_id}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
  role       = aws_iam_role.ebs_csi.name
}

# ── AWS Load Balancer Controller Role (IRSA) ──────────────────────────
resource "aws_iam_role" "lb_controller" {
  name = "${var.project}-${var.env}-lb-controller-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Effect = "Allow"
      Principal = {
        Federated = local.oidc_provider_arn
      }
      Condition = {
        StringEquals = {
          "${local.oidc_provider_id}:sub" = "system:serviceaccount:kube-system:aws-load-balancer-controller"
          "${local.oidc_provider_id}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_policy" "lb_controller" {
  name   = "${var.project}-${var.env}-lb-controller-policy"
  policy = file("${path.module}/policies/lb-controller-policy.json")
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "lb_controller" {
  policy_arn = aws_iam_policy.lb_controller.arn
  role       = aws_iam_role.lb_controller.name
}

# ── Backend App Role (IRSA — for S3, SSM, CUR access) ─────────────────
resource "aws_iam_role" "app_backend" {
  name = "${var.project}-${var.env}-backend-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Effect = "Allow"
      Principal = {
        Federated = local.oidc_provider_arn
      }
      Condition = {
        StringEquals = {
          "${local.oidc_provider_id}:sub" = "system:serviceaccount:finops:backend"
          "${local.oidc_provider_id}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_policy" "app_backend" {
  name = "${var.project}-${var.env}-backend-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SSMRead"
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath",
        ]
        Resource = "arn:aws:ssm:*:*:parameter/${var.project}/${var.env}/*"
      },
      {
        Sid    = "CURAccess"
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage",
          "ce:GetCostForecast",
          "cur:DescribeReportDefinitions",
        ]
        Resource = "*"
      },
      {
        Sid    = "S3Data"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:PutObject",
        ]
        Resource = [
          "arn:aws:s3:::${var.project}-${var.env}-data",
          "arn:aws:s3:::${var.project}-${var.env}-data/*",
        ]
      },
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "app_backend" {
  policy_arn = aws_iam_policy.app_backend.arn
  role       = aws_iam_role.app_backend.name
}
