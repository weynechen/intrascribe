"""
Main API Service Application

Central FastAPI application that orchestrates the Intrascribe platform.
Coordinates with microservices and handles business logic.
"""
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
backend_root = Path(__file__).parent.parent
env_file = backend_root / ".env"
load_dotenv(env_file)

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.logging import ServiceLogger
from shared.config import base_config
from shared.models import ServiceHealthCheck

from core.database import db_manager
from core.redis import redis_manager
from clients.microservice_clients import stt_client, diarization_client

# Initialize logger
logger = ServiceLogger("api-service")

# Service startup time
service_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage service lifecycle"""
    # Startup
    logger.service_start(8000)
    
    # Check database connection
    db_health = db_manager.health_check()
    if db_health["status"] != "healthy":
        logger.error("Database connection failed")
        raise RuntimeError("Database not available")
    
    # Check Redis connection
    redis_health = await redis_manager.health_check()
    if redis_health["status"] != "healthy":
        logger.warning("Redis connection failed - real-time features may be limited")
    else:
        logger.success("Redis connected successfully")
    
    # Check microservices
    microservices = {
        "stt": stt_client,
        "diarization": diarization_client,
    }
    
    for service_name, client in microservices.items():
        try:
            is_healthy = await client.health_check()
            if is_healthy:
                logger.success(f"{service_name} service is available")
            else:
                logger.warning(f"{service_name} service is not available")
        except Exception as e:
            logger.warning(f"Failed to check {service_name} service: {e}")
    
    logger.service_ready(8000)
    
    yield
    
    # Shutdown
    logger.service_stop()


# Create FastAPI app
app = FastAPI(
    title="Intrascribe API Service",
    description="Central API service for the Intrascribe platform",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception in {request.method} {request.url}: {exc}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred"
        }
    )


# Middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing"""
    start_time = time.time()
    
    # Generate request ID for tracing
    request_id = f"{int(start_time)}_{hash(str(request.url)) % 1000:03d}"
    
    logger.request_start(f"{request.method} {request.url.path}", request_id)
    
    response = await call_next(request)
    
    duration_ms = int((time.time() - start_time) * 1000)
    logger.request_end(f"{request.method} {request.url.path}", duration_ms, request_id)
    
    return response


# Health check endpoint
@app.get("/health", response_model=ServiceHealthCheck)
async def health_check():
    """Service health check endpoint"""
    uptime = int(time.time() - service_start_time)
    
    # Check database
    db_health = db_manager.health_check()
    
    # Check Redis
    redis_health = await redis_manager.health_check()
    
    # Check microservices
    microservice_status = {}
    microservices = {
        "stt": stt_client,
        "diarization": diarization_client,
    }
    
    for service_name, client in microservices.items():
        try:
            is_healthy = await client.health_check()
            microservice_status[f"{service_name}_service"] = "healthy" if is_healthy else "unhealthy"
        except:
            microservice_status[f"{service_name}_service"] = "unreachable"
    
    # Determine overall status
    overall_status = "healthy"
    if db_health["status"] != "healthy":
        overall_status = "degraded"
    elif any(status == "unreachable" for status in microservice_status.values()):
        overall_status = "degraded"
    
    return ServiceHealthCheck(
        service_name="api-service",
        status=overall_status,
        version="1.0.0",
        uptime_seconds=uptime,
        details={
            "database": db_health,
            "redis": redis_health,
            "microservices": microservice_status,
        }
    )


@app.get("/info")
async def service_info() -> Dict[str, Any]:
    """Get detailed service information"""
    uptime = int(time.time() - service_start_time)
    
    return {
        "service": {
            "name": "api-service",
            "version": "1.0.0",
            "uptime_seconds": uptime,
            "environment": base_config.environment,
        },
        "endpoints": {
            "health": "/health",
            "sessions": "/api/v1/sessions",
            "users": "/api/v1/users",
            "templates": "/api/v1/templates", 
            "transcriptions": "/api/v1/transcriptions",
            "ai_services": "/api/v1/summarize",
            "livekit": "/api/v1/livekit",
            "audio": "/api/v1/audio",
            "realtime": "/api/v1/realtime",
            "docs": "/docs",
        },
        "microservices": {
            "stt_service": stt_client.base_url,
            "diarization_service": diarization_client.base_url,
        }
    }


# Include routers
from routers import sessions, users, templates, transcriptions, ai_services, livekit, audio, realtime

app.include_router(sessions.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1") 
app.include_router(templates.router, prefix="/api/v1")
app.include_router(transcriptions.router, prefix="/api/v1")
app.include_router(ai_services.router, prefix="/api/v1")
app.include_router(livekit.router, prefix="/api/v1")
app.include_router(audio.router, prefix="/api/v1")
app.include_router(realtime.router, prefix="/api/v1")


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Intrascribe API Service",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
