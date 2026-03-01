"""
Agent 4 — AWS Risk Detective
Cross-correlates topology, behavior, and cost findings to identify the
root-of-root-cause: the AWS resource(s) that appear across ALL analyses
as structural hubs, behavioral bottlenecks, AND cost amplifiers.

This agent answers: "What's the REAL root cause hiding behind your AWS cost spikes?"
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any, Dict, List

from .base_agent import BaseAgent, AgentOutput


class RiskDetectiveAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        self.role = "risk_detective"

    def analyze(self, context: Dict[str, Any]) -> AgentOutput:
        t0 = time.time()

        arch_name = context.get("architecture_name", "Unknown")
        baseline = context.get("baseline_cost", 0)

        topo = context.get("topology_output", {})
        behavior = context.get("behavior_output", {})
        cost = context.get("cost_output", {})
        cascade = context.get("cascade_analysis", {})

        findings: List[Dict[str, Any]] = []

        # ── Cross-correlate: find nodes that appear in ALL analyses ────
        node_mentions = Counter()
        source_map = {}

        for source_name, output in [("topology", topo), ("behavior", behavior), ("cost", cost)]:
            for f in output.get("findings", []):
                node = f.get("affected_node") or f.get("node", "")
                if node and node != "unknown":
                    node_mentions[node] += 1
                    source_map.setdefault(node, set()).add(source_name)

        # Root of root cause: nodes appearing in 2+ analyses
        root_causes = [(node, count) for node, count in node_mentions.most_common(10) if count >= 2]

        # Build amplification lookup from list of dicts
        amp_list = cascade.get("node_amplifications", [])
        amp_lookup = {}
        if isinstance(amp_list, list):
            for n in amp_list:
                key = n.get("node_name", n.get("node_id", ""))
                amp_lookup[key] = n.get("cost_amplification", 1.0)
        elif isinstance(amp_list, dict):
            amp_lookup = amp_list

        for node, count in root_causes[:3]:
            sources = source_map.get(node, set())
            amp = amp_lookup.get(node, 1.0)

            findings.append({
                "pattern": "root_of_root_cause",
                "severity": "critical" if count >= 3 else "high",
                "description": (
                    f"🎯 ROOT CAUSE IDENTIFIED: {node} appears in {count} out of 3 "
                    f"independent analyses ({', '.join(sorted(sources))}). "
                    f"This AWS resource is simultaneously a structural bottleneck, "
                    f"a behavioral risk point, AND a cost amplifier ({amp:.2f}×). "
                    f"This is your #1 priority to fix — it's the hidden reason behind "
                    f"your unpredictable AWS bills. Think of it like a clogged pipe: "
                    f"everything upstream backs up and everything downstream starves."
                ),
                "affected_node": node,
                "metric": count,
                "aws_recommendation": (
                    f"Immediate action for {node}:\n"
                    f"1. Open Amazon CloudWatch → Metrics → search '{node}' → check CPUUtilization, "
                    f"DatabaseConnections, and ReadLatency trends over the last 7 days\n"
                    f"2. If it's an RDS instance: enable Multi-AZ, add read replicas, "
                    f"or migrate to Aurora Serverless v2\n"
                    f"3. If it's an EC2/ECS service: enable Predictive Auto Scaling "
                    f"and set target tracking at 60% CPU\n"
                    f"4. Add Amazon ElastiCache in front to absorb 60-80% of read traffic\n"
                    f"5. Set up AWS Cost Anomaly Detection monitor specifically for this resource"
                ),
            })

        # ── Failure scenario construction ─────────────────────────────
        if root_causes:
            top_node = root_causes[0][0]
            root_cause_nodes = [n for n, _ in root_causes[:3]]
            risk_scores = [topo.get("risk_score", 0), behavior.get("risk_score", 0), cost.get("risk_score", 0)]
            avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0.5

            findings.append({
                "pattern": "failure_scenario",
                "severity": "critical" if avg_risk > 0.6 else "high",
                "description": (
                    f"🔮 Predicted Failure Scenario: When traffic spikes 2-3× "
                    f"(Black Friday, viral event, DDoS), here's what happens:\n"
                    f"Step 1: {top_node} hits its capacity limit (CPU > 90% or max connections)\n"
                    f"Step 2: Upstream services start queuing requests (ALB 504 timeouts increase)\n"
                    f"Step 3: Lambda functions and ECS tasks retry failed requests (3× retry = 3× cost)\n"
                    f"Step 4: CloudWatch Logs volume explodes (each retry = more log entries)\n"
                    f"Step 5: Your AWS bill for this month is 2-4× higher than expected.\n"
                    f"This entire chain starts from one resource: {top_node}."
                ),
                "affected_node": top_node,
                "metric": avg_risk,
                "aws_recommendation": (
                    f"Build an AWS incident runbook for this scenario:\n"
                    f"1. CloudWatch Dashboard: Create a custom dashboard showing {', '.join(root_cause_nodes)} metrics side-by-side\n"
                    f"2. SNS Alert Chain: CloudWatch Alarm → SNS Topic → Lambda function → auto-scale {top_node}\n"
                    f"3. AWS Fault Injection Simulator: Run a chaos test simulating {top_node} failure to validate your auto-recovery\n"
                    f"4. Cost containment: Set AWS Budgets action to automatically stop non-critical EC2 instances when bill exceeds 200% of baseline"
                ),
            })

        # ── Risk score ────────────────────────────────────────────────
        risk_scores = [topo.get("risk_score", 0), behavior.get("risk_score", 0), cost.get("risk_score", 0)]
        risk = max(risk_scores) if risk_scores else 0.5

        # ── LLM enrichment ────────────────────────────────────────────
        system = (
            "You are an AWS FinOps Root Cause Analyst. Your job is to find the HIDDEN "
            "reason behind unpredictable AWS cost spikes. You have data from 3 independent "
            "analyses (topology, behavior, cost). Cross-correlate them to find the one "
            "AWS resource that's causing everything. Use AWS service names ONLY. "
            "Explain the cause-effect chain in simple terms. "
            "Your recommendations must be specific AWS console actions step-by-step."
        )
        correlated = ", ".join(f"{n} ({c} analyses)" for n, c in root_causes[:3])
        user_prompt = (
            f"Architecture: {arch_name} (baseline: ${baseline:,.0f}/mo)\n"
            f"Topology risk: {topo.get('risk_score', 0):.0%}, "
            f"Behavior risk: {behavior.get('risk_score', 0):.0%}, "
            f"Cost risk: {cost.get('risk_score', 0):.0%}\n"
            f"Cross-correlated root causes: {correlated or 'none found'}\n\n"
            f"Findings:\n" + "\n".join(f"- {f['description']}" for f in findings) +
            "\n\nExplain the root-of-root-cause in simple AWS terms. "
            "What specific AWS resource is the hidden trigger? "
            "Give a step-by-step AWS remediation plan."
        )

        llm_response = self._call_llm(system, user_prompt, architecture_name=arch_name)

        analysis = llm_response if llm_response else (
            f"Root Cause Analysis for '{arch_name}': "
            + (" ".join(f["description"] for f in findings[:2]) if findings
               else "No cross-correlated root causes detected — each risk is independent.")
        )

        recommendations = [r.get("aws_recommendation", "") for r in findings if r.get("aws_recommendation")]
        if not recommendations:
            recommendations = ["✅ No cross-correlated root cause found. Individual risks are manageable."]

        elapsed = int((time.time() - t0) * 1000)
        return self._build_output(analysis, findings, risk, 0.88, recommendations, llm_response or "", elapsed)
