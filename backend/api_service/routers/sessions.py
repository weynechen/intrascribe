"""
Session management API routes.
Handles CRUD operations for recording sessions.
"""
import os
import sys
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime
from pydantic import BaseModel

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.models import SessionData, SessionStatus
from shared.utils import timing_decorator, generate_id

from core.auth import get_current_user, verify_session_ownership
from repositories.session_repository import session_repository

logger = ServiceLogger("sessions-api")

router = APIRouter(prefix="/sessions", tags=["Sessions"])


# Request/Response models
class CreateSessionRequest(BaseModel):
    """Request model for creating sessions"""
    title: str
    language: str = "zh-CN"


class UpdateSessionRequest(BaseModel):
    """Request model for updating sessions"""
    title: Optional[str] = None
    status: Optional[str] = None


class SessionResponse(BaseModel):
    """Response model for session data"""
    id: str
    title: str
    status: str
    language: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# API Endpoints
@router.post("/", response_model=SessionResponse)
@timing_decorator
async def create_session(
    request: CreateSessionRequest,
    current_user = Depends(get_current_user)
):
    """
    Create a new recording session.
    
    Args:
        request: Session creation request
        current_user: Current authenticated user
    
    Returns:
        Created session data
    """
    try:
        logger.info(f"Creating session for user: {current_user.id}")
        
        # Create session
        session = session_repository.create_session(
            user_id=current_user.id,
            title=request.title,
            language=request.language
        )
        
        logger.success(f"Session created: {session.id}")
        
        return SessionResponse(
            id=session.id,
            title=session.title,
            status=session.status.value,
            language=session.language,
            created_at=session.created_at,
            updated_at=session.updated_at
        )
        
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session"
        )


@router.get("/{session_id}", response_model=SessionResponse)
@timing_decorator
async def get_session(
    session_id: str = Depends(verify_session_ownership),
    current_user = Depends(get_current_user)
):
    """
    Get session details.
    
    Args:
        session_id: Session ID (verified for ownership)
        current_user: Current authenticated user
    
    Returns:
        Session details
    """
    try:
        session = session_repository.get_session_by_id(session_id, current_user.id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        return SessionResponse(
            id=session.id,
            title=session.title,
            status=session.status.value,
            language=session.language,
            created_at=session.created_at,
            updated_at=session.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session"
        )


@router.get("/", response_model=List[SessionResponse])
@timing_decorator
async def list_sessions(
    limit: int = 50,
    offset: int = 0,
    current_user = Depends(get_current_user)
):
    """
    List user's sessions.
    
    Args:
        limit: Maximum number of sessions to return
        offset: Offset for pagination
        current_user: Current authenticated user
    
    Returns:
        List of user's sessions
    """
    try:
        sessions = session_repository.get_user_sessions(
            current_user.id, 
            limit=min(limit, 100),  # Cap at 100
            offset=offset
        )
        
        return [
            SessionResponse(
                id=session.id,
                title=session.title,
                status=session.status.value,
                language=session.language,
                created_at=session.created_at,
                updated_at=session.updated_at
            )
            for session in sessions
        ]
        
    except Exception as e:
        logger.error(f"Failed to list sessions for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve sessions"
        )


@router.put("/{session_id}", response_model=SessionResponse)
@timing_decorator
async def update_session(
    request: UpdateSessionRequest,
    session_id: str = Depends(verify_session_ownership),
    current_user = Depends(get_current_user)
):
    """
    Update session details.
    
    Args:
        request: Update request
        session_id: Session ID (verified for ownership)
        current_user: Current authenticated user
    
    Returns:
        Updated session data
    """
    try:
        # Convert status string to enum if provided
        status_enum = None
        if request.status:
            try:
                status_enum = SessionStatus(request.status.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {request.status}"
                )
        
        # Update session
        updated_session = session_repository.update_session(
            session_id=session_id,
            title=request.title,
            status=status_enum,
            user_id=current_user.id
        )
        
        if not updated_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or update failed"
            )
        
        logger.success(f"Session updated: {session_id}")
        
        return SessionResponse(
            id=updated_session.id,
            title=updated_session.title,
            status=updated_session.status.value,
            language=updated_session.language,
            created_at=updated_session.created_at,
            updated_at=updated_session.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update session"
        )


