"""
Transcription management API routes.
Handles transcription CRUD operations and real-time transcription data.
"""
import os
import sys
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from datetime import datetime

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.utils import timing_decorator
from shared.models import AudioData

from core.auth import get_current_user, verify_session_ownership
from schemas import (
    TranscriptionSaveRequest, TranscriptionUpdateRequest, 
    TranscriptionResponse, BatchTranscriptionRequest, BatchTranscriptionResponse
)
from clients.microservice_clients import stt_client
from repositories.session_repository import session_repository

logger = ServiceLogger("transcriptions-api")

router = APIRouter(prefix="/transcriptions", tags=["Transcriptions"])


class TranscriptionRepository:
    """Repository for transcription operations"""
    
    def __init__(self):
        from core.database import db_manager
        self.db = db_manager
    
    def save_transcription(
        self,
        session_id: str,
        content: str,
        language: str = "zh-CN",
        confidence_score: float = None,
        segments: List[Dict[str, Any]] = None,
        stt_model: str = "local_funasr",
        word_count: int = None
    ) -> Dict[str, Any]:
        """Save transcription to database"""
        try:
            client = self.db.get_service_client()
            
            transcription_data = {
                "session_id": session_id,
                "content": content,
                "language": language,
                "confidence_score": confidence_score,
                "segments": segments or [],
                "stt_model": stt_model,
                "word_count": word_count or len(content.split()),
                "status": "completed",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            result = client.table('transcriptions').insert(transcription_data).execute()
            
            if not result.data:
                raise Exception("Failed to save transcription")
            
            return result.data[0]
            
        except Exception as e:
            logger.error(f"Failed to save transcription: {e}")
            raise
    
    def get_session_transcriptions(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all transcriptions for a session"""
        try:
            client = self.db.get_service_client()
            
            result = client.table('transcriptions')\
                .select('*')\
                .eq('session_id', session_id)\
                .order('created_at')\
                .execute()
            
            return result.data
            
        except Exception as e:
            logger.error(f"Failed to get transcriptions for session {session_id}: {e}")
            return []


# Global repository instance
transcription_repository = TranscriptionRepository()


@router.post("/", response_model=TranscriptionResponse)
@timing_decorator
async def save_transcription(
    request: TranscriptionSaveRequest,
    current_user = Depends(get_current_user)
):
    """
    Save transcription data.
    
    Args:
        request: Transcription save request
        current_user: Current authenticated user
    
    Returns:
        Saved transcription data
    """
    try:
        # Verify session ownership
        session = session_repository.get_session_by_id(request.session_id, current_user.id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # Save transcription
        transcription = transcription_repository.save_transcription(
            session_id=request.session_id,
            content=request.content,
            language=request.language,
            confidence_score=request.confidence_score,
            segments=request.segments,
            stt_model=request.stt_model,
            word_count=request.word_count
        )
        
        logger.success(f"Saved transcription: {transcription['id']}")
        
        return TranscriptionResponse(
            id=transcription["id"],
            session_id=transcription["session_id"],
            content=transcription["content"],
            language=transcription["language"],
            status=transcription["status"],
            word_count=transcription["word_count"],
            created_at=transcription["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save transcription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save transcription"
        )


@router.put("/{transcription_id}", response_model=TranscriptionResponse)
@timing_decorator
async def update_transcription(
    transcription_id: str,
    request: TranscriptionUpdateRequest,
    current_user = Depends(get_current_user)
):
    """
    Update transcription data.
    
    Args:
        transcription_id: Transcription ID
        request: Transcription update request
        current_user: Current authenticated user
    
    Returns:
        Updated transcription data
    """
    try:
        client = transcription_repository.db.get_service_client()
        
        # Verify transcription exists and user has access
        transcription_result = client.table('transcriptions').select('*').eq('id', transcription_id).execute()
        
        if not transcription_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transcription not found"
            )
        
        transcription = transcription_result.data[0]
        
        # Verify session ownership
        session = session_repository.get_session_by_id(transcription["session_id"], current_user.id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this transcription"
            )
        
        # Update transcription
        updates = {}
        
        if request.content is not None:
            updates["content"] = request.content
            updates["word_count"] = len(request.content.split())
        
        if request.segments:
            updates["segments"] = request.segments
            # Rebuild content from segments if not provided
            if request.content is None:
                content = " ".join(segment.get("text", "") for segment in request.segments if segment.get("text"))
                updates["content"] = content
                updates["word_count"] = len(content.split())
        
        if updates:
            updates["updated_at"] = datetime.utcnow().isoformat()
            
            result = client.table('transcriptions')\
                .update(updates)\
                .eq('id', transcription_id)\
                .execute()
            
            if not result.data:
                raise Exception("Transcription update failed")
            
            updated_transcription = result.data[0]
        else:
            updated_transcription = transcription
        
        logger.success(f"Updated transcription: {transcription_id}")
        
        return TranscriptionResponse(
            id=updated_transcription["id"],
            session_id=updated_transcription["session_id"],
            content=updated_transcription["content"],
            language=updated_transcription["language"],
            status=updated_transcription["status"],
            word_count=updated_transcription["word_count"],
            created_at=updated_transcription["created_at"],
            updated_at=updated_transcription.get("updated_at")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update transcription {transcription_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update transcription"
        )


@router.post("/batch", response_model=BatchTranscriptionResponse)
@timing_decorator
async def batch_transcription(
    audio_file: UploadFile = File(...),
    title: str = "Batch Transcription Session",
    language: str = "zh-CN",
    current_user = Depends(get_current_user)
):
    """
    Batch transcription for uploaded audio file.
    
    Args:
        audio_file: Uploaded audio file
        title: Session title
        language: Language code
        current_user: Current authenticated user
    
    Returns:
        Batch transcription task information
    """
    try:
        logger.info(f"Processing batch transcription: {audio_file.filename}")
        
        # Create session for batch processing
        session = session_repository.create_session(
            user_id=current_user.id,
            title=title,
            language=language
        )
        
        # Read audio file
        audio_content = await audio_file.read()
        
        # Determine audio format
        file_format = "wav"
        if audio_file.filename:
            file_format = audio_file.filename.split('.')[-1].lower()
        
        # Convert to AudioData format
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
        
        # Call STT service
        transcription_result = await stt_client.transcribe_audio(
            audio_data_obj, 
            session.id, 
            language
        )
        
        if transcription_result.success:
            # Save transcription
            transcription = transcription_repository.save_transcription(
                session_id=session.id,
                content=transcription_result.text,
                language=language,
                confidence_score=transcription_result.confidence_score,
                stt_model="local_funasr",
                word_count=len(transcription_result.text.split())
            )
            
            logger.success(f"Batch transcription completed: {session.id}")
            
            return BatchTranscriptionResponse(
                task_id=session.id,  # Use session ID as task ID
                session_id=session.id,
                status="completed",
                message="Batch transcription completed successfully"
            )
        else:
            logger.error(f"Batch transcription failed: {transcription_result.error_message}")
            
            return BatchTranscriptionResponse(
                task_id=session.id,
                session_id=session.id,
                status="failed",
                message=f"Transcription failed: {transcription_result.error_message}"
            )
        
    except Exception as e:
        logger.error(f"Batch transcription failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Batch transcription failed"
        )
