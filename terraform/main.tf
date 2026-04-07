# ═══════════════════════════════════════════════════════════════════════════
# FinOps AI — EKS Deployment Root Module
# ═══════════════════════════════════════════════════════════════════════════

locals {
  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ── 1. Networking (VPC, subnets, NAT, subnet groups) ──────────────────
module "networking" {
  source = "./modules/networking"

  project_name = local.project_name
  environment  = local.environment
  vpc_cidr     = var.vpc_cidr
  az_count     = var.az_count
}

# ── 2. EKS Cluster + Node Groups ─────────────────────────────────────
module "eks" {
  source = "./modules/eks"

  project_name       = local.project_name
  environment        = local.environment
  vpc_id             = module.networking.vpc_id
  private_subnet_ids = module.networking.private_subnet_ids
  public_subnet_ids  = module.networking.public_subnet_ids
  cluster_role_arn   = module.iam_base.eks_cluster_role_arn
  node_role_arn      = module.iam_base.eks_node_role_arn
  ebs_csi_role_arn   = module.iam.ebs_csi_role_arn

  kubernetes_version = var.kubernetes_version
  app_instance_types = var.app_instance_types
  app_desired_size   = var.app_desired_size
  app_min_size       = var.app_min_size
  app_max_size       = var.app_max_size
  enable_gpu_nodes   = var.enable_gpu_nodes
  gpu_instance_types = var.gpu_instance_types
}

# ── 3. IAM — Base roles (no OIDC dependency) ─────────────────────────
# Split IAM into base (cluster/node roles) and OIDC-dependent (IRSA).
# Base roles are needed BEFORE the cluster exists.
module "iam_base" {
  source = "./modules/iam_base"

  project = local.project_name
  env     = local.environment
  tags    = local.common_tags
}

# ── 4. IAM — OIDC + IRSA roles (depends on EKS cluster) ─────────────
module "iam" {
  source = "./modules/iam"

  project             = local.project_name
  env                 = local.environment
  cluster_oidc_issuer = module.eks.cluster_oidc_issuer
  tags                = local.common_tags
}

# ── 5. RDS PostgreSQL ────────────────────────────────────────────────
module "rds" {
  source = "./modules/rds"

  project            = local.project_name
  env                = local.environment
  vpc_id             = module.networking.vpc_id
  private_subnet_ids = module.networking.database_subnet_ids
  instance_class     = var.rds_instance_class
  allocated_storage  = var.rds_allocated_storage
  db_name            = "finops_db"
  db_username        = "finops"

  allowed_security_group_ids = [module.eks.node_security_group_id]

  tags = local.common_tags
}

# ── 6. ElastiCache Redis ────────────────────────────────────────────
module "elasticache" {
  source = "./modules/elasticache"

  project           = local.project_name
  env               = local.environment
  vpc_id            = module.networking.vpc_id
  subnet_group_name = module.networking.elasticache_subnet_group_name
  node_type         = var.redis_node_type

  allowed_security_group_ids = [module.eks.node_security_group_id]

  tags = local.common_tags
}

# ── 7. ECR Repositories ─────────────────────────────────────────────
module "ecr" {
  source = "./modules/ecr"

  project = local.project_name
  env     = local.environment
  tags    = local.common_tags
}
