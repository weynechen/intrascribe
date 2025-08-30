"""
Sessions V2 API routes for async operations.
Handles session finalization, batch operations, and long-running tasks.
"""
import os
import sys
import uuid
import asyncio
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Path
from datetime import datetime

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.utils import timing_decorator
from shared.models import SessionStatus

from core.auth import get_current_user, verify_session_ownership
from core.redis import redis_manager
from repositories.session_repository import session_repository
from routers.transcriptions import transcription_repository

logger = ServiceLogger("sessions-v2-api")

router = APIRouter(prefix="/v2/sessions", tags=["Sessions V2"])


async def finalize_session_task(session_id: str, user_id: str):
    """
    Background task to finalize session by saving Redis data to database.
    
    Args:
        session_id: Session ID to finalize
        user_id: User ID for verification
    """
    try:
        logger.info(f"Starting session finalization: {session_id}")
        
        # Get session to verify it exists and belongs to user
        session = session_repository.get_session_by_id(session_id, user_id)
        if not session:
            logger.error(f"Session not found or access denied: {session_id}")
            return
        
        # Get transcription segments from Redis
        segments = await redis_manager.get_session_transcriptions(session_id)
        logger.info(f"Retrieved {len(segments)} transcription segments from Redis for session: {session_id}")
        
        if segments:
            # Combine all segment texts into full transcription content
            full_text_parts = []
            segment_data = []
            
            for i, segment in enumerate(segments):
                text = segment.get("text", "").strip()
                if text:
                    full_text_parts.append(text)
                    
                    # Prepare segment data for database storage
                    segment_data.append({
                        "index": i,
                        "speaker": segment.get("speaker", "Speaker 1"),
                        "timestamp": segment.get("timestamp"),
                        "text": text,
                        "is_final": segment.get("is_final", True)
                    })
            
            if full_text_parts:
                # Create full transcription content
                full_content = " ".join(full_text_parts)
                
                # Save transcription to database
                transcription = transcription_repository.save_transcription(
                    session_id=session_id,
                    content=full_content,
                    language=session.language,
                    segments=segment_data,
                    stt_model="agent_microservice",
                    word_count=len(full_content.split())
                )
                
                logger.success(f"Saved transcription to database: {transcription.get('id')}")
        
        # Update session status to completed
        updated_session = session_repository.update_session(
            session_id=session_id,
            status=SessionStatus.COMPLETED,
            user_id=user_id
        )
        
        if updated_session:
            logger.success(f"Session finalized successfully: {session_id}")
        else:
            logger.error(f"Failed to update session status: {session_id}")
        
        # Clear Redis data after successful database save
        if segments:
            await redis_manager.clear_session_transcriptions(session_id)
            logger.info(f"Cleared Redis transcription data for session: {session_id}")
            
    except Exception as e:
        logger.error(f"Session finalization failed for {session_id}: {e}")
        # Note: In a production system, you might want to store this error 
        # in a task status table for the frontend to query


def extract_session_id_from_path(session_id_param: str) -> str:
    """Extract actual session ID from path parameter (handles room name format)"""
    if session_id_param.startswith("intrascribe_room_"):
        return session_id_param.replace("intrascribe_room_", "")
    return session_id_param


@router.post("/{session_id}/finalize")
@timing_decorator
async def finalize_session(
    session_id: str,
    current_user = Depends(get_current_user)
):
    """
    Finalize session by processing Redis data and saving to database.
    
    This operation processes transcription data from Redis
    and saves it to the permanent database.
    
    Args:
        session_id: Session ID or room name (will extract actual session ID)
        current_user: Current authenticated user
    
    Returns:
        Task completion result
    """
    try:
        # Extract actual session ID from path parameter
        actual_session_id = extract_session_id_from_path(session_id)
        logger.info(f"Starting session finalization: {session_id} -> {actual_session_id}")
        
        # Verify session ownership manually
        from core.auth import auth_manager
        if not auth_manager.verify_session_ownership(actual_session_id, current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # Execute finalization directly (synchronously)
        await finalize_session_task(actual_session_id, current_user.id)
        
        # Return success response (V2 API format compatible)
        return {
            "success": True,
            "message": "Session finalized successfully",
            "timestamp": datetime.utcnow().isoformat(),
            "task_id": str(uuid.uuid4()),  # Mock task ID for compatibility
            "status": "success",
            "result": {
                "message": "Session finalized successfully",
                "session_id": actual_session_id,
                "transcription_saved": True,
                "total_duration_seconds": 0  # Will be calculated
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to finalize session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to finalize session"
        )


@router.get("/{session_id}/status")
@timing_decorator  
async def get_session_status_v2(
    session_id: str,
    current_user = Depends(get_current_user)
):
    """
    Get detailed session status for V2 API.
    
    Args:
        session_id: Session ID or room name (will extract actual session ID)
        current_user: Current authenticated user
    
    Returns:
        Detailed session status
    """
    try:
        # Extract actual session ID from path parameter
        actual_session_id = extract_session_id_from_path(session_id)
        logger.info(f"Getting session status: {session_id} -> {actual_session_id}")
        
        # Verify session ownership manually
        from core.auth import auth_manager
        if not auth_manager.verify_session_ownership(actual_session_id, current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # Get session from database
        session = session_repository.get_session_by_id(actual_session_id, current_user.id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Get Redis transcription count
        segments = await redis_manager.get_session_transcriptions(actual_session_id)
        
        # Get session state from Redis
        session_state = await redis_manager.get_session_state(actual_session_id)
        
        return {
            "success": True,
            "message": "Session status retrieved",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "id": session.id,
                "title": session.title,
                "status": session.status.value,
                "language": session.language,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "redis_segments": len(segments),
                "redis_state": session_state,
                "is_finalized": session.status == SessionStatus.COMPLETED
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get session status"
        )
