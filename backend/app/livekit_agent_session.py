"""
LiveKit Agent Session 标准实现
按照官方示例的正确AgentSession方式实现
"""
import asyncio
import datetime
import json
import logging
import uuid
from typing import AsyncIterator, Dict, Any, Optional, Tuple
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

from livekit import rtc
from livekit.agents import JobContext, WorkerOptions, WorkerType, JobExecutorType, cli
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import silero
from livekit.agents.stt import STT, STTCapabilities, SpeechEvent, SpeechEventType
from livekit.agents.stt import SpeechData

from .services import audio_transcription_service
from .clients import stt_client, supabase_client
from .repositories import session_repository
from .models import User

# 加载环境变量
load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / '.env')

logger = logging.getLogger(__name__)


class IntrascribeSTTService(STT):
    """
    继承livekit.agent.stt.STT，实现对应的接口
    复用现有的全局STT客户端，避免重复初始化
    """
    
    def __init__(self):
        capabilities = STTCapabilities(
            streaming=False,
            interim_results=False,
        )
        super().__init__(capabilities=capabilities)
        self.session_id = None
        self._audio_buffer = bytearray()
        self._buffer_threshold = 16000 * 2  # 2秒的音频数据
        self._all_audio_data = bytearray()  # 保存所有音频数据用于生成文件
        # 复用全局STT客户端，不重新创建
        logger.info("🔄 复用现有STT客户端，避免重复初始化")
    
    def set_session_id(self, session_id: str):
        """设置当前会话ID"""
        self.session_id = session_id
        logger.info(f"🎯 STT服务设置会话ID: {session_id}")
    
    def get_recorded_audio(self) -> tuple[bytes, int]:
        """获取录制的音频数据"""
        return bytes(self._all_audio_data), 24000  # LiveKit默认采样率
    
    async def flush_remaining_audio(self):
        """处理剩余的音频缓冲区"""
        try:
            if len(self._audio_buffer) > 0 and self.session_id:
                logger.info(f"🔄 处理剩余音频缓冲区: {len(self._audio_buffer)} 字节")
                
                # 转换缓冲区数据为numpy数组
                buffered_audio = np.frombuffer(bytes(self._audio_buffer), dtype=np.int16)
                
                # 调用转录服务处理剩余音频
                audio_tuple = (24000, buffered_audio.reshape(1, -1))
                
                from .services import audio_transcription_service
                transcription_result = await audio_transcription_service.transcribe_audio(
                    audio_tuple, 
                    self.session_id
                )
                
                if transcription_result and transcription_result.get('text'):
                    logger.info(f"✅ 剩余音频转录成功: {transcription_result['text']}")
                
                # 清空缓冲区
                self._audio_buffer.clear()
                
        except Exception as e:
            logger.error(f"❌ 处理剩余音频缓冲区失败: {e}")
    
    async def _recognize_impl(
        self, 
        buffer: rtc.AudioFrame,
        *,
        language: Optional[str] = None,
        conn_options=None,
    ):
        """实现STT识别逻辑，复用AudioTranscriptionService"""
        try:
            if not self.session_id:
                logger.warning("⚠️ 会话ID未设置，跳过转录")
                return SpeechEvent(
                    type=SpeechEventType.FINAL_TRANSCRIPT,
                    alternatives=[]
                )
            
            # 转换音频数据为numpy数组
            audio_data = np.frombuffer(buffer.data, dtype=np.int16)
            sample_rate = buffer.sample_rate
            
            # 保存所有音频数据用于最终生成音频文件
            self._all_audio_data.extend(audio_data.tobytes())
            
            # 缓冲音频数据（复制数据避免引用问题）
            self._audio_buffer.extend(audio_data.tobytes())
            
            # 当缓冲区达到阈值时进行转录
            if len(self._audio_buffer) >= self._buffer_threshold:
                # 转换缓冲区数据为numpy数组
                buffered_audio = np.frombuffer(bytes(self._audio_buffer), dtype=np.int16)
                
                # 重置缓冲区
                self._audio_buffer.clear()
                
                # 调用现有的转录服务（复用全局实例）
                audio_tuple = (sample_rate, audio_data.reshape(1, -1))
                
                logger.info(f"🎵 处理音频: 采样率={sample_rate}, 数据长度={len(audio_data)}")
                
                transcription_result = await audio_transcription_service.transcribe_audio(
                    audio_tuple, 
                    self.session_id
                )
                
                if transcription_result and transcription_result.get('text'):
                    logger.info(f"✅ 转录成功: {transcription_result}")
                    # 返回STT事件，alternatives需要是SpeechData对象
                    speech_data = SpeechData(
                        language="zh-CN",  # 必需的第一个参数
                        text=transcription_result['text'],  # 必需的第二个参数
                        confidence=1.0,  # 设置置信度
                        start_time=0.0,  # 开始时间
                        end_time=1.0     # 结束时间
                    )
                    return SpeechEvent(
                        type=SpeechEventType.FINAL_TRANSCRIPT,
                        alternatives=[speech_data]
                    )
                
        except Exception as e:
            logger.error(f"❌ STT识别失败: {e}")
        
        # 返回空的STT事件而不是None
        return SpeechEvent(
            type=SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[]
        )
    

