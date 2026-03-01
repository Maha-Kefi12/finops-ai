"""
Agent 2 — AWS Behavior Scientist
Analyzes Monte Carlo simulation results to detect nonlinear cost amplification,
cascade formation, and explosive growth patterns in AWS services.

This agent answers: "How do your AWS services BEHAVE under traffic pressure?"
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from .base_agent import BaseAgent, AgentOutput


class BehaviorScientistAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        self.role = "behavior_scientist"

    def analyze(self, context: Dict[str, Any]) -> AgentOutput:
        t0 = time.time()

        mc = context.get("monte_carlo_report", {})
        cascade = context.get("cascade_analysis", {})
        arch_name = context.get("architecture_name", "Unknown")
        baseline = context.get("baseline_cost", 0)

        findings: List[Dict[str, Any]] = []

        # ── 1. Nonlinear cost amplification ───────────────────────────
        scenarios = mc.get("scenario_results", [])
        for sc in scenarios:
            cost_mult = sc.get("cost_multiplier_mean", 1.0)
            traffic = sc.get("traffic_multiplier", 1.0)
            if cost_mult > traffic * 1.15:  # Cost growing faster than traffic
                amp_factor = cost_mult / traffic
                findings.append({
                    "pattern": "nonlinear_cost_growth",
                    "severity": "critical" if amp_factor > 1.5 else "high",
                    "description": (
                        f"💰 Nonlinear Cost Growth at {traffic:.0f}× traffic: "
                        f"Your AWS bill grows {cost_mult:.1f}× while traffic only grew {traffic:.0f}×. "
                        f"This means for every $1 of baseline cost, you'd pay ${cost_mult:.2f} during "
                        f"a traffic surge. The main culprits are vertically-scaled services like "
                        f"Amazon RDS instances that hit their vCPU/memory ceiling and force "
                        f"expensive instance size upgrades (e.g., db.r6g.xlarge → db.r6g.4xlarge = 4× cost)."
                    ),
                    "affected_node": sc.get("label", ""),
                    "metric": amp_factor,
                    "aws_recommendation": (
                        f"Enable Amazon RDS Aurora Auto Scaling for read replicas to handle "
                        f"read traffic horizontally. For write-heavy workloads, consider "
                        f"Amazon DynamoDB with on-demand capacity. Set up AWS Cost Anomaly "
                        f"Detection alerts for any service exceeding {traffic:.0f}× normal spend. "
                        f"Expected savings: 25-40% during traffic spikes."
                    ),
                })
                break

        # ── 2. Cascade probability ────────────────────────────────────
        instability = mc.get("overall_instability_score", 0)
        top_risks = mc.get("top_risk_nodes", [])
        if instability > 0.3:
            risky_services = ", ".join(n.get("node", "?") for n in top_risks[:3])
            findings.append({
                "pattern": "cascade_risk",
                "severity": "critical" if instability > 0.6 else "high",
                "description": (
                    f"⚡ Cascade Risk = {instability:.0%}: There's a {instability:.0%} probability "
                    f"that a single AWS service failure cascades to others. "
                    f"Highest-risk resources: {risky_services}. "
                    f"This means if {top_risks[0]['node'] if top_risks else 'a service'} experiences "
                    f"high CPU utilization or throttling, downstream services (Lambda functions, "
                    f"ECS tasks, API Gateway endpoints) will start timing out and retrying — "
                    f"multiplying your CloudWatch Logs, X-Ray traces, and Lambda invocation costs."
                ),
                "affected_node": top_risks[0]["node"] if top_risks else "",
                "metric": instability,
                "aws_recommendation": (
                    f"Set up Amazon CloudWatch Composite Alarms that trigger when BOTH "
                    f"CPUUtilization > 80% AND request latency > 500ms on {risky_services}. "
                    f"Add AWS Application Auto Scaling step policies to scale out BEFORE "
                    f"hitting capacity. Deploy AWS Fault Injection Simulator (FIS) to "
                    f"test cascade resilience. Enable Lambda reserved concurrency to "
                    f"prevent one function from starving others."
                ),
            })

        # ── 3. Overload probability ───────────────────────────────────
        overload_nodes = mc.get("overload_probabilities", {})
        high_overload = [(k, v) for k, v in overload_nodes.items() if v > 0.2]
        high_overload.sort(key=lambda x: x[1], reverse=True)
        if high_overload:
            node, prob = high_overload[0]
            findings.append({
                "pattern": "service_overload",
                "severity": "high" if prob > 0.5 else "moderate",
                "description": (
                    f"🔴 Service Overload Predicted: {node} has a {prob:.0%} probability "
                    f"of exceeding its capacity limit during traffic spikes. "
                    f"In AWS terms, this means hitting EC2 instance CPU limits, RDS max connections, "
                    f"or Lambda concurrent execution quota. When this happens, requests queue up "
                    f"in the ALB, CloudWatch alarm fires, and your on-call team gets paged at 3 AM."
                ),
                "affected_node": node,
                "metric": prob,
                "aws_recommendation": (
                    f"For {node}: Request a Service Quota increase via AWS Service Quotas console. "
                    f"Enable Predictive Auto Scaling (uses ML to pre-scale before demand hits). "
                    f"Add an Amazon ElastiCache layer to reduce database load by 60-80%. "
                    f"Set CloudWatch alarm: trigger scale-out at 60% capacity, not 80%."
                ),
            })

        # ── 4. Cost spike at specific scenarios ───────────────────────
        risk_class = mc.get("overall_risk_class", "moderate")
        cost_p95 = 0
        cost_mean = 0
        for sc in scenarios:
            if sc.get("traffic_multiplier", 1) >= 3:
                cost_p95 = sc.get("cost_p95", 0)
                cost_mean = sc.get("cost_mean", 0)
                break

        if cost_p95 > baseline * 2.5 and baseline > 0:
            findings.append({
                "pattern": "cost_spike",
                "severity": "critical",
                "description": (
                    f"💸 Cost Spike Alert: At 3× traffic, there's a 5% chance your "
                    f"monthly AWS bill hits ${cost_p95:,.0f} "
                    f"(vs baseline ${baseline:,.0f}/mo — that's {cost_p95/baseline:.1f}× more). "
                    f"This is the P95 worst case from {mc.get('n_trials', 0):,} Monte Carlo simulations. "
                    f"The spike comes from vertical-scaling services (RDS instance upgrades, "
                    f"OpenSearch domain resize) combined with increased data transfer charges."
                ),
                "affected_node": "",
                "metric": cost_p95 / baseline if baseline else 0,
                "aws_recommendation": (
                    f"Buy Savings Plans to lock in baseline rates (saves 20-30%). "
                    f"Set AWS Budgets alert at ${baseline * 1.5:,.0f}/mo (150% threshold). "
                    f"Enable AWS Cost Anomaly Detection to catch spikes within 24 hours. "
                    f"Consider Reserved Instances for your Amazon RDS and ElastiCache — "
                    f"1-year RI saves ~40% vs on-demand."
                ),
            })

        # ── Risk score ────────────────────────────────────────────────
        risk = min(1.0, instability * 0.4 + (0.3 if high_overload else 0) +
                   (0.3 if cost_p95 > baseline * 2 else 0.1))

        # ── LLM enrichment ────────────────────────────────────────────
        system = (
            "You are a senior AWS FinOps analyst specializing in behavioral cost analysis. "
            "ALWAYS use AWS service names (EC2, RDS, Lambda, CloudWatch, Cost Explorer). "
            "Explain cost spikes in terms of AWS billing mechanisms: "
            "On-Demand vs Reserved pricing, data transfer charges, Lambda invocation costs, "
            "RDS instance size pricing tiers. Keep it simple and actionable."
        )
        user_prompt = (
            f"Architecture: {arch_name} (baseline: ${baseline:,.0f}/mo)\n"
            f"Monte Carlo risk class: {risk_class}, instability: {instability:.0%}\n"
            f"Top risk AWS resources: {', '.join(n.get('node', '') for n in top_risks[:3])}\n\n"
            f"Behavioral findings:\n" + "\n".join(f"- {f['description']}" for f in findings) +
            "\n\nExplain in simple AWS terms why this architecture's costs spike "
            "nonlinearly and give 2 specific AWS actions to prevent it."
        )

        llm_response = self._call_llm(system, user_prompt, architecture_name=arch_name)

        analysis = llm_response if llm_response else (
            f"Behavioral Analysis for '{arch_name}': "
            f"Risk class = {risk_class.upper()}, cascade probability = {instability:.0%}. "
            + (" ".join(f["description"] for f in findings[:2]))
        )

        recommendations = [r.get("aws_recommendation", "") for r in findings if r.get("aws_recommendation")]
        if not recommendations:
            recommendations = ["✅ AWS services are scaling linearly — no nonlinear cost risks detected."]

        elapsed = int((time.time() - t0) * 1000)
        return self._build_output(analysis, findings, risk, 0.80, recommendations, llm_response or "", elapsed)
