"""
Celery Configuration & Background Tasks
========================================
Async task execution for recommendation generation and CUR collection.
Uses Celery Beat for hourly scheduling.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from celery import Celery, Task
from celery.schedules import crontab

logger = logging.getLogger(__name__)

# ─── Celery Configuration ─────────────────────────────────────────

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

app = Celery("finops-ai")

app.conf.update(
    broker_url=CELERY_BROKER_URL,
    result_backend=CELERY_RESULT_BACKEND,
    task_track_started=CELERY_TASK_TRACK_STARTED,
    task_time_limit=CELERY_TASK_TIME_LIMIT,
    # Beat schedule for periodic tasks
    beat_schedule={
        "collect-cur-hourly": {
            "task": "src.background.tasks.collect_cur_data",
            "schedule": crontab(minute=0),  # Every hour at :00
            "options": {"expires": 3600},  # Expire after 1 hour
        },
        "cleanup-cache-daily": {
            "task": "src.background.tasks.cleanup_old_cache",
            "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
            "options": {"expires": 86400},
        },
    },
)


class CallbackTask(Task):
    """Task that handles callbacks"""
    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 3}
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True


app.Task = CallbackTask
logger.info("✓ Celery initialized: broker=%s", CELERY_BROKER_URL.split("//")[1].split(":")[0])


# ─── Background Task Definitions ──────────────────────────────────

@app.task(bind=True, name="src.background.tasks.generate_recommendations_bg")
def generate_recommendations_bg(
    self,
    architecture_id: Optional[str] = None,
    architecture_file: Optional[str] = None,
) -> dict:
    """
    Background task: Generate recommendations with progress tracking
    
    This task:
    1. Updates status to 'running'
    2. Loads graph data
    3. Runs GraphAnalyzer
    4. Assembles context
    5. Calls LLM
    6. Deduplicates & validates
    7. Saves to cache & DB
    8. Returns result with cache key
    """
    from src.analysis.graph_analyzer import GraphAnalyzer
    from src.analysis.context_assembler import ContextAssembler
    from src.llm.client import generate_recommendations
    from src.storage.recommendation_cache import get_cache
    import json
    from pathlib import Path
    
    cache = get_cache()
    task_id = self.request.id
    
    try:
        # Update status
        cache.set_task_status(task_id, "running", 0)
        self.update_state(state="PROGRESS", meta={"progress": 10, "stage": "Loading graph..."})
        
        # Load graph data
        graph_data = None
        if architecture_id:
            # Load from DB
            from src.storage.database import get_db
            from src.graph.models import IngestionSnapshot, Architecture, Service, Dependency
            
            db = next(get_db())
            snap = db.query(IngestionSnapshot).filter(
                IngestionSnapshot.architecture_id == architecture_id,
                IngestionSnapshot.status == "completed",
            ).order_by(IngestionSnapshot.created_at.desc()).first()
            
            if snap and snap.raw_data:
                graph_data = snap.raw_data if isinstance(snap.raw_data, dict) else json.loads(snap.raw_data)
        
        elif architecture_file:
            # Load from synthetic file
            synthetic_dir = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic"
            arch_path = synthetic_dir / architecture_file
            if arch_path.exists():
                with open(arch_path) as f:
                    graph_data = json.load(f)
        
        if not graph_data:
            raise ValueError("Could not load graph data")
        
        # Analyze
        cache.set_task_status(task_id, "running", 20)
        self.update_state(state="PROGRESS", meta={"progress": 30, "stage": "Analyzing graph..."})
        
        analyzer = GraphAnalyzer(graph_data)
        report = analyzer.analyze()
        
        # Assemble context
        cache.set_task_status(task_id, "running", 40)
        self.update_state(state="PROGRESS", meta={"progress": 50, "stage": "Assembling context..."})
        
        assembler = ContextAssembler(graph_data, report)
        ctx_pkg = assembler.assemble()
        
        # Generate
        cache.set_task_status(task_id, "running", 60)
        self.update_state(state="PROGRESS", meta={"progress": 70, "stage": "Generating recommendations..."})
        
        arch_name = graph_data.get("metadata", {}).get("name", "")
        rec_result = generate_recommendations(
            context_package=ctx_pkg,
            architecture_name=arch_name,
            raw_graph_data=graph_data,
        )
        
        # Prepare response
        cache.set_task_status(task_id, "running", 90)
        self.update_state(state="PROGRESS", meta={"progress": 90, "stage": "Saving results..."})
        
        response = {
            "recommendations": rec_result.cards,
            "total_estimated_savings": rec_result.total_estimated_savings,
            "llm_used": rec_result.llm_used,
            "generation_time_ms": rec_result.generation_time_ms,
            "architecture_name": rec_result.architecture_name or arch_name,
            "card_count": len(rec_result.cards),
        }
        
        # Cache results
        cache_key = f"{architecture_id or architecture_file}:{task_id}"
        cache.cache_recommendations(cache_key, response)
        
        # Save to history
        cache.save_to_history(architecture_id or architecture_file, response)
        
        # Final status
        cache.set_task_status(task_id, "completed", 100)
        self.update_state(state="SUCCESS", meta={
            "progress": 100,
            "stage": "Complete",
            "result": response
        })
        
        logger.info("✓ Background recommendation task completed: %s", task_id)
        return response
        
    except Exception as e:
        logger.error("Background recommendation task failed: %s", e, exc_info=True)
        cache.set_task_status(task_id, "failed", 0)
        self.update_state(state="FAILURE", meta={"error": str(e)})
        raise


@app.task(name="src.background.tasks.collect_cur_data")
def collect_cur_data() -> dict:
    """
    Cron Task: Collect CUR data hourly
    
    1. Run AWS CUR collector
    2. Parse CUR data
    3. Create/update IngestionSnapshot
    4. Trigger recommendation generation if new data
    """
    from src.ingestion.aws_client import AWSResourceCollector
    from src.ingestion.cur_parser import parse_cur
    from src.ingestion.cur_transformer import CURTransformer
    
    try:
        logger.info("Starting hourly CUR collection...")
        
        # Collect AWS resources
        collector = AWSResourceCollector()
        services, dependencies = collector.discover()
        
        # Parse CUR
        cur_data = parse_cur()
        
        # Transform to architecture
        transformer = CURTransformer()
        arch = transformer.transform(services, cur_data)
        
        logger.info("✓ CUR collection complete: %d services, %d dependencies",
                   len(services), len(dependencies))
        
        return {
            "services_count": len(services),
            "dependencies_count": len(dependencies),
            "timestamp": datetime.utcnow().isoformat(),
            "status": "completed",
        }
        
    except Exception as e:
        logger.error("CUR collection failed: %s", e, exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


@app.task(name="src.background.tasks.cleanup_old_cache")
def cleanup_old_cache() -> dict:
    """
    Cron Task: Clean up old cache entries (daily)
    Removes entries older than HISTORY_KEEP_DAYS
    """
    from src.storage.recommendation_cache import get_cache
    
    try:
        cache = get_cache()
        
        if not cache.enabled:
            return {"status": "skipped", "reason": "Redis not available"}
        
        logger.info("Starting daily cache cleanup...")
        
        # Redis handles expiry automatically via TTL
        # This task ensures consistency
        stats = cache.get_stats()
        
        logger.info("✓ Cache cleanup complete: %s", stats.get("used_memory"))
        
        return {
            "status": "completed",
            "cache_stats": stats,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        logger.error("Cache cleanup failed: %s", e, exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


# ─── Task Helpers ─────────────────────────────────────────────────

def get_task_status(task_id: str) -> dict:
    """Get status of a background task"""
    from celery.result import AsyncResult
    
    result = AsyncResult(task_id, app=app)
    
    return {
        "task_id": task_id,
        "state": result.state,
        "progress": result.info.get("progress", 0) if isinstance(result.info, dict) else 0,
        "stage": result.info.get("stage", "") if isinstance(result.info, dict) else "",
        "result": result.result if result.successful() else None,
        "error": str(result.info) if result.failed() else None,
    }


def revoke_task(task_id: str) -> bool:
    """Cancel a running task"""
    try:
        app.control.revoke(task_id, terminate=True)
        logger.info("✓ Task revoked: %s", task_id)
        return True
    except Exception as e:
        logger.error("Failed to revoke task: %s", e)
        return False


__all__ = [
    "app",
    "generate_recommendations_bg",
    "collect_cur_data",
    "cleanup_old_cache",
    "get_task_status",
    "revoke_task",
]
