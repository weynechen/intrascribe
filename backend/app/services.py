"""
业务服务层
实现核心业务逻辑
"""
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import tempfile
import io
import numpy as np

import librosa
import re
from .models import (
    Session, SessionStatus, SessionCache, Transcription, AISummary, AudioFile,
    UserProfile, TranscriptionSegment
)
from .repositories import (
    session_repository, transcription_repository, ai_summary_repository,
    audio_file_repository, user_repository
)
from .clients import stt_client, ai_client, supabase_client
from .dependencies import BusinessLogicError

logger = logging.getLogger(__name__)


class SessionCacheManager:
    """会话缓存管理器"""
    
    def __init__(self):
        self.session_caches: Dict[str, SessionCache] = {}
        self.current_session_id: Optional[str] = None
    
    def create_session_cache(self, session_id: str, user_id: str) -> SessionCache:
        """创建会话缓存"""
        cache = SessionCache(
            session_id=session_id,
            user_id=user_id,
            start_time=datetime.utcnow(),
            last_activity=datetime.utcnow()
        )
        self.session_caches[session_id] = cache
        logger.info(f"📦 创建会话缓存: {session_id}")
        return cache
    
    def get_session_cache(self, session_id: str) -> Optional[SessionCache]:
        """获取会话缓存"""
        return self.session_caches.get(session_id)
    
    def update_last_activity(self, session_id: str):
        """更新最后活动时间"""
        if session_id in self.session_caches:
            self.session_caches[session_id].last_activity = datetime.utcnow()
    
    def add_audio_segment(self, session_id: str, audio_data: np.ndarray, sample_rate: int):
        """添加音频片段到缓存"""
        cache = self.get_session_cache(session_id)
        if cache:
            cache.audio_segments.append({
                'data': audio_data.copy(),
                'sample_rate': sample_rate,
                'timestamp': datetime.utcnow()
            })
            cache.sample_rate = sample_rate
            self.update_last_activity(session_id)
            logger.debug(f"🎵 添加音频片段到会话 {session_id}，当前片段数: {len(cache.audio_segments)}")
    
    def add_transcription_segment(self, session_id: str, segment: TranscriptionSegment):
        """添加转录片段到缓存"""
        cache = self.get_session_cache(session_id)
        if cache:
            cache.transcription_segments.append(segment)
            self.update_last_activity(session_id)
            logger.debug(f"📝 添加转录片段到会话 {session_id}: {segment.text}")
    
    def remove_session_cache(self, session_id: str):
        """移除会话缓存"""
        if session_id in self.session_caches:
            del self.session_caches[session_id]
            logger.info(f"🗑️ 移除会话缓存: {session_id}")
    
    def get_cache_status(self) -> Dict[str, Any]:
        """获取缓存状态"""
        total_audio_segments = sum(len(cache.audio_segments) for cache in self.session_caches.values())
        total_transcription_segments = sum(len(cache.transcription_segments) for cache in self.session_caches.values())
        
        return {
            "total_sessions": len(self.session_caches),
            "active_sessions": list(self.session_caches.keys()),
            "current_session": self.current_session_id,
            "total_audio_segments": total_audio_segments,
            "total_transcription_segments": total_transcription_segments,
            "oldest_session": min(
                (cache.start_time for cache in self.session_caches.values()),
                default=None
            )
        }


