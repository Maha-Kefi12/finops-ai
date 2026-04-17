"""
Phase 6: Monitoring and Optimization

1. Incremental indexing: Detect new/modified files in /docs
2. Relevance tuning: Admin API to adjust relevance_boost
3. Performance monitoring: Query latency, cache hit rate, top queries
4. Dashboard integration: Add metrics to monitoring
"""

import logging
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict

from sqlalchemy.orm import Session
from sqlalchemy import and_

from src.storage.database import SessionLocal
from src.graph.models import DocChunk, ChunkIndexingStats
from src.rag.document_chunker import chunk_document
from src.rag.embeddings import TFIDFEmbedder
from src.rag.retrieval_service import get_retrieval_service

logger = logging.getLogger(__name__)


@dataclass
class FileModification:
    """Track file modifications for incremental indexing."""
    file_path: str
    status: str  # 'new' | 'modified' | 'unchanged'
    last_hash: str  # MD5 of file contents
    indexed_at: datetime


class FileHashStore:
    """Track file hashes for change detection."""
    
    def __init__(self):
        self.hashes: Dict[str, Tuple[str, datetime]] = {}  # file_path -> (hash, timestamp)
    
    def _compute_file_hash(self, file_path: str) -> str:
        """Compute MD5 hash of file contents."""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.warning(f"Failed to compute hash for {file_path}: {e}")
            return None
    
    def load_from_db(self, db: Session) -> None:
        """Load file hashes from database metadata."""
        try:
            chunks = db.query(DocChunk.source_file, DocChunk.indexed_at).distinct().all()
            
            docs_dir = '/home/finops/finops-ai-system/docs'
            
            for source_file, indexed_at in chunks:
                # Find full path
                file_path = Path(docs_dir) / source_file
                if file_path.exists():
                    file_hash = self._compute_file_hash(str(file_path))
                    if file_hash:
                        self.hashes[str(file_path)] = (file_hash, indexed_at)
            
            logger.info(f"Loaded {len(self.hashes)} file hashes from database")
        
        except Exception as e:
            logger.warning(f"Failed to load file hashes: {e}")
    
    def get_status(self, file_path: str) -> str:
        """Check if file is new, modified, or unchanged."""
        if file_path not in self.hashes:
            return 'new'
        
        current_hash = self._compute_file_hash(file_path)
        stored_hash, stored_time = self.hashes[file_path]
        
        if current_hash == stored_hash:
            return 'unchanged'
        else:
            return 'modified'


class IncrementalIndexer:
    """Detect and index new/modified documents."""
    
    DOCS_DIR = '/home/finops/finops-ai-system/docs'
    
    def __init__(self):
        self.file_hash_store = FileHashStore()
    
    def detect_new_documents(self) -> List[str]:
        """Detect new documents in /docs."""
        db = SessionLocal()
        try:
            self.file_hash_store.load_from_db(db)
            
            docs_path = Path(self.DOCS_DIR)
            files = []
            for ext in ['*.md', '*.pdf']:
                files.extend(docs_path.rglob(ext))
            
            new_files = []
            for file_path in files:
                file_str = str(file_path)
                status = self.file_hash_store.get_status(file_str)
                if status in ['new', 'modified']:
                    new_files.append(file_str)
            
            logger.info(f"Found {len(new_files)} new/modified documents")
            return new_files
        
        finally:
            db.close()
    
    def index_incremental(self) -> Dict[str, Any]:
        """Run incremental indexing."""
        new_files = self.detect_new_documents()
        
        if not new_files:
            logger.info("No new/modified documents found")
            return {
                'new_files': [],
                'chunks_added': 0,
                'duplicates_skipped': 0,
                'status': 'no_changes',
            }
        
        logger.info(f"Indexing {len(new_files)} new/modified files...")
        
        db = SessionLocal()
        try:
            # Get existing hashes
            existing_hashes = {row[0] for row in db.query(DocChunk.content_hash).all()}
            
            # Chunk new files
            all_chunks = []
            failed_files = []
            
            for file_path in new_files:
                try:
                    chunks = chunk_document(file_path)
                    if chunks:
                        all_chunks.extend(chunks)
                    else:
                        logger.warning(f"No chunks from {file_path}")
                except Exception as e:
                    logger.error(f"Failed to chunk {file_path}: {e}")
                    failed_files.append(file_path)
            
            if not all_chunks:
                logger.warning("No chunks generated from new files")
                return {
                    'new_files': new_files,
                    'chunks_added': 0,
                    'duplicates_skipped': 0,
                    'failed_files': failed_files,
                    'status': 'no_chunks',
                }
            
            # Initialize embedder
            embedder = TFIDFEmbedder()
            chunk_texts = [chunk.text for chunk in all_chunks]
            
            # Fit on combined corpus (existing + new)
            existing_texts = [chunk[0] for chunk in db.query(DocChunk.chunk_text).all()]
            all_texts = existing_texts + chunk_texts
            embedder.fit(all_texts)
            
            # Insert new chunks
            chunks_added = 0
            duplicates_skipped = 0
            
            for chunk in all_chunks:
                if chunk.content_hash in existing_hashes:
                    duplicates_skipped += 1
                    continue
                
                embedding = embedder.transform(chunk.text)
                
                doc_chunk = DocChunk(
                    chunk_text=chunk.text,
                    chunk_number=chunk.chunk_number,
                    source_file=chunk.source_file,
                    source_type=chunk.source_type,
                    section_hierarchy=chunk.section_hierarchy,
                    embedding=embedding,
                    embedding_model='tfidf',
                    chunk_size_chars=chunk.chunk_size_chars,
                    content_hash=chunk.content_hash,
                    indexed_at=datetime.utcnow(),
                    metadata_json={'incremental_index': True},
                )
                db.add(doc_chunk)
                chunks_added += 1
            
            db.commit()
            
            logger.info(f"Incremental indexing complete: {chunks_added} chunks added, "
                       f"{duplicates_skipped} duplicates skipped")
            
            return {
                'new_files': new_files,
                'chunks_added': chunks_added,
                'duplicates_skipped': duplicates_skipped,
                'failed_files': failed_files,
                'status': 'success',
            }
        
        except Exception as e:
            logger.error(f"Incremental indexing failed: {e}", exc_info=True)
            db.rollback()
            return {
                'new_files': new_files,
                'chunks_added': 0,
                'duplicates_skipped': 0,
                'status': 'failed',
                'error': str(e),
            }
        
        finally:
            db.close()


