"""
API路由层
定义所有API端点
"""
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status, Query, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from datetime import datetime

from .schemas import (
    # 公共响应
    HealthResponse, ErrorResponse,
    # 用户相关
    UserProfileResponse, UserPreferencesRequest,
    # 会话相关
    CreateSessionRequest, CreateSessionResponse, FinalizeSessionResponse,
    SessionDetailResponse,
    # AI相关
    SummarizeRequest, SummarizeResponse, GenerateTitleRequest, GenerateTitleResponse,
    # 模板相关
    SummaryTemplateRequest, SummaryTemplateResponse,
    # 音频相关
    AudioProcessRequest, AudioUploadResponse, AudioCacheStatusResponse,
    SetCurrentSessionRequest, CurrentSessionResponse,
    # 转录相关
    TranscriptionSaveRequest, TranscriptionUpdateRequest, TranscriptionResponse,
    # AI总结相关
    AISummarySaveRequest, AISummaryResponse
)
from .dependencies import (
    get_current_user, get_current_user_from_header, get_optional_current_user,
    verify_session_ownership, AuthenticationError, BusinessLogicError
)
from .models import User, SessionStatus
from .services import (
    session_service, audio_transcription_service, user_service,
    cache_manager
)
from .repositories import (
    session_repository, transcription_repository, ai_summary_repository,
    audio_file_repository, summary_template_repository
)
from .clients import supabase_client, ai_client
from .batch_transcription import batch_transcription_service

logger = logging.getLogger(__name__)

# 创建API路由器
router = APIRouter()


# =============== 公开API (Public) ===============

@router.get("/health", response_model=HealthResponse, tags=["Public"])
async def health_check():
    """健康检查"""
    return HealthResponse()


# =============== 用户管理 (User Management) ===============

@router.get("/users/profile", response_model=UserProfileResponse, tags=["Users"])
async def get_user_profile(current_user: User = Depends(get_current_user)):
    """获取用户业务资料"""
    try:
        profile = await user_service.get_user_profile(current_user.id)
        return UserProfileResponse(
            subscription=profile.subscription,
            quotas=profile.quotas,
            preferences=profile.preferences
        )
    except BusinessLogicError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取用户资料失败: {e}")
        raise HTTPException(status_code=500, detail="获取用户资料失败")


@router.put("/users/preferences", response_model=UserProfileResponse, tags=["Users"])
async def update_user_preferences(
    request: UserPreferencesRequest,
    current_user: User = Depends(get_current_user)
):
    """更新用户偏好设置"""
    try:
        # 转换请求数据为字典格式
        preferences = request.dict(exclude_unset=True)
        
        profile = await user_service.update_user_preferences(current_user.id, preferences)
        return UserProfileResponse(
            subscription=profile.subscription,
            quotas=profile.quotas,
            preferences=profile.preferences
        )
    except BusinessLogicError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"更新用户偏好失败: {e}")
        raise HTTPException(status_code=500, detail="更新用户偏好失败")


# =============== 会话管理 (Session Management) ===============

@router.post("/sessions", response_model=CreateSessionResponse, tags=["Sessions"])
async def create_session(
    request: CreateSessionRequest,
    current_user: User = Depends(get_current_user)
):
    """创建新的录音会话"""
    try:
        session = await session_service.create_session(
            user_id=current_user.id,
            title=request.title,
            language=request.language,
            stt_model=request.stt_model
        )
        
        return CreateSessionResponse(
            session_id=session.id,
            title=session.title,
            status=session.status,
            created_at=session.created_at or datetime.utcnow(),
            language=session.language,
            usage_hint="Use this 'session_id' as 'webrtc_id' for your WebRTC connection."
        )
    except BusinessLogicError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        raise HTTPException(status_code=500, detail="创建会话失败")


# =============== AI服务 (独立调用) ===============

@router.post("/summarize", response_model=SummarizeResponse, tags=["AI"])
async def summarize_transcription(
    request: SummarizeRequest,
    current_user: User = Depends(get_current_user)
):
    """生成AI总结"""
    try:
        summary, metadata = await ai_client.generate_summary(request.transcription)
        
        return SummarizeResponse(
            summary=summary,
            metadata=metadata
        )
    except Exception as e:
        logger.error(f"生成AI总结失败: {e}")
        raise HTTPException(status_code=500, detail="生成AI总结失败")


