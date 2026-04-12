aws_region   = "us-east-1"
environment  = "dev"
project_name = "finops-ai"

# ── Networking ──
vpc_cidr = "10.0.0.0/16"
az_count = 2

# ── EKS ──
kubernetes_version = "1.30"
app_instance_types = ["t3.large"]
app_desired_size   = 2
app_min_size       = 1
app_max_size       = 4
enable_gpu_nodes   = false
gpu_instance_types = ["g5.xlarge"]

# ── RDS ──
rds_instance_class    = "db.t3.micro"
rds_allocated_storage = 20

# ── Redis ──
redis_node_type = "cache.t3.micro"