async def get_user_id_from_room(room: rtc.Room) -> Optional[str]:
    """从房间参与者信息中提取用户ID"""
    try:
        # 等待参与者连接
        await asyncio.sleep(1)
        
        # 检查远程参与者
        for participant in room.remote_participants.values():
            if participant.identity and participant.identity.startswith("intrascribe_user_"):
                # 从参与者identity中提取用户ID
                user_part = participant.identity.replace("intrascribe_user_", "")
                logger.info(f"🔍 从参与者identity提取用户标识: {user_part}")
                
                # 这里可能需要进一步解析或查询真实的user_id
                # 暂时返回None，使用临时会话
                return None
                
        # 检查本地参与者
        if room.local_participant and room.local_participant.identity:
            logger.info(f"🔍 本地参与者: {room.local_participant.identity}")
            
        logger.warning("⚠️ 无法从房间中提取用户ID")
        return None
        
    except Exception as e:
        logger.error(f"❌ 提取用户ID失败: {e}")
        return None


async def create_session_record(session_id: str, user_id: Optional[str], title: str) -> bool:
    """使用现有的session_repository创建会话记录"""
    try:
        # 如果没有用户ID，使用匿名用户
        if not user_id:
            user_id = await get_or_create_anonymous_user()
        
        # 使用现有的session_repository，传入自定义session_id
        session = await session_repository.create_session(
            user_id=user_id,
            title=title,
            language="zh-CN",
            stt_model="local_funasr",
            session_id=session_id  # 传入我们生成的UUID
        )
        
        logger.info(f"✅ 使用repository创建会话记录成功: {session.id}")
        
        # 创建成功后，立即更新状态为recording
        from .models import SessionStatus
        await session_repository.update_session_status(
            session_id=session_id,
            status=SessionStatus.RECORDING
        )
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 使用repository创建会话记录失败: {e}")
        return False


async def get_or_create_anonymous_user() -> str:
    """获取或创建匿名用户"""
    try:
        client = supabase_client.get_service_client()
        
        # 尝试查找匿名用户
        anonymous_result = client.table('users').select('id').eq('email', 'anonymous@intrascribe.local').execute()
        if anonymous_result.data:
            return anonymous_result.data[0]['id']
        
        # 创建匿名用户
        anonymous_user = {
            "email": "anonymous@intrascribe.local",
            "username": "anonymous_user",
            "password_hash": "no_password",
            "full_name": "匿名用户",
            "is_active": True,
            "is_verified": True
        }
        anonymous_result = client.table('users').insert(anonymous_user).execute()
        if anonymous_result.data:
            logger.info("✅ 创建匿名用户成功")
            return anonymous_result.data[0]['id']
        else:
            raise Exception("创建匿名用户失败")
            
    except Exception as e:
        logger.error(f"❌ 获取或创建匿名用户失败: {e}")
        raise


async def update_session_status(session_id: str, status: str) -> bool:
    """使用现有的session_repository更新会话状态"""
    try:
        from .models import SessionStatus
        
        # 将字符串状态转换为SessionStatus枚举
        status_mapping = {
            "recording": SessionStatus.RECORDING,
            "completed": SessionStatus.COMPLETED,
            "failed": SessionStatus.CANCELLED  # 使用CANCELLED作为失败状态
        }
        
        session_status = status_mapping.get(status, SessionStatus.COMPLETED)
        
        # 使用现有的session_repository方法
        await session_repository.update_session_status(
            session_id=session_id,
            status=session_status,
            ended_at=datetime.datetime.utcnow() if status == "completed" else None
        )
        
        logger.info(f"✅ 使用repository更新会话状态成功: {session_id} -> {status}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 使用repository更新会话状态失败: {e}")
        return False


