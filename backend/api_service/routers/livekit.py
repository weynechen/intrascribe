"""
LiveKit connection and room management API routes.
Handles LiveKit room creation, token generation, and agent coordination.
"""
import os
import sys
import uuid
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.config import service_urls
from shared.utils import timing_decorator

from core.auth import get_current_user
from repositories.session_repository import session_repository

logger = ServiceLogger("livekit-api")

router = APIRouter(prefix="/livekit", tags=["LiveKit"])


# Check LiveKit dependencies
try:
    from livekit.api import AccessToken, VideoGrants
    from livekit.protocol.room import RoomConfiguration
    LIVEKIT_AVAILABLE = True
    logger.info("LiveKit dependencies imported successfully")
except ImportError as e:
    logger.warning(f"LiveKit dependencies not available: {e}")
    LIVEKIT_AVAILABLE = False
    AccessToken = None
    VideoGrants = None
    RoomConfiguration = None


# Request/Response models
from pydantic import BaseModel

class RoomConfigRequest(BaseModel):
    """Room configuration request"""
    room_config: Optional[dict] = None
    title: Optional[str] = "New Recording Session"
    language: Optional[str] = "zh-CN"


class ConnectionDetails(BaseModel):
    """LiveKit connection details"""
    serverUrl: str
    roomName: str
    participantName: str
    participantToken: str
    sessionId: str


# Use shared configuration instead of local config
livekit_config = service_urls


def create_participant_token(
    identity: str, 
    name: str, 
    room_name: str, 
    agent_name: Optional[str] = None
) -> str:
    """
    Create participant access token for LiveKit.
    
    Args:
        identity: Participant identity
        name: Participant display name
        room_name: Room name
        agent_name: Optional agent name for room configuration
    
    Returns:
        JWT access token
    """
    if not LIVEKIT_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LiveKit SDK not available"
        )
    
    if not all([service_urls.livekit_api_url, service_urls.livekit_api_key, service_urls.livekit_secret]):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LiveKit configuration incomplete"
        )
    
    try:
        # Create access token
        at = AccessToken(
            api_key=service_urls.livekit_api_key,
            api_secret=service_urls.livekit_secret
        ).with_identity(identity).with_name(name).with_ttl(timedelta(hours=2))
        
        # Add video grants
        grant = VideoGrants(
            room=room_name,
            room_join=True,
            can_publish=True,
            can_publish_data=True,
            can_subscribe=True
        )
        at = at.with_grants(grant)
        
        # Configure agent if specified
        if agent_name:
            room_config = RoomConfiguration(
                agents=[{"agent_name": agent_name}]
            )
            at = at.with_room_config(room_config)
        
        token = at.to_jwt()
        logger.success(f"Created access token for participant: {identity}")
        
        return token
        
    except Exception as e:
        logger.error(f"Failed to create access token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create access token: {str(e)}"
        )


@router.post("/connection-details", response_model=ConnectionDetails)
@timing_decorator
async def get_connection_details(
    request: RoomConfigRequest,
    current_user = Depends(get_current_user)
):
    """
    Get LiveKit connection details and create session record.
    
    Args:
        request: Room configuration request
        current_user: Current authenticated user
    
    Returns:
        LiveKit connection details
    """
    if not LIVEKIT_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LiveKit SDK not available"
        )
    
    try:
        logger.info(f"Generating LiveKit connection details for user: {current_user.id}")
        
        # 1. Create database session record first
        session = session_repository.create_session(
            user_id=current_user.id,
            title=request.title,
            language=request.language
        )
        
        logger.success(f"Created session record: {session.id}")
        
        # 2. Generate LiveKit room and participant details
        room_name = f"intrascribe_room_{session.id}"
        participant_identity = f"intrascribe_user_{current_user.id}_{int(uuid.uuid4().hex[:8], 16)}"
        participant_name = f"User_{current_user.username if hasattr(current_user, 'username') else 'Anonymous'}"
        
        # 3. Create participant token with agent configuration
        agent_name = "intrascribe-agent-session"
        
        participant_token = create_participant_token(
            identity=participant_identity,
            name=participant_name,
            room_name=room_name,
            agent_name=agent_name
        )
        
        logger.success(f"Generated LiveKit connection for session: {session.id}")
        logger.info(f"Room: {room_name}, Participant: {participant_identity}")
        
        return ConnectionDetails(
            serverUrl=service_urls.livekit_api_url,
            roomName=room_name,
            participantName=participant_name,
            participantToken=participant_token,
            sessionId=session.id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get connection details: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate connection details"
        )


@router.get("/rooms/{room_name}/status")
@timing_decorator
async def get_room_status(
    room_name: str,
    current_user = Depends(get_current_user)
):
    """
    Get LiveKit room status.
    
    Args:
        room_name: LiveKit room name
        current_user: Current authenticated user
    
    Returns:
        Room status information
    """
    try:
        # Extract session ID from room name
        if room_name.startswith("intrascribe_room_"):
            session_id = room_name.replace("intrascribe_room_", "")
            
            # Verify session ownership
            session = session_repository.get_session_by_id(session_id, current_user.id)
            
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this room"
                )
            
            return {
                "room_name": room_name,
                "session_id": session_id,
                "session_status": session.status.value,
                "created_at": session.created_at,
                "participant_count": 0,  # Would need LiveKit API to get actual count
                "recording": session.status.value == "recording"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid room name format"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get room status for {room_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get room status"
        )


@router.post("/rooms/{room_name}/end")
@timing_decorator
async def end_room_session(
    room_name: str,
    current_user = Depends(get_current_user)
):
    """
    End LiveKit room session.
    
    Args:
        room_name: LiveKit room name
        current_user: Current authenticated user
    
    Returns:
        Session end confirmation
    """
    try:
        # Extract session ID from room name
        if room_name.startswith("intrascribe_room_"):
            session_id = room_name.replace("intrascribe_room_", "")
            
            # Verify session ownership
            session = session_repository.get_session_by_id(session_id, current_user.id)
            
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this room"
                )
            
            # Update session status to completed
            from shared.models import SessionStatus
            updated_session = session_repository.update_session(
                session_id=session_id,
                status=SessionStatus.COMPLETED,
                user_id=current_user.id
            )
            
            if updated_session:
                logger.success(f"Ended room session: {room_name}")
                
                return {
                    "message": "Room session ended successfully",
                    "room_name": room_name,
                    "session_id": session_id,
                    "status": updated_session.status.value
                }
            else:
                raise Exception("Failed to update session status")
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid room name format"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to end room session {room_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to end room session"
        )
