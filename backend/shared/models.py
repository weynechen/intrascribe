"""
Shared data models used across microservices.
Defines common data structures for API communication and data transfer.
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class SessionStatus(str, Enum):
    """Session status enumeration"""
    CREATED = "created"
    RECORDING = "recording"
    PAUSED = "paused"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class TaskStatus(str, Enum):
    """Task status enumeration"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AudioData:
    """Audio data structure for inter-service communication"""
    sample_rate: int
    audio_array: List[float]
    format: str = "wav"
    duration_seconds: Optional[float] = None


@dataclass
class TranscriptionSegment:
    """Single transcription segment"""
    index: int
    speaker: str
    start_time: float
    end_time: float
    text: str
    confidence_score: float = 1.0
    is_final: bool = True


@dataclass
class SpeakerSegment:
    """Speaker diarization segment"""
    start_time: float
    end_time: float
    speaker_label: str
    duration: float


@dataclass
class TranscriptionRequest:
    """STT service request model"""
    audio_data: AudioData
    session_id: str
    language: str = "zh-CN"


@dataclass
class TranscriptionResponse:
    """STT service response model"""
    success: bool
    text: str
    confidence_score: float = 1.0
    processing_time_ms: int = 0
    error_message: Optional[str] = None


@dataclass
class SpeakerDiarizationRequest:
    """Speaker diarization request model"""
    audio_data: bytes
    file_format: str
    session_id: str


@dataclass
class SpeakerDiarizationResponse:
    """Speaker diarization response model"""
    success: bool
    segments: List[SpeakerSegment]
    speaker_count: int
    processing_time_ms: int = 0
    error_message: Optional[str] = None


@dataclass
class AISummaryRequest:
    """AI summary request model"""
    transcription_text: str
    session_id: str
    user_id: str
    template_id: Optional[str] = None


@dataclass
class AISummaryResponse:
    """AI summary response model"""
    success: bool
    summary: str
    key_points: List[str] = None
    processing_time_ms: int = 0
    model_used: str = ""
    error_message: Optional[str] = None


@dataclass
class SessionData:
    """Session data structure"""
    id: str
    user_id: str
    title: str
    status: SessionStatus
    language: str = "zh-CN"
    stt_model: str = "whisper"
    metadata: Dict[str, Any] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


@dataclass
class UserData:
    """User data structure"""
    id: str
    email: str
    username: str
    full_name: str
    is_active: bool = True
    is_verified: bool = False
    created_at: Optional[datetime] = None


@dataclass
class ServiceHealthCheck:
    """Service health check response"""
    service_name: str
    status: str
    version: str
    uptime_seconds: int
    details: Dict[str, Any] = None
