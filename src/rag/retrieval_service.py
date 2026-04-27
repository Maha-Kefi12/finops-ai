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
        """Initialize embedder from the persisted vocabulary file.

        CRITICAL: We MUST load the same vocabulary that was used at index time.
        Re-fitting on the DB chunks would produce a different vocabulary ordering,
        making stored vectors and query vectors incomparable (all scores ~= 0).
        """
        import os
        vocab_path = os.path.join(os.path.dirname(__file__), "tfidf_vocab.json")

        if os.path.exists(vocab_path):
            try:
                self.embedder = TFIDFEmbedder.load(vocab_path)
                logger.info(
                    "[RETRIEVAL] Loaded persisted vocabulary: %d tokens from %s",
                    self.embedder.vocab_size, vocab_path
                )
                return
            except Exception as e:
                logger.warning("[RETRIEVAL] Failed to load vocabulary file: %s — falling back to re-fit", e)

        # Fallback: re-fit on all stored chunks (less accurate but functional)
        logger.warning(
            "[RETRIEVAL] No vocabulary file found at %s. "
            "Run the indexing pipeline first to generate it.",
            vocab_path
        )
        db = SessionLocal()
        try:
            chunk_texts = [row[0] for row in db.query(DocChunk.chunk_text).limit(5000).all()]
            if not chunk_texts:
                logger.warning("[RETRIEVAL] No chunks in database — embedder not initialized")
                return
            logger.info("[RETRIEVAL] Re-fitting embedder on %d chunks (vocabulary may differ from index time)", len(chunk_texts))
            self.embedder = TFIDFEmbedder()
            self.embedder.fit(chunk_texts)
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
        """Retrieve top-K chunks using pgvector native cosine search.

        Changes from the previous implementation:
        - Uses pgvector <=> operator (cosine distance) directly in SQL
          instead of loading all 27k chunks into Python memory.
        - Adds source diversification: results are spread across at least
          min(n_sources, 3) different PDFs so the LLM gets a broader
          knowledge base (not just 5 chunks from the same document).
        """
        start_time = time.time()

        # Cache check
        if self.cache_enabled and self.cache:
            cached = self.cache.get(query, top_k)
            if cached:
                latency_ms = (time.time() - start_time) * 1000
                self.latencies.append(latency_ms)
                logger.info("[RETRIEVAL] Cache hit: %d chunks in %.1fms", len(cached), latency_ms)
                return cached

        self._ensure_embedder()
        if not self.embedder:
            logger.error("[RETRIEVAL] Embedder not available")
            return []

        # Embed the query into the SAME vector space as the stored chunks
        query_vec = self.embedder.transform(query)
        # pgvector expects the vector as a string literal: '[0.1,0.2,...]'
        vec_str = "[" + ",".join(f"{v:.6f}" for v in query_vec) + "]"

        db = SessionLocal()
        try:
            # ── Phase 1: Retrieve top (top_k * 6) candidates via pgvector ──
            # Multiplying by 6 gives the diversity pass enough candidates to
            # spread across multiple source files without losing quality.
            candidate_limit = top_k * 6
            sql = text("""
                SELECT
                    id, chunk_text, source_file, source_type,
                    section_hierarchy, retrieval_count, relevance_boost,
                    indexed_at,
                    1 - (embedding <=> CAST(:vec AS vector)) AS cosine_similarity
                FROM doc_chunks
                WHERE is_active = true
                ORDER BY embedding <=> CAST(:vec AS vector)
                LIMIT :lim
            """)
            rows = db.execute(sql, {"vec": vec_str, "lim": candidate_limit}).fetchall()

            if not rows:
                logger.warning("[RETRIEVAL] pgvector returned 0 candidates for query")
                return []

            # ── Phase 2: Source diversification ──
            # Greedily pick the best chunk per source file first,
            # then fill remaining slots with the next-best overall.
            seen_sources: Dict[str, int] = {}   # source_file -> count selected
            max_per_source = max(1, top_k // 3)  # at most 1/3 of results from same doc
            selected = []
            remainder = []

            for row in rows:
                src = row.source_file
                if seen_sources.get(src, 0) < max_per_source:
                    selected.append(row)
                    seen_sources[src] = seen_sources.get(src, 0) + 1
                    if len(selected) >= top_k:
                        break
                else:
                    remainder.append(row)

            # Fill missing slots from remainder (different sources exhausted)
            for row in remainder:
                if len(selected) >= top_k:
                    break
                selected.append(row)

            # ── Phase 3: Build results + update retrieval counts ──
            results = []
            ids_to_update = []
            for row in selected:
                results.append(RetrievalResult(
                    chunk_id=row.id,
                    text=row.chunk_text,
                    source_file=row.source_file,
                    source_type=row.source_type,
                    section_hierarchy=row.section_hierarchy,
                    score=float(row.cosine_similarity),
                    relevance_score=float(row.cosine_similarity),
                    retrieved_at=datetime.utcnow(),
                ))
                ids_to_update.append(row.id)

            if ids_to_update:
                db.execute(
                    text("""
                        UPDATE doc_chunks
                        SET retrieval_count = retrieval_count + 1,
                            last_retrieved  = NOW()
                        WHERE id = ANY(:ids)
                    """),
                    {"ids": ids_to_update},
                )
                db.commit()

            # Cache the results
            if self.cache_enabled and self.cache:
                self.cache.set(query, top_k, results)

            latency_ms = (time.time() - start_time) * 1000
            self.latencies.append(latency_ms)

            sources_used = list(seen_sources.keys())
            logger.info(
                "[RETRIEVAL] %d chunks from %d sources in %.1fms: %s",
                len(results), len(sources_used), latency_ms,
                ", ".join(sources_used)
            )
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
