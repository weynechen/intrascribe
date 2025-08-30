"""
Intrascribe LiveKit Agent using Agent framework.
Clean implementation following official LiveKit Agent examples.
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from dotenv import load_dotenv

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    MetricsCollectedEvent,
    RoomOutputOptions,
    StopResponse,
    WorkerOptions,
    cli,
    llm,
    metrics,
)
from livekit.agents.stt import STT, STTCapabilities, SpeechEvent, SpeechEventType, SpeechData
from livekit.plugins import silero

# Load environment variables
backend_root = Path(__file__).parent.parent.parent
env_file = backend_root / ".env"
load_dotenv(env_file)

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.config import service_urls
from shared.utils import ServiceClient

logger = ServiceLogger("agent-service")


class MicroserviceSTT(STT):
    """STT implementation that calls STT microservice for transcription"""
    
    def __init__(self, session_id: str):
        capabilities = STTCapabilities(
            streaming=False,
            interim_results=False,
        )
        super().__init__(capabilities=capabilities)
        self.session_id = session_id
        self.stt_client = ServiceClient(service_urls.stt_service_url)
        self._audio_buffer = bytearray()
        self._buffer_threshold = 24000 * 2  # 2 seconds of audio data (24kHz)
        
        logger.info(f"STT client initialized for session: {session_id}")
    
    async def _recognize_impl(
        self,
        buffer: rtc.AudioFrame,
        *,
        language: Optional[str] = None,
        conn_options=None,
    ) -> SpeechEvent:
        """Implement STT recognition logic, following original backend audio format"""
        try:
            # Convert audio data
            audio_data = np.frombuffer(buffer.data, dtype=np.int16)
            sample_rate = buffer.sample_rate
            
            # Buffer audio data
            self._audio_buffer.extend(audio_data.tobytes())
            
            # Process when buffer reaches threshold
            if len(self._audio_buffer) >= self._buffer_threshold:
                # Convert buffered data to numpy array
                buffered_audio = np.frombuffer(bytes(self._audio_buffer), dtype=np.int16)
                self._audio_buffer.clear()
                
                # Process audio format following original backend
                target_sample_rate = 24000
                if sample_rate != target_sample_rate:
                    try:
                        import librosa
                        audio_float = buffered_audio.astype(np.float32) / 32768.0
                        audio_resampled = librosa.resample(
                            audio_float, 
                            orig_sr=sample_rate, 
                            target_sr=target_sample_rate
                        )
                        audio_final = (audio_resampled * 32768.0).astype(np.int16)
                    except ImportError:
                        logger.warning("librosa not installed, using original sample rate")
                        audio_final = buffered_audio
                        target_sample_rate = sample_rate
                else:
                    audio_final = buffered_audio
                
                # Follow original backend format: reshape to 2D array
                audio_2d = audio_final.reshape(1, -1)
                audio_for_stt = audio_2d.flatten().astype(np.float32).tolist()
                
                logger.debug(f"Processing audio: sample_rate={target_sample_rate}, samples={len(audio_final)}")
                
                # Call STT microservice
                try:
                    response = await self.stt_client.post("/transcribe", {
                        "audio_data": {
                            "sample_rate": target_sample_rate,
                            "audio_array": audio_for_stt,
                            "format": "wav",
                            "duration_seconds": len(audio_final) / target_sample_rate
                        },
                        "session_id": self.session_id,
                        "language": language or "zh-CN"
                    })
                    
                    if response.get("success") and response.get("text"):
                        text = response["text"].strip()
                        if text:
                            logger.success(f"Transcription successful: '{text[:50]}...'")
                            
                            # Return SpeechEvent
                            speech_data = SpeechData(
                                language=language or "zh-CN",
                                text=text,
                                confidence=response.get("confidence_score", 1.0),
                                start_time=0.0,
                                end_time=len(audio_final) / target_sample_rate
                            )
                            
                            return SpeechEvent(
                                type=SpeechEventType.FINAL_TRANSCRIPT,
                                alternatives=[speech_data]
                            )
                            
                except Exception as e:
                    logger.error(f"STT service call failed: {e}")
            
            # Return empty event
            return SpeechEvent(
                type=SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[]
            )
            
        except Exception as e:
            logger.error(f"STT recognition failed: {e}")
            return SpeechEvent(
                type=SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[]
            )


class Transcriber(Agent):
    """Simple transcription Agent following LiveKit Agent framework"""
    
    def __init__(self, session_id: str, room: rtc.Room):
        self.session_id = session_id
        self._room = room  # Save room reference
        super().__init__(
            instructions="Transcribe user speech to text",
            stt=MicroserviceSTT(session_id),
        )

    async def on_user_turn_completed(self, chat_ctx: llm.ChatContext, new_message: llm.ChatMessage):
        """User speech transcription completed - send transcription data to frontend"""
        user_transcript = new_message.text_content
        logger.info(f"User transcript: {user_transcript}")
        
        # Send transcription data to frontend
        await self._send_transcription_to_frontend(user_transcript)
        
        # Stop response, we only do transcription not conversation
        raise StopResponse()
    
    async def _send_transcription_to_frontend(self, text: str):
        """Send transcription data to frontend"""
        try:
            transcription_data = {
                "index": len(text) // 10,
                "speaker": "Speaker 1", 
                "timestamp": datetime.now().isoformat(),
                "text": text,
                "is_final": True
            }
            
            await self._room.local_participant.publish_data(
                payload=json.dumps(transcription_data, ensure_ascii=False).encode('utf-8'),
                topic="transcription"
            )
            
            logger.info(f"Transcription data sent to frontend: {text}")
            
        except Exception as e:
            logger.error(f"Failed to send transcription data: {e}")


def extract_session_id(room_name: str) -> Optional[str]:
    """Extract session ID from room name"""
    if room_name and room_name.startswith("intrascribe_room_"):
        return room_name.replace("intrascribe_room_", "")
    return None


async def entrypoint(ctx: JobContext):
    """Agent entrypoint - extract session ID and start transcription service"""
    logger.info(f"Intrascribe transcription Agent started - room: {ctx.room.name}")
    
    # Extract session ID
    session_id = extract_session_id(ctx.room.name)
    if not session_id:
        logger.error("Unable to extract session ID, Agent exiting")
        return
    
    logger.info(f"Session ID: {session_id}")
    
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Create session with transcription functionality
    session = AgentSession(
        # VAD needed for non-streaming STT implementations
        vad=silero.VAD.load(min_silence_duration=0.3),
        stt=MicroserviceSTT(session_id),  # Use our STT implementation
    )

    @session.on("metrics_collected")
    def on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)

    await session.start(
        agent=Transcriber(session_id, ctx.room),  # Pass session_id and room
        room=ctx.room,
        room_output_options=RoomOutputOptions(
            transcription_enabled=True,
            # Disable audio output, we only do transcription
            audio_enabled=False,
        ),
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
         
        agent_name="intrascribe-agent-session",
    ))