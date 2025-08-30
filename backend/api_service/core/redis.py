"""
Redis connection and cache management.
Handles Redis operations for real-time data and caching.
"""
import os
import sys
import json
import time
from typing import Dict, Any, Optional, List
import redis.asyncio as redis

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.config import redis_config

logger = ServiceLogger("redis")


class RedisManager:
    """
    Redis connection and operation manager.
    Handles caching, real-time data, and session management.
    """
    
    def __init__(self):
        self.redis_url = redis_config.redis_url
        self._redis_pool = None
    
    async def get_redis(self) -> redis.Redis:
        """Get Redis connection"""
        if self._redis_pool is None:
            self._redis_pool = redis.from_url(
                self.redis_url,
                decode_responses=True,
                retry_on_timeout=True
            )
        return self._redis_pool
    
    async def close(self):
        """Close Redis connection"""
        if self._redis_pool:
            await self._redis_pool.close()
            self._redis_pool = None
    
    # =============== Session Cache Operations ===============
    
    async def store_transcription_segment(
        self, 
        session_id: str, 
        segment: Dict[str, Any]
    ):
        """Store transcription segment in Redis"""
        try:
            redis = await self.get_redis()
            
            # Add timestamp
            segment["timestamp"] = time.time()
            
            # Store in list for real-time access
            await redis.lpush(
                f"session:{session_id}:transcription", 
                json.dumps(segment)
            )
            
            # Set expiration (24 hours)
            await redis.expire(f"session:{session_id}:transcription", 86400)
            
            logger.debug(f"Stored transcription segment for session: {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to store transcription segment: {e}")
    
    async def get_session_transcriptions(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all transcription segments for a session"""
        try:
            redis = await self.get_redis()
            
            # Get all segments (most recent first)
            segments_json = await redis.lrange(f"session:{session_id}:transcription", 0, -1)
            
            segments = []
            for segment_json in reversed(segments_json):  # Reverse to get chronological order
                try:
                    segment = json.loads(segment_json)
                    segments.append(segment)
                except json.JSONDecodeError:
                    continue
            
            logger.debug(f"Retrieved {len(segments)} transcription segments for session: {session_id}")
            
            return segments
            
        except Exception as e:
            logger.error(f"Failed to get session transcriptions: {e}")
            return []
    
    async def clear_session_transcriptions(self, session_id: str):
        """Clear transcription data for a session"""
        try:
            redis = await self.get_redis()
            
            await redis.delete(f"session:{session_id}:transcription")
            
            logger.info(f"Cleared transcription data for session: {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to clear session transcriptions: {e}")
    
    # =============== Session State Management ===============
    
    async def set_session_state(self, session_id: str, state: Dict[str, Any]):
        """Set session state in Redis"""
        try:
            redis = await self.get_redis()
            
            # Store as hash
            await redis.hset(f"session:{session_id}:state", mapping=state)
            
            # Set expiration (24 hours)
            await redis.expire(f"session:{session_id}:state", 86400)
            
            logger.debug(f"Set session state for session: {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to set session state: {e}")
    
    async def get_session_state(self, session_id: str) -> Dict[str, Any]:
        """Get session state from Redis"""
        try:
            redis = await self.get_redis()
            
            state = await redis.hgetall(f"session:{session_id}:state")
            
            return state
            
        except Exception as e:
            logger.error(f"Failed to get session state: {e}")
            return {}
    
    # =============== Cache Operations ===============
    
    async def cache_set(self, key: str, value: Any, ttl: int = 3600):
        """Set cache value with TTL"""
        try:
            redis = await self.get_redis()
            
            serialized_value = json.dumps(value) if not isinstance(value, str) else value
            
            await redis.setex(key, ttl, serialized_value)
            
            logger.debug(f"Cached value for key: {key}")
            
        except Exception as e:
            logger.error(f"Failed to cache value: {e}")
    
    async def cache_get(self, key: str) -> Optional[Any]:
        """Get cached value"""
        try:
            redis = await self.get_redis()
            
            value = await redis.get(key)
            
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value  # Return as string if not JSON
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get cached value: {e}")
            return None
    
    async def cache_delete(self, key: str):
        """Delete cached value"""
        try:
            redis = await self.get_redis()
            
            await redis.delete(key)
            
            logger.debug(f"Deleted cache key: {key}")
            
        except Exception as e:
            logger.error(f"Failed to delete cache key: {e}")
    
    # =============== Health and Status ===============
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Redis health"""
        try:
            redis = await self.get_redis()
            
            # Simple ping test
            pong = await redis.ping()
            
            if pong:
                return {
                    "status": "healthy",
                    "connected": True,
                    "redis_url": self.redis_url.split('@')[-1] if '@' in self.redis_url else self.redis_url
                }
            else:
                return {"status": "unhealthy", "connected": False}
                
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                "status": "unhealthy", 
                "connected": False,
                "error": str(e)
            }


# Global Redis manager instance
redis_manager = RedisManager()
