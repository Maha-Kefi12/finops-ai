"""
PDF export utilities for FinOps AI reports and recommendations
"""

from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


def _get_styles():
    """Get custom paragraph styles for reports."""
    styles = getSampleStyleSheet()
    
    # Title style
    styles.add(ParagraphStyle(
        name='CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1f2937'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    ))
    
    # Heading style
    styles.add(ParagraphStyle(
        name='CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#374151'),
        spaceAfter=8,
        fontName='Helvetica-Bold'
    ))
    
    # Normal text
    styles.add(ParagraphStyle(
        name='CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#4b5563'),
        spaceAfter=6,
    ))
    
    return styles


def generate_llm_report_pdf(
    architecture_id: str,
    architecture_name: str,
    report_data: Dict[str, Any],
    generation_time_ms: Optional[int] = None,
) -> bytes:
    """
    Generate PDF for 5-agent LLM pipeline report.
    
    Args:
        architecture_id: Architecture identifier
        architecture_name: Human-readable architecture name
        report_data: Full report payload from the 5-agent pipeline
        generation_time_ms: Generation time in milliseconds
        
    Returns:
        PDF bytes
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = _get_styles()
    elements = []
    
    # Header
    elements.append(Paragraph("FinOps AI - 5-Agent Pipeline Report", styles['CustomTitle']))
    elements.append(Spacer(1, 12))
    
    # Metadata
    metadata_data = [
        ["Architecture ID", architecture_id],
        ["Architecture Name", architecture_name],
        ["Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")],
        ["Generation Time", f"{generation_time_ms}ms" if generation_time_ms else "N/A"],
    ]
    
    metadata_table = Table(metadata_data, colWidths=[2*inch, 4*inch])
    metadata_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1f2937')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
    ]))
    elements.append(metadata_table)
    elements.append(Spacer(1, 12))
    
    # Summary section
    if isinstance(report_data, dict):
        if "summary" in report_data:
            elements.append(Paragraph("Executive Summary", styles['CustomHeading']))
            summary = report_data["summary"]
            if isinstance(summary, dict):
                for key, value in summary.items():
                    if value:
                        elements.append(Paragraph(
                            f"<b>{key}:</b> {str(value)[:200]}...", 
                            styles['CustomNormal']
                        ))
            else:
                elements.append(Paragraph(str(summary)[:500], styles['CustomNormal']))
            elements.append(Spacer(1, 8))
        
        # Agents section
        if "agents" in report_data:
            elements.append(PageBreak())
            elements.append(Paragraph("Agent Analysis Results", styles['CustomHeading']))
            
            agents = report_data["agents"]
            if isinstance(agents, dict):
                for agent_name, agent_data in agents.items():
                    elements.append(Paragraph(f"Agent: {agent_name}", styles['Heading3']))
                    if isinstance(agent_data, dict):
                        for key, value in agent_data.items():
                            if isinstance(value, (str, int, float)):
                                elements.append(Paragraph(
                                    f"• <b>{key}:</b> {str(value)[:150]}", 
                                    styles['CustomNormal']
                                ))
                    elements.append(Spacer(1, 6))
        
        # Findings section
        if "findings" in report_data:
            elements.append(Paragraph("Key Findings", styles['CustomHeading']))
            findings = report_data["findings"]
            if isinstance(findings, list):
                for i, finding in enumerate(findings[:10], 1):  # Limit to 10
                    elements.append(Paragraph(
                        f"{i}. {str(finding)[:200]}", 
                        styles['CustomNormal']
                    ))
            elif isinstance(findings, dict):
                for key, value in findings.items():
                    elements.append(Paragraph(
                        f"• <b>{key}:</b> {str(value)[:200]}", 
                        styles['CustomNormal']
                    ))
            elements.append(Spacer(1, 8))
        
        # Recommendations from report
        if "recommendations" in report_data:
            elements.append(Paragraph("Recommendations", styles['CustomHeading']))
            recs = report_data["recommendations"]
            if isinstance(recs, list):
                for i, rec in enumerate(recs[:5], 1):  # Limit to 5
                    elements.append(Paragraph(f"{i}. {str(rec)[:250]}", styles['CustomNormal']))
            elif isinstance(recs, dict):
                for key, value in recs.items():
                    elements.append(Paragraph(
                        f"• <b>{key}:</b> {str(value)[:200]}", 
                        styles['CustomNormal']
                    ))
    
    # Footer
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(
        "<i>This report was auto-generated by FinOps AI. Please review all findings with your team.</i>",
        styles['CustomNormal']
    ))
    
    doc.build(elements)
    return buffer.getvalue()


def generate_recommendations_pdf(
    architecture_id: str,
    architecture_name: str,
    recommendations: List[Dict[str, Any]],
    total_savings_monthly: float = 0,
    source: str = "engine",
    llm_model: Optional[str] = None,
) -> bytes:
    """
    Generate PDF for recommendations with FULL detailed card information.
    Includes all fields from the detailed drawer view.
    
    Args:
        architecture_id: Architecture identifier
        architecture_name: Human-readable architecture name
        recommendations: List of recommendation cards
        total_savings_monthly: Total monthly savings
        source: Source of recommendations (engine, llm, both)
        llm_model: LLM model used (if applicable)
        
    Returns:
        PDF bytes
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = _get_styles()
    elements = []
    
    # Header
    elements.append(Paragraph("FinOps AI - Cost Optimization Recommendations", styles['CustomTitle']))
    elements.append(Spacer(1, 12))
    
    # Metadata
    metadata_data = [
        ["Architecture", architecture_name],
        ["Total Recommendations", str(len(recommendations))],
        ["Potential Monthly Savings", f"${total_savings_monthly:,.2f}"],
        ["Annual Impact", f"${total_savings_monthly * 12:,.2f}"],
        ["Source", source.upper()],
        ["Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")],
    ]
    
    if llm_model:
        metadata_data.append(["AI Model", llm_model])
    
    metadata_table = Table(metadata_data, colWidths=[2*inch, 4*inch])
    metadata_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1f2937')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
    ]))
    elements.append(metadata_table)
    elements.append(Spacer(1, 12))
    
    # Recommendations
    if not recommendations:
        elements.append(Paragraph("No recommendations available.", styles['CustomNormal']))
    else:
        elements.append(Paragraph(f"Detailed Recommendations ({len(recommendations)} total)", styles['CustomHeading']))
        elements.append(Spacer(1, 8))
        
        for idx, rec in enumerate(recommendations, 1):
            # Card title with number and source badge
            title = rec.get("title", f"Recommendation {idx}")
            source_badge = rec.get("source", "engine").upper()
            elements.append(Paragraph(
                f"#{idx} {title} <font color='#4f46e5' size=9>[{source_badge}]</font>", 
                styles['Heading3']
            ))
            
            # Description/Service info
            res_info = rec.get("resource_identification", {})
            service_type = res_info.get("service_type") or rec.get("service_type", "AWS")
            resource_id = res_info.get("resource_id") or res_info.get("resource_name", "N/A")
            elements.append(Paragraph(
                f"<b>Resource:</b> {service_type} · {resource_id}", 
                styles['CustomNormal']
            ))
            
            # ═══ KEY METRICS ═══
            elements.append(Paragraph("<b>Key Metrics:</b>", styles['CustomNormal']))
            
            # Financial snapshot (engine cards)
            if rec.get("total_estimated_savings"):
                savings = rec["total_estimated_savings"]
                elements.append(Paragraph(
                    f"• <b>Potential Savings:</b> ${savings:,.2f}/month (${savings*12:,.2f}/year)",
                    styles['CustomNormal']
                ))
            
            # Current cost
            cost_data = rec.get("cost_breakdown", {})
            if isinstance(cost_data, dict):
                current = cost_data.get("current_monthly", 0)
                if current > 0:
                    elements.append(Paragraph(
                        f"• <b>Current Cost:</b> ${current:,.2f}/month",
                        styles['CustomNormal']
                    ))
            
            # Category & Severity
            category = rec.get("category", "optimization")
            severity = rec.get("severity", "medium")
            elements.append(Paragraph(f"• <b>Category:</b> {category.replace('_', ' ').title()}", styles['CustomNormal']))
            elements.append(Paragraph(f"• <b>Severity:</b> {severity.upper()}", styles['CustomNormal']))
            
            # Risk level
            if rec.get("risk_level"):
                elements.append(Paragraph(f"• <b>Risk Level:</b> {rec['risk_level']}", styles['CustomNormal']))
            
            # Confidence scores
            if rec.get("confidence_score"):
                conf = rec["confidence_score"]
                elements.append(Paragraph(f"• <b>Confidence:</b> {conf}%", styles['CustomNormal']))
            
            if rec.get("engine_confidence"):
                elements.append(Paragraph(f"• <b>Engine Confidence:</b> {rec['engine_confidence']}%", styles['CustomNormal']))
            
            if rec.get("llm_confidence"):
                elements.append(Paragraph(f"• <b>LLM Confidence:</b> {rec['llm_confidence']}%", styles['CustomNormal']))
            
            # Implementation complexity
            if rec.get("implementation_complexity"):
                elements.append(Paragraph(f"• <b>Implementation Effort:</b> {rec['implementation_complexity']}", styles['CustomNormal']))
            
            elements.append(Spacer(1, 6))
            
            # ═══ DESCRIPTION / WHY IT MATTERS ═══
            if rec.get("description"):
                elements.append(Paragraph("<b>Description:</b>", styles['CustomNormal']))
                desc = str(rec["description"])[:500]
                elements.append(Paragraph(desc, styles['CustomNormal']))
                elements.append(Spacer(1, 6))
            
            if rec.get("why_it_matters"):
                elements.append(Paragraph("<b>Why It Matters:</b>", styles['CustomNormal']))
                matters = str(rec["why_it_matters"])[:500]
                elements.append(Paragraph(matters, styles['CustomNormal']))
                elements.append(Spacer(1, 6))
            
            if rec.get("raw_analysis"):
                elements.append(Paragraph("<b>Technical Analysis:</b>", styles['CustomNormal']))
                analysis = str(rec["raw_analysis"])[:500]
                elements.append(Paragraph(analysis, styles['CustomNormal']))
                elements.append(Spacer(1, 6))
            
            # ═══ GRAPH CONTEXT / ARCHITECTURE IMPACT ═══
            graph_ctx = rec.get("graph_context", {})
            if isinstance(graph_ctx, dict) and any([
                graph_ctx.get("blast_radius_pct", 0) > 0,
                graph_ctx.get("dependency_count", 0) > 0,
                graph_ctx.get("cross_az_count", 0) > 0,
                graph_ctx.get("is_spof"),
            ]):
                elements.append(Paragraph("<b>Architecture Impact:</b>", styles['CustomNormal']))
                if graph_ctx.get("blast_radius_pct", 0) > 0:
                    elements.append(Paragraph(
                        f"• Blast Radius: {graph_ctx['blast_radius_pct']}%",
                        styles['CustomNormal']
                    ))
                if graph_ctx.get("dependency_count", 0) > 0:
                    elements.append(Paragraph(
                        f"• Dependencies: {graph_ctx['dependency_count']}",
                        styles['CustomNormal']
                    ))
                if graph_ctx.get("cross_az_count", 0) > 0:
                    elements.append(Paragraph(
                        f"• Cross-AZ Links: {graph_ctx['cross_az_count']}",
                        styles['CustomNormal']
                    ))
                if graph_ctx.get("is_spof"):
                    elements.append(Paragraph("• Single Point of Failure - Critical!", styles['CustomNormal']))
                elements.append(Spacer(1, 6))
            
            # ═══ FINANCIAL BREAKDOWN ═══
            if cost_data and isinstance(cost_data, dict):
                cost_items = {k: v for k, v in cost_data.items() if v and k not in ['current_monthly']}
                if cost_items:
                    elements.append(Paragraph("<b>Cost Breakdown:</b>", styles['CustomNormal']))
                    for key, val in list(cost_items.items())[:8]:
                        key_name = key.replace('_', ' ').title()
                        val_str = f"${val:,.2f}" if isinstance(val, (int, float)) else str(val)
                        elements.append(Paragraph(f"• {key_name}: {val_str}", styles['CustomNormal']))
                    elements.append(Spacer(1, 6))
            
            # ═══ IMPLEMENTATION STEPS ═══
            impl_data = rec.get("implementation")
            if impl_data:
                if isinstance(impl_data, list) and len(impl_data) > 0:
                    elements.append(Paragraph("<b>Implementation Steps:</b>", styles['CustomNormal']))
                    for i, step in enumerate(impl_data[:6], 1):
                        if isinstance(step, dict):
                            step_text = step.get("step") or step.get("description") or str(step)
                        else:
                            step_text = str(step)
                        step_text = step_text[:200] if len(step_text) > 200 else step_text
                        elements.append(Paragraph(f"{i}. {step_text}", styles['CustomNormal']))
                    elements.append(Spacer(1, 6))
                elif isinstance(impl_data, dict):
                    elements.append(Paragraph("<b>Implementation Details:</b>", styles['CustomNormal']))
                    for key, val in list(impl_data.items())[:5]:
                        elements.append(Paragraph(f"• {key}: {str(val)[:150]}", styles['CustomNormal']))
                    elements.append(Spacer(1, 6))
            
            # ═══ RECOMMENDATIONS (ACTION ITEMS) ═══
            if rec.get("recommendations") and isinstance(rec["recommendations"], list):
                actions = rec["recommendations"]
                if len(actions) > 0:
                    elements.append(Paragraph("<b>Recommended Actions:</b>", styles['CustomNormal']))
                    for j, action in enumerate(actions[:4], 1):
                        if isinstance(action, dict):
                            action_title = action.get("action", f"Action {j}")
                            action_desc = action.get("description", "")
                            if action_desc:
                                elements.append(Paragraph(
                                    f"{j}. <b>{action_title}:</b> {action_desc[:200]}",
                                    styles['CustomNormal']
                                ))
                            else:
                                elements.append(Paragraph(f"{j}. {action_title}", styles['CustomNormal']))
                        else:
                            elements.append(Paragraph(f"{j}. {str(action)[:200]}", styles['CustomNormal']))
                    elements.append(Spacer(1, 6))
            
            # ═══ ADDITIONAL METADATA ═══
            extra_fields = []
            
            if rec.get("linked_best_practice"):
                extra_fields.append(f"Best Practice: {rec['linked_best_practice']}")
            
            if rec.get("pattern_id"):
                extra_fields.append(f"Pattern ID: {rec['pattern_id']}")
            
            if rec.get("validation_status"):
                extra_fields.append(f"Validation: {rec['validation_status']}")
            
            if extra_fields:
                elements.append(Paragraph("<b>Additional Info:</b>", styles['CustomNormal']))
                for field in extra_fields:
                    elements.append(Paragraph(f"• {field}", styles['CustomNormal']))
                elements.append(Spacer(1, 6))
            
            # Separator between recommendations
            elements.append(Spacer(1, 12))
            elements.append(Paragraph("_" * 80, styles['CustomNormal']))
            elements.append(Spacer(1, 12))
            
            # Page break after every 2 detailed recommendations
            if idx % 2 == 0 and idx < len(recommendations):
                elements.append(PageBreak())
    
    # Footer
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(
        "<i>This report was auto-generated by FinOps AI. All recommendations should be reviewed and tested before implementation.</i>",
        styles['CustomNormal']
    ))
    
    doc.build(elements)
    return buffer.getvalue()
