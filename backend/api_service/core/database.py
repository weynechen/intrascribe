"""
Database connection and management.
Handles Supabase client initialization and connection pooling.
"""
import os
import sys
from typing import Optional

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.config import db_config

logger = ServiceLogger("database")


class DatabaseManager:
    """
    Manages database connections and operations.
    Implements singleton pattern for connection management.
    """
    
    _instance = None
    _anon_client = None
    _service_client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self._initialize_clients()
            self.initialized = True
    
    def _initialize_clients(self):
        """Initialize Supabase clients"""
        try:
            from supabase import create_client, Client
            
            # Validate configuration
            if not db_config.supabase_url or not db_config.supabase_anon_key:
                logger.error("Supabase configuration missing")
                raise ValueError("Supabase URL and anon key are required")
            
            # Create anonymous client (for user-level operations)
            self._anon_client = create_client(
                db_config.supabase_url,
                db_config.supabase_anon_key
            )
            
            # Create service role client (for admin operations)
            if db_config.supabase_service_role_key:
                self._service_client = create_client(
                    db_config.supabase_url,
                    db_config.supabase_service_role_key
                )
            else:
                logger.warning("Service role key not configured - using anon client")
                self._service_client = self._anon_client
            
            logger.success("Database clients initialized successfully")
            logger.info(f"Supabase URL: {db_config.supabase_url}")
            
        except ImportError:
            logger.error("Supabase client not installed")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize database clients: {e}")
            raise
    
    def get_anon_client(self):
        """Get anonymous client for user-level operations"""
        return self._anon_client
    
    def get_service_client(self):
        """Get service role client for admin operations"""
        return self._service_client
    
    def get_authenticated_client(self, access_token: Optional[str] = None):
        """
        Get client with user authentication.
        
        Args:
            access_token: User's access token
        
        Returns:
            Authenticated Supabase client
        """
        if access_token:
            # Create new client instance with user token
            from supabase import create_client
            
            client = create_client(
                db_config.supabase_url,
                db_config.supabase_anon_key
            )
            
            # Set user session
            client.auth.session = {"access_token": access_token}
            return client
        
        return self._anon_client
    
    def health_check(self) -> dict:
        """Check database connection health"""
        try:
            # Try a simple query to test connection
            result = self._anon_client.table('users').select('id').limit(1).execute()
            
            return {
                "status": "healthy",
                "connected": True,
                "service_role_available": self._service_client is not None,
            }
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e)
            }


# Global database manager instance
db_manager = DatabaseManager()
