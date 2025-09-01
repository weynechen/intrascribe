"""
Shared configuration management for microservices.
Centralizes environment variables and service URLs.
"""
import os
import yaml
from typing import Optional, Dict, Any
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


def get_ai_config() -> Dict[str, Any]:
    """
    Load AI configuration from ai_config.yaml file.
    
    Returns:
        Dictionary containing AI configuration
    """
    config_path = BACKEND_ROOT / "ai_config.yaml"
    
    if not config_path.exists():
        # Return default configuration if file doesn't exist
        return {
            "ai_summary": {
                "provider": "litellm",
                "models": [],
                "prompts": {
                    "system_prompt": "你是一个专业的会议记录助手，擅长分析会议转录内容并生成结构化的总结。",
                    "user_prompt_template": "请对以下会议转录内容进行总结：\n\n转录内容：\n{transcription}\n\n请生成一份结构化的会议总结，包含关键要点、行动项目、重要决策等内容。"
                }
            },
            "retry": {
                "max_attempts": 3,
                "backoff_factor": 2,
                "timeout": 30
            },
            "fallback": {
                "enabled": True,
                "mock_response": True
            }
        }
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        return config or {}
    
    except Exception as e:
        from shared.logging import ServiceLogger
        logger = ServiceLogger("config")
        logger.error(f"Failed to load AI config from {config_path}: {e}")
        # Return default config on error
        return {
            "ai_summary": {
                "provider": "litellm",
                "models": [],
                "prompts": {
                    "system_prompt": "你是一个专业的会议记录助手，擅长分析会议转录内容并生成结构化的总结。",
                    "user_prompt_template": "请对以下会议转录内容进行总结：\n\n转录内容：\n{transcription}\n\n请生成一份结构化的会议总结，包含关键要点、行动项目、重要决策等内容。"
                }
            },
            "retry": {
                "max_attempts": 3,
                "backoff_factor": 2,
                "timeout": 30
            },
            "fallback": {
                "enabled": True,
                "mock_response": True
            }
        }


# Global configuration instances
base_config = BaseServiceConfig()
db_config = DatabaseConfig()
redis_config = RedisConfig()
service_urls = ServiceURLConfig()
stt_config = STTConfig()
speaker_config = SpeakerConfig()
ai_config = AIConfig()
