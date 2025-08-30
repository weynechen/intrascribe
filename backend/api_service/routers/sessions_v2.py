"""
Sessions V2 API routes for async operations.
Handles session finalization, batch operations, and long-running tasks.
"""
import os
import sys
import uuid
import tempfile
import wave
import subprocess
import time
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.utils import timing_decorator
from shared.models import SessionStatus

from core.auth import get_current_user, verify_session_ownership
from core.redis import redis_manager
from core.database import db_manager
from repositories.session_repository import session_repository
from routers.transcriptions import transcription_repository

logger = ServiceLogger("sessions-v2-api")

router = APIRouter(prefix="/v2/sessions", tags=["Sessions V2"])


def extract_session_id_from_path(session_id_param: str) -> str:
    """Extract actual session ID from path parameter (handles room name format)"""
    if session_id_param.startswith("intrascribe_room_"):
        return session_id_param.replace("intrascribe_room_", "")
    return session_id_param


def _combine_audio_segments(segments: List[Dict[str, Any]]) -> np.ndarray:
    """Combine audio segments into single array"""
    if not segments:
        return np.array([])
    
    combined = []
    for segment in segments:
        audio_data = segment.get('audio_data', [])
        if audio_data:
            # Convert list back to numpy array
            audio_array = np.array(audio_data, dtype=np.int16)
            combined.append(audio_array.flatten())
    
    if combined:
        return np.concatenate(combined)
    else:
        return np.array([])


async def _convert_to_mp3(audio_data: np.ndarray, sample_rate: int) -> Tuple[bytes, int, float]:
    """Convert audio data to MP3 format"""
    try:
        # Ensure audio data is int16 format
        if audio_data.dtype == np.float32:
            audio_data = (audio_data * 32767).astype(np.int16)
        elif audio_data.dtype != np.int16:
            audio_data = audio_data.astype(np.int16)
        
        # Create temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_wav_path = temp_wav.name
        
        # Write WAV file
        with wave.open(temp_wav_path, 'wb') as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16-bit = 2 bytes
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data.tobytes())
        
        try:
            # Calculate duration
            duration_seconds = len(audio_data) / sample_rate
            
            # Convert to MP3 using ffmpeg
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_mp3:
                temp_mp3_path = temp_mp3.name
            
            try:
                # Simple ffmpeg command
                cmd = [
                    'ffmpeg',
                    '-i', temp_wav_path,
                    '-codec:a', 'mp3',
                    '-b:a', '128k',
                    '-y',  # Overwrite output file
                    temp_mp3_path
                ]
                
                logger.debug(f"🔧 Converting to MP3: {' '.join(cmd)}")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode != 0:
                    raise Exception(f"ffmpeg conversion failed: {result.stderr}")
                
                # Read MP3 data
                with open(temp_mp3_path, 'rb') as mp3_file:
                    mp3_data = mp3_file.read()
                
                return mp3_data, len(mp3_data), duration_seconds
                
            finally:
                # Clean up MP3 temp file
                try:
                    if os.path.exists(temp_mp3_path):
                        os.unlink(temp_mp3_path)
                except Exception as e:
                    logger.warning(f"Failed to clean MP3 temp file: {e}")
                    
        finally:
            # Clean up WAV temp file
            try:
                if os.path.exists(temp_wav_path):
                    os.unlink(temp_wav_path)
            except Exception as e:
                logger.warning(f"Failed to clean WAV temp file: {e}")
        
    except Exception as e:
        logger.error(f"Audio format conversion failed: {e}")
        raise


async def _upload_audio_to_storage(audio_data: bytes, session_id: str, user_id: str) -> Dict[str, Any]:
    """Upload audio file to Supabase Storage"""
    try:
        # Generate storage path
        timestamp = int(time.time())
        storage_path = f"raw/{user_id}/{session_id}_{timestamp}.mp3"
        
        # Get service role client for upload
        client = db_manager.get_service_client()
        
        # Upload file to storage
        logger.info(f"📤 Uploading audio file to: {storage_path}")
        
        result = client.storage.from_("audio-recordings").upload(
            path=storage_path,
            file=audio_data,
            file_options={"content-type": "audio/mpeg"}
        )
        
        if hasattr(result, 'error') and result.error:
            logger.error(f"Storage upload failed: {result.error}")
            return {"success": False, "error": str(result.error)}
        
        # Generate public access URL
        public_url = None
        try:
            url_result = client.storage.from_("audio-recordings").get_public_url(storage_path)
            if url_result:
                public_url = url_result
                logger.info(f"🔗 Generated public URL: {public_url}")
        except Exception as e:
            logger.warning(f"Failed to generate public URL: {e}")
        
        logger.info(f"✅ Audio file uploaded successfully: {storage_path}")
        
        return {
            "success": True,
            "storage_path": storage_path,
            "public_url": public_url
        }
        
    except Exception as e:
        logger.error(f"Failed to upload audio file to storage: {e}")
        return {"success": False, "error": str(e)}


