# ═══════════════════════════════════════════════════════════════════════════
# ElastiCache Redis (replaces docker-compose redis service)
# Used as: Celery broker + result backend + application cache
# ═══════════════════════════════════════════════════════════════════════════

resource "aws_security_group" "redis" {
  name_prefix = "${var.project}-${var.env}-redis-"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
    description     = "Redis from EKS nodes"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.project}-${var.env}-redis-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${var.project}-${var.env}-redis"
  description          = "FinOps AI Redis — Celery broker + cache"

  engine               = "redis"
  engine_version       = "7.1"
  node_type            = var.node_type
  num_cache_clusters   = var.env == "prod" ? 2 : 1
  port                 = 6379
  parameter_group_name = "default.redis7"

  subnet_group_name  = var.subnet_group_name
  security_group_ids = [aws_security_group.redis.id]

  automatic_failover_enabled = var.env == "prod"
  multi_az_enabled           = var.env == "prod"

  at_rest_encryption_enabled = true
  transit_encryption_enabled = false

  snapshot_retention_limit = var.env == "prod" ? 3 : 0
  snapshot_window          = "04:00-05:00"
  maintenance_window       = "Mon:05:00-Mon:06:00"

  apply_immediately = true

  tags = merge(var.tags, { Name = "${var.project}-${var.env}-redis" })
}

# ── Store endpoint in SSM ──────────────────────────────────────────────
resource "aws_ssm_parameter" "redis_host" {
  name  = "/${var.project}/${var.env}/redis/host"
  type  = "String"
  value = aws_elasticache_replication_group.main.primary_endpoint_address
  tags  = var.tags
}
