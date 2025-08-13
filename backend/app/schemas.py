"""
数据传输对象 (DTOs)
用于API请求和响应验证的Pydantic模型
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from .models import SessionStatus, TranscriptionStatus, AISummaryStatus, AudioUploadStatus


# =============== 公共API响应格式 ===============
class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


class ErrorResponse(BaseModel):
    """标准错误响应格式"""
    error: Dict[str, Any]


# =============== 用户相关 ===============
class UserProfileResponse(BaseModel):
    """用户业务资料响应"""
    subscription: Dict[str, Any]
    quotas: Dict[str, Any]
    preferences: Dict[str, Any]


class UserPreferencesRequest(BaseModel):
    """用户偏好设置请求"""
    default_language: Optional[str] = None
    auto_summary: Optional[bool] = None


# =============== 会话相关 ===============
class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    title: str = Field(..., min_length=1, max_length=200)
    language: str = Field(default="zh-CN", pattern=r"^[a-z]{2}-[A-Z]{2}$")
    stt_model: str = Field(default="whisper")


class CreateSessionResponse(BaseModel):
    """创建会话响应"""
    session_id: str
    title: str
    status: SessionStatus
    created_at: datetime
    language: str
    usage_hint: str = "Use this 'session_id' as 'webrtc_id' for your WebRTC connection."


class FinalizeSessionResponse(BaseModel):
    """结束会话响应"""
    message: str
    session_id: str
    status: SessionStatus
    final_data: Dict[str, Any]


class SessionDetailResponse(BaseModel):
    """会话详情响应"""
    id: str
    title: str
    status: SessionStatus
    created_at: datetime
    language: str
    duration_seconds: Optional[float] = None
    transcriptions: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []
    audio_files: List[Dict[str, Any]] = []


# =============== 转录相关 ===============
class TranscriptionSegmentResponse(BaseModel):
    """转录片段响应"""
    index: int
    speaker: Optional[str] = None
    timestamp: str  # 格式: "00:00:10:100-00:00:11:800"
    text: str
    is_final: bool = False
    confidence_score: Optional[float] = None


class TranscriptionSaveRequest(BaseModel):
    """保存转录请求"""
    session_id: str
    content: str
    language: str = "zh-CN"
    confidence_score: Optional[float] = None
    segments: List[Dict[str, Any]] = []
    stt_model: str = "whisper"
    word_count: Optional[int] = None


class TranscriptionUpdateRequest(BaseModel):
    """更新转录请求"""
    segments: List[Dict[str, Any]]
    
    
class TranscriptionResponse(BaseModel):
    """转录响应"""
    id: str
    session_id: str
    content: str
    language: str
    status: TranscriptionStatus
    word_count: Optional[int] = None
    created_at: datetime


# =============== 模板相关 ===============
class SummaryTemplateRequest(BaseModel):
    """总结模板请求"""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    template_content: str = Field(..., min_length=10)
    category: str = Field(default="会议")
    is_default: bool = Field(default=False)
    is_active: bool = Field(default=True)
    tags: List[str] = []


class SummaryTemplateResponse(BaseModel):
    """总结模板响应"""
    id: str
    name: str
    description: Optional[str] = None
    template_content: str
    category: str
    is_default: bool
    is_active: bool
    usage_count: int
    tags: List[str]
    created_at: datetime
    updated_at: datetime


# =============== AI总结相关 ===============
class SummarizeRequest(BaseModel):
    """AI总结请求"""
    transcription: str = Field(..., min_length=10)
    template_id: Optional[str] = None


class SummarizeResponse(BaseModel):
    """AI总结响应"""
    summary: str
    metadata: Dict[str, Any]


class GenerateTitleRequest(BaseModel):
    """生成标题请求"""
    transcription: str = Field(..., min_length=10)
    summary: Optional[str] = None


class GenerateTitleResponse(BaseModel):
    """生成标题响应"""
    title: str
    metadata: Dict[str, Any]


class AISummarySaveRequest(BaseModel):
    """保存AI总结请求"""
    session_id: str
    transcription_id: Optional[str] = None
    summary: str
    key_points: List[str] = []
    action_items: List[str] = []
    ai_model: str
    ai_provider: str = "litellm"
    processing_time_ms: Optional[int] = None
    token_usage: Dict[str, Any] = {}
    cost_cents: Optional[int] = None
    template_id: Optional[str] = None


class AISummaryResponse(BaseModel):
    """AI总结响应"""
    id: str
    session_id: str
    summary: str
    key_points: List[str]
    status: AISummaryStatus
    created_at: datetime


# =============== 音频文件相关 ===============
class AudioFileResponse(BaseModel):
    """音频文件响应"""
    id: str
    session_id: str
    original_filename: Optional[str] = None
    public_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    format: str
    upload_status: AudioUploadStatus
    created_at: datetime


class AudioProcessRequest(BaseModel):
    """音频处理请求"""
    session_id: str
    webrtc_id: Optional[str] = None


class AudioUploadResponse(BaseModel):
    """音频上传响应"""
    success: bool
    audio_file_id: Optional[str] = None
    storage_path: Optional[str] = None
    file_size: Optional[int] = None
    duration_seconds: Optional[float] = None
    message: str = ""


# =============== 批量转录相关 ===============
class BatchTranscriptionResponse(BaseModel):
    """批量转录响应"""
    message: str
    status: str
    session_id: str
    audio_file_id: str
    transcription_id: str
    statistics: Dict[str, Any]
    transcription: Dict[str, Any]


# =============== 缓存和状态相关 ===============
class AudioCacheStatusResponse(BaseModel):
    """音频缓存状态响应"""
    total_sessions: int
    cache_size_mb: float
    active_sessions: List[str]
    oldest_session: Optional[str] = None
    cache_memory_usage: Dict[str, Any]


class SetCurrentSessionRequest(BaseModel):
    """设置当前会话请求"""
    session_id: str


class CurrentSessionResponse(BaseModel):
    """当前会话响应"""
    session_id: Optional[str] = None
    status: str 