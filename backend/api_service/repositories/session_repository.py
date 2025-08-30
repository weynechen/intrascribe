"""
Session repository for database operations.
Handles CRUD operations for sessions using synchronous Supabase client.
"""
import os
import sys
from typing import List, Optional
from datetime import datetime

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.models import SessionData, SessionStatus

from core.database import db_manager

logger = ServiceLogger("session-repo")


class SessionRepository:
    """Repository for session data operations"""
    
    def __init__(self):
        self.db = db_manager
    
    def create_session(
        self,
        user_id: str,
        title: str,
        language: str = "zh-CN",
        stt_model: str = "whisper",
        session_id: str = None
    ) -> SessionData:
        """
        Create a new session.
        
        Args:
            user_id: User ID
            title: Session title
            language: Language code
            stt_model: STT model to use
            session_id: Optional custom session ID
        
        Returns:
            Created session data
        """
        try:
            client = self.db.get_service_client()
            
            session_data = {
                "user_id": user_id,
                "title": title,
                "status": SessionStatus.CREATED.value,
                "created_at": datetime.utcnow().isoformat(),
                "metadata": {
                    "language": language,
                    "stt_model": stt_model
                }
            }
            
            if session_id:
                session_data["id"] = session_id
            
            result = client.table('recording_sessions').insert(session_data).execute()
            
            if not result.data:
                raise Exception("Failed to create session")
            
            created_session = result.data[0]
            
            logger.success(f"Created session: {created_session['id']}")
            
            # Extract metadata fields to top-level for compatibility
            metadata = created_session.get('metadata', {})
            
            return SessionData(
                id=created_session['id'],
                user_id=created_session['user_id'],
                title=created_session['title'],
                status=SessionStatus(created_session['status']),
                language=metadata.get('language', 'zh-CN'),
                stt_model=metadata.get('stt_model', 'whisper'),
                template_id=created_session.get('template_id'),
                metadata=metadata,
                created_at=created_session.get('created_at'),
                updated_at=created_session.get('updated_at'),
                started_at=created_session.get('started_at'),
                ended_at=created_session.get('ended_at'),
                duration_seconds=created_session.get('duration_seconds')
            )
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise
    
    def get_session_by_id(self, session_id: str, user_id: str = None) -> Optional[SessionData]:
        """
        Get session by ID.
        
        Args:
            session_id: Session ID
            user_id: Optional user ID for ownership verification
        
        Returns:
            Session data if found
        """
        try:
            client = self.db.get_service_client()
            
            query = client.table('recording_sessions').select('*').eq('id', session_id)
            
            if user_id:
                query = query.eq('user_id', user_id)
            
            result = query.execute()
            
            if not result.data:
                return None
            
            session = result.data[0]
            
            # Extract metadata fields to top-level for compatibility
            metadata = session.get('metadata', {})
            
            return SessionData(
                id=session['id'],
                user_id=session['user_id'],
                title=session['title'],
                status=SessionStatus(session['status']),
                language=metadata.get('language', 'zh-CN'),
                stt_model=metadata.get('stt_model', 'whisper'),
                template_id=session.get('template_id'),
                metadata=metadata,
                created_at=session.get('created_at'),
                updated_at=session.get('updated_at'),
                started_at=session.get('started_at'),
                ended_at=session.get('ended_at'),
                duration_seconds=session.get('duration_seconds')
            )
            
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None
    
    def get_user_sessions(self, user_id: str, limit: int = 50, offset: int = 0) -> List[SessionData]:
        """
        Get sessions for a user.
        
        Args:
            user_id: User ID
            limit: Maximum number of sessions
            offset: Offset for pagination
        
        Returns:
            List of session data
        """
        try:
            client = self.db.get_service_client()
            
            result = client.table('recording_sessions')\
                .select('*')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .range(offset, offset + limit - 1)\
                .execute()
            
            sessions = []
            for session in result.data:
                # Extract metadata fields to top-level for compatibility
                metadata = session.get('metadata', {})
                
                sessions.append(SessionData(
                    id=session['id'],
                    user_id=session['user_id'],
                    title=session['title'],
                    status=SessionStatus(session['status']),
                    language=metadata.get('language', 'zh-CN'),
                    stt_model=metadata.get('stt_model', 'whisper'),
                    template_id=session.get('template_id'),
                    metadata=metadata,
                    created_at=session.get('created_at'),
                    updated_at=session.get('updated_at'),
                    started_at=session.get('started_at'),
                    ended_at=session.get('ended_at'),
                    duration_seconds=session.get('duration_seconds')
                ))
            
            logger.debug(f"Retrieved {len(sessions)} sessions for user {user_id}")
            
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to get sessions for user {user_id}: {e}")
            return []
    
    def update_session(
        self,
        session_id: str,
        title: str = None,
        status: SessionStatus = None,
        user_id: str = None
    ) -> Optional[SessionData]:
        """
        Update session.
        
        Args:
            session_id: Session ID
            title: New title
            status: New status
            user_id: User ID for ownership verification
        
        Returns:
            Updated session data
        """
        try:
            client = self.db.get_service_client()
            
            update_data = {
                "updated_at": datetime.utcnow().isoformat()
            }
            
            if title is not None:
                update_data["title"] = title
            
            if status is not None:
                update_data["status"] = status.value
            
            query = client.table('recording_sessions').update(update_data).eq('id', session_id)
            
            if user_id:
                query = query.eq('user_id', user_id)
            
            result = query.execute()
            
            if not result.data:
                return None
            
            updated_session = result.data[0]
            
            logger.success(f"Updated session: {session_id}")
            
            # Extract metadata fields to top-level for compatibility
            metadata = updated_session.get('metadata', {})
            
            return SessionData(
                id=updated_session['id'],
                user_id=updated_session['user_id'],
                title=updated_session['title'],
                status=SessionStatus(updated_session['status']),
                language=metadata.get('language', 'zh-CN'),
                stt_model=metadata.get('stt_model', 'whisper'),
                template_id=updated_session.get('template_id'),
                metadata=metadata,
                created_at=updated_session.get('created_at'),
                updated_at=updated_session.get('updated_at'),
                started_at=updated_session.get('started_at'),
                ended_at=updated_session.get('ended_at'),
                duration_seconds=updated_session.get('duration_seconds')
            )
            
        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            return None
    
    def delete_session(self, session_id: str, user_id: str = None) -> bool:
        """
        Delete session.
        
        Args:
            session_id: Session ID
            user_id: User ID for ownership verification
        
        Returns:
            True if deleted successfully
        """
        try:
            client = self.db.get_service_client()
            
            query = client.table('recording_sessions').delete().eq('id', session_id)
            
            if user_id:
                query = query.eq('user_id', user_id)
            
            result = query.execute()
            
            success = len(result.data) > 0
            
            if success:
                logger.success(f"Deleted session: {session_id}")
            else:
                logger.warning(f"Session not found or access denied: {session_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False


# Global repository instance
session_repository = SessionRepository()