class RelevanceTuner:
    """Tune relevance scores for chunks."""
    
    @staticmethod
    def update_relevance_boost(chunk_id: str, boost: float) -> bool:
        """Update relevance boost for a chunk."""
        db = SessionLocal()
        try:
            chunk = db.query(DocChunk).filter(DocChunk.id == chunk_id).first()
            if not chunk:
                logger.warning(f"Chunk not found: {chunk_id}")
                return False
            
            chunk.relevance_boost = boost
            db.commit()
            logger.info(f"Updated relevance boost for {chunk_id} to {boost}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to update relevance boost: {e}")
            db.rollback()
            return False
        
        finally:
            db.close()
    
    @staticmethod
    def update_relevance_by_source(source_file: str, boost: float) -> int:
        """Update relevance boost for all chunks from a source."""
        db = SessionLocal()
        try:
            count = db.query(DocChunk).filter(
                DocChunk.source_file == source_file
            ).update({'relevance_boost': boost})
            db.commit()
            logger.info(f"Updated {count} chunks from {source_file} to boost={boost}")
            return count
        
        except Exception as e:
            logger.error(f"Failed to update relevance boost: {e}")
            db.rollback()
            return 0
        
        finally:
            db.close()


class PerformanceMonitor:
    """Monitor retrieval performance."""
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics."""
        db = SessionLocal()
        try:
            # Get retrieval statistics
            retrieval_service = get_retrieval_service()
            stats = retrieval_service.get_stats()
            
            # Get chunk statistics
            total_chunks = db.query(DocChunk).filter(
                DocChunk.is_active == True
            ).count()
            
            total_sources = db.query(DocChunk.source_file).distinct().count()
            
            # Get top retrieved chunks
            top_chunks = db.query(
                DocChunk.source_file,
                DocChunk.retrieval_count
            ).filter(
                DocChunk.is_active == True,
                DocChunk.retrieval_count > 0
            ).order_by(
                DocChunk.retrieval_count.desc()
            ).limit(10).all()
            
            # Get recent indexing runs
            recent_runs = db.query(ChunkIndexingStats).order_by(
                ChunkIndexingStats.run_date.desc()
            ).limit(5).all()
            
            return {
                'retrieval': {
                    'total_queries': stats.total_queries,
                    'cache_hits': stats.cache_hits,
                    'cache_misses': stats.cache_misses,
                    'hit_rate_percent': (
                        100.0 * stats.cache_hits / (stats.cache_hits + stats.cache_misses)
                        if (stats.cache_hits + stats.cache_misses) > 0 else 0
                    ),
                    'avg_latency_ms': round(stats.avg_latency_ms, 2),
                    'top_queries': stats.top_queries,
                },
                'indexing': {
                    'total_chunks': total_chunks,
                    'total_sources': total_sources,
                    'top_retrieved_chunks': [
                        {'source': source, 'count': count}
                        for source, count in top_chunks
                    ],
                    'recent_runs': [
                        {
                            'run_date': run.run_date.isoformat(),
                            'mode': run.indexing_mode,
                            'chunks_created': run.total_chunks_created,
                            'chunks_stored': run.total_chunks_stored,
                            'status': run.status,
                        }
                        for run in recent_runs
                    ],
                },
                'timestamp': datetime.utcnow().isoformat(),
            }
        
        finally:
            db.close()


# Public API functions
def detect_new_documents() -> List[str]:
    """Detect new/modified documents."""
    indexer = IncrementalIndexer()
    return indexer.detect_new_documents()


def index_incremental() -> Dict[str, Any]:
    """Run incremental indexing."""
    indexer = IncrementalIndexer()
    return indexer.index_incremental()


def update_relevance_boost(chunk_id: str, boost: float) -> bool:
    """Update relevance boost for a chunk."""
    return RelevanceTuner.update_relevance_boost(chunk_id, boost)


def update_relevance_by_source(source_file: str, boost: float) -> int:
    """Update relevance boost for all chunks from a source."""
    return RelevanceTuner.update_relevance_by_source(source_file, boost)


def get_performance_metrics() -> Dict[str, Any]:
    """Get performance metrics."""
    monitor = PerformanceMonitor()
    return monitor.get_performance_metrics()
