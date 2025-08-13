"""
领域模型
定义应用的核心业务实体
"""
from enum import Enum
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid


class SessionStatus(str, Enum):
    """会话状态枚举"""
    CREATED = "created"
    RECORDING = "recording"  
    PAUSED = "paused"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class TranscriptionStatus(str, Enum):
    """转录状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AISummaryStatus(str, Enum):
    """AI总结状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AudioUploadStatus(str, Enum):
    """音频上传状态枚举"""
    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


class User(BaseModel):
    """用户模型"""
    id: str
    email: Optional[str] = None
    created_at: Optional[datetime] = None
    last_sign_in_at: Optional[datetime] = None


class UserProfile(BaseModel):
    """用户业务资料模型"""
    user_id: str
    subscription_plan: str = "free"
    subscription_status: str = "active"
    subscription_expires_at: Optional[datetime] = None
    quotas: Dict[str, Any] = {}
    preferences: Dict[str, Any] = {}
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Session(BaseModel):
    """录制会话模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str
    status: SessionStatus = SessionStatus.CREATED
    language: str = "zh-CN"
    stt_model: str = "whisper"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    metadata: Dict[str, Any] = {}


class AudioFile(BaseModel):
    """音频文件模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    original_filename: Optional[str] = None
    storage_path: Optional[str] = None
    public_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    format: str = "mp3"
    sample_rate: Optional[int] = None
    channels: int = 1
    upload_status: AudioUploadStatus = AudioUploadStatus.PENDING
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TranscriptionSegment(BaseModel):
    """转录片段模型"""
    index: int
    speaker: Optional[str] = None
    start_time: float  # 秒
    end_time: float    # 秒
    text: str
    confidence_score: Optional[float] = None
    is_final: bool = False


class Transcription(BaseModel):
    """转录记录模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    content: str
    language: str = "zh-CN"
    confidence_score: Optional[float] = None
    segments: List[TranscriptionSegment] = []
    stt_model: str = "whisper"
    stt_provider: str = "local"
    word_count: Optional[int] = None
    status: TranscriptionStatus = TranscriptionStatus.PENDING
    processing_time_ms: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AISummary(BaseModel):
    """AI总结模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    transcription_id: str
    summary: str
    key_points: List[str] = []
    action_items: List[str] = []
    ai_model: str
    ai_provider: str = "litellm"
    quality_rating: Optional[float] = None
    status: AISummaryStatus = AISummaryStatus.PENDING
    processing_time_ms: Optional[int] = None
    token_usage: Dict[str, Any] = {}
    cost_cents: Optional[int] = None
    template_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SessionCache(BaseModel):
    """会话缓存模型 - 用于存储活跃会话的实时数据"""
    session_id: str
    user_id: str
    audio_segments: List[Dict[str, Any]] = []  # 音频片段缓存
    transcription_segments: List[TranscriptionSegment] = []  # 转录片段缓存
    start_time: datetime
    last_activity: datetime
    sample_rate: Optional[int] = None
    metadata: Dict[str, Any] = {}
    
    class Config:
        arbitrary_types_allowed = True 