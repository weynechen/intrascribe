"""
AI services API routes.
Handles AI-powered tasks like summarization and title generation.
"""
import os
import sys
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status

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

logger = ServiceLogger("ai-services-api")

router = APIRouter(tags=["AI Services"])


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


# Global repository instance
ai_summary_repository = AISummaryRepository()


@router.post("/summarize", response_model=SummarizeResponse)
@timing_decorator
async def generate_summary(
    request: SummarizeRequest,
    current_user = Depends(get_current_user)
):
    """
    Generate AI summary for transcription text.
    
    Args:
        request: Summarization request
        current_user: Current authenticated user
    
    Returns:
        Generated summary
    """
    try:
        logger.info(f"Processing summarization request for user: {current_user.id}")
        
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
            session_id="direct",  # Direct API call
            template_content=template_content
        )
        
        if result["success"]:
            logger.success(f"Summary generated: {len(result['summary'])} chars")
            
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


@router.post("/generate-title", response_model=GenerateTitleResponse)
@timing_decorator
async def generate_title(
    request: GenerateTitleRequest,
    current_user = Depends(get_current_user)
):
    """
    Generate title for transcription.
    
    Args:
        request: Title generation request
        current_user: Current authenticated user
    
    Returns:
        Generated title
    """
    try:
        logger.info(f"Processing title generation request for user: {current_user.id}")
        
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
            logger.success(f"Title generated: '{result['title']}'")
            
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


@router.post("/save_ai_summaries", response_model=AISummaryResponse)
@timing_decorator
async def save_ai_summary(
    request: AISummarySaveRequest,
    current_user = Depends(get_current_user)
):
    """
    Save AI summary data.
    
    Args:
        request: AI summary save request
        current_user: Current authenticated user
    
    Returns:
        Saved AI summary data
    """
    try:
        # Verify session ownership
        session = session_repository.get_session_by_id(request.session_id, current_user.id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # Save AI summary
        summary = ai_summary_repository.save_ai_summary(
            session_id=request.session_id,
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
        
        logger.success(f"Saved AI summary: {summary['id']}")
        
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