async def entrypoint(ctx: JobContext):
    """LiveKit Agent入口点 - 参考官方示例的正确AgentSession实现"""
    logger.info("🚀 Intrascribe LiveKit Agent 启动 (官方标准AgentSession)")
    
    # 从房间信息中提取会话ID
    session_id = extract_session_id(ctx.room)
    if not session_id:
        logger.error("❌ 无法从房间名称中提取会话ID，Agent退出")
        return
    
    logger.info(f"🎯 从房间名称提取到会话ID: {session_id}")
    
    # 验证会话记录是否存在
    try:
        # 检查会话是否存在（不需要创建新的）
        logger.info(f"🔍 验证会话记录是否存在: {session_id}")
        # 注意：这里我们假设会话记录已经由connection-details API创建
        # 如果需要验证，可以添加repository查询
        
    except Exception as e:
        logger.error(f"❌ 验证会话记录失败: {e}")
        # 继续执行，假设会话记录存在
    
    # 创建自定义STT服务并设置会话ID
    stt_service = IntrascribeSTTService()
    stt_service.set_session_id(session_id)
    # 创建单个 AgentSession 并正确配置事件监听器
    agent_session = AgentSession()
    
    # 将stt_service保存为全局变量，便于在断开连接时访问
    global current_stt_service
    current_stt_service = stt_service
    
    # 监听转录事件，参考官方示例
    @agent_session.on("user_input_transcribed")
    def on_transcript(transcript):
        logger.info(f"🎙️ 用户语音转录: is_final={transcript.is_final}, text='{transcript.transcript}'")
        
        if transcript.is_final:
            # 构造符合设计文档的转录数据格式
            transcription_data = {
                "index": 0,  # 可以根据需要增加计数器
                "speaker": "Speaker 1",  # 实时转录暂时使用固定说话人
                "timestamp": "[00:00:00:000,00:00:00:000]",  # 可以根据实际时间计算
                "text": transcript.transcript,
                "is_final": True
            }
            
            # 发送转录数据到房间
            asyncio.create_task(send_transcription_to_room(ctx.room, transcription_data))
    
    # 启动session
    await agent_session.start(
        agent=Agent(
            instructions="You are a helpful assistant that transcribes user speech to text for Intrascribe platform.",
            stt=stt_service,  # 使用我们自定义的STT服务
            vad=silero.VAD.load(),  # 添加VAD支持非流式STT
            # llm=None,  # 不配置LLM - Agent会自动处理
            # tts=None,  # 不配置TTS - Agent会自动处理
        ),
        room=ctx.room
    )

    await ctx.connect()
    
    logger.info("✅ AgentSession 已启动并等待用户语音输入")
    
    # 添加房间断开连接监听器
    @ctx.room.on("disconnected")
    def on_room_disconnected():
        logger.info(f"🔌 房间 {ctx.room.name} 已断开连接")
        # 异步更新会话状态并保存转录数据
        async def handle_session_end():
            try:
                # 1. 处理剩余的音频缓冲区，确保所有转录都被保存
                if current_stt_service:
                    await current_stt_service.flush_remaining_audio()
                
                # 2. 保存录制的音频文件
                if current_stt_service and hasattr(current_stt_service, '_all_audio_data'):
                    await save_recorded_audio_file(session_id, current_stt_service)
                
                # 3. 保存转录数据到数据库
                await save_session_transcription_data(session_id)
                
                # 4. 更新会话状态
                await update_session_status(session_id, "completed")
                
                logger.info(f"✅ 会话 {session_id} 处理完成")
                
            except Exception as e:
                logger.error(f"❌ 处理会话结束失败: {e}")
        
        asyncio.create_task(handle_session_end())
    
    # Agent将持续运行直到房间关闭或参与者断开连接
    # LiveKit Agent框架会自动处理会话生命周期
    logger.info("🎧 Agent已准备好处理音频输入")


def extract_session_id(room: rtc.Room) -> Optional[str]:
    """从房间信息中提取会话ID"""
    try:
        # 方法1: 从房间名称中提取 (新格式: intrascribe_room_{session_id})
        room_name = room.name
        if room_name:
            if room_name.startswith("intrascribe_room_"):
                # 新格式：直接使用UUID作为会话ID
                session_id = room_name.replace("intrascribe_room_", "")
                logger.info(f"🔍 从房间名称提取会话ID: {session_id}")
                # 验证是否为有效的UUID格式
                try:
                    uuid.UUID(session_id)
                    return session_id
                except ValueError:
                    logger.warning(f"⚠️ 提取的会话ID不是有效的UUID格式: {session_id}")
                    # 继续尝试其他方法
            elif room_name.startswith("session_"):
                session_id = room_name.replace("session_", "")
                logger.info(f"🔍 从房间名称提取会话ID (旧格式): {session_id}")
                return session_id
        
        # 方法2: 从房间元数据中提取
        metadata = room.metadata
        if metadata:
            try:
                meta_dict = json.loads(metadata)
                session_id = meta_dict.get("session_id")
                if session_id:
                    logger.info(f"🔍 从房间元数据提取会话ID: {session_id}")
                    return session_id
            except json.JSONDecodeError:
                pass
        
        # 方法3: 从参与者元数据中提取
        for participant in room.remote_participants.values():
            if participant.metadata:
                try:
                    meta_dict = json.loads(participant.metadata)
                    session_id = meta_dict.get("session_id")
                    if session_id:
                        logger.info(f"🔍 从参与者元数据提取会话ID: {session_id}")
                        return session_id
                except json.JSONDecodeError:
                    continue
        
        logger.warning("⚠️ 无法从房间信息中提取会话ID")
        return None
        
    except Exception as e:
        logger.error(f"❌ 提取会话ID失败: {e}")
        return None


