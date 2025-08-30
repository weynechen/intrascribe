"""
Session management API routes.
Handles CRUD operations for recording sessions.
"""
import os
import sys
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from datetime import datetime
from pydantic import BaseModel

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.models import SessionData, SessionStatus
from shared.utils import timing_decorator, generate_id

from core.auth import get_current_user, verify_session_ownership
from repositories.session_repository import session_repository
from schemas import UpdateSessionTemplateRequest
from routers.transcriptions import transcription_repository, _process_batch_audio_file

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
    template_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RetranscribeResponse(BaseModel):
    """Response model for retranscribe operation"""
    success: bool
    message: str
    session_id: str
    task_id: Optional[str] = None
    transcription_id: Optional[str] = None


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
            template_id=session.template_id,
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
            template_id=session.template_id,
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
                template_id=session.template_id,
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


@router.put("/{session_id}/template", response_model=SessionResponse)
@timing_decorator
async def update_session_template(
    request: UpdateSessionTemplateRequest,
    session_id: str = Depends(verify_session_ownership),
    current_user = Depends(get_current_user)
):
    """
    Update session template.
    
    Args:
        request: Template update request
        session_id: Session ID (verified for ownership)
        current_user: Current authenticated user
    
    Returns:
        Updated session data
    """
    try:
        # Verify session ownership
        session = session_repository.get_session_by_id(session_id, current_user.id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # Verify template exists and belongs to user
        from repositories.user_repository import template_repository
        template = template_repository.get_template_by_id(request.template_id, current_user.id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found"
            )
        
        logger.info(f"Updating template for session {session_id} to template {request.template_id}")
        
        # Update session template_id in database
        from core.database import db_manager
        client = db_manager.get_service_client()
        
        result = client.table('recording_sessions')\
            .update({
                "template_id": request.template_id,
                "updated_at": datetime.utcnow().isoformat()
            })\
            .eq('id', session_id)\
            .eq('user_id', current_user.id)\
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or update failed"
            )
        
        # Get updated session
        updated_session = session_repository.get_session_by_id(session_id, current_user.id)
        
        if not updated_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Failed to retrieve updated session"
            )
        
        logger.success(f"Session template updated: {session_id} -> template {request.template_id}")
        
        return SessionResponse(
            id=updated_session.id,
            title=updated_session.title,
            status=updated_session.status.value,
            language=updated_session.language,
            template_id=updated_session.template_id,
            created_at=updated_session.created_at,
            updated_at=updated_session.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update session template {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update session template"
        )


async def _download_audio_from_storage(storage_path: str, storage_bucket: str = "audio-recordings") -> bytes:
    """Download audio file from Supabase Storage"""
    try:
        from core.database import db_manager
        client = db_manager.get_service_client()
        
        logger.info(f"Downloading audio file from storage: {storage_path}")
        
        # Download file from storage
        result = client.storage.from_(storage_bucket).download(storage_path)
        
        if not result:
            raise Exception("Failed to download audio file from storage")
        
        logger.success(f"Audio file downloaded successfully: {len(result)} bytes")
        return result
        
    except Exception as e:
        logger.error(f"Failed to download audio from storage: {e}")
        raise


async def _retranscribe_session_audio(session_id: str, user_id: str, language: str = "zh-CN", task_id: str = None) -> Dict[str, Any]:
    """Retranscribe audio for an existing session with progress tracking"""
    try:
        logger.info(f"Starting retranscription for session: {session_id}")
        
        # Import tasks_v2 for progress updates
        from routers.tasks_v2 import update_task_status
        
        # Update progress: Finding audio files
        if task_id:
            update_task_status(task_id, "started", progress={"step": "finding_audio", "percentage": 15})
        
        # Get session's audio files
        from core.database import db_manager
        client = db_manager.get_service_client()
        
        audio_files_result = client.table('audio_files')\
            .select('*')\
            .eq('session_id', session_id)\
            .eq('upload_status', 'completed')\
            .execute()
        
        if not audio_files_result.data:
            return {"success": False, "error": "No audio files found for this session"}
        
        # Update progress: Downloading audio
        if task_id:
            update_task_status(task_id, "started", progress={"step": "downloading_audio", "percentage": 25})
        
        # Use the first available audio file
        audio_file = audio_files_result.data[0]
        storage_path = audio_file['storage_path']
        storage_bucket = audio_file.get('storage_bucket', 'audio-recordings')
        original_filename = audio_file.get('original_filename', f"session_{session_id}.mp3")
        
        # Download audio file from storage
        audio_content = await _download_audio_from_storage(storage_path, storage_bucket)
        
        # Update progress: Cleaning up old transcriptions
        if task_id:
            update_task_status(task_id, "started", progress={"step": "cleaning_old_data", "percentage": 35})
        
        # Determine file format
        file_format = audio_file.get('format', 'mp3')
        
        # Delete existing transcriptions for this session
        logger.info(f"Deleting existing transcriptions for session: {session_id}")
        existing_transcriptions = client.table('transcriptions')\
            .select('id')\
            .eq('session_id', session_id)\
            .execute()
        
        if existing_transcriptions.data:
            for transcription in existing_transcriptions.data:
                client.table('transcriptions')\
                    .delete()\
                    .eq('id', transcription['id'])\
                    .execute()
            logger.info(f"Deleted {len(existing_transcriptions.data)} existing transcriptions")
        
        # Update progress: Processing audio
        if task_id:
            update_task_status(task_id, "started", progress={"step": "processing_audio", "percentage": 50})
        
        # Process audio with new transcription
        processing_result = await _process_batch_audio_file(
            audio_content=audio_content,
            file_format=file_format,
            original_filename=original_filename,
            session_id=session_id,
            user_id=user_id,
            language=language
        )
        
        if processing_result["success"]:
            logger.success(f"Retranscription completed successfully for session: {session_id}")
            return {
                "success": True,
                "session_id": session_id,
                "transcription_id": processing_result.get('transcription_id'),
                "duration_seconds": processing_result.get('duration_seconds'),
                "total_segments": processing_result.get('total_segments'),
                "speaker_count": processing_result.get('speaker_count')
            }
        else:
            logger.error(f"Retranscription failed: {processing_result.get('error')}")
            return {"success": False, "error": processing_result.get('error')}
        
    except Exception as e:
        logger.error(f"Retranscription failed for session {session_id}: {e}")
        return {"success": False, "error": str(e)}


async def _retranscribe_session_background_task(session_id: str, user_id: str, task_id: str, language: str = "zh-CN"):
    """Background task for retranscribing session audio"""
    try:
        # Import tasks_v2 to update task status
        from routers.tasks_v2 import update_task_status
        
        # Update task status to started
        update_task_status(task_id, "started", progress={"step": "downloading_audio", "percentage": 10})
        
        logger.info(f"Starting background retranscription task: {task_id} for session: {session_id}")
        
        # Perform the retranscription with progress tracking
        result = await _retranscribe_session_audio(session_id, user_id, language, task_id)
        
        if result["success"]:
            # Update task status to success
            update_task_status(task_id, "success", 
                progress={"step": "completed", "percentage": 100},
                result={
                    "message": "Session retranscribed successfully",
                    "session_id": session_id,
                    "transcription_id": result.get('transcription_id'),
                    "duration_seconds": result.get('duration_seconds', 0),
                    "total_segments": result.get('total_segments', 0),
                    "speaker_count": result.get('speaker_count', 1)
                }
            )
            logger.success(f"Background retranscription completed: {task_id}")
        else:
            # Update task status to failed
            update_task_status(task_id, "failed", error=result.get('error'))
            logger.error(f"Background retranscription failed: {task_id} - {result.get('error')}")
            
    except Exception as e:
        # Import tasks_v2 to update task status
        from routers.tasks_v2 import update_task_status
        
        logger.error(f"Background retranscription task failed: {task_id} - {e}")
        update_task_status(task_id, "failed", error=str(e))


@router.post("/{session_id}/retranscribe", response_model=RetranscribeResponse)
@timing_decorator
async def retranscribe_session(
    background_tasks: BackgroundTasks,
    session_id: str = Depends(verify_session_ownership),
    current_user = Depends(get_current_user)
):
    """
    Retranscribe session audio using the latest transcription algorithms.
    
    This operation runs asynchronously in the background.
    
    Args:
        background_tasks: FastAPI background tasks
        session_id: Session ID (verified for ownership)  
        current_user: Current authenticated user
    
    Returns:
        Task ID for tracking retranscription progress
    """
    try:
        logger.info(f"Starting retranscription task for session: {session_id}")
        
        # Verify session exists and belongs to user
        session = session_repository.get_session_by_id(session_id, current_user.id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Generate task ID
        task_id = generate_id()
        
        # Import tasks_v2 to initialize task status
        from routers.tasks_v2 import update_task_status
        
        # Initialize task status
        update_task_status(task_id, "pending", progress={"step": "initializing", "percentage": 0})
        
        # Start background task
        background_tasks.add_task(
            _retranscribe_session_background_task,
            session_id,
            current_user.id,
            task_id,
            session.language
        )
        
        logger.success(f"Retranscription task started: {task_id} for session: {session_id}")
        
        return RetranscribeResponse(
            success=True,
            message="Retranscription task started successfully",
            session_id=session_id,
            task_id=task_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start retranscription task for session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start retranscription task"
        )
