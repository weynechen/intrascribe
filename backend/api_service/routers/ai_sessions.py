"""
AI Sessions API routes.
Handles AI-powered tasks for specific sessions like summarization and title generation.
"""
import os
import sys
import uuid
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.utils import timing_decorator

from core.auth import get_current_user, verify_session_ownership
from schemas import (
    SummarizeRequest, SummarizeResponse, GenerateTitleRequest, GenerateTitleResponse,
    AISummarySaveRequest, AISummaryResponse
)
from services.ai_service import ai_service
from repositories.session_repository import session_repository
from routers.transcriptions import transcription_repository
from routers.tasks_v2 import update_task_status

logger = ServiceLogger("ai-sessions-api")

class AISummaryRequest(BaseModel):
    """AI Summary request model"""
    template_id: Optional[str] = None

router = APIRouter(prefix="/v2/sessions", tags=["AI Sessions"])


class AISummaryRepository:
    """Repository for AI summary operations"""
    
    def __init__(self):
        from core.database import db_manager
        self.db = db_manager
    
    def save_ai_summary(
        self,
        session_id: str,
        transcription_id: str,
        summary: str,
        key_points: List[str] = None,
        action_items: List[str] = None,
        ai_model: str = "",
        ai_provider: str = "",
        processing_time_ms: int = 0,
        token_usage: Dict[str, int] = None,
        cost_cents: int = 0
    ) -> Dict[str, Any]:
        """Save AI summary to database"""
        try:
            client = self.db.get_service_client()
            
            summary_data = {
                "session_id": session_id,
                "transcription_id": transcription_id,
                "summary": summary,
                "key_points": key_points or [],
                "action_items": action_items or [],
                "ai_model": ai_model,
                "ai_provider": ai_provider,
                "processing_time_ms": processing_time_ms,
                "token_usage": token_usage or {},
                "cost_cents": cost_cents,
                "status": "completed",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            result = client.table('ai_summaries').insert(summary_data).execute()
            
            if not result.data:
                raise Exception("Failed to save AI summary")
            
            return result.data[0]
            
        except Exception as e:
            logger.error(f"Failed to save AI summary: {e}")
            raise
    
    def update_ai_summary(
        self,
        summary_id: str,
        session_id: str,
        summary: str,
        key_points: List[str] = None,
        action_items: List[str] = None,
        ai_model: str = "user_edited",
        ai_provider: str = "manual"
    ) -> Dict[str, Any]:
        """Update existing AI summary"""
        try:
            client = self.db.get_service_client()
            
            update_data = {
                "summary": summary,
                "key_points": key_points or [],
                "action_items": action_items or [],
                "ai_model": ai_model,
                "ai_provider": ai_provider,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            result = client.table('ai_summaries')\
                .update(update_data)\
                .eq('id', summary_id)\
                .eq('session_id', session_id)\
                .execute()
            
            if not result.data:
                raise Exception("Failed to update AI summary")
            
            return result.data[0]
            
        except Exception as e:
            logger.error(f"Failed to update AI summary: {e}")
            raise


# Global repository instance
ai_summary_repository = AISummaryRepository()


async def _process_ai_summary_task(task_id: str, session_id: str, user_id: str, template_id: str = None):
    """
    Background task to process AI summary generation.
    
    Args:
        task_id: Task ID for status tracking
        session_id: Session ID to process
        user_id: User ID for permission verification
    """
    try:
        logger.info(f"Starting AI summary task: {task_id}")
        
        # Update task status to started
        update_task_status(task_id, "started", 
                          progress={"step": "fetching_transcriptions", "percentage": 20})
        
        # Get session data
        session = session_repository.get_session_by_id(session_id, user_id)
        if not session:
            update_task_status(task_id, "failed", 
                              error="Session not found or access denied")
            return
        
        # Get session transcriptions
        transcriptions = transcription_repository.get_session_transcriptions(session_id)
        if not transcriptions:
            update_task_status(task_id, "failed", 
                              error="No transcriptions found for this session")
            return
        
        # Update progress
        update_task_status(task_id, "started", 
                          progress={"step": "combining_transcriptions", "percentage": 40})
        
        # Combine all transcription text
        combined_text = ""
        transcription_ids = []
        
        for transcription in transcriptions:
            if transcription.get("content"):
                combined_text += transcription["content"] + "\n\n"
                transcription_ids.append(transcription["id"])
        
        if not combined_text.strip():
            update_task_status(task_id, "failed", 
                              error="No transcription text found in session")
            return
        
        # Update progress
        update_task_status(task_id, "started", 
                          progress={"step": "preparing_ai_request", "percentage": 60})
        
        # Get template content if specified (priority: parameter > session metadata)
        template_content = None
        effective_template_id = template_id or (session.metadata.get("template_id") if session.metadata else None)
        if effective_template_id:
            from ..repositories.user_repository import template_repository
            template = template_repository.get_template_by_id(effective_template_id, user_id)
            if template:
                template_content = template["template_content"]
                logger.info(f"Using template for AI summary: {effective_template_id}")
        
        # Update progress
        update_task_status(task_id, "started", 
                          progress={"step": "generating_summary", "percentage": 80})
        
        # Generate summary using AI service
        result = await ai_service.generate_summary(
            combined_text,
            session_id=session_id,
            template_content=template_content
        )
        
        if result["success"]:
            # Save AI summary to database (use first transcription_id for UUID field)
            primary_transcription_id = transcription_ids[0] if transcription_ids else None
            if not primary_transcription_id:
                update_task_status(task_id, "failed", 
                                  error="No valid transcription ID found")
                return
            
            summary_data = ai_summary_repository.save_ai_summary(
                session_id=session_id,
                transcription_id=primary_transcription_id,
                summary=result["summary"],
                key_points=result.get("key_points", []),
                action_items=result.get("action_items", []),
                ai_model=result.get("ai_model", ""),
                ai_provider=result.get("ai_provider", ""),
                processing_time_ms=result.get("processing_time_ms", 0),
                token_usage=result.get("token_usage", {}),
                cost_cents=result.get("cost_cents", 0)
            )
            
            # Update task status to success
            update_task_status(task_id, "success", 
                              progress={"step": "completed", "percentage": 100},
                              result={
                                  "summary_id": summary_data["id"],
                                  "session_id": summary_data["session_id"],
                                  "summary": summary_data["summary"],
                                  "key_points": summary_data["key_points"],
                                  "status": summary_data["status"],
                                  "created_at": summary_data["created_at"],
                                  "model_used": result.get("model_used", ""),
                                  "processing_time_ms": result.get("processing_time_ms", 0),
                                  "token_usage": result.get("token_usage", {}),
                                  "cost_cents": result.get("cost_cents", 0)
                              })
            
            logger.success(f"AI summary task completed: {task_id}")
            
        else:
            # Update task status to failed
            update_task_status(task_id, "failed", 
                              error=f"AI summary generation failed: {result['error_message']}")
            logger.error(f"AI summary task failed: {task_id} - {result['error_message']}")
        
    except Exception as e:
        logger.error(f"AI summary task error: {task_id} - {e}")
        update_task_status(task_id, "failed", error=str(e))


@router.post("/{session_id}/ai-summary")
@timing_decorator
async def generate_session_ai_summary(
    session_id: str,
    request: AISummaryRequest,
    background_tasks: BackgroundTasks,
    current_user = Depends(get_current_user)
):
    """
    Generate AI summary for a session's transcriptions (async task).
    
    Args:
        session_id: Session ID to generate summary for
        background_tasks: FastAPI background tasks
        current_user: Current authenticated user
    
    Returns:
        Task information for polling
    """
    try:
        logger.info(f"Submitting AI summary task for session: {session_id}, user: {current_user.id}")
        
        # Verify session ownership
        session = session_repository.get_session_by_id(session_id, current_user.id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # Check if AI service is available
        if not ai_service.is_available():
            logger.error("AI service not available")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI services not available - check API key configuration"
            )
        
        # Generate unique task ID
        task_id = f"ai-summary-{session_id}-{uuid.uuid4().hex[:8]}"
        
        # Initialize task status
        update_task_status(task_id, "pending", 
                          progress={"step": "initializing", "percentage": 0},
                          result=None)
        
        # Start background task
        background_tasks.add_task(
            _process_ai_summary_task,
            task_id=task_id,
            session_id=session_id,
            user_id=current_user.id,
            template_id=request.template_id
        )
        
        logger.info(f"AI summary task submitted: {task_id}")
        
        return {
            "success": True,
            "message": "AI summary task submitted",
            "task_id": task_id,
            "status": "pending",
            "poll_url": f"/api/v2/tasks/{task_id}",
            "estimated_duration": 30
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI summary request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI summary generation failed"
        )


@router.post("/{session_id}/summarize", response_model=SummarizeResponse)
@timing_decorator
async def generate_session_summary(
    session_id: str,
    request: SummarizeRequest,
    current_user = Depends(get_current_user)
):
    """
    Generate AI summary for specific transcription text within a session.
    
    Args:
        session_id: Session ID for verification
        request: Summarization request
        current_user: Current authenticated user
    
    Returns:
        Generated summary
    """
    try:
        logger.info(f"Processing summarization request for session: {session_id}, user: {current_user.id}")
        
        # Verify session ownership
        session = session_repository.get_session_by_id(session_id, current_user.id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # Validate input
        if not request.transcription_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transcription text cannot be empty"
            )
        
        # Check if AI service is available
        if not ai_service.is_available():
            logger.error("AI service not available")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI services not available - check API key configuration"
            )
        
        # Get template content if template ID provided
        template_content = None
        if request.template_id:
            from ..repositories.user_repository import template_repository
            template = template_repository.get_template_by_id(request.template_id, current_user.id)
            if template:
                template_content = template["template_content"]
        
        # Generate summary
        result = await ai_service.generate_summary(
            request.transcription_text,
            session_id=session_id,
            template_content=template_content
        )
        
        if result["success"]:
            logger.success(f"Summary generated for session {session_id}: {len(result['summary'])} chars")
            
            return SummarizeResponse(
                summary=result["summary"],
                key_points=result["key_points"],
                model_used=result["model_used"],
                processing_time_ms=result["processing_time_ms"]
            )
        else:
            logger.error(f"Summary generation failed: {result['error_message']}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Summary generation failed: {result['error_message']}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Summarization request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Summarization failed"
        )


@router.post("/{session_id}/generate-title", response_model=GenerateTitleResponse)
@timing_decorator
async def generate_session_title(
    session_id: str,
    request: GenerateTitleRequest,
    current_user = Depends(get_current_user)
):
    """
    Generate title for session transcription.
    
    Args:
        session_id: Session ID for verification
        request: Title generation request
        current_user: Current authenticated user
    
    Returns:
        Generated title
    """
    try:
        logger.info(f"Processing title generation request for session: {session_id}, user: {current_user.id}")
        
        # Verify session ownership
        session = session_repository.get_session_by_id(session_id, current_user.id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # Validate input
        if not request.transcription_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transcription text cannot be empty"
            )
        
        # Check if AI service is available
        if not ai_service.is_available():
            logger.error("AI service not available")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI services not available - check API key configuration"
            )
        
        # Generate title
        result = await ai_service.generate_title(
            request.transcription_text,
            request.summary_text
        )
        
        if result["success"]:
            logger.success(f"Title generated for session {session_id}: '{result['title']}'")
            
            return GenerateTitleResponse(
                title=result["title"],
                model_used=result["model_used"],
                processing_time_ms=result["processing_time_ms"]
            )
        else:
            logger.error(f"Title generation failed: {result['error_message']}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Title generation failed: {result['error_message']}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Title generation request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Title generation failed"
        )


