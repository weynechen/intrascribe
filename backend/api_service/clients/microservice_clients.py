"""
Microservice client implementations.
Handles communication with other microservices in the architecture.
"""
import os
import sys
from typing import Dict, Any, List, Optional

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.config import service_urls, base_config
from shared.utils import ServiceClient
from shared.models import (
    AudioData, TranscriptionRequest, TranscriptionResponse,
    SpeakerDiarizationRequest, SpeakerDiarizationResponse,
    AISummaryRequest, AISummaryResponse
)

logger = ServiceLogger("microservice-clients")


class STTServiceClient(ServiceClient):
    """Client for STT (Speech-to-Text) microservice"""
    
    def __init__(self):
        super().__init__(
            base_url=service_urls.stt_service_url,
            api_key=base_config.service_api_key
        )
        self.service_name = "stt-service"
    
    async def transcribe_audio(self, audio_data: AudioData, session_id: str, language: str = "zh-CN") -> TranscriptionResponse:
        """
        Transcribe audio to text.
        
        Args:
            audio_data: Audio data to transcribe
            session_id: Session ID for tracking
            language: Language code
        
        Returns:
            Transcription response
        """
        try:
            logger.info(f"Requesting transcription for session: {session_id}")
            
            request_data = {
                "audio_data": {
                    "sample_rate": audio_data.sample_rate,
                    "audio_array": audio_data.audio_array,
                    "format": audio_data.format,
                    "duration_seconds": audio_data.duration_seconds
                },
                "session_id": session_id,
                "language": language
            }
            
            response = await self.post("/transcribe", request_data)
            
            return TranscriptionResponse(
                success=response.get("success", False),
                text=response.get("text", ""),
                confidence_score=response.get("confidence_score", 1.0),
                processing_time_ms=response.get("processing_time_ms", 0),
                error_message=response.get("error_message")
            )
            
        except Exception as e:
            logger.error(f"STT service request failed: {e}")
            return TranscriptionResponse(
                success=False,
                text="",
                error_message=str(e)
            )
    
    async def batch_transcribe(self, requests: List[Dict[str, Any]]) -> List[TranscriptionResponse]:
        """
        Batch transcribe multiple audio files.
        
        Args:
            requests: List of transcription requests
        
        Returns:
            List of transcription responses
        """
        try:
            logger.info(f"Requesting batch transcription: {len(requests)} files")
            
            response = await self.post("/batch-transcribe", requests)
            
            results = []
            for item in response:
                results.append(TranscriptionResponse(
                    success=item.get("success", False),
                    text=item.get("text", ""),
                    confidence_score=item.get("confidence_score", 1.0),
                    processing_time_ms=item.get("processing_time_ms", 0),
                    error_message=item.get("error_message")
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"Batch transcription request failed: {e}")
            return [TranscriptionResponse(
                success=False,
                text="",
                error_message=str(e)
            ) for _ in requests]


class DiarizationServiceClient(ServiceClient):
    """Client for Speaker Diarization microservice"""
    
    def __init__(self):
        super().__init__(
            base_url=service_urls.diarization_service_url,
            api_key=base_config.service_api_key
        )
        self.service_name = "diarization-service"
    
    async def diarize_audio(self, audio_data: bytes, file_format: str, session_id: str) -> SpeakerDiarizationResponse:
        """
        Perform speaker diarization on audio.
        
        Args:
            audio_data: Raw audio bytes
            file_format: Audio format
            session_id: Session ID for tracking
        
        Returns:
            Speaker diarization response
        """
        try:
            logger.info(f"Requesting speaker diarization for session: {session_id}")
            
            request_data = {
                "audio_data": audio_data.hex(),  # Convert bytes to hex string
                "file_format": file_format,
                "session_id": session_id
            }
            
            response = await self.post("/diarize", request_data)
            
            # Convert segments
            segments = []
            for seg in response.get("segments", []):
                from shared.models import SpeakerSegment
                segments.append(SpeakerSegment(
                    start_time=seg["start_time"],
                    end_time=seg["end_time"],
                    speaker_label=seg["speaker_label"],
                    duration=seg["duration"]
                ))
            
            return SpeakerDiarizationResponse(
                success=response.get("success", False),
                segments=segments,
                speaker_count=response.get("speaker_count", 0),
                processing_time_ms=response.get("processing_time_ms", 0),
                error_message=response.get("error_message")
            )
            
        except Exception as e:
            logger.error(f"Speaker diarization request failed: {e}")
            return SpeakerDiarizationResponse(
                success=False,
                segments=[],
                speaker_count=0,
                error_message=str(e)
            )


# AI services are now integrated into the main API service
# No separate AI microservice client needed


# Global client instances
stt_client = STTServiceClient()
diarization_client = DiarizationServiceClient()
