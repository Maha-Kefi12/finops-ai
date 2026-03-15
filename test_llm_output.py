#!/usr/bin/env python3
"""Test script to see actual LLM output."""

import json
import requests
import sys

OLLAMA_URL = "http://localhost:11434"
MODEL = "finops-aws"

# Minimal test context
context = """
ARCHITECTURE: Microservices Demo
TOTAL SERVICES: 5
TOTAL MONTHLY COST: $2,500

KEY METRICS:
- Average latency: 45ms
- Error rate: 0.2%
- CPU utilization: 65%
"""

aws_practices = """
AWS FinOps Best Practices:
1. Rightsize instances
2. Use Reserved Instances
3. Optimize storage
"""

cur_metrics = """
Top 3 Cost Drivers:
1. EC2 - $1,200/mo
2. RDS - $800/mo
3. NAT Gateway - $300/mo
"""

narratives = """
API Service: Critical path, high utilization, good availability
"""

system_prompt = """You are a FinOps optimization expert. Generate EXACTLY 2 cost optimization recommendations in the following format:

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
... similar format ...

Only output recommendations. No explanation before or after."""

user_prompt = f"""Analyze this architecture and generate cost optimization recommendations:

CONTEXT
{context}

AWS BEST PRACTICES
{aws_practices}

CUR METRICS
{cur_metrics}

NARRATIVES
{narratives}

Generate 2 cost optimization recommendations in exactly the format specified by the system prompt."""

print("[*] Calling Ollama LLM...", file=sys.stderr)
print(f"[*] URL: {OLLAMA_URL}/api/chat", file=sys.stderr)
print(f"[*] Model: {MODEL}", file=sys.stderr)

try:
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 4000,
            },
        },
        timeout=300,
    )
    
    if resp.status_code == 200:
        content = resp.json().get("message", {}).get("content", "")
        print("[+] LLM Response received", file=sys.stderr)
        print(f"[+] Length: {len(content)} chars", file=sys.stderr)
        print("\n=== LLM RAW OUTPUT ===")
        print(content)
        print("\n=== END LLM OUTPUT ===\n")
        
        # Try to parse it
        import re
        matches = list(re.finditer(r"COST OPTIMIZATION RECOMMENDATION #(\d+)", content))
        print(f"[*] Found {len(matches)} COST OPTIMIZATION RECOMMENDATION sections", file=sys.stderr)
        for i, match in enumerate(matches):
            print(f"    [{i+1}] at position {match.start()}", file=sys.stderr)
    else:
        print(f"[-] Ollama returned status {resp.status_code}", file=sys.stderr)
        print(f"[-] Response: {resp.text[:500]}", file=sys.stderr)
except Exception as e:
    print(f"[-] Error: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
