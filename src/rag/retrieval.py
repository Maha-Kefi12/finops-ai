"""
GraphRAG Retriever — combines graph engine output, vector similarity,
and behavioral data into grounded context for LLM reasoning.

Pipeline: Query → Embed → Vector Search → Graph Metrics → Format → LLM
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .embeddings import TFIDFEmbedder, architecture_to_text, graph_output_to_text
from .vector_store import VectorStore


RAG_INDEX_DIR = Path(os.getenv(
    "RAG_INDEX_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "data" / "rag_index")
))


class GraphRAGRetriever:
    """Retriever that combines vector similarity with graph engine knowledge."""

    def __init__(self, index_dir: Optional[str] = None):
        self.index_dir = Path(index_dir) if index_dir else RAG_INDEX_DIR
        self.embedder = TFIDFEmbedder()
        self.arch_store = VectorStore(persist_dir=str(self.index_dir))
        self.graph_store = VectorStore(persist_dir=str(self.index_dir))
        self._loaded = False

    def load(self) -> bool:
        """Load persisted index from disk."""
        if self._loaded:
            return True

        try:
            self.arch_store.load("arch_vectors.json")
            self.graph_store.load("graph_vectors.json")

            # Rebuild embedder vocab from stored data
            vocab_path = self.index_dir / "embedder_vocab.json"
            if vocab_path.exists():
                with open(vocab_path) as f:
                    data = json.load(f)
                self.embedder.vocab = data.get("vocab", {})
                self.embedder.idf = data.get("idf", {})
                self.embedder.doc_count = data.get("doc_count", 0)
                self.embedder._fitted = True

            self._loaded = (self.arch_store.size > 0)
            return self._loaded
        except Exception:
            return False

    def query(self, query_text: str, top_k: int = 5,
              filter_pattern: Optional[str] = None,
              filter_region: Optional[str] = None) -> Dict[str, Any]:
        """Query the RAG index for relevant architectures and graph data.

        Returns grounded context combining:
        - Similar architecture descriptions
        - Graph engine metrics for those architectures
        - Statistical summaries
        """
        if not self._loaded:
            self.load()

        if not self.embedder._fitted or self.arch_store.size == 0:
            return {"context": "", "sources": [], "stats": {"indexed": 0}}

        # Embed query
        query_vec = self.embedder.transform(query_text)

        # Build metadata filter
        meta_filter = {}
        if filter_pattern:
            meta_filter["pattern"] = filter_pattern
        if filter_region:
            meta_filter["region"] = filter_region

        # Search architecture store
        arch_results = self.arch_store.search(
            query_vec, top_k=top_k,
            filter_metadata=meta_filter if meta_filter else None
        )

        # Search graph store for matching architectures
        graph_results = self.graph_store.search(
            query_vec, top_k=top_k,
            filter_metadata=meta_filter if meta_filter else None
        )

        # Merge results
        sources = []
        for ar in arch_results:
            matching_graph = next(
                (g for g in graph_results if g["metadata"].get("arch_id") == ar["metadata"].get("arch_id")),
                None
            )
            sources.append({
                "arch_id": ar["metadata"].get("arch_id", ar["id"]),
                "name": ar["metadata"].get("name", ""),
                "pattern": ar["metadata"].get("pattern", ""),
                "region": ar["metadata"].get("region", ""),
                "cost_tier": ar["metadata"].get("cost_tier", ""),
                "services": ar["metadata"].get("services", 0),
                "cost": ar["metadata"].get("cost", 0),
                "similarity": round(ar["score"], 4),
                "graph_summary": matching_graph["text"][:300] if matching_graph else "",
            })

        return {
            "context": self._format_context(sources),
            "sources": sources,
            "stats": self.get_stats(),
        }

    def retrieve_for_architecture(self, arch_name: str, top_k: int = 3) -> Dict[str, Any]:
        """Retrieve context specifically for a named architecture.
        
        Used by agents to get grounded data for a specific architecture.
        """
        return self.query(arch_name, top_k=top_k)

    def _format_context(self, sources: List[Dict]) -> str:
        """Format retrieval results into a grounding prompt for LLM."""
        if not sources:
            return ""

        parts = ["=== GROUNDED CONTEXT FROM RAG INDEX ===\n"]
        parts.append(f"Found {len(sources)} similar architectures in the knowledge base:\n")

        for i, src in enumerate(sources, 1):
            parts.append(
                f"[{i}] {src['name']} ({src['pattern']}, {src['region']}, {src['cost_tier']})\n"
                f"    Services: {src['services']}, Cost: ${src['cost']:,.0f}/mo, "
                f"    Similarity: {src['similarity']:.0%}\n"
            )
            if src.get("graph_summary"):
                parts.append(f"    Graph: {src['graph_summary'][:200]}\n")

        parts.append(
            "\nIMPORTANT: Base your analysis on these documented architectures. "
            "Do NOT invent data points. If the query doesn't match any indexed architecture, "
            "say 'insufficient data in the knowledge base'.\n"
        )
        return "\n".join(parts)

    def get_stats(self) -> Dict[str, Any]:
        """Return index statistics."""
        return {
            "indexed": self.arch_store.size,
            "graph_indexed": self.graph_store.size,
            "vocab_size": self.embedder.vocab_size,
            "arch_stats": self.arch_store.get_stats(),
        }
