"""
依赖注入
定义FastAPI的可重用依赖项
"""
import logging
from typing import Optional
from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .clients import supabase_client
from .models import User

logger = logging.getLogger(__name__)

# 安全方案
security = HTTPBearer(auto_error=False)


class AuthLevel:
    """认证层级定义"""
    PUBLIC = "public"           # 公开访问，无需认证
    AUTHENTICATED = "auth"      # 需要用户认证
    SESSION_BOUND = "session"   # 需要认证 + 会话权限
    RTC_AUTHORIZED = "rtc"      # 需要认证 + RTC权限
    ADMIN = "admin"            # 需要管理员权限


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """
    可选认证依赖 - 获取当前用户（如果已认证）
    用于可以匿名访问但认证后有额外功能的端点
    """
    if not credentials:
        return None
    
    try:
        token = credentials.credentials
        user_id = supabase_client.get_user_id_from_token(f"Bearer {token}")
        
        # 这里可以从数据库获取更详细的用户信息
        # 目前只返回基本的用户ID
        return User(id=user_id)
        
    except Exception as e:
        logger.warning(f"可选认证失败: {e}")
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    """
    必需认证依赖 - 获取当前用户
    用于需要用户认证的端点
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要认证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        token = credentials.credentials
        user_id = supabase_client.get_user_id_from_token(f"Bearer {token}")
        
        # 这里可以从数据库获取更详细的用户信息
        return User(id=user_id)
        
    except Exception as e:
        logger.error(f"用户认证失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_from_header(
    authorization: Optional[str] = Header(None)
) -> User:
    """
    从Header获取当前用户 - 用于某些特殊端点
    """
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要认证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        user_id = supabase_client.get_user_id_from_token(authorization)
        return User(id=user_id)
        
    except Exception as e:
        logger.error(f"用户认证失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def verify_session_ownership(
    session_id: str,
    current_user: User = Depends(get_current_user)
) -> str:
    """
    验证会话所有权依赖
    确保用户只能访问自己的会话
    """
    try:
        # 使用service role验证会话所有权
        client = supabase_client.get_service_client()
        result = client.table('recording_sessions').select('user_id').eq('id', session_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在"
            )
        
        session_user_id = result.data[0]['user_id']
        if session_user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此会话"
            )
        
        return session_id
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证会话所有权失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="验证会话权限时发生错误"
        )


class AuthenticationError(Exception):
    """认证相关异常"""
    pass


class AuthorizationError(Exception):
    """授权相关异常"""
    pass


class BusinessLogicError(Exception):
    """业务逻辑异常"""
    pass


class ExternalServiceError(Exception):
    """外部服务异常"""
    pass


class ValidationError(Exception):
    """验证异常"""
    pass 