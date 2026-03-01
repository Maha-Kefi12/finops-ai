"""
Agent 5 — AWS Executive Synthesizer
Aggregates findings from all 4 agents into a clear AWS executive summary
with risk verdict, financial exposure projection, and prioritized actions.

This agent answers: "What should leadership know and do about our AWS costs?"
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from .base_agent import BaseAgent, AgentOutput


class ExecutiveSynthesizerAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        self.role = "executive_synthesizer"

    def analyze(self, context: Dict[str, Any]) -> AgentOutput:
        t0 = time.time()

        arch_name = context.get("architecture_name", "Unknown")
        baseline = context.get("baseline_cost", 0)
        pattern = context.get("architecture_pattern", "")
        n_services = context.get("n_services", 0)

        topo = context.get("topology_output", {})
        behavior = context.get("behavior_output", {})
        cost = context.get("cost_output", {})
        detective = context.get("detective_output", {})

        # ── Aggregate risk ────────────────────────────────────────────
        risks = [
            topo.get("risk_score", 0),
            behavior.get("risk_score", 0),
            cost.get("risk_score", 0),
            detective.get("risk_score", 0),
        ]
        overall_risk = max(risks)
        avg_risk = sum(risks) / len(risks)

        # ── Verdict ───────────────────────────────────────────────────
        if overall_risk > 0.7:
            verdict = "🔴 HIGH RISK — Immediate AWS action required"
            verdict_detail = (
                f"Your {arch_name} architecture has critical cost spike risks. "
                f"Based on {n_services} AWS services analysis, there's a high probability "
                f"of unexpected bill increases during traffic surges. "
                f"Without intervention, your monthly AWS spend could jump from "
                f"${baseline:,.0f} to ${baseline * 2.5:,.0f}+ during peak events."
            )
        elif overall_risk > 0.4:
            verdict = "🟡 MODERATE RISK — Proactive AWS optimization recommended"
            verdict_detail = (
                f"Your {arch_name} architecture has moderate cost risks that should "
                f"be addressed before the next traffic spike. "
                f"Current baseline of ${baseline:,.0f}/mo could increase to "
                f"${baseline * 1.8:,.0f}/mo during peak events. "
                f"Key actions can reduce this exposure by 30-50%."
            )
        else:
            verdict = "🟢 LOW RISK — Architecture is well-optimized"
            verdict_detail = (
                f"Your {arch_name} architecture handles traffic spikes efficiently. "
                f"AWS costs scale linearly with traffic. Baseline ${baseline:,.0f}/mo. "
                f"Continue monitoring with AWS Cost Anomaly Detection."
            )

        findings: List[Dict[str, Any]] = []
        findings.append({
            "pattern": "executive_verdict",
            "severity": "critical" if overall_risk > 0.7 else "high" if overall_risk > 0.4 else "low",
            "description": f"{verdict} — {verdict_detail}",
            "affected_node": "",
            "metric": overall_risk,
        })

        # ── Financial exposure ────────────────────────────────────────
        mc = context.get("monte_carlo_report", {})
        scenarios = mc.get("scenario_results", [])
        spike_sc = next((s for s in scenarios if s.get("traffic_multiplier", 1) >= 3), None)

        if spike_sc and baseline > 0:
            spike_cost = spike_sc.get("cost_p95", baseline * 2)
            annual_exposure = (spike_cost - baseline) * 3  # assume 3 spike months/year

            findings.append({
                "pattern": "financial_exposure",
                "severity": "high" if annual_exposure > baseline * 6 else "moderate",
                "description": (
                    f"💵 Annual Financial Exposure: ${annual_exposure:,.0f}. "
                    f"Based on Monte Carlo simulations, if you experience 3 traffic spike "
                    f"months per year (Black Friday, product launches, seasonal peaks), "
                    f"your AWS bill could exceed budget by ${annual_exposure:,.0f} annually. "
                    f"P95 worst-case monthly cost: ${spike_cost:,.0f} vs baseline ${baseline:,.0f}."
                ),
                "affected_node": "",
                "metric": annual_exposure,
            })

        # ── Collect all unique recommendations from sub-agents ────────
        all_recs = []
        seen = set()
        for agent_output in [topo, behavior, cost, detective]:
            for r in agent_output.get("recommendations", []):
                if r and r not in seen:
                    all_recs.append(r)
                    seen.add(r)

        # ── LLM enrichment ────────────────────────────────────────────
        system = (
            "You are a VP of Cloud FinOps presenting to the CTO. "
            "Write an executive summary in plain language that a non-technical "
            "executive can understand, BUT use real AWS service names. "
            "Structure: (1) One-sentence verdict, (2) Financial exposure in dollars, "
            "(3) Top 3 prioritized actions with expected savings. "
            "Keep it under 200 words. Be direct, not academic."
        )
        user_prompt = (
            f"AWS Architecture: {arch_name} ({pattern}, {n_services} services, ${baseline:,.0f}/mo)\n"
            f"Risk scores: Topology={risks[0]:.0%}, Behavior={risks[1]:.0%}, "
            f"Cost={risks[2]:.0%}, Root Cause={risks[3]:.0%}\n"
            f"Overall: {overall_risk:.0%}\n"
            f"Verdict: {verdict}\n\n"
            f"Top detective findings:\n"
            + "\n".join(f"- {f['description'][:200]}" for f in detective.get("findings", [])[:3]) +
            f"\n\nTop recommendations:\n"
            + "\n".join(f"- {r[:200]}" for r in all_recs[:5]) +
            "\n\nWrite a 150-word executive summary for the CTO. "
            "Include dollar amounts and specific AWS service actions."
        )

        llm_response = self._call_llm(system, user_prompt, architecture_name=arch_name)

        analysis = llm_response if llm_response else verdict_detail

        # ── Prioritized recommendation list ───────────────────────────
        prioritized = all_recs[:6] if all_recs else [
            "✅ Your AWS architecture is well-optimized. Continue monitoring with CloudWatch."
        ]

        elapsed = int((time.time() - t0) * 1000)
        return self._build_output(analysis, findings, overall_risk, 0.90,
                                  prioritized, llm_response or "", elapsed)
