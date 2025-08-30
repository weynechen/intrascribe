"""
Speaker diarization model management.
Handles pyannote.audio model loading and speaker separation logic.
"""
import os
import sys
import tempfile
import time
from typing import List, Optional
import numpy as np

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.logging import ServiceLogger
from shared.config import speaker_config
from shared.models import SpeakerSegment, SpeakerDiarizationResponse

logger = ServiceLogger("speaker-model")


class SpeakerDiarizationManager:
    """
    Manages speaker diarization model lifecycle and inference.
    Implements singleton pattern to ensure single model instance.
    """
    
    _instance = None
    _pipeline = None
    _model_loaded = False
    _load_time = 0
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._model_loaded:
            self._initialize_pipeline()
    
    def _initialize_pipeline(self):
        """Initialize the pyannote.audio pipeline"""
        try:
            logger.info("Initializing pyannote.audio speaker diarization pipeline...")
            start_time = time.time()
            
            # Check for HuggingFace token
            if not speaker_config.huggingface_token:
                logger.warning("HuggingFace token not configured - diarization will be disabled")
                self._pipeline = None
                self._model_loaded = False
                return
            
            # Import pyannote.audio
            from pyannote.audio import Pipeline
            import torch
            
            # Initialize speaker diarization pipeline
            self._pipeline = Pipeline.from_pretrained(
                speaker_config.pyannote_model,
                use_auth_token=speaker_config.huggingface_token,
            )
            
            # Move to GPU if available
            if torch.cuda.is_available():
                logger.info("Moving speaker diarization pipeline to GPU")
                self._pipeline.to(torch.device("cuda"))
            else:
                logger.info("Using CPU for speaker diarization")
            
            self._load_time = time.time() - start_time
            self._model_loaded = True
            
            logger.success(f"Speaker diarization pipeline loaded in {self._load_time:.2f}s")
            logger.info(f"Model: {speaker_config.pyannote_model}")
            
        except ImportError as e:
            logger.error(f"pyannote.audio not installed: {e}")
            self._pipeline = None
            self._model_loaded = False
        except Exception as e:
            logger.error(f"Failed to initialize speaker diarization pipeline: {e}")
            self._pipeline = None
            self._model_loaded = False
    
    def is_available(self) -> bool:
        """Check if diarization is available"""
        return self._model_loaded and self._pipeline is not None
    
    def get_model_info(self) -> dict:
        """Get model information"""
        return {
            "available": self.is_available(),
            "load_time_seconds": self._load_time,
            "model_name": speaker_config.pyannote_model,
            "device": "cuda" if self.is_available() and hasattr(self._pipeline, 'device') else "cpu",
            "huggingface_token_configured": bool(speaker_config.huggingface_token),
        }
    
    def diarize_audio_file(self, audio_file_path: str, session_id: str = None) -> SpeakerDiarizationResponse:
        """
        Perform speaker diarization on audio file.
        
        Args:
            audio_file_path: Path to audio file
            session_id: Optional session ID for logging
        
        Returns:
            SpeakerDiarizationResponse with segments
        """
        if not self.is_available():
            return SpeakerDiarizationResponse(
                success=False,
                segments=[],
                speaker_count=0,
                error_message="Speaker diarization not available"
            )
        
        try:
            start_time = time.time()
            
            logger.info(f"Starting speaker diarization for file: {audio_file_path}")
            
            # Perform diarization
            diarization = self._pipeline(audio_file_path)
            
            # Convert to speaker segments
            segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                # Skip very short segments
                if turn.duration < speaker_config.min_segment_duration:
                    continue
                
                segment = SpeakerSegment(
                    start_time=turn.start,
                    end_time=turn.end,
                    speaker_label=speaker,
                    duration=turn.duration
                )
                segments.append(segment)
            
            # Remove overlapping segments
            segments = self._remove_overlapping_segments(segments)
            
            # Count unique speakers
            unique_speakers = len(set(seg.speaker_label for seg in segments))
            
            processing_time = int((time.time() - start_time) * 1000)
            
            logger.success(f"Speaker diarization completed in {processing_time}ms")
            logger.info(f"Found {unique_speakers} speakers in {len(segments)} segments")
            
            return SpeakerDiarizationResponse(
                success=True,
                segments=segments,
                speaker_count=unique_speakers,
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            logger.error(f"Speaker diarization failed after {processing_time}ms", e)
            
            return SpeakerDiarizationResponse(
                success=False,
                segments=[],
                speaker_count=0,
                processing_time_ms=processing_time,
                error_message=str(e)
            )
    
    def diarize_audio_data(self, audio_data: bytes, file_format: str, session_id: str = None) -> SpeakerDiarizationResponse:
        """
        Perform speaker diarization on audio data.
        
        Args:
            audio_data: Raw audio bytes
            file_format: Audio format (wav, mp3, etc.)
            session_id: Optional session ID for logging
        
        Returns:
            SpeakerDiarizationResponse with segments
        """
        if not self.is_available():
            return SpeakerDiarizationResponse(
                success=False,
                segments=[],
                speaker_count=0,
                error_message="Speaker diarization not available"
            )
        
        # Create temporary file
        temp_file_path = None
        try:
            # Create temporary file with appropriate extension
            with tempfile.NamedTemporaryFile(
                suffix=f".{file_format}", 
                delete=False
            ) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            # Convert to WAV if needed
            processed_file_path = self._convert_to_wav_if_needed(temp_file_path, file_format)
            
            try:
                # Perform diarization
                result = self.diarize_audio_file(processed_file_path, session_id)
                return result
                
            finally:
                # Clean up converted file if different from original
                if processed_file_path != temp_file_path and os.path.exists(processed_file_path):
                    os.unlink(processed_file_path)
                    
        except Exception as e:
            logger.error(f"Failed to process audio data for diarization", e)
            return SpeakerDiarizationResponse(
                success=False,
                segments=[],
                speaker_count=0,
                error_message=str(e)
            )
        finally:
            # Clean up temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
    
    def _convert_to_wav_if_needed(self, file_path: str, file_format: str) -> str:
        """Convert audio file to WAV format if needed"""
        if file_format.lower() == "wav":
            return file_path
        
        try:
            import librosa
            import soundfile as sf
            
            # Load audio with librosa
            audio_data, sample_rate = librosa.load(file_path, sr=None)
            
            # Create WAV file
            wav_path = file_path.replace(f".{file_format}", ".wav")
            sf.write(wav_path, audio_data, sample_rate)
            
            logger.debug(f"Converted {file_format} to WAV: {wav_path}")
            return wav_path
            
        except Exception as e:
            logger.warning(f"Failed to convert {file_format} to WAV: {e}")
            return file_path  # Return original file and hope for the best
    
    def _remove_overlapping_segments(self, segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """Remove overlapping segments by keeping the longer one"""
        if not segments:
            return segments
        
        # Sort by start time
        sorted_segments = sorted(segments, key=lambda x: x.start_time)
        cleaned_segments = []
        
        for current_segment in sorted_segments:
            # Check for overlap with previous segments
            overlapped = False
            
            for i, existing_segment in enumerate(cleaned_segments):
                if (current_segment.start_time < existing_segment.end_time and 
                    current_segment.end_time > existing_segment.start_time):
                    
                    # There's an overlap
                    if current_segment.duration > existing_segment.duration:
                        # Replace with longer segment
                        cleaned_segments[i] = current_segment
                    
                    overlapped = True
                    break
            
            if not overlapped:
                cleaned_segments.append(current_segment)
        
        return cleaned_segments
    
    def create_fallback_segments(self, audio_duration: float) -> List[SpeakerSegment]:
        """Create single speaker segment when diarization fails"""
        return [SpeakerSegment(
            start_time=0.0,
            end_time=audio_duration,
            speaker_label="speaker_0",
            duration=audio_duration
        )]


# Global diarization manager instance
diarization_manager = SpeakerDiarizationManager()
