"""
AWS FinOps Best Practices Knowledge Base
=========================================
Comprehensive cost optimization guidelines for all AWS services.
Used as context for LLM recommendation generation.

Last Updated: March 2026
Sources: AWS Well-Architected Framework, AWS FinOps Best Practices, 
         AWS Cost Optimization Hub, FinOps Foundation
"""

# ═══════════════════════════════════════════════════════════════════════════
# COMPUTE SERVICES
# ═══════════════════════════════════════════════════════════════════════════

COMPUTE_BEST_PRACTICES = {
    "EC2": {
        "service_name": "Amazon EC2 (Elastic Compute Cloud)",
        "right_sizing": {
            "description": "Match instance types to workload requirements",
            "target_metrics": {
                "cpu_utilization": {
                    "minimum_average": 60,
                    "maximum_average": 70,
                    "peak_threshold": 85,
                    "measurement_period": "30 days minimum"
                },
                "memory_utilization": {
                    "minimum_average": 70,
                    "maximum_average": 80,
                    "peak_threshold": 90
                }
            },
            "optimization_strategies": [
                "CPU <40% for 30+ days → Downsize to next smaller instance type (50% savings per tier)",
                "CPU >85% sustained → Upsize or implement auto-scaling (prevent performance degradation)",
                "Memory pressure >80% → Move to memory-optimized instance family (r5, r6i, r7g)",
                "Burstable instances (t3/t4g) with sustained high CPU → Move to m5/m6i (30-40% more expensive but prevents throttling)"
            ],
            "instance_family_guidance": {
                "General Purpose (t3, m5, m6i, m7g)": "Web servers, app servers, development. Use t3 for variable workloads, m5/m6i for steady state",
                "Compute Optimized (c5, c6i, c7g)": "Batch processing, high-performance web servers. Use for CPU-intensive with <50% memory usage",
                "Memory Optimized (r5, r6i, r7g)": "In-memory databases, caching, analytics. Use when memory >70% but CPU <60%",
                "Storage Optimized (i3, i4i, d2)": "NoSQL databases, data warehousing. Use for >20k IOPS requirements",
                "Accelerated Computing (p3, p4, g4)": "ML training, graphics rendering. Use Spot Instances for 70% savings on interruptible jobs"
            },
            "graviton_migration": {
                "description": "ARM-based Graviton processors offer 20-40% better price-performance",
                "instance_types": "t4g, m7g, c7g, r7g",
                "typical_savings": "20-40% vs comparable x86 instances",
                "recommendation": "Always evaluate Graviton for new workloads"
            }
        },
        "purchasing_options": {
            "on_demand": "Short-term, unpredictable workloads. Cost baseline: 100%. Use only for <5% of steady-state capacity",
            "savings_plans": {
                "discount": "Up to 66% off On-Demand",
                "flexibility": "Can change instance family, size, OS, tenancy, region",
                "recommendation": "Commit to 70-80% of baseline usage from Cost Explorer analysis"
            },
            "reserved_instances": {
                "discount": "Up to 72-75% off On-Demand",
                "status": "Legacy model - Savings Plans preferred for new purchases",
                "marketplace": "Can sell unused RIs on RI Marketplace (typically 5-30% loss)"
            },
            "spot_instances": {
                "discount": "70-90% off On-Demand",
                "use_cases": "Batch processing, CI/CD, ML training (with checkpoints), stateless web servers",
                "best_practices": "Diversify across instance types/AZs. Target <5% interruption rate. Enable capacity rebalancing"
            }
        },
        "auto_scaling": {
            "description": "Automatically adjust capacity based on demand. Pay only for needed capacity",
            "strategies": {
                "target_tracking": "Maintain target metric (e.g., 60% CPU). Scale when >60% for 3 min, scale down when <40% for 15 min",
                "scheduled_scaling": "Known traffic patterns (e.g., business hours only). Typical savings: 60-70% for off-hours shutdown",
                "predictive_scaling": "ML-based forecasting of future demand. Reduces over-provisioning"
            },
            "best_practices": "Set minimum to Savings Plan commitment. Use Spot for above-baseline. Monitor and adjust quarterly"
        },
        "waste_elimination": {
            "stopped_instances": "Stopped instances still incur EBS storage costs ($8-20/month per t3.medium). Terminate if not needed",
            "idle_instances": "CPU <2% for 14+ days → Consider terminating or stopping",
            "old_generation_instances": "t2, m4, c4 cost more/performance than t3, m5, c5 (20-30% savings potential)",
            "dev_instances_24x7": "Dev/test don't need 24x7 uptime. Implement scheduled stop/start for 65-75% savings"
        }
    },
    
    "Lambda": {
        "service_name": "AWS Lambda",
        "right_sizing": {
            "memory_allocation": {
                "description": "Memory determines CPU and network bandwidth",
                "range": "128 MB to 10,240 MB (10 GB)",
                "optimization_approach": "Start with 512 MB. Use AWS Lambda Power Tuning tool. Memory sweet spot often 1024-1792 MB",
                "insight": "Sometimes more memory = faster execution = cheaper overall cost despite higher per-ms pricing"
            },
            "architecture_choice": {
                "x86_64": "Default, broadest compatibility",
                "arm64_graviton2": "20% lower cost per GB-second. Use for new functions unless specific x86 dependency"
            }
        },
        "invocation_optimization": {
            "cold_starts": "First invocation has initialization latency (100-1000ms). Solutions: increase memory (speeds up), minimize dependencies, use SnapStart for Java",
            "concurrent_executions": "Monitor and limit to prevent excessive costs. Batch process if possible",
            "timeout_settings": "Set to minimum needed + 20% buffer. Set alerts on duration >80% of timeout"
        },
        "pricing_optimization": {
            "free_tier": "1M requests + 400k GB-seconds / month (permanent)",
            "cost_comparison": "Lambda <$1 for light workloads, EC2/Fargate cheaper for >20% utilization"
        },
        "best_practices": "Reuse execution context outside handler. Use env vars for config. Disable X-Ray in non-prod. Delete old versions"
    },
    
    "ECS_Fargate": {
        "service_name": "Amazon ECS on AWS Fargate",
        "right_sizing": {
            "cpu_and_memory": "Monitor via Container Insights. Right-size to 60-70% utilization. Use Fargate Spot for dev/test (70% discount)",
            "fargate_vs_ec2": {
                "Fargate": "No cluster mgmt, per-task pricing, auto-scale. ~20-30% more expensive than EC2 for sustained loads",
                "ECS_EC2": "Lower cost if >60% cluster utilization, requires cluster mgmt",
                "cost_crossover": "If cluster utilization >60%, EC2 is typically cheaper"
            }
        },
        "savings_plans": {
            "Fargate_Compute_Savings_Plan": "Up to 50% off On-Demand Fargate. Commit to 60-70% of baseline usage"
        },
        "best_practices": "Use ALB with auto-scaling. Implement health checks. Use Fargate Spot for batch. Use Graviton2 for 20% savings"
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# DATABASE SERVICES
# ═══════════════════════════════════════════════════════════════════════════

DATABASE_BEST_PRACTICES = {
    "RDS": {
        "service_name": "Amazon RDS (Relational Database Service)",
        "right_sizing": {
            "instance_sizing": {
                "target_cpu": "60-75% average, <90% P99",
                "memory_guidance": "Keep freeable memory >20% of total",
                "optimization_process": "CPU <40% for 30+ days → downsize. CPU >80% sustained → upsize. High swap → move to r5/r6i"
            },
            "storage_optimization": {
                "gp3": "General Purpose SSD (latest). $0.115/GB-month, baseline 3k IOPS @ 125MB/s. 20% cheaper than gp2. Migrate gp2→gp3",
                "gp2": "Legacy general purpose. $0.138/GB-month. IOPS scale 3/GB (min 100, max 16k). Plan to migrate to gp3",
                "io1_io2": "Provisioned IOPS. Only for >16k IOPS sustained workloads. Validate with metrics before upgrade",
                "storage_autoscaling_risk": "Can lead to runaway costs. Set maximum threshold. Alert on >50% growth/month"
            }
        },
        "multi_az": {
            "cost": "2x instance cost (double billing)",
            "use_case": "Production databases requiring high availability (99.95% uptime)",
            "optimization": "Disable for dev/test (50% savings). For staging: single-AZ + automated snapshots (RPO: 5 min, RTO: 15 min)"
        },
        "read_replicas": {
            "description": "Asynchronous copies for read scaling. Each billed as separate instance + cross-region data transfer",
            "optimization": "Monitor replica lag (<1 sec). Delete unused replicas. Use smaller instances for low-traffic replicas"
        },
        "reserved_instances": {
            "discount": "Up to 69% off On-Demand (3-year All Upfront)",
            "how_to_purchase": "Analyze 90 days of usage. Identify steady-state dbs. Commit to 70-80% of baseline"
        },
        "engine_specific": {
            "PostgreSQL": "Enable log_statement='none' in production. Use connection pooling (PgBouncer). Tune shared_buffers to 25% RAM",
            "MySQL": "Tune innodb_buffer_pool_size to 70-80% RAM. Use InnoDB (not MyISAM). Partition large tables (>10M rows)",
            "Oracle_BYOL": "Bring Your Own License is 50-60% cheaper long-term vs License Included"
        },
        "waste_elimination": [
            "Delete stopped RDS instances (still incur storage + backup costs)",
            "Idle databases: DatabaseConnections=0 for 30+ days",
            "Delete old snapshots (>6 months for dev/test)",
            "Disable Performance Insights if not reviewed ($0.10/vCPU/day)"
        ]
    },
    
    "Aurora": {
        "service_name": "Amazon Aurora (MySQL/PostgreSQL-compatible)",
        "when_to_use_aurora": "Need >5 read replicas. Variable workloads (use Serverless v2). Global database. <30s automatic failover",
        "when_to_use_rds_instead": "Single-instance with no read scaling. Predictable stable workload. Need Oracle/SQL Server",
        "provisioned_aurora": {
            "pricing": "Instance cost + storage ($0.10/GB-month) + I/O ($0.20/million requests)",
            "optimization": "Monitor I/O requests. If high I/O cost, consider io1/io2-optimized (no I/O charges, higher instance cost)"
        },
        "aurora_serverless_v2": {
            "description": "Auto-scales capacity (0.5-128 ACU). ACU = 2 GB RAM + proportional CPU/networking",
            "cost": "$0.12/ACU-hour",
            "use_case": "Variable workloads (dev/test, intermittent apps). Apps with distinct peak/off-peak",
            "optimization": "Set minimum ACU to 50% of average. Set maximum to 150% of peak. Can pause to 0 ACU for dev/test"
        }
    },
    
    "DynamoDB": {
        "service_name": "Amazon DynamoDB (NoSQL)",
        "capacity_modes": {
            "On_Demand": "$1.25/M writes, $0.25/M reads. 5-7x more expensive than Provisioned for steady workloads. Use first 30 days, then switch",
            "Provisioned": "$0.00065/WCU-hour, $0.00013/RCU-hour. 60-85% cheaper for steady load than On-Demand",
            "reserved_capacity": "50-70% discount on Provisioned. Purchase RIs for 60-70% of baseline capacity"
        },
        "storage_optimization": {
            "standard_storage": "$0.25/GB-month",
            "infrequent_access_IA": "$0.10/GB-month (60% cheaper). Enable Standard-IA, items auto-move after 30 days inactivity",
            "breakeven": "IA reads/writes cost 25% more, but storage 60% cheaper. Breakeven around 80% cold data"
        },
        "best_practices": [
            "Partition keys: Distribute traffic evenly (avoid hot partitions)",
            "Use sparse indexes to reduce index storage costs",
            "Enable TTL (Time To Live) to auto-delete expired items (e.g., sessions)",
            "Batch write operations (BatchWriteItem) to reduce request count",
            "Use Query instead of Scan (Scan reads entire table, very expensive)",
            "Monitor ConsumedReadCapacityUnits and ConsumedWriteCapacityUnits"
        ]
    },
    
    "ElastiCache": {
        "service_name": "Amazon ElastiCache (Redis/Memcached)",
        "when_to_use": "Session storage. Caching frequently accessed data. Real-time leaderboards. Pub/Sub messaging",
        "right_sizing": {
            "memory_planning": "Keep memory usage 60-80%. If <50% for 30+ days → downsize. If >90% → upsize or add nodes",
            "cpu_monitoring": "Redis (single-threaded): Monitor primary CPU. Memcached (multi-threaded): Distributes load better"
        },
        "node_types": "Use r7g (Graviton) for 35% better price-performance vs r5/r6i",
        "reserved_nodes": "Up to 55% discount (3-year All Upfront). Purchase for production, leave dev On-Demand",
        "redis_vs_memcached": {
            "Redis": "Persistence, replication, pub/sub. Use for session storage, leaderboards. Disable persistence for ephemeral cache (saves I/O)",
            "Memcached": "Simple key-value, no persistence, multi-threaded. Use for read-heavy caching. Lower cost"
        }
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# STORAGE SERVICES
# ═══════════════════════════════════════════════════════════════════════════

STORAGE_BEST_PRACTICES = {
    "S3": {
        "service_name": "Amazon S3 (Simple Storage Service)",
        "storage_classes": {
            "S3_Standard": "$0.023/GB-month. Frequently accessed data. $0 retrieval",
            "S3_Intelligent_Tiering": "$0.023/GB-month + monitoring fee. Unknown access patterns. Auto-moves between tiers. Savings up to 95%",
            "S3_Standard_IA": "$0.0125/GB-month (46% cheaper). 30-day minimum + $0.01/GB retrieval. Infrequently accessed data",
            "S3_One_Zone_IA": "$0.01/GB-month (56% cheaper). Single AZ (data lost if AZ destroyed). Use for reproducible/non-critical data",
            "S3_Glacier_Instant": "$0.004/GB-month (83% cheaper). Millisecond retrieval. $0.03/GB retrieval. 90-day minimum",
            "S3_Glacier_Flexible": "$0.0036/GB-month (84% cheaper). 3-12hr retrieval. 90-day minimum. Long-term backups",
            "S3_Glacier_Deep_Archive": "$0.00099/GB-month (96% cheaper). 12-48hr retrieval. 180-day minimum. 7-10 year retention"
        },
        "lifecycle_policies": {
            "example": "Move to IA after 30 days → Glacier after 90 days → delete after 365 days = ~70% cost reduction",
            "best_practices": "Transition current after 30d (→IA). Transition old versions after 90d (→Glacier). Delete versions after 365d",
            "common_logs": "Intelligent-Tiering or IA → Glacier after 90d → delete after 2 years",
            "common_backups": "Standard-IA → Glacier after 90d → Deep Archive after 1 year"
        },
        "versioning_optimization": {
            "issue": "Versioned buckets keep all deleted/modified objects. Cost accumulates (1000 daily updates = 365k objects/year)",
            "solution": "Lifecycle rule: Delete noncurrent versions after 90 days"
        },
        "request_optimization": {
            "pricing": "PUT: $0.005/1000. GET: $0.0004/1000",
            "strategies": "Batch uploads. Use S3 Select (filter server-side). Cache with CloudFront. Use S3 Batch Operations"
        },
        "data_transfer_costs": {
            "inbound": "$0 (free)",
            "outbound_internet": "$0.09/GB (first 10TB/month)",
            "cloudfront": "$0 (free from S3 to CF, CF→Internet cheaper)",
            "optimization": "Use CloudFront for public content (80-90% reduction). Avoid cross-region access"
        }
    },
    
    "EBS": {
        "service_name": "Amazon EBS (Elastic Block Store)",
        "volume_types": {
            "gp3": "$0.08/GB-month. General Purpose SSD (latest). Free 3k IOPS + 125MB/s. 20% cheaper than gp2. Migrate gp2→gp3",
            "gp2": "$0.10/GB-month. Previous gen (25% more expensive). IOPS scale 3/GB. Plan migration",
            "io2_block_express": "$0.125/GB + $0.065/IOPS. Highest performance. 256k IOPS max. Only for >32k IOPS proven need",
            "st1": "$0.045/GB-month (44% cheaper). Throughput optimized HDD. 500MB/s max. Big data, warehousing, sequential access",
            "sc1": "$0.015/GB-month (81% cheaper). Cold HDD. 250MB/s max. Infrequently accessed, archives"
        },
        "right_sizing": {
            "oversized_volumes": "VolumeReadOps + WriteOps = low but size = large → Create snapshot → Create smaller volume (50-70% savings)",
            "underutilized_iops": "Provisioned IOPS >> actual usage → Reduce to 110% of P99 usage. Typical: $50-200/month/volume savings"
        },
        "waste_elimination": [
            "Delete unattached volumes (detached but still billing)",
            "Delete old snapshots (>90 days for dev/test)",
            "Archive snapshots to S3 Glacier (EBS snapshots in S3, use lifecycle)",
            "Delete orphaned snapshots for terminated instances"
        ]
    },
    
    "EFS": {
        "service_name": "Amazon EFS (Elastic File System)",
        "storage_classes": {
            "EFS_Standard": "$0.30/GB-month. Frequently accessed files",
            "EFS_Infrequent_Access": "$0.025/GB-month (92% cheaper) + $0.01/GB retrieval. Files not accessed 30+ days. Enable lifecycle policy"
        },
        "lifecycle_management": {
            "description": "Auto-move files to IA after N days inactivity (7, 14, 30, 60, 90 days)",
            "recommendation": "Set to 30 days. Typical savings: 60-80% for systems with cold data"
        },
        "throughput_modes": {
            "Bursting": "Scales with size (50 MB/s per TB). Burst to 100 MB/s. Included in storage price. Use for most workloads",
            "Provisioned": "$6/MB/s-month (expensive). Fixed throughput. Only for small systems needing high throughput",
            "Elastic": "Auto-scales. $0.03/GB-month + usage-based throughput. New default, simpler"
        }
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# NETWORKING & CONTENT DELIVERY
# ═══════════════════════════════════════════════════════════════════════════

NETWORKING_BEST_PRACTICES = {
    "Data_Transfer": {
        "service_name": "AWS Data Transfer Costs",
        "pricing": {
            "inbound": "$0 (free)",
            "outbound_internet": "First 10TB: $0.09/GB. Next 40TB: $0.085/GB. Over 150TB: $0.050/GB",
            "cross_az": "$0.02/GB total (in + out). Can be 20-40% of total bill for chatty architectures",
            "cross_region": "$0.02/GB (varies by region pair)"
        },
        "optimization": {
            "minimize_cross_az": "Use same-AZ communication. Place read replicas in same AZ. Use VPC endpoints for S3/DynamoDB. Monitor VPC Flow Logs. Savings: $500-5k/month",
            "use_cloudfront": "S3→CF free, CF→Internet cheaper than S3→Internet. Also caches, reduces origin requests",
            "vpc_endpoints": "S3/DynamoDB: $0 (free). Avoid $0.045/GB NAT Gateway cost and cross-AZ charges",
            "nat_gateway_cost": "$0.045/hour (~$32/month) + $0.045/GB processed. Optimize via VPC endpoints and single NAT for dev/test"
        }
    },
    
    "CloudFront": {
        "service_name": "Amazon CloudFront (CDN)",
        "when_to_use": "Static content (images, CSS, JS). Video streaming. Dynamic/API acceleration",
        "pricing": {
            "data_transfer": "First 10TB: $0.085/GB. Next 40TB: $0.080/GB. Over 150TB: $0.040/GB",
            "requests": "$0.0075/10k HTTP HTTPS requests",
            "s3_to_cf": "$0 (free from S3 to CloudFront)"
        },
        "optimization": {
            "price_class": "All Edges (default) vs US/Europe/Asia (10-15% cheaper) vs US/Europe Only (20-25% cheaper)",
            "cache_hit_ratio": "Target >85%. Increase TTL. Remove unnecessary query strings. Use Cache-Control headers. Enable compression"
        }
    },
    
    "Load_Balancers": {
        "ALB": "$0.0225/hour + $0.008/LCU-hour (~$16/month base). HTTP/HTTPS, path/host-based routing",
        "NLB": "$0.0225/hour + $0.006/NLCU-hour. TCP/UDP, extreme performance (<100ms). Use ALB unless need TCP/extreme perf",
        "waste_elimination": [
            "Delete ALBs with 0 targets for >14 days",
            "Consolidate: Use one ALB with multiple target groups vs multiple ALBs"
        ]
    },
    
    "Elastic_IP": {
        "cost": {
            "attached_running": "$0 (free)",
            "unattached_stopped": "$0.005/hour = $3.60/month"
        },
        "optimization": "Release unused Elastic IPs. Use only when necessary (ALB/DNS cheaper). Dev/test: use dynamic public IPs (free)"
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_best_practices_for_service(service_name: str) -> dict:
    """Get best practices for a specific AWS service."""
    all_practices = {
        **COMPUTE_BEST_PRACTICES,
        **DATABASE_BEST_PRACTICES,
        **STORAGE_BEST_PRACTICES,
        **NETWORKING_BEST_PRACTICES,
    }
    return all_practices.get(service_name, {})


def get_all_best_practices_text() -> str:
    """Get all best practices as formatted text for LLM context."""
    all_practices = {
        "compute": COMPUTE_BEST_PRACTICES,
        "database": DATABASE_BEST_PRACTICES,
        "storage": STORAGE_BEST_PRACTICES,
        "networking": NETWORKING_BEST_PRACTICES,
    }
    import json
    return json.dumps(all_practices, indent=2)


__all__ = [
    "COMPUTE_BEST_PRACTICES",
    "DATABASE_BEST_PRACTICES",
    "STORAGE_BEST_PRACTICES",
    "NETWORKING_BEST_PRACTICES",
    "get_best_practices_for_service",
    "get_all_best_practices_text",
]
