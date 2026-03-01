"""
Agent 3 — AWS Cost Economist
Analyzes cost distributions from Monte Carlo simulations to identify
cost amplifier resources, spending concentration, and cost spike risk.

This agent answers: "Which AWS resources drive your biggest cost spikes?"
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List

from .base_agent import BaseAgent, AgentOutput


class CostEconomistAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        self.role = "cost_economist"

    def analyze(self, context: Dict[str, Any]) -> AgentOutput:
        t0 = time.time()

        mc = context.get("monte_carlo_report", {})
        cascade = context.get("cascade_analysis", {})
        arch_name = context.get("architecture_name", "Unknown")
        baseline = context.get("baseline_cost", 0)

        findings: List[Dict[str, Any]] = []

        # ── 1. Identify cost amplifier nodes ──────────────────────────
        node_amps_raw = cascade.get("node_amplifications", [])
        # node_amplifications is a list of dicts from asdict(cascade)
        if isinstance(node_amps_raw, list):
            amplifiers = sorted(
                [(n.get("node_name", n.get("node_id", "?")), n.get("cost_amplification", 1.0))
                 for n in node_amps_raw],
                key=lambda x: x[1], reverse=True
            )[:5]
        elif isinstance(node_amps_raw, dict):
            amplifiers = sorted(node_amps_raw.items(), key=lambda x: x[1], reverse=True)[:5]
        else:
            amplifiers = []

        for node, amp in amplifiers:
            if amp > 1.2:
                findings.append({
                    "pattern": "cost_amplifier",
                    "severity": "critical" if amp > 1.5 else "high" if amp > 1.3 else "moderate",
                    "description": (
                        f"💰 Cost Amplifier: {node} multiplies your AWS costs by {amp:.2f}× "
                        f"during traffic surges. This happens because this resource scales "
                        f"vertically (bigger instance = exponentially more expensive). "
                        f"For example, an RDS db.r6g.xlarge costs $0.48/hr, but upgrading "
                        f"to db.r6g.4xlarge for 2× load costs $1.92/hr (4× the price for 2× capacity)."
                    ),
                    "affected_node": node,
                    "metric": amp,
                    "aws_recommendation": (
                        f"For {node}: Switch to Amazon Aurora Serverless v2 (auto-scales "
                        f"in 0.5 ACU increments, pay only for what you use). "
                        f"Or add Amazon ElastiCache to absorb 60-80% of read queries "
                        f"before they hit the database. "
                        f"Estimated savings: ${baseline * (amp - 1) * 0.3:,.0f}/mo during spikes."
                    ),
                })

        # ── 2. Cost concentration (Pareto analysis) ───────────────────
        bottlenecks = cascade.get("bottleneck_nodes", [])
        if len(bottlenecks) >= 2 and context.get("n_services", 0) > 5:
            pct = len(bottlenecks) / max(context.get("n_services", 1), 1)
            findings.append({
                "pattern": "cost_concentration",
                "severity": "high" if pct < 0.3 else "moderate",
                "description": (
                    f"📊 Cost Concentration: {len(bottlenecks)} out of "
                    f"{context.get('n_services', 0)} AWS resources drive most of your "
                    f"cost variability. These are: {', '.join(bottlenecks[:5])}. "
                    f"In AWS Cost Explorer, these would show up as your top cost drivers "
                    f"in the 'Service' breakdown view. This 80/20 pattern means "
                    f"optimizing just these {len(bottlenecks)} resources cuts your "
                    f"overall cost risk significantly."
                ),
                "affected_node": bottlenecks[0] if bottlenecks else "",
                "metric": pct,
                "aws_recommendation": (
                    f"In AWS Cost Explorer: Go to Cost Explorer → Group by 'Service' → "
                    f"filter to {', '.join(bottlenecks[:3])}. "
                    f"Apply AWS Cost Allocation Tags to track these resources per team. "
                    f"Buy Compute Savings Plans for EC2/Fargate baselines. "
                    f"Use Reserved Instances for RDS and ElastiCache nodes. "
                    f"Expected savings: 20-40% on your top {len(bottlenecks)} resources."
                ),
            })

        # ── 3. Spike vs steady-state variance ────────────────────────
        scenarios = mc.get("scenario_results", [])
        steady = next((s for s in scenarios if s.get("label") == "steady_state"), None)
        spike = next((s for s in scenarios if s.get("label") in ("spike", "extreme")), None)

        if steady and spike:
            steady_cost = steady.get("cost_mean", baseline)
            spike_cost = spike.get("cost_mean", baseline)
            spike_std = spike.get("cost_std", 0)
            volatility = spike_cost / max(steady_cost, 1)

            if volatility > 1.5:
                findings.append({
                    "pattern": "cost_volatility",
                    "severity": "critical" if volatility > 2.5 else "high",
                    "description": (
                        f"📈 High Cost Volatility: Your AWS bill swings from "
                        f"${steady_cost:,.0f}/mo in steady state to ${spike_cost:,.0f}/mo "
                        f"during spikes ({volatility:.1f}× jump). "
                        f"The standard deviation is ±${spike_std:,.0f}, meaning your "
                        f"monthly AWS bill is unpredictable. "
                        f"This makes budgeting impossible — your CFO will see a different "
                        f"number every month. AWS Cost Anomaly Detection would flag this."
                    ),
                    "affected_node": "",
                    "metric": volatility,
                    "aws_recommendation": (
                        f"Enable AWS Cost Anomaly Detection in the AWS Billing console — "
                        f"it uses ML to detect unusual spend patterns within 24 hours. "
                        f"Set AWS Budgets alerts at: ${{steady_cost * 1.2:,.0f}} (warning), "
                        f"${spike_cost * 0.8:,.0f} (critical). "
                        f"Buy Savings Plans to cover your steady-state baseline of "
                        f"${steady_cost:,.0f}/mo, then use On-Demand for burst traffic. "
                        f"This alone saves 20-30% on your baseline costs."
                    ),
                })

        # ── 4. Data Transfer costs ────────────────────────────────────
        n_deps = context.get("n_dependencies", 0)
        if n_deps > 20:
            estimated_transfer = n_deps * 50  # rough estimate
            findings.append({
                "pattern": "data_transfer_risk",
                "severity": "moderate",
                "description": (
                    f"🌐 Data Transfer Cost Risk: With {n_deps} service dependencies, "
                    f"each inter-service call generates data transfer charges. "
                    f"Cross-AZ transfers cost $0.01/GB, and cross-region costs $0.02-0.09/GB. "
                    f"At scale, this can add ${estimated_transfer:,}+/mo to your AWS bill "
                    f"that doesn't show up until you check Cost Explorer by 'Usage Type'."
                ),
                "affected_node": "",
                "metric": n_deps,
                "aws_recommendation": (
                    f"Check AWS Cost Explorer → Group by 'Usage Type' → filter 'DataTransfer'. "
                    f"Deploy services in the SAME Availability Zone where possible. "
                    f"Use VPC Endpoints for S3 and DynamoDB to avoid NAT Gateway charges. "
                    f"Enable S3 Transfer Acceleration for cross-region access."
                ),
            })

        # ── Risk score ────────────────────────────────────────────────
        amp_values = [a for _, a in amplifiers if a > 1.0]
        avg_amp = sum(amp_values) / len(amp_values) if amp_values else 1.0
        risk = min(1.0, (avg_amp - 1.0) * 1.5 + (0.2 if len(bottlenecks) > 3 else 0))

        # ── LLM enrichment ────────────────────────────────────────────
        system = (
            "You are an AWS Cost Optimization specialist. "
            "ALWAYS reference specific AWS services, pricing models, and billing mechanisms. "
            "Use terms like: On-Demand, Reserved Instances, Savings Plans, Spot Instances, "
            "Cost Explorer, Cost Anomaly Detection, AWS Budgets, Cost Allocation Tags. "
            "Explain WHY costs spike in AWS billing terms, not abstract economics."
        )
        user_prompt = (
            f"Architecture: {arch_name} (baseline: ${baseline:,.0f}/mo)\n"
            f"Top cost amplifiers: {', '.join(f'{n} ({a:.2f}×)' for n, a in amplifiers[:3])}\n"
            f"Cost bottleneck resources: {', '.join(bottlenecks[:5])}\n\n"
            f"Findings:\n" + "\n".join(f"- {f['description']}" for f in findings) +
            "\n\nExplain in AWS billing terms why costs spike and give "
            "2 specific AWS cost optimization actions with dollar savings estimates."
        )

        llm_response = self._call_llm(system, user_prompt, architecture_name=arch_name)

        analysis = llm_response if llm_response else (
            f"AWS Cost Analysis for '{arch_name}': "
            + " ".join(f["description"] for f in findings[:2])
        )

        recommendations = [r.get("aws_recommendation", "") for r in findings if r.get("aws_recommendation")]
        if not recommendations:
            recommendations = ["✅ Your AWS costs scale linearly with traffic — no amplification detected."]

        elapsed = int((time.time() - t0) * 1000)
        return self._build_output(analysis, findings, risk, 0.82, recommendations, llm_response or "", elapsed)
