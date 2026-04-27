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

    # ── Fixed output dimension — MUST match the database schema vector(128) ──
    MAX_FEATURES: int = 128

    def fit(self, documents: List[str]) -> "TFIDFEmbedder":
        """Build vocabulary and IDF from a corpus of documents.

        Output dimension is ALWAYS exactly MAX_FEATURES (128) to match
        the PostgreSQL vector(128) column:
        - corpus > 128 unique tokens: keep top-128 by IDF.
        - corpus < 128 unique tokens: pad with __pad_N__ sentinel tokens.
        """
        self.doc_count = len(documents)
        doc_freq: Dict[str, int] = defaultdict(int)

        all_tokens: set = set()
        for doc in documents:
            tokens = set(self._tokenize(doc))
            for t in tokens:
                doc_freq[t] += 1
            all_tokens.update(tokens)

        # Build candidate vocab — filter extreme frequencies
        # min_df: exclude tokens appearing in < 2 docs (too rare / unique)
        # max_df: exclude tokens appearing in > 95% of docs (stop words like 'the', 'and')
        min_df = 2 if self.doc_count >= 50 else 1
        max_df = int(0.95 * self.doc_count) or self.doc_count
        candidate_tokens = [
            t for t in all_tokens
            if min_df <= doc_freq[t] <= max_df
        ]

        # Compute IDF scores (used as weights in transform())
        idf_scores: Dict[str, float] = {}
        for token in candidate_tokens:
            idf_scores[token] = math.log((self.doc_count + 1) / (doc_freq[token] + 1)) + 1

        # ── KEY FIX: Select top MAX_FEATURES by DOCUMENT FREQUENCY descending ──
        # High doc_freq tokens appear in the MOST documents, so they will
        # produce non-zero embeddings for the majority of chunks during
        # transform(). Sorting by IDF (rarest first) caused all-zero vectors
        # because those rare tokens appeared in almost no individual chunk.
        top_tokens = sorted(candidate_tokens, key=lambda t: doc_freq[t], reverse=True)
        top_tokens = top_tokens[:self.MAX_FEATURES]

        # Pad with sentinel tokens if corpus vocabulary < MAX_FEATURES
        if len(top_tokens) < self.MAX_FEATURES:
            n_pad = self.MAX_FEATURES - len(top_tokens)
            for i in range(n_pad):
                pad_tok = f"__pad_{i}__"
                top_tokens.append(pad_tok)
                idf_scores[pad_tok] = 0.0  # Zero weight — no effect on similarity

        # Final vocab — stable alphabetical ordering for reproducibility
        self.vocab = {t: i for i, t in enumerate(sorted(top_tokens))}
        self.idf = {t: idf_scores.get(t, 0.0) for t in self.vocab}

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

    def save(self, path: str) -> None:
        """Persist vocab and IDF weights to a JSON file.

        Call this once after fit() so the retrieval service can reload
        the exact same vocabulary without re-fitting on the whole corpus.
        """
        import json as _json
        state = {
            "vocab": self.vocab,
            "idf": self.idf,
            "doc_count": self.doc_count,
            "max_features": self.MAX_FEATURES,
        }
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(state, f)

    @classmethod
    def load(cls, path: str) -> "TFIDFEmbedder":
        """Reconstruct a fitted TFIDFEmbedder from a saved JSON file.

        This is the correct way to initialize the retrieval-time embedder:
        it uses the EXACT same vocabulary built at index time, so query
        vectors are comparable to stored vectors.
        """
        import json as _json
        with open(path, "r", encoding="utf-8") as f:
            state = _json.load(f)
        obj = cls()
        obj.vocab = state["vocab"]
        obj.idf = state["idf"]
        obj.doc_count = state["doc_count"]
        obj._fitted = True
        return obj


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
