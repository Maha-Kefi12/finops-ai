"""
AWS Security & Compliance Data Collector

Collects comprehensive security, compliance, and operational data from:
- AWS Config (configuration snapshots, compliance status)
- Security Hub (security findings, vulnerabilities)
- GuardDuty (threat detection, anomalies)
- VPC Flow Logs (network traffic patterns)
- IAM Credential Report (access keys, password age, MFA status)
- Trusted Advisor (best practice checks)
- Compute Optimizer (rightsizing recommendations)
- Inspector (vulnerability assessments)

This data enriches the LLM context for deep architectural analysis.
"""
import boto3
import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class AWSSecurityCollector:
    """Comprehensive AWS security and compliance data collector."""
    
    def __init__(self, region: str = "us-east-1", profile: Optional[str] = None):
        self.region = region
        session = boto3.Session(profile_name=profile, region_name=region)
        
        # Initialize AWS clients
        self.config_client = session.client('config')
        self.securityhub_client = session.client('securityhub')
        self.guardduty_client = session.client('guardduty')
        self.ec2_client = session.client('ec2')
        self.iam_client = session.client('iam')
        self.support_client = session.client('support', region_name='us-east-1')  # TA is us-east-1 only
        self.compute_optimizer_client = session.client('compute-optimizer')
        self.inspector_client = session.client('inspector2')
        self.logs_client = session.client('logs')
        self.s3_client = session.client('s3')
        
    def collect_all(self) -> Dict[str, Any]:
        """Collect all security and compliance data."""
        logger.info("Starting comprehensive AWS security data collection...")
        
        data = {
            "metadata": {
                "collection_timestamp": datetime.utcnow().isoformat(),
                "region": self.region,
            },
            "aws_config": self.collect_aws_config(),
            "security_hub": self.collect_security_hub(),
            "guardduty": self.collect_guardduty(),
            "vpc_flow_logs": self.collect_vpc_flow_logs(),
            "iam_credentials": self.collect_iam_credentials(),
            "trusted_advisor": self.collect_trusted_advisor(),
            "compute_optimizer": self.collect_compute_optimizer(),
            "inspector": self.collect_inspector(),
        }
        
        # Generate summary statistics
        data["summary"] = self._generate_summary(data)
        
        logger.info("Security data collection complete")
        return data
    
    # ═══════════════════════════════════════════════════════════════════
    # AWS Config — Configuration Snapshots & Compliance
    # ═══════════════════════════════════════════════════════════════════
    
    def collect_aws_config(self) -> Dict[str, Any]:
        """Collect AWS Config configuration items and compliance status."""
        logger.info("Collecting AWS Config data...")
        
        try:
            # Get all resource types being tracked
            resource_counts = self.config_client.get_discovered_resource_counts()
            
            # Get compliance summary
            compliance_summary = self.config_client.describe_compliance_by_config_rule()
            
            # Get non-compliant resources
            non_compliant = []
            for rule in compliance_summary.get('ComplianceByConfigRules', []):
                if rule.get('Compliance', {}).get('ComplianceType') == 'NON_COMPLIANT':
                    rule_name = rule['ConfigRuleName']
                    # Get details of non-compliant resources
                    try:
                        details = self.config_client.get_compliance_details_by_config_rule(
                            ConfigRuleName=rule_name,
                            ComplianceTypes=['NON_COMPLIANT'],
                            Limit=100
                        )
                        for item in details.get('EvaluationResults', []):
                            non_compliant.append({
                                "rule_name": rule_name,
                                "resource_type": item.get('EvaluationResultIdentifier', {}).get('EvaluationResultQualifier', {}).get('ResourceType'),
                                "resource_id": item.get('EvaluationResultIdentifier', {}).get('EvaluationResultQualifier', {}).get('ResourceId'),
                                "compliance_type": item.get('ComplianceType'),
                                "annotation": item.get('Annotation'),
                                "result_recorded_time": item.get('ResultRecordedTime').isoformat() if item.get('ResultRecordedTime') else None,
                            })
                    except Exception as e:
                        logger.warning(f"Failed to get details for rule {rule_name}: {e}")
            
            # Get configuration snapshots for critical resources
            critical_resources = self._get_critical_config_snapshots()
            
            return {
                "enabled": True,
                "resource_counts": resource_counts.get('resourceCounts', []),
                "total_resources": sum(r.get('count', 0) for r in resource_counts.get('resourceCounts', [])),
                "compliance_summary": {
                    "total_rules": len(compliance_summary.get('ComplianceByConfigRules', [])),
                    "compliant": len([r for r in compliance_summary.get('ComplianceByConfigRules', []) 
                                     if r.get('Compliance', {}).get('ComplianceType') == 'COMPLIANT']),
                    "non_compliant": len([r for r in compliance_summary.get('ComplianceByConfigRules', []) 
                                         if r.get('Compliance', {}).get('ComplianceType') == 'NON_COMPLIANT']),
                },
                "non_compliant_resources": non_compliant[:100],  # Limit to 100 for context size
                "critical_resources": critical_resources,
            }
        except Exception as e:
            logger.error(f"AWS Config collection failed: {e}")
            return {"enabled": False, "error": str(e)}
    
    def _get_critical_config_snapshots(self) -> List[Dict[str, Any]]:
        """Get configuration snapshots for critical resource types."""
        critical_types = [
            'AWS::RDS::DBInstance',
            'AWS::EC2::SecurityGroup',
            'AWS::S3::Bucket',
            'AWS::IAM::Role',
            'AWS::Lambda::Function',
        ]
        
        snapshots = []
        for resource_type in critical_types:
            try:
                resources = self.config_client.list_discovered_resources(
                    resourceType=resource_type,
                    limit=50
                )
                for resource in resources.get('resourceIdentifiers', []):
                    try:
                        config_item = self.config_client.get_resource_config_history(
                            resourceType=resource_type,
                            resourceId=resource['resourceId'],
                            limit=1
                        )
                        if config_item.get('configurationItems'):
                            item = config_item['configurationItems'][0]
                            snapshots.append({
                                "resource_type": resource_type,
                                "resource_id": resource['resourceId'],
                                "resource_name": resource.get('resourceName'),
                                "configuration": json.loads(item.get('configuration', '{}')),
                                "tags": item.get('tags', {}),
                                "configuration_item_capture_time": item.get('configurationItemCaptureTime').isoformat() if item.get('configurationItemCaptureTime') else None,
                            })
                    except Exception as e:
                        logger.debug(f"Failed to get config for {resource['resourceId']}: {e}")
            except Exception as e:
                logger.warning(f"Failed to list {resource_type}: {e}")
        
        return snapshots[:100]  # Limit for context size
    
    # ═══════════════════════════════════════════════════════════════════
    # Security Hub — Security Findings & Vulnerabilities
    # ═══════════════════════════════════════════════════════════════════
    
    def collect_security_hub(self) -> Dict[str, Any]:
        """Collect Security Hub findings (security issues, vulnerabilities)."""
        logger.info("Collecting Security Hub findings...")
        
        try:
            # Get active findings with CRITICAL and HIGH severity
            findings = []
            paginator = self.securityhub_client.get_paginator('get_findings')
            
            for severity in ['CRITICAL', 'HIGH', 'MEDIUM']:
                try:
                    pages = paginator.paginate(
                        Filters={
                            'SeverityLabel': [{'Value': severity, 'Comparison': 'EQUALS'}],
                            'RecordState': [{'Value': 'ACTIVE', 'Comparison': 'EQUALS'}],
                        },
                        PaginationConfig={'MaxItems': 200}  # Limit for context
                    )
                    
                    for page in pages:
                        for finding in page.get('Findings', []):
                            findings.append({
                                "id": finding.get('Id'),
                                "title": finding.get('Title'),
                                "description": finding.get('Description'),
                                "severity": finding.get('Severity', {}).get('Label'),
                                "severity_score": finding.get('Severity', {}).get('Normalized'),
                                "resource_type": finding.get('Resources', [{}])[0].get('Type') if finding.get('Resources') else None,
                                "resource_id": finding.get('Resources', [{}])[0].get('Id') if finding.get('Resources') else None,
                                "compliance_status": finding.get('Compliance', {}).get('Status'),
                                "remediation": finding.get('Remediation', {}).get('Recommendation', {}).get('Text'),
                                "generator_id": finding.get('GeneratorId'),
                                "types": finding.get('Types', []),
                                "first_observed": finding.get('FirstObservedAt'),
                                "last_observed": finding.get('LastObservedAt'),
                            })
                except Exception as e:
                    logger.warning(f"Failed to get {severity} findings: {e}")
            
            # Group by resource
            by_resource = defaultdict(list)
            for finding in findings:
                resource_id = finding.get('resource_id', 'unknown')
                by_resource[resource_id].append(finding)
            
            return {
                "enabled": True,
                "total_findings": len(findings),
                "by_severity": {
                    "CRITICAL": len([f for f in findings if f['severity'] == 'CRITICAL']),
                    "HIGH": len([f for f in findings if f['severity'] == 'HIGH']),
                    "MEDIUM": len([f for f in findings if f['severity'] == 'MEDIUM']),
                },
                "findings": findings[:200],  # Limit for context
                "resources_with_findings": len(by_resource),
                "top_affected_resources": sorted(
                    [{"resource_id": k, "finding_count": len(v)} for k, v in by_resource.items()],
                    key=lambda x: -x['finding_count']
                )[:20],
            }
        except Exception as e:
            logger.error(f"Security Hub collection failed: {e}")
            return {"enabled": False, "error": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════
    # GuardDuty — Threat Detection & Anomalies
    # ═══════════════════════════════════════════════════════════════════
    
    def collect_guardduty(self) -> Dict[str, Any]:
        """Collect GuardDuty findings (threat detection, anomalies)."""
        logger.info("Collecting GuardDuty findings...")
        
        try:
            # Get detector ID
            detectors = self.guardduty_client.list_detectors()
            if not detectors.get('DetectorIds'):
                return {"enabled": False, "error": "No GuardDuty detector found"}
            
            detector_id = detectors['DetectorIds'][0]
            
            # Get findings from last 30 days
            findings = []
            finding_ids = self.guardduty_client.list_findings(
                DetectorId=detector_id,
                FindingCriteria={
                    'Criterion': {
                        'updatedAt': {
                            'Gte': int((datetime.utcnow() - timedelta(days=30)).timestamp() * 1000)
                        }
                    }
                },
                MaxResults=100
            )
            
            if finding_ids.get('FindingIds'):
                findings_detail = self.guardduty_client.get_findings(
                    DetectorId=detector_id,
                    FindingIds=finding_ids['FindingIds']
                )
                
                for finding in findings_detail.get('Findings', []):
                    findings.append({
                        "id": finding.get('Id'),
                        "type": finding.get('Type'),
                        "severity": finding.get('Severity'),
                        "title": finding.get('Title'),
                        "description": finding.get('Description'),
                        "resource_type": finding.get('Resource', {}).get('ResourceType'),
                        "resource_id": finding.get('Resource', {}).get('InstanceDetails', {}).get('InstanceId'),
                        "service": finding.get('Service', {}).get('ServiceName'),
                        "action_type": finding.get('Service', {}).get('Action', {}).get('ActionType'),
                        "count": finding.get('Service', {}).get('Count'),
                        "first_seen": finding.get('Service', {}).get('EventFirstSeen'),
                        "last_seen": finding.get('Service', {}).get('EventLastSeen'),
                    })
            
            return {
                "enabled": True,
                "detector_id": detector_id,
                "total_findings": len(findings),
                "by_severity": {
                    "HIGH": len([f for f in findings if f['severity'] >= 7.0]),
                    "MEDIUM": len([f for f in findings if 4.0 <= f['severity'] < 7.0]),
                    "LOW": len([f for f in findings if f['severity'] < 4.0]),
                },
                "findings": findings,
                "threat_types": list(set(f['type'] for f in findings)),
            }
        except Exception as e:
            logger.error(f"GuardDuty collection failed: {e}")
            return {"enabled": False, "error": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════
    # VPC Flow Logs — Network Traffic Patterns & Anomalies
    # ═══════════════════════════════════════════════════════════════════
    
    def collect_vpc_flow_logs(self) -> Dict[str, Any]:
        """Analyze VPC Flow Logs for network traffic patterns and anomalies."""
        logger.info("Collecting VPC Flow Logs analysis...")
        
        try:
            # Get all VPCs with flow logs enabled
            vpcs = self.ec2_client.describe_vpcs()
            flow_logs_data = []
            
            for vpc in vpcs.get('Vpcs', []):
                vpc_id = vpc['VpcId']
                
                # Check if flow logs are enabled
                flow_logs = self.ec2_client.describe_flow_logs(
                    Filters=[{'Name': 'resource-id', 'Values': [vpc_id]}]
                )
                
                if flow_logs.get('FlowLogs'):
                    for log in flow_logs['FlowLogs']:
                        flow_logs_data.append({
                            "vpc_id": vpc_id,
                            "flow_log_id": log.get('FlowLogId'),
                            "log_destination": log.get('LogDestination'),
                            "log_destination_type": log.get('LogDestinationType'),
                            "traffic_type": log.get('TrafficType'),
                            "log_status": log.get('FlowLogStatus'),
                        })
                        
                        # If logs go to CloudWatch, get recent traffic patterns
                        if log.get('LogDestinationType') == 'cloud-watch-logs':
                            log_group = log.get('LogGroupName')
                            if log_group:
                                traffic_summary = self._analyze_flow_log_patterns(log_group)
                                flow_logs_data[-1]['traffic_summary'] = traffic_summary
            
            return {
                "enabled": len(flow_logs_data) > 0,
                "vpcs_with_flow_logs": len(flow_logs_data),
                "flow_logs": flow_logs_data,
            }
        except Exception as e:
            logger.error(f"VPC Flow Logs collection failed: {e}")
            return {"enabled": False, "error": str(e)}
    
    def _analyze_flow_log_patterns(self, log_group: str) -> Dict[str, Any]:
        """Analyze CloudWatch Logs for VPC flow log patterns."""
        try:
            # Query last 1 hour of logs for traffic patterns
            end_time = int(datetime.utcnow().timestamp() * 1000)
            start_time = int((datetime.utcnow() - timedelta(hours=1)).timestamp() * 1000)
            
            # CloudWatch Insights query for traffic summary
            query = """
            fields @timestamp, srcAddr, dstAddr, srcPort, dstPort, protocol, bytes, packets, action
            | stats count() as connection_count, sum(bytes) as total_bytes by srcAddr, dstAddr, action
            | sort total_bytes desc
            | limit 20
            """
            
            query_id = self.logs_client.start_query(
                logGroupName=log_group,
                startTime=start_time,
                endTime=end_time,
                queryString=query
            )
            
            # Wait for query (simplified - in production use polling)
            import time
            time.sleep(2)
            
            results = self.logs_client.get_query_results(queryId=query_id['queryId'])
            
            if results.get('status') == 'Complete':
                return {
                    "top_connections": results.get('results', [])[:10],
                    "query_status": "complete"
                }
            
            return {"query_status": results.get('status', 'unknown')}
        except Exception as e:
            logger.debug(f"Flow log analysis failed: {e}")
            return {"error": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════
    # IAM Credential Report — Access Keys, Password Age, MFA
    # ═══════════════════════════════════════════════════════════════════
    
    def collect_iam_credentials(self) -> Dict[str, Any]:
        """Collect IAM credential report (access keys, password age, MFA status)."""
        logger.info("Collecting IAM credential report...")
        
        try:
            # Generate credential report
            try:
                self.iam_client.generate_credential_report()
                import time
                time.sleep(2)  # Wait for report generation
            except Exception:
                pass  # Report might already exist
            
            # Get credential report
            report = self.iam_client.get_credential_report()
            report_csv = report['Content'].decode('utf-8')
            
            # Parse CSV
            import csv
            import io
            reader = csv.DictReader(io.StringIO(report_csv))
            
            issues = []
            stats = {
                "total_users": 0,
                "users_with_password": 0,
                "users_with_mfa": 0,
                "users_with_access_keys": 0,
                "old_passwords": 0,
                "old_access_keys": 0,
                "unused_credentials": 0,
            }
            
            for row in reader:
                stats["total_users"] += 1
                user = row['user']
                
                # Check password age
                if row['password_enabled'] == 'true':
                    stats["users_with_password"] += 1
                    if row['password_last_changed'] != 'N/A':
                        password_age = (datetime.utcnow() - datetime.fromisoformat(row['password_last_changed'].replace('Z', '+00:00'))).days
                        if password_age > 90:
                            stats["old_passwords"] += 1
                            issues.append({
                                "user": user,
                                "issue": "password_age",
                                "severity": "MEDIUM",
                                "detail": f"Password is {password_age} days old (>90 days)",
                            })
                
                # Check MFA
                if row['mfa_active'] == 'false' and row['password_enabled'] == 'true':
                    issues.append({
                        "user": user,
                        "issue": "no_mfa",
                        "severity": "HIGH",
                        "detail": "Console access without MFA enabled",
                    })
                else:
                    stats["users_with_mfa"] += 1
                
                # Check access keys
                for key_num in ['1', '2']:
                    if row[f'access_key_{key_num}_active'] == 'true':
                        stats["users_with_access_keys"] += 1
                        
                        # Check key age
                        if row[f'access_key_{key_num}_last_rotated'] != 'N/A':
                            key_age = (datetime.utcnow() - datetime.fromisoformat(row[f'access_key_{key_num}_last_rotated'].replace('Z', '+00:00'))).days
                            if key_age > 90:
                                stats["old_access_keys"] += 1
                                issues.append({
                                    "user": user,
                                    "issue": "old_access_key",
                                    "severity": "MEDIUM",
                                    "detail": f"Access key {key_num} is {key_age} days old (>90 days)",
                                })
                        
                        # Check if key was never used
                        if row[f'access_key_{key_num}_last_used_date'] == 'N/A':
                            stats["unused_credentials"] += 1
                            issues.append({
                                "user": user,
                                "issue": "unused_access_key",
                                "severity": "LOW",
                                "detail": f"Access key {key_num} has never been used",
                            })
            
            return {
                "enabled": True,
                "statistics": stats,
                "issues": issues,
                "report_generated_time": report['GeneratedTime'].isoformat(),
            }
        except Exception as e:
            logger.error(f"IAM credential report collection failed: {e}")
            return {"enabled": False, "error": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════
    # Trusted Advisor — Best Practice Checks
    # ═══════════════════════════════════════════════════════════════════
    
    def collect_trusted_advisor(self) -> Dict[str, Any]:
        """Collect Trusted Advisor recommendations."""
        logger.info("Collecting Trusted Advisor checks...")
        
        try:
            # Get all checks
            checks = self.support_client.describe_trusted_advisor_checks(language='en')
            
            results = []
            for check in checks.get('checks', []):
                check_id = check['id']
                
                try:
                    # Get check result
                    result = self.support_client.describe_trusted_advisor_check_result(
                        checkId=check_id,
                        language='en'
                    )
                    
                    check_result = result.get('result', {})
                    status = check_result.get('status')
                    
                    # Only include checks with issues
                    if status in ['warning', 'error']:
                        results.append({
                            "check_id": check_id,
                            "name": check['name'],
                            "category": check['category'],
                            "description": check['description'],
                            "status": status,
                            "resources_flagged": check_result.get('resourcesSummary', {}).get('resourcesFlagged', 0),
                            "resources_processed": check_result.get('resourcesSummary', {}).get('resourcesProcessed', 0),
                            "flagged_resources": check_result.get('flaggedResources', [])[:10],  # Limit for context
                        })
                except Exception as e:
                    logger.debug(f"Failed to get result for check {check_id}: {e}")
            
            return {
                "enabled": True,
                "total_checks": len(checks.get('checks', [])),
                "checks_with_issues": len(results),
                "by_category": {
                    "cost_optimizing": len([r for r in results if r['category'] == 'cost_optimizing']),
                    "security": len([r for r in results if r['category'] == 'security']),
                    "fault_tolerance": len([r for r in results if r['category'] == 'fault_tolerance']),
                    "performance": len([r for r in results if r['category'] == 'performance']),
                },
                "checks": results,
            }
        except Exception as e:
            logger.error(f"Trusted Advisor collection failed (may require Business/Enterprise support): {e}")
            return {"enabled": False, "error": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════
    # Compute Optimizer — Rightsizing Recommendations
    # ═══════════════════════════════════════════════════════════════════
    
    def collect_compute_optimizer(self) -> Dict[str, Any]:
        """Collect Compute Optimizer rightsizing recommendations."""
        logger.info("Collecting Compute Optimizer recommendations...")
        
        try:
            recommendations = {
                "ec2": [],
                "ebs": [],
                "lambda": [],
                "auto_scaling": [],
            }
            
            # EC2 recommendations
            try:
                ec2_recs = self.compute_optimizer_client.get_ec2_instance_recommendations(maxResults=100)
                for rec in ec2_recs.get('instanceRecommendations', []):
                    recommendations["ec2"].append({
                        "instance_arn": rec.get('instanceArn'),
                        "instance_name": rec.get('instanceName'),
                        "current_instance_type": rec.get('currentInstanceType'),
                        "finding": rec.get('finding'),
                        "utilization_metrics": rec.get('utilizationMetrics', []),
                        "recommendation_options": rec.get('recommendationOptions', [])[:3],  # Top 3
                    })
            except Exception as e:
                logger.debug(f"EC2 recommendations failed: {e}")
            
            # EBS recommendations
            try:
                ebs_recs = self.compute_optimizer_client.get_ebs_volume_recommendations(maxResults=100)
                for rec in ebs_recs.get('volumeRecommendations', []):
                    recommendations["ebs"].append({
                        "volume_arn": rec.get('volumeArn'),
                        "current_configuration": rec.get('currentConfiguration'),
                        "finding": rec.get('finding'),
                        "utilization_metrics": rec.get('utilizationMetrics', []),
                        "volume_recommendation_options": rec.get('volumeRecommendationOptions', [])[:3],
                    })
            except Exception as e:
                logger.debug(f"EBS recommendations failed: {e}")
            
            # Lambda recommendations
            try:
                lambda_recs = self.compute_optimizer_client.get_lambda_function_recommendations(maxResults=100)
                for rec in lambda_recs.get('lambdaFunctionRecommendations', []):
                    recommendations["lambda"].append({
                        "function_arn": rec.get('functionArn'),
                        "current_memory_size": rec.get('currentMemorySize'),
                        "finding": rec.get('finding'),
                        "utilization_metrics": rec.get('utilizationMetrics', []),
                        "memory_size_recommendation_options": rec.get('memorySizeRecommendationOptions', [])[:3],
                    })
            except Exception as e:
                logger.debug(f"Lambda recommendations failed: {e}")
            
            total_recs = sum(len(v) for v in recommendations.values())
            
            return {
                "enabled": total_recs > 0,
                "total_recommendations": total_recs,
                "by_service": {k: len(v) for k, v in recommendations.items()},
                "recommendations": recommendations,
            }
        except Exception as e:
            logger.error(f"Compute Optimizer collection failed: {e}")
            return {"enabled": False, "error": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════
    # Inspector — Vulnerability Assessments
    # ═══════════════════════════════════════════════════════════════════
    
    def collect_inspector(self) -> Dict[str, Any]:
        """Collect Inspector vulnerability findings."""
        logger.info("Collecting Inspector findings...")
        
        try:
            # Get findings
            findings = self.inspector_client.list_findings(
                maxResults=100,
                filterCriteria={
                    'findingStatus': [{'comparison': 'EQUALS', 'value': 'ACTIVE'}]
                }
            )
            
            finding_details = []
            if findings.get('findings'):
                details_response = self.inspector_client.batch_get_findings(
                    findingArns=findings['findings']
                )
                
                for finding in details_response.get('findings', []):
                    finding_details.append({
                        "finding_arn": finding.get('findingArn'),
                        "severity": finding.get('severity'),
                        "title": finding.get('title'),
                        "description": finding.get('description'),
                        "type": finding.get('type'),
                        "resource_type": finding.get('resources', [{}])[0].get('type') if finding.get('resources') else None,
                        "resource_id": finding.get('resources', [{}])[0].get('id') if finding.get('resources') else None,
                        "remediation": finding.get('remediation', {}).get('recommendation', {}).get('text'),
                        "first_observed": finding.get('firstObservedAt').isoformat() if finding.get('firstObservedAt') else None,
                        "last_observed": finding.get('lastObservedAt').isoformat() if finding.get('lastObservedAt') else None,
                    })
            
            return {
                "enabled": True,
                "total_findings": len(finding_details),
                "by_severity": {
                    "CRITICAL": len([f for f in finding_details if f['severity'] == 'CRITICAL']),
                    "HIGH": len([f for f in finding_details if f['severity'] == 'HIGH']),
                    "MEDIUM": len([f for f in finding_details if f['severity'] == 'MEDIUM']),
                    "LOW": len([f for f in finding_details if f['severity'] == 'LOW']),
                },
                "findings": finding_details,
            }
        except Exception as e:
            logger.error(f"Inspector collection failed: {e}")
            return {"enabled": False, "error": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════
    # Summary Generation
    # ═══════════════════════════════════════════════════════════════════
    
    def _generate_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary statistics across all data sources."""
        
        summary = {
            "data_sources_enabled": sum([
                1 if data.get(k, {}).get('enabled') else 0
                for k in ['aws_config', 'security_hub', 'guardduty', 'vpc_flow_logs', 
                         'iam_credentials', 'trusted_advisor', 'compute_optimizer', 'inspector']
            ]),
            "total_security_findings": (
                data.get('security_hub', {}).get('total_findings', 0) +
                data.get('guardduty', {}).get('total_findings', 0) +
                data.get('inspector', {}).get('total_findings', 0)
            ),
            "total_compliance_issues": (
                len(data.get('aws_config', {}).get('non_compliant_resources', [])) +
                len(data.get('iam_credentials', {}).get('issues', []))
            ),
            "total_optimization_opportunities": (
                data.get('compute_optimizer', {}).get('total_recommendations', 0) +
                data.get('trusted_advisor', {}).get('checks_with_issues', 0)
            ),
            "critical_issues": {
                "security_hub_critical": data.get('security_hub', {}).get('by_severity', {}).get('CRITICAL', 0),
                "guardduty_high": data.get('guardduty', {}).get('by_severity', {}).get('HIGH', 0),
                "inspector_critical": data.get('inspector', {}).get('by_severity', {}).get('CRITICAL', 0),
                "iam_no_mfa": len([i for i in data.get('iam_credentials', {}).get('issues', []) if i.get('issue') == 'no_mfa']),
            },
        }
        
        return summary
