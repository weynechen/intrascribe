"""
Audio processing and management API routes.
Handles audio file operations, caching, and processing requests.
"""
import os
import sys
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.config import redis_config
from core.redis import redis_manager
from shared.utils import timing_decorator
from shared.models import AudioData

from core.auth import get_current_user, get_optional_current_user, verify_session_ownership
from schemas import (
    AudioUploadResponse, AudioProcessRequest, SetCurrentSessionRequest, 
    CurrentSessionResponse, AudioCacheStatusResponse
)
from clients.microservice_clients import stt_client, diarization_client
from repositories.session_repository import session_repository

logger = ServiceLogger("audio-api")

router = APIRouter(prefix="/audio", tags=["Audio"])


class AudioCacheManager:
    """Audio cache manager using Redis"""
    
    def __init__(self):
        self.redis_url = redis_config.redis_url
    
    async def get_cache_status(self) -> Dict[str, Any]:
        """Get audio cache status"""
        try:
            redis = await redis_manager.get_redis()
            
            # Get all session keys
            session_keys = await redis.keys("session:*:transcription")
            
            active_sessions = []
            for key in session_keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                session_id = key_str.split(':')[1]
                active_sessions.append(session_id)
            
            # Estimate cache size (rough calculation)
            cache_size_mb = len(session_keys) * 0.1  # Rough estimate
            
            # Get oldest session (simplified)
            oldest_session = active_sessions[0] if active_sessions else None
            
            return {
                "total_sessions": len(session_keys),
                "cache_size_mb": cache_size_mb,
                "active_sessions": len(active_sessions),
                "oldest_session": oldest_session,
                "cache_memory_usage": {
                    "estimated_mb": cache_size_mb,
                    "active_keys": len(session_keys)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache status: {e}")
            return {
                "total_sessions": 0,
                "cache_size_mb": 0.0,
                "active_sessions": 0,
                "oldest_session": None,
                "cache_memory_usage": {}
            }
    
    def set_current_session(self, session_id: str):
        """Set current active session (synchronous)"""
        # For now, we'll store this in a simple way
        # In a real implementation, this might be stored in Redis or database
        self.current_session_id = session_id
        logger.info(f"Set current session: {session_id}")
    
    def get_current_session(self) -> Optional[str]:
        """Get current active session"""
        return getattr(self, 'current_session_id', None)


# Global cache manager instance
cache_manager = AudioCacheManager()


@router.post("/process", response_model=AudioUploadResponse)
@timing_decorator
async def process_audio(
    request: AudioProcessRequest,
    current_user = Depends(get_current_user)
):
    """
    Process audio (compatibility endpoint).
    
    Args:
        request: Audio processing request
        current_user: Current authenticated user
    
    Returns:
        Audio processing response
    """
    try:
        # Verify session ownership
        session = session_repository.get_session_by_id(request.session_id, current_user.id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # This endpoint is mainly for compatibility
        # Actual audio processing happens in real-time via LiveKit Agent
        logger.info(f"Audio processing request for session: {request.session_id}")
        
        return AudioUploadResponse(
            success=True,
            message="Audio processing will be handled by LiveKit Agent in real-time"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Audio processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Audio processing failed"
        )


@router.post("/upload", response_model=AudioUploadResponse)
@timing_decorator
async def upload_audio_file(
    audio_file: UploadFile = File(...),
    session_id: str = None,
    current_user = Depends(get_current_user)
):
    """
    Upload audio file for processing.
    
    Args:
        audio_file: Uploaded audio file
        session_id: Optional session ID
        current_user: Current authenticated user
    
    Returns:
        Audio upload response with processing results
    """
    try:
        logger.info(f"Processing uploaded audio file: {audio_file.filename}")
        
        # Read audio content
        audio_content = await audio_file.read()
        
        # Determine audio format
        file_format = "wav"
        if audio_file.filename:
            file_format = audio_file.filename.split('.')[-1].lower()
        
        # Convert audio to required format
        import numpy as np
        import io
        import librosa
        
        # Load audio with librosa
        audio_data, sample_rate = librosa.load(io.BytesIO(audio_content), sr=16000)
        
        audio_data_obj = AudioData(
            sample_rate=sample_rate,
            audio_array=audio_data.tolist(),
            format=file_format,
            duration_seconds=len(audio_data) / sample_rate
        )
        
        # If session_id provided, verify ownership
        if session_id:
            session = session_repository.get_session_by_id(session_id, current_user.id)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this session"
                )
        else:
            # Create new session for uploaded file
            session = session_repository.create_session(
                user_id=current_user.id,
                title=f"Uploaded: {audio_file.filename}",
                language="zh-CN"
            )
            session_id = session.id
        
        # Call STT service
        transcription_result = await stt_client.transcribe_audio(
            audio_data_obj, 
            session_id, 
            "zh-CN"
        )
        
        if transcription_result.success:
            logger.success(f"Audio file processed successfully: {audio_file.filename}")
            
            return AudioUploadResponse(
                success=True,
                message="Audio file processed successfully",
                file_id=session_id,  # Use session ID as file ID
                file_url=None  # No public URL for processed files
            )
        else:
            logger.error(f"Audio processing failed: {transcription_result.error_message}")
            
            return AudioUploadResponse(
                success=False,
                message=f"Audio processing failed: {transcription_result.error_message}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Audio upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Audio upload failed"
        )


@router.post("/session/set")
@timing_decorator
async def set_current_session(request: SetCurrentSessionRequest):
    """
    Set current active session.
    
    Args:
        request: Set current session request
    
    Returns:
        Success confirmation
    """
    try:
        cache_manager.set_current_session(request.session_id)
        
        return {
            "message": "Current session set successfully",
            "session_id": request.session_id
        }
        
    except Exception as e:
        logger.error(f"Failed to set current session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set current session"
        )


@router.get("/session/current", response_model=CurrentSessionResponse)
@timing_decorator
async def get_current_session():
    """
    Get current active session.
    
    Returns:
        Current session information
    """
    try:
        current_session_id = cache_manager.get_current_session()
        
        return CurrentSessionResponse(
            session_id=current_session_id,
            status="active" if current_session_id else "none"
        )
        
    except Exception as e:
        logger.error(f"Failed to get current session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get current session"
        )


@router.get("/cache/status", response_model=AudioCacheStatusResponse)
@timing_decorator
async def get_audio_cache_status():
    """
    Get audio cache status.
    
    Returns:
        Audio cache status information
    """
    try:
        cache_status = await cache_manager.get_cache_status()
        
        return AudioCacheStatusResponse(
            total_sessions=cache_status["total_sessions"],
            cache_size_mb=cache_status["cache_size_mb"],
            active_sessions=cache_status["active_sessions"],
            oldest_session=cache_status.get("oldest_session"),
            cache_memory_usage=cache_status.get("cache_memory_usage", {})
        )
        
    except Exception as e:
        logger.error(f"Failed to get cache status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get cache status"
        )
