"""
说话人分离服务
基于pyannote.audio实现音频的说话人识别和分离
"""
import logging
import os
import tempfile
from typing import List, Dict, Any, Tuple
import numpy as np
from dataclasses import dataclass
import librosa

import io

logger = logging.getLogger(__name__)

@dataclass
class SpeakerSegment:
    """说话人片段数据结构"""
    start_time: float  # 开始时间（秒）
    end_time: float    # 结束时间（秒）
    speaker_label: str # 说话人标识
    duration: float    # 持续时间（秒）


class SpeakerDiarizationService:
    """说话人分离服务"""
    
    def __init__(self):
        self.pipeline = None
        self._initialize_pipeline()
    
    def _initialize_pipeline(self):
        """初始化pyannote pipeline"""
        try:
            from pyannote.audio import Pipeline
            import torch
            from .config import settings
            
            # Check if HuggingFace token is configured
            if not settings.huggingface_token:
                logger.error("❌ HUGGINGFACE_TOKEN未配置在环境变量中")
                raise Exception("HUGGINGFACE_TOKEN required for pyannote.audio")
            
            # Initialize speaker diarization pipeline
            self.pipeline = Pipeline.from_pretrained(
                settings.pyannote_model,
                use_auth_token=settings.huggingface_token,
            )
            
            # Send pipeline to GPU if available
            if torch.cuda.is_available():
                logger.info("🔥 使用GPU进行说话人分离")
                self.pipeline.to(torch.device("cuda"))
            else:
                logger.info("💻 使用CPU进行说话人分离")
            
            logger.info("🎤 说话人分离服务初始化完成")
            
        except ImportError as e:
            logger.error(f"❌ pyannote.audio未安装: {e}")
            self.pipeline = None
        except Exception as e:
            logger.error(f"❌ 说话人分离服务初始化失败: {e}")
            self.pipeline = None
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.pipeline is not None
    
    async def diarize_audio_file(self, audio_file_path: str) -> List[SpeakerSegment]:
        """
        对音频文件进行说话人分离
        
        Args:
            audio_file_path: 音频文件路径
            
        Returns:
            List[SpeakerSegment]: 说话人片段列表
        """
        if not self.is_available():
            logger.warning("说话人分离服务不可用，返回单一说话人")
            return await self._fallback_single_speaker(audio_file_path)
        
        try:
            logger.info(f"🎤 开始说话人分离: {audio_file_path}")
            
            # Apply pretrained pipeline
            diarization = self.pipeline(audio_file_path)
            
            segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segment = SpeakerSegment(
                    start_time=turn.start,
                    end_time=turn.end,
                    speaker_label=f"{speaker}",
                    duration=turn.end - turn.start
                )
                segments.append(segment)
                
                logger.debug(f"🗣️ 发现说话人片段: {segment.speaker_label} "
                           f"[{segment.start_time:.1f}s - {segment.end_time:.1f}s] "
                           f"时长: {segment.duration:.1f}s")
            
            # Remove overlapping segments (keep longer ones)
            segments = self._remove_overlapping_segments(segments)
            
            logger.info(f"✅ 说话人分离完成，共 {len(segments)} 个片段")
            return segments
            
        except Exception as e:
            logger.error(f"❌ 说话人分离失败: {e}")
            return await self._fallback_single_speaker(audio_file_path)
    
    async def diarize_audio_data(self, audio_data: bytes, format: str = "mp3") -> List[SpeakerSegment]:
        """
        对音频数据进行说话人分离
        
        Args:
            audio_data: 音频数据
            format: 音频格式
            
        Returns:
            List[SpeakerSegment]: 说话人片段列表
        """
        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as temp_file:
            temp_file.write(audio_data)
            temp_file_path = temp_file.name
        
        # Convert to WAV if needed
        processed_file_path = temp_file_path
        was_converted = False
        
        try:
            # Import audio converter here to avoid circular imports
            from .audio_converter import audio_converter
            
            if format.lower() in ['mp3', 'mpeg']:
                logger.info("🔄 说话人分离：检测到MP3，转换为WAV处理...")
                processed_file_path, was_converted = await audio_converter.convert_to_wav_if_needed(
                    temp_file_path, format
                )
            
            # Process the audio file
            segments = await self.diarize_audio_file(processed_file_path)
            return segments
            
        finally:
            # Clean up temporary files
            try:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                
                if was_converted and processed_file_path != temp_file_path:
                    from .audio_converter import audio_converter
                    audio_converter.cleanup_converted_file(processed_file_path, was_converted)
                    
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")
    
    def _remove_overlapping_segments(self, segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """
        移除重叠的说话人片段，保留时间较长的
        
        Args:
            segments: 原始片段列表
            
        Returns:
            List[SpeakerSegment]: 去重后的片段列表
        """
        if not segments:
            return []
        
        # Sort segments by start time
        sorted_segments = sorted(segments, key=lambda x: x.start_time)
        
        filtered_segments = []
        
        for current in sorted_segments:
            # Check for overlap with existing segments
            overlapping = False
            
            for i, existing in enumerate(filtered_segments):
                if self._segments_overlap(existing, current):
                    # Keep the longer segment
                    if current.duration > existing.duration:
                        logger.debug(f"🔄 替换较短片段: {existing.speaker_label} "
                                   f"[{existing.start_time:.1f}s-{existing.end_time:.1f}s] "
                                   f"-> {current.speaker_label} "
                                   f"[{current.start_time:.1f}s-{current.end_time:.1f}s]")
                        filtered_segments[i] = current
                    else:
                        logger.debug(f"⏭️ 跳过较短片段: {current.speaker_label} "
                                   f"[{current.start_time:.1f}s-{current.end_time:.1f}s]")
                    overlapping = True
                    break
            
            if not overlapping:
                filtered_segments.append(current)
        
        # Sort by start time again
        filtered_segments.sort(key=lambda x: x.start_time)
        
        logger.info(f"🔄 去重完成: {len(segments)} -> {len(filtered_segments)} 个片段")
        return filtered_segments
    
    def _segments_overlap(self, seg1: SpeakerSegment, seg2: SpeakerSegment) -> bool:
        """检查两个片段是否重叠"""
        return not (seg1.end_time <= seg2.start_time or seg2.end_time <= seg1.start_time)
    
    async def _fallback_single_speaker(self, audio_file_path: str) -> List[SpeakerSegment]:
        """
        回退方案：将整个音频作为单一说话人处理
        
        Args:
            audio_file_path: 音频文件路径
            
        Returns:
            List[SpeakerSegment]: 单一说话人片段
        """
        try:
            # Get audio duration using audio_converter
            from .audio_converter import audio_converter
            audio_info = await audio_converter.get_audio_info(audio_file_path)
            duration = audio_info.duration
            
            segment = SpeakerSegment(
                start_time=0.0,
                end_time=duration,
                speaker_label="speaker_0",
                duration=duration
            )
            
            logger.info(f"📱 回退到单一说话人模式，时长: {duration:.1f}s")
            return [segment]
            
        except Exception as e:
            logger.error(f"❌ 获取音频时长失败: {e}")
            # Final fallback - assume 60 seconds
            return [SpeakerSegment(
                start_time=0.0,
                end_time=60.0,
                speaker_label="speaker_0",
                duration=60.0
            )]
    
    async def _split_single_segment(self, audio_file_path: str, segment: SpeakerSegment) -> Tuple[SpeakerSegment, bytes]:
        """
        分割单个音频片段
        
        Args:
            audio_file_path: 音频文件路径
            segment: 说话人片段
            
        Returns:
            Tuple[SpeakerSegment, bytes]: 片段信息和对应的音频数据
        """
        import tempfile
        import subprocess
        import asyncio
        from .audio_converter import audio_converter
        
        # Create unique temp file for this segment
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_output:
            temp_output_path = temp_output.name
        
        try:
            if not audio_converter.ffmpeg_path:
                raise Exception("ffmpeg不可用，无法分割音频")
            
            # Use ffmpeg to extract segment
            cmd = [
                audio_converter.ffmpeg_path,
                '-i', audio_file_path,
                '-ss', str(segment.start_time),      # Start time
                '-t', str(segment.duration),         # Duration
                '-acodec', 'pcm_s16le',             # 16-bit PCM
                '-ar', '16000',                     # 16kHz sample rate
                '-ac', '1',                         # Mono
                '-y',                               # Overwrite
                temp_output_path
            ]
            
            logger.debug(f"🔧 并行执行ffmpeg音频分割: {segment.speaker_label} "
                        f"[{segment.start_time:.1f}s-{segment.end_time:.1f}s]")
            
            # Run ffmpeg asynchronously
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
            
            if process.returncode != 0:
                error_msg = f"ffmpeg音频分割失败: {stderr.decode()}"
                logger.error(f"❌ {error_msg}")
                raise Exception(error_msg)
            
            # Read the audio data
            with open(temp_output_path, 'rb') as f:
                audio_bytes = f.read()
            
            logger.debug(f"✂️ 完成音频片段分割: {segment.speaker_label} "
                       f"[{segment.start_time:.1f}s-{segment.end_time:.1f}s] "
                       f"大小: {len(audio_bytes)} bytes")
            
            return (segment, audio_bytes)
            
        finally:
            # Clean up temp file
            try:
                if os.path.exists(temp_output_path):
                    os.unlink(temp_output_path)
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")

    async def split_audio_by_segments(self, audio_file_path: str, segments: List[SpeakerSegment]) -> List[Tuple[SpeakerSegment, bytes]]:
        """
        根据说话人片段分割音频（并行处理）
        
        Args:
            audio_file_path: 音频文件路径
            segments: 说话人片段列表
            
        Returns:
            List[Tuple[SpeakerSegment, bytes]]: 片段信息和对应的音频数据
        """
        try:
            import asyncio
            
            logger.info(f"🚀 开始并行音频分割，共 {len(segments)} 个片段")
            
            # Create tasks for parallel processing
            tasks = [
                self._split_single_segment(audio_file_path, segment)
                for segment in segments
            ]
            
            # Execute all tasks in parallel
            split_audios = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions and log errors
            successful_splits = []
            failed_count = 0
            
            for i, result in enumerate(split_audios):
                if isinstance(result, Exception):
                    logger.error(f"❌ 片段 {segments[i].speaker_label} 分割失败: {result}")
                    failed_count += 1
                else:
                    successful_splits.append(result)
            
            if failed_count > 0:
                logger.warning(f"⚠️ {failed_count} 个片段分割失败")
            
            logger.info(f"✅ 并行音频分割完成，成功 {len(successful_splits)} 个片段")
            return successful_splits
            
        except Exception as e:
            logger.error(f"❌ 并行音频分割失败: {e}")
            raise


# 全局实例
speaker_diarization_service = SpeakerDiarizationService() 