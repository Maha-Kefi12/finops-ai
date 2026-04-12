aws_region   = "us-east-1"
environment  = "prod"
project_name = "finops-ai"

# ── Networking ──
vpc_cidr = "10.0.0.0/16"
az_count = 3

# ── EKS ──
kubernetes_version = "1.30"
app_instance_types = ["m6i.large"]
app_desired_size   = 3
app_min_size       = 2
app_max_size       = 8
enable_gpu_nodes   = true
gpu_instance_types = ["g5.xlarge"]

# ── RDS ──
rds_instance_class    = "db.r6g.large"
rds_allocated_storage = 100

# ── Redis ──
redis_node_type = "cache.r6g.large"
