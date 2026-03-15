"""
Structured Recommendation Output Format
========================================
Produces cost optimization recommendations in a standardized text format.
Input: Context package + CUR data
Output: Formatted COST OPTIMIZATION RECOMMENDATION cards (text)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import textwrap


@dataclass
class ResourceIdentification:
    resource_id: str
    full_arn: str
    service: str
    instance_type: str
    region: str
    availability_zone: str
    tags: Dict[str, str]


@dataclass
class CURLineItem:
    description: str
    usage: str
    cost: float


@dataclass
class CostBreakdown:
    monthly_cost: float
    line_items: List[CURLineItem]
    cost_trend_days_1_30: float
    cost_trend_days_31_60: float
    cost_trend_days_61_90: float
    growth_rate_pct: float
    projection_90d: float


@dataclass
class Inefficiency:
    issue_num: int
    title: str
    severity: str  # HIGH, MEDIUM, LOW
    evidence: List[str]
    root_cause: str


@dataclass
class Recommendation:
    num: int
    title: str
    priority: str  # P0, P1, P2
    action: str
    current_config: str
    new_config: str
    monthly_savings: float
    annual_savings: float
    performance_impact: str
    risk_assessment: str
    implementation_steps: List[str]
    monitoring_steps: List[str]
    validation_criteria: List[str]


@dataclass
class StructuredRecommendationCard:
    resource_id: str
    resource_identification: ResourceIdentification
    cost_breakdown: CostBreakdown
    inefficiencies: List[Inefficiency]
    recommendations: List[Recommendation]
    total_monthly_savings: float
    total_annual_savings: float


class StructuredOutputFormatter:
    """Format recommendations into the standard structured text output."""

    @staticmethod
    def format_recommendation(card: StructuredRecommendationCard) -> str:
        """Format a single recommendation card to standard text output."""
        lines = []

        # Header
        lines.append("═" * 70)
        lines.append(f"COST OPTIMIZATION RECOMMENDATION #{card.resource_id}")
        lines.append("═" * 70)
        lines.append("")

        # Section 1: Resource Identification
        lines.extend(StructuredOutputFormatter._format_resource_section(card.resource_identification))
        lines.append("")

        # Section 2: Cost Breakdown
        lines.extend(StructuredOutputFormatter._format_cost_section(card.cost_breakdown))
        lines.append("")

        # Section 3: Inefficiencies
        lines.extend(StructuredOutputFormatter._format_inefficiencies_section(card.inefficiencies))
        lines.append("")

        # Section 4: Recommendations
        lines.extend(StructuredOutputFormatter._format_recommendations_section(card.recommendations))
        lines.append("")

        # Summary
        lines.append("═" * 70)
        lines.append("SUMMARY")
        lines.append("═" * 70)
        lines.append(f"Total Monthly Savings: ${card.total_monthly_savings:,.2f}")
        lines.append(f"Total Annual Savings: ${card.total_annual_savings:,.2f}")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_resource_section(res: ResourceIdentification) -> List[str]:
        """Format the resource identification section."""
        lines = [
            "═" * 70,
            "RESOURCE IDENTIFICATION",
            "═" * 70,
            "",
            f"Resource ID: {res.resource_id}",
            f"Full ARN: {res.full_arn}",
            f"Service: {res.service}",
            f"Current Instance: {res.instance_type}",
            f"Region: {res.region}",
            f"Availability Zone: {res.availability_zone}",
        ]

        if res.tags:
            tags_str = ", ".join(f"{k}={v}" for k, v in res.tags.items())
            lines.append(f"Tags: {tags_str}")

        return lines

    @staticmethod
    def _format_cost_section(cost: CostBreakdown) -> List[str]:
        """Format the cost breakdown section with CUR line items table."""
        lines = [
            "═" * 70,
            "CURRENT COST BREAKDOWN (from CUR line items)",
            "═" * 70,
            "",
            f"Monthly Costs (last 30 days):",
        ]

        # Table header
        lines.append("┌" + "─" * 40 + "┬─────────────┬──────────┐")
        lines.append(
            "│ " + "CUR Line Item".ljust(38) + " │ " 
            + "Usage".ljust(11) + " │ " + "Cost".ljust(8) + " │"
        )
        lines.append("├" + "─" * 40 + "┼─────────────┼──────────┤")

        # Table rows
        for item in cost.line_items:
            item_str = item.description[:38].ljust(38)
            usage_str = item.usage[:11].ljust(11)
            cost_str = f"${item.cost:,.2f}".ljust(8)
            lines.append(f"│ {item_str} │ {usage_str} │ {cost_str} │")

        # Table footer
        lines.append("├" + "─" * 40 + "┼─────────────┼──────────┤")
        total_str = f"${cost.monthly_cost:,.2f}".ljust(8)
        lines.append(f"│ {'TOTAL MONTHLY COST'.ljust(38)} │ " + " " * 11 + " │ " + total_str + " │")
        lines.append("└" + "─" * 40 + "┴─────────────┴──────────┘")

        # Trend analysis
        lines.append("")
        lines.append("Cost Trend (90 days from CUR):")
        lines.append(f"- Days 1-30: ${cost.cost_trend_days_1_30:,.2f}")
        lines.append(f"- Days 31-60: ${cost.cost_trend_days_31_60:,.2f}")
        lines.append(f"- Days 61-90: ${cost.cost_trend_days_61_90:,.2f}")
        lines.append(f"- Growth rate: {cost.growth_rate_pct:+.1f}% over 90 days")
        lines.append(f"- Projection: ${cost.projection_90d:,.2f}/month in 90 days if unchanged")

        return lines

    @staticmethod
    def _format_inefficiencies_section(inefficiencies: List[Inefficiency]) -> List[str]:
        """Format inefficiencies detected section."""
        lines = [
            "═" * 70,
            f"INEFFICIENCIES DETECTED ({len(inefficiencies)} issues found)",
            "═" * 70,
            "",
        ]

        for ineff in inefficiencies:
            lines.append(f"ISSUE #{ineff.issue_num}: {ineff.title} ({ineff.severity} SEVERITY)")
            lines.append("Source: CUR usage metrics + CloudWatch")
            lines.append("Evidence:")
            for ev in ineff.evidence:
                lines.append(f"- {ev}")
            lines.append(f"Assessment: {ineff.root_cause}")
            lines.append("")

        return lines

    @staticmethod
    def _format_recommendations_section(recommendations: List[Recommendation]) -> List[str]:
        """Format comprehensive recommendations section."""
        lines = [
            "═" * 70,
            "COMPREHENSIVE RECOMMENDATIONS (Prioritized by Savings)",
            "═" * 70,
            "",
        ]

        for rec in recommendations:
            lines.append(f"RECOMMENDATION #{rec.num}: {rec.title}")
            lines.append(f"Priority: {rec.priority} (Highest savings, zero risk)")
            lines.append("")

            lines.append("Action:")
            lines.extend(textwrap.wrap(rec.action, width=66))
            lines.append("")

            lines.append("Current Configuration:")
            lines.extend(textwrap.wrap(rec.current_config, width=66))
            lines.append("")

            lines.append("New Configuration:")
            lines.extend(textwrap.wrap(rec.new_config, width=66))
            lines.append("")

            lines.append("Savings Calculation:")
            lines.append(f"- Monthly savings: ${rec.monthly_savings:,.2f}")
            lines.append(f"- Annual savings: ${rec.annual_savings:,.2f}")
            lines.append("")

            lines.append("Performance Impact:")
            lines.extend(textwrap.wrap(rec.performance_impact, width=66))
            lines.append("")

            lines.append("Risk Mitigation:")
            lines.extend(textwrap.wrap(rec.risk_assessment, width=66))
            lines.append("")

            lines.append("Implementation Steps:")
            for i, step in enumerate(rec.implementation_steps, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

            lines.append("Validation:")
            for i, val in enumerate(rec.validation_criteria, 1):
                lines.append(f"- {val}")
            lines.append("")
            lines.append("---")
            lines.append("")

        return lines
