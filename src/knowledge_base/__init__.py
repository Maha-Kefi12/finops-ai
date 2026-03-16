"""
Knowledge Base Module
=====================

Centralized storage for AWS FinOps best practices, cost optimization patterns,
and domain knowledge used for LLM context enrichment.
"""

from src.knowledge_base.aws_finops_best_practices import (
    COMPUTE_BEST_PRACTICES,
    DATABASE_BEST_PRACTICES,
    STORAGE_BEST_PRACTICES,
    NETWORKING_BEST_PRACTICES,
    get_best_practices_for_service,
    get_all_best_practices_text,
)

__all__ = [
    "COMPUTE_BEST_PRACTICES",
    "DATABASE_BEST_PRACTICES",
    "STORAGE_BEST_PRACTICES",
    "NETWORKING_BEST_PRACTICES",
    "get_best_practices_for_service",
    "get_all_best_practices_text",
]
