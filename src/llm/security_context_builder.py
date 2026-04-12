"""
Security Context Builder for LLM Recommendations

Formats security, compliance, and operational data from AWS services
into a structured context for LLM architectural analysis.
"""
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def build_security_context(graph_data: dict) -> str:
    """
    Build comprehensive security & compliance context from graph metadata.
    
    Extracts and formats data from:
    - AWS Config (compliance violations)
    - Security Hub (security findings)
    - GuardDuty (threat detection)
    - VPC Flow Logs (network patterns)
    - IAM Credential Report (access key age, MFA)
    - Trusted Advisor (best practices)
    - Compute Optimizer (rightsizing)
    - Inspector (vulnerabilities)
    """
    metadata = graph_data.get("metadata", {})
    security_data = metadata.get("security_context", {})
    
    if not security_data or security_data.get("summary", {}).get("data_sources_enabled", 0) == 0:
        return "(No security/compliance data available — CUR-only ingestion)"
    
    sections = []
    summary = security_data.get("summary", {})
    
    # ═══ SUMMARY ═══
    sections.append("━━━ SECURITY & COMPLIANCE SUMMARY ━━━")
    sections.append(f"Data Sources Active: {summary.get('data_sources_enabled', 0)}/8")
    sections.append(f"Total Security Findings: {summary.get('total_security_findings', 0)}")
    sections.append(f"Total Compliance Issues: {summary.get('total_compliance_issues', 0)}")
    sections.append(f"Optimization Opportunities: {summary.get('total_optimization_opportunities', 0)}")
    sections.append("")
    
    critical = summary.get("critical_issues", {})
    if any(critical.values()):
        sections.append("🚨 CRITICAL ISSUES:")
        if critical.get("security_hub_critical", 0) > 0:
            sections.append(f"  • {critical['security_hub_critical']} CRITICAL Security Hub findings")
        if critical.get("guardduty_high", 0) > 0:
            sections.append(f"  • {critical['guardduty_high']} HIGH GuardDuty threats")
        if critical.get("inspector_critical", 0) > 0:
            sections.append(f"  • {critical['inspector_critical']} CRITICAL Inspector vulnerabilities")
        if critical.get("iam_no_mfa", 0) > 0:
            sections.append(f"  • {critical['iam_no_mfa']} IAM users without MFA")
        sections.append("")
    
    # ═══ AWS CONFIG ═══
    config_data = security_data.get("aws_config", {})
    if config_data.get("enabled"):
        sections.append("━━━ AWS CONFIG — COMPLIANCE STATUS ━━━")
        comp = config_data.get("compliance_summary", {})
        sections.append(f"Total Config Rules: {comp.get('total_rules', 0)}")
        sections.append(f"Compliant: {comp.get('compliant', 0)} | Non-Compliant: {comp.get('non_compliant', 0)}")
        
        non_compliant = config_data.get("non_compliant_resources", [])[:10]
        if non_compliant:
            sections.append("\nTop Non-Compliant Resources:")
            for item in non_compliant:
                sections.append(f"  • {item.get('resource_type', 'Unknown')}: {item.get('resource_id', 'N/A')}")
                sections.append(f"    Rule: {item.get('rule_name', 'N/A')}")
                if item.get('annotation'):
                    sections.append(f"    Issue: {item['annotation']}")
        sections.append("")
    
    # ═══ SECURITY HUB ═══
    securityhub_data = security_data.get("security_hub", {})
    if securityhub_data.get("enabled"):
        sections.append("━━━ SECURITY HUB — ACTIVE FINDINGS ━━━")
        by_sev = securityhub_data.get("by_severity", {})
        sections.append(f"CRITICAL: {by_sev.get('CRITICAL', 0)} | HIGH: {by_sev.get('HIGH', 0)} | MEDIUM: {by_sev.get('MEDIUM', 0)}")
        sections.append(f"Resources with findings: {securityhub_data.get('resources_with_findings', 0)}")
        
        findings = securityhub_data.get("findings", [])[:15]
        if findings:
            sections.append("\nTop Security Findings:")
            for f in findings:
                sections.append(f"  [{f.get('severity', 'UNKNOWN')}] {f.get('title', 'N/A')}")
                sections.append(f"    Resource: {f.get('resource_type', 'N/A')} — {f.get('resource_id', 'N/A')}")
                if f.get('remediation'):
                    sections.append(f"    Fix: {f['remediation'][:100]}...")
        sections.append("")
    
    # ═══ GUARDDUTY ═══
    guardduty_data = security_data.get("guardduty", {})
    if guardduty_data.get("enabled"):
        sections.append("━━━ GUARDDUTY — THREAT DETECTION ━━━")
        by_sev = guardduty_data.get("by_severity", {})
        sections.append(f"HIGH: {by_sev.get('HIGH', 0)} | MEDIUM: {by_sev.get('MEDIUM', 0)} | LOW: {by_sev.get('LOW', 0)}")
        
        threat_types = guardduty_data.get("threat_types", [])
        if threat_types:
            sections.append(f"Threat Types Detected: {', '.join(threat_types[:5])}")
        
        findings = guardduty_data.get("findings", [])[:10]
        if findings:
            sections.append("\nRecent Threats:")
            for f in findings:
                sections.append(f"  [{f.get('severity', 0):.1f}] {f.get('type', 'N/A')}")
                sections.append(f"    {f.get('description', 'N/A')[:100]}...")
                sections.append(f"    Resource: {f.get('resource_id', 'N/A')}")
        sections.append("")
    
    # ═══ IAM CREDENTIALS ═══
    iam_data = security_data.get("iam_credentials", {})
    if iam_data.get("enabled"):
        sections.append("━━━ IAM CREDENTIAL REPORT ━━━")
        stats = iam_data.get("statistics", {})
        sections.append(f"Total Users: {stats.get('total_users', 0)}")
        sections.append(f"Users with MFA: {stats.get('users_with_mfa', 0)}/{stats.get('users_with_password', 0)} console users")
        sections.append(f"Old Passwords (>90d): {stats.get('old_passwords', 0)}")
        sections.append(f"Old Access Keys (>90d): {stats.get('old_access_keys', 0)}")
        sections.append(f"Unused Credentials: {stats.get('unused_credentials', 0)}")
        
        issues = iam_data.get("issues", [])[:10]
        if issues:
            sections.append("\nTop IAM Issues:")
            for issue in issues:
                sections.append(f"  [{issue.get('severity', 'UNKNOWN')}] {issue.get('user', 'N/A')}: {issue.get('detail', 'N/A')}")
        sections.append("")
    
    # ═══ TRUSTED ADVISOR ═══
    ta_data = security_data.get("trusted_advisor", {})
    if ta_data.get("enabled"):
        sections.append("━━━ TRUSTED ADVISOR — BEST PRACTICES ━━━")
        by_cat = ta_data.get("by_category", {})
        sections.append(f"Cost Optimization: {by_cat.get('cost_optimizing', 0)} checks")
        sections.append(f"Security: {by_cat.get('security', 0)} checks")
        sections.append(f"Fault Tolerance: {by_cat.get('fault_tolerance', 0)} checks")
        sections.append(f"Performance: {by_cat.get('performance', 0)} checks")
        
        checks = ta_data.get("checks", [])[:10]
        if checks:
            sections.append("\nTop Issues:")
            for check in checks:
                sections.append(f"  [{check.get('status', 'unknown').upper()}] {check.get('name', 'N/A')}")
                sections.append(f"    Category: {check.get('category', 'N/A')}")
                sections.append(f"    Resources Flagged: {check.get('resources_flagged', 0)}")
        sections.append("")
    
    # ═══ COMPUTE OPTIMIZER ═══
    co_data = security_data.get("compute_optimizer", {})
    if co_data.get("enabled"):
        sections.append("━━━ COMPUTE OPTIMIZER — RIGHTSIZING ━━━")
        by_svc = co_data.get("by_service", {})
        sections.append(f"EC2: {by_svc.get('ec2', 0)} recommendations")
        sections.append(f"EBS: {by_svc.get('ebs', 0)} recommendations")
        sections.append(f"Lambda: {by_svc.get('lambda', 0)} recommendations")
        
        recs = co_data.get("recommendations", {})
        ec2_recs = recs.get("ec2", [])[:5]
        if ec2_recs:
            sections.append("\nTop EC2 Rightsizing:")
            for rec in ec2_recs:
                sections.append(f"  {rec.get('instance_name', 'N/A')} ({rec.get('current_instance_type', 'N/A')})")
                sections.append(f"    Finding: {rec.get('finding', 'N/A')}")
                options = rec.get('recommendation_options', [])
                if options:
                    sections.append(f"    Recommended: {options[0].get('instanceType', 'N/A')}")
        sections.append("")
    
    # ═══ INSPECTOR ═══
    inspector_data = security_data.get("inspector", {})
    if inspector_data.get("enabled"):
        sections.append("━━━ INSPECTOR — VULNERABILITY ASSESSMENT ━━━")
        by_sev = inspector_data.get("by_severity", {})
        sections.append(f"CRITICAL: {by_sev.get('CRITICAL', 0)} | HIGH: {by_sev.get('HIGH', 0)} | MEDIUM: {by_sev.get('MEDIUM', 0)}")
        
        findings = inspector_data.get("findings", [])[:10]
        if findings:
            sections.append("\nTop Vulnerabilities:")
            for f in findings:
                sections.append(f"  [{f.get('severity', 'UNKNOWN')}] {f.get('title', 'N/A')}")
                sections.append(f"    Resource: {f.get('resource_type', 'N/A')} — {f.get('resource_id', 'N/A')}")
                if f.get('remediation'):
                    sections.append(f"    Fix: {f['remediation'][:100]}...")
        sections.append("")
    
    # ═══ VPC FLOW LOGS ═══
    flow_data = security_data.get("vpc_flow_logs", {})
    if flow_data.get("enabled"):
        sections.append("━━━ VPC FLOW LOGS — NETWORK TRAFFIC ━━━")
        sections.append(f"VPCs with Flow Logs: {flow_data.get('vpcs_with_flow_logs', 0)}")
        
        flow_logs = flow_data.get("flow_logs", [])[:3]
        if flow_logs:
            sections.append("\nFlow Log Status:")
            for log in flow_logs:
                sections.append(f"  VPC: {log.get('vpc_id', 'N/A')}")
                sections.append(f"    Status: {log.get('log_status', 'N/A')}")
                sections.append(f"    Traffic Type: {log.get('traffic_type', 'N/A')}")
        sections.append("")
    
    return "\n".join(sections)
