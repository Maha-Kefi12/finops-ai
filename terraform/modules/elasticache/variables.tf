variable "project" { type = string }
variable "env" { type = string }
variable "vpc_id" { type = string }

variable "subnet_group_name" {
  description = "ElastiCache subnet group name"
  type        = string
}

variable "allowed_security_group_ids" {
  description = "Security groups allowed to connect on 6379"
  type        = list(string)
  default     = []
}

variable "node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "tags" {
  type    = map(string)
  default = {}
}
