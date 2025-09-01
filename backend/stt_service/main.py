"""
STT Microservice Main Application

FastAPI-based microservice for speech-to-text transcription.
Provides REST API endpoints for audio transcription using FunASR models.
"""
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.logging import ServiceLogger
from shared.config import base_config, stt_config
from shared.models import AudioData, TranscriptionRequest, TranscriptionResponse, ServiceHealthCheck
from shared.utils import timing_decorator

from models import model_manager

# Initialize logger
logger = ServiceLogger("stt-service")

# Service startup time
service_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage service lifecycle"""
    # Startup
    logger.service_start(8001)
    
    # Ensure model is loaded
    if not model_manager.is_loaded():
        logger.error("STT model failed to load during startup")
        raise RuntimeError("STT model not available")
    
    logger.service_ready(8001)
    
    yield
    
    # Shutdown
    logger.service_stop()


# Create FastAPI app
app = FastAPI(
    title="Intrascribe STT Service",
    description="Speech-to-Text microservice using FunASR",
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


# Request/Response models
class TranscribeRequest(BaseModel):
    """HTTP request model for transcription"""
    audio_data: AudioData
    session_id: str
    language: str = "zh-CN"


class TranscribeResponse(BaseModel):
    """HTTP response model for transcription"""
    success: bool
    text: str
    confidence_score: float = 1.0
    processing_time_ms: int = 0
    error_message: str = None


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


# API Endpoints
@app.get("/health", response_model=ServiceHealthCheck)
async def health_check():
    """Service health check endpoint"""
    model_info = model_manager.get_model_info()
    uptime = int(time.time() - service_start_time)
    
    return ServiceHealthCheck(
        service_name="stt-service",
        status="healthy" if model_info["loaded"] else "unhealthy",
        version="1.0.0",
        uptime_seconds=uptime,
        details={
            "model_loaded": model_info["loaded"],
            "model_load_time": model_info["load_time_seconds"],
            "model_device": model_info["device"],
            "model_dir": model_info["model_dir"],
        }
    )


@app.get("/info")
async def service_info() -> Dict[str, Any]:
    """Get detailed service information"""
    model_info = model_manager.get_model_info()
    uptime = int(time.time() - service_start_time)
    
    return {
        "service": {
            "name": "stt-service",
            "version": "1.0.0",
            "uptime_seconds": uptime,
            "environment": base_config.environment,
        },
        "model": model_info,
        "config": {
            "max_audio_length": stt_config.max_audio_length,
            "batch_size": stt_config.batch_size,
        }
    }


@app.post("/transcribe", response_model=TranscribeResponse)
@timing_decorator
async def transcribe_audio(request: TranscribeRequest):
    """
    Transcribe audio to text.
    
    Args:
        request: Transcription request with audio data
    
    Returns:
        Transcription response with text result
    """
    try:
        logger.info(f"Processing transcription request for session: {request.session_id}")
        
        # Validate model availability
        if not model_manager.is_loaded():
            logger.error("STT model not available")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="STT model not available"
            )
        
        # Perform transcription
        result = model_manager.transcribe(request.audio_data)
        
        if result.success:
            logger.success(f"Transcription completed: '{result.text[:50]}...'")
        else:
            logger.error(f"Transcription failed: {result.error_message}")
        
        return TranscribeResponse(
            success=result.success,
            text=result.text,
            confidence_score=result.confidence_score,
            processing_time_ms=result.processing_time_ms,
            error_message=result.error_message or ""
        )
        
    except Exception as e:
        logger.error("Transcription request failed", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {str(e)}"
        )


@app.post("/batch-transcribe")
@timing_decorator
async def batch_transcribe(requests: list[TranscribeRequest]):
    """
    Batch transcription for multiple audio files.
    
    Args:
        requests: List of transcription requests
    
    Returns:
        List of transcription responses
    """
    try:
        logger.info(f"Processing batch transcription: {len(requests)} requests")
        
        # Validate batch size
        if len(requests) > stt_config.batch_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Batch size too large. Max: {stt_config.batch_size}"
            )
        
        # Validate model availability
        if not model_manager.is_loaded():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="STT model not available"
            )
        
        # Process each request
        results = []
        for req in requests:
            result = model_manager.transcribe(req.audio_data)
            results.append(TranscribeResponse(
                success=result.success,
                text=result.text,
                confidence_score=result.confidence_score,
                processing_time_ms=result.processing_time_ms,
                error_message=result.error_message or ""
            ))
        
        successful_count = sum(1 for r in results if r.success)
        logger.success(f"Batch transcription completed: {successful_count}/{len(requests)} successful")
        
        return results
        
    except Exception as e:
        logger.error("Batch transcription failed", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch transcription failed: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,  # Disable reload to prevent model reloading
        log_level="info"
    )
