"""
AWS Cost and Usage Report (CUR) Parser
======================================
Fetches CUR exports from S3, parses CSV rows, and produces a raw JSON
representation of all line items.  This is the first stage of the pipeline:
  CUR (S3/CSV) → Raw JSON → Transformed JSON → Neo4j Graph

CUR columns used:
  - identity/LineItemId
  - bill/BillingPeriodStartDate, bill/BillingPeriodEndDate
  - lineItem/UsageStartDate, lineItem/UsageEndDate
  - lineItem/ProductCode            (e.g. AmazonEC2, AmazonRDS)
  - lineItem/UsageType              (e.g. USE2-BoxUsage:t3.medium)
  - lineItem/Operation              (e.g. RunInstances, CreateDBInstance)
  - lineItem/ResourceId             (e.g. i-0abc..., arn:aws:rds:...)
  - lineItem/UnblendedCost
  - lineItem/BlendedCost
  - lineItem/UsageAmount
  - lineItem/LineItemType           (Usage, Tax, Credit, Refund)
  - product/servicecode             (AmazonEC2, AmazonRDS, AWSLambda)
  - product/region
  - product/instanceType
  - product/operatingSystem
  - resourceTags/user:Name          (customer-assigned Name tag)
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
#  CUR column name normalisation
# ─────────────────────────────────────────────────────────────────────
def _norm_col(col: str) -> str:
    """Normalise a CUR column header: lowercase, replace / with _."""
    return col.strip().lower().replace("/", "_").replace(":", "_")


# ─────────────────────────────────────────────────────────────────────
#  AWS product code → our internal type mapping
# ─────────────────────────────────────────────────────────────────────
PRODUCT_TO_TYPE = {
    "amazonec2": "compute",
    "amazonecs": "container",
    "amazoneks": "container",
    "amazonrds": "database",
    "amazondynamodb": "database",
    "amazonelasticache": "cache",
    "amazons3": "storage",
    "awslambda": "serverless",
    "amazonsqs": "queue",
    "amazonsns": "notification",
    "amazoncloudfront": "cdn",
    "amazonapigateway": "gateway",
    "elasticloadbalancing": "load_balancer",
    "awselasticloadbalancingv2": "load_balancer",
    "amazonvpc": "networking",
    "amazoncloudwatch": "monitoring",
    "amazonroute53": "dns",
    "amazonecr": "container_registry",
    "awskms": "security",
    "awssecretsmanager": "security",
    "awsconfig": "monitoring",
    "awscloudtrail": "logging",
    "awswaf": "security",
    "amazonopensearchservice": "search",
    "amazonkinesis": "streaming",
    "amazonredshift": "database",
    "amazonneptune": "database",
    "amazonemr": "batch",
    "amazonsagemaker": "ml",
    "awsstepfunctions": "serverless",
    "amazonses": "notification",
    "awscodecommit": "devops",
    "awscodebuild": "devops",
    "awscodepipeline": "devops",
}


def _product_to_type(product_code: str) -> str:
    """Map an AWS product code to our internal resource type."""
    key = product_code.lower().replace(" ", "").replace("-", "")
    return PRODUCT_TO_TYPE.get(key, "service")


# ─────────────────────────────────────────────────────────────────────
#  CUR Data Loader — from S3 or local file
# ─────────────────────────────────────────────────────────────────────
class CURLoader:
    """Load CUR CSV data from S3 or a local directory."""

    def __init__(self, region: str = "us-east-1"):
        self.region = region
        try:
            import boto3
            self.session = boto3.Session(region_name=region)
            self.s3 = self.session.client("s3")
        except ImportError:
            self.session = None
            self.s3 = None

    def list_cur_manifests(self, bucket: str, prefix: str) -> List[Dict]:
        """List available CUR manifests in an S3 bucket."""
        if not self.s3:
            return []

        manifests = []
        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith("-Manifest.json") or key.endswith("Manifest.json"):
                        manifests.append({
                            "key": key,
                            "size": obj["Size"],
                            "last_modified": obj["LastModified"].isoformat(),
                        })
        except Exception as e:
            logger.warning(f"Failed listing CUR manifests: {e}")

        return sorted(manifests, key=lambda m: m["last_modified"], reverse=True)

    def load_from_s3(self, bucket: str, manifest_key: str) -> List[Dict]:
        """Load a CUR export from S3 using its manifest."""
        if not self.s3:
            raise RuntimeError("boto3 is required for S3 access")

        # Read manifest
        resp = self.s3.get_object(Bucket=bucket, Key=manifest_key)
        manifest = json.loads(resp["Body"].read().decode("utf-8"))

        report_keys = manifest.get("reportKeys", [])
        if not report_keys:
            raise ValueError("No report keys found in manifest")

        all_rows: List[Dict] = []
        for rk in report_keys:
            rows = self._read_csv_from_s3(bucket, rk)
            all_rows.extend(rows)

        return all_rows

    def _read_csv_from_s3(self, bucket: str, key: str) -> List[Dict]:
        """Read a single CUR CSV file from S3 (handles .gz)."""
        resp = self.s3.get_object(Bucket=bucket, Key=key)
        body = resp["Body"].read()

        if key.endswith(".gz"):
            body = gzip.decompress(body)

        text = body.decode("utf-8")
        return self._parse_csv(text)

    def load_from_local(self, file_path: str) -> List[Dict]:
        """Load CUR data from a local CSV or gzipped CSV file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CUR file not found: {file_path}")

        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as f:
                text = f.read()
        else:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()

        return self._parse_csv(text)

    def _parse_csv(self, text: str) -> List[Dict]:
        """Parse CUR CSV text into a list of dicts with normalised keys."""
        reader = csv.DictReader(io.StringIO(text))
        rows = []
        for row in reader:
            normalised = {_norm_col(k): v for k, v in row.items()}
            rows.append(normalised)
        return rows

    def generate_sample_cur(self) -> List[Dict]:
        """Generate a realistic sample CUR report from actual AWS resources.
        Used when no real CUR export is configured."""
        try:
            from src.ingestion.aws_client import RealAWSCollector
            collector = RealAWSCollector(region=self.region)
            arch = collector.discover_architecture()
        except Exception as e:
            logger.warning(f"AWS collector fallback failed: {e}")
            arch = {"services": [], "dependencies": []}

        rows = []
        now = datetime.utcnow()
        period_start = now.replace(day=1, hour=0, minute=0, second=0)

        for svc in arch.get("services", []):
            product_code = self._type_to_product(svc.get("type", "service"))
            resource_id = svc.get("attributes", {}).get("arn", svc.get("id", ""))
            cost = svc.get("cost_monthly", 0.0)

            # Generate daily line items for current month
            days_in_month = 30
            daily_cost = cost / days_in_month if cost > 0 else 0

            for day in range(1, min(now.day + 1, days_in_month + 1)):
                usage_start = period_start.replace(day=day)
                usage_end = period_start.replace(day=min(day + 1, days_in_month))

                rows.append({
                    "identity_lineitemid": str(uuid.uuid4()),
                    "bill_billingperiodstartdate": period_start.isoformat() + "Z",
                    "bill_billingperiodenddate": period_start.replace(month=period_start.month + 1 if period_start.month < 12 else 1).isoformat() + "Z",
                    "lineitem_usagestartdate": usage_start.isoformat() + "Z",
                    "lineitem_usageenddate": usage_end.isoformat() + "Z",
                    "lineitem_productcode": product_code,
                    "lineitem_usagetype": self._type_to_usage(svc.get("type", "service"), svc),
                    "lineitem_operation": self._type_to_operation(svc.get("type", "service")),
                    "lineitem_resourceid": resource_id or svc["id"],
                    "lineitem_unblendedcost": str(round(daily_cost, 6)),
                    "lineitem_blendedcost": str(round(daily_cost, 6)),
                    "lineitem_usageamount": str(round(24.0 if cost > 0 else 0, 2)),
                    "lineitem_lineitemtype": "Usage",
                    "product_servicecode": product_code,
                    "product_region": self.region,
                    "product_instancetype": svc.get("attributes", {}).get("instance_type", ""),
                    "product_operatingsystem": svc.get("attributes", {}).get("platform", ""),
                    "resourcetags_user_name": svc.get("name", svc["id"]),
                    # Extra context from our discovery
                    "_discovered_type": svc.get("type", "service"),
                    "_discovered_name": svc.get("name", svc["id"]),
                    "_discovered_id": svc["id"],
                })

        return rows

    def _type_to_product(self, stype: str) -> str:
        """Map our internal type to an AWS product code."""
        mapping = {
            "compute": "AmazonEC2", "container": "AmazonECS",
            "database": "AmazonRDS", "cache": "AmazonElastiCache",
            "storage": "AmazonS3", "serverless": "AWSLambda",
            "queue": "AmazonSQS", "notification": "AmazonSNS",
            "cdn": "AmazonCloudFront", "gateway": "AmazonApiGateway",
            "load_balancer": "ElasticLoadBalancing", "vpc": "AmazonVPC",
            "subnet": "AmazonVPC", "security_group": "AmazonVPC",
            "monitoring": "AmazonCloudWatch", "logging": "AWSCloudTrail",
            "container_registry": "AmazonECR", "iam_role": "AWSIAM",
            "elastic_ip": "AmazonEC2", "target_group": "ElasticLoadBalancing",
            "ecs_cluster": "AmazonECS", "route_table": "AmazonVPC",
            "search": "AmazonOpenSearchService",
        }
        return mapping.get(stype, "AmazonEC2")

    def _type_to_usage(self, stype: str, svc: Dict) -> str:
        """Generate a realistic usage type string."""
        itype = svc.get("attributes", {}).get("instance_type", "")
        mapping = {
            "compute": f"USE1-BoxUsage:{itype or 't3.medium'}",
            "database": f"USE1-InstanceUsage:{itype or 'db.t3.medium'}",
            "container": "USE1-Fargate-vCPU-Hours:perCPU",
            "storage": "USE1-TimedStorage-ByteHrs",
            "serverless": "USE1-Lambda-GB-Second",
            "queue": "USE1-Requests-Tier1",
            "load_balancer": "USE1-LoadBalancerUsage",
            "cache": f"USE1-NodeUsage:{itype or 'cache.t3.micro'}",
            "cdn": "USE1-DataTransfer-Out-Bytes",
            "monitoring": "USE1-CW:AlarmMonitorUsage",
        }
        return mapping.get(stype, f"USE1-BoxUsage:unknown")

    def _type_to_operation(self, stype: str) -> str:
        mapping = {
            "compute": "RunInstances", "database": "CreateDBInstance",
            "storage": "PutObject", "serverless": "Invoke",
            "container": "RunTask", "queue": "SendMessage",
            "load_balancer": "LoadBalancing", "cache": "CreateCacheCluster",
        }
        return mapping.get(stype, "Unknown")


