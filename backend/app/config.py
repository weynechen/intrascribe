"""
应用配置模块
使用Pydantic的BaseSettings来管理应用配置
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic_settings import BaseSettings
from pydantic import Field
import logging

logger = logging.getLogger(__name__)


class SupabaseConfig:
    """Supabase配置"""
    def __init__(self, url: str, anon_key: str, service_role_key: str, public_url: str = ""):
        self.url = url
        self.anon_key = anon_key
        self.service_role_key = service_role_key
        self.public_url = public_url


class STTConfig:
    """语音转录配置"""
    def __init__(self, model_dir: str, output_dir: str, delete_audio_file: bool):
        self.model_dir = model_dir
        self.output_dir = output_dir
        self.delete_audio_file = delete_audio_file


class LiveKitConfig:
    """LiveKit配置"""
    def __init__(self, url: str, api_key: str, api_secret: str):
        self.url = url
        self.api_key = api_key
        self.api_secret = api_secret


class ApplicationConfig(BaseSettings):
    """主应用配置"""
    # 基础配置
    debug: bool = Field(default=False, env="DEBUG")
    api_version: str = "v1"
    
    # Supabase配置
    supabase_url: str = Field(default="http://127.0.0.1:54321", env="SUPABASE_URL")
    supabase_anon_key: str = Field(default="", env="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(default="", env="SUPABASE_SERVICE_ROLE_KEY")
    supabase_public_url: str = Field(default="", env="SUPABASE_PUBLIC_URL")
    
    # STT配置
    stt_model_dir: str = Field(default="iic/SenseVoiceSmall", env="STT_MODEL_DIR")
    stt_output_dir: str = Field(default="./temp_audio", env="STT_OUTPUT_DIR")
    stt_delete_audio_file: bool = Field(default=True, env="STT_DELETE_AUDIO_FILE")
    
    # 说话人分离配置
    huggingface_token: str = Field(default="", env="HUGGINGFACE_TOKEN")
    pyannote_model: str = Field(default="pyannote/speaker-diarization-3.1", env="PYANNOTE_MODEL")
    
    # LiveKit 配置
    livekit_url: str = Field(default="ws://localhost:7880", env="LIVEKIT_URL")
    livekit_api_key: str = Field(default="devkey", env="LIVEKIT_API_KEY") 
    livekit_api_secret: str = Field(default="secret", env="LIVEKIT_API_SECRET")
    
    # AI总结配置（从yaml文件加载）
    ai_summary_config: Dict[str, Any] = {}
    
    class Config:
        env_file = Path(__file__).parent.parent / ".env"
        env_file_encoding = 'utf-8'
    
    @property
    def supabase(self) -> SupabaseConfig:
        """获取Supabase配置对象"""
        return SupabaseConfig(
            url=self.supabase_url,
            anon_key=self.supabase_anon_key,
            service_role_key=self.supabase_service_role_key,
            public_url=self.supabase_public_url
        )
    
    @property
    def stt(self) -> STTConfig:
        """获取STT配置对象"""
        return STTConfig(
            model_dir=self.stt_model_dir,
            output_dir=self.stt_output_dir,
            delete_audio_file=self.stt_delete_audio_file
        )
    
    @property
    def livekit(self) -> LiveKitConfig:
        """获取LiveKit配置对象"""
        return LiveKitConfig(
            url=self.livekit_url,
            api_key=self.livekit_api_key,
            api_secret=self.livekit_api_secret
        )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._load_yaml_config()
    
    def _load_yaml_config(self):
        """从config.yaml加载AI总结配置"""
        try:
            current_dir = Path(__file__).parent.parent
            config_path = current_dir / "config.yaml"
            
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as file:
                    yaml_config = yaml.safe_load(file) or {}
                    self.ai_summary_config = yaml_config.get('ai_summary', {})
                    # 更新STT配置
                    fun_local = yaml_config.get('fun_local', {})
                    if fun_local:
                        self.stt.model_dir = fun_local.get('model_dir', self.stt.model_dir)
                        self.stt.output_dir = fun_local.get('output_dir', self.stt.output_dir)
                        self.stt.delete_audio_file = fun_local.get('delete_audio_file', self.stt.delete_audio_file)
                        
                logger.info(f"成功加载YAML配置文件: {config_path}")
            else:
                logger.warning(f"YAML配置文件不存在: {config_path}")
        except Exception as e:
            logger.error(f"加载YAML配置文件失败: {e}")


# 全局配置实例
settings = ApplicationConfig() 