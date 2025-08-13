"""
外部服务客户端
封装对第三方API的调用逻辑
"""
import os
import jwt
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

from supabase import create_client, Client
import numpy as np

from .config import settings
from .models import User, Session, Transcription, AISummary, AudioFile

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Supabase 客户端管理"""
    
    def __init__(self):
        self.url = settings.supabase.url
        self.anon_key = settings.supabase.anon_key
        self.service_role_key = settings.supabase.service_role_key
        
        # 用户级别的客户端（受RLS保护）
        self._anon_client: Client = create_client(self.url, self.anon_key)
        
        # 系统级别的客户端（绕过RLS）
        self._service_client: Client = create_client(self.url, self.service_role_key)
        
        logger.info(f"🔗 Supabase 客户端初始化成功，URL: {self.url}")
    
    def get_user_client(self, access_token: str = None) -> Client:
        """获取用户级别的客户端"""
        if access_token:
            # 设置用户认证令牌
            self._anon_client.auth.session = {"access_token": access_token}
        return self._anon_client
    
    def get_service_client(self) -> Client:
        """获取系统级别的客户端（谨慎使用）"""
        return self._service_client
    
    def get_user_id_from_token(self, authorization_header: str = None) -> str:
        """
        从认证token中提取用户ID
        
        Args:
            authorization_header: 认证头
            
        Returns:
            str: 用户ID
        """
        if authorization_header and authorization_header.startswith('Bearer '):
            try:
                token = authorization_header.replace('Bearer ', '')
                # 解码JWT token获取用户ID (不验证签名，只是为了获取用户信息)
                decoded = jwt.decode(token, options={"verify_signature": False})
                user_id = decoded.get('sub')
                if user_id:
                    logger.info(f"🔐 从认证token获取用户ID: {user_id}")
                    return user_id
            except Exception as e:
                logger.warning(f"⚠️ 无法解析认证token: {e}")
        
        # 如果无法获取用户ID，抛出异常
        raise Exception("无法获取用户认证信息，请确保已登录")
    
    def get_authenticated_client(self, authorization_header: str = None, use_service_role: bool = False) -> Client:
        """
        获取适当的 Supabase 客户端
        
        Args:
            authorization_header: 用户认证头
            use_service_role: 是否使用service role（用于系统级操作）
        
        Returns:
            Client: 配置好的Supabase客户端
        """
        if use_service_role:
            logger.info("🔐 使用 Service Role 权限进行系统级操作")
            return self._service_client
        
        if authorization_header and authorization_header.startswith('Bearer '):
            try:
                token = authorization_header.replace('Bearer ', '')
                # 创建带用户认证的客户端
                user_client = create_client(self.url, self.anon_key)
                user_client.auth.session = {"access_token": token}
                logger.info(f"🔐 使用用户认证token")
                return user_client
            except Exception as e:
                logger.warning(f"⚠️ 用户认证失败，回退到匿名访问: {e}")
        
        logger.info("🔐 使用匿名访问")
        return self._anon_client


class STTClient:
    """语音转录客户端"""
    
    def __init__(self):
        from .stt_adapter import LocalFunASR
        self.stt_model = LocalFunASR()
        logger.info("🎙️ STT客户端初始化完成")
    
    def transcribe(self, audio: Tuple[int, np.ndarray]) -> str:
        """
        语音转文本
        
        Args:
            audio: (sample_rate, audio_array) 元组
            
        Returns:
            转录的文本字符串
        """
        try:
            return self.stt_model.stt(audio)
        except Exception as e:
            logger.error(f"STT转录失败: {e}")
            raise


class AIClient:
    """AI服务客户端"""
    
    def __init__(self):
        from .ai_summary import AISummaryService
        self.ai_service = AISummaryService(settings.ai_summary_config)
        logger.info("🤖 AI客户端初始化完成")
    
    async def generate_summary(self, transcription: str, template_content: str = None) -> Tuple[str, Dict[str, Any]]:
        """
        生成AI总结
        
        Args:
            transcription: 转录文本
            template_content: 可选的模板内容
            
        Returns:
            Tuple[总结内容, 元数据]
        """
        try:
            return await self.ai_service.generate_summary(transcription, template_content)
        except Exception as e:
            logger.error(f"AI总结生成失败: {e}")
            raise
    
    async def generate_title(self, transcription: str, summary: str = None) -> Tuple[str, Dict[str, Any]]:
        """
        生成AI标题
        
        Args:
            transcription: 转录文本
            summary: 可选的总结文本
            
        Returns:
            Tuple[标题内容, 元数据]
        """
        try:
            return await self.ai_service.generate_title(transcription, summary)
        except Exception as e:
            logger.error(f"AI标题生成失败: {e}")
            raise


# 全局客户端实例
supabase_client = SupabaseClient()
stt_client = STTClient()
ai_client = AIClient() 