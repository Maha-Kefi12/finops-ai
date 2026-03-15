#!/usr/bin/env python3
"""Test the recommendation parser with sample LLM output."""

import sys
sys.path.insert(0, '/home/finops/finops-ai-system')

from src.llm.client import _parse_structured_recommendations

# Sample LLM output in the expected format
sample_output = """
COST OPTIMIZATION RECOMMENDATION #1
─────────────────────────────────
RESOURCE IDENTIFICATION
┌─────────────────────────┐
│ Resource Type: EC2      │
│ Instance Size: t3.large │
│ Region: us-east-1       │
│ Owner: platform-team    │
└─────────────────────────┘

CURRENT COST BREAKDOWN
┌────────────────────────────────────────┐
│ Monthly On-Demand Cost: $1,200         │
│ Effective Hourly Rate: $1.65/hour      │
└────────────────────────────────────────┘

INEFFICIENCIES
• ISSUE #1: Over-provisioned for peak load
• ISSUE #2: No Reserved Instance discount

RECOMMENDATIONS
RECOMMENDATION #1: Rightsize to t3.medium (save $400/month)
  - Compute savings: $400/month
  - Implementation effort: 2 hours

SUMMARY
  Monthly Savings: $400
  Implementation Steps: Test on staging, update ASG config, deploy

COST OPTIMIZATION RECOMMENDATION #2
─────────────────────────────────
RESOURCE IDENTIFICATION
┌─────────────────────────┐
│ Resource Type: RDS      │
│ Instance Size: db.r5.2xl│
│ Region: us-east-1       │
│ Owner: backend-team     │
└─────────────────────────┘

CURRENT COST BREAKDOWN
┌────────────────────────────────────────┐
│ Monthly On-Demand Cost: $800           │
│ Effective Hourly Rate: $1.10/hour      │
└────────────────────────────────────────┘

INEFFICIENCIES
• ISSUE #1: Overallocated memory for workload
• ISSUE #2: Multi-AZ redundancy not needed for non-prod

RECOMMENDATIONS
RECOMMENDATION #2: Switch to db.r5.large single-AZ (save $300/month)
  - Compute savings: $300/month
  - Implementation effort: 3 hours

SUMMARY
  Monthly Savings: $300
  Implementation Steps: Backup, fail over to single AZ, monitor
"""

print("[*] Testing parser with sample LLM output")
cards = _parse_structured_recommendations(sample_output)
print(f"[+] Parsed {len(cards)} cards")

for i, card in enumerate(cards, 1):
    print(f"\n=== CARD {i} ===")
    print(f"Title: {card.get('title')}")
    print(f"Resource ID: {card.get('resource_id')}")
    print(f"Savings: ${card.get('total_estimated_savings')}")
    print(f"Inefficiencies: {len(card.get('inefficiencies', []))} items")
    print(f"Recommendations: {len(card.get('recommendations', []))} items")

if not cards:
    print("\n[-] ERROR: Parser returned no cards!")
    print("[-] Sample output first 500 chars:")
    print(sample_output[:500])
else:
    print(f"\n[+] SUCCESS: Parser extracted {len(cards)} valid cards")
