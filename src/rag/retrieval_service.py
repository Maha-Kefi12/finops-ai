"""
Phase 4: Retrieval Service

High-performance retrieval with caching and vector search.
1. Cache check (Redis, 1h TTL): Query hash lookup
2. Vector search (pgvector): Embed query, cosine similarity, top-20
3. Contextual ranking: Score by relevance + boost + recency + popularity
4. Return top-K chunks with scores
"""

import hashlib
import logging
import time
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.storage.database import SessionLocal
from src.graph.models import DocChunk
from src.rag.embeddings import TFIDFEmbedder

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """A retrieval result with metadata."""
    chunk_id: str
    text: str
    source_file: str
    source_type: str
    section_hierarchy: Optional[str]
    score: float
    relevance_score: float
    retrieved_at: datetime


@dataclass
class RetrievalStats:
    """Statistics for retrieval performance."""
    total_queries: int
    cache_hits: int
    cache_misses: int
    avg_latency_ms: float
    top_queries: List[tuple]


class QueryCache:
    """Simple in-memory query cache (extensible to Redis)."""
    
    def __init__(self, ttl_seconds: int = 3600):
        self.cache: Dict[str, tuple] = {}  # query_hash -> (results, timestamp)
        self.ttl_seconds = ttl_seconds
        self.stats = {
            'hits': 0,
            'misses': 0,
            'queries': {}
        }
    
    def _hash_query(self, query: str, top_k: int) -> str:
        """Hash query parameters."""
        key = f"{query}:{top_k}"
        return hashlib.md5(key.encode()).hexdigest()
    
    def get(self, query: str, top_k: int) -> Optional[List[RetrievalResult]]:
        """Get cached results if available and not expired."""
        query_hash = self._hash_query(query, top_k)
        
        if query_hash in self.cache:
            results, timestamp = self.cache[query_hash]
            age_seconds = (datetime.utcnow() - timestamp).total_seconds()
            
            if age_seconds < self.ttl_seconds:
                self.stats['hits'] += 1
                logger.debug(f"Cache hit for query: {query}")
                return results
        
        self.stats['misses'] += 1
        return None
    
    def set(self, query: str, top_k: int, results: List[RetrievalResult]) -> None:
        """Cache query results."""
        query_hash = self._hash_query(query, top_k)
        self.cache[query_hash] = (results, datetime.utcnow())
        
        # Track query frequency
        if query not in self.stats['queries']:
            self.stats['queries'][query] = 0
        self.stats['queries'][query] += 1
    
    def clear(self) -> None:
        """Clear cache."""
        self.cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self.stats['hits'] + self.stats['misses']
        hit_rate = 100.0 * self.stats['hits'] / total if total > 0 else 0
        
        # Top 10 queries by frequency
        top_queries = sorted(
            self.stats['queries'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            'total_queries': total,
            'cache_hits': self.stats['hits'],
            'cache_misses': self.stats['misses'],
            'hit_rate_percent': hit_rate,
            'top_queries': top_queries,
        }


class RetrievalService:
    """High-performance document retrieval service."""
    
    def __init__(self, cache_enabled: bool = True):
        self.embedder = None
        self.cache = QueryCache() if cache_enabled else None
        self.latencies = []
        self.cache_enabled = cache_enabled
    
    def init_embedder(self) -> None:
        """Initialize embedder by fitting on all chunks in database."""
        db = SessionLocal()
        try:
            # Get all chunk texts
            chunks = db.query(DocChunk.chunk_text).all()
            if not chunks:
                logger.warning("No chunks in database, embedder not initialized")
                return
            
            chunk_texts = [chunk[0] for chunk in chunks]
            logger.info(f"Initializing embedder with {len(chunk_texts)} chunks...")
            
            self.embedder = TFIDFEmbedder()
            self.embedder.fit(chunk_texts)
            
            logger.info(f"Embedder ready: vocab_size={self.embedder.vocab_size}")
        
        finally:
            db.close()
    
    def _ensure_embedder(self) -> None:
        """Ensure embedder is initialized."""
        if not self.embedder:
            self.init_embedder()
    
    def _vector_distance(self, v1: List[float], v2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = sum(a * b for a, b in zip(v1, v2))
        norm_v1 = sum(a * a for a in v1) ** 0.5
        norm_v2 = sum(b * b for b in v2) ** 0.5
        
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        
        return dot_product / (norm_v1 * norm_v2)
    
    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        """Retrieve top-K chunks for a query."""
        start_time = time.time()
        
        # Check cache
        if self.cache_enabled and self.cache:
            cached = self.cache.get(query, top_k)
            if cached:
                latency_ms = (time.time() - start_time) * 1000
                self.latencies.append(latency_ms)
                logger.info(f"Retrieved {len(cached)} cached chunks in {latency_ms:.2f}ms")
                return cached
        
        self._ensure_embedder()
        
        if not self.embedder:
            logger.error("Embedder not available")
            return []
        
        # Embed query
        query_embedding = self.embedder.transform(query)
        
        # Search database
        db = SessionLocal()
        try:
            # Query all chunks
            all_chunks = db.query(DocChunk).filter(DocChunk.is_active == True).all()
            
            # Score and rank chunks
            scored_chunks = []
            for chunk in all_chunks:
                # Cosine similarity
                relevance_score = self._vector_distance(query_embedding, chunk.embedding)
                
                # Apply relevance boost
                final_score = relevance_score * chunk.relevance_boost
                
                # Recency boost (more recent chunks score higher)
                age_days = (datetime.utcnow() - chunk.indexed_at).days
                recency_factor = 1.0 if age_days < 1 else (1.0 - 0.1 * min(age_days, 10))
                final_score *= recency_factor
                
                # Popularity boost (frequently retrieved chunks score higher)
                popularity_factor = 1.0 + 0.01 * min(chunk.retrieval_count, 100)
                final_score *= popularity_factor
                
                scored_chunks.append((chunk, relevance_score, final_score))
            
            # Sort by final score (descending)
            scored_chunks.sort(key=lambda x: x[2], reverse=True)
            
            # Get top-K
            results = []
            for chunk, relevance_score, final_score in scored_chunks[:top_k]:
                result = RetrievalResult(
                    chunk_id=chunk.id,
                    text=chunk.chunk_text,
                    source_file=chunk.source_file,
                    source_type=chunk.source_type,
                    section_hierarchy=chunk.section_hierarchy,
                    score=final_score,
                    relevance_score=relevance_score,
                    retrieved_at=datetime.utcnow()
                )
                results.append(result)
                
                # Update retrieval count
                chunk.retrieval_count += 1
                chunk.last_retrieved = datetime.utcnow()
            
            db.commit()
            
            # Cache results
            if self.cache_enabled and self.cache:
                self.cache.set(query, top_k, results)
            
            # Track latency
            latency_ms = (time.time() - start_time) * 1000
            self.latencies.append(latency_ms)
            
            logger.info(f"Retrieved {len(results)} chunks in {latency_ms:.2f}ms (cold)")
            
            return results
        
        finally:
            db.close()
    
    def retrieve_by_source(self, source_file: str) -> List[DocChunk]:
        """Retrieve all active chunks from a specific source file."""
        db = SessionLocal()
        try:
            chunks = db.query(DocChunk).filter(
                DocChunk.source_file == source_file,
                DocChunk.is_active == True
            ).order_by(DocChunk.chunk_number).all()
            
            logger.info(f"Retrieved {len(chunks)} chunks from {source_file}")
            return chunks
        
        finally:
            db.close()
    
    def get_stats(self) -> RetrievalStats:
        """Get retrieval statistics."""
        cache_stats = self.cache.get_stats() if self.cache_enabled and self.cache else {}
        
        avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        
        return RetrievalStats(
            total_queries=cache_stats.get('total_queries', 0),
            cache_hits=cache_stats.get('cache_hits', 0),
            cache_misses=cache_stats.get('cache_misses', 0),
            avg_latency_ms=avg_latency,
            top_queries=cache_stats.get('top_queries', [])
        )
    
    def update_relevance_boost(self, chunk_id: str, boost: float) -> None:
        """Update relevance boost for a chunk."""
        db = SessionLocal()
        try:
            chunk = db.query(DocChunk).filter(DocChunk.id == chunk_id).first()
            if chunk:
                chunk.relevance_boost = boost
                db.commit()
                logger.info(f"Updated relevance boost for {chunk_id} to {boost}")
            else:
                logger.warning(f"Chunk not found: {chunk_id}")
        
        finally:
            db.close()
    
    def clear_cache(self) -> None:
        """Clear retrieval cache."""
        if self.cache_enabled and self.cache:
            self.cache.clear()
            logger.info("Retrieval cache cleared")


# Global retrieval service instance
_retrieval_service = None


def get_retrieval_service() -> RetrievalService:
    """Get or create the global retrieval service."""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService(cache_enabled=True)
        _retrieval_service.init_embedder()
    return _retrieval_service


def retrieve(query: str, top_k: int = 5) -> List[RetrievalResult]:
    """Retrieve top-K chunks for a query."""
    service = get_retrieval_service()
    return service.retrieve(query, top_k)


def get_retrieval_stats() -> RetrievalStats:
    """Get retrieval statistics."""
    service = get_retrieval_service()
    return service.get_stats()
