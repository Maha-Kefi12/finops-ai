variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "cluster_role_arn" {
  type = string
}

variable "node_role_arn" {
  type = string
}

variable "ebs_csi_role_arn" {
  type = string
}

variable "kubernetes_version" {
  type    = string
  default = "1.29"
}

# ── App Node Group ──────────────────────────────────────────────────────
variable "app_instance_types" {
  type    = list(string)
  default = ["t3.large"]
}

variable "app_capacity_type" {
  type    = string
  default = "ON_DEMAND"
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

# ── GPU Node Group (Ollama) ─────────────────────────────────────────────
variable "enable_gpu_nodes" {
  type    = bool
  default = false
}

variable "gpu_instance_types" {
  type    = list(string)
  default = ["g5.xlarge"]
}

variable "gpu_desired_size" {
  type    = number
  default = 1
}

variable "gpu_max_size" {
  type    = number
  default = 2
}
