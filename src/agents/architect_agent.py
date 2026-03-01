"""
Agent 1 — AWS Infrastructure Topology Analyst
Reads the architecture dependency graph and identifies AWS infrastructure
patterns that create cost spike risk: single-AZ bottlenecks, deep service
chains, circular dependencies, and scaling mismatches between services.

This agent answers: "Which AWS resources are structurally risky?"
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from .base_agent import BaseAgent, AgentOutput


# Map generic types to AWS service names
AWS_SERVICE_MAP = {
    "service": "Amazon EC2 / ECS",
    "database": "Amazon RDS",
    "cache": "Amazon ElastiCache",
    "queue": "Amazon SQS",
    "load_balancer": "Application Load Balancer (ALB)",
    "storage": "Amazon S3",
    "serverless": "AWS Lambda",
    "cdn": "Amazon CloudFront",
    "search": "Amazon OpenSearch",
    "batch": "AWS Batch",
}


class TopologyAnalystAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        self.role = "topology_analyst"

    def _aws_name(self, node_id: str, node_type: str = "") -> str:
        """Return AWS-branded description of a node."""
        aws = AWS_SERVICE_MAP.get(node_type, "AWS resource")
        return f"{node_id} ({aws})"

    def analyze(self, context: Dict[str, Any]) -> AgentOutput:
        t0 = time.time()

        cascade = context.get("cascade_analysis", {})
        arch_name = context.get("architecture_name", "Unknown")
        n_services = context.get("n_services", 0)
        n_deps = context.get("n_dependencies", 0)

        findings: List[Dict[str, Any]] = []

        # 1. Centralization — Single point of failure
        cent_score = cascade.get("centralization_score", 0)
        cent_hub = cascade.get("centralization_hub", "unknown")
        if cent_score > 0.3:
            findings.append({
                "pattern": "single_point_of_failure",
                "severity": "critical" if cent_score > 0.6 else "high",
                "description": (
                    f"⚠️ Single Point of Failure: {cent_hub} handles "
                    f"{cent_score:.0%} of all traffic routing. "
                    f"If this resource degrades, {n_deps} downstream AWS services "
                    f"will experience cascading failures. This is like having one "
                    f"ALB target group serving your entire production workload."
                ),
                "affected_node": cent_hub,
                "metric": cent_score,
                "aws_recommendation": (
                    f"Deploy {cent_hub} across multiple Availability Zones with "
                    f"an Application Load Balancer (ALB) health check. "
                    f"Add Amazon Route 53 failover routing for automatic recovery."
                ),
            })

        # 2. Deep dependency chains — Latency amplification
        depth = cascade.get("max_chain_depth", 0)
        chain = cascade.get("longest_chain", [])
        if depth > 4:
            findings.append({
                "pattern": "deep_service_chain",
                "severity": "high" if depth > 6 else "moderate",
                "description": (
                    f"🔗 Deep Service Chain ({depth} hops): "
                    f"{' → '.join(chain[:6])}. "
                    f"Each hop adds ~10-50ms latency. At {depth} hops, "
                    f"a single slow Amazon RDS query at the bottom adds "
                    f"{depth * 30}ms+ to your user-facing API response. "
                    f"This also means {depth}× the CloudWatch log volume "
                    f"and X-Ray trace segments per request."
                ),
                "affected_node": chain[-1] if chain else "",
                "metric": depth,
                "aws_recommendation": (
                    f"Add Amazon ElastiCache (Redis) between hop 2 and hop {depth - 1} "
                    f"to short-circuit the chain. Enable AWS X-Ray tracing to identify "
                    f"the slowest hops. Consider Amazon API Gateway caching for "
                    f"frequently-accessed endpoints."
                ),
            })

        # 3. Circular dependencies — Feedback loops
        cycles = cascade.get("cycles", [])
        if cycles:
            findings.append({
                "pattern": "circular_dependency",
                "severity": "critical",
                "description": (
                    f"🔄 Circular Dependencies: {len(cycles)} feedback loop(s) detected. "
                    f"When Service A calls Service B which calls back to Service A, "
                    f"a single Lambda timeout or ECS task failure can trigger an "
                    f"infinite retry storm — each retry amplifying your AWS bill. "
                    f"This is the #1 cause of unexpected cost spikes."
                ),
                "affected_node": cycles[0][0] if cycles else "",
                "metric": len(cycles),
                "aws_recommendation": (
                    f"Break circular calls by introducing Amazon SQS between services "
                    f"in the loop. Add Amazon SQS Dead Letter Queues (DLQ) to catch "
                    f"retry storms. Set Lambda max retry = 2 and ECS circuit breaker "
                    f"deployment with rollback to prevent runaway invocations."
                ),
            })

        # 4. Scaling mismatch — Horizontal feeds Vertical
        asym = cascade.get("asymmetric_bottlenecks", [])
        if asym:
            findings.append({
                "pattern": "scaling_mismatch",
                "severity": "high" if len(asym) > 3 else "moderate",
                "description": (
                    f"📊 Scaling Mismatch at {len(asym)} boundary(ies): "
                    f"Your EC2 Auto Scaling groups or Lambda functions can scale out "
                    f"horizontally to handle 10× traffic. But the Amazon RDS or "
                    f"OpenSearch instances behind them scale VERTICALLY — meaning "
                    f"you'll hit a hard ceiling and pay 2-3× more per instance. "
                    f"This is why your database bill spikes during traffic surges."
                ),
                "affected_node": str(asym[0]) if asym else "",
                "metric": len(asym),
                "aws_recommendation": (
                    f"For RDS: Enable read replicas and Aurora Auto Scaling to handle "
                    f"read traffic. For OpenSearch: configure Auto-Tune and add data "
                    f"nodes. Set up CloudWatch alarms on CPUUtilization and "
                    f"DatabaseConnections to catch scaling limits before they hit."
                ),
            })

        # ── Risk score ────────────────────────────────────────────────
        risk = min(1.0, (
            (0.3 if cent_score > 0.3 else 0) +
            (0.2 if depth > 5 else 0.1 if depth > 3 else 0) +
            (0.3 if cycles else 0) +
            (0.2 if len(asym) > 2 else 0.1 if asym else 0)
        ))

        dominant = cascade.get("dominant_pattern", "balanced")

        # ── LLM enrichment (AWS-native) ───────────────────────────────
        system = (
            "You are a senior AWS Solutions Architect analyzing infrastructure topology. "
            "ALWAYS use real AWS service names (EC2, RDS, ALB, Lambda, ElastiCache, SQS, CloudWatch, etc). "
            "Explain findings in simple terms that a Cloud Engineer can immediately act on. "
            "Reference specific AWS console actions, CLI commands, or CloudFormation parameters. "
            "Every recommendation must include the expected cost impact."
        )
        user_prompt = (
            f"AWS Architecture: {arch_name} ({n_services} services, {n_deps} dependencies)\n"
            f"Dominant risk pattern: {dominant}\n"
            f"Centralization score: {cent_score:.3f} (hub: {cent_hub})\n"
            f"Max dependency chain depth: {depth}\n"
            f"Circular dependencies: {len(cycles)}\n"
            f"Scaling mismatches (horizontal→vertical): {len(asym)}\n\n"
            f"Key findings:\n" + "\n".join(f"- {f['description']}" for f in findings) +
            "\n\nProvide a 3-sentence AWS infrastructure risk summary and "
            "2 specific AWS actions (with service names and estimated cost impact)."
        )

        llm_response = self._call_llm(system, user_prompt, architecture_name=arch_name)

        analysis = llm_response if llm_response else (
            f"AWS Infrastructure Analysis for '{arch_name}': "
            f"{'⚠️ CRITICAL: Single point of failure at ' + cent_hub + ' — deploy Multi-AZ with ALB failover. ' if cent_score > 0.3 else ''}"
            f"{'Deep service chain ({} hops) adds latency — add ElastiCache layer. '.format(depth) if depth > 4 else ''}"
            f"{'🔴 {} circular dependencies creating retry storms — add SQS dead letter queues. '.format(len(cycles)) if cycles else ''}"
            f"{'Scaling mismatch at {} boundaries — enable RDS read replicas. '.format(len(asym)) if asym else ''}"
            f"Overall AWS infrastructure risk: {risk:.0%}."
        )

        recommendations = [r.get("aws_recommendation", "") for r in findings if r.get("aws_recommendation")]
        if not recommendations:
            recommendations = ["✅ Your AWS infrastructure topology looks healthy. Continue monitoring with CloudWatch."]

        elapsed = int((time.time() - t0) * 1000)
        return self._build_output(analysis, findings, risk, 0.85, recommendations, llm_response or "", elapsed)
