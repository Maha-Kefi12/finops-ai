"""
Phase 1: Vector DB setup script.

Installs pgvector extension, creates doc_chunks and chunk_indexing_stats tables,
initializes indexes for optimal retrieval performance.

Usage:
    python -m src.rag.setup_vectordb [--reset] [--verbose]

Flags:
    --reset: Drop existing tables and rebuild (caution: destructive)
    --verbose: Show detailed setup progress
"""
import os
import sys
import logging
import argparse
from datetime import datetime
from sqlalchemy import text, inspect
from src.storage.database import engine, Base, SessionLocal
from src.graph.models import DocChunk, ChunkIndexingStats

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def enable_pgvector_extension():
    """Install pgvector extension in PostgreSQL."""
    logger.info("Checking pgvector extension...")
    
    with engine.connect() as conn:
        # Check if extension exists
        result = conn.execute(
            text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='vector')")
        )
        extension_exists = result.scalar()
        
        if extension_exists:
            logger.info("✓ pgvector extension already installed")
            conn.commit()
            return
        
        # Try to create extension
        logger.info("Installing pgvector extension...")
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
            logger.info("✓ pgvector extension installed successfully")
        except Exception as e:
            logger.error(f"✗ Failed to install pgvector extension: {e}")
            logger.error("TROUBLESHOOTING:")
            logger.error("  1. Verify PostgreSQL version >= 12")
            logger.error("  2. Install pgvector extension on the PostgreSQL server:")
            logger.error("     - Ubuntu/Debian: sudo apt-get install postgresql-contrib")
            logger.error("     - Or manually: CREATE EXTENSION vector;")
            logger.error("  3. Check database connection string in DATABASE_URL")
            raise


def create_vectordb_tables(reset=False):
    """Create doc_chunks and chunk_indexing_stats tables."""
    logger.info("Creating Vector DB tables...")
    
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    if reset:
        logger.warning("Reset flag set - dropping existing tables...")
        for table_name in ["doc_chunks", "chunk_indexing_stats"]:
            if table_name in existing_tables:
                with engine.connect() as conn:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
                    conn.commit()
                logger.info(f"  ✓ Dropped table: {table_name}")
    
    # Create all Vector DB models
    Base.metadata.create_all(bind=engine, tables=[
        DocChunk.__table__,
        ChunkIndexingStats.__table__
    ])
    
    logger.info("✓ Vector DB tables created successfully")


def verify_vectordb_setup():
    """Verify that Vector DB is properly configured."""
    logger.info("Verifying Vector DB setup...")
    
    with engine.connect() as conn:
        # Check for pgvector extension
        result = conn.execute(
            text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='vector')")
        )
        has_vector = result.scalar()
        if not has_vector:
            logger.warning("⚠ pgvector extension not found")
            return False
        logger.info("  ✓ pgvector extension active")
        
        # Check for tables
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        for table_name in ["doc_chunks", "chunk_indexing_stats"]:
            if table_name not in existing_tables:
                logger.error(f"✗ Table missing: {table_name}")
                return False
            logger.info(f"  ✓ Table exists: {table_name}")
        
        # Check for vector index
        try:
            result = conn.execute(
                text("""
                SELECT COUNT(*)
                FROM pg_indexes
                WHERE tablename = 'doc_chunks' AND indexname LIKE '%vector%'
                """)
            )
            index_count = result.scalar()
            if index_count > 0:
                logger.info(f"  ✓ Vector index found ({index_count} indexes)")
            else:
                logger.warning("⚠ No vector indexes found (retrieval may be slow)")
        except Exception as e:
            logger.warning(f"⚠ Could not verify indexes: {e}")
    
    logger.info("✓ Vector DB verification complete")
    return True


def log_setup_summary():
    """Log a summary of the setup."""
    logger.info("\n" + "="*60)
    logger.info("VECTOR DB SETUP COMPLETE")
    logger.info("="*60)
    logger.info("\nDatabase Tables Created:")
    logger.info("  • doc_chunks (stores chunks + embeddings)")
    logger.info("  • chunk_indexing_stats (tracks indexing runs)")
    logger.info("\nNext Steps (Phase 2-3):")
    logger.info("  1. Run document chunking: python -m src.rag.document_chunker")
    logger.info("  2. Run indexing pipeline: python -m src.rag.indexing_pipeline")
    logger.info("  3. Verify chunks stored: SELECT COUNT(*) FROM doc_chunks;")
    logger.info("\nPerformance Targets:")
    logger.info("  • Query latency: < 100ms (cold), < 5ms (warm)")
    logger.info("  • Cache hit rate: > 80%")
    logger.info("  • Indexing speed: 5,000 chunks/min")
    logger.info("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Vector DB Phase 1 Setup: Install pgvector, create tables"
    )
    parser.add_argument("--reset", action="store_true", help="Drop and recreate tables")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    try:
        logger.info("Starting Vector DB Phase 1 Setup...")
        logger.info(f"Database: {os.getenv('DATABASE_URL', 'postgresql://...')[:50]}...")
        
        # Step 1: Enable pgvector extension
        enable_pgvector_extension()
        
        # Step 2: Create tables
        create_vectordb_tables(reset=args.reset)
        
        # Step 3: Verify setup
        if not verify_vectordb_setup():
            logger.error("Setup verification failed!")
            return 1
        
        # Step 4: Log summary
        log_setup_summary()
        
        logger.info("✅ Phase 1 Setup Successful!")
        return 0
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