# ─────────────────────────────────────────────────────────────────────
#  CUR Parser — parse raw rows into structured data
# ─────────────────────────────────────────────────────────────────────
class CURParser:
    """Parse CUR line items into aggregated resource-level cost data."""

    def __init__(self, raw_rows: List[Dict]):
        self.raw_rows = raw_rows

    def parse(self) -> Dict[str, Any]:
        """Parse raw CUR rows into structured cost report.

        Returns dict with:
          - summary: billing period, total cost, unique resources
          - resources: aggregated per-resource cost data
          - services_breakdown: per-service totals
          - daily_costs: daily cost time series
          - line_items: raw line item count
        """
        if not self.raw_rows:
            return self._empty_report()

        # Aggregate by resource
        resources: Dict[str, Dict] = {}
        service_totals: Dict[str, float] = defaultdict(float)
        daily_totals: Dict[str, float] = defaultdict(float)
        total_cost = 0.0
        billing_start = None
        billing_end = None
        region = None

        for row in self.raw_rows:
            line_type = row.get("lineitem_lineitemtype", "Usage")
            if line_type not in ("Usage", "DiscountedUsage", "SavingsPlanCoveredUsage"):
                continue

            cost = float(row.get("lineitem_unblendedcost", "0") or "0")
            blended = float(row.get("lineitem_blendedcost", "0") or "0")
            usage_amount = float(row.get("lineitem_usageamount", "0") or "0")

            resource_id = row.get("lineitem_resourceid", "")
            product_code = row.get("lineitem_productcode", row.get("product_servicecode", "Unknown"))
            usage_type = row.get("lineitem_usagetype", "")
            operation = row.get("lineitem_operation", "")
            instance_type = row.get("product_instancetype", "")
            name_tag = row.get("resourcetags_user_name", "")
            discovered_name = row.get("_discovered_name", "")
            discovered_id = row.get("_discovered_id", "")
            discovered_type = row.get("_discovered_type", "")

            region = region or row.get("product_region", "us-east-1")

            # Billing period
            bs = row.get("bill_billingperiodstartdate", "")
            be = row.get("bill_billingperiodenddate", "")
            if bs and not billing_start:
                billing_start = bs
            if be:
                billing_end = be

            # Daily aggregation
            usage_date = row.get("lineitem_usagestartdate", "")[:10]
            if usage_date:
                daily_totals[usage_date] += cost

            total_cost += cost
            service_totals[product_code] += cost

            # Resource aggregation
            rid = discovered_id or resource_id or f"{product_code}:{usage_type}"
            if rid not in resources:
                resources[rid] = {
                    "resource_id": resource_id,
                    "discovered_id": discovered_id,
                    "name": discovered_name or name_tag or self._extract_name(resource_id),
                    "product_code": product_code,
                    "resource_type": discovered_type or _product_to_type(product_code),
                    "instance_type": instance_type,
                    "usage_type": usage_type,
                    "operation": operation,
                    "region": row.get("product_region", ""),
                    "unblended_cost": 0.0,
                    "blended_cost": 0.0,
                    "usage_amount": 0.0,
                    "line_item_count": 0,
                    "daily_costs": defaultdict(float),
                }

            resources[rid]["unblended_cost"] += cost
            resources[rid]["blended_cost"] += blended
            resources[rid]["usage_amount"] += usage_amount
            resources[rid]["line_item_count"] += 1
            if usage_date:
                resources[rid]["daily_costs"][usage_date] += cost

        # Convert daily_costs from defaultdict to regular dict
        for rid in resources:
            resources[rid]["daily_costs"] = dict(resources[rid]["daily_costs"])
            resources[rid]["unblended_cost"] = round(resources[rid]["unblended_cost"], 4)
            resources[rid]["blended_cost"] = round(resources[rid]["blended_cost"], 4)
            resources[rid]["usage_amount"] = round(resources[rid]["usage_amount"], 4)

        # Sort resources by cost
        sorted_resources = sorted(
            resources.values(),
            key=lambda r: r["unblended_cost"],
            reverse=True,
        )

        # Sort services by cost
        sorted_services = sorted(
            [{"service": k, "total_cost": round(v, 4)} for k, v in service_totals.items()],
            key=lambda s: s["total_cost"],
            reverse=True,
        )

        # Sort daily costs
        sorted_daily = sorted(
            [{"date": k, "cost": round(v, 4)} for k, v in daily_totals.items()],
            key=lambda d: d["date"],
        )

        return {
            "summary": {
                "billing_period_start": billing_start,
                "billing_period_end": billing_end,
                "total_unblended_cost": round(total_cost, 4),
                "unique_resources": len(resources),
                "total_line_items": len(self.raw_rows),
                "unique_services": len(service_totals),
                "region": region,
            },
            "resources": sorted_resources,
            "services_breakdown": sorted_services,
            "daily_costs": sorted_daily,
            "line_items_count": len(self.raw_rows),
        }

    def _extract_name(self, resource_id: str) -> str:
        """Extract a human-readable name from an AWS resource ID or ARN."""
        if not resource_id:
            return "unknown"
        # ARN format: arn:aws:service:region:account:resource-type/name
        if resource_id.startswith("arn:"):
            parts = resource_id.split(":")
            last = parts[-1] if len(parts) > 5 else resource_id
            if "/" in last:
                return last.split("/")[-1]
            return last
        return resource_id

    def _empty_report(self) -> Dict:
        return {
            "summary": {
                "billing_period_start": None,
                "billing_period_end": None,
                "total_unblended_cost": 0,
                "unique_resources": 0,
                "total_line_items": 0,
                "unique_services": 0,
                "region": None,
            },
            "resources": [],
            "services_breakdown": [],
            "daily_costs": [],
            "line_items_count": 0,
        }