@router.delete("/{session_id}")
@timing_decorator
async def delete_session(
    session_id: str = Depends(verify_session_ownership),
    current_user = Depends(get_current_user)
):
    """
    Delete session.
    
    Args:
        session_id: Session ID (verified for ownership)
        current_user: Current authenticated user
    
    Returns:
        Success confirmation
    """
    try:
        success = session_repository.delete_session(session_id, current_user.id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or deletion failed"
            )
        
        logger.success(f"Session deleted: {session_id}")
        
        return {"message": "Session deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete session"
        )


@router.get("/{session_id}/audio_files")
@timing_decorator
async def get_session_audio_files(
    session_id: str = Depends(verify_session_ownership),
    current_user = Depends(get_current_user)
):
    """
    Get audio files for a session.
    
    Args:
        session_id: Session ID (verified for ownership)
        current_user: Current authenticated user
    
    Returns:
        List of audio files for the session
    """
    try:
        logger.info(f"Getting audio files for session: {session_id}")
        
        # Query audio_files table from database
        from core.database import db_manager
        client = db_manager.get_service_client()
        
        result = client.table('audio_files').select('*').eq('session_id', session_id).execute()
        
        if result.data:
            logger.success(f"Found {len(result.data)} audio files for session: {session_id}")
            return result.data
        else:
            logger.info(f"No audio files found for session: {session_id}")
            return []
        
    except Exception as e:
        logger.error(f"Failed to get audio files for session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audio files"
        )


@router.post("/{session_id}/rename-speaker")
@timing_decorator
async def rename_speaker(
    session_id: str,
    request: Dict[str, str],
    current_user = Depends(get_current_user)
):
    """
    Rename speaker in session transcriptions.
    
    Args:
        session_id: Session ID
        request: Dictionary with oldSpeaker and newSpeaker
        current_user: Current authenticated user
    
    Returns:
        Success confirmation
    """
    try:
        # Verify session ownership
        session = session_repository.get_session_by_id(session_id, current_user.id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        old_speaker = request.get("oldSpeaker")
        new_speaker = request.get("newSpeaker")
        
        if not old_speaker or not new_speaker:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="oldSpeaker and newSpeaker are required"
            )
        
        if old_speaker == new_speaker:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New speaker name must be different from old speaker name"
            )
        
        logger.info(f"Renaming speaker in session {session_id}: '{old_speaker}' -> '{new_speaker}'")
        
        # Update speaker names in transcriptions
        from core.database import db_manager
        client = db_manager.get_service_client()
        
        # Update transcriptions - modify segments to replace speaker names
        transcriptions_result = client.table('transcriptions')\
            .select('*')\
            .eq('session_id', session_id)\
            .execute()
        
        updated_count = 0
        if transcriptions_result.data:
            for transcription in transcriptions_result.data:
                segments = transcription.get('segments', [])
                updated_segments = []
                segment_updated = False
                
                for segment in segments:
                    updated_segment = segment.copy()
                    if updated_segment.get('speaker') == old_speaker:
                        updated_segment['speaker'] = new_speaker
                        segment_updated = True
                    updated_segments.append(updated_segment)
                
                # Only update if segments were actually changed
                if segment_updated:
                    client.table('transcriptions')\
                        .update({
                            'segments': updated_segments, 
                            'updated_at': datetime.utcnow().isoformat()
                        })\
                        .eq('id', transcription['id'])\
                        .execute()
                    updated_count += 1
        
        logger.success(f"Speaker renamed successfully in session {session_id}, updated {updated_count} transcriptions")
        
        return {
            "success": True,
            "message": f"Speaker renamed from '{old_speaker}' to '{new_speaker}'",
            "session_id": session_id,
            "updated_count": updated_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rename speaker in session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rename speaker"
        )