@router.post("/generate-title", response_model=GenerateTitleResponse, tags=["AI"])
async def generate_title(
    request: GenerateTitleRequest,
    current_user: User = Depends(get_current_user)
):
    """生成AI标题"""
    try:
        title, metadata = await ai_client.generate_title(request.transcription, request.summary)
        
        return GenerateTitleResponse(
            title=title,
            metadata=metadata
        )
    except Exception as e:
        logger.error(f"生成AI标题失败: {e}")
        raise HTTPException(status_code=500, detail="生成AI标题失败")


# =============== 模板管理 (Template Management) ===============

@router.post("/templates", response_model=SummaryTemplateResponse, tags=["Templates"])
async def create_template(
    request: SummaryTemplateRequest,
    current_user: User = Depends(get_current_user)
):
    """创建总结模板"""
    try:
        template = await summary_template_repository.create_template(
            user_id=current_user.id,
            name=request.name,
            description=request.description,
            template_content=request.template_content,
            category=request.category,
            is_default=request.is_default,
            is_active=request.is_active,
            tags=request.tags
        )
        
        return SummaryTemplateResponse(**template)
    except Exception as e:
        logger.error(f"创建模板失败: {e}")
        raise HTTPException(status_code=500, detail="创建模板失败")


@router.get("/templates", tags=["Templates"])
async def get_user_templates(
    current_user: User = Depends(get_current_user)
):
    """获取用户的所有模板"""
    try:
        templates = await summary_template_repository.get_user_templates(current_user.id)
        return [SummaryTemplateResponse(**template) for template in templates]
    except Exception as e:
        logger.error(f"获取模板列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取模板列表失败")


