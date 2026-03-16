"""
SQLAlchemy ORM models for graph persistence.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
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
    """Stored recommendation run for an architecture. Enables retry and loading last result."""
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
