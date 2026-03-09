output "endpoint" {
  description = "RDS endpoint (host:port)"
  value       = aws_db_instance.this.endpoint
}

output "address" {
  description = "RDS hostname"
  value       = aws_db_instance.this.address
}

output "port" {
  description = "RDS port"
  value       = aws_db_instance.this.port
}

output "db_name" {
  description = "Database name"
  value       = aws_db_instance.this.db_name
}

output "security_group_id" {
  description = "RDS security group ID"
  value       = aws_security_group.rds.id
}

output "password" {
  description = "RDS master password"
  value       = random_password.master.result
  sensitive   = true
}

output "connection_url_ssm_arn" {
  description = "SSM parameter ARN for connection URL"
  value       = aws_ssm_parameter.db_connection_url.arn
}

output "master_password" {
  description = "Generated master password (sensitive)"
  value       = random_password.master.result
  sensitive   = true
}
