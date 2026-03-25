"""Pydantic schemas for validating persisted ingestion and recommendation payloads."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ServiceSchema(BaseModel):
    id: str
    name: str
    type: str = "service"
    environment: str = "production"
    owner: str = ""
    cost_monthly: float = 0.0
    attributes: Dict[str, Any] = Field(default_factory=dict)


class DependencySchema(BaseModel):
    source: str
    target: str
    type: str = "depends_on"
    weight: float = 1.0


class GraphDataSchema(BaseModel):
    metadata: Dict[str, Any] = Field(default_factory=dict)
    services: List[ServiceSchema] = Field(default_factory=list)
    dependencies: List[DependencySchema] = Field(default_factory=list)
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)


class RecommendationCardSchema(BaseModel):
    """Schema for recommendation cards — accepts all engine + LLM fields."""
    priority: Optional[Any] = None
    recommendation_number: Optional[int] = None
    title: str = ""
    category: Optional[str] = None
    severity: Optional[str] = None
    total_estimated_savings: float = 0.0
    resource_identification: Dict[str, Any] = Field(default_factory=dict)
    cost_breakdown: Dict[str, Any] = Field(default_factory=dict)
    recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    raw_analysis: Optional[str] = None
    # ── Engine fields (graph RAG enriched) ──
    service_type: Optional[str] = None
    risk_level: Optional[str] = None
    why_it_matters: Optional[str] = None
    linked_best_practice: Optional[str] = None
    pattern_id: Optional[str] = None
    graph_context: Dict[str, Any] = Field(default_factory=dict)
    implementation: List[Dict[str, Any]] = Field(default_factory=list)
    source: Optional[str] = None  # "engine" or "llm"

    class Config:
        extra = "allow"  # Allow any additional fields to pass through


class RecommendationPayloadSchema(BaseModel):
    recommendations: List[RecommendationCardSchema] = Field(default_factory=list)
    total_estimated_savings: float = 0.0
    llm_used: bool = False
    generation_time_ms: int = 0
    architecture_name: str = ""
    context_package: Optional[Dict[str, Any]] = None
    deduplicated_existing_count: int = 0


class LLMReportPayloadSchema(BaseModel):
    health_score: Optional[float] = None
    assessment: Optional[str] = None
    cost_optimization: List[Any] = Field(default_factory=list)
    reliability_risks: List[Any] = Field(default_factory=list)
    recommendations: List[Any] = Field(default_factory=list)
    agents: Dict[str, Any] = Field(default_factory=dict)
    all_findings: List[Any] = Field(default_factory=list)
    interesting_nodes: List[Any] = Field(default_factory=list)


def model_to_dict(model_cls: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize payload for both Pydantic v1 and v2."""
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(payload).model_dump()
    return model_cls.parse_obj(payload).dict()
