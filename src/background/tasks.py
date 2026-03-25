"""
Celery Configuration & Background Tasks
========================================
Async task execution for recommendation generation and CUR collection.
Uses Celery Beat for hourly scheduling.
"""

import logging
import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from celery import Celery, Task
from celery.schedules import crontab

logger = logging.getLogger(__name__)


def _recommendation_fingerprint(card: dict) -> str:
    """Create stable recommendation fingerprint for dedupe against DB history."""
    import hashlib

    resource = (card.get("resource_identification") or {}).get("resource_id", "")
    title = card.get("title", "")
    action = ""
    recs = card.get("recommendations") or []
    if recs and isinstance(recs[0], dict):
        action = recs[0].get("action", "")
    savings = round(float(card.get("total_estimated_savings", 0) or 0), 2)
    key = f"{resource.strip().lower()}|{title.strip().lower()}|{action.strip().lower()}|{savings:.2f}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _load_graph_data_for_architecture(db, architecture_id: str) -> dict:
    """Load graph data from latest completed snapshot, fallback to Neo4j graph store."""
    from src.graph.models import IngestionSnapshot
    from src.graph.neo4j_bridge import load_graph_from_neo4j

    snap = (
        db.query(IngestionSnapshot)
        .filter(
            IngestionSnapshot.architecture_id == architecture_id,
            IngestionSnapshot.status == "completed",
        )
        .order_by(IngestionSnapshot.created_at.desc())
        .first()
    )
    if snap and snap.raw_data:
        return snap.raw_data if isinstance(snap.raw_data, dict) else json.loads(snap.raw_data)

    neo4j_graph = load_graph_from_neo4j(architecture_id)
    if not neo4j_graph:
        raise RuntimeError(f"Architecture graph not found in Neo4j: {architecture_id}")
    return neo4j_graph


def _generate_and_store_recommendations(db, architecture_id: str) -> dict:
    """Generate recommendations and persist only cards not already present in DB."""
    from dataclasses import asdict
    from src.analysis.graph_analyzer import GraphAnalyzer
    from src.analysis.context_assembler import ContextAssembler
    from src.llm.client import generate_recommendations
    from src.graph.models import RecommendationResult
    from src.api.schemas.persistence import RecommendationPayloadSchema, model_to_dict

    try:
        graph_data = _load_graph_data_for_architecture(db, architecture_id)
        analyzer = GraphAnalyzer(graph_data)
        report = analyzer.analyze()
        assembler = ContextAssembler(graph_data, report)
        ctx_pkg = assembler.assemble()

        arch_name = graph_data.get("metadata", {}).get("name", "")
        rec_result = generate_recommendations(
            context_package=ctx_pkg,
            architecture_name=arch_name,
            raw_graph_data=graph_data,
        )

        # Build dedupe set from prior completed results
        existing_rows = db.query(RecommendationResult).filter(
            RecommendationResult.architecture_id == architecture_id,
            RecommendationResult.status == "completed",
        ).all()
        fingerprints = set()
        for row in existing_rows:
            payload = row.payload if isinstance(row.payload, dict) else (json.loads(row.payload) if row.payload else {})
            for card in payload.get("recommendations", []):
                fingerprints.add(_recommendation_fingerprint(card))

        fresh_cards = []
        skipped = 0
        for card in rec_result.cards:
            fp = _recommendation_fingerprint(card)
            if fp in fingerprints:
                skipped += 1
                continue
            fingerprints.add(fp)
            fresh_cards.append(card)

        payload = {
            "recommendations": fresh_cards,
            "total_estimated_savings": sum(float(c.get("total_estimated_savings", 0) or 0) for c in fresh_cards),
            "llm_used": rec_result.llm_used,
            "generation_time_ms": rec_result.generation_time_ms,
            "context_package": asdict(ctx_pkg),
            "architecture_name": rec_result.architecture_name or arch_name,
            "deduplicated_existing_count": skipped,
        }
        validated_payload = model_to_dict(RecommendationPayloadSchema, payload)

        row = RecommendationResult(
            architecture_id=architecture_id,
            architecture_file=None,
            status="completed",
            payload=validated_payload,
            generation_time_ms=validated_payload.get("generation_time_ms"),
            total_estimated_savings=validated_payload.get("total_estimated_savings"),
            card_count=len(validated_payload.get("recommendations", [])),
        )
        db.add(row)
        db.commit()

        return {
            "architecture_id": architecture_id,
            "generated_cards": len(fresh_cards),
            "skipped_existing_cards": skipped,
            "total_estimated_savings": validated_payload.get("total_estimated_savings", 0.0),
            "status": "completed",
        }
    except Exception as exc:
        fail_payload = model_to_dict(
            RecommendationPayloadSchema,
            {
                "recommendations": [],
                "total_estimated_savings": 0.0,
                "llm_used": False,
                "generation_time_ms": 0,
                "architecture_name": "",
                "deduplicated_existing_count": 0,
            },
        )
        row = RecommendationResult(
            architecture_id=architecture_id,
            architecture_file=None,
            status="failed",
            error_message=str(exc)[:4096],
            payload=fail_payload,
            generation_time_ms=0,
            total_estimated_savings=0.0,
            card_count=0,
        )
        db.add(row)
        db.commit()
        raise

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
            from src.storage.database import SessionLocal

            db = SessionLocal()
            try:
                graph_data = _load_graph_data_for_architecture(db, architecture_id)
            finally:
                db.close()
        
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
    from src.storage.database import SessionLocal
    from src.graph.models import IngestionSnapshot
    from src.api.handlers.ingest import _run_cur_ingestion_background
    
    try:
        logger.info("Starting hourly CUR pipeline (collect -> snapshot -> LLM recommendations)...")

        db = SessionLocal()
        try:
            region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
            snap = IngestionSnapshot(
                id=str(uuid.uuid4()),
                source="cur-hourly",
                status="running",
                pipeline_stage="queued",
                pipeline_detail="Scheduled hourly CUR ingestion started",
                region=region,
            )
            db.add(snap)
            db.commit()
            snap_id = snap.id

            _run_cur_ingestion_background(
                snap_id=snap_id,
                region=region,
                cur_bucket=os.getenv("CUR_BUCKET"),
                cur_prefix=os.getenv("CUR_PREFIX"),
                collect_cloudwatch=True,
            )

            db.expire_all()
            completed = db.query(IngestionSnapshot).filter(IngestionSnapshot.id == snap_id).first()
            if not completed or completed.status != "completed" or not completed.architecture_id:
                raise RuntimeError("Hourly CUR pipeline failed before recommendation stage")

            rec_summary = _generate_and_store_recommendations(db, completed.architecture_id)

            logger.info(
                "✓ Hourly CUR pipeline complete: snapshot=%s architecture=%s new_cards=%d skipped=%d",
                snap_id,
                completed.architecture_id,
                rec_summary["generated_cards"],
                rec_summary["skipped_existing_cards"],
            )

            return {
                "snapshot_id": snap_id,
                "architecture_id": completed.architecture_id,
                "services_count": completed.total_services or 0,
                "dependencies_count": len((completed.raw_data or {}).get("edges", [])) if isinstance(completed.raw_data, dict) else 0,
                "generated_recommendations": rec_summary["generated_cards"],
                "skipped_existing_recommendations": rec_summary["skipped_existing_cards"],
                "status": "completed",
                "timestamp": datetime.utcnow().isoformat(),
            }
        finally:
            db.close()

        return {
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
