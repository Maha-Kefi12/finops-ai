"""
Real AWS resource collector using boto3.
Discovers ALL infrastructure: EC2, ECS (clusters + services + tasks), RDS, S3,
ELB + Target Groups, Lambda, DynamoDB, ElastiCache, SQS, SNS, CloudFront,
API Gateway (v1+v2), EKS, VPCs, Subnets, Security Groups, NAT Gateways,
Internet Gateways, Route Tables, CloudWatch Alarms — and infers edges between them.
"""
import os
import uuid
import logging
from typing import Dict, Any, List, Tuple, Set

logger = logging.getLogger(__name__)

# ── Estimated monthly costs by resource type (rough USD) ───────────
COST_ESTIMATES = {
    "t2.micro": 8.50, "t3.micro": 7.60, "t3.small": 15.20, "t3.medium": 30.40,
    "t3.large": 60.70, "m5.large": 70.00, "m5.xlarge": 140.00,
    "db.t3.micro": 12.50, "db.t3.small": 25.00, "db.t3.medium": 50.00,
    "db.t3.large": 100.00, "db.r5.large": 170.00,
    "nat_gateway": 32.40, "alb": 22.50, "nlb": 22.50,
    "s3_bucket": 5.00, "sqs_queue": 1.00, "sns_topic": 1.00,
    "cloudwatch_alarm": 0.50, "vpc": 0.0, "subnet": 0.0,
    "security_group": 0.0, "igw": 0.0, "route_table": 0.0,
}


def _tag_name(tags, fallback: str) -> str:
    """Extract Name tag from a list of {Key, Value} dicts."""
    if not tags:
        return fallback
    for t in tags:
        if t.get("Key") == "Name":
            return t["Value"]
    return fallback