@router.post("/{session_id}/save-ai-summary", response_model=AISummaryResponse)
@timing_decorator
async def save_session_ai_summary(
    session_id: str,
    request: AISummarySaveRequest,
    current_user = Depends(get_current_user)
):
    """
    Save AI summary data for a session.
    
    Args:
        session_id: Session ID for verification
        request: AI summary save request
        current_user: Current authenticated user
    
    Returns:
        Saved AI summary data
    """
    try:
        # Verify session ownership
        session = session_repository.get_session_by_id(session_id, current_user.id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # Ensure request session_id matches path session_id
        if request.session_id != session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session ID mismatch between path and request body"
            )
        
        # Save AI summary
        summary = ai_summary_repository.save_ai_summary(
            session_id=session_id,
            transcription_id=request.transcription_id,
            summary=request.summary,
            key_points=request.key_points,
            action_items=request.action_items,
            ai_model=request.ai_model,
            ai_provider=request.ai_provider,
            processing_time_ms=request.processing_time_ms,
            token_usage=request.token_usage,
            cost_cents=request.cost_cents
        )
        
        logger.success(f"Saved AI summary for session {session_id}: {summary['id']}")
        
        return AISummaryResponse(
            id=summary["id"],
            session_id=summary["session_id"],
            summary=summary["summary"],
            key_points=summary["key_points"],
            status=summary["status"],
            created_at=summary["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save AI summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save AI summary"
        )


@router.put("/{session_id}/ai-summaries/{summary_id}", response_model=AISummaryResponse)
@timing_decorator
async def update_session_ai_summary(
    session_id: str,
    summary_id: str,
    request: AISummarySaveRequest,
    current_user = Depends(get_current_user)
):
    """
    Update AI summary for a session.
    
    Args:
        session_id: Session ID for verification
        summary_id: AI summary ID to update
        request: AI summary update request
        current_user: Current authenticated user
    
    Returns:
        Updated AI summary data
    """
    try:
        # Verify session ownership
        session = session_repository.get_session_by_id(session_id, current_user.id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # Ensure request session_id matches path session_id
        if request.session_id != session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session ID mismatch between path and request body"
            )
        
        # Update AI summary
        summary = ai_summary_repository.update_ai_summary(
            summary_id=summary_id,
            session_id=session_id,
            summary=request.summary,
            key_points=request.key_points,
            action_items=request.action_items,
            ai_model=request.ai_model,
            ai_provider=request.ai_provider
        )
        
        logger.success(f"Updated AI summary for session {session_id}: {summary['id']}")
        
        return AISummaryResponse(
            id=summary["id"],
            session_id=summary["session_id"],
            summary=summary["summary"],
            key_points=summary["key_points"],
            status=summary["status"],
            created_at=summary["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update AI summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update AI summary"
        )
