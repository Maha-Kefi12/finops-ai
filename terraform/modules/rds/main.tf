# ============================================================
# MODULE: data/rds
# Creates: RDS PostgreSQL, subnet group, security group
# ============================================================

# ── Random password for master user ──────────────────────────
resource "random_password" "master" {
  length  = 24
  special = false
}

# ── Subnet Group ─────────────────────────────────────────────
resource "aws_db_subnet_group" "this" {
  name       = "${var.project}-${var.env}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = merge(var.tags, { Name = "${var.project}-${var.env}-db-subnet-group" })
}

# ── Security Group ───────────────────────────────────────────
resource "aws_security_group" "rds" {
  name        = "${var.project}-${var.env}-sg-rds"
  description = "Allow PostgreSQL from ECS tasks"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
    description     = "PostgreSQL from app services"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.project}-${var.env}-sg-rds" })
}

# ── RDS Instance ─────────────────────────────────────────────
resource "aws_db_instance" "this" {
  identifier     = "${var.project}-${var.env}-postgres"
  engine         = "postgres"
  engine_version = "16.3"

  instance_class        = var.instance_class
  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.allocated_storage * 2
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.master.result

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  multi_az                = var.env == "prod"
  publicly_accessible     = false
  backup_retention_period = var.env == "prod" ? 7 : 1
  skip_final_snapshot     = var.env != "prod"
  final_snapshot_identifier = var.env == "prod" ? "${var.project}-${var.env}-final-snapshot" : null
  deletion_protection     = var.env == "prod"

  performance_insights_enabled = var.env == "prod"

  tags = merge(var.tags, { Name = "${var.project}-${var.env}-postgres" })
}

# ── Store credentials in SSM Parameter Store ─────────────────
resource "aws_ssm_parameter" "db_host" {
  name  = "/${var.project}/${var.env}/database/host"
  type  = "String"
  value = aws_db_instance.this.address
  tags  = var.tags
}

resource "aws_ssm_parameter" "db_password" {
  name  = "/${var.project}/${var.env}/database/password"
  type  = "SecureString"
  value = random_password.master.result
  tags  = var.tags
}

resource "aws_ssm_parameter" "db_connection_url" {
  name  = "/${var.project}/${var.env}/database/url"
  type  = "SecureString"
  value = "postgresql://${var.db_username}:${random_password.master.result}@${aws_db_instance.this.address}:5432/${var.db_name}"
  tags  = var.tags
}
