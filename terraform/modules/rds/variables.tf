variable "project"     { type = string }
variable "env"         { type = string }
variable "vpc_id"      { type = string }

variable "private_subnet_ids" {
  description = "Subnets for the DB subnet group"
  type        = list(string)
}

variable "allowed_security_group_ids" {
  description = "Security groups allowed to connect on 5432"
  type        = list(string)
  default     = []
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "allocated_storage" {
  description = "Storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "finops"
}

variable "db_username" {
  description = "Master username"
  type        = string
  default     = "finops_admin"
}

variable "tags" {
  type    = map(string)
  default = {}
}
