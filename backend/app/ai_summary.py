import asyncio
import time
import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import litellm
from litellm import acompletion

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """模型配置数据类"""
    name: str
    model: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    max_tokens: int = 2000
    temperature: float = 0.7
    priority: int = 1
    enabled: bool = True


class AISummaryService:
    """AI总结服务"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.models: List[ModelConfig] = []
        self.retry_config = config.get("retry", {})
        self.fallback_config = config.get("fallback", {})
        self.prompts_config = config.get("prompts", {})
        
        # 初始化模型配置
        self._init_models()
        
        # 配置LiteLLM
        self._configure_litellm()
        
    def _init_models(self):
        """初始化模型配置"""
        models_config = self.config.get("models", [])
        
        for model_config in models_config:
            if model_config.get("enabled", True):
                self.models.append(ModelConfig(**model_config))
        
        # 按优先级排序
        self.models.sort(key=lambda x: x.priority)
        
        if self.models:
            logger.info(f"已加载 {len(self.models)} 个AI模型配置")
            for model in self.models:
                logger.info(f"  - {model.name}: {model.model} (优先级: {model.priority})")
        else:
            logger.warning("未找到可用的AI模型配置")
    
    def _configure_litellm(self):
        """配置LiteLLM"""
        # 设置日志级别
        litellm.set_verbose = False
        
        # 设置超时
        timeout = self.retry_config.get("timeout", 30)
        litellm.request_timeout = timeout
        
        logger.info("LiteLLM配置完成")
    
    async def generate_summary(self, transcription: str, template_content: str = None) -> Tuple[str, Dict[str, Any]]:
        """
        Generate AI summary
        
        Args:
            transcription: transcription text
            template_content: optional template content
            
        Returns:
            Tuple[summary content, metadata]
        """
        if not transcription.strip():
            return "转录内容为空，无法生成总结。", {"error": "empty_transcription"}
        
        # 构建提示词
        base_system_prompt = self.prompts_config.get("system_prompt", "你是一个专业的总结和记录的高手。你必须使用Markdown格式输出。")
        
        if template_content:
            # 将template放在system_prompt中，更符合角色定义的语义
            system_prompt = f"""{base_system_prompt}

你需要严格按照以下模板格式进行总结。请注意：
1. 模板是纯文本结构化描述，描述了期望的输出格式和内容要求
2. 请严格遵循模板的结构和格式，用实际内容填充各个部分
3. 保持模板的markdown格式和层次结构
4. 如果某些信息在转录中没有明确提及，可以标注为"未提及"或根据上下文合理推断
5. 确保输出内容完整、准确、结构清晰

输出格式模板：
{template_content}"""
            
            # user_prompt只需要提供转录内容
            user_prompt = f"请按照系统提示中的模板格式，对以下转录内容进行结构化总结：\n\n{transcription}。\n\n以上为内容，请按照模板格式进行总结。"
        else:
            # 使用默认提示词
            system_prompt = base_system_prompt
            user_prompt_template = self.prompts_config.get("user_prompt_template", "请总结以下内容：\n{transcription}")
            user_prompt = user_prompt_template.format(transcription=transcription)
        
        # 尝试使用各个模型
        for model_config in self.models:
            try:
                logger.info(f"尝试使用模型: {model_config.name}")
                logger.info(f"system_prompt: {system_prompt}")
                logger.info(f"user_prompt: {user_prompt}")
                summary, metadata = await self._call_model(model_config, system_prompt, user_prompt)
                
                if summary:
                    metadata.update({
                        "model_used": model_config.name,
                        "model_id": model_config.model,
                        "success": True
                    })
                    logger.info(f"使用模型 {model_config.name} 成功生成总结")
                    return summary, metadata
                    
            except Exception as e:
                logger.warning(f"模型 {model_config.name} 调用失败: {e}")
                continue
        
        # 所有模型都失败，使用回退策略
        return await self._handle_fallback(transcription)
    
    async def generate_title(self, transcription: str, summary: str = None) -> Tuple[str, Dict[str, Any]]:
        """
        生成AI标题
        
        Args:
            transcription: 转录文本
            summary: 可选的总结文本，用于更好地生成标题
            
        Returns:
            Tuple[标题内容, 元数据]
        """
        if not transcription.strip():
            return "无标题内容", {"error": "empty_transcription"}
        
        # 构建标题生成的提示词
        system_prompt = "你是一个专业的会议记录助手，负责为会议内容生成简洁明了的标题。"
        
        if summary:
            # 如果有总结，基于总结和转录生成标题
            user_prompt = f"""请基于以下会议总结和转录内容，生成一个简洁明了的标题（10-15个字）：

