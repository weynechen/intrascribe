"""
Lightweight LiveKit Agent

This agent handles real-time audio processing for LiveKit sessions.
Unlike the original agent, this one doesn't load heavy models locally.
Instead, it communicates with microservices for:
- Speech-to-text transcription
- Speaker diarization
- AI summarization

Benefits:
- Faster startup times
- Lower memory usage per agent
- Better scalability
- Centralized model management
"""
