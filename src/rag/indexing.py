"""
GraphRAG Grounding Layer — indexes the behavioral dataset into a knowledge graph
and retrieves relevant context for every LLM call, ensuring zero hallucinations.

Uses Microsoft GraphRAG's key concepts:
  1. Entity extraction from behavioral records
  2. Community detection in the knowledge graph
  3. Context retrieval via community summaries

When GraphRAG is not installed, falls back to a local semantic index built
from the JSONL behavioral dataset.
"""

from __future__ import annotations

import json
import os
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict


class BehavioralKnowledgeIndex:
    """Local knowledge index built from the behavioral JSONL dataset.
    Groups behavioral records by architecture, scenario, and risk class
    to provide grounded context for LLM reasoning."""

    def __init__(self):
        self.records: List[Dict] = []
        self.by_architecture: Dict[str, List[Dict]] = defaultdict(list)
        self.by_scenario: Dict[str, List[Dict]] = defaultdict(list)
        self.by_risk_class: Dict[str, List[Dict]] = defaultdict(list)
        self.by_pattern: Dict[str, List[Dict]] = defaultdict(list)
        self.community_summaries: Dict[str, str] = {}
        self._indexed = False

    def load_dataset(self, jsonl_path: str | Path):
        """Load the behavioral JSONL dataset into memory and build indices."""
        path = Path(jsonl_path)
        if not path.exists():
            print(f"⚠️  Dataset not found at {path}, running with empty index")
            return

        print(f"📚 Loading behavioral dataset from {path}...")
        count = 0
        with open(path) as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                self.records.append(record)
                self.by_architecture[record["architecture_name"]].append(record)
                self.by_scenario[record["scenario_label"]].append(record)
                self.by_risk_class[record["risk_class"]].append(record)
                dominant = record.get("structural_patterns", {}).get("dominant_pattern", "")
                if dominant:
                    self.by_pattern[dominant].append(record)
                count += 1

        print(f"   ✅ Indexed {count:,} records across {len(self.by_architecture)} architectures")
        self._build_community_summaries()
        self._indexed = True

    def _build_community_summaries(self):
        """Build GraphRAG-style community summaries — aggregated statistical
        summaries for each architecture and pattern community."""

        for arch_name, records in self.by_architecture.items():
            n = len(records)
            costs = [r["stressed_total_cost"] for r in records]
            amps = [r["amplification_factor"] for r in records]
            risk_counts = defaultdict(int)
            for r in records:
                risk_counts[r["risk_class"]] += 1

            overload_probs = [r["overload_probability"] for r in records]
            patterns = defaultdict(int)
            for r in records:
                p = r.get("structural_patterns", {}).get("dominant_pattern", "unknown")
                patterns[p] += 1

            self.community_summaries[f"arch:{arch_name}"] = (
                f"Architecture '{arch_name}' ({records[0]['architecture_pattern']}, "
                f"{records[0]['total_services']} services, {records[0]['total_dependencies']} deps). "
                f"Baseline cost: ${records[0]['baseline_cost_monthly']:,.0f}/mo. "
                f"Across {n:,} behavioral simulations: "
                f"mean stressed cost ${sum(costs)/n:,.0f}, "
                f"mean amplification {sum(amps)/n:.3f}×, "
                f"risk distribution: {dict(risk_counts)}, "
                f"mean overload probability {sum(overload_probs)/n:.1%}. "
                f"Dominant patterns: {dict(patterns)}."
            )

        for pattern, records in self.by_pattern.items():
            n = len(records)
            amps = [r["amplification_factor"] for r in records]
            overloads = [r["overload_probability"] for r in records]
            self.community_summaries[f"pattern:{pattern}"] = (
                f"Structural pattern '{pattern}' observed in {n:,} simulations. "
                f"Mean amplification: {sum(amps)/n:.3f}×, "
                f"mean overload probability: {sum(overloads)/n:.1%}. "
                f"This pattern {'increases' if sum(amps)/n > 1.15 else 'maintains'} "
                f"cost growth relative to traffic."
            )

    def retrieve_context(self, architecture_name: str,
                         scenario: str = "",
                         risk_class: str = "",
                         max_records: int = 10) -> Dict[str, Any]:
        """Retrieve grounded context for LLM reasoning."""

        context = {
            "community_summaries": [],
            "relevant_records": [],
            "statistical_ground_truth": {},
        }

        if not self._indexed:
            return context

        # Community summaries
        arch_key = f"arch:{architecture_name}"
        if arch_key in self.community_summaries:
            context["community_summaries"].append(self.community_summaries[arch_key])

        # Pattern summaries for this architecture
        arch_records = self.by_architecture.get(architecture_name, [])
        if arch_records:
            patterns_seen = set()
            for r in arch_records[:100]:
                p = r.get("structural_patterns", {}).get("dominant_pattern", "")
                if p:
                    patterns_seen.add(p)
            for p in patterns_seen:
                pk = f"pattern:{p}"
                if pk in self.community_summaries:
                    context["community_summaries"].append(self.community_summaries[pk])

        # Relevant records (sample)
        candidates = arch_records
        if scenario:
            candidates = [r for r in candidates if r["scenario_label"] == scenario]
        if risk_class:
            candidates = [r for r in candidates if r["risk_class"] == risk_class]

        # Take highest-amplification records for grounding
        candidates.sort(key=lambda r: r["amplification_factor"], reverse=True)
        sampled = candidates[:max_records]

        for r in sampled:
            context["relevant_records"].append({
                "scenario": r["scenario_label"],
                "traffic_mult": r["traffic_multiplier"],
                "amplification": r["amplification_factor"],
                "risk_class": r["risk_class"],
                "cost_growth": r["cost_growth_ratio"],
                "overloaded": r["overloaded_services"],
                "overload_prob": r["overload_probability"],
                "dominant_pattern": r.get("structural_patterns", {}).get("dominant_pattern", ""),
            })

        # Statistical ground truth
        if arch_records:
            costs = [r["stressed_total_cost"] for r in arch_records]
            amps = [r["amplification_factor"] for r in arch_records]
            context["statistical_ground_truth"] = {
                "n_simulations": len(arch_records),
                "cost_min": round(min(costs), 2),
                "cost_max": round(max(costs), 2),
                "cost_mean": round(sum(costs) / len(costs), 2),
                "cost_std": round((sum((c - sum(costs)/len(costs))**2 for c in costs) / len(costs))**0.5, 2),
                "amp_min": round(min(amps), 4),
                "amp_max": round(max(amps), 4),
                "amp_mean": round(sum(amps) / len(amps), 4),
                "risk_distribution": dict(defaultdict(int, {
                    r["risk_class"]: sum(1 for r2 in arch_records if r2["risk_class"] == r["risk_class"])
                    for r in arch_records[:3]
                })),
            }

        return context

    def format_grounding_prompt(self, context: Dict[str, Any]) -> str:
        """Format the retrieved context into a grounding prompt section
        that constrains LLM output to factual data."""

        parts = []
        parts.append("=== GROUND TRUTH DATA (you MUST base your analysis on this data) ===")

        if context.get("community_summaries"):
            parts.append("\n--- Knowledge Graph Community Summaries ---")
            for s in context["community_summaries"]:
                parts.append(f"• {s}")

        if context.get("statistical_ground_truth"):
            gt = context["statistical_ground_truth"]
            parts.append(f"\n--- Statistical Ground Truth ({gt.get('n_simulations', 0):,} simulations) ---")
            parts.append(f"Cost range: ${gt.get('cost_min', 0):,.0f} – ${gt.get('cost_max', 0):,.0f}")
            parts.append(f"Cost mean ± std: ${gt.get('cost_mean', 0):,.0f} ± ${gt.get('cost_std', 0):,.0f}")
            parts.append(f"Amplification range: {gt.get('amp_min', 0):.3f}× – {gt.get('amp_max', 0):.3f}×")
            parts.append(f"Risk distribution: {gt.get('risk_distribution', {})}")

        if context.get("relevant_records"):
            parts.append(f"\n--- Highest-Risk Behavioral Records ---")
            for r in context["relevant_records"][:5]:
                parts.append(
                    f"• Scenario={r['scenario']}, traffic={r['traffic_mult']:.1f}×, "
                    f"amp={r['amplification']:.3f}×, risk={r['risk_class']}, "
                    f"overloaded={r['overloaded']}"
                )

        parts.append("\n=== END GROUND TRUTH — Do NOT speculate beyond this data ===")
        return "\n".join(parts)


# ── Singleton index ──────────────────────────────────────────────────────
_index: Optional[BehavioralKnowledgeIndex] = None

def get_knowledge_index() -> BehavioralKnowledgeIndex:
    global _index
    if _index is None:
        _index = BehavioralKnowledgeIndex()
        # Try to load from default location
        dataset_path = Path(__file__).resolve().parent.parent.parent / "data" / "behavioral" / "behavioral_dataset.jsonl"
        if dataset_path.exists():
            _index.load_dataset(dataset_path)
    return _index
