"""
批量转录服务
整合说话人分离、音频分割和转录功能
"""
import logging
import tempfile
import os
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass


from .repositories import session_repository, transcription_repository, audio_file_repository
from .services import session_service
from .audio_processing_service import audio_processing_service

logger = logging.getLogger(__name__)

@dataclass
class BatchTranscriptionResult:
    """批量转录结果"""
    session_id: str
    audio_file_id: str
    total_segments: int
    total_duration: float
    transcription_id: str
    transcription_content: str
    segments: List[Dict[str, Any]]
    speaker_count: int


class BatchTranscriptionService:
    """批量转录服务"""
    
    def __init__(self):
        pass  # Now using the universal audio processing service
    
    async def process_audio_file(self, audio_file_data: bytes, original_filename: str, 
                               user_id: str, file_format: str = "mp3") -> BatchTranscriptionResult:
        """
        处理音频文件的完整流程
        
        Args:
            audio_file_data: 音频文件数据
            original_filename: 原始文件名
            user_id: 用户ID
            file_format: 文件格式
            
        Returns:
            BatchTranscriptionResult: 转录结果
        """
        try:
            logger.info(f"🎵 开始批量转录: {original_filename}, 用户: {user_id}")
            
            # Step 1: Create new session
            session = await session_service.create_session(
                user_id=user_id,
                title=f"导入音频: {original_filename}",
                language="zh-CN"
            )
            logger.info(f"✅ 创建会话: {session.id}")
            
            # Step 2: Use universal audio processing service for speaker diarization and transcription
            processing_result = await audio_processing_service.process_audio_with_speaker_diarization(
                audio_data=audio_file_data,
                file_format=file_format,
                original_filename=original_filename
            )
            
            if not processing_result["success"]:
                raise Exception(f"音频处理失败: {processing_result.get('error', 'Unknown error')}")
            
            transcription_segments = processing_result["transcription_segments"]
            full_content = processing_result["transcription_text"]
            
            logger.info(f"✅ 音频处理完成: 片段数={processing_result['total_segments']}, 说话人数={processing_result['speaker_count']}")
            
            # Step 3: Save audio file to storage
            logger.info("💾 保存音频文件...")
            
            # Use optimized audio processing method
            audio_result = await self._process_and_save_audio_file(
                audio_file_data=audio_file_data,
                session_id=session.id,
                user_id=user_id,
                original_filename=original_filename,
                file_format=file_format,
                duration_seconds=processing_result["total_duration"]
            )
            
            if not audio_result["success"]:
                raise Exception(f"保存音频文件失败: {audio_result.get('error', 'Unknown error')}")
            
            audio_file_id = audio_result["audio_file_id"]
            logger.info(f"✅ 音频文件保存成功: {audio_file_id}")
            
            # Step 4: Save transcription results
            logger.info("💾 保存转录结果...")
            
            # Save transcription record
            transcription = await transcription_repository.save_transcription(
                session_id=session.id,
                content=full_content,
                segments=processing_result["segments_data"],
                word_count=len(full_content.split()) if full_content else 0
            )
            
            # Step 5: Update session status
            await session_service.update_session_status(session.id, "completed")
            
            result = BatchTranscriptionResult(
                session_id=session.id,
                audio_file_id=audio_file_id,
                total_segments=processing_result["total_segments"],
                total_duration=processing_result["total_duration"],
                transcription_id=transcription.id,
                transcription_content=full_content,
                segments=processing_result["segments_data"],
                speaker_count=processing_result["speaker_count"]
            )
            
            logger.info(f"✅ 批量转录完成: 会话={session.id}, "
                      f"片段数={processing_result['total_segments']}, "
                      f"说话人数={processing_result['speaker_count']}, "
                      f"转录文本长度={len(full_content)}, "
                      f"原始格式={file_format}, 存储格式=mp3")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 批量转录失败: {e}")
            raise
    
    async def _get_audio_duration(self, audio_file_path: str) -> float:
        """获取音频文件时长（秒）"""
        try:
            # 使用audio_converter获取音频信息
            from .audio_converter import audio_converter
            audio_info = await audio_converter.get_audio_info(audio_file_path)
            return audio_info.duration
        except Exception as e:
            logger.error(f"❌ 获取音频时长失败: {e}")
            return 0.0
    

    

    
    async def _process_and_save_audio_file(self, audio_file_data: bytes, session_id: str, 
                                          user_id: str, original_filename: str, 
                                          file_format: str, duration_seconds: float) -> Dict[str, Any]:
        """
        处理并保存音频文件 - 复用SessionService中的优化逻辑
        包括格式转换、上传到Storage、保存数据库记录
        """
        try:
            # Convert to MP3 format for storage using the method similar to SessionService
            mp3_data, file_size, calculated_duration = await self._convert_to_mp3_bytes(audio_file_data, file_format)
            
            # Use provided duration if available, otherwise use calculated duration
            final_duration = duration_seconds if duration_seconds > 0 else calculated_duration
            
            # Generate storage path for batch transcription
            timestamp = int(__import__('time').time())
            storage_path = f"batch-transcription/{user_id}/{session_id}_{timestamp}.mp3"
            
            # Upload to Supabase Storage using existing method
            storage_result = await self._upload_audio_to_storage(mp3_data, storage_path)
            
            if not storage_result["success"]:
                logger.error(f"音频文件上传失败: {storage_result.get('error', 'Unknown error')}")
                return {"success": False, "error": f"音频文件上传失败: {storage_result.get('error')}"}
            
            # Save audio file record to database
            audio_file = await audio_file_repository.save_audio_file(
                session_id=session_id,
                user_id=user_id,
                original_filename=original_filename,
                storage_path=storage_result["storage_path"],
                public_url=storage_result.get("public_url"),
                file_size_bytes=file_size,
                duration_seconds=final_duration,
                format="mp3"  # Always save as MP3
            )
            
            logger.info(f"✅ 音频文件处理完成: {audio_file.id}, 路径: {storage_result['storage_path']}")
            
            return {
                "success": True,
                "audio_file_id": audio_file.id,
                "storage_path": storage_result["storage_path"],
                "public_url": storage_result.get("public_url"),
                "file_size": file_size,
                "duration_seconds": final_duration
            }
            
        except Exception as e:
            logger.error(f"处理音频文件失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _convert_to_mp3_bytes(self, audio_data: bytes, file_format: str) -> Tuple[bytes, int, float]:
        """
        将音频数据转换为MP3格式 - 使用ffmpeg
        
        Args:
            audio_data: 原始音频数据
            file_format: 音频格式
            
        Returns:
            Tuple[bytes, int, float]: (MP3数据, 文件大小, 时长秒数)
        """
        try:
            import tempfile
            import subprocess
            from .audio_converter import audio_converter
            
            # Create temporary input file
            with tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False) as temp_input:
                temp_input.write(audio_data)
                temp_input_path = temp_input.name
            
            try:
                # Get audio info first
                audio_info = await audio_converter.get_audio_info(temp_input_path)
                duration_seconds = audio_info.duration
                
                # Convert to MP3 using ffmpeg
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_output:
                    temp_output_path = temp_output.name
                
                try:
                    if not audio_converter.ffmpeg_path:
                        raise Exception("ffmpeg不可用，无法转换为MP3")
                    
                    # Use ffmpeg to convert to MP3
                    cmd = [
                        audio_converter.ffmpeg_path,
                        '-i', temp_input_path,          # Input file
                        '-codec:a', 'mp3',              # MP3 codec
                        '-b:a', '128k',                 # 128k bitrate
                        '-y',                           # Overwrite output file
                        temp_output_path
                    ]
                    
                    logger.debug(f"🔧 执行ffmpeg MP3转换命令: {' '.join(cmd)}")
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=300  # 5分钟超时
                    )
                    
                    if result.returncode != 0:
                        error_msg = f"ffmpeg MP3转换失败: {result.stderr}"
                        logger.error(f"❌ {error_msg}")
                        raise Exception(error_msg)
                    
                    # Read MP3 data
                    with open(temp_output_path, 'rb') as mp3_file:
                        mp3_data = mp3_file.read()
                    
                    # Calculate metrics
                    file_size = len(mp3_data)
                    
                    logger.info(f"🔄 音频转换完成: {file_format} -> MP3, "
                              f"原始大小: {len(audio_data)} bytes, "
                              f"MP3大小: {file_size} bytes, "
                              f"时长: {duration_seconds:.2f}s")
                    
                    return mp3_data, file_size, duration_seconds
                    
                finally:
                    # Clean up output temp file
                    try:
                        if os.path.exists(temp_output_path):
                            os.unlink(temp_output_path)
                    except Exception as e:
                        logger.warning(f"清理输出临时文件失败: {e}")
                        
            finally:
                # Clean up input temp file
                try:
                    if os.path.exists(temp_input_path):
                        os.unlink(temp_input_path)
                except Exception as e:
                    logger.warning(f"清理输入临时文件失败: {e}")
                    
        except Exception as e:
            logger.error(f"❌ 音频转换失败: {e}")
            # If conversion fails, return original data with estimated metrics
            logger.warning("⚠️ 转换失败，使用原始音频数据")
            return audio_data, len(audio_data), 0.0

    async def _upload_audio_to_storage(self, audio_data: bytes, storage_path: str) -> Dict[str, Any]:
        """上传音频文件到Supabase Storage"""
        try:
            from .clients import supabase_client
            
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


# 全局实例
batch_transcription_service = BatchTranscriptionService() 