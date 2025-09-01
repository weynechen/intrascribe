"""
Transcription management API routes.
Handles transcription CRUD operations and real-time transcription data.
"""
import os
import sys
import time
import tempfile
import numpy as np
import io
import librosa
from typing import List, Dict, Any, Tuple, Optional
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from datetime import datetime

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.utils import timing_decorator
from shared.models import AudioData, SessionStatus

from core.auth import get_current_user, verify_session_ownership
from core.database import db_manager
from schemas import (
    TranscriptionSaveRequest, TranscriptionUpdateRequest, 
    TranscriptionResponse, BatchTranscriptionRequest, BatchTranscriptionResponse
)
from clients.microservice_clients import stt_client, diarization_client
from repositories.session_repository import session_repository

logger = ServiceLogger("transcriptions-api")

router = APIRouter(prefix="/transcriptions", tags=["Transcriptions"])


class TranscriptionRepository:
    """Repository for transcription operations"""
    
    def __init__(self):
        from core.database import db_manager
        self.db = db_manager
    
    def save_transcription(
        self,
        session_id: str,
        content: str,
        language: str = "zh-CN",
        confidence_score: float = None,
        segments: List[Dict[str, Any]] = None,
        stt_model: str = "local_funasr",
        word_count: int = None
    ) -> Dict[str, Any]:
        """Save transcription to database"""
        try:
            client = self.db.get_service_client()
            
            transcription_data = {
                "session_id": session_id,
                "content": content,
                "language": language,
                "confidence_score": confidence_score,
                "segments": segments or [],
                "stt_model": stt_model,
                "word_count": word_count or len(content.split()),
                "status": "completed",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            result = client.table('transcriptions').insert(transcription_data).execute()
            
            if not result.data:
                raise Exception("Failed to save transcription")
            
            return result.data[0]
            
        except Exception as e:
            logger.error(f"Failed to save transcription: {e}")
            raise
    
    def get_session_transcriptions(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all transcriptions for a session"""
        try:
            client = self.db.get_service_client()
            
            result = client.table('transcriptions')\
                .select('*')\
                .eq('session_id', session_id)\
                .order('created_at')\
                .execute()
            
            return result.data
            
        except Exception as e:
            logger.error(f"Failed to get transcriptions for session {session_id}: {e}")
            return []


# Global repository instance
transcription_repository = TranscriptionRepository()


@router.post("/", response_model=TranscriptionResponse)
@timing_decorator
async def save_transcription(
    request: TranscriptionSaveRequest,
    current_user = Depends(get_current_user)
):
    """
    Save transcription data.
    
    Args:
        request: Transcription save request
        current_user: Current authenticated user
    
    Returns:
        Saved transcription data
    """
    try:
        # Verify session ownership
        session = session_repository.get_session_by_id(request.session_id, current_user.id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session"
            )
        
        # Save transcription
        transcription = transcription_repository.save_transcription(
            session_id=request.session_id,
            content=request.content,
            language=request.language,
            confidence_score=request.confidence_score,
            segments=request.segments,
            stt_model=request.stt_model,
            word_count=request.word_count
        )
        
        logger.success(f"Saved transcription: {transcription['id']}")
        
        return TranscriptionResponse(
            id=transcription["id"],
            session_id=transcription["session_id"],
            content=transcription["content"],
            language=transcription["language"],
            status=transcription["status"],
            word_count=transcription["word_count"],
            created_at=transcription["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save transcription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save transcription"
        )


@router.put("/{transcription_id}", response_model=TranscriptionResponse)
@timing_decorator
async def update_transcription(
    transcription_id: str,
    request: TranscriptionUpdateRequest,
    current_user = Depends(get_current_user)
):
    """
    Update transcription data.
    
    Args:
        transcription_id: Transcription ID
        request: Transcription update request
        current_user: Current authenticated user
    
    Returns:
        Updated transcription data
    """
    try:
        client = transcription_repository.db.get_service_client()
        
        # Verify transcription exists and user has access
        transcription_result = client.table('transcriptions').select('*').eq('id', transcription_id).execute()
        
        if not transcription_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transcription not found"
            )
        
        transcription = transcription_result.data[0]
        
        # Verify session ownership
        session = session_repository.get_session_by_id(transcription["session_id"], current_user.id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this transcription"
            )
        
        # Update transcription
        updates = {}
        
        if request.content is not None:
            updates["content"] = request.content
            updates["word_count"] = len(request.content.split())
        
        if request.segments:
            updates["segments"] = request.segments
            # Rebuild content from segments if not provided
            if request.content is None:
                content = " ".join(segment.get("text", "") for segment in request.segments if segment.get("text"))
                updates["content"] = content
                updates["word_count"] = len(content.split())
        
        if updates:
            updates["updated_at"] = datetime.utcnow().isoformat()
            
            result = client.table('transcriptions')\
                .update(updates)\
                .eq('id', transcription_id)\
                .execute()
            
            if not result.data:
                raise Exception("Transcription update failed")
            
            updated_transcription = result.data[0]
        else:
            updated_transcription = transcription
        
        logger.success(f"Updated transcription: {transcription_id}")
        
        return TranscriptionResponse(
            id=updated_transcription["id"],
            session_id=updated_transcription["session_id"],
            content=updated_transcription["content"],
            language=updated_transcription["language"],
            status=updated_transcription["status"],
            word_count=updated_transcription["word_count"],
            created_at=updated_transcription["created_at"],
            updated_at=updated_transcription.get("updated_at")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update transcription {transcription_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update transcription"
        )


@router.post("/batch", response_model=BatchTranscriptionResponse)
@timing_decorator
async def batch_transcription(
    audio_file: UploadFile = File(...),
    title: str = "Batch Transcription Session",
    language: str = "zh-CN",
    current_user = Depends(get_current_user)
):
    """
    Batch transcription for uploaded audio file.
    Handles complete audio processing including speaker diarization, transcription, and storage.
    
    Args:
        audio_file: Uploaded audio file
        title: Session title
        language: Language code
        current_user: Current authenticated user
    
    Returns:
        Batch transcription task information
    """
    try:
        logger.info(f"Processing batch transcription: {audio_file.filename}")
        
        # Create session for batch processing
        session = session_repository.create_session(
            user_id=current_user.id,
            title=title,
            language=language
        )
        
        # Read audio file
        audio_content = await audio_file.read()
        
        # Determine audio format
        file_format = "wav"
        if audio_file.filename:
            file_format = audio_file.filename.split('.')[-1].lower()
        
        # Process audio with speaker diarization and transcription
        processing_result = await _process_batch_audio_file(
            audio_content=audio_content,
            file_format=file_format,
            original_filename=audio_file.filename,
            session_id=session.id,
            user_id=current_user.id,
            language=language
        )
        
        if processing_result["success"]:
            logger.success(f"Batch transcription completed: {session.id}")
            
            return BatchTranscriptionResponse(
                task_id=session.id,
                session_id=session.id,
                status="completed",
                message=f"Batch transcription completed successfully. "
                       f"Duration: {processing_result.get('duration_seconds', 0):.1f}s, "
                       f"Segments: {processing_result.get('total_segments', 0)}, "
                       f"Speakers: {processing_result.get('speaker_count', 1)}"
            )
        else:
            logger.error(f"Batch transcription failed: {processing_result.get('error')}")
            
            return BatchTranscriptionResponse(
                task_id=session.id,
                session_id=session.id,
                status="failed",
                message=f"Transcription failed: {processing_result.get('error')}"
            )
        
    except Exception as e:
        logger.error(f"Batch transcription failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Batch transcription failed"
        )


async def _process_batch_audio_file(
    audio_content: bytes,
    file_format: str,
    original_filename: str,
    session_id: str,
    user_id: str,
    language: str = "zh-CN"
) -> Dict[str, Any]:
    """
    Process audio file for batch transcription including speaker diarization and storage.
    
    Args:
        audio_content: Raw audio file bytes
        file_format: Audio file format
        original_filename: Original filename
        session_id: Session ID
        user_id: User ID
        language: Language code
    
    Returns:
        Processing result with success status and details
    """
    try:
        logger.info(f"🎵 Starting batch audio processing: {original_filename}, duration estimation...")
        
        # Step 1: Save audio to temporary file for processing
        with tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False) as temp_file:
            temp_file.write(audio_content)
            temp_audio_path = temp_file.name
        
        try:
            # Step 2: Prepare audio for processing (convert format if needed)
            processed_audio_path, was_converted, converted_file_path = await _prepare_audio_for_processing(
                temp_audio_path, file_format
            )
            
            # Get audio duration for analysis
            duration_seconds = await _get_audio_duration(processed_audio_path)
            logger.info(f"📊 Audio analysis: duration={duration_seconds:.2f}s, format={file_format}")
            
            # Step 3: Perform speaker diarization to get intelligent segments
            logger.info("🎤 Performing speaker diarization...")
            diarization_result = await diarization_client.diarize_audio(
                audio_data=audio_content,
                file_format=file_format,
                session_id=session_id
            )
            
            if not diarization_result.success or not diarization_result.segments:
                logger.warning("Speaker diarization failed, using single speaker mode")
                # Create single segment for entire audio if diarization fails
                speaker_segments = [{
                    "start_time": 0.0,
                    "end_time": duration_seconds,
                    "speaker_label": "Speaker 1",
                    "duration": duration_seconds
                }]
            else:
                # Use diarization results and merge adjacent short segments
                speaker_segments = _merge_adjacent_short_segments(diarization_result.segments)
                logger.info(f"✅ Speaker diarization completed: {len(speaker_segments)} segments, "
                           f"{diarization_result.speaker_count} speakers")
            
            # Step 4: Split audio by speaker segments and transcribe each
            logger.info("✂️ Processing speaker segments...")
            all_transcription_segments = []
            combined_text_parts = []
            
            for i, speaker_segment in enumerate(speaker_segments):
                logger.info(f"🔄 Processing segment {i+1}/{len(speaker_segments)}: "
                           f"{speaker_segment.get('speaker_label', 'Speaker 1')} "
                           f"[{speaker_segment.get('start_time', 0):.1f}s-{speaker_segment.get('end_time', 0):.1f}s]")
                
                # Extract audio segment for this speaker
                segment_audio = await _extract_audio_segment(
                    processed_audio_path,
                    speaker_segment.get('start_time', 0),
                    speaker_segment.get('end_time', duration_seconds)
                )
                
                if segment_audio is None:
                    logger.warning(f"⚠️ Failed to extract audio for segment {i+1}, skipping")
                    continue
                
                # Convert segment to AudioData format for STT
                audio_data_obj = AudioData(
                    sample_rate=24000,  # Use 24000Hz like real-time transcription
                    audio_array=segment_audio.tolist(),
                    format="wav",
                    duration_seconds=speaker_segment.get('duration', 0)
                )
                
                # Transcribe segment
                transcription_result = await stt_client.transcribe_audio(
                    audio_data_obj, 
                    session_id, 
                    language
                )
                
                logger.debug(f"🔍 Segment {i+1} transcription result: "
                            f"success={transcription_result.success}, "
                            f"text_length={len(transcription_result.text)}, "
                            f"text_preview='{transcription_result.text[:50]}...'")
                
                if transcription_result.success and transcription_result.text.strip():
                    segment_text = transcription_result.text.strip()
                    
                    # Clean and validate text content
                    import re
                    segment_text = re.sub(r'<\|[^|]*\|>', '', segment_text).strip()
                    
                    if len(segment_text) > 1 and segment_text not in [".", "。", ",", "，", "?", "？", "!", "！"]:
                        combined_text_parts.append(segment_text)
                        
                        # Create segment data
                        segment_data = {
                            "index": len(all_transcription_segments),
                            "speaker": speaker_segment.get('speaker_label', 'Speaker 1'),
                            "start_time": speaker_segment.get('start_time', 0),
                            "end_time": speaker_segment.get('end_time', 0),
                            "text": segment_text,
                            "confidence_score": transcription_result.confidence_score,
                            "is_final": True
                        }
                        all_transcription_segments.append(segment_data)
                        
                        logger.info(f"✅ Segment {i+1} transcribed: '{segment_text[:50]}...'")
                    else:
                        logger.warning(f"⚠️ Segment {i+1} produced only punctuation, skipping")
                else:
                    error_msg = transcription_result.error_message if not transcription_result.success else "empty result"
                    logger.warning(f"❌ Segment {i+1} transcription failed: {error_msg}")
            
            if not combined_text_parts:
                return {
                    "success": False,
                    "error": "No transcription content generated from audio file"
                }
                
        finally:
            # Cleanup temporary files
            await _cleanup_temp_files(temp_audio_path, was_converted, converted_file_path)
        
        # Step 5: Convert audio to MP3 and save to storage
        mp3_data, file_size, final_duration = await _convert_audio_to_mp3(audio_content, file_format)
        
        # Upload to storage
        storage_result = await _upload_audio_to_storage(
            audio_data=mp3_data,
            session_id=session_id,
            user_id=user_id,
            original_filename=original_filename
        )
        
        if not storage_result["success"]:
            return {
                "success": False,
                "error": f"Audio storage failed: {storage_result.get('error')}"
            }
        
        # Step 6: Save audio file record to database
        audio_file_data = {
            "session_id": session_id,
            "user_id": user_id,
            "original_filename": original_filename,
            "storage_path": storage_result["storage_path"],
            "public_url": storage_result.get("public_url"),
            "file_size_bytes": file_size,
            "duration_seconds": final_duration,
            "format": "mp3",
            "sample_rate": 24000,  # Match real-time transcription sample rate
            "upload_status": "completed",
            "processing_status": "completed"
        }
        
        client = db_manager.get_service_client()
        audio_file_result = client.table('audio_files').insert(audio_file_data).execute()
        
        if not audio_file_result.data:
            return {
                "success": False,
                "error": "Failed to save audio file record to database"
            }
        
        audio_file_id = audio_file_result.data[0]["id"]
        logger.success(f"Audio file record saved: {audio_file_id}")
        
        # Step 7: Save transcription results
        full_content = " ".join(combined_text_parts)
        
        transcription = transcription_repository.save_transcription(
            session_id=session_id,
            content=full_content,
            language=language,
            segments=all_transcription_segments,
            stt_model="local_funasr_batch",
            word_count=len(full_content.split())
        )
        
        # Step 8: Update session status to completed
        session_repository.update_session(
            session_id=session_id,
            status=SessionStatus.COMPLETED,
            user_id=user_id
        )
        
        logger.success(f"✅ Batch transcription fully completed: session={session_id}, "
                      f"audio_file={audio_file_id}, transcription={transcription.get('id')}")
        
        return {
            "success": True,
            "session_id": session_id,
            "audio_file_id": audio_file_id,
            "transcription_id": transcription.get('id'),
            "duration_seconds": final_duration,
            "total_segments": len(all_transcription_segments),
            "speaker_count": 1,  # Single speaker for batch processing
            "transcription_content": full_content
        }
        
    except Exception as e:
        logger.error(f"❌ Batch audio processing failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def _convert_audio_to_mp3(audio_content: bytes, file_format: str) -> Tuple[bytes, int, float]:
    """
    Convert audio to MP3 format using ffmpeg.
    
    Args:
        audio_content: Raw audio bytes
        file_format: Original audio format
    
    Returns:
        Tuple of (mp3_data, file_size, duration_seconds)
    """
    try:
        import subprocess
        
        # Create temporary files
        with tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False) as temp_input:
            temp_input.write(audio_content)
            temp_input_path = temp_input.name
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_output:
            temp_output_path = temp_output.name
        
        try:
            # Use ffmpeg to convert to MP3
            cmd = [
                "ffmpeg",
                "-i", temp_input_path,
                "-codec:a", "mp3",
                "-b:a", "128k",
                "-y",  # Overwrite output file
                temp_output_path
            ]
            
            logger.debug(f"🔧 Converting audio to MP3: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )
            
            if result.returncode != 0:
                logger.error(f"❌ ffmpeg conversion failed: {result.stderr}")
                # Fallback: return original data
                logger.warning("⚠️ Using original audio data as fallback")
                return audio_content, len(audio_content), 0.0
            
            # Read converted MP3 data
            with open(temp_output_path, 'rb') as mp3_file:
                mp3_data = mp3_file.read()
            
            # Get duration using librosa
            audio_for_duration, sr = librosa.load(temp_output_path, sr=None)
            duration_seconds = len(audio_for_duration) / sr
            
            logger.info(f"🔄 Audio converted to MP3: {file_format} -> MP3, "
                       f"original size: {len(audio_content)} bytes, "
                       f"MP3 size: {len(mp3_data)} bytes, "
                       f"duration: {duration_seconds:.2f}s")
            
            return mp3_data, len(mp3_data), duration_seconds
            
        finally:
            # Cleanup temporary files
            try:
                if os.path.exists(temp_input_path):
                    os.unlink(temp_input_path)
                if os.path.exists(temp_output_path):
                    os.unlink(temp_output_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp files: {e}")
                
    except Exception as e:
        logger.error(f"❌ Audio conversion failed: {e}")
        # Return original data if conversion fails
        return audio_content, len(audio_content), 0.0


async def _upload_audio_to_storage(
    audio_data: bytes,
    session_id: str,
    user_id: str,
    original_filename: str
) -> Dict[str, Any]:
    """
    Upload audio file to Supabase Storage.
    
    Args:
        audio_data: Audio file bytes
        session_id: Session ID
        user_id: User ID
        original_filename: Original filename
    
    Returns:
        Upload result with storage path and public URL
    """
    try:
        # Generate storage path for batch transcription
        timestamp = int(time.time())
        file_extension = "mp3"  # Always save as MP3
        storage_path = f"batch-transcription/{user_id}/{session_id}_{timestamp}.{file_extension}"
        
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
        logger.error(f"Audio upload to storage failed: {e}")
        return {"success": False, "error": str(e)}


async def _prepare_audio_for_processing(audio_path: str, file_format: str) -> Tuple[str, bool, Optional[str]]:
    """Prepare audio file for processing (convert format if needed)"""
    processed_audio_path = audio_path
    was_converted = False
    converted_file_path = None
    
    if file_format.lower() in ['mp3', 'mpeg']:
        logger.info("🔄 Converting MP3 to WAV for speaker diarization...")
        try:
            import subprocess
            
            # Create WAV output file
            wav_output_path = audio_path.replace(f".{file_format}", ".wav")
            
            cmd = [
                "ffmpeg",
                "-i", audio_path,
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-y",
                wav_output_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0 and os.path.exists(wav_output_path):
                processed_audio_path = wav_output_path
                was_converted = True
                converted_file_path = wav_output_path
                logger.info(f"✅ Audio converted to WAV: {wav_output_path}")
            else:
                logger.warning(f"⚠️ Audio conversion failed, using original: {result.stderr}")
                
        except Exception as e:
            logger.warning(f"⚠️ Audio conversion failed: {e}, using original file")
    
    return processed_audio_path, was_converted, converted_file_path


async def _get_audio_duration(audio_file_path: str) -> float:
    """Get audio file duration in seconds"""
    try:
        # Use librosa to get duration
        audio_data, sample_rate = librosa.load(audio_file_path, sr=None)
        duration = len(audio_data) / sample_rate
        return duration
    except Exception as e:
        logger.error(f"❌ Failed to get audio duration: {e}")
        return 0.0


def _merge_adjacent_short_segments(segments) -> List[Dict[str, Any]]:
    """
    Merge adjacent short segments of the same speaker
    Based on reference implementation logic
    """
    if not segments:
        return []
    
    # Convert segments to dict format for easier processing
    segment_dicts = []
    for seg in segments:
        if hasattr(seg, 'start_time'):
            # SpeakerSegment object
            segment_dicts.append({
                "start_time": seg.start_time,
                "end_time": seg.end_time,
                "speaker_label": seg.speaker_label,
                "duration": seg.duration
            })
        else:
            # Already a dict
            segment_dicts.append(seg)
    
    merged_segments = []
    current_segment = segment_dicts[0]
    
    for segment in segment_dicts[1:]:
        # Check if current and next segment are from same speaker and both are short (< 5s)
        current_duration = current_segment["end_time"] - current_segment["start_time"]
        next_duration = segment["end_time"] - segment["start_time"]
        
        if (current_segment["speaker_label"] == segment["speaker_label"] and 
            current_duration < 5.0 and next_duration < 5.0):
            # Merge segments
            logger.debug(f"🔗 Merging segments: {current_segment['speaker_label']} "
                        f"[{current_segment['start_time']:.1f}s-{current_segment['end_time']:.1f}s] + "
                        f"[{segment['start_time']:.1f}s-{segment['end_time']:.1f}s]")
            
            current_segment = {
                "start_time": current_segment["start_time"],
                "end_time": segment["end_time"],
                "speaker_label": current_segment["speaker_label"],
                "duration": segment["end_time"] - current_segment["start_time"]
            }
        else:
            # No merge, add current segment to result and move to next
            merged_segments.append(current_segment)
            current_segment = segment
    
    # Add the last segment
    merged_segments.append(current_segment)
    
    # Filter out segments shorter than 1s
    filtered_segments = []
    removed_count = 0
    
    for segment in merged_segments:
        segment_duration = segment["end_time"] - segment["start_time"]
        if segment_duration >= 1.0:
            filtered_segments.append(segment)
        else:
            removed_count += 1
            logger.debug(f"🗑️ Removing short segment: {segment['speaker_label']} "
                        f"[{segment['start_time']:.1f}s-{segment['end_time']:.1f}s] "
                        f"duration: {segment_duration:.2f}s")
    
    if removed_count > 0:
        logger.info(f"🗑️ Removed {removed_count} segments shorter than 1s")
    
    logger.info(f"✅ Segment optimization complete: {len(segment_dicts)} -> {len(filtered_segments)} segments")
    
    return filtered_segments


async def _extract_audio_segment(audio_path: str, start_time: float, end_time: float) -> Optional[np.ndarray]:
    """Extract audio segment from file between start_time and end_time"""
    try:
        # Load audio with librosa
        audio_data, sample_rate = librosa.load(audio_path, sr=24000)  # Use 24000Hz
        
        # Calculate sample indices
        start_sample = int(start_time * sample_rate)
        end_sample = int(end_time * sample_rate)
        
        # Extract segment
        segment_audio = audio_data[start_sample:end_sample]
        
        # Convert to format expected by STT (following real-time transcription format)
        if segment_audio.dtype == np.float32:
            # Convert to int16 first, then back to float32 (matching real-time format)
            audio_int16 = (segment_audio * 32768.0).astype(np.int16)
            audio_2d = audio_int16.reshape(1, -1)
            audio_float32 = audio_2d.flatten().astype(np.float32)
        else:
            audio_float32 = segment_audio.astype(np.float32)
        
        # Validate segment has content
        audio_energy = np.sqrt(np.mean(audio_float32**2))
        if audio_energy < 0.01:
            logger.warning(f"⚠️ Audio segment [{start_time:.1f}s-{end_time:.1f}s] appears to be silent")
            return None
        
        logger.debug(f"🔊 Extracted segment: duration={(end_time-start_time):.2f}s, "
                    f"samples={len(audio_float32)}, energy={audio_energy:.4f}")
        
        return audio_float32
        
    except Exception as e:
        logger.error(f"❌ Failed to extract audio segment [{start_time:.1f}s-{end_time:.1f}s]: {e}")
        return None


async def _cleanup_temp_files(temp_audio_path: str, was_converted: bool, converted_file_path: Optional[str]):
    """Cleanup temporary files"""
    try:
        # Cleanup original temp file
        if os.path.exists(temp_audio_path):
            os.unlink(temp_audio_path)
            logger.debug(f"🗑️ Cleaned up temp file: {temp_audio_path}")
        
        # Cleanup converted file
        if was_converted and converted_file_path and os.path.exists(converted_file_path):
            os.unlink(converted_file_path)
            logger.debug(f"🗑️ Cleaned up converted file: {converted_file_path}")
            
    except Exception as e:
        logger.warning(f"⚠️ Failed to cleanup temp files: {e}")
