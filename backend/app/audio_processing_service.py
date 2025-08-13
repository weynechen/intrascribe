"""
通用音频处理服务
抽象说话人分离、音频分割和转录的通用逻辑
"""
import logging
import tempfile
import os
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import re


from .speaker_diarization import speaker_diarization_service, SpeakerSegment
from .audio_converter import audio_converter
from .clients import stt_client
from .models import TranscriptionSegment

logger = logging.getLogger(__name__)


class AudioProcessingService:
    """通用音频处理服务"""
    
    def __init__(self):
        self.speaker_service = speaker_diarization_service
    
    async def process_audio_with_speaker_diarization(
        self, 
        audio_data: bytes, 
        file_format: str = "mp3",
        original_filename: str = "audio"
    ) -> Dict[str, Any]:
        """
        处理音频文件，执行说话人分离和转录
        
        Args:
            audio_data: 音频文件数据（字节）
            file_format: 音频格式
            original_filename: 原始文件名（用于日志）
            
        Returns:
            Dict: 处理结果包含转录片段、说话人数等
        """
        try:
            logger.info(f"🎵 开始处理音频: {original_filename}, 格式: {file_format}")
            
            # 创建临时文件进行处理
            with tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_audio_path = temp_file.name
            
            try:
                # 转换音频格式（如果需要）
                processed_audio_path, was_converted, converted_file_path = await self._prepare_audio_for_processing(
                    temp_audio_path, file_format
                )
                
                # 执行说话人分离
                logger.info("🎤 执行说话人分离...")
                speaker_segments = await self.speaker_service.diarize_audio_file(processed_audio_path)
                
                if not speaker_segments:
                    logger.warning("说话人分离无结果，使用单说话人模式")
                    audio_duration = await self._get_audio_duration(processed_audio_path)
                    speaker_segments = [SpeakerSegment(
                        start_time=0.0,
                        end_time=audio_duration,
                        speaker_label="speaker_0",
                        duration=audio_duration
                    )]
                
                # 合并相邻的短片段
                logger.info("🔗 合并相邻的短片段...")
                speaker_segments = self._merge_adjacent_short_segments(speaker_segments)
                
                # 分割音频并转录
                logger.info("✂️ 分割音频并转录...")
                transcription_segments, transcription_text = await self._segment_and_transcribe(
                    processed_audio_path, speaker_segments
                )
                
                # 统计结果
                unique_speakers = len(set(seg.speaker for seg in transcription_segments))
                total_duration = sum(seg.end_time - seg.start_time for seg in transcription_segments)
                
                result = {
                    "success": True,
                    "transcription_segments": transcription_segments,
                    "transcription_text": transcription_text,
                    "speaker_count": unique_speakers,
                    "total_segments": len(transcription_segments),
                    "total_duration": total_duration,
                    "segments_data": [
                        {
                            "index": seg.index,
                            "speaker": seg.speaker,
                            "start_time": seg.start_time,
                            "end_time": seg.end_time,
                            "text": seg.text,
                            "confidence_score": seg.confidence_score,
                            "is_final": seg.is_final
                        }
                        for seg in transcription_segments
                    ]
                }
                
                logger.info(f"✅ 音频处理完成: 片段数={len(transcription_segments)}, 说话人数={unique_speakers}")
                return result
                
            finally:
                # 清理临时文件
                await self._cleanup_temp_files(temp_audio_path, was_converted, converted_file_path)
            
        except Exception as e:
            logger.error(f"❌ 音频处理失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "transcription_segments": [],
                "transcription_text": "",
                "speaker_count": 0,
                "total_segments": 0,
                "total_duration": 0.0,
                "segments_data": []
            }
    
    async def _prepare_audio_for_processing(self, audio_path: str, file_format: str) -> Tuple[str, bool, Optional[str]]:
        """准备音频文件用于处理（转换格式如果需要）"""
        processed_audio_path = audio_path
        was_converted = False
        converted_file_path = None
        
        if file_format.lower() in ['mp3', 'mpeg']:
            logger.info("🔄 转换MP3为WAV进行说话人分离...")
            processed_audio_path, was_converted = await audio_converter.convert_to_wav_if_needed(
                audio_path, file_format
            )
            if was_converted:
                converted_file_path = processed_audio_path
        
        return processed_audio_path, was_converted, converted_file_path
    
    async def _segment_and_transcribe(self, audio_path: str, speaker_segments: List[SpeakerSegment]) -> Tuple[List[TranscriptionSegment], str]:
        """分割音频并转录"""
        segment_audios = await self.speaker_service.split_audio_by_segments(audio_path, speaker_segments)
        
        transcription_segments = []
        all_transcription_text = []
        
        for i, (speaker_segment, audio_bytes) in enumerate(segment_audios):
            try:
                # 转录音频片段
                audio_array, sample_rate = self._audio_bytes_to_numpy(audio_bytes)
                transcribed_text = stt_client.transcribe((sample_rate, audio_array))
                
                # 清理转录文本
                cleaned_text = re.sub(r'<\|[^|]*\|>', '', transcribed_text).strip()
                
                if cleaned_text:
                    segment = TranscriptionSegment(
                        index=i + 1,
                        speaker=speaker_segment.speaker_label,
                        start_time=speaker_segment.start_time,
                        end_time=speaker_segment.end_time,
                        text=cleaned_text,
                        confidence_score=None,
                        is_final=True
                    )
                    transcription_segments.append(segment)
                    all_transcription_text.append(cleaned_text)
                    
                    logger.info(f"✅ 转录片段 {i+1}: {speaker_segment.speaker_label} "
                              f"[{speaker_segment.start_time:.1f}s-{speaker_segment.end_time:.1f}s] "
                              f"文本长度: {len(cleaned_text)}")
                else:
                    logger.warning(f"⚠️ 片段 {i+1} 转录结果为空")
                    
            except Exception as e:
                logger.error(f"❌ 转录片段 {i+1} 失败: {e}")
                # 创建错误片段
                error_segment = TranscriptionSegment(
                    index=i + 1,
                    speaker=speaker_segment.speaker_label,
                    start_time=speaker_segment.start_time,
                    end_time=speaker_segment.end_time,
                    text=f"转录失败: {str(e)}",
                    confidence_score=None,
                    is_final=True
                )
                transcription_segments.append(error_segment)
        
        full_transcription_text = " ".join(all_transcription_text)
        return transcription_segments, full_transcription_text
    
    def _audio_bytes_to_numpy(self, audio_bytes: bytes) -> Tuple[np.ndarray, int]:
        """将音频字节数据转换为numpy数组"""
        try:
            # 创建临时文件进行转换
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_file_path = temp_file.name
            
            try:
                # 使用librosa加载音频
                import librosa
                audio_array, sample_rate = librosa.load(temp_file_path, sr=None)
                
                # 转换为STT期望的格式（2D数组）
                if audio_array.ndim == 1:
                    audio_array = audio_array.reshape(1, -1)
                
                return audio_array, sample_rate
                
            finally:
                # 清理临时文件
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"清理音频转换临时文件失败: {e}")
                    
        except Exception as e:
            logger.error(f"❌ 音频格式转换失败: {e}")
            raise
    
    async def _get_audio_duration(self, audio_file_path: str) -> float:
        """获取音频文件时长（秒）"""
        try:
            # 使用audio_converter获取音频信息
            audio_info = await audio_converter.get_audio_info(audio_file_path)
            return audio_info.duration
        except Exception as e:
            logger.error(f"❌ 获取音频时长失败: {e}")
            return 0.0
    
    async def _cleanup_temp_files(self, temp_audio_path: str, was_converted: bool, converted_file_path: Optional[str]):
        """清理临时文件"""
        try:
            # 清理原始临时文件
            if os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)
                logger.debug(f"🗑️ 清理原始临时文件: {temp_audio_path}")
            
            # 清理转换后的文件
            if was_converted and converted_file_path:
                audio_converter.cleanup_converted_file(converted_file_path, was_converted)
                
        except Exception as e:
            logger.warning(f"⚠️ 清理临时文件失败: {e}")

    def _merge_adjacent_short_segments(self, segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """
        Merge adjacent short segments of the same speaker
        If adjacent segments are from the same speaker and each segment duration is less than 5s, merge them
        """
        if not segments:
            return segments
        
        merged_segments = []
        current_segment = segments[0]
        
        for segment in segments[1:]:
            # Check if current and next segment are from same speaker and both are short (< 5s)
            current_duration = current_segment.end_time - current_segment.start_time
            next_duration = segment.end_time - segment.start_time
            
            if (current_segment.speaker_label == segment.speaker_label and 
                current_duration < 5.0 and next_duration < 5.0):
                # Merge segments
                logger.debug(f"🔗 合并片段: {current_segment.speaker_label} "
                           f"[{current_segment.start_time:.1f}s-{current_segment.end_time:.1f}s] + "
                           f"[{segment.start_time:.1f}s-{segment.end_time:.1f}s]")
                
                current_segment = SpeakerSegment(
                    start_time=current_segment.start_time,
                    end_time=segment.end_time,
                    speaker_label=current_segment.speaker_label,
                    duration=segment.end_time - current_segment.start_time
                )
            else:
                # No merge, add current segment to result and move to next
                merged_segments.append(current_segment)
                current_segment = segment
        
        # Add the last segment
        merged_segments.append(current_segment)
        
        # Second pass: merge segments shorter than 2s to next segment (regardless of speaker)
        final_segments = []
        i = 0
        while i < len(merged_segments):
            current_seg = merged_segments[i]
            current_duration = current_seg.end_time - current_seg.start_time
            
            # If current segment is shorter than 2s and not the last segment
            if current_duration < 2.0 and i < len(merged_segments) - 1:
                next_seg = merged_segments[i + 1]
                
                logger.debug(f"🔗 强制合并短片段: {current_seg.speaker_label} "
                           f"[{current_seg.start_time:.1f}s-{current_seg.end_time:.1f}s] -> "
                           f"{next_seg.speaker_label} [{next_seg.start_time:.1f}s-{next_seg.end_time:.1f}s]")
                
                # Merge current short segment to next segment
                merged_segment = SpeakerSegment(
                    start_time=current_seg.start_time,
                    end_time=next_seg.end_time,
                    speaker_label=next_seg.speaker_label,  # Keep next segment's speaker label
                    duration=next_seg.end_time - current_seg.start_time
                )
                
                final_segments.append(merged_segment)
                i += 2  # Skip next segment as it's already merged
            else:
                # If last segment is shorter than 2s, merge it to previous segment
                if (current_duration < 2.0 and i == len(merged_segments) - 1 and 
                    len(final_segments) > 0):
                    
                    prev_seg = final_segments.pop()  # Remove last segment from final_segments
                    
                    logger.debug(f"🔗 合并最后短片段: {prev_seg.speaker_label} "
                               f"[{prev_seg.start_time:.1f}s-{prev_seg.end_time:.1f}s] + "
                               f"{current_seg.speaker_label} [{current_seg.start_time:.1f}s-{current_seg.end_time:.1f}s]")
                    
                    merged_segment = SpeakerSegment(
                        start_time=prev_seg.start_time,
                        end_time=current_seg.end_time,
                        speaker_label=prev_seg.speaker_label,  # Keep previous segment's speaker label
                        duration=current_seg.end_time - prev_seg.start_time
                    )
                    
                    final_segments.append(merged_segment)
                else:
                    final_segments.append(current_seg)
                i += 1
        
        # Third pass: remove segments shorter than 1s
        filtered_segments = []
        removed_count = 0
        
        for segment in final_segments:
            segment_duration = segment.end_time - segment.start_time
            if segment_duration >= 1.0:
                filtered_segments.append(segment)
            else:
                removed_count += 1
                logger.debug(f"🗑️ 移除短片段: {segment.speaker_label} "
                           f"[{segment.start_time:.1f}s-{segment.end_time:.1f}s] "
                           f"时长: {segment_duration:.2f}s")
        
        original_count = len(segments)
        final_count = len(filtered_segments)
        
        if removed_count > 0:
            logger.info(f"🗑️ 移除了 {removed_count} 个小于1秒的短片段")
        
        if final_count < original_count:
            logger.info(f"✅ 片段优化完成: {original_count} -> {final_count} 个片段")
        
        return filtered_segments


# 创建全局实例
audio_processing_service = AudioProcessingService() 