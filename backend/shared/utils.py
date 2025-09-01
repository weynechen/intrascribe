"""
Shared utility functions for microservices.
Contains common helper functions used across services.
"""
import time
import uuid
import hashlib
from typing import Dict, Any, Optional
from functools import wraps
import asyncio
import httpx
from .logging import get_logger

logger = get_logger(__name__)


def generate_id() -> str:
    """Generate a unique identifier"""
    return str(uuid.uuid4())


def generate_short_id(length: int = 8) -> str:
    """Generate a short unique identifier"""
    return str(uuid.uuid4()).replace('-', '')[:length]


def hash_string(text: str) -> str:
    """Generate SHA256 hash of a string"""
    return hashlib.sha256(text.encode()).hexdigest()


def timing_decorator(func):
    """Decorator to measure function execution time"""
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            duration_ms = int((time.time() - start_time) * 1000)
            logger.debug(f"Function {func.__name__} completed in {duration_ms}ms")
            return result
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Function {func.__name__} failed after {duration_ms}ms: {e}")
            raise
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration_ms = int((time.time() - start_time) * 1000)
            logger.debug(f"Function {func.__name__} completed in {duration_ms}ms")
            return result
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Function {func.__name__} failed after {duration_ms}ms: {e}")
            raise
    
    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper


class ServiceClient:
    """Base class for inter-service HTTP communication"""
    
    def __init__(self, base_url: str, api_key: str = None, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "intrascribe-microservice/1.0"
        }
        
        if api_key:
            self.headers["X-API-Key"] = api_key
    
    async def _request(
        self, 
        method: str, 
        endpoint: str, 
        data: Dict[str, Any] = None,
        params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to another service"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    headers=self.headers
                )
                response.raise_for_status()
                return response.json()
                
        except httpx.TimeoutException:
            logger.error(f"Request timeout to {url}")
            raise Exception(f"Service request timeout: {url}")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} for {url}")
            raise Exception(f"Service error {e.response.status_code}: {url}")
        except Exception as e:
            logger.error(f"Request failed to {url}: {e}")
            raise Exception(f"Service communication error: {url}")
    
    async def get(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make GET request"""
        return await self._request("GET", endpoint, params=params)
    
    async def post(self, endpoint: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make POST request"""
        return await self._request("POST", endpoint, data=data)
    
    async def put(self, endpoint: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make PUT request"""
        return await self._request("PUT", endpoint, data=data)
    
    async def delete(self, endpoint: str) -> Dict[str, Any]:
        """Make DELETE request"""
        return await self._request("DELETE", endpoint)
    
    async def health_check(self) -> bool:
        """Check if the service is healthy"""
        try:
            response = await self.get("/health")
            return response.get("status") == "healthy"
        except:
            return False


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable string"""
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        return f"{minutes}m {remaining_seconds}s"
    else:
        hours = int(seconds // 3600)
        remaining_minutes = int((seconds % 3600) // 60)
        return f"{hours}h {remaining_minutes}m"


def validate_audio_format(file_format: str) -> bool:
    """Validate audio file format"""
    allowed_formats = ["wav", "mp3", "flac", "ogg", "m4a"]
    return file_format.lower() in allowed_formats


def validate_session_id(session_id: str) -> bool:
    """Validate session ID format (UUID)"""
    try:
        uuid.UUID(session_id)
        return True
    except ValueError:
        return False


class CircuitBreaker:
    """Simple circuit breaker for service calls"""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker logic"""
        if self.state == "open":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "half-open"
            else:
                raise Exception("Circuit breaker is open")
        
        try:
            result = func(*args, **kwargs)
            if self.state == "half-open":
                self.state = "closed"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
            
            raise e
