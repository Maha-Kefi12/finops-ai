"""
Phase 3: Indexing Pipeline

Full document processing from /docs:
1. Scan /docs for .md and .pdf files
2. Chunk each document
3. Generate TF-IDF embeddings
4. Check for duplicates via content_hash
5. Batch insert into doc_chunks table
6. Track stats in chunk_indexing_stats
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.storage.database import engine, SessionLocal
from src.graph.models import DocChunk, ChunkIndexingStats
from src.rag.document_chunker import chunk_document
from src.rag.embeddings import TFIDFEmbedder

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IndexingStats:
    """Statistics for an indexing run."""
    
    def __init__(self):
        self.total_files_found = 0
        self.total_files_processed = 0
        self.total_files_indexed = 0
        self.total_chunks_created = 0
        self.total_chunks_stored = 0
        self.duplicate_chunks_skipped = 0
        self.failed_files = []
        self.start_time = None
        self.end_time = None
        self.total_embedding_time_seconds = 0.0
        self.status = 'pending'
    
    def duration_seconds(self) -> float:
        """Get duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'total_files_found': self.total_files_found,
            'total_files_processed': self.total_files_processed,
            'total_files_indexed': self.total_files_indexed,
            'total_chunks_created': self.total_chunks_created,
            'total_chunks_stored': self.total_chunks_stored,
            'duplicate_chunks_skipped': self.duplicate_chunks_skipped,
            'failed_files': self.failed_files,
            'total_embedding_time_seconds': self.total_embedding_time_seconds,
            'total_indexing_duration_seconds': self.duration_seconds(),
            'status': self.status,
        }


