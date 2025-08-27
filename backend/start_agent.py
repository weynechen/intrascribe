#!/usr/bin/env python3
"""
启动LiveKit Agent的独立脚本
用于替换原有的FastRTC实时转录功能
"""
import logging
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

def main():
    """启动LiveKit Agent"""
    try:
        logger.info("🚀 启动 Intrascribe LiveKit Agent (官方标准AgentSession)")
        logger.info("📝 确保以下环境变量已配置:")
        logger.info(f"   - LIVEKIT_URL: {os.getenv('LIVEKIT_URL', '未设置')}")
        logger.info(f"   - LIVEKIT_API_KEY: {'已设置' if os.getenv('LIVEKIT_API_KEY') else '未设置'}")
        logger.info(f"   - LIVEKIT_API_SECRET: {'已设置' if os.getenv('LIVEKIT_API_SECRET') else '未设置'}")
        
        # 直接调用agent模块的main函数
        from app.livekit_agent_session import main as agent_main
        agent_main()
        
    except Exception as e:
        logger.error(f"❌ 启动Agent失败: {e}")
        raise

if __name__ == "__main__":
    main()
