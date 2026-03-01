"""
TF-IDF Embeddings for GraphRAG — lightweight document vectorization.

Uses pure Python TF-IDF (no heavy ML deps) to embed architecture descriptions,
graph engine output, and behavioral data into searchable document vectors.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple


class TFIDFEmbedder:
    """Lightweight TF-IDF document embedder using pure Python."""

    def __init__(self):
        self.vocab: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_count: int = 0
        self._fitted = False

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Lowercase, split on non-alphanumeric, remove short tokens."""
        tokens = re.findall(r'[a-z0-9]+(?:[\-_][a-z0-9]+)*', text.lower())
        return [t for t in tokens if len(t) > 1]

    def fit(self, documents: List[str]) -> "TFIDFEmbedder":
        """Build vocabulary and IDF from a corpus of documents."""
        self.doc_count = len(documents)
        doc_freq: Dict[str, int] = defaultdict(int)

        all_tokens = set()
        for doc in documents:
            tokens = set(self._tokenize(doc))
            for t in tokens:
                doc_freq[t] += 1
            all_tokens.update(tokens)

        # Build vocab — keep tokens appearing in at least 2 docs or if small corpus
        min_df = 1 if self.doc_count < 50 else 2
        sorted_tokens = sorted(t for t in all_tokens if doc_freq[t] >= min_df)
        self.vocab = {t: i for i, t in enumerate(sorted_tokens)}

        # IDF = log(N / df)
        for token, idx in self.vocab.items():
            self.idf[token] = math.log((self.doc_count + 1) / (doc_freq[token] + 1)) + 1

        self._fitted = True
        return self

    def transform(self, text: str) -> List[float]:
        """Convert a single document to a TF-IDF vector."""
        if not self._fitted:
            raise RuntimeError("Call fit() before transform()")

        tokens = self._tokenize(text)
        tf = Counter(tokens)
        max_tf = max(tf.values()) if tf else 1

        vector = [0.0] * len(self.vocab)
        for token, count in tf.items():
            if token in self.vocab:
                idx = self.vocab[token]
                # Augmented TF * IDF
                vector[idx] = (0.5 + 0.5 * count / max_tf) * self.idf.get(token, 1.0)

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def batch_transform(self, documents: List[str]) -> List[List[float]]:
        """Transform multiple documents."""
        return [self.transform(doc) for doc in documents]

    @property
    def vocab_size(self) -> int:
        return len(self.vocab)


def architecture_to_text(arch: Dict[str, Any]) -> str:
    """Convert an architecture JSON to a searchable text document.
    
    Extracts key information for embedding:
    - Pattern, region, cost tier
    - Service names and types
    - Dependency structure
    - Cost distribution
    """
    meta = arch.get("metadata", {})
    services = arch.get("services", [])
    deps = arch.get("dependencies", [])

    parts = [
        f"Architecture: {meta.get('name', 'Unknown')}",
        f"Pattern: {meta.get('pattern', '')}",
        f"Complexity: {meta.get('complexity', '')}",
        f"Region: {meta.get('region', '')} {meta.get('region_name', '')}",
        f"Cost tier: {meta.get('cost_tier', '')} {meta.get('cost_tier_label', '')}",
        f"Total services: {meta.get('total_services', len(services))}",
        f"Total cost: ${meta.get('total_cost_monthly', 0):,.0f} per month",
    ]

    # Service details
    for svc in services:
        parts.append(
            f"Service {svc.get('name', '')} type {svc.get('type', '')} "
            f"aws {svc.get('aws_service', '')} cost ${svc.get('cost_monthly', 0):,.0f} "
            f"owner {svc.get('owner', '')} region {svc.get('region', '')}"
        )

    # Dependency summary
    dep_types = Counter(d.get("type", "") for d in deps)
    for dtype, count in dep_types.items():
        parts.append(f"Dependency type {dtype} count {count}")

    # Service type summary
    svc_types = Counter(s.get("type", "") for s in services)
    for stype, count in svc_types.items():
        parts.append(f"Service type {stype} count {count}")

    return " . ".join(parts)


def graph_output_to_text(graph_json: Dict[str, Any], arch_name: str = "") -> str:
    """Convert graph engine output to searchable text.
    
    Extracts metrics, critical nodes, cost hotspots for embedding.
    """
    metrics = graph_json.get("metrics", {})
    nodes = graph_json.get("nodes", [])

    parts = [
        f"Graph analysis for {arch_name}",
        f"Total services {metrics.get('total_services', 0)}",
        f"Total dependencies {metrics.get('total_dependencies', 0)}",
        f"Total cost ${metrics.get('total_cost_monthly', 0):,.0f}",
        f"Average degree {metrics.get('avg_degree', 0)}",
        f"Graph density {metrics.get('density', 0)}",
        f"Is DAG {metrics.get('is_dag', True)}",
        f"Components {metrics.get('components', 1)}",
        f"Critical nodes {' '.join(metrics.get('critical_nodes', []))}",
        f"Cost hotspots {' '.join(metrics.get('cost_hotspots', []))}",
    ]

    # Top nodes by centrality
    sorted_nodes = sorted(nodes, key=lambda n: n.get("betweenness_centrality", 0), reverse=True)
    for n in sorted_nodes[:5]:
        parts.append(
            f"Node {n.get('name', '')} type {n.get('type', '')} "
            f"centrality {n.get('betweenness_centrality', 0):.4f} "
            f"cost ${n.get('cost_monthly', 0):,.0f} "
            f"cost_share {n.get('cost_share', 0):.1f}%"
        )

    return " . ".join(parts)
