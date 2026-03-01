"""
FinOps GraphRAG Module

Provides:
  - BehavioralKnowledgeIndex: indexes behavioral JSONL data
  - TFIDFEmbedder: document vectorization
  - VectorStore: cosine similarity search
  - GraphRAGRetriever: combined graph + vector retrieval
"""

from .indexing import BehavioralKnowledgeIndex, get_knowledge_index
from .embeddings import TFIDFEmbedder, architecture_to_text, graph_output_to_text
from .vector_store import VectorStore
from .retrieval import GraphRAGRetriever

__all__ = [
    "BehavioralKnowledgeIndex",
    "get_knowledge_index",
    "TFIDFEmbedder",
    "architecture_to_text",
    "graph_output_to_text",
    "VectorStore",
    "GraphRAGRetriever",
]
