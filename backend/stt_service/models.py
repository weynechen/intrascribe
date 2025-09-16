"""
STT Model management and loading.
Handles both FunASR and Whisper model initialization and speech recognition.
"""
import os
import sys
import tempfile
import wave
import time
from typing import Tuple, Optional
import numpy as np
import torch

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.logging import ServiceLogger
from shared.config import stt_config
from shared.models import AudioData, TranscriptionResponse

logger = ServiceLogger("stt-model")


class STTModelManager:
    """
    Manages STT model lifecycle and inference.
    Implements singleton pattern to ensure single model instance.
    Supports both FunASR and Whisper models based on configuration.
    """
    
    _instance = None
    _model = None
    _processor = None
    _pipeline = None
    _model_loaded = False
    _load_time = 0
    _model_type = None  # 'funasr' or 'whisper'
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._model_loaded:
            self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the appropriate model based on configuration"""
        # Detect model type based on model_dir
        model_dir = stt_config.model_dir.lower()
        
        if 'whisper' in model_dir or model_dir.startswith('openai/'):
            self._model_type = 'whisper'
            self._initialize_whisper_model()
        else:
            self._model_type = 'funasr'
            self._initialize_funasr_model()
    
    def _initialize_funasr_model(self):
        """Initialize the FunASR model"""
        try:
            logger.info("Initializing FunASR model...")
            start_time = time.time()
            
            # Import FunASR
            from funasr import AutoModel
            
            # Set environment variables for performance
            os.environ['DISABLE_TQDM'] = '1'
            os.environ['TQDM_DISABLE'] = '1'
            os.environ['TOKENIZERS_PARALLELISM'] = 'false'
            os.environ['OMP_NUM_THREADS'] = '1'
            os.environ['MKL_NUM_THREADS'] = '1'
            os.environ['NUMEXPR_MAX_THREADS'] = '1'
            
            # Determine device
            if torch.cuda.is_available():
                device = "cuda:0"
                logger.info("CUDA device detected, using GPU acceleration")
            else:
                device = "cpu"
                logger.info("No CUDA device detected, using CPU")
            
            # Load model
            self._model = AutoModel(
                model=stt_config.model_dir,
                vad_kwargs={"max_single_segment_time": 30000},
                hub="ms",  # ModelScope hub for auto download
                device=device,
                disable_update=True,
                disable_log=True,
            )
            
            self._load_time = time.time() - start_time
            self._model_loaded = True
            
            logger.success(f"FunASR model loaded successfully in {self._load_time:.2f}s")
            logger.info(f"Model device: {device}")
            logger.info(f"Model directory: {stt_config.model_dir}")
            
        except Exception as e:
            logger.error(f"Failed to initialize FunASR model: {e}")
            self._model = None
            self._model_loaded = False
            raise
    
    def _initialize_whisper_model(self):
        """Initialize the Whisper model"""
        try:
            logger.info("Initializing Whisper model...")
            start_time = time.time()
            
            # Import transformers
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
            
            # Set environment variables for performance
            os.environ['TOKENIZERS_PARALLELISM'] = 'false'
            os.environ['OMP_NUM_THREADS'] = '1'
            os.environ['MKL_NUM_THREADS'] = '1'
            os.environ['NUMEXPR_MAX_THREADS'] = '1'
            
            # Determine device and dtype
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
            torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            
            if torch.cuda.is_available():
                logger.info("CUDA device detected, using GPU acceleration")
            else:
                logger.info("No CUDA device detected, using CPU")
            
            # Use configured model_dir for Whisper models
            model_id = stt_config.model_dir
            
            # Load model
            self._model = AutoModelForSpeechSeq2Seq.from_pretrained(
                model_id, 
                torch_dtype=torch_dtype, 
                low_cpu_mem_usage=True, 
                use_safetensors=True
            )
            self._model.to(device)
            
            # Load processor
            self._processor = AutoProcessor.from_pretrained(model_id)
            
            # Create pipeline
            self._pipeline = pipeline(
                "automatic-speech-recognition",
                model=self._model,
                tokenizer=self._processor.tokenizer,
                feature_extractor=self._processor.feature_extractor,
                torch_dtype=torch_dtype,
                device=device,
            )
            
            self._load_time = time.time() - start_time
            self._model_loaded = True
            
            logger.success(f"Whisper model loaded successfully in {self._load_time:.2f}s")
            logger.info(f"Model device: {device}")
            logger.info(f"Model ID: {model_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Whisper model: {e}")
            self._model = None
            self._processor = None
            self._pipeline = None
            self._model_loaded = False
            raise
    
    def is_loaded(self) -> bool:
        """Check if model is loaded and ready"""
        if self._model_type == 'whisper':
            return self._model_loaded and self._pipeline is not None
        else:
            return self._model_loaded and self._model is not None
    
    def get_model_info(self) -> dict:
        """Get model information"""
        return {
            "loaded": self._model_loaded,
            "load_time_seconds": self._load_time,
            "model_type": self._model_type,
            "model_dir": stt_config.model_dir,
            "device": "cuda" if torch.cuda.is_available() else "cpu",
        }
    
    def transcribe(self, audio_data: AudioData) -> TranscriptionResponse:
        """
        Transcribe audio data to text.
        
        Args:
            audio_data: Audio data structure
        
        Returns:
            TranscriptionResponse with transcription results
        """
        if not self.is_loaded():
            return TranscriptionResponse(
                success=False,
                text="",
                error_message="STT model not loaded"
            )
        
        try:
            start_time = time.time()
            
            # Convert audio data
            sample_rate = audio_data.sample_rate
            audio_array = np.array(audio_data.audio_array)
            
            # Validate audio length
            max_length = stt_config.max_audio_length * sample_rate
            if len(audio_array) > max_length:
                return TranscriptionResponse(
                    success=False,
                    text="",
                    error_message=f"Audio too long. Max {stt_config.max_audio_length}s"
                )
            
            logger.debug(f"Starting transcription for audio length: {len(audio_array)} samples with {self._model_type} model")
            
            # Route to appropriate transcription method
            if self._model_type == 'whisper':
                return self._transcribe_with_whisper(audio_array, sample_rate, start_time)
            else:
                return self._transcribe_with_funasr(audio_array, sample_rate, start_time)
                
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            logger.error(f"Transcription failed after {processing_time}ms", e)
            
            return TranscriptionResponse(
                success=False,
                text="",
                processing_time_ms=processing_time,
                error_message=str(e)
            )
    
    def _transcribe_with_whisper(self, audio_array: np.ndarray, sample_rate: int, start_time: float) -> TranscriptionResponse:
        """Transcribe using Whisper model
        https://huggingface.co/openai/whisper-large-v3
        
        Args:
            audio_array: Audio array
            sample_rate: Sample rate
            start_time: Start time
        
        Returns:
            TranscriptionResponse with transcription results
        """
        # Prepare audio data for Whisper
        # Whisper expects float32 arrays normalized to [-1, 1]
        if audio_array.dtype == np.int16:
            # Convert int16 to float32 and normalize
            audio_float = audio_array.astype(np.float32) / 32768.0
        elif audio_array.dtype == np.float32:
            # Already float32, ensure it's normalized
            audio_float = np.clip(audio_array, -1.0, 1.0)
        else:
            # Convert other types to float32 and normalize
            audio_float = audio_array.astype(np.float32)
            if audio_float.max() > 1.0 or audio_float.min() < -1.0:
                audio_float = audio_float / np.max(np.abs(audio_float))
        
        # Create audio input for pipeline
        audio_input = {
            "array": audio_float,
            "sampling_rate": sample_rate
        }
        
        # Perform transcription with language setting
        # Use configured language or auto-detect
        generate_kwargs = {
            "task": "transcribe"    # Transcribe (not translate)
        }
        
        # Add language setting if not "auto"
        if stt_config.language and stt_config.language.lower() != "auto":
            generate_kwargs["language"] = stt_config.language.lower()
            
        result = self._pipeline(audio_input, generate_kwargs=generate_kwargs)
        
        # Extract text from result
        if result and "text" in result:
            text = result["text"].strip()
            
            logger.debug(f"🔍 Whisper result: '{text}' (length: {len(text)})")
            
            # Clean up text (remove extra whitespace)
            import re
            if text:
                # Remove extra whitespace
                text = re.sub(r'\s+', ' ', text).strip()
                # Remove standalone punctuation if it's the only content
                if text in [".", "。", ",", "，", "?", "？", "!", "！"]:
                    text = ""
            
            processing_time = int((time.time() - start_time) * 1000)
            
            if text:
                logger.success(f"Transcription completed in {processing_time}ms: '{text[:100]}...'")
                
                return TranscriptionResponse(
                    success=True,
                    text=text,
                    confidence_score=1.0,  # Whisper doesn't provide confidence scores in this format
                    processing_time_ms=processing_time
                )
            else:
                logger.warning(f"Transcription result is empty after cleanup (processing_time: {processing_time}ms)")
                
                return TranscriptionResponse(
                    success=False,
                    text="",
                    error_message="Transcription resulted in empty text (possibly no speech detected)"
                )
        else:
            return TranscriptionResponse(
                success=False,
                text="",
                error_message="No transcription result from Whisper model"
            )
    
    def _transcribe_with_funasr(self, audio_array: np.ndarray, sample_rate: int, start_time: float) -> TranscriptionResponse:
        """Transcribe using FunASR model"""
        # Convert to appropriate format for FunASR
        if audio_array.dtype == np.float32:
            # Convert float32 to int16
            audio_array = (audio_array * 32767).astype(np.int16)
        elif audio_array.dtype != np.int16:
            audio_array = audio_array.astype(np.int16)
        
        # Create temporary WAV file
        temp_path = self._create_temp_wav_file(audio_array, sample_rate)
        
        try:
            # Perform transcription
            result = self._model.generate(
                input=temp_path,
                cache={},
                language="auto",  # Auto-detect language
                use_itn=True,  # Use inverse text normalization
            )
            
            # Extract text from result
            if result and len(result) > 0:
                # FunASR result structure analysis
                raw_result = result[0]
                logger.debug(f"🔍 Raw FunASR result structure: {type(raw_result)} - {raw_result}")
                
                # Try different text extraction methods
                text = ""
                if isinstance(raw_result, dict):
                    # Method 1: Direct text field
                    text = raw_result.get("text", "")
                    
                    # Method 2: Check for other possible fields
                    if not text:
                        for field in ["transcript", "transcription", "result", "content"]:
                            if field in raw_result:
                                text = raw_result[field]
                                break
                elif isinstance(raw_result, str):
                    # Raw result is already a string
                    text = raw_result
                elif hasattr(raw_result, 'text'):
                    # Object with text attribute
                    text = raw_result.text
                
                # Additional result inspection for debugging
                logger.debug(f"🔍 Extracted text before cleanup: '{text}' (length: {len(text)})")
                
                # Clean up text (remove special tokens and whitespace)
                import re
                if text:
                    # Remove FunASR special tokens
                    text = re.sub(r'<\|[^|]*\|>', '', text)
                    # Remove extra whitespace
                    text = re.sub(r'\s+', ' ', text).strip()
                    # Remove standalone punctuation if it's the only content
                    if text in [".", "。", ",", "，", "?", "？", "!", "！"]:
                        text = ""
                
                processing_time = int((time.time() - start_time) * 1000)
                
                if text:
                    logger.success(f"Transcription completed in {processing_time}ms: '{text[:100]}...'")
                    
                    return TranscriptionResponse(
                        success=True,
                        text=text,
                        confidence_score=1.0,  # FunASR doesn't provide confidence scores
                        processing_time_ms=processing_time
                    )
                else:
                    logger.warning(f"Transcription result is empty after cleanup (processing_time: {processing_time}ms)")
                    
                    return TranscriptionResponse(
                        success=False,
                        text="",
                        error_message="Transcription resulted in empty text (possibly no speech detected)"
                    )
            else:
                return TranscriptionResponse(
                    success=False,
                    text="",
                    error_message="No transcription result from FunASR model"
                )
                
        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def _create_temp_wav_file(self, audio_array: np.ndarray, sample_rate: int) -> str:
        """Create temporary WAV file from audio array"""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                temp_path = tmp_file.name
            
            # Write WAV file
            with wave.open(temp_path, 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_array.tobytes())
            
            return temp_path
            
        except Exception as e:
            logger.error(f"Failed to create temporary WAV file", e)
            raise
    


# Global model manager instance
model_manager = STTModelManager()
