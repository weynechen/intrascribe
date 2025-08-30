"""
API Schema definitions for the Intrascribe platform.
Defines request and response models for all API endpoints.
"""
import os
import sys
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.models import SessionStatus


# =============== Common Response Formats ===============

class HealthResponse(BaseModel):
    """Health check response"""
    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


class ErrorResponse(BaseModel):
    """Standard error response format"""
    error: Dict[str, Any]


class BaseResponse(BaseModel):
    """Base response format"""
    success: bool = True
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# =============== User Management ===============

class UserProfileResponse(BaseModel):
    """User profile response"""
    subscription: Dict[str, Any]
    quotas: Dict[str, Any] 
    preferences: Dict[str, Any]


class UserPreferencesRequest(BaseModel):
    """User preferences update request"""
    default_language: Optional[str] = None
    auto_summary: Optional[bool] = None
    default_stt_model: Optional[str] = None
    notification_settings: Optional[Dict[str, Any]] = None


# =============== Session Management ===============

class CreateSessionRequest(BaseModel):
    """Create session request"""
    title: str = Field(..., min_length=1, max_length=200)
    language: str = Field(default="zh-CN", pattern=r"^[a-z]{2}-[A-Z]{2}$")
    stt_model: str = Field(default="local_funasr")


class SessionResponse(BaseModel):
    """Session response"""
    id: str
    title: str
    status: str
    language: str
    template_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    
    @classmethod
    def created(cls, session_data: Dict[str, Any]):
        return cls(**session_data)
    
    @classmethod
    def deleted(cls, session_id: str):
        return cls(
            id=session_id,
            title="",
            status="deleted",
            language="",
            created_at=datetime.utcnow()
        )


class SessionDetailResponse(BaseModel):
    """Detailed session response"""
    id: str
    title: str
    status: str
    created_at: datetime
    language: str
    duration_seconds: Optional[float] = None
    transcriptions: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []
    audio_files: List[Dict[str, Any]] = []


class UpdateSessionRequest(BaseModel):
    """Update session request"""
    title: Optional[str] = None
    status: Optional[str] = None


class RenameSpeakerRequest(BaseModel):
    """Rename speaker request"""
    old_speaker: str = Field(..., alias="oldSpeaker")
    new_speaker: str = Field(..., alias="newSpeaker")


class UpdateSessionTemplateRequest(BaseModel):
    """Update session template request"""
    template_id: Optional[str] = None


# =============== Template Management ===============

class SummaryTemplateRequest(BaseModel):
    """Summary template request"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    template_content: str = Field(..., min_length=1)
    category: str = Field(default="general")
    is_default: bool = Field(default=False)
    is_active: bool = Field(default=True)
    tags: List[str] = Field(default=[])


class SummaryTemplateResponse(BaseModel):
    """Summary template response"""
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    template_content: str
    category: str
    is_default: bool
    is_active: bool
    tags: List[str]
    created_at: datetime
    updated_at: Optional[datetime] = None


# =============== Transcription Management ===============

class TranscriptionSegment(BaseModel):
    """Transcription segment"""
    index: int
    speaker: Optional[str] = None
    start_time: float
    end_time: float
    text: str
    confidence_score: Optional[float] = None
    is_final: bool = False


class TranscriptionSaveRequest(BaseModel):
    """Save transcription request"""
    session_id: str
    content: str
    language: str = "zh-CN"
    confidence_score: Optional[float] = None
    segments: List[Dict[str, Any]] = []
    stt_model: str = "local_funasr"
    word_count: Optional[int] = None


class TranscriptionUpdateRequest(BaseModel):
    """Update transcription request"""
    content: Optional[str] = None
    segments: List[Dict[str, Any]] = []


class TranscriptionResponse(BaseModel):
    """Transcription response"""
    id: str
    session_id: str
    content: str
    language: str
    status: str
    word_count: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# =============== AI Services ===============

class SummarizeRequest(BaseModel):
    """Summarization request"""
    transcription_text: str
    template_id: Optional[str] = None


class SummarizeResponse(BaseModel):
    """Summarization response"""
    summary: str
    key_points: List[str] = []
    model_used: str = ""
    processing_time_ms: int = 0


class GenerateTitleRequest(BaseModel):
    """Generate title request"""
    transcription_text: str
    summary_text: Optional[str] = None


class GenerateTitleResponse(BaseModel):
    """Generate title response"""
    title: str
    model_used: str = ""
    processing_time_ms: int = 0


class AISummarySaveRequest(BaseModel):
    """Save AI summary request"""
    session_id: str
    transcription_id: str
    summary: str
    key_points: List[str] = []
    action_items: List[str] = []
    ai_model: str = ""
    ai_provider: str = ""
    processing_time_ms: int = 0
    token_usage: Dict[str, int] = {}
    cost_cents: int = 0


class AISummaryResponse(BaseModel):
    """AI summary response"""
    id: str
    session_id: str
    summary: str
    key_points: List[str] = []
    status: str
    created_at: datetime


# =============== Audio Processing ===============

class AudioUploadResponse(BaseModel):
    """Audio upload response"""
    success: bool
    message: str
    file_id: Optional[str] = None
    file_url: Optional[str] = None


class AudioProcessRequest(BaseModel):
    """Audio processing request"""
    session_id: str
    audio_format: str = "wav"


class AudioCacheStatusResponse(BaseModel):
    """Audio cache status response"""
    total_sessions: int
    cache_size_mb: float
    active_sessions: int
    oldest_session: Optional[str] = None
    cache_memory_usage: Dict[str, Any] = {}


class SetCurrentSessionRequest(BaseModel):
    """Set current session request"""
    session_id: str


class CurrentSessionResponse(BaseModel):
    """Current session response"""
    session_id: Optional[str] = None
    status: str


# =============== Batch Processing ===============

class BatchTranscriptionRequest(BaseModel):
    """Batch transcription request"""
    audio_file_url: str
    session_title: str = "Batch Transcription Session"
    language: str = "zh-CN"
    stt_model: str = "local_funasr"


class BatchTranscriptionResponse(BaseModel):
    """Batch transcription response"""
    task_id: str
    session_id: str
    status: str
    message: str


# =============== LiveKit Integration ===============

class LiveKitConnectionRequest(BaseModel):
    """LiveKit connection request"""
    session_id: str
    user_identity: Optional[str] = None


class LiveKitConnectionResponse(BaseModel):
    """LiveKit connection response"""
    room_name: str
    access_token: str
    room_url: str
    session_id: str


# =============== Task Management ===============

class TaskStatusResponse(BaseModel):
    """Task status response"""
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    progress: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None


class AsyncTaskResponse(BaseModel):
    """Async task submission response"""
    task_id: str
    status: str
    message: str
    poll_url: str