class RealAWSCollector:
    """Discovers AWS resources and builds an architecture dict with edges."""

    def __init__(self, region: str = "us-east-1"):
        self.region = region
        try:
            import boto3
            self.session = boto3.Session(region_name=region)
        except ImportError:
            raise RuntimeError("boto3 is required for AWS discovery")

        self._services: List[Dict] = []
        self._deps: List[Dict] = []
        self._seen_ids: Set[str] = set()
        self._dep_keys: Set[str] = set()
        # Maps for cross-referencing
        self._sg_to_vpc: Dict[str, str] = {}
        self._subnet_to_vpc: Dict[str, str] = {}
        self._tg_arn_to_name: Dict[str, str] = {}
        self._lb_arn_to_name: Dict[str, str] = {}
        self._tg_targets: Dict[str, List[str]] = {}

    # ── helpers ──────────────────────────────────────────────────────
    def _add_svc(self, sid: str, name: str, stype: str, cost: float = 0.0, **attrs):
        if sid in self._seen_ids:
            return
        self._seen_ids.add(sid)
        self._services.append({
            "id": sid, "name": name, "type": stype,
            "cost_monthly": round(cost, 2), "environment": "production",
            "owner": "", "attributes": {k: str(v) for k, v in attrs.items() if v},
        })

    def _add_dep(self, src: str, tgt: str, dtype: str = "calls"):
        if src == tgt or src not in self._seen_ids or tgt not in self._seen_ids:
            return
        key = f"{src}|{tgt}|{dtype}"
        if key in self._dep_keys:
            return
        self._dep_keys.add(key)
        self._deps.append({"source": src, "target": tgt, "type": dtype, "weight": 1.0})

    # ── public entry ─────────────────────────────────────────────────
    def discover_architecture(self) -> Dict[str, Any]:
        # Phase 1: Collect all resources
        collectors = [
            ("VPC", self._collect_vpcs),
            ("Subnets", self._collect_subnets),
            ("SecurityGroups", self._collect_security_groups),
            ("IGW", self._collect_internet_gateways),
            ("NAT", self._collect_nat_gateways),
            ("RouteTables", self._collect_route_tables),
            ("ELB", self._collect_elb),
            ("TargetGroups", self._collect_target_groups),
            ("EC2", self._collect_ec2),
            ("ECS", self._collect_ecs),
            ("RDS", self._collect_rds),
            ("Lambda", self._collect_lambda),
            ("S3", self._collect_s3),
            ("DynamoDB", self._collect_dynamodb),
            ("ElastiCache", self._collect_elasticache),
            ("SQS", self._collect_sqs),
            ("SNS", self._collect_sns),
            ("CloudFront", self._collect_cloudfront),
            ("APIGateway", self._collect_apigateway),
            ("APIGatewayV2", self._collect_apigateway_v2),
            ("EKS", self._collect_eks),
            ("CloudWatch", self._collect_cloudwatch_alarms),
            ("ECR", self._collect_ecr),
            ("LogGroups", self._collect_log_groups),
            ("IAMRoles", self._collect_iam_roles),
            ("ElasticIPs", self._collect_elastic_ips),
        ]

        errors = []
        for label, fn in collectors:
            try:
                fn()
                logger.info(f"Collector {label}: OK ({len(self._services)} svcs so far)")
            except Exception as e:
                errors.append(f"{label}: {e}")
                logger.warning(f"Collector {label} failed: {e}")

        if not self._services:
            raise RuntimeError(
                f"All AWS collectors failed. Errors: " + "; ".join(errors[:3])
            )

        # Phase 2: Infer cross-service dependencies
        self._infer_dependencies()

        total_cost = sum(s.get("cost_monthly", 0) for s in self._services)

        return {
            "metadata": {
                "name": f"AWS Live ({self.region})",
                "pattern": "discovered",
                "complexity": "high" if len(self._services) >= 30 else "medium",
                "environment": "production",
                "region": self.region,
                "total_services": len(self._services),
                "total_cost_monthly": round(total_cost, 2),
            },
            "services": self._services,
            "dependencies": self._deps,
        }

    # ──────────────────────────────────────────────────────────────────
    #  VPC / Networking
    # ──────────────────────────────────────────────────────────────────
    def _collect_vpcs(self):
        ec2 = self.session.client("ec2")
        for v in ec2.describe_vpcs().get("Vpcs", []):
            vid = v["VpcId"]
            name = _tag_name(v.get("Tags"), vid)
            self._add_svc(vid, name, "vpc", 0.0, cidr=v.get("CidrBlock", ""))

    def _collect_subnets(self):
        ec2 = self.session.client("ec2")
        for s in ec2.describe_subnets().get("Subnets", []):
            sid = s["SubnetId"]
            name = _tag_name(s.get("Tags"), sid)
            vpc_id = s.get("VpcId", "")
            self._subnet_to_vpc[sid] = vpc_id
            self._add_svc(sid, name, "subnet", 0.0,
                         az=s.get("AvailabilityZone", ""), cidr=s.get("CidrBlock", ""))
            if vpc_id in self._seen_ids:
                self._add_dep(sid, vpc_id, "belongs_to")

    def _collect_security_groups(self):
        ec2 = self.session.client("ec2")
        for sg in ec2.describe_security_groups().get("SecurityGroups", []):
            sgid = sg["GroupId"]
            name = sg.get("GroupName", sgid)
            vpc_id = sg.get("VpcId", "")
            self._sg_to_vpc[sgid] = vpc_id
            self._add_svc(sgid, name, "security_group", 0.0,
                         description=sg.get("Description", ""))
            if vpc_id in self._seen_ids:
                self._add_dep(sgid, vpc_id, "belongs_to")

    def _collect_internet_gateways(self):
        ec2 = self.session.client("ec2")
        for igw in ec2.describe_internet_gateways().get("InternetGateways", []):
            igw_id = igw["InternetGatewayId"]
            name = _tag_name(igw.get("Tags"), igw_id)
            self._add_svc(igw_id, name, "gateway", 0.0)
            for att in igw.get("Attachments", []):
                vpc_id = att.get("VpcId")
                if vpc_id and vpc_id in self._seen_ids:
                    self._add_dep(igw_id, vpc_id, "attached_to")

    def _collect_nat_gateways(self):
        ec2 = self.session.client("ec2")
        for nat in ec2.describe_nat_gateways(
            Filters=[{"Name": "state", "Values": ["available"]}]
        ).get("NatGateways", []):
            nid = nat["NatGatewayId"]
            name = _tag_name(nat.get("Tags"), nid)
            subnet_id = nat.get("SubnetId", "")
            self._add_svc(nid, name, "gateway", COST_ESTIMATES["nat_gateway"])
            if subnet_id in self._seen_ids:
                self._add_dep(nid, subnet_id, "deployed_in")

    def _collect_route_tables(self):
        ec2 = self.session.client("ec2")
        for rt in ec2.describe_route_tables().get("RouteTables", []):
            rtid = rt["RouteTableId"]
            name = _tag_name(rt.get("Tags"), rtid)
            vpc_id = rt.get("VpcId", "")
            self._add_svc(rtid, name, "route_table", 0.0)
            if vpc_id in self._seen_ids:
                self._add_dep(rtid, vpc_id, "belongs_to")
            # Routes pointing to NAT/IGW
            for route in rt.get("Routes", []):
                gw = route.get("GatewayId") or route.get("NatGatewayId")
                if gw and gw != "local" and gw in self._seen_ids:
                    self._add_dep(rtid, gw, "routes_through")
            # Subnet associations
            for assoc in rt.get("Associations", []):
                sub = assoc.get("SubnetId")
                if sub and sub in self._seen_ids:
                    self._add_dep(sub, rtid, "uses")

    # ──────────────────────────────────────────────────────────────────
    #  Load Balancing
    # ──────────────────────────────────────────────────────────────────
    def _collect_elb(self):
        elb = self.session.client("elbv2")
        for lb in elb.describe_load_balancers().get("LoadBalancers", []):
            lid = lb["LoadBalancerName"]
            self._lb_arn_to_name[lb["LoadBalancerArn"]] = lid
            ltype = lb.get("Type", "application")
            cost = COST_ESTIMATES.get("alb" if ltype == "application" else "nlb", 22.50)
            self._add_svc(lid, lid, "load_balancer", cost,
                         scheme=lb.get("Scheme", ""), lb_type=ltype)
            vpc_id = lb.get("VpcId", "")
            if vpc_id in self._seen_ids:
                self._add_dep(lid, vpc_id, "deployed_in")
            for az in lb.get("AvailabilityZones", []):
                sub = az.get("SubnetId")
                if sub and sub in self._seen_ids:
                    self._add_dep(lid, sub, "deployed_in")
            for sg in lb.get("SecurityGroups", []):
                if sg in self._seen_ids:
                    self._add_dep(lid, sg, "uses_sg")

    def _collect_target_groups(self):
        elb = self.session.client("elbv2")
        for tg in elb.describe_target_groups().get("TargetGroups", []):
            tg_name = tg["TargetGroupName"]
            tg_arn = tg["TargetGroupArn"]
            self._tg_arn_to_name[tg_arn] = tg_name
            self._add_svc(tg_name, tg_name, "target_group", 0.0,
                         target_type=tg.get("TargetType", ""),
                         protocol=tg.get("Protocol", ""))
            for lb_arn in tg.get("LoadBalancerArns", []):
                lb_name = self._lb_arn_to_name.get(lb_arn)
                if lb_name and lb_name in self._seen_ids:
                    self._add_dep(lb_name, tg_name, "routes_to")
            try:
                targets = elb.describe_target_health(
                    TargetGroupArn=tg_arn
                ).get("TargetHealthDescriptions", [])
                for t in targets:
                    target_id = t["Target"]["Id"]
                    self._tg_targets.setdefault(tg_name, []).append(target_id)
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────────
    #  Compute
    # ──────────────────────────────────────────────────────────────────
    def _collect_ec2(self):
        ec2 = self.session.client("ec2")
        paginator = ec2.get_paginator("describe_instances")
        for page in paginator.paginate():
            for res in page.get("Reservations", []):
                for inst in res.get("Instances", []):
                    iid = inst["InstanceId"]
                    state = inst["State"]["Name"]
                    if state in ("terminated", "shutting-down"):
                        continue
                    name = _tag_name(inst.get("Tags"), iid)
                    itype = inst.get("InstanceType", "t3.micro")
                    cost = COST_ESTIMATES.get(itype, 30.0)
                    self._add_svc(iid, name, "service", cost,
                                 instance_type=itype, state=state)
                    sub = inst.get("SubnetId")
                    if sub and sub in self._seen_ids:
                        self._add_dep(iid, sub, "deployed_in")
                    for sg in inst.get("SecurityGroups", []):
                        sgid = sg["GroupId"]
                        if sgid in self._seen_ids:
                            self._add_dep(iid, sgid, "uses_sg")

    def _collect_ecs(self):
        ecs = self.session.client("ecs")
        clusters = ecs.list_clusters().get("clusterArns", [])
        for cluster_arn in clusters:
            cluster_name = cluster_arn.rsplit("/", 1)[-1]
            self._add_svc(cluster_name, cluster_name, "ecs_cluster", 0.0)

            # Services
            svc_arns = ecs.list_services(cluster=cluster_arn).get("serviceArns", [])
            if svc_arns:
                svc_details = ecs.describe_services(
                    cluster=cluster_arn, services=svc_arns
                ).get("services", [])
                for svc in svc_details:
                    svc_name = svc["serviceName"]
                    svc_id = f"ecs-svc-{svc_name}"
                    self._add_svc(svc_id, svc_name, "service", 30.0,
                                 desired_count=svc.get("desiredCount", 0),
                                 running_count=svc.get("runningCount", 0),
                                 launch_type=svc.get("launchType", "FARGATE"))
                    self._add_dep(svc_id, cluster_name, "runs_in")

                    # ECS Service → Target Group
                    for lb_conf in svc.get("loadBalancers", []):
                        tg_arn = lb_conf.get("targetGroupArn", "")
                        tg_name = self._tg_arn_to_name.get(tg_arn)
                        if tg_name and tg_name in self._seen_ids:
                            self._add_dep(tg_name, svc_id, "routes_to")

                    # ECS Service → Subnets & SGs
                    net_conf = svc.get("networkConfiguration", {}).get("awsvpcConfiguration", {})
                    for sub in net_conf.get("subnets", []):
                        if sub in self._seen_ids:
                            self._add_dep(svc_id, sub, "deployed_in")
                    for sg in net_conf.get("securityGroups", []):
                        if sg in self._seen_ids:
                            self._add_dep(svc_id, sg, "uses_sg")

            # Tasks
            task_arns = ecs.list_tasks(cluster=cluster_arn).get("taskArns", [])
            if task_arns:
                task_details = ecs.describe_tasks(
                    cluster=cluster_arn, tasks=task_arns
                ).get("tasks", [])
                for task in task_details:
                    task_short = task["taskArn"].rsplit("/", 1)[-1][:12]
                    task_id = f"ecs-task-{task_short}"
                    td_arn = task.get("taskDefinitionArn", "")
                    td_name = td_arn.rsplit("/", 1)[-1] if "/" in td_arn else ""
                    self._add_svc(task_id, f"Task {task_short}", "container", 5.0,
                                 task_definition=td_name,
                                 last_status=task.get("lastStatus", ""))
                    self._add_dep(task_id, cluster_name, "runs_in")

                    for att in task.get("attachments", []):
                        for detail in att.get("details", []):
                            if detail.get("name") == "subnetId" and detail["value"] in self._seen_ids:
                                self._add_dep(task_id, detail["value"], "deployed_in")

    def _collect_rds(self):
        rds = self.session.client("rds")
        for db in rds.describe_db_instances().get("DBInstances", []):
            did = db["DBInstanceIdentifier"]
            iclass = db.get("DBInstanceClass", "db.t3.micro")
            cost = COST_ESTIMATES.get(iclass, 50.0)
            self._add_svc(did, did, "database", cost,
                         engine=db.get("Engine", ""),
                         engine_version=db.get("EngineVersion", ""),
                         storage_gb=db.get("AllocatedStorage", 0),
                         multi_az=str(db.get("MultiAZ", False)))
            for sg in db.get("VpcSecurityGroups", []):
                sgid = sg.get("VpcSecurityGroupId")
                if sgid and sgid in self._seen_ids:
                    self._add_dep(did, sgid, "uses_sg")
            sg_detail = db.get("DBSubnetGroup", {})
            for sub in sg_detail.get("Subnets", []):
                sub_id = sub.get("SubnetIdentifier")
                if sub_id and sub_id in self._seen_ids:
                    self._add_dep(did, sub_id, "deployed_in")

    def _collect_lambda(self):
        lam = self.session.client("lambda")
        paginator = lam.get_paginator("list_functions")
        for page in paginator.paginate():
            for fn in page.get("Functions", []):
                fid = fn["FunctionName"]
                self._add_svc(fid, fid, "serverless", 5.0,
                             runtime=fn.get("Runtime", ""),
                             memory_mb=fn.get("MemorySize", 128))
                vpc_conf = fn.get("VpcConfig", {})
                for sub in vpc_conf.get("SubnetIds", []):
                    if sub in self._seen_ids:
                        self._add_dep(fid, sub, "deployed_in")
                for sg in vpc_conf.get("SecurityGroupIds", []):
                    if sg in self._seen_ids:
                        self._add_dep(fid, sg, "uses_sg")
        # Event source mappings
        try:
            for esm in lam.list_event_source_mappings().get("EventSourceMappings", []):
                fn_arn = esm.get("FunctionArn", "")
                fn_name = fn_arn.rsplit(":", 1)[-1] if ":" in fn_arn else fn_arn
                source_arn = esm.get("EventSourceArn", "")
                source_name = source_arn.rsplit(":", 1)[-1] if ":" in source_arn else source_arn
                if fn_name in self._seen_ids and source_name in self._seen_ids:
                    self._add_dep(source_name, fn_name, "triggers")
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────
    #  Storage & Messaging
    # ──────────────────────────────────────────────────────────────────
    def _collect_s3(self):
        s3 = self.session.client("s3")
        for b in s3.list_buckets().get("Buckets", []):
            bid = b["Name"]
            self._add_svc(bid, bid, "storage", COST_ESTIMATES["s3_bucket"])

    def _collect_dynamodb(self):
        ddb = self.session.client("dynamodb")
        paginator = ddb.get_paginator("list_tables")
        for page in paginator.paginate():
            for t in page.get("TableNames", []):
                self._add_svc(t, t, "database", 10.0)

    def _collect_elasticache(self):
        ec = self.session.client("elasticache")
        for c in ec.describe_cache_clusters().get("CacheClusters", []):
            cid = c["CacheClusterId"]
            self._add_svc(cid, cid, "cache", 25.0, engine=c.get("Engine", ""))
            for sg in c.get("SecurityGroups", []):
                sgid = sg.get("SecurityGroupId")
                if sgid and sgid in self._seen_ids:
                    self._add_dep(cid, sgid, "uses_sg")

    def _collect_sqs(self):
        sqs = self.session.client("sqs")
        resp = sqs.list_queues()
        for url in resp.get("QueueUrls", []):
            name = url.rsplit("/", 1)[-1]
            self._add_svc(name, name, "queue", COST_ESTIMATES["sqs_queue"])

    def _collect_sns(self):
        sns = self.session.client("sns")
        for t in sns.list_topics().get("Topics", []):
            arn = t["TopicArn"]
            name = arn.rsplit(":", 1)[-1]
            self._add_svc(name, name, "notification", COST_ESTIMATES["sns_topic"])
            try:
                for sub in sns.list_subscriptions_by_topic(TopicArn=arn).get("Subscriptions", []):
                    endpoint = sub.get("Endpoint", "")
                    protocol = sub.get("Protocol", "")
                    if protocol == "sqs":
                        q_name = endpoint.rsplit(":", 1)[-1]
                        if q_name in self._seen_ids:
                            self._add_dep(name, q_name, "publishes_to")
                    elif protocol == "lambda":
                        fn_name = endpoint.rsplit(":", 1)[-1]
                        if fn_name in self._seen_ids:
                            self._add_dep(name, fn_name, "triggers")
            except Exception:
                pass

    def _collect_cloudfront(self):
        cf = self.session.client("cloudfront")
        dist_list = cf.list_distributions().get("DistributionList", {})
        for dist in (dist_list.get("Items", []) if isinstance(dist_list, dict) else []):
            did = dist["Id"]
            comment = dist.get("Comment", did) or did
            self._add_svc(did, comment, "cdn", 15.0)
            for origin in dist.get("Origins", {}).get("Items", []):
                domain = origin.get("DomainName", "")
                if ".s3." in domain or domain.endswith(".s3.amazonaws.com"):
                    bucket = domain.split(".")[0]
                    if bucket in self._seen_ids:
                        self._add_dep(did, bucket, "origin")

    def _collect_apigateway(self):
        apig = self.session.client("apigateway")
        for api in apig.get_rest_apis().get("items", []):
            aid = f"apigw-{api['id']}"
            self._add_svc(aid, api["name"], "api_gateway", 10.0)

    def _collect_apigateway_v2(self):
        apig2 = self.session.client("apigatewayv2")
        for api in apig2.get_apis().get("Items", []):
            aid = f"apigw2-{api['ApiId']}"
            self._add_svc(aid, api["Name"], "api_gateway", 10.0,
                         protocol=api.get("ProtocolType", ""))

    def _collect_eks(self):
        eks = self.session.client("eks")
        for name in eks.list_clusters().get("clusters", []):
            self._add_svc(f"eks-{name}", name, "service", 73.0)

    def _collect_cloudwatch_alarms(self):
        cw = self.session.client("cloudwatch")
        paginator = cw.get_paginator("describe_alarms")
        for page in paginator.paginate():
            for alarm in page.get("MetricAlarms", []):
                aid = alarm["AlarmName"]
                self._add_svc(aid, aid, "monitoring", COST_ESTIMATES["cloudwatch_alarm"],
                             metric=alarm.get("MetricName", ""),
                             namespace=alarm.get("Namespace", ""))
                for action in alarm.get("AlarmActions", []):
                    if ":sns:" in action:
                        topic_name = action.rsplit(":", 1)[-1]
                        if topic_name in self._seen_ids:
                            self._add_dep(aid, topic_name, "alerts_to")

    def _collect_ecr(self):
        ecr = self.session.client("ecr")
        for repo in ecr.describe_repositories().get("repositories", []):
            rid = f"ecr-{repo['repositoryName']}"
            self._add_svc(rid, repo["repositoryName"], "container_registry", 2.0,
                         uri=repo.get("repositoryUri", ""))

    def _collect_log_groups(self):
        logs = self.session.client("logs")
        paginator = logs.get_paginator("describe_log_groups")
        for page in paginator.paginate():
            for lg in page.get("logGroups", []):
                name = lg["logGroupName"]
                safe_id = f"log-{name.replace('/', '-').strip('-')}"
                self._add_svc(safe_id, name, "logging", 1.0,
                             retention_days=lg.get("retentionInDays", "never"),
                             stored_bytes=lg.get("storedBytes", 0))

    def _collect_iam_roles(self):
        iam = self.session.client("iam")
        roles = iam.list_roles(MaxItems=100).get("Roles", [])
        # Only include project-relevant roles (not AWS service-linked generic ones)
        for role in roles:
            rname = role["RoleName"]
            # Include roles matching the project pattern or ECS/Lambda task roles
            if any(kw in rname.lower() for kw in ("finops", "ecs-task", "ecs-execution", "lambda")):
                rid = f"iam-{rname}"
                self._add_svc(rid, rname, "iam_role", 0.0,
                             arn=role.get("Arn", ""),
                             path=role.get("Path", "/"))

    def _collect_elastic_ips(self):
        ec2 = self.session.client("ec2")
        for eip in ec2.describe_addresses().get("Addresses", []):
            alloc_id = eip.get("AllocationId", eip.get("PublicIp", "unknown"))
            public_ip = eip.get("PublicIp", alloc_id)
            name = _tag_name(eip.get("Tags"), f"EIP-{public_ip}")
            self._add_svc(alloc_id, name, "elastic_ip", 3.60,
                         public_ip=public_ip,
                         association=eip.get("AssociationId", "unattached"))
            # EIP attached to NAT gateway or instance
            instance_id = eip.get("InstanceId")
            if instance_id and instance_id in self._seen_ids:
                self._add_dep(alloc_id, instance_id, "attached_to")

    # ──────────────────────────────────────────────────────────────────
    #  Phase 2: Infer cross-service dependencies
    # ──────────────────────────────────────────────────────────────────
    def _infer_dependencies(self):
        """Infer logical edges between discovered resources."""
        # SG inbound rule cross-references
        try:
            ec2 = self.session.client("ec2")
            for sg in ec2.describe_security_groups().get("SecurityGroups", []):
                sgid = sg["GroupId"]
                if sgid not in self._seen_ids:
                    continue
                for rule in sg.get("IpPermissions", []):
                    for pair in rule.get("UserIdGroupPairs", []):
                        ref_sg = pair.get("GroupId")
                        if ref_sg and ref_sg in self._seen_ids and ref_sg != sgid:
                            self._add_dep(sgid, ref_sg, "allows_from")
        except Exception:
            pass

        # Naming convention: services sharing a project prefix → connected
        app_services = [s for s in self._services if s["type"] in ("service", "serverless", "container")]
        data_services = [s for s in self._services if s["type"] in ("database", "cache", "storage", "queue", "notification")]

        for app in app_services:
            app_prefix = app["name"].rsplit("-", 1)[0] if "-" in app["name"] else ""
            if len(app_prefix) < 5:
                continue
            for data in data_services:
                data_prefix = data["name"].rsplit("-", 1)[0] if "-" in data["name"] else ""
                if app_prefix and data_prefix and app_prefix == data_prefix:
                    self._add_dep(app["id"], data["id"], "uses")

        # ECR → ECS (container registry serves container services)
        ecr_svcs = [s for s in self._services if s["type"] == "container_registry"]
        ecs_svcs = [s for s in self._services if s["type"] in ("service", "container") and "ecs" in s["id"]]
        for ecr in ecr_svcs:
            for ecs in ecs_svcs:
                # Match by name fragments
                ecr_base = ecr["name"].replace("finops-", "").replace("dev-", "")
                ecs_base = ecs["name"].replace("finops-", "").replace("dev-", "")
                if ecr_base in ecs_base or ecs_base in ecr_base:
                    self._add_dep(ecs["id"], ecr["id"], "pulls_from")

        # Log groups → ECS/Lambda (by name matching)
        log_svcs = [s for s in self._services if s["type"] == "logging"]
        compute_svcs = [s for s in self._services if s["type"] in ("service", "serverless", "container", "ecs_cluster")]
        for log in log_svcs:
            log_name = log["name"].lower()
            for comp in compute_svcs:
                comp_name = comp["name"].lower()
                if comp_name in log_name or comp["id"].replace("ecs-svc-", "") in log_name:
                    self._add_dep(comp["id"], log["id"], "logs_to")

        # IAM roles → ECS (task/execution roles)
        iam_svcs = [s for s in self._services if s["type"] == "iam_role"]
        for iam in iam_svcs:
            iam_name = iam["name"].lower()
            for comp in ecs_svcs:
                if "ecs" in iam_name or "task" in iam_name:
                    self._add_dep(comp["id"], iam["id"], "assumes_role")

        # Elastic IPs → NAT gateways (match via subnet)
        # Already partially handled by attachment detection

        logger.info(f"Final: {len(self._services)} services, {len(self._deps)} dependencies")
