"""
LiveKit 连接详情API
按照官方example的标准实现
"""
import logging
import random
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .dependencies import get_current_user
from .models import User
from .config import settings
from .repositories import session_repository

logger = logging.getLogger(__name__)

# 检查LiveKit依赖
try:
    from livekit.api import AccessToken, VideoGrants
    from livekit.protocol.room import RoomConfiguration
    LIVEKIT_AVAILABLE = True
    logger.info("✅ LiveKit依赖导入成功")
except ImportError as e:
    logging.warning(f"❌ LiveKit依赖不可用: {e}")
    LIVEKIT_AVAILABLE = False
    AccessToken = None
    VideoGrants = None
    RoomConfiguration = None


# 创建连接详情路由器
connection_router = APIRouter(prefix="/livekit", tags=["LiveKit Connection"])

class RoomConfigRequest(BaseModel):
    room_config: Optional[dict] = None
    title: Optional[str] = "新录音会话"
    language: Optional[str] = "zh-CN"

class ConnectionDetails(BaseModel):
    serverUrl: str
    roomName: str
    participantName: str
    participantToken: str
    sessionId: str  # 添加会话ID字段

def create_participant_token(identity: str, name: str, room_name: str, agent_name: Optional[str] = None) -> str:
    """创建参与者访问令牌"""
    if not LIVEKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="LiveKit SDK不可用")
    
    if not all([settings.livekit.url, settings.livekit.api_key, settings.livekit.api_secret]):
        raise HTTPException(status_code=500, detail="LiveKit配置不完整")
    
    try:
        # 创建访问令牌并设置属性 (使用链式调用)
        at = AccessToken(
            api_key=settings.livekit.api_key,
            api_secret=settings.livekit.api_secret
        ).with_identity(identity).with_name(name).with_ttl(timedelta(minutes=15))
        
        # 添加视频权限
        grant = VideoGrants(
            room=room_name,
            room_join=True,
            can_publish=True,
            can_publish_data=True,
            can_subscribe=True
        )
        at = at.with_grants(grant)
        
        # 配置agent
        if agent_name:
            room_config = RoomConfiguration(
                agents=[{"agent_name": agent_name}]
            )
            at = at.with_room_config(room_config)
        
        return at.to_jwt()
        
    except Exception as e:
        logger.error(f"❌ 创建访问令牌失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建访问令牌失败: {str(e)}")

@connection_router.post("/connection-details", response_model=ConnectionDetails)
async def get_connection_details(
    request: RoomConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """
    获取LiveKit连接详情并创建会话记录
    """
    if not LIVEKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="LiveKit SDK不可用")
    
    try:
        logger.info(f"🔗 为用户 {current_user.id} 生成LiveKit连接详情")
        
        # 1. 先创建数据库会话记录
        logger.info("📝 创建数据库会话记录...")
        session = await session_repository.create_session(
            user_id=current_user.id,
            title=request.title or "新录音会话",
            language=request.language or "zh-CN",
            stt_model="local_funasr"
        )
        logger.info(f"✅ 会话记录创建成功: {session.id}")
        
        # 2. 解析agent名称
        agent_name = None
        if request.room_config and request.room_config.get("agents"):
            agents = request.room_config["agents"]
            if agents and len(agents) > 0:
                agent_name = agents[0].get("agent_name")
        
        # 3. 生成参与者信息，使用会话ID作为房间名的一部分
        participant_name = current_user.email or f"user_{current_user.id[:8]}"
        participant_identity = f"intrascribe_user_{random.randint(1000, 9999)}"
        # 使用会话ID作为房间名，这样LiveKit Agent可以通过房间名获取会话ID
        room_name = f"intrascribe_room_{session.id}"
        
        # 4. 生成访问令牌
        participant_token = create_participant_token(
            identity=participant_identity,
            name=participant_name,
            room_name=room_name,
            agent_name=agent_name
        )
        
        # 5. 更新会话状态为录音中
        from .models import SessionStatus
        await session_repository.update_session_status(
            session_id=session.id,
            status=SessionStatus.RECORDING
        )
        logger.info(f"✅ 会话状态已更新为录音中: {session.id}")
        
        # 6. 返回连接详情
        connection_details = ConnectionDetails(
            serverUrl=settings.livekit.url,
            roomName=room_name,
            participantName=participant_name,
            participantToken=participant_token,
            sessionId=session.id
        )
        
        logger.info(f"✅ 连接详情生成成功: 房间={room_name}, 会话={session.id}, Agent={agent_name}")
        return connection_details
        
    except Exception as e:
        logger.error(f"❌ 生成连接详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成连接详情失败: {str(e)}")

@connection_router.get("/health")
async def health_check():
    """LiveKit健康检查"""
    return {
        "status": "ok" if LIVEKIT_AVAILABLE else "error",
        "livekit_available": LIVEKIT_AVAILABLE,
        "server_url": settings.livekit.url if LIVEKIT_AVAILABLE else None
    }
