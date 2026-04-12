variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name used as prefix for all resources"
  type        = string
  default     = "finops-ai"
}

# ── Networking ──────────────────────────────────────────────────────────
variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones"
  type        = number
  default     = 2
}

# ── EKS ─────────────────────────────────────────────────────────────────
variable "kubernetes_version" {
  description = "EKS Kubernetes version"
  type        = string
  default     = "1.30"
}

variable "app_instance_types" {
  description = "EC2 instance types for application node group"
  type        = list(string)
  default     = ["t3.large"]
}

variable "app_desired_size" {
  type    = number
  default = 2
}

variable "app_min_size" {
  type    = number
  default = 1
}

variable "app_max_size" {
  type    = number
  default = 4
}

variable "enable_gpu_nodes" {
  description = "Enable GPU node group for Ollama LLM inference"
  type        = bool
  default     = false
}

variable "gpu_instance_types" {
  description = "GPU instance types for Ollama"
  type        = list(string)
  default     = ["g5.xlarge"]
}

# ── RDS ─────────────────────────────────────────────────────────────────
variable "rds_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "rds_allocated_storage" {
  description = "RDS storage in GB"
  type        = number
  default     = 20
}

# ── ElastiCache ─────────────────────────────────────────────────────────
variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.micro"
}