总结内容：
{summary}

转录内容：
{transcription[:500]}...

要求：
1. 标题要能准确概括会议的主要内容和目的
2. 长度控制在10-15个字
3. 直接返回标题，不要其他解释
4. 使用中文
"""
        else:
            # 仅基于转录内容生成标题
            user_prompt = f"""请基于以下会议转录内容，生成一个简洁明了的标题（10-15个字）：

转录内容：
{transcription[:500]}...

要求：
1. 标题要能准确概括会议的主要内容和目的
2. 长度控制在10-15个字
3. 直接返回标题，不要其他解释
4. 使用中文
"""
        
        # 尝试使用各个模型
        for model_config in self.models:
            try:
                logger.info(f"尝试使用模型 {model_config.name} 生成标题")
                title, metadata = await self._call_model(model_config, system_prompt, user_prompt)
                
                if title:
                    # 清理标题，移除多余的内容
                    title = title.strip().replace('"', '').replace("'", "")
                    # 如果标题太长，截断到合适长度
                    if len(title) > 20:
                        title = title[:17] + "..."
                    
                    metadata.update({
                        "model_used": model_config.name,
                        "model_id": model_config.model,
                        "success": True,
                        "title_type": "summary_based" if summary else "transcription_based"
                    })
                    logger.info(f"使用模型 {model_config.name} 成功生成标题: {title}")
                    return title, metadata
                    
            except Exception as e:
                logger.warning(f"模型 {model_config.name} 生成标题失败: {e}")
                continue
        
        # 所有模型都失败，使用回退策略
        return await self._handle_title_fallback(transcription)
    
    async def _call_model(self, model_config: ModelConfig, system_prompt: str, user_prompt: str) -> Tuple[str, Dict[str, Any]]:
        """
        调用特定模型
        
        Args:
            model_config: 模型配置
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            
        Returns:
            Tuple[响应内容, 元数据]
        """
        start_time = time.time()
        
        try:
            # 构建消息
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # 准备API调用参数
            kwargs = {
                "model": model_config.model,
                "messages": messages,
                "max_tokens": model_config.max_tokens,
                "temperature": model_config.temperature,
            }
            
            # 如果有API key，添加到环境或参数中
            if model_config.api_key:
                # 根据模型类型设置不同的API key环境变量
                if "openai" in model_config.model.lower():
                    import os
                    os.environ["OPENAI_API_KEY"] = model_config.api_key
                elif "claude" in model_config.model.lower():
                    import os
                    os.environ["ANTHROPIC_API_KEY"] = model_config.api_key
                # 可以根据需要添加更多模型的API key设置
            
            if model_config.api_base:
                kwargs["api_base"] = model_config.api_base
            
            # 调用模型
            response = await acompletion(**kwargs)
            
            # 提取响应内容
            content = response.choices[0].message.content
            
            # 清理响应内容
            content = self._clean_llm_response(content)
            
            # 计算处理时间
            processing_time = (time.time() - start_time) * 1000
            
            # 构建元数据
            metadata = {
                "total_processing_time": processing_time,
                "transcription_length": len(user_prompt),
                "timestamp": int(time.time()),
                "tokens_used": getattr(response.usage, 'total_tokens', 0) if hasattr(response, 'usage') else 0,
            }
            
            # 添加成本信息 - 处理LiteLLM的成本计算
            try:
                # LiteLLM可能在response对象的不同位置返回成本信息
                cost_usd = None
                
                # 尝试从response._response_ms中获取成本
                if hasattr(response, '_response_ms') and response._response_ms:
                    cost_usd = response._response_ms
                # 尝试从response中的其他成本属性获取
                elif hasattr(response, 'cost'):
                    cost_usd = response.cost
                elif hasattr(response, '_response_cost_usd'):
                    cost_usd = response._response_cost_usd
                # 尝试从usage中获取成本
                elif hasattr(response, 'usage') and hasattr(response.usage, 'cost'):
                    cost_usd = response.usage.cost
                elif hasattr(response, 'usage') and hasattr(response.usage, 'total_cost'):
                    cost_usd = response.usage.total_cost
                
                # 转换USD到cents并确保是整数
                if cost_usd is not None:
                    # 转换为分（cents）并四舍五入为整数
                    cost_cents = round(float(cost_usd) * 100)
                    metadata["cost_cents"] = cost_cents
                    logger.info(f"💰 成本计算: {cost_usd} USD = {cost_cents} cents")
                else:
                    # 如果没有成本信息，设置为0
                    metadata["cost_cents"] = 0
                    logger.debug("💰 未找到成本信息，设置为0")
                    
            except Exception as e:
                logger.warning(f"💰 成本计算失败: {e}")
                metadata["cost_cents"] = 0
            
            return content, metadata
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            metadata = {
                "error": str(e),
                "total_processing_time": processing_time,
                "timestamp": int(time.time()),
            }
            raise Exception(f"模型调用失败: {e}")
    
    async def _handle_fallback(self, transcription: str) -> Tuple[str, Dict[str, Any]]:
        """
        处理回退策略
        
        Args:
            transcription: 转录文本
            
        Returns:
            Tuple[回退总结, 元数据]
        """
        # 生成简单的基于规则的总结
        mock_summary = self._generate_mock_summary(transcription)
        
        metadata = {
            "error": "所有AI模型调用失败",
            "fallback_used": True,
            "timestamp": int(time.time()),
            "transcription_length": len(transcription)
        }
        
        return mock_summary, metadata
    
    def _generate_mock_summary(self, transcription: str) -> str:
        """
        生成基于规则的简单总结
        
        Args:
            transcription: 转录文本
            
        Returns:
            简单的总结文本
        """
        # 简单的文本分析
        word_count = len(transcription.split())
        char_count = len(transcription)
        
        # 提取一些关键信息（简单的关键词）
        keywords = []
        common_words = ['会议', '讨论', '决定', '计划', '项目', '方案', '问题', '解决', '目标', '时间']
        for word in common_words:
            if word in transcription:
                keywords.append(word)
        
        # 构建简单总结
        summary_parts = [
            f"本次会议/对话共包含约 {word_count} 个词，{char_count} 个字符。"
        ]
        
        if keywords:
            summary_parts.append(f"主要涉及：{', '.join(keywords[:5])}等话题。")
        
        # 提取前几句作为内容概述
        sentences = transcription.split('。')[:3]
        if sentences:
            content_preview = '。'.join(sentences)[:200] + "..."
            summary_parts.append(f"内容概述：{content_preview}")
        
        return "\n\n".join(summary_parts)
    
    async def _handle_title_fallback(self, transcription: str) -> Tuple[str, Dict[str, Any]]:
        """
        处理标题生成的回退策略
        
        Args:
            transcription: 转录文本
            
        Returns:
            Tuple[回退标题, 元数据]
        """
        from datetime import datetime
        
        # 生成基于时间的默认标题
        now = datetime.now()
        default_title = f"会议记录 {now.strftime('%Y-%m-%d %H:%M')}"
        
        metadata = {
            "error": "所有AI模型调用失败",
            "fallback_used": True,
            "timestamp": int(time.time()),
            "transcription_length": len(transcription)
        }
        
        return default_title, metadata
    
    def _clean_llm_response(self, content: str) -> str:
        """
        清理LLM响应内容
        
        Args:
            content: 原始响应内容
            
        Returns:
            清理后的内容
        """
        if not content:
            return ""
        
        # 移除多余的空白字符
        content = content.strip()
        
        # 移除可能的markdown格式
        content = re.sub(r'^```.*?\n', '', content, flags=re.MULTILINE)
        content = re.sub(r'\n```$', '', content)
        
        # 移除多余的换行
        content = re.sub(r'\n{3,}', '\n\n', content)

        # 移除<think> 和 </think> 标签
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        
        return content
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表"""
        return [
            {
                "name": model.name,
                "model": model.model,
                "enabled": model.enabled,
                "priority": model.priority
            }
            for model in self.models
        ]
    
    def get_config_status(self) -> Dict[str, Any]:
        """获取配置状态"""
        return {
            "total_models": len(self.models),
            "enabled_models": len([m for m in self.models if m.enabled]),
            "has_fallback": bool(self.fallback_config),
            "retry_config": self.retry_config
        } 