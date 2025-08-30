"""
Real-time API routes for live transcription and session monitoring.
Handles real-time data access and WebSocket-like functionality.
"""
import os
import sys
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import json
import asyncio

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.utils import timing_decorator

from core.auth import get_current_user, verify_session_ownership, verify_session_ownership_or_service, get_current_user_or_service
from core.redis import redis_manager

logger = ServiceLogger("realtime-api")

router = APIRouter(prefix="/realtime", tags=["Real-time"])


@router.get("/sessions/{session_id}/transcription")
@timing_decorator
async def get_session_transcription_realtime(
    session_id: str = Depends(verify_session_ownership),
    current_user = Depends(get_current_user)
):
    """
    Get real-time transcription data for a session.
    
    Args:
        session_id: Session ID (verified for ownership)
        current_user: Current authenticated user
    
    Returns:
        Real-time transcription segments
    """
    try:
        # Get transcription segments from Redis
        segments = await redis_manager.get_session_transcriptions(session_id)
        
        logger.info(f"Retrieved {len(segments)} real-time transcription segments for session: {session_id}")
        
        return {
            "session_id": session_id,
            "segments": segments,
            "total_segments": len(segments),
            "last_updated": max([seg.get("timestamp", 0) for seg in segments]) if segments else 0
        }
        
    except Exception as e:
        logger.error(f"Failed to get real-time transcription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get real-time transcription"
        )


@router.get("/sessions/{session_id}/status")
@timing_decorator
async def get_session_realtime_status(
    session_id: str = Depends(verify_session_ownership),
    current_user = Depends(get_current_user)
):
    """
    Get real-time session status.
    
    Args:
        session_id: Session ID (verified for ownership)
        current_user: Current authenticated user
    
    Returns:
        Session real-time status
    """
    try:
        # Get session state from Redis
        session_state = await redis_manager.get_session_state(session_id)
        
        # Get transcription count
        segments = await redis_manager.get_session_transcriptions(session_id)
        
        status_info = {
            "session_id": session_id,
            "status": session_state.get("status", "unknown"),
            "participant_count": int(session_state.get("participant_count", 0)),
            "recording": session_state.get("recording", False),
            "transcription_segments": len(segments),
            "last_activity": session_state.get("last_activity", 0),
            "duration_seconds": session_state.get("duration_seconds", 0)
        }
        
        logger.debug(f"Real-time status for session {session_id}: {status_info}")
        
        return status_info
        
    except Exception as e:
        logger.error(f"Failed to get session status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get session status"
        )


@router.post("/sessions/{session_id}/transcription")
@timing_decorator
async def store_transcription_segment(
    segment_data: Dict[str, Any],
    session_id: str = Depends(verify_session_ownership_or_service),
    current_user_or_service = Depends(get_current_user_or_service)
):
    """
    Store real-time transcription segment.
    
    Args:
        segment_data: Transcription segment data
        session_id: Session ID (verified for ownership or service access)
        current_user_or_service: Current authenticated user or None if service
    
    Returns:
        Success confirmation
    """
    try:
        # Validate segment data
        required_fields = ["text", "speaker"]
        if not all(field in segment_data for field in required_fields):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields in segment data"
            )
        
        # Store in Redis
        await redis_manager.store_transcription_segment(session_id, segment_data)
        
        logger.debug(f"Stored transcription segment for session: {session_id}")
        
        return {
            "success": True,
            "message": "Transcription segment stored successfully",
            "session_id": session_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to store transcription segment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store transcription segment"
        )


@router.delete("/sessions/{session_id}/transcription")
@timing_decorator
async def clear_session_transcription(
    session_id: str = Depends(verify_session_ownership),
    current_user = Depends(get_current_user)
):
    """
    Clear real-time transcription data for a session.
    
    Args:
        session_id: Session ID (verified for ownership)
        current_user: Current authenticated user
    
    Returns:
        Success confirmation
    """
    try:
        await redis_manager.clear_session_transcriptions(session_id)
        
        logger.info(f"Cleared transcription data for session: {session_id}")
        
        return {
            "success": True,
            "message": "Session transcription data cleared",
            "session_id": session_id
        }
        
    except Exception as e:
        logger.error(f"Failed to clear transcription data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear transcription data"
        )


@router.get("/cache/stats")
@timing_decorator
async def get_cache_statistics():
    """
    Get cache statistics and performance metrics.
    
    Returns:
        Cache statistics
    """
    try:
        redis_health = await redis_manager.health_check()
        
        # Get Redis info if connected
        cache_stats = {
            "redis_status": redis_health["status"],
            "connected": redis_health["connected"]
        }
        
        if redis_health["connected"]:
            redis = await redis_manager.get_redis()
            
            # Get basic Redis info
            info = await redis.info()
            
            cache_stats.update({
                "memory_used_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
                "total_keys": info.get("db0", {}).get("keys", 0) if "db0" in info else 0,
                "connected_clients": info.get("connected_clients", 0),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
            })
        
        return cache_stats
        
    except Exception as e:
        logger.error(f"Failed to get cache statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get cache statistics"
        )
