"""
Redis Cache Management for Recommendations
===========================================
Provides caching, backup, and quick retrieval of recommendations
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

CACHE_TTL_HOURS = 24  # Recommendations cached for 24 hours
HISTORY_KEEP_DAYS = 90  # Keep history for 90 days


class RecommendationCache:
    """Manages Redis cache for recommendations"""

    def __init__(self):
        self.client = None
        self.enabled = HAS_REDIS
        
        if self.enabled:
            try:
                self.client = redis.Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    db=REDIS_DB,
                    password=REDIS_PASSWORD,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                    health_check_interval=30,
                )
                # Test connection
                self.client.ping()
                logger.info("✓ Redis connected: %s:%d", REDIS_HOST, REDIS_PORT)
            except Exception as e:
                logger.warning("Redis connection failed: %s (caching disabled)", e)
                self.enabled = False
                self.client = None

    def _key(self, prefix: str, identifier: str) -> str:
        """Generate cache key"""
        return f"finops:rec:{prefix}:{identifier}"

    def cache_recommendations(self, 
                            architecture_id: str,
                            recommendations: Dict[str, Any],
                            ttl_hours: int = CACHE_TTL_HOURS) -> bool:
        """Cache recommendation results"""
        if not self.enabled:
            return False

        try:
            key = self._key("current", architecture_id)
            ttl_seconds = ttl_hours * 3600
            
            data = {
                "recommendations": recommendations,
                "cached_at": datetime.utcnow().isoformat(),
                "ttl_hours": ttl_hours,
            }
            
            self.client.setex(
                key,
                ttl_seconds,
                json.dumps(data)
            )
            logger.info("✓ Cached recommendations for %s (TTL: %dh)", architecture_id, ttl_hours)
            return True
        except Exception as e:
            logger.warning("Failed to cache recommendations: %s", e)
            return False

    def get_cached_recommendations(self, architecture_id: str) -> Optional[Dict]:
        """Retrieve cached recommendations"""
        if not self.enabled:
            return None

        try:
            key = self._key("current", architecture_id)
            data = self.client.get(key)
            
            if data:
                logger.info("✓ Retrieved cached recommendations for %s", architecture_id)
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning("Failed to retrieve cached recommendations: %s", e)
            return None

    def delete_cached(self, architecture_id: str) -> bool:
        """Delete cached recommendations"""
        if not self.enabled:
            return False

        try:
            key = self._key("current", architecture_id)
            self.client.delete(key)
            logger.info("✓ Deleted cached recommendations for %s", architecture_id)
            return True
        except Exception as e:
            logger.warning("Failed to delete cache: %s", e)
            return False

    # ─── History Management ───────────────────────────────────────

    def save_to_history(self, 
                       architecture_id: str,
                       recommendations: Dict[str, Any],
                       timestamp: Optional[datetime] = None) -> bool:
        """Save recommendations to history list"""
        if not self.enabled:
            return False

        try:
            if not timestamp:
                timestamp = datetime.utcnow()
            
            history_key = self._key("history", architecture_id)
            
            entry = {
                "timestamp": timestamp.isoformat(),
                "total_savings": recommendations.get("total_estimated_savings", 0),
                "card_count": len(recommendations.get("cards", [])),
                "generation_time_ms": recommendations.get("generation_time_ms", 0),
            }
            
            # Push to history (keeps last 100 entries)
            self.client.lpush(history_key, json.dumps(entry))
            self.client.ltrim(history_key, 0, 99)  # Keep last 100
            
            # Set expiry
            self.client.expire(history_key, HISTORY_KEEP_DAYS * 86400)
            
            logger.info("✓ Saved to history for %s", architecture_id)
            return True
        except Exception as e:
            logger.warning("Failed to save history: %s", e)
            return False

    def get_history(self, architecture_id: str, limit: int = 50) -> List[Dict]:
        """Get recommendation history"""
        if not self.enabled:
            return []

        try:
            history_key = self._key("history", architecture_id)
            entries = self.client.lrange(history_key, 0, limit - 1)
            
            history = []
            for entry in entries:
                try:
                    history.append(json.loads(entry))
                except json.JSONDecodeError:
                    pass
            
            return history
        except Exception as e:
            logger.warning("Failed to retrieve history: %s", e)
            return []

    # ─── Status Tracking ──────────────────────────────────────────

    def set_task_status(self, task_id: str, status: str, progress: int = 0) -> bool:
        """Set background task status"""
        if not self.enabled:
            return False

        try:
            key = f"finops:task:{task_id}"
            data = {
                "status": status,  # pending | running | completed | failed
                "progress": progress,  # 0-100
                "updated_at": datetime.utcnow().isoformat(),
            }
            
            # Expire after 24 hours
            self.client.setex(key, 86400, json.dumps(data))
            return True
        except Exception as e:
            logger.warning("Failed to set task status: %s", e)
            return False

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get background task status"""
        if not self.enabled:
            return None

        try:
            key = f"finops:task:{task_id}"
            data = self.client.get(key)
            
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning("Failed to get task status: %s", e)
            return None

    # ─── Health Check ─────────────────────────────────────────────

    def health_check(self) -> bool:
        """Check Redis connection"""
        if not self.enabled:
            return False

        try:
            self.client.ping()
            return True
        except Exception:
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get Redis cache statistics"""
        if not self.enabled:
            return {"enabled": False}

        try:
            info = self.client.info("memory")
            return {
                "enabled": True,
                "used_memory": info.get("used_memory_human", "N/A"),
                "used_memory_peak": info.get("used_memory_peak_human", "N/A"),
                "connected": True,
            }
        except Exception:
            return {"enabled": True, "connected": False}


# Global cache instance
_cache_instance = None


def get_cache() -> RecommendationCache:
    """Get or create cache instance"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = RecommendationCache()
    return _cache_instance


__all__ = ["RecommendationCache", "get_cache"]
