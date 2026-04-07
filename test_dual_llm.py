"""Quick test: run recommendation pipeline on multiple synthetic architectures
   and verify both engine (narrated) + LLM proposed cards appear."""
import json, sys, os, time

sys.path.insert(0, os.path.dirname(__file__))

from src.llm.client import generate_recommendations
from dataclasses import dataclass

SYNTHETIC_DIR = os.path.join(os.path.dirname(__file__), "data", "synthetic")

# Pick 3 diverse architectures for a fast test
TEST_FILES = [
    "adtech_medium_us-east-1_growth_v1.json",
    "healthcare_large_us-east-1_enterprise_v1.json",
    "ecommerce_small_eu-west-1_enterprise_v0.json",
]

@dataclass
class MinimalContext:
    service_inventory: str = ""
    cloudwatch_metrics: str = ""
    graph_context: str = ""
    business_graph_context: str = ""
    pricing_data: str = ""
    aws_best_practices: str = ""

for fname in TEST_FILES:
    fpath = os.path.join(SYNTHETIC_DIR, fname)
    if not os.path.exists(fpath):
        print(f"SKIP {fname} (not found)")
        continue

    print(f"\n{'='*70}")
    print(f"TESTING: {fname}")
    print(f"{'='*70}")

    with open(fpath) as f:
        graph_data = json.load(f)

    ctx = MinimalContext()
    t0 = time.time()
    result = generate_recommendations(ctx, architecture_name=fname, raw_graph_data=graph_data)
    elapsed = time.time() - t0

    engine_count = sum(1 for c in result.cards if c.get("source") in ("engine", "engine_backed"))
    llm_count = sum(1 for c in result.cards if c.get("source") == "llm_proposed")

    print(f"\n--- RESULTS for {fname} ({elapsed:.1f}s) ---")
    print(f"  Total cards: {len(result.cards)}")
    print(f"  Engine:      {engine_count}")
    print(f"  LLM:         {llm_count}")
    print(f"  Savings:     ${result.total_estimated_savings:.2f}")

    # Check narrative enrichment on engine cards
    narrated = 0
    for c in result.cards:
        if c.get("source") in ("engine", "engine_backed"):
            why = c.get("why_it_matters", "")
            if why and len(why) > 50:
                narrated += 1
    print(f"  Narrated engine cards: {narrated}/{engine_count}")

    # Show LLM card actions
    if llm_count > 0:
        print(f"  LLM actions: {[c.get('action','?') for c in result.cards if c.get('source') == 'llm_proposed']}")
    else:
        print("  ⚠️  NO LLM CARDS — quality gates may still be too strict")

    print()
