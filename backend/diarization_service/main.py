"""
Speaker Diarization Microservice Main Application

FastAPI-based microservice for speaker diarization and identification.
Provides REST API endpoints for speaker separation using pyannote.audio.
"""
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Request, status, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.logging import ServiceLogger
from shared.config import base_config, speaker_config
from shared.models import SpeakerDiarizationRequest, SpeakerDiarizationResponse, ServiceHealthCheck
from shared.utils import timing_decorator, validate_audio_format

from models import diarization_manager

# Initialize logger
logger = ServiceLogger("diarization-service")

# Service startup time
service_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage service lifecycle"""
    # Startup
    logger.service_start(8002)
    
    # Check if diarization is available
    if not diarization_manager.is_available():
        logger.warning("Speaker diarization not available - service will run in limited mode")
    
    logger.service_ready(8002)
    
    yield
    
    # Shutdown
    logger.service_stop()


# Create FastAPI app
app = FastAPI(
    title="Intrascribe Speaker Diarization Service",
    description="Speaker separation and identification microservice using pyannote.audio",
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
class DiarizeRequest(BaseModel):
    """HTTP request model for diarization"""
    audio_data: str  # Hex-encoded audio data
    file_format: str
    session_id: str = None


class DiarizeResponse(BaseModel):
    """HTTP response model for diarization"""
    success: bool
    segments: list
    speaker_count: int
    processing_time_ms: int = 0
    error_message: Optional[str] = None


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
    model_info = diarization_manager.get_model_info()
    uptime = int(time.time() - service_start_time)
    
    return ServiceHealthCheck(
        service_name="diarization-service",
        status="healthy",
        version="1.0.0",
        uptime_seconds=uptime,
        details={
            "diarization_available": model_info["available"],
            "model_load_time": model_info["load_time_seconds"],
            "model_name": model_info["model_name"],
            "device": model_info["device"],
            "token_configured": model_info["huggingface_token_configured"],
        }
    )


@app.get("/info")
async def service_info() -> Dict[str, Any]:
    """Get detailed service information"""
    model_info = diarization_manager.get_model_info()
    uptime = int(time.time() - service_start_time)
    
    return {
        "service": {
            "name": "diarization-service",
            "version": "1.0.0",
            "uptime_seconds": uptime,
            "environment": base_config.environment,
        },
        "diarization": model_info,
        "config": {
            "min_segment_duration": speaker_config.min_segment_duration,
            "max_speakers": speaker_config.max_speakers,
            "pyannote_model": speaker_config.pyannote_model,
        }
    }


@app.post("/diarize", response_model=DiarizeResponse)
@timing_decorator
async def diarize_audio_data(request: DiarizeRequest):
    """
    Perform speaker diarization on audio data.
    
    Args:
        request: Diarization request with audio data
    
    Returns:
        Diarization response with speaker segments
    """
    try:
        logger.info(f"Processing diarization request for session: {request.session_id}")
        
        # Validate audio format
        if not validate_audio_format(request.file_format):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported audio format: {request.file_format}"
            )
        
        # Check if diarization is available
        if not diarization_manager.is_available():
            logger.warning("Diarization not available, creating fallback single speaker")
            
            # Estimate audio duration (assuming 16kHz, 16-bit audio)
            estimated_duration = len(request.audio_data) / (16000 * 2)
            
            fallback_segments = diarization_manager.create_fallback_segments(estimated_duration)
            
            return DiarizeResponse(
                success=True,
                segments=[{
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "speaker_label": seg.speaker_label,
                    "duration": seg.duration
                } for seg in fallback_segments],
                speaker_count=1,
                processing_time_ms=0,
                error_message="Diarization not available - using single speaker fallback"
            )
        
        # Convert hex string back to bytes
        try:
            audio_bytes = bytes.fromhex(request.audio_data)
            logger.debug(f"🔍 Converted hex audio data: {len(audio_bytes)} bytes")
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid hex audio data: {e}"
            )
        
        # Perform diarization
        result = diarization_manager.diarize_audio_data(
            audio_bytes,  # Use converted bytes
            request.file_format, 
            request.session_id
        )
        
        if result.success:
            logger.success(f"Diarization completed: {result.speaker_count} speakers, {len(result.segments)} segments")
        else:
            logger.error(f"Diarization failed: {result.error_message}")
        
        return DiarizeResponse(
            success=result.success,
            segments=[{
                "start_time": seg.start_time,
                "end_time": seg.end_time,
                "speaker_label": seg.speaker_label,
                "duration": seg.duration
            } for seg in result.segments],
            speaker_count=result.speaker_count,
            processing_time_ms=result.processing_time_ms,
            error_message=result.error_message if result.error_message else None
        )
        
    except Exception as e:
        logger.error("Diarization request failed", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Diarization failed: {str(e)}"
        )


@app.post("/diarize-file")
@timing_decorator
async def diarize_audio_file(
    audio_file: UploadFile = File(...),
    session_id: str = None
):
    """
    Perform speaker diarization on uploaded audio file.
    
    Args:
        audio_file: Uploaded audio file
        session_id: Optional session ID for logging
    
    Returns:
        Diarization response with speaker segments
    """
    try:
        logger.info(f"Processing file diarization: {audio_file.filename}")
        
        # Read file content
        audio_data = await audio_file.read()
        
        # Extract file format from filename
        file_format = "wav"  # default
        if audio_file.filename:
            file_format = audio_file.filename.split('.')[-1].lower()
        
        # Validate audio format
        if not validate_audio_format(file_format):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported audio format: {file_format}"
            )
        
        # Create request object
        request = DiarizeRequest(
            audio_data=audio_data,
            file_format=file_format,
            session_id=session_id
        )
        
        # Process using the same logic as data endpoint
        return await diarize_audio_data(request)
        
    except Exception as e:
        logger.error("File diarization failed", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File diarization failed: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8002,
        reload=False,  # Disable reload to prevent model reloading
        log_level="info"
    )