async def _process_cached_audio(session_id: str, user_id: str, audio_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Process cached audio segments and save to storage"""
    try:
        if not audio_segments:
            return {"success": False, "message": "No audio data to process"}
        
        logger.info(f"🎵 Processing {len(audio_segments)} audio segments for session: {session_id}")
        
        # Combine audio segments
        combined_audio = _combine_audio_segments(audio_segments)
        if len(combined_audio) == 0:
            return {"success": False, "message": "No valid audio data"}
        
        # Get sample rate from first segment
        sample_rate = audio_segments[0].get("sample_rate", 24000)
        
        # Convert to MP3 format
        mp3_data, file_size, duration_seconds = await _convert_to_mp3(combined_audio, sample_rate)
        
        # Upload to Supabase Storage
        storage_result = await _upload_audio_to_storage(mp3_data, session_id, user_id)
        
        if not storage_result["success"]:
            return {"success": False, "error": f"Audio upload failed: {storage_result.get('error')}"}
        
        # Save audio file record to database
        audio_file_data = {
            "session_id": session_id,
            "user_id": user_id,
            "original_filename": f"session_{session_id}.mp3",
            "storage_path": storage_result["storage_path"],
            "public_url": storage_result.get("public_url"),
            "file_size_bytes": file_size,
            "duration_seconds": duration_seconds,
            "format": "mp3",
            "sample_rate": sample_rate,
            "upload_status": "completed",
            "processing_status": "completed"
        }
        
        # Insert into database using service client
        client = db_manager.get_service_client()
        result = client.table('audio_files').insert(audio_file_data).execute()
        
        if result.data:
            audio_file_id = result.data[0]["id"]
            logger.success(f"Audio file record saved: {audio_file_id}")
            
            return {
                "success": True,
                "audio_file_id": audio_file_id,
                "storage_path": storage_result["storage_path"],
                "duration_seconds": duration_seconds,
                "file_size": file_size
            }
        else:
            return {"success": False, "error": "Failed to save audio file record"}
            
    except Exception as e:
        logger.error(f"Audio processing failed: {e}")
        return {"success": False, "error": str(e)}


async def finalize_session_task(session_id: str, user_id: str):
    """
    Background task to finalize session by saving Redis data to database.
    
    Args:
        session_id: Session ID to finalize
        user_id: User ID for verification
    """
    try:
        logger.info(f"Starting session finalization: {session_id}")
        
        # Get session to verify it exists and belongs to user
        session = session_repository.get_session_by_id(session_id, user_id)
        if not session:
            logger.error(f"Session not found or access denied: {session_id}")
            return
        
        # Get transcription and audio segments from Redis
        transcription_segments = await redis_manager.get_session_transcriptions(session_id)
        audio_segments = await redis_manager.get_session_audio_segments(session_id)
        
        logger.info(f"Retrieved {len(transcription_segments)} transcription segments and {len(audio_segments)} audio segments from Redis for session: {session_id}")
        
        audio_file_id = None
        total_duration = 0.0
        
        # Process audio data if available
        if audio_segments:
            try:
                audio_result = await _process_cached_audio(session_id, user_id, audio_segments)
                if audio_result.get("success"):
                    audio_file_id = audio_result.get("audio_file_id")
                    total_duration = audio_result.get("duration_seconds", 0.0)
                    logger.success(f"Audio file processed and saved: {audio_file_id}")
                else:
                    logger.warning(f"Audio processing failed: {audio_result.get('error')}")
            except Exception as e:
                logger.error(f"Audio processing failed: {e}")
        
        # Process transcription data if available
        if transcription_segments:
            # Combine all segment texts into full transcription content
            full_text_parts = []
            segment_data = []
            
            for i, segment in enumerate(transcription_segments):
                text = segment.get("text", "").strip()
                if text:
                    full_text_parts.append(text)
                    
                    # Prepare segment data for database storage
                    segment_data.append({
                        "index": i,
                        "speaker": segment.get("speaker", "Speaker 1"),
                        "timestamp": segment.get("timestamp"),
                        "text": text,
                        "is_final": segment.get("is_final", True)
                    })
            
            if full_text_parts:
                # Create full transcription content
                full_content = " ".join(full_text_parts)
                
                # Save transcription to database
                transcription = transcription_repository.save_transcription(
                    session_id=session_id,
                    content=full_content,
                    language=session.language,
                    segments=segment_data,
                    stt_model="agent_microservice",
                    word_count=len(full_content.split())
                )
                
                logger.success(f"Saved transcription to database: {transcription.get('id')}")
        
        # Update session status to completed with duration
        updated_session = session_repository.update_session(
            session_id=session_id,
            status=SessionStatus.COMPLETED,
            user_id=user_id
        )
        
        # Also update duration if we have audio data
        if total_duration > 0:
            try:
                client = db_manager.get_service_client()
                client.table('recording_sessions').update({
                    "duration_seconds": int(total_duration),
                    "ended_at": datetime.utcnow().isoformat()
                }).eq('id', session_id).execute()
                logger.info(f"Updated session duration: {total_duration} seconds")
            except Exception as e:
                logger.warning(f"Failed to update session duration: {e}")
        
        if updated_session:
            logger.success(f"Session finalized successfully: {session_id}")
        else:
            logger.error(f"Failed to update session status: {session_id}")
        
        # Clear Redis data after successful database save
        if transcription_segments:
            await redis_manager.clear_session_transcriptions(session_id)
            logger.info(f"Cleared Redis transcription data for session: {session_id}")
        
        if audio_segments:
            await redis_manager.clear_session_audio_segments(session_id)
            logger.info(f"Cleared Redis audio data for session: {session_id}")
            
    except Exception as e:
        logger.error(f"Session finalization failed for {session_id}: {e}")
        # Note: In a production system, you might want to store this error 
        # in a task status table for the frontend to query


@router.post("/{session_id}/finalize")
@timing_decorator
async def finalize_session(
    session_id: str,
    current_user = Depends(get_current_user)
):
    """
    Finalize session by processing Redis data and saving to database.
    
    This operation processes transcription data from Redis
    and saves it to the permanent database.
    
    Args:
        session_id: Session ID or room name (will extract actual session ID)
        current_user: Current authenticated user
    
    Returns:
        Task completion result
    """
    try:
        # Extract actual session ID from path parameter
        actual_session_id = extract_session_id_from_path(session_id)
        logger.info(f"Starting session finalization: {session_id} -> {actual_session_id}")
        
        # Verify session ownership manually
        from core.auth import auth_manager
        if not auth_manager.verify_session_ownership(actual_session_id, current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # Execute finalization directly (synchronously)
        await finalize_session_task(actual_session_id, current_user.id)
        
        # Return success response (V2 API format compatible)
        return {
            "success": True,
            "message": "Session finalized successfully",
            "timestamp": datetime.utcnow().isoformat(),
            "task_id": str(uuid.uuid4()),  # Mock task ID for compatibility
            "status": "success",
            "result": {
                "message": "Session finalized successfully",
                "session_id": actual_session_id,
                "transcription_saved": True,
                "total_duration_seconds": 0  # Will be calculated
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to finalize session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to finalize session"
        )


@router.get("/{session_id}/status")
@timing_decorator  
async def get_session_status_v2(
    session_id: str,
    current_user = Depends(get_current_user)
):
    """
    Get detailed session status for V2 API.
    
    Args:
        session_id: Session ID or room name (will extract actual session ID)
        current_user: Current authenticated user
    
    Returns:
        Detailed session status
    """
    try:
        # Extract actual session ID from path parameter
        actual_session_id = extract_session_id_from_path(session_id)
        logger.info(f"Getting session status: {session_id} -> {actual_session_id}")
        
        # Verify session ownership manually
        from core.auth import auth_manager
        if not auth_manager.verify_session_ownership(actual_session_id, current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # Get session from database
        session = session_repository.get_session_by_id(actual_session_id, current_user.id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Get Redis transcription and audio counts
        transcription_segments = await redis_manager.get_session_transcriptions(actual_session_id)
        audio_segments = await redis_manager.get_session_audio_segments(actual_session_id)
        
        # Get session state from Redis
        session_state = await redis_manager.get_session_state(actual_session_id)
        
        return {
            "success": True,
            "message": "Session status retrieved",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "id": session.id,
                "title": session.title,
                "status": session.status.value,
                "language": session.language,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "redis_transcription_segments": len(transcription_segments),
                "redis_audio_segments": len(audio_segments),
                "redis_state": session_state,
                "is_finalized": session.status == SessionStatus.COMPLETED
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get session status"
        )
