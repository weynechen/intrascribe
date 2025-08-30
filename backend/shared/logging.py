"""
Shared logging configuration for microservices.
Provides consistent logging format and behavior across all services.
"""
import logging
import sys
from typing import Optional
from .config import base_config


def setup_logging(
    service_name: str,
    log_level: Optional[str] = None,
    log_format: Optional[str] = None
) -> logging.Logger:
    """
    Set up logging for a microservice.
    
    Args:
        service_name: Name of the service for log identification
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_format: Custom log format string
    
    Returns:
        Configured logger instance
    """
    # Use config defaults if not provided
    log_level = log_level or base_config.log_level
    log_format = log_format or base_config.log_format
    
    # Create logger
    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    
    # Create formatter
    formatter = logging.Formatter(log_format)
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    # Prevent duplicate logs
    logger.propagate = False
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with consistent configuration.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class ServiceLogger:
    """
    Service logger wrapper with common log patterns.
    """
    
    def __init__(self, service_name: str):
        self.logger = setup_logging(service_name)
        self.service_name = service_name
    
    def service_start(self, port: int):
        """Log service startup"""
        self.logger.info(f"🚀 {self.service_name} starting on port {port}")
    
    def service_ready(self, port: int):
        """Log service ready"""
        self.logger.info(f"✅ {self.service_name} ready and listening on port {port}")
    
    def service_stop(self):
        """Log service shutdown"""
        self.logger.info(f"🛑 {self.service_name} shutting down")
    
    def request_start(self, endpoint: str, request_id: str = None):
        """Log request start"""
        request_info = f" [{request_id}]" if request_id else ""
        self.logger.info(f"📥 Request{request_info}: {endpoint}")
    
    def request_end(self, endpoint: str, duration_ms: int, request_id: str = None):
        """Log request completion"""
        request_info = f" [{request_id}]" if request_id else ""
        self.logger.info(f"📤 Response{request_info}: {endpoint} - {duration_ms}ms")
    
    def error(self, message: str, exception: Exception = None):
        """Log error with optional exception"""
        if exception:
            self.logger.error(f"❌ {message}: {str(exception)}")
        else:
            self.logger.error(f"❌ {message}")
    
    def warning(self, message: str):
        """Log warning"""
        self.logger.warning(f"⚠️ {message}")
    
    def info(self, message: str):
        """Log info"""
        self.logger.info(f"ℹ️ {message}")
    
    def debug(self, message: str):
        """Log debug"""
        self.logger.debug(f"🔍 {message}")
    
    def success(self, message: str):
        """Log success"""
        self.logger.info(f"✅ {message}")
