"""
Shared configuration management for microservices.
Centralizes environment variables and service URLs.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pathlib import Path

# Get the backend_new root directory path
BACKEND_ROOT = Path(__file__).parent.parent
ENV_FILE_PATH = BACKEND_ROOT / ".env"


class BaseServiceConfig(BaseSettings):
    """Base configuration for all microservices"""
    
    # Service identification
    service_name: str = "intrascribe-service"
    service_version: str = "1.0.0"
    environment: str = "development"
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Security
    api_key_header: str = "X-API-Key"
    service_api_key: str = "intrascribe-internal-key"
    
    class Config:
        env_file = str(ENV_FILE_PATH)
        extra = "ignore"
        case_sensitive = False


class DatabaseConfig(BaseSettings):
    """Database configuration"""
    
    # Supabase configuration
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_anon_key: str = os.getenv("SUPABASE_ANON_KEY", "")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    
    class Config:
        env_file = str(ENV_FILE_PATH)
        extra = "ignore"


class RedisConfig(BaseSettings):
    """Redis configuration"""
    
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))
    redis_password: Optional[str] = os.getenv("REDIS_PASSWORD")
    
    @property
    def redis_url(self) -> str:
        """Build Redis URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    class Config:
        env_file = str(ENV_FILE_PATH)
        extra = "ignore"


class ServiceURLConfig(BaseSettings):
    """Service URLs configuration"""
    
    # Internal service URLs
    api_service_url: str = "http://localhost:8000"
    stt_service_url: str = "http://localhost:8001"
    diarization_service_url: str = "http://localhost:8002"
    
    # External services
    livekit_api_url: str = os.getenv("LIVEKIT_API_URL", "")
    livekit_api_key: str = os.getenv("LIVEKIT_API_KEY", "")
    livekit_secret: str = os.getenv("LIVEKIT_API_SECRET", "")
    
    class Config:
        env_file = str(ENV_FILE_PATH)
        extra = "ignore"


class STTConfig(BaseSettings):
    """STT service specific configuration"""
    
    model_dir: str = os.getenv("STT_MODEL_DIR", "iic/SenseVoiceSmall")
    output_dir: str = os.getenv("STT_OUTPUT_DIR", "./temp_audio")
    delete_audio_file: bool = True
    max_audio_length: int = 300  # 5 minutes max
    batch_size: int = 1
    
    class Config:
        env_file = str(ENV_FILE_PATH)
        extra = "ignore"


class SpeakerConfig(BaseSettings):
    """Speaker diarization service configuration"""
    
    huggingface_token: str = os.getenv("HUGGINGFACE_TOKEN", "")
    pyannote_model: str = "pyannote/speaker-diarization-3.1"
    min_segment_duration: float = 1.0
    max_speakers: int = 10
    
    class Config:
        env_file = str(ENV_FILE_PATH)
        extra = "ignore"


class AIConfig(BaseSettings):
    """AI service configuration"""
    
    default_model: str = "gpt-3.5-turbo"
    max_tokens: int = 4000
    temperature: float = 0.7
    timeout_seconds: int = 30
    
    # API keys (loaded from env)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    
    class Config:
        env_file = str(ENV_FILE_PATH)
        extra = "ignore"


# Global configuration instances
base_config = BaseServiceConfig()
db_config = DatabaseConfig()
redis_config = RedisConfig()
service_urls = ServiceURLConfig()
stt_config = STTConfig()
speaker_config = SpeakerConfig()
ai_config = AIConfig()
