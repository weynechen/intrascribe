"""
intrascribe 应用入口
负责初始化和启动FastAPI应用
"""
import logging
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Tuple
import numpy as np
import json

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastrtc import (
    AdditionalOutputs,
    ReplyOnPause,
    Stream,
    get_current_context,
    audio_to_bytes,
    get_twilio_turn_credentials,
    AlgoOptions
)
import gradio as gr

# 导入新架构的模块
from app.config import settings
from app.api import router as api_router
from app.services import audio_transcription_service, cache_manager
from app.models import TranscriptionSegment

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 输出到控制台
    ],
    force=True  # 强制重新配置
)

# 设置具体模块的日志级别
logging.getLogger("app").setLevel(logging.INFO)
logging.getLogger("app.config").setLevel(logging.INFO)
logging.getLogger("app.services").setLevel(logging.INFO)
logging.getLogger("app.clients").setLevel(logging.INFO)
logging.getLogger("app.repositories").setLevel(logging.INFO)
logging.getLogger("app.api").setLevel(logging.INFO)
logging.getLogger("supabase").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("funasr").setLevel(logging.WARNING)
logging.getLogger("modelscope").setLevel(logging.WARNING)

# 确保app模块日志传播到根logger
app_logger = logging.getLogger("app")
app_logger.propagate = True

logger = logging.getLogger(__name__)
logger.info("🚀 日志系统初始化完成")

# 创建FastAPI应用
app = FastAPI(
    title="intrascribe API",
    description="自动语音识别与实时通信平台",
    version="1.0.0",
    debug=settings.debug
)

# 配置CORS - 支持开发环境和生产环境
allowed_origins = [
    "http://localhost:3000",  # 开发环境直接访问
    "http://127.0.0.1:3000",  # 本地开发环境
    "https://localhost",  # 本地HTTPS测试
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载API路由
app.include_router(api_router, prefix=f"/api/{settings.api_version}")

# 根目录挂载测试页面
@app.get("/")
def index():
    # rtc_config = get_twilio_turn_credentials() if get_space() else None
    rtc_config = None
    html_content = (cur_dir.parent / "index.html").read_text()
    html_content = html_content.replace("__RTC_CONFIGURATION__", json.dumps(rtc_config))
    return HTMLResponse(content=html_content)

# =============== 异常处理器 ===============
from app.dependencies import AuthenticationError, AuthorizationError, BusinessLogicError, ExternalServiceError
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError):
    """认证错误处理器"""
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "code": "AUTHENTICATION_ERROR",
                "message": str(exc),
                "request_id": getattr(request.state, 'request_id', None),
                "path": request.url.path
            }
        }
    )

@app.exception_handler(AuthorizationError)
async def authorization_error_handler(request: Request, exc: AuthorizationError):
    """授权错误处理器"""
    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "code": "AUTHORIZATION_ERROR",
                "message": str(exc),
                "request_id": getattr(request.state, 'request_id', None),
                "path": request.url.path
            }
        }
    )

@app.exception_handler(BusinessLogicError)
async def business_logic_error_handler(request: Request, exc: BusinessLogicError):
    """业务逻辑错误处理器"""
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "BUSINESS_LOGIC_ERROR",
                "message": str(exc),
                "request_id": getattr(request.state, 'request_id', None),
                "path": request.url.path
            }
        }
    )

@app.exception_handler(ExternalServiceError)
async def external_service_error_handler(request: Request, exc: ExternalServiceError):
    """外部服务错误处理器"""
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "code": "EXTERNAL_SERVICE_ERROR",
                "message": str(exc),
                "request_id": getattr(request.state, 'request_id', None),
                "path": request.url.path
            }
        }
    )

logger.info("✅ FastAPI应用初始化完成")


# =============== FastRTC 集成 ===============

async def transcribe(audio: Tuple[int, np.ndarray]):
    """
    使用本地 ASR 模型进行语音转录 - 集成到新架构
    """
    try:
        sample_rate, audio_data = audio
        current_time = datetime.now()
        context = get_current_context()
        session_id = context.webrtc_id
       
        # 添加音频数据格式调试
        logger.info(f"🎵 接收音频数据: 采样率={sample_rate}, 数据类型={type(audio_data)}, 形状={getattr(audio_data, 'shape', 'N/A')}")
        logger.info(f"📋 会话ID: {session_id}")
        
        # 使用新架构的音频转录服务，传递会话ID
        transcription_result = await audio_transcription_service.transcribe_audio(audio, session_id)
        
        if transcription_result and transcription_result.get('text'):
            logger.info(f"🎙️ 转录完成: {transcription_result}")
            
            # 直接返回结构化的转录数据，用JSON格式传递
            yield AdditionalOutputs(json.dumps(transcription_result, ensure_ascii=False))
        else:
            # 如果转录失败或为空，返回空内容
            yield AdditionalOutputs("")
        
    except Exception as e:
        logger.error(f"转录过程中发生错误: {e}")
        # 构造错误消息的结构化格式
        error_result = {
            "index": 0,
            "speaker": "system",
            "timestamp": "[00:00:00:000,00:00:00:000]",
            "text": f"转录错误: {str(e)}",
            "is_final": True
        }
        yield AdditionalOutputs(json.dumps(error_result, ensure_ascii=False))


