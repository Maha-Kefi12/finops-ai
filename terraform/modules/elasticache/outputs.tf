output "primary_endpoint" {
  value = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "port" {
  value = 6379
}

output "security_group_id" {
  value = aws_security_group.redis.id
}

output "redis_url" {
  description = "Full Redis URL for Celery broker"
  value       = "redis://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379"
}