# 移除手动音频处理函数，现在由AgentSession自动处理


async def save_recorded_audio_file(session_id: str, stt_service: IntrascribeSTTService):
    """保存录制的音频文件"""
    try:
        import librosa
        import soundfile as sf
        import io
        
        # 获取录制的音频数据
        audio_data, sample_rate = stt_service.get_recorded_audio()
        
        if not audio_data:
            logger.warning(f"⚠️ 会话 {session_id} 没有录制音频数据")
            return
        
        # 转换为numpy数组
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        
        if len(audio_array) == 0:
            logger.warning(f"⚠️ 会话 {session_id} 音频数据为空")
            return
        
        # 计算音频时长
        duration_seconds = len(audio_array) / sample_rate
        logger.info(f"🎵 录制音频时长: {duration_seconds:.2f} 秒")
        
        # 将int16转换为float32并归一化
        audio_float = audio_array.astype(np.float32) / 32768.0
        
        # 创建临时WAV文件
        audio_io = io.BytesIO()
        sf.write(audio_io, audio_float, sample_rate, format='WAV')
        audio_io.seek(0)
        
        # 生成文件名
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"livekit_recording_{session_id[:8]}_{timestamp}.wav"
        
        # 上传到Supabase Storage
        client = supabase_client.get_service_client()
        
        # 上传文件
        upload_result = client.storage.from_("audio-files").upload(
            path=f"recordings/{filename}",
            file=audio_io.getvalue(),
            file_options={
                "content-type": "audio/wav",
                "cache-control": "3600"
            }
        )
        
        if upload_result.error:
            raise Exception(f"上传音频文件失败: {upload_result.error}")
        
        # 创建音频文件记录
        from .repositories import audio_file_repository
        audio_file = await audio_file_repository.create_audio_file(
            session_id=session_id,
            filename=filename,
            file_path=f"recordings/{filename}",
            file_size=len(audio_io.getvalue()),
            duration_seconds=int(duration_seconds),
            format="wav",
            sample_rate=sample_rate
        )
        
        logger.info(f"✅ 音频文件已保存: {audio_file.id}, 文件: {filename}")
        
    except Exception as e:
        logger.error(f"❌ 保存音频文件失败: {e}")


async def save_session_transcription_data(session_id: str):
    """保存会话的转录数据到数据库"""
    try:
        from .services import audio_transcription_service
        
        # 获取会话缓存
        cache = audio_transcription_service.cache_manager.get_session_cache(session_id)
        if not cache:
            logger.warning(f"⚠️ 未找到会话缓存: {session_id}")
            return
        
        if not cache.transcription_segments:
            logger.warning(f"⚠️ 会话 {session_id} 没有转录数据")
            return
        
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
        from .repositories import transcription_repository
        transcription = await transcription_repository.save_transcription(
            session_id=session_id,
            content=full_content,
            segments=segments_data,
            word_count=len(full_content.split()) if full_content else 0
        )
        
        logger.info(f"✅ 转录数据已保存到数据库: {transcription.id}")
        logger.info(f"📝 转录内容: {full_content[:100]}...")
        
    except Exception as e:
        logger.error(f"❌ 保存转录数据到数据库失败: {e}")


async def send_transcription_to_room(room: rtc.Room, transcription_data: Dict[str, Any]):
    """发送转录数据到房间"""
    try:
        # 将转录数据编码为字节
        data_bytes = json.dumps(transcription_data, ensure_ascii=False).encode('utf-8')
        
        # 使用简化的publish_data API发送转录数据
        await room.local_participant.publish_data(
            data_bytes,
            reliable=True,
            topic="transcription"
        )
        logger.info(f"📤 转录数据已发送: {transcription_data['text'][:50]}...")
        
    except Exception as e:
        logger.error(f"❌ 发送转录数据失败: {e}")
        # 记录详细错误信息以便调试
        import traceback
        logger.error(f"❌ 错误详情: {traceback.format_exc()}")


def main():
    """主函数 - 启动LiveKit Agent"""
    logger.info("🚀 启动 Intrascribe LiveKit Agent (官方标准AgentSession)")
    
    # 使用线程池避免重复加载STT模型，增加初始化超时
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="intrascribe-agent-session",
        job_executor_type=JobExecutorType.THREAD,  # 使用线程而不是进程
        initialize_process_timeout=60.0,  # 增加初始化超时到60秒
        num_idle_processes=0  # 不预启动进程
    ), hot_reload=False)


if __name__ == "__main__":
    main()