class SessionService:
    """会话服务"""
    
    def __init__(self, cache_manager: SessionCacheManager):
        self.cache_manager = cache_manager
    
    async def create_session(self, user_id: str, title: str, language: str = "zh-CN", 
                           stt_model: str = "whisper") -> Session:
        """创建新会话"""
        try:
            # 1. 在数据库中创建会话记录
            session = await session_repository.create_session(
                user_id=user_id,
                title=title,
                language=language,
                stt_model=stt_model
            )
            
            # 2. 创建会话缓存
            self.cache_manager.create_session_cache(session.id, user_id)
            
            # 3. 设置为当前活跃会话
            self.cache_manager.current_session_id = session.id
            
            logger.info(f"✅ 创建会话成功: {session.id}")
            return session
            
        except Exception as e:
            logger.error(f"创建会话失败: {e}")
            raise BusinessLogicError(f"创建会话失败: {e}")
    
    async def get_session(self, session_id: str, user_id: str) -> Optional[Session]:
        """获取会话详情"""
        try:
            return await session_repository.get_session_by_id(session_id, user_id)
        except Exception as e:
            logger.error(f"获取会话详情失败: {e}")
            raise BusinessLogicError(f"获取会话详情失败: {e}")
    
    async def finalize_session(self, session_id: str, user_id: str) -> Dict[str, Any]:
        """结束并整理会话"""
        try:
            # 1. 验证会话所有权
            session = await session_repository.get_session_by_id(session_id, user_id)
            if not session:
                raise BusinessLogicError("会话不存在或无权访问")
            
            # 2. 获取会话缓存
            cache = self.cache_manager.get_session_cache(session_id)
            if not cache:
                raise BusinessLogicError("会话缓存不存在，可能已经被清理")
            
            # 3. 处理音频数据
            audio_result = await self._process_cached_audio(cache)
            
            # 4. 保存初始转录数据（用于备份）
            transcription_result = await self._save_transcription_data(cache)
            
            # 5. 更新会话状态为processing，准备批量处理
            # 确保写入数据库的时长为整数
            raw_duration = audio_result.get('duration_seconds', 0)
            try:
                safe_duration = int(float(raw_duration))
            except (TypeError, ValueError):
                safe_duration = 0
            await session_repository.update_session_status(
                session_id=session_id,
                status=SessionStatus.PROCESSING,
                ended_at=datetime.utcnow(),
                duration_seconds=safe_duration
            )
            
            # 6. 直接使用内存中的音频数据进行批量重新处理（优化：避免下载）
            logger.info(f"🔄 启动批量重新处理任务: session_id={session_id}")
            try:
                # 获取合并的音频数据
                combined_audio = self._combine_audio_segments(cache.audio_segments)
                mp3_data, _, _ = await self._convert_to_mp3(combined_audio, cache.sample_rate)
                
                await self._reprocess_session_with_audio_data(
                    session_id=session_id,
                    user_id=user_id,
                    audio_data=mp3_data,
                    audio_file_id=audio_result.get('audio_file_id')
                )
            except Exception as e:
                logger.error(f"⚠️ 批量重新处理失败，但会话已保存: {e}")
                # 即使批量处理失败，也标记会话为completed，避免状态卡住
                await session_repository.update_session_status(
                    session_id=session_id,
                    status=SessionStatus.COMPLETED
                )
            
            # 7. 清理缓存
            self.cache_manager.remove_session_cache(session_id)
            if self.cache_manager.current_session_id == session_id:
                self.cache_manager.current_session_id = None
            
            # 8. 返回结果
            final_data = {
                "total_duration_seconds": audio_result.get('duration_seconds', 0),
                "word_count": transcription_result.get('word_count', 0),
                "audio_file_path": audio_result.get('storage_path'),
                "transcription_saved": transcription_result.get('success', False),
                "audio_file_id": audio_result.get('audio_file_id'),
                "transcription_id": transcription_result.get('transcription_id'),
                "reprocessing_started": True
            }
            
            logger.info(f"✅ 会话结束成功，批量重新处理已启动: {session_id}")
            return final_data
            
        except Exception as e:
            logger.error(f"结束会话失败: {e}")
            raise BusinessLogicError(f"结束会话失败: {e}")
    
    async def _process_cached_audio(self, cache: SessionCache) -> Dict[str, Any]:
        """处理缓存的音频数据"""
        try:
            if not cache.audio_segments:
                logger.warning("没有音频数据需要处理")
                return {"success": False, "message": "没有音频数据"}
            
            logger.info(f"🎵 开始处理 {len(cache.audio_segments)} 个音频片段")
            
            # 合并音频片段
            combined_audio = self._combine_audio_segments(cache.audio_segments)
            
            # 转换为MP3格式
            mp3_data, file_size, duration_seconds = await self._convert_to_mp3(combined_audio, cache.sample_rate)
            
            # 上传到Supabase Storage
            storage_result = await self._upload_audio_to_storage(
                mp3_data, cache.session_id, cache.user_id
            )
            
            if not storage_result["success"]:
                logger.error(f"音频文件上传失败: {storage_result.get('error', 'Unknown error')}")
                return {"success": False, "error": f"音频文件上传失败: {storage_result.get('error')}"}
            
            # 保存音频文件记录到数据库
            audio_file = await audio_file_repository.save_audio_file(
                session_id=cache.session_id,
                user_id=cache.user_id,
                original_filename=f"session_{cache.session_id}.mp3",
                storage_path=storage_result["storage_path"],
                public_url=storage_result.get("public_url"),
                file_size_bytes=file_size,
                duration_seconds=duration_seconds,
                format="mp3",
                sample_rate=cache.sample_rate
            )
            
            logger.info(f"✅ 音频文件处理完成: {audio_file.id}, 路径: {storage_result['storage_path']}")
            
            return {
                "success": True,
                "audio_file_id": audio_file.id,
                "storage_path": storage_result["storage_path"],
                "public_url": storage_result.get("public_url"),
                "file_size": file_size,
                "duration_seconds": duration_seconds
            }
            
        except Exception as e:
            logger.error(f"处理音频数据失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _combine_audio_segments(self, segments: List[Dict[str, Any]]) -> np.ndarray:
        """合并音频片段"""
        if not segments:
            return np.array([])
        
        # 假设所有片段都有相同的采样率
        combined = []
        for segment in segments:
            audio_data = segment['data']
            if isinstance(audio_data, np.ndarray):
                combined.append(audio_data.flatten())
        
        if combined:
            return np.concatenate(combined)
        else:
            return np.array([])
    
    async def _convert_to_mp3(self, audio_data: np.ndarray, sample_rate: int) -> Tuple[bytes, int, float]:
        """将音频数据转换为MP3格式"""
        try:
            import tempfile
            import subprocess
            import wave
            from .audio_converter import audio_converter
            
            # 确保音频数据为int16格式
            if audio_data.dtype == np.float32:
                audio_data = (audio_data * 32767).astype(np.int16)
            elif audio_data.dtype != np.int16:
                audio_data = audio_data.astype(np.int16)
            
            # 创建临时WAV文件
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                temp_wav_path = temp_wav.name
            
            # 写入WAV文件
            with wave.open(temp_wav_path, 'wb') as wav_file:
                wav_file.setnchannels(1)  # 单声道
                wav_file.setsampwidth(2)  # 16-bit = 2 bytes
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_data.tobytes())
            
            try:
                # 计算时长
                duration_seconds = len(audio_data) / sample_rate
                
                # 使用ffmpeg转换为MP3
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_mp3:
                    temp_mp3_path = temp_mp3.name
                
                try:
                    if not audio_converter.ffmpeg_path:
                        raise Exception("ffmpeg不可用，无法转换为MP3")
                    
                    cmd = [
                        audio_converter.ffmpeg_path,
                        '-i', temp_wav_path,            # Input WAV file
                        '-codec:a', 'mp3',              # MP3 codec
                        '-b:a', '128k',                 # 128k bitrate
                        '-y',                           # Overwrite output file
                        temp_mp3_path
                    ]
                    
                    logger.debug(f"🔧 执行ffmpeg MP3转换: {' '.join(cmd)}")
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    if result.returncode != 0:
                        error_msg = f"ffmpeg MP3转换失败: {result.stderr}"
                        logger.error(f"❌ {error_msg}")
                        raise Exception(error_msg)
                    
                    # 读取MP3数据
                    with open(temp_mp3_path, 'rb') as mp3_file:
                        mp3_data = mp3_file.read()
                    
                    return mp3_data, len(mp3_data), duration_seconds
                    
                finally:
                    # 清理MP3临时文件
                    try:
                        if os.path.exists(temp_mp3_path):
                            os.unlink(temp_mp3_path)
                    except Exception as e:
                        logger.warning(f"清理MP3临时文件失败: {e}")
                        
            finally:
                # 清理WAV临时文件
                try:
                    if os.path.exists(temp_wav_path):
                        os.unlink(temp_wav_path)
                except Exception as e:
                    logger.warning(f"清理WAV临时文件失败: {e}")
            
        except Exception as e:
            logger.error(f"转换音频格式失败: {e}")
            raise
    
    async def _upload_audio_to_storage(self, audio_data: bytes, session_id: str, user_id: str) -> Dict[str, Any]:
        """上传音频文件到Supabase Storage"""
        try:
            # 生成存储路径
            timestamp = int(time.time())
            storage_path = f"raw/{user_id}/{session_id}_{timestamp}.mp3"
            
            # 获取service role客户端用于上传
            client = supabase_client.get_service_client()
            
            # 上传文件到storage
            logger.info(f"📤 开始上传音频文件到: {storage_path}")
            
            result = client.storage.from_("audio-recordings").upload(
                path=storage_path,
                file=audio_data,
                file_options={"content-type": "audio/mpeg"}
            )
            
            if hasattr(result, 'error') and result.error:
                logger.error(f"Storage上传失败: {result.error}")
                return {"success": False, "error": str(result.error)}
            
            # 生成公开访问URL
            public_url = None
            try:
                # 如果配置了公共URL，使用它来构建完整的访问路径
                from .config import settings
                if settings.supabase.public_url:
                    public_url = f"{settings.supabase.public_url}/storage/v1/object/public/audio-recordings/{storage_path}"
                    logger.info(f"🔗 使用配置的公开访问URL: {public_url}")
                else:
                    # 回退到默认的URL生成方式
                    url_result = client.storage.from_("audio-recordings").get_public_url(storage_path)
                    if url_result:
                        public_url = url_result
                        logger.info(f"🔗 使用默认生成的公开访问URL: {public_url}")
            except Exception as e:
                logger.warning(f"生成公开URL失败: {e}")
            
            logger.info(f"✅ 音频文件上传成功: {storage_path}")
            
            return {
                "success": True,
                "storage_path": storage_path,
                "public_url": public_url
            }
            
        except Exception as e:
            logger.error(f"上传音频文件到Storage失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _save_transcription_data(self, cache: SessionCache) -> Dict[str, Any]:
        """保存转录数据"""
        try:
            if not cache.transcription_segments:
                logger.warning("没有转录数据需要保存")
                return {"success": False, "message": "没有转录数据"}
            
            # 合并转录内容
            full_content = " ".join(segment.text for segment in cache.transcription_segments)
            
            # 转换segments为字典格式
            segments_data = [
                {
                    "index": seg.index,
                    "speaker": seg.speaker,
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "text": seg.text,
                    "confidence_score": seg.confidence_score,
                    "is_final": seg.is_final
                }
                for seg in cache.transcription_segments
            ]
            
            # 保存转录记录
            transcription = await transcription_repository.save_transcription(
                session_id=cache.session_id,
                content=full_content,
                segments=segments_data,
                word_count=len(full_content.split())
            )
            
            return {
                "success": True,
                "transcription_id": transcription.id,
                "word_count": transcription.word_count
            }
            
        except Exception as e:
            logger.error(f"保存转录数据失败: {e}")
            return {"success": False, "error": str(e)}
    
    def set_current_session(self, session_id: str):
        """设置当前活跃会话"""
        self.cache_manager.current_session_id = session_id
        logger.info(f"🎯 设置当前会话: {session_id}")
    
    def get_current_session(self) -> Optional[str]:
        """获取当前活跃会话"""
        return self.cache_manager.current_session_id
    
    async def update_session_status(self, session_id: str, status: str) -> bool:
        """更新会话状态"""
        try:
            from .models import SessionStatus
            session_status = SessionStatus(status)
            await session_repository.update_session_status(session_id, session_status)
            logger.info(f"✅ 更新会话状态: session_id={session_id}, status={status}")
            return True
        except Exception as e:
            logger.error(f"❌ 更新会话状态失败: {e}")
            return False

    async def delete_session(self, session_id: str, user_id: str) -> bool:
        """删除会话及其关联的音频文件"""
        try:
            # 清理缓存（如果存在）
            if session_id in self.cache_manager.session_caches:
                self.cache_manager.remove_session_cache(session_id)
                logger.info(f"🧹 清理会话缓存: {session_id}")
            
            # 如果这是当前活跃会话，清除引用
            if self.cache_manager.current_session_id == session_id:
                self.cache_manager.current_session_id = None
            
            # 调用仓储层删除
            result = await session_repository.delete_session(session_id, user_id)
            
            if result:
                logger.info(f"✅ 会话删除成功: {session_id}")
            else:
                logger.warning(f"⚠️ 会话删除结果异常: {session_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 删除会话失败: {e}")
            raise BusinessLogicError(f"删除会话失败: {e}")

    async def _reprocess_session_with_audio_data(self, session_id: str, user_id: str, 
                                               audio_data: bytes, audio_file_id: str):
        """使用内存中的音频数据重新处理会话，包括说话人分离和转录"""
        try:
            from .audio_processing_service import audio_processing_service
            
            logger.info(f"🎤 开始重新处理会话（使用内存音频数据）: {session_id}")
            
            # 使用通用音频处理服务进行处理
            processing_result = await audio_processing_service.process_audio_with_speaker_diarization(
                audio_data=audio_data,
                file_format="mp3",  # 内存中的音频已经是MP3格式
                original_filename=f"session_{session_id}.mp3"
            )
            
            if processing_result["success"]:
                # 更新转录记录
                await transcription_repository.update_transcription_with_reprocessed_data(
                    session_id=session_id,
                    content=processing_result["transcription_text"],
                    segments=processing_result["segments_data"],
                    word_count=len(processing_result["transcription_text"].split()) if processing_result["transcription_text"] else 0
                )
                
                logger.info(f"✅ 会话重新处理完成: {session_id}, 检测到 {processing_result['speaker_count']} 个说话人")
                
                # 更新会话状态为completed
                await session_repository.update_session_status(
                    session_id=session_id,
                    status=SessionStatus.COMPLETED
                )
            else:
                logger.error(f"❌ 会话重新处理失败: {session_id}, 错误: {processing_result.get('error')}")
                # 仍然标记为completed，避免状态卡住
                await session_repository.update_session_status(
                    session_id=session_id,
                    status=SessionStatus.COMPLETED
                )
                
        except Exception as e:
            logger.error(f"❌ 重新处理会话失败: {e}")
            # 确保会话状态不会卡在processing
            try:
                await session_repository.update_session_status(
                    session_id=session_id,
                    status=SessionStatus.COMPLETED
                )
            except Exception as status_error:
                logger.error(f"更新会话状态失败: {status_error}")


class AudioTranscriptionService:
    """音频转录服务"""
    
    def __init__(self, cache_manager: SessionCacheManager):
        self.cache_manager = cache_manager
    
    async def transcribe_audio(self, audio: Tuple[int, np.ndarray], session_id: str) -> Dict[str, Any]:
        """转录音频片段，返回结构化的转录数据"""
        try:
            sample_rate, audio_data = audio
            
            # 使用传入的会话ID
            current_session_id = session_id
            
            # 如果会话缓存不存在，从数据库获取会话信息并创建缓存
            if not self.cache_manager.get_session_cache(current_session_id):
                logger.info(f"🆕 为会话 {current_session_id} 创建新的缓存")
                # 从数据库获取会话信息来获取正确的用户ID
                try:
                    session = await session_repository.get_session_by_id(current_session_id)
                    if session:
                        self.cache_manager.create_session_cache(current_session_id, session.user_id)
                    else:
                        logger.error(f"会话 {current_session_id} 不存在于数据库中")
                        return {"error": "会话不存在"}
                except Exception as e:
                    logger.error(f"获取会话信息失败: {e}")
                    return {"error": f"获取会话信息失败: {e}"}
            
            # 设置为当前活跃会话
            self.cache_manager.current_session_id = current_session_id
            
            # 获取会话缓存
            session_cache = self.cache_manager.get_session_cache(current_session_id)
            
            # 计算时间戳信息
            audio_duration = audio_data.shape[1] / sample_rate  # 当前音频片段时长（秒）
            logger.info(f"🎵 音频片段时长: {audio_duration} 秒,len(audio_data): {len(audio_data)},sample_rate: {sample_rate}")
            start_time = 0.0
            
            # 如果有之前的转录片段，计算累积时间
            if session_cache.transcription_segments:
                last_segment = session_cache.transcription_segments[-1]
                start_time = last_segment.end_time
            
            end_time = start_time + audio_duration
            
            # 添加音频数据到缓存
            self.cache_manager.add_audio_segment(current_session_id, audio_data, sample_rate)
            
            # 使用STT服务进行转录
            transcribed_text = stt_client.transcribe(audio)
            # 清理转录文本，移除<|...|>格式的标记
            cleaned_text = re.sub(r'<\|[^|]*\|>', '', transcribed_text).strip()
            
            if cleaned_text:
                # 创建转录片段
                segment_index = len(session_cache.transcription_segments) + 1
                segment = TranscriptionSegment(
                    index=segment_index,
                    speaker="pending_speaker",  # Real-time transcription uses temporary speaker label
                    start_time=start_time,
                    end_time=end_time,
                    text=cleaned_text,
                    is_final=True
                )
                
                # 添加到缓存
                self.cache_manager.add_transcription_segment(current_session_id, segment)
                
                # 格式化时间戳为 [开始时间,结束时间] 格式，精确到毫秒
                start_time_str = self._format_timestamp(start_time)
                end_time_str = self._format_timestamp(end_time)
                timestamp_range = f"[{start_time_str},{end_time_str}]"
                
                # 返回符合设计文档的结构化数据
                return {
                    "index": segment_index,
                    "speaker": "pending_speaker",  # Use temporary speaker identifier for real-time
                    "timestamp": timestamp_range,
                    "text": cleaned_text,
                    "is_final": True
                }
            else:
                # 如果转录为空，返回空结果
                return None
            
        except Exception as e:
            logger.error(f"音频转录失败: {e}")
            return {
                "index": 0,
                "speaker": "system",
                "timestamp": "[00:00:00:000,00:00:00:000]",
                "text": f"转录失败: {str(e)}",
                "is_final": True
            }
    
    def _format_timestamp(self, seconds: float) -> str:
        """将秒数格式化为 HH:MM:SS:mmm 格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d}:{milliseconds:03d}"


class AIService:
    """AI服务"""
    
    async def generate_summary(self, transcription: str) -> Tuple[str, Dict[str, Any]]:
        """生成AI总结"""
        try:
            return await ai_client.generate_summary(transcription)
        except Exception as e:
            logger.error(f"生成AI总结失败: {e}")
            return f"AI总结生成失败：{str(e)}", {
                "error": str(e),
                "fallback_used": True,
                "timestamp": int(time.time())
            }
    
    async def generate_title(self, transcription: str, summary: str = None) -> Tuple[str, Dict[str, Any]]:
        """生成AI标题"""
        try:
            return await ai_client.generate_title(transcription, summary)
        except Exception as e:
            logger.error(f"生成AI标题失败: {e}")
            from datetime import datetime
            now = datetime.now()
            default_title = f"会议记录 {now.strftime('%Y-%m-%d %H:%M')}"
            return default_title, {
                "error": str(e),
                "fallback_used": True,
                "timestamp": int(time.time())
            }


class UserService:
    """用户服务"""
    
    async def get_user_profile(self, user_id: str) -> UserProfile:
        """获取用户业务资料"""
        try:
            return await user_repository.get_user_profile(user_id)
        except Exception as e:
            logger.error(f"获取用户资料失败: {e}")
            raise BusinessLogicError(f"获取用户资料失败: {e}")
    
    async def update_user_preferences(self, user_id: str, preferences: Dict[str, Any]) -> UserProfile:
        """更新用户偏好设置"""
        try:
            return await user_repository.update_user_preferences(user_id, preferences)
        except Exception as e:
            logger.error(f"更新用户偏好失败: {e}")
            raise BusinessLogicError(f"更新用户偏好失败: {e}")


# 全局服务实例
cache_manager = SessionCacheManager()
session_service = SessionService(cache_manager)
audio_transcription_service = AudioTranscriptionService(cache_manager)
ai_service = AIService()
user_service = UserService() 