class DocumentIndexer:
    """Indexes documents into the vector database."""
    
    DOCS_DIR = '/app/docs' if os.path.isdir('/app/docs') else '/home/finops/finops-ai-system/docs'
    BATCH_SIZE = 200
    
    def __init__(self, mode: str = 'full', verbose: bool = False):
        self.mode = mode
        self.verbose = verbose
        self.stats = IndexingStats()
        self.embedder = None
        self.existing_hashes = set()
    
    def scan_documents(self) -> List[str]:
        """Scan /docs for all .md and .pdf files."""
        docs_path = Path(self.DOCS_DIR)
        
        if not docs_path.exists():
            logger.error(f"Docs directory not found: {self.DOCS_DIR}")
            return []
        
        files = []
        for ext in ['*.md', '*.pdf']:
            files.extend(docs_path.rglob(ext))
        
        # Convert to string paths and sort
        file_paths = sorted([str(f) for f in files])
        self.stats.total_files_found = len(file_paths)
        
        logger.info(f"Found {len(file_paths)} documents to index")
        return file_paths
    
    def load_existing_hashes(self, db: Session) -> None:
        """Load existing content hashes to detect duplicates."""
        try:
            result = db.query(DocChunk.content_hash).all()
            self.existing_hashes = {row[0] for row in result}
            logger.info(f"Loaded {len(self.existing_hashes)} existing content hashes")
        except Exception as e:
            logger.warning(f"Failed to load existing hashes: {e}")
    
    def init_embedder(self, all_chunks: List) -> None:
        """Initialize TF-IDF embedder by fitting on all chunk texts."""
        chunk_texts = [chunk.text for chunk in all_chunks]
        
        logger.info(f"Initializing TF-IDF embedder with {len(chunk_texts)} chunks...")
        self.embedder = TFIDFEmbedder()
        self.embedder.fit(chunk_texts)
        
        logger.info(f"TF-IDF embedder ready: vocab_size={self.embedder.vocab_size}")
    
    def get_embeddings(self, chunks: List) -> List[List[float]]:
        """Generate embeddings for chunks."""
        if not self.embedder:
            raise RuntimeError("Embedder not initialized")
        
        embeddings = self.embedder.batch_transform([chunk.text for chunk in chunks])
        return embeddings
    
    def index_documents(self, mode: str = 'incremental') -> IndexingStats:
        """Index all documents.

        Args:
            mode: 'incremental' (default) — skip chunks that already exist (by content_hash).
                  'full' — re-index everything (drops existing chunks first).
        """
        self.stats.start_time = datetime.utcnow()
        
        try:
            # Step 1: Scan documents
            file_paths = self.scan_documents()
            if not file_paths:
                logger.error("No documents found")
                self.stats.status = 'failed'
                self.stats.end_time = datetime.utcnow()
                return self.stats
            
            # Step 2: Chunk all documents
            all_chunks = []
            logger.info(f"Chunking {len(file_paths)} documents...")
            for file_path in file_paths:
                try:
                    chunks = chunk_document(file_path)
                    if chunks:
                        all_chunks.extend(chunks)
                        self.stats.total_files_processed += 1
                        self.stats.total_chunks_created += len(chunks)
                    else:
                        logger.warning(f"No chunks generated for {file_path}")
                except Exception as e:
                    logger.error(f"Failed to chunk {file_path}: {e}")
                    self.stats.failed_files.append({
                        'filename': os.path.basename(file_path),
                        'error': str(e)
                    })
            
            if not all_chunks:
                logger.error("No chunks generated from any document")
                self.stats.status = 'failed'
                self.stats.end_time = datetime.utcnow()
                return self.stats
            
            logger.info(f"Total chunks created: {self.stats.total_chunks_created}")
            
            # Step 3: Initialize embedder
            self.init_embedder(all_chunks)

            # ── SANITY CHECK: Verify embedding dimension matches DB schema ──
            actual_dim = self.embedder.vocab_size
            expected_dim = 128  # Must match vector(128) column in doc_chunks
            if actual_dim != expected_dim:
                raise RuntimeError(
                    f"Embedding dimension mismatch: embedder produced {actual_dim} dims "
                    f"but database expects {expected_dim}. "
                    f"Check TFIDFEmbedder.MAX_FEATURES == {expected_dim}."
                )
            logger.info(f"✓ Dimension check passed: {actual_dim} dims == vector({expected_dim})")

            # ── Persist vocabulary so the retrieval service uses the SAME space ──
            # Without this, retrieve() re-fits on a different random sample and
            # produces vectors that are NOT comparable to the stored embeddings.
            vocab_path = os.path.join(os.path.dirname(__file__), "tfidf_vocab.json")
            self.embedder.save(vocab_path)
            logger.info(f"✓ Vocabulary saved to {vocab_path} ({self.embedder.vocab_size} tokens)")

            # Step 4: Insert into database in batches

            db = SessionLocal()
            try:
                # If full mode, purge existing chunks first
                if mode == 'full':
                    deleted = db.execute(text("DELETE FROM doc_chunks")).rowcount
                    db.commit()
                    logger.info(f"[FULL MODE] Purged {deleted} existing chunks from doc_chunks")
                    self.existing_hashes = set()  # Reset — nothing left to deduplicate against
                else:
                    # Incremental: skip already-indexed chunks
                    self.load_existing_hashes(db)
                
                # Process in batches
                total = len(all_chunks)
                stored_in_batch = 0
                skipped_errors = 0

                for i, chunk in enumerate(all_chunks):
                    # Check for duplicates
                    if chunk.content_hash in self.existing_hashes:
                        self.stats.duplicate_chunks_skipped += 1
                        continue

                    try:
                        # Get embedding
                        embedding = self.embedder.transform(chunk.text)

                        # Create DocChunk
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
                            metadata_json={
                                'chunked_at': datetime.utcnow().isoformat(),
                                'chunker_version': '1.1',
                            }
                        )

                        db.add(doc_chunk)
                        stored_in_batch += 1
                        self.stats.total_chunks_stored += 1

                        # Flush every 50 items to keep memory usage manageable
                        if stored_in_batch % 50 == 0:
                            db.flush()

                        # Commit + log progress every BATCH_SIZE items
                        if stored_in_batch % self.BATCH_SIZE == 0:
                            db.commit()
                            pct = round((i + 1) / total * 100, 1)
                            logger.info(
                                f"[INSERT] {self.stats.total_chunks_stored} chunks committed "
                                f"({pct}% of {total} | {skipped_errors} errors skipped)"
                            )

                    except Exception as chunk_err:
                        db.rollback()
                        skipped_errors += 1
                        if skipped_errors <= 10:
                            logger.warning(
                                f"[SKIP] Chunk {i} from {chunk.source_file} skipped: {chunk_err}"
                            )

                # Final commit for remaining items
                try:
                    db.commit()
                    logger.info(
                        f"[INSERT] Final commit: {self.stats.total_chunks_stored} total stored "
                        f"({skipped_errors} skipped)"
                    )
                except Exception as final_err:
                    logger.error(f"[INSERT] Final commit failed: {final_err}")
                    db.rollback()

                self.stats.total_files_indexed = self.stats.total_files_processed
                self.stats.status = 'success'

                logger.info(f"✓ Indexing complete: {self.stats.total_chunks_stored} chunks stored")

            finally:
                db.close()
            
            # Step 5: Record indexing stats
            db = SessionLocal()
            try:
                stats_record = ChunkIndexingStats(
                    run_date=self.stats.start_time,
                    indexing_mode=mode,
                    total_files_processed=self.stats.total_files_processed,
                    total_files_indexed=self.stats.total_files_indexed,
                    total_chunks_created=self.stats.total_chunks_created,
                    total_chunks_stored=self.stats.total_chunks_stored,
                    duplicate_chunks_skipped=self.stats.duplicate_chunks_skipped,
                    failed_files=self.stats.failed_files if self.stats.failed_files else None,
                    total_embedding_time_seconds=self.stats.total_embedding_time_seconds,
                    total_indexing_duration_seconds=self.stats.duration_seconds(),
                    status=self.stats.status,
                    error_message=None,
                    completion_time=datetime.utcnow(),
                )
                db.add(stats_record)
                db.commit()
                logger.info("✓ Indexing stats recorded")
            finally:
                db.close()
        
        except Exception as e:
            logger.error(f"Indexing failed: {e}", exc_info=True)
            self.stats.status = 'failed'
        
        self.stats.end_time = datetime.utcnow()
        return self.stats
    
    def log_summary(self) -> None:
        """Log indexing summary."""
        stats = self.stats.to_dict()
        
        logger.info("\n" + "="*60)
        logger.info("INDEXING PIPELINE COMPLETE")
        logger.info("="*60)
        logger.info(f"Total files found:        {stats['total_files_found']}")
        logger.info(f"Total files processed:    {stats['total_files_processed']}")
        logger.info(f"Total files indexed:      {stats['total_files_indexed']}")
        logger.info(f"Total chunks created:     {stats['total_chunks_created']}")
        logger.info(f"Total chunks stored:      {stats['total_chunks_stored']}")
        logger.info(f"Duplicate chunks skipped: {stats['duplicate_chunks_skipped']}")
        logger.info(f"Duration:                 {stats['total_indexing_duration_seconds']:.2f}s")
        logger.info(f"Status:                   {stats['status']}")
        
        if stats['failed_files']:
            logger.warning(f"Failed files ({len(stats['failed_files'])}):")
            for failed in stats['failed_files']:
                logger.warning(f"  - {failed['filename']}: {failed['error']}")
        
        logger.info("="*60 + "\n")


def index_all_documents(mode: str = 'full', verbose: bool = False) -> IndexingStats:
    """Index all documents from /docs."""
    indexer = DocumentIndexer(mode=mode, verbose=verbose)
    stats = indexer.index_documents(mode=mode)
    indexer.log_summary()
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Vector DB Phase 3: Index documents from /docs"
    )
    parser.add_argument(
        "--mode",
        choices=['full', 'incremental'],
        default='full',
        help="Indexing mode: full (re-index all) or incremental (skip existing)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    try:
        logger.info(f"Starting Vector DB Phase 3: Indexing Pipeline (mode={args.mode})...")
        stats = index_all_documents(mode=args.mode, verbose=args.verbose)
        
        if stats.status == 'success':
            logger.info("✅ Indexing Successful!")
            return 0
        else:
            logger.error("❌ Indexing Failed!")
            return 1
    
    except Exception as e:
        logger.error(f"❌ Pipeline failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