@router.get("/templates/{template_id}", response_model=SummaryTemplateResponse, tags=["Templates"])
async def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取指定模板"""
    try:
        template = await summary_template_repository.get_template_by_id(template_id, current_user.id)
        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")
        
        return SummaryTemplateResponse(**template)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模板失败: {e}")
        raise HTTPException(status_code=500, detail="获取模板失败")


@router.put("/templates/{template_id}", response_model=SummaryTemplateResponse, tags=["Templates"])
async def update_template(
    template_id: str,
    request: SummaryTemplateRequest,
    current_user: User = Depends(get_current_user)
):
    """更新模板"""
    try:
        updates = request.dict(exclude_unset=True)
        template = await summary_template_repository.update_template(
            template_id=template_id,
            user_id=current_user.id,
            **updates
        )
        
        return SummaryTemplateResponse(**template)
    except Exception as e:
        logger.error(f"更新模板失败: {e}")
        raise HTTPException(status_code=500, detail="更新模板失败")


@router.delete("/templates/{template_id}", tags=["Templates"])
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_user)
):
    """删除模板"""
    try:
        await summary_template_repository.delete_template(template_id, current_user.id)
        return {"message": "模板删除成功", "template_id": template_id}
    except Exception as e:
        logger.error(f"删除模板失败: {e}")
        raise HTTPException(status_code=500, detail="删除模板失败")


@router.get("/templates/system", tags=["Templates"])
async def get_system_templates(
    current_user: User = Depends(get_current_user)
):
    """获取系统模板列表"""
    try:
        templates = await summary_template_repository.get_system_templates()
        return [SummaryTemplateResponse(**template) for template in templates]
    except Exception as e:
        logger.error(f"获取系统模板失败: {e}")
        raise HTTPException(status_code=500, detail="获取系统模板失败")


@router.post("/templates/system/{system_template_id}/copy", response_model=SummaryTemplateResponse, tags=["Templates"])
async def copy_system_template(
    system_template_id: str,
    current_user: User = Depends(get_current_user)
):
    """将系统模板复制到用户模板中"""
    try:
        template = await summary_template_repository.copy_system_template_to_user(
            system_template_id, current_user.id
        )
        return SummaryTemplateResponse(**template)
    except Exception as e:
        logger.error(f"复制系统模板失败: {e}")
        raise HTTPException(status_code=500, detail="复制系统模板失败")


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse, tags=["Sessions"])
async def get_session_detail(
    session_id: str = Depends(verify_session_ownership),
    current_user: User = Depends(get_current_user)
):
    """获取会话详情"""
    try:
        session = await session_service.get_session(session_id, current_user.id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        # 获取关联数据
        transcriptions = await transcription_repository.get_session_transcriptions(session_id)
        summaries = await ai_summary_repository.get_session_summaries(session_id)
        audio_files = await audio_file_repository.get_session_audio_files(session_id)
        
        return SessionDetailResponse(
            id=session.id,
            title=session.title,
            status=session.status,
            created_at=session.created_at or datetime.utcnow(),
            language=session.language,
            duration_seconds=session.duration_seconds,
            transcriptions=[{
                "id": t.id,
                "content": t.content,
                "segments": t.segments,
                "word_count": t.word_count,
                "status": t.status,
                "created_at": t.created_at
            } for t in transcriptions],
            summaries=[{
                "id": s.id,
                "summary": s.summary,
                "key_points": s.key_points,
                "status": s.status,
                "created_at": s.created_at
            } for s in summaries],
            audio_files=[{
                "id": af.id,
                "original_filename": af.original_filename,
                "public_url": af.public_url,
                "duration_seconds": af.duration_seconds,
                "format": af.format,
                "upload_status": af.upload_status,
                "created_at": af.created_at
            } for af in audio_files]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话详情失败: {e}")
        raise HTTPException(status_code=500, detail="获取会话详情失败")


@router.post("/sessions/{session_id}/finalize", response_model=FinalizeSessionResponse, tags=["Sessions"])
async def finalize_session(
    session_id: str = Depends(verify_session_ownership),
    current_user: User = Depends(get_current_user)
):
    """结束并整理会话"""
    try:
        final_data = await session_service.finalize_session(session_id, current_user.id)
        
        return FinalizeSessionResponse(
            message="Session finalized successfully.",
            session_id=session_id,
            status=SessionStatus.COMPLETED,
            final_data=final_data
        )
    except BusinessLogicError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"结束会话失败: {e}")
        raise HTTPException(status_code=500, detail="结束会话失败")


@router.post("/sessions/{session_id}/retranscribe", tags=["Sessions"])
async def retranscribe_session(
    session_id: str = Depends(verify_session_ownership),
    current_user: User = Depends(get_current_user)
):
    """重新转录会话 - 复用录音结束后的重新处理逻辑"""
    try:
        # 验证会话状态
        session = await session_repository.get_session_by_id(session_id, current_user.id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        if session.status != SessionStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="只有已完成的会话才能重新转录")
        
        # 获取会话的音频文件
        audio_files = await audio_file_repository.get_session_audio_files(session_id)
        if not audio_files:
            raise HTTPException(status_code=400, detail="该会话没有音频文件，无法重新转录")
        
        # 获取第一个音频文件（通常会话只有一个音频文件）
        audio_file = audio_files[0]
        
        logger.info(f"🔄 开始重新转录会话: {session_id}, 音频文件: {audio_file.id}")
        
        # 更新会话状态为processing
        await session_repository.update_session_status(
            session_id=session_id,
            status=SessionStatus.PROCESSING
        )
        
        # 从Supabase Storage下载音频文件
        try:
            client = supabase_client.get_service_client()
            
            # 从storage中下载文件 - 使用正确的桶名称
            download_result = client.storage.from_("audio-recordings").download(audio_file.storage_path)
            
            if not download_result:
                raise Exception("无法下载音频文件")
            
            audio_data = download_result
            
            # 异步触发重新处理 - 复用finalize中的重新处理逻辑
            import asyncio
            asyncio.create_task(
                session_service._reprocess_session_with_audio_data(
                    session_id=session_id,
                    user_id=current_user.id,
                    audio_data=audio_data,
                    audio_file_id=audio_file.id
                )
            )
            
            return {
                "success": True,
                "message": "重新转录已开始，请等待处理完成",
                "session_id": session_id,
                "status": "processing"
            }
            
        except Exception as storage_error:
            # 恢复会话状态
            await session_repository.update_session_status(
                session_id=session_id,
                status=SessionStatus.COMPLETED
            )
            logger.error(f"下载音频文件失败: {storage_error}")
            raise HTTPException(status_code=500, detail=f"下载音频文件失败: {str(storage_error)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新转录失败: {e}")
        # 确保会话状态不会卡在processing
        try:
            await session_repository.update_session_status(
                session_id=session_id,
                status=SessionStatus.COMPLETED
            )
        except:
            pass
        raise HTTPException(status_code=500, detail=f"重新转录失败: {str(e)}")

@router.post("/sessions/{session_id}/rename-speaker", tags=["Sessions"])
async def rename_speaker(
    session_id: str,
    request: dict,
    current_user: User = Depends(get_current_user),
    verified_session_id: str = Depends(verify_session_ownership)
):
    """重命名会话中的说话人"""
    try:
        old_speaker = request.get("oldSpeaker")
        new_speaker = request.get("newSpeaker")
        
        logger.info(f"🔍 重命名说话人请求: session_id={session_id}, old_speaker='{old_speaker}', new_speaker='{new_speaker}'")
        
        if not old_speaker or not new_speaker:
            raise HTTPException(status_code=400, detail="缺少必要参数: oldSpeaker 和 newSpeaker")
        
        if old_speaker == new_speaker:
            raise HTTPException(status_code=400, detail="新旧说话人名称相同")
        
        # 获取会话的转录数据
        transcriptions = await transcription_repository.get_session_transcriptions(session_id)
        if not transcriptions:
            logger.error(f"❌ 会话无转录数据: session_id={session_id}")
            raise HTTPException(status_code=404, detail="会话无转录数据")
        
        logger.info(f"📊 找到 {len(transcriptions)} 个转录记录")
        
        # 更新每个转录中的说话人名称
        updated_count = 0
        for i, transcription in enumerate(transcriptions):
            logger.info(f"🔍 检查转录记录 {i+1}: id={transcription.id}")
            
            if not transcription.segments:
                logger.info(f"⚠️ 转录记录 {i+1} 没有segments数据")
                continue
                
            if not isinstance(transcription.segments, list):
                logger.info(f"⚠️ 转录记录 {i+1} 的segments不是列表格式: type={type(transcription.segments)}")
                continue
            
            logger.info(f"📊 转录记录 {i+1} 包含 {len(transcription.segments)} 个片段")
            
            segments_updated = False
            updated_segments = []
            
            for j, segment in enumerate(transcription.segments):
                # 处理TranscriptionSegment模型对象
                if hasattr(segment, 'speaker') and hasattr(segment, 'text'):
                    # 是TranscriptionSegment对象
                    segment_speaker = segment.speaker
                    segment_text = segment.text[:50] if segment.text else ""
                    logger.info(f"🔍 片段 {j+1} (模型对象): speaker='{segment_speaker}', text='{segment_text}...'")
                    
                    if segment_speaker == old_speaker:
                        logger.info(f"✅ 找到匹配的片段 {j+1}, 将 '{old_speaker}' 更新为 '{new_speaker}'")
                        # 创建新的segment字典，更新speaker
                        updated_segment = {
                            "index": segment.index,
                            "speaker": new_speaker,
                            "start_time": segment.start_time,
                            "end_time": segment.end_time,
                            "text": segment.text,
                            "confidence_score": segment.confidence_score,
                            "is_final": segment.is_final
                        }
                        updated_segments.append(updated_segment)
                        segments_updated = True
                        updated_count += 1
                    else:
                        # 保持原样，转换为字典格式
                        updated_segment = {
                            "index": segment.index,
                            "speaker": segment.speaker,
                            "start_time": segment.start_time,
                            "end_time": segment.end_time,
                            "text": segment.text,
                            "confidence_score": segment.confidence_score,
                            "is_final": segment.is_final
                        }
                        updated_segments.append(updated_segment)
                elif isinstance(segment, dict):
                    # 是字典格式
                    segment_speaker = segment.get("speaker")
                    segment_text = segment.get("text", "")[:50]
                    logger.info(f"🔍 片段 {j+1} (字典格式): speaker='{segment_speaker}', text='{segment_text}...'")
                    
                    if segment_speaker == old_speaker:
                        logger.info(f"✅ 找到匹配的片段 {j+1}, 将 '{old_speaker}' 更新为 '{new_speaker}'")
                        segment["speaker"] = new_speaker
                        segments_updated = True
                        updated_count += 1
                    updated_segments.append(segment)
                else:
                    logger.info(f"⚠️ 片段 {j+1} 格式未知: type={type(segment)}")
                    updated_segments.append(segment)
            
            # 如果该转录的segments有更新，则保存
            if segments_updated:
                logger.info(f"💾 保存转录记录 {i+1} 的更新: id={transcription.id}")
                await transcription_repository.update_transcription_segments(
                    transcription.id, updated_segments
                )
            else:
                logger.info(f"ℹ️ 转录记录 {i+1} 无需更新")
        
        logger.info(f"✅ 说话人重命名成功: {old_speaker} -> {new_speaker}, 更新了 {updated_count} 个片段")
        
        return {
            "success": True,
            "message": f"说话人重命名成功: {old_speaker} -> {new_speaker}",
            "session_id": session_id,
            "updated_segments": updated_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重命名说话人失败: {e}")
        raise HTTPException(status_code=500, detail=f"重命名说话人失败: {str(e)}")



@router.delete("/sessions/{session_id}", tags=["Sessions"])
async def delete_session(
    session_id: str = Depends(verify_session_ownership),
    current_user: User = Depends(get_current_user)
):
    """删除会话及其关联的音频文件"""
    try:
        result = await session_service.delete_session(session_id, current_user.id)
        
        if result:
            return {
                "message": "会话删除成功",
                "session_id": session_id,
                "deleted": True
            }
        else:
            raise HTTPException(status_code=404, detail="会话不存在或已被删除")
    except BusinessLogicError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        raise HTTPException(status_code=500, detail="删除会话失败")


@router.put("/sessions/{session_id}/template", tags=["Sessions"])
async def update_session_template(
    request: dict,
    session_id: str = Depends(verify_session_ownership),
    current_user: User = Depends(get_current_user)
):
    """更新会话的模板选择"""
    try:
        template_id = request.get("template_id", "")
        logger.info(f"更新会话 {session_id} 的模板选择为: {template_id}")
        
        # 验证模板是否存在（如果不为空）
        if template_id:
            template = await summary_template_repository.get_template_by_id(template_id, current_user.id)
            if not template:
                raise HTTPException(status_code=404, detail="指定的模板不存在")
        
        # 更新会话模板
        await session_repository.update_session_template(session_id, template_id)
        
        return {
            "message": "会话模板更新成功",
            "session_id": session_id,
            "template_id": template_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新会话模板失败: {e}")
        raise HTTPException(status_code=500, detail="更新会话模板失败")


@router.post("/sessions/{session_id}/summarize", tags=["Sessions"])
async def generate_session_summary(
    session_id: str = Depends(verify_session_ownership),
    current_user: User = Depends(get_current_user),
    force: bool = Query(False, description="强制重新生成总结"),
    template_id: Optional[str] = Query(None, description="使用的模板ID")
):
    """为会话生成AI总结"""
    try:
        # 获取会话的转录内容
        transcriptions = await transcription_repository.get_session_transcriptions(session_id)
        if not transcriptions:
            raise HTTPException(status_code=400, detail="该会话没有转录内容")
        
        # 合并所有转录内容
        full_transcription = " ".join(t.content for t in transcriptions)
        
        # 打印转录内容长度
        logger.info(f"转录内容长度: {len(full_transcription)}")

        # 检查是否已有总结
        existing_summaries = await ai_summary_repository.get_session_summaries(session_id)
        if existing_summaries and not force:
            # 返回现有总结
            summary = existing_summaries[0]
            return {
                "id": summary.id,
                "summary": summary.summary,
                "key_points": summary.key_points,
                "status": summary.status,
                "message": "使用现有总结，如需重新生成请使用 force=true"
            }
        
        # 获取模板内容
        template_content = None
        if template_id:
            template = await summary_template_repository.get_template_by_id(template_id, current_user.id)
            if template:
                template_content = template['template_content']
                # 增加模板使用次数
                await summary_template_repository.increment_usage_count(template_id)
            else:
                logger.warning(f"指定的模板不存在或无权访问: {template_id}")
        elif not template_id:
            # 如果没有指定模板，尝试使用默认模板
            default_template = await summary_template_repository.get_default_template(current_user.id)
            if default_template:
                template_content = default_template['template_content']
                template_id = default_template['id']
                # 增加模板使用次数
                await summary_template_repository.increment_usage_count(template_id)
        
        # 生成新的AI总结
        summary_text, metadata = await ai_client.generate_summary(full_transcription, template_content)
        
        # 保存总结到数据库
        summary = await ai_summary_repository.save_ai_summary(
            session_id=session_id,
            transcription_id=transcriptions[0].id if transcriptions else None,
            summary=summary_text,
            key_points=[],  # 可以后续扩展提取关键点
            action_items=[],
            ai_model=metadata.get("model_used", "unknown"),
            ai_provider="litellm",
            processing_time_ms=int(metadata.get("total_processing_time", 0)),  # 确保是整数
            token_usage=metadata.get("token_usage", {}),
            cost_cents=int(metadata.get("cost_cents", 0)),  # 确保是整数
            template_id=template_id
        )
        
        return {
            "id": summary.id,
            "summary": summary.summary,
            "key_points": summary.key_points,
            "status": summary.status,
            "message": "AI总结生成完成"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成会话总结失败: {e}")
        raise HTTPException(status_code=500, detail="生成会话总结失败")


@router.get("/sessions/{session_id}/audio_files", tags=["Sessions"])
async def get_session_audio_files(
    session_id: str,
    current_user: User = Depends(get_current_user_from_header)
):
    """获取会话的音频文件列表"""
    try:
        # 验证会话所有权
        client = supabase_client.get_service_client()
        result = client.table('recording_sessions').select('user_id').eq('id', session_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        session_user_id = result.data[0]['user_id']
        if session_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问此会话")
        
        audio_files = await audio_file_repository.get_session_audio_files(session_id)
        return [
            {
                "id": af.id,
                "original_filename": af.original_filename,
                "public_url": af.public_url,
                "file_size_bytes": af.file_size_bytes,
                "duration_seconds": af.duration_seconds,
                "format": af.format,
                "upload_status": af.upload_status,
                "created_at": af.created_at
            }
            for af in audio_files
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话音频文件失败: {e}")
        raise HTTPException(status_code=500, detail="获取会话音频文件失败")


@router.get("/sessions/{session_id}/audio_files/{file_id}", tags=["Sessions"])
async def get_audio_file_detail(
    file_id: str,
    session_id: str,
    current_user: User = Depends(get_current_user_from_header)
):
    """获取单个音频文件详情"""
    try:
        # 验证会话所有权
        client = supabase_client.get_service_client()
        result = client.table('recording_sessions').select('user_id').eq('id', session_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        session_user_id = result.data[0]['user_id']
        if session_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问此会话")
        
        audio_file = await audio_file_repository.get_audio_file_by_id(file_id)
        if not audio_file or audio_file.session_id != session_id:
            raise HTTPException(status_code=404, detail="音频文件不存在")
        
        return {
            "id": audio_file.id,
            "session_id": audio_file.session_id,
            "original_filename": audio_file.original_filename,
            "public_url": audio_file.public_url,
            "file_size_bytes": audio_file.file_size_bytes,
            "duration_seconds": audio_file.duration_seconds,
            "format": audio_file.format,
            "sample_rate": audio_file.sample_rate,
            "channels": audio_file.channels,
            "upload_status": audio_file.upload_status,
            "created_at": audio_file.created_at
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取音频文件详情失败: {e}")
        raise HTTPException(status_code=500, detail="获取音频文件详情失败")


# =============== 转录相关API ===============

@router.post("/transcriptions", response_model=TranscriptionResponse, tags=["Transcriptions"])
async def save_transcription(
    request: TranscriptionSaveRequest,
    current_user: User = Depends(get_current_user_from_header)
):
    """保存转录记录"""
    try:
        # 验证用户对会话的所有权
        session = await session_repository.get_session_by_id(request.session_id, current_user.id)
        if not session:
            raise HTTPException(status_code=403, detail="无权访问此会话")
        
        transcription = await transcription_repository.save_transcription(
            session_id=request.session_id,
            content=request.content,
            language=request.language,
            confidence_score=request.confidence_score,
            segments=request.segments,
            stt_model=request.stt_model,
            word_count=request.word_count
        )
        
        return TranscriptionResponse(
            id=transcription.id,
            session_id=transcription.session_id,
            content=transcription.content,
            language=transcription.language,
            status=transcription.status,
            word_count=transcription.word_count,
            created_at=transcription.created_at or datetime.utcnow()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"保存转录记录失败: {e}")
        raise HTTPException(status_code=500, detail="保存转录记录失败")


@router.put("/transcriptions/{transcription_id}", response_model=TranscriptionResponse, tags=["Transcriptions"])
async def update_transcription(
    transcription_id: str,
    request: TranscriptionUpdateRequest,
    current_user: User = Depends(get_current_user_from_header)
):
    """更新转录记录"""
    try:
        logger.info(f"🔍 收到更新转录请求: transcription_id={transcription_id}, user_id={current_user.id}")
        
        # 获取用户的所有会话来验证权限
        user_sessions = await session_repository.get_user_sessions(current_user.id)
        existing_transcription = None
        
        # 找到对应的转录记录并验证权限
        for session in user_sessions:
            session_transcriptions = await transcription_repository.get_session_transcriptions(session.id)
            for trans in session_transcriptions:
                if trans.id == transcription_id:
                    existing_transcription = trans
                    break
            if existing_transcription:
                break
        
        if not existing_transcription:
            raise HTTPException(status_code=404, detail="转录记录不存在或无权访问")
        
        # 从segments重新构建content
        updated_content = " ".join(segment.get("text", "") for segment in request.segments if segment.get("text"))
        
        logger.info(f"📝 更新转录内容: 原长度={len(existing_transcription.content)}, 新长度={len(updated_content)}")
        
        # 更新转录记录
        updated_transcription = await transcription_repository.update_transcription(
            transcription_id=transcription_id,
            content=updated_content,
            segments=request.segments
        )
        
        logger.info(f"✅ 转录记录更新成功: transcription_id={transcription_id}")
        
        return TranscriptionResponse(
            id=updated_transcription.id,
            session_id=updated_transcription.session_id,
            content=updated_transcription.content,
            language=updated_transcription.language,
            status=updated_transcription.status,
            word_count=updated_transcription.word_count,
            created_at=updated_transcription.created_at or datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 更新转录记录失败: {e}")
        raise HTTPException(status_code=500, detail="更新转录记录失败")


# =============== AI总结相关API ===============

@router.post("/save_ai_summaries", response_model=AISummaryResponse, tags=["Save AI Summaries"])
async def save_ai_summary(
    request: AISummarySaveRequest,
    current_user: User = Depends(get_current_user_from_header)
):
    """保存AI总结"""
    try:
        # 验证用户对会话的所有权
        session = await session_repository.get_session_by_id(request.session_id, current_user.id)
        if not session:
            raise HTTPException(status_code=403, detail="无权访问此会话")
        
        summary = await ai_summary_repository.save_ai_summary(
            session_id=request.session_id,
            transcription_id=request.transcription_id,
            summary=request.summary,
            key_points=request.key_points,
            action_items=request.action_items,
            ai_model=request.ai_model,
            ai_provider=request.ai_provider,
            processing_time_ms=request.processing_time_ms,
            token_usage=request.token_usage,
            cost_cents=request.cost_cents
        )
        
        return AISummaryResponse(
            id=summary.id,
            session_id=summary.session_id,
            summary=summary.summary,
            key_points=summary.key_points,
            status=summary.status,
            created_at=summary.created_at or datetime.utcnow()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"保存AI总结失败: {e}")
        raise HTTPException(status_code=500, detail="保存AI总结失败")


@router.put("/update_ai_summaries/{summary_id}", response_model=AISummaryResponse, tags=["AI Summaries"])
async def update_ai_summary(
    summary_id: str,
    request: AISummarySaveRequest,
    current_user: User = Depends(get_current_user_from_header)
):
    """更新AI总结"""
    try:
        logger.info(f"🔍 收到更新AI总结请求: summary_id={summary_id}, user_id={current_user.id}")
        logger.info(f"📝 请求数据: {request.dict()}")
        
        # 验证总结内容不为空
        if not request.summary or not request.summary.strip():
            logger.error(f"❌ 总结内容为空: summary='{request.summary}'")
            raise HTTPException(status_code=400, detail="总结内容不能为空")
        
        # 验证用户对会话的所有权
        session = await session_repository.get_session_by_id(request.session_id, current_user.id)
        if not session:
            logger.error(f"❌ 会话不存在或用户无权访问: session_id={request.session_id}, user_id={current_user.id}")
            raise HTTPException(status_code=403, detail="无权访问此会话")

        # 验证AI总结存在并属于该会话
        existing_summary = await ai_summary_repository.get_ai_summary_by_id(summary_id)
        if not existing_summary:
            logger.error(f"❌ AI总结不存在: summary_id={summary_id}")
            raise HTTPException(status_code=404, detail="AI总结不存在")
        
        if existing_summary.session_id != request.session_id:
            logger.error(f"❌ AI总结不属于该会话: summary_id={summary_id}, expected_session={request.session_id}, actual_session={existing_summary.session_id}")
            raise HTTPException(status_code=403, detail="无权访问此AI总结")

        logger.info(f"📝 更新前的总结内容: '{existing_summary.summary[:100]}...'")
        logger.info(f"📝 更新后的总结内容: '{request.summary[:100]}...'")

        # 更新AI总结
        updated_summary = await ai_summary_repository.update_ai_summary(
            summary_id=summary_id,
            summary=request.summary,
            key_points=request.key_points,
            action_items=request.action_items
        )
        
        logger.info(f"✅ AI总结更新成功: summary_id={summary_id}")
        
        return AISummaryResponse(
            id=updated_summary.id,
            session_id=updated_summary.session_id,
            summary=updated_summary.summary,
            key_points=updated_summary.key_points,
            status=updated_summary.status,
            created_at=updated_summary.created_at or datetime.utcnow()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 更新AI总结失败: {e}")
        raise HTTPException(status_code=500, detail="更新AI总结失败")


# =============== 音频处理和缓存管理API ===============

@router.post("/audio/process", response_model=AudioUploadResponse, tags=["Audio"])
async def process_audio(
    request: AudioProcessRequest,
    current_user: User = Depends(get_current_user_from_header)
):
    """处理音频（兼容性接口）"""
    try:
        # 验证用户对会话的所有权
        session = await session_repository.get_session_by_id(request.session_id, current_user.id)
        if not session:
            raise HTTPException(status_code=403, detail="无权访问此会话")
        
        # 这个接口主要用于兼容性，实际的音频处理在finalize_session中进行
        return AudioUploadResponse(
            success=True,
            message="请使用 POST /sessions/{session_id}/finalize 来完成会话并处理音频"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理音频失败: {e}")
        raise HTTPException(status_code=500, detail="处理音频失败")


@router.post("/audio/session/set", tags=["Audio"])
async def set_current_session(request: SetCurrentSessionRequest):
    """设置当前活跃会话"""
    try:
        session_service.set_current_session(request.session_id)
        return {"message": "当前会话设置成功", "session_id": request.session_id}
    except Exception as e:
        logger.error(f"设置当前会话失败: {e}")
        raise HTTPException(status_code=500, detail="设置当前会话失败")


@router.get("/audio/session/current", response_model=CurrentSessionResponse, tags=["Audio"])
async def get_current_session():
    """获取当前活跃会话"""
    try:
        current_session_id = session_service.get_current_session()
        return CurrentSessionResponse(
            session_id=current_session_id,
            status="active" if current_session_id else "none"
        )
    except Exception as e:
        logger.error(f"获取当前会话失败: {e}")
        raise HTTPException(status_code=500, detail="获取当前会话失败")


# =============== 批量转录API ===============

@router.post("/batch-transcription", tags=["Batch Transcription"])
async def batch_transcription(
    audio_file: UploadFile = File(..., description="音频文件 (WAV 或 MP3 格式)"),
    current_user: User = Depends(get_current_user_from_header)
):
    """批量音频转录端点"""
    try:
        logger.info(f"🎵 收到批量转录请求，用户: {current_user.id}, 文件: {audio_file.filename}")
        
        # Validate file format - support multiple MIME type variants
        valid_content_types = [
            "audio/wav", "audio/x-wav", "audio/wave",  # WAV variants
            "audio/mpeg", "audio/mp3", "audio/mpeg3"   # MP3 variants
        ]
        
        logger.info(f"🔍 文件MIME类型: {audio_file.content_type}")
        
        if not audio_file.content_type or audio_file.content_type not in valid_content_types:
            logger.error(f"❌ 不支持的文件格式: {audio_file.content_type}")
            raise HTTPException(
                status_code=400, 
                detail=f"仅支持 WAV 和 MP3 格式的音频文件，当前格式: {audio_file.content_type}"
            )
        
        # Read audio file data
        audio_data = await audio_file.read()
        if not audio_data:
            raise HTTPException(status_code=400, detail="音频文件为空")
        
        # Determine file format
        file_format = "mp3"  # default to mp3
        wav_types = ["audio/wav", "audio/x-wav", "audio/wave"]
        if audio_file.content_type in wav_types:
            file_format = "wav"
        
        logger.info(f"📁 处理文件: {audio_file.filename}, 大小: {len(audio_data)} bytes, 格式: {file_format}")
        
        # Process audio file with batch transcription service
        result = await batch_transcription_service.process_audio_file(
            audio_file_data=audio_data,
            original_filename=audio_file.filename or "unknown.mp3",
            user_id=current_user.id,
            file_format=file_format
        )
        
        logger.info(f"✅ 批量转录完成: session_id={result.session_id}")
        
        # Return comprehensive result
        return {
            "message": "批量转录完成",
            "status": "completed",
            "session_id": result.session_id,
            "audio_file_id": result.audio_file_id,
            "transcription_id": result.transcription_id,
            "statistics": {
                "total_segments": result.total_segments,
                "total_duration_seconds": result.total_duration,
                "speaker_count": result.speaker_count,
                "transcription_length": len(result.transcription_content)
            },
            "transcription": {
                "content": result.transcription_content,
                "segments": result.segments
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 批量转录失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量转录失败: {str(e)}")


@router.get("/audio/cache/status", response_model=AudioCacheStatusResponse, tags=["Audio"])
async def get_audio_cache_status():
    """获取音频缓存状态"""
    try:
        cache_status = cache_manager.get_cache_status()
        
        return AudioCacheStatusResponse(
            total_sessions=cache_status["total_sessions"],
            cache_size_mb=cache_status["cache_size_mb"],
            active_sessions=cache_status["active_sessions"],
            oldest_session=cache_status.get("oldest_session"),
            cache_memory_usage=cache_status.get("memory_usage", {})
        )
    except Exception as e:
        logger.error(f"获取缓存状态失败: {e}")
        raise HTTPException(status_code=500, detail="获取缓存状态失败")
