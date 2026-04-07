# ═══════════════════════════════════════════════════════════════════════════
# EKS Cluster + Managed Node Groups
# ═══════════════════════════════════════════════════════════════════════════

# ── EKS Cluster ─────────────────────────────────────────────────────────
resource "aws_eks_cluster" "main" {
  name     = "${var.project_name}-${var.environment}"
  role_arn = var.cluster_role_arn
  version  = var.kubernetes_version

  vpc_config {
    subnet_ids              = concat(var.private_subnet_ids, var.public_subnet_ids)
    endpoint_private_access = true
    endpoint_public_access  = true
    security_group_ids      = [aws_security_group.cluster.id]
  }

  enabled_cluster_log_types = ["api", "audit", "authenticator"]

  tags = {
    Name = "${var.project_name}-${var.environment}-eks"
  }
}

# ── Cluster Security Group ──────────────────────────────────────────────
resource "aws_security_group" "cluster" {
  name_prefix = "${var.project_name}-${var.environment}-eks-cluster-"
  vpc_id      = var.vpc_id

  tags = {
    Name = "${var.project_name}-${var.environment}-eks-cluster-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group_rule" "cluster_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.cluster.id
}

# ── Node Security Group ────────────────────────────────────────────────
resource "aws_security_group" "nodes" {
  name_prefix = "${var.project_name}-${var.environment}-eks-nodes-"
  vpc_id      = var.vpc_id

  tags = {
    Name = "${var.project_name}-${var.environment}-eks-nodes-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group_rule" "nodes_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.nodes.id
}

resource "aws_security_group_rule" "nodes_internal" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "-1"
  source_security_group_id = aws_security_group.nodes.id
  security_group_id        = aws_security_group.nodes.id
  description              = "Node-to-node communication"
}

resource "aws_security_group_rule" "nodes_from_cluster" {
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.cluster.id
  security_group_id        = aws_security_group.nodes.id
  description              = "Cluster API to nodes"
}

resource "aws_security_group_rule" "nodes_from_cluster_kubelet" {
  type                     = "ingress"
  from_port                = 1025
  to_port                  = 65535
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.cluster.id
  security_group_id        = aws_security_group.nodes.id
  description              = "Cluster to node kubelet/pods"
}

resource "aws_security_group_rule" "cluster_from_nodes" {
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.nodes.id
  security_group_id        = aws_security_group.cluster.id
  description              = "Nodes to cluster API"
}

# ── Application Node Group (backend, celery, frontend, neo4j) ──────────
resource "aws_eks_node_group" "app" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.project_name}-${var.environment}-app"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.private_subnet_ids

  instance_types = var.app_instance_types
  capacity_type  = var.app_capacity_type

  scaling_config {
    desired_size = var.app_desired_size
    min_size     = var.app_min_size
    max_size     = var.app_max_size
  }

  update_config {
    max_unavailable = 1
  }

  labels = {
    role = "app"
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-app-nodes"
  }

  depends_on = [aws_eks_cluster.main]
}

# ── GPU Node Group (for Ollama LLM inference) ──────────────────────────
resource "aws_eks_node_group" "gpu" {
  count           = var.enable_gpu_nodes ? 1 : 0
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.project_name}-${var.environment}-gpu"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.private_subnet_ids

  instance_types = var.gpu_instance_types
  capacity_type  = "ON_DEMAND"

  scaling_config {
    desired_size = var.gpu_desired_size
    min_size     = 0
    max_size     = var.gpu_max_size
  }

  update_config {
    max_unavailable = 1
  }

  labels = {
    role                             = "gpu"
    "nvidia.com/gpu.present"         = "true"
  }

  taint {
    key    = "nvidia.com/gpu"
    value  = "true"
    effect = "NO_SCHEDULE"
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-gpu-nodes"
  }

  depends_on = [aws_eks_cluster.main]
}

# ── EKS Addons ─────────────────────────────────────────────────────────
resource "aws_eks_addon" "vpc_cni" {
  cluster_name = aws_eks_cluster.main.name
  addon_name   = "vpc-cni"

  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
}

resource "aws_eks_addon" "coredns" {
  cluster_name = aws_eks_cluster.main.name
  addon_name   = "coredns"

  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"

  depends_on = [aws_eks_node_group.app]
}

resource "aws_eks_addon" "kube_proxy" {
  cluster_name = aws_eks_cluster.main.name
  addon_name   = "kube-proxy"

  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
}

resource "aws_eks_addon" "ebs_csi" {
  cluster_name             = aws_eks_cluster.main.name
  addon_name               = "aws-ebs-csi-driver"
  service_account_role_arn = var.ebs_csi_role_arn

  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
}
