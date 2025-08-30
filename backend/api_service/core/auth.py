"""
Authentication and authorization utilities.
Handles JWT tokens, user verification, and access control.
"""
import os
import sys
import jwt
from typing import Optional
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.models import UserData

from .database import db_manager

logger = ServiceLogger("auth")

# Security scheme
security = HTTPBearer()


class AuthManager:
    """Manages authentication and authorization"""
    
    def __init__(self):
        self.db = db_manager
    
    def get_user_id_from_token(self, authorization_header: str) -> Optional[str]:
        """
        Extract user ID from JWT token.
        
        Args:
            authorization_header: Authorization header with Bearer token
        
        Returns:
            User ID if valid, None otherwise
        """
        try:
            if not authorization_header or not authorization_header.startswith('Bearer '):
                return None
            
            token = authorization_header.replace('Bearer ', '')
            
            # Decode JWT token (without signature verification for user ID extraction)
            decoded = jwt.decode(token, options={"verify_signature": False})
            user_id = decoded.get('sub')
            
            if user_id:
                logger.debug(f"Extracted user ID from token: {user_id}")
                return user_id
                
            return None
            
        except Exception as e:
            logger.warning(f"Failed to extract user ID from token: {e}")
            return None
    
    def get_user_by_id(self, user_id: str) -> Optional[UserData]:
        """
        Get user data by ID.
        
        Args:
            user_id: User ID
        
        Returns:
            UserData if found, None otherwise
        """
        try:
            client = self.db.get_service_client()
            
            result = client.table('users').select('*').eq('id', user_id).execute()
            
            if result.data and len(result.data) > 0:
                user_data = result.data[0]
                return UserData(
                    id=user_data['id'],
                    email=user_data['email'],
                    username=user_data['username'],
                    full_name=user_data['full_name'],
                    is_active=user_data.get('is_active', True),
                    is_verified=user_data.get('is_verified', False),
                    created_at=user_data.get('created_at')
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user by ID {user_id}: {e}")
            return None
    
    def verify_session_ownership(self, session_id: str, user_id: str) -> bool:
        """
        Verify that a user owns a session.
        
        Args:
            session_id: Session ID
            user_id: User ID
        
        Returns:
            True if user owns session, False otherwise
        """
        try:
            client = self.db.get_service_client()
            
            result = client.table('recording_sessions').select('user_id').eq('id', session_id).execute()
            
            if result.data and len(result.data) > 0:
                session_user_id = result.data[0]['user_id']
                return session_user_id == user_id
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to verify session ownership: {e}")
            return False


# Global auth manager instance
auth_manager = AuthManager()


# Dependency functions for FastAPI
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> UserData:
    """
    Get current authenticated user.
    
    Args:
        credentials: HTTP authorization credentials
    
    Returns:
        Current user data
    
    Raises:
        HTTPException: If authentication fails
    """
    try:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header missing"
            )
        
        # Extract user ID from token
        user_id = auth_manager.get_user_id_from_token(f"Bearer {credentials.credentials}")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Get user data
        user = auth_manager.get_user_by_id(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive"
            )
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[UserData]:
    """
    Get current user if authenticated, None otherwise.
    
    Args:
        credentials: Optional HTTP authorization credentials
    
    Returns:
        Current user data or None
    """
    try:
        if not credentials:
            return None
        
        return await get_current_user(credentials)
        
    except:
        return None


async def get_current_user_or_service(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[UserData]:
    """
    Get current user from JWT token or authenticate as service using service token.
    
    Args:
        credentials: HTTP authorization credentials
    
    Returns:
        UserData if user authenticated, None if service authenticated
    
    Raises:
        HTTPException: If authentication fails
    """
    try:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header missing"
            )
        
        token = credentials.credentials
        
        # Check if it's a service token
        service_token = os.getenv("SERVICE_TOKEN")
        if service_token and token == service_token:
            logger.debug("Authenticated as internal service")
            return None  # Service authentication, no user
        
        # Try user authentication
        user_id = auth_manager.get_user_id_from_token(f"Bearer {token}")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Get user data
        user = auth_manager.get_user_by_id(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive"
            )
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )


def verify_session_ownership(session_id: str, current_user: UserData = Depends(get_current_user)) -> str:
    """
    Verify session ownership dependency.
    
    Args:
        session_id: Session ID to verify
        current_user: Current authenticated user
    
    Returns:
        Session ID if ownership is verified
    
    Raises:
        HTTPException: If ownership verification fails
    """
    try:
        if not auth_manager.verify_session_ownership(session_id, current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        return session_id
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session ownership verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ownership verification failed"
        )


def verify_session_ownership_or_service(
    session_id: str, 
    current_user_or_service: Optional[UserData] = Depends(get_current_user_or_service)
) -> str:
    """
    Verify session ownership or allow if service authenticated.
    
    Args:
        session_id: Session ID to verify
        current_user_or_service: Current authenticated user or None if service
    
    Returns:
        Session ID if ownership is verified or service authenticated
    
    Raises:
        HTTPException: If ownership verification fails
    """
    try:
        # If service authenticated, allow access
        if current_user_or_service is None:
            logger.debug(f"Service access granted for session: {session_id}")
            return session_id
        
        # Otherwise verify user ownership
        if not auth_manager.verify_session_ownership(session_id, current_user_or_service.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        return session_id
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session ownership verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ownership verification failed"
        )