# 创建FastRTC Stream
stream = Stream(
    ReplyOnPause(transcribe,
                 input_sample_rate= 16000,
                 output_sample_rate = 16000,
                 algo_options=AlgoOptions(
                     audio_chunk_duration=1.0,  # 将音频块持续时间增加到1秒
                     started_talking_threshold=0.2,  # 开始说话的阈值
                     speech_threshold=0.1,  # 暂停检测的阈值
                 )
                 ),
    modality="audio",
    mode="send",
    additional_inputs=None,
    additional_outputs_handler=lambda a, b: b,
    # rtc_configuration=get_twilio_turn_credentials() if get_space() else None,
    concurrency_limit=100, 
    # time_limit=90 if get_space() else None,
)

# 挂载FastRTC到FastAPI
stream.mount(app)

logger.info("✅ FastRTC集成完成")

# =============== FastRTC SSE端点 ===============
from pydantic import BaseModel

class SendInput(BaseModel):
    webrtc_id: str
    transcript: str

@app.post("/send_input")
def send_input(body: SendInput):
    """向FastRTC流发送输入"""
    stream.set_input(body.webrtc_id, body.transcript)
    return {"success": True}

@app.get("/transcript")
def transcript_endpoint(webrtc_id: str):
    """实时转录SSE端点"""
    async def output_stream():
        async for output in stream.output_stream(webrtc_id):
            # 现在output.args[0]是JSON格式的转录数据
            transcript_json = output.args[0]
            
            # 只有当转录数据非空时才发送
            if transcript_json and transcript_json.strip():
                try:
                    # 尝试解析JSON数据
                    transcript_event = json.loads(transcript_json)
                    
                    # 验证数据格式是否符合设计文档要求
                    if (isinstance(transcript_event, dict) and 
                        transcript_event.get('text') and
                        transcript_event.get('index') is not None and
                        transcript_event.get('speaker') and
                        transcript_event.get('timestamp') and
                        transcript_event.get('timestamp').startswith('[') and
                        transcript_event.get('timestamp').endswith(']')):
                        
                        yield f"event: output\ndata: {json.dumps(transcript_event, ensure_ascii=False)}\n\n"
                    else:
                        logger.warning(f"收到不符合格式要求的转录数据: {transcript_event}")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"解析转录JSON数据失败: {e}, 原始数据: {transcript_json}")
                    # 不再提供fallback处理，严格要求符合设计文档格式
                    logger.error("转录数据格式不正确，已跳过该数据")

    return StreamingResponse(output_stream(), media_type="text/event-stream")



cur_dir = Path(__file__).parent


# =============== 应用启动信息 ===============

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("🎬 intrascribe 应用启动中...")
    logger.info(f"📖 配置信息:")
    logger.info(f"  - Debug模式: {settings.debug}")
    logger.info(f"  - API版本: {settings.api_version}")
    logger.info(f"  - Supabase URL: {settings.supabase.url}")
    logger.info(f"  - STT模型目录: {settings.stt.model_dir}")
    logger.info(f"  - 音频输出目录: {settings.stt.output_dir}")
    
    # 打印所有注册的路由
    logger.info("🛣️ 已注册的路由:")
    from fastapi.routing import APIRoute, Mount
    
    def print_routes(routes, prefix=""):
        for route in routes:
            if isinstance(route, APIRoute):
                methods = ", ".join(route.methods)
                logger.info(f"  - [{methods}] {prefix}{route.path}")
            elif isinstance(route, Mount):
                logger.info(f"  - [MOUNT] {prefix}{route.path}")
                if hasattr(route, 'routes'):
                    print_routes(route.routes, prefix + route.path)
    
    print_routes(app.routes)
    
    logger.info("🚀 应用启动完成！")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("🛑 intrascribe 应用正在关闭...")
    
    # 清理会话缓存
    active_sessions = list(cache_manager.session_caches.keys())
    if active_sessions:
        logger.info(f"🧹 清理 {len(active_sessions)} 个活跃会话缓存")
        for session_id in active_sessions:
            cache_manager.remove_session_cache(session_id)
    
    logger.info("✅ 应用关闭完成")


if __name__ == "__main__":
    # 如果直接运行此文件，启动开发服务器
    import uvicorn
    
    logger.info("🔧 开发模式启动")
    # 配置uvicorn使用我们的日志配置，而不是默认配置
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_config=None,  # 禁用uvicorn默认日志配置
        access_log=True,  # 启用访问日志
        log_level="info"  # 设置日志级别
    )