"""
In-Memory Vector Store — fast cosine similarity search for RAG retrieval.

Stores document vectors (from TF-IDF embeddings) with metadata.
Persists to JSON for reuse across sessions. Supports:
  - Batch indexing of 2000+ documents
  - Top-k cosine similarity search
  - Filtering by metadata (pattern, region, etc.)
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class VectorStore:
    """In-memory vector store with cosine similarity search."""

    def __init__(self, persist_dir: Optional[str] = None):
        self.documents: List[Dict[str, Any]] = []  # {id, text, vector, metadata}
        self.persist_dir = Path(persist_dir) if persist_dir else None
        if self.persist_dir:
            self.persist_dir.mkdir(parents=True, exist_ok=True)

    def add(self, doc_id: str, text: str, vector: List[float],
            metadata: Optional[Dict] = None) -> None:
        """Add a document to the store."""
        self.documents.append({
            "id": doc_id,
            "text": text,
            "vector": vector,
            "metadata": metadata or {},
        })

    def add_batch(self, items: List[Dict[str, Any]]) -> None:
        """Add multiple documents. Each item: {id, text, vector, metadata}."""
        self.documents.extend(items)

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
        norm_b = math.sqrt(sum(x * x for x in b)) or 1.0
        return dot / (norm_a * norm_b)

    def search(self, query_vector: List[float], top_k: int = 5,
               filter_metadata: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Find top-k most similar documents to query vector.
        
        Returns list of {id, text, metadata, score} sorted by similarity.
        """
        results = []

        for doc in self.documents:
            # Apply metadata filter
            if filter_metadata:
                skip = False
                for key, value in filter_metadata.items():
                    if doc["metadata"].get(key) != value:
                        skip = True
                        break
                if skip:
                    continue

            score = self._cosine_similarity(query_vector, doc["vector"])
            results.append({
                "id": doc["id"],
                "text": doc["text"],
                "metadata": doc["metadata"],
                "score": score,
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def save(self, filename: str = "vector_store.json") -> str:
        """Persist to JSON (vectors stored as lists)."""
        if not self.persist_dir:
            raise RuntimeError("No persist_dir set")

        filepath = self.persist_dir / filename

        # Store without vectors for space efficiency — rebuild from embedder
        store_data = {
            "doc_count": len(self.documents),
            "documents": [
                {
                    "id": d["id"],
                    "text": d["text"][:500],  # Truncate text for storage
                    "metadata": d["metadata"],
                    "vector": d["vector"],
                }
                for d in self.documents
            ],
        }

        with open(filepath, "w") as f:
            json.dump(store_data, f)

        return str(filepath)

    def load(self, filename: str = "vector_store.json") -> bool:
        """Load from persisted JSON."""
        if not self.persist_dir:
            return False

        filepath = self.persist_dir / filename
        if not filepath.exists():
            return False

        with open(filepath) as f:
            store_data = json.load(f)

        self.documents = store_data.get("documents", [])
        return True

    @property
    def size(self) -> int:
        return len(self.documents)

    def clear(self) -> None:
        self.documents = []

    def get_stats(self) -> Dict[str, Any]:
        """Return store statistics."""
        if not self.documents:
            return {"size": 0}

        patterns = set()
        regions = set()
        cost_tiers = set()
        for d in self.documents:
            m = d.get("metadata", {})
            if m.get("pattern"):
                patterns.add(m["pattern"])
            if m.get("region"):
                regions.add(m["region"])
            if m.get("cost_tier"):
                cost_tiers.add(m["cost_tier"])

        return {
            "size": len(self.documents),
            "patterns": sorted(patterns),
            "regions": sorted(regions),
            "cost_tiers": sorted(cost_tiers),
            "vector_dim": len(self.documents[0].get("vector", [])) if self.documents else 0,
        }
