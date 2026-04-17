"""
Phase 5: RAG Integration

Hook into LLM and engine pipelines:
1. LLM Pipeline: Inject retrieved docs into context
2. Engine Pipeline: Reference docs for analysis
3. REST API: Add RAG endpoints
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import asdict
from datetime import datetime

from src.rag.retrieval_service import retrieve, get_retrieval_service, get_retrieval_stats
from src.graph.models import DocChunk
from sqlalchemy.orm import Session
from src.storage.database import SessionLocal

logger = logging.getLogger(__name__)


class RAGContext:
    """Context information for RAG-enriched requests."""
    
    def __init__(self):
        self.query: Optional[str] = None
        self.retrieved_chunks: List[Dict[str, Any]] = []
        self.retrieval_latency_ms: float = 0.0
        self.cache_hit: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'query': self.query,
            'retrieved_chunks': self.retrieved_chunks,
            'retrieval_latency_ms': self.retrieval_latency_ms,
            'cache_hit': self.cache_hit,
        }


class RAGIntegration:
    """Integration layer for RAG with LLM and engine pipelines."""
    
    def __init__(self):
        self.retrieval_service = get_retrieval_service()
    
    def retrieve_context(self, query: str, top_k: int = 5) -> RAGContext:
        """Retrieve context for a query."""
        context = RAGContext()
        context.query = query
        
        try:
            # Retrieve chunks
            results = retrieve(query, top_k=top_k)
            
            # Convert to dict for easy consumption
            for result in results:
                context.retrieved_chunks.append({
                    'chunk_id': result.chunk_id,
                    'text': result.text,
                    'source_file': result.source_file,
                    'source_type': result.source_type,
                    'section_hierarchy': result.section_hierarchy,
                    'score': round(result.score, 4),
                    'relevance_score': round(result.relevance_score, 4),
                })
            
            # Get stats
            stats = self.retrieval_service.get_stats()
            if stats.total_queries > 0:
                context.retrieval_latency_ms = stats.avg_latency_ms
                context.cache_hit = stats.cache_hits > 0
            
            logger.info(f"Retrieved {len(context.retrieved_chunks)} chunks for query: {query}")
            
        except Exception as e:
            logger.error(f"Failed to retrieve context: {e}", exc_info=True)
        
        return context
    
    def format_context_for_llm(self, rag_context: RAGContext) -> str:
        """Format retrieved context for injection into LLM prompts."""
        if not rag_context.retrieved_chunks:
            return ""
        
        lines = ["\n--- RETRIEVED CONTEXT FROM DOCUMENTATION ---"]
        
        for i, chunk in enumerate(rag_context.retrieved_chunks, 1):
            source = chunk['source_file']
            section = chunk.get('section_hierarchy', 'N/A')
            score = chunk['score']
            
            lines.append(f"\n[Document {i}] {source} | Section: {section} | Relevance: {score}")
            lines.append("---")
            lines.append(chunk['text'][:500])  # Truncate for context window
            lines.append("---")
        
        lines.append("\n--- END RETRIEVED CONTEXT ---\n")
        
        return "\n".join(lines)
    
    def inject_into_llm_prompt(self, base_prompt: str, query: str, 
                              top_k: int = 5) -> tuple[str, RAGContext]:
        """Inject retrieved docs into LLM prompt."""
        rag_context = self.retrieve_context(query, top_k=top_k)
        
        context_text = self.format_context_for_llm(rag_context)
        
        # Inject context before the main query
        enhanced_prompt = f"{context_text}\n{base_prompt}"
        
        logger.info(f"Enhanced prompt with {len(rag_context.retrieved_chunks)} chunks")
        
        return enhanced_prompt, rag_context
    
    def log_doc_usage(self, recommendation_id: str, chunks: List[Dict[str, Any]]) -> None:
        """Log which documents were used for a recommendation."""
        if not chunks:
            return
        
        sources = set()
        for chunk in chunks:
            sources.add(chunk['source_file'])
        
        logger.info(
            f"Recommendation {recommendation_id} used {len(sources)} source documents: "
            f"{', '.join(sorted(sources))}"
        )
    
    def get_document_sources(self) -> List[Dict[str, Any]]:
        """Get list of indexed document sources."""
        db = SessionLocal()
        try:
            # Get unique source files
            sources = db.query(DocChunk.source_file).distinct().all()
            
            result = []
            for (source_file,) in sources:
                # Count chunks per source
                chunk_count = db.query(DocChunk).filter(
                    DocChunk.source_file == source_file
                ).count()
                
                # Get source type
                chunk = db.query(DocChunk).filter(
                    DocChunk.source_file == source_file
                ).first()
                
                if chunk:
                    result.append({
                        'source_file': source_file,
                        'source_type': chunk.source_type,
                        'chunk_count': chunk_count,
                    })
            
            return sorted(result, key=lambda x: x['source_file'])
        
        finally:
            db.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get RAG statistics."""
        stats = self.retrieval_service.get_stats()
        
        db = SessionLocal()
        try:
            total_chunks = db.query(DocChunk).filter(
                DocChunk.is_active == True
            ).count()
            
            total_sources = db.query(DocChunk.source_file).distinct().count()
        
        finally:
            db.close()
        
        return {
            'total_indexed_chunks': total_chunks,
            'total_source_documents': total_sources,
            'total_queries': stats.total_queries,
            'cache_hits': stats.cache_hits,
            'cache_misses': stats.cache_misses,
            'avg_latency_ms': round(stats.avg_latency_ms, 2),
            'top_queries': stats.top_queries,
        }


# Global RAG integration instance
_rag_integration = None


def get_rag_integration() -> RAGIntegration:
    """Get or create the global RAG integration."""
    global _rag_integration
    if _rag_integration is None:
        _rag_integration = RAGIntegration()
    return _rag_integration


def retrieve_context(query: str, top_k: int = 5) -> RAGContext:
    """Retrieve context for a query."""
    rag = get_rag_integration()
    return rag.retrieve_context(query, top_k)


def format_context_for_llm(rag_context: RAGContext) -> str:
    """Format retrieved context for LLM injection."""
    rag = get_rag_integration()
    return rag.format_context_for_llm(rag_context)


def inject_into_llm_prompt(base_prompt: str, query: str, 
                          top_k: int = 5) -> tuple[str, RAGContext]:
    """Inject retrieved docs into LLM prompt."""
    rag = get_rag_integration()
    return rag.inject_into_llm_prompt(base_prompt, query, top_k)


def get_rag_stats() -> Dict[str, Any]:
    """Get RAG statistics."""
    rag = get_rag_integration()
    return rag.get_stats()
