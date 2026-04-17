"""
SQLAlchemy ORM models for graph persistence.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, JSON, Text, Index, Boolean
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from src.storage.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class Architecture(Base):
    __tablename__ = "architectures"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    pattern = Column(String(100), nullable=False)
    complexity = Column(String(50), nullable=False)
    environment = Column(String(50), default="production")
    region = Column(String(50), default="us-east-1")
    total_services = Column(Integer, default=0)
    total_cost_monthly = Column(Float, default=0.0)
    source_file = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    metadata_json = Column(JSON, nullable=True)

    services = relationship("Service", back_populates="architecture", cascade="all, delete-orphan")
    dependencies = relationship("Dependency", back_populates="architecture", cascade="all, delete-orphan")


class Service(Base):
    __tablename__ = "services"

    id = Column(String, primary_key=True)
    architecture_id = Column(String, ForeignKey("architectures.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    service_type = Column(String(100), nullable=False)
    environment = Column(String(50), default="production")
    owner = Column(String(255), nullable=True)
    cost_monthly = Column(Float, default=0.0)
    attributes = Column(JSON, nullable=True)
    # Graph metrics (computed)
    degree_centrality = Column(Float, default=0.0)
    betweenness_centrality = Column(Float, default=0.0)
    in_degree = Column(Integer, default=0)
    out_degree = Column(Integer, default=0)

    architecture = relationship("Architecture", back_populates="services")


class Dependency(Base):
    __tablename__ = "dependencies"

    id = Column(String, primary_key=True, default=generate_uuid)
    architecture_id = Column(String, ForeignKey("architectures.id", ondelete="CASCADE"), nullable=False)
    source = Column(String, ForeignKey("services.id"), nullable=False)
    target = Column(String, ForeignKey("services.id"), nullable=False)
    dep_type = Column(String(100), nullable=False)
    weight = Column(Float, default=1.0)

    architecture = relationship("Architecture", back_populates="dependencies")


class IngestionSnapshot(Base):
    __tablename__ = "ingestion_snapshots"
    __table_args__ = {"extend_existing": True}

    id = Column(String, primary_key=True, default=generate_uuid)
    account_id = Column(String, nullable=True)
    architecture_id = Column(String, nullable=True)
    source = Column(String, nullable=False, default="file")
    status = Column(String, nullable=False, default="pending")
    pipeline_stage = Column(String, nullable=True)
    pipeline_detail = Column(String, nullable=True)
    region = Column(String, nullable=True)
    total_services = Column(Integer, nullable=True, default=0)
    total_cost_monthly = Column(Float, nullable=True, default=0.0)
    duration_seconds = Column(Float, nullable=True, default=0.0)
    error_message = Column(String, nullable=True)
    raw_data = Column(JSON, nullable=True)
    llm_report = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RecommendationResult(Base):
    """Legacy — kept for import compat. Replaced by RecSnapshot."""
    __tablename__ = "recommendation_results"
    __table_args__ = {"extend_existing": True}

    id = Column(String, primary_key=True, default=generate_uuid)
    architecture_id = Column(String, nullable=False, index=True)
    architecture_file = Column(String, nullable=True)
    status = Column(String, nullable=False, default="completed")
    error_message = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)
    generation_time_ms = Column(Integer, nullable=True)
    total_estimated_savings = Column(Float, nullable=True, default=0.0)
    card_count = Column(Integer, nullable=True, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class RecSnapshot(Base):
    """One recommendation run snapshot — stores every engine+LLM run for history.

    Columns are straight-to-the-point, queryable, and indexed for performance.
    The heavy `cards` JSONB is only fetched when loading a specific snapshot.
    """
    __tablename__ = "rec_snapshots"
    __table_args__ = (
        Index("ix_rec_snap_arch_created", "architecture_id", "created_at"),
        {"extend_existing": True},
    )

    id                  = Column(String, primary_key=True, default=generate_uuid)
    architecture_id     = Column(String, nullable=False, index=True)
    architecture_name   = Column(String(255), nullable=True)
    status              = Column(String(20), nullable=False, default="completed")  # completed | failed
    source              = Column(String(20), nullable=False, default="both")       # engine | llm | both
    card_count          = Column(Integer, nullable=False, default=0)
    engine_card_count   = Column(Integer, nullable=False, default=0)
    llm_card_count      = Column(Integer, nullable=False, default=0)
    total_savings_monthly = Column(Float, nullable=False, default=0.0)
    generation_time_ms  = Column(Integer, nullable=True)
    llm_model           = Column(String(100), nullable=True)                       # e.g. gpt-4o-mini
    cards               = Column(JSON, nullable=True)                              # full card array
    error_message       = Column(Text, nullable=True)
    created_at          = Column(DateTime, nullable=False, default=datetime.utcnow)


class LLMReport(Base):
    """Stored LLM report from 5-agent AI pipeline analysis."""
    __tablename__ = "llm_reports"
    __table_args__ = {"extend_existing": True}

    id = Column(String, primary_key=True, default=generate_uuid)
    architecture_id = Column(String, nullable=False, index=True)
    architecture_file = Column(String, nullable=True)
    status = Column(String, nullable=False, default="completed")
    error_message = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)
    generation_time_ms = Column(Integer, nullable=True)
    agent_names = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DocChunk(Base):
    """Document chunks from /docs for RAG retrieval.
    
    One-time chunked from MD/PDF files, stored persistently in PostgreSQL with pgvector embeddings.
    Supports rapid semantic search and context injection into LLM/engine pipelines.
    """
    __tablename__ = "doc_chunks"
    __table_args__ = (
        Index("ix_doc_chunks_vector", "embedding", postgresql_using="ivfflat"),
        Index("ix_doc_chunks_hash", "content_hash"),
        Index("ix_doc_chunks_active", "is_active"),
        Index("ix_doc_chunks_source", "source_file"),
        Index("ix_doc_chunks_last_retrieved", "last_retrieved"),
        {"extend_existing": True},
    )

    id                  = Column(String, primary_key=True, default=generate_uuid)
    chunk_text          = Column(Text, nullable=False)
    chunk_number        = Column(Integer, nullable=True)
    source_file         = Column(String(255), nullable=False, index=True)
    source_type         = Column(String(20), nullable=False)          # 'markdown' | 'pdf'
    section_hierarchy   = Column(String(500), nullable=True)          # Breadcrumb path (MD header hierarchy)
    embedding           = Column(Vector(128), nullable=False)         # TF-IDF embeddings (128 dims)
    embedding_model     = Column(String(50), nullable=True)           # 'tfidf' | 'other'
    chunk_size_chars    = Column(Integer, nullable=True)
    content_hash        = Column(String(64), nullable=False, unique=True)  # SHA-256 for deduplication
    indexed_at          = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_retrieved      = Column(DateTime, nullable=True)
    retrieval_count     = Column(Integer, nullable=False, default=0)
    relevance_boost     = Column(Float, nullable=False, default=1.0)  # Manual tuning factor
    is_active           = Column(Boolean, nullable=False, default=True)
    metadata_json       = Column(JSON, nullable=True)                 # Extra context


class ChunkIndexingStats(Base):
    """Tracking for document indexing runs (one-time + incremental).
    
    Monitor progress, detect issues, and validate data quality.
    """
    __tablename__ = "chunk_indexing_stats"
    __table_args__ = (
        Index("ix_indexing_stats_run_date", "run_date"),
        {"extend_existing": True},
    )

    id                      = Column(Integer, primary_key=True, autoincrement=True)
    run_date                = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    indexing_mode           = Column(String(50), nullable=False)      # 'full' | 'incremental'
    total_files_processed   = Column(Integer, nullable=False, default=0)
    total_files_indexed     = Column(Integer, nullable=False, default=0)
    total_chunks_created    = Column(Integer, nullable=False, default=0)
    total_chunks_stored     = Column(Integer, nullable=False, default=0)
    duplicate_chunks_skipped = Column(Integer, nullable=False, default=0)
    failed_files            = Column(JSON, nullable=True)             # Array of {filename, error}
    total_embedding_time_seconds = Column(Float, nullable=True)
    total_indexing_duration_seconds = Column(Float, nullable=True)
    status                  = Column(String(50), nullable=False)      # 'success' | 'partial' | 'failed'
    error_message           = Column(Text, nullable=True)
    completion_time         = Column(DateTime, nullable=True)
