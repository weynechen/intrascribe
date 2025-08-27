"""
数据仓储层
负责数据库交互操作，为服务层提供清晰的数据访问接口
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from .clients import supabase_client
from .models import (
    Session, SessionStatus, Transcription, AISummary, AudioFile,
    UserProfile, TranscriptionSegment
)

logger = logging.getLogger(__name__)


class SessionRepository:
    """会话数据仓储"""
    
    def __init__(self):
        self.client = supabase_client
    
    async def create_session(self, user_id: str, title: str, language: str = "zh-CN", 
                           stt_model: str = "whisper", session_id: Optional[str] = None) -> Session:
        """创建新会话"""
        try:
            client = self.client.get_service_client()
            
            session_data = {
                "user_id": user_id,
                "title": title,
                "status": SessionStatus.CREATED.value,
                "created_at": datetime.utcnow().isoformat(),
                "metadata": {
                    "language": language,
                    "stt_model": stt_model
                }
            }
            
            # 如果提供了自定义session_id，则使用它
            if session_id:
                session_data["id"] = session_id
            
            result = client.table('recording_sessions').insert(session_data).execute()
            
            if not result.data:
                raise Exception("创建会话失败")
            
            session_dict = result.data[0]
            # 从metadata中提取language和stt_model字段到顶级，以兼容现有的Session模型
            if 'metadata' in session_dict and session_dict['metadata']:
                session_dict['language'] = session_dict['metadata'].get('language', 'zh-CN')
                session_dict['stt_model'] = session_dict['metadata'].get('stt_model', 'whisper')
            else:
                session_dict['language'] = 'zh-CN'
                session_dict['stt_model'] = 'whisper'
            
            return Session(**session_dict)
            
        except Exception as e:
            logger.error(f"创建会话失败: {e}")
            raise
    
    async def get_session_by_id(self, session_id: str, user_id: str = None) -> Optional[Session]:
        """根据ID获取会话"""
        try:
            # 始终使用service_client，因为API级别已经验证了权限
            client = self.client.get_service_client()
            
            query = client.table('recording_sessions').select('*').eq('id', session_id)
            
            if user_id:
                query = query.eq('user_id', user_id)
            
            result = query.execute()
            
            if not result.data:
                return None
            
            session_dict = result.data[0]
            # 从metadata中提取language和stt_model字段到顶级，以兼容现有的Session模型
            if 'metadata' in session_dict and session_dict['metadata']:
                session_dict['language'] = session_dict['metadata'].get('language', 'zh-CN')
                session_dict['stt_model'] = session_dict['metadata'].get('stt_model', 'whisper')
            else:
                session_dict['language'] = 'zh-CN'
                session_dict['stt_model'] = 'whisper'
            
            return Session(**session_dict)
            
        except Exception as e:
            logger.error(f"获取会话失败: {e}")
            raise
    
    async def update_session_status(self, session_id: str, status: SessionStatus, 
                                  ended_at: Optional[datetime] = None,
                                  duration_seconds: Optional[float] = None) -> Session:
        """更新会话状态"""
        try:
            client = self.client.get_service_client()
            
            update_data = {
                "status": status.value,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            if ended_at:
                update_data["ended_at"] = ended_at.isoformat()
            
            if duration_seconds is not None:
                # 会话表字段为 INTEGER，确保写入整数值
                try:
                    update_data["duration_seconds"] = int(float(duration_seconds))
                except (TypeError, ValueError):
                    logger.warning(f"duration_seconds 无法转换为整数，收到值: {duration_seconds}")
                    update_data["duration_seconds"] = 0
            
            result = client.table('recording_sessions').update(update_data).eq('id', session_id).execute()
            
            if not result.data:
                raise Exception("更新会话状态失败")
            
            session_dict = result.data[0]
            return Session(**session_dict)
            
        except Exception as e:
            logger.error(f"更新会话状态失败: {e}")
            raise

    async def delete_session(self, session_id: str, user_id: str) -> bool:
        """删除会话及其关联的音频文件"""
        try:
            client = self.client.get_service_client()
            
            # 1. 验证会话所有权
            session_result = client.table('recording_sessions')\
                .select('user_id')\
                .eq('id', session_id)\
                .execute()
            
            if not session_result.data:
                logger.warning(f"要删除的会话不存在: {session_id}")
                return False
            
            session_user_id = session_result.data[0]['user_id']
            if session_user_id != user_id:
                logger.error(f"用户 {user_id} 无权删除会话 {session_id}")
                raise Exception("无权删除此会话")
            
            # 2. 获取关联的音频文件，准备删除Storage中的文件
            audio_files_result = client.table('audio_files')\
                .select('storage_path')\
                .eq('session_id', session_id)\
                .execute()
            
            storage_paths = [af['storage_path'] for af in audio_files_result.data if af.get('storage_path')]
            
            # 3. 删除会话记录（级联删除相关记录）
            delete_result = client.table('recording_sessions')\
                .delete()\
                .eq('id', session_id)\
                .execute()
            
            if not delete_result.data:
                logger.warning(f"删除会话记录失败或记录不存在: {session_id}")
            else:
                logger.info(f"✅ 删除会话记录成功: {session_id}")
            
            # 4. 删除Storage中的音频文件
            if storage_paths:
                logger.info(f"🗑️ 准备删除 {len(storage_paths)} 个音频文件")
                deleted_count = 0
                failed_count = 0
                
                for storage_path in storage_paths:
                    try:
                        # Delete file from Supabase Storage
                        storage_result = client.storage.from_("audio-recordings").remove([storage_path])
                        
                        # Check if deletion was successful
                        if hasattr(storage_result, 'error') and storage_result.error:
                            logger.warning(f"删除Storage文件失败: {storage_path}, 错误: {storage_result.error}")
                            failed_count += 1
                        else:
                            logger.info(f"✅ 删除Storage文件成功: {storage_path}")
                            deleted_count += 1
                            
                    except Exception as e:
                        logger.warning(f"删除Storage文件失败: {storage_path}, 异常: {e}")
                        failed_count += 1
                
                logger.info(f"🗑️ 音频文件删除完成: 成功 {deleted_count} 个, 失败 {failed_count} 个")
            
            return True
            
        except Exception as e:
            logger.error(f"删除会话失败: {e}")
            raise
    
    async def get_user_sessions(self, user_id: str, limit: int = 50, offset: int = 0) -> List[Session]:
        """获取用户的会话列表"""
        try:
            client = self.client.get_service_client()
            
            result = client.table('recording_sessions')\
                .select('*')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .limit(limit)\
                .offset(offset)\
                .execute()
            
            sessions = []
            for session_dict in result.data:
                # 从metadata中提取language和stt_model字段到顶级，以兼容现有的Session模型
                if 'metadata' in session_dict and session_dict['metadata']:
                    session_dict['language'] = session_dict['metadata'].get('language', 'zh-CN')
                    session_dict['stt_model'] = session_dict['metadata'].get('stt_model', 'whisper')
                else:
                    session_dict['language'] = 'zh-CN'
                    session_dict['stt_model'] = 'whisper'
                sessions.append(Session(**session_dict))
            
            return sessions
            
        except Exception as e:
            logger.error(f"获取用户会话列表失败: {e}")
            raise

    async def update_session_template(self, session_id: str, template_id: str) -> bool:
        """更新会话的模板选择"""
        try:
            client = self.client.get_service_client()
            
            result = client.table('recording_sessions')\
                .update({"template_id": template_id})\
                .eq('id', session_id)\
                .execute()
            
            if not result.data:
                logger.warning(f"更新会话模板失败，会话可能不存在: {session_id}")
                return False
            
            logger.info(f"✅ 更新会话 {session_id} 的模板为: {template_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新会话模板失败: {e}")
            raise


class TranscriptionRepository:
    """转录数据仓储"""
    
    def __init__(self):
        self.client = supabase_client
    
    async def save_transcription(self, session_id: str, content: str, language: str = "zh-CN",
                               confidence_score: Optional[float] = None,
                               segments: List[Dict[str, Any]] = None,
                               stt_model: str = "whisper",
                               word_count: Optional[int] = None) -> Transcription:
        """保存转录记录"""
        try:
            client = self.client.get_service_client()
            
            if word_count is None and content:
                word_count = len(content.split())
            
            transcription_data = {
                "session_id": session_id,
                "content": content,
                "language": language,
                "confidence_score": confidence_score,
                "segments": segments or [],
                "stt_model": stt_model,
                "word_count": word_count,
                "status": "completed",
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = client.table('transcriptions').insert(transcription_data).execute()
            
            if not result.data:
                raise Exception("保存转录记录失败")
            
            transcription_dict = result.data[0]
            # 为兼容性添加默认的stt_provider字段
            transcription_dict['stt_provider'] = 'local'
            return Transcription(**transcription_dict)
            
        except Exception as e:
            logger.error(f"保存转录记录失败: {e}")
            raise
    
    async def get_session_transcriptions(self, session_id: str) -> List[Transcription]:
        """获取会话的转录记录"""
        try:
            client = self.client.get_service_client()
            
            result = client.table('transcriptions')\
                .select('*')\
                .eq('session_id', session_id)\
                .order('created_at', desc=True)\
                .execute()
            
            return [Transcription(**trans_dict) for trans_dict in result.data]
            
        except Exception as e:
            logger.error(f"获取会话转录记录失败: {e}")
            raise

    async def update_transcription(self, transcription_id: str, content: str = None,
                                 segments: List[Dict[str, Any]] = None) -> Transcription:
        """更新转录记录"""
        try:
            client = self.client.get_service_client()
            
            update_data = {
                "updated_at": datetime.utcnow().isoformat()
            }
            
            if content is not None:
                update_data["content"] = content
                update_data["word_count"] = len(content.split())
            
            if segments is not None:
                update_data["segments"] = segments
            
            result = client.table('transcriptions')\
                .update(update_data)\
                .eq('id', transcription_id)\
                .execute()
            
            if not result.data:
                raise Exception("更新转录记录失败")
            
            transcription_dict = result.data[0]
            # 为兼容性添加默认的stt_provider字段
            transcription_dict['stt_provider'] = 'local'
            return Transcription(**transcription_dict)
            
        except Exception as e:
            logger.error(f"更新转录记录失败: {e}")
            raise

    async def update_transcription_with_reprocessed_data(self, session_id: str, content: str,
                                                       segments: List[Dict[str, Any]], 
                                                       word_count: int) -> Transcription:
        """更新会话的转录记录（用于重新处理后的数据）"""
        try:
            client = self.client.get_service_client()
            
            # 查找会话的现有转录记录
            existing_result = client.table('transcriptions')\
                .select('*')\
                .eq('session_id', session_id)\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
            
            if existing_result.data:
                # 更新现有记录
                transcription_id = existing_result.data[0]['id']
                update_data = {
                    "content": content,
                    "segments": segments,
                    "word_count": word_count,
                    "status": "completed",
                    "updated_at": datetime.utcnow().isoformat()
                }
                
                result = client.table('transcriptions')\
                    .update(update_data)\
                    .eq('id', transcription_id)\
                    .execute()
                
                if not result.data:
                    raise Exception("更新转录记录失败")
                
                transcription_dict = result.data[0]
                logger.info(f"✅ 更新现有转录记录: {transcription_id}")
            else:
                # 创建新的转录记录
                transcription_data = {
                    "session_id": session_id,
                    "content": content,
                    "segments": segments,
                    "word_count": word_count,
                    "language": "zh-CN",
                    "stt_model": "whisper",
                    "status": "completed",
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
                
                result = client.table('transcriptions')\
                    .insert(transcription_data)\
                    .execute()
                
                if not result.data:
                    raise Exception("创建转录记录失败")
                
                transcription_dict = result.data[0]
                logger.info(f"✅ 创建新转录记录: {transcription_dict['id']}")
            
            # 为兼容性添加默认的stt_provider字段
            transcription_dict['stt_provider'] = 'local'
            return Transcription(**transcription_dict)
            
        except Exception as e:
            logger.error(f"更新会话转录记录失败: {e}")
            raise

    async def update_transcription_segments(self, transcription_id: str, segments: List[Dict[str, Any]]) -> Transcription:
        """仅更新转录记录的segments字段"""
        try:
            client = self.client.get_service_client()
            
            update_data = {
                "segments": segments,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            result = client.table('transcriptions')\
                .update(update_data)\
                .eq('id', transcription_id)\
                .execute()
            
            if not result.data:
                raise Exception("更新转录segments失败")
            
            transcription_dict = result.data[0]
            # 为兼容性添加默认的stt_provider字段
            transcription_dict['stt_provider'] = 'local'
            return Transcription(**transcription_dict)
            
        except Exception as e:
            logger.error(f"更新转录segments失败: {e}")
            raise


class AISummaryRepository:
    """AI总结数据仓储"""
    
    def __init__(self):
        self.client = supabase_client
    
    async def save_ai_summary(self, session_id: str, transcription_id: str, summary: str,
                            key_points: List[str] = None, action_items: List[str] = None,
                            ai_model: str = "", ai_provider: str = "litellm",
                            processing_time_ms: Optional[int] = None,
                            token_usage: Dict[str, Any] = None,
                            cost_cents: Optional[int] = None, template_id: Optional[str] = None) -> AISummary:
        """保存AI总结"""
        try:
            client = self.client.get_service_client()
            
            # 确保数值字段是正确的类型
            if processing_time_ms is not None:
                processing_time_ms = int(float(processing_time_ms))  # Convert float to int if needed
            if cost_cents is not None:
                cost_cents = int(float(cost_cents))  # Convert float to int if needed
            
            summary_data = {
                "session_id": session_id,
                "transcription_id": transcription_id,
                "summary": summary,
                "key_points": key_points or [],
                "action_items": action_items or [],
                "ai_model": ai_model,
                "ai_provider": ai_provider,
                "status": "completed",
                "processing_time_ms": processing_time_ms,
                "token_usage": token_usage or {},
                "cost_cents": cost_cents,
                "template_id": template_id,
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = client.table('ai_summaries').insert(summary_data).execute()
            
            if not result.data:
                raise Exception("保存AI总结失败")
            
            summary_dict = result.data[0]
            return AISummary(**summary_dict)
            
        except Exception as e:
            logger.error(f"保存AI总结失败: {e}")
            raise
    
    async def get_session_summaries(self, session_id: str) -> List[AISummary]:
        """获取会话的AI总结"""
        try:
            client = self.client.get_service_client()
            
            result = client.table('ai_summaries')\
                .select('*')\
                .eq('session_id', session_id)\
                .order('created_at', desc=True)\
                .execute()
            
            return [AISummary(**summary_dict) for summary_dict in result.data]
            
        except Exception as e:
            logger.error(f"获取会话AI总结失败: {e}")
            raise

    async def get_ai_summary_by_id(self, summary_id: str) -> Optional[AISummary]:
        """根据ID获取AI总结"""
        try:
            client = self.client.get_service_client()
            
            result = client.table('ai_summaries')\
                .select('*')\
                .eq('id', summary_id)\
                .execute()
            
            if result.data:
                return AISummary(**result.data[0])
            return None
            
        except Exception as e:
            logger.error(f"获取AI总结失败: {e}")
            raise

    async def update_ai_summary(self, summary_id: str, summary: str, 
                              key_points: List[str] = None, 
                              action_items: List[str] = None) -> AISummary:
        """更新AI总结"""
        try:
            logger.info(f"🔍 Repository: 开始更新AI总结 summary_id={summary_id}")
            logger.info(f"📝 Repository: 更新数据 summary_length={len(summary)}, summary_preview='{summary[:100]}...'")
            
            client = self.client.get_service_client()
            
            update_data = {
                "summary": summary,
                "key_points": key_points or [],
                "action_items": action_items or [],
                "updated_at": datetime.utcnow().isoformat()
            }
            
            logger.info(f"📤 Repository: 执行数据库更新操作")
            
            result = client.table('ai_summaries')\
                .update(update_data)\
                .eq('id', summary_id)\
                .execute()
            
            if not result.data:
                logger.error("❌ Repository: 数据库更新返回空结果")
                raise Exception("更新AI总结失败")
            
            summary_dict = result.data[0]
            logger.info(f"✅ Repository: 数据库更新成功, 返回数据: summary_length={len(summary_dict.get('summary', ''))}")
            
            return AISummary(**summary_dict)
            
        except Exception as e:
            logger.error(f"❌ Repository: 更新AI总结失败: {e}")
            raise


class AudioFileRepository:
    """音频文件数据仓储"""
    
    def __init__(self):
        self.client = supabase_client
    
    async def save_audio_file(self, session_id: str, user_id: str, original_filename: Optional[str] = None,
                            storage_path: Optional[str] = None, public_url: Optional[str] = None,
                            file_size_bytes: Optional[int] = None,
                            duration_seconds: Optional[float] = None,
                            format: str = "mp3", sample_rate: Optional[int] = None) -> AudioFile:
        """保存音频文件记录"""
        try:
            client = self.client.get_service_client()
            
            audio_data = {
                "session_id": session_id,
                "user_id": user_id,
                "original_filename": original_filename,
                "storage_path": storage_path,
                "public_url": public_url,
                "file_size_bytes": file_size_bytes,
                "duration_seconds": duration_seconds,
                "format": format,
                "sample_rate": sample_rate,
                "channels": 1,  # 默认单声道
                "upload_status": "completed",
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = client.table('audio_files').insert(audio_data).execute()
            
            if not result.data:
                raise Exception("保存音频文件记录失败")
            
            audio_dict = result.data[0]
            return AudioFile(**audio_dict)
            
        except Exception as e:
            logger.error(f"保存音频文件记录失败: {e}")
            raise
    
    async def get_session_audio_files(self, session_id: str) -> List[AudioFile]:
        """获取会话的音频文件"""
        try:
            client = self.client.get_service_client()
            
            result = client.table('audio_files')\
                .select('*')\
                .eq('session_id', session_id)\
                .order('created_at', desc=True)\
                .execute()
            
            return [AudioFile(**audio_dict) for audio_dict in result.data]
            
        except Exception as e:
            logger.error(f"获取会话音频文件失败: {e}")
            raise
    
    async def get_audio_file_by_id(self, file_id: str) -> Optional[AudioFile]:
        """根据ID获取音频文件"""
        try:
            client = self.client.get_service_client()
            
            result = client.table('audio_files').select('*').eq('id', file_id).execute()
            
            if not result.data:
                return None
            
            audio_dict = result.data[0]
            return AudioFile(**audio_dict)
            
        except Exception as e:
            logger.error(f"获取音频文件失败: {e}")
            raise


class UserRepository:
    """用户数据仓储"""
    
    def __init__(self):
        self.client = supabase_client
    
    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户业务资料"""
        try:
            client = self.client.get_service_client()
            
            result = client.table('user_profiles').select('*').eq('user_id', user_id).execute()
            
            if not result.data:
                # 如果用户资料不存在，创建默认资料
                return await self.create_user_profile(user_id)
            
            profile_dict = result.data[0]
            return UserProfile(**profile_dict)
            
        except Exception as e:
            logger.error(f"获取用户资料失败: {e}")
            raise
    
    async def create_user_profile(self, user_id: str) -> UserProfile:
        """创建用户业务资料"""
        try:
            client = self.client.get_service_client()
            
            profile_data = {
                "user_id": user_id,
                "subscription_plan": "free",
                "subscription_status": "active",
                "quotas": {
                    "transcription_minutes": {"used": 0, "limit": 1000},
                    "ai_summary_count": {"used": 0, "limit": 100}
                },
                "preferences": {
                    "default_language": "zh-CN",
                    "auto_summary": True
                },
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = client.table('user_profiles').insert(profile_data).execute()
            
            if not result.data:
                raise Exception("创建用户资料失败")
            
            # 为新用户创建默认模板
            await self._create_default_template_for_user(user_id)
            
            profile_dict = result.data[0]
            return UserProfile(**profile_dict)
            
        except Exception as e:
            logger.error(f"创建用户资料失败: {e}")
            raise

    async def _create_default_template_for_user(self, user_id: str):
        """为新用户创建默认模板"""
        try:
            client = self.client.get_service_client()
            
            default_template = {
                "user_id": user_id,
                "name": "我的默认模板",
                "description": "您的个人默认总结模板，可以根据需要进行编辑",
                "template_content": """# 会议总结

## 基本信息
- 会议主题：根据讨论内容总结主要议题
- 参会人员：列出参与讨论的人员
- 会议时间：如果提及具体时间请注明

## 主要议题
列出本次会议讨论的主要话题，用条目形式展示

## 重要决议
总结会议中达成的重要决定和结论

## 行动项
列出需要后续执行的具体任务和责任人

## 待解决问题
记录尚未解决或需要进一步讨论的问题

## 下次会议安排
如果有提及下次会议的时间或议题，请在此记录""",
                "is_default": True,
                "is_active": True,
                "category": "会议",
                "tags": ["默认", "会议", "通用"],
                "is_system_template": False
            }
            
            result = client.table('summary_templates').insert(default_template).execute()
            
            if result.data:
                logger.info(f"为用户 {user_id} 创建了默认模板")
            else:
                logger.warning(f"为用户 {user_id} 创建默认模板失败")
            
        except Exception as e:
            logger.error(f"创建默认模板失败: {e}")
            # 不抛出异常，因为这不应该阻止用户注册
    
    async def update_user_preferences(self, user_id: str, preferences: Dict[str, Any]) -> UserProfile:
        """更新用户偏好设置"""
        try:
            client = self.client.get_service_client()
            
            # 先获取当前偏好
            current_profile = await self.get_user_profile(user_id)
            if not current_profile:
                raise Exception("用户资料不存在")
            
            # 合并偏好设置
            updated_preferences = {**current_profile.preferences, **preferences}
            
            update_data = {
                "preferences": updated_preferences,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            result = client.table('user_profiles').update(update_data).eq('user_id', user_id).execute()
            
            if not result.data:
                raise Exception("更新用户偏好失败")
            
            profile_dict = result.data[0]
            return UserProfile(**profile_dict)
            
        except Exception as e:
            logger.error(f"更新用户偏好失败: {e}")
            raise


# 仓储实例
session_repository = SessionRepository()
transcription_repository = TranscriptionRepository()
ai_summary_repository = AISummaryRepository()


class SummaryTemplateRepository:
    """总结模板数据访问层"""
    
    def __init__(self):
        logger.info("📝 模板Repository初始化")
    
    async def create_template(self, user_id: str, name: str, template_content: str, 
                            description: str = None, category: str = "会议", 
                            is_default: bool = False, is_active: bool = True,
                            tags: List[str] = None) -> Dict[str, Any]:
        """创建总结模板"""
        try:
            client = supabase_client.get_service_client()
            
            template_data = {
                "user_id": user_id,
                "name": name,
                "description": description,
                "template_content": template_content,
                "category": category,
                "is_default": is_default,
                "is_active": is_active,
                "tags": tags or []
            }
            
            result = client.table('summary_templates').insert(template_data).execute()
            
            if not result.data:
                raise Exception("创建模板失败：数据库返回空结果")
            
            return result.data[0]
            
        except Exception as e:
            logger.error(f"创建模板失败: {e}")
            raise
    
    async def get_user_templates(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的所有模板"""
        try:
            client = supabase_client.get_service_client()
            
            result = client.table('summary_templates')\
                .select('*')\
                .eq('user_id', user_id)\
                .eq('is_active', True)\
                .order('created_at', desc=True)\
                .execute()
                
            return result.data or []
            
        except Exception as e:
            logger.error(f"获取用户模板失败: {e}")
            raise

    async def get_system_templates(self) -> List[Dict[str, Any]]:
        """获取所有系统模板"""
        try:
            client = supabase_client.get_service_client()
            
            result = client.table('summary_templates')\
                .select('*')\
                .eq('is_system_template', True)\
                .eq('is_active', True)\
                .order('created_at', desc=False)\
                .execute()
                
            return result.data or []
            
        except Exception as e:
            logger.error(f"获取系统模板失败: {e}")
            raise

    async def copy_system_template_to_user(self, system_template_id: str, user_id: str) -> Dict[str, Any]:
        """将系统模板复制到用户模板中"""
        try:
            client = supabase_client.get_service_client()
            
            # 获取系统模板
            sys_template_result = client.table('summary_templates')\
                .select('*')\
                .eq('id', system_template_id)\
                .eq('is_system_template', True)\
                .single()\
                .execute()
            
            if not sys_template_result.data:
                raise Exception("系统模板不存在")
            
            sys_template = sys_template_result.data
            
            # 创建用户模板副本
            user_template_data = {
                "user_id": user_id,
                "name": sys_template['name'],
                "description": sys_template['description'],
                "template_content": sys_template['template_content'],
                "category": sys_template['category'],
                "tags": sys_template['tags'],
                "is_default": False,  # 复制的模板不设为默认
                "is_active": True,
                "is_system_template": False  # 用户模板
            }
            
            result = client.table('summary_templates').insert(user_template_data).execute()
            
            if not result.data:
                raise Exception("复制模板失败")
            
            return result.data[0]
            
        except Exception as e:
            logger.error(f"复制系统模板失败: {e}")
            raise
    
    async def get_template_by_id(self, template_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取模板"""
        try:
            client = supabase_client.get_service_client()
            
            result = client.table('summary_templates')\
                .select('*')\
                .eq('id', template_id)\
                .eq('user_id', user_id)\
                .single()\
                .execute()
                
            return result.data if result.data else None
            
        except Exception as e:
            logger.error(f"获取模板失败: {e}")
            return None
    
    async def get_default_template(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户的默认模板"""
        try:
            client = supabase_client.get_service_client()
            
            result = client.table('summary_templates')\
                .select('*')\
                .eq('user_id', user_id)\
                .eq('is_default', True)\
                .eq('is_active', True)\
                .single()\
                .execute()
                
            return result.data if result.data else None
            
        except Exception as e:
            logger.error(f"获取默认模板失败: {e}")
            return None
    
    async def update_template(self, template_id: str, user_id: str, **updates) -> Dict[str, Any]:
        """更新模板"""
        try:
            client = supabase_client.get_service_client()
            
            # 如果设置为默认模板，先取消其他默认模板
            if updates.get('is_default'):
                await client.table('summary_templates')\
                    .update({'is_default': False})\
                    .eq('user_id', user_id)\
                    .neq('id', template_id)\
                    .execute()
            
            result = client.table('summary_templates')\
                .update(updates)\
                .eq('id', template_id)\
                .eq('user_id', user_id)\
                .execute()
                
            if not result.data:
                raise Exception("更新模板失败：数据库返回空结果")
                
            return result.data[0]
            
        except Exception as e:
            logger.error(f"更新模板失败: {e}")
            raise
    
    async def delete_template(self, template_id: str, user_id: str) -> bool:
        """删除模板"""
        try:
            client = supabase_client.get_service_client()
            
            result = client.table('summary_templates')\
                .delete()\
                .eq('id', template_id)\
                .eq('user_id', user_id)\
                .execute()
                
            return True
            
        except Exception as e:
            logger.error(f"删除模板失败: {e}")
            raise
    
    async def increment_usage_count(self, template_id: str):
        """增加模板使用次数"""
        try:
            client = supabase_client.get_service_client()
            
            # 使用PostgreSQL的increment功能
            result = client.rpc('increment_template_usage', {
                'template_id': template_id
            }).execute()
            
        except Exception as e:
            logger.warning(f"更新模板使用次数失败: {e}")
            # 不抛出异常，因为这不是关键操作


summary_template_repository = SummaryTemplateRepository()
audio_file_repository = AudioFileRepository()
user_repository = UserRepository() 