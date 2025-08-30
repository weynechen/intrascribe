"""
User repository for database operations.
Handles CRUD operations for users and user preferences.
"""
import os
import sys
from typing import Optional, Dict, Any
from datetime import datetime

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.models import UserData

from core.database import db_manager

logger = ServiceLogger("user-repo")


class UserRepository:
    """Repository for user data operations"""
    
    def __init__(self):
        self.db = db_manager
    
    def get_user_by_id(self, user_id: str) -> Optional[UserData]:
        """
        Get user by ID.
        
        Args:
            user_id: User ID
        
        Returns:
            UserData if found
        """
        try:
            client = self.db.get_service_client()
            
            result = client.table('users').select('*').eq('id', user_id).execute()
            
            if not result.data:
                return None
            
            user = result.data[0]
            
            return UserData(
                id=user['id'],
                email=user['email'],
                username=user['username'],
                full_name=user['full_name'],
                is_active=user.get('is_active', True),
                is_verified=user.get('is_verified', False),
                created_at=user.get('created_at')
            )
            
        except Exception as e:
            logger.error(f"Failed to get user {user_id}: {e}")
            return None
    
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Get user business profile with subscription, quotas, and preferences.
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with profile information
        """
        try:
            client = self.db.get_service_client()
            
            # Get user basic info
            user_result = client.table('users').select('*').eq('id', user_id).execute()
            
            if not user_result.data:
                raise Exception("User not found")
            
            user = user_result.data[0]
            
            # Get user preferences (assuming we have a user_preferences table)
            prefs_result = client.table('user_preferences').select('*').eq('user_id', user_id).execute()
            preferences = prefs_result.data[0] if prefs_result.data else {}
            
            # Default subscription info
            subscription = {
                "plan": "free",
                "status": "active",
                "expires_at": None
            }
            
            # Default quotas
            quotas = {
                "monthly_sessions": {"used": 0, "limit": 100},
                "monthly_transcription_minutes": {"used": 0, "limit": 1000},
                "storage_mb": {"used": 0, "limit": 1000}
            }
            
            # Format preferences
            user_preferences = {
                "default_language": preferences.get("default_language", "zh-CN"),
                "auto_summary": preferences.get("auto_summary", True),
                "default_stt_model": preferences.get("default_stt_model", "local_funasr"),
                "notification_settings": preferences.get("notification_settings", {})
            }
            
            logger.debug(f"Retrieved profile for user {user_id}")
            
            return {
                "subscription": subscription,
                "quotas": quotas,
                "preferences": user_preferences
            }
            
        except Exception as e:
            logger.error(f"Failed to get user profile {user_id}: {e}")
            raise
    
    def update_user_preferences(self, user_id: str, preferences: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update user preferences.
        
        Args:
            user_id: User ID
            preferences: Preferences to update
        
        Returns:
            Updated profile information
        """
        try:
            client = self.db.get_service_client()
            
            # Update or insert user preferences
            prefs_data = {
                "user_id": user_id,
                "updated_at": datetime.utcnow().isoformat(),
                **preferences
            }
            
            # Try to update existing preferences
            existing = client.table('user_preferences').select('*').eq('user_id', user_id).execute()
            
            if existing.data:
                # Update existing preferences
                client.table('user_preferences').update(prefs_data).eq('user_id', user_id).execute()
                logger.success(f"Updated preferences for user {user_id}")
            else:
                # Create new preferences record
                prefs_data["created_at"] = datetime.utcnow().isoformat()
                client.table('user_preferences').insert(prefs_data).execute()
                logger.success(f"Created preferences for user {user_id}")
            
            # Return updated profile
            return self.get_user_profile(user_id)
            
        except Exception as e:
            logger.error(f"Failed to update user preferences {user_id}: {e}")
            raise


class TemplateRepository:
    """Repository for summary templates"""
    
    def __init__(self):
        self.db = db_manager
    
    def create_template(
        self,
        user_id: str,
        name: str,
        description: str = None,
        template_content: str = "",
        category: str = "general",
        is_default: bool = False,
        is_active: bool = True,
        tags: list[str] = None
    ) -> Dict[str, Any]:
        """Create a new template"""
        try:
            client = self.db.get_service_client()
            
            template_data = {
                "user_id": user_id,
                "name": name,
                "description": description,
                "template_content": template_content,
                "category": category,
                "is_default": is_default,
                "is_active": is_active,
                "tags": tags or [],
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            result = client.table('summary_templates').insert(template_data).execute()
            
            if not result.data:
                raise Exception("Failed to create template")
            
            created_template = result.data[0]
            logger.success(f"Created template: {created_template['id']}")
            
            return created_template
            
        except Exception as e:
            logger.error(f"Failed to create template: {e}")
            raise
    
    def get_user_templates(self, user_id: str) -> list[Dict[str, Any]]:
        """Get all templates for a user"""
        try:
            client = self.db.get_service_client()
            
            result = client.table('summary_templates')\
                .select('*')\
                .eq('user_id', user_id)\
                .eq('is_active', True)\
                .order('created_at', desc=True)\
                .execute()
            
            logger.debug(f"Retrieved {len(result.data)} templates for user {user_id}")
            
            return result.data
            
        except Exception as e:
            logger.error(f"Failed to get user templates {user_id}: {e}")
            return []
    
    def get_template_by_id(self, template_id: str, user_id: str = None) -> Optional[Dict[str, Any]]:
        """Get template by ID"""
        try:
            client = self.db.get_service_client()
            
            query = client.table('summary_templates').select('*').eq('id', template_id)
            
            if user_id:
                query = query.eq('user_id', user_id)
            
            result = query.execute()
            
            if not result.data:
                return None
            
            return result.data[0]
            
        except Exception as e:
            logger.error(f"Failed to get template {template_id}: {e}")
            return None
    
    def get_system_templates(self) -> list[Dict[str, Any]]:
        """Get system templates"""
        try:
            client = self.db.get_service_client()
            
            # System templates have user_id as null or a special system user ID
            result = client.table('summary_templates')\
                .select('*')\
                .is_('user_id', 'null')\
                .eq('is_active', True)\
                .order('name')\
                .execute()
            
            logger.debug(f"Retrieved {len(result.data)} system templates")
            
            return result.data
            
        except Exception as e:
            logger.error(f"Failed to get system templates: {e}")
            return []


# Global repository instances
user_repository = UserRepository()
template_repository = TemplateRepository()
