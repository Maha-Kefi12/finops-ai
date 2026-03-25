"""
Recommendation Management API Handlers
======================================
Endpoints for storing, retrieving, and managing recommendations through history
"""

import json
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.storage.database import get_db
from src.graph.models import RecommendationResult
from src.storage.recommendation_cache import get_cache
from src.background.tasks import generate_recommendations_bg, get_task_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


# ─── Get Recommendation History ────────────────────────────────────

class HistoryRequest:
    """Request model for history"""
    architecture_id: Optional[str] = None
    architecture_file: Optional[str] = None
    limit: int = 50


@router.get("/history")
async def get_recommendation_history(
    architecture_id: Optional[str] = None,
    architecture_file: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    Get recommendation history from database and cache
    
    Returns last N recommendation runs sorted by timestamp (newest first)
    Includes: status, card count, total savings, generation time, timestamp
    """
    if not architecture_id and not architecture_file:
        raise HTTPException(400, "Provide architecture_id or architecture_file")
    
    try:
        # Try cache first
        cache = get_cache()
        cache_id = architecture_id or architecture_file
        cached_history = cache.get_history(cache_id, limit)
        
        if cached_history:
            logger.info("Retrieved %d cached history entries", len(cached_history))
            return {
                "source": "cache",
                "history": cached_history,
                "total": len(cached_history),
            }
        
        # Fall back to database
        query = db.query(RecommendationResult).filter(
            RecommendationResult.status == "completed"
        )
        
        if architecture_id:
            query = query.filter(RecommendationResult.architecture_id == architecture_id)
        else:
            query = query.filter(RecommendationResult.architecture_file == architecture_file)
        
        results = query.order_by(
            RecommendationResult.created_at.desc()
        ).limit(limit).all()
        
        history = [
            {
                "id": str(r.id),
                "timestamp": r.created_at.isoformat() if r.created_at else None,
                "status": r.status,
                "card_count": r.card_count,
                "total_estimated_savings": r.total_estimated_savings,
                "generation_time_ms": r.generation_time_ms,
            }
            for r in results
        ]
        
        logger.info("Retrieved %d DB history entries", len(history))
        return {
            "source": "database",
            "history": history,
            "total": len(history),
        }
        
    except Exception as e:
        logger.error("Failed to get history: %s", e)
        raise HTTPException(500, f"Failed to retrieve history: {str(e)}")


# ─── Get Single Recommendation Result ──────────────────────────────

@router.get("/result/{result_id}")
async def get_recommendation_result(
    result_id: str,
    db: Session = Depends(get_db),
):
    """
    Get full recommendation result by ID
    
    Returns complete cards, context, metrics, etc.
    """
    try:
        result = db.query(RecommendationResult).filter(
            RecommendationResult.id == result_id
        ).first()
        
        if not result:
            raise HTTPException(404, f"Recommendation result not found: {result_id}")
        
        return {
            "id": str(result.id),
            "architecture_id": result.architecture_id,
            "status": result.status,
            "created_at": result.created_at.isoformat() if result.created_at else None,
            "total_estimated_savings": result.total_estimated_savings,
            "generation_time_ms": result.generation_time_ms,
            "card_count": result.card_count,
            "payload": result.payload if isinstance(result.payload, dict) else json.loads(result.payload or "{}"),
        }
        
    except Exception as e:
        logger.error("Failed to get result: %s", e)
        raise HTTPException(500, f"Failed to retrieve result: {str(e)}")


# ─── Start Background Recommendation Generation ─────────────────────

class GenerateRecommendationsRequest:
    """Request to generate recommendations in background"""
    architecture_id: Optional[str] = None
    architecture_file: Optional[str] = None
    use_cache: bool = True


@router.post("/generate-bg")
async def generate_recommendations_background(
    architecture_id: Optional[str] = None,
    architecture_file: Optional[str] = None,
    use_cache: bool = True,
):
    """
    Start background recommendation generation task
    
    Returns task_id for polling status
    Uses cache to return instant results if available and use_cache=True
    """
    if not architecture_id and not architecture_file:
        raise HTTPException(400, "Provide architecture_id or architecture_file")
    
    try:
        cache = get_cache()
        cache_id = architecture_id or architecture_file
        
        # Check cache first
        if use_cache:
            cached = cache.get_cached_recommendations(cache_id)
            if cached:
                logger.info("Cache hit for %s", cache_id)
                return {
                    "source": "cache",
                    "recommendations": cached.get("recommendations", []),
                    "total_estimated_savings": cached.get("total_estimated_savings", 0),
                    "generation_time_ms": cached.get("generation_time_ms", 0),
                    "cached_at": cached.get("cached_at"),
                    "task_id": None,  # No background task needed
                }
        
        # Start background task
        task = generate_recommendations_bg.delay(
            architecture_id=architecture_id,
            architecture_file=architecture_file,
        )
        
        logger.info("Started background recommendation task: %s", task.id)
        
        return {
            "source": "background",
            "task_id": task.id,
            "status": "queued",
            "message": "Recommendations are being generated. Poll /recommendations/task-status/{task_id} for progress",
        }
        
    except Exception as e:
        logger.error("Failed to start background task: %s", e)
        raise HTTPException(500, f"Failed to start task: {str(e)}")


# ─── Get Background Task Status ────────────────────────────────────

@router.get("/task-status/{task_id}")
async def get_background_task_status(task_id: str):
    """
    Get status of a background recommendation task
    
    Returns: state, progress (0-100), stage, result (if complete), error (if failed)
    """
    try:
        status = get_task_status(task_id)
        
        return {
            "task_id": task_id,
            "state": status.get("state"),
            "progress": status.get("progress", 0),
            "stage": status.get("stage", ""),
            "result": status.get("result"),
            "error": status.get("error"),
        }
        
    except Exception as e:
        logger.error("Failed to get task status: %s", e)
        raise HTTPException(500, f"Failed to get task status: {str(e)}")


# ─── Clear Cache ───────────────────────────────────────────────────

@router.post("/cache/clear")
async def clear_recommendation_cache(
    architecture_id: Optional[str] = None,
    architecture_file: Optional[str] = None,
):
    """
    Clear cached recommendations to force fresh analysis
    
    Use this before clicking 'Refresh' to get latest recommendations
    """
    if not architecture_id and not architecture_file:
        raise HTTPException(400, "Provide architecture_id or architecture_file")
    
    try:
        cache = get_cache()
        cache_id = architecture_id or architecture_file
        
        success = cache.delete_cached(cache_id)
        
        return {
            "cleared": success,
            "cache_id": cache_id,
            "message": "Cache cleared. Next request will generate fresh recommendations." if success 
                      else "Cache clear failed or Redis unavailable",
        }
        
    except Exception as e:
        logger.error("Failed to clear cache: %s", e)
        raise HTTPException(500, f"Failed to clear cache: {str(e)}")


# ─── Get Cache Statistics ──────────────────────────────────────────

@router.get("/cache/stats")
async def get_cache_statistics():
    """Get Redis cache statistics and health"""
    try:
        cache = get_cache()
        stats = cache.get_stats()
        
        return {
            "cache_enabled": stats.get("enabled", False),
            "cache_connected": stats.get("connected", False),
            "used_memory": stats.get("used_memory"),
            "peak_memory": stats.get("used_memory_peak"),
        }
        
    except Exception as e:
        logger.error("Failed to get cache stats: %s", e)
        raise HTTPException(500, f"Failed to get cache stats: {str(e)}")


# ─── Summary Endpoint ──────────────────────────────────────────────

@router.get("/summary")
async def get_recommendations_summary(
    architecture_id: Optional[str] = None,
    architecture_file: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Get summary of all recommendations for an architecture
    
    Aggregates all completed recommendation runs:
    - Total potential savings (sum across all runs)
    - Total annual savings
    - Average generation time
    - Last update timestamp
    """
    if not architecture_id and not architecture_file:
        raise HTTPException(400, "Provide architecture_id or architecture_file")
    
    try:
        query = db.query(RecommendationResult).filter(
            RecommendationResult.status == "completed"
        )
        
        if architecture_id:
            query = query.filter(RecommendationResult.architecture_id == architecture_id)
        else:
            query = query.filter(RecommendationResult.architecture_file == architecture_file)
        
        results = query.all()
        
        if not results:
            return {
                "total_monthly_savings": 0,
                "total_annual_savings": 0,
                "average_generation_time_ms": 0,
                "total_recommendations": 0,
                "last_updated": None,
                "architecture_id": architecture_id,
                "architecture_file": architecture_file,
            }
        
        total_monthly = sum(r.total_estimated_savings or 0 for r in results)
        total_annual = total_monthly * 12
        avg_time = sum(r.generation_time_ms or 0 for r in results) / len(results)
        total_recs = sum(r.card_count or 0 for r in results)
        last_updated = max(r.created_at for r in results if r.created_at)
        
        return {
            "total_monthly_savings": round(total_monthly, 2),
            "total_annual_savings": round(total_annual, 2),
            "average_generation_time_ms": round(avg_time, 0),
            "total_recommendations": total_recs,
            "last_updated": last_updated.isoformat() if last_updated else None,
            "architecture_id": architecture_id,
            "architecture_file": architecture_file,
        }
        
    except Exception as e:
        logger.error("Failed to get summary: %s", e)
        raise HTTPException(500, f"Failed to get summary: {str(e)}")


__all__ = ["router"]
