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
        "best_practices": "Use ALB with auto-scaling. Implement health checks. Use Fargate Spot for batch. Use Graviton2 for 20% savings",
        "waste_elimination": [
            "Delete idle ECS services with desiredCount=0 for 14+ days",
            "Remove unused task definitions (keep last 3 revisions)",
            "Monitor tasks with 0 network activity — possible zombie containers",
            "Use Fargate Spot for fault-tolerant workloads (70% savings)",
            "Consolidate multiple small services onto shared ALB target groups"
        ]
    },

    "ECS_EC2": {
        "service_name": "Amazon ECS on EC2",
        "right_sizing": {
            "cluster_utilization": "Target 70-80% cluster CPU/memory reservation. Below 50% = over-provisioned cluster",
            "container_sizing": "Monitor actual vs reserved CPU/memory per task. Over-reserved containers waste cluster capacity",
            "instance_selection": "Use Graviton (c7g, m7g) for 20-40% savings. Use Spot for worker nodes (70% discount)"
        },
        "capacity_providers": {
            "description": "Use Capacity Providers to mix On-Demand (base) + Spot (burst)",
            "strategy": "Base: On-Demand at 60% of steady-state. Burst: Spot for remaining capacity",
            "auto_scaling": "Enable managed scaling with target 70% capacity utilization"
        },
        "waste_elimination": [
            "Cluster with <50% CPU reservation = over-provisioned, reduce instance count",
            "Empty EC2 instances in cluster (no tasks scheduled) = terminate",
            "Container instances running outdated AMI = replace with optimized AMI",
            "Services with desiredCount=0 for 30+ days = delete"
        ],
        "best_practices": "Use Bottlerocket OS (15% faster startup). Enable container insights. Use service auto-scaling with target tracking"
    },

    "EKS": {
        "service_name": "Amazon Elastic Kubernetes Service (EKS)",
        "cluster_costs": {
            "control_plane": "$0.10/hour per cluster ($73/month). Cannot reduce. Consolidate workloads to fewer clusters",
            "data_plane": "Worker node EC2/Fargate costs + EBS storage + data transfer",
            "hidden_costs": "CoreDNS, kube-proxy, VPC CNI, EBS CSI driver, ALB Ingress Controller, CloudWatch logs"
        },
        "right_sizing": {
            "node_sizing": "Target 65-80% CPU and memory allocation across nodes. Below 50% = over-provisioned",
            "pod_requests_limits": {
                "description": "Pod requests reserve cluster capacity. Over-requesting wastes nodes",
                "best_practice": "Set requests to P95 actual usage. Set limits to 2x requests. Use VPA (Vertical Pod Autoscaler) to auto-tune",
                "common_waste": "Default 250m CPU + 256Mi memory requests on low-traffic pods wastes 60-80% of reserved capacity"
            },
            "node_groups": {
                "general": "m7g.xlarge (Graviton) for mixed workloads — 20-40% cheaper than m5.xlarge",
                "compute": "c7g instances for CPU-bound pods",
                "memory": "r7g instances for memory-bound pods (Redis, Java apps)",
                "gpu": "g5 instances for ML inference. Use Spot for training jobs"
            }
        },
        "cost_optimization": {
            "karpenter": "Use Karpenter instead of Cluster Autoscaler — faster scaling, better bin-packing, automatic Spot diversification",
            "spot_instances": "Use Spot for stateless workloads (70% savings). Configure pod disruption budgets. Diversify across 10+ instance types",
            "fargate_profiles": "Use Fargate for batch/cron jobs — no node management, pay per pod. But 20-30% more expensive for sustained loads",
            "savings_plans": "Compute Savings Plans apply to EKS EC2 nodes. Commit to 70% of baseline capacity"
        },
        "autoscaling": {
            "HPA": "Horizontal Pod Autoscaler — scale pods by CPU/memory/custom metrics. Target 60-70% utilization",
            "VPA": "Vertical Pod Autoscaler — auto-tune pod requests/limits. Run in recommendation mode first",
            "Karpenter": "Node-level autoscaler — provisions right-sized nodes based on pending pod requirements. Removes empty nodes automatically",
            "KEDA": "Event-driven autoscaler — scale to zero for queue-based workloads (SQS, Kafka). Massive savings for batch"
        },
        "networking": {
            "ALB_Ingress": "Use single ALB with Ingress rules vs multiple LoadBalancer services (save $16/month per eliminated LB)",
            "internal_traffic": "Use ClusterIP services for internal communication (free). Avoid LoadBalancer type for internal services",
            "VPC_CNI": "Monitor IP address consumption. Use prefix delegation mode for dense node packing"
        },
        "storage": {
            "EBS_CSI": "Use gp3 volumes (20% cheaper than gp2). Set appropriate size — PVCs default to 20Gi but many need <5Gi",
            "EFS_CSI": "Shared storage for ReadWriteMany. Enable IA lifecycle (92% savings on cold files)",
            "ephemeral": "Use emptyDir for scratch space (free, lost on pod restart). Don't use PVCs for temp data"
        },
        "waste_elimination": [
            "Idle clusters ($73/month control plane even with 0 nodes) — delete unused clusters",
            "Orphaned PVCs after StatefulSet deletion — delete unbound PersistentVolumeClaims",
            "Over-provisioned node groups with <50% utilization — consolidate or downsize",
            "Pods in CrashLoopBackOff consuming resources — fix or remove",
            "Unused namespaces with idle deployments — scale to 0 or delete",
            "Dev/staging clusters running 24x7 — schedule node scale-down after hours (65% savings)",
            "Multiple LoadBalancer services — consolidate to single ALB Ingress ($16/month each)"
        ],
        "monitoring": {
            "cost_allocation": "Use Kubecost or OpenCost for per-namespace/team cost attribution",
            "metrics": "Monitor node_cpu_utilization, node_memory_utilization, pod_cpu_request_vs_actual",
            "alerts": "Alert on: node utilization <50% for 7+ days, unschedulable pods, PVC >80% full"
        }
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
    },

    "API_Gateway": {
        "service_name": "Amazon API Gateway",
        "pricing": {
            "REST_API": "$3.50/million requests (first 333M). Cache: $0.02-$3.80/hr depending on size",
            "HTTP_API": "$1.00/million requests (71% cheaper than REST). Use for simple proxy/Lambda integrations",
            "WebSocket": "$1.00/million connection-minutes + $1.00/million messages"
        },
        "right_sizing": {
            "choose_http_vs_rest": "HTTP API is 71% cheaper. Use REST only if you need: request validation, WAF, API keys, usage plans, caching",
            "caching": "Enable API cache for GET endpoints. 0.5GB cache = $0.02/hr ($14/month). Reduces Lambda invocations by 80-95%",
            "throttling": "Set throttle limits to prevent runaway costs. Default 10k/s burst, 5k/s sustained"
        },
        "waste_elimination": [
            "Delete unused API stages (each stage has independent caching costs)",
            "Remove APIs with 0 requests for 30+ days",
            "Disable caching on stages that don't benefit (write-heavy endpoints)",
            "Migrate REST APIs to HTTP APIs where possible (71% savings)"
        ],
        "best_practices": "Use HTTP API for Lambda proxy. Enable request/response compression. Set appropriate timeout (29s max). Use Lambda authorizers instead of IAM for public APIs"
    },

    "Route53": {
        "service_name": "Amazon Route 53 (DNS)",
        "pricing": {
            "hosted_zone": "$0.50/month per hosted zone",
            "queries": "$0.40/million for standard queries. $0.60/million for latency-based/geo/failover",
            "health_checks": "$0.50-$2.00/month per check (depending on type)"
        },
        "optimization": {
            "consolidate_zones": "Merge hosted zones where possible ($0.50/month each)",
            "ttl_tuning": "Increase TTL for stable records (3600s+) to reduce query volume and cost",
            "health_checks": "Delete unused health checks. Use CloudWatch alarms instead of HTTP health checks where possible ($0.10 vs $0.75/month)"
        }
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# SERVERLESS SERVICES
# ═══════════════════════════════════════════════════════════════════════════

SERVERLESS_BEST_PRACTICES = {
    "Lambda": {
        "service_name": "AWS Lambda",
        "pricing": {
            "requests": "$0.20/million invocations",
            "duration": "$0.0000166667/GB-second (x86). $0.0000133334/GB-second (ARM/Graviton — 20% cheaper)",
            "free_tier": "1M requests + 400k GB-seconds/month (perpetual)"
        },
        "right_sizing": {
            "memory_tuning": "Sweet spot 1024-1792 MB for most functions. More memory = more CPU = faster execution = sometimes cheaper overall",
            "power_tuning": "Use AWS Lambda Power Tuning tool to find optimal memory/cost balance per function",
            "arm64_graviton": "20% cheaper per GB-second. Use for all new functions unless x86 native dependency required",
            "provisioned_concurrency": "$0.0000041667/GB-second idle. Use ONLY for sub-100ms latency SLA. Otherwise cold starts are fine"
        },
        "waste_elimination": [
            "Functions with 0 invocations for 30+ days — delete or archive",
            "Over-provisioned memory: actual usage <30% of allocated — reduce memory",
            "Provisioned concurrency on dev/test functions — remove (use on-demand)",
            "Excessive CloudWatch log retention — set to 7-30 days for non-prod ($0.50/GB ingestion)",
            "Duplicate functions across regions — consolidate to single region if latency allows"
        ],
        "architecture": {
            "cold_starts": "Keep functions warm with scheduled pings only if SLA requires <100ms. Otherwise accept cold starts (saves provisioned concurrency cost)",
            "connection_pooling": "Use RDS Proxy ($0.015/vCPU-hour) to avoid connection exhaustion. Cheaper than scaling RDS",
            "step_functions": "Orchestrate multiple Lambdas via Step Functions instead of chaining (better error handling, cheaper retries)"
        }
    },

    "Step_Functions": {
        "service_name": "AWS Step Functions",
        "pricing": {
            "standard": "$0.025/1000 state transitions. Each step = 1 transition. 4000 free/month",
            "express": "$0.000001/request + duration-based ($0.00001667/GB-second). 80-90% cheaper for high-volume"
        },
        "optimization": {
            "choose_express_vs_standard": "Express: high-volume (>10k/day), <5min duration, idempotent. Standard: long-running, need exactly-once, audit trail",
            "reduce_transitions": "Combine sequential Lambda calls into single function to reduce transition count",
            "parallel_execution": "Use Parallel state to run branches concurrently — faster and same cost per transition"
        },
        "waste_elimination": [
            "Unused state machines with 0 executions for 30+ days — delete",
            "Standard workflows for simple sequences — migrate to Express (90% savings)",
            "Excessive Wait states — use EventBridge Scheduler instead (cheaper for long delays)"
        ]
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# MESSAGING & STREAMING SERVICES
# ═══════════════════════════════════════════════════════════════════════════

MESSAGING_BEST_PRACTICES = {
    "SQS": {
        "service_name": "Amazon SQS (Simple Queue Service)",
        "pricing": {
            "standard": "$0.40/million requests (first 1M free/month)",
            "fifo": "$0.50/million requests. Use ONLY when strict ordering/exactly-once required",
            "request_batching": "BatchSendMessage/BatchReceiveMessage: 10 messages = 1 request. 10x cost reduction"
        },
        "optimization": {
            "long_polling": "Set ReceiveMessageWaitTimeSeconds=20 to reduce empty receives (60-80% fewer requests)",
            "batch_operations": "Always use batch send/receive/delete (10 msgs per request). Single-message operations waste 10x cost",
            "visibility_timeout": "Set to 6x average processing time. Too short = duplicate processing = double cost",
            "dead_letter_queue": "Route failed messages to DLQ after 3 retries. Prevents infinite reprocessing cost"
        },
        "waste_elimination": [
            "Queues with 0 messages for 30+ days — delete",
            "FIFO queues used where Standard suffices — switch to Standard (20% cheaper)",
            "High ApproximateNumberOfMessagesNotVisible = slow consumers — fix or scale consumers"
        ]
    },

    "SNS": {
        "service_name": "Amazon SNS (Simple Notification Service)",
        "pricing": {
            "publish": "$0.50/million publishes",
            "deliveries": "HTTP/S: $0.06/million. SQS: free. Lambda: free. Email: $2/100k. SMS: $0.00645/msg (US)",
            "free_tier": "1M publishes + 100k HTTP deliveries/month"
        },
        "optimization": {
            "filter_policies": "Use message filtering at SNS (free) instead of filtering in Lambda/consumer (saves invocation cost)",
            "fanout_pattern": "SNS→SQS fanout is free (SQS delivery). Cheaper than individual Lambda invocations",
            "batch_publish": "Use PublishBatch (up to 10 messages per request) to reduce API call cost"
        },
        "waste_elimination": [
            "Topics with 0 subscribers — delete",
            "Unused subscriptions (endpoint returning errors) — remove",
            "SMS notifications where email/push suffices — switch delivery channel"
        ]
    },

    "Kinesis": {
        "service_name": "Amazon Kinesis Data Streams",
        "pricing": {
            "on_demand": "$0.04/hr/shard + $0.08/GB write. Auto-scales. Use for variable/unknown workloads",
            "provisioned": "$0.015/shard-hour (~$11/shard/month) + $0.014/million PUT units. Manual scaling",
            "extended_retention": "Default 24hrs (free). 7 days: $0.015/shard-hour. 365 days: $0.023/shard-hour"
        },
        "optimization": {
            "shard_right_sizing": "Each shard: 1MB/s write, 2MB/s read. Monitor IncomingBytes to right-size. Over-sharded = wasted $11/shard/month",
            "on_demand_vs_provisioned": "On-demand: variable traffic, no ops. Provisioned: steady traffic, 60% cheaper at scale",
            "enhanced_fan_out": "$0.013/shard-hour + $0.015/GB read. Use only when consumer count >2 or need <200ms latency",
            "consider_alternatives": "For <1MB/s: use SQS (10x cheaper). For ETL: use Kinesis Firehose (no shard management)"
        },
        "waste_elimination": [
            "Streams with 0 PutRecord for 7+ days — delete or switch to on-demand",
            "Over-sharded streams (IncomingBytes <30% capacity) — reduce shard count",
            "Extended retention enabled but no consumer reads old data — reduce to 24hr default"
        ]
    },

    "EventBridge": {
        "service_name": "Amazon EventBridge",
        "pricing": {
            "custom_events": "$1.00/million events published",
            "aws_events": "Free (CloudTrail, EC2 state changes, etc.)",
            "schema_discovery": "$0.10/million events ingested for schema discovery"
        },
        "optimization": "Use specific event patterns to filter at source. Disable schema discovery in production. Use DLQ for failed targets."
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# ANALYTICS & ML SERVICES
# ═══════════════════════════════════════════════════════════════════════════

ANALYTICS_BEST_PRACTICES = {
    "EMR": {
        "service_name": "Amazon EMR (Elastic MapReduce)",
        "pricing": {
            "ec2_mode": "EC2 instance cost + EMR surcharge (varies by instance type, ~15-25% on top)",
            "serverless": "Pay per vCPU-hour + memory-hour. No cluster management. Use for intermittent Spark jobs",
            "eks_mode": "Run Spark on EKS. Share cluster with other workloads. Best for Kubernetes-native orgs"
        },
        "optimization": {
            "spot_instances": "Use Spot for task nodes (70% savings). Keep master + core on On-Demand for stability",
            "auto_scaling": "Use managed scaling for task nodes. Set min/max instances. Target 70% YARN utilization",
            "transient_clusters": "Launch cluster → run job → terminate. Avoid persistent clusters for batch workloads (50-80% savings)",
            "graviton": "Use m7g/c7g instances for 20-40% better price-performance"
        },
        "waste_elimination": [
            "Idle clusters running 24x7 for batch jobs — use transient clusters",
            "Over-provisioned master nodes — use smallest instance that fits (m5.xlarge usually sufficient)",
            "Persistent clusters at <30% YARN utilization — downsize or switch to transient"
        ]
    },

    "Glue": {
        "service_name": "AWS Glue (ETL)",
        "pricing": {
            "etl_jobs": "$0.44/DPU-hour. 1 DPU = 4 vCPU + 16GB. Minimum 2 DPUs per job",
            "crawler": "$0.44/DPU-hour for catalog crawling. Minimize frequency",
            "data_catalog": "Free for first 1M objects. $1/100k objects after"
        },
        "optimization": {
            "right_size_dpus": "Start with 2 DPUs, scale up only if needed. Monitor job metrics to find optimal DPU count",
            "job_bookmarks": "Enable to process only new data (avoid reprocessing entire dataset)",
            "partition_pruning": "Partition data by date/key. Glue reads only relevant partitions (90% less data scanned)",
            "glue_flex": "Use Flex execution class for non-urgent ETL (35% cheaper, may start with delay)"
        },
        "waste_elimination": [
            "Jobs that haven't run in 30+ days — delete",
            "Crawlers running hourly on static data — reduce to daily or weekly",
            "Development endpoints running 24x7 — use Glue Studio notebooks instead (free when idle)"
        ]
    },

    "Athena": {
        "service_name": "Amazon Athena (Serverless SQL)",
        "pricing": {
            "per_query": "$5.00/TB scanned. Minimum 10MB per query",
            "provisioned": "DPU-based pricing for reserved capacity"
        },
        "optimization": {
            "columnar_format": "Convert CSV/JSON to Parquet/ORC (90% less data scanned = 90% cheaper queries)",
            "partitioning": "Partition by date/region/category. Query only relevant partitions. 10-100x cost reduction",
            "compression": "Compress Parquet with Snappy/Zstd (30-50% less data scanned)",
            "ctas_views": "Use CREATE TABLE AS to materialize expensive queries. Query result table instead"
        }
    },

    "SageMaker": {
        "service_name": "Amazon SageMaker (ML)",
        "pricing": {
            "notebooks": "ml.t3.medium $0.05/hr. STOP when not in use — notebooks bill while running",
            "training": "On-Demand: varies by instance. Spot training: up to 90% savings for interruptible jobs",
            "inference": "Real-time endpoints: per-instance-hour. Serverless: per-invocation + duration. Batch: per-instance-hour"
        },
        "optimization": {
            "notebook_lifecycle": "Auto-stop notebooks after 1hr idle. Use lifecycle configs to enforce",
            "spot_training": "Use managed Spot training for 60-90% savings. Set MaxWaitTimeInSeconds for SLA",
            "inference_right_sizing": "Monitor ModelLatency and Invocations. Use ml.inf1 (Inferentia) for 70% cheaper inference on supported models",
            "multi_model_endpoints": "Host multiple models on single endpoint (share instance cost across models)",
            "serverless_inference": "Use for <1 req/sec workloads. Scales to 0 (no cost when idle). Max 6MB payload"
        },
        "waste_elimination": [
            "Running notebook instances not in use — stop immediately ($0.05-$4.90/hr wasted)",
            "Real-time endpoints with <1 invocation/hr — switch to Serverless inference",
            "Training jobs using On-Demand for non-urgent experiments — switch to Spot (90% savings)",
            "Old model artifacts in S3 — delete unused models (storage cost)"
        ]
    },

    "Redshift": {
        "service_name": "Amazon Redshift (Data Warehouse)",
        "right_sizing": {
            "cluster_utilization": "Target 60-80% CPU. Below 40% for 14+ days = over-provisioned. Downsize or pause",
            "node_selection": "ra3.xlarge ($1.086/hr) for <500GB. ra3.4xlarge for 500GB-2TB. ra3.16xlarge for >2TB",
            "concurrency_scaling": "Free 1hr/day per cluster. Use for peak bursts. Disable if not needed ($0.25/credit-hour)"
        },
        "cost_optimization": {
            "reserved_nodes": "Up to 75% off On-Demand (3-year). Commit to 70% of steady-state capacity",
            "serverless": "Pay per RPU-hour ($0.375/RPU-hour). Auto-scales. Use for variable/intermittent query workloads",
            "pause_resume": "Pause clusters during off-hours (50% savings). Automate with Lambda/EventBridge schedule",
            "spectrum": "Query S3 data directly ($5/TB scanned). Offload cold data to S3, keep hot data in Redshift"
        },
        "waste_elimination": [
            "Clusters paused for 30+ days — consider terminating and using Serverless",
            "Unused snapshots consuming storage — delete (charged at S3 rates)",
            "Low concurrency scaling usage — disable to avoid accidental charges"
        ]
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# SECURITY & COMPLIANCE SERVICES
# ═══════════════════════════════════════════════════════════════════════════

SECURITY_BEST_PRACTICES = {
    "WAF": {
        "service_name": "AWS WAF (Web Application Firewall)",
        "pricing": {
            "web_acl": "$5/month per Web ACL",
            "rules": "$1/month per rule",
            "requests": "$0.60/million requests inspected"
        },
        "optimization": {
            "consolidate_acls": "Use single Web ACL with multiple rule groups vs multiple ACLs ($5 each)",
            "rate_based_rules": "Use rate-based rules to block DDoS instead of expensive third-party solutions",
            "managed_rules": "AWS Managed Rules are $1-20/month each. Cheaper than building custom rules"
        }
    },

    "GuardDuty": {
        "service_name": "Amazon GuardDuty (Threat Detection)",
        "pricing": {
            "cloudtrail_analysis": "$4.00/million events (first 500M), then $1.00-$0.50/million",
            "vpc_flow_logs": "$1.00/GB (first 500GB), then $0.50-$0.25/GB",
            "dns_logs": "$1.00/million queries (first 500M)"
        },
        "optimization": "Enable in all accounts/regions (required for compliance). Use delegated admin for consolidated billing. Disable optional features (S3/EKS/RDS protection) in dev accounts if not needed."
    },

    "Config": {
        "service_name": "AWS Config (Configuration Compliance)",
        "pricing": {
            "recording": "$0.003/configuration item recorded",
            "rules": "$0.001/rule evaluation/region. Can add up with many rules across regions"
        },
        "optimization": {
            "limit_resource_types": "Record only needed resource types (not ALL). Reduces recording cost by 60-80%",
            "reduce_rule_evaluations": "Use periodic (daily) rules instead of change-triggered for non-critical checks",
            "single_aggregator": "Use single aggregator account instead of per-account conformance packs"
        }
    },

    "Secrets_Manager": {
        "service_name": "AWS Secrets Manager",
        "pricing": {
            "per_secret": "$0.40/month per secret",
            "api_calls": "$0.05/10k API calls"
        },
        "optimization": "Use SSM Parameter Store SecureString (free for standard, $0.05/10k for advanced) for non-rotating secrets. Reserve Secrets Manager for secrets that need auto-rotation."
    },

    "KMS": {
        "service_name": "AWS Key Management Service",
        "pricing": {
            "customer_managed_keys": "$1/month per key + $0.03/10k requests",
            "aws_managed_keys": "Free key + $0.03/10k requests",
            "symmetric_api": "$0.03/10k encrypt/decrypt calls"
        },
        "optimization": "Use AWS managed keys where possible (free). Consolidate customer-managed keys. Delete unused keys after mandatory 7-30 day waiting period."
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# MANAGEMENT & MONITORING SERVICES
# ═══════════════════════════════════════════════════════════════════════════

MANAGEMENT_BEST_PRACTICES = {
    "CloudWatch": {
        "service_name": "Amazon CloudWatch",
        "pricing": {
            "metrics": "First 10 custom metrics free. Then $0.30/metric/month. Detailed (1-min): $0.30/metric",
            "dashboards": "$3/month per dashboard (first 3 free)",
            "logs_ingestion": "$0.50/GB ingested",
            "logs_storage": "$0.03/GB/month stored. MAJOR COST DRIVER — set retention policies",
            "alarms": "$0.10/alarm/month (standard). $0.30/alarm/month (high-resolution)"
        },
        "optimization": {
            "log_retention": "Set retention to 7d for dev, 30d for staging, 90d for prod. Default is FOREVER (infinite cost accumulation)",
            "log_level": "Use WARN/ERROR in production (not DEBUG). DEBUG logging can 10x log volume and cost",
            "metric_filters": "Use metric filters instead of CloudWatch Logs Insights for repeated queries (cheaper)",
            "contributor_insights": "$0.02/rule/month per log group. Disable if not actively used",
            "embedded_metrics": "Use EMF (Embedded Metric Format) to publish metrics from logs (no extra API calls)"
        },
        "waste_elimination": [
            "Log groups with 'never expire' retention — set appropriate retention (biggest CW cost driver)",
            "Unused dashboards — delete ($3/month each)",
            "Alarms in INSUFFICIENT_DATA state — fix or delete",
            "Custom metrics not consumed by any alarm or dashboard — stop publishing",
            "Detailed monitoring on dev/test instances — switch to basic (5-min, free)"
        ]
    },

    "Systems_Manager": {
        "service_name": "AWS Systems Manager",
        "pricing": {
            "parameter_store": "Standard: free (up to 10k params). Advanced: $0.05/param/month",
            "session_manager": "Free (replaces SSH bastion hosts — saves $30+/month per bastion)",
            "patch_manager": "Free for OS patching. $0.02/node/hour for application patching"
        },
        "optimization": "Use Parameter Store Standard tier (free) instead of Secrets Manager for non-rotating config. Use Session Manager instead of bastion hosts."
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
        **SERVERLESS_BEST_PRACTICES,
        **MESSAGING_BEST_PRACTICES,
        **ANALYTICS_BEST_PRACTICES,
        **SECURITY_BEST_PRACTICES,
        **MANAGEMENT_BEST_PRACTICES,
    }
    return all_practices.get(service_name, {})


def get_all_best_practices_text() -> str:
    """Get all best practices as formatted text for LLM context."""
    all_practices = {
        "compute": COMPUTE_BEST_PRACTICES,
        "database": DATABASE_BEST_PRACTICES,
        "storage": STORAGE_BEST_PRACTICES,
        "networking": NETWORKING_BEST_PRACTICES,
        "serverless": SERVERLESS_BEST_PRACTICES,
        "messaging": MESSAGING_BEST_PRACTICES,
        "analytics": ANALYTICS_BEST_PRACTICES,
        "security": SECURITY_BEST_PRACTICES,
        "management": MANAGEMENT_BEST_PRACTICES,
    }
    import json
    return json.dumps(all_practices, indent=2)


__all__ = [
    "COMPUTE_BEST_PRACTICES",
    "DATABASE_BEST_PRACTICES",
    "STORAGE_BEST_PRACTICES",
    "NETWORKING_BEST_PRACTICES",
    "SERVERLESS_BEST_PRACTICES",
    "MESSAGING_BEST_PRACTICES",
    "ANALYTICS_BEST_PRACTICES",
    "SECURITY_BEST_PRACTICES",
    "MANAGEMENT_BEST_PRACTICES",
    "get_best_practices_for_service",
    "get_all_best_practices_text",
]
