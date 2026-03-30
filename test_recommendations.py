#!/usr/bin/env python3
"""Test script for recommendation generation API"""
import requests
import json
import sys

def test_recommendations():
    url = "http://localhost:8000/api/analyze/recommendations"
    payload = {"architecture_file": "ecommerce_small_us-east-1_startup_v1.json"}
    
    print("🚀 Testing recommendation generation...")
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print("-" * 70)
    print("⏳ This may take 1-3 minutes for LLM generation...")
    print()
    
    try:
        response = requests.post(url, json=payload, timeout=300)
        
        if response.status_code == 200:
            data = response.json()
            
            print("✅ SUCCESS!")
            print(f"Total recommendations: {len(data.get('recommendations', []))}")
            print(f"Total savings: ${data.get('total_estimated_savings', 0):.2f}/month")
            print(f"LLM used: {data.get('llm_used', False)}")
            print(f"Generation time: {data.get('generation_time_ms', 0)}ms")
            print("-" * 70)
            
            # Analyze recommendation sources
            recs = data.get('recommendations', [])
            if recs:
                sources = {}
                validation_statuses = {}
                
                for rec in recs:
                    src = rec.get('source', 'unknown')
                    sources[src] = sources.get(src, 0) + 1
                    
                    status = rec.get('validation_status', 'none')
                    validation_statuses[status] = validation_statuses.get(status, 0) + 1
                
                print("\n📊 Recommendation Breakdown:")
                print(f"  By Source:")
                for src, count in sources.items():
                    print(f"    - {src}: {count}")
                
                print(f"\n  By Validation Status:")
                for status, count in validation_statuses.items():
                    print(f"    - {status}: {count}")
                
                # Show first recommendation details
                print("\n📝 First Recommendation Sample:")
                first_rec = recs[0]
                print(f"  Title: {first_rec.get('title', 'N/A')}")
                print(f"  Source: {first_rec.get('source', 'N/A')}")
                print(f"  Action: {first_rec.get('action', 'N/A')}")
                print(f"  Savings: ${first_rec.get('total_estimated_savings', 0):.2f}/month")
                print(f"  Validation Status: {first_rec.get('validation_status', 'N/A')}")
                if first_rec.get('validation_notes'):
                    print(f"  Validation Notes: {first_rec.get('validation_notes')}")
                if first_rec.get('engine_confidence'):
                    print(f"  Engine Confidence: {first_rec.get('engine_confidence'):.2f}")
                if first_rec.get('llm_confidence'):
                    print(f"  LLM Confidence: {first_rec.get('llm_confidence'):.2f}")
            
            return 0
        else:
            print(f"❌ ERROR: HTTP {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return 1
            
    except requests.exceptions.Timeout:
        print("❌ ERROR: Request timed out after 120s")
        return 1
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(test_recommendations())
